from datetime import datetime, time, timedelta

from market_bot.bar_builder import IST, Bar, BarBuilder
from market_bot.kite_provider import Tick


def test_session_bars_keeps_current_ist_session() -> None:
    now = datetime.now(IST)
    stale = Bar(now - timedelta(days=1), 99, 100, 98, 99, 10)
    current = Bar(now, 100, 101, 99, 100, 10)

    assert BarBuilder()._session_bars([stale, current]) == [current]


def test_get_bars_does_not_fall_back_to_stale_session_data() -> None:
    now = datetime.now(IST)
    stale = Bar(now - timedelta(days=1), 99, 100, 98, 99, 10)
    builder = BarBuilder()
    builder.seed_bars(1, [stale])

    assert builder.get_bars(1) == []


def test_process_tick_converts_cumulative_volume_to_bar_delta() -> None:
    start = datetime.now(IST).replace(second=0, microsecond=0)
    builder = BarBuilder(interval_seconds=60)

    builder.process_tick(Tick(1, start, 100.0, volume=100))
    builder.process_tick(Tick(1, start + timedelta(seconds=30), 101.0, volume=115))
    builder.process_tick(Tick(1, start + timedelta(seconds=60), 102.0, volume=123))

    assert builder.get_bars(1)[0].volume == 15
    assert builder.get_bars(1)[0].timestamp == start


def test_process_tick_floors_slots_and_skips_minutes_without_ticks(caplog) -> None:
    start = datetime.now(IST).replace(hour=9, minute=15, second=37, microsecond=0)
    builder = BarBuilder(interval_seconds=60)

    builder.process_tick(Tick(1, start, 100.0))
    builder.process_tick(Tick(1, start + timedelta(seconds=33), 101.0))
    builder.process_tick(Tick(1, start + timedelta(minutes=3, seconds=23), 104.0))

    bars = builder.get_bars(1)
    assert [bar.timestamp for bar in bars] == [
        start.replace(minute=15, second=0),
        start.replace(minute=16, second=0),
    ]
    assert [bar.close for bar in bars] == [100.0, 101.0]
    assert "Feed gap for token 1: no ticks for 120s before" in caplog.text


def test_process_tick_enforces_session_bounds() -> None:
    builder = BarBuilder(
        interval_seconds=60,
        session_start=time(9, 15),
        session_end=time(15, 30),
    )

    builder.process_tick(
        Tick(1, datetime(2026, 11, 23, 9, 14, 59, tzinfo=IST), 99.0)
    )
    builder.process_tick(
        Tick(1, datetime(2026, 11, 23, 9, 15, tzinfo=IST), 100.0)
    )
    builder.process_tick(
        Tick(1, datetime(2026, 11, 23, 15, 30, tzinfo=IST), 101.0)
    )

    assert builder.last_bar_time[1] == datetime(2026, 11, 23, 9, 15, tzinfo=IST)
    assert builder.current_bar[1]["close"] == 100.0