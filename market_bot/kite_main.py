"""
Zerodha Kite Connect based trading bot with live market streaming.
Uses real-time ticks aggregated into bars, with conservative signal logic.
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
                stop_loss_pct=self.config.get("stop_loss_pct", 1.5),
                take_profit_pct=self.config.get("take_profit_pct", 3.0),
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

            self.trade_journal.log_trade(alert)
            logger.info(
                f"[{symbol}] BUY ALERT -> Entry={alert['entry']:.2f}, "
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
                    reason="AUTO_CLOSE",
                )
                logger.info(self.telegram_notifier.build_message(close_alert))
                self.telegram_notifier.send_trade_alert(close_alert)
            else:
                logger.info(f"[{symbol}] BUY OPEN -> current={price:.2f}, P&L={pnl:.2f}")

    def _handle_sell_signal(self, symbol: str, price: float, score: int) -> None:
        """Handle a SELL signal."""
        open_trade = self.trade_journal.get_open_trade(symbol, "SELL")
        if open_trade is None:
            risk_plan = build_risk_plan(
                price,
                "SELL",
                stop_loss_pct=self.config.get("stop_loss_pct", 1.5),
                take_profit_pct=self.config.get("take_profit_pct", 3.0),
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

            self.trade_journal.log_trade(alert)
            logger.info(
                f"[{symbol}] SELL ALERT -> Entry={alert['entry']:.2f}, "
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
                    reason="AUTO_CLOSE",
                )
                logger.info(self.telegram_notifier.build_message(close_alert))
                self.telegram_notifier.send_trade_alert(close_alert)
            else:
                logger.info(f"[{symbol}] SELL OPEN -> current={price:.2f}, P&L={pnl:.2f}")

    def run(self) -> None:
        """Start the bot and stream market data."""
        logger.info("Starting Kite Trading Bot")
        logger.info(f"Instruments: {list(self.config['instrument_tokens'].keys())}")
        logger.info(f"Bar interval: {self.config.get('bar_interval_seconds', 60)}s")

        try:
            self.kite_stream.start()
            logger.info("Waiting for WebSocket connection...")
            if self.kite_stream.wait_for_connection(timeout=15):
                logger.info("WebSocket connected, streaming live data...")
                while True:
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
