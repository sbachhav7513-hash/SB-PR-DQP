from unittest.mock import Mock

from market_bot.telegram_notifier import TelegramNotifier


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
        telegram_trade_id=7,
    )
    close = notifier.format_close(
        ticker="NIFTY_CE",
        action="BUY",
        exit_price=85.0,
        pnl=390.0,
        reason="TAKE_PROFIT",
        mode="intraday_options",
        telegram_trade_id=7,
    )

    assert entry["message"].startswith("#7 OPTION Trade:")
    assert close["message"].startswith("#7 Trade Closed:")


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

    assert "Mode: Intraday Futures" in message
    assert "Instruments tracked: 15" in message

    options_message = notifier.build_heartbeat_message(
        instruments=12,
        bar_interval_seconds=30,
        mode="intraday_options",
    )

    assert "Mode: Intraday Options" in options_message
    assert "Instruments tracked: 12" in options_message


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

    assert [call.kwargs["data"]["chat_id"] for call in post.call_args_list] == [
        "existing-chat",
        "trade-group",
    ]


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

    post.assert_called_once()


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

    post.assert_called_once()
    assert post.call_args.kwargs["data"]["chat_id"] == "existing-chat"