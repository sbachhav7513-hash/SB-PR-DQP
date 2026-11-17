from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tools.paper_entry_replay import (
    first_five_minute_confirmation,
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
