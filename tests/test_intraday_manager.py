import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest

from market_bot.accuracy_filters import AccuracyFilters
from market_bot.bar_builder import Bar
from market_bot.engine import SupportResistanceReversal
from market_bot.intraday_manager import IntradayManager
from market_bot.kite_main import KiteTradingBot
from market_bot.kite_provider import Tick
from market_bot.trade_journal import (
    PaperShadowExitJournal,
    TradeJournal,
    normalize_decision_outcome,
)
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


def test_option_buy_uses_latest_premium_for_position_sizing():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "entry_cutoff_minutes_before_close": 0,
        "option_premium_stop_pct": 0.10,
        "option_premium_target_pct": 0.20,
        "option_max_risk_per_lot_pct": 10.0,
    }
    bot.live_orders_enabled = False
    bot.paper_trading_enabled = True
    bot.intraday_manager = IntradayManager()
    bot.intraday_manager.set_contract_specs(
        {"NIFTY_CE": {"lot_size": 65, "multiplier": 1}}
    )
    bot.intraday_manager.calculate_option_size = Mock(return_value=2 * 65)
    bot.trade_journal = Mock()
    bot.trade_journal.get_open_trade.return_value = None
    bot.telegram_notifier = Mock()
    bot.telegram_notifier.format_trade.return_value = {
        "ticker": "NIFTY_CE",
        "entry": 120.0,
        "stop_loss": 96.0,
        "take_profit": 144.0,
    }
    bot.kite_stream = SimpleNamespace(contract_symbols={})
    bot.latest_prices = {"NIFTY_CE": 123.0}

    result = bot._handle_buy_signal("NIFTY_CE", 120.0, 80)

    assert result == "trade_opened"
    bot.intraday_manager.calculate_option_size.assert_called_once_with(
        "NIFTY_CE",
        premium=123.0,
        max_risk_per_trade=pytest.approx(799.5),
        premium_stop_pct=0.10,
    )
    position = bot.intraday_manager.active_positions["NIFTY_CE"]
    assert position["entry_price"] == 123.0
    assert position["stop_loss"] == pytest.approx(110.7)
    assert position["take_profit"] == pytest.approx(147.6)
    assert position["staged_targets_enabled"] is False
    assert position["trailing_enabled"] is True
    assert position["exit_strategy"] == "paper_option_adaptive"
    assert position["runner_activation_r"] is None
    assert position["runner_gap_r"] is None
    assert position["adaptive_breakeven_r"] == 0.5
    assert position["adaptive_trail_activation_r"] == 1.0
    assert position["adaptive_trail_gap_r"] == 0.5
    assert position["adaptive_runner_activation_r"] == 2.0
    assert position["adaptive_runner_gap_r"] == 1.0


def test_adaptive_option_exit_uses_shared_strategy_config():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"option_adaptive_exit_enabled": True}
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot._options_enabled = Mock(return_value=True)

    assert bot._option_adaptive_exit_enabled("NIFTY_CE") is True

    bot.live_orders_enabled = True
    bot.paper_trading_enabled = False
    assert bot._option_adaptive_exit_enabled("NIFTY_CE") is True

    bot.config["option_adaptive_exit_enabled"] = False
    assert bot._option_adaptive_exit_enabled("NIFTY_CE") is False


def test_paper_range_breakout_triggers_on_close_above_previous_15_bars():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "option_range_breakout_enabled": True,
        "option_range_lookback_bars": 15,
        "option_range_target_r": 2.0,
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot._options_enabled = Mock(return_value=True)
    bot.option_quote_cache = {"NIFTY_CE": {"last_price": 28.25}}
    bot.kite_stream = SimpleNamespace(
        contract_tick_sizes={"NIFTY_CE": 0.05}
    )
    bot.intraday_manager = SimpleNamespace(
        active_positions={}, session_trade_symbols=set()
    )
    bot._option_quality_gate = Mock(return_value=(True, "OK"))
    bot._handle_buy_signal = Mock(return_value="trade_opened")
    start = datetime(2026, 10, 14, 12, 38)
    bars = [
        Bar(start + timedelta(minutes=index), 27.0, 27.7, 26.55, 27.0, 1000)
        for index in range(15)
    ]
    bars.append(
        Bar(start + timedelta(minutes=15), 27.0, 27.7, 26.8, 27.0, 1000)
    )
    bars.append(
        Bar(start + timedelta(minutes=16), 27.7, 28.3, 27.6, 28.25, 1000)
    )

    with patch(
        "market_bot.kite_main.market_session_state",
        return_value="REGULAR_SESSION",
    ):
        outcome = bot._try_option_range_breakout("NIFTY_CE", bars)

    assert outcome == "PAPER_RANGE_BREAKOUT_TRADE_OPENED"
    bot._option_quality_gate.assert_called_once_with(
        "NIFTY_CE", "BUY", score=None
    )
    assert bot._handle_buy_signal.call_args.args == ("NIFTY_CE", 28.25, 0)
    assert bot._handle_buy_signal.call_args.kwargs["paper_range_stop"] == pytest.approx(
        26.5
    )
    assert bot._handle_buy_signal.call_args.kwargs["paper_range_target_r"] == 2.0


def test_paper_range_breakout_waits_for_one_completed_follow_through_bar():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "option_range_breakout_enabled": True,
        "option_range_lookback_bars": 15,
        "option_range_confirmation_bars": 1,
        "option_range_target_r": 2.0,
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot._options_enabled = Mock(return_value=True)
    bot.option_quote_cache = {"NIFTY_CE": {"last_price": 28.35}}
    bot.kite_stream = SimpleNamespace(contract_tick_sizes={"NIFTY_CE": 0.05})
    bot.intraday_manager = SimpleNamespace(
        active_positions={}, session_trade_symbols=set()
    )
    bot._option_quality_gate = Mock(return_value=(True, "OK"))
    bot._handle_buy_signal = Mock(return_value="trade_opened")
    start = datetime(2026, 10, 14, 12, 38)
    bars = [
        Bar(start + timedelta(minutes=index), 27.0, 27.7, 26.55, 27.0, 1000)
        for index in range(15)
    ]
    bars.extend(
        [
            Bar(start + timedelta(minutes=15), 27.7, 28.3, 27.6, 28.25, 1200),
            Bar(start + timedelta(minutes=16), 28.25, 28.5, 28.1, 28.3, 1100),
        ]
    )

    with patch(
        "market_bot.kite_main.market_session_state",
        return_value="REGULAR_SESSION",
    ):
        outcome = bot._try_option_range_breakout("NIFTY_CE", bars)

    assert outcome == "PAPER_RANGE_BREAKOUT_TRADE_OPENED"
    bot._handle_buy_signal.assert_called_once_with(
        "NIFTY_CE",
        28.35,
        0,
        strategy_variant="option_range_breakout",
        minimum_signal_score=0,
        paper_range_stop=pytest.approx(26.5),
        paper_range_target_r=2.0,
    )


def test_paper_range_breakout_rejects_follow_through_close_below_range():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "option_range_breakout_enabled": True,
        "option_range_lookback_bars": 15,
        "option_range_confirmation_bars": 1,
        "option_range_target_r": 2.0,
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot._options_enabled = Mock(return_value=True)
    bot.option_quote_cache = {"NIFTY_CE": {"last_price": 28.35}}
    bot._option_quality_gate = Mock(return_value=(True, "OK"))
    bot._handle_buy_signal = Mock(return_value="trade_opened")
    start = datetime(2026, 10, 14, 12, 38)
    bars = [
        Bar(start + timedelta(minutes=index), 27.0, 27.7, 26.55, 27.0, 1000)
        for index in range(15)
    ]
    bars.extend(
        [
            Bar(start + timedelta(minutes=15), 27.7, 28.3, 27.6, 28.25, 1200),
            Bar(start + timedelta(minutes=16), 28.25, 28.5, 27.6, 27.65, 1100),
        ]
    )

    outcome = bot._try_option_range_breakout("NIFTY_CE", bars)

    assert (
        outcome
        == "PAPER_RANGE_BREAKOUT_REJECTED:"
        "follow_through_close_below_range"
    )
    bot._option_quality_gate.assert_not_called()
    bot._handle_buy_signal.assert_not_called()


@pytest.mark.parametrize("breakout_volume", [0, 999])
def test_paper_range_breakout_rejects_volume_below_prior_15_bar_average(
    breakout_volume,
):
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "option_range_breakout_enabled": True,
        "option_range_lookback_bars": 15,
        "option_range_target_r": 2.0,
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot._options_enabled = Mock(return_value=True)
    bot._option_quality_gate = Mock(return_value=(True, "OK"))
    bot._handle_buy_signal = Mock(return_value="trade_opened")
    start = datetime(2026, 10, 14, 12, 38)
    bars = [
        Bar(start + timedelta(minutes=index), 27.0, 27.7, 26.55, 27.0, 1000)
        for index in range(15)
    ]
    bars.append(
        Bar(start + timedelta(minutes=15), 27.0, 27.7, 26.8, 27.0, 1000)
    )
    bars.append(
        Bar(
            start + timedelta(minutes=16),
            27.7,
            28.3,
            27.6,
            28.25,
            breakout_volume,
        )
    )

    outcome = bot._try_option_range_breakout("NIFTY_CE", bars)

    assert (
        outcome
        == "PAPER_RANGE_BREAKOUT_REJECTED:"
        "breakout_volume_below_15_bar_average"
    )
    bot._option_quality_gate.assert_not_called()
    bot._handle_buy_signal.assert_not_called()


def test_paper_range_breakout_keeps_fixed_2r_exit_with_range_risk_sizing():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "entry_cutoff_minutes_before_close": 0,
        "option_premium_stop_pct": 0.10,
        "option_premium_target_pct": 0.20,
        "option_max_risk_per_lot_pct": 10.0,
        "option_adaptive_exit_enabled": True,
        "option_min_lots": 1,
        "option_max_lots": 3,
        "strong_signal_score": 82,
        "option_milestone_pct": 0.10,
    }
    bot.live_orders_enabled = False
    bot.paper_trading_enabled = True
    bot._options_enabled = Mock(return_value=True)
    bot._live_entry_allowed = Mock(return_value=True)
    bot._staged_option_targets_enabled = Mock(return_value=True)
    bot.intraday_manager = IntradayManager(trailing_enabled=True)
    bot.intraday_manager.set_contract_specs(
        {"NIFTY_CE": {"lot_size": 65, "multiplier": 1}}
    )
    bot.intraday_manager.calculate_option_size = Mock(return_value=65)
    bot.trade_journal = Mock()
    bot.trade_journal.get_open_trade.return_value = None
    bot.telegram_notifier = Mock()
    bot.telegram_notifier.format_trade.return_value = {
        "ticker": "NIFTY_CE",
        "entry": 28.25,
    }
    bot.telegram_notifier.build_message.return_value = "paper trade"
    bot.kite_stream = SimpleNamespace(contract_symbols={})
    bot.latest_prices = {"NIFTY_CE": 28.25}
    bot._persist_current_live_risk_state = Mock()

    result = bot._handle_buy_signal(
        "NIFTY_CE",
        28.25,
        0,
        strategy_variant="option_range_breakout",
        minimum_signal_score=0,
        paper_range_stop=26.5,
        paper_range_target_r=2.0,
    )

    assert result == "trade_opened"
    bot.intraday_manager.calculate_option_size.assert_called_once_with(
        "NIFTY_CE",
        premium=28.25,
        max_risk_per_trade=pytest.approx(28.25 * 65 * 0.10),
        premium_stop_pct=pytest.approx(1.75 / 28.25),
    )
    position = bot.intraday_manager.active_positions["NIFTY_CE"]
    assert position["stop_loss"] == 26.5
    assert position["take_profit"] == pytest.approx(31.75)
    assert position["trailing_enabled"] is False
    assert position["staged_targets_enabled"] is False
    assert position["exit_strategy"] == "paper_range_breakout_2r"
    assert position["runner_activation_r"] is None
    assert position["runner_gap_r"] is None


def test_option_trail_runner_ignores_reference_target_and_timebox():
    manager = IntradayManager(trailing_enabled=True)
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        65,
        28.25,
        26.5,
        31.75,
        trailing_enabled=True,
        exit_strategy="paper_option_2r_trail_runner",
    )
    manager.milestone_timebox_expired = Mock(return_value=True)
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot._close_position = Mock()

    result = bot._check_position_exit("NIFTY_CE", 31.75)

    assert result is None
    bot._close_position.assert_not_called()
    manager.milestone_timebox_expired.assert_not_called()


@pytest.mark.parametrize(
    ("direction", "entry", "stop", "reference", "activation_price", "high_or_low", "expected_stop"),
    [
        ("BUY", 100.0, 90.0, 120.0, 110.0, 130.0, 110.0),
        ("SELL", 100.0, 110.0, 80.0, 90.0, 70.0, 90.0),
    ],
)
def test_option_trail_runner_activates_at_1r_and_ratchets_at_2r_gap(
    direction, entry, stop, reference, activation_price, high_or_low, expected_stop
):
    manager = IntradayManager(trailing_enabled=False)
    manager.register_position(
        "NIFTY_CE",
        direction,
        1,
        entry,
        stop,
        reference,
        trailing_enabled=True,
        exit_strategy="paper_option_2r_trail_runner",
    )

    assert manager.update_trailing_stop("NIFTY_CE", activation_price) == stop
    assert manager.active_positions["NIFTY_CE"]["trailing_active"] is True
    assert manager.update_trailing_stop("NIFTY_CE", high_or_low) == expected_stop


def test_option_trail_runner_keeps_initial_stop_as_floor_and_stop_reason():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        1,
        100.0,
        90.0,
        120.0,
        trailing_enabled=True,
        exit_strategy="paper_option_2r_trail_runner",
    )
    manager.update_trailing_stop("NIFTY_CE", 110.0)
    assert manager.active_positions["NIFTY_CE"]["trailing_stop"] == 90.0

    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot._close_position = Mock()

    assert bot._check_position_exit("NIFTY_CE", 89.0) == "STOP_LOSS"
    bot._close_position.assert_called_once_with("NIFTY_CE", 89.0, "STOP_LOSS")


def test_option_trail_runner_state_is_persisted_when_high_water_changes():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        1,
        100.0,
        90.0,
        120.0,
        trailing_enabled=True,
        exit_strategy="paper_option_2r_trail_runner",
    )
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot.trade_journal = Mock()
    bot.trade_journal.update_open_trade.return_value = True

    assert bot._check_position_exit("NIFTY_CE", 110.0) is None

    bot.trade_journal.update_open_trade.assert_called_once()
    args = bot.trade_journal.update_open_trade.call_args.args
    assert args[0] == "NIFTY_CE"
    assert args[1]["highest_price"] == 110.0
    assert args[1]["trailing_active"] is True
    assert args[1]["trailing_stop"] == 90.0
    assert args[2] == "BUY"
    assert manager.active_positions["NIFTY_CE"]["runner_persistence_pending"] is False


@pytest.mark.parametrize(
    ("direction", "entry", "stop", "prices", "expected_stops", "expected_modes"),
    [
        (
            "BUY",
            100.0,
            90.0,
            [105.0, 110.0, 120.0],
            [100.0, 105.0, 110.0],
            ["breakeven", "profit_trail", "runner"],
        ),
        (
            "SELL",
            100.0,
            110.0,
            [95.0, 90.0, 80.0],
            [100.0, 95.0, 90.0],
            ["breakeven", "profit_trail", "runner"],
        ),
    ],
)
def test_adaptive_option_exit_selects_mode_from_trade_progress(
    direction, entry, stop, prices, expected_stops, expected_modes
):
    manager = IntradayManager(trailing_enabled=False)
    manager.register_position(
        "NIFTY_CE",
        direction,
        1,
        entry,
        stop,
        120.0 if direction == "BUY" else 80.0,
        trailing_enabled=True,
        exit_strategy="paper_option_adaptive",
        adaptive_breakeven_r=0.5,
        adaptive_trail_activation_r=1.0,
        adaptive_trail_gap_r=0.5,
        adaptive_runner_activation_r=2.0,
        adaptive_runner_gap_r=1.0,
    )

    for price, expected_stop, expected_mode in zip(
        prices, expected_stops, expected_modes
    ):
        assert manager.update_trailing_stop("NIFTY_CE", price) == pytest.approx(
            expected_stop
        )
        position = manager.active_positions["NIFTY_CE"]
        assert position["adaptive_exit_mode"] == expected_mode


def test_adaptive_option_exit_stop_only_ratchets_tighter():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        1,
        100.0,
        90.0,
        120.0,
        trailing_enabled=True,
        exit_strategy="paper_option_adaptive",
    )

    assert manager.update_trailing_stop("NIFTY_CE", 110.0) == 105.0
    assert manager.update_trailing_stop("NIFTY_CE", 120.0) == 110.0
    assert manager.update_trailing_stop("NIFTY_CE", 115.0) == 110.0
    assert manager.active_positions["NIFTY_CE"]["adaptive_exit_mode"] == "runner"


def test_adaptive_option_exit_mode_and_mfe_are_persisted():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        1,
        100.0,
        90.0,
        120.0,
        trailing_enabled=True,
        exit_strategy="paper_option_adaptive",
    )
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot.trade_journal = Mock()
    bot.trade_journal.update_open_trade.return_value = True

    assert bot._check_position_exit("NIFTY_CE", 105.0) is None

    fields = bot.trade_journal.update_open_trade.call_args.args[1]
    assert fields["adaptive_exit_mode"] == "breakeven"
    assert fields["max_favorable_r"] == pytest.approx(0.5)
    assert fields["trailing_stop"] == 100.0


def test_option_trail_runner_ignores_opposite_signal_until_exit_rule_triggers():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"trading_mode": "intraday_options"}
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.intraday_manager = SimpleNamespace(
        active_positions={
            "NIFTY_CE": {"direction": "BUY", "exit_strategy": "paper_option_2r_trail_runner"}
        }
    )
    bot.trade_journal = Mock()
    bot.trade_journal.get_open_trade.side_effect = [None, {"action": "BUY"}]
    bot._close_position = Mock()

    assert bot._handle_sell_signal("NIFTY_CE", 105.0, 80) == "runner_position_active"
    bot._close_position.assert_not_called()


def test_option_trail_runner_is_forced_out_by_market_close():
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = SimpleNamespace(
        get_all_open_positions=Mock(
            return_value={"NIFTY_CE": {"entry_price": 100.0}}
        )
    )
    bot.latest_prices = {"NIFTY_CE": 115.0}
    bot._close_position = Mock()

    bot._handle_market_close_exit()

    bot._close_position.assert_called_once_with(
        "NIFTY_CE", 115.0, "MARKET_CLOSE_FORCED_EXIT"
    )


def test_option_range_breakout_runs_in_live_mode():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "option_range_breakout_enabled": True,
        "option_range_lookback_bars": 15,
        "option_range_target_r": 2.0,
    }
    bot.paper_trading_enabled = False
    bot.live_orders_enabled = True
    bot._options_enabled = Mock(return_value=True)
    bot.option_quote_cache = {"NIFTY_CE": {"last_price": 28.25}}
    bot.kite_stream = SimpleNamespace(contract_tick_sizes={"NIFTY_CE": 0.05})
    bot.intraday_manager = SimpleNamespace(
        active_positions={}, session_trade_symbols=set()
    )
    bot._option_quality_gate = Mock(return_value=(True, "OK"))
    bot._handle_buy_signal = Mock(return_value="trade_opened")
    start = datetime(2026, 10, 14, 12, 38)
    bars = [
        Bar(start + timedelta(minutes=index), 27, 27.7, 26.55, 27, 1000)
        for index in range(15)
    ]
    bars.extend(
        [
            Bar(start + timedelta(minutes=15), 27, 27.7, 26.8, 27, 1000),
            Bar(start + timedelta(minutes=16), 27.7, 28.3, 27.6, 28.25, 1000),
        ]
    )

    with patch(
        "market_bot.kite_main.market_session_state",
        return_value="REGULAR_SESSION",
    ):
        outcome = bot._try_option_range_breakout("NIFTY_CE", bars)

    assert outcome == "PAPER_RANGE_BREAKOUT_TRADE_OPENED"
    bot._handle_buy_signal.assert_called_once()


