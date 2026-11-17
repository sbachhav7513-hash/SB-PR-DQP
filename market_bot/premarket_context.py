from __future__ import annotations

import json
import math
import os
import threading
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
CONTEXT_VERSION = "premarket_context_v1"
MARKET_OPEN = time(9, 15)
RANGE_WINDOW_END = time(10, 30)


def _number(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _local_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def _daily_candles(
    candles: Iterable[Dict[str, Any]], before: date
) -> list[Dict[str, Any]]:
    by_day: Dict[date, Dict[str, Any]] = {}
    for candle in candles:
        if not isinstance(candle, dict):
            continue
        candle_time = _local_datetime(candle.get("date", candle.get("time")))
        if candle_time is None or candle_time.date() >= before:
            continue
        open_price = _number(candle.get("open"))
        high = _number(candle.get("high"))
        low = _number(candle.get("low"))
        close = _number(candle.get("close"))
        if (
            open_price is None
            or high is None
            or low is None
            or close is None
            or high < max(open_price, close)
            or low > min(open_price, close)
            or high < low
        ):
            continue
        by_day[candle_time.date()] = {
            "date": candle_time.date().isoformat(),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "range_pct": (high - low) / open_price * 100.0,
        }
    return [by_day[key] for key in sorted(by_day)[-5:]]


def _window_range(candles: Iterable[Dict[str, Any]], session_day: date) -> Optional[float]:
    rows = []
    for candle in candles:
        if not isinstance(candle, dict):
            continue
        candle_time = _local_datetime(candle.get("date", candle.get("time")))
        if (
            candle_time is None
            or candle_time.date() != session_day
            or not MARKET_OPEN <= candle_time.time() < RANGE_WINDOW_END
        ):
            continue
        high = _number(candle.get("high"))
        low = _number(candle.get("low"))
        open_price = _number(candle.get("open"))
        if high is not None and low is not None and open_price is not None and high >= low:
            rows.append((candle_time, high, low, open_price))
    if not rows:
        return None
    rows.sort(key=lambda row: row[0])
    return (max(row[1] for row in rows) - min(row[2] for row in rows)) / rows[0][3] * 100.0


def calculate_live_range(
    candles: Iterable[Dict[str, Any]], current_day: date
) -> Dict[str, Any]:
    per_day: Dict[date, float] = {}
    materialized = list(candles)
    dates = set()
    for candle in materialized:
        if not isinstance(candle, dict):
            continue
        candle_time = _local_datetime(candle.get("date", candle.get("time")))
        if candle_time is not None and candle_time.date() < current_day:
            dates.add(candle_time.date())
    for session_day in sorted(dates, reverse=True):
        value = _window_range(materialized, session_day)
        if value is not None:
            per_day[session_day.isoformat()] = value
            if len(per_day) == 5:
                break
    per_day = dict(sorted(per_day.items()))
    prior_ranges = list(per_day.values())
    average = (
        sum(prior_ranges) / 5
        if len(prior_ranges) == 5
        else None
    )
    live_range = _window_range(materialized, current_day)
    ratio = (
        live_range / average
        if live_range is not None and average not in (None, 0)
        else None
    )
    return {
        "window_start": MARKET_OPEN.strftime("%H:%M"),
        "window_end": RANGE_WINDOW_END.strftime("%H:%M"),
        "live_range_pct": live_range,
        "prior_session_ranges_pct": per_day,
        "prior_sessions_available": len(prior_ranges),
        "average_range_pct_5_sessions_same_window": average,
        "ratio_to_5_session_average": ratio,
    }


def _five_session_return(sessions: list[Dict[str, Any]]) -> Optional[float]:
    if len(sessions) < 5:
        return None
    first_open = sessions[0]["open"]
    last_close = sessions[-1]["close"]
    return (last_close / first_open - 1.0) * 100.0


def _vix_context(candles: Iterable[Dict[str, Any]], before: date) -> Dict[str, Any]:
    sessions = _daily_candles(candles, before)
    if not sessions:
        return {
            "prior_close": None,
            "change_1d_points": None,
            "change_1d_pct": None,
        }
    latest_close = sessions[-1]["close"]
    previous_close = sessions[-2]["close"] if len(sessions) >= 2 else None
    return {
        "prior_close": latest_close,
        "change_1d_points": (
            latest_close - previous_close if previous_close is not None else None
        ),
        "change_1d_pct": (
            (latest_close / previous_close - 1.0) * 100.0
            if previous_close not in (None, 0)
            else None
        ),
    }


def build_context_snapshot(
    *,
    captured_at: datetime,
    stage: str,
    symbols: Iterable[str],
    daily_history: Dict[str, Iterable[Dict[str, Any]]],
    prices: Optional[Dict[str, Any]] = None,
    session_opens: Optional[Dict[str, Any]] = None,
    intraday_history: Optional[Dict[str, Iterable[Dict[str, Any]]]] = None,
    vix_history: Optional[Iterable[Dict[str, Any]]] = None,
    data_errors: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    local_time = captured_at.astimezone(IST) if captured_at.tzinfo else captured_at.replace(tzinfo=IST)
    prices = prices or {}
    session_opens = session_opens or {}
    intraday_history = intraday_history or {}
    data_errors = data_errors or {}
    underlyings: Dict[str, Dict[str, Any]] = {}
    for raw_symbol in dict.fromkeys(str(item).upper() for item in symbols):
        sessions = _daily_candles(daily_history.get(raw_symbol, ()), local_time.date())
        prior = sessions[-1] if sessions else None
        current_open = _number(session_opens.get(raw_symbol))
        current_price = _number(prices.get(raw_symbol))
        if current_price is None and prior is not None:
            current_price = prior["close"]
            price_source = "prior_close"
        else:
            price_source = "live"
        levels = (
            {key: prior[key] for key in ("high", "low", "close")}
            if prior is not None
            else {"high": None, "low": None, "close": None}
        )
        distances = {
            key: (
                (current_price - level) / level * 100.0
                if current_price is not None and level
                else None
            )
            for key, level in levels.items()
        }
        directions = [
            {
                "date": session["date"],
                "direction": (
                    "UP"
                    if session["close"] > session["open"]
                    else "DOWN"
                    if session["close"] < session["open"]
                    else "FLAT"
                ),
            }
            for session in sessions[-3:]
        ]
        underlyings[raw_symbol] = {
            "data_status": "available" if sessions else "unavailable",
            "data_error": data_errors.get(raw_symbol),
            "previous_sessions": sessions,
            "average_range_pct_3_sessions": (
                sum(item["range_pct"] for item in sessions[-3:]) / 3.0
                if len(sessions) >= 3
                else None
            ),
            "average_range_pct_5_sessions": (
                sum(item["range_pct"] for item in sessions[-5:]) / 5.0
                if len(sessions) >= 5
                else None
            ),
            "last_3_open_to_close_directions": directions,
            "current_session_open": current_open,
            "gap_vs_prior_close_pct": (
                (current_open / prior["close"] - 1.0) * 100.0
                if current_open is not None and prior is not None
                else None
            ),
            "reference_price": current_price,
            "reference_price_source": price_source if current_price is not None else None,
            "prior_day_levels": levels,
            "distance_from_prior_day_levels_pct": distances,
            "five_session_return_pct": _five_session_return(sessions),
        }
    benchmark_return = underlyings.get("NIFTY", {}).get("five_session_return_pct")
    for row in underlyings.values():
        symbol_return = row["five_session_return_pct"]
        row["relative_strength_vs_nifty_5d_pct_points"] = (
            symbol_return - benchmark_return
            if symbol_return is not None and benchmark_return is not None
            else None
        )
    if "NIFTY" in underlyings and underlyings["NIFTY"]["five_session_return_pct"] is not None:
        underlyings["NIFTY"]["relative_strength_vs_nifty_5d_pct_points"] = 0.0
    if stage == "1030":
        for symbol, candles in intraday_history.items():
            if symbol in underlyings:
                underlyings[symbol]["live_range_1030"] = calculate_live_range(
                    candles, local_time.date()
                )
    return {
        "version": CONTEXT_VERSION,
        "stage": stage,
        "captured_at": local_time.isoformat(timespec="seconds"),
        "underlyings": underlyings,
        "india_vix": _vix_context(vix_history or (), local_time.date()),
    }


def format_summary(snapshot: Dict[str, Any], max_length: int = 3800) -> str:
    def render(value: Any) -> str:
        return "n/a" if value is None else f"{value:.2f}"

    lines = [
        f"Premarket context ({snapshot.get('captured_at', '')}; PAPER, log-only)"
    ]
    for symbol, row in snapshot.get("underlyings", {}).items():
        average_3 = row.get("average_range_pct_3_sessions")
        average_5 = row.get("average_range_pct_5_sessions")
        gap = row.get("gap_vs_prior_close_pct")
        relative = row.get("relative_strength_vs_nifty_5d_pct_points")
        lines.append(
            f"{symbol}: range avg 3/5d "
            f"{render(average_3)}/{render(average_5)}%; "
            f"gap {render(gap)}%; RS vs NIFTY {render(relative)}pp"
        )
    vix = snapshot.get("india_vix", {})
    lines.append(
        "India VIX prior close/change: "
        f"{render(vix.get('prior_close'))}/"
        f"{render(vix.get('change_1d_pct'))}%"
    )
    message = "\n".join(lines)
    return message if len(message) <= max_length else message[: max_length - 3] + "..."


class PremarketContextStore:
    """Keep the day's scheduled premarket snapshots in one JSON file."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self._lock = threading.Lock()
        self._latest_snapshot: Optional[Dict[str, Any]] = None

    def completed_stages(self, session_date: date) -> set[str]:
        destination = self.directory / f"{session_date.isoformat()}.json"
        with self._lock:
            if not destination.exists():
                return set()
            with destination.open("r", encoding="utf-8") as handle:
                daily_record = json.load(handle)
            snapshots = daily_record.get("snapshots", {})
            if not isinstance(snapshots, dict):
                raise ValueError(f"Invalid snapshots in premarket context document: {destination}")
            latest = daily_record.get("latest_snapshot")
            if latest in snapshots and isinstance(snapshots[latest], dict):
                self._latest_snapshot = snapshots[latest]
            return {str(stage) for stage in snapshots}

    def write_snapshot(self, snapshot: Dict[str, Any]) -> Path:
        session_date = datetime.fromisoformat(snapshot["captured_at"]).date()
        destination = self.directory / f"{session_date.isoformat()}.json"
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                with destination.open("r", encoding="utf-8") as handle:
                    daily_record = json.load(handle)
                if not isinstance(daily_record, dict):
                    raise ValueError(f"Invalid premarket context document: {destination}")
            else:
                daily_record = {
                    "date": session_date.isoformat(),
                    "version": CONTEXT_VERSION,
                    "snapshots": {},
                }
            snapshots = daily_record.setdefault("snapshots", {})
            if not isinstance(snapshots, dict):
                raise ValueError(f"Invalid snapshots in premarket context document: {destination}")
            snapshots[snapshot["stage"]] = snapshot
            daily_record["latest_snapshot"] = snapshot["stage"]
            temporary = destination.with_name(
                f".{destination.name}.{os.getpid()}.{threading.get_ident()}.tmp"
            )
            try:
                with temporary.open("w", encoding="utf-8") as handle:
                    json.dump(daily_record, handle, indent=2, default=str)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()
            self._latest_snapshot = snapshot
        return destination

    def context_for(self, ticker: Any) -> Dict[str, Any]:
        symbol = str(ticker or "").upper().split("_", 1)[0]
        snapshot = self._latest_snapshot
        if snapshot is None:
            return {
                "version": CONTEXT_VERSION,
                "status": "not_captured",
                "underlying": symbol,
            }
        row = snapshot.get("underlyings", {}).get(symbol)
        if not isinstance(row, dict):
            return {
                "version": CONTEXT_VERSION,
                "status": "underlying_unavailable",
                "stage": snapshot.get("stage"),
                "captured_at": snapshot.get("captured_at"),
                "underlying": symbol,
                "india_vix": snapshot.get("india_vix"),
            }
        return {
            "version": CONTEXT_VERSION,
            "status": row.get("data_status", "unavailable"),
            "stage": snapshot.get("stage"),
            "captured_at": snapshot.get("captured_at"),
            "underlying": symbol,
            **row,
            "india_vix": snapshot.get("india_vix"),
        }
