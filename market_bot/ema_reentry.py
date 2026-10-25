from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional


@dataclass(frozen=True)
class EmaReentrySignal:
    option_leg: str
    signal: str
    stop_time: datetime
    crossover_time: datetime
    signal_time: datetime
    crossover_level: float
    confirmation_close: float
    vwap: Optional[float]
    reason: str


def _timestamp(value: object) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _aligned_ema(values: List[float], period: int) -> List[Optional[float]]:
    output: List[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return output
    previous = sum(values[:period]) / period
    output[period - 1] = previous
    multiplier = 2.0 / (period + 1)
    for index in range(period, len(values)):
        previous += multiplier * (values[index] - previous)
        output[index] = previous
    return output


def _vwap_at(history: List[Dict], signal_index: int) -> Optional[float]:
    signal_time = _timestamp(
        history[signal_index].get("time", history[signal_index].get("date"))
    )
    if signal_time is None:
        return None
    numerator = 0.0
    denominator = 0.0
    for candle in history[: signal_index + 1]:
        timestamp = _timestamp(candle.get("time", candle.get("date")))
        if timestamp is None or timestamp.date() != signal_time.date():
            continue
        try:
            high = float(candle["high"])
            low = float(candle["low"])
            close = float(candle["close"])
            volume = float(candle.get("volume", 0.0))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not all(math.isfinite(value) for value in (high, low, close, volume)):
            continue
        if volume < 0:
            continue
        numerator += ((high + low + close) / 3.0) * volume
        denominator += volume
    return numerator / denominator if denominator > 0 else None


def find_ema_reentry_signal(
    history: List[Dict],
    option_leg: str,
    stopped_at: datetime,
    *,
    window_minutes: int = 10,
) -> Optional[EmaReentrySignal]:
    """Find a post-stop EMA(5/20) cross and later close beyond its candle."""
    option_leg = option_leg.upper()
    if option_leg not in {"CE", "PE"}:
        raise ValueError("option_leg must be CE or PE")
    if window_minutes <= 0:
        raise ValueError("window_minutes must be positive")

    stop_time = _timestamp(stopped_at)
    if stop_time is None:
        return None
    deadline = stop_time + timedelta(minutes=window_minutes)
    candles = []
    for candle in history:
        timestamp = _timestamp(candle.get("time", candle.get("date")))
        try:
            values = tuple(
                float(candle[key]) for key in ("high", "low", "close")
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (
            timestamp is None
            or not all(math.isfinite(value) for value in values)
            or values[0] < values[1]
        ):
            continue
        candles.append((timestamp, candle, values))

    if len(candles) < 21:
        return None
    valid_candle_history = [candle for _, candle, _ in candles]
    closes = [values[2] for _, _, values in candles]
    fast = _aligned_ema(closes, 5)
    slow = _aligned_ema(closes, 20)
    bullish = option_leg == "CE"
    for cross_index in range(20, len(candles)):
        cross_bar_time, _, (cross_high, cross_low, _) = candles[cross_index]
        cross_time = cross_bar_time + timedelta(minutes=1)
        if cross_time <= stop_time or cross_time > deadline:
            continue
        prior_fast = fast[cross_index - 1]
        prior_slow = slow[cross_index - 1]
        current_fast = fast[cross_index]
        current_slow = slow[cross_index]
        if None in (prior_fast, prior_slow, current_fast, current_slow):
            continue
        crossed = (
            prior_fast <= prior_slow and current_fast > current_slow
            if bullish
            else prior_fast >= prior_slow and current_fast < current_slow
        )
        if not crossed:
            continue

        for signal_index in range(cross_index + 1, len(candles)):
            signal_bar_time, _, (_, _, close) = candles[signal_index]
            signal_time = signal_bar_time + timedelta(minutes=1)
            if signal_time > deadline:
                break
            trend_valid = (
                fast[signal_index] is not None
                and slow[signal_index] is not None
                and (
                    fast[signal_index] > slow[signal_index]
                    if bullish
                    else fast[signal_index] < slow[signal_index]
                )
            )
            broke_level = close > cross_high if bullish else close < cross_low
            if trend_valid and broke_level:
                direction = "BUY" if bullish else "SELL"
                return EmaReentrySignal(
                    option_leg=option_leg,
                    signal=direction,
                    stop_time=stop_time,
                    crossover_time=cross_time,
                    signal_time=signal_time,
                    crossover_level=cross_high if bullish else cross_low,
                    confirmation_close=close,
                    vwap=_vwap_at(valid_candle_history, signal_index),
                    reason=(
                        f"EMA(5) crossed {'above' if bullish else 'below'} "
                        "EMA(20), then underlying closed "
                        f"{'above crossover high' if bullish else 'below crossover low'}"
                    ),
                )
    return None
