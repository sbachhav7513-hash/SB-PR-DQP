from __future__ import annotations

import csv
import gzip
import math
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
MARKET_CLOSE = time(15, 30)
RECOVERY_CHECKPOINTS_MINUTES = (5, 15, 30, 60)


def _datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _read_rows(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _contract_rows(
    day_dir: Path, contract_id: str, suffix: str
) -> list[dict[str, Any]]:
    symbol = contract_id.split(":", 1)[-1]
    rows = []
    for path in sorted(day_dir.glob(f"NFO_{symbol}.{suffix}.csv*")):
        for raw in _read_rows(path):
            if raw.get("contract_id") != contract_id:
                continue
            timestamp = _datetime(
                raw.get("candle_start_time") if suffix == "candles" else raw.get("time")
            )
            if timestamp is None:
                continue
            row: dict[str, Any] = {"time": timestamp}
            for key, value in raw.items():
                if key not in {"candle_start_time", "time"}:
                    row[key] = _number(value) if _number(value) is not None else value
            rows.append(row)
    return sorted(rows, key=lambda row: row["time"])


def _underlying_rows(
    paper_root: Path, symbol: str, target_date: date
) -> list[dict[str, Any]]:
    path = (
        paper_root
        / "underlying_candles"
        / target_date.isoformat()
        / f"{symbol}.candles.csv"
    )
    if not path.is_file():
        return []
    rows = []
    for raw in _read_rows(path):
        timestamp = _datetime(raw.get("candle_start_time"))
        if timestamp is None or raw.get("symbol", "").upper() != symbol:
            continue
        rows.append(
            {
                "time": timestamp,
                "high": _number(raw.get("high")),
                "low": _number(raw.get("low")),
                "close": _number(raw.get("close")),
            }
        )
    return sorted(rows, key=lambda row: row["time"])


def _first_full_minute(value: datetime) -> datetime:
    minute = value.replace(second=0, microsecond=0)
    return minute + timedelta(minutes=1) if value > minute else minute


def _covered_minutes(
    candles: list[dict[str, Any]], start: datetime, end: datetime
) -> tuple[int, int]:
    expected_times = []
    current = start
    while current < end:
        expected_times.append(current)
        current += timedelta(minutes=1)
    by_time = {
        row["time"].replace(second=0, microsecond=0): row
        for row in candles
    }
    observed = sum(
        timestamp in by_time
        and str(by_time[timestamp].get("gap", "")).lower() not in {"true", "1"}
        and _number(by_time[timestamp].get("close")) is not None
        for timestamp in expected_times
    )
    return observed, len(expected_times)


def _nearest_bid(
    quotes: list[dict[str, Any]],
    target: datetime,
    not_before: datetime,
    session_close: datetime,
) -> dict[str, Any] | None:
    if target >= session_close:
        return None
    valid = []
    for row in quotes:
        timestamp = row["time"]
        bid = _number(row.get("bid"))
        ask = _number(row.get("ask"))
        quote_age = _number(row.get("quote_age_seconds"))
        if (
            timestamp <= not_before
            or timestamp >= session_close
            or bid is None
            or bid <= 0
            or (ask is not None and ask < bid)
            or (quote_age is not None and quote_age > 60)
        ):
            continue
        valid.append(row)
    if not valid:
        return None
    row = min(valid, key=lambda item: abs((item["time"] - target).total_seconds()))
    return {
        "target_time": target.isoformat(),
        "sample_time": row["time"].isoformat(),
        "bid": _number(row.get("bid")),
        "sample_offset_seconds": round((row["time"] - target).total_seconds(), 3),
        "quote_age_seconds": _number(row.get("quote_age_seconds")),
    }


def _r_value(price: float, entry: float, risk: float, is_long: bool) -> float:
    return (price - entry) / risk if is_long else (entry - price) / risk


def _recovery_type(trade: dict[str, Any]) -> str | None:
    reason = str(trade.get("reason") or trade.get("exit_reason") or "").upper()
    if reason == "STOP_LOSS":
        return "initial_stop"
    if reason == "TRAILING_STOP":
        if str(trade.get("adaptive_exit_mode") or "").lower() == "breakeven":
            return "breakeven"
        trigger = _number(trade.get("exit_trigger_price"))
        entry = _number(trade.get("entry"))
        if trigger is not None and entry is not None and math.isclose(
            trigger, entry, rel_tol=0.0, abs_tol=0.01
        ):
            return "breakeven"
        return "trailing_stop"
    return None


def build_recovery_record(
    trade: dict[str, Any], paper_root: Path, target_date: date
) -> dict[str, Any] | None:
    recovery_type = _recovery_type(trade)
    if recovery_type is None:
        return None

    entry_time = _datetime(trade.get("entry_time") or trade.get("timestamp"))
    exit_time = _datetime(trade.get("closed_at"))
    entry = _number(trade.get("entry"))
    initial_stop = _number(trade.get("initial_stop_loss", trade.get("stop_loss")))
    risk = _number(trade.get("initial_risk_per_unit"))
    if risk is None and entry is not None and initial_stop is not None:
        risk = abs(entry - initial_stop)
    risk = risk if risk is not None and risk > 0 else None
    contract_id = str(trade.get("contract_id") or "")
    missing: list[str] = []
    if entry_time is None or exit_time is None or exit_time < (entry_time or exit_time):
        missing.append("missing or invalid entry/exit time")
    if entry is None or risk is None:
        missing.append("missing entry premium or initial risk per unit")
    if not contract_id.startswith("NFO:"):
        missing.append("missing exact option contract_id")
        candles: list[dict[str, Any]] = []
        quotes: list[dict[str, Any]] = []
    else:
        day_dir = paper_root / "option_candles" / target_date.isoformat()
        candles = _contract_rows(day_dir, contract_id, "candles")
        quotes = _contract_rows(day_dir, contract_id, "quotes")
        if not candles:
            missing.append("missing option candles")
        if not quotes:
            missing.append("missing option quotes")

    if exit_time is None:
        end_time = datetime.combine(target_date, MARKET_CLOSE, IST)
        recovery_start = end_time
        duration_seconds = None
    else:
        session_close = datetime.combine(target_date, MARKET_CLOSE, IST)
        recovery_start = _first_full_minute(exit_time)
        end_time = min(exit_time + timedelta(minutes=60), session_close)
        duration_seconds = (
            max((exit_time - entry_time).total_seconds(), 0.0)
            if entry_time is not None
            else None
        )
    session_close = datetime.combine(target_date, MARKET_CLOSE, IST)
    end_to_close = session_close
    observed_60m, expected_60m = _covered_minutes(
        candles, recovery_start, end_time
    )
    observed_close, expected_close = _covered_minutes(
        candles, recovery_start, end_to_close
    )
    if observed_60m != expected_60m:
        missing.append(f"option capture in 60m window {observed_60m}/{expected_60m} minutes")
    if observed_close != expected_close:
        missing.append(f"option capture through close {observed_close}/{expected_close} minutes")

    checkpoints: dict[str, Any] = {}
    if exit_time is not None:
        for minutes in RECOVERY_CHECKPOINTS_MINUTES:
            key = f"bid_after_{minutes}m"
            sample = _nearest_bid(
                quotes,
                exit_time + timedelta(minutes=minutes),
                exit_time,
                session_close,
            )
            checkpoints[key] = sample
            if sample is None and exit_time + timedelta(minutes=minutes) < session_close:
                missing.append(f"no valid bid near {minutes}m checkpoint")

    is_long = str(trade.get("action") or "BUY").upper() != "SELL"
    path_rows_60m = [
        row
        for row in candles
        if exit_time is not None
        and recovery_start <= row["time"] < end_time
        and _number(row.get("high")) is not None
        and _number(row.get("low")) is not None
    ]
    path_rows_close = [
        row
        for row in candles
        if exit_time is not None
        and recovery_start <= row["time"] < end_to_close
        and _number(row.get("high")) is not None
        and _number(row.get("low")) is not None
    ]

    def r_extremes(rows: list[dict[str, Any]]) -> tuple[float | None, float | None]:
        if entry is None or risk is None or not rows:
            return None, None
        highs = [_r_value(float(row["high"]), entry, risk, is_long) for row in rows]
        lows = [_r_value(float(row["low"]), entry, risk, is_long) for row in rows]
        favorable = [max(high, low) for high, low in zip(highs, lows)]
        adverse = [min(high, low) for high, low in zip(highs, lows)]
        return max(favorable), min(adverse)

    max_60m, min_60m = r_extremes(path_rows_60m)
    max_close, min_close = r_extremes(path_rows_close)
    reclaim_time = None
    one_r_time = None
    if entry is not None and risk is not None:
        for row in path_rows_close:
            favorable = (
                float(row["high"]) if is_long else float(row["low"])
            )
            current_r = _r_value(favorable, entry, risk, is_long)
            if reclaim_time is None and current_r >= 0:
                reclaim_time = row["time"].isoformat()
            if one_r_time is None and current_r >= 1.0:
                one_r_time = row["time"].isoformat()

    ticker = str(trade.get("ticker") or "")
    underlying_symbol, _, option_leg = ticker.rpartition("_")
    underlying_rows = _underlying_rows(paper_root, underlying_symbol.upper(), target_date)
    underlying_entry = _number(trade.get("underlying_price_at_entry"))
    if underlying_entry is None and entry_time is not None:
        matching = [
            row for row in underlying_rows
            if row["time"] + timedelta(minutes=1) <= entry_time
        ]
        if matching:
            underlying_entry = _number(matching[-1].get("close"))
    underlying_reversal_time = None
    underlying_60m_reversal_time = None
    underlying_observed_60m = underlying_expected_60m = 0
    underlying_observed_close = underlying_expected_close = 0
    underlying_long = (option_leg.upper() == "CE") == is_long
    if underlying_entry is None or not underlying_rows:
        missing.append("missing underlying entry reference or candles")
    else:
        underlying_observed_60m, underlying_expected_60m = _covered_minutes(
            underlying_rows, recovery_start, end_time
        )
        underlying_observed_close, underlying_expected_close = _covered_minutes(
            underlying_rows, recovery_start, end_to_close
        )
        if underlying_observed_60m != underlying_expected_60m:
            missing.append(
                "underlying capture in 60m window "
                f"{underlying_observed_60m}/{underlying_expected_60m} minutes"
            )
        if underlying_observed_close != underlying_expected_close:
            missing.append(
                "underlying capture through close "
                f"{underlying_observed_close}/{underlying_expected_close} minutes"
            )
    if underlying_entry is not None and underlying_rows and exit_time is not None:
        for row in underlying_rows:
            if not recovery_start <= row["time"] < end_to_close:
                continue
            low = _number(row.get("low"))
            high = _number(row.get("high"))
            adverse = (
                low is not None and low < underlying_entry
                if underlying_long
                else high is not None and high > underlying_entry
            )
            if adverse:
                underlying_reversal_time = row["time"].isoformat()
                if row["time"] < end_time:
                    underlying_60m_reversal_time = row["time"].isoformat()
                break

    return {
        "trade_id": trade.get("trade_id"),
        "ticker": trade.get("ticker"),
        "contract_id": contract_id,
        "entry_time": entry_time.isoformat() if entry_time else None,
        "exit_time": exit_time.isoformat() if exit_time else None,
        "exit_type": recovery_type,
        "entry_to_exit_seconds": duration_seconds,
        "stop_within_5m": (
            duration_seconds is not None and duration_seconds <= 300
        ),
        **checkpoints,
        "max_r_within_60m": max_60m,
        "min_r_within_60m": min_60m,
        "max_r_to_close": max_close,
        "min_r_to_close": min_close,
        "reclaimed_entry": reclaim_time is not None,
        "reclaimed_entry_time": reclaim_time,
        "reached_plus_1r": one_r_time is not None,
        "reached_plus_1r_time": one_r_time,
        "underlying_reversed_within_60m": (
            None
            if underlying_entry is None or not underlying_rows
            else underlying_60m_reversal_time is not None
        ),
        "underlying_reversed_to_close": (
            None
            if underlying_entry is None or not underlying_rows
            else underlying_reversal_time is not None
        ),
        "underlying_reversal_time": underlying_reversal_time,
        "option_minutes_observed_60m": observed_60m,
        "option_minutes_expected_60m": expected_60m,
        "option_minutes_observed_to_close": observed_close,
        "option_minutes_expected_to_close": expected_close,
        "underlying_minutes_observed_60m": underlying_observed_60m,
        "underlying_minutes_expected_60m": underlying_expected_60m,
        "underlying_minutes_observed_to_close": underlying_observed_close,
        "underlying_minutes_expected_to_close": underlying_expected_close,
        "right_censored_at_close": (
            exit_time is not None
            and exit_time + timedelta(minutes=60) > session_close
        ),
        "status": "incomplete" if missing else "complete",
        "missing_reasons": missing,
    }


RECOVERY_COLUMNS = (
    "trade_id",
    "ticker",
    "contract_id",
    "entry_time",
    "exit_time",
    "exit_type",
    "entry_to_exit_seconds",
    "stop_within_5m",
    "bid_after_5m",
    "bid_after_15m",
    "bid_after_30m",
    "bid_after_60m",
    "max_r_within_60m",
    "min_r_within_60m",
    "max_r_to_close",
    "min_r_to_close",
    "reclaimed_entry",
    "reclaimed_entry_time",
    "reached_plus_1r",
    "reached_plus_1r_time",
    "underlying_reversed_within_60m",
    "underlying_reversed_to_close",
    "underlying_reversal_time",
    "option_minutes_observed_60m",
    "option_minutes_expected_60m",
    "option_minutes_observed_to_close",
    "option_minutes_expected_to_close",
    "underlying_minutes_observed_60m",
    "underlying_minutes_expected_60m",
    "underlying_minutes_observed_to_close",
    "underlying_minutes_expected_to_close",
    "right_censored_at_close",
    "status",
    "missing_reasons",
)
