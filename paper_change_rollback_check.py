#!/usr/bin/env python3
"""Print daily PAPER change performance and enforce the agreed rollback rule."""

from __future__ import annotations

import argparse
import csv
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
    "option_premium_rising_momentum_v2",
    "index_persistence_pass",
    "premium_floor_v2",
    "banknifty_caps_v2",
    "nifty_vol_floor_v2",
    "capital_based_risk_v2",
)
REMOVAL_ONLY_KEY = "premium_floor_v2"
CAPITAL_BASED_RISK_KEY = "capital_based_risk_v2"
ROLLBACK_TRADES = 15
ROLLBACK_SESSIONS = 5
BROKERAGE_PER_ORDER_INR = 20.0
STT_SELL_RATE = 0.0015
NSE_FO_TRANSACTION_RATE = 0.0003553
SEBI_TURNOVER_RATE = 0.000001
STAMP_DUTY_BUY_RATE = 0.00003
GST_RATE = 0.18
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
    gross = _gross_pnl_rupees(trade)
    if gross is None:
        gross = _finite_amount(trade.get("after_cost_pnl", trade.get("net_pnl")))
    if gross is None:
        return None
    try:
        quantity = abs(float(trade.get("quantity", 0)))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(quantity) or quantity <= 0:
        return None

    entry = _finite_amount(trade.get("entry"))
    exit_price = _finite_amount(
        trade.get(
            "exit_price",
            trade.get("paper_exit_ltp", trade.get("last_price")),
        )
    )
    if entry is None or exit_price is None or entry < 0 or exit_price < 0:
        brokerage = BROKERAGE_PER_ORDER_INR * 2
        transaction = sebi = stt = stamp = 0.0
    else:
        buy_turnover = entry * quantity
        sell_turnover = exit_price * quantity
        turnover = buy_turnover + sell_turnover
        brokerage = BROKERAGE_PER_ORDER_INR * 2
        transaction = turnover * NSE_FO_TRANSACTION_RATE
        sebi = turnover * SEBI_TURNOVER_RATE
        stt = sell_turnover * STT_SELL_RATE
        stamp = buy_turnover * STAMP_DUTY_BUY_RATE
    gst = GST_RATE * (brokerage + transaction + sebi)
    slippage = SLIPPAGE_PER_UNIT_PER_SIDE_INR * quantity * 2
    return gross - brokerage - transaction - sebi - stt - stamp - gst - slippage


def _profit_factor(values: list[float]) -> float:
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if losses == 0:
        return math.inf if gains > 0 else 0.0
    return gains / losses


def _change_evaluations(row: dict[str, Any]) -> dict[str, Any]:
    evaluations = row.get("paper_change_gate_evaluations")
    if not isinstance(evaluations, dict):
        measurements = row.get("gate_measurements")
        evaluations = (
            measurements.get("paper_change_gate_evaluations")
            if isinstance(measurements, dict)
            else {}
        )
    return evaluations if isinstance(evaluations, dict) else {}


def _candle_rows(
    candle_root: Path, contract_id: str, event_date: str, signal_time: datetime
) -> list[dict[str, Any]]:
    day_path = candle_root / event_date
    if not day_path.is_dir():
        return []
    matched: list[dict[str, Any]] = []
    for path in day_path.glob("*.csv"):
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                if str(row.get("contract_id", "")) != contract_id:
                    continue
                try:
                    candle_time = datetime.fromisoformat(
                        str(row.get("timestamp", "")).replace("Z", "+00:00")
                    )
                except ValueError:
                    continue
                if candle_time.tzinfo is None:
                    candle_time = candle_time.replace(tzinfo=IST)
                if candle_time.astimezone(IST) > signal_time.astimezone(IST):
                    matched.append({**row, "_time": candle_time})
    return sorted(matched, key=lambda row: row["_time"])