def test_support_reversal_is_shared_and_deduplicates_same_level():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "support_reversal_enabled": True,
        "bar_interval_seconds": 60,
        "support_reversal_cooldown_minutes": 15,
        "instrument_tokens": {"NIFTY_CE": 100},
    }
    bot.paper_trading_enabled = False
    bot.live_orders_enabled = True
    values = [
        (100.0, 100.2, 99.95, 100.0),
        (100.0, 100.1, 99.90, 99.95),
        (99.9, 100.0, 99.80, 99.90),
        (99.9, 100.1, 99.90, 100.0),
        (100.0, 100.2, 99.95, 100.1),
        (100.1, 100.1, 99.85, 99.95),
        (99.95, 100.1, 99.95, 100.0),
        (100.0, 100.05, 99.90, 100.0),
        (99.95, 100.0, 99.70, 99.85),
        (99.9, 100.25, 99.8, 100.15),
    ]
    start = datetime(2026, 10, 23, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    underlying_bars = []
    for group_index, (open_price, high, low, close) in enumerate(values):
        for minute in range(5):
            underlying_bars.append(
                Bar(
                    timestamp=start + timedelta(minutes=group_index * 5 + minute),
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=100,
                )
            )

    candidate = bot._support_reversal_candidate(
        "NIFTY_CE", underlying_bars
    )

    assert candidate is not None
    assert candidate.signal == "BUY"
    bot._mark_support_reversal_attempt("NIFTY_CE", candidate)
    assert bot._support_reversal_candidate(
        "NIFTY_CE", underlying_bars
    ) is None

    assert bot._support_reversal_candidate("NIFTY_CE", underlying_bars) is None


def test_paper_range_breakout_outcomes_are_classified_in_daily_reports():
    assert normalize_decision_outcome("PAPER_RANGE_BREAKOUT_TRADE_OPENED") == (
        "trade_opened"
    )
    assert normalize_decision_outcome(
        "PAPER_RANGE_BREAKOUT_REJECTED:option quote stale"
    ) == "option_filter"


def test_active_config_sizes_options_within_shared_per_trade_risk():
    with open("kite_config.json", encoding="utf-8") as config_file:
        config = json.load(config_file)
    with open("kite_config.example.json", encoding="utf-8") as example_config_file:
        example_config = json.load(example_config_file)

    manager = IntradayManager(
        account_size=config["account_size"],
        max_risk_per_trade=config["max_risk_per_trade"],
        daily_max_loss_pct=config["daily_max_loss_pct"],
    )
    manager.set_contract_specs({"NIFTY_CE": {"lot_size": 65, "multiplier": 1}})
    bot = object.__new__(KiteTradingBot)
    bot.config = config
    bot.intraday_manager = manager
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False

    quantity = bot._calculate_option_quantity(
        "NIFTY_CE",
        premium=100.0,
        premium_stop_pct=config["option_premium_stop_pct"],
    )
    risk = manager.estimate_trade_risk(
        "NIFTY_CE",
        quantity,
        100.0,
        100.0 * (1.0 - config["option_premium_stop_pct"]),
    )

    assert config["mode"] == "PAPER"
    assert config["option_range_breakout_enabled"] is False
    assert example_config["option_range_breakout_enabled"] is False
    assert config["support_reversal_enabled"] is True
    assert example_config["support_reversal_enabled"] is True
    assert config["support_reversal_min_premium"] == 5.0
    assert example_config["support_reversal_min_premium"] == 5.0
    assert config["option_min_lots"] == 1
    assert config["max_risk_per_trade"] == 1000.0
    assert config["daily_max_loss_pct"] == 10.0
    assert config["min_entry_score"] == 60
    assert config["option_max_risk_per_lot_pct"] == 10.0
    assert manager.daily_max_loss == 10_000.0
    assert manager.max_risk_per_trade == 1000.0
    assert quantity == 65
    assert risk == pytest.approx(650.0)
    assert risk <= manager.available_daily_risk()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        quantity,
        100.0,
        100.0 * (1.0 - config["option_premium_stop_pct"]),
        100.0 * 1.10,
    )

    manager.set_contract_specs(
        {
            "NIFTY_CE": {"lot_size": 65, "multiplier": 1},
            "TCS_PE": {"lot_size": 175, "multiplier": 1},
        }
    )
    quantity = bot._calculate_option_quantity(
        "TCS_PE",
        premium=95.60,
        premium_stop_pct=config["option_premium_stop_pct"],
    )
    risk = manager.estimate_trade_risk(
        "TCS_PE",
        quantity,
        95.60,
        95.60 * (1.0 - config["option_premium_stop_pct"]),
    )

    assert quantity == 0
    assert risk == 0
    assert bot._pending_entry_evaluations["TCS_PE"][
        "rejection_reason"
    ] == "one_lot_exceeds_trade_risk_cap"
    assert risk <= manager.available_daily_risk()

    assert manager.available_daily_risk() == pytest.approx(1_000.0)


def test_per_trade_risk_cap_is_separate_from_two_percent_daily_stop():
    manager = IntradayManager(
        account_size=100_000,
        risk_per_trade_pct=1.0,
        max_risk_per_trade=350.0,
        daily_max_loss_pct=2.0,
    )

    manager.set_contract_specs({"NIFTY_CE": {"lot_size": 65, "multiplier": 1}})

    assert manager.max_risk_per_trade == 350.0
    assert manager.daily_max_loss == 2_000.0
    assert manager.calculate_option_size(
        "NIFTY_CE", premium=12.0, premium_stop_pct=0.20
    ) == 130

    manager.record_trade_close("NIFTY_CE", "STOP_LOSS", pnl=-350.0)

    assert manager.can_open_trade("BANKNIFTY_CE", "BUY") == (True, "OK")
    assert manager.available_daily_risk() == 350.0


def test_two_percent_daily_loss_stop_blocks_after_cumulative_losses():
    manager = IntradayManager(
        account_size=100_000,
        max_risk_per_trade=350.0,
        daily_max_loss_pct=2.0,
    )
    manager.daily_pnl = -2_000.0

    allowed, reason = manager.can_open_trade("NIFTY_CE", "BUY")

    assert allowed is False
    assert "daily loss cap" in reason.lower()


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


def test_shadow_validation_does_not_start_entry_cooldown():
    filters = AccuracyFilters()
    history = [
        {"high": 101.0, "low": 99.0, "close": 100.0}
        for _ in range(14)
    ]

    allowed, reason = filters.validate_entry_with_reason(
        symbol="NIFTY",
        signal="BUY",
        score=85,
        history=history,
        current_bar={"close": 101.0},
        previous_bar={"close": 100.0},
        current_time=1000.0,
        hour=10,
        minute=0,
        record_entry=False,
    )

    assert allowed is True
    assert reason == "OK"
    assert filters.last_entry_time == {}


def test_primary_score_floor_is_70_and_shadow_override_remains_available():
    history = [
        {"high": 101.0, "low": 99.0, "close": 100.0}
        for _ in range(14)
    ]
    validation = {
        "symbol": "NIFTY",
        "signal": "BUY",
        "score": 70,
        "history": history,
        "current_bar": {"close": 101.0},
        "previous_bar": {"close": 100.0},
        "current_time": 1000.0,
        "hour": 10,
        "minute": 0,
        "record_entry": False,
    }

    primary_allowed, primary_reason = AccuracyFilters().validate_entry_with_reason(
        **validation
    )
    below_floor = {**validation, "score": 69}
    below_floor_allowed, below_floor_reason = (
        AccuracyFilters().validate_entry_with_reason(**below_floor)
    )
    assert primary_allowed is True
    assert primary_reason == "OK"
    assert below_floor_allowed is False
    assert below_floor_reason == "score<70"
    assert AccuracyFilters.should_enter_trade("BUY", 70, True, True)
    assert not AccuracyFilters.should_enter_trade("BUY", 69, True, True)


def test_accuracy_filter_requires_confirmation_and_same_score_floor():
    filters = AccuracyFilters()
    history = [
        {"high": 101.0, "low": 99.0, "close": 100.0}
        for _ in range(14)
    ]
    validation = {
        "symbol": "NIFTY",
        "signal": "BUY",
        "score": 85,
        "history": history,
        "current_bar": {"close": 99.0},
        "previous_bar": {"close": 100.0},
        "current_time": 1000.0,
        "hour": 10,
        "minute": 0,
        "record_entry": False,
    }

    strict_allowed, strict_reason = filters.validate_entry_with_reason(**validation)
    low_score_allowed, low_score_reason = filters.validate_entry_with_reason(
        **{
            **validation,
            "score": 60,
            "current_bar": {"close": 101.0},
        }
    )

    assert strict_allowed is False
    assert strict_reason == "confirmation"
    assert low_score_allowed is False
    assert low_score_reason == "score<70"


def test_paper_position_size_respects_risk_budget_when_one_lot_is_too_large():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)

    assert manager.calculate_position_size("NIFTY", 100.0, 70.0) == 0


