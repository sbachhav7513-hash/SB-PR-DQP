"""Export one session of Kite underlying and near-ATM option history."""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import os
import sys
import time
from datetime import date, datetime, time as clock_time, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from kiteconnect import KiteConnect

from .kite_history_export import (
    _resolve_underlyings,
    _safe_filename,
    export_history,
)
from .secrets import load_local_environment


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _select_daily_options(
    master_rows: List[Dict],
    spot_closes: Dict[str, float],
    target_date: date,
    config: Dict,
) -> tuple[List[Dict[str, object]], List[str]]:
    roots = {
        str(symbol).strip().upper()
        for symbol in config.get("options_underlyings", [])
    }
    candidates = []
    for row in master_rows:
        underlying = str(row.get("name", "")).strip().upper()
        if (
            underlying not in roots
            or str(row.get("instrument_type", "")).upper() not in {"CE", "PE"}
            or not row.get("instrument_token")
            or row.get("strike") is None
            or not row.get("expiry")
            or not row.get("lot_size")
        ):
            continue
        expiry = _as_date(row["expiry"])
        if expiry < target_date:
            continue
        candidates.append((underlying, expiry, row))

    expiries_by_root: Dict[str, List[date]] = {}
    for underlying, expiry, _ in candidates:
        expiries_by_root.setdefault(underlying, []).append(expiry)

    lookahead = max(
        int(config.get("option_expiry_days", 14)),
        0,
        calendar.monthrange(target_date.year, target_date.month)[1]
        - target_date.day,
    )
    expiry_limit = target_date + timedelta(days=lookahead)
    expiry_mode = str(config.get("option_expiry_mode", "nearest")).lower().strip()
    if expiry_mode not in {"nearest", "next_week"}:
        raise ValueError("option_expiry_mode must be 'nearest' or 'next_week'")

    selected_expiries: Dict[str, date] = {}
    for underlying, expiries in expiries_by_root.items():
        eligible = sorted({
            expiry for expiry in expiries if expiry <= expiry_limit
        })
        if expiry_mode == "next_week":
            if len(eligible) >= 2:
                selected_expiries[underlying] = eligible[1]
        elif eligible:
            selected_expiries[underlying] = eligible[0]

    configured_steps = config.get("option_strike_step", {})
    max_distance_pct = max(
        float(config.get("option_max_strike_distance_pct", 0.5)),
        0.0,
    )
    selected: List[Dict[str, object]] = []
    for underlying, expiry in selected_expiries.items():
        spot = float(spot_closes.get(underlying, 0))
        if spot <= 0:
            continue
        strikes = [
            float(row["strike"])
            for root, row_expiry, row in candidates
            if root == underlying and row_expiry == expiry
        ]
        step = float(configured_steps.get(underlying, 0))
        if step <= 0:
            ordered = sorted(set(strikes))
            step = min(
                (
                    right - left
                    for left, right in zip(ordered, ordered[1:])
                    if right > left
                ),
                default=1.0,
            )
        atm_strike = round(spot / step) * step

        for root, row_expiry, row in candidates:
            if root != underlying or row_expiry != expiry:
                continue
            strike = float(row["strike"])
            if not (
                abs(strike - atm_strike) < 1e-9
                or abs(strike - spot) / spot * 100.0 <= max_distance_pct
            ):
                continue
            symbol = str(row["tradingsymbol"]).strip().upper()
            option_type = str(row["instrument_type"]).strip().upper()
            selected.append({
                "kind": "option",
                "underlying": underlying,
                "tradingsymbol": symbol,
                "expiry": expiry.isoformat(),
                "strike": strike,
                "instrument_type": option_type,
                "instrument_token": int(row["instrument_token"]),
                "lot_size": int(row["lot_size"]),
                "active_from": target_date.isoformat(),
                "active_to": min(target_date, expiry).isoformat(),
                "filename": f"options__{_safe_filename(symbol)}.csv",
            })

    selected_roots = {str(item["underlying"]) for item in selected}
    missing = sorted(roots - selected_roots)
    return selected, missing


def _previous_session_close(
    kite: KiteConnect,
    instrument: Dict[str, object],
    target_date: date,
) -> float:
    start = datetime.combine(target_date - timedelta(days=7), clock_time(9, 15))
    end = datetime.combine(target_date - timedelta(days=1), clock_time(15, 30))
    candles = kite.historical_data(
        int(instrument["instrument_token"]),
        start,
        end,
        "minute",
    )
    prior = [
        candle for candle in candles
        if _as_date(candle["date"]) < target_date
    ]
    if not prior:
        return 0.0
    return float(max(prior, key=lambda candle: candle["date"])["close"])


