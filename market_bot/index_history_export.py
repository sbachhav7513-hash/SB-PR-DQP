from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import date, datetime, time as clock_time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from .kite_provider import KiteHistoricalProvider
from .secrets import load_local_environment


IST = ZoneInfo("Asia/Kolkata")
MAX_CHUNK_DAYS = 55
SESSION_START = clock_time(9, 15)
SESSION_END = clock_time(15, 30)
MINUTES_PER_SESSION = 375
CSV_FIELDS = ["timestamp", "open", "high", "low", "close", "volume"]


def _date_chunks(start: date, end: date) -> Iterable[tuple[date, date]]:
    if start > end:
        raise ValueError("start date must be on or before end date")
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=MAX_CHUNK_DAYS - 1), end)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def _local_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=IST)
    return value.astimezone(IST)


def _is_regular_session_candle(candle: Dict) -> bool:
    timestamp = _local_timestamp(candle["time"])
    return SESSION_START <= timestamp.time().replace(tzinfo=None) < SESSION_END


def _missing_minutes_by_session(candles: List[Dict]) -> Dict[str, List[str]]:
    actual_by_day: Dict[date, set] = {}
    for candle in candles:
        timestamp = _local_timestamp(candle["time"])
        actual_by_day.setdefault(timestamp.date(), set()).add(
            timestamp.replace(second=0, microsecond=0)
        )

    missing = {}
    for session_date, actual in sorted(actual_by_day.items()):
        session_open = datetime.combine(session_date, SESSION_START, IST)
        expected = {
            session_open + timedelta(minutes=offset)
            for offset in range(MINUTES_PER_SESSION)
        }
        absent = sorted(expected - actual)
        if absent:
            missing[session_date.isoformat()] = [
                timestamp.strftime("%H:%M") for timestamp in absent
            ]
    return missing


def download_index_history(
    provider: KiteHistoricalProvider,
    instruments: Dict[str, int],
    start: date,
    end: date,
    output_dir: Path,
    request_delay: float = 0.4,
    overwrite: bool = False,
) -> Dict[str, Dict]:
    if start > end:
        raise ValueError("start date must be on or before end date")
    if request_delay < 0:
        raise ValueError("request delay cannot be negative")
    if not instruments:
        raise ValueError("at least one instrument token is required")
    for symbol, token in instruments.items():
        if not symbol.strip() or int(token) <= 0:
            raise ValueError("instrument symbols and tokens must be valid")

    output_dir = Path(output_dir)
    planned_paths = [
        output_dir / f"{symbol.upper()}.csv" for symbol in instruments
    ] + [output_dir / "manifest.json"]
    existing = [path for path in planned_paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "history exports already exist; pass overwrite=True or choose a "
            "different output directory: " + ", ".join(str(path) for path in existing)
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    reports = {}
    for symbol, token in instruments.items():
        candles_by_time = {}
        request_count = 0
        for chunk_start, chunk_end in _date_chunks(start, end):
            fetched = provider.fetch_history(
                int(token),
                datetime.combine(chunk_start, SESSION_START),
                datetime.combine(chunk_end, SESSION_END),
                interval="minute",
            )
            request_count += 1
            for candle in fetched:
                timestamp = _local_timestamp(candle["time"])
                if (
                    start <= timestamp.date() <= end
                    and _is_regular_session_candle(candle)
                ):
                    candle = {**candle, "time": timestamp}
                    candles_by_time[timestamp] = candle
            if request_delay:
                time.sleep(request_delay)

        candles = [candles_by_time[key] for key in sorted(candles_by_time)]
        path = output_dir / f"{symbol.upper()}.csv"
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for candle in candles:
                writer.writerow(
                    {
                        "timestamp": candle["time"].isoformat(),
                        **{field: candle[field] for field in CSV_FIELDS[1:]},
                    }
                )

        session_dates = sorted({candle["time"].date() for candle in candles})
        missing = _missing_minutes_by_session(candles)
        reports[symbol.upper()] = {
            "file": str(path),
            "bars": len(candles),
            "sessions": len(session_dates),
            "first_date": session_dates[0].isoformat() if session_dates else None,
            "last_date": session_dates[-1].isoformat() if session_dates else None,
            "missing_minutes": missing,
            "historical_requests": request_count,
        }

    manifest = {
        "source": "KiteHistoricalProvider",
        "created_at_ist": datetime.now(IST).isoformat(),
        "interval": "minute",
        "timezone": "Asia/Kolkata",
        "session": {"start": "09:15", "end_exclusive": "15:30"},
        "requested_period": {
            "start_date_inclusive": start.isoformat(),
            "end_date_inclusive": end.isoformat(),
        },
        "instruments": reports,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return reports


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download read-only Kite one-minute index spot history."
    )
    parser.add_argument("--config", type=Path, default=Path("kite_config.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("historical_data"))
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2015, 1, 1))
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=datetime.now(IST).date(),
    )
    parser.add_argument("--request-delay", type=float, default=0.4)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    if args.request_delay < 0:
        parser.error("--request-delay cannot be negative")

    config = json.loads(args.config.read_text(encoding="utf-8"))
    tokens = config.get("instrument_tokens", {})
    instruments = {
        symbol: int(tokens[symbol])
        for symbol in ("NIFTY", "BANKNIFTY")
        if symbol in tokens
    }
    missing_symbols = sorted({"NIFTY", "BANKNIFTY"} - set(instruments))
    if missing_symbols:
        parser.error(
            "kite_config.json is missing spot instrument tokens for: "
            + ", ".join(missing_symbols)
        )

    load_local_environment()
    api_key = os.getenv("KITE_API_KEY")
    access_token = os.getenv("KITE_ACCESS_TOKEN")
    if not api_key or not access_token:
        parser.error("KITE_API_KEY and KITE_ACCESS_TOKEN are required.")

    provider = KiteHistoricalProvider(api_key, access_token)
    reports = download_index_history(
        provider,
        instruments,
        args.start_date,
        args.end_date,
        args.output_dir,
        request_delay=args.request_delay,
        overwrite=args.overwrite,
    )
    for symbol, report in reports.items():
        missing = report["missing_minutes"]
        missing_text = (
            ", ".join(
                f"{day}: {len(minutes)}"
                for day, minutes in missing.items()
            )
            if missing
            else "none"
        )
        print(
            f"{symbol}: first={report['first_date']}, "
            f"last={report['last_date']}, sessions={report['sessions']}, "
            f"bars={report['bars']}, requests={report['historical_requests']}, "
            f"days_with_missing_minutes={missing_text}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