def test_open_positions_and_realized_losses_share_daily_risk_budget():
    manager = IntradayManager(
        account_size=100_000,
        risk_per_trade_pct=1.0,
        daily_max_loss=350.0,
    )
    manager.set_contract_specs(
        {
            "NIFTY_CE": {"lot_size": 65, "multiplier": 1},
            "BANKNIFTY_CE": {"lot_size": 10, "multiplier": 1},
            "ICICIBANK_CE": {"lot_size": 10, "multiplier": 1},
        }
    )
    manager.register_position("NIFTY_CE", "BUY", 130, 12.0, 9.6, 14.4)

    assert manager.open_position_risk() == pytest.approx(312.0)
    assert manager.available_daily_risk() == pytest.approx(38.0)
    assert (
        manager.calculate_option_size(
            "BANKNIFTY_CE", 10.0, premium_stop_pct=0.20
        )
        == 10
    )

    manager.register_position("BANKNIFTY_CE", "BUY", 10, 10.0, 8.0, 12.0)
    assert manager.available_daily_risk() == pytest.approx(18.0)
    assert (
        manager.calculate_option_size(
            "ICICIBANK_CE", 10.0, premium_stop_pct=0.20
        )
        == 0
    )
    assert manager.daily_risk_exceeded() is False


def test_session_trade_restore_reinstates_realized_daily_loss():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    manager = IntradayManager(daily_max_loss=350.0)
    manager.restore_session_trades(
        [
            {
                "ticker": "NIFTY_CE",
                "status": "closed",
                "timestamp": now.isoformat(),
                "closed_at": now.isoformat(),
                "pnl": -125.0,
            }
        ]
    )

    assert manager.daily_pnl == -125.0
    assert manager.available_daily_risk() == pytest.approx(225.0)


def test_session_rollover_resets_daily_loss_and_trade_counters():
    manager = IntradayManager(daily_max_loss=350.0)
    manager._session_date = datetime(2000, 1, 1).date()
    manager.daily_pnl = -125.0
    manager.daily_trade_count = 2
    manager.consecutive_losses = 2
    manager.session_trade_symbols.add("NIFTY_CE")
    manager.session_trade_counts["NIFTY_CE"] = 1
    manager.session_loss_stop_times["NIFTY_CE"] = datetime.now(
        ZoneInfo("Asia/Kolkata")
    )
    manager.session_reversal_symbols.add("NIFTY_PE")

    manager._refresh_session()

    assert manager.daily_pnl == 0.0
    assert manager.daily_trade_count == 0
    assert manager.consecutive_losses == 0
    assert manager.session_trade_symbols == set()
    assert manager.session_trade_counts == {}
    assert manager.session_loss_stop_times == {}
    assert manager.session_reversal_symbols == set()
    assert manager.available_daily_risk() == pytest.approx(350.0)


def test_session_restore_fails_closed_for_invalid_realized_pnl():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    manager = IntradayManager(daily_max_loss=350.0)

    with pytest.raises(RuntimeError, match="non-finite P&L"):
        manager.restore_session_trades(
            [
                {
                    "ticker": "NIFTY_CE",
                    "status": "closed",
                    "timestamp": now.isoformat(),
                    "closed_at": now.isoformat(),
                    "pnl": float("nan"),
                }
            ]
        )


def test_paper_open_position_restore_reserves_daily_risk():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    bot = object.__new__(KiteTradingBot)
    bot.config = {"option_milestone_pct": 0.10, "strong_signal_score": 82}
    bot.intraday_manager = IntradayManager(
        account_size=100_000,
        risk_per_trade_pct=1.0,
        daily_max_loss=350.0,
    )
    bot.intraday_manager.set_contract_specs(
        {"NIFTY_CE": {"lot_size": 65, "multiplier": 1}}
    )

    bot._restore_paper_positions(
        [
            {
                "ticker": "NIFTY_CE",
                "action": "BUY",
                "quantity": 130,
                "entry": 12.0,
                "stop_loss": 9.6,
                "take_profit": 14.4,
                "status": "open",
                "timestamp": now.isoformat(),
            }
        ]
    )

    assert set(bot.intraday_manager.active_positions) == {"NIFTY_CE"}
    assert bot.intraday_manager.available_daily_risk() == pytest.approx(38.0)


def test_paper_runner_restore_reinstates_trailing_state():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    bot = object.__new__(KiteTradingBot)
    bot.config = {"option_milestone_pct": 0.10, "strong_signal_score": 82}
    bot.intraday_manager = IntradayManager()
    bot.intraday_manager.set_contract_specs(
        {"NIFTY_CE": {"lot_size": 65, "multiplier": 1}}
    )

    bot._restore_paper_positions(
        [
            {
                "ticker": "NIFTY_CE",
                "action": "BUY",
                "quantity": 65,
                "entry": 100.0,
                "stop_loss": 90.0,
                "take_profit": 120.0,
                "status": "open",
                "timestamp": now.isoformat(),
                "exit_strategy": "paper_option_2r_trail_runner",
                "trailing_enabled": True,
                "runner_activation_r": 1.0,
                "runner_gap_r": 2.0,
                "highest_price": 135.0,
                "lowest_price": 100.0,
                "trailing_stop": 115.0,
                "trailing_active": True,
            }
        ]
    )

    position = bot.intraday_manager.active_positions["NIFTY_CE"]
    assert position["highest_price"] == 135.0
    assert position["lowest_price"] == 100.0
    assert position["trailing_stop"] == 115.0
    assert position["trailing_active"] is True
    assert position["runner_activation_r"] == 1.0
    assert position["runner_gap_r"] == 2.0


def test_paper_adaptive_exit_restore_reinstates_mode_and_thresholds():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    bot = object.__new__(KiteTradingBot)
    bot.config = {"option_milestone_pct": 0.10, "strong_signal_score": 82}
    bot.intraday_manager = IntradayManager()
    bot.intraday_manager.set_contract_specs(
        {"NIFTY_CE": {"lot_size": 65, "multiplier": 1}}
    )

    bot._restore_paper_positions(
        [
            {
                "ticker": "NIFTY_CE",
                "action": "BUY",
                "quantity": 65,
                "entry": 100.0,
                "stop_loss": 90.0,
                "take_profit": 120.0,
                "status": "open",
                "timestamp": now.isoformat(),
                "exit_strategy": "paper_option_adaptive",
                "trailing_enabled": True,
                "adaptive_breakeven_r": 0.5,
                "adaptive_trail_activation_r": 1.0,
                "adaptive_trail_gap_r": 0.5,
                "adaptive_runner_activation_r": 2.0,
                "adaptive_runner_gap_r": 1.0,
                "adaptive_exit_mode": "profit_trail",
                "max_favorable_r": 1.5,
                "highest_price": 115.0,
                "lowest_price": 100.0,
                "trailing_stop": 110.0,
                "trailing_active": True,
            }
        ]
    )

    position = bot.intraday_manager.active_positions["NIFTY_CE"]
    assert position["exit_strategy"] == "paper_option_adaptive"
    assert position["adaptive_exit_mode"] == "profit_trail"
    assert position["max_favorable_r"] == pytest.approx(1.5)
    assert position["trailing_stop"] == pytest.approx(110.0)


def test_paper_trade_mark_is_persisted_and_throttled(tmp_path):
    journal = TradeJournal(str(tmp_path / "trades.jsonl"))
    journal.log_trade(
        {
            "ticker": "AAPL",
            "action": "BUY",
            "entry": 100.0,
        }
    )

    assert journal.update_trade_mark("AAPL", 108.0, "BUY") is True
    [trade] = journal.read_trades()
    assert trade["last_price"] == 108.0
    assert trade["updated_at"]

    assert journal.update_trade_mark("AAPL", 109.0, "BUY") is False
    assert journal.read_trades()[0]["last_price"] == 108.0


def test_paper_market_tick_persists_active_position_mark():
    bot = object.__new__(KiteTradingBot)
    bot.symbol_map = {101: "AAPL"}
    bot.latest_prices = {}
    bot.option_quote_cache = {}
    bot.intraday_manager = SimpleNamespace(
        active_positions={"AAPL": {"direction": "BUY"}},
        should_exit_all_positions=Mock(return_value=False),
    )
    bot.paper_trading_enabled = True
    bot.trade_journal = Mock()
    bot.bar_builder = Mock()
    bot._check_position_exit = Mock()
    tick = SimpleNamespace(
        instrument_token=101,
        last_price=108.0,
        volume=100,
        timestamp=datetime.now(ZoneInfo("Asia/Kolkata")),
        oi=None,
        iv=None,
    )

    bot._on_tick(tick)

    bot.trade_journal.update_trade_mark.assert_called_once_with(
        "AAPL", 108.0, "BUY"
    )


def test_stale_paper_position_closes_at_last_persisted_mark(tmp_path):
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    opened_at = now - timedelta(days=1)
    mark_time = opened_at + timedelta(minutes=5)
    journal = TradeJournal(str(tmp_path / "trades.jsonl"))
    journal.log_trade(
        {
            "ticker": "AAPL",
            "action": "BUY",
            "quantity": 2,
            "entry": 100.0,
            "stop_loss": 90.0,
            "take_profit": 120.0,
            "last_price": 108.0,
            "updated_at": mark_time.isoformat(),
            "timestamp": opened_at.isoformat(),
        }
    )
    bot = object.__new__(KiteTradingBot)
    bot.config = {}
    bot.trade_journal = journal
    bot.intraday_manager = IntradayManager()

    bot._restore_paper_positions(journal.read_trades())

    [trade] = journal.read_trades()
    assert trade["status"] == "closed"
    assert trade["exit_price"] == 108.0
    assert trade["pnl"] == 8.0
    assert trade["closed_at"] == mark_time.isoformat(timespec="seconds")
    assert trade["reason"] == "STALE_PAPER_POSITION_RECOVERY_AT_LAST_MARK"
    assert bot.intraday_manager.active_positions == {}


