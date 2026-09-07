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


class KiteHistoricalProvider:
    """Fetch normalized OHLCV candles through the Kite REST API."""

    def __init__(self, api_key: str, access_token: str) -> None:
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)

    def fetch_history(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "5minute",
        continuous: bool = False,
        oi: bool = False,
    ) -> List[Dict]:
        if instrument_token <= 0:
            raise ValueError("instrument_token must be positive")
        if from_date >= to_date:
            raise ValueError("from_date must be earlier than to_date")

        candles = self.kite.historical_data(
            instrument_token,
            from_date,
            to_date,
            interval,
            continuous=continuous,
            oi=oi,
        )
        return [
            {
                "time": candle["date"],
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
                "volume": int(candle.get("volume", 0)),
            }
            for candle in candles
        ]


class KiteMarketStream:
    def __init__(self, config: KiteConfig, on_tick_callback: Optional[Callable[[Tick], None]] = None) -> None:
        self.config = config
        self.kite = KiteConnect(api_key=config.api_key)
        self.kite.set_access_token(config.access_token)
        self.ticker = KiteTicker(api_key=config.api_key, access_token=config.access_token)
        self.on_tick_callback = on_tick_callback
        self.is_connected = False
        self.connection_lock = threading.Lock()

    def refresh_instrument_tokens(self) -> Dict[str, int]:
        """Resolve configured symbols against Kite's current instrument master."""
        master = {
            row["tradingsymbol"]: int(row["instrument_token"])
            for row in self.kite.instruments("NSE")
            if row.get("tradingsymbol") and row.get("instrument_token")
        }
        resolved = {
            symbol: master.get(symbol, int(token))
            for symbol, token in self.config.instrument_tokens.items()
        }

        quotes = self.kite.ltp([str(token) for token in resolved.values()])
        invalid_symbols = [
            symbol
            for symbol, token in resolved.items()
            if str(token) not in quotes
        ]
        if invalid_symbols:
            raise RuntimeError(
                "Unable to resolve valid Kite instrument tokens for: "
                + ", ".join(invalid_symbols)
            )

        for symbol, old_token in self.config.instrument_tokens.items():
            new_token = resolved[symbol]
            if int(old_token) != new_token:
                logger.warning(
                    "Updated stale Kite token for %s: %s -> %s",
                    symbol,
                    old_token,
                    new_token,
                )
        self.config.instrument_tokens = resolved
        logger.info("Validated %d Kite instrument tokens", len(resolved))
        return resolved

    def validate_session(self) -> bool:
        """Verify REST authentication before attempting the WebSocket handshake."""
        try:
            profile = self.kite.profile()
            logger.info(
                "Kite REST session valid for user %s; testing WebSocket separately",
                profile.get("user_id", "unknown"),
            )
            return True
        except Exception as exc:
            logger.error(
                "Kite REST authentication failed. The configured API key and access token "
                "cannot be used: %s",
                exc,
            )
            return False

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
        message = f"{code} {reason}".strip()
        if "403" in str(reason) or "Forbidden" in str(reason):
            logger.warning(
                "Kite WebSocket closed with 403 Forbidden. This usually means the Kite access token is "
                "expired, invalid, or not created for the same account/API key. Regenerate a fresh token "
                "and update kite_config.json."
            )
        else:
            logger.warning(f"Kite WebSocket closed: {message}")
        self.is_connected = False

    def on_error(self, ws: any, code: int, reason: str) -> None:
        """Callback on WebSocket error."""
        message = f"{code} {reason}".strip()
        if "403" in str(reason) or "Forbidden" in str(reason):
            logger.error(
                "Kite WebSocket error: 403 Forbidden. Check that your Kite API key, access token, and account "
                "match the same Zerodha app, and regenerate a fresh access token if needed."
            )
        else:
            logger.error(f"Kite WebSocket error: {message}")
        self.is_connected = False

    def start(self) -> None:
        """Connect and start streaming."""
        logger.info("Starting Kite market stream")
        if not self.validate_session():
            raise RuntimeError("Kite REST authentication failed; WebSocket was not started")
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
