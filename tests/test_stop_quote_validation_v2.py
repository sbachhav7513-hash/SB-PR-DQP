from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market_bot.intraday_manager import IntradayManager
from market_bot.kite_main import KiteTradingBot


IST = ZoneInfo("Asia/Kolkata")


def _bot(*, stop=27.135):
    manager = IntradayManager(trailing_enabled=False)
    manager.register_position(
        "INFY_CE",
        "BUY",
        400,
        30.15,
        stop,
        36.18,
        trailing_enabled=False,
    )
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "option_quote_validated_stops_enabled": True,
        "stop_quote_validation_v2": True,
        "stop_quote_bad_tick_drop_pct": 0.15,
        "stop_quote_bad_tick_lookback_seconds": 2.0,
        "stop_quote_bad_tick_confirm_seconds": 3.0,
        "option_quote_max_age_seconds": 60,
        "partial_profit_v2": False,
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.intraday_manager = manager
    bot.option_quote_cache = {}
    bot._close_position_calls = []
    bot._close_position = lambda symbol, price, reason: (
        bot._close_position_calls.append((symbol, price, reason)) or True
    )
    bot._maybe_execute_partial_profit = lambda symbol, position, metrics: False
    bot._is_option_dynamic_exit = lambda position: False
    return bot


def _set_quote(bot, *, timestamp, bid, ask, ltp):
    bot.option_quote_cache["INFY_CE"] = {
        "timestamp": timestamp,
        "bid": bid,
        "ask": ask,
        "last_price": ltp,
    }


def test_infy_nov6_out_of_spread_quote_triggers_stop_at_bid():
    bot = _bot()
    now = datetime.now(IST) - timedelta(seconds=5)
    quotes = (
        (now - timedelta(seconds=50), 27.50, 27.70, 27.70),
        (now - timedelta(seconds=11), 26.85, 26.95, 26.70),
        (now, 26.50, 26.60, 26.50),
    )

    for quote_time, bid, ask, ltp in quotes:
        _set_quote(
            bot,
            timestamp=quote_time,
            bid=bid,
            ask=ask,
            ltp=ltp,
        )
        result = bot._check_position_exit("INFY_CE", ltp)
        if bid <= 27.135:
            assert result == "STOP_LOSS"
            break
        assert result is None

    assert bot._close_position_calls == [("INFY_CE", 26.85, "STOP_LOSS")]


def test_normal_stop_exit_uses_bid():
    bot = _bot(stop=18.04)
    now = datetime.now(IST) - timedelta(seconds=5)
    _set_quote(bot, timestamp=now - timedelta(seconds=1), bid=20.0, ask=20.1, ltp=20.05)
    assert bot._check_position_exit("INFY_CE", 20.05) is None

    _set_quote(bot, timestamp=now, bid=18.0, ask=18.1, ltp=18.05)
    assert bot._check_position_exit("INFY_CE", 18.05) == "STOP_LOSS"
    assert bot._close_position_calls == [("INFY_CE", 18.0, "STOP_LOSS")]


def test_bad_tick_requires_second_below_stop_quote(caplog):
    bot = _bot()
    now = datetime.now(IST) - timedelta(seconds=5)
    _set_quote(bot, timestamp=now - timedelta(seconds=1), bid=30.0, ask=30.2, ltp=30.1)
    assert bot._check_position_exit("INFY_CE", 30.1) is None

    _set_quote(bot, timestamp=now, bid=20.0, ask=20.2, ltp=19.9)
    assert bot._check_position_exit("INFY_CE", 19.9) is None
    assert bot._close_position_calls == []
    assert "reason=suspicious_bid_drop" in caplog.text
    assert bot.intraday_manager.active_positions["INFY_CE"][
        "guarded_exit_quote_count"
    ] == 1

    _set_quote(
        bot,
        timestamp=now + timedelta(seconds=2),
        bid=19.9,
        ask=20.1,
        ltp=20.0,
    )
    assert bot._check_position_exit("INFY_CE", 20.0) == "STOP_LOSS"
    assert bot._close_position_calls == [("INFY_CE", 19.9, "STOP_LOSS")]
    assert "reason=consecutive_bids_below_stop" in caplog.text


def test_bad_tick_guard_expires_and_next_quote_is_evaluated_normally():
    bot = _bot()
    now = datetime.now(IST) - timedelta(seconds=5)
    _set_quote(bot, timestamp=now - timedelta(seconds=1), bid=30.0, ask=30.2, ltp=30.1)
    assert bot._check_position_exit("INFY_CE", 30.1) is None

    _set_quote(bot, timestamp=now, bid=20.0, ask=20.2, ltp=19.9)
    assert bot._check_position_exit("INFY_CE", 19.9) is None

    _set_quote(
        bot,
        timestamp=now + timedelta(seconds=4),
        bid=19.0,
        ask=19.2,
        ltp=19.1,
    )
    assert bot._check_position_exit("INFY_CE", 19.1) == "STOP_LOSS"
    assert bot._close_position_calls == [("INFY_CE", 19.0, "STOP_LOSS")]


def test_stale_exit_quote_is_logged_and_does_not_close(caplog):
    bot = _bot()
    stale = datetime.now(IST) - timedelta(seconds=61)
    _set_quote(bot, timestamp=stale, bid=20.0, ask=20.2, ltp=20.1)

    assert bot._check_position_exit("INFY_CE", 20.1) is None
    assert bot._close_position_calls == []
    assert "reason=stale_quote" in caplog.text
    assert "contract=INFY_CE" in caplog.text


def test_entry_validity_keeps_ltp_within_spread_rule():
    bot = _bot()
    now = datetime.now(IST)
    quote = {"timestamp": now, "bid": 26.85, "ask": 26.95, "last_price": 26.70}

    assert bot._option_quote_metrics(quote)["valid"] is False
    assert bot._option_exit_quote_metrics(quote)["exit_valid"] is True


def test_disabling_v2_restores_existing_strict_exit_quote_validation():
    bot = _bot()
    bot.config["stop_quote_validation_v2"] = False
    now = datetime.now(IST)
    _set_quote(bot, timestamp=now, bid=26.85, ask=26.95, ltp=26.70)

    assert bot._check_position_exit("INFY_CE", 26.70) is None
    assert bot._close_position_calls == []


def test_forced_exit_uses_valid_bid_and_audits_fallback(caplog):
    bot = _bot()
    position = bot.intraday_manager.active_positions["INFY_CE"]
    now = datetime.now(IST) - timedelta(seconds=5)
    out_of_spread = {
        "timestamp": now,
        "bid": 26.85,
        "ask": 26.95,
        "last_price": 26.70,
    }
    assert bot._select_paper_option_exit_fill(
        "INFY_CE", position, out_of_spread, 30.0, "MARKET_CLOSE_FORCED_EXIT"
    ) == (26.85, True, False, None)

    stale = {**out_of_spread, "timestamp": now - timedelta(seconds=61)}
    assert bot._select_paper_option_exit_fill(
        "INFY_CE", position, stale, 30.0, "MARKET_CLOSE_FORCED_EXIT"
    ) == (30.0, False, True, "stale_quote")
    assert "FORCED_EXIT_FALLBACK" in caplog.text
    assert "fallback_price=30.0" in caplog.text