def _write_daily_master(
    path: Path,
    rows: List[Dict],
    roots: set[str],
    snapshot_date: date,
) -> int:
    fields = [
        "snapshot_date",
        "underlying",
        "tradingsymbol",
        "expiry",
        "strike",
        "instrument_type",
        "instrument_token",
        "lot_size",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            if (
                str(row.get("name", "")).strip().upper() not in roots
                or str(row.get("instrument_type", "")).upper() not in {"CE", "PE"}
            ):
                continue
            expiry = row.get("expiry")
            writer.writerow({
                "snapshot_date": snapshot_date.isoformat(),
                "underlying": row.get("name"),
                "tradingsymbol": row.get("tradingsymbol"),
                "expiry": _as_date(expiry).isoformat() if expiry else "",
                "strike": row.get("strike"),
                "instrument_type": row.get("instrument_type"),
                "instrument_token": row.get("instrument_token"),
                "lot_size": row.get("lot_size"),
            })
            written += 1
    return written


def _read_daily_master(path: Path, expected_date: date) -> List[Dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {
            "snapshot_date",
            "underlying",
            "tradingsymbol",
            "expiry",
            "strike",
            "instrument_type",
            "instrument_token",
            "lot_size",
        }
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise ValueError(
                f"{path} is missing snapshot columns: " + ", ".join(missing)
            )
        rows = []
        for line_number, row in enumerate(reader, start=2):
            if date.fromisoformat(row["snapshot_date"]) != expected_date:
                raise ValueError(
                    f"{path} line {line_number} has a different snapshot date"
                )
            rows.append({
                "name": row["underlying"].strip().upper(),
                "tradingsymbol": row["tradingsymbol"].strip().upper(),
                "expiry": date.fromisoformat(row["expiry"]),
                "strike": float(row["strike"]),
                "instrument_type": row["instrument_type"].strip().upper(),
                "instrument_token": int(row["instrument_token"]),
                "lot_size": int(row["lot_size"]),
            })
    if not rows:
        raise ValueError(f"{path} contains no option contracts")
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only daily Kite export of underlying and configured near-ATM "
            "option candles for offline strategy research."
        )
    )
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--config", type=Path, default=Path("kite_config.json"))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data_uploads/kite_daily"),
    )
    parser.add_argument(
        "--snapshot-only",
        action="store_true",
        help="Save today's configured-underlying NFO contract master before the session.",
    )
    parser.add_argument("--request-delay", type=float, default=0.35)
    args = parser.parse_args(argv)
    if args.request_delay < 0:
        parser.error("--request-delay cannot be negative")
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        parser.error(f"cannot read config {args.config}: {error}")

    load_local_environment()
    api_key = os.getenv("KITE_API_KEY")
    access_token = os.getenv("KITE_ACCESS_TOKEN")
    if not api_key or not access_token:
        parser.error(
            "KITE_API_KEY and KITE_ACCESS_TOKEN must be set in the environment "
            "or local .env file"
        )

    try:
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        roots = [
            str(symbol).strip().upper()
            for symbol in dict.fromkeys(config.get("options_underlyings", []))
        ]
        output_dir = args.output_root / args.date.isoformat()
        daily_master = output_dir / "nfo_instruments_snapshot.csv"
        if args.snapshot_only:
            if daily_master.exists():
                raise FileExistsError(
                    f"{daily_master} already exists; refusing to replace the dated snapshot"
                )
            master_rows = kite.instruments("NFO")
            written = _write_daily_master(
                daily_master,
                master_rows,
                {str(symbol).upper() for symbol in roots},
                args.date,
            )
            if not written:
                raise ValueError(
                    "Kite returned no configured-underlying option contracts"
                )
            print(
                f"Saved {written} dated option mappings to "
                f"{daily_master.resolve()}; run again after market close "
                "without --snapshot-only to export candles."
            )
            return 0

        master_rows = _read_daily_master(daily_master, args.date)
        master_roots = {
            str(row["name"]).strip().upper()
            for row in master_rows
        }
        eligible_roots = [root for root in roots if root in master_roots]
        unavailable_roots = sorted(set(roots) - set(eligible_roots))
        try:
            spot_instruments = _resolve_underlyings(
                kite,
                eligible_roots,
                config.get("instrument_tokens", {}),
            )
        except ValueError:
            spot_instruments = []
            for root in eligible_roots:
                try:
                    spot_instruments.extend(_resolve_underlyings(
                        kite,
                        [root],
                        config.get("instrument_tokens", {}),
                    ))
                except ValueError:
                    unavailable_roots.append(root)
        eligible_roots = [
            root for root in eligible_roots
            if any(
                str(instrument["underlying"]).upper() == root
                for instrument in spot_instruments
            )
        ]
        if not spot_instruments:
            raise ValueError(
                "could not resolve an underlying token for any configured option root"
            )
        spot_closes = {}
        for instrument in spot_instruments:
            spot_closes[str(instrument["underlying"])] = _previous_session_close(
                kite,
                instrument,
                args.date,
            )
            if args.request_delay:
                time.sleep(args.request_delay)

        selection_config = {
            **config,
            "options_underlyings": eligible_roots,
        }
        options, missing_roots = _select_daily_options(
            master_rows,
            spot_closes,
            args.date,
            selection_config,
        )
        missing_roots = sorted(set(missing_roots) | set(unavailable_roots))
        underlyings = [
            {
                **instrument,
                "filename": f"underlyings__{_safe_filename(str(instrument['underlying']))}.csv",
            }
            for instrument in spot_instruments
        ]
        manifest = export_history(
            kite,
            underlyings + options,
            args.date,
            args.date,
            output_dir,
            chunk_days=1,
            request_delay=args.request_delay,
        )
        manifest["option_universe_method"] = (
            "For each configured underlying, nearest/next_week expiry selected "
            "under kite_provider rules; ATM and all listed strikes within "
            "option_max_strike_distance_pct of prior-session close exported."
        )
        manifest["underlyings_without_selected_contracts"] = missing_roots
        manifest["prior_session_close"] = spot_closes
        manifest["limitations"].append(
            "Option universe is a prior-close near-ATM proxy for contracts the strategy "
            "could select; it is not a tick-by-tick snapshot of runtime selection."
        )
        manifest["limitations"].append(
            "Historical bid/ask and IV are unavailable from this Kite candle export."
        )
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))

    print(
        f"Exported {len(manifest['instruments'])} instruments "
        f"({len(underlyings)} underlyings, {len(options)} options) to "
        f"{output_dir.resolve()}"
    )
    if missing_roots:
        print("No eligible option contracts for: " + ", ".join(missing_roots))
    return 0


if __name__ == "__main__":
    sys.exit(main())
