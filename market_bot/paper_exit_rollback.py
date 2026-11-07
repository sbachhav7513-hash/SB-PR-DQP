from __future__ import annotations

import json
import math
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
EXIT_FLAGS = (
    "runner_gap_v2",
    "profit_lock_v2",
    "trail_close_confirm_v2",
)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _trade_flags(trade: dict[str, Any]) -> set[str]:
    for key in (
        "paper_exit_flags_at_entry",
        "paper_exit_flags",
        "paper_change_flags_at_entry",
        "paper_change_flags",
    ):
        if trade.get(key) not in (None, ""):
            return set(_list_value(trade.get(key)))
    return set()


def _planned_risk(trade: dict[str, Any]) -> float | None:
    risk = _number(
        trade.get("planned_risk_rupees")
        or trade.get("paper_entry_risk_rupees")
        or trade.get("risk_amount")
    )
    if risk is not None and risk > 0:
        return risk
    risk_per_unit = _number(trade.get("initial_risk_per_unit"))
    quantity = _number(trade.get("quantity"))
    if risk_per_unit is not None and quantity is not None:
        derived = abs(risk_per_unit * quantity)
        if derived > 0:
            return derived
    entry = _number(trade.get("entry"))
    stop = _number(trade.get("initial_stop_loss", trade.get("stop_loss")))
    if entry is not None and stop is not None and quantity is not None:
        derived = abs(entry - stop) * abs(quantity)
        return derived if derived > 0 else None
    return None


def _trade_pnl(trade: dict[str, Any]) -> float | None:
    return _number(trade.get("pnl_rupees", trade.get("pnl")))


def _trade_session(trade: dict[str, Any]) -> str | None:
    value = trade.get("closed_at") or trade.get("timestamp") or trade.get("entry_time")
    parsed = _parse_time(value)
    return parsed.date().isoformat() if parsed else None


def _counterfactual_delta_r(
    trade: dict[str, Any], flag: str, candle_root: Path
) -> tuple[float | None, str | None]:
    contract_id = str(trade.get("contract_id") or "")
    entry_time = _parse_time(trade.get("entry_time") or trade.get("timestamp"))
    if not contract_id.startswith("NFO:") or entry_time is None:
        return None, "missing exact contract_id or entry time"
    try:
        from tools.replay_exit_policies import (
            load_market_rows,
            parse_datetime,
            simulate_policy,
        )
    except ImportError as exc:
        return None, f"offline replay unavailable: {exc}"

    day_dir = candle_root / entry_time.date().isoformat()
    candles = load_market_rows(day_dir, contract_id, "candles")
    quotes = load_market_rows(day_dir, contract_id, "quotes")
    if not candles or not quotes:
        return None, "missing exact-contract candles or quotes"

    replay_trade = dict(trade)
    replay_trade["_entry_time_parsed"] = parse_datetime(entry_time.isoformat())
    if replay_trade["_entry_time_parsed"] is None:
        return None, "invalid replay entry time"
    params = _dict_value(trade.get("paper_exit_parameters"))
    runner_gap = _number(params.get("runner_gap_r"))
    if runner_gap is None:
        runner_gap = 1.5 if "runner_gap_v2" in _trade_flags(trade) else 1.0
    lock_r = _number(params.get("profit_lock_r"))
    if lock_r is None:
        lock_r = 0.15
    close_confirm = "trail_close_confirm_v2" in _trade_flags(trade)
    args = Namespace(
        slippage=0.01,
        brokerage_per_order=20.0,
        stt_rate=0.001,
        exchange_rate=0.0003503,
        sebi_rate=0.000001,
        stamp_rate=0.00003,
        gst_rate=0.18,
    )
    old_settings = {
        "runner_gap": runner_gap,
        "profit_lock_r": None if flag == "profit_lock_v2" else lock_r,
        "close_confirm": (
            False if flag == "trail_close_confirm_v2" else close_confirm
        ),
    }
    new_settings = {
        "runner_gap": runner_gap,
        "profit_lock_r": (
            lock_r if flag == "profit_lock_v2" else (
                lock_r if "profit_lock_v2" in _trade_flags(trade) else None
            )
        ),
        "close_confirm": (
            True if flag == "trail_close_confirm_v2" else close_confirm
        ),
    }
    old = simulate_policy(
        replay_trade, candles, quotes, args, f"{flag}_old", **old_settings
    )
    new = simulate_policy(
        replay_trade, candles, quotes, args, f"{flag}_new", **new_settings
    )
    if (
        not old.complete
        or not new.complete
        or old.r_multiple is None
        or new.r_multiple is None
    ):
        return None, f"incomplete paired replay (old={old.note or old.exit_reason}; new={new.note or new.exit_reason})"
    return float(old.r_multiple) - float(new.r_multiple), None


