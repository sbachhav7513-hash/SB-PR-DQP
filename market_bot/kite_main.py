"""
Zerodha Kite Connect based trading bot with live market streaming.
Uses real-time ticks aggregated into bars, with intraday futures optimization.
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from .bar_builder import BarBuilder, Bar
from .engine import score_market
from .intraday_manager import IntradayManager
from .kite_provider import KiteConfig, KiteMarketStream, Tick
from .risk_manager import build_risk_plan
from .telegram_notifier import TelegramNotifier
from .trade_journal import TradeJournal


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


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
            ),
            on_tick_callback=self.bar_builder.process_tick,
        )
        self.telegram_notifier = TelegramNotifier(
            token=self.config.get("telegram_token"),
            chat_id=self.config.get("telegram_chat_id"),
        )
        self.trade_journal = TradeJournal("trades.jsonl")
        self.symbol_map = {v: k for k, v in self.config["instrument_tokens"].items()}

    def _load_config(self) -> Dict:
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Create {self.config_path} from kite_config.example.json"
            )
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def on_bar_complete(self, token_str: str, bar: Bar) -> None:
        """Called when a new bar is completed."""
        token = int(token_str)
        symbol = self.symbol_map.get(token, f"TOKEN_{token}")

        # Check if it's time to exit all positions (3:15 PM)
        if self.intraday_manager.should_exit_all_positions():
            self._handle_market_close_exit(symbol, bar.close)
            return

        logger.info(
            f"[{symbol}] Bar: O={bar.open:.2f} H={bar.high:.2f} L={bar.low:.2f} C={bar.close:.2f} V={bar.volume}"
        )

        # Get last N bars for signal evaluation
        bars = self.bar_builder.get_bars(token, limit=50)
        if len(bars) < 30:
            logger.debug(f"[{symbol}] Not enough bars yet ({len(bars)}/30)")
            return

        # Convert bars to history format for engine
        history = [b.to_dict() for b in bars]

        # Evaluate signal
        market_score = score_market(symbol, history)
        logger.info(f"[{symbol}] Score={market_score.score} Signal={market_score.signal}")

        if market_score.signal == "BUY":
            self._handle_buy_signal(symbol, bar.close, market_score.score)
        elif market_score.signal == "SELL":
            self._handle_sell_signal(symbol, bar.close, market_score.score)
        else:
            logger.debug(f"[{symbol}] HOLD - not enough confidence")

    def _handle_buy_signal(self, symbol: str, price: float, score: int) -> None:
        """Handle a BUY signal."""
        open_trade = self.trade_journal.get_open_trade(symbol, "BUY")
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
                return
            
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
        else:
            pnl = self.trade_journal.update_trade_pnl(symbol, price, "BUY")
            updated = self.trade_journal.get_open_trade(symbol, "BUY")
            if updated is None:
                close_alert = self.telegram_notifier.format_close(
                    ticker=symbol,
                    action="BUY",
                    exit_price=price,
                    pnl=pnl,
                    reason="TAKE_PROFIT",
                )
                logger.info(self.telegram_notifier.build_message(close_alert))
                self.telegram_notifier.send_trade_alert(close_alert)
                self.intraday_manager.close_position(symbol, price, "TAKE_PROFIT")
            else:
                logger.info(f"[{symbol}] BUY OPEN -> current={price:.2f}, P&L={pnl:.2f}")

    def _handle_sell_signal(self, symbol: str, price: float, score: int) -> None:
        """Handle a SELL signal."""
        open_trade = self.trade_journal.get_open_trade(symbol, "SELL")
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
                return
            
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
        else:
            pnl = self.trade_journal.update_trade_pnl(symbol, price, "SELL")
            updated = self.trade_journal.get_open_trade(symbol, "SELL")
            if updated is None:
                close_alert = self.telegram_notifier.format_close(
                    ticker=symbol,
                    action="SELL",
                    exit_price=price,
                    pnl=pnl,
                    reason="TAKE_PROFIT",
                )
                logger.info(self.telegram_notifier.build_message(close_alert))
                self.telegram_notifier.send_trade_alert(close_alert)
                self.intraday_manager.close_position(symbol, price, "TAKE_PROFIT")
            else:
                logger.info(f"[{symbol}] SELL OPEN -> current={price:.2f}, P&L={pnl:.2f}")

    def _handle_market_close_exit(self, symbol: str, price: float) -> None:
        """Force exit all positions before market close (3:15 PM)."""
        positions = self.intraday_manager.get_all_open_positions()
        if not positions:
            return
        
        logger.warning(f"Market close time (3:15 PM) - Force closing all positions")
        
        for pos_symbol, pos_details in positions.items():
            exit_info = self.intraday_manager.close_position(pos_symbol, price, "MARKET_CLOSE")
            if exit_info:
                close_alert = self.telegram_notifier.format_close(
                    ticker=pos_symbol,
                    action=exit_info["direction"],
                    exit_price=price,
                    pnl=exit_info["pnl_rupees"],
                    reason="MARKET_CLOSE_FORCED_EXIT",
                )
                logger.warning(f"[{pos_symbol}] Forced exit at market close: ₹{exit_info['pnl_rupees']:.0f}")
                self.telegram_notifier.send_trade_alert(close_alert)

    def run(self) -> None:
        """Start the bot and stream market data with intraday monitoring."""
        logger.info("Starting Kite Trading Bot - INTRADAY FUTURES MODE")
        logger.info(f"Instruments: {list(self.config['instrument_tokens'].keys())}")
        logger.info(f"Bar interval: {self.config.get('bar_interval_seconds', 60)}s")
        logger.info(f"Market close exit time: {self.intraday_manager.AUTO_EXIT_TIME}")
        logger.info(f"Risk per trade: {self.intraday_manager.risk_per_trade_pct}%")

        try:
            self.kite_stream.start()
            logger.info("Waiting for WebSocket connection...")
            if self.kite_stream.wait_for_connection(timeout=15):
                logger.info("WebSocket connected, streaming live data...")
                last_close_check = datetime.now()
                
                while True:
                    # Check every 30 seconds if it's time to force exit
                    now = datetime.now()
                    if (now - last_close_check).total_seconds() >= 30:
                        if self.intraday_manager.should_exit_all_positions():
                            positions = self.intraday_manager.get_all_open_positions()
                            if positions:
                                logger.warning(
                                    f"Market close in ~15 min. {len(positions)} open positions. "
                                    "Will force exit at 3:15 PM"
                                )
                        last_close_check = now
                    
                    time.sleep(1)
            else:
                logger.error("Failed to connect to Kite WebSocket")
                sys.exit(1)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            self.kite_stream.stop()
            logger.info("Bot shutdown complete")


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
