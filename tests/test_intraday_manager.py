import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from market_bot.accuracy_filters import AccuracyFilters
from market_bot.bar_builder import Bar
from market_bot.intraday_manager import IntradayManager
from market_bot.kite_main import KiteTradingBot
from market_bot.trade_journal import TradeJournal
from market_bot.weekly_report import summarize_best_setup_windows


def test_preclose_exit_and_market_close_are_distinct_boundaries():
    manager = IntradayManager()

    with patch("market_bot.intraday_manager.datetime") as clock:
        clock.now.return_value = datetime(2026, 9, 17, 15, 20)
        assert manager.should_exit_all_positions() is True
        assert manager.is_market_closed() is False

        clock.now.return_value = datetime(2026, 9, 17, 15, 30)
        assert manager.is_market_closed() is True


def test_index_quantity_uses_complete_lot_size():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)

    assert manager.calculate_position_size("NIFTY", 100.0, 90.0) == 100
    assert manager.calculate_position_size("BANKNIFTY", 100.0, 90.0) == 75


def test_position_size_skips_when_one_lot_exceeds_risk_budget():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)

    assert manager.calculate_position_size("NIFTY", 100.0, 70.0) == 0


def test_daily_loss_limit_caps_per_trade_risk_budget():
    manager = IntradayManager(
        account_size=100_000,
        risk_per_trade_pct=1.0,
        daily_max_loss=250.0,
    )

    assert manager.max_risk_per_trade == 250.0
    assert manager.calculate_position_size("NIFTY", 100.0, 90.0) == 0


def test_one_minute_volatility_floor_uses_configurable_small_percentage():
    filters = AccuracyFilters()
    history = [
        {"high": 25015.0, "low": 24985.0, "close": 25000.0}
        for _ in range(14)
    ]

    assert filters.is_volatility_acceptable(history) is True
    strict_filters = AccuracyFilters(min_volatility_pct=0.2)
    allowed, reason = strict_filters.validate_entry_with_reason(
        symbol="NIFTY",
        signal="BUY",
        score=85,
        history=history,
        current_bar={"close": 25001.0},
        previous_bar={"close": 25000.0},
        current_time=0.0,
        hour=10,
        minute=0,
    )

    assert allowed is False
    assert reason == "volatility"


def test_paper_position_size_simulates_one_lot_when_risk_budget_is_too_small():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)

    assert (
        manager.calculate_position_size(
            "NIFTY", 100.0, 70.0, allow_paper_lot=True
        )
        == 50
    )


def test_close_trade_records_exit_reason(tmp_path):
    path = tmp_path / "trades.jsonl"
    journal = TradeJournal(str(path))
    journal.log_trade({"ticker": "NIFTY", "action": "BUY", "entry": 100.0})

    journal.close_trade("NIFTY", 101.0, "BUY", "MARKET_CLOSE_FORCED_EXIT")

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["status"] == "closed"
    assert record["reason"] == "MARKET_CLOSE_FORCED_EXIT"


def test_consecutive_losses_trigger_circuit_breaker():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)
    manager.max_consecutive_losses = 2

    assert manager.can_open_trade("NIFTY", "BUY")[0] is True

    manager.record_trade_close("NIFTY", "STOP_LOSS", pnl=-200.0)
    assert manager.can_open_trade("NIFTY", "BUY")[0] is True

    manager.record_trade_close("NIFTY", "STOP_LOSS", pnl=-300.0)
    allowed, reason = manager.can_open_trade("NIFTY", "BUY")
    assert allowed is False
    assert "consecutive loss" in reason.lower()


def test_symbol_remains_blocked_after_trade_closes_for_the_session():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)
    manager.record_trade_open("NIFTY", "BUY")
    manager.record_trade_close("NIFTY", "STOP_LOSS", pnl=-200.0)

    allowed, reason = manager.can_open_trade("NIFTY", "SELL")

    assert allowed is False
    assert "already traded this session" in reason.lower()


def test_session_trades_are_restored_from_the_journal():
    manager = IntradayManager()
    manager.restore_session_trades([
        {
            "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
            "ticker": "BANKNIFTY_CE",
            "status": "closed",
        }
    ])

    allowed, reason = manager.can_open_trade("BANKNIFTY_CE", "BUY")

    assert allowed is False
    assert "already traded this session" in reason.lower()