def test_stale_paper_position_without_recovery_mark_closes_at_entry_estimate(
    tmp_path,
):
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    journal = TradeJournal(str(tmp_path / "trades.jsonl"))
    journal.log_trade(
        {
            "ticker": "AAPL",
            "action": "BUY",
            "quantity": 2,
            "entry": 100.0,
            "stop_loss": 90.0,
            "take_profit": 120.0,
            "updated_at": now.isoformat(),
            "timestamp": (now - timedelta(days=1)).isoformat(),
        }
    )
    bot = object.__new__(KiteTradingBot)
    bot.config = {}
    bot.trade_journal = journal
    bot.intraday_manager = IntradayManager()

    bot._restore_paper_positions(journal.read_trades())

    [trade] = journal.read_trades()
    assert trade["status"] == "closed"
    assert trade["exit_price"] == trade["entry"] == 100.0
    assert trade["pnl"] == 0.0
    assert trade["reason"] == "STALE_PAPER_POSITION_RECOVERY_AT_ENTRY_ESTIMATE"


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


def test_paper_stop_reentry_requires_cooldown_score_and_is_limited_to_one():
    manager = IntradayManager(account_size=100_000, daily_max_loss=10_000.0)
    manager.record_trade_open("NIFTY_CE", "BUY")
    manager.record_trade_close("NIFTY_CE", "STOP_LOSS", pnl=-200.0)

    allowed, reason = manager.can_open_trade(
        "NIFTY_CE",
        "BUY",
        allow_stop_reentry=True,
        stop_reentry_cooldown_seconds=900,
        signal_score=80,
        minimum_stop_reentry_score=75,
    )
    assert allowed is False
    assert "cooldown" in reason.lower()

    manager.session_loss_stop_times["NIFTY_CE"] = (
        datetime.now(ZoneInfo("Asia/Kolkata")) - timedelta(minutes=16)
    )
    allowed, reason = manager.can_open_trade(
        "NIFTY_CE",
        "BUY",
        allow_stop_reentry=True,
        stop_reentry_cooldown_seconds=900,
        signal_score=74,
        minimum_stop_reentry_score=75,
    )
    assert allowed is False
    assert "score 75" in reason.lower()

    allowed, reason = manager.can_open_trade(
        "NIFTY_CE",
        "BUY",
        allow_stop_reentry=True,
        stop_reentry_cooldown_seconds=900,
        signal_score=75,
        minimum_stop_reentry_score=75,
    )
    assert (allowed, reason) == (True, "OK")

    manager.record_trade_open("NIFTY_CE", "BUY")
    allowed, reason = manager.can_open_trade(
        "NIFTY_CE",
        "BUY",
        allow_stop_reentry=True,
        stop_reentry_cooldown_seconds=900,
        signal_score=85,
        minimum_stop_reentry_score=75,
    )
    assert allowed is False
    assert "one stop-loss re-entry" in reason.lower()


def test_only_negative_stop_exits_qualify_for_paper_reentry():
    manager = IntradayManager(account_size=100_000, daily_max_loss=10_000.0)
    manager.record_trade_open("NIFTY_CE", "BUY")
    manager.record_trade_close("NIFTY_CE", "TIME_BOX", pnl=-200.0)

    allowed, reason = manager.can_open_trade(
        "NIFTY_CE",
        "BUY",
        allow_stop_reentry=True,
        signal_score=85,
    )

    assert allowed is False
    assert "no qualifying loss stop" in reason.lower()


def test_stop_reentry_policy_is_shared_across_execution_modes():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "stop_reentry_enabled": True,
        "stop_reentry_cooldown_minutes": 15,
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.stop_reentry_min_score = 75
    bot.stop_reentry_cooldown_minutes = 15
    bot.intraday_manager = Mock()
    bot.intraday_manager.can_open_trade.return_value = (True, "OK")

    assert bot._can_open_trade_for_signal("NIFTY_CE", "BUY", 80) == (True, "OK")
    bot.intraday_manager.can_open_trade.assert_called_once_with(
        "NIFTY_CE",
        "BUY",
        allow_stop_reentry=True,
        stop_reentry_cooldown_seconds=900,
        signal_score=80,
        minimum_stop_reentry_score=75,
    )

    bot.intraday_manager.can_open_trade.reset_mock()
    bot.live_orders_enabled = True
    assert bot._can_open_trade_for_signal("NIFTY_CE", "BUY", 80) == (True, "OK")
    bot.intraday_manager.can_open_trade.assert_called_once_with(
        "NIFTY_CE",
        "BUY",
        allow_stop_reentry=True,
        stop_reentry_cooldown_seconds=900,
        signal_score=80,
        minimum_stop_reentry_score=75,
    )


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


def test_stop_reentry_state_is_restored_from_journal():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    trade_time = now - timedelta(minutes=20)
    manager = IntradayManager(account_size=100_000, daily_max_loss=10_000.0)

    manager.restore_session_trades(
        [
            {
                "ticker": "NIFTY_CE",
                "status": "closed",
                "timestamp": trade_time.isoformat(),
                "closed_at": trade_time.isoformat(),
                "reason": "STOP_LOSS",
                "pnl": -200.0,
            }
        ]
    )

    assert manager.session_trade_counts["NIFTY_CE"] == 1
    assert "NIFTY_CE" in manager.session_loss_stop_times
    assert manager.can_open_trade(
        "NIFTY_CE",
        "BUY",
        allow_stop_reentry=True,
        stop_reentry_cooldown_seconds=900,
        signal_score=75,
        minimum_stop_reentry_score=75,
    ) == (True, "OK")


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


def test_shared_entry_cutoff_blocks_at_1445_in_both_modes():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"entry_cutoff_minutes_before_close": 45}
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.intraday_manager = IntradayManager()
    ist = ZoneInfo("Asia/Kolkata")

    assert bot._entry_cutoff_reason(
        datetime(2026, 10, 16, 14, 44, tzinfo=ist)
    ) is None
    assert bot._entry_cutoff_reason(
        datetime(2026, 10, 16, 14, 45, tzinfo=ist)
    ) == "entry_cutoff_blocked:45m_before_close"

    bot.live_orders_enabled = True
    assert bot._entry_cutoff_reason(
        datetime(2026, 10, 16, 15, 0, tzinfo=ist)
    ) == "entry_cutoff_blocked:45m_before_close"


@pytest.mark.parametrize("_handler", ["_handle_buy_signal", "_handle_sell_signal"])
def test_both_entry_handlers_apply_common_paper_cutoff(_handler):
    bot = object.__new__(KiteTradingBot)
    bot.config = {}
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.trade_journal = Mock()
    bot.trade_journal.get_open_trade.return_value = None
    bot.intraday_manager = SimpleNamespace(active_positions={})
    bot._entry_cutoff_reason = Mock(
        return_value="entry_cutoff_blocked:45m_before_close"
    )

    result = getattr(bot, _handler)("TCS_CE", 100.0, 80)

    assert result == "entry_cutoff_blocked:45m_before_close"
    bot._entry_cutoff_reason.assert_called_once_with()


def test_paper_risk_cap_sizes_from_actual_option_stop_distance():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "max_risk_per_trade": 1000.0,
        "option_max_risk_per_lot_pct": 10.0,
        "option_min_lots": 1,
        "option_max_lots": 3,
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.intraday_manager = IntradayManager(
        account_size=100_000,
        max_risk_per_trade=10_000.0,
        daily_max_loss=10_000.0,
    )
    bot.intraday_manager.set_contract_specs(
        {"TCS_PE": {"lot_size": 225, "multiplier": 1}}
    )
    stop_pct = (112.0 - 100.95) / 112.0

    quantity = bot._calculate_option_quantity("TCS_PE", 112.0, stop_pct)

    assert quantity == 0
    evaluation = bot._pending_entry_evaluations["TCS_PE"]
    assert evaluation["option_risk_per_lot_rupees"] == pytest.approx(
        112.0 * stop_pct * 225
    )
    assert evaluation["option_risk_per_lot_rupees"] > 1000.0
    assert evaluation["rejection_reason"] == "one_lot_exceeds_trade_risk_cap"


def test_paper_risk_cap_allows_one_lot_when_stop_risk_is_within_budget():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "max_risk_per_trade": 1000.0,
        "option_max_risk_per_lot_pct": 10.0,
        "option_min_lots": 1,
        "option_max_lots": 3,
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.intraday_manager = IntradayManager(
        account_size=100_000,
        max_risk_per_trade=10_000.0,
        daily_max_loss=10_000.0,
    )
    bot.intraday_manager.set_contract_specs(
        {"NIFTY_CE": {"lot_size": 65, "multiplier": 1}}
    )

    quantity = bot._calculate_option_quantity("NIFTY_CE", 123.0, 0.10)

    assert quantity == 65
    assert bot._pending_entry_evaluations["NIFTY_CE"][
        "estimated_initial_risk_rupees"
    ] == pytest.approx(799.5)


def test_paper_per_trade_risk_cap_also_applies_to_futures_sizing():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"max_risk_per_trade": 1000.0}
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.intraday_manager = IntradayManager(
        account_size=100_000,
        max_risk_per_trade=10_000.0,
        daily_max_loss=10_000.0,
    )
    bot.intraday_manager.set_contract_specs(
        {"TCS": {"lot_size": 225, "multiplier": 1}}
    )

    quantity = bot._calculate_position_size("TCS", 112.0, 100.95)

    assert quantity == 0
    assert bot._pending_entry_evaluations["TCS"][
        "rejection_reason"
    ] == "one_lot_exceeds_trade_risk_cap"


def test_decision_record_includes_pending_entry_risk_evaluation():
    bot = object.__new__(KiteTradingBot)
    bot.decision_journal = Mock()
    bot._pending_entry_evaluations = {
        "TCS_CE": {
            "risk_cap_rupees": 1000.0,
            "option_risk_per_lot_rupees": 2486.25,
            "accepted": False,
        }
    }
    bar = Bar(
        datetime(2026, 10, 16, 14, 45, tzinfo=ZoneInfo("Asia/Kolkata")),
        100.0,
        101.0,
        99.0,
        100.5,
        10,
    )

    bot._record_decision(
        "TCS_CE", bar, [bar], None, "BUY",
        "risk_cap_blocked:one_lot_exceeds_1000_rupees"
    )

    payload = bot.decision_journal.log_decision.call_args.args[0]
    assert payload["entry_evaluation"]["risk_cap_rupees"] == 1000.0
    assert "TCS_CE" not in bot._pending_entry_evaluations


