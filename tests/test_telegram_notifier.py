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