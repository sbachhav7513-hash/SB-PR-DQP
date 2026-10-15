from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from .trade_journal import PaperTradingRecorder, normalize_decision_outcome


logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
MIN_CLOSED_TRADES_FOR_SCREENING = 10


def _load_jsonl(path: Path, days: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    records: List[Dict[str, Any]] = []
    valid_records: List[tuple[datetime, Dict[str, Any]]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    timestamp_raw = str(record.get("timestamp", "")).replace("Z", "+00:00")
                    if not timestamp_raw:
                        continue
                    timestamp = datetime.fromisoformat(timestamp_raw)
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    valid_records.append((timestamp.astimezone(timezone.utc), record))
                except (json.JSONDecodeError, TypeError, ValueError):
                    logger.warning("Skipping invalid record in %s at line %s", path, line_number)
    except OSError:
        logger.exception("Could not read %s", path)

    if not valid_records:
        return []

    latest_timestamp = max(timestamp for timestamp, _ in valid_records)
    fallback_cutoff = latest_timestamp - timedelta(days=days)
    for timestamp, record in valid_records:
        if timestamp > cutoff:
            records.append(record)
    if records:
        return records

    for timestamp, record in valid_records:
        if timestamp >= fallback_cutoff:
            records.append(record)
    return records


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _recorded_trade_pnl(trade: Dict[str, Any]) -> float:
    value = trade.get("pnl_rupees")
    if value in (None, ""):
        value = trade.get("pnl", trade.get("profit", 0))
    return _number(value)


def _learning_feedback(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize repeated realized loss patterns without changing strategy settings."""
    grouped: Dict[str, List[float]] = defaultdict(list)
    pnls = []
    for trade in trades:
        pnl = _recorded_trade_pnl(trade)
        pnls.append(pnl)
        reason = str(
            trade.get("exit_reason_category") or trade.get("reason") or "UNKNOWN"
        ).strip().upper()
        grouped[reason or "UNKNOWN"].append(pnl)

    loss_patterns = []
    for reason, reason_pnls in grouped.items():
        losses = sum(1 for pnl in reason_pnls if pnl < 0)
        total_pnl = sum(reason_pnls)
        if losses < 2 or total_pnl >= 0:
            continue
        loss_patterns.append(
            {
                "exit_reason": reason,
                "trades": len(reason_pnls),
                "losses": losses,
                "recorded_pnl_before_costs": round(total_pnl, 2),
                "average_recorded_pnl_before_costs": round(
                    total_pnl / len(reason_pnls), 2
                ),
            }
        )
    loss_patterns.sort(key=lambda item: item["recorded_pnl_before_costs"])

    trade_count = len(trades)
    if trade_count == 0:
        status = "no_closed_trades"
        recommendation = (
            "No closed-trade outcomes are available; keep collecting paper evidence. "
            "No strategy settings are changed automatically."
        )
    elif trade_count < MIN_CLOSED_TRADES_FOR_SCREENING:
        status = "collecting_evidence"
        recommendation = (
            f"{trade_count}/{MIN_CLOSED_TRADES_FOR_SCREENING} closed trades: "
            "below the minimum screening sample. Treat loss patterns as review "
            "hypotheses; do not tune strategy settings from this sample."
        )
    else:
        status = "minimum_screening_sample_met"
        recommendation = (
            "The minimum screening count is met, not proof of an edge. Validate any "
            "candidate change with walk-forward replay and realistic costs; no "
            "strategy settings are changed automatically."
        )

    return {
        "status": status,
        "closed_trades": trade_count,
        "minimum_closed_trades_for_screening": MIN_CLOSED_TRADES_FOR_SCREENING,
        "recorded_pnl_before_costs": round(sum(pnls), 2),
        "average_recorded_pnl_before_costs": (
            round(sum(pnls) / trade_count, 2) if trade_count else 0.0
        ),
        "loss_patterns_for_review": loss_patterns,
        "automatic_strategy_changes": False,
        "recommendation": recommendation,
    }


def _recent_parquet_records(
    root: Path,
    filename: str,
    days: int,
    columns: List[str],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in sorted(root.glob(f"*/*/day_*/{filename}")):
        try:
            rows = PaperTradingRecorder._read_parquet(path, columns=columns)
        except Exception:
            try:
                rows = PaperTradingRecorder._read_parquet(path)
            except Exception:
                logger.exception("Could not read paper journal %s", path)
                continue
        for row in rows:
            for field in ("reasons", "news_headlines"):
                value = row.get(field)
                if isinstance(value, str):
                    try:
                        row[field] = json.loads(value)
                    except json.JSONDecodeError:
                        row[field] = [value] if value else []
            records.append(row)

    valid_records: List[tuple[datetime, Dict[str, Any]]] = []
    for record in records:
        try:
            timestamp_raw = str(record.get("timestamp", "")).replace("Z", "+00:00")
            timestamp = datetime.fromisoformat(timestamp_raw)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            valid_records.append((timestamp.astimezone(timezone.utc), record))
        except (TypeError, ValueError):
            continue
    if not valid_records:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = [record for timestamp, record in valid_records if timestamp > cutoff]
    if recent:
        return recent

    latest_timestamp = max(timestamp for timestamp, _ in valid_records)
    fallback_cutoff = latest_timestamp - timedelta(days=days)
    return [
        record for timestamp, record in valid_records
        if timestamp >= fallback_cutoff
    ]


def _load_report_records(
    data_dir: Path,
    paper_data_dir: Path,
    jsonl_name: str,
    parquet_name: str,
    days: int,
    columns: List[str],
) -> List[Dict[str, Any]]:
    parquet_records = _recent_parquet_records(
        paper_data_dir, parquet_name, days, columns
    )
    if parquet_records:
        return parquet_records
    return _load_jsonl(data_dir / jsonl_name, days)


def _performance_by_key(
    trades: List[Dict[str, Any]], key_name: str
) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[float]] = defaultdict(list)
    for trade in trades:
        if key_name == "hour":
            try:
                key = str(
                    PaperTradingRecorder._event_datetime(
                        trade.get("timestamp", "")
                    ).hour
                )
            except (TypeError, ValueError):
                continue
        else:
            value = trade.get(key_name)
            key = str(value or ("primary" if key_name == "strategy_variant" else "UNKNOWN"))
        grouped[key].append(_recorded_trade_pnl(trade))

    performance: Dict[str, Dict[str, Any]] = {}
    for key, pnls in grouped.items():
        wins = sum(1 for pnl in pnls if pnl > 0)
        performance[key] = {
            "trades": len(pnls),
            "wins": wins,
            "losses": len(pnls) - wins,
            "win_rate": round(wins / len(pnls) * 100, 2),
            "total_pnl": round(sum(pnls), 2),
        }
    return performance


def _option_exit_comparison(
    trades: List[Dict[str, Any]], days: int
) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        ticker = str(trade.get("ticker", "")).upper()
        if not ticker.endswith(("_CE", "_PE")):
            continue
        strategy = trade.get("exit_strategy")
        if strategy not in {
            "tiered_milestone",
            "paper_option_2r_trail_runner",
        }:
            strategy = "fixed_20pct_baseline"
        grouped[strategy].append(trade)

    return {
        strategy: _option_exit_metrics(strategy_trades, days)
        for strategy, strategy_trades in grouped.items()
    }


def _option_exit_metrics(
    trades: List[Dict[str, Any]], days: int
) -> Dict[str, Any]:
    closed = [trade for trade in trades if trade.get("status") == "closed"]
    pnls = []
    for trade in closed:
        pnl_value = trade.get("pnl_rupees")
        if pnl_value in (None, ""):
            pnl_value = trade.get("pnl", trade.get("profit", 0))
        pnls.append(_number(pnl_value))
    return {
        "trade_entries": len(trades),
        "entries_per_day": round(len(trades) / days, 2) if days > 0 else 0.0,
        "closed_trades": len(closed),
        "average_pnl_per_trade": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        "total_pnl": round(sum(pnls), 2),
    }


def _load_filter_stats(
    root: Path, days: int, decisions: List[Dict[str, Any]]
) -> Dict[str, int]:
    names = (
        "volatility_rejected",
        "confirmation_rejected",
        "cooldown_rejected",
        "hours_rejected",
        "threshold_rejected",
    )
    stats = {name: 0 for name in names}
    stats["approved_entries"] = 0
    stats["option_rejected"] = 0
    stats["risk_rejected"] = 0
    stats["execution_failures"] = 0
    if decisions:
        for entry in decisions:
            outcome = str(entry.get("outcome", ""))
            detail = str(entry.get("outcome_detail") or outcome)
            category = normalize_decision_outcome(outcome)
            if category == "trade_opened":
                stats["approved_entries"] += 1
            elif category == "accuracy_filter" or detail.startswith("accuracy_filter_rejected:"):
                reason = str(entry.get("rejection_reason", "")) or detail.split(":", 1)[-1]
                if reason == "volatility":
                    stats["volatility_rejected"] += 1
                elif reason == "confirmation":
                    stats["confirmation_rejected"] += 1
                elif reason == "cooldown":
                    stats["cooldown_rejected"] += 1
                elif reason == "trading_hours":
                    stats["hours_rejected"] += 1
                else:
                    stats["threshold_rejected"] += 1
            elif category == "option_filter" or detail.startswith("OPTION_FILTER_"):
                stats["option_rejected"] += 1
            elif category == "risk_blocked":
                stats["risk_rejected"] += 1
            elif category == "execution_failed":
                stats["execution_failures"] += 1
        stats["total_rejected"] = sum(stats[name] for name in names) + sum(
            stats[name]
            for name in ("option_rejected", "risk_rejected", "execution_failures")
        )
        return stats

    for entry in _load_jsonl(root / "filter_log.jsonl", days):
        if entry.get("action") == "APPROVED":
            stats["approved_entries"] += 1
        elif entry.get("action") == "REJECTED" and entry.get("filter") in stats:
            stats[entry["filter"]] += 1
    stats["total_rejected"] = sum(stats[name] for name in names)
    return stats


def build_weekly_report(
    data_dir: str = ".",
    days: int = 7,
    paper_data_dir: str | None = None,
) -> Dict[str, Any]:
    root = Path(data_dir)
    paper_root = Path(paper_data_dir) if paper_data_dir else root / "paper_trading_data"
    trade_records = _load_report_records(
        root,
        paper_root,
        "trades.jsonl",
        "trades.parquet",
        days,
        [
            "timestamp", "ticker", "action", "status", "pnl", "pnl_rupees",
            "strategy_variant", "exit_strategy", "reason", "exit_reason_category",
        ],
    )
    trades = [trade for trade in trade_records if trade.get("status") == "closed"]
    decisions = _load_report_records(
        root,
        paper_root,
        "decision_log.jsonl",
        "decisions.parquet",
        days,
        [
            "timestamp", "ticker", "signal", "outcome", "score", "reasons",
            "outcome_detail", "rejection_reason", "market_session", "market_hours",
            "session_timezone", "strategy_variant",
        ],
    )

    grouped: Dict[str, List[float]] = defaultdict(list)
    for trade in trades:
        key = f"{trade.get('ticker', 'UNKNOWN')}:{trade.get('action', 'UNKNOWN')}"
        grouped[key].append(_recorded_trade_pnl(trade))

    profiles: List[Dict[str, Any]] = []
    for key, pnls in grouped.items():
        if len(pnls) < MIN_CLOSED_TRADES_FOR_SCREENING:
            continue
        wins = sum(1 for pnl in pnls if pnl > 0)
        profiles.append({
            "profile": key,
            "trades": len(pnls),
            "win_rate": round(wins / len(pnls) * 100, 2),
            "total_pnl": round(sum(pnls), 2),
            "average_pnl": round(sum(pnls) / len(pnls), 2),
        })
    profiles.sort(key=lambda item: item["average_pnl"], reverse=True)

    pnl_values = [_recorded_trade_pnl(trade) for trade in trades]
    wins = [pnl for pnl in pnl_values if pnl > 0]
    losses = [pnl for pnl in pnl_values if pnl <= 0]
    total_loss = sum(losses)
    outcome_counts: Dict[str, int] = defaultdict(int)
    market_session_counts: Dict[str, int] = defaultdict(int)
    for decision in decisions:
        outcome_counts[normalize_decision_outcome(decision.get("outcome", "UNKNOWN"))] += 1
        session = decision.get("market_session")
        if not session:
            event_time = PaperTradingRecorder._event_datetime(decision.get("timestamp", ""))
            local_time = event_time.time()
            session = (
                "regular_session" if time(9, 15) <= local_time < time(15, 30)
                else "before_open" if local_time < time(9, 15)
                else "after_close"
            )
        market_session_counts[str(session)] += 1
    news_risk_counts = {
        level: sum(
            1 for item in decisions
            if item.get("news_risk", "UNKNOWN") == level
        )
        for level in ("NORMAL", "ELEVATED", "HIGH", "UNKNOWN", "DISABLED")
    }
    news_suppressed_entries = sum(
        1 for item in decisions
        if any("news risk" in reason.lower() for reason in item.get("reasons", []))
    )
    learning_feedback = _learning_feedback(trades)
    rejected_entries = sum(
        outcome_counts[name]
        for name in ("accuracy_filter", "option_filter", "risk_blocked", "execution_failed")
    )
    approved_entries = outcome_counts["trade_opened"]
    non_entry_decisions = len(decisions) - approved_entries - rejected_entries
    return {
        "generated_at": datetime.now(IST).isoformat(timespec="seconds"),
        "session_timezone": IST.key,
        "market_session_hours": {"open": "09:15", "close": "15:30"},
        "period_days": days,
        "closed_trades": len(trades),
        "total_pnl": round(sum(pnl_values), 2),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(
            sum(1 for pnl in pnl_values if pnl > 0) / len(pnl_values) * 100, 2
        ) if pnl_values else 0.0,
        "average_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "average_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "largest_win": round(max(pnl_values), 2) if pnl_values else 0.0,
        "largest_loss": round(min(pnl_values), 2) if pnl_values else 0.0,
        "profit_factor": round(sum(wins) / abs(total_loss), 2) if total_loss else 0.0,
        "decisions_recorded": len(decisions),
        "signal_counts": {
            signal: sum(1 for item in decisions if item.get("signal") == signal)
            for signal in ("BUY", "SELL", "HOLD", "ERROR")
        },
        "outcome_counts": dict(outcome_counts),
        "market_session_counts": dict(market_session_counts),
        "decision_reconciliation": {
            "approved_entries": approved_entries,
            "classified_rejections": rejected_entries,
            "non_entry_decisions": non_entry_decisions,
            "accounted_decisions": approved_entries + rejected_entries + non_entry_decisions,
            "matches_decisions_recorded": (
                approved_entries + rejected_entries + non_entry_decisions == len(decisions)
            ),
        },
        "performance_by_symbol": _performance_by_key(trades, "ticker"),
        "performance_by_hour": _performance_by_key(trades, "hour"),
        "performance_by_strategy_variant": _performance_by_key(
            trades, "strategy_variant"
        ),
        "option_exit_comparison": _option_exit_comparison(trade_records, days),
        "filter_stats": _load_filter_stats(root, days, decisions),
        "news_summary": {
            "risk_counts": news_risk_counts,
            "suppressed_entries": news_suppressed_entries,
        },
        "best_observed_profiles": profiles[:5],
        "pnl_basis": "Recorded paper P&L; brokerage, taxes, and slippage are not deducted.",
        "learning_feedback": learning_feedback,
        "recommendation": learning_feedback["recommendation"],
    }


def summarize_best_setup_windows(
    data_dir: str = ".",
    days: int = 7,
    paper_data_dir: str | None = None,
) -> List[Dict[str, Any]]:
    """Find the strongest daily time-direction windows based on recent trade records."""
    root = Path(data_dir)
    paper_root = Path(paper_data_dir) if paper_data_dir else root / "paper_trading_data"
    trades = [
        trade for trade in _load_report_records(
            root,
            paper_root,
            "trades.jsonl",
            "trades.parquet",
            days,
            [
                "timestamp", "ticker", "action", "status", "pnl", "pnl_rupees",
            ],
        )
        if trade.get("status") == "closed"
    ]
    if not trades:
        return []

    grouped: Dict[str, List[float]] = defaultdict(list)
    for trade in trades:
        try:
            stamp = PaperTradingRecorder._event_datetime(trade.get("timestamp", ""))
        except (TypeError, ValueError):
            continue
        hour = stamp.hour
        label = f"{hour:02d}:{trade.get('action', 'UNKNOWN')}"
        grouped[label].append(_recorded_trade_pnl(trade))

    summaries: List[Dict[str, Any]] = []
    for label, pnls in grouped.items():
        wins = sum(1 for pnl in pnls if pnl > 0)
        total = sum(pnls)
        if len(pnls) < MIN_CLOSED_TRADES_FOR_SCREENING:
            continue
        summaries.append({
            "label": label,
            "trades": len(pnls),
            "wins": wins,
            "losses": len(pnls) - wins,
            "win_rate": round((wins / len(pnls)) * 100.0, 2),
            "total_pnl": round(total, 2),
            "average_pnl": round(total / len(pnls), 2),
        })

    summaries.sort(key=lambda item: (item["win_rate"], item["average_pnl"]), reverse=True)
    return summaries[:5]


def write_weekly_report(
    data_dir: str = ".",
    days: int = 7,
    output_dir: str = ".",
    paper_data_dir: str | None = None,
) -> Path:
    report = build_weekly_report(data_dir, days, paper_data_dir)
    report["best_setup_windows"] = summarize_best_setup_windows(
        data_dir, days, paper_data_dir
    )
    destination = Path(output_dir) / f"weekly_report_{datetime.now():%Y_%m_%d}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        temporary.replace(destination)
    except OSError:
        logger.exception("Could not publish weekly report to %s", destination)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return destination


def _date_records(
    path: Path,
    paper_data_dir: Path,
    parquet_name: str,
    target_date,
) -> List[Dict[str, Any]]:
    records = _recent_parquet_records(
        paper_data_dir,
        parquet_name,
        days=3660,
        columns=(
            [
                "timestamp", "status", "pnl", "pnl_rupees", "reason",
                "exit_reason_category", "ticker", "action", "score",
                "strategy_variant",
            ]
            if parquet_name == "trades.parquet"
            else [
                "timestamp", "signal", "outcome", "score", "reasons",
                "outcome_detail", "rejection_reason", "trend_shadow_signal",
                "trend_shadow_rejection_reason", "strategy_variant",
            ]
        ),
    )
    if not records:
        records = _load_jsonl(path, days=3660)
    return [
        record for record in records
        if PaperTradingRecorder._event_datetime(record.get("timestamp")).date() == target_date
    ]


def write_daily_summary(
    data_dir: str = ".", paper_data_dir: str = "paper_trading_data", target_date=None
) -> Path:
    """Write a compact compressed Parquet snapshot for the paper-trading session."""
    now = datetime.now()
    target_date = target_date or now.date()
    trades = [
        trade for trade in _date_records(
            Path(data_dir) / "trades.jsonl",
            Path(paper_data_dir),
            "trades.parquet",
            target_date,
        )
        if trade.get("status") == "closed"
    ]
    decisions = _date_records(
        Path(data_dir) / "decision_log.jsonl",
        Path(paper_data_dir),
        "decisions.parquet",
        target_date,
    )
    pnls = [_recorded_trade_pnl(trade) for trade in trades]
    values = {
        "date": target_date.isoformat(),
        "closed_trades": len(trades),
        "winning_trades": sum(1 for pnl in pnls if pnl > 0),
        "losing_trades": sum(1 for pnl in pnls if pnl <= 0),
        "total_pnl": round(sum(pnls), 2),
        "average_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        "decisions_recorded": len(decisions),
        "buy_signals": sum(1 for item in decisions if item.get("signal") == "BUY"),
        "sell_signals": sum(1 for item in decisions if item.get("signal") == "SELL"),
        "hold_signals": sum(1 for item in decisions if item.get("signal") == "HOLD"),
        "stop_loss_exits": sum(1 for trade in trades if trade.get("reason") == "STOP_LOSS"),
        "take_profit_exits": sum(1 for trade in trades if trade.get("reason") == "TAKE_PROFIT"),
    }
    recorder = PaperTradingRecorder(paper_data_dir)
    destination = recorder._day_path(
        datetime.combine(target_date, datetime.min.time()).isoformat(), "daily_summary.parquet"
    )
    recorder._write_parquet(
        destination,
        [{"metric": key, "value": value} for key, value in values.items()],
        ["metric", "value"],
    )
    return destination


def write_daily_review(
    data_dir: str = ".", paper_data_dir: str = "paper_trading_data", target_date=None
) -> Path:
    """Write a human-readable, date-scoped review of trades and entry decisions."""
    target_date = target_date or datetime.now(IST).date()
    trades = [
        trade
        for trade in _date_records(
            Path(data_dir) / "trades.jsonl",
            Path(paper_data_dir),
            "trades.parquet",
            target_date,
        )
        if trade.get("status") == "closed"
    ]
    decisions = _date_records(
        Path(data_dir) / "decision_log.jsonl",
        Path(paper_data_dir),
        "decisions.parquet",
        target_date,
    )

    pnls = [_recorded_trade_pnl(trade) for trade in trades]
    wins = sum(1 for pnl in pnls if pnl > 0)
    signal_counts: Dict[str, int] = defaultdict(int)
    outcome_counts: Dict[str, int] = defaultdict(int)
    rejection_counts: Dict[str, int] = defaultdict(int)
    hold_reasons: Dict[str, int] = defaultdict(int)
    shadow_rejections: Dict[str, int] = defaultdict(int)
    shadow_candidates = 0
    option_leg_skips = 0
    has_shadow_telemetry = any(
        "trend_shadow_signal" in item or "trend_shadow_rejection_reason" in item
        for item in decisions
    )

    for decision in decisions:
        signal = str(decision.get("signal") or "UNKNOWN")
        signal_counts[signal] += 1
        outcome = normalize_decision_outcome(decision.get("outcome"))
        outcome_counts[outcome] += 1
        detail = str(decision.get("outcome_detail") or decision.get("outcome") or "")
        if detail == "OPTION_LEG_SKIPPED":
            option_leg_skips += 1
        if outcome in {"accuracy_filter", "option_filter", "risk_blocked", "execution_failed"}:
            rejection_counts[detail or outcome] += 1

        if signal == "HOLD":
            reasons = decision.get("reasons") or []
            if isinstance(reasons, str):
                try:
                    reasons = json.loads(reasons)
                except json.JSONDecodeError:
                    reasons = [reasons]
            if isinstance(reasons, list):
                for reason in reasons:
                    if reason:
                        hold_reasons[str(reason)] += 1

        shadow_signal = decision.get("trend_shadow_signal")
        if shadow_signal in {"BUY", "SELL"}:
            shadow_candidates += 1
        shadow_rejection = decision.get("trend_shadow_rejection_reason")
        if shadow_rejection:
            shadow_rejections[str(shadow_rejection)] += 1

    def format_counts(counts: Dict[str, int]) -> List[str]:
        return (
            [f"- {name}: {count}" for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
            if counts
            else ["- None recorded"]
        )

    win_rate = wins / len(trades) * 100 if trades else 0.0
    recorder = PaperTradingRecorder(paper_data_dir)
    destination = recorder._day_path(
        datetime.combine(target_date, datetime.min.time()).isoformat(),
        "daily_review.md",
    )
    lines = [
        f"# Daily Paper-Trading Review - {target_date:%Y-%m-%d}",
        "",
        "## Results",
        f"- Closed trades: {len(trades)}",
        f"- Wins / losses: {wins} / {len(trades) - wins}",
        f"- Recorded P&L before unmodeled trading costs: {sum(pnls):.2f}",
        f"- Win rate: {win_rate:.1f}%",
        f"- Decisions: {len(decisions)}",
        "",
        "## Signals",
        *format_counts(signal_counts),
        "",
        "## Entry Flow",
        f"- BUY/SELL signals: {signal_counts['BUY'] + signal_counts['SELL']}",
        f"- Unselected option-leg skips: {option_leg_skips}",
        f"- Side-eligible directional candidates: {max(signal_counts['BUY'] + signal_counts['SELL'] - option_leg_skips, 0)}",
        f"- Entries opened: {outcome_counts['trade_opened']}",
        "",
        "## Outcomes",
        *format_counts(outcome_counts),
        "",
        "## Closed Trades",
        "| Symbol | Direction | Variant | Score | Milestone | Held (s) | Recorded P&L | Exit reason |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    if trades:
        lines.extend(
            "| {ticker} | {action} | {variant} | {score} | {milestone} | {held} | {pnl:.2f} | {reason} |".format(
                ticker=str(trade.get("ticker") or "UNKNOWN").replace("|", "/"),
                action=str(trade.get("action") or "UNKNOWN").replace("|", "/"),
                variant=str(trade.get("strategy_variant") or "primary").replace("|", "/"),
                score=trade.get("score") or "N/A",
                milestone=(
                    f"{_number(trade['milestone_reached_pct']):.1f}%"
                    if trade.get("milestone_reached_pct") not in (None, "")
                    else "N/A"
                ),
                held=(
                    int(_number(trade.get("holding_time_seconds", trade.get("duration_seconds"))))
                    if trade.get("holding_time_seconds", trade.get("duration_seconds"))
                    not in (None, "")
                    else "N/A"
                ),
                pnl=_number(trade.get("pnl", trade.get("profit", 0))),
                reason=str(
                    trade.get("exit_reason_category") or trade.get("reason") or "UNKNOWN"
                ).replace("|", "/"),
            )
            for trade in trades
        )
    else:
        lines.append("| No closed trades | - | - | - | - | - | 0.00 | - |")
    learning_feedback = _learning_feedback(trades)
    loss_patterns = learning_feedback["loss_patterns_for_review"]
    lines.extend(
        [
            "",
            "## Learning Feedback",
            f"- Status: {learning_feedback['status']} "
            f"({learning_feedback['closed_trades']}/"
            f"{learning_feedback['minimum_closed_trades_for_screening']} closed trades "
            "for the minimum screening sample).",
            f"- {learning_feedback['recommendation']}",
            (
                "- Repeated losing exit patterns to review: "
                + "; ".join(
                    f"{item['exit_reason']} ({item['losses']} losses / "
                    f"{item['trades']} trades, "
                    f"{item['recorded_pnl_before_costs']:.2f} before costs)"
                    for item in loss_patterns
                )
                if loss_patterns
                else "- No repeated losing exit pattern (at least two losses) in this sample."
            ),
            "- These patterns are descriptive, not causal; paper P&L excludes unmodeled brokerage, taxes, and slippage.",
            "- No strategy or configuration settings are changed automatically.",
        ]
    )
    lines.extend(
        [
            "",
            "### Entry Rejections",
            *format_counts(rejection_counts),
            "",
            "## HOLD Reasons",
            *format_counts(hold_reasons),
            "",
            "## Paper Shadow",
        ]
    )
    if has_shadow_telemetry:
        lines.extend(
            [f"- Directional candidates: {shadow_candidates}", "- Rejection reasons:", *format_counts(shadow_rejections)]
        )
    else:
        lines.append("- Shadow fields are absent from this archive; verify the running bot version and configuration.")
    lines.extend(
        [
            "",
            "## Review Notes",
            "- Reason counts are mentions; one decision may contain multiple reasons.",
            (
                "- With no closed trades, assess candidate and rejection flow only; do not infer strategy accuracy."
                if not trades
                else f"- The {len(trades)} closed-trade daily sample is below the "
                f"{MIN_CLOSED_TRADES_FOR_SCREENING}-trade screening minimum; do not "
                "infer a durable edge."
                if len(trades) < MIN_CLOSED_TRADES_FOR_SCREENING
                else "- The daily screening count is met, but one session is not proof of a durable edge."
            ),
            "- Change at most one paper-only strategy/filter variable after a cost-aware, out-of-sample review.",
            "",
        ]
    )
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def write_weekly_review(
    data_dir: str = ".", paper_data_dir: str = "paper_trading_data", days: int = 7
) -> Path:
    """Write a human-readable review with evidence-based improvement prompts."""
    report = build_weekly_report(data_dir, days, paper_data_dir)
    now = datetime.now()
    recorder = PaperTradingRecorder(paper_data_dir)
    day_path = recorder._day_path(now.isoformat(), "daily_summary.parquet")
    destination = day_path.parent.parent / f"weekly_review_{now:%Y_%m_%d}.md"
    issues: List[str] = []
    improvements: List[str] = []
    if report["closed_trades"] == 0:
        issues.append("No closed trades were recorded; paper-trading data is insufficient for strategy conclusions.")
        improvements.append("Continue paper trading and verify that entry and exit events are being recorded.")
    elif report["closed_trades"] < MIN_CLOSED_TRADES_FOR_SCREENING:
        issues.append(
            f"Only {report['closed_trades']} closed trades were recorded; "
            f"the {MIN_CLOSED_TRADES_FOR_SCREENING}-trade screening minimum is not met."
        )
        if report["total_pnl"] < 0:
            issues.append(
                "Recorded period P&L is negative before separately modeled trading costs."
            )
        improvements.append(
            "Treat repeated losing patterns as review hypotheses, continue paper "
            "trading, and do not tune thresholds from this sample."
        )
    elif report["total_pnl"] < 0:
        issues.append(f"The period finished negative at {report['total_pnl']:.2f} P&L.")
        improvements.append(
            "Review losing trades and validate one candidate change in a walk-forward "
            "replay with realistic costs before changing parameters."
        )
    if report["closed_trades"] and report["win_rate"] < 50:
        issues.append(
            f"Win rate was {report['win_rate']:.2f}%; inspect loss clusters, "
            "not win rate alone."
        )
        improvements.append(
            "Compare expectancy and loss size after realistic costs; do not raise "
            "the score threshold from win rate alone."
        )
    if report["signal_counts"].get("ERROR", 0):
        issues.append(f"Strategy evaluation errors occurred {report['signal_counts']['ERROR']} times.")
        improvements.append("Investigate every strategy error before relying on live alerts.")
    if not issues:
        issues.append("No major negative pattern was detected by the current automated checks.")
        improvements.append(
            "Keep collecting paper-trading data; do not treat the highest observed "
            "profile as a strategy recommendation."
        )

    lines = [
        f"# Paper Trading Review - {now:%Y-%m-%d}",
        "",
        "## Observed Results",
        f"- Closed trades: {report['closed_trades']}",
        f"- Recorded P&L before unmodeled trading costs: {report['total_pnl']:.2f}",
        f"- Win rate: {report['win_rate']:.2f}%",
        f"- Decisions recorded: {report['decisions_recorded']}",
        f"- High-news-risk decisions: {report['news_summary']['risk_counts'].get('HIGH', 0)}",
        f"- Entries suppressed by news filter: {report['news_summary']['suppressed_entries']}",
        f"- Learning feedback: {report['learning_feedback']['status']} "
        f"({report['learning_feedback']['closed_trades']}/"
        f"{report['learning_feedback']['minimum_closed_trades_for_screening']} trades)",
        f"- Feedback: {report['learning_feedback']['recommendation']}",
        "- Recorded paper P&L does not deduct brokerage, taxes, or slippage.",
        "",
        "## Option Exit Strategy Comparison",
        "| Strategy | Entries | Entries/day | Closed trades | Average recorded P&L/closed trade | Total recorded P&L |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        *(
            [
                "| {strategy} | {trade_entries} | {entries_per_day:.2f} | {closed_trades} | {average_pnl_per_trade:.2f} | {total_pnl:.2f} |".format(
                    strategy=str(strategy).replace("|", "/"),
                    **metrics,
                )
                for strategy, metrics in sorted(report["option_exit_comparison"].items())
            ]
            or ["| No option trades recorded | - | - | - | - | - |"]
        ),
        "Legacy option trades without an exit-strategy tag are grouped as the fixed-20% baseline; compare sample counts before drawing conclusions.",
        "",
        "## What Needs Attention",
        *[f"- {issue}" for issue in issues],
        "",
        "## Recommended Improvements",
        *[f"- {improvement}" for improvement in improvements],
        "",
        "## Review Before Changing",
        "- Compare the daily trades.parquet files for the week, not just the aggregate P&L.",
        "- Check whether losses cluster by symbol, BUY/SELL direction, time, or exit reason.",
        "- Do not change a strategy or risk parameter from low-sample patterns; paper P&L is pre-cost.",
        "- No parameter or live-order setting is changed automatically by learning feedback.",
        "",
    ]
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination