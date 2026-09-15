from datetime import datetime, timedelta

from market_bot.bar_builder import Bar, BarBuilder

builder = BarBuilder(interval_seconds=60)
today = datetime.now().replace(hour=9, minute=30, second=0, microsecond=0)
yesterday = today - timedelta(days=1)

stale = [
    Bar(timestamp=yesterday + timedelta(minutes=index), open=100.0 + index, high=101.0 + index, low=99.0 + index, close=100.5 + index, volume=100)
    for index in range(8)
]
fresh = [
    Bar(timestamp=today + timedelta(minutes=index), open=110.0 + index, high=111.0 + index, low=109.0 + index, close=110.5 + index, volume=100)
    for index in range(12)
]

builder.seed_bars(123, stale + fresh)
bars = builder.get_bars(123, limit=50)
assert bars
assert all(bar.timestamp.date() == today.date() for bar in bars), f'Found stale bars: {[b.timestamp.date() for b in bars[:3]]}'
print('OK', len(bars), bars[-1].timestamp)
