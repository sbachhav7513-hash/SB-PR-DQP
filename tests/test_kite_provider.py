import calendar
import os
import time
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock, call, patch
from zoneinfo import ZoneInfo

import pytest

from market_bot.intraday_manager import IntradayManager
from market_bot.kite_main import KiteTradingBot
from market_bot.kite_provider import KiteConfig, KiteMarketStream, Tick


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
        stream._select_current_futures = Mock(
            side_effect=AssertionError("futures must stay disabled in options mode")
        )

    assert stream.refresh_instrument_tokens() == {
        "NIFTY": 100,
        "NIFTY_CE": 200,
        "NIFTY_PE": 201,
    }
    stream._select_current_futures.assert_not_called()
    assert stream.contract_symbols == {
        "NIFTY_CE": "NIFTY26SEP25000CE",
        "NIFTY_PE": "NIFTY26SEP25000PE",
    }
    assert stream.contract_specs["NIFTY_CE"] == {"lot_size": 65, "multiplier": 1}


def test_options_lookahead_includes_expiry_at_calendar_month_end():
    kite = Mock()
    today = date.today()
    month_end = today.replace(
        day=calendar.monthrange(today.year, today.month)[1]
    )
    kite.instruments.return_value = [
        {
            "name": "NIFTY",
            "tradingsymbol": f"NIFTY{month_end:%d}25000CE",
            "instrument_type": "CE",
            "expiry": month_end,
            "strike": 25000,
            "instrument_token": 200,
            "lot_size": 65,
        },
        {
            "name": "NIFTY",
            "tradingsymbol": f"NIFTY{month_end:%d}25000PE",
            "instrument_type": "PE",
            "expiry": month_end,
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
                option_expiry_days=0,
                option_strike_step={"NIFTY": 50},
            )
        )

    resolved = stream.refresh_instrument_tokens()

    assert resolved == {
        "NIFTY": 100,
        "NIFTY_CE": 200,
        "NIFTY_PE": 201,
    }


def test_stop_disables_retries_before_closing_stream():
    with patch("market_bot.kite_provider.KiteConnect"), patch(
        "market_bot.kite_provider.KiteTicker"
    ) as ticker_factory:
        stream = KiteMarketStream(KiteConfig(api_key="key", access_token="token"))

    stream.stop()

    assert stream._stopping is True
    assert ticker_factory.return_value.method_calls[:2] == [
        call.stop_retry(),
        call.close(),
    ]


def test_on_ticks_drops_non_positive_prices_before_callback():
    callback = Mock()
    with patch("market_bot.kite_provider.KiteConnect"), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(api_key="key", access_token="token"),
            on_tick_callback=callback,
        )

    stream.on_ticks(
        None,
        [{"instrument_token": 100, "timestamp": 1700000000, "last_price": 0}],
    )

    callback.assert_not_called()


def test_refresh_instrument_tokens_combines_futures_and_options():
    kite = Mock()

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(
                api_key="key",
                access_token="token",
                trading_mode="intraday_both",
                instrument_tokens={"NIFTY": 100},
                futures_underlyings=["NIFTY"],
                options_underlyings=["NIFTY"],
            )
        )

    stream._select_current_futures = Mock(return_value={"NIFTY": 300})
    stream._select_current_options = Mock(return_value={"NIFTY_CE": 200, "NIFTY_PE": 201})
    stream.contract_specs = {"NIFTY": {"lot_size": 75, "multiplier": 1}}
    stream.contract_symbols = {"NIFTY": "NIFTY26SEPFUT"}

    resolved = stream.refresh_instrument_tokens()

    assert resolved == {"NIFTY": 300, "NIFTY_CE": 200, "NIFTY_PE": 201}
    assert stream.config.instrument_tokens == resolved
    stream._select_current_options.assert_called_once()


def test_buy_uses_ce_and_sell_uses_pe_for_underlying():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "instrument_tokens": {"NIFTY_CE": 200, "NIFTY_PE": 201},
    }

    assert bot._preferred_option_symbol("NIFTY", "BUY") == "NIFTY_CE"
    assert bot._preferred_option_symbol("NIFTY", "SELL") == "NIFTY_PE"
    assert bot._preferred_option_symbol("NIFTY", "HOLD") is None


