from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
RUN_UP_LOOKBACK_MINUTES = 60
RUN_UP_VETO_THRESHOLD_PCT = 8.0


@dataclass(frozen=True)
class OptionMoveMeasurement:
    value_pct: float | None
    status: str


def _as_ist(value: datetime | str) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=IST)
    return value.astimezone(IST)


def prior_60m_option_move(
    bars: Iterable[object], signal_time: datetime | str
) -> OptionMoveMeasurement:
    """Measure a complete, contiguous 60-minute option-close move at signal time."""
    cutoff = _as_ist(signal_time)
    if cutoff is None:
        return OptionMoveMeasurement(None, "lookback_incomplete")

    closes: dict[datetime, float] = {}
    for bar in bars:
        timestamp = _as_ist(getattr(bar, "timestamp", None))
        if timestamp is None or timestamp > cutoff:
            continue
        try:
            close = float(getattr(bar, "close"))
        except (AttributeError, TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(close) and close > 0:
            closes[timestamp] = close

    if not closes:
        return OptionMoveMeasurement(None, "lookback_incomplete")

    latest = max(closes)
    earliest = latest - timedelta(minutes=RUN_UP_LOOKBACK_MINUTES)
    expected_times = (
        earliest + timedelta(minutes=offset)
        for offset in range(RUN_UP_LOOKBACK_MINUTES + 1)
    )
    if any(timestamp not in closes for timestamp in expected_times):
        return OptionMoveMeasurement(None, "lookback_incomplete")

    start_close = closes[earliest]
    latest_close = closes[latest]
    return OptionMoveMeasurement(
        (latest_close / start_close - 1.0) * 100.0,
        "complete",
    )
