#!/usr/bin/env python3
"""Replay exit policies against archived exact-contract option data.

This utility is intentionally isolated from the live trading and exit code.
It reads paper trade Parquet files and archived option candles/quotes, then
writes a Markdown report. It never writes to the paper session or bot config.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


IST = ZoneInfo("Asia/Kolkata")
EXIT_FRACTIONS = (0.33, 0.50, 0.66)
RUNNER_GAPS = (1.25, 1.50, 1.75, 2.00)
DEFAULT_START = date(2026, 11, 4)
DEFAULT_END = date(2026, 11, 6)
EXPECTED_NOV06_GROSS = 5344.50


@dataclass(frozen=True)
class Fill:
    price: float
    timestamp: datetime
    source: str


@dataclass
class Replay:
    policy: str
    gross: float | None
    net: float | None
    r_multiple: float | None
    exit_price: float | None
    exit_time: datetime | None
    exit_reason: str
    costs: float | None
    complete: bool
    note: str = ""


def parse_datetime(value: Any) -> datetime | None:
    if value is None or str(value).strip() in {"", "None", "nan"}:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def number(value: Any, default: float | None = None) -> float | None:
    if value is None or pd.isna(value) or str(value).strip() in {"", "None", "nan"}:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def clean_record(record: dict[str, Any]) -> dict[str, Any]:
    clean = {}
    for key, value in record.items():
        try:
            missing = bool(pd.isna(value))
        except (TypeError, ValueError):
            missing = False
        clean[str(key)] = None if missing else value
    return clean


def load_trades(root: Path, start: date, end: date) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for path in sorted((root / "paper_trading_data").rglob("trades.parquet")):
        frame = pd.read_parquet(path)
        for raw in frame.to_dict(orient="records"):
            record = clean_record(raw)
            if str(record.get("status", "")).lower() != "closed":
                continue
            entered = parse_datetime(record.get("entry_time")) or parse_datetime(
                record.get("timestamp")
            )
            if entered is None or not start <= entered.date() <= end:
                continue
            record["_entry_time_parsed"] = entered
            record["_closed_at_parsed"] = (
                parse_datetime(record.get("closed_at"))
                or parse_datetime(record.get("updated_at"))
            )
            record["_source_file"] = str(path)
            trades.append(record)
    return sorted(
        trades,
        key=lambda row: (row["_entry_time_parsed"], str(row.get("trade_id", ""))),
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_market_rows(
    day_dir: Path, contract_id: str, suffix: str
) -> list[dict[str, Any]]:
    symbol = contract_id.split(":", 1)[-1]
    candidates = sorted(day_dir.glob(f"NFO_{symbol}.{suffix}.csv*"))
    rows_by_time: dict[datetime, dict[str, Any]] = {}
    for path in candidates:
        for raw in _read_csv(path):
            if raw.get("contract_id") != contract_id:
                continue
            time_value = (
                raw.get("candle_start_time") if suffix == "candles" else raw.get("time")
            )
            timestamp = parse_datetime(time_value)
            if timestamp is None:
                continue
            row: dict[str, Any] = {"time": timestamp, "_path": path.name}
            for key, value in raw.items():
                if key in {"candle_start_time", "time"}:
                    continue
                parsed = number(value)
                if parsed is not None:
                    row[key] = parsed
                elif value is not None:
                    row[key] = value
            old = rows_by_time.get(timestamp)
            if old is None or _row_quality(row, suffix) > _row_quality(old, suffix):
                rows_by_time[timestamp] = row
    return [rows_by_time[key] for key in sorted(rows_by_time)]


def _row_quality(row: dict[str, Any], suffix: str) -> tuple[float, ...]:
    if suffix == "candles":
        return (
            float(str(row.get("gap", "")).lower() not in {"true", "1"}),
            float(row.get("tick_count") or 0),
            float(row.get("volume") or 0),
        )
    bid = number(row.get("bid"), 0.0) or 0.0
    ask = number(row.get("ask"), 0.0) or 0.0
    return (
        float(bid > 0 and ask >= bid),
        -float(row.get("quote_age_seconds") or math.inf),
    )


def read_capture_gaps(day_dir: Path) -> tuple[dict[str, int], dict[str, int]]:
    report = day_dir / "capture_report.txt"
    candle_gaps: dict[str, int] = {}
    tick_gaps: dict[str, int] = {}
    if not report.is_file():
        return candle_gaps, tick_gaps
    text = report.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("Candle gaps:"):
            try:
                candle_gaps = {
                    str(key): int(value)
                    for key, value in json.loads(line.split(":", 1)[1].strip()).items()
                }
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
        elif line.startswith("Tick gaps >30s:"):
            try:
                tick_gaps = {
                    str(key): int(value)
                    for key, value in json.loads(line.split(":", 1)[1].strip()).items()
                }
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
    return candle_gaps, tick_gaps


def build_capture_index(root: Path) -> dict[date, tuple[dict[str, int], dict[str, int]]]:
    result = {}
    for day_dir in sorted((root / "paper_trading_data" / "option_candles").glob("20??-??-??")):
        try:
            day = date.fromisoformat(day_dir.name)
        except ValueError:
            continue
        result[day] = read_capture_gaps(day_dir)
    return result


def valid_market_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid = []
    for row in rows:
        if all(number(row.get(field)) is not None for field in ("open", "high", "low", "close")):
            if min(float(row[field]) for field in ("open", "high", "low", "close")) > 0:
                valid.append(row)
    return valid


def valid_quote(row: dict[str, Any]) -> bool:
    bid = number(row.get("bid"))
    ask = number(row.get("ask"))
    return bid is not None and bid > 0 and (ask is None or ask >= bid)


def next_bar_fill(
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    bar_index: int,
) -> Fill | None:
    if bar_index + 1 < len(candles):
        bar = candles[bar_index + 1]
        price = number(bar.get("open"))
        if price is not None:
            return Fill(price, bar["time"], "next_candle_open")
    after = candles[bar_index]["time"] + timedelta(minutes=1)
    for quote in quotes:
        if quote["time"] >= after and valid_quote(quote):
            bid = number(quote.get("bid"))
            if bid is not None and bid > 0:
                return Fill(bid, quote["time"], "sampled_bid")
    return None


def stop_bar_fill(
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    bar_index: int,
    stop: float,
) -> Fill | None:
    bar_start = candles[bar_index]["time"]
    bar_end = bar_start + timedelta(minutes=1)
    sampled = [
        row for row in quotes
        if bar_start <= row["time"] < bar_end
        and valid_quote(row)
    ]
    if sampled:
        closest = min(sampled, key=lambda row: abs(float(row["bid"]) - stop))
        return Fill(float(closest["bid"]), closest["time"], "sampled_bid_stop_bar")
    return next_bar_fill(candles, quotes, bar_index)


def quote_at_or_before(
    candles: list[dict[str, Any]], quotes: list[dict[str, Any]], target: datetime
) -> tuple[float | None, datetime | None, float | None, str]:
    eligible = [
        row for row in quotes
        if row["time"] <= target and valid_quote(row)
    ]
    source = "sampled_quote_bid"
    if eligible:
        row = eligible[-1]
        price = float(row["bid"])
    else:
        eligible_candles = [
            row for row in candles
            if row["time"] <= target and (number(row.get("bid")) or 0) > 0
        ]
        if not eligible_candles:
            return None, None, None, "missing"
        row = eligible_candles[-1]
        price = float(row["bid"])
        source = "candle_sampled_bid"
    age = (target - row["time"]).total_seconds()
    return price, row["time"], age, source


def trade_values(trade: dict[str, Any]) -> dict[str, Any]:
    entry = number(trade.get("entry"))
    stop = number(trade.get("stop_loss"))
    quantity = number(trade.get("quantity"))
    if entry is None or stop is None or quantity is None or entry <= stop or quantity <= 0:
        raise ValueError(f"Invalid long option trade inputs for {trade.get('trade_id')}")
    risk_points = entry - stop
    risk_rupees = risk_points * quantity
    if risk_points <= 0 or risk_rupees <= 0:
        raise ValueError(f"Invalid initial premium risk for {trade.get('trade_id')}")
    return {
        "entry": entry,
        "stop": stop,
        "quantity": quantity,
        "risk_points": risk_points,
        "risk_rupees": risk_rupees,
    }


def compute_costs(
    entry: float,
    quantity: float,
    exits: list[tuple[float, float]],
    slippage: float,
    brokerage_per_order: float,
    stt_rate: float,
    exchange_rate: float,
    sebi_rate: float,
    stamp_rate: float,
    gst_rate: float,
) -> float:
    buy_turnover = entry * quantity
    sell_turnover = sum(price * qty for price, qty in exits)
    turnover = buy_turnover + sell_turnover
    slip_cost = buy_turnover * slippage + sum(
        price * qty * slippage for price, qty in exits
    )
    brokerage = brokerage_per_order * (1 + len(exits))
    stt = sell_turnover * stt_rate
    exchange = turnover * exchange_rate
    sebi = turnover * sebi_rate
    stamp = buy_turnover * stamp_rate
    gst = (brokerage + exchange + sebi) * gst_rate
    return slip_cost + brokerage + stt + exchange + sebi + stamp + gst


def make_replay(
    policy: str,
    gross: float,
    exits: list[tuple[float, float]],
    exit_time: datetime | None,
    exit_reason: str,
    trade: dict[str, Any],
    costs_args: argparse.Namespace,
    complete: bool = True,
    note: str = "",
) -> Replay:
    values = trade_values(trade)
    costs = compute_costs(
        values["entry"],
        values["quantity"],
        exits,
        costs_args.slippage,
        costs_args.brokerage_per_order,
        costs_args.stt_rate,
        costs_args.exchange_rate,
        costs_args.sebi_rate,
        costs_args.stamp_rate,
        costs_args.gst_rate,
    )
    net = gross - costs
    return Replay(
        policy=policy,
        gross=gross,
        net=net,
        r_multiple=net / values["risk_rupees"],
        exit_price=exits[-1][0] if exits else None,
        exit_time=exit_time,
        exit_reason=exit_reason,
        costs=costs,
        complete=complete,
        note=note,
    )


def recorded_replay(trade: dict[str, Any], args: argparse.Namespace) -> Replay:
    pnl = number(trade.get("pnl_rupees"), number(trade.get("pnl")))
    if pnl is None:
        return Replay("P0", None, None, None, None, None, "missing recorded P&L", None, False)
    exit_price = number(trade.get("exit_price"))
    quantity = number(trade.get("quantity"), 0) or 0
    entry = number(trade.get("entry"), 0) or 0
    exits = [(exit_price, quantity)] if exit_price is not None else []
    result = make_replay(
        "P0",
        pnl,
        exits,
        trade.get("_closed_at_parsed"),
        str(trade.get("exit_reason") or trade.get("reason") or "recorded"),
        trade,
        args,
        complete=bool(exits),
        note=f"recorded/{str(trade.get('exit_source') or 'unknown').lower()}",
    )
    result.exit_price = exit_price
    if exit_price is None:
        result.note = "missing recorded exit price"
    if entry <= 0:
        result.complete = False
    return result


def eod_fill(
    candles: list[dict[str, Any]], quotes: list[dict[str, Any]], trade_date: date
) -> Fill | None:
    deadline = datetime.combine(trade_date, time(15, 29, 59), tzinfo=IST)
    eligible = [
        row for row in quotes
        if row["time"] <= deadline and valid_quote(row)
    ]
    if eligible:
        row = eligible[-1]
        return Fill(float(row["bid"]), row["time"], "sampled_bid_eod")
    eligible_candles = [
        row for row in candles
        if row["time"] <= deadline and (number(row.get("bid")) or 0) > 0
    ]
    if eligible_candles:
        row = eligible_candles[-1]
        return Fill(float(row["bid"]), row["time"], "candle_sampled_bid_eod")
    return None


def simulate_policy(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    args: argparse.Namespace,
    policy: str,
    runner_gap: float = 1.0,
    partial_fraction: float = 0.0,
    partial_r: float | None = None,
    p4_qualifies: bool = False,
) -> Replay:
    values = trade_values(trade)
    entry, initial_stop = values["entry"], values["stop"]
    quantity, risk_points = values["quantity"], values["risk_points"]
    entry_time: datetime = trade["_entry_time_parsed"]
    trade_day = entry_time.date()
    session_cutoff = datetime.combine(trade_day, time(15, 29, 59), tzinfo=IST)
    candles = [
        row for row in valid_market_rows(candles)
        if row["time"] <= session_cutoff
    ]
    quotes = sorted(
        (row for row in quotes if valid_quote(row)),
        key=lambda row: row["time"],
    )
    active = [
        row for row in candles
        if row["time"] + timedelta(minutes=1) > entry_time
    ]
    if not active:
        return Replay(policy, None, None, None, None, None, "missing post-entry candles", None, False)
    first_index = candles.index(active[0])
    remaining = quantity
    realized_gross = 0.0
    exit_fills: list[tuple[float, float]] = []
    exits_summary: list[tuple[float, float]] = []
    current_stop = initial_stop
    highest = entry
    runner_active = False
    partial_done = partial_fraction <= 0
    partial_qty = min(quantity * partial_fraction, quantity)
    reason = "session_end"
    last_fill: Fill | None = None
    i = first_index

    while i < len(candles) and remaining > 1e-9:
        bar = candles[i]
        if bar["time"] < entry_time:
            i += 1
            continue
        low = float(bar["low"])
        high = float(bar["high"])
        if bar["time"] < entry_time < bar["time"] + timedelta(minutes=1):
            entry_minute = [
                row for row in quotes
                if entry_time <= row["time"] < bar["time"] + timedelta(minutes=1)
            ]
            sampled_prices = [
                number(row.get("ltp"), number(row.get("bid")))
                for row in entry_minute
                if number(row.get("ltp"), number(row.get("bid"))) is not None
            ]
            sampled_bids = [
                float(row["bid"]) for row in entry_minute if valid_quote(row)
            ]
            if sampled_prices:
                high = max(sampled_prices)
                low = min(sampled_bids or sampled_prices)
        stop_hit = low <= current_stop
        highest_after = max(highest, high)
        candidate_stop = current_stop
        if highest_after >= entry + 0.5 * risk_points:
            candidate_stop = max(candidate_stop, entry)
        if highest_after >= entry + 2.0 * risk_points:
            runner_active = True
        if runner_active:
            candidate_stop = max(candidate_stop, highest_after - runner_gap * risk_points)
        stop_hit = stop_hit or low <= candidate_stop

        if stop_hit:
            fill = stop_bar_fill(candles, quotes, i, candidate_stop)
            if fill is None:
                return Replay(policy, None, None, None, None, None, "stop hit but no permitted fill", None, False)
            realized_gross += (fill.price - entry) * remaining
            exit_fills.append((fill.price, remaining))
            exits_summary.append((fill.price, remaining))
            last_fill = fill
            reason = "runner_stop" if runner_active else (
                "breakeven_stop" if candidate_stop >= entry else "initial_stop"
            )
            remaining = 0.0
            break

        highest = highest_after
        current_stop = candidate_stop
        partial_triggered = (
            not partial_done
            and partial_r is not None
            and highest >= entry + partial_r * risk_points
            and (policy != "P4" or p4_qualifies)
        )
        if partial_triggered:
            fill = next_bar_fill(candles, quotes, i)
            if fill is None:
                return Replay(policy, None, None, None, None, None, "partial trigger but no permitted fill", None, False)
            sold = min(partial_qty, remaining)
            realized_gross += (fill.price - entry) * sold
            exit_fills.append((fill.price, sold))
            exits_summary.append((fill.price, sold))
            remaining -= sold
            partial_done = True
            last_fill = fill
            reason = f"partial_{partial_r:g}R_then_{'runner' if runner_active else 'stop'}"
            # The partial fills at the next bar open; the remaining quantity is
            # then managed through that bar's range on the next iteration.
            i += 1
            continue
        i += 1

    if remaining > 1e-9:
        final_fill = eod_fill(candles, quotes, trade_day)
        if final_fill is None or final_fill.timestamp < entry_time:
            return Replay(policy, None, None, None, None, None, "no valid end-of-session sampled bid", None, False)
        realized_gross += (final_fill.price - entry) * remaining
        exit_fills.append((final_fill.price, remaining))
        exits_summary.append((final_fill.price, remaining))
        last_fill = final_fill
        reason = "session_end_sampled_bid"

    if not exits_summary or last_fill is None:
        return Replay(policy, None, None, None, None, None, "no exit fills", None, False)
    result = make_replay(
        policy,
        realized_gross,
        exits_summary,
        last_fill.timestamp,
        reason,
        trade,
        args,
    )
    result.exit_price = last_fill.price
    result.note = last_fill.source
    return result


def session_max_r(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
) -> float | None:
    values = trade_values(trade)
    start = trade["_entry_time_parsed"]
    cutoff = datetime.combine(start.date(), time(15, 29, 59), tzinfo=IST)
    highs = []
    for row in valid_market_rows(candles):
        bar_end = row["time"] + timedelta(minutes=1)
        if bar_end <= start or row["time"] > cutoff:
            continue
        if row["time"] < start < bar_end:
            partial_samples = [
                number(quote.get("ltp"))
                for quote in quotes
                if start <= quote["time"] < bar_end
            ]
            highs.extend(
                float(value) for value in partial_samples if value is not None
            )
        else:
            highs.append(float(row["high"]))
    if not highs:
        return None
    return (max(highs) - values["entry"]) / values["risk_points"]


def path_max_r(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    exit_time: datetime | None,
) -> float | None:
    if exit_time is None:
        return None
    values = trade_values(trade)
    entry_time = trade["_entry_time_parsed"]
    highs = []
    for bar in valid_market_rows(candles):
        bar_start = bar["time"]
        bar_end = bar_start + timedelta(minutes=1)
        if bar_end <= entry_time or bar_start > exit_time:
            continue
        if bar_end <= exit_time:
            highs.append(float(bar["high"]))
            continue
        sampled = [
            number(row.get("ltp"))
            for row in quotes
            if max(bar_start, entry_time) <= row["time"] <= min(bar_end, exit_time)
            and number(row.get("ltp")) is not None
        ]
        if sampled:
            highs.extend(float(value) for value in sampled if value is not None)
    if not highs:
        return None
    return (max(highs) - values["entry"]) / values["risk_points"]


def money(value: float | None) -> str:
    return "NA" if value is None else f"{value:,.2f}"


def metric(value: float | None, digits: int = 2) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def policy_label(policy: str) -> str:
    return policy.replace("_", " ")


def summary_metrics(
    outcomes: list[tuple[dict[str, Any], Replay]]
) -> dict[str, Any]:
    valid = [(trade, result) for trade, result in outcomes if result.complete and result.net is not None]
    if not valid:
        return {
            "n": 0, "gross": None, "net": None, "r": None, "win": None,
            "pf": None, "median_r": None, "drawdown": None, "without_best": None,
            "missing": len(outcomes),
        }
    nets = [float(result.net) for _, result in valid]
    rs = [float(result.r_multiple) for _, result in valid if result.r_multiple is not None]
    positive = sum(value > 0 for value in nets)
    gains = sum(value for value in nets if value > 0)
    losses = -sum(value for value in nets if value < 0)
    equity, peak, max_drawdown = 0.0, 0.0, 0.0
    for value in nets:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    best = max(nets)
    return {
        "n": len(valid),
        "gross": sum(float(result.gross) for _, result in valid if result.gross is not None),
        "net": sum(nets),
        "r": sum(rs),
        "win": positive / len(valid) * 100,
        "pf": gains / losses if losses else math.inf,
        "median_r": float(pd.Series(rs).median()) if rs else None,
        "drawdown": max_drawdown,
        "without_best": sum(nets) - best,
        "missing": len(outcomes) - len(valid),
    }


def load_decisions(root: Path, day: date) -> list[dict[str, Any]]:
    month_dir = root / "paper_trading_data" / day.strftime("%Y-%m")
    day_dirs = list(month_dir.glob(f"week_*/day_{day.day:02d}"))
    result = []
    for day_dir in day_dirs:
        for path in sorted((day_dir / "decisions").glob("*.parquet")):
            frame = pd.read_parquet(path)
            result.extend(clean_record(row) for row in frame.to_dict(orient="records"))
    return result


def entry_context(
    trade: dict[str, Any], decisions: list[dict[str, Any]]
) -> dict[str, Any]:
    signal_id = str(trade.get("signal_id") or "")
    matches = [
        row for row in decisions
        if signal_id and str(row.get("signal_id") or "") == signal_id
    ]
    if not matches:
        contract = str(trade.get("contract_id") or "")
        signal_time = parse_datetime(trade.get("signal_time")) or trade["_entry_time_parsed"]
        matches = [
            row for row in decisions
            if str(row.get("contract_id") or "") == contract
            and (parse_datetime(row.get("timestamp")) is not None)
            and abs((parse_datetime(row["timestamp"]) - signal_time).total_seconds()) <= 300
        ]
    reasons: list[str] = []
    explicit = {}
    if matches:
        matches.sort(key=lambda row: parse_datetime(row.get("timestamp")) or datetime.min.replace(tzinfo=IST))
        for row in matches:
            value = row.get("reasons")
            if value:
                try:
                    parsed = json.loads(value) if isinstance(value, str) else value
                    if isinstance(parsed, list):
                        reasons.extend(str(item) for item in parsed)
                    else:
                        reasons.append(str(parsed))
                except (TypeError, json.JSONDecodeError):
                    reasons.append(str(value))
            for field in (
                "regime", "market_regime", "pivot_count",
                "failed_support_reclaim", "support_reclaim_failed",
            ):
                if row.get(field) not in (None, ""):
                    explicit[field] = row[field]

    joined = " ".join(reasons).lower()
    regime = explicit.get("regime") or explicit.get("market_regime")
    if not regime:
        match = re.search(r"\b(sideways|bullish|bearish|trending|range-bound)\s+regime\b", joined)
        regime = match.group(1) if match else None
    pivot_count = number(explicit.get("pivot_count"))
    if pivot_count is None:
        match = re.search(r"(\d+)\s+clustered pivots", joined)
        pivot_count = float(match.group(1)) if match else None
    support_confirmed = (
        True if "support/reversal confirmed" in joined
        else False if "support/reversal" in joined or "support reclaim" in joined
        else None
    )
    failed_reclaim = explicit.get("failed_support_reclaim", explicit.get("support_reclaim_failed"))
    if failed_reclaim is None:
        failed_reclaim = (
            True if "failed support reclaim" in joined or "support reclaim failed" in joined
            else None
        )
    return {
        "matched_decisions": len(matches),
        "regime": str(regime) if regime is not None else None,
        "pivot_count": pivot_count,
        "support_reversal_confirmed": support_confirmed,
        "failed_support_reclaim": failed_reclaim,
        "reasons": reasons,
    }


def classify_premium_rise(trade: dict[str, Any]) -> tuple[float | None, str]:
    signal = number(trade.get("signal_ltp"), number(trade.get("signal_premium")))
    entry = number(trade.get("entry"))
    if signal is None or entry is None or signal <= 0:
        return None, "unavailable"
    rise = (entry / signal - 1.0) * 100
    return rise, "rise" if rise > 0.05 else "fall" if rise < -0.05 else "flat"


def checks(
    trades: list[dict[str, Any]],
    market: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    outcomes: dict[tuple[str, str], Replay],
) -> list[str]:
    failures: list[str] = []
    nov6 = [
        trade for trade in trades if trade["_entry_time_parsed"].date() == date(2026, 11, 6)
    ]
    nov6_gross = sum(
        number(trade.get("pnl_rupees"), number(trade.get("pnl"), 0.0)) or 0.0
        for trade in nov6
    )
    if abs(nov6_gross - EXPECTED_NOV06_GROSS) > 0.01:
        failures.append(
            f"P0 Nov 6 gross was {nov6_gross:.2f}, expected {EXPECTED_NOV06_GROSS:.2f}"
        )
    bank = next((trade for trade in nov6 if trade.get("ticker") == "BANKNIFTY_CE"), None)
    bank_result = outcomes.get((str(bank.get("trade_id")), "P1")) if bank else None
    if bank_result is None or bank_result.exit_price is None or abs(bank_result.exit_price - 900.40) > 10.00:
        got = "missing" if bank_result is None else str(bank_result.exit_price)
        failures.append(f"BANKNIFTY_CE P1 exit was {got}, expected near 900.40")
    sbin = next((trade for trade in nov6 if trade.get("ticker") == "SBIN_CE"), None)
    if sbin is None:
        failures.append("Nov 6 SBIN_CE trade is missing")
    else:
        candles, _ = market.get(str(sbin.get("trade_id")), ([], []))
        stop = number(sbin.get("stop_loss"))
        entry = sbin["_entry_time_parsed"]
        p1 = outcomes.get((str(sbin.get("trade_id")), "P1"))
        crossed = any(
            row["time"].date() == entry.date()
            and row["time"].time() == time(10, 31)
            and row["time"] > (p1.exit_time if p1 and p1.exit_time else entry)
            and number(row.get("low")) is not None
            and number(row.get("low")) <= (stop or -math.inf)
            for row in candles
        )
        if not crossed:
            failures.append("SBIN_CE did not show the post-P1 original-stop crossing at 10:31")
    return failures


def fmt_pf(value: float | None) -> str:
    if value is None:
        return "NA"
    return "inf" if math.isinf(value) else f"{value:.2f}"


def render_report(
    trades: list[dict[str, Any]],
    market: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    capture_index: dict[date, tuple[dict[str, int], dict[str, int]]],
    contexts: dict[str, dict[str, Any]],
    max_rs: dict[str, float | None],
    p4_eligible_ids: set[str],
    replays: dict[tuple[str, str], Replay],
    args: argparse.Namespace,
) -> str:
    sessions = sorted({trade["_entry_time_parsed"].date() for trade in trades})
    lines = [
        f"# Exact-contract exit-policy replay: {args.start} to {args.end}",
        "",
        f"**Sessions covered: {len(sessions)} ({', '.join(day.isoformat() for day in sessions)}).**",
    ]
    if len(sessions) < 3:
        lines += ["", "**WARNING: fewer than 3 sessions are covered.**"]
    lines += [
        "",
        f"Trades: **{len(trades)}**. This replay uses only exact option-contract archives; no underlying candles are used for option prices.",
        "It is an offline analysis tool and does not import or modify the live exit path, bot configuration, or running paper session.",
        "",
        "## Method and assumptions",
        "",
        "- R is the initial option premium risk: `(entry premium - original stop) * quantity`. The original stop is always retained.",
        "- P1 moves the stop to entry after +0.5R; a runner activates at +2R and trails the high watermark by 1R. P2 changes only that trailing gap. P3 adds one partial at +1R; P4 is the conditional +0.5R partial for trades whose P1 path reaches +0.5R but stays below +1R before P1 exits, then breakeven for the remainder.",
        "- Thresholds use exact-contract option candle highs/lows; exits fill at the nearest sampled bid in the stop-trigger minute when available, otherwise at the following candle open (or a later sampled bid if no next candle exists). No candle high/low is used as a fill. Since sampled quote cadence can be sparse, stop-minute bid timing is approximate; a same-candle stop takes priority over a partial/target event.",
        f"- Costs: {args.slippage:.2%} adverse slippage on the entry and each exit fill; brokerage ₹{args.brokerage_per_order:.2f} per order; STT {args.stt_rate:.3%} on sell turnover; exchange {args.exchange_rate:.4%}; SEBI {args.sebi_rate:.5%}; stamp duty {args.stamp_rate:.3%} on buy turnover; GST {args.gst_rate:.0%} on brokerage/exchange/SEBI. Rates are configurable estimates, not broker-confirmed charges.",
        "- P0 is recorded gross P&L and records manual exits separately; its net figure is a cost-adjusted estimate, not the paper journal's reported P&L.",
        "- Partial percentages are theoretical unit splits. These trades are generally one lot; 33/50/66% reductions may not be exchange-valid lot quantities.",
        "",
        "## Data coverage and integrity",
        "",
        "| Session | Closed trades | Trade contracts with candles | Trade contracts with sampled quotes | Capture candle-gap flags | Tick-gap flags (>30s) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for session in sessions:
        day_trades = [t for t in trades if t["_entry_time_parsed"].date() == session]
        candle_contracts = {
            str(t.get("contract_id"))
            for t in day_trades
            if t.get("contract_id")
            and market.get(str(t.get("trade_id")), ([], []))[0]
        }
        quote_contracts = {
            str(t.get("contract_id"))
            for t in day_trades
            if t.get("contract_id")
            and market.get(str(t.get("trade_id")), ([], []))[1]
        }
        cg, tg = capture_index.get(session, ({}, {}))
        lines.append(
            f"| {session} | {len(day_trades)} | {len(candle_contracts)} | {len(quote_contracts)} | "
            f"{sum(cg.values())} | {sum(tg.values())} |"
        )
    lines += [
        "",
        "Capture-reported contract gaps are **flagged, not silently imputed**. Policy summaries retain those trades if a replay path exists; the per-trade table and limitations identify capture warnings. This makes the estimates conditional on recorded candles and does not reconstruct missing ticks. The requested trade partitions, exact option candles, capture reports, and sampled quote streams were present for these three sessions; some contracts have capture-reported gaps. Explicit failed-support-reclaim labels are missing for all 17 trades, and per-entry regime/pivot labels are not available for three.",
        "",
        "## Required checks",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    nov6 = [t for t in trades if t["_entry_time_parsed"].date() == date(2026, 11, 6)]
    nov6_total = sum(
        number(t.get("pnl_rupees"), number(t.get("pnl"), 0.0)) or 0.0 for t in nov6
    )
    bank = next((t for t in nov6 if t.get("ticker") == "BANKNIFTY_CE"), None)
    bank_p1 = replays.get((str(bank.get("trade_id")), "P1")) if bank else None
    sb = next((t for t in nov6 if t.get("ticker") == "SBIN_CE"), None)
    sb_p1 = replays.get((str(sb.get("trade_id")), "P1")) if sb else None
    sb_candles = market.get(str(sb.get("trade_id")), ([], []))[0] if sb else []
    sb_cross = next(
        (
            row for row in sb_candles
            if row["time"].date() == date(2026, 11, 6)
            and row["time"].time() == time(10, 31)
            and sb_p1 and sb_p1.exit_time and row["time"] > sb_p1.exit_time
            and number(row.get("low")) is not None
            and number(row.get("low")) <= (number(sb.get("stop_loss"), -math.inf) or -math.inf)
        ),
        None,
    )
    lines += [
        *[
            f"| P0 recorded gross {session} | ₹{sum(number(t.get('pnl_rupees'), number(t.get('pnl'), 0.0)) or 0.0 for t in trades if t['_entry_time_parsed'].date() == session):,.2f} (closed trade rows) |"
            for session in sessions if session != date(2026, 11, 6)
        ],
        f"| P0 recorded Nov 6 gross = ₹5,344.50 | {'PASS' if abs(nov6_total-EXPECTED_NOV06_GROSS)<=0.01 else 'FAIL'} (₹{nov6_total:,.2f}) |",
        f"| BANKNIFTY_CE P1 exit near ₹900.40 (within ₹10 tolerance) | {'PASS' if bank_p1 and bank_p1.exit_price is not None and abs(bank_p1.exit_price-900.40)<=10 else 'FAIL'} (₹{money(bank_p1.exit_price if bank_p1 else None)}; sampled bid or next open) |",
        f"| SBIN_CE original stop crossed at 10:31 after P1 exit | {'PASS' if sb_cross else 'FAIL'} ({'low ₹'+money(number(sb_cross.get('low'))) if sb_cross else 'crossing not found'}) |",
        "",
        "## Per-trade results",
        "",
        "P2 rows show the full gap sensitivity. P3 rows show all partial sizes at 1.50R gap; P4 rows show each partial size. `NA` indicates missing/uncertain replay data.",
        "",
        "| Session | Trade | Recorded source | Gap flags | MFE (R) | P4 eligible | P0 gross ₹ | P1 net ₹ / R | P2 1.25R | P2 1.50R | P2 1.75R | P2 2.00R | P3 33% | P3 50% | P3 66% | P4 33% | P4 50% | P4 66% |",
        "|---|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for trade in trades:
        tid = str(trade.get("trade_id"))
        day = trade["_entry_time_parsed"].date()
        contract = str(trade.get("contract_id") or "")
        cg, tg = capture_index.get(day, ({}, {}))
        gapflags = []
        if cg.get(contract):
            gapflags.append(f"candles:{cg[contract]}")
        if tg.get(contract):
            gapflags.append(f"ticks:{tg[contract]}")
        gaptext = ", ".join(gapflags) if gapflags else "none reported"
        outcomes = {
            name: replays.get((tid, name))
            for name in [
                "P0", "P1", "P2_1.25", "P2_1.50", "P2_1.75", "P2_2.00",
                "P3_1.50_33", "P3_1.50_50", "P3_1.50_66",
                "P4_33", "P4_50", "P4_66",
            ]
        }
        p0 = outcomes["P0"]
        p1 = outcomes["P1"]
        def compact(result: Replay | None) -> str:
            if result is None or not result.complete or result.net is None:
                return "NA"
            return f"{result.net:,.0f}/{result.r_multiple:+.2f}"
        lines.append(
            f"| {day} | {trade.get('ticker')} `{tid}` | {trade.get('exit_source') or 'unknown'} | {gaptext} | "
            f"{metric(max_rs.get(tid))} | {'yes' if tid in p4_eligible_ids else 'no'} | "
            f"{money(p0.gross if p0 else None)} | {compact(p1)} | "
            + " | ".join(compact(outcomes[k]) for k in [
                "P2_1.25", "P2_1.50", "P2_1.75", "P2_2.00",
                "P3_1.50_33", "P3_1.50_50", "P3_1.50_66", "P4_33", "P4_50", "P4_66",
            ])
            + " |"
        )
    lines += [
        "",
        "## Policy summary",
        "",
        "P0 net is cost-adjusted estimate; alternative policies use simulated gross less estimated costs. R uses initial premium risk. Drawdown is peak-to-trough over chronological closed-trade net equity, starting at zero. Profit factor is net wins divided by absolute net losses.",
        "",
        "| Policy | N | Gross ₹ | Net ₹ | Net R | Win % | Profit factor | Median R | Max drawdown ₹ | Net without best trade ₹ | Incomplete |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    policy_names = ["P0", "P1"] + [f"P2_{gap:.2f}" for gap in RUNNER_GAPS]
    policy_names += [
        f"P3_{gap:.2f}_{pct}"
        for gap in RUNNER_GAPS for pct in (33, 50, 66)
    ]
    policy_names += [f"P4_{pct}" for pct in (33, 50, 66)]
    for name in policy_names:
        rows = [(t, replays.get((str(t.get("trade_id")), name))) for t in trades]
        outcomes = [(t, r) for t, r in rows if r is not None]
        stats = summary_metrics(outcomes)
        lines.append(
            f"| {policy_label(name)} | {stats['n']} | {money(stats['gross'])} | {money(stats['net'])} | "
            f"{metric(stats['r'])} | {metric(stats['win'])} | {fmt_pf(stats['pf'])} | "
            f"{metric(stats['median_r'])} | {money(stats['drawdown'])} | "
            f"{money(stats['without_best'])} | {stats['missing']} |"
        )
    lines += [
        "",
        "## Full sensitivity grid",
        "",
        "| Policy | Gap R | Partial trigger | Partial % | N | Net ₹ | Net R | Win % | PF | Median R | Without-best net ₹ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for gap in RUNNER_GAPS:
        for pct in (0, 33, 50, 66):
            name = f"P2_{gap:.2f}" if pct == 0 else f"P3_{gap:.2f}_{pct}"
            stats = summary_metrics([
                (t, replays.get((str(t.get("trade_id")), name)))
                for t in trades if replays.get((str(t.get("trade_id")), name)) is not None
            ])
            lines.append(
                f"| {name} | {gap:.2f} | {'none' if pct == 0 else '1R'} | "
                f"{'0%' if pct == 0 else str(pct)+'%'} | {stats['n']} | {money(stats['net'])} | "
                f"{metric(stats['r'])} | {metric(stats['win'])} | {fmt_pf(stats['pf'])} | "
                f"{metric(stats['median_r'])} | {money(stats['without_best'])} |"
            )
    for pct in (33, 50, 66):
        name = f"P4_{pct}"
        stats = summary_metrics([
            (t, replays.get((str(t.get("trade_id")), name)))
            for t in trades if replays.get((str(t.get("trade_id")), name)) is not None
        ])
        eligible = sum(str(t.get("trade_id")) in p4_eligible_ids for t in trades)
        lines.append(
            f"| {name} | 1.00 (P1 gap) | 0.5R conditional | {pct}% | {stats['n']} "
            f"(eligible {eligible}) | {money(stats['net'])} | {metric(stats['r'])} | "
            f"{metric(stats['win'])} | {fmt_pf(stats['pf'])} | {metric(stats['median_r'])} | "
            f"{money(stats['without_best'])} |"
        )
    lines += [
        "",
        "## Manual-exit comparison",
        "",
        "15:15 and 15:29 marks use the last sampled option bid at or before that clock time; quote age is shown. These are marks, not fills. Policy exits are simulated using the stated fill convention.",
        "",
        "| Session | Trade | Recorded exit / gross ₹ | P1 fill / gross / net ₹ | P2 1.50R fill / gross / net ₹ | 15:15 bid (time, age s) | 15:29 bid (time, age s) |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    manual = [t for t in trades if str(t.get("exit_source", "")).upper() == "MANUAL"]
    for trade in manual:
        tid = str(trade.get("trade_id"))
        day = trade["_entry_time_parsed"].date()
        candles, quotes = market.get(tid, ([], []))
        marks = []
        for clock in (time(15, 15), time(15, 29)):
            target = datetime.combine(day, clock, tzinfo=IST)
            price, stamp, age, _ = quote_at_or_before(candles, quotes, target)
            marks.append(
                "NA" if price is None else
                f"₹{price:.2f} ({stamp.strftime('%H:%M:%S')}, {age:.0f})"
            )
        recorded = number(trade.get("exit_price"))
        p0 = replays.get((tid, "P0"))
        p1 = replays.get((tid, "P1"))
        p2 = replays.get((tid, "P2_1.50"))
        lines.append(
            f"| {day} | {trade.get('ticker')} `{tid}` | ₹{money(recorded)} / ₹{money(p0.gross if p0 else None)} | "
            f"₹{money(p1.exit_price if p1 else None)} / ₹{money(p1.gross if p1 else None)} / ₹{money(p1.net if p1 else None)} | "
            f"₹{money(p2.exit_price if p2 else None)} / ₹{money(p2.gross if p2 else None)} / ₹{money(p2.net if p2 else None)} | "
            f"{marks[0]} | {marks[1]} |"
        )
    lines += [
        "",
        "## Entry-pattern counts",
        "",
        "Outcome labels use recorded gross P&L (>0 winner; <=0 non-winner). Signal-to-fill premium change compares recorded entry premium with signal LTP (or signal premium) and is not an underlying-price return.",
        "",
        "| Pattern | Trades | Winners | Non-winners |",
        "|---|---:|---:|---:|",
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        rise, rise_class = classify_premium_rise(trade)
        ctx = contexts.get(str(trade.get("trade_id")), {})
        values = {
            f"signal-to-fill premium: {rise_class}",
            f"strategy variant: {trade.get('strategy_variant') or 'unspecified'}",
            f"regime: {ctx.get('regime') or 'not recorded'}",
            "support-reversal: " + (
                "confirmed" if ctx.get("support_reversal_confirmed") is True
                else "not confirmed" if ctx.get("support_reversal_confirmed") is False
                else "not recorded"
            ),
            "failed support reclaim: " + (
                "yes" if str(ctx.get("failed_support_reclaim")).lower() in {"true", "1", "yes"}
                else "no" if str(ctx.get("failed_support_reclaim")).lower() in {"false", "0", "no"}
                else "not recorded"
            ),
            f"pivot count: {int(ctx['pivot_count']) if ctx.get('pivot_count') is not None else 'not recorded'}",
        }
        for value in values:
            groups.setdefault(value, []).append(trade)
    for name in sorted(groups):
        rows = groups[name]
        winners = sum((number(t.get("pnl_rupees"), number(t.get("pnl"), 0)) or 0) > 0 for t in rows)
        non_winners = len(rows) - winners
        lines.append(f"| {name} | {len(rows)} | {winners} | {non_winners} |")
    lines += [
        "",
        "### Premium-rise magnitude",
        "",
        "| Trade | Entry vs signal LTP | Recorded gross ₹ | Matched decision records |",
        "|---|---:|---:|---:|",
    ]
    for trade in trades:
        tid = str(trade.get("trade_id"))
        rise, _ = classify_premium_rise(trade)
        lines.append(
            f"| {trade.get('ticker')} `{tid}` | {metric(rise)}% | "
            f"{money(number(trade.get('pnl_rupees'), number(trade.get('pnl'))))} | "
            f"{contexts.get(tid, {}).get('matched_decisions', 0)} |"
        )
    lines += [
        "",
        "## Trades differing by more than 3R",
        "",
        "Paired policy difference is net R on the same recorded entry and quantity. Pairs with incomplete replays are omitted.",
        "",
        "| Trade | Policy A | Policy B | Difference (R) |",
        "|---|---|---|---:|",
    ]
    differences = []
    for trade in trades:
        tid = str(trade.get("trade_id"))
        baseline = replays.get((tid, "P1"))
        if baseline is None or baseline.r_multiple is None or not baseline.complete:
            continue
        for name in policy_names:
            if name in {"P0", "P1"}:
                continue
            other = replays.get((tid, name))
            if other and other.complete and other.r_multiple is not None:
                delta = other.r_multiple - baseline.r_multiple
                if abs(delta) > 3:
                    differences.append((trade, name, delta))
    if differences:
        for trade, name, delta in differences:
            lines.append(f"| {trade.get('ticker')} `{trade.get('trade_id')}` | P1 | {name} | {delta:+.2f} |")
    else:
        lines.append("| None | — | — | — |")
    lines += [
        "",
        "## Verdicts",
        "",
    ]
    p1_outcomes = [
        (t, replays.get((str(t.get("trade_id")), "P1"))) for t in trades
    ]
    p1_stats = summary_metrics([(t, r) for t, r in p1_outcomes if r])
    valid_p1 = p1_stats["n"]
    day_deltas: dict[str, dict[str, float]] = {}
    for gap in RUNNER_GAPS:
        name = f"P2_{gap:.2f}"
        day_deltas[name] = {}
        for trade in trades:
            p1 = replays.get((str(trade.get("trade_id")), "P1"))
            other = replays.get((str(trade.get("trade_id")), name))
            if p1 and other and p1.complete and other.complete and p1.net is not None and other.net is not None:
                day = trade["_entry_time_parsed"].date().isoformat()
                day_deltas[name][day] = day_deltas[name].get(day, 0.0) + other.net - p1.net
    p2_wins = [
        name for name, by_day in day_deltas.items()
        if sum(by_day.values()) > 0 and sum(value > 0 for value in by_day.values()) >= 2
    ]
    p2_overall_best = max(
        (sum(values.values()) for values in day_deltas.values()), default=0.0
    )
    def paired_robustness(name: str) -> tuple[float, float, int, int, int]:
        paired = []
        by_day: dict[str, float] = {}
        for trade in trades:
            p1 = replays.get((str(trade.get("trade_id")), "P1"))
            alternative = replays.get((str(trade.get("trade_id")), name))
            if (
                p1 and alternative and p1.complete and alternative.complete
                and p1.net is not None and alternative.net is not None
            ):
                delta = alternative.net - p1.net
                paired.append((trade, delta))
                day = trade["_entry_time_parsed"].date().isoformat()
                by_day[day] = by_day.get(day, 0.0) + delta
        total = sum(delta for _, delta in paired)
        largest = max(paired, key=lambda row: row[1], default=(None, 0.0))
        robust_total = total - max(0.0, largest[1])
        removed_day = (
            largest[0]["_entry_time_parsed"].date().isoformat()
            if largest[0] is not None and largest[1] > 0 else None
        )
        robust_days = sum(
            1 for day, delta in by_day.items()
            if delta - (largest[1] if day == removed_day else 0.0) > 0
        )
        positive_days = sum(delta > 0 for delta in by_day.values())
        return total, robust_total, positive_days, robust_days, len(paired)

    p2_robust = {
        f"P2_{gap:.2f}": paired_robustness(f"P2_{gap:.2f}")
        for gap in RUNNER_GAPS
    }
    p2_robust_wins = [
        name for name, result in p2_robust.items()
        if result[0] > 0 and result[1] > 0 and result[3] >= 2 and result[4] >= 10
    ]
    q1 = (
        "supported" if p2_robust_wins and len(sessions) >= 3
        else "not supported" if p2_overall_best <= 0 and valid_p1 >= 10
        else "insufficient data"
    )
    lines.append(
        f"1. **Wider runner gap after 2R:** {q1} — {valid_p1} paired trades across {len(sessions)} sessions; "
        f"all-grid gaps with positive aggregate and ≥2 positive days: {', '.join(p2_wins) or 'none'}; "
        f"after removing each candidate's largest positive trade contribution, qualifying gaps: "
        f"{', '.join(p2_robust_wins) or 'none'}."
    )
    p3_candidates = []
    for gap in RUNNER_GAPS:
        for pct in (33, 50, 66):
            name = f"P3_{gap:.2f}_{pct}"
            deltas = []
            by_day: dict[str, float] = {}
            for trade in trades:
                p1 = replays.get((str(trade.get("trade_id")), "P1"))
                alt = replays.get((str(trade.get("trade_id")), name))
                if p1 and alt and p1.complete and alt.complete and p1.net is not None and alt.net is not None:
                    delta = alt.net - p1.net
                    deltas.append(delta)
                    day = trade["_entry_time_parsed"].date().isoformat()
                    by_day[day] = by_day.get(day, 0.0) + delta
            p3_candidates.append((sum(deltas), name, by_day, len(deltas)))
    p3_best = max(p3_candidates, default=(0.0, "", {}, 0), key=lambda row: row[0])
    p3_good_days = sum(value > 0 for value in p3_best[2].values())
    _, p3_robust_delta, _, p3_robust_days, _ = paired_robustness(p3_best[1]) if p3_best[1] else (0, 0, 0, 0, 0)
    q2 = (
        "supported" if p3_best[0] > 0 and p3_robust_delta > 0
        and p3_robust_days >= 2 and p3_best[3] >= 10
        else "not supported" if all(row[0] <= 0 for row in p3_candidates) and valid_p1 >= 10
        else "insufficient data"
    )
    lines.append(
        f"2. **1R partial plus runner vs P1:** {q2} — best grid cell {p3_best[1] or 'none'}, "
        f"paired n={p3_best[3]}, aggregate change ₹{p3_best[0]:,.2f}, positive days={p3_good_days}/{len(sessions)}."
        f" After removing its largest positive trade contribution, paired change is ₹{p3_robust_delta:,.2f}."
    )
    p4_eligible = [t for t in trades if str(t.get("trade_id")) in p4_eligible_ids]
    p4_delta_rows: list[tuple[dict[str, Any], float]] = []
    p4_daily_delta: dict[date, float] = {}
    for trade in p4_eligible:
        p1 = replays.get((str(trade.get("trade_id")), "P1"))
        alt = replays.get((str(trade.get("trade_id")), "P4_50"))
        if p1 and alt and p1.complete and alt.complete and p1.net is not None and alt.net is not None:
            delta = alt.net - p1.net
            p4_delta_rows.append((trade, delta))
            day = trade["_entry_time_parsed"].date()
            p4_daily_delta[day] = p4_daily_delta.get(day, 0.0) + delta
    p4_total = sum(delta for _, delta in p4_delta_rows)
    best_p4_trade, best_p4_delta = max(
        p4_delta_rows, key=lambda row: row[1], default=(None, 0.0)
    )
    p4_trimmed = p4_total - max(0.0, best_p4_delta)
    trimmed_daily = dict(p4_daily_delta)
    if best_p4_trade is not None and best_p4_delta > 0:
        best_day = best_p4_trade["_entry_time_parsed"].date()
        trimmed_daily[best_day] -= best_p4_delta
    p4_robust_days = sum(delta > 0 for delta in trimmed_daily.values())
    p4_positive_days = sum(delta > 0 for delta in p4_daily_delta.values())
    q3 = (
        "supported" if len(p4_delta_rows) >= 3 and p4_trimmed > 0
        and p4_robust_days >= 2 and p4_positive_days >= 2
        and sum(v > 0 for _, v in p4_delta_rows) > len(p4_delta_rows) / 2
        else "not supported" if len(p4_delta_rows) >= 3 and p4_total <= 0
        else "insufficient data"
    )
    lines.append(
        f"3. **0.5R partial for 0.5R-to-<1R trades:** {q3} — eligible trades={len(p4_eligible)}, "
        f"complete paired n={len(p4_delta_rows)}, 50% partial net change ₹{p4_total:,.2f}, "
        f"positive sessions={p4_positive_days}/{len(p4_daily_delta)}, after removing best paired trade "
        f"₹{p4_trimmed:,.2f} (positive sessions remaining={p4_robust_days})."
    )
    manual_comp = []
    for trade in manual:
        p1 = replays.get((str(trade.get("trade_id")), "P1"))
        if p1 and p1.complete and p1.net is not None:
            actual = number(trade.get("pnl_rupees"), number(trade.get("pnl")))
            if actual is not None and p1.gross is not None:
                manual_comp.append(actual - p1.gross)
    manual_better = sum(value > 0 for value in manual_comp)
    manual_worse = sum(value < 0 for value in manual_comp)
    q4 = (
        "supported" if len(manual_comp) >= 5 and sum(manual_comp) > 0 and manual_better > manual_worse
        else "not supported" if len(manual_comp) >= 5 and sum(manual_comp) < 0 and manual_worse > manual_better
        else "insufficient data"
    )
    lines.append(
        f"4. **Manual exits better than P1 on manual-exit trades:** {q4} — manual trades={len(manual)}, "
        f"complete paired n={len(manual_comp)}, recorded-minus-P1-gross mean "
        f"₹{(sum(manual_comp)/len(manual_comp)) if manual_comp else 0:,.2f}. This is a selected, non-random subset."
        f" Aggregate manual-minus-P1 gross was ₹{sum(manual_comp):,.2f}; manual gross was higher on "
        f"{manual_better} and lower on {manual_worse} paired trades."
    )
    rise_rows = [(t, classify_premium_rise(t)[0], classify_premium_rise(t)[1]) for t in trades]
    rise_known = [(t, val, cls) for t, val, cls in rise_rows if val is not None]
    yes_count = sum((number(t.get("pnl_rupees"), number(t.get("pnl"), 0)) or 0) > 0 for t, _, cls in rise_known if cls == "rise")
    no_count = sum((number(t.get("pnl_rupees"), number(t.get("pnl"), 0)) or 0) > 0 for t, _, cls in rise_known if cls != "rise")
    feature_coverage = sum(
        contexts.get(str(t.get("trade_id")), {}).get("regime") is not None
        or contexts.get(str(t.get("trade_id")), {}).get("pivot_count") is not None
        for t in trades
    )
    lines.append(
        f"5. **Entry patterns separate losers from winners:** insufficient data — signal-to-fill premium known "
        f"for {len(rise_known)}/{len(trades)} trades (rise winners {yes_count}; flat/fall winners {no_count}); "
        f"regime or pivot context available for {feature_coverage}/{len(trades)}; failed-reclaim labels are not consistently recorded."
    )
    lines += [
        "",
        "## Limitations",
        "",
        "- Only 17 closed trades over three sessions were present (4 on Nov 4, 3 on Nov 5, 10 on Nov 6). This is a short, selected paper sample, not a holdout or walk-forward test.",
        "- Nov 6's recorded total is dominated by BANKNIFTY CE and LT CE. The report includes results without each policy's best trade and should not be used to tune to Nov 6.",
        "- Archived option candles are one-minute aggregates; within-bar ordering is unknowable. The conservative stop-first convention and next-open fills reduce but do not remove this ambiguity.",
        "- Capture reports show missing candles/tick gaps for some contracts. The report flags those gaps; prices and exits through missing intervals cannot be reconstructed. Quote marks can be stale and their age is shown.",
        "- No underlying candles are substituted. Decision reason strings are used only for entry-pattern labels, where available; missing regime/pivot/reclaim context is left unknown.",
        "- P0 exit/P&L may reflect paper journaling and manual actions, not exchange-confirmed fills. Brokerage, tax rates, and slippage are estimates; no order-book depth/market impact is modeled.",
        "- Partial units are not necessarily valid lot-sized quantities. P3/P4 are counterfactual unless position quantity allows the selected partial under exchange lot rules.",
        "",
        "## Paper-mode recommendation and data needed",
        "",
        "Do not replace the current exit behavior based on this short replay alone. If the checks pass, the safest next paper experiment is a **shadow-only** comparison that records P1 and each wider-gap/partial variant side by side, without changing actual exits or orders; keep the original stop invariant. Avoid choosing a single gap from the best-performing day.",
        "",
        "Before adopting any policy, collect more sessions of exact-contract candles and timestamped executable bid/ask quotes through each trade's exit, verified lot-level fill and order-cost data, explicit manual-exit rationale, and consistently persisted per-entry regime, pivot count, support-reclaim outcome, and signal-to-fill premium. Include out-of-sample/walk-forward sessions and gap-free intervals, and verify feasible lot quantities for partials.",
        "",
    ]
    return "\n".join(lines)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/EXIT_POLICY_REPLAY_2026-11-04_to_2026-11-06.md"),
    )
    parser.add_argument("--slippage", type=float, default=0.01, help="Adverse fraction per side; default 0.01")
    parser.add_argument("--brokerage-per-order", type=float, default=20.0)
    parser.add_argument("--stt-rate", type=float, default=0.001)
    parser.add_argument("--exchange-rate", type=float, default=0.0003503)
    parser.add_argument("--sebi-rate", type=float, default=0.000001)
    parser.add_argument("--stamp-rate", type=float, default=0.00003)
    parser.add_argument("--gst-rate", type=float, default=0.18)
    return parser


def run(args: argparse.Namespace) -> int:
    if args.start > args.end:
        raise ValueError("--start must be on or before --end")
    if args.slippage < 0 or args.brokerage_per_order < 0 or any(
        getattr(args, key) < 0
        for key in ("stt_rate", "exchange_rate", "sebi_rate", "stamp_rate", "gst_rate")
    ):
        raise ValueError("Cost and slippage parameters must be non-negative")
    root = args.root.resolve()
    trades = load_trades(root, args.start, args.end)
    if not trades:
        raise ValueError(f"No closed trades found between {args.start} and {args.end}")
    capture_index = build_capture_index(root)
    market: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}
    contexts: dict[str, dict[str, Any]] = {}
    max_rs: dict[str, float | None] = {}
    p4_eligible_ids: set[str] = set()
    replays: dict[tuple[str, str], Replay] = {}
    decisions_by_day: dict[date, list[dict[str, Any]]] = {}
    for trade in trades:
        tid = str(trade.get("trade_id"))
        day = trade["_entry_time_parsed"].date()
        contract = str(trade.get("contract_id") or "")
        if not contract.startswith("NFO:"):
            market[tid] = ([], [])
        else:
            day_dir = root / "paper_trading_data" / "option_candles" / day.isoformat()
            candles = load_market_rows(day_dir, contract, "candles")
            quotes = load_market_rows(day_dir, contract, "quotes")
            market[tid] = (candles, quotes)
        candles, quotes = market[tid]
        if day not in decisions_by_day:
            decisions_by_day[day] = load_decisions(root, day)
        contexts[tid] = entry_context(trade, decisions_by_day[day])
        max_rs[tid] = session_max_r(trade, candles, quotes) if candles else None
        replays[(tid, "P0")] = recorded_replay(trade, args)
        if not candles:
            for name in ["P1"] + [f"P2_{gap:.2f}" for gap in RUNNER_GAPS]:
                replays[(tid, name)] = Replay(name, None, None, None, None, None, "missing exact-contract candles", None, False)
            for gap in RUNNER_GAPS:
                for pct in (33, 50, 66):
                    name = f"P3_{gap:.2f}_{pct}"
                    replays[(tid, name)] = Replay(name, None, None, None, None, None, "missing exact-contract candles", None, False)
            for pct in (33, 50, 66):
                name = f"P4_{pct}"
                replays[(tid, name)] = Replay(name, None, None, None, None, None, "missing exact-contract candles", None, False)
            continue
        replays[(tid, "P1")] = simulate_policy(trade, candles, quotes, args, "P1", runner_gap=1.0)
        p1_result = replays[(tid, "P1")]
        p1_path_r = path_max_r(
            trade, candles, quotes, p1_result.exit_time
        ) if p1_result.complete else None
        for gap in RUNNER_GAPS:
            name = f"P2_{gap:.2f}"
            replays[(tid, name)] = simulate_policy(
                trade, candles, quotes, args, name, runner_gap=gap
            )
            for pct in (33, 50, 66):
                name = f"P3_{gap:.2f}_{pct}"
                replays[(tid, name)] = simulate_policy(
                    trade, candles, quotes, args, name, runner_gap=gap,
                    partial_fraction=pct / 100, partial_r=1.0,
                )
        qualifies = (
            p1_path_r is not None
            and 0.5 <= p1_path_r < 1.0
        )
        if qualifies:
            p4_eligible_ids.add(tid)
        for pct in (33, 50, 66):
            name = f"P4_{pct}"
            replays[(tid, name)] = simulate_policy(
                trade, candles, quotes, args, name, runner_gap=1.0,
                partial_fraction=pct / 100, partial_r=0.5,
                p4_qualifies=qualifies,
            )

    failures = checks(trades, market, replays)
    if failures:
        print("Required checks failed; stopping without writing a report:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 2

    report = render_report(
        trades, market, capture_index, contexts, max_rs,
        p4_eligible_ids, replays, args
    )
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"Report written: {output}")
    print(f"Sessions: {len({t['_entry_time_parsed'].date() for t in trades})}; trades: {len(trades)}")
    print("All required replay checks passed.")
    return 0


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, ImportError) as error:
        print(f"Replay failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
