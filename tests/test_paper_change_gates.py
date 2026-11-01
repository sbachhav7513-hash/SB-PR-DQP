from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from market_bot.bar_builder import Bar
from market_bot.engine import SupportResistanceReversal
from market_bot.kite_main import KiteTradingBot


IST = ZoneInfo("Asia/Kolkata")


def _option_bot(now, *, mode="PAPER", fallback=True):
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "mode": mode,
        "trading_mode": "intraday_options",
        "option_quote_max_age_seconds": 60,
        "option_min_premium": 12,
        "option_max_premium": 800,
        "option_min_volume": 200,
        "option_min_oi": 400,
        "option_iv_min": 0.08,
        "option_iv_max": 1.2,
        "stale_quote_candle_fallback": fallback,
        "option_candle_momentum": True,
        "index_persistence_pass": True,
        "instrument_tokens": {"NIFTY_CE": 123},
        "bar_interval_seconds": 60,
    }
    bot.paper_trading_enabled = mode == "PAPER"
    bot.live_orders_enabled = mode == "LIVE"
    bot.option_quote_cache = {
        "NIFTY_CE": {
            "last_price": 99,
            "bid": 104,
            "ask": 105,
            "volume": 500,
            "oi": 1000,
            "timestamp": now - timedelta(seconds=80),
        }
    }
    return bot


def test_stale_quote_fallback_uses_recent_completed_candle_and_conservative_fill():
    now = datetime(2026, 10, 30, 10, 0, tzinfo=IST)
    bot = _option_bot(now)
    candle = Bar(
        now - timedelta(minutes=1),
        100,
        103,
        99,
        101,
        1000,
    )

    allowed, reason = bot._option_quality_gate(
        "NIFTY_CE", "BUY", now=now, option_candle=candle
    )

    context = bot._option_gate_context["NIFTY_CE"]
    assert allowed is True
    assert reason == "OK"
    assert context["quote_source"] == "candle_fallback"
    assert context["quote_age_seconds"] == 80
    assert context["candle_age_seconds"] == 0
    assert context["gate_reference_price"] == 101.05
    assert context["fallback_fill_price"] == 105.05


def test_stale_quote_fallback_rejects_old_candle_and_is_paper_only():
    now = datetime(2026, 10, 30, 10, 0, tzinfo=IST)
    old_candle = Bar(now - timedelta(seconds=181), 100, 103, 99, 101, 1000)
    bot = _option_bot(now)

    allowed, reason = bot._option_quality_gate(
        "NIFTY_CE", "BUY", now=now, option_candle=old_candle
    )

    assert allowed is False
    assert reason.startswith("option quote stale")

    live_bot = _option_bot(now, mode="LIVE")
    recent_candle = Bar(now - timedelta(minutes=1), 100, 103, 99, 101, 1000)
    allowed, reason = live_bot._option_quality_gate(
        "NIFTY_CE", "BUY", now=now, option_candle=recent_candle
    )
    assert allowed is False
    assert reason.startswith("option quote stale")


def test_option_momentum_measurement_uses_last_completed_option_candle():
    now = datetime(2026, 10, 30, 10, 0, tzinfo=IST)
    bot = _option_bot(now)
    underlying_candle = Bar(now - timedelta(minutes=1), 100, 110, 90, 101, 100)
    option_candle = Bar(now - timedelta(minutes=1), 100, 104, 100, 103, 1000)
    bot.bar_builder = SimpleNamespace(
        get_bars=lambda token, limit: [underlying_candle]
    )
    bot.option_quote_cache["NIFTY_CE"]["timestamp"] = now

    measurements = bot._decision_gate_measurements(
        "NIFTY_CE",
        [option_candle],
        "BUY",
        75,
        "primary",
        option_candle,
    )

    assert measurements["body_ratio"] == 0.75
    assert measurements["body_ratio_threshold"] == 0.6
    assert measurements["body_ratio_source"] == "last_completed_option_candle"
    assert measurements["body_ratio_passed"] is True


def test_index_persistence_requires_three_signals_premium_rise_and_confirmed_level():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "index_persistence_pass": True,
        "mode": "PAPER",
        "trading_mode": "intraday_options",
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    candidate = SupportResistanceReversal(
        signal="BUY",
        level=25000,
        touches=3,
        bars_since_touch=1,
        bar_time=datetime(2026, 10, 30, 10, 0, tzinfo=IST),
    )

    assert not bot._index_persistence_pass(
        "NIFTY_CE",
        "BUY",
        datetime(2026, 10, 30, 10, 0, tzinfo=IST),
        100,
        None,
    )
    assert not bot._index_persistence_pass(
        "NIFTY_CE",
        "BUY",
        datetime(2026, 10, 30, 10, 2, tzinfo=IST),
        102,
        None,
    )
    assert bot._index_persistence_pass(
        "NIFTY_CE",
        "BUY",
        datetime(2026, 10, 30, 10, 4, tzinfo=IST),
        104,
        candidate,
    )
