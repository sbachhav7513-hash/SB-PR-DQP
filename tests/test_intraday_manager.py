import json
from datetime import datetime
from unittest.mock import Mock, patch

from market_bot.accuracy_filters import AccuracyFilters
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
