from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from .bar_builder import IST


def _bar_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)


def first_reversal_confirmation(
    bars: list[dict[str, Any]],
    signal_time: datetime,
    level: float,
    signal: str,
    *,
    touch_tolerance_pct: float = 0.10,
    window_minutes: int = 15,
) -> datetime | None:
    """Return the close time of the first qualifying completed 5-minute candle."""
    if (
        not math.isfinite(level)
        or level <= 0
        or signal not in {"BUY", "SELL"}
        or not math.isfinite(touch_tolerance_pct)
        or touch_tolerance_pct < 0
        or window_minutes <= 0
    ):
        return None
    signal_time = _bar_time(signal_time)
    if signal_time is None:
        return None
    deadline = signal_time + timedelta(minutes=window_minutes)
    buckets: dict[int, list[tuple[datetime, dict[str, Any]]]] = {}
    for bar in bars:
        timestamp = _bar_time(bar.get("time"))
        if timestamp is None:
            continue
        buckets.setdefault(int(timestamp.timestamp()) // 300, []).append(
            (timestamp, bar)
        )

    for bucket, items in sorted(buckets.items()):
        items.sort(key=lambda item: item[0])
        completed_at = items[-1][0] + timedelta(minutes=1)
        if (
            items[0][0] < signal_time
            or completed_at > deadline
            or len(items) != 5
        ):
            continue
        if any(
            items[index + 1][0] - items[index][0] != timedelta(minutes=1)
            for index in range(4)
        ):
            continue
        try:
            high = max(float(row["high"]) for _, row in items)
            low = min(float(row["low"]) for _, row in items)
            close = float(items[-1][1]["close"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        candle_range = high - low
        if (
            not all(math.isfinite(value) for value in (high, low, close))
            or candle_range <= 0
            or close < low
            or close > high
        ):
            continue
        if signal == "BUY":
            tested_level = abs(low - level) / level * 100.0 <= touch_tolerance_pct
            closed_in_direction = (close - low) / candle_range >= 0.40
        else:
            tested_level = abs(high - level) / level * 100.0 <= touch_tolerance_pct
            closed_in_direction = (close - low) / candle_range <= 0.60
        if tested_level and closed_in_direction:
            return completed_at
    return None


def level_stop_triggered(
    signal: str, close: float, level: float, buffer_pct: float
) -> bool:
    if (
        signal not in {"BUY", "SELL"}
        or not all(math.isfinite(value) for value in (close, level, buffer_pct))
        or close <= 0
        or level <= 0
        or not 0 <= buffer_pct < 100
    ):
        return False
    buffer = buffer_pct / 100.0
    if signal == "BUY":
        return close <= level * (1.0 - buffer)
    return close >= level * (1.0 + buffer)


def level_distance_pct(close: float, level: float) -> float | None:
    if (
        not math.isfinite(close)
        or not math.isfinite(level)
        or close <= 0
        or level <= 0
    ):
        return None
    return abs(close - level) / level * 100.0
