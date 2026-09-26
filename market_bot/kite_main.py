"""
Zerodha Kite Connect based trading bot with live market streaming.
Uses real-time ticks aggregated into bars, with intraday futures optimization.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from .accuracy_filters import AccuracyFilters
from .bar_builder import BarBuilder, Bar
from .engine import market_session_state, score_market
from .intraday_manager import IntradayManager
from .kite_provider import KiteConfig, KiteHistoricalProvider, KiteMarketStream, Tick
from .market_news import NewsMonitor, apply_news_filter
from .risk_manager import build_risk_plan
from .telegram_notifier import TelegramNotifier
from .trade_journal import DecisionJournal, TradeJournal
from .weekly_report import write_daily_summary, write_weekly_report, write_weekly_review


log_path = Path("kite_bot.log")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_path, mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
HEARTBEAT_INTERVAL_SECONDS = 30 * 60


class KiteTradingBot:
    def _late_window_blocked(self, now: Optional[datetime] = None) -> bool:
        if not self.config.get("late_window_enabled", True):
            return False
        start = datetime.strptime(
            str(self.config.get("late_window_start", "12:00")), "%H:%M"
        ).time()
        end = datetime.strptime(
            str(self.config.get("late_window_end", "13:00")), "%H:%M"
        ).time()
        if start == end:
            return False
        now = now or datetime.now(IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        else:
            now = now.astimezone(IST)
        current = now.time()
        return start <= current < end if start < end else current >= start or current < end

    def _options_enabled(self) -> bool:
        return self.config.get("trading_mode") in {"intraday_options", "intraday_both"}

    def _option_target_increment(self, score: int) -> float:
        """Return the next profit extension as a fraction of entry price."""
        strong_score = int(self.config.get("strong_signal_score", 82))
        if score >= strong_score:
            return float(self.config.get("strong_option_next_target_pct", 0.20))
        return float(self.config.get("normal_option_next_target_pct", 0.10))

    def __init__(self, config_path: str = "kite_config.json") -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config()

        # Initialize intraday manager for futures trading
        self.intraday_manager = IntradayManager(
            account_size=self.config.get("account_size", 100000),
            risk_per_trade_pct=self.config.get("risk_per_trade_pct", 1.0),
            trailing_enabled=self.config.get("trailing_enabled", True),
            trailing_activation_ratio=self.config.get("trailing_activation_ratio", 0.5),
            trailing_distance_ratio=self.config.get("trailing_distance_ratio", 0.25),
            daily_max_loss=self.config.get("daily_max_loss"),
        )

        self.bar_builder = BarBuilder(
            interval_seconds=self.config.get("bar_interval_seconds", 60),
            on_bar_callback=self.on_bar_complete,
        )
        self.kite_stream = KiteMarketStream(
            KiteConfig(
                api_key=self.config["kite_api_key"],
                access_token=self.config["kite_access_token"],
                trading_mode=self.config.get("trading_mode", "intraday_futures"),
                instrument_tokens=self.config["instrument_tokens"],
                futures_underlyings=self.config.get("futures_underlyings", []),
                auto_discover_futures=self.config.get("auto_discover_futures", False),
                max_futures=self.config.get("max_futures", 20),
                min_futures_volume=self.config.get("min_futures_volume", 0),
                options_underlyings=self.config.get("options_underlyings", []),
                option_expiry_days=self.config.get("option_expiry_days", 14),
                option_expiry_mode=self.config.get("option_expiry_mode", "nearest"),
                option_strike_step=self.config.get("option_strike_step", {}),
                min_options_volume=self.config.get("min_options_volume", 0),
            ),
            on_tick_callback=self._on_tick,
            on_connection_change=self._on_connection_change,
        )
        self.config["instrument_tokens"] = self.kite_stream.refresh_instrument_tokens()
        self.paper_trading_enabled = bool(
            self.config.get("paper_trading_enabled", True)
        )
        self.live_orders_enabled = bool(self.config.get("live_orders_enabled", False))
        if self.paper_trading_enabled and self.live_orders_enabled:
            raise RuntimeError(
                "paper_trading_enabled and live_orders_enabled cannot both be true"
            )
        if self.live_orders_enabled and not self.config.get("live_orders_confirmed", False):
            raise RuntimeError(
                "live_orders_enabled requires live_orders_confirmed=true in kite_config.json"
            )
        self.intraday_manager.set_contract_specs(self.kite_stream.contract_specs)
        self._warm_up_bars()
        self.telegram_notifier = TelegramNotifier(
            token=self.config.get("telegram_token"),
            chat_id=self.config.get("telegram_chat_id"),
        )
        self.paper_trading_dir = self.config.get("paper_trading_dir", "paper_trading_data")
        self.trade_journal = TradeJournal("trades.jsonl", self.paper_trading_dir)
        self.intraday_manager.restore_session_trades(self.trade_journal.read_trades())
        self.decision_journal = DecisionJournal(
            self.config.get("decision_log_path", "decision_log.jsonl"),
            self.paper_trading_dir,
        )
        self.weekly_report_dir = Path(
            self.config.get("weekly_report_dir", ".")
        )
        self.last_weekly_report_date = None
        self.last_daily_summary_date = None
        self._entries_paused = False
        self._risk_state_reconciled = not self.live_orders_enabled
        if self.live_orders_enabled:
            self._reconcile_live_state()
        self.symbol_map = {v: k for k, v in self.config["instrument_tokens"].items()}
        self.latest_prices: Dict[str, float] = {}
        self.option_quote_cache: Dict[str, dict] = {}
        self.premarkarket_candidates: list[tuple[str, str, int, str]] = []
        self.benchmark_symbol = self.config.get("benchmark_symbol", "NIFTY")
        self.use_market_context = self.config.get("use_market_context", True)
        self.accuracy_filters = AccuracyFilters(
            min_entry_score=int(self.config.get("min_entry_score", 75)),
            min_volatility_pct=float(self.config.get("min_volatility_pct", 0.05)),
            max_volatility_pct=float(self.config.get("max_volatility_pct", 5.0)),
        )
        self.news_monitor = NewsMonitor(
            feeds=self.config.get("news_feeds"),
            refresh_seconds=self.config.get("news_refresh_seconds", 900),
        ) if self.config.get("news_enabled", True) else None

    def _on_connection_change(self, connected: bool, reason: str) -> None:
        self._entries_paused = not connected
        if not connected:
            logger.error("Kite connection lost; pausing new entries: %s", reason)
            notifier = getattr(self, "telegram_notifier", None)
            if notifier:
                notifier.send_message(f"URGENT: Kite connection lost; new entries paused.\n{reason}")
            return

        logger.info("Kite connection restored; reconciling broker state")
        try:
            if self.live_orders_enabled:
                self._reconcile_live_state()
            self._entries_paused = False
            notifier = getattr(self, "telegram_notifier", None)
            if notifier:
                notifier.send_message("Kite connection restored; broker state reconciled.")
        except Exception as exc:
            self._entries_paused = True
            logger.exception("Broker reconciliation failed after reconnect")
            notifier = getattr(self, "telegram_notifier", None)
            if notifier:
                notifier.send_message(f"URGENT: broker reconciliation failed; trading paused.\n{exc}")

    def _persist_risk_state(self, positions: list[dict], orders: list[dict]) -> None:
        target_date = datetime.now(IST).date().isoformat()
        realized_pnl = sum(
            float(row.get("realised", row.get("realized", 0.0)) or 0.0)
            for row in positions
        )
        unrealized_pnl = sum(
            float(
                row.get(
                    "unrealised",
                    row.get("unrealized", row.get("pnl", 0.0)),
                )
                or 0.0
            )
            for row in positions
        )
        state_dir = Path(self.config.get("risk_state_dir", "."))
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / f"risk_state_{target_date}.json"
        path.write_text(
            json.dumps(
                {
                    "trading_date": target_date,
                    "broker_positions": positions,
                    "completed_orders": orders,
                    "realized_pnl": realized_pnl,
                    "unrealized_pnl": unrealized_pnl,
                    "daily_pnl": realized_pnl,
                    "active_positions": self.intraday_manager.get_all_open_positions(),
                    "updated_at": datetime.now(IST).isoformat(timespec="seconds"),
                },
                default=str,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _reconcile_live_state(self) -> None:
        positions = self.kite_stream.get_positions()
        orders = self.kite_stream.get_completed_orders()
        broker_symbol_map = {
            trading_symbol: symbol
            for symbol, trading_symbol in self.kite_stream.contract_symbols.items()
        }
        broker_positions = {
            broker_symbol_map.get(
                row.get("tradingsymbol", ""), row.get("tradingsymbol", "")
            ): row
            for row in positions
            if int(row.get("quantity", 0) or 0) != 0
        }
        open_trades = {
            trade.get("ticker"): trade
            for trade in self.trade_journal.read_trades()
            if trade.get("status") == "open"
        }
        if set(broker_positions) != set(open_trades):
            raise RuntimeError(
                "Broker positions and open trade journal cannot be reconciled: "
                f"broker={sorted(broker_positions)}, journal={sorted(open_trades)}"
            )

        self.intraday_manager.active_positions.clear()
        for symbol, broker_position in broker_positions.items():
            trade = open_trades[symbol]
            quantity = abs(int(broker_position.get("quantity", 0) or 0))
            direction = "BUY" if int(broker_position.get("quantity", 0) or 0) > 0 else "SELL"
            entry_price = float(trade.get("entry", broker_position.get("average_price", 0.0)))
            stop_loss = float(trade.get("stop_loss", entry_price))
            take_profit = float(trade.get("take_profit", entry_price))
            if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
                raise RuntimeError(f"Open trade {symbol} has incomplete risk levels")
            if not trade.get("protection_order_id"):
                raise RuntimeError(f"Open trade {symbol} has no recorded protective stop")
            estimated_risk = self.intraday_manager.estimate_trade_risk(
                symbol, quantity, entry_price, stop_loss
            )
            if estimated_risk > self.intraday_manager.max_risk_per_trade + 1e-6:
                raise RuntimeError(
                    f"Open trade {symbol} exceeds the per-trade risk cap: "
                    f"{estimated_risk:.2f} > {self.intraday_manager.max_risk_per_trade:.2f}"
                )
            self.intraday_manager.register_position(
                symbol, direction, quantity, entry_price, stop_loss, take_profit,
                signal_score=trade.get("score"),
            )
            if trade.get("protection_order_id"):
                self.intraday_manager.active_positions[symbol]["protection_order_id"] = (
                    trade["protection_order_id"]
                )
        self._persist_risk_state(positions, orders)
        realized_pnl = sum(
            float(row.get("realised", row.get("realized", 0.0)) or 0.0)
            for row in positions
        )
        self.intraday_manager.daily_pnl = realized_pnl
        self._risk_state_reconciled = True

    def _reconcile_after_order_failure(self, symbol: str) -> None:
        self._entries_paused = True
        try:
            self._reconcile_live_state()
            self._entries_paused = False
        except Exception as exc:
            logger.exception("[%s] Broker state remains uncertain after order failure", symbol)
            self.telegram_notifier.send_message(
                f"URGENT: {symbol} order result is uncertain; trading paused.\n{exc}"
            )

    def _persist_current_live_risk_state(self) -> None:
        if not self.live_orders_enabled:
            return
        try:
            self._persist_risk_state(
                self.kite_stream.get_positions(),
                self.kite_stream.get_completed_orders(),
            )
        except Exception:
            logger.exception("Could not persist current broker risk state")

    def _preferred_option_symbol(self, underlying: str, signal: str) -> Optional[str]:
        """Map a directional signal to the correct option contract for one underlying."""
        if not self._options_enabled():
            return None
        if not underlying:
            return None
        preferred_map = {
            "BUY": "CE",
            "SELL": "PE",
        }
        required_type = preferred_map.get(signal)
        if required_type is None:
            return None
        option_key = f"{underlying.upper()}_{required_type}"
        if option_key in self.config.get("instrument_tokens", {}):
            return option_key
        fallback = (
            f"{underlying.upper()}_PE"
            if required_type == "CE"
            else f"{underlying.upper()}_CE"
        )
        return fallback if fallback in self.config.get("instrument_tokens", {}) else None

    def _option_leg_is_active(self, symbol: str, signal: str) -> bool:
        """Only allow the preferred option leg to trade for a given underlying."""
        if not self._options_enabled():
            return True
        if "_" not in symbol:
            return True
        underlying = symbol.rsplit("_", 1)[0].upper()
        preferred = self._preferred_option_symbol(underlying, signal)
        if preferred is None:
            return True
        return symbol == preferred

    def _option_trade_action(self, symbol: str, signal: str) -> str:
        """Buy the selected option leg instead of shorting the bearish leg."""
        if self._options_enabled() and symbol.endswith("_PE") and signal == "SELL":
            return "BUY"
        return signal

    def _option_quality_gate(
        self,
        symbol: str,
        signal: str,
        score: Optional[int] = None,
    ) -> tuple[bool, str]:
        """Reject options that fail sanity checks, with a softer fallback for healthy setups."""
        if not self._options_enabled():
            return True, "OK"

        quote_data = self.option_quote_cache.get(symbol, {})
        if not quote_data and symbol in self.latest_prices:
            price_candidate = self.latest_prices[symbol]
            if isinstance(price_candidate, dict):
                quote_data = price_candidate
            else:
                quote_data = {"last_price": float(price_candidate)}

        if not quote_data:
            return False, "option quote unavailable"

        stream = getattr(self, "kite_stream", None)
        expiry = getattr(stream, "contract_expiries", {}).get(symbol)
        if (
            expiry is not None
            and self.config.get("avoid_option_expiry_day", True)
            and expiry <= datetime.now(IST).date()
        ):
            return False, "option expiry-day risk"

        premium = float(quote_data.get("last_price", quote_data.get("premium", 0.0)) or 0.0)
        volume = int(quote_data.get("volume", 0) or 0)
        oi = int(quote_data.get("oi", 0) or 0)
        iv = float(quote_data.get("iv", 0.0) or 0.0)
        min_premium = float(self.config.get("option_min_premium", 12.0))
        max_premium = float(self.config.get("option_max_premium", 800.0))
        min_volume = int(self.config.get("option_min_volume", 200))
        min_oi = int(self.config.get("option_min_oi", 400))
        iv_min = float(self.config.get("option_iv_min", 0.08))
        iv_max = float(self.config.get("option_iv_max", 1.20))

        strong_signal = score is not None and score >= int(self.config.get("strong_signal_score", 82))
        premium_floor = min_premium * (0.75 if strong_signal else 0.65)
        volume_floor = max(int(min_volume * (0.8 if strong_signal else 0.7)), 150)
        oi_floor = max(int(min_oi * (0.8 if strong_signal else 0.7)), 300)

        if premium < min_premium:
            if premium >= premium_floor and volume >= volume_floor and oi >= oi_floor:
                pass
            else:
                return False, f"premium too low: {premium} < {min_premium}"
        if premium > max_premium:
            return False, f"premium too high: {premium} > {max_premium}"
        if volume < min_volume:
            if volume >= volume_floor and premium >= premium_floor and oi >= oi_floor:
                pass
            else:
                return False, f"volume too low: {volume} < {min_volume}"
        if "oi" in quote_data and int(quote_data["oi"] or 0) < min_oi:
            oi = int(quote_data["oi"] or 0)
            if oi >= oi_floor and premium >= premium_floor and volume >= volume_floor:
                pass
            else:
                return False, f"open interest too low: {oi} < {min_oi}"
        if "iv" in quote_data:
            iv_current = float(quote_data["iv"])
            if not iv_min <= iv_current <= iv_max:
                if strong_signal and iv_min * 0.7 <= iv_current <= iv_max * 1.25:
                    pass
                else:
                    iv = iv_current
                    return False, f"IV out of range: {iv} not in [{iv_min}, {iv_max}]"
        return True, "OK"

    def _warm_up_bars(self) -> None:
        """Load recent candles so signals do not wait for a fresh session's bars."""
        provider = KiteHistoricalProvider(
            self.config["kite_api_key"], self.config["kite_access_token"]
        )
        to_date = datetime.now(IST)
        from_date = to_date - timedelta(days=5)
        interval_seconds = self.config.get("bar_interval_seconds", 60)
        interval = "minute" if interval_seconds == 60 else f"{interval_seconds // 60}minute"
        seeded = 0
        for symbol, token in self.config["instrument_tokens"].items():
            try:
                history = provider.fetch_history(
                    token, from_date, to_date, interval=interval
                )
                bars = [
                    Bar(
                        timestamp=item["time"],
                        open=item["open"],
                        high=item["high"],
                        low=item["low"],
                        close=item["close"],
                        volume=item["volume"],
                    )
                    for item in history
                ]
                self.bar_builder.seed_bars(token, bars)
                seeded += len(bars)
                logger.info("[%s] Warmed up %d historical bars", symbol, len(bars))
            except Exception:
                logger.exception(
                    "[%s] Historical warm-up failed; live bars will still be used", symbol
                )
        logger.info("Historical warm-up complete: %d bars loaded", seeded)

    def _load_config(self) -> Dict:
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Create {self.config_path} from kite_config.example.json"
            )
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # Kite and Telegram credentials must never be read from the JSON file.
        config["kite_api_key"] = os.getenv("KITE_API_KEY")
        config["kite_access_token"] = os.getenv("KITE_ACCESS_TOKEN")
        config["telegram_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
        config["telegram_chat_id"] = os.getenv("TELEGRAM_CHAT_ID")
        if not config["kite_api_key"] or not config["kite_access_token"]:
            raise RuntimeError(
                "KITE_API_KEY and KITE_ACCESS_TOKEN must be set as environment variables."
            )
        return config

    def on_bar_complete(self, token_str: str, bar: Bar) -> None:
        """Called when a new bar is completed."""
        token = int(token_str)
        symbol = self.symbol_map.get(token, f"TOKEN_{token}")

        # Check if it's time to exit all positions (3:15 PM)
        if self.intraday_manager.should_exit_all_positions():
            self._handle_market_close_exit()
            self._record_decision(symbol, bar, [], None, "MARKET_CLOSE", "forced_exit_check")
            return

        logger.info(
            f"[{symbol}] Bar: O={bar.open:.2f} H={bar.high:.2f} L={bar.low:.2f} C={bar.close:.2f} V={bar.volume}"
        )

        # Get last N bars for signal evaluation
        bars = self.bar_builder.get_bars(token, limit=50)
        if len(bars) < 30:
            logger.debug(f"[{symbol}] Not enough bars yet ({len(bars)}/30)")
            self._record_decision(
                symbol,
                bar,
                bars,
                None,
                "HOLD",
                "not_enough_bars",
            )
            return

        signal_bars = bars
        if self.config.get("trading_mode") == "intraday_both" and "_" in symbol:
            underlying = symbol.rsplit("_", 1)[0].upper()
            underlying_token = self.config["instrument_tokens"].get(underlying)
            underlying_bars = (
                self.bar_builder.get_bars(underlying_token, limit=50)
                if underlying_token is not None
                else []
            )
            if len(underlying_bars) < 30:
                logger.info(
                    "[%s] Skipping option signal until %s has enough underlying bars",
                    symbol,
                    underlying,
                )
                self._record_decision(
                    symbol,
                    bar,
                    bars,
                    None,
                    "HOLD",
                    "underlying_signal_unavailable",
                )
                return
            signal_bars = underlying_bars

        # Convert bars to history format for engine
        history = [b.to_dict() for b in signal_bars]
        session_state = market_session_state(history, now=datetime.now(IST))
        session_label = {
            "BEFORE_OPEN": "before open",
            "REGULAR_SESSION": "regular session",
            "AFTER_CLOSE": "after close",
        }.get(session_state, "unknown")
        logger.info(f"[{symbol}] status={session_label}")

        if session_state == "AFTER_CLOSE":
            reason = "Market is after close; no live trading signal"
            self._record_decision(symbol, bar, bars, None, "HOLD", reason)
            logger.info(f"[{symbol}] status={session_label} | {reason}")
            return

        context_histories = {}
        benchmark_symbols = self.config.get(
            "benchmark_symbols", [self.benchmark_symbol, "BANKNIFTY"]
        )
        if self.use_market_context:
            for benchmark_symbol in dict.fromkeys(benchmark_symbols):
                benchmark_token = self.config["instrument_tokens"].get(benchmark_symbol)
                if benchmark_token is None or benchmark_symbol == symbol:
                    continue
                benchmark_bars = self.bar_builder.get_bars(benchmark_token, limit=100)
                if benchmark_bars:
                    context_histories[benchmark_symbol] = [
                        b.to_dict() for b in benchmark_bars
                    ]

        try:
            market_score = score_market(
                symbol,
                history,
                ema_fast=self.config.get("ema_fast", 9),
                ema_slow=self.config.get("ema_slow", 21),
                rsi_period=self.config.get("rsi_period", 14),
                context_histories=context_histories,
                allow_before_open=(session_state == "BEFORE_OPEN"),
                session_state=session_state,
                hard_context_filter=bool(self.config.get("hard_context_filter", True)),
                min_adx=float(self.config.get("min_adx", 18.0)),
                sideways_range_pct=float(self.config.get("sideways_range_pct", 1.0)),
                sideways_net_move_pct=float(
                    self.config.get("sideways_net_move_pct", 1.0)
                ),
                min_trend_strength=float(
                    self.config.get("min_trend_strength", 0.02)
                ),
            )
        except Exception:
            logger.exception("[%s] Strategy evaluation failed", symbol)
            self._record_decision(symbol, bar, bars, None, "ERROR", "strategy_error")
            return
        news_context = self.news_monitor.snapshot() if self.news_monitor else None
        if news_context:
            filtered_signal, news_reason = apply_news_filter(
                market_score.signal, news_context
            )
            if news_reason:
                market_score.signal = filtered_signal
                market_score.reasons.append(news_reason)
        logger.info(
            "[%s] Score=%s Signal=%s Reasons=%s",
            symbol,
            market_score.score,
            market_score.signal,
            "; ".join(market_score.reasons) or "none",
        )

        if session_state == "BEFORE_OPEN":
            logger.info(
                "[%s] pre-market analysis: score=%s signal=%s (no orders until regular session)",
                symbol,
                market_score.score,
                market_score.signal,
            )
            if market_score.signal in {"BUY", "SELL"}:
                self.premarkarket_candidates.append(
                    (
                        symbol,
                        market_score.signal,
                        market_score.score,
                        "; ".join(market_score.reasons[:3]),
                    )
                )
            self._record_decision(
                symbol,
                bar,
                bars,
                market_score,
                market_score.signal,
                "PREMARKET_WATCHLIST",
                news_context,
            )
            return

        if (
            market_score.signal in {"BUY", "SELL"}
            and self._late_window_blocked(datetime.now(IST))
        ):
            logger.info(
                "[%s] Entry blocked by configured late-window guard at %s IST",
                symbol,
                datetime.now(IST).strftime("%H:%M"),
            )
            self._record_decision(
                symbol,
                bar,
                bars,
                market_score,
                market_score.signal,
                "late_window_blocked",
                news_context,
            )
            return

        if (
            self._options_enabled()
            and "_" in symbol
            and market_score.signal in {"BUY", "SELL"}
        ):
            underlying = symbol.rsplit("_", 1)[0].upper()
            preferred = self._preferred_option_symbol(underlying, market_score.signal)
            if preferred and symbol != preferred:
                logger.info(
                    "[%s] Skipping %s because %s is the active option leg for %s signal",
                    symbol,
                    symbol,
                    preferred,
                    market_score.signal,
                )
                self._record_decision(
                    symbol,
                    bar,
                    bars,
                    market_score,
                    market_score.signal,
                    "OPTION_LEG_SKIPPED",
                    news_context,
                )
                return

            allowed, option_reason = self._option_quality_gate(
                symbol,
                market_score.signal,
                market_score.score,
            )
            if not allowed:
                logger.info("[%s] Option quality reject: %s", symbol, option_reason)
                self._record_decision(
                    symbol,
                    bar,
                    bars,
                    market_score,
                    market_score.signal,
                    f"OPTION_FILTER_{option_reason.upper().replace(' ', '_')}",
                    news_context,
                )
                return

        if self.premarkarket_candidates:
            self.premarkarket_candidates.clear()

        if market_score.signal in {"BUY", "SELL"}:
            previous_bar = (
                signal_bars[-2].to_dict()
                if len(signal_bars) > 1
                else signal_bars[-1].to_dict()
            )
            current_time = time.time()
            now = datetime.now(IST)
            allowed, rejection_reason = self.accuracy_filters.validate_entry_with_reason(
                symbol=symbol,
                signal=market_score.signal,
                score=market_score.score,
                history=history,
                current_bar=signal_bars[-1].to_dict(),
                previous_bar=previous_bar,
                current_time=current_time,
                hour=now.hour,
                minute=now.minute,
            )
            if not allowed:
                logger.info(
                    "[%s] Signal rejected by accuracy filter (%s): score=%s signal=%s",
                    symbol,
                    rejection_reason,
                    market_score.score,
                    market_score.signal,
                )
                self._record_decision(
                    symbol,
                    bar,
                    bars,
                    market_score,
                    market_score.signal,
                    f"accuracy_filter_rejected:{rejection_reason}",
                    news_context,
                )
                return

        trade_action = self._option_trade_action(symbol, market_score.signal)
        if trade_action == "BUY":
            outcome = self._handle_buy_signal(symbol, bar.close, market_score.score)
        elif trade_action == "SELL":
            outcome = self._handle_sell_signal(symbol, bar.close, market_score.score)
        else:
            logger.debug(f"[{symbol}] HOLD - not enough confidence")
            outcome = "hold"

        self._record_decision(
            symbol,
            bar,
            bars,
            market_score,
            market_score.signal,
            outcome,
            news_context,
        )

    def _on_tick(self, tick: Tick) -> None:
        """Monitor risk levels on every quote before aggregating the tick."""
        symbol = self.symbol_map.get(tick.instrument_token, f"TOKEN_{tick.instrument_token}")
        self.latest_prices[symbol] = tick.last_price
        self.option_quote_cache[symbol] = {
            "last_price": float(tick.last_price),
            "volume": int(tick.volume),
        }
        if tick.oi is not None:
            self.option_quote_cache[symbol]["oi"] = int(tick.oi)
        if tick.iv is not None:
            self.option_quote_cache[symbol]["iv"] = float(tick.iv)
        if self.intraday_manager.should_exit_all_positions():
            self._handle_market_close_exit()
        else:
            self._check_position_exit(symbol, tick.last_price)
        self.bar_builder.process_tick(tick)

    def _check_position_exit(self, symbol: str, price: float) -> Optional[str]:
        position = self.intraday_manager.active_positions.get(symbol)
        if not position:
            return None

        trailing_stop = self.intraday_manager.update_trailing_stop(symbol, price)
        if position.get("target_advanced"):
            self._publish_target_update(symbol, position, trailing_stop)

        if position["direction"] == "BUY":
            if price <= position["stop_loss"]:
                reason = "STOP_LOSS"
            elif trailing_stop is not None and price <= trailing_stop:
                reason = "TRAILING_STOP"
            elif not self.intraday_manager.trailing_enabled and price >= position["take_profit"]:
                reason = "TAKE_PROFIT"
            else:
                return None
        else:
            if price >= position["stop_loss"]:
                reason = "STOP_LOSS"
            elif trailing_stop is not None and price >= trailing_stop:
                reason = "TRAILING_STOP"
            elif not self.intraday_manager.trailing_enabled and price <= position["take_profit"]:
                reason = "TAKE_PROFIT"
            else:
                return None

        self._close_position(symbol, price, reason)
        return reason

    def _live_entry_allowed(self, symbol: str) -> bool:
        if not getattr(self, "live_orders_enabled", False):
            return True
        if getattr(self, "_entries_paused", False) or not getattr(self, "_risk_state_reconciled", False):
            logger.warning("[%s] Live entry blocked until broker state is safe", symbol)
            return False
        if not getattr(self.kite_stream, "is_connected", False):
            logger.warning("[%s] Live entry blocked while Kite is disconnected", symbol)
            return False
        return True

    def _place_protective_stop(self, symbol: str, position: dict) -> bool:
        try:
            order_id = self.kite_stream.place_protective_stop_order(
                symbol,
                position["direction"],
                int(position["quantity"]),
                float(position["stop_loss"]),
            )
            position["protection_order_id"] = order_id
            self.trade_journal.update_open_trade(
                symbol,
                {"protection_order_id": order_id},
                position["direction"],
            )
            return True
        except Exception as exc:
            logger.exception("[%s] Protective stop could not be placed", symbol)
            self.telegram_notifier.send_message(
                f"URGENT: protective stop failed for {symbol}; emergency exit required.\n{exc}"
            )
            return False

    def _abort_live_entry(self, symbol: str, price: float, reason: str) -> None:
        self._entries_paused = True
        self._risk_state_reconciled = False
        position = self.intraday_manager.active_positions.get(symbol)
        if position and not self.trade_journal.get_open_trade(
            symbol, position["direction"]
        ):
            try:
                self.trade_journal.log_trade({
                    "ticker": symbol,
                    "action": position["direction"],
                    "entry": position["entry_price"],
                    "stop_loss": position["stop_loss"],
                    "take_profit": position["take_profit"],
                    "quantity": position["quantity"],
                    "score": position.get("signal_score"),
                    "protection_order_id": position.get("protection_order_id"),
                    "status": "open",
                })
            except Exception:
                logger.exception("[%s] Could not journal an aborted live entry", symbol)
        self._close_position(symbol, price, reason)
        self._reconcile_after_order_failure(symbol)

    def _publish_target_update(
        self, symbol: str, position: dict, trailing_stop: Optional[float]
    ) -> None:
        """Persist and announce each staged target advance once."""
        action = position["direction"]
        fields = {
            "take_profit": position["take_profit"],
            "target_stage": position["target_stage"],
            "trailing_stop": trailing_stop,
            "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
        }
        self.trade_journal.update_open_trade(symbol, fields, action)
        trailing_text = f"{trailing_stop:.2f}" if trailing_stop is not None else "not active"
        self.telegram_notifier.send_message(
            f"Target advanced: {action} {symbol}\n"
            f"Stage: {position['target_stage']}\n"
            f"Next target: {position['take_profit']:.2f}\n"
            f"Trailing stop: {trailing_text}"
        )

    def _close_position(self, symbol: str, price: float, reason: str) -> None:
        position = self.intraday_manager.active_positions.get(symbol)
        action = position["direction"] if position else None
        if self.live_orders_enabled and position:
            exit_side = "SELL" if action == "BUY" else "BUY"
            protection_order_id = position.get("protection_order_id")
            protection_cancelled = not protection_order_id
            if protection_order_id:
                try:
                    self.kite_stream.cancel_order(protection_order_id)
                    protection_cancelled = True
                except Exception:
                    logger.warning("[%s] Protective stop %s was already active or unavailable", symbol, protection_order_id)
            remaining = abs(int(position["quantity"]))
            max_attempts = int(self.config.get("max_exit_retries", 3))
            for attempt in range(1, max_attempts + 1):
                try:
                    exit_order_id = self.kite_stream.place_market_order(symbol, exit_side, remaining)
                    fill = self.kite_stream.wait_for_order_fill(exit_order_id, remaining)
                    price = float(fill["average_price"])
                    broker_remaining = abs(self.kite_stream.get_position_quantity(symbol))
                    if broker_remaining == 0:
                        break
                    remaining = broker_remaining
                    logger.warning("[%s] Exit attempt %d left %d units; retrying", symbol, attempt, remaining)
                except Exception:
                    logger.exception("[%s] Live exit attempt %d failed", symbol, attempt)
                    try:
                        remaining = abs(self.kite_stream.get_position_quantity(symbol))
                    except Exception:
                        logger.exception("[%s] Could not verify broker quantity after exit failure", symbol)
                        remaining = -1
                    if remaining == 0:
                        break
                if remaining <= 0:
                    break
            if remaining != 0:
                protection_restored = False
                if remaining > 0 and protection_cancelled:
                    position["quantity"] = remaining
                    protection_restored = self._place_protective_stop(symbol, position)
                self._entries_paused = True
                self._risk_state_reconciled = False
                protection_state = (
                    "protective stop was restored"
                    if protection_restored
                    else "protective stop status is uncertain; manual protection is required"
                )
                self.telegram_notifier.send_message(
                    f"URGENT: {symbol} is not flat after {max_attempts} exit attempts; "
                    f"{protection_state}. New entries are paused."
                )
                logger.error("[%s] Broker position remains open after exit retries", symbol)
                if protection_restored:
                    self._reconcile_after_order_failure(symbol)
                return
        trade = self.trade_journal.get_open_trade(symbol, action)
        journal_pnl = self.trade_journal.close_trade(symbol, price, action, reason)
        exit_info = self.intraday_manager.close_position(symbol, price, reason)
        if not trade and not exit_info:
            return

        pnl = exit_info["pnl_rupees"] if exit_info else journal_pnl
        if exit_info:
            self.intraday_manager.record_trade_close(
                symbol, reason, exit_info["pnl_rupees"]
            )
            self.trade_journal.annotate_trade(
                symbol,
                {
                    "pnl": exit_info["pnl_rupees"],
                    "pnl_points": exit_info["pnl_points"],
                    "pnl_rupees": exit_info["pnl_rupees"],
                    "duration_seconds": exit_info["duration"],
                    "quantity": exit_info["quantity"],
                },
                action,
            )
        self._persist_current_live_risk_state()
        mode = "intraday_options" if self._options_enabled() else "futures"
        option_leg = "CE" if symbol.endswith("_CE") else "PE" if symbol.endswith("_PE") else None
        trading_symbol = self.kite_stream.contract_symbols.get(symbol, symbol)
        close_alert = self.telegram_notifier.format_close(
            ticker=symbol,
            action=action or (trade or {}).get("action", "UNKNOWN"),
            exit_price=price,
            pnl=pnl,
            reason=reason,
            mode=mode,
            option_leg=option_leg,
            trading_symbol=trading_symbol,
        )
        logger.info(self.telegram_notifier.build_message(close_alert))
        self.telegram_notifier.send_trade_alert(close_alert)

    def _record_decision(
        self,
        symbol: str,
        bar: Bar,
        bars: list,
        market_score,
        signal: str,
        outcome: str,
        news_context=None,
    ) -> None:
        reasons = list(market_score.reasons) if market_score else []
        if not reasons:
            reasons = [outcome]
        self.decision_journal.log_decision(
            {
                "event": "bar_decision",
                "bar": bar.to_dict(),
                "ticker": symbol,
                "signal": signal,
                "outcome": outcome,
                "bars_available": len(bars),
                "history": [item.to_dict() for item in bars],
                "score": market_score.score if market_score else None,
                "reasons": reasons,
                "news_risk": news_context.risk_level if news_context else "DISABLED",
                "news_sentiment": news_context.sentiment if news_context else "DISABLED",
                "news_headlines": news_context.headlines[:5] if news_context else [],
            }
        )

    def _handle_buy_signal(self, symbol: str, price: float, score: int) -> str:
        """Handle a BUY signal."""
        open_trade = self.trade_journal.get_open_trade(symbol, "BUY")
        opposite_trade = self.trade_journal.get_open_trade(symbol, "SELL")
        if opposite_trade or (
            symbol in self.intraday_manager.active_positions
            and self.intraday_manager.active_positions[symbol]["direction"] == "SELL"
        ):
            self._close_position(symbol, price, "SIGNAL_REVERSAL")
            if (
                symbol in self.intraday_manager.active_positions
                or self.trade_journal.get_open_trade(symbol, "SELL")
            ):
                return "reversal_close_failed"
        if open_trade is None:
            if not self._live_entry_allowed(symbol):
                return "live_entry_paused"
            allowed, reason = self.intraday_manager.can_open_trade(symbol, "BUY")
            if not allowed:
                logger.info("[%s] Trade blocked: %s", symbol, reason)
                return f"trade_blocked:{reason}"
            if self._options_enabled() and "_" in symbol:
                premium_stop_pct = float(self.config.get("option_premium_stop_pct", 0.20))
                premium_target_pct = float(self.config.get("option_premium_target_pct", 0.40))
                premium = float(self.latest_prices.get(symbol, price))
                stop_loss = max(price * (1.0 - premium_stop_pct), 0.01)
                take_profit = price * (1.0 + premium_target_pct)
                quantity = self.intraday_manager.calculate_option_size(
                    symbol,
                    premium=max(premium, 0.01),
                    max_risk_per_trade=self.intraday_manager.max_risk_per_trade,
                    premium_stop_pct=premium_stop_pct,
                    allow_paper_lot=self.paper_trading_enabled,
                )
            else:
                risk_plan = build_risk_plan(
                    price,
                    "BUY",
                    stop_loss_pct=self.config.get("stop_loss_pct", 0.75),
                    take_profit_pct=self.config.get("take_profit_pct", 1.5),
                )
                stop_loss = risk_plan.stop_loss
                take_profit = risk_plan.take_profit
                quantity = self.intraday_manager.calculate_position_size(
                    symbol,
                    price,
                    stop_loss,
                    allow_paper_lot=self.paper_trading_enabled,
                )

            if quantity == 0:
                logger.warning(f"[{symbol}] Cannot calculate position size, skipping trade")
                return "position_size_zero"

            order_id = None
            if self.live_orders_enabled:
                try:
                    order_id = self.kite_stream.place_market_order(
                        symbol, "BUY", quantity
                    )
                    fill = self.kite_stream.wait_for_order_fill(order_id, quantity)
                    quantity = int(fill["filled_quantity"])
                    price = float(fill["average_price"])
                    if self._options_enabled() and "_" in symbol:
                        stop_loss = max(price * (1.0 - premium_stop_pct), 0.01)
                        take_profit = price * (1.0 + premium_target_pct)
                    else:
                        risk_plan = build_risk_plan(
                            price,
                            "BUY",
                            stop_loss_pct=self.config.get("stop_loss_pct", 0.75),
                            take_profit_pct=self.config.get("take_profit_pct", 1.5),
                        )
                        stop_loss = risk_plan.stop_loss
                        take_profit = risk_plan.take_profit
                except Exception:
                    logger.exception("[%s] Live BUY order was not filled", symbol)
                    self._reconcile_after_order_failure(symbol)
                    return "live_order_failed"

            # Register position in intraday manager
            self.intraday_manager.register_position(
                symbol,
                "BUY",
                quantity,
                price,
                stop_loss,
                take_profit,
                signal_score=score,
                staged_targets_enabled=(
                    self._options_enabled()
                    and "_" in symbol
                    and self.config.get("staged_option_targets_enabled", True)
                ),
                target_increment_pct=self._option_target_increment(score),
            )
            self.intraday_manager.record_trade_open(symbol, "BUY")
            if self.live_orders_enabled and not self._place_protective_stop(
                symbol, self.intraday_manager.active_positions[symbol]
            ):
                self._abort_live_entry(symbol, price, "PROTECTION_FAILED")
                return "protective_stop_failed"
            if (
                self.live_orders_enabled
                and self.intraday_manager.estimate_trade_risk(
                    symbol, quantity, price, stop_loss
                ) > self.intraday_manager.max_risk_per_trade + 1e-6
            ):
                self._abort_live_entry(symbol, price, "RISK_LIMIT_EXCEEDED")
                return "risk_blocked:filled_risk_exceeds_limit"

            mode = "intraday_options" if self._options_enabled() else "futures"
            option_leg = "CE" if symbol.endswith("_CE") else "PE" if symbol.endswith("_PE") else None
            trading_symbol = self.kite_stream.contract_symbols.get(symbol, symbol)
            alert = self.telegram_notifier.format_trade(
                ticker=symbol,
                action="BUY",
                score=score,
                entry=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                mode=mode,
                option_leg=option_leg,
                trading_symbol=trading_symbol,
                trailing_enabled=self.intraday_manager.trailing_enabled,
            )
            alert["pnl"] = 0.0
            alert["status"] = "open"
            alert["stop_loss"] = stop_loss
            alert["take_profit"] = take_profit
            alert["quantity"] = quantity
            if order_id:
                alert["order_id"] = order_id
            protection_order_id = self.intraday_manager.active_positions[symbol].get(
                "protection_order_id"
            )
            if protection_order_id:
                alert["protection_order_id"] = protection_order_id

            self.trade_journal.log_trade(alert)
            self._persist_current_live_risk_state()
            logger.info(
                f"[{symbol}] BUY ALERT -> {quantity} qty @ {alert['entry']:.2f}, "
                f"SL={alert['stop_loss']:.2f}, TP={alert['take_profit']:.2f}"
            )
            logger.info(self.telegram_notifier.build_message(alert))
            self.telegram_notifier.send_trade_alert(alert)
            return "trade_opened"
        else:
            logger.info(f"[{symbol}] BUY OPEN -> current={price:.2f}")
            return "position_updated"

    def _handle_sell_signal(self, symbol: str, price: float, score: int) -> str:
        """Handle a SELL signal."""
        open_trade = self.trade_journal.get_open_trade(symbol, "SELL")
        opposite_trade = self.trade_journal.get_open_trade(symbol, "BUY")
        if opposite_trade or (
            symbol in self.intraday_manager.active_positions
            and self.intraday_manager.active_positions[symbol]["direction"] == "BUY"
        ):
            self._close_position(symbol, price, "SIGNAL_REVERSAL")
            if (
                symbol in self.intraday_manager.active_positions
                or self.trade_journal.get_open_trade(symbol, "BUY")
            ):
                return "reversal_close_failed"
        if open_trade is None:
            if not self._live_entry_allowed(symbol):
                return "live_entry_paused"
            allowed, reason = self.intraday_manager.can_open_trade(symbol, "SELL")
            if not allowed:
                logger.info("[%s] Trade blocked: %s", symbol, reason)
                return f"trade_blocked:{reason}"
            if self._options_enabled() and "_" in symbol:
                premium_stop_pct = float(self.config.get("option_premium_stop_pct", 0.20))
                premium_target_pct = float(self.config.get("option_premium_target_pct", 0.40))
                premium = float(self.latest_prices.get(symbol, price))
                stop_loss = min(price * (1.0 + premium_stop_pct), 1e9)
                take_profit = max(price * (1.0 - premium_target_pct), 0.01)
                quantity = self.intraday_manager.calculate_option_size(
                    symbol,
                    premium=max(premium, 0.01),
                    max_risk_per_trade=self.intraday_manager.max_risk_per_trade,
                    premium_stop_pct=premium_stop_pct,
                    allow_paper_lot=self.paper_trading_enabled,
                )
            else:
                risk_plan = build_risk_plan(
                    price,
                    "SELL",
                    stop_loss_pct=self.config.get("stop_loss_pct", 0.75),
                    take_profit_pct=self.config.get("take_profit_pct", 1.5),
                )
                stop_loss = risk_plan.stop_loss
                take_profit = risk_plan.take_profit
                quantity = self.intraday_manager.calculate_position_size(
                    symbol,
                    price,
                    stop_loss,
                    allow_paper_lot=self.paper_trading_enabled,
                )

            if quantity == 0:
                logger.warning(f"[{symbol}] Cannot calculate position size, skipping trade")
                return "position_size_zero"

            order_id = None
            if self.live_orders_enabled:
                try:
                    order_id = self.kite_stream.place_market_order(
                        symbol, "SELL", quantity
                    )
                    fill = self.kite_stream.wait_for_order_fill(order_id, quantity)
                    quantity = int(fill["filled_quantity"])
                    price = float(fill["average_price"])
                    if self._options_enabled() and "_" in symbol:
                        stop_loss = min(price * (1.0 + premium_stop_pct), 1e9)
                        take_profit = max(price * (1.0 - premium_target_pct), 0.01)
                    else:
                        risk_plan = build_risk_plan(
                            price,
                            "SELL",
                            stop_loss_pct=self.config.get("stop_loss_pct", 0.75),
                            take_profit_pct=self.config.get("take_profit_pct", 1.5),
                        )
                        stop_loss = risk_plan.stop_loss
                        take_profit = risk_plan.take_profit
                except Exception:
                    logger.exception("[%s] Live SELL order was not filled", symbol)
                    self._reconcile_after_order_failure(symbol)
                    return "live_order_failed"

            # Register position in intraday manager
            self.intraday_manager.register_position(
                symbol,
                "SELL",
                quantity,
                price,
                stop_loss,
                take_profit,
                signal_score=score,
                staged_targets_enabled=(
                    self._options_enabled()
                    and "_" in symbol
                    and self.config.get("staged_option_targets_enabled", True)
                ),
                target_increment_pct=self._option_target_increment(score),
            )
            self.intraday_manager.record_trade_open(symbol, "SELL")
            if self.live_orders_enabled and not self._place_protective_stop(
                symbol, self.intraday_manager.active_positions[symbol]
            ):
                self._abort_live_entry(symbol, price, "PROTECTION_FAILED")
                return "protective_stop_failed"
            if (
                self.live_orders_enabled
                and self.intraday_manager.estimate_trade_risk(
                    symbol, quantity, price, stop_loss
                ) > self.intraday_manager.max_risk_per_trade + 1e-6
            ):
                self._abort_live_entry(symbol, price, "RISK_LIMIT_EXCEEDED")
                return "risk_blocked:filled_risk_exceeds_limit"

            mode = "intraday_options" if self._options_enabled() else "futures"
            option_leg = "CE" if symbol.endswith("_CE") else "PE" if symbol.endswith("_PE") else None
            trading_symbol = self.kite_stream.contract_symbols.get(symbol, symbol)
            alert = self.telegram_notifier.format_trade(
                ticker=symbol,
                action="SELL",
                score=score,
                entry=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                mode=mode,
                option_leg=option_leg,
                trading_symbol=trading_symbol,
                trailing_enabled=self.intraday_manager.trailing_enabled,
            )
            alert["pnl"] = 0.0
            alert["status"] = "open"
            alert["stop_loss"] = stop_loss
            alert["take_profit"] = take_profit
            alert["quantity"] = quantity
            if order_id:
                alert["order_id"] = order_id
            protection_order_id = self.intraday_manager.active_positions[symbol].get(
                "protection_order_id"
            )
            if protection_order_id:
                alert["protection_order_id"] = protection_order_id

            self.trade_journal.log_trade(alert)
            self._persist_current_live_risk_state()
            logger.info(
                f"[{symbol}] SELL ALERT -> {quantity} qty @ {alert['entry']:.2f}, "
                f"SL={alert['stop_loss']:.2f}, TP={alert['take_profit']:.2f}"
            )
            logger.info(self.telegram_notifier.build_message(alert))
            self.telegram_notifier.send_trade_alert(alert)
            return "trade_opened"
        else:
            logger.info(f"[{symbol}] SELL OPEN -> current={price:.2f}")
            return "position_updated"

    def _handle_market_close_exit(self) -> None:
        """Force exit all positions before market close (3:15 PM)."""
        positions = self.intraday_manager.get_all_open_positions()
        if positions:
            logger.warning(f"Market close time (3:15 PM) - Force closing all positions")
            for pos_symbol, pos_details in positions.items():
                price = self.latest_prices.get(pos_symbol, pos_details["entry_price"])
                self._close_position(pos_symbol, price, "MARKET_CLOSE_FORCED_EXIT")

    def _finalize_daily_session(self, now: datetime) -> bool:
        """Complete post-close reporting only after the broker confirms flatness."""
        self._handle_market_close_exit()
        if self.intraday_manager.get_all_open_positions():
            self.telegram_notifier.send_message(
                "URGENT: session cannot complete; local positions remain open after exit retries."
            )
            return False
        if self.live_orders_enabled:
            try:
                open_positions = [
                    position
                    for position in self.kite_stream.get_positions()
                    if int(position.get("quantity", 0) or 0) != 0
                ]
                if open_positions:
                    self.telegram_notifier.send_message(
                        "URGENT: session cannot complete; broker account is not flat: "
                        + ", ".join(
                            str(position.get("tradingsymbol", "unknown"))
                            for position in open_positions
                        )
                    )
                    return False
            except Exception as exc:
                logger.exception("Could not confirm broker flatness at session close")
                self.telegram_notifier.send_message(
                    f"URGENT: session cannot complete; broker flatness is unknown.\n{exc}"
                )
                return False
        self._write_daily_summary_if_due()
        self._run_weekly_report_if_due(now)
        return True

    def _write_daily_summary_if_due(self) -> None:
        """Publish one daily paper-trading summary after the session closes."""
        today = datetime.now(IST).date()
        if self.last_daily_summary_date == today:
            return
        try:
            today_trades = [
                trade
                for trade in self.trade_journal.read_trades()
                if trade.get("status") == "closed"
                and str(trade.get("closed_at", "")).startswith(today.isoformat())
            ]
            pnls = [float(trade.get("pnl", 0.0)) for trade in today_trades]
            summary_path = write_daily_summary(
                data_dir=".", paper_data_dir=self.paper_trading_dir, target_date=today
            )
            self.last_daily_summary_date = today
            logger.info("Daily paper-trading summary written to %s", summary_path)
            self.telegram_notifier.send_daily_summary(
                summary_date=today.isoformat(),
                closed_trades=len(today_trades),
                winning_trades=sum(1 for pnl in pnls if pnl > 0),
                losing_trades=sum(1 for pnl in pnls if pnl <= 0),
                total_pnl=sum(pnls),
            )
        except Exception:
            logger.exception("Daily paper-trading summary failed; trading remains active")

    def run(self) -> None:
        """Start the bot and stream market data with intraday monitoring."""
        logger.info(
            "Starting Kite Trading Bot - %s MODE",
            self.config.get("trading_mode", "intraday_futures").upper(),
        )
        logger.info(
            "Execution mode: %s",
            "REALTIME PAPER TRADING" if self.paper_trading_enabled else "LIVE ORDERS",
        )
        logger.info(f"Instruments: {list(self.config['instrument_tokens'].keys())}")
        logger.info(f"Bar interval: {self.config.get('bar_interval_seconds', 60)}s")
        logger.info(f"Market close exit time: {self.intraday_manager.AUTO_EXIT_TIME}")
        logger.info(f"Risk per trade: {self.intraday_manager.risk_per_trade_pct}%")

        try:
            if self.news_monitor:
                self.news_monitor.start()
            self.kite_stream.start()
            logger.info("Waiting for WebSocket connection...")
            if self.kite_stream.wait_for_connection(timeout=15):
                logger.info("WebSocket connected, streaming live data...")
                self.telegram_notifier.send_heartbeat(
                    instruments=len(self.config["instrument_tokens"]),
                    bar_interval_seconds=self.config.get("bar_interval_seconds", 60),
                    mode=self.config.get("trading_mode", "intraday_futures"),
                )
                last_heartbeat = time.monotonic()
                last_close_check = datetime.now(IST)

                while True:
                    now_monotonic = time.monotonic()
                    if now_monotonic - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                        self.telegram_notifier.send_heartbeat(
                            instruments=len(self.config["instrument_tokens"]),
                            bar_interval_seconds=self.config.get("bar_interval_seconds", 60),
                            mode=self.config.get("trading_mode", "intraday_futures"),
                        )
                        last_heartbeat = now_monotonic

                    # Check every 30 seconds if it's time to force exit
                    now = datetime.now(IST)
                    if (now - last_close_check).total_seconds() >= 30:
                        if self.intraday_manager.is_market_closed():
                            if self._finalize_daily_session(now):
                                logger.info("Market session complete; shutting down bot.")
                                break
                        if self.intraday_manager.should_exit_all_positions():
                            self._handle_market_close_exit()
                        last_close_check = now

                    time.sleep(1)
            else:
                logger.error("Failed to connect to Kite WebSocket")
                sys.exit(1)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            if self.news_monitor:
                self.news_monitor.stop()
            self.kite_stream.stop()
            logger.info("Bot shutdown complete")

    def _run_weekly_report_if_due(self, now: datetime) -> None:
        """Publish one protected weekly report after Friday's close check."""
        if now.weekday() != 4 or self.last_weekly_report_date == now.date():
            return
        try:
            report_path = write_weekly_report(
                data_dir=".",
                days=self.config.get("weekly_report_days", 7),
                output_dir=str(self.weekly_report_dir),
                paper_data_dir=self.paper_trading_dir,
            )
            review_path = write_weekly_review(
                data_dir=".",
                paper_data_dir=self.paper_trading_dir,
                days=self.config.get("weekly_report_days", 7),
            )
            if report_path.exists():
                self.last_weekly_report_date = now.date()
                logger.info(
                    "Automatic weekly report written to %s; review written to %s",
                    report_path,
                    review_path,
                )
            else:
                logger.error("Weekly report was not published; it will be retried")
        except Exception:
            logger.exception("Weekly analytics failed; trading remains active")


def main() -> None:
    """Entry point for the Kite-based bot."""
    try:
        bot = KiteTradingBot()
        bot.run()
    except FileNotFoundError as exc:
        logger.error(f"Configuration error: {exc}")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"Fatal error: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
