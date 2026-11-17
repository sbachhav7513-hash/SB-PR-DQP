#!/usr/bin/env python3
"""Replay PAPER support-reversal entry and level-stop flags on archived trades."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from market_bot.support_reversal_flags import (
    first_reversal_confirmation,
    level_distance_pct,
)

if __package__:
    from .paper_entry_replay import (
        IST,
        ReplayArm,
        _number,
        _quote_at_or_after,
        _read_jsonl,
        load_option_market,
        load_underlying_bars,
        parse_datetime,
        simulate_fixed_exit,
    )
else:
    from paper_entry_replay import (
        IST,
        ReplayArm,
        _number,
        _quote_at_or_after,
        _read_jsonl,
        load_option_market,
        load_underlying_bars,
        parse_datetime,
        simulate_fixed_exit,
    )


START_DATE = date(2026, 10, 30)
FIRST_PERIOD_END = date(2026, 11, 11)
SECOND_PERIOD_START = date(2026, 11, 12)
END_DATE = date(2026, 11, 16)
BUFFER_VALUES = (0.05, 0.10, 0.15)
DISTANCE_VALUES = (0.20, 0.30, 0.40)
ZERO_TRADE_STATUSES = {"not_confirmed", "entry_distance_exceeded"}


def _support_route(trade: dict[str, Any]) -> bool:
    return (
        trade.get("route") == "support_reversal"
        and trade.get("strategy_variant") == "paper_underlying_support_reversal"
    )


def _load_day_support_metadata(
    paper_root: Path, trade_date: date
) -> dict[tuple[str, datetime], dict[str, Any]]:
    import pandas as pd

    month_dir = paper_root / trade_date.strftime("%Y-%m")
    day_name = f"day_{trade_date.day:02d}"
    day_dirs = [
        week / day_name
        for week in sorted(month_dir.glob("week_*"))
        if (week / day_name).is_dir()
    ]
    records: dict[tuple[str, datetime], dict[str, Any]] = {}
    for day_dir in day_dirs:
        for path in sorted(day_dir.rglob("decisions*.parquet")):
            frame = pd.read_parquet(
                path,
                columns=[
                    "ticker",
                    "event",
                    "route",
                    "signal",
                    "signal_time",
                    "support_resistance_level",
                ],
            )
            frame = frame[
                (frame["event"].astype(str) == "entry_confirmation")
                & (frame["route"].astype(str) == "support_reversal")
            ]
            for row in frame.to_dict(orient="records"):
                signal_time = parse_datetime(row.get("signal_time"))
                level = _number(row.get("support_resistance_level"))
                signal = str(row.get("signal") or "").upper()
                ticker = str(row.get("ticker") or "").upper()
                if (
                    signal_time is None
                    or level is None
                    or level <= 0
                    or signal not in {"BUY", "SELL"}
                    or not ticker
                ):
                    continue
                records[(ticker, signal_time)] = {
                    "level": level,
                    "signal": signal,
                }
    return records


def _entry_underlying_close(
    bars: list[dict[str, Any]], entry_time: datetime
) -> float | None:
    completed = [
        row
        for row in bars
        if row["time"] + timedelta(minutes=1) <= entry_time
        and row.get("close") is not None
    ]
    return float(completed[-1]["close"]) if completed else None


def _period_label(trade_date: date) -> str:
    return (
        "30-Oct to 11-Nov"
        if trade_date <= FIRST_PERIOD_END
        else "12-Nov to 16-Nov"
    )


def _alternative_for_reversal_confirm(
    record: dict[str, Any], charge_config: dict[str, Any] | None
) -> ReplayArm:
    metadata = record["support_metadata"]
    if metadata is None:
        return ReplayArm("support_level_missing")
    confirmation_time = first_reversal_confirmation(
        record["underlying_bars"],
        record["signal_time"],
        metadata["level"],
        metadata["signal"],
    )
    if confirmation_time is None:
        return ReplayArm("not_confirmed")
    quote = _quote_at_or_after(record["quotes"], confirmation_time)
    if quote is None:
        return ReplayArm("delayed_ask_missing")
    return simulate_fixed_exit(
        record["candles"],
        record["quotes"],
        quote["time"],
        quote["ask"],
        record["quantity"],
        charge_config,
    )


def _alternative_for_level_stop(
    record: dict[str, Any],
    buffer_pct: float,
    max_distance_pct: float,
    charge_config: dict[str, Any] | None,
) -> ReplayArm:
    metadata = record["support_metadata"]
    if metadata is None:
        return ReplayArm("support_level_missing")
    current_close = _entry_underlying_close(
        record["underlying_bars"], record["entry_time"]
    )
    if current_close is None:
        return ReplayArm("underlying_entry_path_missing")
    distance_pct = level_distance_pct(current_close, metadata["level"])
    if distance_pct is None:
        return ReplayArm("underlying_entry_path_invalid")
    if distance_pct > max_distance_pct:
        return ReplayArm("entry_distance_exceeded")
    return simulate_fixed_exit(
        record["candles"],
        record["quotes"],
        record["entry_time"],
        record["baseline_entry"],
        record["quantity"],
        charge_config,
        underlying_bars=record["underlying_bars"],
        support_level=metadata["level"],
        support_signal=metadata["signal"],
        level_buffer_pct=buffer_pct,
    )


def _comparable(
    record: dict[str, Any], alternative: ReplayArm
) -> bool:
    return record["baseline"].status == "complete" and (
        alternative.status == "complete"
        or alternative.status in ZERO_TRADE_STATUSES
    )


def _metrics(
    records: list[dict[str, Any]],
    variant: str,
    *,
    omit_trade_id: str | None = None,
) -> dict[str, Any]:
    paired = [
        record
        for record in records
        if record["trade"]["trade_id"] != omit_trade_id
        and _comparable(record, record["alternatives"][variant])
    ]
    baseline_values = [record["baseline"] for record in paired]
    alternative_values = [record["alternatives"][variant] for record in paired]
    count = len(paired)
    baseline_mean = (
        sum(float(arm.net_r or 0.0) for arm in baseline_values) / count
        if count
        else None
    )
    alternative_mean = (
        sum(float(arm.net_r or 0.0) for arm in alternative_values) / count
        if count
        else None
    )
    baseline_rupees = sum(float(arm.net_rupees or 0.0) for arm in baseline_values)
    alternative_rupees = sum(
        float(arm.net_rupees or 0.0) for arm in alternative_values
    )
    support_rows = [record for record in paired if record["eligible"]]
    kept = sum(
        record["alternatives"][variant].status == "complete"
        for record in support_rows
    )
    wins_lost = sum(
        record["baseline"].net_rupees is not None
        and record["baseline"].net_rupees > 0
        and (
            record["alternatives"][variant].status != "complete"
            or (record["alternatives"][variant].net_rupees or 0.0) <= 0
        )
        for record in support_rows
    )
    return {
        "paired_n": count,
        "support_n": len(support_rows),
        "kept": kept,
        "wins_lost": wins_lost,
        "baseline_mean_r": baseline_mean,
        "alternative_mean_r": alternative_mean,
        "baseline_rupees": baseline_rupees,
        "alternative_rupees": alternative_rupees,
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _best_baseline_trade_id(records: list[dict[str, Any]]) -> str | None:
    baseline_rows = [
        record for record in records if record["baseline"].status == "complete"
    ]
    best_record = max(
        baseline_rows,
        key=lambda item: float(
            item["baseline"].net_r
            if item["baseline"].net_r is not None
            else float("-inf")
        ),
        default=None,
    )
    return str(best_record["trade"]["trade_id"]) if best_record is not None else None


def _beats_baseline(records: list[dict[str, Any]], variant: str) -> bool:
    for label in ("30-Oct to 11-Nov", "12-Nov to 16-Nov"):
        period_records = [
            record for record in records if record["period"] == label
        ]
        best_trade_id = _best_baseline_trade_id(period_records)
        regular = _metrics(period_records, variant)
        without_best = _metrics(
            period_records, variant, omit_trade_id=best_trade_id
        )
        for metrics in (regular, without_best):
            if (
                metrics["alternative_mean_r"] is None
                or metrics["baseline_mean_r"] is None
                or metrics["alternative_rupees"] <= metrics["baseline_rupees"]
                or metrics["alternative_mean_r"] <= metrics["baseline_mean_r"]
            ):
                return False
    return True


def build_report(
    trades: list[dict[str, Any]],
    candle_root: Path,
    paper_data_root: Path,
    charge_config: dict[str, Any] | None = None,
) -> str:
    trades = [
        trade
        for trade in trades
        if START_DATE
        <= (parse_datetime(trade.get("timestamp")) or datetime.min.replace(tzinfo=IST)).date()
        <= END_DATE
    ]
    if len(trades) != 51:
        raise ValueError(f"Expected 51 closed PAPER trades, found {len(trades)}")

    day_metadata: dict[date, dict[tuple[str, datetime], dict[str, Any]]] = {}
    market_cache: dict[tuple[date, str], list[dict[str, Any]]] = {}
    records = []
    for trade in trades:
        entered = parse_datetime(trade.get("timestamp"))
        signal_time = parse_datetime(trade.get("signal_time"))
        entry_time = parse_datetime(trade.get("entry_time")) or entered
        quantity = _number(trade.get("quantity"))
        baseline_entry = _number(trade.get("entry"))
        if (
            entered is None
            or signal_time is None
            or entry_time is None
            or quantity is None
            or baseline_entry is None
        ):
            raise ValueError(f"Missing replay input: {trade.get('trade_id')}")

        candles, quotes = load_option_market(candle_root, trade)
        underlying = str(trade["ticker"]).rsplit("_", 1)[0].upper()
        cache_key = (entered.date(), underlying)
        if cache_key not in market_cache:
            market_cache[cache_key] = load_underlying_bars(
                paper_data_root, entered.date(), underlying
            )
        underlying_bars = market_cache[cache_key]
        if entered.date() not in day_metadata:
            day_metadata[entered.date()] = _load_day_support_metadata(
                paper_data_root, entered.date()
            )
        support_metadata = day_metadata[entered.date()].get(
            (str(trade["ticker"]).upper(), signal_time)
        )
        baseline = simulate_fixed_exit(
            candles,
            quotes,
            entry_time,
            baseline_entry,
            quantity,
            charge_config,
        )
        records.append(
            {
                "trade": trade,
                "date": entered.date(),
                "period": _period_label(entered.date()),
                "entry_time": entry_time,
                "signal_time": signal_time,
                "quantity": quantity,
                "baseline_entry": baseline_entry,
                "candles": candles,
                "quotes": quotes,
                "underlying_bars": underlying_bars,
                "support_metadata": support_metadata,
                "eligible": _support_route(trade),
                "baseline": baseline,
                "alternatives": {},
            }
        )

    for record in records:
        if record["eligible"]:
            reversal_arm = _alternative_for_reversal_confirm(record, charge_config)
        else:
            reversal_arm = record["baseline"]
        record["alternatives"]["reversal_confirm_v2"] = reversal_arm
        for buffer_pct in BUFFER_VALUES:
            for distance_pct in DISTANCE_VALUES:
                variant = f"level_stop_v2 b={buffer_pct:.2f}% d={distance_pct:.2f}%"
                if record["eligible"]:
                    arm = _alternative_for_level_stop(
                        record, buffer_pct, distance_pct, charge_config
                    )
                else:
                    arm = record["baseline"]
                record["alternatives"][variant] = arm

    baseline_rows = [
        record for record in records if record["baseline"].status == "complete"
    ]
    best_trade_ids = {
        period: _best_baseline_trade_id(
            [record for record in records if record["period"] == period]
        )
        for period in ("30-Oct to 11-Nov", "12-Nov to 16-Nov")
    }
    variants = ["reversal_confirm_v2"] + [
        f"level_stop_v2 b={buffer_pct:.2f}% d={distance_pct:.2f}%"
        for buffer_pct in BUFFER_VALUES
        for distance_pct in DISTANCE_VALUES
    ]
    selected_level_variant = next(
        (
            variant
            for variant in variants[1:]
            if _beats_baseline(records, variant)
        ),
        None,
    )
    on_flags = []
    if _beats_baseline(records, "reversal_confirm_v2"):
        on_flags.append("reversal_confirm_v2")
    if selected_level_variant is not None:
        on_flags.append(selected_level_variant)

    output = [
        "# PAPER support-reversal v2 paired replay",
        "",
        f"Closed PAPER options replayed: **{len(trades)}** ({START_DATE} to {END_DATE}).",
        f"Exact support-reversal route cohort: **{sum(record['eligible'] for record in records)}**; other routes are unchanged/pass-through.",
        f"Baseline complete exits: **{len(baseline_rows)}/51**.",
        "Best baseline trade removed from each period's no-best columns: "
        + "; ".join(
            f"{period}: `{trade_id or 'none'}`"
            for period, trade_id in best_trade_ids.items()
        )
        + ".",
        "",
        "The paired arms use the archived option candle and quote/bid paths. Both use the same fixed PAPER exit simulator: 10% premium stop backstop, 20% target, stop-first on same-candle stop/target touches, session-end bid exit, and configured PAPER fees on both orders. Dropped entries contribute zero net R and rupees; missing replay paths are excluded from both arms. Mean net R and net rupees are therefore paired portfolio results, while `kept` counts only complete trades in the eligible support-reversal cohort.",
        "",
        "For `reversal_confirm_v2`, the signal's recorded pivot and direction are matched to completed decision-journal rows. A complete, contiguous, wall-clock 5-minute underlying candle must start after the signal, test the level within 0.10%, close in the directional 60% of its range, and complete within 15 minutes. Entry uses the first valid archived ask at or after that candle's completion.",
        "",
        "For `level_stop_v2`, entry is skipped when the last completed underlying close before entry is more than `d` from the pivot. A completed 1-minute close beyond the pivot by `b` exits at the first valid archived option bid at or after that close; the premium stop remains active as backstop. Grid values are in percent.",
        "",
        "| Period | Variant | Paired n | Support kept | Wins lost | Mean net R (base / variant) | Net ₹ (base / variant) | Without best mean net R (base / variant) | Without best net ₹ (base / variant) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for period in ("30-Oct to 11-Nov", "12-Nov to 16-Nov"):
        period_records = [record for record in records if record["period"] == period]
        for variant in variants:
            metrics = _metrics(period_records, variant)
            without_best = _metrics(
                period_records,
                variant,
                omit_trade_id=best_trade_ids[period],
            )
            output.append(
                f"| {period} | {variant} | {metrics['paired_n']} | "
                f"{metrics['kept']}/{metrics['support_n']} | {metrics['wins_lost']} | "
                f"{metrics['baseline_mean_r']:.4f} / {metrics['alternative_mean_r']:.4f} | "
                f"{metrics['baseline_rupees']:.2f} / {metrics['alternative_rupees']:.2f} | "
                f"{without_best['baseline_mean_r']:.4f} / {without_best['alternative_mean_r']:.4f} | "
                f"{without_best['baseline_rupees']:.2f} / {without_best['alternative_rupees']:.2f} |"
                if metrics["paired_n"] and without_best["paired_n"]
                else f"| {period} | {variant} | {metrics['paired_n']} | "
                f"{metrics['kept']}/{metrics['support_n']} | {metrics['wins_lost']} | "
                f"N/A | N/A | N/A | N/A |"
            )

    reversal_rejected = sum(
        record["eligible"]
        and record["alternatives"]["reversal_confirm_v2"].status
        == "not_confirmed"
        for record in records
    )
    level_skips = {
        variant: sum(
            record["eligible"]
            and record["alternatives"][variant].status == "entry_distance_exceeded"
            for record in records
        )
        for variant in variants[1:]
    }
    output.extend(
        [
            "",
            "## Decision",
            "",
            (
                "Default ON candidates: "
                + ", ".join(on_flags)
                + ". Each passed the strict comparison against baseline for both periods, and each period remains ahead after removing the best baseline trade."
                if on_flags
                else "Both flags remain **OFF**. No candidate beat baseline in both periods for both mean net R and net rupees, including each period's no-best result."
            ),
            f"`reversal_confirm_v2` dropped {reversal_rejected} eligible signals for no qualifying confirmation.",
            "Level-stop entry skips by grid: "
            + ", ".join(f"{variant}: {count}" for variant, count in level_skips.items())
            + ".",
            "",
            "## Coverage",
            "",
            f"- Support-route rows with archived pivot metadata: {sum(record['eligible'] and record['support_metadata'] is not None for record in records)}/{sum(record['eligible'] for record in records)}.",
            f"- Missing baseline exit paths: {sum(record['baseline'].status != 'complete' for record in records)}.",
            f"- Confirmation alternatives with missing ask/exit path: {sum(record['eligible'] and record['alternatives']['reversal_confirm_v2'].status not in {'complete', 'not_confirmed'} for record in records)}.",
            "- Other variants with missing decision/underlying/option paths are excluded from their paired metric denominators, not imputed.",
        ]
    )
    return "\n".join(output) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", type=Path, default=Path("trades.jsonl"))
    parser.add_argument(
        "--candles",
        type=Path,
        default=Path("paper_trading_data/option_candles"),
    )
    parser.add_argument("--paper-data", type=Path, default=Path("paper_trading_data"))
    parser.add_argument("--config", type=Path, default=Path("kite_config.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "PAPER_SUPPORT_REVERSAL_V2_REPLAY_2026-10-30_to_2026-11-16.md"
        ),
    )
    args = parser.parse_args()
    try:
        trades = _read_jsonl(args.trades)
        config = json.loads(args.config.read_text(encoding="utf-8"))
        report = build_report(trades, args.candles, args.paper_data, config)
        args.output.write_text(report, encoding="utf-8", newline="\n")
        print(f"Wrote {args.output}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Replay failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
