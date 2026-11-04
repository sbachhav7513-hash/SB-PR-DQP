import queue
import threading
import time
from unittest.mock import Mock

import requests

from market_bot.kite_main import KiteTradingBot
from market_bot.telegram_notifier import TelegramNotifier
from market_bot.telegram_control.listener import TelegramCommandListener


def test_option_trade_message_includes_exact_trading_symbol():
    payload = TelegramNotifier().format_trade(
        ticker="NIFTY_CE",
        action="BUY",
        score=8,
        entry=120.0,
        stop_loss=78.0,
        take_profit=196.0,
        mode="intraday_options",
        option_leg="CE",
        trading_symbol="NIFTY26SEP25000CE",
    )

    assert "OPTION Trade: BUY NIFTY_CE | Leg: CE" in payload["message"]
    assert "Trading symbol: NIFTY26SEP25000CE" in payload["message"]
    assert payload["trading_symbol"] == "NIFTY26SEP25000CE"


def test_close_message_includes_exact_trading_symbol():
    payload = TelegramNotifier().format_close(
        ticker="NIFTY_PE",
        action="SELL",
        exit_price=95.0,
        pnl=-25.0,
        reason="SIGNAL_REVERSAL",
        mode="intraday_options",
        option_leg="PE",
        trading_symbol="NIFTY26SEP25000PE",
    )

    assert "Trade Closed: OPTION SELL NIFTY_PE | Leg: PE" in payload["message"]
    assert "Trading symbol: NIFTY26SEP25000PE" in payload["message"]


def test_entry_and_exit_messages_include_stable_telegram_trade_id():
    notifier = TelegramNotifier()

    entry = notifier.format_trade(
        ticker="NIFTY_CE",
        action="BUY",
        score=80,
        entry=79.0,
        stop_loss=70.0,
        take_profit=95.0,
        mode="intraday_options",
        trade_id=7,
    )
    close = notifier.format_close(
        ticker="NIFTY_CE",
        action="BUY",
        exit_price=85.0,
        pnl=390.0,
        reason="TAKE_PROFIT",
        mode="intraday_options",
        trade_id=7,
    )

    assert entry["message"].startswith("#7 OPTION Trade:")
    assert entry["message"].endswith(
        "Manual commands: /exit 7, /exitat 7 <price>, /be 7"
    )
    assert close["message"].startswith("#7 Trade Closed:")
    assert "Exit reason: TAKE_PROFIT" in close["message"]
    assert "Exit source: BOT" in close["message"]


def test_trade_messages_render_without_trade_id():
    notifier = TelegramNotifier()

    entry = notifier.format_trade(
        ticker="NIFTY_CE",
        action="BUY",
        score=80,
        entry=79.0,
        stop_loss=70.0,
        take_profit=95.0,
        trade_id=None,
    )
    close = notifier.format_close(
        ticker="NIFTY_CE",
        action="BUY",
        exit_price=85.0,
        pnl=6.0,
        reason="MANUAL_EXIT",
        trade_id=None,
    )

    assert "#None" not in entry["message"]
    assert entry["message"].endswith("Manual commands: /exit, /exitat, /be")
    assert "#None" not in close["message"]
    assert "Exit source: MANUAL" in close["message"]


def test_trailing_stop_is_clear_in_telegram_messages():
    notifier = TelegramNotifier()

    trade = notifier.format_trade(
        ticker="NIFTY_CE",
        action="BUY",
        score=8,
        entry=55.0,
        stop_loss=50.0,
        take_profit=85.0,
        trailing_enabled=True,
    )
    close = notifier.format_close(
        ticker="NIFTY_CE",
        action="BUY",
        exit_price=76.0,
        pnl=21.0,
        reason="TRAILING_STOP",
    )

    assert "Trailing reference: 85.00" in trade["message"]
    assert "Reason: Trailing Stop" in close["message"]


def test_heartbeat_message_uses_configured_trading_mode():
    notifier = TelegramNotifier()

    message = notifier.build_heartbeat_message(
        instruments=15,
        bar_interval_seconds=60,
        mode="intraday_futures",
    )

    assert "Mode: PAPER" in message
    assert "Trading mode: Intraday Futures" in message
    assert "Status: RUNNING" in message
    assert "Instruments tracked: 15" in message

    options_message = notifier.build_heartbeat_message(
        instruments=12,
        bar_interval_seconds=30,
        mode="intraday_options",
    )

    assert "Trading mode: Intraday Options" in options_message
    assert "Instruments tracked: 12" in options_message

    paused_message = notifier.build_heartbeat_message(
        instruments=12,
        bar_interval_seconds=30,
        mode="intraday_options",
        execution_mode="SIM",
        state="PAUSED",
    )
    assert "Mode: SIM" in paused_message
    assert "Status: PAUSED" in paused_message


