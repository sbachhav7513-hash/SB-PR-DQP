from datetime import datetime, timedelta

from market_bot.bar_builder import IST, Bar, BarBuilder
from market_bot.kite_provider import Tick


def test_session_bars_keeps_current_ist_session() -> None:
    now = datetime.now(IST)
    stale = Bar(now - timedelta(days=1), 99, 100, 98, 99, 10)
    current = Bar(now, 100, 101, 99, 100, 10)

    assert BarBuilder()._session_bars([stale, current]) == [current]


def test_process_tick_converts_cumulative_volume_to_bar_delta() -> None:
    start = datetime.now(IST)
    builder = BarBuilder(interval_seconds=60)

    builder.process_tick(Tick(1, start, 100.0, volume=100))
    builder.process_tick(Tick(1, start + timedelta(seconds=30), 101.0, volume=115))
    builder.process_tick(Tick(1, start + timedelta(seconds=60), 102.0, volume=123))

    assert builder.get_bars(1)[0].volume == 15