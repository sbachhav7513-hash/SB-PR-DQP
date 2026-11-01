from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests


logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        trade_chat_id: Optional[str] = None,
    ) -> None:
        self.token = token.strip() if token else None
        self.chat_id = chat_id.strip() if chat_id else None
        self.trade_chat_id = trade_chat_id.strip() if trade_chat_id else None

    @staticmethod
    def _trade_message(text: str, trade_id: Optional[int], *, entry: bool = False) -> str:
        if trade_id is None:
            return text

        reference = f"#{trade_id}"
        if text.startswith(f"{reference} "):
            text = text[len(reference) + 1 :]
        if entry:
            text = "\n".join(
                line for line in text.splitlines()
                if not line.startswith("Manual commands:")
            )
            text += (
                f"\nManual commands: /exit {trade_id}, "
                f"/exitat {trade_id} <price>, /be {trade_id}"
            )
        return f"{reference} {text}"

    def send_trade_alert(
        self, payload: Dict[str, Any], trade_id: Optional[int] = None
    ) -> bool:
        text = payload.get("message", "Trade alert")
        resolved_trade_id = trade_id
        if resolved_trade_id is None:
            resolved_trade_id = payload.get("trade_id")
        if resolved_trade_id is None:
            resolved_trade_id = payload.get("telegram_trade_id")
        text = self._trade_message(
            text,
            resolved_trade_id,
            entry=payload.get("status") == "open" and payload.get("entry") is not None,
        )
        chat_ids = dict.fromkeys(
            chat_id
            for chat_id in (self.chat_id, self.trade_chat_id)
            if chat_id
        )
        if not chat_ids:
            return False
        results = [self._send_message_to_chat(chat_id, text) for chat_id in chat_ids]
        return all(results)

    def send_message(self, text: str, trade_id: Optional[int] = None) -> bool:
        text = self._trade_message(text, trade_id)
        return self._send_message_to_chat(self.chat_id, text)

    def _send_message_to_chat(self, chat_id: Optional[str], text: str) -> bool:
        if not self.token or not chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {
            "chat_id": chat_id,
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
            logger.error(
                "Telegram alert request failed (%s)",
                type(exc).__name__,
            )
            return False
        except ValueError as exc:
            logger.error("Telegram returned an invalid response: %s", exc)
            return False

    def build_heartbeat_message(
        self,
        instruments: int,
        bar_interval_seconds: int,
        mode: Optional[str] = None,
        execution_mode: Optional[str] = None,
        state: str = "RUNNING",
    ) -> str:
        normalized_mode = str(mode or "intraday_futures").strip().lower()
        if normalized_mode in {"intraday_options", "options"}:
            mode_label = "Intraday Options"
        elif normalized_mode in {"intraday_both", "both"}:
            mode_label = "Intraday Both"
        else:
            mode_label = "Intraday Futures"

        return (
            "Market Bot Status\n"
            f"Status: {state.upper()}\n"
            f"Mode: {str(execution_mode or 'PAPER').upper()}\n"
            f"Trading mode: {mode_label}\n"
            "Signal engine: online\n"
            f"Instruments tracked: {instruments}\n"
            f"Bar interval: {bar_interval_seconds}s\n"
            "Next check: recent bars and live quote feed are being monitored\n"
            "Action: no trade signal yet; confirm signal quality and market context"
        )

    def send_heartbeat(
        self,
        instruments: int,
        bar_interval_seconds: int,
        mode: Optional[str] = None,
        execution_mode: Optional[str] = None,
        state: str = "RUNNING",
    ) -> bool:
        return self.send_message(
            self.build_heartbeat_message(
                instruments, bar_interval_seconds, mode, execution_mode, state
            )
        )

    def send_daily_summary(
        self,
        summary_date: str,
        closed_trades: int,
        winning_trades: int,
        losing_trades: int,
        total_pnl: float,
    ) -> bool:
        return self.send_trade_alert(
            {
                "message": (
                    f"Paper trading daily summary ({summary_date})\n"
                    f"Closed trades: {closed_trades}\n"
                    f"Wins/Losses: {winning_trades}/{losing_trades}\n"
                    f"P&L: {total_pnl:.2f}"
                )
            }
        )

    def format_trade(
        self,
        ticker: str,
        action: str,
        score: int,
        entry: float,
        stop_loss: float,
        take_profit: float,
        mode: str = "FUTURE",
        option_leg: Optional[str] = None,
        trading_symbol: Optional[str] = None,
        trailing_enabled: bool = False,
        trade_id: Optional[int] = None,
        telegram_trade_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        label = "OPTION" if str(mode).lower() == "intraday_options" else "FUTURE"
        leg = f" | Leg: {option_leg}" if option_leg else ""
        target_label = "Trailing reference" if trailing_enabled else "Target"
        resolved_trade_id = trade_id if trade_id is not None else telegram_trade_id
        trade_reference = f"#{resolved_trade_id} " if resolved_trade_id is not None else ""
        return {
            "ticker": ticker,
            "trading_symbol": trading_symbol or ticker,
            "action": action,
            "score": score,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "mode": label,
            "message": (
                f"{trade_reference}{label} Trade: {action} {ticker}{leg}\n"
                f"Score: {score}\n"
                f"Trading symbol: {trading_symbol or ticker}\n"
                f"Entry: {entry:.2f}\n"
                f"Stop Loss: {stop_loss:.2f}\n"
                f"{target_label}: {take_profit:.2f}\n"
                + (
                    f"Manual commands: /exit {resolved_trade_id}, "
                    f"/exitat {resolved_trade_id} <price>, /be {resolved_trade_id}"
                    if resolved_trade_id is not None
                    else "Manual commands: /exit, /exitat, /be"
                )
            ),
            "trade_id": resolved_trade_id,
        }

    def build_message(self, payload: Dict[str, Any]) -> str:
        return payload.get("message", "Trade alert")

    def format_watchlist(
        self,
        candidates: list[tuple[str, str, int, str]],
        session_label: str = "PREMARKET",
    ) -> Dict[str, Any]:
        lines = [f"Pre-market watchlist ({session_label})"]
        if not candidates:
            lines.append("No qualified setups")
        else:
            for ticker, signal, score, reason in candidates:
                lines.append(f"{signal} {ticker} | score={score} | {reason}")
        return {
            "message": "\n".join(lines),
            "candidates": candidates,
        }

    def send_watchlist(
        self,
        candidates: list[tuple[str, str, int, str]],
        session_label: str = "PREMARKET",
    ) -> bool:
        payload = self.format_watchlist(candidates, session_label)
        return self.send_trade_alert(payload)

    def format_close(
        self,
        ticker: str,
        action: str,
        exit_price: float,
        pnl: float,
        reason: str,
        mode: str = "FUTURE",
        option_leg: Optional[str] = None,
        trading_symbol: Optional[str] = None,
        trade_id: Optional[int] = None,
        telegram_trade_id: Optional[int] = None,
        exit_source: Optional[str] = None,
        exit_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        label = "OPTION" if str(mode).lower() == "intraday_options" else "FUTURE"
        leg = f" | Leg: {option_leg}" if option_leg else ""
        resolved_trade_id = trade_id if trade_id is not None else telegram_trade_id
        trade_reference = f"#{resolved_trade_id} " if resolved_trade_id is not None else ""
        normalized_exit_source = str(
            exit_source or ("MANUAL" if reason in {"MANUAL_EXIT", "MANUAL_TARGET"} else "BOT")
        ).upper()
        normalized_exit_reason = exit_reason or reason
        reason_label = {
            "TRAILING_STOP": "Trailing Stop",
            "TAKE_PROFIT": "Take Profit",
            "STOP_LOSS": "Stop Loss",
        }.get(reason, reason.replace("_", " ").title())
        payload = {
            "ticker": ticker,
            "action": action,
            "exit_price": exit_price,
            "pnl": pnl,
            "reason": reason,
            "exit_reason": normalized_exit_reason,
            "exit_source": normalized_exit_source,
            "trade_id": resolved_trade_id,
            "mode": label,
            "message": (
                f"{trade_reference}Trade Closed: {label} {action} {ticker}{leg}\n"
                f"Trading symbol: {trading_symbol or ticker}\n"
                f"Exit: {exit_price:.2f}\n"
                f"P&L: {pnl:.2f}\n"
                f"Reason: {reason_label}\n"
                f"Exit reason: {normalized_exit_reason}\n"
                f"Exit source: {normalized_exit_source}"
            ),
        }
        return payload
