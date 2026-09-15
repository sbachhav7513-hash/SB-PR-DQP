from datetime import datetime, timedelta
from market_bot.engine import score_market

# A steady bullish trend that should be tradable, but is not near the 10-bar breakout high.
base = datetime(2026, 9, 15, 9, 30, 0)
history = [
    {"time": base + timedelta(minutes=i), "close": 100.0 + i * 0.65}
    for i in range(60)
]
result = score_market('TEST', history)
print(result.score)
print(result.signal)
print(result.reasons)
