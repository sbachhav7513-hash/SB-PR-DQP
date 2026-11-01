#!/usr/bin/env python3
"""Print daily PAPER change performance and enforce the agreed rollback rule."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
CHANGE_KEYS = (
    "stale_quote_candle_fallback",
    "option_candle_momentum",
    "index_persistence_pass",
)
ROLLBACK_TRADES = 15
ROLLBACK_SESSIONS = 5
ROUND_TRIP_COST_INR = 98.0
SLIPPAGE_PER_UNIT_PER_SIDE_INR = 0.05


def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            yield row


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return _as_list(parsed)
    return []


def _event_date(value: Any) -> str | None:
    try:
        event_time = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=IST)
    return event_time.astimezone(IST).date().isoformat()


def _latest_trades(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return latest
    for row in _read_jsonl(path):
        trade_id = row.get("trade_id")
        if trade_id:
            latest[str(trade_id)] = row
    return latest


def _finite_amount(value: Any) -> float | None:
    try:
        amount = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return amount if math.isfinite(amount) else None


def _gross_pnl_rupees(trade: dict[str, Any]) -> float | None:
    amount = _finite_amount(trade.get("pnl_rupees"))
    if amount is not None:
        return amount

    quantity = trade.get("quantity")
    try:
        quantity_value = abs(float(quantity))
    except (TypeError, ValueError, OverflowError):
        quantity_value = 0.0
    if quantity_value <= 0 or not math.isfinite(quantity_value):
        return None

    status = str(trade.get("status", "")).lower()
    if status == "open":
        try:
            entry = float(trade["entry"])
            mark = float(trade.get("last_price", trade.get("paper_exit_ltp")))
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(entry) or not math.isfinite(mark):
            return None
        direction = 1.0 if str(trade.get("action", "")).upper() == "BUY" else -1.0
        return (mark - entry) * direction * quantity_value

    try:
        pnl = float(trade["pnl"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(pnl):
        return None
    return pnl * quantity_value


def _net_pnl_rupees(trade: dict[str, Any]) -> float | None:
    recorded_net = _finite_amount(
        trade.get("after_cost_pnl", trade.get("net_pnl"))
    )
    if recorded_net is not None:
        return recorded_net
    gross = _gross_pnl_rupees(trade)
    if gross is None:
        return None
    try:
        quantity = abs(float(trade.get("quantity", 0)))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(quantity) or quantity <= 0:
        return None

    entry_slippage_already_in_fill = (
        str(trade.get("entry_fill_source", "")).lower() == "candle_fallback"
    )
    slippage_sides = 1 if entry_slippage_already_in_fill else 2
    return (
        gross
        - ROUND_TRIP_COST_INR
        - SLIPPAGE_PER_UNIT_PER_SIDE_INR * quantity * slippage_sides
    )


def _profit_factor(values: list[float]) -> float:
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if losses == 0:
        return math.inf if gains > 0 else 0.0
    return gains / losses


def run_check(config_path: Path, trades_path: Path, decisions_path: Path) -> int:
    with config_path.open("r", encoding="utf-8") as source:
        config = json.load(source)
    if not isinstance(config, dict):
        raise ValueError(f"{config_path} must contain a JSON object")
    mode = str(config.get("mode", "")).strip().upper()
    if mode != "PAPER":
        print(f"Mode is {mode or 'unspecified'}; no config changes made (PAPER only).")
        return 0

    trades = _latest_trades(trades_path)
    session_dates = {key: set() for key in CHANGE_KEYS}
    if decisions_path.exists():
        for row in _read_jsonl(decisions_path):
            event_date = _event_date(row.get("timestamp"))
            if event_date is None:
                continue
            for key in _as_list(row.get("paper_change_flags")):
                if key in session_dates:
                    session_dates[key].add(event_date)

    changes: list[str] = []
    print(
        "PAPER change daily summary "
        f"(cost model: INR {ROUND_TRIP_COST_INR:.0f}/trade + "
        f"INR {SLIPPAGE_PER_UNIT_PER_SIDE_INR:.2f}/unit/side)"
    )
    for key in CHANGE_KEYS:
        attributed = [
            row
            for row in trades.values()
            if key in _as_list(row.get("paper_change_attributions"))
        ]
        net_values = [
            net
            for row in attributed
            if (net := _net_pnl_rupees(row)) is not None
        ]
        missing = len(attributed) - len(net_values)
        total_net = sum(net_values)
        factor = _profit_factor(net_values)
        session_count = len(session_dates[key])
        factor_text = "inf" if math.isinf(factor) else f"{factor:.2f}"
        print(
            f"{key}: added_trades={len(attributed)} sessions={session_count} "
            f"net_pnl_inr={total_net:.2f} PF={factor_text} "
            f"pnl_unavailable={missing} active={bool(config.get(key, True))}"
        )

        threshold_reached = (
            len(attributed) >= ROLLBACK_TRADES
            or session_count >= ROLLBACK_SESSIONS
        )
        if (
            bool(config.get(key, True))
            and threshold_reached
            and bool(net_values)
            and not missing
            and (total_net < 0 or factor < 1.0)
        ):
            config[key] = False
            changes.append(key)

    if changes:
        temporary = config_path.with_name(config_path.name + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as destination:
                json.dump(config, destination, indent=2)
                destination.write("\n")
            os.replace(temporary, config_path)
        except OSError:
            if temporary.exists():
                temporary.unlink()
            raise
        print("Rollback switched OFF: " + ", ".join(changes))
        print("Restart the PAPER bot to apply the updated config hash and flags.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("kite_config.json"))
    parser.add_argument("--trades", type=Path, default=Path("trades.jsonl"))
    parser.add_argument("--decisions", type=Path, default=Path("decision_log.jsonl"))
    args = parser.parse_args()
    try:
        return run_check(args.config, args.trades, args.decisions)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Rollback check failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
