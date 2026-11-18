from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from market_bot.bar_builder import Bar
from market_bot.kite_main import KiteTradingBot
from market_bot.paper_run_up import prior_60m_option_move


IST = ZoneInfo("Asia/Kolkata")


def _bars(now, last_close=109.0):
    bars = [
        Bar(
            now - timedelta(minutes=60 - offset),
            100.0,
            101.0,
            99.0,
            100.0 + (last_close - 100.0) * offset / 60,
            10,
        )
        for offset in range(61)
    ]
    return bars


def _entry_bot(symbol="NIFTY_CE", *, mode="PAPER", flag=None, bars=None):
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "mode": mode,
        "trading_mode": "intraday_options",
        "instrument_tokens": {symbol: 123},
        "option_premium_stop_pct": 0.10,
        "option_premium_target_pct": 0.20,
    }
    if flag is not None:
        bot.config["run_up_veto_v2"] = flag
    bot.paper_trading_enabled = mode == "PAPER"
    bot.live_orders_enabled = mode == "LIVE"
    bot.latest_prices = {symbol: 100.0}
    bot.option_quote_cache = {symbol: {}}
    bot.trade_journal = SimpleNamespace(
        get_open_trade=Mock(return_value=None)
    )
    bot.intraday_manager = SimpleNamespace(
        active_positions={},
        session_trade_symbols=set(),
    )
    bot.bar_builder = SimpleNamespace(
        get_bars=lambda token, limit: list(bars or [])[-limit:]
    )
    bot._entry_cutoff_reason = lambda: None
    bot._live_entry_allowed = lambda _: True
    bot._can_open_trade_for_signal = lambda *args, **kwargs: (True, "OK")
    bot._options_enabled = lambda: True
    bot._option_adaptive_exit_enabled = lambda _: False
    bot._staged_option_targets_enabled = lambda _: False
    bot._option_entry_target_pct = lambda _: 0.20
    bot._calculate_option_quantity = lambda *args: 0
    bot._entry_risk_cap = lambda: 1000.0
    return bot


def test_prior_60m_move_uses_timestamp_aligned_closes_and_ignores_future_bar():
    signal_time = datetime(2026, 11, 16, 10, 0, tzinfo=IST)
    bars = _bars(signal_time, last_close=108.0)
    bars.append(
        Bar(signal_time + timedelta(minutes=1), 200, 200, 200, 200, 1)
    )

    measurement = prior_60m_option_move(bars, signal_time)

    assert measurement.status == "complete"
    assert measurement.value_pct == pytest.approx(8.0)


def test_prior_60m_move_marks_missing_minute_as_incomplete():
    signal_time = datetime(2026, 11, 16, 10, 0, tzinfo=IST)
    bars = _bars(signal_time)
    bars.pop(20)

    measurement = prior_60m_option_move(bars, signal_time)

    assert measurement.value_pct is None
    assert measurement.status == "lookback_incomplete"
    assert measurement.fail_open_cause == "session_history_incomplete"


def test_prior_60m_move_classifies_gap_after_session_warmup():
    signal_time = datetime(2026, 11, 16, 11, 0, tzinfo=IST)
    bars = _bars(signal_time)
    bars.pop(20)

    measurement = prior_60m_option_move(bars, signal_time)

    assert measurement.status == "lookback_incomplete"
    assert measurement.fail_open_cause == "missing_minute"


@pytest.mark.parametrize("symbol", ["NIFTY_CE", "TCS_PE"])
def test_paper_run_up_veto_blocks_both_tiers_above_eight_percent(
    symbol, caplog
):
    caplog.set_level("INFO", logger="market_bot.kite_main")
    signal_time = datetime(2026, 11, 16, 10, 0, tzinfo=IST)
    bot = _entry_bot(symbol, bars=_bars(signal_time, last_close=109.0))

    result = bot._handle_buy_signal(
        symbol,
        100.0,
        80,
        entry_telemetry={"signal_time": signal_time},
    )

    assert result == "run_up_veto_v2"
    assert "prior_60m_option_move_pct=9.0000" in caplog.text
    assert (
        bot._signal_change_gate_evaluations[symbol]["run_up_veto_v2"]["passed"]
        is False
    )


@pytest.mark.parametrize(
    ("mode", "flag", "last_close", "expected"),
    [
        ("PAPER", True, 108.0, "position_size_zero"),
        ("PAPER", True, 109.0, "run_up_veto_v2"),
        ("PAPER", False, 120.0, "position_size_zero"),
        ("LIVE", True, 120.0, "position_size_zero"),
        ("BACKTEST", True, 120.0, "position_size_zero"),
    ],
)
def test_run_up_veto_threshold_rollback_and_live_isolation(
    mode, flag, last_close, expected
):
    signal_time = datetime(2026, 11, 16, 10, 0, tzinfo=IST)
    bot = _entry_bot(
        mode=mode,
        flag=flag,
        bars=_bars(signal_time, last_close=last_close),
    )

    assert (
        bot._handle_buy_signal(
            "NIFTY_CE",
            100.0,
            80,
            entry_telemetry={"signal_time": signal_time},
        )
        == expected
    )


