from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from .strategy import ema, rsi

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class TradingScore:
    ticker: str
    score: int
    signal: str
    reasons: List[str] = field(default_factory=list)


def _extract_timestamps(history: List[Dict]) -> List[datetime]:
    timestamps: List[datetime] = []
    for item in history:
        value = item.get("time")
        if isinstance(value, datetime):
            timestamps.append(value)
        elif isinstance(value, str):
            try:
                timestamps.append(datetime.fromisoformat(value))
            except ValueError:
                continue
    return timestamps


def _current_session_history(history: List[Dict]) -> List[Dict]:
    """Ignore stale bars from prior trading sessions when evaluating live signals."""
    if not history:
        return []

    parsed: List[datetime] = []
    for item in history:
        value = item.get("time")
        dt = None
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value)
            except ValueError:
                continue

        if dt is None:
            continue
        if dt.tzinfo is not None:
            dt = dt.astimezone(IST)
        else:
            dt = dt.replace(tzinfo=IST)
        parsed.append(dt)

    if not parsed:
        return list(history)

    current_day = max(parsed).date()
    same_session = []
    for item in history:
        value = item.get("time")
        dt = None
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value)
            except ValueError:
                continue

        if dt is None:
            continue
        if dt.tzinfo is not None:
            dt = dt.astimezone(IST)
        else:
            dt = dt.replace(tzinfo=IST)
        if dt.date() == current_day:
            same_session.append(item)

    return same_session if same_session else list(history)


def market_session_state(history: List[Dict]) -> str:
    """Classify bar timestamps as before-open, regular-session, or after-close."""
    history = _current_session_history(history)
    timestamps = _extract_timestamps(history)
    if not timestamps:
        return "UNKNOWN"

    if all((ts.hour < 9) or (ts.hour == 9 and ts.minute < 15) for ts in timestamps):
        return "BEFORE_OPEN"
    if all(ts.hour > 15 or (ts.hour == 15 and ts.minute >= 30) for ts in timestamps):
        return "AFTER_CLOSE"
    return "REGULAR_SESSION"


def market_session_label(history: List[Dict]) -> str:
    """Return a short, uniform label for the current market session."""
    state = market_session_state(history)
    labels = {
        "BEFORE_OPEN": "before open",
        "REGULAR_SESSION": "regular session",
        "AFTER_CLOSE": "after close",
        "UNKNOWN": "unknown",
    }
    return labels.get(state, "unknown")


def score_market(
    ticker: str,
    history: List[Dict],
    ema_fast: int = 9,
    ema_slow: int = 21,
    rsi_period: int = 14,
    context_history: Optional[List[Dict]] = None,
    allow_before_open: bool = False,
) -> TradingScore:
    history = _current_session_history(history)
    closes = [item["close"] for item in history if "close" in item]
    if len(closes) < max(ema_slow + 1, rsi_period + 1, 30):
        return TradingScore(ticker=ticker, score=0, signal="HOLD", reasons=["Not enough data"])

    session_state = market_session_state(history)
    if session_state == "BEFORE_OPEN" and not allow_before_open:
        return TradingScore(
            ticker=ticker,
            score=0,
            signal="HOLD",
            reasons=["Market is before open; wait for regular session to begin"],
        )
    if session_state == "AFTER_CLOSE":
        return TradingScore(
            ticker=ticker,
            score=0,
            signal="HOLD",
            reasons=["Market is after close; no live trading signal"],
        )

    reason = (
        "Pre-market analysis active; no orders until regular session begins"
        if session_state == "BEFORE_OPEN" and allow_before_open
        else None
    )

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
        score += 25
        reasons.append("EMA bearish")

    if macd >= 0 and macd >= prev_macd - 1e-9:
        score += 18
        reasons.append("MACD improving")
    elif macd <= 0 and macd <= prev_macd + 1e-9:
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
        and price > closes[-20]
        and trend_strength > 0.02
        and macd >= 0
        and macd >= prev_macd - 1e-9
    )
    down_trend_conf = (
        fast_now < slow_now
        and price < closes[-20]
        and trend_strength > 0.02
        and macd <= 0
        and macd <= prev_macd + 1e-9
    )

    if score >= 55 and up_trend_conf and price >= recent_high * 0.997:
        signal = "BUY"
    elif score >= 55 and down_trend_conf and price <= recent_low * 1.003:
        signal = "SELL"
    elif score >= 60 and up_trend_conf and price >= recent_high * 0.999:
        signal = "BUY"
    elif score >= 60 and down_trend_conf and price <= recent_low * 1.001:
        signal = "SELL"
    else:
        signal = "HOLD"

    if context_history:
        signal, context_reason = filter_signal_by_context(
            signal, context_history, ema_fast, ema_slow
        )
        if context_reason:
            reasons.append(context_reason)

    if reason is not None:
        reasons.append(reason)

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
