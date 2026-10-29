from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from market_bot.intraday_manager import IntradayManager
from market_bot.kite_main import KiteTradingBot
from market_bot.strategy_config import strategy_config_hash


IST = ZoneInfo("Asia/Kolkata")


def _quote(timestamp, *, bid, ask, ltp):
    return {
        "timestamp": timestamp,
        "bid": bid,
        "ask": ask,
        "last_price": ltp,
    }


def _bot_with_infY_position():
    manager = IntradayManager()
    manager.register_position(
        "INFY_CE",
        "BUY",
        1,
        18.50,
        18.04,
        22.20,
        trailing_enabled=False,
    )
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "option_quote_validated_stops_enabled": True,
        "option_quote_max_age_seconds": 60,
    }
    bot.intraday_manager = manager
    bot.option_quote_cache = {}
    bot._close_position = Mock()
    return bot


def test_infY_out_of_spread_quote_does_not_trigger_option_stop():
    bot = _bot_with_infY_position()
    now = datetime.now(IST)
    bot.option_quote_cache["INFY_CE"] = _quote(
        now, bid=18.20, ask=18.25, ltp=18.05
    )

    assert bot._check_position_exit("INFY_CE", 18.05) is None
    bot._close_position.assert_not_called()


def test_fresh_valid_bid_triggers_stop_and_is_the_paper_exit_price():
    bot = _bot_with_infY_position()
    now = datetime.now(IST)
    bot.option_quote_cache["INFY_CE"] = _quote(
        now, bid=18.00, ask=18.10, ltp=18.05
    )

    assert bot._check_position_exit("INFY_CE", 18.05) == "STOP_LOSS"
    bot._close_position.assert_called_once_with("INFY_CE", 18.00, "STOP_LOSS")


def test_stale_stop_quote_holds_once_then_exits_at_last_valid_bid():
    bot = _bot_with_infY_position()
    now = datetime.now(IST)
    bot.option_quote_cache["INFY_CE"] = _quote(
        now, bid=18.20, ask=18.30, ltp=18.25
    )
    assert bot._check_position_exit("INFY_CE", 18.25) is None

    stale_quote_time = now - timedelta(seconds=61)
    bot.option_quote_cache["INFY_CE"] = _quote(
        stale_quote_time, bid=18.00, ask=18.10, ltp=18.05
    )
    assert bot._check_position_exit("INFY_CE", 18.05) is None
    bot._close_position.assert_not_called()

    bot.option_quote_cache["INFY_CE"] = _quote(
        stale_quote_time,
        bid=18.10,
        ask=18.20,
        ltp=18.15,
    )
    assert bot._check_position_exit("INFY_CE", 18.15) == "feed_failure_exit"
    bot._close_position.assert_called_once_with(
        "INFY_CE", 18.20, "feed_failure_exit"
    )


def test_ema_reentry_is_cancelled_when_option_premium_makes_new_low():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "option_quote_validated_stops_enabled": True,
        "option_quote_max_age_seconds": 60,
    }
    now = datetime.now(IST)
    bot.option_quote_cache = {
        "INFY_CE": _quote(now, bid=17.95, ask=18.05, ltp=17.99)
    }
    bot.trade_journal = Mock()
    bot.decision_journal = Mock()
    state = {
        "original_trade_id": "infy-stop-1",
        "stop_time": now - timedelta(minutes=5),
        "stop_out_low": 18.00,
        "status": "observing",
    }

    assert bot._ema_reentry_premium_made_new_low("INFY_CE", state) is True
    assert state["status"] == "cancelled"
    assert state["outcome"] == "PREMIUM_NEW_LOW"
    bot.trade_journal.annotate_trade.assert_called_once_with(
        "INFY_CE",
        {
            "ema_reentry_outcome": "PREMIUM_NEW_LOW",
            "ema_reentry_new_low": 17.99,
        },
        action="BUY",
    )
    logged = bot.decision_journal.log_decision.call_args.args[0]
    assert logged["ema_reentry_event"] == "CANCELLED_NEW_LOW"
    assert logged["route"] == "ema_reentry"