def test_incomplete_lookback_fails_open_and_is_logged(caplog):
    caplog.set_level("INFO", logger="market_bot.kite_main")
    signal_time = datetime(2026, 11, 16, 10, 0, tzinfo=IST)
    bars = _bars(signal_time)
    bars.pop(20)
    bot = _entry_bot(bars=bars)

    result = bot._handle_buy_signal(
        "NIFTY_CE",
        100.0,
        80,
        entry_telemetry={"signal_time": signal_time},
    )

    assert result == "position_size_zero"
    assert "run_up_veto_v2 failed open; cause=session_history_incomplete" in caplog.text
    assert "failed_open" == bot._last_run_up_entry_decision["NIFTY_CE"][
        "run_up_veto_status"
    ]


def test_backfilled_measurement_is_used_by_the_existing_veto_gate():
    signal_time = datetime(2026, 11, 16, 11, 0, tzinfo=IST)
    bot = _entry_bot(flag=True)

    result = bot._handle_buy_signal(
        "NIFTY_CE",
        100.0,
        80,
        confirmed_entry_metadata={
            "signal_time": signal_time,
            "run_up_backfill_measurement": {
                "value_pct": 8.5,
                "status": "complete",
                "fail_open_cause": None,
            },
        },
    )

    assert result == "run_up_veto_v2"
    assert bot._signal_change_gate_evaluations["NIFTY_CE"]["run_up_veto_v2"][
        "prior_60m_option_move_pct"
    ] == 8.5


def test_historical_backfill_computes_the_same_61_close_measurement(monkeypatch):
    from concurrent.futures import Future
    import time

    import market_bot.kite_main as kite_main

    class InlineExecutor:
        def __init__(self, **_kwargs):
            pass

        def submit(self, function):
            future = Future()
            try:
                future.set_result(function())
            except Exception as error:
                future.set_exception(error)
            return future

    signal_time = datetime(2026, 11, 16, 11, 0, tzinfo=IST)
    rows = [
        {
            "time": signal_time - timedelta(minutes=60 - offset),
            "open": 100.0,
            "high": 110.0,
            "low": 100.0,
            "close": 100.0 + offset / 60 * 9.0,
            "volume": 1,
        }
        for offset in range(61)
    ]

    class Provider:
        def fetch_history(self, token, start, end, *, interval):
            assert token == 123
            assert start == signal_time - timedelta(minutes=60)
            assert end == signal_time + timedelta(minutes=1)
            assert interval == "minute"
            return rows

    monkeypatch.setattr(kite_main, "ThreadPoolExecutor", InlineExecutor)
    bot = object.__new__(KiteTradingBot)
    bot.config = {"instrument_tokens": {"NIFTY_CE": 123}}
    bot._run_up_backfill_provider = Provider()
    bot._run_up_backfill_last_request = time.monotonic() - 2

    state, measurement = bot._poll_run_up_backfill(
        "NIFTY_CE", signal_time, "missing_minute"
    )

    assert state == "complete"
    assert measurement.status == "complete"
    assert measurement.value_pct == pytest.approx(9.0)


def test_historical_backfill_failure_is_logged_and_fails_open(monkeypatch, caplog):
    from concurrent.futures import Future
    import time

    import market_bot.kite_main as kite_main

    class InlineExecutor:
        def __init__(self, **_kwargs):
            pass

        def submit(self, function):
            future = Future()
            try:
                future.set_result(function())
            except Exception as error:
                future.set_exception(error)
            return future

    class Provider:
        def fetch_history(self, *_args, **_kwargs):
            raise RuntimeError("historical API unavailable")

    monkeypatch.setattr(kite_main, "ThreadPoolExecutor", InlineExecutor)
    bot = object.__new__(KiteTradingBot)
    bot.config = {"instrument_tokens": {"NIFTY_CE": 123}}
    bot._run_up_backfill_provider = Provider()
    bot._run_up_backfill_last_request = time.monotonic() - 2
    signal_time = datetime(2026, 11, 16, 11, 0, tzinfo=IST)

    with caplog.at_level("WARNING", logger="market_bot.kite_main"):
        state, measurement = bot._poll_run_up_backfill(
            "NIFTY_CE", signal_time, "missing_minute"
        )

    assert state == "complete"
    assert measurement.fail_open_cause == "historical_api_error:RuntimeError"
    assert "Run-up historical backfill failed open" in caplog.text
