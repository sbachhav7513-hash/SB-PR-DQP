#!/usr/bin/env python3
"""Fixed 15-minute ORB baseline and declared 30-minute sensitivity."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

try:
    import pyarrow.parquet as pq
except ImportError as exc:  # pragma: no cover - environment-specific prerequisite
    raise SystemExit("pyarrow is required to read archived PAPER decisions") from exc


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DATA = ROOT / "data_uploads" / "kite_daily"
PAPER = ROOT / "paper_trading_data"
TRADES_FILE = ROOT / "trades.jsonl"
LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))
DATES = [
    "2026-10-14",
    "2026-10-15",
    "2026-10-16",
    "2026-10-19",
    "2026-10-21",
    "2026-10-22",
    "2026-10-23",
    "2026-10-26",
    "2026-10-27",
    "2026-10-28",
    "2026-10-29",
    "2026-10-30",
    "2026-11-02",
    "2026-11-03",
    "2026-11-04",
    "2026-11-05",
    "2026-11-06",
    "2026-11-09",
]
UNDERLYINGS = [
    "NIFTY",
    "BANKNIFTY",
    "RELIANCE",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "INFY",
    "TCS",
    "LT",
]
INDEXES = {"NIFTY", "BANKNIFTY"}
EXIT_SLIPPAGE = 0.01
ENTRY_SLIPPAGE = 0.01
INITIAL_STOP_PCT = 0.10
LOCK_TRIGGER_R = 0.5
LOCK_R = 0.15
RUNNER_TRIGGER_R = 2.0
RUNNER_GAP_R = 1.5
ENTRY_CUTOFF = time(14, 45)
EXIT_CUTOFF = time(15, 14)
EXPIRY_LOOKAHEAD_DAYS = 35

CHARGES = {
    "brokerage_mode": "flat",
    "brokerage_flat_inr": 20.0,
    "brokerage_percentage_rate": 0.0003,
    "stt_sell_rate": 0.0015,
    "exchange_rate": 0.0003553,
    "sebi_rate": 0.000001,
    "stamp_buy_rate": 0.00003,
    "gst_rate": 0.18,
}

CSV_FIELDS = [
    "date",
    "underlying",
    "tier",
    "direction",
    "signal_time",
    "entry_time",
    "entry",
    "exit_time",
    "exit",
    "exit_reason",
    "net_r",
    "net_rupees",
    "option_contract",
    "expiry",
    "strike",
    "lot_size",
    "entry_option_candle",
    "option_candles_observed",
    "option_candles_expected",
    "option_candle_coverage_pct",
    "day_direction",
    "partial_status",
    "raw_entry_open",
    "raw_exit_price",
    "fees_rupees",
    "initial_risk_rupees",
    "range_minutes",
]


def parse_dt(value: Any) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


def iso_minute(value: datetime | None) -> str:
    return value.isoformat(timespec="minutes") if value else ""


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def fnum(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def fee_for_round_trip(
    entry: float, exit_price: float, quantity: int
) -> float:
    entry_turnover = entry * quantity
    exit_turnover = exit_price * quantity
    total_turnover = entry_turnover + exit_turnover
    brokerage = 2 * CHARGES["brokerage_flat_inr"]
    exchange = total_turnover * CHARGES["exchange_rate"]
    sebi = total_turnover * CHARGES["sebi_rate"]
    stt = exit_turnover * CHARGES["stt_sell_rate"]
    stamp = entry_turnover * CHARGES["stamp_buy_rate"]
    gst = (brokerage + exchange + sebi) * CHARGES["gst_rate"]
    components = [
        round(brokerage, 2),
        round(stt, 2),
        round(exchange, 2),
        round(sebi, 2),
        round(stamp, 2),
        round(gst, 2),
    ]
    return round(sum(components), 2)


def load_market_data() -> tuple[dict, dict, dict]:
    underlyings: dict[tuple[str, str], list[dict]] = {}
    instruments: dict[tuple[str, str], list[dict]] = {}
    options: dict[tuple[str, str, str, float, str], dict] = {}

    for day in DATES:
        directory = DATA / day
        instrument_rows = read_csv(directory / "nfo_instruments_snapshot.csv")
        for row in instrument_rows:
            underlying = row["underlying"].upper()
            if underlying not in UNDERLYINGS:
                continue
            row["strike_value"] = float(row["strike"])
            row["expiry_value"] = date.fromisoformat(row["expiry"])
            instruments.setdefault((day, underlying), []).append(row)

        for underlying in UNDERLYINGS:
            file_path = directory / f"underlyings__{underlying}.csv"
            if not file_path.exists():
                underlyings[(day, underlying)] = []
                continue
            candles = []
            for row in read_csv(file_path):
                dt = parse_dt(row["timestamp"])
                candles.append(
                    {
                        "time": dt,
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                    }
                )
            underlyings[(day, underlying)] = sorted(
                candles, key=lambda candle: candle["time"]
            )

        metadata_by_symbol = {
            row["tradingsymbol"]: row for row in instrument_rows
        }
        for file_path in directory.glob("options__*.csv"):
            tradingsymbol = file_path.stem.removeprefix("options__")
            metadata = metadata_by_symbol.get(tradingsymbol)
            if not metadata:
                continue
            underlying = metadata["underlying"].upper()
            if underlying not in UNDERLYINGS:
                continue
            option_type = metadata["instrument_type"].upper()
            expiry = metadata["expiry"]
            strike = float(metadata["strike"])
            bars = {}
            for row in read_csv(file_path):
                dt = parse_dt(row["timestamp"])
                bars[dt] = {
                    "time": dt,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
            options[(day, underlying, expiry, strike, option_type)] = {
                "bars": bars,
                "filename": file_path.name,
                "tradingsymbol": metadata["tradingsymbol"],
                "lot_size": int(metadata["lot_size"]),
                "expiry": expiry,
                "strike": strike,
                "option_type": option_type,
                "underlying": underlying,
            }
    return underlyings, instruments, options


def choose_contract(
    day: str,
    underlying: str,
    option_type: str,
    spot: float,
    instruments: dict,
) -> dict | None:
    day_date = date.fromisoformat(day)
    valid = [
        row
        for row in instruments.get((day, underlying), [])
        if day_date <= row["expiry_value"]
        <= day_date + timedelta(days=EXPIRY_LOOKAHEAD_DAYS)
        and row["instrument_type"].upper() == option_type
    ]
    if not valid:
        return None
    nearest_expiry = min(row["expiry_value"] for row in valid)
    same_expiry = [row for row in valid if row["expiry_value"] == nearest_expiry]
    chosen = min(
        same_expiry,
        key=lambda row: (abs(row["strike_value"] - spot), row["strike_value"]),
    )
    return {
        "underlying": underlying,
        "option_type": option_type,
        "expiry": chosen["expiry"],
        "strike": float(chosen["strike"]),
        "tradingsymbol": chosen["tradingsymbol"],
        "filename": f"options__{chosen['tradingsymbol']}.csv",
        "lot_size": int(chosen["lot_size"]),
    }


def get_day_direction(candles: list[dict]) -> str:
    if not candles:
        return "unknown"
    first = next(
        (bar for bar in candles if bar["time"].time() == time(9, 15)), None
    )
    last = max(candles, key=lambda bar: bar["time"], default=None)
    if first is None or last is None:
        return "unknown"
    if last["close"] > first["open"]:
        return "up"
    if last["close"] < first["open"]:
        return "down"
    return "flat"


def make_signals(
    range_minutes: int,
    underlyings: dict,
    instruments: dict,
    options: dict,
) -> list[dict]:
    signals = []
    for day in DATES:
        for underlying in UNDERLYINGS:
            candles = underlyings.get((day, underlying), [])
            range_start = datetime.combine(
                date.fromisoformat(day), time(9, 15), tzinfo=LOCAL_TZ
            )
            range_end = range_start + timedelta(minutes=range_minutes)
            last_signal_start = datetime.combine(
                date.fromisoformat(day), ENTRY_CUTOFF, tzinfo=LOCAL_TZ
            )
            range_bars = [
                bar
                for bar in candles
                if range_start <= bar["time"] < range_end
            ]
            if len(range_bars) != range_minutes:
                continue
            range_high = max(bar["high"] for bar in range_bars)
            range_low = min(bar["low"] for bar in range_bars)
            later = [
                bar
                for bar in candles
                if range_end <= bar["time"] <= last_signal_start
            ]
            chosen = None
            direction = None
            for bar in later:
                if bar["close"] > range_high:
                    chosen, direction = bar, "CE"
                    break
                if bar["close"] < range_low:
                    chosen, direction = bar, "PE"
                    break
            if chosen is None:
                continue
            position = candles.index(chosen)
            if position + 1 >= len(candles):
                continue
            next_bar = candles[position + 1]
            contract = choose_contract(
                day, underlying, direction, chosen["close"], instruments
            )
            tier = "index" if underlying in INDEXES else "stock"
            day_direction = get_day_direction(candles)
            signal = {
                "date": day,
                "underlying": underlying,
                "tier": tier,
                "direction": direction,
                "signal_time": chosen["time"],
                "entry_time": next_bar["time"],
                "range_minutes": range_minutes,
                "range_high": range_high,
                "range_low": range_low,
                "spot_at_signal": chosen["close"],
                "day_direction": day_direction,
                "contract": contract,
            }
            signals.append(
                simulate_signal(signal, contract, options)
            )
    return sorted(
        signals,
        key=lambda row: (
            row["date"],
            row["underlying"],
            row["signal_time"] or datetime.min.replace(tzinfo=LOCAL_TZ),
        ),
    )


def blank_trade(signal: dict, reason: str) -> dict:
    contract = signal.get("contract") or {}
    return {
        "date": signal["date"],
        "underlying": signal["underlying"],
        "tier": signal["tier"],
        "direction": signal["direction"],
        "signal_time": signal["signal_time"],
        "entry_time": signal["entry_time"],
        "entry": None,
        "exit_time": None,
        "exit": None,
        "exit_reason": reason,
        "net_r": None,
        "net_rupees": None,
        "option_contract": contract.get("tradingsymbol", ""),
        "expiry": contract.get("expiry", ""),
        "strike": contract.get("strike", ""),
        "lot_size": contract.get("lot_size", ""),
        "entry_option_candle": False,
        "option_candles_observed": 0,
        "option_candles_expected": 0,
        "option_candle_coverage_pct": 0.0,
        "day_direction": signal["day_direction"],
        "partial_status": "single-lot-ineligible",
        "raw_entry_open": None,
        "raw_exit_price": None,
        "fees_rupees": None,
        "initial_risk_rupees": None,
        "range_minutes": signal["range_minutes"],
        "_exit_bar_time": None,
    }


def simulate_signal(
    signal: dict,
    contract: dict | None,
    options: dict,
) -> dict:
    if contract is None:
        return blank_trade(signal, "no option data: no valid expiry/strike")
    key = (
        signal["date"],
        signal["underlying"],
        contract["expiry"],
        float(contract["strike"]),
        signal["direction"],
    )
    contract_data = options.get(key)
    if contract_data is None:
        return blank_trade(signal, "no option data: contract candle file absent")
    entry_bar = contract_data["bars"].get(signal["entry_time"])
    if entry_bar is None:
        return blank_trade(signal, "no option data: no entry-time candle")

    qty = contract["lot_size"]
    raw_entry = entry_bar["open"]
    entry = raw_entry * (1.0 + ENTRY_SLIPPAGE)
    risk_per_unit = entry * INITIAL_STOP_PCT
    initial_stop = entry - risk_per_unit
    active_stop = initial_stop
    stop_reason = "initial_stop"
    peak = entry
    runner_active = False
    entry_date = signal["entry_time"].date()
    last_allowed_start = datetime.combine(entry_date, EXIT_CUTOFF, tzinfo=LOCAL_TZ)
    bars = sorted(
        (
            bar
            for dt, bar in contract_data["bars"].items()
            if signal["entry_time"] <= dt <= last_allowed_start
        ),
        key=lambda bar: bar["time"],
    )
    exit_bar = None
    raw_exit = None
    exit_reason = ""
    for bar in bars:
        if runner_active:
            if bar["close"] <= active_stop:
                raw_exit = bar["close"]
                exit_bar = bar
                exit_reason = "runner_trail_close_confirm"
                break
        else:
            stop_hit = bar["open"] <= active_stop or bar["low"] <= active_stop
            if stop_hit:
                raw_exit = (
                    bar["open"] if bar["open"] <= active_stop else active_stop
                )
                exit_bar = bar
                exit_reason = (
                    "initial_stop"
                    if stop_reason == "initial_stop"
                    else "profit_lock"
                )
                break

        peak = max(peak, bar["high"])
        favorable_r = (peak - entry) / risk_per_unit
        if favorable_r >= LOCK_TRIGGER_R:
            active_stop = max(active_stop, entry + LOCK_R * risk_per_unit)
            stop_reason = "profit_lock"
        if favorable_r >= RUNNER_TRIGGER_R:
            runner_active = True
            active_stop = max(
                active_stop, peak - RUNNER_GAP_R * risk_per_unit
            )
            stop_reason = "runner"

    if exit_bar is None:
        if not bars:
            return blank_trade(signal, "no option data: no post-entry candles")
        exit_bar = bars[-1]
        raw_exit = exit_bar["close"]
        exit_reason = "forced_15:15"

    exit_fill = raw_exit * (1.0 - EXIT_SLIPPAGE)
    fees = fee_for_round_trip(entry, exit_fill, qty)
    gross = (exit_fill - entry) * qty
    net = gross - fees
    risk_rupees = risk_per_unit * qty
    expected_bars = (
        int((exit_bar["time"] - signal["entry_time"]).total_seconds() // 60) + 1
    )
    observed_bars = sum(
        1
        for dt in contract_data["bars"]
        if signal["entry_time"] <= dt <= exit_bar["time"]
    )
    coverage = observed_bars / expected_bars if expected_bars > 0 else 0.0
    return {
        "date": signal["date"],
        "underlying": signal["underlying"],
        "tier": signal["tier"],
        "direction": signal["direction"],
        "signal_time": signal["signal_time"],
        "entry_time": signal["entry_time"],
        "entry": entry,
        "exit_time": exit_bar["time"],
        "exit": exit_fill,
        "exit_reason": exit_reason,
        "net_r": net / risk_rupees,
        "net_rupees": net,
        "option_contract": contract["tradingsymbol"],
        "expiry": contract["expiry"],
        "strike": contract["strike"],
        "lot_size": qty,
        "entry_option_candle": True,
        "option_candles_observed": observed_bars,
        "option_candles_expected": expected_bars,
        "option_candle_coverage_pct": coverage * 100.0,
        "day_direction": signal["day_direction"],
        "partial_status": "single-lot-ineligible",
        "raw_entry_open": raw_entry,
        "raw_exit_price": raw_exit,
        "fees_rupees": fees,
        "initial_risk_rupees": risk_rupees,
        "range_minutes": signal["range_minutes"],
        "_exit_bar_time": exit_bar["time"],
    }


def fmt(value: Any, digits: int = 4) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    if isinstance(value, datetime):
        return iso_minute(value)
    return str(value)


def write_trade_csv(rows: list[dict], path: Path) -> str:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            output = {}
            for field in CSV_FIELDS:
                value = row.get(field)
                if field in {"signal_time", "entry_time", "exit_time"}:
                    value = iso_minute(value) if isinstance(value, datetime) else ""
                elif field in {"entry_option_candle"}:
                    value = fmt(value)
                elif isinstance(value, (int, float)):
                    value = fmt(value, 6 if field in {"net_r", "option_candle_coverage_pct"} else 4)
                output[field] = value if value is not None else ""
            writer.writerow(output)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decision_files() -> list[Path]:
    found = []
    for path in PAPER.rglob("*.parquet"):
        if path.name.startswith("decisions"):
            found.append(path)
    return sorted(found)


def parse_json_dict(value: Any) -> dict:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def load_decisions() -> list[dict]:
    columns = [
        "timestamp",
        "ticker",
        "signal",
        "outcome",
        "outcome_detail",
        "rejection_reason",
        "bar",
        "strategy_variant",
    ]
    unique = {}
    for path in decision_files():
        try:
            table = pq.read_table(path, columns=columns)
        except (OSError, ValueError):
            continue
        for row in table.to_pylist():
            try:
                stamp = parse_dt(row["timestamp"])
            except (TypeError, ValueError):
                continue
            day = stamp.date().isoformat()
            if day not in DATES:
                continue
            row["time"] = stamp
            row["date"] = day
            if str(row.get("strategy_variant") or "primary") != "primary":
                continue
            identifier = tuple(
                str(row.get(name) or "")
                for name in (
                    "timestamp",
                    "ticker",
                    "signal",
                    "outcome",
                    "outcome_detail",
                    "rejection_reason",
                    "bar",
                    "strategy_variant",
                )
            )
            unique[identifier] = row
    return sorted(unique.values(), key=lambda row: row["time"])


def decision_episodes(rows: list[dict], rejected_only: bool) -> list[dict]:
    candidates = []
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        signal = str(row.get("signal") or "").upper()
        if not ticker.endswith(("_CE", "_PE")) or signal not in {"BUY", "SELL"}:
            continue
        rejection = str(row.get("rejection_reason") or "").strip()
        outcome = str(row.get("outcome") or "")
        if rejected_only and not (
            rejection
            or outcome in {"option_filter", "accuracy_filter", "risk_blocked"}
        ):
            continue
        row = dict(row)
        row["direction"] = "CE" if signal == "BUY" else "PE"
        row["underlying"] = ticker.rsplit("_", 1)[0]
        row["rejection"] = rejection or outcome
        candidates.append(row)

    candidates.sort(
        key=lambda row: (
            row["date"],
            row["underlying"],
            row["direction"],
            row["time"],
        )
    )
    episodes = []
    last = None
    for row in candidates:
        group_key = (
            row["date"],
            row["underlying"],
            row["direction"],
            row["rejection"] if rejected_only else "",
        )
        if (
            last is None
            or group_key != last["_group_key"]
            or (row["time"] - last["_last_time"]).total_seconds() > 5 * 60
        ):
            episode = dict(row)
            episode["_group_key"] = group_key
            episode["_last_time"] = row["time"]
            episodes.append(episode)
            last = episode
        else:
            last["_last_time"] = row["time"]
    return episodes


def match_decision_bar(
    episode: dict,
    options: dict,
) -> dict | None:
    bar = parse_json_dict(episode.get("bar"))
    if not bar:
        return None
    try:
        bar_time = parse_dt(bar.get("time"))
        target = {
            name: float(bar[name])
            for name in ("open", "high", "low", "close")
        }
    except (TypeError, ValueError, KeyError):
        return None
    candidates = []
    for key, data in options.items():
        day, underlying, expiry, strike, option_type = key
        if (
            day != episode["date"]
            or underlying != episode["underlying"]
            or option_type != episode["direction"]
        ):
            continue
        candle = data["bars"].get(bar_time.replace(second=0, microsecond=0))
        if candle and all(
            abs(candle[field] - target[field]) <= 0.011
            for field in ("open", "high", "low", "close")
        ):
            candidates.append(data)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # Identical sampled OHLCs are rare; prefer the nearest-to-spot contract.
        spot = None
        for path in (DATA / episode["date"]).glob(
            f"underlyings__{episode['underlying']}.csv"
        ):
            for candle in read_csv(path):
                dt = parse_dt(candle["timestamp"])
                if dt <= bar_time:
                    spot = float(candle["close"])
                else:
                    break
        if spot is not None:
            return min(candidates, key=lambda item: (abs(item["strike"] - spot), item["strike"]))
    return None


def replay_rejections(episodes: list[dict], options: dict) -> list[dict]:
    replayed = []
    for episode in episodes:
        data = match_decision_bar(episode, options)
        contract = None
        if data:
            contract = {
                "tradingsymbol": data["tradingsymbol"],
                "expiry": data["expiry"],
                "strike": data["strike"],
                "lot_size": data["lot_size"],
            }
            bar_data = parse_json_dict(episode.get("bar"))
            try:
                bar_time = parse_dt(bar_data["time"]).replace(second=0, microsecond=0)
            except (TypeError, ValueError, KeyError):
                bar_time = None
            entry_time = bar_time + timedelta(minutes=1) if bar_time else None
            if entry_time is None or entry_time not in data["bars"]:
                data = None
        if not data:
            replayed.append(
                {
                    "date": episode["date"],
                    "underlying": episode["underlying"],
                    "direction": episode["direction"],
                    "episode_time": episode["time"],
                    "rejection": episode["rejection"],
                    "entry_time": None,
                    "contract": "",
                    "net_r": None,
                    "net_rupees": None,
                    "status": "no exact option-candle contract match at entry",
                }
            )
            continue
        signal = {
            "date": episode["date"],
            "underlying": episode["underlying"],
            "tier": "index" if episode["underlying"] in INDEXES else "stock",
            "direction": episode["direction"],
            "signal_time": episode["time"],
            "entry_time": entry_time,
            "range_minutes": 0,
            "day_direction": "not-classified",
        }
        trade = simulate_signal(signal, contract, options)
        replayed.append(
            {
                "date": episode["date"],
                "underlying": episode["underlying"],
                "direction": episode["direction"],
                "episode_time": episode["time"],
                "rejection": episode["rejection"],
                "entry_time": trade["entry_time"] if trade["entry"] is not None else None,
                "contract": contract["tradingsymbol"],
                "net_r": trade["net_r"],
                "net_rupees": trade["net_rupees"],
                "status": trade["exit_reason"],
            }
        )
    return replayed


def load_actual_paper_trades() -> list[dict]:
    output = []
    if not TRADES_FILE.exists():
        return output
    for line in TRADES_FILE.read_text(encoding="utf-8").splitlines():
        try:
            trade = json.loads(line)
        except json.JSONDecodeError:
            continue
        ticker = str(trade.get("ticker") or "").upper()
        if not ticker.endswith(("_CE", "_PE")):
            continue
        underlying = ticker.rsplit("_", 1)[0]
        if underlying not in UNDERLYINGS or trade.get("status") != "closed":
            continue
        try:
            stamp = parse_dt(trade.get("timestamp"))
            day = stamp.date().isoformat()
            entry = float(trade["entry"])
            quantity = int(trade.get("entry_quantity") or trade.get("quantity"))
            exit_price = float(trade["exit_price"])
            pnl = float(trade.get("pnl", trade.get("pnl_rupees")))
        except (TypeError, ValueError, KeyError, OverflowError):
            continue
        if day not in DATES or quantity <= 0:
            continue
        risk = fnum(trade.get("paper_entry_risk_rupees"))
        if risk is None or risk <= 0:
            risk_per_unit = fnum(trade.get("initial_risk_per_unit"))
            if risk_per_unit is not None and risk_per_unit > 0:
                risk = risk_per_unit * quantity
        if risk is None or risk <= 0:
            stop = trade.get("initial_stop_loss")
            risk_source = "initial_stop_loss"
            if stop in (None, ""):
                risk_source = "recorded_stop_loss"
                stop = trade.get("stop_loss")
                modifications = trade.get("risk_modifications") or []
                if isinstance(modifications, str):
                    try:
                        modifications = json.loads(modifications)
                    except json.JSONDecodeError:
                        modifications = []
                if isinstance(modifications, list):
                    for modification in modifications:
                        if (
                            isinstance(modification, dict)
                            and modification.get("field") == "stop_loss"
                        ):
                            stop = modification.get("old_value")
                            risk_source = "recovered_initial_stop"
                            break
            stop_value = fnum(stop)
            if stop_value is None:
                continue
            risk = abs(entry - stop_value) * quantity
        else:
            risk_source = (
                "paper_entry_risk_rupees"
                if fnum(trade.get("paper_entry_risk_rupees")) is not None
                else "initial_risk_per_unit"
            )
        exit_legs = trade.get("exit_legs")
        fee = None
        if isinstance(exit_legs, list) and exit_legs:
            entry_turnover = entry * quantity
            exit_orders = []
            for leg in exit_legs:
                leg_price = fnum(leg.get("fill", leg.get("price")))
                leg_qty = fnum(leg.get("quantity"))
                if leg_price is not None and leg_qty is not None and leg_qty > 0:
                    exit_orders.append((leg_price, int(leg_qty)))
            if exit_orders:
                fee = fee_for_orders(entry_turnover, entry, exit_orders)
        if fee is None:
            fee = fee_for_round_trip(entry, exit_price, quantity)
        if risk <= 0:
            continue
        output.append(
            {
                "date": day,
                "underlying": underlying,
                "direction": "CE" if ticker.endswith("_CE") else "PE",
                "timestamp": stamp,
                "tier": "index" if underlying in INDEXES else "stock",
                "quantity": quantity,
                "entry": entry,
                "exit": exit_price,
                "gross_rupees": pnl,
                "fees_rupees": fee,
                "net_rupees": pnl - fee,
                "gross_r": pnl / risk,
                "net_r": (pnl - fee) / risk,
                "initial_risk_rupees": risk,
                "risk_source": risk_source,
                "trade_id": trade.get("trade_id", ""),
                "strategy_variant": trade.get("strategy_variant", ""),
            }
        )
    return output


def fee_for_orders(
    entry_turnover: float,
    entry_price: float,
    exits: list[tuple[float, int]],
) -> float:
    total_turnover = entry_turnover
    sell_turnover = 0.0
    brokerage = CHARGES["brokerage_flat_inr"]
    stamp = entry_turnover * CHARGES["stamp_buy_rate"]
    for price, quantity in exits:
        turnover = price * quantity
        total_turnover += turnover
        sell_turnover += turnover
        brokerage += CHARGES["brokerage_flat_inr"]
    exchange = total_turnover * CHARGES["exchange_rate"]
    sebi = total_turnover * CHARGES["sebi_rate"]
    stt = sell_turnover * CHARGES["stt_sell_rate"]
    gst = (brokerage + exchange + sebi) * CHARGES["gst_rate"]
    return round(
        sum(
            round(value, 2)
            for value in (brokerage, stt, exchange, sebi, stamp, gst)
        ),
        2,
    )


def metric_row(rows: list[dict], tier: str) -> dict:
    selected = [
        row
        for row in rows
        if row.get("net_r") is not None
        and (tier == "combined" or row.get("tier") == tier)
    ]
    wins = [row for row in selected if row["net_rupees"] > 0]
    losses = [row for row in selected if row["net_rupees"] < 0]
    net_rupees = sum(row["net_rupees"] for row in selected)
    gross_wins = sum(row["net_rupees"] for row in wins)
    gross_losses = abs(sum(row["net_rupees"] for row in losses))
    best = max(selected, key=lambda row: row["net_rupees"]) if selected else None
    without_best = [
        row for row in selected if row is not best
    ] if best else selected
    daily = defaultdict(float)
    for row in selected:
        daily[row["date"]] += row["net_rupees"]
    positive = sum(1 for day in DATES if daily.get(day, 0.0) > 0)
    return {
        "tier": tier,
        "trades": len(selected),
        "signals": sum(
            1
            for row in rows
            if tier == "combined" or row.get("tier") == tier
        ),
        "no_option_data": sum(
            1
            for row in rows
            if row.get("net_r") is None
            and (tier == "combined" or row.get("tier") == tier)
        ),
        "win_rate": len(wins) / len(selected) if selected else 0.0,
        "mean_net_r": mean(row["net_r"] for row in selected) if selected else 0.0,
        "profit_factor": (
            gross_wins / gross_losses if gross_losses > 0 else None
        ),
        "net_rupees": net_rupees,
        "best_trade_rupees": best["net_rupees"] if best else 0.0,
        "net_without_best": sum(row["net_rupees"] for row in without_best),
        "mean_r_without_best": (
            mean(row["net_r"] for row in without_best) if without_best else 0.0
        ),
        "positive_sessions": positive,
        "total_sessions": len(DATES),
        "mean_candle_coverage_pct": (
            mean(row["option_candle_coverage_pct"] for row in selected)
            if selected
            else 0.0
        ),
    }


def bot_metric(rows: list[dict]) -> dict:
    wins = [row for row in rows if row["net_rupees"] > 0]
    losses = [row for row in rows if row["net_rupees"] < 0]
    total = sum(row["net_rupees"] for row in rows)
    return {
        "trades": len(rows),
        "win_rate": len(wins) / len(rows) if rows else 0.0,
        "mean_net_r": mean(row["net_r"] for row in rows) if rows else 0.0,
        "mean_gross_r": (
            mean(row["gross_r"] for row in rows if "gross_r" in row)
            if rows and any("gross_r" in row for row in rows)
            else None
        ),
        "net_rupees": total,
        "profit_factor": (
            sum(row["net_rupees"] for row in wins)
            / abs(sum(row["net_rupees"] for row in losses))
            if losses
            else None
        ),
    }


def match_count(orb: list[dict], episodes: list[dict]) -> int:
    count = 0
    for trade in orb:
        if trade["net_r"] is None and not trade.get("signal_time"):
            continue
        for episode in episodes:
            if (
                trade["date"] != episode["date"]
                or trade["underlying"] != episode["underlying"]
                or trade["direction"] != episode["direction"]
            ):
                continue
            episode_time = episode.get("time", episode.get("timestamp"))
            if episode_time is not None and abs(
                (trade["signal_time"] - episode_time).total_seconds()
            ) <= 300:
                count += 1
                break
    return count


def signal_direction_table(rows: list[dict]) -> dict:
    counts = defaultdict(int)
    for row in rows:
        if row["net_r"] is not None:
            counts[(row["direction"], row["day_direction"])] += 1
    output = {}
    for direction in ("CE", "PE"):
        total = sum(counts[(direction, day)] for day in ("up", "down", "flat"))
        output[direction] = {
            day: {
                "trades": counts[(direction, day)],
                "share_pct": (
                    counts[(direction, day)] / total * 100.0 if total else 0.0
                ),
            }
            for day in ("up", "down", "flat")
        }
    return output


def result_label(primary: dict, bot: dict) -> str:
    if primary["trades"] < 40:
        return "NO CONCLUSION: fewer than 40 baseline trades had entry option data."
    if (
        primary["mean_net_r"] >= bot["mean_net_r"]
        and primary["net_without_best"] > 0
    ):
        return "MATCHES OR BEATS the recorded PAPER traded mean under this fixed model."
    if primary["mean_net_r"] < bot["mean_net_r"]:
        return "BASELINE WORSE than the recorded PAPER traded mean under this fixed model."
    return "NO CONCLUSION: it did not remain positive after removing its best trade."


def table_metrics(rows: list[dict]) -> str:
    headers = [
        "Tier",
        "Trades",
        "Signals",
        "No option data",
        "Win rate",
        "Mean net R",
        "Profit factor",
        "Net INR",
        "Net INR excl. best",
        "Mean R excl. best",
        "Positive sessions",
        "Mean candle coverage",
    ]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for tier in ("index", "stock", "combined"):
        item = metric_row(rows, tier)
        pf = "n/a" if item["profit_factor"] is None else f'{item["profit_factor"]:.3f}'
        lines.append(
            "| "
            + " | ".join(
                [
                    tier,
                    str(item["trades"]),
                    str(item["signals"]),
                    str(item["no_option_data"]),
                    f'{item["win_rate"]:.1%}',
                    f'{item["mean_net_r"]:+.4f}',
                    pf,
                    f'{item["net_rupees"]:+,.2f}',
                    f'{item["net_without_best"]:+,.2f}',
                    f'{item["mean_r_without_best"]:+.4f}',
                    f'{item["positive_sessions"]}/{item["total_sessions"]}',
                    f'{item["mean_candle_coverage_pct"]:.1f}%',
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def write_report(
    primary: list[dict],
    sensitivity: list[dict],
    hashes: dict[str, str],
    actual: list[dict],
    rejected_replay: list[dict],
    bot_signals: list[dict],
    bot_rejections: list[dict],
    all_decisions: list[dict],
) -> None:
    primary_all = metric_row(primary, "combined")
    actual_stats = bot_metric(actual)
    rejected_with_data = [
        row for row in rejected_replay if row["net_r"] is not None
    ]
    rejected_stats = bot_metric(rejected_with_data)
    no_option_primary = sum(1 for row in primary if row["net_r"] is None)
    entry_candles = sum(1 for row in primary if row["entry_option_candle"])
    expected = sum(row["option_candles_expected"] for row in primary)
    observed = sum(row["option_candles_observed"] for row in primary)
    direction = signal_direction_table(primary)
    matched_signal = match_count(primary, bot_signals)
    matched_trade = match_count(primary, actual)
    matched_reject = match_count(primary, bot_rejections)
    actual_by_variant = defaultdict(list)
    for row in actual:
        actual_by_variant[row["strategy_variant"] or "primary"].append(row)
    risk_sources = Counter(row["risk_source"] for row in actual)

    lines = [
        "# Fixed ORB sanity baseline",
        "",
        "## Result",
        "",
        result_label(primary_all, actual_stats),
        "",
        "This is a fixed, in-sample sanity baseline over 18 sessions, not an edge test. "
        "Eighteen sessions cannot prove an edge either way. No bot entry or exit change is proposed.",
        "",
        "## Output order and integrity",
        "",
        "The trade-level CSVs below were written and SHA-256 hashed before this summary was generated.",
        "",
        f"- 15-minute baseline: `orb_15m_trades.csv` SHA-256 `{hashes['orb_15m_trades.csv']}`",
        f"- 30-minute sensitivity: `orb_30m_sensitivity_trades.csv` SHA-256 `{hashes['orb_30m_sensitivity_trades.csv']}`",
        "- Digests are also stored in `SHA256SUMS.txt`.",
        "",
        "## Data and fixed rules",
        "",
        f"- Sessions: {len(DATES)} ({DATES[0]} through {DATES[-1]}); dates: {', '.join(DATES)}. The 2026-10-20 no-data day is excluded.",
        f"- Underlyings: {', '.join(UNDERLYINGS)}. Opening-range bars and option bars use `Asia/Kolkata` minute timestamps.",
        "- 15-minute range uses 09:15–09:29 start-stamped bars; signal scan begins with the 09:30 bar and ends with a signal bar starting by 14:45. "
        "The 30-minute sensitivity uses 09:15–09:44 and begins scanning at 09:45.",
        "- The breakout is the first close strictly outside the range, one signal per underlying/day. Entry uses the next underlying bar's timestamp and the selected option candle's open.",
        "- Contract selection uses the full per-day NFO snapshot: earliest expiry from the session date through +35 calendar days, then the strike nearest the underlying close on the breakout bar (ties choose lower strike). "
        "The exact selected contract must have a sampled option candle at the next-bar entry timestamp; otherwise it is counted as no option data and excluded from P&L.",
        f"- Primary option coverage: {entry_candles}/{len(primary)} signals had the selected-contract entry candle; {no_option_primary} are no-option-data signals. "
        f"Across included trades, {observed}/{expected} expected one-minute candles were present ({observed / expected:.1%} overall where expected > 0).",
        "- Each included trade is one lot. At +0.5R the stop is raised to +0.15R; the runner activates at +2R with a 1.5R gap. "
        "The current `partial_profit_v2` setting is 50% at +0.5R, but it is ineligible for these one-lot baseline positions (floor of half a lot is zero); no baseline partial is taken. "
        "The current stock +0.8R take-profit requires a valid live option bid and was not reproducible from these OHLC candles, so it is not modeled.",
        "- `trail_close_confirm_v2` is represented by requiring a one-minute close beyond an already-active runner stop. A trailing stop updated from a candle's high applies from the following candle.",
        "- Ambiguous intrabar sequences are handled conservatively: the stop active before the candle is checked first; newly reached locks/runner stops do not apply retroactively within that candle. "
        "A stop gap uses the candle open if it is beyond the stop; otherwise the stop level is used.",
        "- Forced exit uses the last available option candle starting by 15:14 (15:15 close). Missing minutes are not interpolated; the observed/expected held-minute coverage appears per row.",
        f"- Entry and exit slippage: external fixed assumption of {ENTRY_SLIPPAGE:.0%} of option premium on each side (entry premium +1%, exit premium −1%), as requested; it is not a bot setting.",
        "- There are no historical bid/ask quotes in the candle dataset. This is candle-based and likely still slightly optimistic versus real fills.",
        "- Fees use the checked-in PAPER flat brokerage mode: INR 20 per order; STT 0.15% on sell turnover; exchange 0.03553%; SEBI 0.0001%; stamp duty 0.003% on buy turnover; GST 18% on brokerage + exchange + SEBI. "
        "Round-trip brokerage is INR 40 before taxes/other charges.",
        "- Net R divides net rupees by initial premium risk (10% of slipped entry premium × lot size). Profit factor is the ratio of positive to absolute negative net rupees.",
        "",
        "## 15-minute baseline results",
        "",
        table_metrics(primary),
        "",
        "## 30-minute sensitivity (reported separately; not selected)",
        "",
        table_metrics(sensitivity),
        "",
        "No better-performing range is selected; 30 minutes is a single predeclared sensitivity only.",
        "",
        "## Bot results on the same underlyings and dates",
        "",
        f"- Actual closed PAPER journal trades (not replay): **{actual_stats['trades']}**; mean gross R **{actual_stats['mean_gross_r']:+.4f}**; mean net R **{actual_stats['mean_net_r']:+.4f}**; win rate **{actual_stats['win_rate']:.1%}**; net rupees **{actual_stats['net_rupees']:+,.2f}**; profit factor **{actual_stats['profit_factor']:.3f}**.",
        "- Actual trade P&L comes from closed rows in `trades.jsonl`; recorded fills already incorporate the bot's paper bid/ask handling. The checked-in modeled fees above were deducted, with no second slippage deduction on those actual fills. Net R uses `paper_entry_risk_rupees` when available, otherwise initial-risk/stop fields and the earliest logged stop modification.",
        f"- Actual PAPER trades by recorded strategy variant: "
        + "; ".join(
            f"{variant}: {bot_metric(rows)['trades']} trades, mean net R {bot_metric(rows)['mean_net_r']:+.4f}"
            for variant, rows in sorted(actual_by_variant.items())
        )
        + ". The journal includes actual `paper_option_range_breakout` entries even though the checked-in current config disables that feature; all actual variants are included in the aggregate, and this is not a pure primary-only cohort.",
        f"- Risk-denominator sources in the actual journal: {dict(risk_sources)}.",
        f"- Rejected episodes: {len(rejected_replay)} deduplicated primary decision episodes; exact option candle contract and next-minute entry data were available for {len(rejected_with_data)} "
        f"({len(rejected_replay) - len(rejected_with_data)} unmatched). "
        f"The matched counterfactual mean net R is **{rejected_stats['mean_net_r']:+.4f}** on {rejected_stats['trades']} episodes (net INR {rejected_stats['net_rupees']:+,.2f}).",
        "- Rejected-episode outcomes are a counterfactual replay, not bot trades or observed PAPER P&L. Episodes are formed from contiguous same-day/symbol/direction/rejection decision rows separated by no more than five minutes; only cases whose decision-bar OHLC matches exactly one sampled option contract (or an identical-match tie resolved by nearest spot) are assigned an outcome.",
        f"- ORB reconciliation (primary {len(primary)} signals): {matched_signal} coincide within ±5 minutes and same direction with a distinct bot signal episode; {matched_trade} with an actual bot trade timestamp; {matched_reject} with a rejected bot episode. These categories can overlap.",
        f"- Decision archive rows considered: {len(all_decisions)} primary deduplicated rows; bot signal episodes: {len(bot_signals)}; rejected episodes: {len(bot_rejections)}. Matching compares option ticker suffix to ORB direction (BUY/CE, SELL/PE).",
        "",
        "## Trades by underlying day direction",
        "",
        "| ORB direction | Day direction | Trades | Share within ORB direction |",
        "|---|---:|---:|---:|",
    ]
    for option_direction in ("CE", "PE"):
        for day_direction in ("up", "down", "flat"):
            detail = direction[option_direction][day_direction]
            lines.append(
                f"| {option_direction} | {day_direction} | {detail['trades']} | {detail['share_pct']:.1f}% |"
            )
    lines.extend(
        [
            "",
            "Day direction is underlying first 09:15 bar open to its last available session close (stocks' underlying files end at 15:14; index files run later). "
            "The table includes only baseline trades with entry option data.",
            "",
            "## Data gaps and limitations",
            "",
            "- Option candles are sampled contracts, not complete chains. Selected contracts with no entry candle are counted but excluded; a missing bar during a held trade reduces the reported coverage and is not reconstructed.",
            "- No bid/ask history, quote freshness, intrabar tick order, queue position, latency, market impact, or executable fill confirmation is available. The 1% one-way slippage assumption is fixed as specified, but cannot prove actual execution costs.",
            "- The bot's actual journal does not provide complete immutable strategy state for every trade. Its net R is post-hoc modeled from the recorded entry, exit, stop, quantity, and checked-in fees; any recorded partial exit legs are used when present.",
            "- Rejected decisions do not retain exact option-contract identifiers in the decision schema. Rejected counterfactuals are therefore restricted to a candle-value match against sampled option files; unmatched episodes have no outcome and are not in the mean.",
            "- The stock +0.8R target cannot be faithfully reproduced without live bid validation. No standalone +0.5R breakeven is modeled: the fixed requested/current PAPER interpretation is the +0.15R lock at +0.5R.",
            "- This sample is small, clustered by day and underlying, and includes a majority-up market period. Descriptive results do not establish predictive power.",
            "",
        ]
    )
    (OUT / "ORB_BASELINE_REPORT.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    underlyings, instruments, options = load_market_data()
    primary = make_signals(15, underlyings, instruments, options)
    sensitivity = make_signals(30, underlyings, instruments, options)

    primary_hash = write_trade_csv(primary, OUT / "orb_15m_trades.csv")
    sensitivity_hash = write_trade_csv(
        sensitivity, OUT / "orb_30m_sensitivity_trades.csv"
    )
    hashes = {
        "orb_15m_trades.csv": primary_hash,
        "orb_30m_sensitivity_trades.csv": sensitivity_hash,
    }
    (OUT / "SHA256SUMS.txt").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in hashes.items()),
        encoding="ascii",
    )

    decisions = load_decisions()
    all_signal_episodes = decision_episodes(decisions, rejected_only=False)
    rejected_episodes = decision_episodes(decisions, rejected_only=True)
    rejection_replay = replay_rejections(rejected_episodes, options)
    actual = load_actual_paper_trades()
    write_report(
        primary,
        sensitivity,
        hashes,
        actual,
        rejection_replay,
        all_signal_episodes,
        rejected_episodes,
        decisions,
    )

    primary_metric = metric_row(primary, "combined")
    actual_metric = bot_metric(actual)
    print(f"Primary signals: {len(primary)}; option-data trades: {primary_metric['trades']}; no data: {primary_metric['no_option_data']}")
    print(f"Primary mean net R: {primary_metric['mean_net_r']:+.5f}")
    print(f"Bot actual trades: {actual_metric['trades']}; mean net R: {actual_metric['mean_net_r']:+.5f}")
    print(f"Rejected episodes mapped: {sum(row['net_r'] is not None for row in rejection_replay)}/{len(rejection_replay)}")
    print(f"CSV hashes: {hashes}")
    print(f"Report: {OUT / 'ORB_BASELINE_REPORT.md'}")


if __name__ == "__main__":
    main()