def test_late_window_guard_uses_configured_ist_bounds_and_can_be_disabled():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"late_window_start": "12:00", "late_window_end": "13:00"}
    ist = ZoneInfo("Asia/Kolkata")

    assert bot._late_window_blocked(datetime(2026, 9, 26, 12, 0, tzinfo=ist)) is True
    assert bot._late_window_blocked(datetime(2026, 9, 26, 12, 59, tzinfo=ist)) is True
    assert bot._late_window_blocked(datetime(2026, 9, 26, 13, 0, tzinfo=ist)) is False
    assert bot._late_window_blocked(datetime(2026, 9, 26, 11, 59, tzinfo=ist)) is False
    bot.config["late_window_enabled"] = False
    assert bot._late_window_blocked(datetime(2026, 9, 26, 12, 30, tzinfo=ist)) is False


def test_live_entry_aborts_when_fill_slippage_exceeds_risk_cap():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"trading_mode": "intraday_futures"}
    bot.live_orders_enabled = True
    bot.paper_trading_enabled = False
    bot._entries_paused = False
    bot._risk_state_reconciled = True
    bot.intraday_manager = IntradayManager(account_size=10_000, risk_per_trade_pct=1.0)
    bot.kite_stream = Mock()
    bot.kite_stream.is_connected = True
    bot.kite_stream.place_market_order.return_value = "entry-order"
    bot.kite_stream.wait_for_order_fill.return_value = {
        "filled_quantity": 100,
        "average_price": 200.0,
    }
    bot.kite_stream.place_protective_stop_order.return_value = "stop-order"
    bot.trade_journal = Mock()
    bot.trade_journal.get_open_trade.return_value = None
    bot.telegram_notifier = Mock()
    bot._abort_live_entry = Mock()

    result = bot._handle_buy_signal("NIFTY", 100.0, 80)

    assert result == "risk_blocked:filled_risk_exceeds_limit"
    bot.kite_stream.place_protective_stop_order.assert_called_once()
    bot._abort_live_entry.assert_called_once_with("NIFTY", 200.0, "RISK_LIMIT_EXCEEDED")


def test_live_entry_aborts_when_protective_stop_placement_fails():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"trading_mode": "intraday_futures"}
    bot.live_orders_enabled = True
    bot.paper_trading_enabled = False
    bot._entries_paused = False
    bot._risk_state_reconciled = True
    bot.intraday_manager = IntradayManager()
    bot.kite_stream = Mock()
    bot.kite_stream.is_connected = True
    bot.kite_stream.place_market_order.return_value = "entry-order"
    bot.kite_stream.wait_for_order_fill.return_value = {
        "filled_quantity": 50,
        "average_price": 100.0,
    }
    bot.kite_stream.place_protective_stop_order.side_effect = RuntimeError("rejected")
    bot.trade_journal = Mock()
    bot.trade_journal.get_open_trade.return_value = None
    bot.telegram_notifier = Mock()
    bot._abort_live_entry = Mock()

    result = bot._handle_buy_signal("NIFTY", 100.0, 80)

    assert result == "protective_stop_failed"
    assert bot.intraday_manager.session_trade_symbols == {"NIFTY"}
    bot._abort_live_entry.assert_called_once_with("NIFTY", 100.0, "PROTECTION_FAILED")


def test_failed_live_exit_replaces_canceled_stop_and_pauses_entries():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"max_exit_retries": 1}
    bot.live_orders_enabled = True
    bot.intraday_manager = IntradayManager()
    bot.intraday_manager.register_position("NIFTY", "BUY", 50, 100.0, 99.0, 102.0)
    bot.intraday_manager.active_positions["NIFTY"]["protection_order_id"] = "old-stop"
    bot.kite_stream = Mock()
    bot.kite_stream.get_position_quantity.return_value = 50
    bot.kite_stream.place_market_order.side_effect = RuntimeError("exit rejected")
    bot.kite_stream.place_protective_stop_order.return_value = "replacement-stop"
    bot.trade_journal = Mock()
    bot.trade_journal.get_open_trade.return_value = {"ticker": "NIFTY", "action": "BUY"}
    bot.telegram_notifier = Mock()
    bot._reconcile_after_order_failure = Mock()

    bot._close_position("NIFTY", 99.0, "STOP_LOSS")

    position = bot.intraday_manager.active_positions["NIFTY"]
    assert position["quantity"] == 50
    assert position["protection_order_id"] == "replacement-stop"
    assert bot._entries_paused is True
    assert bot._risk_state_reconciled is False
    bot.kite_stream.place_protective_stop_order.assert_called_once_with(
        "NIFTY", "BUY", 50, 99.0
    )
    bot._reconcile_after_order_failure.assert_called_once_with("NIFTY")


