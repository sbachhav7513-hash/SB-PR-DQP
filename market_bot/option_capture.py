from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import queue
import re
import threading
from collections import defaultdict, deque
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
MAX_DAILY_CAPTURE_BYTES = 256 * 1024 * 1024
LOW_TICK_THRESHOLD = 2
CANDLE_FIELDS = [
    "contract_id",
    "underlying",
    "leg",
    "strike",
    "expiry",
    "candle_start_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "tick_count",
    "last_tick_time",
    "bid",
    "ask",
    "config_hash",
    "git_sha",
    "capture_all_evaluated_contracts",
    "low_tick",
    "gap",
]
QUOTE_FIELDS = [
    "time",
    "contract_id",
    "underlying",
    "leg",
    "strike",
    "expiry",
    "ltp",
    "bid",
    "ask",
    "last_tick_time",
    "quote_age_seconds",
    "config_hash",
    "git_sha",
    "capture_all_evaluated_contracts",
]


def _as_ist(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=IST)
    return value.astimezone(IST)


def _minute_start(value: datetime) -> datetime:
    return _as_ist(value).replace(second=0, microsecond=0)


def _iso(value: Optional[datetime]) -> str:
    return _as_ist(value).isoformat(timespec="seconds") if value else ""


def _safe_contract_id(contract_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", contract_id.strip())
    if not safe:
        raise ValueError("contract_id cannot produce a safe filename")
    return safe


def _file_time(value: str) -> Optional[datetime]:
    try:
        return _as_ist(datetime.fromisoformat(value))
    except (TypeError, ValueError):
        return None


class OptionCaptureWriter:
    """Non-blocking option tick capture, CSV persistence, and EOD reporting."""

    def __init__(
        self,
        root: str | Path,
        *,
        config_hash: str,
        git_sha: str,
        contracts_by_token: Dict[int, Dict[str, Any]],
        enabled: bool = True,
        max_queue_size: int = 10000,
        max_daily_bytes: int = MAX_DAILY_CAPTURE_BYTES,
        auto_start: bool = True,
    ) -> None:
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")
        if max_daily_bytes <= 0:
            raise ValueError("max_daily_bytes must be positive")
        self.root = Path(root)
        self.config_hash = config_hash
        self.git_sha = git_sha
        self.enabled = bool(enabled)
        self.max_daily_bytes = max_daily_bytes
        self.contracts_by_token = {
            int(token): dict(metadata)
            for token, metadata in contracts_by_token.items()
        }
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._worker: Optional[threading.Thread] = None
        self._closed = False
        self._stats_lock = threading.Lock()
        self._dropped_rows = 0
        self._pending_warning: Optional[tuple[int, str]] = None
        self._signal_attempts: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        self._thread_state: Dict[str, Any] = {
            "registered": defaultdict(dict),
            "signals": defaultdict(dict),
            "signal_contracts": defaultdict(set),
            "next_minute": {},
            "current_bars": {},
            "completed": defaultdict(lambda: deque(maxlen=420)),
            "last_ticks": {},
            "last_quotes": {},
            "last_quote_write": {},
            "last_quote_written_values": {},
            "seen_candles": defaultdict(set),
            "daily_bytes": defaultdict(int),
            "contracts_captured": defaultdict(set),
            "tick_gaps": defaultdict(int),
            "last_tick_time": {},
            "finalized_dates": set(),
            "skipped_contracts": [],
        }
        self.root.mkdir(parents=True, exist_ok=True)
        if auto_start and self.enabled:
            self.start()

    @property
    def dropped_rows(self) -> int:
        with self._stats_lock:
            return self._dropped_rows

    def memory_state_sizes(self) -> Dict[str, int]:
        sizes: Dict[str, int] = {}
        for name, value in self._thread_state.items():
            if isinstance(value, dict):
                values = list(value.values())
                sizes[f"{name}_keys"] = len(values)
                sizes[f"{name}_items"] = sum(
                    len(item)
                    for item in values
                    if isinstance(item, (dict, set, list, tuple, deque))
                )
            elif isinstance(value, set):
                sizes[f"{name}_items"] = len(value)
        attempts = list(self._signal_attempts.values())
        sizes["signal_attempts_days"] = len(attempts)
        sizes["signal_attempts_items"] = sum(len(day) for day in attempts)
        return sizes

    def start(self) -> None:
        if not self.enabled or self._worker is not None:
            return
        self._worker = threading.Thread(
            target=self._run, name="option-capture-writer", daemon=True
        )
        self._worker.start()

    def record_tick(self, tick: Any) -> bool:
        """Queue a tick without waiting for the writer or touching trading state."""
        if not self.enabled or self._closed:
            return False
        token = int(tick.instrument_token)
        if token not in self.contracts_by_token:
            return False
        payload = {
            "instrument_token": token,
            "timestamp": tick.timestamp,
            "last_price": tick.last_price,
            "bid": tick.bid,
            "ask": tick.ask,
            "volume": tick.volume,
            "oi": tick.oi,
        }
        return self._enqueue(("tick", payload), "tick")

    def register_signal(
        self,
        signal_id: str,
        signal_time: datetime,
        contract: Optional[Dict[str, Any]],
        opposite_contract: Optional[Dict[str, Any]],
    ) -> bool:
        if not self.enabled or self._closed:
            return False
        contract_id = str((contract or {}).get("contract_id", ""))
        with self._stats_lock:
            self._signal_attempts[_as_ist(signal_time).date().isoformat()].setdefault(
                signal_id,
                {
                    "signal_id": signal_id,
                    "signal_time": _as_ist(signal_time),
                    "contract_id": contract_id,
                },
            )
        return self._enqueue(
            (
                "register",
                {
                    "signal_id": signal_id,
                    "signal_time": _as_ist(signal_time),
                    "contract": dict(contract or {}),
                    "opposite_contract": dict(opposite_contract or {}),
                },
            ),
            "signal registration",
        )

    def update_signal_status(
        self, signal_id: str, *, pending: bool, rejected: bool
    ) -> bool:
        if not self.enabled or self._closed:
            return False
        return self._enqueue(
            ("signal_status", (signal_id, pending, rejected)),
            "signal status",
        )

    def set_skipped_contracts(self, skipped: Iterable[Dict[str, Any]]) -> bool:
        if not self.enabled or self._closed:
            return False
        return self._enqueue(("skipped", list(skipped)), "subscription report")

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait for queued work; reserved for tests and shutdown, never trading paths."""
        if not self.enabled or self._worker is None or self._closed:
            return True
        completed = threading.Event()
        if not self._enqueue(("barrier", completed), "flush barrier"):
            return False
        return completed.wait(timeout)

    def close(self, timeout: float = 5.0) -> None:
        if not self.enabled or self._closed:
            return
        self._closed = True
        if self._worker is None:
            return
        completed = threading.Event()
        try:
            self._queue.put(("close", completed), timeout=max(timeout, 0.1))
        except queue.Full:
            self._warn_drop("shutdown event")
            return
        completed.wait(timeout)
        self._worker.join(timeout=max(timeout, 0.1))

    def _enqueue(self, event: tuple, description: str) -> bool:
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            self._warn_drop(description)
            return False

    def _warn_drop(self, reason: str) -> None:
        with self._stats_lock:
            self._dropped_rows += 1
            count = self._dropped_rows
            if count == 1 or count % 100 == 0:
                self._pending_warning = (count, reason)

    def _drain_pending_warning(self) -> None:
        with self._stats_lock:
            warning = self._pending_warning
            self._pending_warning = None
        if warning is not None:
            logger.warning(
                "Option capture dropped rows=%d (latest reason: %s)",
                warning[0],
                warning[1],
            )

    def _run(self) -> None:
        while True:
            try:
                event = self._queue.get(timeout=0.25)
            except queue.Empty:
                self._drain_pending_warning()
                try:
                    self._run_timers(datetime.now(IST))
                except OSError as exc:
                    self._warn_drop(f"timer disk error: {exc}")
                    logger.warning("Option capture timer I/O failed: %s", exc)
                except Exception:
                    self._warn_drop("timer processing error")
                    logger.exception("Option capture timer processing failed")
                continue
            try:
                kind, payload = event
                if kind == "close":
                    try:
                        now = datetime.now(IST)
                        self._flush_registered(now)
                        self._finalize_if_closed(now)
                    except OSError as exc:
                        self._warn_drop(f"shutdown disk error: {exc}")
                        logger.warning("Option capture shutdown flush failed: %s", exc)
                    finally:
                        self._drain_pending_warning()
                        payload.set()
                    return
                if kind == "barrier":
                    try:
                        self._run_timers(datetime.now(IST))
                    finally:
                        payload.set()
                elif kind == "tick":
                    self._handle_tick(payload)
                elif kind == "register":
                    self._handle_registration(payload)
                elif kind == "signal_status":
                    self._handle_signal_status(*payload)
                elif kind == "skipped":
                    self._thread_state["skipped_contracts"] = payload
                self._run_timers(datetime.now(IST))
            except OSError as exc:
                self._warn_drop(f"disk error: {exc}")
                logger.warning("Option capture writer I/O failed: %s", exc)
            except Exception:
                self._warn_drop("writer processing error")
                logger.exception("Option capture writer failed to process a row")
            finally:
                self._drain_pending_warning()
                self._queue.task_done()

    def _run_timers(self, now: datetime) -> None:
        local_now = _as_ist(now)
        self._flush_registered(local_now)
        self._sample_quotes(local_now)
        self._finalize_if_closed(local_now)

    def _handle_tick(self, payload: Dict[str, Any]) -> None:
        token = payload["instrument_token"]
        timestamp = _as_ist(payload["timestamp"])
        minute = _minute_start(timestamp)
        current = self._thread_state["current_bars"].get(token)
        previous_time = self._thread_state["last_tick_time"].get(token)
        if (current and minute < current["minute"]) or (
            previous_time is not None and timestamp < previous_time
        ):
            return
        if previous_time is not None:
            gap = (timestamp - previous_time).total_seconds()
            if gap > 30:
                self._thread_state["tick_gaps"][
                    (timestamp.date().isoformat(), token)
                ] += 1
        self._thread_state["last_tick_time"][token] = timestamp
        self._thread_state["last_ticks"][token] = timestamp
        self._thread_state["last_quotes"][token] = payload

        if current and minute > current["minute"]:
            self._complete_current_bar(token)
            current = None
        if current is None:
            current = {
                "minute": minute,
                "open": payload["last_price"],
                "high": payload["last_price"],
                "low": payload["last_price"],
                "close": payload["last_price"],
                "volume": 0,
                "oi": payload.get("oi"),
                "tick_count": 0,
                "last_tick_time": timestamp,
                "bid": payload.get("bid"),
                "ask": payload.get("ask"),
                "last_cumulative_volume": None,
            }
            self._thread_state["current_bars"][token] = current
        current["high"] = max(current["high"], payload["last_price"])
        current["low"] = min(current["low"], payload["last_price"])
        current["close"] = payload["last_price"]
        current["tick_count"] += 1
        current["last_tick_time"] = timestamp
        if payload.get("oi") is not None:
            current["oi"] = payload["oi"]
        if payload.get("bid", 0) > 0:
            current["bid"] = payload["bid"]
        if payload.get("ask", 0) > 0:
            current["ask"] = payload["ask"]
        cumulative = payload.get("volume")
        if cumulative is not None:
            previous_cumulative = self._thread_state.setdefault(
                "last_cumulative_volume", {}
            ).get(token)
            if previous_cumulative is not None:
                current["volume"] += max(cumulative - previous_cumulative, 0)
            self._thread_state["last_cumulative_volume"][token] = cumulative
        self._flush_registered(timestamp)
        self._sample_quotes(timestamp)
        if timestamp.time() >= datetime_time(15, 30):
            self._finalize_date(timestamp.date())

    def _complete_current_bar(self, token: int) -> None:
        current = self._thread_state["current_bars"].pop(token, None)
        if current is None:
            return
        self._thread_state["completed"][token].append(
            {
                "candle_start_time": current["minute"],
                "open": current["open"],
                "high": current["high"],
                "low": current["low"],
                "close": current["close"],
                "volume": current["volume"],
                "oi": current["oi"],
                "tick_count": current["tick_count"],
                "last_tick_time": current["last_tick_time"],
                "bid": current["bid"],
                "ask": current["ask"],
                "low_tick": current["tick_count"] < LOW_TICK_THRESHOLD,
                "gap": False,
            }
        )

    def _handle_registration(self, payload: Dict[str, Any]) -> None:
        signal_id = payload["signal_id"]
        signal_time = payload["signal_time"]
        signals = self._thread_state["signals"][signal_time.date().isoformat()]
        if signal_id not in signals:
            signals[signal_id] = {
                "signal_id": signal_id,
                "signal_time": signal_time,
                "contract_id": "",
                "forward_candle_time": None,
                "pending": True,
                "rejected_until": None,
            }
        for role in ("contract", "opposite_contract"):
            metadata = payload[role]
            token = metadata.get("instrument_token")
            contract_id = str(metadata.get("contract_id", ""))
            if not token or not contract_id:
                continue
            token = int(token)
            self.contracts_by_token[token] = dict(metadata)
            day_key = signal_time.date().isoformat()
            self._thread_state["registered"][day_key][token] = dict(metadata)
            self._thread_state["signal_contracts"][(day_key, signal_id)].add(token)
            self._thread_state["next_minute"].setdefault(
                (day_key, token), _minute_start(signal_time)
            )
            if role == "contract":
                signals[signal_id]["contract_id"] = contract_id
            self._persist_registered_history(day_key, token, signal_time)

    def _persist_registered_history(
        self, day_key: str, token: int, signal_time: datetime
    ) -> None:
        for candle in self._thread_state["completed"][token]:
            candle_time = candle["candle_start_time"]
            if candle_time.date().isoformat() != day_key:
                continue
            next_minute = self._thread_state["next_minute"].get((day_key, token))
            if next_minute is None or candle_time < next_minute:
                continue
            self._append_candle(day_key, token, candle)
            self._thread_state["next_minute"][(day_key, token)] = (
                candle_time + timedelta(minutes=1)
            )
        self._flush_registered(_as_ist(signal_time))

    def _handle_signal_status(
        self, signal_id: str, pending: bool, rejected: bool
    ) -> None:
        for signals in self._thread_state["signals"].values():
            record = signals.get(signal_id)
            if record is None:
                continue
            record["pending"] = pending
            record["rejected_until"] = (
                record["signal_time"] + timedelta(minutes=10) if rejected else None
            )
            return

    def _flush_registered(self, now: datetime) -> None:
        local_now = _as_ist(now)
        completed_before = _minute_start(local_now)
        day_key = local_now.date().isoformat()
        for token in list(self._thread_state["registered"].get(day_key, {})):
            current = self._thread_state["current_bars"].get(token)
            if current and current["minute"] < completed_before:
                self._complete_current_bar(token)
            next_minute = self._thread_state["next_minute"].get((day_key, token))
            if next_minute is None:
                continue
            cached = {
                item["candle_start_time"]: item
                for item in self._thread_state["completed"][token]
                if item["candle_start_time"].date().isoformat() == day_key
            }
            while next_minute < completed_before:
                candle = cached.get(next_minute)
                if candle is None:
                    candle = {
                        "candle_start_time": next_minute,
                        "open": "",
                        "high": "",
                        "low": "",
                        "close": "",
                        "volume": 0,
                        "oi": "",
                        "tick_count": 0,
                        "last_tick_time": None,
                        "bid": "",
                        "ask": "",
                        "low_tick": False,
                        "gap": True,
                    }
                self._append_candle(day_key, token, candle)
                next_minute += timedelta(minutes=1)
                self._thread_state["next_minute"][(day_key, token)] = next_minute

    def _append_candle(self, day_key: str, token: int, candle: Dict[str, Any]) -> None:
        metadata = self.contracts_by_token[token]
        contract_id = str(metadata["contract_id"])
        path = self._data_path(day_key, contract_id, "candles")
        candle_time = candle["candle_start_time"]
        key = (day_key, token, candle_time.isoformat())
        seen = self._thread_state["seen_candles"][day_key]
        if key in seen:
            return
        if not seen and path.exists():
            self._load_seen_candles(path, day_key, token)
            if key in seen:
                return
        row = {
            "contract_id": contract_id,
            "underlying": metadata.get("underlying", ""),
            "leg": metadata.get("leg", ""),
            "strike": metadata.get("strike", ""),
            "expiry": self._expiry_text(metadata.get("expiry")),
            "candle_start_time": _iso(candle_time),
            "open": candle.get("open", ""),
            "high": candle.get("high", ""),
            "low": candle.get("low", ""),
            "close": candle.get("close", ""),
            "volume": candle.get("volume", 0),
            "oi": candle.get("oi", ""),
            "tick_count": candle.get("tick_count", 0),
            "last_tick_time": _iso(candle.get("last_tick_time")),
            "bid": candle.get("bid", ""),
            "ask": candle.get("ask", ""),
            "config_hash": self.config_hash,
            "git_sha": self.git_sha,
            "capture_all_evaluated_contracts": self.enabled,
            "low_tick": bool(candle.get("low_tick", False)),
            "gap": bool(candle.get("gap", False)),
        }
        if not self._append_row(path, CANDLE_FIELDS, row, day_key):
            return
        seen.add(key)
        self._thread_state["contracts_captured"][day_key].add(contract_id)
        for signals in self._thread_state["signals"].get(day_key, {}).values():
            if contract_id == signals.get("contract_id"):
                signal_end = signals["signal_time"] + timedelta(minutes=60)
                if candle_time >= signal_end:
                    previous = signals.get("forward_candle_time")
                    if previous is None or candle_time > previous:
                        signals["forward_candle_time"] = candle_time

    def _sample_quotes(self, now: datetime) -> None:
        local_now = _as_ist(now)
        day_key = local_now.date().isoformat()
        for token in list(self._thread_state["registered"].get(day_key, {})):
            metadata = self._thread_state["registered"][day_key][token]
            signal_records = []
            for (signal_day, signal_id), tokens in self._thread_state[
                "signal_contracts"
            ].items():
                if signal_day == day_key and token in tokens:
                    signal_records.append(
                        self._thread_state["signals"][day_key].get(signal_id, {})
                    )
            high_frequency = any(
                record.get("pending")
                or (
                    record.get("rejected_until") is not None
                    and local_now < record["rejected_until"]
                )
                for record in signal_records
            )
            interval = 5 if high_frequency else 30
            last_write = self._thread_state["last_quote_write"].get(
                (day_key, token)
            )
            if last_write is not None and (local_now - last_write).total_seconds() < interval:
                continue
            quote = self._thread_state["last_quotes"].get(token, {})
            tick_time = self._thread_state["last_ticks"].get(token)
            values = (
                quote.get("last_price"),
                quote.get("bid"),
                quote.get("ask"),
                _iso(tick_time),
            )
            previous_values = self._thread_state["last_quote_written_values"].get(
                (day_key, token)
            )
            heartbeat_due = (
                last_write is None
                or (local_now - last_write).total_seconds() >= 60
            )
            if values == previous_values and not heartbeat_due:
                continue
            contract_id = str(metadata.get("contract_id", ""))
            row = {
                "time": _iso(local_now),
                "contract_id": contract_id,
                "underlying": metadata.get("underlying", ""),
                "leg": metadata.get("leg", ""),
                "strike": metadata.get("strike", ""),
                "expiry": self._expiry_text(metadata.get("expiry")),
                "ltp": quote.get("last_price", ""),
                "bid": quote.get("bid", ""),
                "ask": quote.get("ask", ""),
                "last_tick_time": _iso(tick_time),
                "quote_age_seconds": (
                    max((local_now - tick_time).total_seconds(), 0.0)
                    if tick_time
                    else ""
                ),
                "config_hash": self.config_hash,
                "git_sha": self.git_sha,
                "capture_all_evaluated_contracts": self.enabled,
            }
            path = self._data_path(day_key, contract_id, "quotes")
            written = self._append_row(path, QUOTE_FIELDS, row, day_key)
            self._thread_state["last_quote_write"][(day_key, token)] = local_now
            self._thread_state["last_quote_written_values"][(day_key, token)] = values
            if written:
                self._thread_state["contracts_captured"][day_key].add(contract_id)

    def _append_row(
        self, path: Path, fields: list[str], row: Dict[str, Any], day_key: str
    ) -> bool:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
        if not path.exists() or path.stat().st_size == 0:
            writer.writeheader()
        writer.writerow(row)
        content = buffer.getvalue()
        byte_count = len(content.encode("utf-8"))
        if self._thread_state["daily_bytes"][day_key] + byte_count > self.max_daily_bytes:
            self._warn_drop("daily capture size cap")
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="") as destination:
            destination.write(content)
        self._thread_state["daily_bytes"][day_key] += byte_count
        return True

    def _load_seen_candles(self, path: Path, day_key: str, token: int) -> None:
        with path.open("r", encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source):
                timestamp = row.get("candle_start_time", "")
                if timestamp:
                    self._thread_state["seen_candles"][day_key].add(
                        (day_key, token, timestamp)
                    )

    def _data_path(self, day_key: str, contract_id: str, kind: str) -> Path:
        return (
            self.root
            / day_key
            / f"{_safe_contract_id(contract_id)}.{kind}.csv"
        )

    @staticmethod
    def _expiry_text(value: Any) -> str:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return "" if value is None else str(value)

    def _finalize_if_closed(self, now: datetime) -> None:
        if _as_ist(now).time() >= datetime_time(15, 30):
            self._finalize_date(_as_ist(now).date())

    def _finalize_date(self, target_date: date) -> None:
        day_key = target_date.isoformat()
        if day_key in self._thread_state["finalized_dates"]:
            return
        close_time = datetime.combine(target_date, datetime_time(15, 30), IST)
        for token in list(self._thread_state["registered"].get(day_key, {})):
            current = self._thread_state["current_bars"].get(token)
            if current and current["minute"] < close_time:
                self._complete_current_bar(token)
        try:
            self._flush_registered(close_time)
        except OSError as exc:
            self._warn_drop(f"end-of-day disk error: {exc}")
            logger.warning("Option capture EOD flush failed for %s: %s", day_key, exc)
        self._write_daily_report(day_key)
        self._compress_daily_files(day_key)
        self._thread_state["finalized_dates"].add(day_key)

    def _write_daily_report(self, day_key: str) -> None:
        signals_by_id = dict(self._thread_state["signals"].get(day_key, {}))
        with self._stats_lock:
            attempted = dict(self._signal_attempts.get(day_key, {}))
        for signal_id, record in attempted.items():
            signals_by_id.setdefault(
                signal_id,
                {
                    **record,
                    "forward_candle_time": None,
                    "pending": False,
                    "rejected_until": None,
                },
            )
        signals = list(signals_by_id.values())
        resolved = sum(bool(record.get("contract_id")) for record in signals)
        forward = sum(record.get("forward_candle_time") is not None for record in signals)
        match_rate = resolved / len(signals) if signals else 1.0
        captured = sorted(self._thread_state["contracts_captured"].get(day_key, set()))
        gaps = {
            self.contracts_by_token[token].get("contract_id", str(token)): count
            for (gap_day, token), count in self._thread_state["tick_gaps"].items()
            if gap_day == day_key
        }
        candle_gaps: Dict[str, int] = defaultdict(int)
        for path in (self.root / day_key).glob("*.candles.csv"):
            with path.open("r", encoding="utf-8", newline="") as source:
                for row in csv.DictReader(source):
                    if row.get("gap", "").lower() == "true":
                        candle_gaps[row.get("contract_id", path.stem)] += 1
        delays = []
        for metadata in self._thread_state["registered"].get(day_key, {}).values():
            resolved_at = _file_time(str(metadata.get("resolved_at", "")))
            subscribed_at = _file_time(
                str(metadata.get("subscription_started_at", ""))
            )
            if resolved_at and subscribed_at:
                delays.append(
                    {
                        "contract_id": metadata.get("contract_id", ""),
                        "seconds": max(
                            (subscribed_at - resolved_at).total_seconds(), 0.0
                        ),
                    }
                )
        report = {
            "date": day_key,
            "signals": len(signals),
            "signals_with_resolved_contract_id": resolved,
            "signals_with_60_minutes_forward_candles": forward,
            "match_rate": round(match_rate, 4),
            "contracts_captured": captured,
            "contracts_captured_count": len(captured),
            "contracts_skipped": self._thread_state["skipped_contracts"],
            "contracts_skipped_count": len(
                self._thread_state["skipped_contracts"]
            ),
            "tick_gaps_over_30_seconds_per_contract": gaps,
            "candle_gaps_per_contract": dict(candle_gaps),
            "dropped_rows": self.dropped_rows,
            "subscription_start_delays": delays,
        }
        directory = self.root / day_key
        directory.mkdir(parents=True, exist_ok=True)
        json_path = directory / "capture_report.json"
        temporary = json_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(json_path)
        text_lines = [
            f"Option capture report — {day_key}",
            f"Signals: {len(signals)}",
            f"Resolved contract_id: {resolved}/{len(signals)}",
            f"60-minute forward candles: {forward}/{len(signals)}",
            f"Match rate: {match_rate:.1%}",
            f"Contracts captured ({len(captured)}): {', '.join(captured)}",
            f"Contracts skipped ({report['contracts_skipped_count']}): "
            f"{json.dumps(report['contracts_skipped'], sort_keys=True)}",
            f"Tick gaps >30s: {json.dumps(gaps, sort_keys=True)}",
            f"Candle gaps: {json.dumps(dict(candle_gaps), sort_keys=True)}",
            f"Dropped rows: {self.dropped_rows}",
            f"Subscription start delays: {json.dumps(delays, sort_keys=True)}",
        ]
        (directory / "capture_report.txt").write_text(
            "\n".join(text_lines) + "\n", encoding="utf-8"
        )
        if match_rate < 0.95:
            logger.critical(
                "OPTION CAPTURE MATCH RATE BELOW 95%%: %s (%.1f%%; %d/%d resolved)",
                day_key,
                match_rate * 100,
                resolved,
                len(signals),
            )
        logger.info(
            "Option capture EOD report written: %s (signals=%d resolved=%d forward60=%d)",
            json_path,
            len(signals),
            resolved,
            forward,
        )

    def _compress_daily_files(self, day_key: str) -> None:
        directory = self.root / day_key
        if not directory.exists():
            return
        for path in list(directory.glob("*.candles.csv")) + list(
            directory.glob("*.quotes.csv")
        ):
            compressed = path.with_suffix(path.suffix + ".gz")
            try:
                with path.open("rb") as source, compressed.open("xb") as raw_target:
                    with gzip.GzipFile(fileobj=raw_target, mode="wb") as target:
                        while chunk := source.read(1024 * 1024):
                            target.write(chunk)
            except FileExistsError:
                continue
            except OSError:
                logger.exception("Could not compress option capture file %s", path)
                if compressed.exists():
                    compressed.unlink()
                continue
            path.unlink()


def load_option_capture(
    root: str | Path, target_date: date | str, decision_row: Dict[str, Any]
) -> Dict[str, list[Dict[str, str]]]:
    """Load exact-contract capture rows; missing contract_id is never inferred."""
    contract_id = str(decision_row.get("contract_id", "")).strip()
    if not contract_id:
        raise ValueError("decision row has no contract_id; contract inference is disabled")
    if isinstance(target_date, datetime):
        day_key = target_date.date().isoformat()
    elif isinstance(target_date, date):
        day_key = target_date.isoformat()
    else:
        day_key = str(target_date)
    directory = Path(root) / day_key
    prefix = _safe_contract_id(contract_id)
    candles = _read_csv_rows(directory, f"{prefix}.candles.csv")
    quotes = _read_csv_rows(directory, f"{prefix}.quotes.csv")
    return {"candles": candles, "quotes": quotes}


def _read_csv_rows(directory: Path, filename: str) -> list[Dict[str, str]]:
    path = directory / filename
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source))
    compressed = path.with_suffix(path.suffix + ".gz")
    if not compressed.exists():
        return []
    with gzip.open(compressed, "rt", encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))
