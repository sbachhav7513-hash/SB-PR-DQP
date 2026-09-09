from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .strategy import ema, rsi


@dataclass
class TradingScore:
    ticker: str
    score: int
    signal: str
    reasons: List[str] = field(default_factory=list)


def score_market(
    ticker: str,
    history: List[Dict],
    ema_fast: int = 9,
    ema_slow: int = 21,
    rsi_period: int = 14,
    context_history: Optional[List[Dict]] = None,
) -> TradingScore:
    closes = [item["close"] for item in history if "close" in item]
    if len(closes) < max(ema_slow + 1, rsi_period + 1, 40):
        return TradingScore(ticker=ticker, score=0, signal="HOLD", reasons=["Not enough data"])

    fast = ema(closes, ema_fast)
    slow = ema(closes, ema_slow)
    latest_rsi = rsi(closes, rsi_period)
    if not fast or not slow or not latest_rsi:
        return TradingScore(ticker=ticker, score=0, signal="HOLD", reasons=["Indicators unavailable"])

    price = closes[-1]
    fast_now = fast[-1]
    slow_now = slow[-1]
    rsi_now = latest_rsi[-1]
    macd = fast_now - slow_now
    prev_macd = fast[-2] - slow[-2] if len(fast) >= 2 and len(slow) >= 2 else macd
    recent_window = closes[-10:]
    recent_high = max(recent_window)
    recent_low = min(recent_window)
    trend_strength = abs(price - closes[-20]) / max(closes[-20], 1e-9)

    score = 0
    reasons: List[str] = []

    if fast_now > slow_now:
        score += 25
        reasons.append("EMA bullish")
    elif fast_now < slow_now:
        score += 10
        reasons.append("EMA bearish")

    if macd > 0 and macd >= prev_macd:
        score += 18
        reasons.append("MACD improving")
    elif macd < 0 and macd <= prev_macd:
        score += 10
        reasons.append("MACD weakening")

    if 45 <= rsi_now <= 70:
        score += 20
        reasons.append("RSI in trend zone")
    elif rsi_now < 35:
        score += 15
        reasons.append("RSI oversold")
    elif rsi_now > 65:
        score += 12
        reasons.append("RSI overbought")

    if price > recent_high * 0.995:
        score += 10
        reasons.append("Price near recent high")
    elif price < recent_low * 1.005:
        score += 8
        reasons.append("Price near recent low")

    if trend_strength > 0.02:
        score += 12
        reasons.append("Trend momentum present")

    up_trend_conf = (
        fast_now > slow_now
        and rsi_now < 70
        and rsi_now > 45
        and price > closes[-20]
        and trend_strength > 0.02
        and macd > 0
        and macd >= prev_macd
    )
    down_trend_conf = (
        fast_now < slow_now
        and rsi_now > 30
        and rsi_now < 55
        and price < closes[-20]
        and trend_strength > 0.02
        and macd < 0
        and macd <= prev_macd
    )

    if score >= 75 and up_trend_conf and price >= recent_high * 0.997:
        signal = "BUY"
    elif score >= 75 and down_trend_conf and price <= recent_low * 1.003:
        signal = "SELL"
    elif score >= 70 and up_trend_conf and price >= recent_high * 0.999 and rsi_now < 68:
        signal = "BUY"
    elif score >= 70 and down_trend_conf and price <= recent_low * 1.001 and rsi_now > 32:
        signal = "SELL"
    else:
        signal = "HOLD"

    if context_history:
        signal, context_reason = filter_signal_by_context(
            signal, context_history, ema_fast, ema_slow
        )
        if context_reason:
            reasons.append(context_reason)

    return TradingScore(ticker=ticker, score=min(score, 100), signal=signal, reasons=reasons)


def filter_signal_by_context(
    signal: str,
    history: List[Dict],
    ema_fast: int = 9,
    ema_slow: int = 21,
) -> tuple[str, Optional[str]]:
    context_signal = market_context_signal(history, ema_fast, ema_slow)
    if context_signal == "BEARISH" and signal == "BUY":
        return signal, "Benchmark trend bearish (soft context warning)"
    if context_signal == "BULLISH" and signal == "SELL":
        return signal, "Benchmark trend bullish (soft context warning)"
    return signal, None


def market_context_signal(
    history: List[Dict],
    ema_fast: int = 9,
    ema_slow: int = 21,
) -> str:
    """Return a benchmark trend suitable for filtering symbol signals."""
    closes = [item["close"] for item in history if "close" in item]
    if len(closes) < max(ema_slow + 1, 20):
        return "NEUTRAL"

    fast = ema(closes, ema_fast)
    slow = ema(closes, ema_slow)
    if not fast or not slow:
        return "NEUTRAL"

    if fast[-1] > slow[-1] and closes[-1] > closes[-20]:
        return "BULLISH"
    if fast[-1] < slow[-1] and closes[-1] < closes[-20]:
        return "BEARISH"
    return "NEUTRAL"
