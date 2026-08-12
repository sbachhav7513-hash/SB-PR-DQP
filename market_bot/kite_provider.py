from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

try:
    from kiteconnect import KiteConnect, KiteTicker
except ImportError:
    raise ImportError("kiteconnect is required. Install with: pip install kiteconnect")


logger = logging.getLogger(__name__)


@dataclass
class Tick:
    instrument_token: int
    timestamp: datetime
    last_price: float
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0


@dataclass
class KiteConfig:
    api_key: str
    access_token: str
    instrument_tokens: Dict[str, int] = field(default_factory=dict)


class KiteMarketStream:
    def __init__(self, config: KiteConfig, on_tick_callback: Optional[Callable[[Tick], None]] = None) -> None:
        self.config = config
        self.kite = KiteConnect(api_key=config.api_key)
        self.kite.set_access_token(config.access_token)
        self.ticker = KiteTicker(api_key=config.api_key, access_token=config.access_token)
        self.on_tick_callback = on_tick_callback
        self.is_connected = False
        self.connection_lock = threading.Lock()

    def on_ticks(self, ws: any, ticks: List[Dict]) -> None:
        """Callback when ticks arrive from Kite WebSocket."""
        for tick in ticks:
            try:
                tick_obj = Tick(
                    instrument_token=tick.get("instrument_token", 0),
                    timestamp=datetime.fromtimestamp(tick.get("timestamp", 0)),
                    last_price=float(tick.get("last_price", 0.0)),
                    bid=float(tick.get("bid", 0.0)),
                    ask=float(tick.get("ask", 0.0)),
                    volume=int(tick.get("volume", 0)),
                )
                if self.on_tick_callback:
                    self.on_tick_callback(tick_obj)
            except Exception as exc:
                logger.error(f"Error processing tick: {exc}")

    def on_connect(self, ws: any, response: any) -> None:
        """Callback when WebSocket connects."""
        logger.info("Kite WebSocket connected")
        self.is_connected = True
        tokens = list(self.config.instrument_tokens.values())
        if tokens:
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_FULL, tokens)
            logger.info(f"Subscribed to {len(tokens)} instruments")

    def on_close(self, ws: any, code: int, reason: str) -> None:
        """Callback when WebSocket closes."""
        logger.warning(f"Kite WebSocket closed: {code} {reason}")
        self.is_connected = False

    def on_error(self, ws: any, code: int, reason: str) -> None:
        """Callback on WebSocket error."""
        logger.error(f"Kite WebSocket error: {code} {reason}")
        self.is_connected = False

    def start(self) -> None:
        """Connect and start streaming."""
        logger.info("Starting Kite market stream")
        self.ticker.on_ticks = self.on_ticks
        self.ticker.on_connect = self.on_connect
        self.ticker.on_close = self.on_close
        self.ticker.on_error = self.on_error
        self.ticker.connect(threaded=True)

    def stop(self) -> None:
        """Disconnect the stream."""
        logger.info("Stopping Kite market stream")
        if self.ticker:
            self.ticker.close()
        self.is_connected = False

    def wait_for_connection(self, timeout: float = 10.0) -> bool:
        """Wait for WebSocket to connect."""
        start = time.time()
        while not self.is_connected and (time.time() - start) < timeout:
            time.sleep(0.1)
        return self.is_connected
