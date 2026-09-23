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


def market_session_state(
    history: List[Dict], now: Optional[datetime] = None
) -> str:
    """Classify bar timestamps, or the live clock when explicitly provided."""
    if now is not None:
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        else:
            now = now.astimezone(IST)
        current_minutes = now.hour * 60 + now.minute
        if current_minutes < 9 * 60 + 15:
            return "BEFORE_OPEN"
        if current_minutes >= 15 * 60 + 30:
            return "AFTER_CLOSE"
        return "REGULAR_SESSION"

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

def calculate_adx(history: List[Dict], period: int = 14) -> Optional[float]:
    """Calculate ADX from completed OHLC bars, or return None without OHLC data."""
    if len(history) < period * 2 or not all(
        all(key in bar for key in ("high", "low", "close")) for bar in history
    ):
        return None

    true_ranges: List[float] = []
    plus_moves: List[float] = []
    minus_moves: List[float] = []
    for current, previous in zip(history[1:], history[:-1]):
        true_ranges.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        ))
        up_move = current["high"] - previous["high"]
        down_move = previous["low"] - current["low"]
        plus_moves.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_moves.append(down_move if down_move > up_move and down_move > 0 else 0.0)

    dx_values: List[float] = []
    for index in range(period - 1, len(true_ranges)):
        tr_sum = sum(true_ranges[index - period + 1:index + 1])
        if tr_sum <= 0:
            dx_values.append(0.0)
            continue
        plus_di = 100.0 * sum(plus_moves[index - period + 1:index + 1]) / tr_sum
        minus_di = 100.0 * sum(minus_moves[index - period + 1:index + 1]) / tr_sum
        denominator = plus_di + minus_di
        dx_values.append(100.0 * abs(plus_di - minus_di) / denominator if denominator else 0.0)

    if len(dx_values) < period:
        return None
    return sum(dx_values[-period:]) / period


def score_market(
    ticker: str,
    history: List[Dict],
    ema_fast: int = 9,
    ema_slow: int = 21,
    rsi_period: int = 14,
    context_history: Optional[List[Dict]] = None,
    allow_before_open: bool = False,
    session_state: Optional[str] = None,
    hard_context_filter: bool = True,
    min_adx: float = 18.0,
) -> TradingScore:
    history = _current_session_history(history)
    closes = [item["close"] for item in history if "close" in item]
    if len(closes) < max(ema_slow + 1, rsi_period + 1, 30):
        return TradingScore(ticker=ticker, score=0, signal="HOLD", reasons=["Not enough data"])

    session_state = session_state or market_session_state(history)
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

    adx = calculate_adx(history)
    if adx is not None and adx < min_adx:
        return TradingScore(
            ticker=ticker,
            score=0,
            signal="HOLD",
            reasons=[f"ADX too weak ({adx:.1f} < {min_adx:.1f})"],
        )

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
        score += 18
        reasons.append("MACD weakening")

    bullish_market = fast_now > slow_now
    bearish_market = fast_now < slow_now
    if bullish_market and 45 <= rsi_now <= 70:
        score += 20
        reasons.append("RSI in trend zone")
    elif bearish_market and 30 <= rsi_now <= 55:
        score += 20
        reasons.append("RSI in trend zone")
    elif bullish_market and rsi_now < 35:
        score += 15
        reasons.append("RSI oversold")
    elif bearish_market and rsi_now > 65:
        score += 12
        reasons.append("RSI overbought")
    elif bullish_market and rsi_now > 70:
        reasons.append("RSI overbought against BUY")
    elif bearish_market and rsi_now < 30:
        reasons.append("RSI oversold against SELL")

    if price > recent_high * 0.995:
        score += 10
        reasons.append("Price near recent high")
    elif price < recent_low * 1.005:
        score += 10
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
            signal, context_history, ema_fast, ema_slow, hard_context_filter
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
    hard_block: bool = False,
) -> tuple[str, Optional[str]]:
    context_signal = market_context_signal(history, ema_fast, ema_slow)
    if context_signal == "BEARISH" and signal == "BUY":
        if hard_block:
            return "HOLD", "Benchmark trend bearish; BUY blocked"
        return signal, "Benchmark trend bearish (soft context warning)"
    if context_signal == "BULLISH" and signal == "SELL":
        if hard_block:
            return "HOLD", "Benchmark trend bullish; SELL blocked"
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
