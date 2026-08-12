import sys
import time
from datetime import datetime
from typing import List

from .config import BotConfig
from .data_provider import MarketDataProvider
from .strategy import analyze_history, Signal


def format_signal(signal: Signal) -> str:
    return (
        f"[{signal.ticker}] {signal.action} @ {signal.price:.2f}: {signal.reason}"
    )


def print_header(config: BotConfig) -> None:
    print("Share Market Alert Bot")
    print("======================")
    print(f"Tickers: {', '.join(config.tickers)}")
    print(f"Polling interval: {config.interval_seconds}s")
    print(f"EMA: {config.ema_fast}/{config.ema_slow}, RSI period: {config.rsi_period}")
    print()


def run_bot(config: BotConfig) -> None:
    provider = MarketDataProvider()
    print_header(config)

    try:
        while True:
            loop_start = datetime.now()
            for ticker in config.tickers:
                print(f"[{loop_start:%Y-%m-%d %H:%M:%S}] Checking {ticker}...")
                history = provider.fetch_history(
                    ticker,
                    period="1d",
                    interval="2m",
                )

                signal = analyze_history(
                    ticker=ticker,
                    history=history,
                    ema_fast=config.ema_fast,
                    ema_slow=config.ema_slow,
                    rsi_period=config.rsi_period,
                    alert_rsi_low=config.alert_rsi_low,
                    alert_rsi_high=config.alert_rsi_high,
                )

                if signal:
                    print(format_signal(signal))
                else:
                    print(f"[{ticker}] No actionable signal at {history[-1]['close']:.2f}" if history else f"[{ticker}] No data")

            print("-")
            time.sleep(config.interval_seconds)
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
        sys.exit(0)


def main() -> None:
    config = BotConfig.load()
    run_bot(config)
