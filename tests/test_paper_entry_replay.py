from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tools.paper_entry_replay import (
    first_five_minute_confirmation,
    runtime_five_minute_confirmation,
    simulate_fixed_exit,
)


IST = ZoneInfo("Asia/Kolkata")


def test_five_minute_confirmation_requires_directional_continuation():
    signal_time = datetime(2026, 11, 16, 10, 0, tzinfo=IST)
    bars = [
        {
            "time": signal_time + timedelta(minutes=minute),
            "close": 100.0 + minute,
        }
        for minute in range(5)
    ]

    end_time, close, status = first_five_minute_confirmation(
        bars,
        signal_time,
        confirmation_close=103.0,
        leg="CE",
    )

    assert end_time == signal_time + timedelta(minutes=5)
    assert close == 104.0
    assert status == "continues"

    assert first_five_minute_confirmation(
        bars,
        signal_time,
        confirmation_close=104.0,
        leg="CE",
    )[2] == "not_continued"


def test_five_minute_confirmation_does_not_skip_incomplete_intervals():
    signal_time = datetime(2026, 11, 16, 10, 0, tzinfo=IST)
    bars = [
        {
            "time": signal_time + timedelta(minutes=minute),
            "close": 100.0 + minute,
        }
        for minute in range(2)
    ] + [
        {
            "time": signal_time + timedelta(minutes=minute),
            "close": 100.0 + minute,
        }
        for minute in range(3, 8)
    ]

    assert first_five_minute_confirmation(
        bars,
        signal_time,
        confirmation_close=100.0,
        leg="CE",
    ) == (None, None, "five_minute_path_incomplete")


def test_runtime_five_minute_confirmation_accepts_seconds_and_clock_boundaries():
    window_start = datetime(2026, 11, 16, 10, 5, tzinfo=IST)
    bars = [
        {
            "time": window_start - timedelta(seconds=1),
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
        },
        *[
            {
                "time": window_start + timedelta(minutes=minute, seconds=17),
                "open": 100.0 + minute,
                "high": 102.0 + minute,
                "low": 99.0 + minute,
                "close": 101.0 + minute,
            }
            for minute in range(5)
        ],
        {
            "time": window_start + timedelta(minutes=5),
            "open": 999.0,
            "high": 999.0,
            "low": 999.0,
            "close": 999.0,
        },
    ]

    completed_at, close, status = runtime_five_minute_confirmation(
        bars,
        datetime(2026, 11, 16, 10, 2, 18, tzinfo=IST),
        confirmation_close=104.0,
        leg="CE",
    )

    assert completed_at == window_start + timedelta(minutes=5, seconds=17)
    assert close == 105.0
    assert status == "passed"

    assert runtime_five_minute_confirmation(
        bars[:3] + bars[4:-1],
        datetime(2026, 11, 16, 10, 2, 18, tzinfo=IST),
        confirmation_close=104.0,
        leg="CE",
    ) == (None, None, "data_missing")


@pytest.mark.parametrize(
    ("leg", "reference", "expected"),
    [("CE", 105.0, "failed"), ("PE", 106.0, "passed")],
)
def test_runtime_five_minute_confirmation_uses_strict_directional_close(
    leg, reference, expected
):
    start = datetime(2026, 11, 16, 10, 5, tzinfo=IST)
    bars = [
        {
            "time": start + timedelta(minutes=minute, seconds=9),
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0 + minute,
        }
        for minute in range(5)
    ]

    assert runtime_five_minute_confirmation(
        bars,
        datetime(2026, 11, 16, 10, 2, 9, tzinfo=IST),
        confirmation_close=reference,
        leg=leg,
    )[2] == expected


def test_fixed_exit_uses_stop_first_when_both_levels_touch_in_one_candle():
    entry_time = datetime(2026, 11, 16, 10, 0, tzinfo=IST)
    candles = [
        {
            "time": entry_time,
            "low": 88.0,
            "high": 125.0,
            "bid": 89.0,
            "gap": False,
        }
    ]
    quotes = [
        {
            "time": entry_time + timedelta(seconds=10),
            "bid": 121.0,
            "ask": 122.0,
        },
        {
            "time": entry_time + timedelta(seconds=20),
            "bid": 89.0,
            "ask": 90.0,
        },
    ]

    result = simulate_fixed_exit(
        candles,
        quotes,
        entry_time,
        entry_price=100.0,
        quantity=10,
    )

    assert result.status == "complete"
    assert result.exit_reason == "stop"
    assert result.exit_price == 89.0
    assert result.net_rupees < (89.0 - 100.0) * 10
    assert result.net_r is not None
    assert result.net_r < -1.0


def test_fixed_exit_does_not_use_pre_entry_candle_extremes():
    entry_time = datetime(2026, 11, 16, 10, 0, 30, tzinfo=IST)
    candle_start = entry_time - timedelta(seconds=30)
    candles = [
        {
            "time": candle_start,
            "low": 80.0,
            "high": 130.0,
            "bid": 100.0,
            "gap": False,
        },
        {
            "time": entry_time + timedelta(minutes=1),
            "low": 99.0,
            "high": 101.0,
            "bid": 100.0,
            "gap": False,
        },
    ]
    quotes = [
        {
            "time": entry_time + timedelta(seconds=10),
            "bid": 100.0,
            "ask": 101.0,
        },
        {
            "time": entry_time + timedelta(minutes=1, seconds=10),
            "bid": 100.0,
            "ask": 101.0,
        },
    ]

    result = simulate_fixed_exit(
        candles,
        quotes,
        entry_time,
        entry_price=100.0,
        quantity=1,
    )

    assert result.status == "complete"
    assert result.exit_reason == "session_end"


def test_fixed_exit_supports_underlying_level_stop_at_next_option_bid():
    entry_time = datetime(2026, 11, 16, 10, 0, tzinfo=IST)
    candles = [
        {
            "time": entry_time,
            "low": 99.0,
            "high": 101.0,
            "bid": 100.0,
            "gap": False,
        }
    ]
    quotes = [
        {
            "time": entry_time + timedelta(minutes=1),
            "bid": 98.5,
            "ask": 99.0,
        }
    ]
    underlying_bars = [
        {
            "time": entry_time,
            "close": 99.89,
        }
    ]

    result = simulate_fixed_exit(
        candles,
        quotes,
        entry_time,
        entry_price=100.0,
        quantity=1,
        underlying_bars=underlying_bars,
        support_level=100.0,
        support_signal="BUY",
        level_buffer_pct=0.10,
    )

    assert result.status == "complete"
    assert result.exit_reason == "level_stop"
    assert result.exit_time == entry_time + timedelta(minutes=1)
    assert result.exit_price == 98.5
