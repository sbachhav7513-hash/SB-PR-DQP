"""Export historical Kite candles for offline, read-only strategy research."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import date, datetime, time as clock_time, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from kiteconnect import KiteConnect

from .secrets import load_local_environment

IST = ZoneInfo("Asia/Kolkata")
MAX_CHUNK_DAYS = 55
OPTION_FIELDS = {
    "underlying",
    "tradingsymbol",
    "expiry",
    "strike",
    "instrument_type",
    "instrument_token",
    "lot_size",
}
CSV_FIELDS = ["timestamp", "open", "high", "low", "close", "volume", "oi"]


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"date must use YYYY-MM-DD format: {value!r}"
        ) from error


def _date_chunks(start: date, end: date, chunk_days: int) -> Iterable[tuple[date, date]]:
    if start > end:
        raise ValueError("start date must be on or before end date")
    if not 1 <= chunk_days <= MAX_CHUNK_DAYS:
        raise ValueError(f"chunk-days must be between 1 and {MAX_CHUNK_DAYS}")
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    if not safe:
        raise ValueError("instrument symbol cannot produce a safe filename")
    return safe


def _normalise_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError(f"unsupported candle timestamp: {value!r}")
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=IST)
    else:
        timestamp = timestamp.astimezone(IST)
    return timestamp.isoformat()


def _normalise_candle(candle: Dict) -> Dict[str, object]:
    try:
        result: Dict[str, object] = {
            "timestamp": _normalise_timestamp(candle["date"]),
        }
        for field in ("open", "high", "low", "close", "volume"):
            result[field] = candle[field]
        result["oi"] = candle.get("oi")
        if result["oi"] is None:
            result["oi"] = ""
        return result
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Kite returned an invalid candle: {candle!r}") from error


def _read_option_manifest(
    path: Path,
    start: date,
    end: date,
) -> List[Dict[str, object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fields = set(reader.fieldnames or [])
        missing = sorted(OPTION_FIELDS - fields)
        if missing:
            raise ValueError(
                f"{path} is missing required option manifest columns: "
                + ", ".join(missing)
            )

        contracts = []
        seen_tokens = set()
        for line_number, row in enumerate(reader, start=2):
            try:
                underlying = row["underlying"].strip().upper()
                symbol = row["tradingsymbol"].strip().upper()
                option_type = row["instrument_type"].strip().upper()
                expiry = date.fromisoformat(row["expiry"].strip())
                token = int(row["instrument_token"])
                lot_size = int(row["lot_size"])
                strike = float(row["strike"])
                active_from = date.fromisoformat(
                    (
                        row.get("active_from")
                        or min(start, expiry).isoformat()
                    ).strip()
                )
                active_to = date.fromisoformat(
                    (row.get("active_to") or expiry.isoformat()).strip()
                )
            except (AttributeError, TypeError, ValueError) as error:
                raise ValueError(
                    f"{path} has invalid option contract values on line {line_number}"
                ) from error

            if not underlying or not symbol:
                raise ValueError(
                    f"{path} requires underlying and tradingsymbol on line {line_number}"
                )
            if option_type not in {"CE", "PE"}:
                raise ValueError(
                    f"{path} instrument_type must be CE or PE on line {line_number}"
                )
            if token <= 0 or lot_size <= 0 or strike <= 0:
                raise ValueError(
                    f"{path} has non-positive token, lot size, or strike on line {line_number}"
                )
            if active_from > active_to or active_from > expiry:
                raise ValueError(
                    f"{path} has an invalid active date range on line {line_number}"
                )
            if token in seen_tokens:
                raise ValueError(
                    f"{path} repeats instrument token {token}; use one row per contract"
                )
            seen_tokens.add(token)

            effective_start = max(start, active_from)
            effective_end = min(end, active_to, expiry)
            if effective_start > effective_end:
                continue

            contracts.append({
                "kind": "option",
                "underlying": underlying,
                "tradingsymbol": symbol,
                "expiry": expiry.isoformat(),
                "strike": strike,
                "instrument_type": option_type,
                "instrument_token": token,
                "lot_size": lot_size,
                "active_from": effective_start.isoformat(),
                "active_to": effective_end.isoformat(),
                "filename": f"options__{_safe_filename(symbol)}.csv",
            })
    return contracts


def _resolve_underlyings(
    kite: KiteConnect,
    symbols: List[str],
    configured_tokens: Dict[str, object],
) -> List[Dict[str, object]]:
    master_rows = kite.instruments("NSE")
    by_symbol = {
        str(row.get("tradingsymbol", "")).strip().upper(): row
        for row in master_rows
        if row.get("tradingsymbol") and row.get("instrument_token")
    }
    by_name = {
        str(row.get("name", "")).strip().upper(): row
        for row in master_rows
        if row.get("name") and row.get("instrument_token")
    }

    resolved = []
    seen = set()
    for requested in symbols:
        symbol = requested.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        row = by_symbol.get(symbol) or by_name.get(symbol)
        token = (
            int(row["instrument_token"])
            if row
            else int(configured_tokens.get(symbol, 0))
        )
        if token <= 0:
            raise ValueError(
                f"could not resolve underlying {symbol!r}; add its current "
                "instrument token to kite_config.json or use a supported NSE symbol"
            )
        resolved.append({
            "kind": "underlying",
            "underlying": symbol,
            "tradingsymbol": str(row.get("tradingsymbol", symbol)) if row else symbol,
            "instrument_token": token,
            "filename": f"underlyings__{_safe_filename(symbol)}.csv",
        })
    if not resolved:
        raise ValueError("provide at least one underlying symbol")
    return resolved


def _fetch_contract_history(
    kite: KiteConnect,
    instrument: Dict[str, object],
    start: date,
    end: date,
    chunk_days: int,
    request_delay: float,
) -> tuple[List[Dict[str, object]], int]:
    candles_by_time: Dict[str, Dict[str, object]] = {}
    request_count = 0
    interval_start = max(start, date.fromisoformat(
        str(instrument.get("active_from", start.isoformat()))
    ))
    interval_end = min(end, date.fromisoformat(
        str(instrument.get("active_to", end.isoformat()))
    ))
    for chunk_start, chunk_end in _date_chunks(
        interval_start, interval_end, chunk_days
    ):
        from_datetime = datetime.combine(chunk_start, clock_time(9, 15))
        to_datetime = datetime.combine(chunk_end, clock_time(15, 30))
        rows = kite.historical_data(
            int(instrument["instrument_token"]),
            from_datetime,
            to_datetime,
            "minute",
            oi=instrument["kind"] == "option",
        )
        request_count += 1
        for candle in rows:
            normalised = _normalise_candle(candle)
            candles_by_time[str(normalised["timestamp"])] = normalised
        if request_delay > 0:
            time.sleep(request_delay)

    candles = [candles_by_time[key] for key in sorted(candles_by_time)]
    return candles, request_count


def export_history(
    kite: KiteConnect,
    instruments: List[Dict[str, object]],
    start: date,
    end: date,
    output_dir: Path,
    chunk_days: int = 50,
    request_delay: float = 0.35,
    overwrite: bool = False,
) -> Dict[str, object]:
    """Fetch all requested candles before writing the export and its manifest."""
    if start > end:
        raise ValueError("start date must be on or before end date")
    if not 1 <= chunk_days <= MAX_CHUNK_DAYS:
        raise ValueError(f"chunk-days must be between 1 and {MAX_CHUNK_DAYS}")
    if request_delay < 0:
        raise ValueError("request delay cannot be negative")
    if not instruments:
        raise ValueError("no instruments were selected for export")

    output_dir = Path(output_dir)
    planned_paths = [
        output_dir / str(instrument["filename"])
        for instrument in instruments
    ]
    planned_paths.append(output_dir / "manifest.json")
    existing = [path for path in planned_paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "export files already exist; choose another output directory or use "
            "--overwrite: " + ", ".join(str(path) for path in existing)
        )

    fetched = []
    for instrument in instruments:
        lower = max(
            start,
            date.fromisoformat(str(instrument.get("active_from", start.isoformat()))),
        )
        upper = min(
            end,
            date.fromisoformat(str(instrument.get("active_to", end.isoformat()))),
        )
        if lower > upper:
            continue
        candles, request_count = _fetch_contract_history(
            kite,
            instrument,
            lower,
            upper,
            chunk_days,
            request_delay,
        )
        fetched.append((instrument, candles, request_count))

    output_dir.mkdir(parents=True, exist_ok=True)
    exported_instruments = []
    for instrument, candles, request_count in fetched:
        path = output_dir / str(instrument["filename"])
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(candles)

        session_dates = sorted({
            str(row["timestamp"])[:10]
            for row in candles
        })
        exported_instruments.append({
            **instrument,
            "bars": len(candles),
            "sessions_with_bars": len(session_dates),
            "first_timestamp": candles[0]["timestamp"] if candles else None,
            "last_timestamp": candles[-1]["timestamp"] if candles else None,
            "oi_bars": sum(row["oi"] != "" for row in candles),
            "historical_requests": request_count,
            "file": path.name,
        })

    manifest = {
        "source": "Kite Connect historical_data API",
        "created_at_ist": datetime.now(IST).isoformat(),
        "requested_interval": "minute",
        "requested_period": {
            "start_date_inclusive": start.isoformat(),
            "end_date_inclusive": end.isoformat(),
        },
        "timezone": "Asia/Kolkata",
        "instruments": exported_instruments,
        "limitations": [
            "Kite historical candles do not include historical bid/ask or implied volatility.",
            "Option contracts are exported only when their exact historical instrument token is supplied in the option manifest.",
            "An empty candle file means the API returned no rows for that contract and period; it does not imply that the contract was tradable.",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _load_config(path: Path) -> Dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read configuration {path}: {error}") from error


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export Kite minute candles for offline research. This command is "
            "read-only and never places orders."
        )
    )
    parser.add_argument("--start-date", required=True, type=_parse_date)
    parser.add_argument("--end-date", required=True, type=_parse_date)
    parser.add_argument("--config", type=Path, default=Path("kite_config.json"))
    parser.add_argument(
        "--underlyings",
        nargs="+",
        help="Underlying NSE/index symbols; defaults to configured option roots and benchmarks.",
    )
    parser.add_argument(
        "--option-manifest",
        type=Path,
        help="CSV containing exact historical option symbols and instrument tokens.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data_uploads/kite_history"),
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=50,
        help=f"Calendar days per Kite request (1-{MAX_CHUNK_DAYS}, default 50).",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=0.35,
        help="Seconds to wait after each history request (default 0.35).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace matching output CSV files and manifest.",
    )
    args = parser.parse_args(argv)

    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    if not 1 <= args.chunk_days <= MAX_CHUNK_DAYS:
        parser.error(f"--chunk-days must be between 1 and {MAX_CHUNK_DAYS}")
    if args.request_delay < 0:
        parser.error("--request-delay cannot be negative")

    config = _load_config(args.config)
    load_local_environment()
    api_key = os.getenv("KITE_API_KEY")
    access_token = os.getenv("KITE_ACCESS_TOKEN")
    if not api_key or not access_token:
        parser.error(
            "KITE_API_KEY and KITE_ACCESS_TOKEN must be set in the environment "
            "or local .env file. Do not put credentials in the export manifest."
        )

    configured_tokens = config.get("instrument_tokens", {})
    if not isinstance(configured_tokens, dict):
        parser.error("kite_config.json instrument_tokens must be an object")
    symbols = args.underlyings or list(dict.fromkeys(
        list(config.get("options_underlyings", []))
        + list(config.get("benchmark_symbols", []))
        + [config.get("benchmark_symbol", "NIFTY")]
    ))

    try:
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        instruments = _resolve_underlyings(kite, symbols, configured_tokens)
        if args.option_manifest:
            instruments.extend(_read_option_manifest(
                args.option_manifest,
                args.start_date,
                args.end_date,
            ))
        manifest = export_history(
            kite,
            instruments,
            args.start_date,
            args.end_date,
            args.output_dir,
            chunk_days=args.chunk_days,
            request_delay=args.request_delay,
            overwrite=args.overwrite,
        )
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))

    print(
        f"Exported {len(manifest['instruments'])} instruments to "
        f"{args.output_dir.resolve()}"
    )
    for instrument in manifest["instruments"]:
        print(
            f"{instrument['tradingsymbol']}: {instrument['bars']} bars, "
            f"{instrument['sessions_with_bars']} sessions, "
            f"OI bars {instrument['oi_bars']}"
        )
    if args.option_manifest is None:
        print(
            "No option contracts were requested. Supply --option-manifest with "
            "exact historical contract tokens for options replay."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