def test_one_r_shadow_runner_records_quote_fills_costs_and_actual_exit(tmp_path):
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "paper_shadow_1r_runner_enabled": True,
        "paper_shadow_fee_per_order": 10.0,
        "paper_shadow_fee_bps_per_side": 5.0,
        "paper_shadow_slippage_bps_per_side": 0.0,
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot._options_enabled = Mock(return_value=True)
    bot.option_quote_cache = {
        "TCS_CE": {
            "last_price": 112.0,
            "bid": 111.9,
            "ask": 112.1,
            "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")),
        }
    }
    bot.paper_shadow_exit_journal = PaperShadowExitJournal(
        str(tmp_path / "shadow.jsonl")
    )
    bot.paper_shadow_positions = {}
    bot.intraday_manager = SimpleNamespace(
        should_exit_all_positions=Mock(return_value=False)
    )
    entry_time = datetime(2026, 10, 16, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    bot._start_paper_shadow_runner(
        "TCS_CE", "tcs-trade", 112.0, 100.95, 225, entry_time.isoformat()
    )
    state = bot.paper_shadow_positions["tcs-trade"]
    assert state["entry_fill_price"] == pytest.approx(112.1)
    assert state["risk_distance"] == pytest.approx(11.15)

    bot._update_paper_shadow_runner(
        "TCS_CE",
        Tick(
            1,
            datetime(2026, 10, 16, 10, 1, tzinfo=ZoneInfo("Asia/Kolkata")),
            124.5,
            bid=124.4,
            ask=124.5,
        ),
    )
    assert state["trailing_active"] is True
    assert state["trailing_stop"] == pytest.approx(113.25)

    bot._update_paper_shadow_runner(
        "TCS_CE",
        Tick(
            1,
            datetime(2026, 10, 16, 10, 2, tzinfo=ZoneInfo("Asia/Kolkata")),
            113.3,
            bid=113.2,
            ask=113.3,
        ),
    )
    closed = bot.paper_shadow_exit_journal.latest["tcs-trade"]
    assert closed["status"] == "closed"
    assert closed["exit_fill_source"] == "best_bid"
    assert closed["gross_pnl_rupees"] == pytest.approx(247.5)
    assert closed["estimated_fee_rupees"] == pytest.approx(45.34625)
    assert closed["net_pnl_estimate_rupees"] == pytest.approx(202.15375)

    bot.option_quote_cache["TCS_CE"] = {
        "last_price": 117.0,
        "bid": 116.9,
        "ask": 117.0,
    }
    bot._record_paper_shadow_actual_exit(
        {
            "trade_id": "tcs-trade",
            "ticker": "TCS_CE",
            "action": "BUY",
            "entry": 112.0,
            "quantity": 225,
            "paper_entry_bid": 111.9,
            "paper_entry_ask": 112.1,
            "paper_entry_quote_is_fresh": True,
        },
        117.0,
        "TAKE_PROFIT",
    )

    compared = bot.paper_shadow_exit_journal.latest["tcs-trade"]
    assert compared["actual_gross_pnl_rupees"] == pytest.approx(1125.0)
    assert compared["actual_bid_ask_gross_pnl_rupees"] == pytest.approx(1080.0)
    assert compared["actual_net_pnl_estimate_rupees"] == pytest.approx(1034.2375)
    restored = PaperShadowExitJournal(str(tmp_path / "shadow.jsonl"))
    assert restored.latest["tcs-trade"]["status"] == "closed"


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


def test_live_entry_aborts_when_fill_exceeds_aggregate_daily_risk():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"trading_mode": "intraday_futures"}
    bot.live_orders_enabled = True
    bot.paper_trading_enabled = False
    bot._entries_paused = False
    bot._risk_state_reconciled = True
    bot.intraday_manager = IntradayManager(
        account_size=10_000,
        risk_per_trade_pct=1.0,
        daily_max_loss=150.0,
    )
    bot.intraday_manager.set_contract_specs(
        {
            "EXISTING": {"lot_size": 1, "multiplier": 1},
            "NIFTY": {"lot_size": 1, "multiplier": 1},
        }
    )
    bot.intraday_manager.register_position(
        "EXISTING", "BUY", 145, 100.0, 99.0, 102.0
    )
    bot.kite_stream = Mock()
    bot.kite_stream.is_connected = True
    bot.kite_stream.place_market_order.return_value = "entry-order"
    bot.kite_stream.wait_for_order_fill.return_value = {
        "filled_quantity": 5,
        "average_price": 200.0,
    }
    bot.kite_stream.place_protective_stop_order.return_value = "stop-order"
    bot.trade_journal = Mock()
    bot.trade_journal.get_open_trade.return_value = None
    bot.telegram_notifier = Mock()
    bot._abort_live_entry = Mock()

    result = bot._handle_buy_signal("NIFTY", 100.0, 80)

    assert result == "risk_blocked:filled_risk_exceeds_aggregate_limit"
    bot.kite_stream.place_protective_stop_order.assert_called_once()
    bot._abort_live_entry.assert_called_once_with(
        "NIFTY", 200.0, "AGGREGATE_RISK_LIMIT_EXCEEDED"
    )


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
        110.0,
        signal_score=85,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
    )

    manager.update_trailing_stop("NIFTY_CE", 110.0)
    position = manager.active_positions["NIFTY_CE"]

    assert position["target_stage"] == 1
    assert position["take_profit"] == 120.0
    assert position["trailing_stop"] == 100.0
    assert position["signal_score"] == 85


def test_staged_sell_target_advances_by_configured_increment():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_PE",
        "SELL",
        1,
        100.0,
        120.0,
        90.0,
        signal_score=85,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
    )

    manager.update_trailing_stop("NIFTY_PE", 90.0)
    position = manager.active_positions["NIFTY_PE"]

    assert position["target_stage"] == 1
    assert position["take_profit"] == 80.0
    assert position["trailing_stop"] == 100.0


def test_milestone_stop_locks_more_when_entry_signal_is_weaker():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        130,
        100.0,
        80.0,
        110.0,
        signal_score=78,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
        strong_signal_score=82,
    )

    assert manager.update_trailing_stop("NIFTY_CE", 110.0) == 105.0
    assert manager.update_trailing_stop("NIFTY_CE", 120.0) == 115.0


def test_milestone_timebox_uses_entry_score_and_restarts_after_milestone():
    manager = IntradayManager()
    entered_at = datetime(2026, 10, 2, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        130,
        100.0,
        80.0,
        110.0,
        signal_score=85,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
        entry_time=entered_at,
        milestone_started_at=entered_at,
    )

    manager.active_positions["NIFTY_CE"]["current_signal_score"] = 70
    assert not manager.milestone_timebox_expired(
        "NIFTY_CE", entered_at.replace(minute=9, second=59)
    )
    assert manager.milestone_timebox_expired(
        "NIFTY_CE", entered_at.replace(minute=10)
    )
    manager.update_trailing_stop(
        "NIFTY_CE", 110.0, now=entered_at.replace(minute=10)
    )
    assert not manager.milestone_timebox_expired(
        "NIFTY_CE", entered_at.replace(minute=19, second=59)
    )
    assert manager.milestone_timebox_expired(
        "NIFTY_CE", entered_at.replace(minute=20)
    )


def test_tick_exit_closes_when_milestone_window_expires_outside_paper_extension():
    manager = IntradayManager()
    entered_at = datetime(2026, 10, 2, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        130,
        100.0,
        80.0,
        110.0,
        signal_score=78,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
        entry_time=entered_at,
        milestone_started_at=entered_at,
    )
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot._close_position = Mock()
    bot.paper_trading_enabled = False
    bot.config = {"extend_option_timebox": False}

    with patch("market_bot.intraday_manager.datetime") as clock:
        clock.now.return_value = entered_at.replace(minute=5)
        assert bot._check_position_exit("NIFTY_CE", 104.0) == "TIME_BOX"

    bot._close_position.assert_called_once_with("NIFTY_CE", 104.0, "TIME_BOX")


def test_paper_timebox_expiry_extends_window_and_persists_checkpoint():
    manager = IntradayManager()
    entered_at = datetime(2026, 10, 2, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        130,
        100.0,
        80.0,
        110.0,
        signal_score=78,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
        entry_time=entered_at,
        milestone_started_at=entered_at,
    )
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot.paper_trading_enabled = True
    bot.config = {"extend_option_timebox": True}
    bot.trade_journal = Mock()
    bot.trade_journal.update_open_trade.return_value = True
    bot._close_position = Mock()
    checkpoint_time = entered_at.replace(minute=5)

    with patch("market_bot.intraday_manager.datetime") as clock:
        clock.now.return_value = checkpoint_time
        assert bot._check_position_exit("NIFTY_CE", 104.0) == "TIME_BOX_EXTENDED"

    assert manager.active_positions["NIFTY_CE"]["milestone_started_at"] == checkpoint_time
    assert not manager.milestone_timebox_expired(
        "NIFTY_CE", checkpoint_time + timedelta(minutes=4, seconds=59)
    )
    bot.trade_journal.update_open_trade.assert_called_once_with(
        "NIFTY_CE",
        {"milestone_started_at": checkpoint_time.isoformat()},
        "BUY",
    )
    bot._close_position.assert_not_called()


