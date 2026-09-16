from datetime import date, timedelta
from unittest.mock import Mock, patch

from market_bot.intraday_manager import IntradayManager
from market_bot.kite_main import KiteTradingBot
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


def test_refresh_instrument_tokens_selects_atm_call_and_put_for_options():
    kite = Mock()
    today = date.today()
    kite.instruments.return_value = [
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTY26SEP25000CE",
            "instrument_type": "CE",
            "expiry": today + timedelta(days=7),
            "strike": 25000,
            "instrument_token": 200,
            "lot_size": 65,
        },
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTY26SEP25000PE",
            "instrument_type": "PE",
            "expiry": today + timedelta(days=7),
            "strike": 25000,
            "instrument_token": 201,
            "lot_size": 65,
        },
    ]
    kite.ltp.return_value = {
        "100": {"last_price": 25010.0},
        "200": {"last_price": 120.0},
        "201": {"last_price": 110.0},
    }

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(
                api_key="key",
                access_token="token",
                trading_mode="intraday_options",
                instrument_tokens={"NIFTY": 100},
                options_underlyings=["NIFTY"],
                option_strike_step={"NIFTY": 50},
            )
        )

    assert stream.refresh_instrument_tokens() == {
        "NIFTY_CE": 200,
        "NIFTY_PE": 201,
    }
    assert stream.contract_symbols == {
        "NIFTY_CE": "NIFTY26SEP25000CE",
        "NIFTY_PE": "NIFTY26SEP25000PE",
    }
    assert stream.contract_specs["NIFTY_CE"] == {"lot_size": 65, "multiplier": 1}


def test_buy_uses_ce_and_sell_uses_pe_for_underlying():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "instrument_tokens": {"NIFTY_CE": 200, "NIFTY_PE": 201},
    }

    assert bot._preferred_option_symbol("NIFTY", "BUY") == "NIFTY_CE"
    assert bot._preferred_option_symbol("NIFTY", "SELL") == "NIFTY_PE"
    assert bot._preferred_option_symbol("NIFTY", "HOLD") is None


def test_near_atm_option_selection_prefers_closest_strike_within_allowed_distance():
    kite = Mock()
    today = date.today()
    kite.instruments.return_value = [
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTY26SEP24800CE",
            "instrument_type": "CE",
            "expiry": today + timedelta(days=7),
            "strike": 24800,
            "instrument_token": 200,
            "lot_size": 50,
        },
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTY26SEP24900CE",
            "instrument_type": "CE",
            "expiry": today + timedelta(days=7),
            "strike": 24900,
            "instrument_token": 201,
            "lot_size": 50,
        },
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTY26SEP24800PE",
            "instrument_type": "PE",
            "expiry": today + timedelta(days=7),
            "strike": 24800,
            "instrument_token": 202,
            "lot_size": 50,
        },
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTY26SEP24900PE",
            "instrument_type": "PE",
            "expiry": today + timedelta(days=7),
            "strike": 24900,
            "instrument_token": 203,
            "lot_size": 50,
        },
    ]
    kite.ltp.return_value = {
        "100": {"last_price": 24880.0},
        "200": {"last_price": 120.0},
        "201": {"last_price": 100.0},
        "202": {"last_price": 110.0},
        "203": {"last_price": 95.0},
    }

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(
                api_key="key",
                access_token="token",
                trading_mode="intraday_options",
                instrument_tokens={"NIFTY": 100},
                options_underlyings=["NIFTY"],
                option_strike_step={"NIFTY": 50},
                option_max_strike_distance_pct=0.5,
            )
        )

    resolved = stream.refresh_instrument_tokens()
    assert resolved["NIFTY_CE"] == 201
    assert resolved["NIFTY_PE"] == 203


def test_next_week_option_mode_skips_nearest_expiry():
    kite = Mock()
    today = date.today()
    near_expiry = today + timedelta(days=2)
    next_week_expiry = today + timedelta(days=9)
    kite.instruments.return_value = [
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTY26SEP25000CE",
            "instrument_type": "CE",
            "expiry": near_expiry,
            "strike": 25000,
            "instrument_token": 200,
            "lot_size": 65,
        },
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTY26SEP25000PE",
            "instrument_type": "PE",
            "expiry": near_expiry,
            "strike": 25000,
            "instrument_token": 201,
            "lot_size": 65,
        },
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTY26OCT25000CE",
            "instrument_type": "CE",
            "expiry": next_week_expiry,
            "strike": 25000,
            "instrument_token": 300,
            "lot_size": 65,
        },
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTY26OCT25000PE",
            "instrument_type": "PE",
            "expiry": next_week_expiry,
            "strike": 25000,
            "instrument_token": 301,
            "lot_size": 65,
        },
    ]
    kite.ltp.side_effect = [
        {"100": {"last_price": 25010.0}},
        {
            "300": {"last_price": 120.0},
            "301": {"last_price": 110.0},
        },
    ]

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(
                api_key="key",
                access_token="token",
                trading_mode="intraday_options",
                instrument_tokens={"NIFTY": 100},
                options_underlyings=["NIFTY"],
                option_expiry_days=14,
                option_expiry_mode="next_week",
                option_strike_step={"NIFTY": 50},
            )
        )

    assert stream.refresh_instrument_tokens() == {
        "NIFTY_CE": 300,
        "NIFTY_PE": 301,
    }


