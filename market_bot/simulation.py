from __future__ import annotations

import csv
import json
import logging
import math
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .kite_provider import Tick


logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class SimulationMarketStream:
    """Local-only quote source used by the paper simulation mode."""

    def __init__(
        self,
        instrument_tokens: dict[str, int],
        on_tick_callback: Callable[[Tick], None],
        on_connection_change: Optional[Callable[[bool, str], None]] = None,
        script_path: Optional[str | Path] = None,
        tick_interval_seconds: float = 2.0,
    ) -> None:
        interval = float(tick_interval_seconds)
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("Simulation tick interval must be finite and positive")
        self.instrument_tokens = {
            str(symbol): int(token) for symbol, token in instrument_tokens.items()
        }
        self.on_tick_callback = on_tick_callback
        self.on_connection_change = on_connection_change
        self.is_connected = False
        self.contract_specs: dict[str, dict] = {}
        self.contract_symbols: dict[str, str] = {}
        self.contract_exchanges: dict[str, str] = {}
        self.contract_expiries: dict[str, object] = {}
        self.contract_tick_sizes: dict[str, float] = {}
        self.capture_contracts_by_token: dict[int, dict] = {}
        self.capture_contracts_by_symbol: dict[str, dict] = {}
        self.capture_opposites_by_token: dict[int, dict] = {}
        self.capture_only_tokens: list[int] = []
        self.capture_subscription_skipped: list[dict] = []
        self.capture_subscription_started_at: dict[int, datetime] = {}
        self.tick_interval_seconds = interval
        self._prices: dict[str, float] = {}
        self._script = self._load_script(script_path) if script_path else []
        self._script_index = 0
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def _positive_price(value: object) -> float:
        try:
            price = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Invalid simulation price: {value!r}") from exc
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Simulation prices must be finite and positive")
        return price

    @classmethod
    def _load_script(cls, script_path: str | Path) -> list[tuple[str, float]]:
        path = Path(script_path)
        if not path.is_file():
            raise FileNotFoundError(f"Simulation price file not found: {path}")
        if path.suffix.lower() == ".json":
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict) and "ticks" in payload:
                payload = payload["ticks"]
            if isinstance(payload, dict):
                rows = [
                    {"symbol": symbol, "price": price}
                    for symbol, prices in payload.items()
                    for price in (prices if isinstance(prices, list) else [prices])
                ]
            elif isinstance(payload, list):
                rows = payload
            else:
                raise ValueError("Simulation JSON must contain a list or symbol map")
        elif path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        else:
            raise ValueError("Simulation price file must be JSON or CSV")

        script: list[tuple[str, float]] = []
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                raise ValueError(f"Simulation tick {index} must be an object")
            symbol = str(row.get("symbol", "")).strip().upper()
            if not symbol:
                raise ValueError(f"Simulation tick {index} is missing its symbol")
            script.append((symbol, cls._positive_price(row.get("price"))))
        if not script:
            raise ValueError(f"Simulation price file contains no ticks: {path}")
        return script

    def refresh_instrument_tokens(self) -> dict[str, int]:
        return dict(self.instrument_tokens)

    def ensure_symbol(self, symbol: str) -> int:
        normalized = str(symbol).strip().upper()
        if not normalized:
            raise ValueError("Simulation symbol must not be empty")
        with self._lock:
            if normalized not in self.instrument_tokens:
                self.instrument_tokens[normalized] = (
                    max(self.instrument_tokens.values(), default=900_000_000) + 1
                )
            return self.instrument_tokens[normalized]

    def set_price(self, symbol: str, price: object, *, emit: bool = True) -> float:
        normalized = str(symbol).strip().upper()
        value = self._positive_price(price)
        self.ensure_symbol(normalized)
        with self._lock:
            self._prices[normalized] = value
        if emit:
            self.publish(normalized)
        return value

    def current_price(self, symbol: str) -> Optional[float]:
        with self._lock:
            return self._prices.get(str(symbol).strip().upper())

    def publish(self, symbol: str) -> None:
        normalized = str(symbol).strip().upper()
        with self._lock:
            price = self._prices.get(normalized)
            token = self.instrument_tokens.get(normalized)
        if price is None or token is None:
            raise ValueError(f"No simulation price is available for {normalized}")
        self.on_tick_callback(
            Tick(
                instrument_token=token,
                timestamp=datetime.now(IST),
                last_price=price,
                bid=price,
                ask=price,
                volume=1,
            )
        )

    def advance(self) -> bool:
        with self._lock:
            if self._script_index >= len(self._script):
                return False
            symbol, price = self._script[self._script_index]
            self._script_index += 1
        self.set_price(symbol, price)
        return True

    @property
    def script_exhausted(self) -> bool:
        with self._lock:
            return self._script_index >= len(self._script)

    def start(self) -> None:
        if self.is_connected:
            return
        self._stop_event.clear()
        self.is_connected = True
        if self.on_connection_change:
            self.on_connection_change(True, "SIMULATION FEED")
        if self._script:
            self._thread = threading.Thread(
                target=self._run_script,
                name="simulation-price-feed",
                daemon=True,
            )
            self._thread.start()

    def _run_script(self) -> None:
        while not self._stop_event.is_set() and self.advance():
            if self._stop_event.wait(self.tick_interval_seconds):
                return

    def wait_for_connection(self, timeout: float = 15) -> bool:
        return self.is_connected and timeout >= 0

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=max(1.0, self.tick_interval_seconds + 1))
        self.is_connected = False
        if self.on_connection_change:
            self.on_connection_change(False, "SIMULATION FEED STOPPED")

    @staticmethod
    def _deny_broker_operation(*args, **kwargs):
        if args or kwargs:
            logger.error("Blocked broker operation attempted in simulation mode")
        raise RuntimeError("Broker operations are disabled in simulation mode")

    place_market_order = _deny_broker_operation
    wait_for_order_fill = _deny_broker_operation
    place_protective_stop_order = _deny_broker_operation
    modify_protective_stop_order = _deny_broker_operation
    cancel_order = _deny_broker_operation
    get_position_quantity = _deny_broker_operation
    get_positions = _deny_broker_operation
    get_completed_orders = _deny_broker_operation
    cancel_pending_non_protective_orders = _deny_broker_operation
