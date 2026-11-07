#!/usr/bin/env python3
"""Replay isolated PAPER exit-flag effects against the legacy P1 baseline.

Run from the repository root, optionally overriding the date range and output:
python .\\tools\\replay_exit_effects.py --start 2026-10-28 --end 2026-11-06
"""

from __future__ import annotations

import argparse
import sys
from argparse import Namespace
from datetime import date
from pathlib import Path
from typing import Any

try:
    from . import replay_exit_policies as replay
except ImportError:
    import replay_exit_policies as replay


SCENARIOS: dict[str, dict[str, Any]] = {
    "legacy_P1": {
        "runner_gap": 1.0,
    },
    "runner_gap_v2_only": {
        "runner_gap": 1.5,
    },
    "profit_lock_v2_only": {
        "runner_gap": 1.0,
        "profit_lock_r": 0.15,
    },
    "trail_close_confirm_v2_only": {
        "runner_gap": 1.0,
        "close_confirm": True,
    },
    "profit_lock_plus_close_confirm": {
        "runner_gap": 1.0,
        "profit_lock_r": 0.15,
        "close_confirm": True,
    },
    "all_three_flags": {
        "runner_gap": 1.5,
        "profit_lock_r": 0.15,
        "close_confirm": True,
    },
}


def _cost_args(slippage: float) -> Namespace:
    return Namespace(
        slippage=slippage,
        brokerage_per_order=20.0,
        stt_rate=0.001,
        exchange_rate=0.0003503,
        sebi_rate=0.000001,
        stamp_rate=0.00003,
        gst_rate=0.18,
    )


def _replay_scenario(
    trade: dict[str, Any],
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    args: Namespace,
    scenario: str,
) -> replay.Replay:
    return replay.simulate_policy(
        trade,
        candles,
        quotes,
        args,
        scenario,
        **SCENARIOS[scenario],
    )


def build_report(root: Path, start: date, end: date) -> str:
    if start > end:
        raise ValueError("--start must be on or before --end")

    all_trades = replay.load_trades(root, start, end)
    trades = [
        trade
        for trade in all_trades
        if str(trade.get("contract_id") or "").startswith("NFO:")
    ]
    excluded_without_contract = len(all_trades) - len(trades)
    results: dict[tuple[str, str], dict[str, replay.Replay]] = {}
    for trade in trades:
        trade_id = str(trade.get("trade_id"))
        day_dir = (
            root
            / "paper_trading_data"
            / "option_candles"
            / trade["_entry_time_parsed"].date().isoformat()
        )
        candles = replay.load_market_rows(day_dir, str(trade["contract_id"]), "candles")
        quotes = replay.load_market_rows(day_dir, str(trade["contract_id"]), "quotes")
        if not candles:
            continue

        half_spread = replay.measured_half_spread_rate(quotes)
        cost_models = {"flat_1_percent": _cost_args(0.01)}
        if half_spread is not None:
            cost_models["measured_half_spread"] = _cost_args(half_spread)

        for cost_model, args in cost_models.items():
            for scenario in SCENARIOS:
                results.setdefault((scenario, cost_model), {})[trade_id] = (
                    _replay_scenario(trade, candles, quotes, args, scenario)
                )

    lines = [
        f"# Isolated PAPER exit-flag replay: {start} to {end}",
        "",
        f"Closed exact-contract rows: {len(trades)}; rows without contract IDs excluded: {excluded_without_contract}.",
        "Only trades with archived option candles can be simulated; paired comparisons include only complete baseline and scenario replays.",
        "Flat costs use 1% adverse slippage per side. Measured half-spread uses each contract's mean valid half-spread/midpoint rate. Brokerage, STT, exchange, SEBI, stamp duty, and GST use the constants in `replay_exit_policies.py`.",
        "This is an offline counterfactual. It does not change flag defaults or production behavior.",
        "",
        "| Scenario | Cost model | Paired N | Net change vs legacy P1 (₹) | Without best paired trade (₹) | Best paired trade |",
        "|---|---|---:|---:|---:|---|",
    ]
    for scenario in list(SCENARIOS)[1:]:
        for cost_model in ("flat_1_percent", "measured_half_spread"):
            baseline = results.get(("legacy_P1", cost_model), {})
            alternative = results.get((scenario, cost_model), {})
            paired = replay.paired_net_change(
                trades,
                {
                    **{(trade_id, "legacy"): item for trade_id, item in baseline.items()},
                    **{(trade_id, scenario): item for trade_id, item in alternative.items()},
                },
                "legacy",
                scenario,
            )
            lines.append(
                f"| {scenario} | {cost_model} | {paired['n']} | "
                f"{replay.money(paired['net_change'])} | "
                f"{replay.money(paired['without_best'])} | "
                f"{paired['best_trade_id'] or 'NA'} |"
            )
    if not trades:
        lines.append("| No exact-contract trades | - | 0 | NA | NA | NA |")
    return "\n".join(lines) + "\n"


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--start", type=date.fromisoformat, default=replay.DEFAULT_START)
    parser.add_argument("--end", type=date.fromisoformat, default=replay.DEFAULT_END)
    parser.add_argument("--output", type=Path, help="Write Markdown report to this path")
    return parser


def main() -> int:
    args = make_parser().parse_args()
    try:
        report = build_report(args.root.resolve(), args.start, args.end)
        if args.output is None:
            sys.stdout.buffer.write(report.encode("utf-8"))
        else:
            output = args.output if args.output.is_absolute() else args.root / args.output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(report, encoding="utf-8")
            print(f"Report written: {output}")
    except (OSError, ValueError) as exc:
        print(f"Isolated exit replay failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
