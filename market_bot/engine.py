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


def score_market(ticker: str, history: List[Dict]) -> TradingScore:
    closes = [item["close"] for item in history if "close" in item]
    if len(closes) < 40:
        return TradingScore(ticker=ticker, score=0, signal="HOLD", reasons=["Not enough data"])

    fast = ema(closes, 9)
    slow = ema(closes, 21)
    latest_rsi = rsi(closes, 14)
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

    if score >= 85 and up_trend_conf and price >= recent_high * 0.995:
        signal = "BUY"
    elif score >= 85 and down_trend_conf and price <= recent_low * 1.005:
        signal = "SELL"
    elif score >= 80 and up_trend_conf and price >= recent_high * 0.998 and rsi_now < 65:
        signal = "BUY"
    elif score >= 80 and down_trend_conf and price <= recent_low * 1.002 and rsi_now > 35:
        signal = "SELL"
    else:
        signal = "HOLD"

    return TradingScore(ticker=ticker, score=min(score, 100), signal=signal, reasons=reasons)