def test_bearish_option_signal_buys_pe_instead_of_shorting_it():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "instrument_tokens": {"NIFTY_CE": 200, "NIFTY_PE": 201},
    }

    assert bot._option_trade_action("NIFTY_CE", "BUY") == "BUY"
    assert bot._option_trade_action("NIFTY_PE", "SELL") == "BUY"
    assert bot._option_trade_action("NIFTY_CE", "SELL") == "HOLD"
    assert bot._option_trade_action("NIFTY_PE", "BUY") == "HOLD"


def test_futures_sell_action_is_unchanged_in_both_mode():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"trading_mode": "intraday_both"}

    assert bot._option_trade_action("NIFTY", "SELL") == "SELL"


def test_option_selection_does_not_fallback_to_the_opposite_leg():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "instrument_tokens": {"NIFTY_CE": 200},
    }

    assert bot._preferred_option_symbol("NIFTY", "SELL") is None
    assert bot._option_leg_is_active("NIFTY_CE", "SELL") is False


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
        "NIFTY": 100,
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
        "NIFTY_CE": {
            "last_price": 20.0,
            "volume": 200,
            "oi": 500,
            "iv": 0.12,
            "timestamp": datetime.now().astimezone(),
        }
    }

    allowed, reason = bot._option_quality_gate("NIFTY_CE", "BUY")

    assert allowed is False
    assert "premium" in reason.lower() or "volume" in reason.lower() or "iv" in reason.lower()


def test_option_quality_gate_allows_quotes_without_unavailable_iv_or_oi():
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
        "NIFTY_CE": {
            "last_price": 80.0,
            "volume": 1000,
            "timestamp": datetime.now().astimezone(),
        }
    }

    allowed, reason = bot._option_quality_gate("NIFTY_CE", "BUY")

    assert allowed is True
    assert reason == "OK"


def test_option_quality_gate_rejects_expiry_day_risk():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "avoid_option_expiry_day": True,
    }
    bot.option_quote_cache = {
        "NIFTY_CE": {
            "last_price": 80.0,
            "volume": 1000,
            "timestamp": datetime.now().astimezone(),
        }
    }
    bot.kite_stream = Mock()
    bot.kite_stream.contract_expiries = {"NIFTY_CE": date.today()}

    allowed, reason = bot._option_quality_gate("NIFTY_CE", "BUY")

    assert allowed is False
    assert reason == "option expiry-day risk"


def test_option_quality_gate_requires_fresh_timestamped_quotes_for_ce_and_pe():
    for symbol, signal in (("NIFTY_CE", "BUY"), ("NIFTY_PE", "SELL")):
        bot = object.__new__(KiteTradingBot)
        bot.config = {"trading_mode": "intraday_options"}
        bot.option_quote_cache = {
            symbol: {
                "last_price": 80.0,
                "volume": 1000,
                "timestamp": datetime.now().astimezone() - timedelta(seconds=61),
            }
        }

        allowed, reason = bot._option_quality_gate(symbol, signal)
        assert allowed is False
        assert "stale" in reason

        bot.option_quote_cache[symbol].pop("timestamp")
        allowed, reason = bot._option_quality_gate(symbol, signal)
        assert allowed is False
        assert "timestamp unavailable" in reason


def test_option_quality_gate_uses_softer_strong_signal_floors_for_ce_and_pe():
    for symbol, signal in (("NIFTY_CE", "BUY"), ("NIFTY_PE", "SELL")):
        bot = object.__new__(KiteTradingBot)
        bot.config = {
            "trading_mode": "intraday_options",
            "option_min_premium": 10.0,
            "option_min_volume": 1000,
            "option_min_oi": 1000,
        }
        bot.option_quote_cache = {
            symbol: {
                "last_price": 6.0,
                "volume": 650,
                "oi": 650,
                "timestamp": datetime.now().astimezone(),
            }
        }

        allowed, reason = bot._option_quality_gate(symbol, signal, score=81)
        assert allowed is False
        assert "premium" in reason

        allowed, reason = bot._option_quality_gate(symbol, signal, score=82)
        assert allowed is True
        assert reason == "OK"