def evaluate_paper_exit_rollbacks(
    trades: list[dict[str, Any]], candle_root: Path
) -> dict[str, dict[str, Any]]:
    closed = [
        trade for trade in trades
        if str(trade.get("status", "")).lower() == "closed"
    ]
    summaries: dict[str, dict[str, Any]] = {}
    for flag in EXIT_FLAGS:
        tagged = sorted(
            (trade for trade in closed if flag in _trade_flags(trade)),
            key=lambda row: (
                _parse_time(row.get("closed_at") or row.get("timestamp"))
                or datetime.min.replace(tzinfo=IST),
                str(row.get("trade_id") or ""),
            ),
        )
        reasons: list[str] = []
        events: list[str] = []
        if flag == "runner_gap_v2":
            trade_sessions = sorted(
                {session for trade in closed if (session := _trade_session(trade))}
            )
            window_sessions = trade_sessions[-5:]
            runner_trades = [
                trade for trade in tagged
                if _trade_session(trade) in window_sessions
                and (_number(trade.get("max_favorable_r")) or 0.0) >= 2.0
            ]
            runner_drawdowns = []
            for trade in runner_trades:
                risk = _planned_risk(trade)
                pnl = _trade_pnl(trade)
                peak = _number(trade.get("max_favorable_r"))
                if risk and pnl is not None and peak is not None:
                    exit_r = pnl / risk
                    if peak - exit_r > 1.0:
                        runner_drawdowns.append(trade)
            if len(window_sessions) >= 5 and len(runner_drawdowns) > 2:
                reasons.append(
                    f"{len(runner_drawdowns)} runner exits more than 1R below peak "
                    f"after 2R activation in the last five closed-trade sessions"
                )
            events.append(
                f"runner_drawdowns={len(runner_drawdowns)} "
                f"closed_trade_sessions={len(window_sessions)}/5"
            )

        oversized = []
        daily_pnl: dict[str, float] = {}
        for trade in tagged:
            pnl = _trade_pnl(trade)
            risk = _planned_risk(trade)
            if pnl is not None and risk is not None and pnl < -1.5 * risk:
                oversized.append(trade)
            session = _trade_session(trade)
            if pnl is not None and session:
                daily_pnl[session] = daily_pnl.get(session, 0.0) + pnl
        if oversized:
            reasons.append(
                f"trade {oversized[0].get('trade_id', 'unknown')} lost more than "
                "1.5x planned risk"
            )
        loss_days = [
            (session, pnl) for session, pnl in daily_pnl.items() if pnl <= -6000.0
        ]
        if loss_days:
            session, pnl = sorted(loss_days)[0]
            reasons.append(
                f"tagged day loss reached INR 6000 on {session} (P&L {pnl:.2f})"
            )
        events.append(
            f"risk_overruns={len(oversized)} "
            f"days_at_or_below_-6000={len(loss_days)}"
        )

        comparison_count = 0
        old_better_count = 0
        comparison_missing = 0
        if flag in {"profit_lock_v2", "trail_close_confirm_v2"}:
            first_ten = tagged[:10]
            for trade in first_ten:
                delta_r, missing_reason = _counterfactual_delta_r(
                    trade, flag, candle_root
                )
                if delta_r is None:
                    comparison_missing += 1
                    continue
                comparison_count += 1
                if delta_r > 0.5:
                    old_better_count += 1
            if len(tagged) >= 10 and old_better_count > 3:
                reasons.append(
                    f"old rule would have exited more than 0.5R better in "
                    f"{old_better_count} of the first ten tagged trades"
                )
            events.append(
                f"first_ten_old_rule_better={old_better_count} "
                f"paired={comparison_count}/10 missing={comparison_missing} "
                f"tagged={len(tagged)}/10"
            )

        summaries[flag] = {
            "tagged_trades": len(tagged),
            "rollback_reasons": reasons,
            "checks": events,
            "rollback_required": bool(reasons),
        }
    return summaries
