"""Append today's NSE index and India VIX minute candles to the local archive."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, time as clock_time
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd
from kiteconnect import KiteConnect

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_bot.secrets import load_local_environment

IST = ZoneInfo("Asia/Kolkata")
SESSION_START = clock_time(9, 15)
SESSION_END = clock_time(15, 30)
REQUEST_DELAY_SECONDS = 0.35
INSTRUMENTS = (
    ("NIFTY", "NIFTY_5y.parquet", {"NIFTY 50", "NIFTY"}),
    ("BANKNIFTY", "BANKNIFTY_5y.parquet", {"NIFTY BANK", "BANKNIFTY"}),
    ("INDIA VIX", "INDIA_VIX_5y.parquet", {"INDIA VIX", "INDIAVIX"}),
)
BASE_COLUMNS = ("timestamp", "open", "high", "low", "close")


def resolve_instrument_tokens(rows: Iterable[Mapping[str, object]]) -> Dict[str, int]:
    """Resolve the three NSE index instruments by exact master labels."""
    aliases = {
        symbol: names
        for symbol, _, names in INSTRUMENTS
    }
    resolved: Dict[str, int] = {}
    for row in rows:
        labels = {
            str(row.get("tradingsymbol", "")).strip().upper(),
            str(row.get("name", "")).strip().upper(),
        }
        for symbol, names in aliases.items():
            if symbol not in resolved and labels.intersection(names):
                try:
                    token = int(row.get("instrument_token", 0) or 0)
                except (TypeError, ValueError, OverflowError):
                    continue
                if token > 0:
                    resolved[symbol] = token
    missing = [symbol for symbol, _, _ in INSTRUMENTS if symbol not in resolved]
    if missing:
        raise ValueError(
            "NSE instrument master is missing: " + ", ".join(missing)
        )
    return resolved


def _session_frame(
    candles: Sequence[Mapping[str, object]], session_day: date, symbol: str
) -> pd.DataFrame:
    rows = []
    for candle in candles:
        try:
            timestamp = pd.Timestamp(candle["date"])
            if timestamp.tzinfo is None:
                timestamp = timestamp.tz_localize(IST)
            else:
                timestamp = timestamp.tz_convert(IST)
            if timestamp.date() != session_day:
                continue
            row = {
                "timestamp": timestamp,
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
            }
            if symbol != "INDIA VIX":
                row["volume"] = int(candle.get("volume", 0) or 0)
            rows.append(row)
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise ValueError(
                f"Kite returned an invalid {symbol} minute candle"
            ) from error
    columns = list(BASE_COLUMNS)
    if symbol != "INDIA VIX":
        columns.append("volume")
    return pd.DataFrame(rows, columns=columns)


def append_session_candles(
    destination: Path, candles: pd.DataFrame, session_day: date
) -> int:
    """Merge a session idempotently and atomically replace its parquet archive."""
    destination = Path(destination)
    if not destination.is_file():
        raise FileNotFoundError(f"archive parquet does not exist: {destination}")
    if candles.empty:
        return 0

    existing = pd.read_parquet(destination)
    if "timestamp" not in existing.columns:
        raise ValueError(f"{destination} has no timestamp column")
    if not pd.api.types.is_datetime64_any_dtype(existing["timestamp"]):
        existing["timestamp"] = pd.to_datetime(
            existing["timestamp"], errors="raise"
        )
    if getattr(existing["timestamp"].dt, "tz", None) is None:
        existing["timestamp"] = existing["timestamp"].dt.tz_localize(IST)
    else:
        existing["timestamp"] = existing["timestamp"].dt.tz_convert(IST)

    day_mask = existing["timestamp"].dt.date == session_day
    existing = existing.loc[~day_mask]
    columns = list(existing.columns)
    missing = [column for column in columns if column not in candles.columns]
    if missing:
        raise ValueError(
            "Fetched candles are missing archive columns: " + ", ".join(missing)
        )
    merged = pd.concat(
        [existing, candles.reindex(columns=columns)], ignore_index=True
    )
    merged = (
        merged.sort_values("timestamp")
        .drop_duplicates(subset=["timestamp"], keep="last")
        .reset_index(drop=True)
    )

    temporary = destination.with_name(
        f".{destination.stem}.{os.getpid()}.tmp.parquet"
    )
    try:
        merged.to_parquet(temporary, index=False)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return len(candles)


def archive_session(
    kite: KiteConnect,
    archive_dir: Path,
    session_day: date,
    request_delay: float = REQUEST_DELAY_SECONDS,
) -> Dict[str, int]:
    """Fetch sequentially, then append all available session data."""
    if request_delay < 0:
        raise ValueError("request delay cannot be negative")

    try:
        tokens = resolve_instrument_tokens(kite.instruments("NSE"))
    except Exception as error:
        raise RuntimeError(
            f"NSE instrument lookup failed ({type(error).__name__})"
        ) from None
    start = datetime.combine(session_day, SESSION_START)
    end = datetime.combine(session_day, SESSION_END)
    fetched: Dict[str, pd.DataFrame] = {}
    for symbol, _, _ in INSTRUMENTS:
        try:
            candles = kite.historical_data(
                tokens[symbol], start, end, "minute"
            )
        except Exception as error:
            raise RuntimeError(
                f"Historical fetch failed for {symbol} "
                f"({type(error).__name__})"
            ) from None
        fetched[symbol] = _session_frame(candles, session_day, symbol)
        if request_delay:
            time.sleep(request_delay)

    populated = [symbol for symbol, frame in fetched.items() if not frame.empty]
    if not populated:
        return {symbol: 0 for symbol, _, _ in INSTRUMENTS}
    missing = [symbol for symbol in fetched if fetched[symbol].empty]
    if missing:
        raise RuntimeError(
            "Session data was incomplete; no archive was updated for: "
            + ", ".join(missing)
        )

    archive_dir = Path(archive_dir)
    destinations = {
        symbol: archive_dir / filename
        for symbol, filename, _ in INSTRUMENTS
    }
    absent = [str(path) for path in destinations.values() if not path.is_file()]
    if absent:
        raise FileNotFoundError(
            "Expected existing archive parquet files: " + ", ".join(absent)
        )

    return {
        symbol: append_session_candles(
            destinations[symbol], frame, session_day
        )
        for symbol, frame in fetched.items()
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch today's 1-minute NIFTY, BANKNIFTY, and India VIX candles "
            "into the research archive; this script never places orders."
        )
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=ROOT / "tmp" / "longhist" / "data",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=REQUEST_DELAY_SECONDS,
    )
    args = parser.parse_args(argv)
    if args.request_delay < 0:
        parser.error("--request-delay cannot be negative")

    now = datetime.now(IST)
    if now.weekday() >= 5:
        print("Weekend; no archive update.")
        return 0
    if now.time() < clock_time(16, 0):
        parser.error("run only after 16:00 Asia/Kolkata")

    load_local_environment()
    api_key = os.getenv("KITE_API_KEY")
    access_token = os.getenv("KITE_ACCESS_TOKEN")
    if not api_key or not access_token:
        parser.error(
            "KITE_API_KEY and KITE_ACCESS_TOKEN must be present in the "
            "environment or local .env file."
        )

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    try:
        counts = archive_session(
            kite, args.archive_dir, now.date(), args.request_delay
        )
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))

    if not any(counts.values()):
        print(f"No session candles returned for {now.date()}; archive unchanged.")
        return 0
    for symbol, count in counts.items():
        print(f"{symbol}: appended {count} minute candles for {now.date()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