def test_option_quality_gate_rejects_invalid_or_unavailable_quotes():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"trading_mode": "intraday_options"}
    bot.option_quote_cache = {}
    bot.latest_prices = {"NIFTY_CE": 100.0}

    allowed, reason = bot._option_quality_gate("NIFTY_CE", "BUY")
    assert allowed is False
    assert reason == "option quote unavailable"

    bot.option_quote_cache["NIFTY_CE"] = {
        "last_price": float("nan"),
        "volume": 1000,
        "timestamp": datetime.now().astimezone(),
    }
    allowed, reason = bot._option_quality_gate("NIFTY_CE", "BUY")
    assert allowed is False
    assert reason == "invalid option quote"


def test_on_tick_stores_timestamp_required_by_option_quality_gate():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"trading_mode": "intraday_options"}
    bot.symbol_map = {101: "NIFTY_CE"}
    bot.latest_prices = {}
    bot.option_quote_cache = {}
    bot.intraday_manager = Mock()
    bot.intraday_manager.should_exit_all_positions.return_value = False
    bot._check_position_exit = Mock()
    bot.bar_builder = Mock()
    timestamp = datetime.now().astimezone()

    bot._on_tick(Tick(101, timestamp, 80.0, volume=1000))

    assert bot.option_quote_cache["NIFTY_CE"]["timestamp"] == timestamp
    assert bot._option_quality_gate("NIFTY_CE", "BUY") == (True, "OK")


def test_intraday_manager_allows_multiple_trades_but_blocks_symbol_repeats():
    manager = IntradayManager(account_size=100000, risk_per_trade_pct=1.0)
    manager.daily_max_loss = 250.0

    allowed, reason = manager.can_open_trade("NIFTY_CE", "BUY")
    assert allowed is True
    manager.record_trade_open("NIFTY_CE", "BUY")

    allowed, reason = manager.can_open_trade("NIFTY_CE", "BUY")
    assert allowed is False
    assert "symbol" in reason.lower() or "trade" in reason.lower()

    manager.session_trade_symbols.clear()
    manager.session_reversal_symbols.clear()
    allowed, reason = manager.can_open_trade("NIFTY_PE", "SELL")
    assert allowed is True

    manager.record_trade_open("BANKNIFTY_CE", "BUY")
    allowed, reason = manager.can_open_trade("FINNIFTY_CE", "BUY")
    assert allowed is True

    manager.record_trade_open("NIFTY_PE", "SELL")
    manager.record_trade_close("NIFTY_PE", "SIGNAL_REVERSAL", pnl=-500.0)
    allowed, reason = manager.can_open_trade("NIFTY_PE", "SELL")
    assert allowed is False
    assert "reversed" in reason.lower() or "loss" in reason.lower() or "trade" in reason.lower()


def test_option_position_size_uses_contract_lots_and_respects_risk_budget():
    manager = IntradayManager(account_size=100000, risk_per_trade_pct=1.0)
    manager.set_contract_specs({"NIFTY_CE": {"lot_size": 65, "multiplier": 1}})

    assert manager.calculate_option_size(
        "NIFTY_CE", premium=10.0, premium_stop_pct=0.35
    ) == 260
    assert manager.calculate_option_size(
        "NIFTY_CE", premium=100.0, premium_stop_pct=0.35
    ) == 0


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


def test_on_ticks_uses_kite_exchange_timestamp_and_volume_fields():
    kite = Mock()

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(api_key="key", access_token="token")
        )

    callback = Mock()
    stream.on_tick_callback = callback
    exchange_epoch = datetime(2026, 9, 16, 8, 40, tzinfo=timezone.utc).timestamp()
    exchange_timestamp = datetime.fromtimestamp(exchange_epoch)

    stream.on_ticks(
        None,
        [
            {
                "instrument_token": 123,
                "exchange_timestamp": exchange_timestamp,
                "last_price": 100.0,
                "volume_traded": 42,
            }
        ],
    )

    tick = callback.call_args.args[0]
    assert tick.timestamp == datetime.fromtimestamp(
        exchange_epoch, tz=timezone.utc
    ).astimezone(tick.timestamp.tzinfo)
    assert tick.volume == 42