def test_paper_timebox_extension_does_not_override_stop_loss():
    manager = IntradayManager()
    entered_at = datetime(2026, 10, 2, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        130,
        100.0,
        80.0,
        110.0,
        signal_score=78,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
        entry_time=entered_at,
        milestone_started_at=entered_at,
    )
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot.paper_trading_enabled = True
    bot.config = {"extend_option_timebox": True}
    bot.trade_journal = Mock()
    bot._close_position = Mock()

    with patch("market_bot.intraday_manager.datetime") as clock:
        clock.now.return_value = entered_at.replace(minute=5)
        assert bot._check_position_exit("NIFTY_CE", 79.0) == "STOP_LOSS"

    bot._close_position.assert_called_once_with("NIFTY_CE", 79.0, "STOP_LOSS")
    bot.trade_journal.update_open_trade.assert_not_called()


def test_option_signal_weakening_uses_adverse_premium_move_for_ce_and_pe_buys():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        130,
        100.0,
        80.0,
        110.0,
        signal_score=80,
        minimum_signal_score=70,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
    )
    manager.register_position(
        "BANKNIFTY_PE",
        "BUY",
        130,
        100.0,
        80.0,
        110.0,
        signal_score=80,
        minimum_signal_score=70,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
    )
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot._close_position = Mock()
    bot.paper_trading_enabled = True
    bot.trade_journal = Mock()

    assert bot._check_option_signal_health("NIFTY_CE", "HOLD", 69, 70, 95.0) is None
    assert manager.active_positions["NIFTY_CE"]["weak_signal_adverse_checks"] == 1
    bot._close_position.assert_not_called()
    assert bot._check_option_signal_health("NIFTY_CE", "HOLD", 70, 70, 95.0) is None
    assert manager.active_positions["NIFTY_CE"]["weak_signal_adverse_checks"] == 0
    assert bot._check_option_signal_health("NIFTY_CE", "HOLD", 69, 70, 95.0) is None
    assert bot._check_option_signal_health("NIFTY_CE", "HOLD", 69, 70, 95.0) == "SIGNAL_WEAKEN"
    bot._close_position.assert_called_once_with("NIFTY_CE", 95.0, "SIGNAL_WEAKEN")

    bot._close_position.reset_mock()
    assert bot._check_option_signal_health("BANKNIFTY_PE", "HOLD", 69, 70, 105.0) is None
    assert manager.active_positions["BANKNIFTY_PE"]["weak_signal_adverse_checks"] == 0
    bot._close_position.assert_not_called()

    assert bot._check_option_signal_health("BANKNIFTY_PE", "HOLD", 69, 70, 95.0) is None
    assert bot._check_option_signal_health("BANKNIFTY_PE", "HOLD", 69, 70, 95.0) == "SIGNAL_WEAKEN"
    bot._close_position.assert_called_once_with("BANKNIFTY_PE", 95.0, "SIGNAL_WEAKEN")


def test_option_signal_weakening_confirmation_is_shared_across_modes():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        130,
        100.0,
        80.0,
        110.0,
        signal_score=80,
        minimum_signal_score=70,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
    )
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot.paper_trading_enabled = False
    bot.live_orders_enabled = True
    bot.trade_journal = Mock()
    bot._close_position = Mock()

    assert bot._check_option_signal_health("NIFTY_CE", "HOLD", 69, 70, 95.0) is None
    assert bot._check_option_signal_health("NIFTY_CE", "HOLD", 69, 70, 95.0) == "SIGNAL_WEAKEN"
    bot._close_position.assert_called_once_with("NIFTY_CE", 95.0, "SIGNAL_WEAKEN")


def test_option_signal_confirmation_count_is_restored_with_position():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        130,
        100.0,
        80.0,
        110.0,
        signal_score=80,
        staged_targets_enabled=True,
        weak_signal_adverse_checks=1,
    )

    assert manager.active_positions["NIFTY_CE"]["weak_signal_adverse_checks"] == 1


def test_live_milestone_moves_existing_broker_protective_stop():
    position = {
        "direction": "BUY",
        "take_profit": 120.0,
        "target_stage": 1,
        "milestone_reached_pct": 10.0,
        "milestone_started_at": datetime.now(ZoneInfo("Asia/Kolkata")),
        "trailing_stop": 100.0,
        "signal_score": 85,
        "current_signal_score": 85,
        "decision_window_minutes": 10,
        "protection_order_id": "protect-123",
    }
    bot = object.__new__(KiteTradingBot)
    bot.live_orders_enabled = True
    bot.kite_stream = Mock()
    bot.trade_journal = Mock()
    bot.telegram_notifier = Mock()

    assert bot._publish_target_update("NIFTY_CE", position, 100.0) is True

    bot.kite_stream.modify_protective_stop_order.assert_called_once_with(
        "NIFTY_CE", "BUY", "protect-123", 100.0
    )


def test_option_sizing_requires_two_risk_qualified_lots_and_caps_at_three():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"option_min_lots": 2, "option_max_lots": 3}
    bot.intraday_manager = IntradayManager()
    bot.intraday_manager.set_contract_specs(
        {"NIFTY_CE": {"lot_size": 65, "multiplier": 1}}
    )
    bot.intraday_manager.calculate_option_size = Mock(return_value=65)

    assert bot._calculate_option_quantity("NIFTY_CE", 50.0, 0.20) == 0
    assert not bot._option_quantity_within_lot_bounds("NIFTY_CE", 65)
    bot.intraday_manager.calculate_option_size.return_value = 5 * 65
    assert bot._calculate_option_quantity("NIFTY_CE", 50.0, 0.20) == 3 * 65
    assert bot._option_quantity_within_lot_bounds("NIFTY_CE", 3 * 65)


def test_option_trade_risk_is_capped_at_one_lot_premium_value():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "option_min_lots": 1,
        "option_max_lots": 3,
        "option_max_risk_per_lot_pct": 20.0,
    }
    bot.intraday_manager = IntradayManager(
        account_size=100_000,
        risk_per_trade_pct=1.0,
        daily_max_loss=350.0,
    )
    bot.intraday_manager.set_contract_specs(
        {"NIFTY_CE": {"lot_size": 65, "multiplier": 1}}
    )

    quantity = bot._calculate_option_quantity("NIFTY_CE", 12.0, 0.20)

    assert quantity == 65
    assert bot.intraday_manager.estimate_trade_risk(
        "NIFTY_CE", quantity, 12.0, 12.0 * (1.0 - 0.20)
    ) == pytest.approx(156.0)


def test_staged_target_does_not_move_back_when_price_retraces():
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        1,
        100.0,
        80.0,
        110.0,
        signal_score=85,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
    )

    manager.update_trailing_stop("NIFTY_CE", 110.0)
    manager.update_trailing_stop("NIFTY_CE", 120.0)
    manager.update_trailing_stop("NIFTY_CE", 115.0)

    position = manager.active_positions["NIFTY_CE"]
    assert position["target_stage"] == 2
    assert position["take_profit"] == 130.0
    assert position["trailing_stop"] == 110.0


