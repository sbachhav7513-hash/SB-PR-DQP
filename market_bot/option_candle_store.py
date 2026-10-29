from __future__ import annotations

import csv
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional, Set
from zoneinfo import ZoneInfo

from .bar_builder import Bar


IST = ZoneInfo("Asia/Kolkata")
OPTION_CANDLE_FIELDS = [
    "contract_id",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "bid",
    "ask",
    "config_hash",
]


class OptionCandleRecorder:
    """Persist minute premium candles for contracts that pass entry eligibility."""

    def __init__(self, root: str | Path, config_hash: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.config_hash = config_hash
        self._active_contracts: Dict[str, Set[str]] = {}
        self._active_contract_ids: Dict[str, Dict[str, Set[str]]] = {}
        self._seen_timestamps: Dict[Path, Set[str]] = {}
        self._load_active_contracts_for_today()

    @staticmethod
    def _local_timestamp(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=IST)
        return value.astimezone(IST)

    @staticmethod
    def _safe_symbol(symbol: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", symbol.strip())
        if not safe:
            raise ValueError("option symbol cannot produce a safe filename")
        return safe

    def _day_directory(self, timestamp: datetime) -> Path:
        local_time = self._local_timestamp(timestamp)
        return self.root / local_time.date().isoformat()

    def _candle_path(
        self, symbol: str, timestamp: datetime, contract_id: str = ""
    ) -> Path:
        filename = self._safe_symbol(symbol)
        if contract_id:
            filename = f"{self._safe_symbol(contract_id)}__{filename}"
        return self._day_directory(timestamp) / f"{filename}.csv"

    @staticmethod
    def _ensure_schema(path: Path) -> None:
        if not path.exists() or path.stat().st_size == 0:
            return
        with path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames == OPTION_CANDLE_FIELDS:
                return
            rows = list(reader)

        temporary = path.with_name(f".{path.name}.tmp")
        with temporary.open("w", encoding="utf-8", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=OPTION_CANDLE_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)

    def _load_active_contracts_for_today(self) -> None:
        today = datetime.now(IST).date().isoformat()
        directory = self.root / today
        if not directory.exists():
            return
        for path in directory.glob("*.csv"):
            symbol = path.stem.rsplit("__", 1)[-1]
            self._active_contracts.setdefault(today, set()).add(symbol)

    def capture_eligible(
        self,
        symbol: str,
        candles: Iterable[Bar],
        signal_time: datetime,
        contract_id: str = "",
    ) -> int:
        local_signal_time = self._local_timestamp(signal_time)
        day_key = local_signal_time.date().isoformat()
        self._active_contracts.setdefault(day_key, set()).add(symbol)
        if contract_id:
            contract_ids = self._active_contract_ids.setdefault(
                day_key, {}
            ).setdefault(symbol, set())
            contract_ids.add(contract_id)
        captured = 0
        for candle in candles:
            if self._local_timestamp(candle.timestamp).date().isoformat() != day_key:
                continue
            captured += self._append(symbol, candle, contract_id)
        return captured

    def is_active(self, symbol: str, timestamp: datetime) -> bool:
        day_key = self._local_timestamp(timestamp).date().isoformat()
        return symbol in self._active_contracts.get(day_key, set())

    def record_active(
        self, symbol: str, candle: Bar, contract_id: str = ""
    ) -> bool:
        if not self.is_active(symbol, candle.timestamp):
            return False
        day_key = self._local_timestamp(candle.timestamp).date().isoformat()
        active_ids = self._active_contract_ids.get(day_key, {}).get(symbol, set())
        if active_ids:
            captured = 0
            for active_contract_id in active_ids:
                if active_contract_id == contract_id:
                    captured += self._append(symbol, candle, active_contract_id)
            return bool(captured)
        return bool(self._append(symbol, candle, contract_id))

    def _append(self, symbol: str, candle: Bar, contract_id: str = "") -> int:
        timestamp = self._local_timestamp(candle.timestamp)
        path = self._candle_path(symbol, timestamp, contract_id)
        self._ensure_schema(path)
        seen = self._seen_timestamps.get(path)
        if seen is None:
            seen = set()
            if path.exists():
                with path.open("r", encoding="utf-8", newline="") as source:
                    for row in csv.DictReader(source):
                        if row.get("timestamp"):
                            seen.add(row["timestamp"])
            self._seen_timestamps[path] = seen

        timestamp_text = timestamp.isoformat(timespec="seconds")
        if timestamp_text in seen:
            return 0
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "contract_id": contract_id,
            "timestamp": timestamp_text,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "bid": self._positive_quote(candle.bid),
            "ask": self._positive_quote(candle.ask),
            "config_hash": self.config_hash,
        }
        write_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=OPTION_CANDLE_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        seen.add(timestamp_text)
        return 1

    @staticmethod
    def _positive_quote(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        try:
            quote = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return quote if math.isfinite(quote) and quote > 0 else None
