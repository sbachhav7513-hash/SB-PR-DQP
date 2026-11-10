from __future__ import annotations

import json
import logging
import math
import os
import queue
import re
import threading
import time as time_module
import weakref
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
from fastparquet import ParquetFile, write as write_parquet

from .change_tracking import get_git_identity
from .reporting_metrics import ReportingStep


logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
DECISION_QUEUE_SIZE = 50_000
DECISION_BATCH_SIZE = 200
DECISION_FLUSH_INTERVAL_SECONDS = 60.0
REJECTED_SIGNAL_UPDATE_QUEUE_SIZE = 10_000
DECISION_WRITERS: weakref.WeakSet = weakref.WeakSet()
DECISION_WRITERS_LOCK = threading.Lock()


def normalize_decision_outcome(value: Any) -> str:
    """Map detailed decision results into stable report categories."""
    outcome = str(value or "UNKNOWN")
    lowered = outcome.lower()
    if outcome in {
        "trade_opened", "accuracy_filter", "option_filter", "risk_blocked",
        "execution_failed", "premarket", "market_closed", "hold", "operational",
        "paper_entry_cutoff", "paper_risk_cap",
    }:
        return outcome
    if outcome == "PAPER_RANGE_BREAKOUT_TRADE_OPENED":
        return "trade_opened"
    if outcome.startswith("PAPER_RANGE_BREAKOUT_REJECTED:"):
        return "option_filter"
    if outcome.startswith("PAPER_RANGE_BREAKOUT_TRADE_BLOCKED:"):
        return "risk_blocked"
    if outcome == "PAPER_RANGE_BREAKOUT_PAPER_ENTRY_CUTOFF_BLOCKED":
        return "paper_entry_cutoff"
    if outcome == "PAPER_RANGE_BREAKOUT_PAPER_RISK_CAP_BLOCKED":
        return "paper_risk_cap"
    if outcome.startswith(
        (
            "PAPER_RANGE_BREAKOUT_POSITION_SIZE_ZERO",
            "PAPER_RANGE_BREAKOUT_INVALID_RISK",
        )
    ):
        return "risk_blocked"
    if outcome == "trade_opened":
        return "trade_opened"
    if outcome.startswith("accuracy_filter_rejected:"):
        return "accuracy_filter"
    if outcome.startswith("OPTION_FILTER_"):
        return "option_filter"
    if outcome in {
        "trade_blocked", "live_entry_paused", "position_size_zero",
        "late_window_blocked",
    } or outcome.startswith(("trade_blocked:", "risk_blocked:")):
        return "risk_blocked"
    if outcome.startswith("paper_entry_cutoff_blocked"):
        return "paper_entry_cutoff"
    if outcome.startswith("paper_risk_cap_blocked"):
        return "paper_risk_cap"
    if outcome.startswith("entry_cutoff_blocked"):
        return "paper_entry_cutoff"
    if outcome.startswith("risk_cap_blocked"):
        return "paper_risk_cap"
    if outcome in {
        "live_order_failed", "protective_stop_failed", "reversal_close_failed",
        "execution_failed",
    }:
        return "execution_failed"
    if outcome == "PREMARKET_WATCHLIST":
        return "premarket"
    if outcome == "MARKET_CLOSED" or "after close" in lowered:
        return "market_closed"
    if outcome in {
        "not_enough_bars", "underlying_signal_unavailable", "strategy_error",
        "forced_exit_check", "position_updated", "UNKNOWN",
    }:
        return "operational"
    if lowered == "hold" or outcome == "HOLD":
        return "hold"
    return "operational"


def normalize_entry_confirmation_detail(record: Dict[str, Any]) -> str:
    event = str(record.get("confirmation_event") or "")
    if event in {"signal_generated", "signal_ignored_pending"}:
        return "pending"
    if event == "confirmed_trade":
        return "trade_opened"
    if event in {
        "rejected_by_confirmation",
        "confirmation_error",
        "expired_signal",
    }:
        return "confirmation_failed"
    if event == "filter_failed_after_confirmation":
        reason = " ".join(
            str(record.get(key) or "")
            for key in ("cancellation_reason", "cancellation_sub_reason")
        ).lower()
        if any(marker in reason for marker in ("stale_quote", "stale quote", "quote stale")):
            return "stale_quote"
        if any(
            marker in reason
            for marker in (
                "risk_cap",
                "one_lot_exceeds",
                "loss_cap",
                "daily loss",
                "risk budget",
            )
        ):
            return "risk_cap"
    return "other_filter"