def test_aborted_live_fill_is_journaled_before_emergency_exit():
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = IntradayManager()
    bot.intraday_manager.register_position("NIFTY", "BUY", 50, 100.0, 99.0, 102.0)
    bot.trade_journal = Mock()
    bot.trade_journal.get_open_trade.return_value = None
    bot._close_position = Mock()
    bot._reconcile_after_order_failure = Mock()

    bot._abort_live_entry("NIFTY", 100.0, "PROTECTION_FAILED")

    journal_entry = bot.trade_journal.log_trade.call_args.args[0]
    assert journal_entry["ticker"] == "NIFTY"
    assert journal_entry["status"] == "open"
    bot._close_position.assert_called_once_with("NIFTY", 100.0, "PROTECTION_FAILED")


def test_live_reconciliation_rejects_open_trade_without_recorded_protection():
    bot = object.__new__(KiteTradingBot)
    bot.kite_stream = SimpleNamespace(
        get_positions=lambda: [{"tradingsymbol": "NIFTY_FUT", "quantity": 50}],
        get_completed_orders=lambda: [],
        contract_symbols={"NIFTY": "NIFTY_FUT"},
    )
    bot.trade_journal = SimpleNamespace(read_trades=lambda: [{
        "ticker": "NIFTY",
        "action": "BUY",
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "status": "open",
    }])
    bot.intraday_manager = IntradayManager()

    try:
        bot._reconcile_live_state()
    except RuntimeError as error:
        assert "no recorded protective stop" in str(error)
    else:
        raise AssertionError("Reconciliation should fail without a recorded protective stop")


def test_close_position_updates_daily_risk_state():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)
    manager.register_position("NIFTY", "BUY", 50, 100.0, 99.0, 102.0)

    closed = manager.close_position("NIFTY", 99.0, "STOP_LOSS")
    manager.record_trade_close("NIFTY", "STOP_LOSS", closed["pnl_rupees"])

    assert manager.daily_pnl == -50.0
    assert manager.consecutive_losses == 1


def test_buy_trailing_stop_ratchets_up_after_half_target_move():
    manager = IntradayManager()
    manager.register_position("NIFTY_CE", "BUY", 1, 55.0, 50.0, 85.0)

    assert manager.update_trailing_stop("NIFTY_CE", 70.0) == 62.5
    assert manager.update_trailing_stop("NIFTY_CE", 80.0) == 72.5
    assert manager.update_trailing_stop("NIFTY_CE", 75.0) == 72.5


def test_sell_trailing_stop_ratchets_down_after_half_target_move():
    manager = IntradayManager()
    manager.register_position("NIFTY_PE", "SELL", 1, 55.0, 60.0, 25.0)

    assert manager.update_trailing_stop("NIFTY_PE", 40.0) == 47.5
    assert manager.update_trailing_stop("NIFTY_PE", 30.0) == 37.5
    assert manager.update_trailing_stop("NIFTY_PE", 35.0) == 37.5


def test_tick_exit_holds_past_target_until_trailing_stop_is_hit():
    manager = IntradayManager()
    manager.register_position("NIFTY_CE", "BUY", 1, 55.0, 50.0, 85.0)
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot._close_position = Mock()

    assert bot._check_position_exit("NIFTY_CE", 85.0) is None
    assert bot._check_position_exit("NIFTY_CE", 76.0) == "TRAILING_STOP"
    bot._close_position.assert_called_once_with("NIFTY_CE", 76.0, "TRAILING_STOP")


