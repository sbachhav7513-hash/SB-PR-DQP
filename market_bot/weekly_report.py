from __future__ import annotations

import json
import logging
import math
import csv
import gzip
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import pandas as pd
from fastparquet import ParquetFile

from .trade_journal import (
    PaperTradingRecorder,
    normalize_decision_outcome,
    read_decisions,
)
from .stop_reentry_journal import FAILURE_BUCKETS, summarize_stop_events
from .paper_recovery import RECOVERY_COLUMNS, build_recovery_record
from .paper_exit_rollback import EXIT_FLAGS, evaluate_paper_exit_rollbacks
from .reporting_metrics import ReportingBudgetExceeded, ReportingStep


logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
MIN_CLOSED_TRADES_FOR_SCREENING = 10


def _load_jsonl(path: Path, days: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    def read_from(
        cutoff_time: datetime, inclusive: bool
    ) -> tuple[List[Dict[str, Any]], datetime | None]:
        records: List[Dict[str, Any]] = []
        latest_timestamp = None
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        timestamp_raw = str(record.get("timestamp", "")).replace(
                            "Z", "+00:00"
                        )
                        if not timestamp_raw:
                            continue
                        timestamp = datetime.fromisoformat(timestamp_raw)
                        if timestamp.tzinfo is None:
                            timestamp = timestamp.replace(tzinfo=timezone.utc)
                        timestamp = timestamp.astimezone(timezone.utc)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        logger.warning(
                            "Skipping invalid record in %s at line %s",
                            path,
                            line_number,
                        )
                        continue
                    latest_timestamp = max(
                        latest_timestamp or timestamp, timestamp
                    )
                    if (
                        timestamp >= cutoff_time
                        if inclusive
                        else timestamp > cutoff_time
                    ):
                        records.append(record)
        except OSError:
            logger.exception("Could not read %s", path)
        return records, latest_timestamp

    with ReportingStep(logger, f"weekly_jsonl_{path.name}", [path]) as step:
        records, latest_timestamp = read_from(cutoff, inclusive=False)
        if not records and latest_timestamp is not None:
            records, _ = read_from(
                latest_timestamp - timedelta(days=days), inclusive=True
            )
        step.rows = len(records)
        step.columns = sorted(
            {column for record in records for column in record}
        )
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


def _optional_finite_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _trade_fee_total(trade: Dict[str, Any]) -> float | None:
    fees = trade.get("fees")
    if isinstance(fees, str):
        try:
            fees = json.loads(fees)
        except json.JSONDecodeError:
            fees = None
    if isinstance(fees, dict):
        total = _optional_finite_number(fees.get("total_fees"))
        if total is not None:
            return total
    return _optional_finite_number(trade.get("fees_rupees"))


def _trade_cost_values(trade: Dict[str, Any]) -> tuple[float, float | None, float | None]:
    gross = _optional_finite_number(trade.get("gross_pnl_rupees"))
    if gross is None:
        gross = _recorded_trade_pnl(trade)
    fees = _trade_fee_total(trade)
    net_value = trade.get("net_pnl")
    if net_value in (None, ""):
        net_value = trade.get("after_cost_pnl")
    net = _optional_finite_number(net_value)
    if net is None and fees is not None:
        net = gross - fees
    return gross, fees, net


def _option_leg(trade: Dict[str, Any]) -> str:
    leg = str(trade.get("option_leg") or "").upper()
    if leg in {"CE", "PE"}:
        return leg
    ticker = str(trade.get("ticker") or trade.get("symbol") or "").upper()
    if ticker.endswith(("_CE", "CE")):
        return "CE"
    if ticker.endswith(("_PE", "PE")):
        return "PE"
    return "UNKNOWN"


def _cost_performance(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    dimensions: Dict[str, Dict[str, Any]] = {
        "tier": {},
        "CE/PE": {},
        "exit_trigger": {},
    }
    for trade in trades:
        gross, fees, net = _trade_cost_values(trade)
        risk_multiple = _optional_finite_number(trade.get("r_multiple"))
        labels = {
            "tier": str(trade.get("tier") or "UNKNOWN"),
            "CE/PE": _option_leg(trade),
            "exit_trigger": str(
                trade.get("exit_trigger") or trade.get("reason") or "UNKNOWN"
            ),
        }
        for dimension, label in labels.items():
            row = dimensions[dimension].setdefault(
                label,
                {
                    "trades": 0,
                    "gross_pnl": 0.0,
                    "fees_sum": 0.0,
                    "fee_coverage": 0,
                    "net_pnl_sum": 0.0,
                    "net_coverage": 0,
                    "r_sum": 0.0,
                    "r_coverage": 0,
                },
            )
            row["trades"] += 1
            row["gross_pnl"] += gross
            if fees is not None:
                row["fees_sum"] += fees
                row["fee_coverage"] += 1
            if net is not None:
                row["net_pnl_sum"] += net
                row["net_coverage"] += 1
            if risk_multiple is not None:
                row["r_sum"] += risk_multiple
                row["r_coverage"] += 1
    for rows in dimensions.values():
        for row in rows.values():
            row["gross_pnl"] = round(row["gross_pnl"], 2)
            row["modeled_fees"] = (
                round(row.pop("fees_sum"), 2)
                if row["fee_coverage"]
                else None
            )
            if not row["fee_coverage"]:
                row.pop("fees_sum")
            row["net_pnl"] = (
                round(row.pop("net_pnl_sum"), 2)
                if row["net_coverage"]
                else None
            )
            if not row["net_coverage"]:
                row.pop("net_pnl_sum")
            row["total_r"] = (
                round(row.pop("r_sum"), 3)
                if row["r_coverage"]
                else None
            )
            if not row["r_coverage"]:
                row.pop("r_sum")
            row["average_r"] = (
                round(row["total_r"] / row["r_coverage"], 3)
                if row["r_coverage"]
                else None
            )
    return dimensions


def _human_command_affected(trades: List[Dict[str, Any]]) -> bool:
    for trade in trades:
        if _flag(trade.get("manual_exit")) or trade.get("exit_command"):
            return True
        events = trade.get("manual_exit_events")
        if isinstance(events, str):
            try:
                events = json.loads(events)
            except json.JSONDecodeError:
                events = []
        if isinstance(events, list) and events:
            return True
    return False


def _command_affected_trade(command: Dict[str, Any]) -> bool:
    text = str(command.get("text") or "").strip().lower()
    name = text.split(maxsplit=1)[0] if text else ""
    if name not in {"/exit", "/exitat", "/cancel", "/sl", "/be", "/target"}:
        return False
    result = str(command.get("response") or "").lower()
    return bool(result) and not any(
        marker in result
        for marker in ("usage:", "could not", "failed", "disabled", "not found")
    )


def _cost_totals(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    fee_values = [
        fees
        for trade in trades
        if (fees := _trade_fee_total(trade)) is not None
    ]
    net_values = [
        net
        for trade in trades
        if (net := _trade_cost_values(trade)[2]) is not None
    ]
    return {
        "gross_pnl": round(
            sum(_trade_cost_values(trade)[0] for trade in trades), 2
        ),
        "modeled_fees": round(sum(fee_values), 2) if fee_values else None,
        "net_pnl": round(sum(net_values), 2) if net_values else None,
        "fee_coverage": len(fee_values),
        "net_coverage": len(net_values),
        "trades": len(trades),
    }


def _cost_performance_lines(
    performance: Dict[str, Dict[str, Any]]
) -> List[str]:
    lines = [
        "| Dimension | Group | Trades | Gross P&L | Modeled fees | Net P&L | R total | Average R |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for dimension, groups in performance.items():
        for label, values in sorted(groups.items()):
            fees = (
                f"{values['modeled_fees']:.2f} "
                f"({values['fee_coverage']}/{values['trades']})"
                if values["modeled_fees"] is not None
                else "N/A"
            )
            net = (
                f"{values['net_pnl']:.2f} "
                f"({values['net_coverage']}/{values['trades']})"
                if values["net_pnl"] is not None
                else "N/A"
            )
            total_r = (
                f"{values['total_r']:.3f}"
                if values["total_r"] is not None
                else "N/A"
            )
            average_r = (
                f"{values['average_r']:.3f}"
                if values["average_r"] is not None
                else "N/A"
            )
            lines.append(
                f"| {dimension} | {label.replace('|', '/')} | "
                f"{values['trades']} | {values['gross_pnl']:.2f} | "
                f"{fees} | {net} | {total_r} | {average_r} |"
            )
    if len(lines) == 2:
        lines.append("| No closed trades | - | 0 | 0.00 | N/A | N/A | N/A | N/A |")
    return lines


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


def _quote_cost_coverage(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    quote_based_pnls = []
    for trade in trades:
        entry = _number(trade.get("entry"))
        quantity = _number(trade.get("quantity"))
        entry_bid = _number(trade.get("paper_entry_bid"))
        entry_ask = _number(trade.get("paper_entry_ask"))
        exit_ltp = _number(trade.get("paper_exit_ltp"))
        exit_bid = _number(trade.get("paper_exit_bid"))
        exit_ask = _number(trade.get("paper_exit_ask"))
        if (
            quantity <= 0
            or min(entry_bid, entry_ask, exit_ltp, exit_bid, exit_ask) <= 0
            or entry_bid > entry
            or entry > entry_ask
            or exit_bid > exit_ltp
            or exit_ltp > exit_ask
        ):
            continue
        quote_based_pnls.append((exit_bid - entry_ask) * quantity)

    return {
        "closed_trades": len(trades),
        "quote_consistent_trades": len(quote_based_pnls),
        "quote_based_pnl": round(sum(quote_based_pnls), 2),
    }


def _stop_risk_overruns(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    stop_losses = []
    for trade in trades:
        if str(trade.get("reason", "")).upper() != "STOP_LOSS":
            continue
        initial_risk = _number(trade.get("paper_entry_risk_rupees"))
        if initial_risk <= 0:
            continue
        loss = max(0.0, -_recorded_trade_pnl(trade))
        stop_losses.append(max(0.0, loss - initial_risk))

    return {
        "stop_losses_with_risk_data": len(stop_losses),
        "overrun_trades": sum(1 for overrun in stop_losses if overrun > 0.01),
        "total_overrun_rupees": round(sum(stop_losses), 2),
    }


def _recent_recovery_summary(paper_root: Path, days: int) -> Dict[str, Any]:
    cutoff = datetime.now(IST).date() - timedelta(days=max(days - 1, 0))
    records: Dict[str, Dict[str, Any]] = {}
    for path in paper_root.rglob("stop_out_recovery.parquet"):
        try:
            frame = pd.read_parquet(path, engine="fastparquet")
        except (OSError, ValueError, ImportError):
            logger.exception("Could not read stop-out recovery file %s", path)
            continue
        for row in frame.to_dict(orient="records"):
            exit_time = _parse_datetime(row.get("exit_time"))
            trade_id = str(row.get("trade_id") or "")
            if (
                not trade_id
                or exit_time is None
                or exit_time.date() < cutoff
                or exit_time.date() > datetime.now(IST).date()
            ):
                continue
            records[trade_id] = row
    recovered = list(records.values())
    return {
        "trades": len(recovered),
        "incomplete": sum(
            str(row.get("status", "")).lower() != "complete"
            for row in recovered
        ),
        "stop_within_5m": sum(_flag(row.get("stop_within_5m")) for row in recovered),
        "reclaimed_entry": sum(_flag(row.get("reclaimed_entry")) for row in recovered),
        "reached_plus_1r": sum(_flag(row.get("reached_plus_1r")) for row in recovered),
        "underlying_reversed": sum(
            _flag(row.get("underlying_reversed_to_close")) for row in recovered
        ),
    }


def _recent_parquet_records(
    root: Path,
    filename: str,
    days: int,
    columns: List[str],
    hourly_decisions_only: bool = False,
) -> List[Dict[str, Any]]:
    candidate_records: List[Dict[str, Any]] = []
    day_dirs = _recent_day_directories(root, days)
    for day_dir in day_dirs:
        if filename == "decisions.parquet":
            sources = _decision_source_files(
                day_dir, hourly_only=hourly_decisions_only
            )
            try:
                with ReportingStep(
                    logger,
                    f"weekly_decisions_{day_dir.name}",
                    sources,
                    columns,
                ) as step:
                    frame = read_decisions(
                        day_dir,
                        columns=columns,
                        reporting_step=step,
                        hourly_only=hourly_decisions_only,
                    )
                    step.rows = len(frame)
                    day_records = (
                        frame.astype(object)
                        .where(frame.notna(), None)
                        .to_dict(orient="records")
                    )
                    candidate_records.extend(day_records)
                    del frame, day_records
            except ReportingBudgetExceeded:
                raise
            except Exception:
                logger.exception("Could not read paper decision journal %s", day_dir)
            continue

        path = day_dir / filename
        if not path.is_file():
            continue
        try:
            with ReportingStep(
                logger,
                f"weekly_{filename.removesuffix('.parquet')}_{day_dir.name}",
                [path],
                columns,
            ) as step:
                frame, selected_columns = _read_projected_parquet(path, columns)
                step.columns = selected_columns
                step.rows = len(frame)
                day_records = frame.to_dict(orient="records")
                for row in day_records:
                    for field in (
                        "reasons",
                        "news_headlines",
                        "entry_feature_values",
                        "entry_feature_null_reasons",
                    ):
                        value = row.get(field)
                        if isinstance(value, str):
                            try:
                                row[field] = json.loads(value)
                            except json.JSONDecodeError:
                                row[field] = [value] if value else []
                candidate_records.extend(day_records)
            del frame, day_records
        except Exception:
            logger.exception("Could not read paper journal %s", path)

    return _recent_records(candidate_records, days)


def _read_projected_parquet(
    path: Path, columns: List[str]
) -> tuple[pd.DataFrame, List[str]]:
    try:
        import gc
        import pyarrow as pyarrow
        import pyarrow.parquet as pyarrow_parquet
    except ImportError:
        pyarrow = None
        pyarrow_parquet = None
    if pyarrow_parquet is not None:
        parquet = pyarrow_parquet.ParquetFile(path)
        available_columns = parquet.schema.names
        row_count = parquet.metadata.num_rows
    else:
        parquet = ParquetFile(path)
        available_columns = parquet.columns
        row_count = parquet.count()
    selected_columns = [
        column for column in columns if column in available_columns
    ]
    if selected_columns:
        if pyarrow_parquet is not None:
            batch_frames = [
                batch.to_pandas()
                for batch in parquet.iter_batches(
                    columns=selected_columns, batch_size=8192
                )
            ]
            frame = (
                pd.concat(batch_frames, ignore_index=True)
                if batch_frames
                else pd.DataFrame(columns=selected_columns)
            ).reindex(columns=columns)
            del batch_frames
        else:
            frame = pd.read_parquet(
                path, engine="fastparquet", columns=selected_columns
            ).reindex(columns=columns)
    else:
        frame = pd.DataFrame(index=range(row_count), columns=columns)
    del parquet
    if pyarrow is not None:
        gc.collect()
        pyarrow.default_memory_pool().release_unused()
    return frame, selected_columns


def _decision_source_files(
    day_dir: Path, hourly_only: bool = False
) -> List[Path]:
    parts_dir = day_dir / "decisions"
    if hourly_only:
        return (
            sorted(parts_dir.glob("decisions_*.parquet"))
            if parts_dir.is_dir()
            else []
        )
    sources = []
    legacy = day_dir / "decisions.parquet"
    if legacy.is_file():
        sources.append(legacy)
    sources.extend(sorted(day_dir.glob("decisions_part*.parquet")))
    if parts_dir.is_dir():
        sources.extend(sorted(parts_dir.glob("decisions_*.parquet")))
    return sources


def _recent_day_directories(root: Path, days: int) -> List[Path]:
    candidates = sorted(
        (path for path in root.glob("*/*/day_*") if path.is_dir()),
        key=lambda path: path.as_posix(),
    )
    if not candidates:
        return []

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    recent = []
    for path in candidates:
        try:
            month = path.parents[1].name
            day_number = int(path.name.removeprefix("day_"))
            day = date.fromisoformat(f"{month}-{day_number:02d}")
        except (ValueError, IndexError):
            continue
        if day >= cutoff_date:
            recent.append((day, path))
    if recent:
        return [path for _, path in recent]
    return candidates[-max(days, 1):]


def _legacy_decision_days(root: Path, days: int) -> List[str]:
    return [
        day_dir.name
        for day_dir in _recent_day_directories(root, days)
        if (day_dir / "decisions.parquet").is_file()
        or any(day_dir.glob("decisions_part*.parquet"))
    ]


def _recent_records(
    records: List[Dict[str, Any]], days: int
) -> List[Dict[str, Any]]:
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
    hourly_decisions_only: bool = False,
) -> List[Dict[str, Any]]:
    parquet_records = _recent_parquet_records(
        paper_data_dir,
        parquet_name,
        days,
        columns,
        hourly_decisions_only=hourly_decisions_only,
    )
    if parquet_records:
        return parquet_records
    if hourly_decisions_only and parquet_name == "decisions.parquet":
        return []
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
        strategy = str(trade.get("exit_strategy") or "").strip()
        if not strategy:
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


def _flag(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def _string_list(value: Any) -> List[str]:
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


def _ema_reentry_summary(
    trade_records: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    closed = [trade for trade in trade_records if trade.get("status") == "closed"]
    reentries = [trade for trade in closed if _flag(trade.get("is_ema_reentry"))]
    eligible_stops = [
        trade for trade in closed if _flag(trade.get("ema_reentry_eligible"))
    ]
    reentry_pnls = [_recorded_trade_pnl(trade) for trade in reentries]
    baseline_trades = [
        trade for trade in closed if not _flag(trade.get("is_ema_reentry"))
    ]
    baseline_pnls = [_recorded_trade_pnl(trade) for trade in baseline_trades]
    comparison_pnls = [*baseline_pnls, *reentry_pnls]
    confirmed = sum(
        str(item.get("ema_reentry_event", "")).upper() == "SIGNAL_CONFIRMED"
        for item in decisions
    )
    expired = sum(
        str(item.get("ema_reentry_event", "")).upper() == "WINDOW_EXPIRED"
        for item in decisions
    )
    rejected = sum(
        str(item.get("ema_reentry_event", "")).upper() == "ENTRY_REJECTED"
        for item in decisions
    )
    wins = sum(pnl > 0 for pnl in reentry_pnls)
    losses = sum(pnl < 0 for pnl in reentry_pnls)
    breakeven = sum(pnl == 0 for pnl in reentry_pnls)
    return {
        "paper_only": True,
        "eligible_stop_losses": len(eligible_stops),
        "signals_confirmed": confirmed,
        "windows_expired": expired,
        "no_signal": sum(
            str(trade.get("ema_reentry_outcome", "")).upper() == "NO_SIGNAL"
            for trade in eligible_stops
        ),
        "entry_rejections": rejected,
        "reentries_closed": len(reentries),
        "trade_log": [
            {
                "trade_id": trade.get("trade_id"),
                "original_trade_id": trade.get("original_trade_id"),
                "ticker": trade.get("ticker"),
                "stop_time": trade.get("ema_reentry_stop_time"),
                "signal_time": trade.get("reentry_signal_time"),
                "reason": trade.get("reentry_reason"),
                "entry_price": _number(
                    trade.get("reentry_entry_price", trade.get("entry"))
                ),
                "exit_price": _number(
                    trade.get("reentry_exit_price", trade.get("exit_price"))
                ),
                "pnl": _recorded_trade_pnl(trade),
                "outcome": (
                    trade.get("reentry_outcome")
                    or (
                        "WIN"
                        if _recorded_trade_pnl(trade) > 0
                        else "LOSS"
                        if _recorded_trade_pnl(trade) < 0
                        else "BREAKEVEN"
                    )
                ),
            }
            for trade in reentries
        ],
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate_pct": round(wins / len(reentries) * 100, 2) if reentries else 0.0,
        "total_reentry_pnl": round(sum(reentry_pnls), 2),
        "baseline_comparison": {
            "baseline_closed_trades": len(baseline_trades),
            "baseline_pnl": round(sum(baseline_pnls), 2),
            "strategy_closed_trades": len(comparison_pnls),
            "strategy_pnl": round(sum(comparison_pnls), 2),
            "incremental_reentry_pnl": round(sum(reentry_pnls), 2),
            "pnl_change": round(sum(comparison_pnls) - sum(baseline_pnls), 2),
            "baseline_win_rate_pct": (
                round(sum(pnl > 0 for pnl in baseline_pnls) / len(baseline_pnls) * 100, 2)
                if baseline_pnls
                else 0.0
            ),
            "strategy_win_rate_pct": (
                round(
                    sum(pnl > 0 for pnl in comparison_pnls)
                    / len(comparison_pnls)
                    * 100,
                    2,
                )
                if comparison_pnls
                else 0.0
            ),
        },
        "pnl_basis": (
            "Recorded paper option P&L; includes the original stopped trade and "
            "any closed re-entry. Unmodeled costs may apply."
        ),
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
            category = _decision_outcome_category(entry)
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


def _decision_outcome_category(decision: Dict[str, Any]) -> str:
    outcome = normalize_decision_outcome(decision.get("outcome"))
    detail = normalize_decision_outcome(decision.get("outcome_detail"))
    return "trade_opened" if detail == "trade_opened" else outcome


def build_weekly_report(
    data_dir: str = ".",
    days: int = 7,
    paper_data_dir: str | None = None,
    hourly_decisions_only: bool = False,
) -> Dict[str, Any]:
    root = Path(data_dir)
    paper_root = Path(paper_data_dir) if paper_data_dir else root / "paper_trading_data"
    if hourly_decisions_only:
        legacy_days = _legacy_decision_days(paper_root, days)
        if legacy_days:
            raise ValueError(
                "Weekly report requires hourly decision partitions; migrate legacy "
                f"decision files for {', '.join(legacy_days)} before running"
            )
    trade_records = _load_report_records(
        root,
        paper_root,
        "trades.jsonl",
        "trades.parquet",
        days,
        [
            "trade_id", "timestamp", "ticker", "action", "status", "pnl", "pnl_rupees",
            "gross_pnl_rupees", "fees", "fees_rupees", "fee_model_status",
            "after_cost_pnl", "net_pnl", "r_multiple", "tier", "exit_trigger",
            "manual_exit", "manual_exit_events", "exit_command",
            "strategy_variant", "exit_strategy", "reason", "exit_reason_category",
            "quantity", "entry", "exit_price", "paper_entry_bid",
            "paper_entry_ask", "paper_exit_ltp", "paper_exit_bid",
            "paper_exit_ask", "paper_exit_quote_timestamp",
            "paper_entry_risk_rupees",
            "is_ema_reentry", "original_trade_id", "ema_reentry_eligible",
            "ema_reentry_stop_time", "ema_reentry_outcome",
            "reentry_signal_time", "reentry_reason", "reentry_vwap",
            "reentry_entry_price", "reentry_exit_price", "reentry_pnl",
            "reentry_outcome",
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
            "event", "ema_reentry_event", "original_trade_id", "stop_time",
            "reentry_signal_time", "reentry_reason", "reentry_vwap",
        ],
        hourly_decisions_only=hourly_decisions_only,
    )
    rollback_trades = _load_report_records(
        root,
        paper_root,
        "trades.jsonl",
        "trades.parquet",
        30,
        [
            "trade_id", "timestamp", "entry_time", "closed_at", "status",
            "reason", "pnl", "pnl_rupees", "action", "quantity", "entry",
            "stop_loss", "initial_stop_loss", "initial_risk_per_unit",
            "planned_risk_rupees", "paper_entry_risk_rupees",
            "max_favorable_r", "contract_id", "paper_exit_flags_at_entry",
            "paper_exit_flags", "paper_change_flags_at_entry",
            "paper_change_flags", "paper_exit_parameters",
        ],
    )
    exit_flag_rollback = evaluate_paper_exit_rollbacks(
        rollback_trades, paper_root / "option_candles"
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
        outcome_counts[_decision_outcome_category(decision)] += 1
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
    with ReportingStep(
        logger, "weekly_learning_feedback", [], ["pnl_rupees", "pnl", "reason"]
    ) as step:
        step.rows = len(trades)
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
        "performance_by_exit_reason": _performance_by_key(trades, "reason"),
        "cost_totals": _cost_totals(trades),
        "cost_performance": _cost_performance(trades),
        "human_command_affected_trade": _human_command_affected(trades),
        "ema_reentry_summary": _ema_reentry_summary(trade_records, decisions),
        "option_exit_comparison": _option_exit_comparison(trade_records, days),
        "quote_cost_coverage": _quote_cost_coverage(trades),
        "stop_risk_overruns": _stop_risk_overruns(trades),
        "stop_out_recovery": _recent_recovery_summary(paper_root, days),
        "paper_exit_rollback": exit_flag_rollback,
        "filter_stats": _load_filter_stats(root, days, decisions),
        "news_summary": {
            "risk_counts": news_risk_counts,
            "suppressed_entries": news_suppressed_entries,
        },
        "best_observed_profiles": profiles[:5],
        "pnl_basis": (
            "Gross recorded P&L; modeled brokerage, taxes, and fees are reported "
            "separately. Net P&L is gross less modeled fees; no slippage is deducted."
        ),
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
    report: Dict[str, Any] | None = None,
) -> Path:
    report = report or build_weekly_report(data_dir, days, paper_data_dir)
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
    columns = _daily_record_columns(parquet_name)
    day_dir = (
        paper_data_dir
        / target_date.strftime("%Y-%m")
        / f"week_{target_date.isocalendar().week:02d}"
        / f"day_{target_date.day:02d}"
    )
    if parquet_name == "decisions.parquet":
        sources = _decision_source_files(day_dir)
        with ReportingStep(
            logger, "daily_decisions", sources, columns
        ) as step:
            frame = read_decisions(day_dir, columns=columns)
            step.files = _decision_source_files(day_dir)
            step.rows = len(frame)
            records = (
                frame.astype(object)
                .where(frame.notna(), None)
                .to_dict(orient="records")
            )
            records = [
                record
                for record in records
                if _record_matches_date(record, target_date)
            ]
            del frame
    else:
        parquet_path = day_dir / parquet_name
        if parquet_path.is_file():
            with ReportingStep(
                logger, "daily_trades", [parquet_path], columns
            ) as step:
                frame, selected_columns = _read_projected_parquet(
                    parquet_path, columns
                )
                step.columns = selected_columns
                step.rows = len(frame)
                records = frame.to_dict(orient="records")
                records = [
                    record
                    for record in records
                    if _record_matches_date(record, target_date)
                ]
                del frame
        else:
            records = []

    if not records:
        records = _load_jsonl_for_date(path, target_date)
    for record in records:
        for field in ("entry_feature_values", "entry_feature_null_reasons"):
            value = record.get(field)
            if isinstance(value, str):
                try:
                    record[field] = json.loads(value)
                except json.JSONDecodeError:
                    logger.warning(
                        "Could not decode %s for trade %s",
                        field,
                        record.get("trade_id", record.get("signal_uid", "unknown")),
                    )
                    record[field] = {}
    return records


def _record_matches_date(record: Dict[str, Any], target_date) -> bool:
    timestamp_raw = (
        record.get("timestamp")
        or record.get("message_time")
        or record.get("logged_at")
    )
    if not timestamp_raw:
        return False
    try:
        timestamp = datetime.fromisoformat(
            str(timestamp_raw).replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(IST).date() == target_date


def _daily_record_columns(parquet_name: str) -> List[str]:
    if parquet_name == "trades.parquet":
        return [
            "trade_id", "timestamp", "status", "pnl", "pnl_rupees", "reason",
            "gross_pnl_rupees", "fees", "fees_rupees", "fee_model_status",
            "net_pnl", "after_cost_pnl", "r_multiple", "tier", "exit_trigger",
            "exit_command", "manual_exit", "manual_exit_events",
            "contract_id", "entry_time", "closed_at",
            "exit_reason_category", "ticker", "action", "score",
            "strategy_variant", "is_ema_reentry", "original_trade_id",
            "ema_reentry_eligible", "ema_reentry_outcome",
            "reentry_pnl", "reentry_outcome",
            "entry_mode", "route", "signal_time", "signal_close",
            "confirmation_candle_time", "confirmation_close",
            "confirmation_result", "confirmation_delay_seconds",
            "signal_premium", "order_premium",
            "entry_quote_bid", "entry_quote_ask", "entry_quote_ltp",
            "entry_quote_timestamp", "fill_premium", "fill_bid", "fill_ask",
            "fill_ltp", "fill_quote_age_seconds", "fill_percent_change_from_signal",
            "fill_rule", "entry_regime", "entry_pivot_count",
            "support_reclaim_result", "support_distance_pct",
            "signal_to_entry_delay_seconds", "holding_time_seconds",
            "manual_exit_reason", "paper_change_flags_at_entry",
            "signal_uid", "order_time", "entry_feature_values",
            "entry_feature_null_reasons", "mfe_r", "mfe_time", "mae_r",
            "mae_time",
            "paper_change_flags_at_exit", "paper_exit_flags_at_entry",
            "paper_exit_flags_at_exit", "paper_exit_parameters",
            "exit_trigger_price",
            "exit_trigger_source", "initial_stop_loss", "initial_risk_per_unit",
            "planned_risk_rupees",
        ]
    if parquet_name == "commands.parquet":
        return [
            "chat_id", "user_id", "text", "update_id",
            "message_timestamp", "message_time", "logged_at", "response",
        ]
    return [
        "timestamp", "signal", "outcome", "score", "reasons",
        "outcome_detail", "rejection_reason", "trend_shadow_signal",
        "trend_shadow_rejection_reason", "strategy_variant", "event",
        "ema_reentry_event", "confirmation_event", "signal_id",
        "entry_mode", "route", "signal_time", "signal_close",
        "confirmation_candle_time", "confirmation_close",
        "confirmation_result", "confirmation_delay_seconds",
        "signal_premium", "signal_bid", "signal_ask", "signal_ltp",
        "order_premium", "order_bid", "order_ask", "order_ltp",
        "cancellation_reason", "cancellation_sub_reason",
    ]


def _load_jsonl_for_date(path: Path, target_date) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    records = []
    line_count = 0
    with ReportingStep(logger, "daily_jsonl_fallback", [path]) as step:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    line_count += 1
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        timestamp_raw = str(record.get("timestamp", ""))
                        if not timestamp_raw:
                            continue
                        timestamp = datetime.fromisoformat(
                            timestamp_raw.replace("Z", "+00:00")
                        )
                    except (json.JSONDecodeError, TypeError, ValueError):
                        logger.warning(
                            "Skipping invalid record in %s at line %s",
                            path,
                            line_number,
                        )
                        continue
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    if timestamp.astimezone(IST).date() == target_date:
                        records.append(record)
        except OSError:
            logger.exception("Could not read %s", path)
        step.rows = len(records)
    return records


def _entry_confirmation_metrics(
    trades: List[Dict[str, Any]], decisions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    confirmation_decisions = [
        item
        for item in decisions
        if item.get("event") == "entry_confirmation"
    ]
    generated = [
        item
        for item in confirmation_decisions
        if item.get("confirmation_event") == "signal_generated"
    ]
    rejected = [
        item
        for item in confirmation_decisions
        if item.get("confirmation_event") == "rejected_by_confirmation"
    ]
    passed_count = sum(
        1
        for item in confirmation_decisions
        if item.get("confirmation_result") == "passed"
    )
    after_confirmation: Dict[str, int] = defaultdict(int)
    for item in confirmation_decisions:
        if item.get("confirmation_event") == "filter_failed_after_confirmation":
            after_confirmation[
                str(item.get("cancellation_sub_reason") or "unknown")
            ] += 1

    confirmed_trade_rows = [
        trade for trade in trades if trade.get("entry_mode") == "confirmed"
    ]
    confirmed_trade_events = [
        item
        for item in confirmation_decisions
        if item.get("confirmation_event") == "confirmed_trade"
    ]
    delays = [
        _number(item.get("confirmation_delay_seconds"))
        for item in confirmed_trade_events
        if item.get("confirmation_delay_seconds") not in (None, "")
    ]
    if not delays:
        delays = [
            _number(trade.get("confirmation_delay_seconds"))
            for trade in confirmed_trade_rows
            if trade.get("confirmation_delay_seconds") not in (None, "")
        ]
    premium_changes = []
    premium_records = confirmed_trade_events or confirmed_trade_rows
    for record in premium_records:
        signal_premium = _number(record.get("signal_premium"))
        order_premium = _number(record.get("order_premium"))
        if signal_premium > 0 and order_premium > 0:
            premium_changes.append(
                (order_premium - signal_premium) / signal_premium * 100.0
            )
    pnls = [_recorded_trade_pnl(trade) for trade in confirmed_trade_rows]
    wins = sum(1 for pnl in pnls if pnl > 0)
    after_cost_values = [
        _number(
            trade.get("after_cost_pnl", trade.get("net_pnl"))
        )
        for trade in confirmed_trade_rows
        if trade.get("after_cost_pnl", trade.get("net_pnl")) not in (None, "")
    ]

    return {
        "signals_generated": len(generated),
        "signals_confirmed": passed_count,
        "rejected_by_confirmation_ce": sum(
            1 for item in rejected if item.get("cancellation_reason") == "confirmation_failed_ce"
        ),
        "rejected_by_confirmation_pe": sum(
            1 for item in rejected if item.get("cancellation_reason") == "confirmation_failed_pe"
        ),
        "filter_failed_after_confirmation": dict(sorted(after_confirmation.items())),
        "expired_signal": sum(
            1
            for item in confirmation_decisions
            if item.get("confirmation_event") == "expired_signal"
        ),
        "confirmed_trades": max(
            len(confirmed_trade_events), len(confirmed_trade_rows)
        ),
        "win_rate_pct": wins / len(confirmed_trade_rows) * 100
        if confirmed_trade_rows
        else 0.0,
        "gross_pnl": round(sum(pnls), 2),
        "after_cost_pnl": (
            round(sum(after_cost_values), 2) if after_cost_values else None
        ),
        "average_delay_seconds": (
            sum(delays) / len(delays) if delays else 0.0
        ),
        "average_premium_change_pct": (
            sum(premium_changes) / len(premium_changes)
            if premium_changes
            else 0.0
        ),
    }


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
    rollback_trades = _load_report_records(
        Path(data_dir),
        Path(paper_data_dir),
        "trades.jsonl",
        "trades.parquet",
        30,
        [
            "trade_id", "timestamp", "entry_time", "closed_at", "status",
            "reason", "pnl", "pnl_rupees", "action", "quantity", "entry",
            "stop_loss", "initial_stop_loss", "initial_risk_per_unit",
            "planned_risk_rupees", "paper_entry_risk_rupees",
            "max_favorable_r", "contract_id", "paper_exit_flags_at_entry",
            "paper_exit_flags", "paper_change_flags_at_entry",
            "paper_change_flags", "paper_exit_parameters",
        ],
    )
    exit_flag_rollback = evaluate_paper_exit_rollbacks(
        rollback_trades, Path(paper_data_dir) / "option_candles"
    )
    pnls = [_recorded_trade_pnl(trade) for trade in trades]
    ema_reentry = _ema_reentry_summary(trades, decisions)
    entry_confirmation = _entry_confirmation_metrics(trades, decisions)
    stop_reentry = summarize_stop_events(
        paper_data_dir, target_date, warn_missing=True
    )
    cost_totals = _cost_totals(trades)
    values = {
        "date": target_date.isoformat(),
        "closed_trades": len(trades),
        "winning_trades": sum(1 for pnl in pnls if pnl > 0),
        "losing_trades": sum(1 for pnl in pnls if pnl <= 0),
        "total_pnl": round(sum(pnls), 2),
        "gross_pnl_rupees": cost_totals["gross_pnl"],
        "modeled_fees_rupees": cost_totals["modeled_fees"],
        "net_pnl_rupees": cost_totals["net_pnl"],
        "modeled_fee_coverage": cost_totals["fee_coverage"],
        "net_pnl_coverage": cost_totals["net_coverage"],
        "human_command_affected_trade": _human_command_affected(trades),
        "cost_performance": _cost_performance(trades),
        "average_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        "decisions_recorded": len(decisions),
        "buy_signals": sum(1 for item in decisions if item.get("signal") == "BUY"),
        "sell_signals": sum(1 for item in decisions if item.get("signal") == "SELL"),
        "hold_signals": sum(1 for item in decisions if item.get("signal") == "HOLD"),
        "stop_loss_exits": sum(1 for trade in trades if trade.get("reason") == "STOP_LOSS"),
        "take_profit_exits": sum(1 for trade in trades if trade.get("reason") == "TAKE_PROFIT"),
        "ema_reentry_eligible_stops": ema_reentry["eligible_stop_losses"],
        "ema_reentry_signals_confirmed": ema_reentry["signals_confirmed"],
        "ema_reentries_closed": ema_reentry["reentries_closed"],
        "ema_reentry_pnl": ema_reentry["total_reentry_pnl"],
        "ema_reentry_baseline_pnl": ema_reentry["baseline_comparison"][
            "baseline_pnl"
        ],
        "ema_reentry_strategy_pnl": ema_reentry["baseline_comparison"][
            "strategy_pnl"
        ],
        "entry_confirmation_signals_generated": entry_confirmation[
            "signals_generated"
        ],
        "entry_confirmation_signals_confirmed": entry_confirmation[
            "signals_confirmed"
        ],
        "entry_confirmation_rejected_ce": entry_confirmation[
            "rejected_by_confirmation_ce"
        ],
        "entry_confirmation_rejected_pe": entry_confirmation[
            "rejected_by_confirmation_pe"
        ],
        "entry_confirmation_expired": entry_confirmation["expired_signal"],
        "entry_confirmation_confirmed_trades": entry_confirmation[
            "confirmed_trades"
        ],
        "entry_confirmation_win_rate_pct": entry_confirmation["win_rate_pct"],
        "entry_confirmation_gross_pnl": entry_confirmation["gross_pnl"],
        "entry_confirmation_after_cost_pnl": entry_confirmation["after_cost_pnl"],
        "entry_confirmation_average_delay_seconds": entry_confirmation[
            "average_delay_seconds"
        ],
        "entry_confirmation_average_premium_change_pct": entry_confirmation[
            "average_premium_change_pct"
        ],
        "stop_events": stop_reentry["stop_events"],
        "stop_events_reentered": stop_reentry["stop_events_reentered"],
        "stop_events_recovered_above_entry_30m": stop_reentry[
            "stop_events_recovered_above_entry_30m"
        ],
        "stop_events_recovered_above_entry_60m": stop_reentry[
            "stop_events_recovered_above_entry_60m"
        ],
        "stop_events_candles_missing": stop_reentry[
            "stop_events_candles_missing"
        ],
    }
    for bucket in FAILURE_BUCKETS:
        values[f"stop_events_first_failed_{bucket.replace(' ', '_')}"] = (
            stop_reentry["stop_events_first_failed_condition"].get(bucket, 0)
        )
    for flag, result in exit_flag_rollback.items():
        values[f"{flag}_tagged_trades"] = result["tagged_trades"]
        values[f"{flag}_rollback_required"] = result["rollback_required"]
        values[f"{flag}_rollback_reasons"] = result["rollback_reasons"]
    for reason, count in entry_confirmation[
        "filter_failed_after_confirmation"
    ].items():
        values[f"entry_confirmation_filter_failed_{reason}"] = count
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


def _option_capture_window_status(
    trade: Dict[str, Any], paper_data_dir: Path, target_date: date
) -> str:
    contract_id = str(trade.get("contract_id") or "").strip()
    if not contract_id:
        return "incomplete: missing contract_id"
    start = _parse_datetime(trade.get("signal_time")) or _parse_datetime(
        trade.get("entry_time")
    )
    end = _parse_datetime(trade.get("closed_at"))
    if start is None or end is None or end < start:
        return "incomplete: missing trade window"
    day_dir = paper_data_dir / "option_candles" / target_date.isoformat()
    symbol = contract_id.split(":", 1)[-1]
    paths = sorted(day_dir.glob(f"NFO_{symbol}.candles.csv*"))
    if not paths:
        return "incomplete: no candle file"
    rows_by_minute: Dict[datetime, bool] = {}
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                if row.get("contract_id") != contract_id:
                    continue
                timestamp = _parse_datetime(row.get("candle_start_time"))
                if timestamp is None:
                    continue
                minute = timestamp.replace(second=0, microsecond=0)
                rows_by_minute[minute] = row.get("gap", "").lower() not in {
                    "true", "1"
                }
    first = start.replace(second=0, microsecond=0)
    last = end.replace(second=0, microsecond=0)
    expected = int((last - first).total_seconds() // 60) + 1
    observed = sum(
        rows_by_minute.get(first + timedelta(minutes=index), False)
        for index in range(expected)
    )
    return "complete" if observed == expected else f"incomplete: {observed}/{expected} minutes"


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


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
    for trade in trades:
        trade["option_capture_status"] = _option_capture_window_status(
            trade, Path(paper_data_dir), target_date
        )
    recovery_rows = [
        recovery
        for trade in trades
        if (
            recovery := build_recovery_record(
                trade, Path(paper_data_dir), target_date
            )
        )
        is not None
    ]
    decisions = _date_records(
        Path(data_dir) / "decision_log.jsonl",
        Path(paper_data_dir),
        "decisions.parquet",
        target_date,
    )
    commands = _date_records(
        Path(data_dir) / "commands.jsonl",
        Path(paper_data_dir),
        "commands.parquet",
        target_date,
    )
    stop_reentry = summarize_stop_events(
        paper_data_dir, target_date, warn_missing=False
    )
    rollback_trades = _load_report_records(
        Path(data_dir),
        Path(paper_data_dir),
        "trades.jsonl",
        "trades.parquet",
        30,
        [
            "trade_id", "timestamp", "entry_time", "closed_at", "status",
            "reason", "pnl", "pnl_rupees", "action", "quantity", "entry",
            "stop_loss", "initial_stop_loss", "initial_risk_per_unit",
            "planned_risk_rupees", "paper_entry_risk_rupees",
            "max_favorable_r", "contract_id", "paper_exit_flags_at_entry",
            "paper_exit_flags", "paper_change_flags_at_entry",
            "paper_change_flags", "paper_exit_parameters",
        ],
    )
    exit_flag_rollback = evaluate_paper_exit_rollbacks(
        rollback_trades, Path(paper_data_dir) / "option_candles"
    )

    pnls = [_recorded_trade_pnl(trade) for trade in trades]
    wins = sum(1 for pnl in pnls if pnl > 0)
    losses = sum(1 for pnl in pnls if pnl < 0)
    breakeven = sum(1 for pnl in pnls if pnl == 0)
    ema_reentry = _ema_reentry_summary(trades, decisions)
    entry_confirmation = _entry_confirmation_metrics(trades, decisions)
    signal_counts: Dict[str, int] = defaultdict(int)
    outcome_counts: Dict[str, int] = defaultdict(int)
    rejection_counts: Dict[str, int] = defaultdict(int)
    hold_reasons: Dict[str, int] = defaultdict(int)
    shadow_rejections: Dict[str, int] = defaultdict(int)
    shadow_candidates = 0
    option_leg_skips = 0

    for decision in decisions:
        signal = str(decision.get("signal") or "UNKNOWN")
        signal_counts[signal] += 1
        outcome = _decision_outcome_category(decision)
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

    day_dir = (
        Path(paper_data_dir)
        / target_date.strftime("%Y-%m")
        / f"week_{target_date.isocalendar().week:02d}"
        / f"day_{target_date.day:02d}"
    )
    with ReportingStep(
        logger,
        "daily_review_paper_shadow",
        _decision_source_files(day_dir),
        ["trend_shadow_signal", "trend_shadow_rejection_reason"],
    ) as step:
        step.rows = len(decisions)
        has_shadow_telemetry = any(
            "trend_shadow_signal" in item
            or "trend_shadow_rejection_reason" in item
            for item in decisions
        )
        for decision in decisions:
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
    cost_totals = _cost_totals(trades)
    cost_performance = _cost_performance(trades)
    human_command_affected = _human_command_affected(trades) or any(
        _command_affected_trade(command) for command in commands
    )
    ema_reentries = [
        trade for trade in trades if _flag(trade.get("is_ema_reentry"))
    ]
    recorder = PaperTradingRecorder(paper_data_dir)
    destination = recorder._day_path(
        datetime.combine(target_date, datetime.min.time()).isoformat(),
        "daily_review.md",
    )
    if recovery_rows:
        recovery_path = recorder._day_path(
            datetime.combine(target_date, datetime.min.time()).isoformat(),
            "stop_out_recovery.parquet",
        )
        recorder._write_parquet(
            recovery_path,
            recovery_rows,
            list(RECOVERY_COLUMNS),
        )
    lines = [
        f"# Daily Paper-Trading Review - {target_date:%Y-%m-%d}",
        "",
        "## Results",
        f"- Closed trades: {len(trades)}",
        f"- Wins / losses / breakeven: {wins} / {losses} / {breakeven}",
        f"- Gross recorded P&L before modeled fees: {sum(pnls):.2f}",
        f"- Win rate: {win_rate:.1f}%",
        f"- Decisions: {len(decisions)}",
        "",
        "## Modeled Fees and Net Performance",
        f"- Gross P&L: {cost_totals['gross_pnl']:.2f}",
        (
            f"- Modeled fees: {cost_totals['modeled_fees']:.2f} "
            f"({cost_totals['fee_coverage']}/{cost_totals['trades']} trades)"
            if cost_totals["modeled_fees"] is not None
            else f"- Modeled fees: unavailable (0/{cost_totals['trades']} trades)"
        ),
        (
            f"- Net P&L (gross minus modeled fees; no slippage): "
            f"{cost_totals['net_pnl']:.2f} "
            f"({cost_totals['net_coverage']}/{cost_totals['trades']} trades)"
            if cost_totals["net_pnl"] is not None
            else f"- Net P&L: unavailable (0/{cost_totals['trades']} trades)"
        ),
        f"- Human command affected at least one trade: "
        f"{'yes' if human_command_affected else 'no'}",
        "- All fee figures are modeled from the configured paper charge model.",
        "",
        *_cost_performance_lines(cost_performance),
        "",
        "## One-Candle Entry Confirmation",
        f"- Signals generated: {entry_confirmation['signals_generated']}",
        f"- Direction confirmed: {entry_confirmation['signals_confirmed']}",
        "- Rejected by confirmation (CE / PE): "
        f"{entry_confirmation['rejected_by_confirmation_ce']} / "
        f"{entry_confirmation['rejected_by_confirmation_pe']}",
        "- Filter failures after confirmation: "
        f"{json.dumps(entry_confirmation['filter_failed_after_confirmation'], sort_keys=True)}",
        f"- Expired signals: {entry_confirmation['expired_signal']}",
        f"- Confirmed trades: {entry_confirmation['confirmed_trades']}",
        f"- Win rate: {entry_confirmation['win_rate_pct']:.1f}%",
        f"- Gross recorded P&L: {entry_confirmation['gross_pnl']:.2f}",
        (
            f"- After-cost P&L: {entry_confirmation['after_cost_pnl']:.2f}"
            if entry_confirmation["after_cost_pnl"] is not None
            else "- After-cost P&L: unavailable (trade journal has no after-cost field)"
        ),
        f"- Average delay: {entry_confirmation['average_delay_seconds']:.1f}s",
        "- Average premium change from signal to fill: "
        f"{entry_confirmation['average_premium_change_pct']:.3f}%",
        "",
        "## EMA Stop-Loss Re-entry",
        f"- Eligible stop-loss trades: {ema_reentry['eligible_stop_losses']}",
        f"- Confirmed signals: {ema_reentry['signals_confirmed']}",
        f"- Windows expired without a signal: {ema_reentry['no_signal']}",
        f"- Signal entries rejected by other gates: {ema_reentry['entry_rejections']}",
        f"- Re-entries closed: {ema_reentry['reentries_closed']}",
        f"- Re-entry wins / losses / breakeven: {ema_reentry['wins']} / "
        f"{ema_reentry['losses']} / {ema_reentry['breakeven']}",
        f"- Re-entry P&L: {ema_reentry['total_reentry_pnl']:.2f}",
        f"- Baseline P&L: "
        f"{ema_reentry['baseline_comparison']['baseline_pnl']:.2f}; "
        f"with re-entries: "
        f"{ema_reentry['baseline_comparison']['strategy_pnl']:.2f}",
        "",
        "### Re-entry Trade Log",
        "| Original trade ID | Symbol | Stop time | Signal time | Reason | Entry | Exit | P&L | Outcome |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
        *(
            [
                "| {original_trade_id} | {ticker} | {stop_time} | {signal_time} | "
                "{reason} | {entry:.2f} | {exit:.2f} | {pnl:.2f} | {outcome} |".format(
                    original_trade_id=str(trade.get("original_trade_id") or "N/A").replace("|", "/"),
                    ticker=str(trade.get("ticker") or "UNKNOWN").replace("|", "/"),
                    stop_time=str(trade.get("ema_reentry_stop_time") or "N/A"),
                    signal_time=str(trade.get("reentry_signal_time") or "N/A"),
                    reason=str(trade.get("reentry_reason") or "N/A").replace("|", "/"),
                    entry=_number(trade.get("reentry_entry_price", trade.get("entry"))),
                    exit=_number(trade.get("reentry_exit_price", trade.get("exit_price"))),
                    pnl=_recorded_trade_pnl(trade),
                    outcome=str(
                        trade.get("reentry_outcome")
                        or (
                            "WIN" if _recorded_trade_pnl(trade) > 0
                            else "LOSS" if _recorded_trade_pnl(trade) < 0
                            else "BREAKEVEN"
                        )
                    ),
                )
                for trade in ema_reentries
            ]
            or ["| No re-entry trades recorded | - | - | - | - | - | - | 0.00 | - |"]
        ),
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
        "| Symbol | Direction | Variant | Score | Held (s) | P&L | Exit | Manual | Flags at entry → exit | Signal/order/fill premium | Fill bid/ask/LTP/age | Fill Δ% | Trigger price/source | Capture |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    if trades:
        lines.extend(
            "| {ticker} | {action} | {variant} | {score} | {held} | {pnl:.2f} | {reason} | {manual} | {entry_flags} → {exit_flags} | {premiums} | {quote} | {fill_change} | {trigger} | {capture} |".format(
                ticker=str(trade.get("ticker") or "UNKNOWN").replace("|", "/"),
                action=str(trade.get("action") or "UNKNOWN").replace("|", "/"),
                variant=str(trade.get("strategy_variant") or "primary").replace("|", "/"),
                score=trade.get("score") or "N/A",
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
                manual=(
                    "yes: " + str(trade.get("manual_exit_reason") or "manual")
                    if _flag(trade.get("manual_exit"))
                    else "no"
                ).replace("|", "/"),
                entry_flags=str(
                    trade.get("paper_exit_flags_at_entry")
                    or trade.get("paper_change_flags_at_entry")
                    or trade.get("paper_change_flags")
                    or []
                ).replace("|", "/"),
                exit_flags=str(
                    trade.get("paper_exit_flags_at_exit")
                    or trade.get("paper_change_flags_at_exit")
                    or []
                ).replace("|", "/"),
                quote=(
                    f"{trade.get('fill_bid', 'N/A')}/"
                    f"{trade.get('fill_ask', 'N/A')}/"
                    f"{trade.get('fill_ltp', 'N/A')}/"
                    f"{trade.get('fill_quote_age_seconds', 'N/A')}s"
                ).replace("|", "/"),
                premiums="/".join(
                    str(trade.get(key, "N/A"))
                    for key in ("signal_premium", "order_premium", "fill_premium")
                ).replace("|", "/"),
                fill_change=(
                    f"{_number(trade.get('fill_percent_change_from_signal')):+.3f}"
                    if trade.get("fill_percent_change_from_signal") not in (None, "")
                    else "N/A"
                ),
                trigger=(
                    f"{trade.get('exit_trigger_price', 'N/A')}/"
                    f"{trade.get('exit_trigger_source', 'N/A')}"
                ).replace("|", "/"),
                capture=str(trade.get("option_capture_status") or "unverified").replace(
                    "|", "/"
                ),
            )
            for trade in trades
        )
    else:
        lines.append("| No closed trades | - | - | - | - | 0.00 | - | - | - | - | - | - | - | - |")
    feature_names = (
        "regime_label",
        "regime_range_pct",
        "regime_20_bar_move_pct",
        "pivot_count",
        "pivot_level",
        "distance_to_pivot_pct",
        "near_recent_high",
        "distance_to_recent_high_pct",
        "near_recent_low",
        "distance_to_recent_low_pct",
        "ema_fast_value",
        "ema_slow_value",
        "ema_state",
        "macd_value",
        "macd_state",
        "rsi_value",
        "rsi_state",
        "adx_value",
        "adx_state",
        "option_candle_body_ratio",
        "option_candle_body_ratio_threshold",
        "option_candle_direction_rule",
        "prior_30m_underlying_move_pct",
        "prior_60m_underlying_move_pct",
        "prior_30m_option_move_pct",
        "prior_60m_option_move_pct",
        "signal_id",
        "signal_uid",
        "signal_time",
        "signal_premium",
        "confirmation_time",
        "confirmation_ltp",
        "order_time",
        "fill_bid",
        "fill_ask",
        "fill_ltp",
        "fill_quote_age_seconds",
        "signal_to_fill_pct",
        "tier",
        "lot_size",
        "lots",
        "quantity",
        "risk_amount",
        "risk_cap",
        "time_of_day_bucket",
        "active_paper_change_flags",
        "paper_change_attributions",
        "partial_status",
        "mfe_r",
        "mfe_time",
        "mae_r",
        "mae_time",
    )
    feature_values_by_trade = []
    for trade in trades:
        values = trade.get("entry_feature_values")
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except json.JSONDecodeError:
                values = {}
        feature_values_by_trade.append(
            values if isinstance(values, dict) else {}
        )
    feature_denominator = len(trades)
    lines.extend(["", "## Entry Features"])
    if trades:
        for trade, values in zip(trades, feature_values_by_trade):
            compact = (
                f"regime={values.get('regime_label', 'N/A')}/"
                f"{values.get('regime_range_pct', 'N/A')}%/"
                f"{values.get('regime_20_bar_move_pct', 'N/A')}%; "
                f"pivot={values.get('pivot_count', 'N/A')}@"
                f"{values.get('pivot_level', 'N/A')}; "
                f"near H/L={values.get('near_recent_high', 'N/A')}/"
                f"{values.get('near_recent_low', 'N/A')}; "
                f"EMA/MACD/RSI/ADX={values.get('ema_state', 'N/A')}/"
                f"{values.get('macd_state', 'N/A')}/"
                f"{values.get('rsi_state', 'N/A')}/"
                f"{values.get('adx_state', 'N/A')}; "
                f"option momentum={values.get('option_candle_body_ratio', 'N/A')}/"
                f"{values.get('option_candle_direction_rule', 'N/A')}; "
                f"prior U30/U60/O30/O60="
                f"{values.get('prior_30m_underlying_move_pct', 'N/A')}/"
                f"{values.get('prior_60m_underlying_move_pct', 'N/A')}/"
                f"{values.get('prior_30m_option_move_pct', 'N/A')}/"
                f"{values.get('prior_60m_option_move_pct', 'N/A')}; "
                f"signal={values.get('signal_uid', 'N/A')}@"
                f"{values.get('signal_time', 'N/A')} premium="
                f"{values.get('signal_premium', 'N/A')}; "
                f"tier/lots/qty={values.get('tier', 'N/A')}/"
                f"{values.get('lots', 'N/A')}/{values.get('quantity', 'N/A')}; "
                f"risk/cap={values.get('risk_amount', 'N/A')}/"
                f"{values.get('risk_cap', 'N/A')}; "
                f"bucket={values.get('time_of_day_bucket', 'N/A')}; "
                f"partial={values.get('partial_status', 'N/A')}; "
                f"MFE/MAE={values.get('mfe_r', 'N/A')}@"
                f"{values.get('mfe_time', 'N/A')}/"
                f"{values.get('mae_r', 'N/A')}@{values.get('mae_time', 'N/A')}"
            ).replace("|", "/")
            lines.append(
                f"- {str(trade.get('ticker') or 'UNKNOWN').replace('|', '/')} "
                f"({trade.get('signal_uid') or 'no signal_uid'}): {compact}"
            )
        lines.extend(
            [
                "",
                "| Field | Populated | Share |",
                "| --- | ---: | ---: |",
            ]
        )
        for field in feature_names:
            populated = sum(
                field in values and values[field] is not None
                for values in feature_values_by_trade
            )
            lines.append(
                f"| {field} | {populated}/{feature_denominator} | "
                f"{100 * populated / feature_denominator:.1f}% |"
            )
    else:
        lines.append("- No closed trades.")
    lines.extend(
        [
            "",
            "## Stop-out recovery",
            "",
            "Option R uses initial per-unit risk and one-minute option OHLC; checkpoint bids are the nearest valid archived quote after exit to each checkpoint, with quote age and sample offset shown. Underlying reversal means the captured one-minute range crossed the entry-time underlying reference against the option direction.",
            "",
            "| Trade | Exit type | Entry→exit seconds | ≤5m | Bid @ 5m | Bid @ 15m | Bid @ 30m | Bid @ 60m | Max/min R 60m | Max/min R close | Reclaimed entry | Reached +1R | Underlying reversed | Capture |",
            "| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    def recovery_bid_text(value: Any) -> str:
        if not isinstance(value, dict):
            return "N/A"
        bid = _number(value.get("bid"))
        age = value.get("quote_age_seconds")
        offset = value.get("sample_offset_seconds")
        return (
            f"{bid:.2f} (age {age if age is not None else 'N/A'}s; "
            f"offset {offset if offset is not None else 'N/A'}s)"
            if bid is not None
            else "N/A"
        )

    if recovery_rows:
        for recovery in recovery_rows:
            within_5m = (
                "yes" if _flag(recovery.get("stop_within_5m")) else "no"
            )
            reclaimed = (
                str(recovery.get("reclaimed_entry_time") or "yes")
                if _flag(recovery.get("reclaimed_entry"))
                else "no"
            )
            plus_one_r = (
                str(recovery.get("reached_plus_1r_time") or "yes")
                if _flag(recovery.get("reached_plus_1r"))
                else "no"
            )
            underlying = (
                "yes"
                if _flag(recovery.get("underlying_reversed_to_close"))
                else "no"
                if recovery.get("underlying_reversed_to_close") not in (None, "")
                else "unknown"
            )
            max_min_60 = (
                f"{recovery.get('max_r_within_60m')}/"
                f"{recovery.get('min_r_within_60m')}"
            )
            max_min_close = (
                f"{recovery.get('max_r_to_close')}/"
                f"{recovery.get('min_r_to_close')}"
            )
            lines.append(
                f"| {recovery.get('trade_id')} | {recovery.get('exit_type')} | "
                f"{recovery.get('entry_to_exit_seconds')} | {within_5m} | "
                f"{recovery_bid_text(recovery.get('bid_after_5m'))} | "
                f"{recovery_bid_text(recovery.get('bid_after_15m'))} | "
                f"{recovery_bid_text(recovery.get('bid_after_30m'))} | "
                f"{recovery_bid_text(recovery.get('bid_after_60m'))} | "
                f"{max_min_60} | {max_min_close} | {reclaimed} | {plus_one_r} | "
                f"{underlying} | {recovery.get('status')} |"
            )
    else:
        lines.append("| No initial-stop, trailing-stop, or breakeven exits | - | - | - | - | - | - | - | - | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## Paper exit flag results",
            "",
            "| Flag | Tagged trades (W/L/BE) | Tagged P&L | Untagged trades (W/L/BE) | Untagged P&L |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for flag in EXIT_FLAGS:
        tagged = [
            trade
            for trade in trades
            if flag
            in _string_list(
                trade.get("paper_exit_flags_at_entry")
                or trade.get("paper_change_flags_at_entry")
                or trade.get("paper_change_flags")
            )
        ]
        untagged = [trade for trade in trades if trade not in tagged]

        def result_counts(rows: List[Dict[str, Any]]) -> str:
            values = [_recorded_trade_pnl(item) for item in rows]
            return (
                f"{len(rows)} ({sum(value > 0 for value in values)}/"
                f"{sum(value < 0 for value in values)}/"
                f"{sum(value == 0 for value in values)})"
            )

        lines.append(
            f"| {flag} | {result_counts(tagged)} | "
            f"{sum(_recorded_trade_pnl(item) for item in tagged):.2f} | "
            f"{result_counts(untagged)} | "
            f"{sum(_recorded_trade_pnl(item) for item in untagged):.2f} |"
        )
    lines.extend(
        [
            "",
            "## Paper exit flag rollback checks",
            "",
            "| Flag | Tagged trades | Threshold checks | Status |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for flag in EXIT_FLAGS:
        result = exit_flag_rollback[flag]
        lines.append(
            f"| {flag} | {result['tagged_trades']} | "
            f"{'; '.join(result['checks']) or 'checks not evaluated'} | "
            f"{'; '.join(result['rollback_reasons']) or 'no rollback trigger'} |"
        )
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
            "## Stop-Out Re-entry Diagnostics",
            f"- Stop events: {stop_reentry['stop_events']}",
            f"- Stop events followed by a re-entry: {stop_reentry['stop_events_reentered']}",
            "- Recovered above entry within 30 / 60 minutes: "
            f"{stop_reentry['stop_events_recovered_above_entry_30m']} / "
            f"{stop_reentry['stop_events_recovered_above_entry_60m']}",
            f"- Stop events with missing option candles: {stop_reentry['stop_events_candles_missing']}",
            "- First failed condition by stop event: "
            f"{json.dumps(stop_reentry['stop_events_first_failed_condition'], sort_keys=True)}",
        ]
    )
    lines.extend(
        [
            "",
            "## Review Notes",
            "- Reason counts are mentions; one decision may contain multiple reasons.",
            "- Stop-loss exits count only records whose reason is exactly STOP_LOSS; TRAILING_STOP is excluded even when exit_reason_category is SL.",
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
    data_dir: str = ".",
    paper_data_dir: str = "paper_trading_data",
    days: int = 7,
    report: Dict[str, Any] | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Write a human-readable review with evidence-based improvement prompts."""
    report = report or build_weekly_report(data_dir, days, paper_data_dir)
    ema_reentry_summary = report["ema_reentry_summary"]
    cost_totals = report.get("cost_totals") or {
        "gross_pnl": report.get("total_pnl", 0.0),
        "modeled_fees": None,
        "net_pnl": None,
        "fee_coverage": 0,
        "net_coverage": 0,
        "trades": report.get("closed_trades", 0),
    }
    cost_performance = report.get(
        "cost_performance",
        {"tier": {}, "CE/PE": {}, "exit_trigger": {}},
    )
    now = datetime.now()
    destination = (
        Path(output_path)
        if output_path is not None
        else _weekly_review_destination(paper_data_dir, now)
    )
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
        f"- Gross recorded P&L before modeled fees: {report['total_pnl']:.2f}",
        f"- Recorded expectancy before costs: "
        f"{report['total_pnl'] / report['closed_trades']:.2f} per trade"
        if report["closed_trades"]
        else "- Recorded expectancy before costs: unavailable (no closed trades)",
        f"- Average win / loss: {report['average_win']:.2f} / "
        f"{report['average_loss']:.2f}",
        f"- Profit factor before costs: {report['profit_factor']:.2f}",
        f"- Win rate: {report['win_rate']:.2f}%",
        f"- Decisions recorded: {report['decisions_recorded']}",
        f"- High-news-risk decisions: {report['news_summary']['risk_counts'].get('HIGH', 0)}",
        f"- Entries suppressed by news filter: {report['news_summary']['suppressed_entries']}",
        f"- Learning feedback: {report['learning_feedback']['status']} "
        f"({report['learning_feedback']['closed_trades']}/"
        f"{report['learning_feedback']['minimum_closed_trades_for_screening']} trades)",
        f"- Feedback: {report['learning_feedback']['recommendation']}",
        "",
        "## Modeled Fees and Net Performance",
        f"- Gross P&L: {cost_totals['gross_pnl']:.2f}",
        (
            f"- Modeled fees: {cost_totals['modeled_fees']:.2f} "
            f"({cost_totals['fee_coverage']}/{cost_totals['trades']} trades)"
            if cost_totals["modeled_fees"] is not None
            else f"- Modeled fees: unavailable (0/{cost_totals['trades']} trades)"
        ),
        (
            f"- Net P&L (gross minus modeled fees; no slippage): "
            f"{cost_totals['net_pnl']:.2f} "
            f"({cost_totals['net_coverage']}/{cost_totals['trades']} trades)"
            if cost_totals["net_pnl"] is not None
            else f"- Net P&L: unavailable (0/{cost_totals['trades']} trades)"
        ),
        f"- Human command affected at least one trade: "
        f"{'yes' if report.get('human_command_affected_trade', False) else 'no'}",
        "- All fee figures are modeled from the configured paper charge model.",
        "",
        *_cost_performance_lines(cost_performance),
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
        "## Performance by Entry Strategy",
        "| Entry strategy | Closed trades | Wins | Losses | Recorded P&L |",
        "| --- | ---: | ---: | ---: | ---: |",
        *(
            [
                f"| {str(strategy).replace('|', '/')} | {metrics['trades']} | "
                f"{metrics['wins']} | {metrics['losses']} | "
                f"{metrics['total_pnl']:.2f} |"
                for strategy, metrics in sorted(
                    report["performance_by_strategy_variant"].items()
                )
            ]
            or ["| No strategy-tagged trades | - | - | - | - |"]
        ),
        "",
        "## EMA Stop-Loss Re-entry Comparison",
        f"- Eligible stop-loss trades: {ema_reentry_summary['eligible_stop_losses']}",
        f"- Confirmed re-entry signals: {ema_reentry_summary['signals_confirmed']}",
        f"- Windows expired without a signal: {ema_reentry_summary['no_signal']}",
        f"- Signal entries rejected by other gates: "
        f"{ema_reentry_summary['entry_rejections']}",
        f"- Closed re-entries: {ema_reentry_summary['reentries_closed']}",
        f"- Re-entry wins / losses / breakeven: "
        f"{ema_reentry_summary['wins']} / "
        f"{ema_reentry_summary['losses']} / "
        f"{ema_reentry_summary['breakeven']}",
        f"- Baseline P&L: "
        f"{ema_reentry_summary['baseline_comparison']['baseline_pnl']:.2f}; "
        f"with re-entries: "
        f"{ema_reentry_summary['baseline_comparison']['strategy_pnl']:.2f}",
        "Paper-only comparison; the baseline excludes EMA re-entry trades, and all figures use recorded P&L.",
        "",
        "## Stop-out Recovery",
        f"- Recovery records: {report['stop_out_recovery']['trades']}",
        f"- Incomplete records: {report['stop_out_recovery']['incomplete']}",
        f"- Exits within five minutes: {report['stop_out_recovery']['stop_within_5m']}",
        f"- Option reclaimed entry / reached +1R: "
        f"{report['stop_out_recovery']['reclaimed_entry']} / "
        f"{report['stop_out_recovery']['reached_plus_1r']}",
        f"- Underlying reversed against the position: "
        f"{report['stop_out_recovery']['underlying_reversed']}",
        "Detailed per-trade checkpoint bids and R excursions are in each session's stop_out_recovery.parquet file.",
        "",
        "## PAPER Exit Rollback Checks",
        "| Flag | Tagged trades | Checks | Result |",
        "| --- | ---: | --- | --- |",
        *[
            f"| {flag} | {report['paper_exit_rollback'][flag]['tagged_trades']} | "
            f"{'; '.join(report['paper_exit_rollback'][flag]['checks']) or 'checks not evaluated'} | "
            f"{'; '.join(report['paper_exit_rollback'][flag]['rollback_reasons']) or 'no rollback trigger'} |"
            for flag in EXIT_FLAGS
        ],
        "If a threshold triggers, set that flag to false, stop and restart the PAPER bot, then verify the next trade's paper_exit_flags_at_entry omits the flag. LIVE behavior is unaffected.",
        "",
        "## Loss Clusters",
        "| Exit reason | Closed trades | Wins | Losses | Recorded P&L |",
        "| --- | ---: | ---: | ---: | ---: |",
        *(
            [
                f"| {str(reason).replace('|', '/')} | {metrics['trades']} | "
                f"{metrics['wins']} | {metrics['losses']} | "
                f"{metrics['total_pnl']:.2f} |"
                for reason, metrics in sorted(
                    report["performance_by_exit_reason"].items(),
                    key=lambda item: item[1]["total_pnl"],
                )
            ]
            or ["| No closed-trade exits recorded | - | - | - | - |"]
        ),
        "",
        "### Symbols",
        "| Symbol | Closed trades | Wins | Losses | Recorded P&L |",
        "| --- | ---: | ---: | ---: | ---: |",
        *(
            [
                f"| {str(symbol).replace('|', '/')} | {metrics['trades']} | "
                f"{metrics['wins']} | {metrics['losses']} | "
                f"{metrics['total_pnl']:.2f} |"
                for symbol, metrics in sorted(
                    report["performance_by_symbol"].items(),
                    key=lambda item: item[1]["total_pnl"],
                )[:5]
            ]
            or ["| No symbol-level trades recorded | - | - | - | - |"]
        ),
        "",
        "### Entry hour (IST)",
        "| Hour | Closed trades | Wins | Losses | Recorded P&L |",
        "| --- | ---: | ---: | ---: | ---: |",
        *(
            [
                f"| {hour}:00 | {metrics['trades']} | {metrics['wins']} | "
                f"{metrics['losses']} | {metrics['total_pnl']:.2f} |"
                for hour, metrics in sorted(
                    report["performance_by_hour"].items(),
                    key=lambda item: item[1]["total_pnl"],
                )
            ]
            or ["| No entry-hour trades recorded | - | - | - | - |"]
        ),
        "",
        "## Cost-data coverage",
        (
            "- Entry and exit bid/ask snapshots bracketed the recorded LTP for "
            f"{report['quote_cost_coverage']['quote_consistent_trades']}/"
            f"{report['quote_cost_coverage']['closed_trades']} closed trades. "
            f"The quote-based P&L proxy on this subset is "
            f"{report['quote_cost_coverage']['quote_based_pnl']:.2f}; "
            "it is not a full-sample expectancy."
            if report["quote_cost_coverage"]["closed_trades"]
            else "- No closed trades are available for quote-based cost coverage."
        ),
        "- Brokerage, taxes, and slippage are not included; do not treat the partial quote proxy as a net-performance result.",
        (
            f"- {report['stop_risk_overruns']['overrun_trades']}/"
            f"{report['stop_risk_overruns']['stop_losses_with_risk_data']} "
            f"stop-loss exits exceeded their recorded initial risk by a total of "
            f"{report['stop_risk_overruns']['total_overrun_rupees']:.2f}; "
            "the paper exit is marked at the observed tick after the stop threshold, "
            "not guaranteed at the stop price."
            if report["stop_risk_overruns"]["stop_losses_with_risk_data"]
            else "- Stop-loss risk overruns cannot be assessed because initial-risk estimates are unavailable."
        ),
        "- The available week-level records do not by themselves constitute an out-of-sample walk-forward replay; do not infer a parameter change from these aggregates.",
        "- Keep score thresholds unchanged based on win rate alone.",
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def _weekly_review_destination(
    paper_data_dir: str | Path, now: datetime | None = None
) -> Path:
    now = now or datetime.now()
    recorder = PaperTradingRecorder(paper_data_dir)
    day_path = recorder._day_path(now.isoformat(), "daily_summary.parquet")
    return day_path.parent.parent / f"weekly_review_{now:%Y_%m_%d}.md"