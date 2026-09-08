"""
Zerodha Kite Connect based trading bot with live market streaming.
Uses real-time ticks aggregated into bars, with intraday futures optimization.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from .bar_builder import BarBuilder, Bar
from .engine import score_market
from .intraday_manager import IntradayManager
from .kite_provider import KiteConfig, KiteMarketStream, Tick
from .market_news import NewsMonitor, apply_news_filter
from .risk_manager import build_risk_plan
from .telegram_notifier import TelegramNotifier
from .trade_journal import DecisionJournal, TradeJournal
from .weekly_report import write_daily_summary, write_weekly_report, write_weekly_review


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class KiteTradingBot:
    def __init__(self, config_path: str = "kite_config.json") -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # Initialize intraday manager for futures trading
        self.intraday_manager = IntradayManager(
            account_size=self.config.get("account_size", 100000),
            risk_per_trade_pct=self.config.get("risk_per_trade_pct", 1.0),
        )
        
        self.bar_builder = BarBuilder(
            interval_seconds=self.config.get("bar_interval_seconds", 60),
            on_bar_callback=self.on_bar_complete,
        )
        self.kite_stream = KiteMarketStream(
            KiteConfig(
                api_key=self.config["kite_api_key"],
                access_token=self.config["kite_access_token"],
                instrument_tokens=self.config["instrument_tokens"],
                futures_underlyings=self.config.get("futures_underlyings", []),
                auto_discover_futures=self.config.get("auto_discover_futures", False),
                max_futures=self.config.get("max_futures", 20),
                min_futures_volume=self.config.get("min_futures_volume", 0),
            ),
            on_tick_callback=self._on_tick,
        )
        self.config["instrument_tokens"] = self.kite_stream.refresh_instrument_tokens()
        self.intraday_manager.set_contract_specs(self.kite_stream.contract_specs)
        self.telegram_notifier = TelegramNotifier(
            token=self.config.get("telegram_token"),
            chat_id=self.config.get("telegram_chat_id"),
        )
        self.paper_trading_dir = self.config.get("paper_trading_dir", "paper_trading_data")
        self.trade_journal = TradeJournal("trades.jsonl", self.paper_trading_dir)
        self.decision_journal = DecisionJournal(
            self.config.get("decision_log_path", "decision_log.jsonl"),
            self.paper_trading_dir,
        )
        self.weekly_report_dir = Path(
            self.config.get("weekly_report_dir", ".")
        )
        self.last_weekly_report_date = None
        self.last_daily_summary_date = None
        self.symbol_map = {v: k for k, v in self.config["instrument_tokens"].items()}
        self.latest_prices: Dict[str, float] = {}
        self.benchmark_symbol = self.config.get("benchmark_symbol", "NIFTY")
        self.use_market_context = self.config.get("use_market_context", True)
        self.news_monitor = NewsMonitor(
            feeds=self.config.get("news_feeds"),
            refresh_seconds=self.config.get("news_refresh_seconds", 900),
        ) if self.config.get("news_enabled", True) else None

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

        # Convert bars to history format for engine
        history = [b.to_dict() for b in bars]
        benchmark_history = None
        benchmark_token = self.config["instrument_tokens"].get(self.benchmark_symbol)
        if (
            self.use_market_context
            and self.benchmark_symbol != symbol
            and benchmark_token is not None
        ):
            benchmark_bars = self.bar_builder.get_bars(benchmark_token, limit=50)
            if benchmark_bars:
                benchmark_history = [b.to_dict() for b in benchmark_bars]

        # Evaluate signal
        try:
            market_score = score_market(
                symbol,
                history,
                ema_fast=self.config.get("ema_fast", 9),
                ema_slow=self.config.get("ema_slow", 21),
                rsi_period=self.config.get("rsi_period", 14),
                context_history=benchmark_history,
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
        logger.info(f"[{symbol}] Score={market_score.score} Signal={market_score.signal}")

        if market_score.signal == "BUY":
            outcome = self._handle_buy_signal(symbol, bar.close, market_score.score)
        elif market_score.signal == "SELL":
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
        if self.intraday_manager.should_exit_all_positions():
            self._handle_market_close_exit()
        else:
            self._check_position_exit(symbol, tick.last_price)
        self.bar_builder.process_tick(tick)

    def _check_position_exit(self, symbol: str, price: float) -> Optional[str]:
        position = self.intraday_manager.active_positions.get(symbol)
        if not position:
            return None

        if position["direction"] == "BUY":
            if price <= position["stop_loss"]:
                reason = "STOP_LOSS"
            elif price >= position["take_profit"]:
                reason = "TAKE_PROFIT"
            else:
                return None
        else:
            if price >= position["stop_loss"]:
                reason = "STOP_LOSS"
            elif price <= position["take_profit"]:
                reason = "TAKE_PROFIT"
            else:
                return None

        self._close_position(symbol, price, reason)
        return reason

    def _close_position(self, symbol: str, price: float, reason: str) -> None:
        position = self.intraday_manager.active_positions.get(symbol)
        action = position["direction"] if position else None
        trade = self.trade_journal.get_open_trade(symbol, action)
        journal_pnl = self.trade_journal.close_trade(symbol, price, action, reason)
        exit_info = self.intraday_manager.close_position(symbol, price, reason)
        if not trade and not exit_info:
            return

        pnl = exit_info["pnl_rupees"] if exit_info else journal_pnl
        if exit_info:
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
        close_alert = self.telegram_notifier.format_close(
            ticker=symbol,
            action=action or (trade or {}).get("action", "UNKNOWN"),
            exit_price=price,
            pnl=pnl,
            reason=reason,
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
                "reasons": market_score.reasons if market_score else [],
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
        if open_trade is None:
            risk_plan = build_risk_plan(
                price,
                "BUY",
                stop_loss_pct=self.config.get("stop_loss_pct", 0.75),
                take_profit_pct=self.config.get("take_profit_pct", 1.5),
            )
            
            # Calculate position size for futures
            quantity = self.intraday_manager.calculate_position_size(
                symbol, price, risk_plan.stop_loss
            )
            
            if quantity == 0:
                logger.warning(f"[{symbol}] Cannot calculate position size, skipping trade")
                return "position_size_zero"
            
            # Register position in intraday manager
            self.intraday_manager.register_position(
                symbol, "BUY", quantity, price, risk_plan.stop_loss, risk_plan.take_profit
            )
            
            alert = self.telegram_notifier.format_trade(
                ticker=symbol,
                action="BUY",
                score=score,
                entry=risk_plan.entry_price,
                stop_loss=risk_plan.stop_loss,
                take_profit=risk_plan.take_profit,
            )
            alert["pnl"] = 0.0
            alert["status"] = "open"
            alert["stop_loss"] = risk_plan.stop_loss
            alert["take_profit"] = risk_plan.take_profit
            alert["quantity"] = quantity

            self.trade_journal.log_trade(alert)
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
        if open_trade is None:
            risk_plan = build_risk_plan(
                price,
                "SELL",
                stop_loss_pct=self.config.get("stop_loss_pct", 0.75),
                take_profit_pct=self.config.get("take_profit_pct", 1.5),
            )
            
            # Calculate position size for futures
            quantity = self.intraday_manager.calculate_position_size(
                symbol, price, risk_plan.stop_loss
            )
            
            if quantity == 0:
                logger.warning(f"[{symbol}] Cannot calculate position size, skipping trade")
                return "position_size_zero"
            
            # Register position in intraday manager
            self.intraday_manager.register_position(
                symbol, "SELL", quantity, price, risk_plan.stop_loss, risk_plan.take_profit
            )
            
            alert = self.telegram_notifier.format_trade(
                ticker=symbol,
                action="SELL",
                score=score,
                entry=risk_plan.entry_price,
                stop_loss=risk_plan.stop_loss,
                take_profit=risk_plan.take_profit,
            )
            alert["pnl"] = 0.0
            alert["status"] = "open"
            alert["stop_loss"] = risk_plan.stop_loss
            alert["take_profit"] = risk_plan.take_profit
            alert["quantity"] = quantity

            self.trade_journal.log_trade(alert)
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
        self._write_daily_summary_if_due()

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
        logger.info("Starting Kite Trading Bot - INTRADAY FUTURES MODE")
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
                )
                last_close_check = datetime.now(IST)
                
                while True:
                    # Check every 30 seconds if it's time to force exit
                    now = datetime.now(IST)
                    if (now - last_close_check).total_seconds() >= 30:
                        if self.intraday_manager.should_exit_all_positions():
                            positions = self.intraday_manager.get_all_open_positions()
                            if positions:
                                self._handle_market_close_exit()
                            else:
                                self._write_daily_summary_if_due()
                            self._run_weekly_report_if_due(now)
                            logger.info("Market session complete; shutting down bot.")
                            break
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