def test_staged_buy_target_advances_by_configured_increment():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        1,
        100.0,
        80.0,
        140.0,
        signal_score=78,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
    )

    manager.update_trailing_stop("NIFTY_CE", 140.0)
    position = manager.active_positions["NIFTY_CE"]

    assert position["target_stage"] == 1
    assert position["take_profit"] == 150.0
    assert position["trailing_stop"] == 130.0
    assert position["signal_score"] == 78


def test_staged_sell_target_advances_by_configured_increment():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_PE",
        "SELL",
        1,
        100.0,
        120.0,
        60.0,
        signal_score=85,
        staged_targets_enabled=True,
        target_increment_pct=0.20,
    )

    manager.update_trailing_stop("NIFTY_PE", 60.0)
    position = manager.active_positions["NIFTY_PE"]

    assert position["target_stage"] == 1
    assert position["take_profit"] == 40.0
    assert position["trailing_stop"] == 70.0


def test_staged_target_does_not_move_back_when_price_retraces():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        1,
        100.0,
        80.0,
        140.0,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
    )

    manager.update_trailing_stop("NIFTY_CE", 140.0)
    manager.update_trailing_stop("NIFTY_CE", 145.0)
    manager.update_trailing_stop("NIFTY_CE", 135.0)

    position = manager.active_positions["NIFTY_CE"]
    assert position["take_profit"] == 150.0
    assert position["trailing_stop"] == 135.0


def test_target_advance_updates_open_journal_and_telegram(tmp_path):
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        1,
        100.0,
        80.0,
        140.0,
        signal_score=85,
        staged_targets_enabled=True,
        target_increment_pct=0.20,
    )
    journal = TradeJournal(str(tmp_path / "trades.jsonl"))
    journal.log_trade(
        {
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "entry": 100.0,
            "stop_loss": 80.0,
            "take_profit": 140.0,
        }
    )
    notifier = Mock()
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot.trade_journal = journal
    bot.telegram_notifier = notifier
    bot._close_position = Mock()

    assert bot._check_position_exit("NIFTY_CE", 140.0) is None

    open_trade = journal.get_open_trade("NIFTY_CE", "BUY")
    assert open_trade["take_profit"] == 160.0
    assert open_trade["target_stage"] == 1
    notifier.send_message.assert_called_once()
    assert "Next target: 160.00" in notifier.send_message.call_args.args[0]


def test_disabling_trailing_keeps_fixed_target_exit():
    manager = IntradayManager(trailing_enabled=False)
    manager.register_position("NIFTY", "BUY", 1, 55.0, 50.0, 85.0)
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot._close_position = Mock()

    assert bot._check_position_exit("NIFTY", 85.0) == "TAKE_PROFIT"


def test_adaptive_score_threshold_rises_for_weak_symbol_performance():
    filters = AccuracyFilters()

    assert filters.get_min_score(recent_trades=7, recent_win_rate=20.0) >= 92
    assert filters.get_min_score(recent_trades=7, recent_win_rate=72.0) <= 90


def test_maximum_engine_score_is_not_rejected_by_accuracy_filter():
    filters = AccuracyFilters()

    assert filters.should_enter_trade(
        signal="BUY",
        score=85,
        volatility_acceptable=True,
        confirmation=True,
    ) is True


