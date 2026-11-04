from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests


logger = logging.getLogger(__name__)
TELEGRAM_QUEUE_SIZE = 1000
TELEGRAM_TIMEOUT_SECONDS = 5
TELEGRAM_RETRY_BACKOFF_SECONDS = (1, 3)


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
        self._queue = deque()
        self._queue_condition = threading.Condition()
        self._deferred = threading.local()
        self._closed = False
        self._sent = 0
        self._failed = 0
        self._dropped = 0
        self._processing = False
        self._last_success_time: Optional[str] = None
        self._sender_thread: Optional[threading.Thread] = None
        if self.token:
            self._sender_thread = threading.Thread(
                target=self._run_sender,
                name="telegram-message-sender",
                daemon=True,
            )
            self._sender_thread.start()

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
        return self._enqueue_messages(
            [
                {
                    "kind": "message",
                    "chat_id": chat_id,
                    "text": text,
                    "priority": "normal",
                }
                for chat_id in chat_ids
            ]
        )

    def send_message(
        self,
        text: str,
        trade_id: Optional[int] = None,
        *,
        priority: str = "normal",
    ) -> bool:
        text = self._trade_message(text, trade_id)
        if not self.chat_id:
            return False
        return self._enqueue_messages(
            [
                {
                    "kind": "message",
                    "chat_id": self.chat_id,
                    "text": text,
                    "priority": priority,
                }
            ]
        )

    def enqueue_command_reply(
        self,
        chat_id: str,
        text: str,
        reply_markup: Optional[dict] = None,
    ) -> bool:
        return self._enqueue_messages(
            [
                {
                    "kind": "message",
                    "chat_id": str(chat_id),
                    "text": text,
                    "reply_markup": reply_markup,
                    "priority": "normal",
                }
            ]
        )

    def enqueue_callback_ack(self, callback_id: str) -> bool:
        return self._enqueue_messages(
            [
                {
                    "kind": "callback_ack",
                    "callback_id": callback_id,
                    "priority": "normal",
                }
            ]
        )

    def _enqueue_messages(self, messages: list[dict]) -> bool:
        if not self.token or not messages:
            return False
        depth = getattr(self._deferred, "depth", 0)
        if depth:
            self._deferred.messages.extend(messages)
            return True
        return self._enqueue_messages_now(messages)

    def begin_defer(self) -> None:
        depth = getattr(self._deferred, "depth", 0)
        if depth == 0:
            self._deferred.messages = []
        self._deferred.depth = depth + 1

    def end_defer(self) -> None:
        depth = getattr(self._deferred, "depth", 0)
        if depth <= 0:
            raise RuntimeError("Telegram defer scope is not active")
        self._deferred.depth = depth - 1
        if depth == 1:
            messages = self._deferred.messages
            self._deferred.messages = []
            if messages:
                self._enqueue_messages_now(messages)

    def _enqueue_messages_now(self, messages: list[dict]) -> bool:
        accepted = True
        with self._queue_condition:
            if self._closed:
                self._dropped += len(messages)
                return False
            for message in messages:
                if len(self._queue) >= TELEGRAM_QUEUE_SIZE:
                    heartbeat_index = next(
                        (
                            index
                            for index, queued in enumerate(self._queue)
                            if queued["priority"] == "heartbeat"
                        ),
                        None,
                    )
                    if heartbeat_index is not None:
                        del self._queue[heartbeat_index]
                        self._dropped += 1
                        logger.warning(
                            "Telegram queue full; dropped oldest heartbeat message"
                        )
                    else:
                        self._dropped += 1
                        accepted = False
                        logger.warning(
                            "Telegram queue full; dropped incoming %s message",
                            message["priority"],
                        )
                        continue
                self._queue.append(message)
            self._queue_condition.notify()
        return accepted

    def telemetry(self) -> dict:
        with self._queue_condition:
            return {
                "queue_depth": len(self._queue),
                "sent": self._sent,
                "failed": self._failed,
                "dropped": self._dropped,
                "last_success_time": self._last_success_time or "never",
            }

    def close(self, timeout: float = 0.0) -> None:
        with self._queue_condition:
            self._closed = True
            self._queue_condition.notify_all()
        if (
            self._sender_thread is not None
            and self._sender_thread is not threading.current_thread()
        ):
            self._sender_thread.join(timeout=max(0.0, timeout))

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._queue_condition:
            while self._queue or self._processing:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._queue_condition.wait(remaining)
            return True

    def _run_sender(self) -> None:
        while True:
            with self._queue_condition:
                while not self._queue and not self._closed:
                    self._queue_condition.wait()
                if not self._queue and self._closed:
                    return
                message = self._queue.popleft()
                self._processing = True
            try:
                self._deliver(message)
            finally:
                with self._queue_condition:
                    self._processing = False
                    self._queue_condition.notify_all()

    def _deliver(self, message: dict) -> None:
        for attempt in range(3):
            try:
                if message["kind"] == "callback_ack":
                    url = (
                        f"https://api.telegram.org/bot{self.token}/"
                        "answerCallbackQuery"
                    )
                    data = {"callback_query_id": message["callback_id"]}
                else:
                    url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                    data = {
                        "chat_id": message["chat_id"],
                        "text": message["text"],
                    }
                    if message.get("reply_markup") is not None:
                        data["reply_markup"] = json.dumps(message["reply_markup"])
                    else:
                        data["parse_mode"] = "HTML"
                response = requests.post(
                    url, data=data, timeout=TELEGRAM_TIMEOUT_SECONDS
                )
                response.raise_for_status()
                result = response.json()
                if not result.get("ok"):
                    raise RuntimeError(
                        result.get("description", "Telegram rejected message")
                    )
            except Exception as exc:
                if attempt < 2:
                    time.sleep(TELEGRAM_RETRY_BACKOFF_SECONDS[attempt])
                    continue
                with self._queue_condition:
                    self._failed += 1
                logger.error(
                    "Telegram delivery failed chat=%s attempts=3 error=%s",
                    message.get("chat_id", "callback"),
                    type(exc).__name__,
                )
                return
            with self._queue_condition:
                self._sent += 1
                self._last_success_time = datetime.now(timezone.utc).isoformat()
            return

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
            ),
            priority="heartbeat",
        )

    def send_daily_summary(
        self,
        summary_date: str,
        closed_trades: int,
        winning_trades: int,
        losing_trades: int,
        total_pnl: float,
        message: Optional[str] = None,
    ) -> bool:
        return self.send_trade_alert(
            {
                "message": message
                or (
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
