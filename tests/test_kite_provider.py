from datetime import date, timedelta
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


def test_refresh_instrument_tokens_ignores_futures_without_live_quotes():
    kite = Mock()
    today = date.today()
    kite.instruments.return_value = [
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTYFUT",
            "instrument_type": "FUT",
            "expiry": today + timedelta(days=30),
            "instrument_token": 100,
            "lot_size": 50,
        },
        {
            "name": "INFY",
            "tradingsymbol": "INFYFUT",
            "instrument_type": "FUT",
            "expiry": today + timedelta(days=30),
            "instrument_token": 300,
            "lot_size": 500,
        },
    ]
    kite.ltp.return_value = {
        "100": {"last_price": 0.0},
        "300": {"last_price": 1500.0},
    }

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(
                api_key="key",
                access_token="token",
                futures_underlyings=["NIFTY", "INFY"],
            )
        )

    assert stream.refresh_instrument_tokens() == {"INFY": 300}
    assert stream.contract_specs == {"INFY": {"lot_size": 500, "multiplier": 1}}
    kite.ltp.assert_called_once_with(["100", "300"])

def test_refresh_instrument_tokens_falls_back_to_ltp_when_quote_api_returns_empty():
    kite = Mock()
    today = date.today()
    kite.instruments.return_value = [
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTYFUT",
            "instrument_type": "FUT",
            "expiry": today + timedelta(days=30),
            "instrument_token": 100,
            "lot_size": 50,
        },
        {
            "name": "INFY",
            "tradingsymbol": "INFYFUT",
            "instrument_type": "FUT",
            "expiry": today + timedelta(days=30),
            "instrument_token": 300,
            "lot_size": 500,
        },
    ]
    kite.quote.return_value = {}
    kite.ltp.return_value = {
        "100": {"last_price": 0.0},
        "300": {"last_price": 1500.0},
    }

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(
                api_key="key",
                access_token="token",
                futures_underlyings=["NIFTY", "INFY"],
                auto_discover_futures=True,
                min_futures_volume=0,
            )
        )

    assert stream.refresh_instrument_tokens() == {"INFY": 300}
    assert stream.contract_specs == {"INFY": {"lot_size": 500, "multiplier": 1}}
    kite.quote.assert_called_once_with(["NFO:NIFTYFUT", "NFO:INFYFUT"])
    kite.ltp.assert_called_once_with(["100", "300"])


def test_refresh_instrument_tokens_returns_empty_when_no_futures_survive_quote_checks():
    kite = Mock()
    today = date.today()
    kite.instruments.return_value = [
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTYFUT",
            "instrument_type": "FUT",
            "expiry": today + timedelta(days=30),
            "instrument_token": 100,
            "lot_size": 50,
        },
        {
            "name": "INFY",
            "tradingsymbol": "INFYFUT",
            "instrument_type": "FUT",
            "expiry": today + timedelta(days=30),
            "instrument_token": 300,
            "lot_size": 500,
        },
    ]
    kite.quote.return_value = {}
    kite.ltp.return_value = {
        "100": {"last_price": 0.0},
        "300": {"last_price": 0.0},
    }

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(
                api_key="key",
                access_token="token",
                futures_underlyings=["NIFTY", "INFY"],
                auto_discover_futures=True,
                min_futures_volume=50000,
            )
        )

    assert stream.refresh_instrument_tokens() == {}
    assert stream.contract_specs == {}
    kite.quote.assert_called_once_with(["NFO:NIFTYFUT", "NFO:INFYFUT"])
    assert kite.ltp.call_args_list == [
        ((["100", "300"],), {}),
        ((["100", "300"],), {}),
    ]


def test_on_ticks_drops_malformed_zero_instrument_tokens():
    kite = Mock()

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(api_key="key", access_token="token")
        )

    callback = Mock()
    stream.on_tick_callback = callback

    malformed_ticks = [
        {"timestamp": 1700000000, "last_price": 100.0},
        {"instrument_token": 0, "timestamp": 1700000000, "last_price": 100.0},
    ]

    stream.on_ticks(None, malformed_ticks)

    callback.assert_not_called()


def test_refresh_instrument_tokens_selects_current_nearest_futures_expiry():
    kite = Mock()
    today = date.today()
    kite.instruments.return_value = [
        {
            "name": "INFY",
            "tradingsymbol": "INFYFUT",
            "instrument_type": "FUT",
            "expiry": today + timedelta(days=30),
            "instrument_token": 300,
            "lot_size": 500,
        },
        {
            "name": "INFY",
            "tradingsymbol": "INFYFUTOLD",
            "instrument_type": "FUT",
            "expiry": today - timedelta(days=1),
            "instrument_token": 301,
            "lot_size": 500,
        },
    ]
    kite.ltp.return_value = {"300": {"last_price": 1500.0}}

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(
                api_key="key",
                access_token="token",
                futures_underlyings=["INFY"],
            )
        )

    assert stream.refresh_instrument_tokens() == {"INFY": 300}
    assert stream.contract_specs == {"INFY": {"lot_size": 500, "multiplier": 1}}
    kite.ltp.assert_called_once_with(["300"])