from datetime import datetime, timedelta

from market_bot.bar_builder import IST, Bar, BarBuilder


def test_session_bars_keeps_current_ist_session() -> None:
    now = datetime.now(IST)
    stale = Bar(now - timedelta(days=1), 99, 100, 98, 99, 10)
    current = Bar(now, 100, 101, 99, 100, 10)

    assert BarBuilder()._session_bars([stale, current]) == [current]