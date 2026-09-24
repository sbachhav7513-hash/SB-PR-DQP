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


def calculate_atr(history: List[Dict], period: int = 14) -> Optional[float]:
    """Calculate ATR from completed OHLC bars without using the current bar."""
    if len(history) < period + 1 or not all(
        all(key in bar for key in ("high", "low", "close")) for bar in history
    ):
        return None

    true_ranges = [
        max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        )
        for current, previous in zip(history[1:], history[:-1])
    ]
    return sum(true_ranges[-period:]) / period


def calculate_vwap(history: List[Dict], period: int = 20) -> Optional[float]:
    """Calculate a volume-weighted average price when OHLCV data is available."""
    if len(history) < period or not all(
        all(key in bar for key in ("high", "low", "close", "volume"))
        for bar in history[-period:]
    ):
        return None

    bars = history[-period:]
    volume = sum(float(bar["volume"]) for bar in bars)
    if volume <= 0:
        return None
    return sum(
        ((bar["high"] + bar["low"] + bar["close"]) / 3.0) * float(bar["volume"])
        for bar in bars
    ) / volume


def _bollinger_widths(closes: List[float], period: int = 20) -> List[float]:
    if len(closes) < period:
        return []
    widths = []
    for end in range(period, len(closes) + 1):
        window = closes[end - period:end]
        mean = sum(window) / period
        variance = sum((value - mean) ** 2 for value in window) / period
        widths.append((4.0 * variance**0.5) / max(mean, 1e-9))
    return widths


def is_compression_breakout(history: List[Dict], lookback: int = 20) -> bool:
    """Return whether the bars before the latest bar contracted before expansion."""
    if len(history) < lookback + 20:
        return False
    closes = [bar["close"] for bar in history]
    widths = _bollinger_widths(closes[:-1])
    if len(widths) < 5:
        return False
    recent_widths = widths[-4:]
    contraction = all(
        recent_widths[index] <= recent_widths[index - 1] + 1e-12
        for index in range(1, len(recent_widths))
    )
    previous_widths = widths[-10:-4]
    narrower_than_average = bool(previous_widths) and recent_widths[-1] < (
        sum(previous_widths) / len(previous_widths)
    )
    previous_ranges = [
        bar["high"] - bar["low"]
        for bar in history[-12:-2]
        if "high" in bar and "low" in bar
    ]
    pre_breakout_range = history[-2].get("high", 0) - history[-2].get("low", 0)
    current_range = history[-1].get("high", 0) - history[-1].get("low", 0)
    range_contracted = bool(previous_ranges) and pre_breakout_range < (
        sum(previous_ranges) / len(previous_ranges)
    )
    range_expanded = bool(previous_ranges) and current_range > (
        sum(previous_ranges) / len(previous_ranges)
    )
    return contraction and narrower_than_average and range_contracted and range_expanded


def breakout_quality(history: List[Dict], direction: str, lookback: int = 20) -> bool:
    """Validate close, volume, and ATR quality for a completed breakout candle."""
    if len(history) < lookback + 15:
        return False
    if not all(
        all(key in bar for key in ("high", "low", "close", "volume"))
        for bar in history
    ):
        return False

    current = history[-1]
    previous = history[-lookback - 1:-1]
    prior_high = max(bar["high"] for bar in previous)
    prior_low = min(bar["low"] for bar in previous)
    average_volume = sum(float(bar["volume"]) for bar in previous) / lookback
    atr = calculate_atr(history[:-1])
    if atr is None or atr <= 0 or average_volume <= 0:
        return False

    candle_range = current["high"] - current["low"]
    size_ok = 0.5 * atr <= candle_range <= 2.0 * atr
    volume_ok = float(current["volume"]) > average_volume
    if direction == "BUY":
        close_outside = current["close"] > prior_high and current["close"] >= current["open"]
    elif direction == "SELL":
        close_outside = current["close"] < prior_low and current["close"] <= current["open"]
    else:
        return False
    return close_outside and volume_ok and size_ok


def higher_timeframe_signal(history: List[Dict], group_size: int = 5) -> str:
    """Derive a slower trend from groups of lower-timeframe completed bars."""
    closes = [bar["close"] for bar in history if "close" in bar]
    grouped = [
        closes[index + group_size - 1]
        for index in range(0, len(closes) - group_size + 1, group_size)
    ]
    if len(grouped) < 16:
        return "UNKNOWN"
    fast = sum(grouped[-4:]) / 4
    slow = sum(grouped[-12:]) / 12
    if fast > slow and grouped[-1] > grouped[-4]:
        return "BULLISH"
    if fast < slow and grouped[-1] < grouped[-4]:
        return "BEARISH"
    return "NEUTRAL"


