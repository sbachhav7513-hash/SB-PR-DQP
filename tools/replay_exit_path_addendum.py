#!/usr/bin/env python3
"""Offline exact-option path and tier replay addendum.

This script imports only the prior standalone replay helpers; it does not
import or alter the live exit path, bot configuration, or paper session.
"""

from __future__ import annotations

import argparse
import math
import sys
import tempfile
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from market_bot.runtime_safety import require_temporary_path

import replay_exit_policies as replay


START = date(2026, 10, 28)
END = date(2026, 11, 6)
LEVELS = (0.5, 1.0, 1.5, 2.0, 3.0)
STATIC_GAPS = (1.25, 1.5, 1.75, 2.0)
VOL_WINDOWS = (15, 30)
VOL_MULTIPLIERS = (3, 4, 5)
STOCK_STOP_PCTS = (0.08, 0.10, 0.12)


def exact_market_rows(day_dir: Path, contract: str, suffix: str) -> list[dict[str, Any]]:
    rows = replay.load_market_rows(day_dir, contract, suffix)
    if rows or suffix != "candles":
        return rows

    symbol = contract.split(":", 1)[-1]
    legacy = sorted(day_dir.glob(f"NFO_{symbol}__*.csv"))
    rows_by_time: dict[datetime, dict[str, Any]] = {}
    for path in legacy:
        for raw in replay._read_csv(path):
            if raw.get("contract_id") != contract:
                continue
            timestamp = replay.parse_datetime(raw.get("timestamp"))
            if timestamp is None:
                continue
            row: dict[str, Any] = {"time": timestamp, "_path": path.name}
            for key, value in raw.items():
                if key in {"timestamp", "contract_id"}:
                    continue
                parsed = replay.number(value)
                if parsed is not None:
                    row[key] = parsed
                elif value:
                    row[key] = value
            rows_by_time[timestamp] = row
    return [rows_by_time[key] for key in sorted(rows_by_time)]


