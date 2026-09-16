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