def test_paper_option_entry_uses_ask_without_changing_ltp_sizing():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "entry_cutoff_minutes_before_close": 0,
        "option_quote_validated_stops_enabled": True,
        "option_premium_stop_pct": 0.10,
        "option_premium_target_pct": 0.20,
        "option_max_risk_per_lot_pct": 10.0,
        "option_min_lots": 1,
        "option_max_lots": 3,
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.latest_prices = {"INFY_CE": 18.25}
    bot.option_quote_cache = {
        "INFY_CE": _quote(
            datetime.now(IST), bid=18.20, ask=18.30, ltp=18.25
        )
    }
    manager = IntradayManager()
    manager.set_contract_specs(
        {"INFY_CE": {"lot_size": 1, "multiplier": 1}}
    )
    bot.intraday_manager = manager
    bot.trade_journal = Mock()
    bot.trade_journal.get_open_trade.return_value = None
    bot.telegram_notifier = Mock()
    bot.telegram_notifier.format_trade.side_effect = lambda **fields: {
        "ticker": "INFY_CE",
        "entry": fields["entry"],
        "stop_loss": fields["stop_loss"],
        "take_profit": fields["take_profit"],
    }
    bot.kite_stream = SimpleNamespace(contract_symbols={})
    bot._entry_cutoff_reason = Mock(return_value=None)
    bot._live_entry_allowed = Mock(return_value=True)
    bot._can_open_trade_for_signal = Mock(return_value=(True, "OK"))
    bot._options_enabled = Mock(return_value=True)
    bot._option_adaptive_exit_enabled = Mock(return_value=False)
    bot._staged_option_targets_enabled = Mock(return_value=False)
    bot._option_entry_target_pct = Mock(return_value=0.20)
    bot._calculate_option_quantity = Mock(return_value=1)
    bot._option_target_increment = Mock(return_value=0.10)
    bot._entry_score_floor = Mock(return_value=70)
    bot._entry_risk_cap = Mock(return_value=1000.0)
    bot._persist_current_live_risk_state = Mock()

    assert bot._handle_buy_signal("INFY_CE", 18.25, 80) == "trade_opened"

    position = manager.active_positions["INFY_CE"]
    assert position["entry_price"] == 18.30
    assert position["stop_loss"] == 18.30 * 0.9
    assert position["take_profit"] == 18.30 * 1.2
    bot._calculate_option_quantity.assert_called_once_with(
        "INFY_CE", 18.25, 0.10
    )
    logged_trade = bot.trade_journal.log_trade.call_args.args[0]
    assert logged_trade["entry_quote_bid"] == 18.20
    assert logged_trade["entry_quote_ask"] == 18.30
    assert logged_trade["entry_quote_ltp"] == 18.25
    assert logged_trade["entry_fill_source"] == "best_ask"


def test_strategy_config_version_produces_a_new_hash():
    config_v1 = {
        "ema_reentry_enabled": True,
        "option_quote_max_age_seconds": 60,
    }
    config_v2 = {
        **config_v1,
        "strategy_config_version": "v2",
        "option_quote_validated_stops_enabled": True,
    }

    assert strategy_config_hash(config_v2) != strategy_config_hash(config_v1)


def test_synthetic_stop_disconnect_warning_identifies_unprotected_options():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"option_quote_validated_stops_enabled": True}
    bot.live_orders_enabled = True
    bot.intraday_manager = SimpleNamespace(
        active_positions={
            "INFY_CE": {"direction": "BUY", "protection_order_id": None}
        }
    )
    bot.telegram_notifier = Mock()

    bot._on_connection_change(False, "stream disconnected")

    assert bot._entries_paused is True
    message = bot.telegram_notifier.send_message.call_args.args[0]
    assert "no broker-side stop" in message
    assert "INFY_CE" in message


def test_synthetic_stop_target_updates_do_not_modify_broker_stop():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"option_quote_validated_stops_enabled": True}
    bot.live_orders_enabled = True
    bot.kite_stream = Mock()
    bot.trade_journal = Mock()
    bot.telegram_notifier = Mock()
    position = {
        "direction": "BUY",
        "take_profit": 22.20,
        "target_stage": 1,
        "milestone_reached_pct": 0.1,
        "milestone_started_at": datetime.now(IST),
        "current_signal_score": 80,
        "decision_window_minutes": 5,
    }

    assert bot._publish_target_update("INFY_CE", position, 18.00) is True

    bot.kite_stream.modify_protective_stop_order.assert_not_called()
    bot.trade_journal.update_open_trade.assert_called_once()