def test_trade_alert_is_sent_to_existing_and_trade_chats(monkeypatch):
    response = Mock()
    response.json.return_value = {"ok": True}
    post = Mock(return_value=response)
    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    notifier = TelegramNotifier(
        token="token",
        chat_id="existing-chat",
        trade_chat_id="trade-group",
    )

    assert notifier.send_trade_alert({"message": "Trade opened"})
    assert notifier.wait_until_idle()

    assert [call.kwargs["data"]["chat_id"] for call in post.call_args_list] == [
        "existing-chat",
        "trade-group",
    ]
    notifier.close(timeout=1)


def test_trade_alert_deduplicates_same_primary_and_trade_chat(monkeypatch):
    response = Mock()
    response.json.return_value = {"ok": True}
    post = Mock(return_value=response)
    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    notifier = TelegramNotifier(
        token="token",
        chat_id="same-chat",
        trade_chat_id="same-chat",
    )

    assert notifier.send_trade_alert({"message": "Trade closed"})
    assert notifier.wait_until_idle()

    post.assert_called_once()
    notifier.close(timeout=1)


def test_regular_status_message_stays_in_existing_chat(monkeypatch):
    response = Mock()
    response.json.return_value = {"ok": True}
    post = Mock(return_value=response)
    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    notifier = TelegramNotifier(
        token="token",
        chat_id="existing-chat",
        trade_chat_id="trade-group",
    )

    assert notifier.send_message("Bot is online")
    assert notifier.wait_until_idle()

    post.assert_called_once()
    assert post.call_args.kwargs["data"]["chat_id"] == "existing-chat"
    notifier.close(timeout=1)


def _telegram_response():
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"ok": True}
    return response


def test_open_trade_alert_escapes_html_and_logs_enqueue_and_delivery(
    monkeypatch, caplog
):
    caplog.set_level("INFO", logger="market_bot.telegram_notifier")
    post = Mock(return_value=_telegram_response())
    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    notifier = TelegramNotifier(token="token", chat_id="chat")
    payload = notifier.format_trade(
        ticker="NIFTY_CE & <PE>",
        action="BUY",
        score=80,
        entry=79.0,
        stop_loss=70.0,
        take_profit=95.0,
        trade_id=17,
    )
    payload["status"] = "open"

    try:
        assert notifier.send_trade_alert(payload, trade_id=17)
        assert notifier.wait_until_idle()

        post.assert_called_once()
        text = post.call_args.kwargs["data"]["text"]
        assert post.call_args.kwargs["data"]["parse_mode"] == "HTML"
        assert "NIFTY_CE &amp; &lt;PE&gt;" in text
        assert "/exitat 17 &lt;price&gt;" in text
        assert notifier.telemetry()["sent"] == 1
        assert "Telegram entry alert enqueued trade_id=17" in caplog.text
        assert (
            "Telegram entry alert send result trade_id=17 chat=chat "
            "sent=true status=200"
        ) in caplog.text
    finally:
        notifier.close(timeout=1)


def test_telegram_http_4xx_is_not_retried_and_logs_description(monkeypatch, caplog):
    caplog.set_level("INFO", logger="market_bot.telegram_notifier")
    response = Mock()
    response.status_code = 400
    response.json.return_value = {
        "ok": False,
        "description": "Bad Request: can't parse entities",
    }
    post = Mock(return_value=response)
    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    notifier = TelegramNotifier(token="token", chat_id="chat")
    payload = notifier.format_trade(
        ticker="NIFTY_CE",
        action="BUY",
        score=80,
        entry=79.0,
        stop_loss=70.0,
        take_profit=95.0,
        trade_id=19,
    )
    payload["status"] = "open"

    try:
        assert notifier.send_trade_alert(payload, trade_id=19)
        assert notifier.wait_until_idle()

        post.assert_called_once()
        assert notifier.telemetry()["failed"] == 1
        assert "status=400" in caplog.text
        assert "description=Bad Request: can't parse entities" in caplog.text
        assert (
            "Telegram entry alert send result trade_id=19 chat=chat "
            "sent=false status=400"
        ) in caplog.text
    finally:
        notifier.close(timeout=1)


def test_exit_trade_alert_escapes_dynamic_html_before_send(monkeypatch):
    post = Mock(return_value=_telegram_response())
    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    notifier = TelegramNotifier(token="token", chat_id="chat")
    payload = notifier.format_close(
        ticker="NIFTY&<PE>",
        action="SELL",
        exit_price=95.0,
        pnl=-25.0,
        reason="BROKER<&>",
    )

    try:
        assert notifier.send_trade_alert(payload, trade_id=20)
        assert notifier.wait_until_idle()

        post.assert_called_once()
        text = post.call_args.kwargs["data"]["text"]
        assert "NIFTY&amp;&lt;PE&gt;" in text
        assert "BROKER&lt;&amp;&gt;" in text
    finally:
        notifier.close(timeout=1)


