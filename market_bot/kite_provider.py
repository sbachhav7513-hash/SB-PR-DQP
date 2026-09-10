from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
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
    futures_underlyings: List[str] = field(default_factory=list)
    auto_discover_futures: bool = False
    max_futures: int = 20
    min_futures_volume: int = 0


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
        self.ticker = KiteTicker(
            api_key=config.api_key,
            access_token=config.access_token,
            reconnect=True,
            reconnect_max_tries=300,
            reconnect_max_delay=60,
        )
        self.on_tick_callback = on_tick_callback
        self.is_connected = False
        self.connection_lock = threading.Lock()
        self.contract_specs: Dict[str, Dict[str, int]] = {}

    def refresh_instrument_tokens(self) -> Dict[str, int]:
        """Resolve configured symbols against Kite's current instrument master."""
        if self.config.futures_underlyings:
            return self._select_current_futures()

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

    def _select_current_futures(self) -> Dict[str, int]:
        today = date.today()
        requested = {symbol.upper() for symbol in self.config.futures_underlyings}
        candidates = [
            row for row in self.kite.instruments("NFO")
            if row.get("instrument_type") == "FUT"
            and (self.config.auto_discover_futures or row.get("name", "").upper() in requested)
            and row.get("expiry")
            and row["expiry"] >= today
            and row.get("instrument_token")
        ]
        selected: Dict[str, dict] = {}
        for row in candidates:
            underlying = row["name"].upper()
            current = selected.get(underlying)
            if current is None or row["expiry"] < current["expiry"]:
                selected[underlying] = row

        if not selected:
            raise RuntimeError("No current NFO futures contracts matched futures_underlyings")

        selected_rows = list(selected.values())
        tokens = [str(int(row["instrument_token"])) for row in selected_rows]
        fallback_to_ltp = False
        if self.config.auto_discover_futures or self.config.min_futures_volume > 0:
            quote_symbols = [f"NFO:{row['tradingsymbol']}" for row in selected_rows]
            try:
                raw_quotes = self.kite.quote(quote_symbols)
            except Exception as exc:
                logger.warning(
                    "Kite quote endpoint failed for NFO futures, falling back to LTP: %s",
                    exc,
                )
                raw_quotes = {}

            quote_lookup = {
                token: raw_quotes.get(symbol, {})
                for token, symbol in zip(tokens, quote_symbols)
            }

            # If the quote API is incomplete, empty, or omits live prices,
            # downgrade the whole contract gate to the LTP feed instead of
            # poisoning every row with invalid quote data.
            quote_is_complete = bool(raw_quotes) and len(raw_quotes) >= len(selected_rows)
            quote_has_prices = all(
                isinstance(record, dict)
                and float(record.get("last_price", 0.0)) > 0
                for record in quote_lookup.values()
            )
            if not quote_is_complete or not quote_has_prices:
                logger.warning(
                    "Kite quote lookup for NFO futures is incomplete or missing live prices; "
                    "falling back to LTP for %d token(s)",
                    len(tokens),
                )
                quotes = self.kite.ltp(tokens)
                fallback_to_ltp = True
            else:
                quotes = quote_lookup
        else:
            quotes = self.kite.ltp(tokens)

        def evaluate_quotes(quotes_map: Dict[str, Dict], enforce_volume: bool = True) -> List[dict]:
            invalid = []
            for row, token in zip(selected_rows, tokens):
                quote = quotes_map.get(token, {})
                if not isinstance(quote, dict):
                    quote = {}

                skip_quote = False
                if float(quote.get("last_price", 0)) <= 0:
                    skip_quote = True
                elif (
                    enforce_volume
                    and self.config.min_futures_volume > 0
                    and quote.get("volume") is not None
                    and int(quote.get("volume", 0)) < self.config.min_futures_volume
                ):
                    skip_quote = True
                if skip_quote:
                    invalid.append(row["name"])
                    logger.warning(
                        "Skipping NFO futures contract %s without a usable live quote or with insufficient volume",
                        row["name"],
                    )

            return [row for row in selected_rows if row["name"] not in invalid]

        selected_rows = evaluate_quotes(quotes)
        if not selected_rows and not fallback_to_ltp and (
            self.config.auto_discover_futures or self.config.min_futures_volume > 0
        ):
            logger.warning(
                "No NFO futures from the quote feed passed validation; retrying with LTP feed",
            )
            quotes = self.kite.ltp(tokens)
            fallback_to_ltp = True
            selected_rows = evaluate_quotes(quotes)

        if not selected_rows and self.config.min_futures_volume > 0:
            logger.warning(
                "All NFO futures were eliminated by the configured min_futures_volume gate; "
                "retrying quote-only validation without the volume threshold",
            )
            selected_rows = evaluate_quotes(self.kite.ltp(tokens), enforce_volume=False)

        if not selected_rows:
            logger.error(
                "No eligible NFO futures contracts passed quote checks. "
                "Candidates=%d, tokens=%s, min_futures_volume=%d, quote_symbols=%s",
                len(selected_rows),
                ",".join(tokens),
                self.config.min_futures_volume,
                ",".join(quote_symbols),
            )
            logger.warning(
                "Falling back to an empty futures instrument map instead of crashing. "
                "Kite quote availability, min_futures_volume=%d, and futures_underlyings=%s "
                "need inspection before the next run.",
                self.config.min_futures_volume,
                ",".join(self.config.futures_underlyings),
            )
            self.contract_specs = {}
            return {}

        if self.config.auto_discover_futures:
            selected_rows.sort(
                key=lambda row: (
                    float(quotes.get(str(int(row["instrument_token"])), {}).get("volume", 0)),
                    float(quotes.get(str(int(row["instrument_token"])), {}).get("oi", 0)),
                ),
                reverse=True,
            )
        else:
            selected_rows.sort(key=lambda row: (row["expiry"], row["name"]))
        selected_rows = selected_rows[: self.config.max_futures]

        self.contract_specs = {
            row["name"].upper(): {
                "lot_size": int(row.get("lot_size", 1)),
                "multiplier": 1,
            }
            for row in selected_rows
        }
        resolved = {
            row["name"].upper(): int(row["instrument_token"])
            for row in selected_rows
        }
        self.config.instrument_tokens = resolved
        logger.info(
            "Selected %d current NFO futures: %s",
            len(resolved),
            ", ".join(resolved),
        )
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
                "and update KITE_ACCESS_TOKEN in .env."
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

    def on_reconnect(self, ws: any, attempts_count: int) -> None:
        """Log an automatic WebSocket reconnect attempt."""
        logger.warning("Kite WebSocket reconnecting (attempt %d)", attempts_count)

    def on_noreconnect(self, ws: any) -> None:
        """Log when the client's configured reconnect attempts are exhausted."""
        logger.error(
            "Kite WebSocket could not reconnect after %d attempts; restart the bot.",
            self.ticker.reconnect_max_tries,
        )

    def start(self) -> None:
        """Connect and start streaming."""
        logger.info("Starting Kite market stream")
        if not self.validate_session():
            raise RuntimeError("Kite REST authentication failed; WebSocket was not started")
        self.ticker.on_ticks = self.on_ticks
        self.ticker.on_connect = self.on_connect
        self.ticker.on_close = self.on_close
        self.ticker.on_error = self.on_error
        self.ticker.on_reconnect = self.on_reconnect
        self.ticker.on_noreconnect = self.on_noreconnect
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