def classify_price_regime(
    closes: List[float],
    sideways_range_pct: float = 1.0,
    sideways_net_move_pct: float = 1.0,
) -> str:
    """Classify close-only data for entry filtering."""
    if len(closes) < 21:
        return "UNKNOWN"

    previous_window = closes[-21:-1]
    recent_window = closes[-10:-1]
    recent_range_pct = (
        (max(recent_window) - min(recent_window)) / max(closes[-1], 1e-9) * 100.0
    )
    net_move_pct = abs(closes[-1] - closes[-20]) / max(closes[-20], 1e-9) * 100.0
    if (
        recent_range_pct < sideways_range_pct
        and net_move_pct < sideways_net_move_pct
    ):
        return "SIDEWAYS"

    previous_moves = [
        abs(previous_window[index] - previous_window[index - 1])
        for index in range(1, len(previous_window))
    ]
    average_move = sum(previous_moves) / len(previous_moves)
    latest_move = abs(closes[-1] - closes[-2])
    if average_move > 0 and latest_move > average_move * 3:
        return "EXTENDED"

    return "TRENDING"


def score_market(
    ticker: str,
    history: List[Dict],
    ema_fast: int = 9,
    ema_slow: int = 21,
    rsi_period: int = 14,
    context_history: Optional[List[Dict]] = None,
    context_histories: Optional[Dict[str, List[Dict]]] = None,
    allow_before_open: bool = False,
    session_state: Optional[str] = None,
    hard_context_filter: bool = True,
    min_adx: float = 18.0,
    sideways_range_pct: float = 1.0,
    sideways_net_move_pct: float = 1.0,
    min_trend_strength: float = 0.02,
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
    recent_window = closes[-11:-1]
    recent_high = max(recent_window)
    recent_low = min(recent_window)
    trend_strength = abs(price - closes[-20]) / max(closes[-20], 1e-9)
    regime = classify_price_regime(
        closes,
        sideways_range_pct=sideways_range_pct,
        sideways_net_move_pct=sideways_net_move_pct,
    )
    complete_ohlcv = len(history) == len(closes) and all(
        all(key in bar for key in ("open", "high", "low", "close", "volume"))
        for bar in history
    )

    compression_breakout = (
        complete_ohlcv
        and is_compression_breakout(history)
        and (
            breakout_quality(history, "BUY")
            or breakout_quality(history, "SELL")
        )
    )

    if regime == "SIDEWAYS" and not compression_breakout:
        return TradingScore(
            ticker=ticker,
            score=0,
            signal="HOLD",
            reasons=["Sideways regime: range too narrow for a directional entry"],
        )

    if regime == "EXTENDED":
        return TradingScore(
            ticker=ticker,
            score=0,
            signal="HOLD",
            reasons=["Extended move: wait for a pullback or retest before entering"],
        )

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
        and trend_strength > min_trend_strength
        and macd >= 0
        and macd >= prev_macd - 1e-9
    )
    down_trend_conf = (
        fast_now < slow_now
        and price < closes[-20]
        and trend_strength > min_trend_strength
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

    if complete_ohlcv and signal in {"BUY", "SELL"}:
        vwap = calculate_vwap(history)
        current_adx = adx
        previous_adx = calculate_adx(history[:-1])
        current_spread = abs(fast_now - slow_now) / max(price, 1e-9)
        previous_spread = abs(fast[-2] - slow[-2]) / max(closes[-2], 1e-9)
        higher_timeframe = higher_timeframe_signal(history)
        quality_reasons: List[str] = []

        if not is_compression_breakout(history):
            quality_reasons.append("No volatility compression before breakout")
        if not breakout_quality(history, signal):
            quality_reasons.append("Breakout lacks close, volume, or ATR confirmation")
        if current_adx is not None and previous_adx is not None and current_adx <= previous_adx:
            quality_reasons.append("ADX is not rising")
        if current_spread <= previous_spread:
            quality_reasons.append("EMA spread is not expanding")
        if vwap is not None and (
            (signal == "BUY" and price <= vwap)
            or (signal == "SELL" and price >= vwap)
        ):
            quality_reasons.append("Price is on the wrong side of VWAP")
        if higher_timeframe not in {"UNKNOWN", "NEUTRAL"} and (
            (signal == "BUY" and higher_timeframe != "BULLISH")
            or (signal == "SELL" and higher_timeframe != "BEARISH")
        ):
            quality_reasons.append(
                f"Higher-timeframe trend disagrees ({higher_timeframe})"
            )

        if quality_reasons:
            signal = "HOLD"
            reasons.extend(quality_reasons)
        else:
            reasons.extend(
                [
                    "Compression breakout confirmed",
                    "Volume and ATR candle-size confirmed",
                    "ADX rising and EMA spread expanding",
                    "VWAP and higher-timeframe trend aligned",
                ]
            )

    contexts = dict(context_histories or {})
    if context_history:
        contexts.setdefault("benchmark", context_history)
    for context_name, context_bars in contexts.items():
        signal, context_reason = filter_signal_by_context(
            signal, context_bars, ema_fast, ema_slow, hard_context_filter
        )
        if context_reason:
            reasons.append(f"{context_name}: {context_reason}")

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
