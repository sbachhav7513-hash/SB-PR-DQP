from __future__ import annotations

from typing import Any, Dict, Optional

import requests


class TelegramNotifier:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.token = token.strip() if token else None
        self.chat_id = chat_id.strip() if chat_id else None

    def send_trade_alert(self, payload: Dict[str, Any]) -> bool:
        if not self.token or not self.chat_id:
            return False

        text = payload.get("message", "Trade alert")
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        try:
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            return True
        except requests.RequestException:
            return False

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
