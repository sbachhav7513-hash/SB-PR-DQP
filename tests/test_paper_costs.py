import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from market_bot.kite_main import KiteTradingBot
from market_bot.paper_costs import (
    DEFAULT_CHARGE_MODEL,
    calculate_order_fees,
    calculate_trade_fees,
)
from market_bot.telegram_control.listener import TelegramCommand
from market_bot.trade_journal import TradeJournal


def test_default_charge_model_counts_entry_and_each_partial_exit_order():
    fees = calculate_trade_fees(
        {
            "action": "BUY",
            "entry": 100.0,
            "entry_quantity": 10,
            "quantity": 10,
            "exit_legs": [
                {"leg_type": "partial", "fill": 120.0, "quantity": 4},
                {"leg_type": "final", "fill": 110.0, "quantity": 6},
            ],
        }
    )

    assert fees["order_count"] == 3
    assert fees["brokerage"] == 60.0
    assert fees["stt"] == 1.71
    assert fees["exchange"] == 0.76
    assert fees["sebi"] == 0.0
    assert fees["stamp"] == 0.03
    assert fees["gst"] == 10.94
    assert fees["total_fees"] == 73.44
    assert fees["fee_model_status"] == "modeled"


def test_min_flat_percentage_brokerage_is_applied_per_executed_order():
    fees = calculate_order_fees(
        [
            {"side": "BUY", "price": 100.0, "quantity": 10},
            {"side": "SELL", "price": 110.0, "quantity": 10},
        ],
        {
            "paper_charge_model": {
                **DEFAULT_CHARGE_MODEL,
                "brokerage_mode": "min_flat_percentage",
            }
        },
    )

    assert fees["brokerage"] == pytest.approx(0.63)
    assert fees["order_count"] == 2


def test_flat_brokerage_mode_can_be_overridden_by_config():
    fees = calculate_order_fees(
        [{"side": "BUY", "price": 1.0, "quantity": 1}],
        {"paper_charge_model": {"brokerage_flat_inr": 7.0}},
    )

    assert fees["brokerage"] == 7.0
    assert fees["brokerage_mode"] == "flat"


def test_invalid_charge_model_and_order_data_fail_explicitly():
    with pytest.raises(ValueError, match="brokerage_mode"):
        calculate_order_fees(
            [{"side": "BUY", "price": 100, "quantity": 1}],
            {"paper_charge_model": {"brokerage_mode": "unsupported"}},
        )
    with pytest.raises(ValueError, match="price"):
        calculate_order_fees([{"side": "BUY", "price": 0, "quantity": 1}])


def test_paper_close_persists_gross_fees_net_and_command_link(tmp_path):
    bot = KiteTradingBot.__new__(KiteTradingBot)
    symbol = "NIFTY_CE"
    trade_journal = TradeJournal(str(tmp_path / "trades.jsonl"))
    trade_journal.log_trade(
        {
            "ticker": symbol,
            "action": "BUY",
            "entry": 100.0,
            "quantity": 1,
        }
    )
    position = {
        "direction": "BUY",
        "entry_price": 100.0,
        "quantity": 1,
        "stop_loss": 90.0,
        "take_profit": 120.0,
    }
    bot.config = {}
    bot.mode = "PAPER"
    bot.live_orders_enabled = False
    bot.paper_trading_enabled = True
    bot.trade_journal = trade_journal
    bot.intraday_manager = SimpleNamespace(
        active_positions={symbol: position},
        contract_specs={symbol: {"multiplier": 1.0, "lot_size": 1}},
        close_position=Mock(
            return_value={
                "pnl_rupees": -5.0,
                "pnl_points": -5.0,
                "duration": 30.0,
                "quantity": 1,
            }
        ),
        record_trade_close=Mock(),
        record_trade_close_after_partial=Mock(),
    )
    bot.option_quote_cache = {}
    bot._select_paper_option_exit_fill = Mock(
        return_value=(95.0, False, False, None)
    )
    bot._record_paper_shadow_actual_exit = Mock()
    bot._active_paper_change_flags = Mock(return_value=[])
    bot._paper_change_enabled = Mock(return_value=False)
    bot._activate_daily_loss_shutdown = Mock()
    bot._ema_reentry_enabled = Mock(return_value=False)
    bot._options_enabled = Mock(return_value=True)
    bot._persist_current_live_risk_state = Mock()
    bot.kite_stream = SimpleNamespace(contract_symbols={})
    bot.telegram_notifier = Mock()
    bot.telegram_notifier.format_close.return_value = {}
    bot.telegram_notifier.build_message.return_value = "closed"
    bot._current_telegram_command = TelegramCommand(
        chat_id="101",
        user_id="202",
        text="/exit 1",
        update_id=7,
        message_timestamp=1790000000,
    )

    assert bot._close_position(symbol, 95.0, "MANUAL_EXIT")

    [trade] = trade_journal.read_trades()
    assert trade["gross_pnl_rupees"] == -5.0
    assert trade["fees"]["order_count"] == 2
    assert trade["fees_rupees"] > 0
    assert trade["after_cost_pnl"] == trade["net_pnl"]
    assert trade["net_pnl"] == round(-5.0 - trade["fees_rupees"], 2)
    assert trade["exit_trigger"] == "human /exit"
    assert trade["exit_command"] == {
        "text": "/exit 1",
        "message_time": trade["exit_trigger_set_time"],
        "chat_id": "101",
    }
