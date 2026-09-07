from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests


logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.token = token.strip() if token else None
        self.chat_id = chat_id.strip() if chat_id else None

    def send_trade_alert(self, payload: Dict[str, Any]) -> bool:
        return self.send_message(payload.get("message", "Trade alert"))

    def send_message(self, text: str) -> bool:
        if not self.token or not self.chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        try:
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                logger.error("Telegram rejected alert: %s", result.get("description", "unknown error"))
                return False
            return True
        except requests.RequestException as exc:
            logger.error("Telegram alert request failed: %s", exc)
            return False
        except ValueError as exc:
            logger.error("Telegram returned an invalid response: %s", exc)
            return False

    def send_heartbeat(self, instruments: int, bar_interval_seconds: int) -> bool:
        return self.send_message(
            "Paper bot heartbeat\n"
            "Status: running\n"
            f"Instruments: {instruments}\n"
            f"Bar interval: {bar_interval_seconds}s"
        )

    def send_daily_summary(
        self,
        summary_date: str,
        closed_trades: int,
        winning_trades: int,
        losing_trades: int,
        total_pnl: float,
    ) -> bool:
        return self.send_message(
            f"Paper trading daily summary ({summary_date})\n"
            f"Closed trades: {closed_trades}\n"
            f"Wins/Losses: {winning_trades}/{losing_trades}\n"
            f"P&L: {total_pnl:.2f}"
        )

    def format_trade(self, ticker: str, action: str, score: int, entry: float, stop_loss: float, take_profit: float) -> Dict[str, Any]:
        return {
            "ticker": ticker,
            "action": action,
            "score": score,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "message": (
                f"{action} {ticker}\n"
                f"Score: {score}\n"
                f"Entry: {entry:.2f}\n"
                f"Stop Loss: {stop_loss:.2f}\n"
                f"Target: {take_profit:.2f}"
            ),
        }

    def build_message(self, payload: Dict[str, Any]) -> str:
        return payload.get("message", "Trade alert")

    def format_close(self, ticker: str, action: str, exit_price: float, pnl: float, reason: str) -> Dict[str, Any]:
        payload = {
            "ticker": ticker,
            "action": action,
            "exit_price": exit_price,
            "pnl": pnl,
            "reason": reason,
            "message": (
                f"Trade Closed: {action} {ticker}\n"
                f"Exit: {exit_price:.2f}\n"
                f"P&L: {pnl:.2f}\n"
                f"Reason: {reason}"
            ),
        }
        return payload