def test_option_quality_gate_rejects_low_premium_volume_and_iv():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "option_min_premium": 25.0,
        "option_max_premium": 150.0,
        "option_min_volume": 500,
        "option_min_oi": 2000,
        "option_iv_min": 0.15,
        "option_iv_max": 0.80,
    }
    bot.option_quote_cache = {
        "NIFTY_CE": {"last_price": 20.0, "volume": 200, "oi": 500, "iv": 0.12}
    }

    allowed, reason = bot._option_quality_gate("NIFTY_CE", "BUY")

    assert allowed is False
    assert "premium" in reason.lower() or "volume" in reason.lower() or "iv" in reason.lower()


def test_intraday_manager_enforces_daily_cap_and_symbol_repeat_guard():
    manager = IntradayManager(account_size=100000, risk_per_trade_pct=1.0)
    manager.daily_max_trades = 1
    manager.daily_max_loss = 250.0

    allowed, reason = manager.can_open_trade("NIFTY_CE", "BUY")
    assert allowed is True
    manager.record_trade_open("NIFTY_CE", "BUY")

    allowed, reason = manager.can_open_trade("NIFTY_CE", "BUY")
    assert allowed is False
    assert "symbol" in reason.lower() or "trade" in reason.lower()

    manager.session_trade_symbols.clear()
    manager.daily_trade_count = 0
    manager.session_reversal_symbols.clear()
    allowed, reason = manager.can_open_trade("NIFTY_PE", "SELL")
    assert allowed is True

    manager.record_trade_open("NIFTY_PE", "SELL")
    manager.record_trade_close("NIFTY_PE", "SIGNAL_REVERSAL", pnl=-500.0)
    allowed, reason = manager.can_open_trade("NIFTY_PE", "SELL")
    assert allowed is False
    assert "reversed" in reason.lower() or "loss" in reason.lower() or "trade" in reason.lower()


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


def test_futures_underlyings_take_priority_over_configured_spot_tokens():
    kite = Mock()
    today = date.today()
    kite.instruments.return_value = [
        {
            "name": "NIFTY",
            "tradingsymbol": "NIFTY26SEP",
            "instrument_type": "FUT",
            "expiry": today + timedelta(days=7),
            "instrument_token": 9001,
            "lot_size": 65,
        }
    ]
    kite.ltp.return_value = {"9001": {"last_price": 25000.0}}

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(
                api_key="key",
                access_token="token",
                instrument_tokens={"NIFTY": 256265},
                futures_underlyings=["NIFTY"],
            )
        )

    assert stream.refresh_instrument_tokens() == {"NIFTY": 9001}
    assert stream.contract_symbols == {"NIFTY": "NIFTY26SEP"}
    kite.instruments.assert_called_once_with("NFO")


def test_place_market_order_uses_selected_nfo_contract():
    kite = Mock()
    kite.TRANSACTION_TYPE_BUY = "BUY"
    kite.TRANSACTION_TYPE_SELL = "SELL"
    kite.VARIETY_REGULAR = "regular"
    kite.EXCHANGE_NFO = "NFO"
    kite.ORDER_TYPE_MARKET = "MARKET"
    kite.PRODUCT_MIS = "MIS"
    kite.VALIDITY_DAY = "DAY"
    kite.place_order.return_value = "order-123"

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(KiteConfig(api_key="key", access_token="token"))
    stream.contract_symbols = {"NIFTY": "NIFTY26SEP"}

    assert stream.place_market_order("NIFTY", "BUY", 65) == "order-123"
    kite.place_order.assert_called_once_with(
        variety="regular",
        exchange="NFO",
        tradingsymbol="NIFTY26SEP",
        transaction_type="BUY",
        quantity=65,
        order_type="MARKET",
        product="MIS",
        validity="DAY",
    )