from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Signal:
    ticker: str
    action: str
    reason: str
    price: float


def ema(series: List[float], period: int) -> List[float]:
    if len(series) < period:
        return []

    sma = sum(series[:period]) / period
    multiplier = 2 / (period + 1)
    emas = [sma]

    for price in series[period:]:
        next_ema = (price - emas[-1]) * multiplier + emas[-1]
        emas.append(next_ema)

    return emas


def rsi(series: List[float], period: int = 14) -> List[float]:
    if len(series) <= period:
        return []

    changes = [series[i] - series[i - 1] for i in range(1, len(series))]
    gains = [change if change > 0 else 0 for change in changes[:period]]
    losses = [-change if change < 0 else 0 for change in changes[:period]]

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    output: List[float] = []
    for change in changes[period:]:
        gain = change if change > 0 else 0
        loss = -change if change < 0 else 0
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period

        if average_loss == 0:
            output.append(100.0)
        else:
            rs = average_gain / average_loss
            output.append(100.0 - (100.0 / (1 + rs)))

    return output


def analyze_history(
    ticker: str,
    history: List[Dict],
    ema_fast: int,
    ema_slow: int,
    rsi_period: int,
    alert_rsi_low: int,
    alert_rsi_high: int,
) -> Optional[Signal]:
    closes = [item["close"] for item in history]
    if len(closes) < max(ema_slow + 2, rsi_period + 2):
        return None

    fast_ema = ema(closes, ema_fast)
    slow_ema = ema(closes, ema_slow)
    latest_rsi = rsi(closes, rsi_period)

    if not fast_ema or not slow_ema or not latest_rsi:
        return None

    price = closes[-1]
    fast_now = fast_ema[-1]
    slow_now = slow_ema[-1]
    fast_prev = fast_ema[-2] if len(fast_ema) >= 2 else fast_now
    slow_prev = slow_ema[-2] if len(slow_ema) >= 2 else slow_now
    rsi_now = latest_rsi[-1]

    if fast_prev <= slow_prev and fast_now > slow_now and rsi_now < alert_rsi_high:
        return Signal(
            ticker=ticker,
            action="BUY",
            reason=f"Fast EMA crossed above slow EMA and RSI={rsi_now:.1f}",
            price=price,
        )

    if fast_prev >= slow_prev and fast_now < slow_now and rsi_now > alert_rsi_low:
        return Signal(
            ticker=ticker,
            action="SELL",
            reason=f"Fast EMA crossed below slow EMA and RSI={rsi_now:.1f}",
            price=price,
        )

    if rsi_now <= alert_rsi_low:
        return Signal(
            ticker=ticker,
            action="BUY",
            reason=f"RSI oversold at {rsi_now:.1f}",
            price=price,
        )

    if rsi_now >= alert_rsi_high:
        return Signal(
            ticker=ticker,
            action="SELL",
            reason=f"RSI overbought at {rsi_now:.1f}",
            price=price,
        )

    recent_high = max(closes[-5:]) if len(closes) >= 5 else max(closes)
    recent_low = min(closes[-5:]) if len(closes) >= 5 else min(closes)
    if price > recent_high and fast_now > slow_now:
        return Signal(
            ticker=ticker,
            action="BUY",
            reason="Price breakout above recent high with bullish EMA alignment",
            price=price,
        )

    if price < recent_low and fast_now < slow_now:
        return Signal(
            ticker=ticker,
            action="SELL",
            reason="Price dropped below recent low with bearish EMA alignment",
            price=price,
        )

    return None
