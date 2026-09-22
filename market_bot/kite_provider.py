from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

try:
    from kiteconnect import KiteConnect, KiteTicker
except ImportError:
    raise ImportError("kiteconnect is required. Install with: pip install kiteconnect")


logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


@dataclass
class Tick:
    instrument_token: int
    timestamp: datetime
    last_price: float
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0
    oi: Optional[int] = None
    iv: Optional[float] = None


@dataclass
class KiteConfig:
    api_key: str
    access_token: str
    trading_mode: str = "intraday_futures"
    instrument_tokens: Dict[str, int] = field(default_factory=dict)
    futures_underlyings: List[str] = field(default_factory=list)
    auto_discover_futures: bool = False
    max_futures: int = 20
    min_futures_volume: int = 0
    options_underlyings: List[str] = field(default_factory=list)
    option_expiry_days: int = 14
    option_expiry_mode: str = "nearest"
    option_strike_step: Dict[str, float] = field(default_factory=dict)
    option_max_strike_distance_pct: float = 0.5
    min_options_volume: int = 0


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
        self._stopping = False
        self.connection_lock = threading.Lock()
        self.contract_specs: Dict[str, Dict[str, int]] = {}
        self.contract_symbols: Dict[str, str] = {}

    def refresh_instrument_tokens(self) -> Dict[str, int]:
        """Resolve configured symbols against Kite's current instrument master."""
        if self.config.trading_mode == "intraday_options":
            if not self.config.options_underlyings:
                raise RuntimeError(
                    "intraday_options requires at least one options_underlyings entry"
                )
            return self._select_current_options()

        if self.config.trading_mode == "intraday_both":
            spot_tokens = dict(self.config.instrument_tokens)
            futures = self._select_current_futures()
            futures_specs = dict(self.contract_specs)
            futures_symbols = dict(self.contract_symbols)

            self.config.instrument_tokens = spot_tokens
            options = self._select_current_options()
            self.contract_specs = {**futures_specs, **self.contract_specs}
            self.contract_symbols = {**futures_symbols, **self.contract_symbols}
            combined = {**futures, **options}
            self.config.instrument_tokens = combined
            logger.info(
                "Combined NFO subscription: %d futures/options contracts",
                len(combined),
            )
            return combined

        if self.config.instrument_tokens and not self.config.futures_underlyings:
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
            if not invalid_symbols:
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
                logger.info("Validated %d configured Kite instrument tokens", len(resolved))
                return resolved
            logger.warning(
                "Configured Kite token validation failed for: %s; falling back to futures discovery.",
                ", ".join(invalid_symbols),
            )

        if self.config.futures_underlyings:
            return self._select_current_futures()

        configured_symbols = ", ".join(self.config.instrument_tokens.keys())
        raise RuntimeError(
            f"No valid Kite instrument tokens are available for the configured symbols: {configured_symbols}"
        )

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
            self.contract_symbols = {}
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
        self.contract_symbols = {
            row["name"].upper(): row["tradingsymbol"] for row in selected_rows
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

    def _select_current_options(self) -> Dict[str, int]:
        """Select the ATM CE and PE contracts for each configured underlying."""
        today = date.today()
        requested = {symbol.upper() for symbol in self.config.options_underlyings}
        instruments = [
            row
            for row in self.kite.instruments("NFO")
            if row.get("instrument_type") in {"CE", "PE"}
            and row.get("name", "").upper() in requested
            and row.get("expiry")
            and row["expiry"] >= today
            and row.get("strike") is not None
            and row.get("instrument_token")
        ]
        if not instruments:
            raise RuntimeError("No current NFO options matched options_underlyings")

        expiries_by_underlying: Dict[str, List[date]] = defaultdict(list)
        for row in instruments:
            underlying = row["name"].upper()
            expiry = row["expiry"]
            if expiry not in expiries_by_underlying[underlying]:
                expiries_by_underlying[underlying].append(expiry)

        expiry_limit = today.toordinal() + max(self.config.option_expiry_days, 0)
        selected_expiries: Dict[str, date] = {}
        expiry_mode = self.config.option_expiry_mode.lower().strip()
        if expiry_mode not in {"nearest", "next_week"}:
            raise ValueError(
                "option_expiry_mode must be 'nearest' or 'next_week'"
            )
        for underlying, expiries in expiries_by_underlying.items():
            eligible = sorted(
                expiry for expiry in expiries if expiry.toordinal() <= expiry_limit
            )
            if expiry_mode == "next_week":
                if len(eligible) < 2:
                    logger.warning(
                        "Skipping %s: next_week expiry is unavailable; nearest expiry will not be used",
                        underlying,
                    )
                    continue
                selected_expiries[underlying] = eligible[1]
            elif eligible:
                selected_expiries[underlying] = eligible[0]

        if not selected_expiries:
            raise RuntimeError(
                f"No {expiry_mode} NFO option expiry matched option_expiry_days"
            )

        candidates = [
            row
            for row in instruments
            if row["expiry"] == selected_expiries.get(row["name"].upper())
        ]
        underlying_tokens = {
            underlying: int(self.config.instrument_tokens[underlying])
            for underlying in selected_expiries
            if underlying in self.config.instrument_tokens
        }
        if len(underlying_tokens) != len(selected_expiries):
            missing = sorted(set(selected_expiries) - set(underlying_tokens))
            raise RuntimeError(
                "Options require spot instrument_tokens for: " + ", ".join(missing)
            )
        underlying_prices = self.kite.ltp([str(token) for token in underlying_tokens.values()])

        selected: Dict[str, dict] = {}
        for underlying in selected_expiries:
            price_record = underlying_prices.get(str(underlying_tokens.get(underlying, "")), {})
            underlying_price = float(price_record.get("last_price", 0))
            if underlying_price <= 0:
                logger.warning("Skipping %s options without an underlying price", underlying)
                continue
            step = float(self.config.option_strike_step.get(underlying, 0))
            if step <= 0:
                strikes = sorted({float(row["strike"]) for row in candidates if row["name"].upper() == underlying})
                step = min(
                    (right - left for left, right in zip(strikes, strikes[1:]) if right > left),
                    default=1,
                )
            atm_strike = round(underlying_price / step) * step
            max_distance_pct = max(float(self.config.option_max_strike_distance_pct), 0.0)
            matching = [
                row
                for row in candidates
                if row["name"].upper() == underlying
                and (
                    abs(float(row["strike"]) - atm_strike) < 1e-9
                    or (
                        underlying_price > 0
                        and abs(float(row["strike"]) - underlying_price)
                        / underlying_price
                        * 100.0
                        <= max_distance_pct
                    )
                )
            ]
            if not matching:
                matching = [
                    row for row in candidates if row["name"].upper() == underlying and abs(float(row["strike"]) - atm_strike) < 1e-9
                ]
            if not matching:
                continue

            for option_type in ("CE", "PE"):
                same_strike = [
                    row for row in matching if row["instrument_type"] == option_type
                ]
                if same_strike:
                    chosen = min(
                        same_strike,
                        key=lambda row: (
                            abs(float(row["strike"]) - underlying_price),
                            abs(float(row["strike"]) - atm_strike),
                            row["tradingsymbol"],
                        ),
                    )
                    selected[f"{underlying}_{option_type}"] = chosen

        if not selected:
            raise RuntimeError("No ATM NFO options matched configured underlyings")

        option_tokens = [str(int(row["instrument_token"])) for row in selected.values()]
        quotes = self.kite.ltp(option_tokens)
        volume_quotes: Dict[str, Dict] = {}
        if self.config.min_options_volume > 0:
            try:
                raw_quotes = self.kite.quote(
                    [f"NFO:{row['tradingsymbol']}" for row in selected.values()]
                )
                volume_quotes = {
                    str(int(row["instrument_token"])): raw_quotes.get(
                        f"NFO:{row['tradingsymbol']}", {}
                    )
                    for row in selected.values()
                }
            except Exception as exc:
                logger.warning("Kite option quote lookup failed: %s", exc)
        eligible = {}
        for symbol, row in selected.items():
            token = str(int(row["instrument_token"]))
            quote = quotes.get(token, {})
            if float(quote.get("last_price", 0)) <= 0:
                logger.warning("Skipping option %s without a usable live quote", symbol)
                continue
            volume_quote = volume_quotes.get(token, quote)
            if self.config.min_options_volume > 0 and int(volume_quote.get("volume", 0)) < self.config.min_options_volume:
                logger.warning("Skipping option %s below minimum volume", symbol)
                continue
            eligible[symbol] = row

        if not eligible:
            raise RuntimeError("No valid option contracts remained after quote validation")

        self.contract_specs = {
            symbol: {"lot_size": int(row.get("lot_size", 1)), "multiplier": 1}
            for symbol, row in eligible.items()
        }
        self.contract_symbols = {
            symbol: row["tradingsymbol"]
            for symbol, row in eligible.items()
        }
        resolved = {
            symbol: int(row["instrument_token"])
            for symbol, row in eligible.items()
        }
        self.config.instrument_tokens = resolved
        logger.info("Selected %d ATM NFO option contracts: %s", len(resolved), ", ".join(resolved))
        return resolved

    def place_market_order(self, symbol: str, side: str, quantity: int) -> str:
        """Place one validated MIS market order for a selected NFO contract."""
        if side not in {"BUY", "SELL"}:
            raise ValueError(f"Unsupported order side: {side}")
        if quantity <= 0:
            raise ValueError("Order quantity must be positive")

        tradingsymbol = self.contract_symbols.get(symbol)
        if not tradingsymbol:
            raise RuntimeError(f"No selected NFO contract is available for {symbol}")

        transaction_type = (
            self.kite.TRANSACTION_TYPE_BUY
            if side == "BUY"
            else self.kite.TRANSACTION_TYPE_SELL
        )
        order_id = self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=self.kite.EXCHANGE_NFO,
            tradingsymbol=tradingsymbol,
            transaction_type=transaction_type,
            quantity=quantity,
            order_type=self.kite.ORDER_TYPE_MARKET,
            product=self.kite.PRODUCT_MIS,
            validity=self.kite.VALIDITY_DAY,
        )
        if not order_id:
            raise RuntimeError(
                f"Kite returned no order id for {side} {quantity} {tradingsymbol}"
            )
        logger.info(
            "Kite order accepted: id=%s side=%s quantity=%s contract=%s",
            order_id,
            side,
            quantity,
            tradingsymbol,
        )
        return str(order_id)

    def wait_for_order_fill(
        self, order_id: str, requested_quantity: int, timeout_seconds: float = 10.0
    ) -> Dict[str, float | int | str]:
        """Wait for a market order to complete and return its execution details."""
        deadline = time.monotonic() + timeout_seconds
        terminal_failures = {"REJECTED", "CANCELLED", "CANCELLED AMO"}
        while time.monotonic() < deadline:
            history = self.kite.order_history(order_id)
            if not history:
                time.sleep(0.25)
                continue

            latest = history[-1]
            status = str(latest.get("status", "")).upper()
            if status == "COMPLETE":
                filled_quantity = int(latest.get("filled_quantity", 0) or 0)
                average_price = float(latest.get("average_price", 0.0) or 0.0)
                if filled_quantity != requested_quantity or average_price <= 0:
                    raise RuntimeError(
                        f"Order {order_id} completed with invalid fill: "
                        f"quantity={filled_quantity}, average_price={average_price}"
                    )
                return {
                    "order_id": str(order_id),
                    "status": status,
                    "filled_quantity": filled_quantity,
                    "average_price": average_price,
                }
            if status in terminal_failures:
                message = latest.get("status_message") or latest.get("status_message_raw")
                raise RuntimeError(f"Order {order_id} {status}: {message or 'no reason'}")
            time.sleep(0.25)

        raise TimeoutError(
            f"Timed out waiting for order {order_id} to complete after {timeout_seconds:.1f}s"
        )

    def assert_flat_account(self) -> None:
        """Fail closed when live trading starts with an unmanaged position."""
        positions = self.kite.positions()
        open_positions = [
            position
            for position in positions.get("net", [])
            if int(position.get("quantity", 0) or 0) != 0
        ]
        if open_positions:
            symbols = ", ".join(
                str(position.get("tradingsymbol", "unknown"))
                for position in open_positions
            )
            raise RuntimeError(
                "Live trading requires a flat account at startup; unmanaged positions: "
                + symbols
            )

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
                token = tick.get("instrument_token")
                if token is None:
                    logger.warning("Dropping Kite tick without instrument_token: %s", tick)
                    continue

                try:
                    instrument_token = int(token)
                except (TypeError, ValueError):
                    logger.warning("Dropping Kite tick with invalid instrument_token=%r: %s", token, tick)
                    continue

                if instrument_token <= 0:
                    logger.warning("Dropping Kite tick with non-positive instrument_token=%s: %s", instrument_token, tick)
                    continue

                raw_timestamp = tick.get("exchange_timestamp", tick.get("timestamp"))
                if raw_timestamp is None:
                    logger.warning("Dropping Kite tick without timestamp: %s", tick)
                    continue
                if isinstance(raw_timestamp, datetime):
                    timestamp = (
                        raw_timestamp.replace(tzinfo=IST)
                        if raw_timestamp.tzinfo is None
                        else raw_timestamp.astimezone(IST)
                    )
                else:
                    timestamp = datetime.fromtimestamp(float(raw_timestamp), tz=IST)

                tick_obj = Tick(
                    instrument_token=instrument_token,
                    timestamp=timestamp,
                    last_price=float(tick.get("last_price", 0.0)),
                    bid=float(tick.get("bid", 0.0)),
                    ask=float(tick.get("ask", 0.0)),
                    volume=int(tick.get("volume_traded", tick.get("volume", 0))),
                    oi=(int(tick["oi"]) if tick.get("oi") is not None else None),
                    iv=(float(tick["iv"]) if tick.get("iv") is not None else None),
                )
                if tick_obj.last_price <= 0:
                    logger.warning(
                        "Dropping Kite tick with non-positive last_price=%s for instrument_token=%s",
                        tick_obj.last_price,
                        instrument_token,
                    )
                    continue
                if self.on_tick_callback:
                    self.on_tick_callback(tick_obj)
            except Exception as exc:
                logger.error(f"Error processing tick: {exc}")

    def on_connect(self, ws: any, response: any) -> None:
        """Callback when WebSocket connects."""
        if self._stopping:
            logger.info("Ignoring Kite WebSocket connection during shutdown")
            ws.close()
            return
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
        if self._stopping:
            logger.info("Ignoring Kite WebSocket reconnect during shutdown")
            return
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
        self._stopping = False
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
        self._stopping = True
        if self.ticker:
            self.ticker.stop_retry()
            self.ticker.close()
        self.is_connected = False

    def wait_for_connection(self, timeout: float = 10.0) -> bool:
        """Wait for WebSocket to connect."""
        start = time.time()
        while not self.is_connected and (time.time() - start) < timeout:
            time.sleep(0.1)
        return self.is_connected