class PaperTradingRecorder:
    """Store paper-trading events in date-partitioned compressed Parquet files."""

    TRADE_COLUMNS = [
        "trade_id", "telegram_trade_id", "timestamp", "config_hash", "git_sha", "git_dirty",
        "ticker", "trading_symbol",
        "contract_id",
        "action", "quantity", "entry",
        "exit_price", "stop_loss", "take_profit", "status", "pnl", "pnl_points",
        "pnl_rupees", "duration_seconds", "reason", "score", "exit_source", "exit_reason",
        "risk_modifications", "closed_at", "updated_at",
        "holding_time_seconds", "protection_order_id", "strategy_variant",
        "exit_strategy", "target_stage", "milestone_reached_pct",
        "exit_reason_category", "entry_time", "milestone_started_at",
        "minimum_signal_score", "option_milestone_pct", "trailing_stop",
        "current_signal_score", "decision_window_minutes",
        "weak_signal_adverse_checks",
        "trailing_enabled",
        "runner_activation_r",
        "runner_gap_r",
        "adaptive_breakeven_r",
        "adaptive_trail_activation_r",
        "adaptive_trail_gap_r",
        "adaptive_runner_activation_r",
        "adaptive_runner_gap_r",
        "adaptive_exit_mode",
        "max_favorable_r",
        "highest_price",
        "lowest_price",
        "trailing_active",
        "paper_entry_ltp",
        "paper_entry_bid",
        "paper_entry_ask",
        "entry_quote_ltp",
        "entry_quote_bid",
        "entry_quote_ask",
        "entry_quote_timestamp",
        "entry_fill_source",
        "fill_premium",
        "fill_bid",
        "fill_ask",
        "fill_ltp",
        "fill_quote_age_seconds",
        "fill_rule",
        "fill_percent_change_from_signal",
        "entry_regime",
        "entry_pivot_count",
        "support_reclaim_result",
        "support_distance_pct",
        "signal_to_entry_delay_seconds",
        "manual_exit",
        "manual_exit_reason",
        "order_time",
        "tier",
        "signal_uid",
        "entry_feature_values",
        "entry_feature_null_reasons",
        "mfe_r",
        "mfe_time",
        "mae_r",
        "mae_time",
        "entry_quantity",
        "remaining_quantity",
        "partial_status",
        "partial_exit_done",
        "partial_ineligible_single_lot",
        "partial_quantity",
        "partial_pnl_rupees",
        "partial_profit_r",
        "partial_profit_fraction",
        "exit_legs",
        "r_multiple",
        "initial_stop_loss",
        "initial_risk_per_unit",
        "planned_risk_rupees",
        "max_favorable_r_time",
        "trailing_stop_history",
        "runner_active",
        "profit_lock_stop",
        "profit_lock_r",
        "profit_lock_enabled",
        "trail_close_confirm_enabled",
        "trail_close_confirmed",
        "trail_close_confirmation",
        "paper_exit_parameters",
        "exit_trigger_price",
        "exit_trigger_source",
        "guarded_exit_quote_count",
        "forced_exit_fallback_used",
        "forced_exit_fallback_price",
        "forced_exit_fallback_reason",
        "paper_change_flags_at_entry",
        "paper_change_flags_at_exit",
        "paper_exit_flags_at_entry",
        "paper_exit_flags_at_exit",
        "entry_mode",
        "route",
        "after_cost_pnl",
        "net_pnl",
        "signal_id",
        "signal_time",
        "signal_close",
        "atr_pct",
        "effective_volatility_threshold_pct",
        "momentum_candle",
        "momentum_body_ratio",
        "momentum_body_ratio_threshold",
        "direction_rule",
        "active_paper_change_attributions",
        "confirmation_candle_time",
        "confirmation_close",
        "confirmation_result",
        "confirmation_momentum_candle",
        "confirmation_momentum_body_ratio",
        "confirmation_momentum_body_ratio_threshold",
        "confirmation_bid",
        "confirmation_ask",
        "confirmation_ltp",
        "confirmation_quote_age_seconds",
        "confirmation_delay_seconds",
        "signal_premium",
        "signal_bid",
        "signal_ask",
        "signal_ltp",
        "signal_quote_age_seconds",
        "quote_source",
        "quote_age_seconds",
        "candle_age_seconds",
        "option_token",
        "last_tick_time",
        "tick_gap_seconds",
        "daily_tick_gaps_over_30s",
        "paper_change_flags",
        "paper_change_attributions",
        "paper_change_gate_evaluations",
        "would_pass_baseline",
        "paper_entry_bid_ask_spread",
        "order_premium",
        "order_bid",
        "order_ask",
        "order_ltp",
        "order_quote_age_seconds",
        "paper_entry_quote_is_fresh",
        "paper_entry_risk_rupees",
        "paper_risk_cap_rupees",
        "risk_cap_rupees",
        "invested_amount",
        "lots",
        "lot_size",
        "premium",
        "option_stop_pct",
        "risk_amount",
        "proposed_invested_amount",
        "proposed_lots",
        "proposed_risk_amount",
        "max_capital_per_trade_pct",
        "max_capital_per_trade_amount",
        "banknifty_max_capital_per_trade_pct",
        "banknifty_max_capital_per_trade_amount",
        "max_capital_per_trade_used_pct",
        "max_capital_per_trade_used_amount",
        "max_open_risk_pct",
        "max_open_risk_amount",
        "open_risk_amount",
        "remaining_daily_risk_amount",
        "max_risk_per_trade_ignored",
        "max_lots",
        "premium_cap",
        "lots_reduced_reason",
        "rejection_reason",
        "capital_based_risk_v2",
        "paper_exit_ltp",
        "paper_exit_bid",
        "paper_exit_ask",
        "paper_exit_quote_timestamp",
        "is_ema_reentry",
        "original_trade_id",
        "ema_reentry_eligible",
        "ema_reentry_stop_time",
        "ema_reentry_outcome",
        "reentry_signal_time",
        "reentry_reason",
        "reentry_vwap",
        "reentry_entry_price",
        "reentry_exit_price",
        "reentry_pnl",
        "reentry_outcome",
    ]
    DECISION_COLUMNS = [
        "timestamp", "config_hash", "git_sha", "git_dirty",
        "ticker", "contract_id", "strike", "expiry", "lot_size",
        "underlying_price_at_selection", "signal", "outcome", "score", "reasons",
        "bars_available", "bar", "history", "outcome_detail", "rejection_reason",
        "market_session", "market_hours", "session_timezone",
        "trend_shadow_signal", "trend_shadow_rejection_reason", "strategy_variant",
        "entry_evaluation",
        "event", "ema_reentry_event", "original_trade_id", "stop_time",
        "reentry_signal_time", "reentry_reason", "reentry_vwap",
        "reentry_entry_price", "reentry_exit_price", "reentry_pnl",
        "reentry_outcome",
        "confirmation_event", "signal_id", "signal_uid",
        "entry_feature_values", "entry_feature_null_reasons",
        "order_time", "entry_mode", "route",
        "signal_time", "signal_close", "signal_bar", "signal_premium",
        "signal_bid", "signal_ask", "signal_ltp", "signal_quote_age_seconds",
        "quote_source", "quote_age_seconds", "candle_age_seconds",
        "option_token", "last_tick_time", "tick_gap_seconds",
        "daily_tick_gaps_over_30s", "paper_change_flags",
        "paper_change_attributions", "body_ratio", "body_ratio_threshold",
        "paper_change_gate_evaluations", "would_pass_baseline",
        "body_ratio_source",
        "atr_pct", "effective_volatility_threshold_pct", "momentum_candle",
        "momentum_body_ratio", "momentum_body_ratio_threshold", "direction_rule",
        "active_paper_change_attributions",
        "confirmation_candle_time", "confirmation_close",
        "confirmation_result", "confirmation_delay_seconds",
        "confirmation_body_ratio", "confirmation_body_ratio_threshold",
        "confirmation_momentum_candle", "confirmation_momentum_body_ratio",
        "confirmation_momentum_body_ratio_threshold",
        "confirmation_bid", "confirmation_ask", "confirmation_ltp",
        "confirmation_quote_age_seconds", "order_premium", "order_bid",
        "order_ask", "order_ltp", "order_quote_age_seconds",
        "cancellation_reason", "cancellation_sub_reason",
        "support_resistance_level", "support_resistance_touches",
        "ema_fast_value", "ema_slow_value",
        "invested_amount", "lots", "quantity", "risk_amount", "risk_cap_rupees",
        "tier",
        "premium", "option_stop_pct",
        "proposed_invested_amount", "proposed_lots", "proposed_risk_amount",
        "max_capital_per_trade_pct", "max_capital_per_trade_amount",
        "banknifty_max_capital_per_trade_pct",
        "banknifty_max_capital_per_trade_amount",
        "max_capital_per_trade_used_pct",
        "max_capital_per_trade_used_amount", "max_open_risk_pct",
        "max_open_risk_amount", "open_risk_amount",
        "remaining_daily_risk_amount", "max_risk_per_trade_ignored",
        "max_lots", "premium_cap", "lots_reduced_reason",
        "capital_based_risk_v2",
    ]

    def __init__(
        self,
        root: str = "paper_trading_data",
        config_hash: Optional[str] = None,
        git_sha: Optional[str] = None,
        git_dirty: Optional[bool] = None,
    ) -> None:
        self.root = Path(root)
        if git_sha is None or git_dirty is None:
            identity = get_git_identity()
            git_sha = git_sha or identity.sha
            git_dirty = git_dirty if git_dirty is not None else identity.dirty
        self.config_hash = config_hash
        self.git_sha = git_sha
        self.git_dirty = git_dirty
        self._decision_queue: queue.Queue = queue.Queue(maxsize=DECISION_QUEUE_SIZE)
        self._decision_worker: Optional[threading.Thread] = None
        self._decision_lock = threading.Lock()
        self._decision_closed = False
        self._decision_shutdown_complete = False
        self._decision_drops = 0
        self._decision_last_flush_rows = 0
        self._decision_last_flush_ms = 0.0
        self._decision_compaction_status = "idle"
        self._decision_failure_count = 0
        self._decision_writer_cpu_ms = 0.0
        self._decision_touched_days: set[Path] = set()
        self._decision_sequences: Dict[tuple[Path, int], int] = {}
        self._trade_feature_write_errors = 0
        self._trade_feature_write_warning_at = float("-inf")
        self._trade_feature_write_lock = threading.Lock()

    def _stamp_identity(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        entry = dict(payload)
        if self.config_hash is not None:
            entry.setdefault("config_hash", self.config_hash)
        entry["git_sha"] = self.git_sha
        entry["git_dirty"] = self.git_dirty
        return entry

    def _record_trade_feature_write_error(self, error: Exception) -> None:
        with self._trade_feature_write_lock:
            self._trade_feature_write_errors += 1
            now = time_module.monotonic()
            if now - self._trade_feature_write_warning_at >= 60.0:
                self._trade_feature_write_warning_at = now
                logger.warning(
                    "Paper trade feature serialization failed "
                    "null_reason=feature_error exception=%s",
                    type(error).__name__,
                )

    def feature_telemetry(self) -> Dict[str, int]:
        with self._trade_feature_write_lock:
            return {
                "trade_feature_write_errors": self._trade_feature_write_errors
            }

    @staticmethod
    def _event_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            event_time = value
        else:
            try:
                event_time = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                event_time = datetime.now(timezone.utc)
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        return event_time.astimezone(IST)

    def _day_path(self, timestamp: Any, filename: str) -> Path:
        event_time = self._event_datetime(timestamp)
        iso_week = event_time.isocalendar().week
        directory = (
            self.root
            / event_time.strftime("%Y-%m")
            / f"week_{iso_week:02d}"
            / f"day_{event_time.day:02d}"
        )
        directory.mkdir(parents=True, exist_ok=True)
        return directory / filename

    @staticmethod
    def _parquet_value(value: Any) -> str:
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, default=str, separators=(",", ":"))
        return "" if value is None else str(value)

    @staticmethod
    def _read_parquet(
        path: Path, columns: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        return pd.read_parquet(
            path, engine="fastparquet", columns=columns
        ).to_dict(orient="records")

    @staticmethod
    def _write_parquet(path: Path, rows: List[Dict[str, Any]], columns: List[str]) -> None:
        frame = pd.DataFrame([
            {
                column: PaperTradingRecorder._parquet_value(row.get(column, ""))
                for column in columns
            }
            for row in rows
        ], columns=columns)
        temporary = path.with_name(f".{path.name}.tmp")
        write_parquet(temporary, frame, compression="SNAPPY")
        temporary.replace(path)

    def record_decision(self, payload: Dict[str, Any]) -> None:
        entry = self._stamp_identity(payload)
        for key, value in entry.items():
            if isinstance(value, (dict, list, set, tuple, bytearray)):
                entry[key] = deepcopy(value)
        with self._decision_lock:
            if self._decision_closed:
                self._decision_drops += 1
                self._log_decision_drop()
                return
            if self._decision_worker is None or not self._decision_worker.is_alive():
                if self._decision_worker is not None:
                    self._decision_failure_count += 1
                    logger.error("Restarting stopped paper decision writer")
                self._decision_worker = threading.Thread(
                    target=self._run_decision_writer,
                    name="paper-decision-writer",
                    daemon=True,
                )
                self._decision_worker.start()
                with DECISION_WRITERS_LOCK:
                    DECISION_WRITERS.add(self)
            try:
                self._decision_queue.put_nowait(("decision", entry))
            except queue.Full:
                self._decision_drops += 1
                self._log_decision_drop()

    def _log_decision_drop(self) -> None:
        if self._decision_drops == 1 or self._decision_drops % 100 == 0:
            logger.warning(
                "Paper decision queue full or closed; dropped rows=%d",
                self._decision_drops,
            )

    def decision_telemetry(self) -> Dict[str, Any]:
        return {
            "queue_depth": self._decision_queue.qsize(),
            "last_flush_rows": self._decision_last_flush_rows,
            "last_flush_ms": round(self._decision_last_flush_ms, 3),
            "drops": self._decision_drops,
            "compaction_status": self._decision_compaction_status,
            "write_failures": self._decision_failure_count,
            "writer_cpu_ms": round(self._decision_writer_cpu_ms, 3),
        }

    def _write_decision_part(self, day_dir: Path, hour: int, rows: List[Dict[str, Any]]) -> None:
        parts_dir = day_dir / "decisions"
        parts_dir.mkdir(parents=True, exist_ok=True)
        sequence_key = (parts_dir, hour)
        sequence = self._decision_sequences.get(sequence_key)
        if sequence is None:
            existing = [
                int(match.group(1))
                for path in parts_dir.glob(f"decisions_{hour:02d}_*_*")
                if (match := re.fullmatch(
                    rf"decisions_{hour:02d}_\d{{6}}_(\d+)\.parquet",
                    path.name,
                ))
            ]
            sequence = max(existing, default=0)
        sequence += 1
        self._decision_sequences[sequence_key] = sequence
        stamp = datetime.now(IST).strftime("%H%M%S")
        destination = parts_dir / (
            f"decisions_{hour:02d}_{stamp}_{sequence:06d}.parquet"
        )
        temporary = destination.with_name(f".{destination.name}.tmp")
        nested_columns = {
            column
            for row in rows
            for column, value in row.items()
            if isinstance(value, (dict, list, tuple))
        }
        frame = pd.DataFrame(rows, columns=self.DECISION_COLUMNS).fillna("")
        for column in self.DECISION_COLUMNS:
            if column in nested_columns:
                frame[column] = frame[column].map(self._parquet_value)
            else:
                frame[column] = frame[column].astype(str)
        write_parquet(temporary, frame, compression="SNAPPY")
        os.replace(temporary, destination)
        self._decision_touched_days.add(day_dir)

    def _flush_decision_batch(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        started = time_module.perf_counter()
        cpu_started = time_module.thread_time()
        grouped: Dict[tuple[Path, int], List[Dict[str, Any]]] = {}
        for row in rows:
            timestamp = row.get(
                "timestamp", datetime.now(timezone.utc).isoformat(timespec="seconds")
            )
            event_time = self._event_datetime(timestamp)
            day_dir = self._day_path(timestamp, "decisions.parquet").parent
            grouped.setdefault((day_dir, event_time.hour), []).append(row)
        written = 0
        try:
            for (day_dir, hour), group in grouped.items():
                self._write_decision_part(day_dir, hour, group)
                written += len(group)
        except (OSError, TypeError, ValueError):
            self._decision_failure_count += 1
            logger.exception("Could not flush paper decision batch")
        finally:
            self._decision_last_flush_rows = written
            self._decision_last_flush_ms = (
                time_module.perf_counter() - started
            ) * 1000
            self._decision_writer_cpu_ms += (
                time_module.thread_time() - cpu_started
            ) * 1000

    def _compact_decision_hour(self, day_dir: Path, hour: int) -> bool:
        parts_dir = day_dir / "decisions"
        destination = parts_dir / f"decisions_{hour:02d}.parquet"
        parts = sorted(parts_dir.glob(f"decisions_{hour:02d}_*.parquet"))
        if not parts:
            return destination.exists()
        frames = []
        if destination.exists():
            frames.append(pd.read_parquet(destination, engine="fastparquet"))
        frames.extend(pd.read_parquet(path, engine="fastparquet") for path in parts)
        combined = pd.concat(frames, ignore_index=True, sort=False)
        combined = _deduplicate_decision_frame(combined)
        expected_rows = len(combined)
        temporary = destination.with_name(f".{destination.name}.tmp")
        try:
            if not destination.exists() or len(pd.read_parquet(
                destination, engine="fastparquet"
            )) != expected_rows:
                write_parquet(temporary, combined, compression="SNAPPY")
                written_rows = len(pd.read_parquet(temporary, engine="fastparquet"))
                if written_rows != expected_rows:
                    raise IOError(
                        f"Compaction row-count mismatch for {destination}: "
                        f"{written_rows} != {expected_rows}"
                    )
                os.replace(temporary, destination)
            compacted_rows = len(pd.read_parquet(destination, engine="fastparquet"))
            if compacted_rows != expected_rows:
                raise IOError(
                    f"Compaction row-count mismatch for {destination}: "
                    f"{compacted_rows} != {expected_rows}"
                )
            for path in parts:
                path.unlink(missing_ok=True)
            return True
        finally:
            temporary.unlink(missing_ok=True)

    def _compact_ended_decision_hours(self, final: bool = False) -> None:
        cpu_started = time_module.thread_time()
        now = datetime.now(IST)
        try:
            for day_dir in tuple(self._decision_touched_days):
                parts_dir = day_dir / "decisions"
                hours = {
                    int(match.group(1))
                    for path in parts_dir.glob("decisions_*.parquet")
                    if (match := re.fullmatch(
                        r"decisions_(\d{2})_\d{6}_\d+\.parquet", path.name
                    ))
                }
                for hour in sorted(hours):
                    try:
                        day = datetime.strptime(
                            f"{day_dir.parent.parent.name}-"
                            f"{day_dir.name.removeprefix('day_')}",
                            "%Y-%m-%d",
                        ).date()
                    except ValueError:
                        logger.error(
                            "Could not determine date for decision directory %s",
                            day_dir,
                        )
                        continue
                    if final or day < now.date() or (
                        day == now.date() and hour < now.hour
                    ):
                        self._decision_compaction_status = (
                            f"compacting {day_dir.name} {hour:02d}"
                        )
                        self._compact_decision_hour(day_dir, hour)
        finally:
            self._decision_compaction_status = "idle"
            self._decision_writer_cpu_ms += (
                time_module.thread_time() - cpu_started
            ) * 1000

    def _run_decision_writer(self) -> None:
        pending: List[Dict[str, Any]] = []
        last_flush = time_module.monotonic()
        while True:
            timeout = max(
                0.05,
                DECISION_FLUSH_INTERVAL_SECONDS
                - (time_module.monotonic() - last_flush),
            )
            try:
                kind, payload = self._decision_queue.get(timeout=timeout)
            except queue.Empty:
                if pending:
                    self._flush_decision_batch(pending)
                    pending = []
                    last_flush = time_module.monotonic()
                try:
                    self._compact_ended_decision_hours()
                except (OSError, TypeError, ValueError):
                    self._decision_failure_count += 1
                    logger.exception("Could not compact ended paper decision hours")
                except Exception:
                    self._decision_failure_count += 1
                    logger.exception("Unexpected paper decision compaction failure")
                continue
            try:
                if kind == "decision":
                    pending.append(payload)
                    while self._decision_closed or (
                        len(pending) < DECISION_BATCH_SIZE
                    ):
                        try:
                            next_kind, next_payload = self._decision_queue.get_nowait()
                        except queue.Empty:
                            break
                        try:
                            if next_kind == "decision":
                                pending.append(next_payload)
                            else:
                                self._decision_queue.put_nowait((next_kind, next_payload))
                                break
                        finally:
                            self._decision_queue.task_done()
                    if len(pending) >= DECISION_BATCH_SIZE:
                        self._flush_decision_batch(pending)
                        pending = []
                        last_flush = time_module.monotonic()
                        self._compact_after_flush()
                elif kind == "flush":
                    completed, compact_final_hour = payload
                    try:
                        self._flush_decision_batch(pending)
                        pending = []
                        last_flush = time_module.monotonic()
                        if compact_final_hour:
                            self._compact_ended_decision_hours(final=True)
                        else:
                            self._compact_after_flush()
                    except (OSError, TypeError, ValueError):
                        self._decision_failure_count += 1
                        logger.exception("Could not flush or compact paper decisions")
                    except Exception:
                        self._decision_failure_count += 1
                        logger.exception("Unexpected error flushing paper decisions")
                    finally:
                        completed.set()
                elif kind == "close":
                    try:
                        self._flush_decision_batch(pending)
                        pending = []
                        self._decision_compaction_status = "compacting final hours"
                        self._compact_ended_decision_hours(final=True)
                    except (OSError, TypeError, ValueError):
                        self._decision_failure_count += 1
                        logger.exception("Could not flush or compact final paper decisions")
                    except Exception:
                        self._decision_failure_count += 1
                        logger.exception("Unexpected final paper decision writer error")
                    finally:
                        self._decision_compaction_status = "idle"
                        payload.set()
                    logger.info(
                        "Paper decision writer shutdown complete; queue_depth=%d drops=%d",
                        self._decision_queue.qsize(),
                        self._decision_drops,
                    )
                    return
            except Exception:
                self._decision_failure_count += 1
                logger.exception("Paper decision writer failed processing a queue item")
            finally:
                self._decision_queue.task_done()

    def _compact_after_flush(self) -> None:
        try:
            self._compact_ended_decision_hours()
        except (OSError, TypeError, ValueError):
            self._decision_failure_count += 1
            logger.exception("Could not compact ended paper decision hours")

    def flush_decisions(
        self, timeout: float = 20.0, *, compact_final_hour: bool = False
    ) -> bool:
        worker = self._decision_worker
        if worker is None:
            return True
        if not worker.is_alive():
            if self._decision_shutdown_complete:
                return self._decision_failure_count == 0
            logger.error("Paper decision writer stopped before a flush completed")
            return False
        if self._decision_closed:
            return False
        completed = threading.Event()
        started = time_module.monotonic()
        try:
            self._decision_queue.put(
                ("flush", (completed, compact_final_hour)),
                timeout=max(timeout, 0.0),
            )
        except queue.Full:
            logger.error("Could not queue decision flush before timeout")
            return False
        remaining = max(0.0, timeout - (time_module.monotonic() - started))
        if not completed.wait(remaining):
            logger.error("Paper decision flush did not complete within %.1f seconds", timeout)
            return False
        return self._decision_failure_count == 0

    def close_decisions(self, timeout: float = 20.0) -> bool:
        with self._decision_lock:
            if self._decision_closed:
                worker = self._decision_worker
                return (
                    (worker is None or not worker.is_alive())
                    and self._decision_shutdown_complete
                    and self._decision_failure_count == 0
                )
            self._decision_closed = True
            worker = self._decision_worker
        if worker is None:
            self._decision_shutdown_complete = True
            return True
        if not worker.is_alive():
            logger.error("Paper decision writer stopped before shutdown")
            return False
        completed = threading.Event()
        started = time_module.monotonic()
        try:
            self._decision_queue.put(("close", completed), timeout=timeout)
        except queue.Full:
            logger.error("Could not queue paper decision shutdown before timeout")
            return False
        remaining = max(0.0, timeout - (time_module.monotonic() - started))
        finished = completed.wait(remaining)
        worker.join(max(0.0, timeout - (time_module.monotonic() - started)))
        if not finished or worker.is_alive():
            logger.error("Paper decision writer did not stop within %.1f seconds", timeout)
            return False
        self._decision_shutdown_complete = True
        with DECISION_WRITERS_LOCK:
            DECISION_WRITERS.discard(self)
        return self._decision_failure_count == 0

    def record_trade(self, payload: Dict[str, Any]) -> None:
        entry = self._stamp_identity(payload)
        timestamp = entry.get("timestamp", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        path = self._day_path(timestamp, "trades.parquet")
        rows = self._read_parquet(path)
        trade_id = str(entry.get("trade_id", ""))
        updated = False

        feature_columns = {
            "signal_uid",
            "entry_feature_values",
            "entry_feature_null_reasons",
            "mfe_r",
            "mfe_time",
            "mae_r",
            "mae_time",
        }

        def serialize_row() -> Dict[str, Any]:
            row = {
                column: self._parquet_value(entry.get(column))
                for column in self.TRADE_COLUMNS
                if column not in feature_columns
            }
            feature_errors = {}
            for column in feature_columns:
                try:
                    row[column] = self._parquet_value(entry.get(column))
                except Exception as error:
                    self._record_trade_feature_write_error(error)
                    feature_errors[column] = type(error).__name__
                    row[column] = ""
            if feature_errors:
                existing_reasons = entry.get("entry_feature_null_reasons")
                reasons = (
                    dict(existing_reasons)
                    if isinstance(existing_reasons, dict)
                    else {}
                )
                reasons["feature_error"] = (
                    "feature_error:"
                    + ",".join(sorted(set(feature_errors.values())))
                )
                reasons.update(
                    {
                        column: f"feature_error:{error_class}"
                        for column, error_class in feature_errors.items()
                    }
                )
                row["entry_feature_null_reasons"] = json.dumps(
                    reasons, default=str, separators=(",", ":")
                )
            return row

        serialized_row = serialize_row()
        for index, row in enumerate(rows):
            if trade_id and row.get("trade_id") == trade_id:
                rows[index] = serialized_row
                updated = True
                break
        if not updated:
            rows.append(serialized_row)
        self._write_parquet(path, rows, self.TRADE_COLUMNS)


def _deduplicate_decision_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    comparable = frame.astype("string").fillna("\0")
    return frame.loc[~comparable.duplicated(keep="first")].reset_index(drop=True)


def read_decisions(
    day_path: str | Path,
    columns: Optional[List[str]] = None,
    reporting_step: Optional[ReportingStep] = None,
    hourly_only: bool = False,
) -> pd.DataFrame:
    """Read day decisions; single-source projections retain source row multiplicity."""
    directory = Path(day_path)
    with DECISION_WRITERS_LOCK:
        writers = list(DECISION_WRITERS)
    for writer in writers:
        try:
            directory.resolve().relative_to(writer.root.resolve())
        except ValueError:
            continue
        if not writer.flush_decisions(timeout=20.0):
            raise TimeoutError(f"Timed out flushing decisions before reading {directory}")

    parts_dir = directory / "decisions"
    legacy = directory / "decisions.parquet"
    if hourly_only:
        sources = (
            sorted(parts_dir.glob("decisions_*.parquet"))
            if parts_dir.is_dir()
            else []
        )
    else:
        sources = []
        if legacy.is_file():
            sources.append(legacy)
        sources.extend(sorted(directory.glob("decisions_part*.parquet")))
        if parts_dir.is_dir():
            sources.extend(sorted(parts_dir.glob("decisions_*.parquet")))
    if not sources:
        return pd.DataFrame()

    if columns:
        frames = []
        source_columns = set()
        for source in sources:
            try:
                import gc
                import pyarrow as pyarrow
                import pyarrow.parquet as pyarrow_parquet
            except ImportError:
                pyarrow = None
                pyarrow_parquet = None
            if pyarrow_parquet is not None:
                parquet = pyarrow_parquet.ParquetFile(source)
                available_columns = parquet.schema.names
                row_count = parquet.metadata.num_rows
                if reporting_step is not None:
                    reporting_step.record_parquet_metadata(
                        parquet.metadata.num_row_groups,
                        len(available_columns),
                    )
            else:
                parquet = ParquetFile(source)
                available_columns = parquet.columns
                row_count = parquet.count()
                if reporting_step is not None:
                    reporting_step.record_parquet_metadata(
                        len(parquet.row_groups),
                        len(available_columns),
                    )
            selected_columns = [
                column for column in columns if column in available_columns
            ]
            source_columns.update(available_columns)
            if selected_columns:
                if pyarrow_parquet is not None:
                    table = pyarrow.Table.from_batches(
                        parquet.iter_batches(
                            columns=selected_columns, batch_size=2048
                        )
                    )
                    frame = table.to_pandas().reindex(columns=columns)
                    del table
                else:
                    frame = pd.read_parquet(
                        source,
                        engine="fastparquet",
                        columns=selected_columns,
                    ).reindex(columns=columns)
            else:
                frame = pd.DataFrame(
                    index=range(row_count), columns=columns
                )
            del parquet
            frames.append(frame)
            if pyarrow is not None:
                gc.collect()
                pyarrow.default_memory_pool().release_unused()
        result = frames[0] if len(frames) == 1 else pd.concat(
            frames, ignore_index=True, sort=False
        ).convert_dtypes()
        has_legacy_parts = any(
            source.name.startswith("decisions_part") for source in sources
        )
        has_legacy_overlap = not hourly_only and (
            has_legacy_parts
            or (
                legacy.is_file()
                and any(source.parent != directory for source in sources)
            )
        )
        if has_legacy_overlap and source_columns.issubset(columns):
            result = _deduplicate_decision_frame(result)
        if "timestamp" in result.columns and not result.empty:
            order = pd.to_datetime(
                result["timestamp"],
                format="mixed",
                utc=True,
                errors="coerce",
            )
            result = (
                result.assign(_decision_sort_timestamp=order)
                .sort_values(
                    "_decision_sort_timestamp",
                    kind="mergesort",
                    na_position="last",
                )
                .drop(columns="_decision_sort_timestamp")
                .reset_index(drop=True)
            )
        return result

    frames = [
        pd.read_parquet(source, engine="fastparquet")
        for source in sources
    ]
    if len(frames) == 1:
        result = frames[0]
    else:
        columns = list(dict.fromkeys(
            column for frame in frames for column in frame.columns
        ))
        aligned = [
            frame.reindex(columns=columns).astype(object)
            for frame in frames
        ]
        result = pd.concat(aligned, ignore_index=True, sort=False).convert_dtypes()
    result = _deduplicate_decision_frame(result)
    if "timestamp" in result.columns and not result.empty:
        order = pd.to_datetime(
            result["timestamp"],
            format="mixed",
            utc=True,
            errors="coerce",
        )
        result = (
            result.assign(_decision_sort_timestamp=order)
            .sort_values("_decision_sort_timestamp", kind="mergesort", na_position="last")
            .drop(columns="_decision_sort_timestamp")
            .reset_index(drop=True)
        )
    if columns:
        result = result.reindex(columns=columns)
    return result


def rejected_signal_updates_path(path: str | Path) -> Path:
    rejected_path = Path(path)
    return rejected_path.with_name(
        f"{rejected_path.stem}.updates{rejected_path.suffix}"
    )


def read_rejected_signals(path: str | Path) -> List[Dict[str, Any]]:
    """Read legacy rows and overlay append-only patches by signal ID."""
    rejected_path = Path(path)
    rows: Dict[str, Dict[str, Any]] = {}
    for source_path, is_updates in (
        (rejected_path, False),
        (rejected_signal_updates_path(rejected_path), True),
    ):
        if not source_path.exists():
            continue
        try:
            with source_path.open("r", encoding="utf-8") as source:
                for line_number, line in enumerate(source, 1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Skipping invalid rejected-signal record %s:%d",
                            source_path,
                            line_number,
                        )
                        continue
                    if not isinstance(record, dict):
                        continue
                    signal_id = str(record.get("signal_id", ""))
                    if not signal_id:
                        continue
                    if not is_updates:
                        rows[signal_id] = record
                        continue
                    patch = record.get("patch")
                    if signal_id in rows and isinstance(patch, dict):
                        rows[signal_id].update(patch)
        except OSError:
            logger.exception("Could not read rejected-signal journal %s", source_path)
            raise
    return list(rows.values())


class RejectedSignalJournal:
    """Track rejected signals and annotate their forward option-candle outcomes."""

    HORIZONS_MINUTES = (15, 30, 60)

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.updates_path = rejected_signal_updates_path(path)
        self.pending: Dict[str, Dict[str, Any]] = {}
        self.pending_by_contract: Dict[str, set[str]] = {}
        self.seen_ids = set()
        self._queue: queue.Queue = queue.Queue(
            maxsize=REJECTED_SIGNAL_UPDATE_QUEUE_SIZE
        )
        self._writer: Optional[threading.Thread] = None
        self._writer_lock = threading.Lock()
        self._closed = False
        self._retry_records: List[Dict[str, Any]] = []
        self._stats_lock = threading.Lock()
        self._last_flush_rows = 0
        self._last_flush_ms = 0.0
        self._write_failures = 0
        self._dropped_updates = 0
        self._load_pending()

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            event_time = value
        else:
            try:
                event_time = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=IST)
        return event_time.astimezone(IST)

    @staticmethod
    def _positive_number(value: Any) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if math.isfinite(number) and number > 0 else None

    @staticmethod
    def _gate_for_entry(entry: Dict[str, Any]) -> Optional[str]:
        signal = str(entry.get("signal", "")).upper()
        if signal == "HOLD":
            reasons = entry.get("reasons")
            if isinstance(reasons, list) and any(
                "sideways regime" in str(reason).lower() for reason in reasons
            ):
                return "sideways regime"
        if signal not in {"BUY", "SELL"}:
            return None

        detail = str(entry.get("outcome_detail", entry.get("outcome", "")))
        outcome = str(entry.get("outcome", ""))
        confirmation_event = str(entry.get("confirmation_event", ""))
        if entry.get("event") == "entry_confirmation":
            if confirmation_event == "rejected_by_confirmation":
                return "confirmation failure"
            if confirmation_event == "filter_failed_after_confirmation":
                return "post-confirmation filter"
            if confirmation_event in {"expired_signal", "confirmation_error"}:
                return "confirmation failure"
            return None

        lowered_detail = detail.lower().replace("_", " ")
        if detail == "OPTION_LEG_SKIPPED" or "leg unavailable" in lowered_detail:
            return "leg skipped"
        if "support reversal" in lowered_detail and "body ratio" in lowered_detail:
            return "weak candle momentum"
        if "late window" in lowered_detail or "entry cutoff" in lowered_detail:
            return "trading hours"
        if outcome == "accuracy_filter":
            reason = str(entry.get("rejection_reason", detail)).lower()
            if "volatility" in reason:
                return "volatility"
            if "score" in reason:
                return "score <70"
            return reason.replace("_", " ") or "accuracy filter"
        if outcome == "option_filter":
            reason = str(entry.get("rejection_reason", detail)).lower()
            if "weak candle momentum" in reason:
                return "weak candle momentum"
            if "stale" in reason or "quote" in reason:
                return "stale quote"
            if "premium" in reason and any(
                marker in reason for marker in ("high", "above", "maximum", "max")
            ):
                return "premium too high"
            if "leg" in reason and any(
                marker in reason for marker in ("skip", "unavailable")
            ):
                return "leg skipped"
            return reason.replace("_", " ") or "option filter"
        if outcome in {"risk_blocked", "paper_risk_cap"} or "risk_cap" in lowered_detail:
            return "risk cap"
        if outcome == "paper_entry_cutoff":
            return "trading hours"
        if outcome == "execution_failed":
            return "execution failure"
        return None

    def _load_pending(self) -> None:
        for row in read_rejected_signals(self.path):
            signal_id = str(row.get("signal_id", ""))
            self.seen_ids.add(signal_id)
            if any(
                row.get(f"forward_{minutes}m_status") == "pending"
                for minutes in self.HORIZONS_MINUTES
            ):
                self.pending[signal_id] = row
                self.pending_by_contract.setdefault(
                    str(row.get("contract_id", "")), set()
                ).add(signal_id)

    def telemetry(self) -> Dict[str, Any]:
        with self._stats_lock:
            return {
                "queue_depth": self._queue.qsize(),
                "last_flush_rows": self._last_flush_rows,
                "last_flush_ms": round(self._last_flush_ms, 3),
                "write_failures": self._write_failures,
                "dropped_updates": self._dropped_updates,
                "pending_rows": len(self.pending),
            }

    @staticmethod
    def _repair_jsonl_tail(destination: Any) -> None:
        destination.seek(0, os.SEEK_END)
        end = destination.tell()
        if not end:
            return
        destination.seek(end - 1)
        if destination.read(1) == b"\n":
            destination.seek(0, os.SEEK_END)
            return
        position = end - 1
        while position >= 0:
            destination.seek(position)
            if destination.read(1) == b"\n":
                position += 1
                break
            position -= 1
        line_start = position if position >= 0 else 0
        destination.seek(line_start)
        tail = destination.read(end - line_start)
        try:
            json.loads(tail)
        except (json.JSONDecodeError, UnicodeDecodeError):
            destination.truncate(line_start)
        else:
            destination.seek(0, os.SEEK_END)
            destination.write(b"\n")
        destination.seek(0, os.SEEK_END)

    @classmethod
    def _append_jsonl_records(
        cls, path: Path, records: List[Dict[str, Any]], description: str
    ) -> None:
        payload = "".join(
            json.dumps(record, default=str) + "\n" for record in records
        ).encode("utf-8")
        destination = path.open("r+b") if path.exists() else path.open("w+b")
        with destination:
            cls._repair_jsonl_tail(destination)
            if destination.write(payload) != len(payload):
                raise OSError(f"Short write to {description}")
            destination.flush()

    def _append_update_records(self, records: List[Dict[str, Any]]) -> bool:
        if not records:
            return True
        started = time_module.perf_counter()
        try:
            self._append_jsonl_records(
                self.updates_path, records, "rejected-signal updates"
            )
        except (OSError, TypeError, ValueError):
            with self._stats_lock:
                self._write_failures += 1
            logger.exception(
                "Could not append rejected-signal updates to %s",
                self.updates_path,
            )
            return False
        finally:
            with self._stats_lock:
                self._last_flush_rows = len(records)
                self._last_flush_ms = (
                    time_module.perf_counter() - started
                ) * 1000.0
        return True

    def _run_writer(self) -> None:
        while True:
            kind, payload = self._queue.get()
            try:
                if kind == "updates":
                    records = self._retry_records + payload
                    if self._append_update_records(records):
                        self._retry_records = []
                    else:
                        self._retry_records = records
                elif kind in {"flush", "close"}:
                    if self._retry_records and self._append_update_records(
                        self._retry_records
                    ):
                        self._retry_records = []
                    success = not self._retry_records
                    payload.append(success)
                    payload[0].set()
                    if kind == "close":
                        return
            except Exception:
                with self._stats_lock:
                    self._write_failures += 1
                logger.exception("Rejected-signal writer failed")
            finally:
                self._queue.task_done()

    def flush(self, timeout: float = 5.0) -> bool:
        completed: List[Any] = [threading.Event()]
        with self._writer_lock:
            writer = self._writer
            if self._closed:
                return (
                    (writer is None or not writer.is_alive())
                    and not self._retry_records
                )
            if writer is None:
                return not self._retry_records
            if not writer.is_alive():
                logger.error("Rejected-signal writer stopped before flush")
                return False
            try:
                self._queue.put(("flush", completed), timeout=max(timeout, 0.0))
            except queue.Full:
                logger.error("Could not queue rejected-signal flush before timeout")
                return False
        if not completed[0].wait(timeout):
            logger.error("Rejected-signal flush timed out")
            return False
        return bool(completed[1]) if len(completed) > 1 else False

    def close(self, timeout: float = 5.0) -> bool:
        with self._writer_lock:
            if self._closed:
                writer = self._writer
                if writer is None or not writer.is_alive():
                    return not self._retry_records
                already_closing = True
            else:
                self._closed = True
                writer = self._writer
                already_closing = False
        if writer is None:
            return True
        if already_closing:
            writer.join(timeout=max(timeout, 0.0))
            return not writer.is_alive()
        completed: List[Any] = [threading.Event()]
        try:
            self._queue.put(("close", completed), timeout=max(timeout, 0.0))
        except queue.Full:
            logger.error("Could not queue rejected-signal shutdown before timeout")
            with self._writer_lock:
                self._closed = False
            return False
        finished = completed[0].wait(timeout)
        writer.join(timeout=max(timeout, 0.0))
        return finished and bool(completed[1] if len(completed) > 1 else False)

    def read(self, timeout: float = 5.0) -> List[Dict[str, Any]]:
        with self._writer_lock:
            closed = self._closed
            writer = self._writer
        if closed:
            if writer is not None:
                writer.join(timeout=max(timeout, 0.0))
                if writer.is_alive():
                    raise OSError("Rejected-signal writer did not shut down")
        elif not self.flush(timeout):
            raise OSError("Rejected-signal updates did not flush")
        return read_rejected_signals(self.path)

    def record_rejection(self, entry: Dict[str, Any]) -> None:
        gate = self._gate_for_entry(entry)
        if gate is None:
            return

        rejected_at = self._parse_datetime(entry.get("timestamp"))
        if rejected_at is None:
            logger.error("Rejected signal has an invalid timestamp: %r", entry.get("timestamp"))
            return
        is_confirmation_event = entry.get("event") == "entry_confirmation"
        signal_time_value = (
            entry.get("signal_time")
            if is_confirmation_event
            else entry.get("timestamp")
        )
        signal_time = self._parse_datetime(signal_time_value)
        if signal_time is None:
            logger.error("Rejected signal has an invalid signal time: %r", signal_time_value)
            return
        measurements = entry.get("gate_measurements")
        measurements = measurements if isinstance(measurements, dict) else {}
        signal_id = str(entry.get("signal_id") or uuid4().hex)
        if signal_id in self.seen_ids:
            logger.warning("Ignoring duplicate rejected-signal id %s", signal_id)
            return
        if self._closed:
            logger.error("Rejected-signal journal is closed; rejection was not recorded")
            return

        if entry.get("event") == "entry_confirmation":
            bid = entry.get("confirmation_bid", entry.get("signal_bid"))
            ask = entry.get("confirmation_ask", entry.get("signal_ask"))
            ltp = entry.get("confirmation_ltp", entry.get("signal_ltp"))
            quote_age = entry.get(
                "confirmation_quote_age_seconds",
                entry.get("signal_quote_age_seconds"),
            )
        else:
            bid = measurements.get("bid", entry.get("signal_bid"))
            ask = measurements.get("ask", entry.get("signal_ask"))
            ltp = measurements.get("ltp", entry.get("signal_ltp"))
            quote_age = measurements.get(
                "quote_age_seconds", entry.get("signal_quote_age_seconds")
            )

        option_bar_close = self._positive_number(measurements.get("option_bar_close"))
        confirmation_close = self._positive_number(entry.get("confirmation_close"))
        signal_premium = self._positive_number(
            entry.get("signal_premium", entry.get("signal_ltp"))
        )
        reference_premium = (
            self._positive_number(ltp)
            or confirmation_close
            or signal_premium
            or option_bar_close
        )
        reference_time_value = (
            entry.get("forward_reference_time") or entry.get("timestamp")
        )
        reference_time = self._parse_datetime(reference_time_value)
        if reference_time is None:
            logger.error(
                "Rejected signal has an invalid forward-reference time: %r",
                reference_time_value,
            )
            return

        row: Dict[str, Any] = {
            "signal_id": signal_id,
            "ist_time": signal_time.isoformat(),
            "signal_time_ist": signal_time.isoformat(),
            "rejected_at_ist": rejected_at.isoformat(),
            "forward_reference_time_ist": reference_time.isoformat(),
            "ticker": entry.get("ticker"),
            "contract_id": entry.get("contract_id", ""),
            "config_hash": entry.get("config_hash"),
            "signal": str(entry.get("signal", "")).upper(),
            "route": measurements.get("route")
            or entry.get("route")
            or entry.get("strategy_variant", "scored"),
            "score": entry.get("score"),
            "gate": gate,
            "reason": (
                entry.get("cancellation_sub_reason")
                or entry.get("cancellation_reason")
                or entry.get("rejection_reason")
                or next(
                    (
                        reason
                        for reason in entry.get("reasons", [])
                        if gate == "sideways regime"
                        and "sideways regime" in str(reason).lower()
                    ),
                    None,
                )
                or entry.get("outcome_detail")
            ),
            "outcome_detail": entry.get("outcome_detail"),
            "body_ratio": measurements.get("body_ratio"),
            "body_ratio_threshold": measurements.get("body_ratio_threshold"),
            "body_ratio_source": measurements.get("body_ratio_source"),
            "quote_age_seconds": quote_age,
            "quote_age_threshold_seconds": measurements.get(
                "quote_age_threshold_seconds"
            ),
            "volatility_pct": measurements.get("volatility_pct"),
            "volatility_min_pct": measurements.get("volatility_min_pct"),
            "volatility_max_pct": measurements.get("volatility_max_pct"),
            "adx": measurements.get("adx"),
            "adx_threshold": measurements.get("adx_threshold"),
            "score_threshold": measurements.get("score_threshold"),
            "bid": bid,
            "ask": ask,
            "ltp": ltp,
            "premium_at_signal": signal_premium or self._positive_number(ltp),
            "option_bar_close": measurements.get("option_bar_close"),
            "option_bar_time": measurements.get("option_bar_time"),
            "forward_reference_premium": reference_premium,
            "forward_reference_premium_source": (
                "ltp"
                if self._positive_number(ltp) is not None
                else "confirmation_close"
                if confirmation_close is not None
                else "signal_premium"
                if signal_premium is not None
                else "option_bar_close"
                if option_bar_close is not None
                else None
            ),
        }
        for minutes in self.HORIZONS_MINUTES:
            row[f"forward_{minutes}m_mfe_pct"] = None
            row[f"forward_{minutes}m_mae_pct"] = None
            row[f"forward_{minutes}m_candles"] = None
            row[f"forward_{minutes}m_coverage_pct"] = None
            row[f"forward_{minutes}m_status"] = (
                "pending"
                if row["contract_id"] and reference_premium is not None
                else "unmatched"
            )

        try:
            self._append_jsonl_records(
                self.path, [row], "rejected-signal journal"
            )
        except (OSError, TypeError, ValueError):
            logger.exception("Could not write rejected-signal journal %s", self.path)
            return

        self.seen_ids.add(signal_id)
        if any(
            row[f"forward_{minutes}m_status"] == "pending"
            for minutes in self.HORIZONS_MINUTES
        ):
            self.pending[signal_id] = row
            self.pending_by_contract.setdefault(
                str(row.get("contract_id", "")), set()
            ).add(signal_id)

    def observe_forward_candles(
        self,
        contract_id: str,
        candles: List[Any],
        observed_at: Any,
        interval_seconds: int = 60,
    ) -> None:
        observed_time = self._parse_datetime(observed_at)
        if not contract_id or observed_time is None or interval_seconds <= 0:
            return

        normalized_candles = []
        for candle in candles:
            values = candle.to_dict() if hasattr(candle, "to_dict") else candle
            if not isinstance(values, dict):
                continue
            candle_time = self._parse_datetime(values.get("time", values.get("timestamp")))
            try:
                high = float(values.get("high"))
                low = float(values.get("low"))
            except (TypeError, ValueError, OverflowError):
                continue
            if (
                candle_time is None
                or not math.isfinite(high)
                or not math.isfinite(low)
                or high <= 0
                or low <= 0
            ):
                continue
            normalized_candles.append((candle_time, high, low))

        updates: Dict[str, Dict[str, Any]] = {}
        for signal_id in tuple(self.pending_by_contract.get(str(contract_id), ())):
            current = self.pending.get(signal_id)
            if current is None:
                continue
            reference_time = self._parse_datetime(
                current.get("forward_reference_time_ist")
            )
            reference_premium = self._positive_number(
                current.get("forward_reference_premium")
            )
            if reference_time is None or reference_premium is None:
                continue
            row = dict(current)
            for minutes in self.HORIZONS_MINUTES:
                status_key = f"forward_{minutes}m_status"
                if row.get(status_key) != "pending":
                    continue
                deadline = reference_time + timedelta(minutes=minutes)
                if observed_time < deadline:
                    continue
                window_candles = [
                    (high, low)
                    for candle_time, high, low in normalized_candles
                    if reference_time <= candle_time
                    and candle_time + timedelta(seconds=interval_seconds) <= deadline
                ]
                if window_candles:
                    highs = [high for high, _ in window_candles]
                    lows = [low for _, low in window_candles]
                    expected = max(1, int(minutes * 60 / interval_seconds))
                    row[f"forward_{minutes}m_mfe_pct"] = (
                        (max(highs) - reference_premium) / reference_premium * 100
                    )
                    row[f"forward_{minutes}m_mae_pct"] = (
                        (min(lows) - reference_premium) / reference_premium * 100
                    )
                    row[f"forward_{minutes}m_candles"] = len(window_candles)
                    row[f"forward_{minutes}m_coverage_pct"] = min(
                        100.0, len(window_candles) / expected * 100
                    )
                    row[status_key] = (
                        "complete" if len(window_candles) == expected else "partial"
                    )
                else:
                    row[status_key] = "unmatched"
            if row != current:
                updates[signal_id] = row

        if not updates or not self._write_updates(updates):
            return
        for signal_id, row in updates.items():
            if all(
                row.get(f"forward_{minutes}m_status") != "pending"
                for minutes in self.HORIZONS_MINUTES
            ):
                self.pending.pop(signal_id, None)
                contract_id = str(row.get("contract_id", ""))
                contract_signals = self.pending_by_contract.get(contract_id)
                if contract_signals is not None:
                    contract_signals.discard(signal_id)
                    if not contract_signals:
                        self.pending_by_contract.pop(contract_id, None)
            else:
                self.pending[signal_id] = row

    def _write_updates(self, updates: Dict[str, Dict[str, Any]]) -> bool:
        records = []
        for signal_id, row in updates.items():
            current = self.pending.get(signal_id, {})
            patch = {
                key: value
                for key, value in row.items()
                if key != "signal_id" and current.get(key) != value
            }
            if patch:
                records.append({"signal_id": signal_id, "patch": patch})
        if not records:
            return True
        with self._writer_lock:
            if self._closed:
                logger.error("Rejected-signal writer is closed; update was not queued")
                return False
            if self._writer is None:
                self._writer = threading.Thread(
                    target=self._run_writer,
                    name="rejected-signal-writer",
                    daemon=True,
                )
                self._writer.start()
            try:
                self._queue.put_nowait(("updates", records))
            except queue.Full:
                with self._stats_lock:
                    self._dropped_updates += len(records)
                logger.error(
                    "Rejected-signal update queue full; dropped updates=%d",
                    len(records),
                )
                return False
        return True


class DecisionJournal:
    """Append-only audit log for market data and strategy decisions."""

    MAX_HISTORY_BARS = 5

    def __init__(
        self,
        path: str = "decision_log.jsonl",
        paper_data_dir: Optional[str] = None,
        config_hash: Optional[str] = None,
        git_sha: Optional[str] = None,
        git_dirty: Optional[bool] = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rejected_signal_journal = RejectedSignalJournal(
            self.path.with_name("rejected_signals.jsonl")
        )
        self.config_hash = config_hash
        if git_sha is None or git_dirty is None:
            identity = get_git_identity()
            git_sha = git_sha or identity.sha
            git_dirty = git_dirty if git_dirty is not None else identity.dirty
        self.git_sha = git_sha
        self.git_dirty = git_dirty
        self.paper_recorder = (
            PaperTradingRecorder(
                paper_data_dir, config_hash, self.git_sha, self.git_dirty
            )
            if paper_data_dir
            else None
        )

    def flush_decisions(
        self, timeout: float = 20.0, *, compact_final_hour: bool = False
    ) -> bool:
        started = time_module.monotonic()
        rejected_flushed = self.rejected_signal_journal.flush(timeout)
        if self.paper_recorder is None:
            return rejected_flushed
        remaining = max(0.0, timeout - (time_module.monotonic() - started))
        decisions_flushed = self.paper_recorder.flush_decisions(
            remaining, compact_final_hour=compact_final_hour
        )
        return rejected_flushed and decisions_flushed

    def close(self, timeout: float = 20.0) -> bool:
        started = time_module.monotonic()
        rejected_closed = self.rejected_signal_journal.close(timeout)
        remaining = max(0.0, timeout - (time_module.monotonic() - started))
        decisions_closed = (
            self.paper_recorder.close_decisions(remaining)
            if self.paper_recorder is not None
            else True
        )
        return decisions_closed and rejected_closed

    def log_decision(self, payload: Dict[str, Any]) -> None:
        entry = dict(payload)
        entry.setdefault("contract_id", "")
        if self.config_hash is not None:
            entry["config_hash"] = self.config_hash
        entry["git_sha"] = self.git_sha
        entry["git_dirty"] = self.git_dirty
        history = entry.get("history")
        if isinstance(history, list) and len(history) > self.MAX_HISTORY_BARS:
            entry["history"] = history[-self.MAX_HISTORY_BARS:]
        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        if entry.get("event") == "entry_confirmation":
            detail = normalize_entry_confirmation_detail(entry)
            entry["outcome_detail"] = detail
        else:
            detail = str(entry.get("outcome", "UNKNOWN"))
            entry.setdefault("outcome_detail", detail)
        entry["outcome"] = normalize_decision_outcome(detail)
        if entry["outcome"] in {
            "accuracy_filter", "option_filter", "risk_blocked", "execution_failed",
            "paper_entry_cutoff", "paper_risk_cap",
        }:
            rejection_reason = detail
            if detail.startswith("accuracy_filter_rejected:"):
                rejection_reason = detail.split(":", 1)[1]
            elif detail.startswith(("trade_blocked:", "risk_blocked:")):
                rejection_reason = detail.split(":", 1)[1]
            elif detail.startswith("OPTION_FILTER_"):
                rejection_reason = detail.removeprefix("OPTION_FILTER_").lower().replace("_", " ")
            elif detail.startswith("PAPER_RANGE_BREAKOUT_REJECTED:"):
                rejection_reason = detail.split(":", 1)[1].replace("_", " ").lower()
            elif detail.startswith(("paper_entry_cutoff_blocked:", "entry_cutoff_blocked:")):
                rejection_reason = detail.split(":", 1)[1].replace("_", " ")
            elif detail.startswith(("paper_risk_cap_blocked:", "risk_cap_blocked:")):
                rejection_reason = detail.split(":", 1)[1].replace("_", " ")
            elif detail == "PAPER_RANGE_BREAKOUT_PAPER_ENTRY_CUTOFF_BLOCKED":
                rejection_reason = "paper entry cutoff"
            elif detail == "PAPER_RANGE_BREAKOUT_PAPER_RISK_CAP_BLOCKED":
                rejection_reason = "paper per-trade risk cap"
            entry.setdefault("rejection_reason", rejection_reason)
        event_time = PaperTradingRecorder._event_datetime(entry["timestamp"])
        local_time = event_time.time()
        in_market_hours = time(9, 15) <= local_time < time(15, 30)
        entry.setdefault(
            "market_session",
            "regular_session" if in_market_hours else (
                "before_open" if local_time < time(9, 15) else "after_close"
            ),
        )
        entry.setdefault("market_hours", in_market_hours)
        entry.setdefault("session_timezone", IST.key)
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, default=str) + "\n")
            if self.paper_recorder:
                self.paper_recorder.record_decision(entry)
        except (OSError, TypeError, ValueError):
            # Observability must never interrupt live order handling.
            logger.exception("Could not write decision audit record to %s", self.path)
        try:
            self.rejected_signal_journal.record_rejection(entry)
        except (
            AttributeError,
            KeyError,
            OSError,
            OverflowError,
            TypeError,
            ValueError,
            ZeroDivisionError,
        ):
            logger.exception(
                "Could not record rejected-signal telemetry for %s",
                entry.get("ticker"),
            )


class PaperShadowExitJournal:
    """Persist snapshots of independent paper exit experiments."""

    def __init__(
        self,
        path: str,
        config_hash: Optional[str] = None,
        git_sha: Optional[str] = None,
        git_dirty: Optional[bool] = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.config_hash = config_hash
        if git_sha is None or git_dirty is None:
            identity = get_git_identity()
            git_sha = git_sha or identity.sha
            git_dirty = git_dirty if git_dirty is not None else identity.dirty
        self.git_sha = git_sha
        self.git_dirty = git_dirty
        self.latest: Dict[str, Dict[str, Any]] = {}
        if not self.path.exists():
            return

        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "Skipping invalid shadow-exit journal line %s", line_number
                    )
                    continue
                trade_id = str(record.get("trade_id", ""))
                if trade_id:
                    self.latest[trade_id] = record

    def _append(self, record: Dict[str, Any]) -> None:
        if self.config_hash is not None:
            record.setdefault("config_hash", self.config_hash)
        record["git_sha"] = self.git_sha
        record["git_dirty"] = self.git_dirty
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
        self.latest[str(record["trade_id"])] = dict(record)

    def start(self, record: Dict[str, Any]) -> None:
        entry = dict(record)
        if self.config_hash is not None:
            entry["config_hash"] = self.config_hash
        entry["git_sha"] = self.git_sha
        entry["git_dirty"] = self.git_dirty
        entry["status"] = "open"
        entry["event"] = "opened"
        self._append(entry)

    def update(self, trade_id: str, fields: Dict[str, Any]) -> bool:
        current = self.latest.get(str(trade_id))
        if current is None or current.get("status") != "open":
            return False
        updated = {**current, **fields, "event": "updated"}
        self._append(updated)
        return True

    def close(self, trade_id: str, fields: Dict[str, Any]) -> bool:
        current = self.latest.get(str(trade_id))
        if current is None or current.get("status") != "open":
            return False
        closed = {
            **current,
            **fields,
            "status": "closed",
            "event": "closed",
        }
        self._append(closed)
        return True

    def annotate_actual_exit(self, trade_id: str, fields: Dict[str, Any]) -> bool:
        current = self.latest.get(str(trade_id))
        if current is None:
            return False
        updated = {**current, **fields, "event": "actual_exit_recorded"}
        self._append(updated)
        return True

    def get_open_for_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        open_records = [
            record for record in self.latest.values()
            if record.get("ticker") == symbol and record.get("status") == "open"
        ]
        if not open_records:
            return None
        return max(open_records, key=lambda record: str(record.get("entry_time", "")))


class TradeJournal:
    PAPER_MARK_INTERVAL_SECONDS = 60

    def __init__(
        self,
        path: str = "trades.jsonl",
        paper_data_dir: Optional[str] = None,
        config_hash: Optional[str] = None,
        git_sha: Optional[str] = None,
        git_dirty: Optional[bool] = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.config_hash = config_hash
        if git_sha is None or git_dirty is None:
            identity = get_git_identity()
            git_sha = git_sha or identity.sha
            git_dirty = git_dirty if git_dirty is not None else identity.dirty
        self.git_sha = git_sha
        self.git_dirty = git_dirty
        self.paper_recorder = (
            PaperTradingRecorder(
                paper_data_dir, config_hash, self.git_sha, self.git_dirty
            )
            if paper_data_dir
            else None
        )
        self._last_paper_mark_at: Dict[str, Optional[datetime]] = {}

    def _write_trades(self, trades: List[Dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            for trade in trades:
                handle.write(json.dumps(trade, default=str) + "\n")

    def _stamp_trade_identity(self, trade: Dict[str, Any]) -> None:
        if self.config_hash is not None:
            trade.setdefault("config_hash", self.config_hash)
        trade["git_sha"] = self.git_sha
        trade["git_dirty"] = self.git_dirty

    def log_trade(self, payload: Dict[str, Any]) -> int:
        entry = dict(payload)
        entry.setdefault("contract_id", "")
        self._stamp_trade_identity(entry)
        if not entry.get("timestamp"):
            entry["timestamp"] = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
        if not entry.get("entry_time"):
            entry["entry_time"] = entry["timestamp"]
        entry.setdefault("status", "open")
        entry.setdefault("pnl", 0.0)
        entry.setdefault("exit_source", "BOT")
        entry.setdefault("exit_reason", None)
        entry.setdefault("risk_modifications", [])
        entry.setdefault("trade_id", f"{entry['ticker']}-{entry['timestamp']}-{entry.get('action', 'UNKNOWN')}")
        if entry.get("telegram_trade_id") is None:
            previous = self.read_trades()
            entry["telegram_trade_id"] = max(
                (
                    int(trade["telegram_trade_id"])
                    for trade in previous
                    if isinstance(trade.get("telegram_trade_id"), int)
                    and not isinstance(trade.get("telegram_trade_id"), bool)
                ),
                default=0,
            ) + 1
        self._last_paper_mark_at.pop(str(entry["ticker"]), None)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")
        if self.paper_recorder:
            self.paper_recorder.record_trade(entry)
        return int(entry["telegram_trade_id"])

    def read_trades(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []

        trades: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                line = line.strip()
                if line:
                    try:
                        trades.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping invalid trade journal line %s", line_number)
        used_ids = [
            int(trade["telegram_trade_id"])
            for trade in trades
            if isinstance(trade.get("telegram_trade_id"), int)
            and not isinstance(trade.get("telegram_trade_id"), bool)
        ]
        next_id = max(used_ids, default=0) + 1
        changed = False
        for trade in trades:
            if (
                not isinstance(trade.get("telegram_trade_id"), int)
                or isinstance(trade.get("telegram_trade_id"), bool)
            ):
                trade["telegram_trade_id"] = next_id
                next_id += 1
                changed = True
        if changed:
            self._write_trades(trades)
        return trades

    def log_command(self, command: Dict[str, Any]) -> None:
        path = self.path.with_name("commands.jsonl")
        entry = {
            **command,
            "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")

    def get_open_trade(self, ticker: str, action: Optional[str] = None) -> Optional[Dict[str, Any]]:
        for trade in reversed(self.read_trades()):
            if trade.get("ticker") != ticker:
                continue
            if trade.get("status") != "open":
                continue
            if action and trade.get("action") != action:
                continue
            return trade
        return None

    def update_trade_mark(
        self, ticker: str, current_price: float, action: Optional[str] = None
    ) -> bool:
        """Periodically persist a paper position's latest price for restart recovery."""
        if not math.isfinite(current_price) or current_price <= 0:
            raise ValueError("current_price must be a finite positive number")

        now = datetime.now(timezone.utc)
        if ticker in self._last_paper_mark_at:
            previous_update = self._last_paper_mark_at[ticker]
            if previous_update is None:
                return False
            elapsed = (now - previous_update).total_seconds()
            if 0 <= elapsed < self.PAPER_MARK_INTERVAL_SECONDS:
                return False

        trades = self.read_trades()
        for trade in reversed(trades):
            if trade.get("ticker") != ticker and trade.get("symbol") != ticker:
                continue
            if trade.get("status") != "open":
                continue
            trade_action = str(trade.get("action", "")).upper()
            if action and trade_action != action.upper():
                continue

            self._stamp_trade_identity(trade)
            try:
                previous_update = datetime.fromisoformat(
                    str(trade.get("updated_at", "")).replace("Z", "+00:00")
                )
            except (TypeError, ValueError):
                previous_update = None
            if previous_update is not None:
                if previous_update.tzinfo is None:
                    previous_update = previous_update.replace(tzinfo=timezone.utc)
                previous_update = previous_update.astimezone(timezone.utc)
                elapsed = (now - previous_update).total_seconds()
                if 0 <= elapsed < self.PAPER_MARK_INTERVAL_SECONDS:
                    self._last_paper_mark_at[ticker] = previous_update
                    return False

            trade["last_price"] = float(current_price)
            trade["updated_at"] = now.isoformat(timespec="seconds")
            self._write_trades(trades)
            if self.paper_recorder:
                self.paper_recorder.record_trade(trade)
            self._last_paper_mark_at[ticker] = now
            return True

        logger.error(
            "Cannot persist paper price mark: no open journal trade for %s", ticker
        )
        self._last_paper_mark_at[ticker] = None
        return False

    def update_trade_pnl(self, ticker: str, current_price: float, action: Optional[str] = None) -> float:
        self._last_paper_mark_at.pop(ticker, None)
        trades = self.read_trades()
        for trade in reversed(trades):
            if trade.get("ticker") != ticker:
                continue
            if trade.get("status") != "open":
                continue
            if action and trade.get("action") != action:
                continue
            self._stamp_trade_identity(trade)

            entry_price = float(trade.get("entry", 0.0))
            stop_loss = float(trade.get("stop_loss", 0.0))
            take_profit = float(trade.get("take_profit", 0.0))

            if trade.get("action") == "BUY":
                pnl = current_price - entry_price
                if current_price <= stop_loss:
                    trade["status"] = "closed"
                    trade["exit_price"] = current_price
                    trade["pnl"] = stop_loss - entry_price
                    trade["closed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    trade["reason"] = "STOP_LOSS"
                    trade["exit_reason"] = "STOP_LOSS"
                    self._write_trades(trades)
                    if self.paper_recorder:
                        self.paper_recorder.record_trade(trade)
                    return trade["pnl"]
                if current_price >= take_profit:
                    trade["status"] = "closed"
                    trade["exit_price"] = current_price
                    trade["pnl"] = take_profit - entry_price
                    trade["closed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    trade["reason"] = "TAKE_PROFIT"
                    trade["exit_reason"] = "TAKE_PROFIT"
                    self._write_trades(trades)
                    if self.paper_recorder:
                        self.paper_recorder.record_trade(trade)
                    return trade["pnl"]
            elif trade.get("action") == "SELL":
                pnl = entry_price - current_price
                if current_price >= stop_loss:
                    trade["status"] = "closed"
                    trade["exit_price"] = current_price
                    trade["pnl"] = entry_price - stop_loss
                    trade["closed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    trade["reason"] = "STOP_LOSS"
                    trade["exit_reason"] = "STOP_LOSS"
                    self._write_trades(trades)
                    if self.paper_recorder:
                        self.paper_recorder.record_trade(trade)
                    return trade["pnl"]
                if current_price <= take_profit:
                    trade["status"] = "closed"
                    trade["exit_price"] = current_price
                    trade["pnl"] = entry_price - take_profit
                    trade["closed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    trade["reason"] = "TAKE_PROFIT"
                    trade["exit_reason"] = "TAKE_PROFIT"
                    self._write_trades(trades)
                    if self.paper_recorder:
                        self.paper_recorder.record_trade(trade)
                    return trade["pnl"]
            else:
                pnl = 0.0

            trade["pnl"] = pnl
            trade["last_price"] = current_price
            trade["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._write_trades(trades)
            if self.paper_recorder:
                self.paper_recorder.record_trade(trade)
            return pnl

        return 0.0

    def close_trade(
        self,
        ticker: str,
        exit_price: float,
        action: Optional[str] = None,
        reason: str = "SIGNAL",
        trade_id: Optional[str] = None,
        closed_at: Optional[str] = None,
        exit_source: Optional[str] = None,
        exit_reason: Optional[str] = None,
        manual_exit: Optional[bool] = None,
    ) -> float:
        trades = self.read_trades()
        for trade in reversed(trades):
            if trade.get("ticker") != ticker and trade.get("symbol") != ticker:
                continue
            if trade_id is not None and str(trade.get("trade_id")) != trade_id:
                continue
            if trade.get("status") != "open":
                continue
            trade_action = str(trade.get("action", "")).upper()
            if action and trade_action != action.upper():
                continue

            self._stamp_trade_identity(trade)
            entry_price = float(trade.get("entry", 0.0))
            if trade_action == "BUY":
                pnl = exit_price - entry_price
            elif trade_action == "SELL":
                pnl = entry_price - exit_price
            else:
                pnl = 0.0

            trade["pnl"] = pnl
            if reason == "MANUAL_TARGET" and pnl <= 0:
                reason = "MANUAL_EXIT"
            trade["exit_price"] = exit_price
            trade["status"] = "closed"
            trade["closed_at"] = (
                closed_at
                or datetime.now(timezone.utc).isoformat(timespec="seconds")
            )
            trade["reason"] = reason
            resolved_exit_source = exit_source or (
                "MANUAL"
                if manual_exit
                or reason in {"MANUAL_EXIT", "MANUAL_TARGET"}
                else "BOT"
            )
            is_manual_exit = str(resolved_exit_source).upper() == "MANUAL"
            trade["exit_source"] = resolved_exit_source
            trade["exit_reason"] = exit_reason or reason
            trade["manual_exit"] = is_manual_exit
            trade["manual_exit_reason"] = reason if is_manual_exit else None
            trade["manual_exit_price"] = None
            self._write_trades(trades)
            if self.paper_recorder:
                self.paper_recorder.record_trade(trade)
            self._last_paper_mark_at.pop(ticker, None)
            return pnl

        return 0.0

    def annotate_trade(
        self, ticker: str, fields: Dict[str, Any], action: Optional[str] = None
    ) -> bool:
        """Add execution details calculated by the intraday position manager."""
        trades = self.read_trades()
        for trade in reversed(trades):
            if trade.get("ticker") != ticker or trade.get("status") != "closed":
                continue
            if action and trade.get("action") != action:
                continue
            self._stamp_trade_identity(trade)
            trade.update(fields)
            self._write_trades(trades)
            if self.paper_recorder:
                self.paper_recorder.record_trade(trade)
            return True
        return False

    def update_open_trade(
        self, ticker: str, fields: Dict[str, Any], action: Optional[str] = None
    ) -> bool:
        """Update live target and risk fields without closing the trade."""
        trades = self.read_trades()
        for trade in reversed(trades):
            if trade.get("ticker") != ticker or trade.get("status") != "open":
                continue
            if action and trade.get("action") != action:
                continue
            self._stamp_trade_identity(trade)
            trade.update(fields)
            self._write_trades(trades)
            if self.paper_recorder:
                self.paper_recorder.record_trade(trade)
            return True
        return False

    def current_pnl(self) -> float:
        trades = self.read_trades()
        pnl = 0.0
        for trade in trades:
            pnl += float(trade.get("pnl", 0.0))
        return pnl

    def portfolio_summary(self) -> Dict[str, float]:
        trades = self.read_trades()
        closed = sum(float(t.get("pnl", 0.0)) for t in trades if t.get("status") == "closed")
        open_trades = sum(float(t.get("pnl", 0.0)) for t in trades if t.get("status") == "open")
        return {"closed_pnl": closed, "open_pnl": open_trades, "total_pnl": closed + open_trades}
