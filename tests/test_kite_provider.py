from unittest.mock import Mock, patch

from market_bot.kite_provider import KiteConfig, KiteMarketStream


def test_refresh_instrument_tokens_remaps_stale_symbols_and_validates_all_tokens():
    kite = Mock()
    kite.instruments.return_value = [
        {"tradingsymbol": "INFY", "instrument_token": 408065},
    ]
    kite.ltp.return_value = {"408065": {"last_price": 100.0}, "256265": {"last_price": 20000.0}}

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(
                api_key="key",
                access_token="token",
                instrument_tokens={"INFY": 1222041, "NIFTY": 256265},
            )
        )

    resolved = stream.refresh_instrument_tokens()

    assert resolved == {"INFY": 408065, "NIFTY": 256265}
    assert stream.config.instrument_tokens == resolved
    kite.ltp.assert_called_once_with(["408065", "256265"])


def test_refresh_instrument_tokens_fails_for_unresolved_symbols():
    kite = Mock()
    kite.instruments.return_value = []
    kite.ltp.return_value = {}

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(
                api_key="key",
                access_token="token",
                instrument_tokens={"REMOVED": 123},
            )
        )

    try:
        stream.refresh_instrument_tokens()
    except RuntimeError as exc:
        assert "REMOVED" in str(exc)
    else:
        raise AssertionError("Expected unresolved symbols to fail startup validation")