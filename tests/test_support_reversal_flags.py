from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from market_bot.bar_builder import Bar
from market_bot.engine import SupportResistanceReversal
from market_bot.kite_main import KiteTradingBot
from market_bot.support_reversal_flags import (
    first_reversal_confirmation,
    level_distance_pct,
    level_stop_triggered,
)


IST = ZoneInfo("Asia/Kolkata")


def _bars(start, *, low, high, closes):
    return [
        {
            "time": start + timedelta(minutes=index),
            "open": close,
            "high": high,
            "low": low,
            "close": close,
        }
        for index, close in enumerate(closes)
    ]


def test_reversal_confirm_v2_requires_complete_test_and_reclaim_candle():
    signal_time = datetime(2026, 11, 17, 10, 0, tzinfo=IST)
    later = _bars(
        signal_time + timedelta(minutes=5),
        low=99.95,
        high=101,
        closes=[100.2, 100.3, 100.4, 100.6, 100.7],
    )
    assert first_reversal_confirmation(later, signal_time, 100, "BUY") == (
        signal_time + timedelta(minutes=10)
    )

    incomplete = later[:4]
    assert first_reversal_confirmation(incomplete, signal_time, 100, "BUY") is None
    outside_window = _bars(
        signal_time + timedelta(minutes=15),
        low=99.95,
        high=101,
        closes=[100.2, 100.3, 100.4, 100.6, 100.7],
    )
    assert first_reversal_confirmation(outside_window, signal_time, 100, "BUY") is None
    resistance = _bars(
        signal_time + timedelta(minutes=5),
        low=99,
        high=100.05,
        closes=[99.8, 99.7, 99.6, 99.5, 99.63],
    )
    assert first_reversal_confirmation(
        resistance, signal_time, 100, "SELL"
    ) == signal_time + timedelta(minutes=10)


def test_level_stop_v2_respects_direction_buffer_and_entry_distance():
    assert level_stop_triggered("BUY", 99.89, 100, 0.10)
    assert not level_stop_triggered("BUY", 99.91, 100, 0.10)
    assert level_stop_triggered("SELL", 100.11, 100, 0.10)
    assert not level_stop_triggered("SELL", 100.09, 100, 0.10)
    assert abs(level_distance_pct(100.3, 100) - 0.3) < 1e-12
    assert abs(level_distance_pct(99.7, 100) - 0.3) < 1e-12


def test_paper_only_flags_are_disabled_for_live_and_level_stop_exits_at_bid():
    now = datetime(2026, 11, 17, 10, 10, tzinfo=IST)
    position = {
        "support_reversal_level_v2": 100.0,
        "support_reversal_signal_v2": "BUY",
        "support_reversal_buffer_pct_v2": 0.1,
        "direction": "BUY",
    }
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "mode": "PAPER",
        "trading_mode": "intraday_options",
        "level_stop_v2": True,
        "instrument_tokens": {"NIFTY": 1},
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.bar_builder = SimpleNamespace(
        get_bars=lambda token, limit: [
            Bar(now - timedelta(minutes=1), 100.0, 100.1, 99.8, 99.89, 10)
        ]
    )
    bot.option_quote_cache = {"NIFTY_CE": {"bid": 49.5, "ask": 50.0}}
    bot._option_quote_metrics = lambda quote, now=None: {
        "valid": True,
        "fresh": True,
        "bid": quote["bid"],
    }
    bot._close_position = Mock(return_value=True)

    assert bot._support_reversal_level_stop("NIFTY_CE", position) is True
    bot._close_position.assert_called_once_with(
        "NIFTY_CE", 49.5, "SUPPORT_REVERSAL_LEVEL_STOP_V2"
    )

    live_bot = object.__new__(KiteTradingBot)
    live_bot.config = {
        **bot.config,
        "mode": "LIVE",
        "reversal_confirm_v2": True,
    }
    live_bot.paper_trading_enabled = False
    live_bot.live_orders_enabled = True
    assert live_bot._paper_change_enabled("level_stop_v2") is False
    assert live_bot._paper_change_enabled("reversal_confirm_v2") is False

    bot.config["reversal_confirm_v2"] = True
    assert bot._paper_change_enabled("reversal_confirm_v2") is True
    bot.simulation_mode = True
    assert bot._paper_change_enabled("reversal_confirm_v2") is False


def test_reversal_confirm_v2_waits_for_completed_five_minute_bar_and_next_minute():
    signal_time = datetime(2026, 11, 17, 10, 0, tzinfo=IST)
    candidate = SupportResistanceReversal(
        signal="BUY",
        level=100.0,
        touches=2,
        bars_since_touch=1,
        bar_time=signal_time,
    )
    underlying_bars = [
        Bar(
            signal_time + timedelta(minutes=5 + minute),
            100.1,
            101.0,
            99.95,
            close,
            10,
        )
        for minute, close in enumerate((100.2, 100.3, 100.4, 100.6, 100.7))
    ]
    bot = object.__new__(KiteTradingBot)
    bot._support_reversal_confirmation_pending = {}

    before_close = bot._support_reversal_confirmation_candidate(
        "NIFTY_CE",
        underlying_bars,
        candidate,
        signal_time,
        signal_time + timedelta(minutes=9, seconds=59),
    )
    assert before_close is None

    at_close = bot._support_reversal_confirmation_candidate(
        "NIFTY_CE",
        underlying_bars,
        None,
        signal_time,
        signal_time + timedelta(minutes=10),
    )
    assert at_close == candidate

    after_next_bar = bot._support_reversal_confirmation_candidate(
        "NIFTY_CE",
        underlying_bars,
        None,
        signal_time,
        signal_time + timedelta(minutes=11, seconds=1),
    )
    assert after_next_bar is None


def test_level_stop_v2_metadata_is_attached_only_to_support_reversal_route():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "mode": "PAPER",
        "level_stop_v2": True,
        "trading_mode": "intraday_options",
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot._options_enabled = lambda: True
    bot._support_reversal_entry_metadata = {
        "NIFTY_CE": {"level": 25000.0, "signal": "BUY", "buffer_pct": 0.1}
    }
    position = {"direction": "BUY"}
    bot._attach_support_reversal_level_stop(
        "NIFTY_CE",
        position,
        {"route": "scored", "strategy_variant": "primary"},
    )
    assert "support_reversal_level_v2" not in position

    bot._attach_support_reversal_level_stop(
        "NIFTY_CE",
        position,
        {
            "route": "support_reversal",
            "strategy_variant": "paper_underlying_support_reversal",
        },
    )
    assert position["support_reversal_level_v2"] == 25000.0
    assert position["support_reversal_signal_v2"] == "BUY"