def test_naive_kite_timestamp_normalizes_from_host_local_time():
    exchange_epoch = datetime(
        2026, 10, 5, 4, 50, tzinfo=timezone.utc
    ).timestamp()
    raw_timestamp = datetime.fromtimestamp(exchange_epoch)

    normalized = KiteMarketStream._normalize_exchange_timestamp(raw_timestamp)

    assert normalized == datetime.fromtimestamp(
        exchange_epoch, tz=ZoneInfo("Asia/Kolkata")
    )


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="requires POSIX timezone control")
def test_naive_kite_timestamp_is_converted_from_utc_host_timezone():
    previous_timezone = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "UTC"
        time.tzset()
        exchange_epoch = datetime(
            2026, 10, 5, 4, 50, tzinfo=timezone.utc
        ).timestamp()
        raw_timestamp = datetime.fromtimestamp(exchange_epoch)

        normalized = KiteMarketStream._normalize_exchange_timestamp(raw_timestamp)

        assert normalized == datetime.fromtimestamp(
            exchange_epoch, tz=timezone.utc
        ).astimezone(normalized.tzinfo)
    finally:
        if previous_timezone is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous_timezone
        time.tzset()


def test_on_ticks_drops_implausible_epoch_exchange_timestamp():
    kite = Mock()

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(api_key="key", access_token="token")
        )

    callback = Mock()
    stream.on_tick_callback = callback
    stream.on_ticks(
        None,
        [{"instrument_token": 123, "exchange_timestamp": 0, "last_price": 100.0}],
    )

    callback.assert_not_called()


def test_on_ticks_falls_back_to_valid_timestamp_for_epoch_exchange_timestamp():
    kite = Mock()

    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(
            KiteConfig(api_key="key", access_token="token")
        )

    callback = Mock()
    stream.on_tick_callback = callback
    fallback_timestamp = datetime(2026, 10, 7, 9, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    stream.on_ticks(
        None,
        [
            {
                "instrument_token": 123,
                "exchange_timestamp": datetime(1970, 1, 1),
                "timestamp": fallback_timestamp,
                "last_price": 100.0,
            }
        ],
    )

    tick = callback.call_args.args[0]
    assert tick.timestamp == fallback_timestamp


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


def test_modify_protective_stop_rounds_trigger_to_contract_tick():
    stream = object.__new__(KiteMarketStream)
    stream.kite = Mock()
    stream.kite.VARIETY_REGULAR = "regular"
    stream.contract_tick_sizes = {"NIFTY_CE": 0.05}

    stream.modify_protective_stop_order(
        "NIFTY_CE", "BUY", "stop-123", 100.03
    )

    stream.kite.modify_order.assert_called_once_with(
        variety="regular",
        order_id="stop-123",
        trigger_price=100.0,
    )


def test_wait_for_order_fill_returns_verified_execution_details():
    kite = Mock()
    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(KiteConfig(api_key="key", access_token="token"))

    kite.order_history.return_value = [
        {
            "status": "COMPLETE",
            "filled_quantity": 65,
            "average_price": 123.45,
        }
    ]

    assert stream.wait_for_order_fill("order-123", 65) == {
        "order_id": "order-123",
        "status": "COMPLETE",
        "filled_quantity": 65,
        "average_price": 123.45,
    }


def test_wait_for_order_fill_rejects_broker_rejection():
    kite = Mock()
    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(KiteConfig(api_key="key", access_token="token"))

    kite.order_history.return_value = [
        {"status": "REJECTED", "status_message": "Insufficient margin"}
    ]

    try:
        stream.wait_for_order_fill("order-123", 65)
    except RuntimeError as exc:
        assert "Insufficient margin" in str(exc)
    else:
        raise AssertionError("Expected broker rejection to abort the entry")


def test_assert_flat_account_rejects_unmanaged_positions():
    kite = Mock()
    with patch("market_bot.kite_provider.KiteConnect", return_value=kite), patch(
        "market_bot.kite_provider.KiteTicker"
    ):
        stream = KiteMarketStream(KiteConfig(api_key="key", access_token="token"))

    kite.positions.return_value = {
        "net": [{"tradingsymbol": "NIFTY26SEP", "quantity": 65}]
    }

    try:
        stream.assert_flat_account()
    except RuntimeError as exc:
        assert "NIFTY26SEP" in str(exc)
    else:
        raise AssertionError("Expected startup to reject unmanaged positions")