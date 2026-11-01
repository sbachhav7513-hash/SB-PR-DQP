from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

import requests


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramCommand:
    chat_id: str
    user_id: Optional[str]
    text: str
    update_id: int
    message_timestamp: float


def parse_allowed_chat_ids(
    value: Optional[str],
    excluded_chat_ids: Iterable[str] = (),
) -> set[str]:
    allowed_ids = {
        item.strip()
        for item in (value or "").split(",")
        if item.strip()
    }
    return allowed_ids - {str(chat_id).strip() for chat_id in excluded_chat_ids}


class TelegramCommandListener:
    def __init__(
        self,
        token: str,
        allowed_chat_ids: Iterable[str],
        command_queue: queue.Queue[TelegramCommand],
        reply_queue: queue.Queue[tuple[str, str]],
        on_failure: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._token = token
        self._allowed_ids = {str(value) for value in allowed_chat_ids}
        self._command_queue = command_queue
        self._reply_queue = reply_queue
        self._on_failure = on_failure
        self._started_at = time.time()
        self.last_update_id: Optional[int] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._started_at = time.time()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="telegram-command-listener",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=6)

    def handle_update(self, update: dict) -> bool:
        update_id = update.get("update_id")
        try:
            update_id = int(update_id)
        except (TypeError, ValueError):
            return False

        if self.last_update_id is None or update_id > self.last_update_id:
            self.last_update_id = update_id

        message = update.get("message")
        if not isinstance(message, dict):
            return False
        chat = message.get("chat")
        sender = message.get("from")
        chat_id = str(chat.get("id")) if isinstance(chat, dict) and chat.get("id") is not None else ""
        user_id = (
            str(sender.get("id"))
            if isinstance(sender, dict) and sender.get("id") is not None
            else None
        )
        if chat_id not in self._allowed_ids:
            logger.warning("Ignoring Telegram update from unauthorized id %s", chat_id or "unknown")
            return False
        if user_id is not None and user_id != chat_id and user_id not in self._allowed_ids:
            logger.warning("Ignoring Telegram update from unauthorized id %s", user_id)
            return False

        try:
            message_timestamp = float(message.get("date"))
        except (TypeError, ValueError):
            return False
        if message_timestamp < self._started_at:
            return False

        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            return False

        self._command_queue.put(
            TelegramCommand(
                chat_id=chat_id,
                user_id=user_id,
                text=text.strip(),
                update_id=update_id,
                message_timestamp=message_timestamp,
            )
        )
        return True

    def _poll_updates(self) -> list[dict]:
        params = {"timeout": 1}
        if self.last_update_id is not None:
            params["offset"] = self.last_update_id + 1
        response = requests.get(
            f"https://api.telegram.org/bot{self._token}/getUpdates",
            params=params,
            timeout=5,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise RuntimeError("Telegram getUpdates request was rejected")
        return result.get("result", [])

    def _send_replies(self) -> None:
        while True:
            try:
                chat_id, text = self._reply_queue.get_nowait()
            except queue.Empty:
                return
            try:
                response = requests.post(
                    f"https://api.telegram.org/bot{self._token}/sendMessage",
                    data={"chat_id": chat_id, "text": text},
                    timeout=5,
                )
                response.raise_for_status()
            except requests.RequestException:
                logger.warning("Could not deliver a Telegram command response")

    def _run(self) -> None:
        failures = 0
        while not self._stop_event.is_set():
            try:
                for update in self._poll_updates():
                    self.handle_update(update)
                self._send_replies()
                failures = 0
            except Exception:
                failures += 1
                logger.warning(
                    "Telegram command listener failed (%d consecutive failure(s))",
                    failures,
                )
                if failures == 3 and self._on_failure:
                    try:
                        self._on_failure(
                            "Telegram command listener has failed 3 consecutive "
                            "times; it will keep retrying while trading continues."
                        )
                    except Exception:
                        logger.warning("Could not send Telegram listener failure alert")
                self._stop_event.wait(min(2 ** (failures - 1), 30))