def _removed_trade_estimate(
    decision: dict[str, Any], candle_root: Path, config: dict[str, Any]
) -> dict[str, Any]:
    measurements = decision.get("gate_measurements")
    measurements = measurements if isinstance(measurements, dict) else {}
    evaluation = _change_evaluations(decision).get(REMOVAL_ONLY_KEY, {})
    signal_value = (
        decision.get("signal_time")
        or (decision.get("bar") or {}).get("timestamp")
        or decision.get("timestamp")
    )
    try:
        signal_time = datetime.fromisoformat(str(signal_value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return {"status": "missing_signal_time"}
    if signal_time.tzinfo is None:
        signal_time = signal_time.replace(tzinfo=IST)
    contract_id = str(decision.get("contract_id", ""))
    candles = _candle_rows(
        candle_root,
        contract_id,
        signal_time.astimezone(IST).date().isoformat(),
        signal_time,
    )
    entry = _finite_amount(
        measurements.get("ask")
        or decision.get("signal_ask")
        or measurements.get("ltp")
        or decision.get("signal_ltp")
    )
    try:
        quantity = int(decision.get("lot_size") or 0)
        stop_pct = float(config.get("option_premium_stop_pct", 0.10))
        target_pct = float(config.get("option_premium_target_pct", 0.20))
    except (TypeError, ValueError, OverflowError):
        return {"status": "invalid_exit_or_lot_config"}
    if entry is None or entry <= 0 or quantity <= 0 or not candles:
        return {
            "status": "candle_mapping_unavailable",
            "candle_count": len(candles),
            "entry": entry,
            "contract_id": contract_id,
        }

    stop = entry * (1.0 - stop_pct)
    target = entry * (1.0 + target_pct)
    exit_price = None
    exit_time = None
    exit_reason = "last_mapped_candle"
    for candle in candles:
        try:
            low = float(candle["low"])
            high = float(candle["high"])
            open_price = float(candle["open"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        exit_time = candle["_time"]
        if low <= stop:
            exit_price = min(stop, open_price) if open_price < stop else stop
            exit_reason = "10pct_stop"
            break
        if high >= target:
            exit_price = max(target, open_price) if open_price > target else target
            exit_reason = "configured_target"
            break
    if exit_price is None:
        last_candle = candles[-1]
        exit_price = _finite_amount(last_candle.get("bid")) or _finite_amount(
            last_candle.get("close")
        )
        exit_time = last_candle["_time"]
    if exit_price is None:
        return {"status": "invalid_candle_prices", "candle_count": len(candles)}
    gross = (exit_price - entry) * quantity
    net = _net_pnl_rupees(
        {
            "pnl_rupees": gross,
            "quantity": quantity,
            "entry": entry,
            "exit_price": exit_price,
        }
    )
    return {
        "status": "estimated",
        "contract_id": contract_id,
        "signal_time": signal_time.isoformat(),
        "entry": entry,
        "exit": exit_price,
        "exit_time": exit_time.isoformat() if exit_time else None,
        "exit_reason": exit_reason,
        "quantity": quantity,
        "gross_pnl_inr": gross,
        "net_pnl_inr": net,
        "candle_count": len(candles),
        "premium_floor": evaluation.get("floor"),
    }


def _removed_decisions(
    decisions_path: Path, candle_root: Path, config: dict[str, Any]
) -> list[dict[str, Any]]:
    if not decisions_path.exists():
        return []
    removed: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(decisions_path):
        evaluation = _change_evaluations(row).get(REMOVAL_ONLY_KEY)
        if not isinstance(evaluation, dict):
            continue
        if evaluation.get("passed") is not False or not evaluation.get(
            "would_pass_baseline"
        ):
            continue
        identity = str(
            row.get("signal_id")
            or f"{row.get('contract_id')}:{row.get('signal_time') or row.get('timestamp')}"
        )
        removed[identity] = _removed_trade_estimate(row, candle_root, config)
    return list(removed.values())


def _banknifty_stop_reason(trades: dict[str, dict[str, Any]]) -> str | None:
    banknifty = [
        row
        for row in trades.values()
        if str(row.get("ticker", "")).upper().startswith("BANKNIFTY")
        and str(row.get("status", "")).lower() == "closed"
        and "banknifty_caps_v2" in _as_list(row.get("paper_change_flags"))
    ]
    banknifty.sort(
        key=lambda row: str(row.get("closed_at") or row.get("timestamp") or "")
    )
    consecutive_losses = 0
    for row in banknifty:
        net = _net_pnl_rupees(row)
        if net is None:
            consecutive_losses = 0
            continue
        if net < -2500.0:
            return f"single BANKNIFTY loss INR {net:.2f} exceeds INR 2500"
        consecutive_losses = consecutive_losses + 1 if net < 0 else 0
        if consecutive_losses >= 2:
            return "two consecutive BANKNIFTY net losses"
    return None


def _capital_risk_trades(
    trades: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        row
        for row in trades.values()
        if CAPITAL_BASED_RISK_KEY
        in _as_list(row.get("paper_change_flags"))
        and str(row.get("status", "")).lower() == "closed"
    ]


def _trade_investment_amount(trade: dict[str, Any]) -> float | None:
    invested = _finite_amount(trade.get("invested_amount"))
    if invested is not None and invested >= 0:
        return invested
    entry = _finite_amount(trade.get("entry"))
    quantity = _finite_amount(trade.get("quantity"))
    if entry is None or quantity is None or entry < 0:
        return None
    return entry * abs(quantity)


def _trade_risk_amount(trade: dict[str, Any]) -> float | None:
    risk = _finite_amount(
        trade.get("risk_amount", trade.get("paper_entry_risk_rupees"))
    )
    return risk if risk is not None and risk >= 0 else None


def _trade_lots(trade: dict[str, Any]) -> float | None:
    lots = _finite_amount(trade.get("lots"))
    if lots is not None and lots >= 0:
        return lots
    quantity = _finite_amount(trade.get("quantity"))
    lot_size = _finite_amount(trade.get("lot_size"))
    if quantity is None or lot_size is None or lot_size <= 0:
        return None
    return abs(quantity) / lot_size


def _capital_based_stop_reason(
    trades: dict[str, dict[str, Any]]
) -> str | None:
    daily_losses: dict[str, float] = {}
    for row in _capital_risk_trades(trades):
        pnl = _net_pnl_rupees(row)
        if pnl is None:
            continue
        risk = _trade_risk_amount(row)
        if risk is not None and pnl < -1.5 * risk:
            return (
                f"trade {row.get('trade_id', 'unknown')} loss INR {pnl:.2f} "
                f"exceeds 1.5x risk INR {risk:.2f}"
            )
        event_date = _event_date(row.get("closed_at") or row.get("timestamp"))
        if event_date is not None:
            daily_losses[event_date] = daily_losses.get(event_date, 0.0) + max(
                -pnl, 0.0
            )
    for event_date, realized_loss in sorted(daily_losses.items()):
        if realized_loss >= 10_000.0:
            return (
                f"daily loss limit INR 10000 hit on {event_date} "
                f"(realized loss INR {realized_loss:.2f})"
            )
        if realized_loss >= 6_000.0:
            return (
                f"daily realized loss INR 6000 reached on {event_date} "
                f"(realized loss INR {realized_loss:.2f})"
            )
    return None


def _print_capital_based_daily_summary(
    trades: dict[str, dict[str, Any]]
) -> None:
    daily: dict[str, list[dict[str, Any]]] = {}
    for row in _capital_risk_trades(trades):
        event_date = _event_date(row.get("closed_at") or row.get("timestamp"))
        if event_date is not None:
            daily.setdefault(event_date, []).append(row)
    for event_date, rows in sorted(daily.items()):
        invested = [
            amount
            for row in rows
            if (amount := _trade_investment_amount(row)) is not None
        ]
        risks = [
            amount
            for row in rows
            if (amount := _trade_risk_amount(row)) is not None
        ]
        pnl_values = [
            amount
            for row in rows
            if (amount := _net_pnl_rupees(row)) is not None
        ]
        lots = [
            f"{row.get('trade_id', 'unknown')}:{lot_count:g}"
            for row in rows
            if (lot_count := _trade_lots(row)) is not None
        ]
        invested_total = sum(invested)
        pnl_total = sum(pnl_values)
        pnl_per_invested = (
            f"{pnl_total / invested_total:.6f}"
            if invested_total > 0
            else "unavailable"
        )
        print(
            f"{CAPITAL_BASED_RISK_KEY} daily {event_date}: "
            f"trades={len(rows)} lots_per_trade=[{', '.join(lots)}] "
            f"invested_inr={invested_total:.2f} risk_taken_inr={sum(risks):.2f} "
            f"pnl_inr={pnl_total:.2f} "
            f"pnl_per_inr_invested={pnl_per_invested}"
        )


def run_check(
    config_path: Path,
    trades_path: Path,
    decisions_path: Path,
    candle_root: Path = Path("paper_trading_data/option_candles"),
) -> int:
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

    changes: list[tuple[str, str]] = []
    print(
        "PAPER change daily summary "
        "(cost model: Zerodha NSE F&O; brokerage INR 20/order, STT 0.15% sell, "
        "NSE transaction 0.03553%, SEBI INR 10/crore, stamp 0.003% buy, "
        f"GST 18%, slippage INR {SLIPPAGE_PER_UNIT_PER_SIDE_INR:.2f}/unit/side)"
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
        wins = sum(value > 0 for value in net_values)
        win_pct = 100.0 * wins / len(net_values) if net_values else 0.0
        worst = min(
            (
                (net, str(row.get("trade_id", "")))
                for row in attributed
                if (net := _net_pnl_rupees(row)) is not None
            ),
            default=None,
        )
        session_count = len(session_dates[key])
        factor_text = "inf" if math.isinf(factor) else f"{factor:.2f}"
        worst_text = (
            f"{worst[1]}:{worst[0]:.2f}" if worst is not None else "unavailable"
        )
        print(
            f"{key}: attributed_trades={len(attributed)} "
            f"sample_pnl={len(net_values)} sessions={session_count} "
            f"net_pnl_inr={total_net:.2f} PF={factor_text} "
            f"win_pct={win_pct:.1f} worst_trade={worst_text} "
            f"pnl_unavailable={missing} active={bool(config.get(key, True))}"
        )
        if len(attributed) < 10:
            print(f"{key}: cannot be judged (fewer than 10 attributed trades)")

        threshold_reached = (
            len(attributed) >= ROLLBACK_TRADES
            or session_count >= ROLLBACK_SESSIONS
        )
        if key == REMOVAL_ONLY_KEY:
            continue
        if key == CAPITAL_BASED_RISK_KEY:
            if bool(config.get(key, True)):
                stop_reason = _capital_based_stop_reason(trades)
                if stop_reason:
                    config[key] = False
                    changes.append((key, stop_reason))
            continue
        if key == "banknifty_caps_v2" and bool(config.get(key, True)):
            stop_reason = _banknifty_stop_reason(trades)
            if stop_reason:
                config[key] = False
                changes.append((key, stop_reason))
                continue
        if (
            bool(config.get(key, True))
            and threshold_reached
            and bool(net_values)
            and not missing
            and (total_net < 0 or factor < 1.0)
        ):
            config[key] = False
            changes.append(
                (key, "rollback threshold reached and net P/L < 0 or PF < 1.0")
            )

    _print_capital_based_daily_summary(trades)
    removed = _removed_decisions(decisions_path, candle_root, config)
    estimated = [
        row for row in removed if row.get("status") == "estimated"
    ]
    removed_net = sum(
        float(row["net_pnl_inr"]) for row in estimated
    )
    print(
        f"{REMOVAL_ONLY_KEY}: removed_signals={len(removed)} "
        f"candle_estimates={len(estimated)} "
        f"estimated_net_pnl_inr={removed_net:.2f} rollback=report_only"
    )
    for row in removed:
        if row.get("status") == "estimated":
            print(
                "  removed_trade: "
                f"contract={row.get('contract_id')} "
                f"signal_time={row.get('signal_time')} "
                f"entry={row.get('entry'):.2f} exit={row.get('exit'):.2f} "
                f"exit_reason={row.get('exit_reason')} "
                f"net_pnl_inr={row.get('net_pnl_inr'):.2f}"
            )
        else:
            print(
                "  removed_trade: "
                f"contract={row.get('contract_id', 'unknown')} "
                f"status={row.get('status')}"
            )

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
        for key, reason in changes:
            print(f"Rollback switched OFF: {key} ({reason})")
        print("Restart the PAPER bot to apply the updated config hash and flags.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("kite_config.json"))
    parser.add_argument("--trades", type=Path, default=Path("trades.jsonl"))
    parser.add_argument("--decisions", type=Path, default=Path("decision_log.jsonl"))
    parser.add_argument(
        "--candles",
        type=Path,
        default=Path("paper_trading_data/option_candles"),
    )
    args = parser.parse_args()
    try:
        return run_check(args.config, args.trades, args.decisions, args.candles)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Rollback check failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