def test_option_volatility_filter_uses_underlying_signal_bars():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_both",
        "instrument_tokens": {"NIFTY": 1},
        "benchmark_symbols": [],
        "late_window_enabled": False,
    }
    bot.symbol_map = {100: "NIFTY_CE"}
    option_bars = [
        Bar(datetime(2026, 9, 24, 10, index), 100, 101, 99, 100, 10)
        for index in range(30)
    ]
    underlying_bars = [
        Bar(datetime(2026, 9, 24, 10, index), 25000, 25010, 24990, 25000, 100)
        for index in range(30)
    ]
    bot.bar_builder = Mock()
    bot.bar_builder.get_bars.side_effect = lambda token, limit: (
        underlying_bars if token == 1 else option_bars
    )
    bot.intraday_manager = Mock()
    bot.intraday_manager.should_exit_all_positions.return_value = False
    bot.use_market_context = False
    bot.benchmark_symbol = "NIFTY"
    bot.news_monitor = None
    bot.premarkarket_candidates = []
    bot.option_quote_cache = {"NIFTY_CE": {"last_price": 100}}
    bot.latest_prices = {}
    bot.kite_stream = SimpleNamespace(contract_expiries={})
    bot._preferred_option_symbol = Mock(return_value="NIFTY_CE")
    bot._option_quality_gate = Mock(return_value=(True, "OK"))
    bot._record_decision = Mock()
    bot.accuracy_filters = Mock()
    bot.accuracy_filters.validate_entry_with_reason.return_value = (False, "volatility")

    with patch("market_bot.kite_main.market_session_state", return_value="REGULAR_SESSION"), \
        patch(
            "market_bot.kite_main.score_market",
            return_value=SimpleNamespace(signal="BUY", score=80, reasons=[]),
        ):
        bot.on_bar_complete("100", option_bars[-1])

    validated_history = bot.accuracy_filters.validate_entry_with_reason.call_args.kwargs[
        "history"
    ]
    assert validated_history == [item.to_dict() for item in underlying_bars]


def test_option_quality_gate_allows_reasonable_low_premium_when_volume_and_oi_are_healthy():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "option_min_premium": 25.0,
        "option_max_premium": 550.0,
        "option_min_volume": 500,
        "option_min_oi": 1000,
        "option_iv_min": 0.15,
        "option_iv_max": 0.85,
    }
    bot.option_quote_cache = {
        "TCS_CE": {
            "last_price": 18.5,
            "volume": 900,
            "oi": 2200,
            "iv": 0.42,
        }
    }

    allowed, reason = bot._option_quality_gate("TCS_CE", "BUY")

    assert allowed is True
    assert reason == "OK"


def test_configured_entry_score_floor_allows_conservative_directional_score():
    filters = AccuracyFilters(min_entry_score=75)
    history = [
        {"high": 101.0 + index, "low": 99.0 + index, "close": 100.0 + index}
        for index in range(30)
    ]

    allowed, reason = filters.validate_entry_with_reason(
        symbol="NIFTY",
        signal="BUY",
        score=75,
        history=history,
        current_bar={"close": 130.0},
        previous_bar={"close": 129.0},
        current_time=0.0,
        hour=10,
        minute=0,
    )

    assert allowed is True
    assert reason == "OK"


def test_entry_score_floor_is_capped_at_strategy_maximum():
    assert AccuracyFilters(min_entry_score=100).min_score_floor == 85


def test_symbol_win_rate_cap_blocks_weak_symbols():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)
    manager.min_symbol_trades_for_cap = 5
    manager.symbol_min_win_rate = 35.0
    manager.symbol_performance["INFY_PE"] = {"wins": 1, "trades": 5, "win_rate": 20.0}

    allowed, reason = manager.can_open_trade("INFY_PE", "BUY")

    assert allowed is False
    assert "win-rate cap" in reason.lower()


def test_best_setup_windows_summary_prefers_high_win_rate_periods(tmp_path):
    trades_path = tmp_path / "trades.jsonl"
    trades_path.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-09-17T09:45:00+05:30", "ticker": "LT_CE", "action": "BUY", "pnl": 100.0, "status": "closed"}),
                json.dumps({"timestamp": "2026-09-17T09:50:00+05:30", "ticker": "LT_CE", "action": "BUY", "pnl": 80.0, "status": "closed"}),
                json.dumps({"timestamp": "2026-09-18T10:05:00+05:30", "ticker": "LT_CE", "action": "BUY", "pnl": -60.0, "status": "closed"}),
                json.dumps({"timestamp": "2026-09-16T11:10:00+05:30", "ticker": "INFY_PE", "action": "SELL", "pnl": -80.0, "status": "closed"}),
                json.dumps({"timestamp": "2026-09-16T11:05:00+05:30", "ticker": "INFY_PE", "action": "SELL", "pnl": 90.0, "status": "closed"}),
            ]
        ) + "\n",
        encoding="utf-8",
    )

    windows = summarize_best_setup_windows(str(tmp_path), days=7)

    assert windows
    assert windows[0]["label"] == "09:BUY"
    assert windows[0]["win_rate"] >= 50.0
