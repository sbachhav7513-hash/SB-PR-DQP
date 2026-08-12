import requests
import sys
import time
from datetime import datetime

from .config import BotConfig
from .data_provider import MarketDataProvider
from .engine import score_market
from .live_feed import LiveMarketFeed
from .risk_manager import build_risk_plan
from .strategy import Signal
from .telegram_notifier import TelegramNotifier
from .trade_journal import TradeJournal


def format_signal(signal: Signal) -> str:
    stop_text = f" SL={signal.stop_loss:.2f}" if signal.stop_loss is not None else ""
    take_text = f" TP={signal.take_profit:.2f}" if signal.take_profit is not None else ""
    return (
        f"[{signal.ticker}] {signal.action} @ {signal.price:.2f}: {signal.reason}{stop_text}{take_text}"
    )


def print_header(config: BotConfig) -> None:
    print("Share Market Alert Bot")
    print("======================")
    print(f"Tickers: {', '.join(config.tickers)}")
    print(f"Polling interval: {config.interval_seconds}s")
    print(f"EMA: {config.ema_fast}/{config.ema_slow}, RSI period: {config.rsi_period}")
    print("Risk model: conservative score + stop-loss + target")
    print()


def run_bot(config: BotConfig) -> None:
    provider = MarketDataProvider()
    feed = LiveMarketFeed(provider)
    bot = TelegramNotifier(
        token=config.telegram_token,
        chat_id=config.telegram_chat_id,
    )
    journal = TradeJournal("trades.jsonl")
    print_header(config)

    try:
        while True:
            loop_start = datetime.now()
            for ticker in config.tickers:
                print(f"[{loop_start:%Y-%m-%d %H:%M:%S}] Checking {ticker}...")
                try:
                    snapshot = feed.fetch_snapshot(ticker, period="1d", interval="2m")
                except requests.exceptions.RequestException as exc:
                    print(f"[{ticker}] Failed to fetch history: {exc}")
                    snapshot = None

                if snapshot is None or not snapshot.history:
                    print(f"[{ticker}] No data")
                    continue

                market_score = score_market(ticker, snapshot.history)
                print(f"[{ticker}] score={market_score.score} decision={market_score.signal}")

                if market_score.signal == "BUY":
                    entry_price = snapshot.last_price or snapshot.history[-1]["close"]
                    open_trade = journal.get_open_trade(ticker, "BUY")
                    if open_trade is None:
                        risk_plan = build_risk_plan(
                            entry_price,
                            "BUY",
                            stop_loss_pct=config.stop_loss_pct,
                            take_profit_pct=config.take_profit_pct,
                        )
                        alert = bot.format_trade(
                            ticker=ticker,
                            action="BUY",
                            score=market_score.score,
                            entry=risk_plan.entry_price,
                            stop_loss=risk_plan.stop_loss,
                            take_profit=risk_plan.take_profit,
                        )
                        alert["pnl"] = 0.0
                        alert["status"] = "open"
                        alert["stop_loss"] = risk_plan.stop_loss
                        alert["take_profit"] = risk_plan.take_profit
                        journal.log_trade(alert)
                        print(f"[{ticker}] BUY ALERT -> Entry={alert['entry']:.2f}, SL={alert['stop_loss']:.2f}, TP={alert['take_profit']:.2f}, score={alert['score']}, P&L={alert['pnl']:.2f}")
                        print(bot.build_message(alert))
                        bot.send_trade_alert(alert)
                    else:
                        pnl = journal.update_trade_pnl(ticker, entry_price, "BUY")
                        updated = journal.get_open_trade(ticker, "BUY")
                        if updated is None:
                            close_message = bot.format_close(
                                ticker=ticker,
                                action="BUY",
                                exit_price=entry_price,
                                pnl=pnl,
                                reason="AUTO_CLOSE",
                            )
                            print(bot.build_message(close_message))
                            bot.send_trade_alert(close_message)
                        else:
                            print(f"[{ticker}] BUY OPEN -> Entry={open_trade['entry']:.2f}, current_price={entry_price:.2f}, P&L={pnl:.2f}")

                elif market_score.signal == "SELL":
                    entry_price = snapshot.last_price or snapshot.history[-1]["close"]
                    open_trade = journal.get_open_trade(ticker, "SELL")
                    if open_trade is None:
                        risk_plan = build_risk_plan(
                            entry_price,
                            "SELL",
                            stop_loss_pct=config.stop_loss_pct,
                            take_profit_pct=config.take_profit_pct,
                        )
                        alert = bot.format_trade(
                            ticker=ticker,
                            action="SELL",
                            score=market_score.score,
                            entry=risk_plan.entry_price,
                            stop_loss=risk_plan.stop_loss,
                            take_profit=risk_plan.take_profit,
                        )
                        alert["pnl"] = 0.0
                        alert["status"] = "open"
                        alert["stop_loss"] = risk_plan.stop_loss
                        alert["take_profit"] = risk_plan.take_profit
                        journal.log_trade(alert)
                        print(f"[{ticker}] SELL ALERT -> Entry={alert['entry']:.2f}, SL={alert['stop_loss']:.2f}, TP={alert['take_profit']:.2f}, score={alert['score']}, P&L={alert['pnl']:.2f}")
                        print(bot.build_message(alert))
                        bot.send_trade_alert(alert)
                    else:
                        pnl = journal.update_trade_pnl(ticker, entry_price, "SELL")
                        updated = journal.get_open_trade(ticker, "SELL")
                        if updated is None:
                            close_message = bot.format_close(
                                ticker=ticker,
                                action="SELL",
                                exit_price=entry_price,
                                pnl=pnl,
                                reason="AUTO_CLOSE",
                            )
                            print(bot.build_message(close_message))
                            bot.send_trade_alert(close_message)
                        else:
                            print(f"[{ticker}] SELL OPEN -> Entry={open_trade['entry']:.2f}, current_price={entry_price:.2f}, P&L={pnl:.2f}")
                else:
                    print(f"[{ticker}] HOLD - not enough confidence")

            summary = journal.portfolio_summary()
            print(f"[PORTFOLIO] closed={summary['closed_pnl']:.2f}, open={summary['open_pnl']:.2f}, total={summary['total_pnl']:.2f}")
            print("-")
            time.sleep(config.interval_seconds)
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
        sys.exit(0)


def main() -> None:
    try:
        config = BotConfig.load()
    except FileNotFoundError as exc:
        print(f"Configuration error: {exc}")
        print("Create config.json from config.example.json and run the bot again.")
        raise SystemExit(1) from exc
    run_bot(config)