def test_target_advance_updates_open_journal_and_telegram(tmp_path):
    manager = IntradayManager()
    manager.register_position(
        "NIFTY_CE",
        "BUY",
        1,
        100.0,
        80.0,
        110.0,
        signal_score=85,
        staged_targets_enabled=True,
        target_increment_pct=0.10,
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

    assert bot._check_position_exit("NIFTY_CE", 110.0) is None

    open_trade = journal.get_open_trade("NIFTY_CE", "BUY")
    assert open_trade["take_profit"] == 120.0
    assert open_trade["target_stage"] == 1
    notifier.send_message.assert_called_once()
    assert "Next target: 120.00" in notifier.send_message.call_args.args[0]


def test_disabling_trailing_keeps_fixed_target_exit():
    manager = IntradayManager(trailing_enabled=False)
    manager.register_position("NIFTY", "BUY", 1, 55.0, 50.0, 85.0)
    bot = object.__new__(KiteTradingBot)
    bot.intraday_manager = manager
    bot._close_position = Mock()

    assert bot._check_position_exit("NIFTY", 85.0) == "TAKE_PROFIT"


def test_maximum_engine_score_is_not_rejected_by_accuracy_filter():
    filters = AccuracyFilters()

    assert filters.should_enter_trade(
        signal="BUY",
        score=85,
        volatility_acceptable=True,
        confirmation=True,
    ) is True


@pytest.mark.parametrize(
    (
        "paper_trading_enabled",
        "live_orders_enabled",
        "buy_outcome",
        "entry_recorded",
    ),
    [
        (True, False, "trade_opened", True),
        (True, False, "trade_blocked:consecutive_losses", False),
        (False, True, "trade_opened", True),
    ],
)
def test_option_entry_uses_one_strategy_in_both_modes(
    paper_trading_enabled, live_orders_enabled, buy_outcome, entry_recorded
):
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "instrument_tokens": {"NIFTY": 1},
        "options_underlyings": ["NIFTY"],
        "benchmark_symbols": [],
        "late_window_enabled": False,
        "allow_trend_continuation": True,
        "min_entry_score": 55,
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
    underlying_bars[-1] = Bar(
        datetime(2026, 9, 24, 10, 29), 25000, 25020, 24990, 25020, 100
    )
    bot.bar_builder = Mock()
    bot.bar_builder.get_bars.side_effect = lambda token, limit: (
        underlying_bars if token == 1 else option_bars
    )
    bot.intraday_manager = Mock()
    bot.intraday_manager.should_exit_all_positions.return_value = False
    bot.use_market_context = False
    bot.paper_trading_enabled = paper_trading_enabled
    bot.min_entry_score = 55
    bot.live_orders_enabled = live_orders_enabled
    bot.benchmark_symbol = "NIFTY"
    bot.news_monitor = None
    bot.premarkarket_candidates = []
    bot.option_quote_cache = {"NIFTY_CE": {"last_price": 100}}
    bot.latest_prices = {}
    bot.kite_stream = SimpleNamespace(contract_expiries={})
    bot._preferred_option_symbol = Mock(return_value="NIFTY_CE")
    bot._has_option_candle_momentum = Mock(return_value=True)
    bot._option_quality_gate = Mock(return_value=(True, "OK"))
    bot._record_decision = Mock()
    bot._handle_buy_signal = Mock(return_value=buy_outcome)
    bot.accuracy_filters = Mock()
    bot.accuracy_filters.min_score_floor = 55
    bot.accuracy_filters.validate_entry_with_reason.side_effect = (
        lambda **kwargs: (
            kwargs["score"] >= kwargs["min_score"],
            f"score<{kwargs['min_score']}",
        )
    )

    with patch("market_bot.kite_main.market_session_state", return_value="REGULAR_SESSION"), \
        patch(
            "market_bot.kite_main.score_market",
            return_value=SimpleNamespace(
                signal="BUY", score=60, reasons=[], strategy_variant=None
            ),
        ) as score_market_mock:
        bot.on_bar_complete("100", option_bars[-1])

    assert score_market_mock.call_args.kwargs[
        "volume_confirmation_history"
    ] == [{"volume": 10}] * len(underlying_bars)
    assert score_market_mock.call_args.kwargs[
        "allow_trend_continuation"
    ] is True
    assert bot.accuracy_filters.validate_entry_with_reason.call_args.kwargs[
        "min_score"
    ] == 55
    assert bot.accuracy_filters.validate_entry_with_reason.call_args.kwargs[
        "record_entry"
    ] is False
    bot._handle_buy_signal.assert_called_once()
    assert bot._handle_buy_signal.call_args.kwargs[
        "minimum_signal_score"
    ] == 55
    if entry_recorded:
        bot.accuracy_filters.record_entry.assert_called_once_with(
            "NIFTY_CE",
            bot.accuracy_filters.validate_entry_with_reason.call_args.kwargs[
                "current_time"
            ],
        )
    else:
        bot.accuracy_filters.record_entry.assert_not_called()
    assert not any(
        key.startswith(("paper_shadow_", "allow_paper_shadow"))
        for key in score_market_mock.call_args.kwargs
    )
    validated_history = bot.accuracy_filters.validate_entry_with_reason.call_args.kwargs[
        "history"
    ]
    assert validated_history == [item.to_dict() for item in underlying_bars]
    assert (
        bot.accuracy_filters.validate_entry_with_reason.call_args.kwargs["min_score"]
        == 55
    )
    assert (
        "require_confirmation"
        not in bot.accuracy_filters.validate_entry_with_reason.call_args.kwargs
    )
    underlying_bars[-1] = Bar(
        datetime(2026, 9, 24, 10, 29), 25000, 25010, 24990, 25005, 100
    )
    bot._has_option_candle_momentum.side_effect = (
        KiteTradingBot._has_option_candle_momentum
    )
    bot._record_decision.reset_mock()
    bot._option_quality_gate.reset_mock()

    with patch("market_bot.kite_main.market_session_state", return_value="REGULAR_SESSION"), \
        patch(
            "market_bot.kite_main.score_market",
            return_value=SimpleNamespace(signal="BUY", score=80, reasons=[]),
        ):
        bot.on_bar_complete("100", option_bars[-1])

    bot._option_quality_gate.assert_not_called()
    assert bot._record_decision.call_args.args[5] == (
        "OPTION_FILTER_WEAK_CANDLE_MOMENTUM"
    )


@pytest.mark.parametrize(
    ("primary_reasons", "existing_positions", "expected_trade"),
    [
        ([], {}, True),
        (["RSI overbought against BUY"], {}, False),
        ([], {"NIFTY_PE": {"direction": "BUY"}}, False),
    ],
)
def test_support_reversal_candidate_uses_existing_paper_entry_gates(
    primary_reasons, existing_positions, expected_trade
):
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "instrument_tokens": {"NIFTY": 1},
        "benchmark_symbols": [],
        "late_window_enabled": False,
        "allow_trend_continuation": True,
        "min_entry_score": 55,
        "support_reversal_enabled": True,
        "support_reversal_min_premium": 5.0,
        "support_reversal_min_score": 75,
        "support_reversal_min_candle_body_ratio": 0.2,
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
    underlying_bars[-1] = Bar(
        datetime(2026, 9, 24, 10, 29), 25000, 25030, 24990, 25020, 100
    )
    bot.bar_builder = Mock()
    bot.bar_builder.get_bars.side_effect = lambda token, limit: (
        underlying_bars if token == 1 else option_bars
    )
    bot.intraday_manager = Mock()
    bot.intraday_manager.active_positions = existing_positions
    bot.intraday_manager.should_exit_all_positions.return_value = False
    bot.use_market_context = False
    bot.paper_trading_enabled = True
    bot.min_entry_score = 55
    bot.live_orders_enabled = False
    bot.benchmark_symbol = "NIFTY"
    bot.news_monitor = None
    bot.premarkarket_candidates = []
    bot.option_quote_cache = {"NIFTY_CE": {"last_price": 5.5}}
    bot.latest_prices = {}
    bot.kite_stream = SimpleNamespace(contract_expiries={})
    bot._preferred_option_symbol = Mock(return_value="NIFTY_CE")
    bot._support_reversal_candidate = Mock(
        return_value=SupportResistanceReversal(
            signal="BUY",
            level=25000.0,
            touches=2,
            bars_since_touch=0,
            bar_time=datetime(2026, 9, 24, 10, 20, tzinfo=ZoneInfo("Asia/Kolkata")),
        )
    )
    bot._mark_support_reversal_attempt = Mock()
    bot._has_option_candle_momentum = Mock(return_value=True)
    bot._option_quality_gate = Mock(return_value=(True, "OK"))
    bot._record_decision = Mock()
    bot._handle_buy_signal = Mock(return_value="trade_opened")
    bot.accuracy_filters = Mock()
    bot.accuracy_filters.min_score_floor = 55
    bot.accuracy_filters.validate_entry_with_reason.return_value = (True, "OK")

    with patch(
        "market_bot.kite_main.market_session_state",
        return_value="REGULAR_SESSION",
    ), patch(
        "market_bot.kite_main.score_market",
        return_value=SimpleNamespace(
            signal="HOLD",
            score=0,
            reasons=primary_reasons,
            strategy_variant=None,
        ),
    ):
        bot.on_bar_complete("100", option_bars[-1])

    if not expected_trade:
        bot._option_quality_gate.assert_not_called()
        bot._mark_support_reversal_attempt.assert_not_called()
        bot._handle_buy_signal.assert_not_called()
        return

    bot._option_quality_gate.assert_called_once_with(
        "NIFTY_CE",
        "BUY",
        75,
        minimum_premium_override=5.0,
    )
    bot.accuracy_filters.validate_entry_with_reason.assert_called_once()
    bot._has_option_candle_momentum.assert_called_once_with(
        "BUY",
        underlying_bars[-1].to_dict(),
        minimum_body_ratio=0.2,
    )
    bot._mark_support_reversal_attempt.assert_called_once()
    bot._handle_buy_signal.assert_called_once_with(
        "NIFTY_CE",
        option_bars[-1].close,
        75,
        strategy_variant="paper_underlying_support_reversal",
        minimum_signal_score=55,
    )


def test_option_candle_momentum_uses_requested_directional_body_ratio():
    assert KiteTradingBot._has_option_candle_momentum(
        "BUY", {"open": 100, "high": 115, "low": 95, "close": 110}
    ) is False
    assert KiteTradingBot._has_option_candle_momentum(
        "BUY",
        {"open": 100, "high": 115, "low": 95, "close": 110},
        minimum_body_ratio=0.40,
    ) is True
    assert KiteTradingBot._has_option_candle_momentum(
        "BUY", {"open": 100, "high": 110, "low": 90, "close": 95}
    ) is False
    assert KiteTradingBot._has_option_candle_momentum(
        "BUY", {"open": 100, "high": 120, "low": 90, "close": 120}
    ) is True
    assert KiteTradingBot._has_option_candle_momentum(
        "SELL", {"open": 120, "high": 120, "low": 90, "close": 90}
    ) is True
    assert KiteTradingBot._has_option_candle_momentum(
        "BUY", {"open": 100, "high": 100, "low": 100, "close": 100}
    ) is False


def test_option_candle_threshold_is_shared_across_modes():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"option_min_candle_body_ratio": 0.40}
    bot.option_min_candle_body_ratio = 0.40

    bot.paper_trading_enabled = True
    assert bot._option_candle_min_body_ratio() == 0.40
    bot.paper_trading_enabled = False
    bot.live_orders_enabled = True
    assert bot._option_candle_min_body_ratio() == 0.40


def test_options_only_underlying_bars_are_context_not_trade_entries():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "options_underlyings": ["NIFTY"],
    }
    bot.symbol_map = {1: "NIFTY"}
    bot.intraday_manager = Mock()
    bot.intraday_manager.should_exit_all_positions.return_value = False
    bot._record_decision = Mock()
    bar = Bar(datetime(2026, 9, 24, 10, 0), 25000, 25010, 24990, 25000, 100)

    bot.on_bar_complete("1", bar)

    assert bot._record_decision.call_args.args[0] == "NIFTY"
    assert bot._record_decision.call_args.args[4:] == (
        "HOLD",
        "underlying_context_only",
    )


def test_options_only_skips_entry_when_directional_option_leg_is_unavailable():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "instrument_tokens": {"NIFTY": 1, "NIFTY_CE": 100},
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
    bot._record_decision = Mock()
    bot._handle_sell_signal = Mock()
    bot.kite_stream = SimpleNamespace(contract_expiries={})

    with patch("market_bot.kite_main.market_session_state", return_value="REGULAR_SESSION"), \
        patch(
            "market_bot.kite_main.score_market",
            return_value=SimpleNamespace(signal="SELL", score=80, reasons=[]),
        ):
        bot.on_bar_complete("100", option_bars[-1])

    bot._handle_sell_signal.assert_not_called()
    assert bot._record_decision.call_args.args[5] == "OPTION_FILTER_LEG_UNAVAILABLE"


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
            "timestamp": datetime.now().astimezone(),
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


def test_best_setup_windows_are_withheld_below_screening_sample(tmp_path):
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

    assert windows == []