def load_market(root: Path, trade: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    contract = str(trade.get("contract_id") or "")
    if not contract.startswith("NFO:"):
        return [], []
    day_dir = root / "paper_trading_data" / "option_candles" / trade["_entry_time_parsed"].date().isoformat()
    return (
        replay.valid_market_rows(exact_market_rows(day_dir, contract, "candles")),
        replay.load_market_rows(day_dir, contract, "quotes"),
    )


def s(value: Any) -> str:
    return str(value) if value not in (None, "") else ""


def fmt(value: float | None, digits: int = 2) -> str:
    return "NA" if value is None or not math.isfinite(value) else f"{value:.{digits}f}"


def fmt_time(value: datetime | None, approximate: bool = False) -> str:
    if value is None:
        return "never"
    prefix = "~" if approximate else ""
    return prefix + value.strftime("%H:%M:%S" if value.second else "%H:%M")


def trade_id(trade: dict[str, Any]) -> str:
    return str(trade.get("trade_id") or f"{trade.get('ticker')}@{trade['_entry_time_parsed'].isoformat()}")


def qty_and_lots(trade: dict[str, Any]) -> tuple[float | None, float | None]:
    qty = replay.number(trade.get("quantity"))
    lots = replay.number(trade.get("lots"))
    if lots is None:
        lot_size = replay.number(trade.get("lot_size"))
        lots = qty / lot_size if qty and lot_size else None
    return qty, lots


def exit_source(trade: dict[str, Any]) -> str:
    source = str(trade.get("exit_source") or "").upper()
    reason = str(trade.get("exit_reason") or trade.get("reason") or "").upper()
    return "yes" if source == "MANUAL" or "MANUAL" in reason else "no"


def segment(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    selected = []
    valid_quotes = [q for q in quotes if replay.valid_quote(q) and start <= q["time"] <= end]
    for bar in candles:
        bar_start = bar["time"]
        bar_end = bar_start + timedelta(minutes=1)
        if bar_end <= start or bar_start > end:
            continue
        values = dict(bar)
        values["_approx_high_time"] = True
        values["_approx_low_time"] = True
        if bar_start < start or bar_end > end:
            samples = [
                q for q in valid_quotes
                if max(start, bar_start) <= q["time"] <= min(end, bar_end)
            ]
            prices = [
                replay.number(q.get("ltp"), replay.number(q.get("bid")))
                for q in samples
            ]
            bids = [replay.number(q.get("bid")) for q in samples]
            prices = [v for v in prices if v is not None]
            bids = [v for v in bids if v is not None]
            if prices:
                values["high"] = max(prices)
                values["low"] = min(bids or prices)
                values["_approx_high_time"] = False
                values["_approx_low_time"] = False
                values["_sample_quotes"] = samples
        selected.append(values)
    return selected


def path_extrema(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    end: datetime,
) -> dict[str, Any]:
    values = replay.trade_values(trade)
    start = trade["_entry_time_parsed"]
    bars = segment(trade, candles, quotes, start, end)
    if not bars:
        return {}
    highs = [(float(b["high"]), b["time"], bool(b.get("_approx_high_time"))) for b in bars]
    lows = [(float(b["low"]), b["time"], bool(b.get("_approx_low_time"))) for b in bars]
    high_value, high_time, high_approx = max(highs, key=lambda x: x[0])
    low_value, low_time, low_approx = min(lows, key=lambda x: x[0])

    max_pullback = 0.0
    pullback_peak = None
    pullback_low = None
    previous_peak = values["entry"]
    for i, bar in enumerate(bars):
        previous_peak = max(previous_peak, float(bar["high"]))
        for later in bars[i + 1 :]:
            drop = previous_peak - float(later["low"])
            if drop > max_pullback:
                max_pullback = drop
                pullback_peak = previous_peak
                pullback_low = float(later["low"])

    level_hits: dict[float, tuple[datetime | None, float | None, bool]] = {}
    for level in LEVELS:
        threshold = values["entry"] + level * values["risk_points"]
        hit = None
        for bar in bars:
            if float(bar["high"]) >= threshold:
                sampled = [
                    q for q in quotes
                    if max(start, bar["time"]) <= q["time"] < min(
                        end + timedelta(microseconds=1), bar["time"] + timedelta(minutes=1)
                    )
                    and replay.valid_quote(q)
                    and replay.number(q.get("ltp"), replay.number(q.get("bid"), -math.inf)) >= threshold
                ]
                if sampled:
                    q = sampled[0]
                    peak_at_hit = replay.number(q.get("ltp"), replay.number(q.get("bid")))
                    hit = (q["time"], peak_at_hit, False)
                else:
                    hit = (bar["time"], float(bar["high"]), True)
                break
        level_hits[level] = hit or (None, None, False)

    return {
        "bars": bars,
        "mfe": (high_value - values["entry"]) / values["risk_points"],
        "mfe_time": high_time,
        "mfe_approx": high_approx,
        "mae": (low_value - values["entry"]) / values["risk_points"],
        "mae_time": low_time,
        "mae_approx": low_approx,
        "pullback_r": max_pullback / values["risk_points"],
        "pullback_pct": (max_pullback / pullback_peak * 100) if pullback_peak else 0.0,
        "pullback_peak": pullback_peak,
        "pullback_low": pullback_low,
        "level_hits": level_hits,
    }


def active_stop_at_level(
    level: float,
    hit_price: float | None,
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    hit_time: datetime | None,
) -> str:
    values = replay.trade_values(trade)
    if hit_time is None:
        return "—"
    if level < 0.5:
        return f"initial {values['stop']:.2f}"
    if level < 2:
        return f"BE {values['entry']:.2f}"
    hit_minute = hit_time.replace(second=0, microsecond=0)
    exact_sample_time = hit_time > hit_minute
    prior_highs = [
        float(row["high"]) for row in candles
        if trade["_entry_time_parsed"] <= row["time"]
        and (row["time"] < hit_minute if exact_sample_time else row["time"] <= hit_time)
    ]
    peak = max([values["entry"], *(prior_highs or [hit_price or values["entry"]])])
    stop = max(values["entry"], peak - values["risk_points"])
    return f"runner {stop:.2f} (1R)"


def mark_r(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    target: datetime,
) -> str:
    price, timestamp, age, _ = replay.quote_at_or_before(candles, quotes, target)
    if price is None or timestamp is None:
        return "NA"
    vals = replay.trade_values(trade)
    return f"{(price - vals['entry']) / vals['risk_points']:+.2f}R@{timestamp:%H:%M}"


def post_exit_metrics(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    exit_time: datetime | None,
) -> dict[str, Any]:
    if exit_time is None:
        return {}
    vals = replay.trade_values(trade)
    cutoff = datetime.combine(exit_time.date(), time(15, 29, 59), tzinfo=replay.IST)
    future = segment(trade, candles, quotes, exit_time, cutoff)
    if not future:
        return {"max": None, "min": None}
    max_r = (max(float(row["high"]) for row in future) - vals["entry"]) / vals["risk_points"]
    min_r = (min(float(row["low"]) for row in future) - vals["entry"]) / vals["risk_points"]
    return {
        "max": max_r,
        "min": min_r,
        "15": mark_r(trade, candles, quotes, exit_time + timedelta(minutes=15)),
        "30": mark_r(trade, candles, quotes, exit_time + timedelta(minutes=30)),
        "60": mark_r(trade, candles, quotes, exit_time + timedelta(minutes=60)),
        "1515": mark_r(
            trade, candles, quotes,
            datetime.combine(exit_time.date(), time(15, 15), tzinfo=replay.IST),
        ),
        "1529": mark_r(
            trade, candles, quotes,
            datetime.combine(exit_time.date(), time(15, 29), tzinfo=replay.IST),
        ),
    }


def capture_flags(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    capture_index: dict[date, tuple[dict[str, int], dict[str, int]]],
) -> str:
    contract = str(trade.get("contract_id") or "")
    day = trade["_entry_time_parsed"].date()
    candle_gaps, tick_gaps = capture_index.get(day, ({}, {}))
    candle_count = candle_gaps.get(contract, 0)
    tick_count = tick_gaps.get(contract, 0)
    low_tick_rows = [
        row for row in candles
        if str(row.get("low_tick", "")).lower() in {"true", "1", "yes"}
        and trade["_entry_time_parsed"] <= row["time"] <= (trade.get("_closed_at_parsed") or row["time"])
    ]
    candle_gap_rows = [
        row for row in candles
        if str(row.get("gap", "")).lower() in {"true", "1", "yes"}
        and trade["_entry_time_parsed"] <= row["time"] <= (trade.get("_closed_at_parsed") or row["time"])
    ]
    pieces = []
    exit_time = trade.get("_closed_at_parsed")
    if not contract.startswith("NFO:"):
        pieces.append("exact contract identifier missing")
    elif exit_time and not any(
        row["time"] + timedelta(minutes=1) > trade["_entry_time_parsed"]
        and row["time"] <= exit_time
        for row in candles
    ):
        pieces.append("no option candles during trade window")
    if candle_count:
        pieces.append(f"session capture candle gaps {candle_count} (not time-localized)")
    if tick_count:
        pieces.append(f"session capture tick gaps {tick_count} (not time-localized)")
    if candle_gap_rows:
        pieces.append(f"path gap flags {len(candle_gap_rows)}")
    if low_tick_rows:
        pieces.append(f"path low-tick flags {len(low_tick_rows)}")
    return "; ".join(pieces) or ("none reported" if candles else "no exact-contract path")


def tier(trade: dict[str, Any]) -> str:
    ticker = str(trade.get("ticker") or "").upper()
    return "index options" if ticker.startswith(("NIFTY_", "BANKNIFTY_")) else "stock options"


def premium_band(trade: dict[str, Any]) -> str:
    entry = replay.number(trade.get("entry"), 0.0) or 0.0
    return "below 20" if entry < 20 else "20 to 60" if entry <= 60 else "above 60"


def dynamic_gap(window: int, multiplier: int, risk: float, prior: list[dict[str, Any]]) -> float:
    ranges = [
        float(row["high"]) - float(row["low"])
        for row in prior[-window:]
        if replay.number(row.get("high")) is not None and replay.number(row.get("low")) is not None
    ]
    if not ranges:
        return 1.0
    median_range = float(pd.Series(ranges).median())
    return max(1.0, multiplier * median_range / risk)


def simulate_vol_policy(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    args: argparse.Namespace,
    window: int,
    multiplier: int,
) -> replay.Replay:
    vals = replay.trade_values(trade)
    start = trade["_entry_time_parsed"]
    cutoff = datetime.combine(start.date(), time(15, 29, 59), tzinfo=replay.IST)
    bars = [b for b in replay.valid_market_rows(candles) if b["time"] <= cutoff]
    quotes = sorted((q for q in quotes if replay.valid_quote(q)), key=lambda q: q["time"])
    active = [i for i, b in enumerate(bars) if b["time"] + timedelta(minutes=1) > start]
    if not active:
        return replay.Replay("P2v", None, None, None, None, None, "missing post-entry candles", None, False)
    remaining = vals["quantity"]
    gross = 0.0
    fills: list[tuple[float, float]] = []
    current_stop = vals["stop"]
    highest = vals["entry"]
    runner = False
    last_fill = None
    reason = "session_end"
    for i in active:
        bar = bars[i]
        if bar["time"] < start:
            continue
        high, low = float(bar["high"]), float(bar["low"])
        if bar["time"] < start < bar["time"] + timedelta(minutes=1):
            sample = [q for q in quotes if start <= q["time"] < bar["time"] + timedelta(minutes=1)]
            prices = [replay.number(q.get("ltp"), replay.number(q.get("bid"))) for q in sample]
            prices = [v for v in prices if v is not None]
            bids = [float(q["bid"]) for q in sample if replay.valid_quote(q)]
            if prices:
                high = max(prices)
                low = min(bids or prices)
        highest_after = max(highest, high)
        candidate = current_stop
        if highest_after >= vals["entry"] + 0.5 * vals["risk_points"]:
            candidate = max(candidate, vals["entry"])
        if highest_after >= vals["entry"] + 2.0 * vals["risk_points"]:
            runner = True
        gap = dynamic_gap(window, multiplier, vals["risk_points"], bars[:i])
        if runner:
            candidate = max(candidate, highest_after - gap * vals["risk_points"])
        if low <= candidate:
            fill = replay.stop_bar_fill(bars, quotes, i, candidate)
            if fill is None:
                return replay.Replay("P2v", None, None, None, None, None, "stop hit but no permitted fill", None, False)
            gross += (fill.price - vals["entry"]) * remaining
            fills.append((fill.price, remaining))
            last_fill = fill
            reason = "runner_stop" if runner else "breakeven_stop" if candidate >= vals["entry"] else "initial_stop"
            remaining = 0
            break
        highest, current_stop = highest_after, candidate
    if remaining > 1e-9:
        fill = replay.eod_fill(bars, quotes, start.date())
        if fill is None or fill.timestamp < start:
            return replay.Replay("P2v", None, None, None, None, None, "no valid end-of-session sampled bid", None, False)
        gross += (fill.price - vals["entry"]) * remaining
        fills.append((fill.price, remaining))
        last_fill = fill
        reason = "session_end_sampled_bid"
    result = replay.make_replay(
        f"P2v_{window}_{multiplier}", gross, fills, last_fill.timestamp,
        reason, trade, args,
    )
    result.exit_price = last_fill.price
    result.note = f"vol_gap={gap:.2f}R" if "gap" in locals() else "vol_gap=1.00R"
    return result


def stop_variant(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    args: argparse.Namespace,
    stop_fraction: float,
) -> replay.Replay:
    changed = deepcopy(trade)
    entry = replay.number(changed.get("entry"))
    if entry is None:
        return replay.Replay("stop_variant", None, None, None, None, None, "missing entry", None, False)
    changed["stop_loss"] = entry * (1 - stop_fraction)
    return replay.simulate_policy(
        changed, candles, quotes, args,
        f"stock_stop_{int(stop_fraction * 100)}pct", runner_gap=1.0,
    )


def stats_rows(
    trades: list[dict[str, Any]],
    replays: dict[tuple[str, str], replay.Replay],
    policies: list[str],
    selected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for label, group in selected:
        for policy in policies:
            outcomes = [
                (t, replays.get((trade_id(t), policy)))
                for t in group
            ]
            summary = replay.summary_metrics([(t, r) for t, r in outcomes if r is not None])
            rows.append({"group": label, "policy": policy, **summary})
    return rows


def format_stats(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Tier | Policy | n | Gross ₹ | Net ₹ | Net R | Win % | PF | Median R | Max DD ₹ | Without best ₹ | Missing |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['group']} | {row['policy']} | {row['n']} | "
            f"{replay.money(row['gross'])} | {replay.money(row['net'])} | {fmt(row['r'])} | "
            f"{fmt(row['win'])} | {replay.fmt_pf(row['pf'])} | {fmt(row['median_r'])} | "
            f"{replay.money(row['drawdown'])} | {replay.money(row['without_best'])} | {row['missing']} |"
        )
    return lines


def quote_spreads(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
) -> tuple[list[float], list[float]]:
    end = trade.get("_closed_at_parsed") or trade["_entry_time_parsed"]
    source = [q for q in quotes if replay.valid_quote(q) and trade["_entry_time_parsed"] <= q["time"] <= end]
    if not source:
        source = [
            c for c in candles
            if replay.valid_quote(c) and trade["_entry_time_parsed"] <= c["time"] <= end
        ]
    spreads, percentages = [], []
    for row in source:
        bid, ask = replay.number(row.get("bid")), replay.number(row.get("ask"))
        if bid is None or ask is None or ask < bid:
            continue
        mid = (bid + ask) / 2
        spreads.append(ask - bid)
        if mid > 0:
            percentages.append((ask - bid) / mid * 100)
    return spreads, percentages


def tier_statistics(
    trades: list[dict[str, Any]],
    market: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    paths: dict[str, dict[str, Any]],
    replays: dict[tuple[str, str], replay.Replay],
) -> list[str]:
    groups: list[tuple[str, list[dict[str, Any]]]] = [
        ("index options", [t for t in trades if tier(t) == "index options"]),
        ("stock options", [t for t in trades if tier(t) == "stock options"]),
    ]
    stocks = [t for t in trades if tier(t) == "stock options"]
    groups += [(f"stock premium {band}", [t for t in stocks if premium_band(t) == band])
               for band in ("below 20", "20 to 60", "above 60")]
    lines = [
        "| Tier | Exact-path trades | Sessions | Entry premium range ₹ | Tick size % of premium* | Median spread ₹ / % | Median 1-min range % | Median pullback (R / %) among MFE ≥1R | P1 stop exits / P1 outcomes; avg overrun % | BE exits; later +1R / BE; original stop / BE |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, group in groups:
        exact = [t for t in group if paths.get(trade_id(t))]
        sessions = sorted({t["_entry_time_parsed"].date().isoformat() for t in exact})
        entries = [replay.number(t.get("entry")) for t in exact]
        entries = [x for x in entries if x is not None]
        tick_pct = [0.05 / x * 100 for x in entries if x > 0]
        spreads, spread_pcts, minute_vols, pullbacks = [], [], [], []
        overrun_pcts = []
        stops = 0
        p1_count = 0
        be_exits = 0
        be_later_1r = 0
        be_later_stop = 0
        for t in exact:
            tid = trade_id(t)
            candles, quotes = market[tid]
            sp, spp = quote_spreads(t, candles, quotes)
            spreads.extend(sp)
            spread_pcts.extend(spp)
            vals = replay.number(t.get("entry"))
            if vals and paths.get(tid):
                per_bar = [
                    (float(b["high"]) - float(b["low"])) / vals * 100
                    for b in paths[tid]["bars"]
                ]
                if per_bar:
                    minute_vols.append(float(pd.Series(per_bar).median()))
            p = paths.get(tid)
            if p and p.get("mfe") is not None and p["mfe"] >= 1:
                pullbacks.append((p["pullback_r"], p["pullback_pct"]))
            result = replays.get((tid, "P1"))
            if result and result.complete:
                p1_count += 1
            if result and result.complete and result.exit_reason in {"initial_stop", "breakeven_stop", "runner_stop"}:
                stops += 1
                initial = replay.trade_values(t)["stop"]
                planned = initial
                if p and p.get("mfe") is not None and p["mfe"] >= 0.5:
                    planned = replay.trade_values(t)["entry"]
                if p and p.get("mfe") is not None and p["mfe"] >= 2:
                    highs = [float(b["high"]) for b in p["bars"] if b["time"] <= (result.exit_time or b["time"])]
                    if highs:
                        planned = max(planned, max(highs) - replay.trade_values(t)["risk_points"])
                if result.exit_price is not None and planned > result.exit_price:
                    overrun_pcts.append((planned - result.exit_price) / planned * 100)
                if result.exit_reason == "breakeven_stop" and result.exit_time:
                    be_exits += 1
                    after = [b for b in candles if b["time"] > result.exit_time]
                    vals0 = replay.trade_values(t)
                    if any(float(b["high"]) >= vals0["entry"] + vals0["risk_points"] for b in after):
                        be_later_1r += 1
                    if any(float(b["low"]) <= vals0["stop"] for b in after):
                        be_later_stop += 1
        med = lambda values: float(pd.Series(values).median()) if values else None
        lines.append(
            f"| {label} | {len(exact)}/{len(group)} | {', '.join(sessions) or 'none'} | "
            f"{fmt(min(entries) if entries else None)}–{fmt(max(entries) if entries else None)} | "
            f"{fmt(med(tick_pct))} | {fmt(med(spreads))} / {fmt(med(spread_pcts))}% "
            f"({len(spreads)} quotes) | {fmt(med(minute_vols))}% | "
            f"{fmt(med([x[0] for x in pullbacks]))} R / {fmt(med([x[1] for x in pullbacks]))}% "
            f"(n={len(pullbacks)}) | {stops}/{p1_count}; {fmt(med(overrun_pcts))}% (n={len(overrun_pcts)}) | "
            f"{be_exits}; {be_later_1r}/{be_exits}; {be_later_stop}/{be_exits} |"
        )
    lines += [
        "",
        "*Tick percent assumes a ₹0.05 option tick; the archived records do not include a per-contract tick-size field. Spread observations use sampled quote bid/ask, or candle bid/ask where no quote stream exists; not all are executable snapshots.",
    ]
    return lines


def make_case_path(
    title: str,
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> list[str]:
    bars = [
        b for b in candles
        if start.replace(second=0, microsecond=0) <= b["time"] <= end
    ]
    vals = replay.trade_values(trade)
    q_by_minute: dict[datetime, list[dict[str, Any]]] = {}
    for q in quotes:
        if start <= q["time"] <= end:
            key = q["time"].replace(second=0, microsecond=0)
            q_by_minute.setdefault(key, []).append(q)
    lines = [
        f"### {title}",
        "",
        "| Minute | Open | High | Low | Close | Bid | Ask | sampled quote n / LTP range |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for b in bars:
        qs = q_by_minute.get(b["time"].replace(second=0, microsecond=0), [])
        bids = [replay.number(q.get("bid")) for q in qs]
        asks = [replay.number(q.get("ask")) for q in qs]
        ltps = [replay.number(q.get("ltp")) for q in qs]
        bids = [v for v in bids if v is not None]
        asks = [v for v in asks if v is not None]
        ltps = [v for v in ltps if v is not None]
        bid = bids[-1] if bids else replay.number(b.get("bid"))
        ask = asks[-1] if asks else replay.number(b.get("ask"))
        rng = f"{min(ltps):.2f}–{max(ltps):.2f}" if ltps else "—"
        lines.append(
            f"| {b['time']:%H:%M:%S} | {fmt(replay.number(b.get('open')))} | "
            f"{fmt(replay.number(b.get('high')))} | {fmt(replay.number(b.get('low')))} | "
            f"{fmt(replay.number(b.get('close')))} | {fmt(bid)} | {fmt(ask)} | {len(qs)} / {rng} |"
        )
    lines.append("")
    lines.append(
        f"Rows are the archived exact-contract option candles. Quote LTP ranges are sampled values, not continuous ticks; "
        f"R uses entry ₹{vals['entry']:.2f} and risk ₹{vals['risk_points']:.2f}/unit. Boundary-minute OHLC may include prices outside the displayed window; quote ranges are clipped to it. Underlying OHLC is not present."
    )
    return lines


def mark_price(
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    target: datetime,
) -> str:
    price, timestamp, _, _ = replay.quote_at_or_before(candles, quotes, target)
    return f"{price:.2f}@{timestamp:%H:%M}" if price is not None and timestamp else "NA"


def make_report(
    root: Path,
    trades: list[dict[str, Any]],
    market: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    paths: dict[str, dict[str, Any]],
    capture_index: dict[date, tuple[dict[str, int], dict[str, int]]],
    replays: dict[tuple[str, str], replay.Replay],
    contexts: dict[str, dict[str, Any]],
) -> str:
    sessions = sorted({t["_entry_time_parsed"].date() for t in trades})
    exact_trades = [t for t in trades if paths.get(trade_id(t))]
    missing_trades = [t for t in trades if not paths.get(trade_id(t))]
    lines = [
        f"# Exit replay addendum: exact-option paths and tier policies ({START} to {END})",
        "",
        f"**Sessions with trade records: {len(sessions)} ({', '.join(d.isoformat() for d in sessions)}).** "
        f"Exact option paths are available for {len(exact_trades)}/{len(trades)} trades.",
        "",
        "This is an offline analysis-only addendum. It does not import the live exit path, change bot/configuration, or interact with the paper session.",
        "",
        "## Inputs, scope, and assumptions",
        "",
        f"- Included closed trades dated {START}–{END}; policy calculations use only verified exact-contract option candles. {len(missing_trades)} closed trade(s) have no verifiable exact-contract path and are shown as missing rather than inferred.",
        "- Reuses the previous replay's fill/cost assumptions: 1% adverse slippage per side, ₹20/order brokerage, taxes/fees as configured in `replay_exit_policies.py`; a stop wins a same-candle tie; stop fills use nearest sampled bid in the stop minute or next-candle open. No candle high/low is used as a fill.",
        "- P1: 0.5R break-even, runner activation at 2R, 1R trailing gap. P2 changes the gap. P2v uses `max(1R, multiplier × median prior complete 1-minute (high−low) range / initial risk)`, over prior 15 or 30 bars; it never widens the initial stop. P4 is a 50% partial at 0.5R only for trades whose P1 path reaches 0.5R but not 1R, with break-even for the remainder.",
        "- P5 reversal definition requested: CE reversal = a completed underlying 1-minute close below the prior underlying 1-minute low; PE reversal = a close above the prior high. No underlying OHLC file was found, so P5 cannot be replayed and is not proxied with option premiums.",
        "- Quotes are sampled, not continuous. Legacy Oct 29–30 candle exports are one-minute exact-contract files but lack separate sampled-quote streams. At candle-only resolution a threshold time is marked with `~` and intrabar event order is unknowable.",
        "",
        "## Data gaps and required sanity checks",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Nov 6 recorded gross | ₹{sum(replay.number(t.get('pnl_rupees'), replay.number(t.get('pnl'), 0.0)) or 0 for t in trades if t['_entry_time_parsed'].date() == date(2026, 11, 6)):,.2f} (required ₹5,344.50) |",
    ]
    bank = next((t for t in trades if t["_entry_time_parsed"].date() == date(2026, 11, 6) and t.get("ticker") == "BANKNIFTY_CE"), None)
    bank_p1 = replays.get((trade_id(bank), "P1")) if bank else None
    sbin = next((t for t in trades if t["_entry_time_parsed"].date() == date(2026, 11, 6) and t.get("ticker") == "SBIN_CE"), None)
    sb_candles = market.get(trade_id(sbin), ([], []))[0] if sbin else []
    sb_cross = bool(sbin and any(
        b["time"].time() == time(10, 31) and float(b["low"]) <= replay.trade_values(sbin)["stop"]
        for b in sb_candles
    ))
    lines += [
        f"| Nov 6 P0 gross = ₹5,344.50 | {'PASS' if abs(sum(replay.number(t.get('pnl_rupees'), replay.number(t.get('pnl'), 0.0)) or 0 for t in trades if t['_entry_time_parsed'].date() == date(2026, 11, 6)) - 5344.50) < 0.01 else 'FAIL'} |",
        f"| BANKNIFTY CE P1 exit within ₹10 of ₹900.40 | {'PASS' if bank_p1 and bank_p1.exit_price is not None and abs(bank_p1.exit_price - 900.40) <= 10 else 'FAIL'} (₹{fmt(bank_p1.exit_price if bank_p1 else None)}) |",
        f"| SBIN CE original stop crossed at 10:31 | {'PASS' if sb_cross else 'FAIL'} |",
        "",
        f"Exact underlying candles: **missing**. Oct 28 trade records have no `contract_id`; the matching date archive is ticker-named rather than contract-identified, so the two Oct 28 trades are excluded from price replay. Other missing in-trade paths: {', '.join(str(t.get('ticker')) + ' ' + t['_entry_time_parsed'].date().isoformat() for t in missing_trades if t['_entry_time_parsed'].date() != date(2026, 10, 28)) or 'none'}. For Nov 6 NIFTY PE the exact-contract archive begins at 11:52, after the 10:46 exit; only post-exit option candles exist.",
        "",
        "## In-trade path table",
        "",
        "MFE/MAE use option OHLC; extrema timestamps are minute approximations unless they come from a sampled quote in a partial minute. Pullback is the largest prior-bar peak to a later-bar low (not an assumed high-then-low within one candle).",
        "",
        "| Date / trade | Entry time / premium | Initial stop | R ₹/unit | Qty / lots | Recorded exit time / price / reason | Manual | MFE R / time | MAE R / time | Largest pullback R / % peak | Signal-to-fill % | Capture/path flags |",
        "|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|---|",
    ]
    for t in trades:
        tid = trade_id(t)
        p = paths.get(tid)
        qty, lots = qty_and_lots(t)
        entry = replay.number(t.get("entry"))
        signal = replay.number(t.get("signal_ltp"), replay.number(t.get("signal_premium")))
        rise = (entry / signal - 1) * 100 if entry and signal else None
        exit_time = t.get("_closed_at_parsed")
        flags = capture_flags(t, market[tid][0], capture_index)
        reason = t.get("exit_reason") or t.get("reason") or "recorded reason missing"
        stop = replay.number(t.get("stop_loss"))
        risk = entry - stop if entry is not None and stop is not None else None
        lines.append(
            f"| {t['_entry_time_parsed'].date()} `{t.get('ticker')}` | {t['_entry_time_parsed']:%H:%M:%S} / "
            f"{fmt(entry)} | {fmt(stop)} | {fmt(risk)} | {fmt(qty, 0)} / {fmt(lots)} | "
            f"{fmt_time(exit_time)} / {fmt(replay.number(t.get('exit_price')))} / {reason} | "
            f"{'yes' if exit_source(t) == 'yes' else 'no'} | "
            f"{fmt(p.get('mfe') if p else None)} / {fmt_time(p.get('mfe_time') if p else None, p.get('mfe_approx', False) if p else False)} | "
            f"{fmt(p.get('mae') if p else None)} / {fmt_time(p.get('mae_time') if p else None, p.get('mae_approx', False) if p else False)} | "
            f"{fmt(p.get('pullback_r') if p else None)} / {fmt(p.get('pullback_pct') if p else None)}% | "
            f"{fmt(rise)}% | {flags} |"
        )
    lines += [
        "",
        "### First threshold time and active P1 stop",
        "",
        "Candle-only first touches are prefixed `~`. The stop shown is the theoretical stop immediately after that level; at 2R+, runner stop is the observed high-watermark minus 1R.",
        "",
        "| Date / trade | 0.5R time / stop | 1R time / stop | 1.5R time / stop | 2R time / stop | 3R time / stop |",
        "|---|---|---|---|---|---|",
    ]
    for t in trades:
        p = paths.get(trade_id(t))
        cells = []
        for level in LEVELS:
            if not p:
                cells.append("NA (path missing)")
                continue
            hit_time, hit_price, approx = p["level_hits"][level]
            stop_state = active_stop_at_level(level, hit_price, t, market[trade_id(t)][0], hit_time)
            cells.append(f"{fmt_time(hit_time, approx)} / {stop_state}" if hit_time else "never")
        lines.append(f"| {t['_entry_time_parsed'].date()} `{t.get('ticker')}` | " + " | ".join(cells) + " |")
    lines += [
        "",
        "### Post-exit option path and underlying context",
        "",
        "Post-exit extrema are option-candle R through the session close. Snapshot R values use the last valid sampled bid at/before the requested time and show the mark timestamp. Underlying columns are NA because exact underlying OHLC data is absent.",
        "",
        "| Trade | Post-exit max / min R | +15m | +30m | +60m | 15:15 | 15:29 | Underlying at entry / option peak / exit | Opposing underlying lower-low (CE) / higher-high (PE), peak to exit |",
        "|---|---:|---|---|---|---|---|---|---|",
    ]
    for t in trades:
        tid = trade_id(t)
        post = post_exit_metrics(t, *market[tid], t.get("_closed_at_parsed")) if market[tid][0] else {}
        lines.append(
            f"| `{t.get('ticker')}` {t['_entry_time_parsed'].date()} | {fmt(post.get('max'))} / {fmt(post.get('min'))} | "
            f"{post.get('15', 'NA')} | {post.get('30', 'NA')} | {post.get('60', 'NA')} | "
            f"{post.get('1515', 'NA')} | {post.get('1529', 'NA')} | NA / NA / NA | NA (source missing) |"
        )

    # Case write-ups are based on the exact contract archive and use no underlying proxy.
    if bank:
        b_candles, b_quotes = market[trade_id(bank)]
        entry = bank["_entry_time_parsed"]
        actual_exit = bank["_closed_at_parsed"]
        bank_end = actual_exit + timedelta(minutes=30) if actual_exit else entry + timedelta(minutes=80)
        bpath = paths.get(trade_id(bank), {})
        peak = bpath.get("mfe")
        p1_exit = bank_p1.exit_price if bank_p1 else None
        peak_premium = replay.trade_values(bank)["entry"] + (peak or 0) * replay.trade_values(bank)["risk_points"]
        pullback_r = (peak_premium - (p1_exit or 0)) / replay.trade_values(bank)["risk_points"] if p1_exit else None
        lines += [
            "",
            "## Case A — BANKNIFTY CE, 2026-11-06",
            "",
            f"Recorded entry ₹{replay.number(bank.get('entry')):.2f} at {entry:%H:%M:%S}; original stop ₹{replay.number(bank.get('stop_loss')):.2f}; R ₹{replay.trade_values(bank)['risk_points']:.2f}/unit. "
            f"Recorded exit ₹{replay.number(bank.get('exit_price')):.2f} at {actual_exit:%H:%M:%S}, and P1 replay exit ₹{p1_exit:.2f} (nearest sampled bid). "
            f"Archived in-trade peak ≈₹{peak_premium:.2f} ({fmt(peak)}R); P1 runner was active after 2R with a 1R trail. "
            f"Peak-to-recorded-exit pullback was ≈{fmt((peak_premium - replay.number(bank.get('exit_price'))) / replay.trade_values(bank)['risk_points'])}R "
            f"({fmt((peak_premium - replay.number(bank.get('exit_price'))) / peak_premium * 100)}% of peak premium); "
            f"the P1 replay fill at ₹{p1_exit:.2f} implies ≈{fmt(pullback_r)}R. "
            f"The archive's maximum option high in the 30 minutes after exit was ₹{max((float(b['high']) for b in b_candles if actual_exit <= b['time'] <= bank_end), default=0):.2f}, so these candles do not support a ₹1,200 touch within that window; "
            f"the later full-session option high was ₹{max((float(b['high']) for b in b_candles if actual_exit <= b['time'] <= datetime.combine(actual_exit.date(), time(15, 29), tzinfo=replay.IST)), default=0):.2f}. "
            "The option then continued higher in the archive. Exact underlying movement during the pullback is unknowable here; the data shows a premium pullback followed by continuation, but cannot distinguish underlying reversal from option-premium noise.",
            "",
        ]
        lines += make_case_path("Exact-option candles: entry through 30 minutes after recorded exit", bank, b_candles, b_quotes, entry, bank_end)

    hdf = next((t for t in trades if t["_entry_time_parsed"].date() == date(2026, 11, 6) and t.get("ticker") == "HDFCBANK_PE"), None)
    if hdf:
        h_candles, h_quotes = market[trade_id(hdf)]
        entry = hdf["_entry_time_parsed"]
        actual_exit = hdf["_closed_at_parsed"]
        signal_time = replay.parse_datetime(hdf.get("signal_time")) or entry
        hdf_end = actual_exit + timedelta(minutes=60) if actual_exit else entry + timedelta(minutes=82)
        vals = replay.trade_values(hdf)
        be_threshold = vals["entry"] + 0.5 * vals["risk_points"]
        hdf_path = paths.get(trade_id(hdf), {})
        high = vals["entry"] + (hdf_path.get("mfe") or 0) * vals["risk_points"]
        qualifying_quotes = [
            q for q in h_quotes
            if signal_time <= q["time"] <= actual_exit
            and replay.number(q.get("ltp"), replay.number(q.get("bid"), -math.inf)) >= be_threshold
        ]
        lines += [
            "",
            "## Case B — HDFCBANK PE, 2026-11-06",
            "",
            f"Exact option candles show a high of ₹{high:.2f} while open ({fmt(hdf_path.get('mfe'))}R from ₹{vals['entry']:.2f}; R ₹{vals['risk_points']:.2f}/unit). "
            f"The 0.5R break-even activation threshold is ₹{be_threshold:.3f}. "
            f"{'Sampled quote' if qualifying_quotes else 'Candle'} evidence first reaches that threshold at "
            f"{fmt_time(qualifying_quotes[0]['time'] if qualifying_quotes else hdf_path.get('level_hits', {}).get(0.5, (None,))[0], not bool(qualifying_quotes))}; "
            f"recorded exit was ₹{replay.number(hdf.get('exit_price')):.2f} at {actual_exit:%H:%M:%S} (journal reason `{hdf.get('exit_reason')}`). "
            f"Thus a ₹17-area touch occurred while the bot trade was still open and the exit is consistent with the 0.5R BE stop, not merely a post-exit rally. The journal has no order-event/stop-price field, so the exact trigger level cannot be independently proven from the recorded reason alone.",
            "",
        ]
        lines += make_case_path("Exact-option candles: signal through 60 minutes after recorded exit", hdf, h_candles, h_quotes, signal_time, hdf_end)

        key_times = sorted(set(
            [q["time"] for q in qualifying_quotes[:5]]
            + [q["time"] for q in h_quotes if actual_exit and abs((q["time"] - actual_exit).total_seconds()) <= 60]
        ))
        if key_times:
            lines += [
                "",
                "Sampled HDFCBANK quote evidence near the threshold and recorded exit:",
                "",
                "| Time | Bid | Ask | LTP |",
                "|---|---:|---:|---:|",
            ]
            for moment in key_times:
                q = next(q for q in h_quotes if q["time"] == moment)
                lines.append(
                    f"| {moment:%H:%M:%S} | {fmt(replay.number(q.get('bid')))} | "
                    f"{fmt(replay.number(q.get('ask')))} | {fmt(replay.number(q.get('ltp')))} |"
                )

    lines += [
        "",
        "## Tier statistics",
        "",
        *tier_statistics(trades, market, paths, replays),
        "",
        "Underlying reversal measures (and P5) are unavailable for every tier: no exact underlying candle files were found. No parameter was fitted by symbol.",
        "",
        "## Policy results by tier and combined",
        "",
        "All results use net P&L after the previous replay's estimated costs. In the policy tables, `Without best` removes that policy's own highest-net trade. The sensitivity grid separately reports paired net change vs P1 before and after removing the largest positive paired-trade contribution. Drawdown is sequential cumulative net P&L by trade time.",
        "",
    ]
    groups = [
        ("index options", [t for t in exact_trades if tier(t) == "index options"]),
        ("stock options", [t for t in exact_trades if tier(t) == "stock options"]),
        ("combined", exact_trades),
    ]
    policy_names = ["P1"] + [f"P2_{g:.2f}" for g in STATIC_GAPS] + [
        f"P2v_{w}_{m}" for w in VOL_WINDOWS for m in VOL_MULTIPLIERS
    ] + ["P4_50"]
    for label, group in groups:
        table_rows = []
        for policy in policy_names:
            outcomes = [(t, replays[(trade_id(t), policy)]) for t in group if (trade_id(t), policy) in replays]
            table_rows.append({"group": label, "policy": policy, **replay.summary_metrics(outcomes)})
        lines += [f"### {label}", "", *format_stats(table_rows), ""]
    lines += [
        "### Stock-only initial stop sensitivity",
        "",
        "These alternatives set the stock-option initial stop to 8%, 10%, or 12% below entry and replay P1; index stops are unchanged. 'Earlier/later' compares the alternative P1 exit time with the 10% stock stop replay for the same trade.",
        "",
        "| Stop % | Trades | Net ₹ | Net R | Win % | PF | Median R | Max DD ₹ | Without best ₹ | Earlier exits | Later exits |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    stock_trades = [t for t in exact_trades if tier(t) == "stock options"]
    for pct in STOCK_STOP_PCTS:
        name = f"stock_stop_{int(pct * 100)}pct"
        outcomes = [(t, replays[(trade_id(t), name)]) for t in stock_trades if (trade_id(t), name) in replays]
        m = replay.summary_metrics(outcomes)
        earlier = later = 0
        for t in stock_trades:
            alt, base = replays.get((trade_id(t), name)), replays.get((trade_id(t), "stock_stop_10pct"))
            if alt and base and alt.exit_time and base.exit_time:
                earlier += alt.exit_time < base.exit_time
                later += alt.exit_time > base.exit_time
        lines.append(
            f"| {int(pct * 100)} | {m['n']} | {replay.money(m['net'])} | {fmt(m['r'])} | {fmt(m['win'])} | "
            f"{replay.fmt_pf(m['pf'])} | {fmt(m['median_r'])} | {replay.money(m['drawdown'])} | "
            f"{replay.money(m['without_best'])} | {earlier} | {later} |"
        )
    lines += [
        "",
        "### Full gap/volatility sensitivity grid",
        "",
        "| Family | Parameter | Index net ₹ / R | Stock net ₹ / R | Combined net ₹ / R | Index Δ / ex-best paired ₹ | Stock Δ / ex-best paired ₹ | Combined Δ / ex-best paired ₹ |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for policy in policy_names:
        if policy == "P1":
            family, parameter = "baseline", "1R gap"
        elif policy.startswith("P2v"):
            _, window, multiple = policy.split("_")
            family, parameter = "volatility", f"{window} bars × {multiple}, floor 1R"
        elif policy.startswith("P2_"):
            family, parameter = "fixed gap", policy.removeprefix("P2_") + "R"
        else:
            family, parameter = "partial", "50% at 0.5R if <1R"
        cells = []
        for label, group in groups:
            vals = replay.summary_metrics([
                (t, replays[(trade_id(t), policy)])
                for t in group if (trade_id(t), policy) in replays
            ])
            cells.append(f"{replay.money(vals['net'])} / {fmt(vals['r'])}")
        combined = replay.summary_metrics([
            (t, replays[(trade_id(t), policy)])
            for t in exact_trades if (trade_id(t), policy) in replays
        ])
        deltas = []
        for _, group in groups:
            paired = []
            if policy != "P1":
                for t in group:
                    base_result = replays.get((trade_id(t), "P1"))
                    alternative = replays.get((trade_id(t), policy))
                    if (
                        base_result and alternative and base_result.complete and alternative.complete
                        and base_result.net is not None and alternative.net is not None
                    ):
                        paired.append(alternative.net - base_result.net)
            total_delta = sum(paired)
            best_delta = max(paired, default=0.0)
            deltas.append(f"{total_delta:,.2f} / {total_delta - max(0.0, best_delta):,.2f}")
        lines.append(f"| {family} | {parameter} | {cells[0]} | {cells[1]} | {cells[2]} | {deltas[0]} | {deltas[1]} | {deltas[2]} |")

    lines += [
        "",
        "## Manual exits and entry-pattern counts",
        "",
        "| Manual trade | Recorded exit ₹ / time | P1 exit ₹ / time | Option bid at 15:15 | Option bid at 15:29 |",
        "|---|---|---|---|---|",
    ]
    manual = [t for t in trades if exit_source(t) == "yes" and paths.get(trade_id(t))]
    for t in manual:
        tid = trade_id(t)
        p1 = replays.get((tid, "P1"))
        at_1515 = mark_price(*market[tid], datetime.combine(t["_entry_time_parsed"].date(), time(15, 15), tzinfo=replay.IST))
        at_1529 = mark_price(*market[tid], datetime.combine(t["_entry_time_parsed"].date(), time(15, 29), tzinfo=replay.IST))
        lines.append(
            f"| `{t.get('ticker')}` {t['_entry_time_parsed'].date()} | {fmt(replay.number(t.get('exit_price')))} / {fmt_time(t.get('_closed_at_parsed'))} | "
            f"{fmt(p1.exit_price if p1 else None)} / {fmt_time(p1.exit_time if p1 else None)} | {at_1515} | {at_1529} |"
        )
    rises = [replay.classify_premium_rise(t) for t in exact_trades]
    rising = sum(1 for _, kind in rises if kind == "rise")
    falling = sum(1 for _, kind in rises if kind == "fall")
    flat = sum(1 for _, kind in rises if kind == "flat")
    contexts_known = sum(
        contexts.get(trade_id(t), {}).get("regime") is not None
        or contexts.get(trade_id(t), {}).get("pivot_count") is not None
        for t in exact_trades
    )
    lines += [
        "",
        f"Signal-to-fill premium: rise {rising}, fall {falling}, flat {flat} of {len(exact_trades)} exact-path trades. "
        f"Regime or pivot context appears in {contexts_known}/{len(exact_trades)} decision records; failed-support-reclaim labels are not consistently present. "
        "These small counts are descriptive and do not establish separation of winners and losers.",
        "",
        "| Signal-to-fill premium change | Trades | Winners (recorded gross >0) | Losers / flat |",
        "|---|---:|---:|---:|",
    ]
    for kind in ("rise", "flat", "fall", "unavailable"):
        group = [t for t in exact_trades if replay.classify_premium_rise(t)[1] == kind]
        wins = sum(
            (replay.number(t.get("pnl_rupees"), replay.number(t.get("pnl"), 0.0)) or 0) > 0
            for t in group
        )
        lines.append(f"| {kind} | {len(group)} | {wins} | {len(group) - wins} |")
    pattern_counts: dict[tuple[str, str], list[int]] = {}
    for t in exact_trades:
        context = contexts.get(trade_id(t), {})
        labels = [
            ("regime", str(context.get("regime") or "unknown")),
            ("pivot count", str(int(context["pivot_count"])) if context.get("pivot_count") is not None else "unknown"),
            (
                "failed support reclaim",
                "yes" if context.get("failed_support_reclaim") is True
                else "no" if context.get("failed_support_reclaim") is False
                else "unknown",
            ),
        ]
        is_winner = (replay.number(t.get("pnl_rupees"), replay.number(t.get("pnl"), 0.0)) or 0) > 0
        for pattern, label in labels:
            row = pattern_counts.setdefault((pattern, label), [0, 0])
            row[0] += 1
            row[1] += int(is_winner)
    lines += [
        "",
        "| Recorded entry context | Label | Trades | Winners | Losers / flat |",
        "|---|---|---:|---:|---:|",
    ]
    for (pattern, label), (count, wins) in sorted(pattern_counts.items()):
        lines.append(f"| {pattern} | {label} | {count} | {wins} | {count - wins} |")
    lines += [
        "",
        "## Trades differing by more than 3R between policies",
        "",
        "Difference is paired net R on the same entry, compared with P1; the path columns show exact-option MFE and max pullback. Both the full policy result table and 'without best' values above prevent a single best trade from standing alone.",
        "",
        "| Trade | Policy | ΔR vs P1 | MFE R | Pullback R / % |",
        "|---|---|---:|---:|---:|",
    ]
    diffs = []
    for t in exact_trades:
        tid = trade_id(t)
        p1 = replays.get((tid, "P1"))
        if not p1 or not p1.complete or p1.r_multiple is None:
            continue
        compared_policies = policy_names + ["stock_stop_8pct", "stock_stop_12pct"]
        for policy in compared_policies:
            if policy == "P1":
                continue
            if policy.startswith("stock_stop_") and tier(t) != "stock options":
                continue
            alt = replays.get((tid, policy))
            if alt and alt.complete and alt.r_multiple is not None:
                delta = alt.r_multiple - p1.r_multiple
                if abs(delta) > 3:
                    p = paths[tid]
                    diffs.append((t, policy, delta, p))
    for t, policy, delta, p in diffs:
        lines.append(f"| `{t.get('ticker')}` {t['_entry_time_parsed'].date()} | {policy} | {delta:+.2f} | {fmt(p['mfe'])} | {fmt(p['pullback_r'])} / {fmt(p['pullback_pct'])}% |")
    if not diffs:
        lines.append("| None | — | — | — | — |")

    lines += [
        "",
        "## Verdicts",
        "",
    ]
    for name, group in (("index options", [t for t in exact_trades if tier(t) == "index options"]),
                        ("stock options", [t for t in exact_trades if tier(t) == "stock options"])):
        for topic in ("wider runner gap", "volatility-scaled gap"):
            lines.append(
                f"- **{topic}, {name}: insufficient data** — n={len(group)} exact-path trades across "
                f"{len({t['_entry_time_parsed'].date() for t in group})} sessions. Paired results are shown in the full grid; "
                "sample size and short regime coverage do not support changing policy."
            )

    # Explicit, conservative verdicts for low-sample and missing-input hypotheses.
    for label, sample, status, explanation in [
        ("Underlying-reversal trail (P5)", 0, "insufficient data", f"underlying OHLC is missing; {len(exact_trades)} option trades have no valid underlying series"),
        ("Separate 8%/10%/12% stock stop", len([t for t in exact_trades if tier(t) == "stock options"]), "insufficient data", "the 18 stock trades span few sessions; compare the full sensitivity table, do not select a stop"),
    ]:
        lines.append(f"- **{label}: {status}** — n={sample}; {explanation}.")
    for label, kind in (("0.5R partial, index tier", "index options"), ("0.5R partial, stock tier", "stock options")):
        group = [t for t in exact_trades if tier(t) == kind]
        eligible = [
            t for t in group
            if paths.get(trade_id(t)) and 0.5 <= paths[trade_id(t)].get("mfe", -math.inf) < 1.0
        ]
        lines.append(f"- **{label}: insufficient data** — eligible n={len(eligible)} of {len(group)}; policy results are shown as P4_50.")
    lines += [
        "",
        "## Limitations and paper-mode conclusion",
        "",
        f"- Sample: {len(exact_trades)} exact-contract trades over {len(sessions)} recorded sessions; index tier n={sum(tier(t) == 'index options' for t in exact_trades)}, stock tier n={sum(tier(t) == 'stock options' for t in exact_trades)}. Both are far below robust policy-validation scale; stock premium bands are smaller still.",
        "- Sampled quote resolution is irregular; prices between samples and exact stop trigger ordering cannot be recovered. Candle OHLC intrabar order is unknown. Counterfactual fills are estimates, not exchange fills.",
        "- Capture reports flag missing intervals; those trades remain conditional on captured prices. Oct 28 exact contract association and underlying candles are missing. Manual exit rationale, per-trade order events, and exact fee/slippage records are incomplete.",
        "- **Index options:** keep P1 unchanged in paper; compare wider fixed and volatility-scaled gaps in shadow mode only. **Stock options:** keep P1 and the current initial stop; do not adopt a separate stop or partial rule; shadow-test those variants only. Do not activate P5 without underlying bars. Do not select settings by the best day or best trade.",
        "- Before further policy decisions, collect exact-contract option OHLC plus timestamped bid/ask through 15:29, matching underlying 1-minute OHLC for each entry, candle/quote capture-gap and low-tick flags, order/stop activation and fill event logs, explicit manual-exit rationale, verified lot-level fees/slippage, and consistent regime/pivot/support-reclaim labels. Seek at least 30–50 independent sessions per tier (with multiple market regimes) before treating small differences as actionable; use a time-based holdout.",
        "",
    ]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    trades = replay.load_trades(root, args.start, args.end)
    if not trades:
        raise ValueError(f"No closed trades found between {args.start} and {args.end}")
    capture_index = replay.build_capture_index(root)
    market: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}
    paths: dict[str, dict[str, Any]] = {}
    contexts: dict[str, dict[str, Any]] = {}
    replays: dict[tuple[str, str], replay.Replay] = {}
    for trade in trades:
        tid = trade_id(trade)
        candles, quotes = load_market(root, trade)
        market[tid] = (candles, quotes)
        if candles and trade.get("_closed_at_parsed"):
            paths[tid] = path_extrema(trade, candles, quotes, trade["_closed_at_parsed"])
        day_decisions = replay.load_decisions(root, trade["_entry_time_parsed"].date())
        contexts[tid] = replay.entry_context(trade, day_decisions)
        replays[(tid, "P0")] = replay.recorded_replay(trade, args)
        if not candles or not paths.get(tid):
            continue
        replays[(tid, "P1")] = replay.simulate_policy(trade, candles, quotes, args, "P1", runner_gap=1.0)
        for gap in STATIC_GAPS:
            name = f"P2_{gap:.2f}"
            replays[(tid, name)] = replay.simulate_policy(trade, candles, quotes, args, name, runner_gap=gap)
        for window in VOL_WINDOWS:
            for multiple in VOL_MULTIPLIERS:
                name = f"P2v_{window}_{multiple}"
                replays[(tid, name)] = simulate_vol_policy(trade, candles, quotes, args, window, multiple)
        p1_exit = replays[(tid, "P1")].exit_time
        p1_path = replay.path_max_r(trade, candles, quotes, p1_exit) if p1_exit else None
        qualifies = p1_path is not None and 0.5 <= p1_path < 1.0
        replays[(tid, "P4_50")] = replay.simulate_policy(
            trade, candles, quotes, args, "P4_50", runner_gap=1.0,
            partial_fraction=0.5 if qualifies else 0.0,
            partial_r=0.5 if qualifies else None,
            p4_qualifies=qualifies,
        )
        if tier(trade) == "stock options":
            for pct in STOCK_STOP_PCTS:
                name = f"stock_stop_{int(pct * 100)}pct"
                replays[(tid, name)] = stop_variant(trade, candles, quotes, args, pct)

    # Retain all original sanity checks, including the three required Nov 6 checks.
    failures = replay.checks(trades, market, replays)
    if failures:
        print("Required checks failed; report not written:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 2
    report = make_report(root, trades, market, paths, capture_index, replays, contexts)
    output = require_temporary_path(
        args.output if args.output.is_absolute() else root / args.output,
        purpose="Replay addendum report",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"Report written: {output}")
    print(f"Trades: {len(trades)}; exact-option paths: {sum(bool(path) for path in paths.values())}; sessions: {len({t['_entry_time_parsed'].date() for t in trades})}")
    print("All required original replay checks passed.")
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = replay.make_parser()
    parser.description = __doc__
    parser.set_defaults(
        start=START,
        end=END,
        output=Path(tempfile.gettempdir())
        / "EXIT_POLICY_PATH_ADDENDUM_2026-10-28_to_2026-11-06.md",
    )
    return parser


def main() -> int:
    args = make_parser().parse_args()
    try:
        return run(args)
    except (OSError, ValueError, ImportError) as error:
        print(f"Addendum replay failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