def test_slow_send_does_not_delay_on_tick(monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def hanging_post(*_args, **_kwargs):
        entered.set()
        release.wait(60)
        return _telegram_response()

    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", hanging_post)
    notifier = TelegramNotifier(token="token", chat_id="chat")
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot._telegram_execution_lock = threading.RLock()
    bot._on_tick_serialized = lambda _tick: notifier.send_message("tick alert")

    try:
        started = time.perf_counter()
        bot._on_tick(None)
        assert time.perf_counter() - started < 0.1
        assert entered.wait(1)
    finally:
        release.set()
        notifier.close(timeout=1)


def test_tick_message_is_queued_after_execution_lock_is_released(monkeypatch):
    acquired_during_send = threading.Event()
    lock = threading.RLock()

    def post(*_args, **_kwargs):
        if lock.acquire(blocking=False):
            acquired_during_send.set()
            lock.release()
        return _telegram_response()

    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    notifier = TelegramNotifier(token="token", chat_id="chat")
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot._telegram_execution_lock = lock
    bot._on_tick_serialized = lambda _tick: notifier.send_message("tick alert")

    bot._on_tick(None)

    assert notifier.wait_until_idle()
    assert acquired_during_send.is_set()
    notifier.close(timeout=1)


def test_send_retries_then_succeeds(monkeypatch):
    post = Mock(side_effect=[requests.Timeout(), _telegram_response()])
    delays = []
    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    monkeypatch.setattr(
        "market_bot.telegram_notifier.time.sleep", lambda seconds: delays.append(seconds)
    )
    notifier = TelegramNotifier(token="token", chat_id="chat")

    assert notifier.send_message("retry")
    assert notifier.wait_until_idle()

    assert post.call_count == 2
    assert post.call_args.kwargs["timeout"] == 5
    assert delays == [1]
    assert notifier.telemetry()["sent"] == 1
    assert notifier.telemetry()["failed"] == 0
    assert notifier.telemetry()["last_success_time"] != "never"
    notifier.close(timeout=1)


def test_exhausted_retries_count_one_failed_message(monkeypatch, caplog):
    post = Mock(side_effect=requests.Timeout())
    delays = []
    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    monkeypatch.setattr(
        "market_bot.telegram_notifier.time.sleep", lambda seconds: delays.append(seconds)
    )
    notifier = TelegramNotifier(token="token", chat_id="chat")

    assert notifier.send_message("failure")
    assert notifier.wait_until_idle()

    assert post.call_count == 3
    assert post.call_args.kwargs["timeout"] == 5
    assert delays == [1, 3]
    assert notifier.telemetry()["failed"] == 1
    assert "Telegram delivery failed chat=chat attempts=3" in caplog.text
    notifier.close(timeout=1)


def test_queue_full_drops_heartbeat_before_regular_messages(monkeypatch):
    monkeypatch.setattr("market_bot.telegram_notifier.TELEGRAM_QUEUE_SIZE", 3)
    entered = threading.Event()
    release = threading.Event()
    delivered = []

    def post(_url, *, data, **_kwargs):
        if data["text"] == "first":
            entered.set()
            release.wait(2)
        delivered.append(data["text"])
        return _telegram_response()

    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    notifier = TelegramNotifier(token="token", chat_id="chat")
    notifier.send_message("first")
    assert entered.wait(1)
    notifier.send_heartbeat(1, 60)
    notifier.send_message("second")
    notifier.send_message("third")
    notifier.send_message("fourth")

    assert notifier.telemetry()["dropped"] == 1
    release.set()
    assert notifier.wait_until_idle()

    assert delivered == ["first", "second", "third", "fourth"]
    notifier.close(timeout=1)


def test_command_reply_uses_the_shared_sender(monkeypatch):
    post = Mock(return_value=_telegram_response())
    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    notifier = TelegramNotifier(token="token", chat_id="primary")
    listener = TelegramCommandListener(
        token="token",
        allowed_chat_ids=("chat",),
        command_queue=queue.Queue(),
        reply_queue=queue.Queue(),
        enqueue_reply=notifier.enqueue_command_reply,
        enqueue_callback_ack=notifier.enqueue_callback_ack,
    )
    listener._callback_ack_queue.put("callback-1")
    listener._reply_queue.put(("chat", "Command completed"))

    listener._send_replies()
    assert notifier.wait_until_idle()

    assert post.call_count == 2
    assert post.call_args_list[0].args[0].endswith("/answerCallbackQuery")
    assert post.call_args_list[0].kwargs["data"]["callback_query_id"] == "callback-1"
    assert post.call_args_list[1].args[0].endswith("/sendMessage")
    assert post.call_args_list[1].kwargs["data"]["chat_id"] == "chat"
    assert post.call_args_list[1].kwargs["data"]["text"] == "Command completed"
    notifier.close(timeout=1)


def test_messages_remain_ordered_per_chat(monkeypatch):
    delivered = []
    post = Mock(
        side_effect=lambda _url, *, data, **_kwargs: (
            delivered.append(data["text"]) or _telegram_response()
        )
    )
    monkeypatch.setattr("market_bot.telegram_notifier.requests.post", post)
    notifier = TelegramNotifier(token="token", chat_id="chat")

    for text in ("one", "two", "three"):
        notifier.send_message(text)
    assert notifier.wait_until_idle()

    assert delivered == ["one", "two", "three"]
    notifier.close(timeout=1)