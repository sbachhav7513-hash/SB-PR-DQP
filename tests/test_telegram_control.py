import queue
import threading
import time
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from market_bot.kite_main import KiteTradingBot
from market_bot.trade_journal import TradeJournal
from market_bot.telegram_control.commands import process_telegram_command
from market_bot.telegram_control.listener import (
    TelegramCommand,
    TelegramCommandListener,
    parse_allowed_chat_ids,
)


def _update(update_id, chat_id, text, *, date=None, user_id=None):
    sender_id = user_id if user_id is not None else chat_id
    return {
        "update_id": update_id,
        "message": {
            "date": int(time.time()) if date is None else date,
            "chat": {"id": chat_id},
            "from": {"id": sender_id},
            "text": text,
        },
    }


def _listener(allowed=("101",)):
    return TelegramCommandListener(
        token="not-a-real-token",
        allowed_chat_ids=allowed,
        command_queue=queue.Queue(),
        reply_queue=queue.Queue(),
    )


def test_unauthorized_chat_is_ignored_without_reply_or_queue_entry():
    listener = _listener()

    accepted = listener.handle_update(_update(1, 202, "/pause"))

    assert not accepted
    assert listener._command_queue.empty()
    assert listener._reply_queue.empty()


def test_exit_confirmation_buttons_queue_only_authorized_callbacks():
    listener = _listener()
    callback = {
        "update_id": 2,
        "callback_query": {
            "id": "callback-1",
            "from": {"id": 101},
            "message": {"chat": {"id": 101}},
            "data": "confirm_exit",
        },
    }

    assert listener.handle_update(callback)
    queued = listener._command_queue.get_nowait()
    assert queued.text == "YES"
    assert queued.chat_id == "101"
    assert listener._callback_ack_queue.get_nowait() == "callback-1"

    callback["update_id"] = 3
    callback["callback_query"]["from"] = {"id": 202}
    assert not listener.handle_update(callback)
    assert listener._command_queue.empty()


def test_live_exit_confirmation_reply_has_confirm_and_cancel_buttons(monkeypatch):
    listener = _listener()
    response = Mock()
    response.raise_for_status = Mock()
    post = Mock(return_value=response)
    monkeypatch.setattr("market_bot.telegram_control.listener.requests.post", post)
    listener._reply_queue.put(
        ("101", "Confirm LIVE exit for trade #1 within 30 seconds.")
    )

    listener._send_replies()

    payload = post.call_args.kwargs["data"]
    markup = json.loads(payload["reply_markup"])
    assert [button["text"] for button in markup["inline_keyboard"][0]] == [
        "Confirm",
        "Cancel",
    ]


def test_trade_group_is_excluded_from_command_allowlist():
    allowed_ids = parse_allowed_chat_ids(
        "101,202",
        excluded_chat_ids=("202",),
    )

    assert allowed_ids == {"101"}


def test_updates_older_than_listener_start_are_ignored():
    listener = _listener()

    accepted = listener.handle_update(
        _update(7, 101, "/pause", date=int(listener._started_at) - 1)
    )

    assert not accepted
    assert listener.last_update_id == 7
    assert listener._command_queue.empty()


def test_pause_blocks_entries_but_open_position_stop_loss_still_fires():
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot._telegram_entries_paused = True
    bot.intraday_manager = Mock()
    bot.intraday_manager.can_open_trade = Mock()
    assert bot._can_open_trade_for_signal("NIFTY_CE", "BUY", 80) == (
        False,
        "telegram entries paused",
    )
    bot.intraday_manager.can_open_trade.assert_not_called()

    position = {
        "direction": "BUY",
        "entry_price": 100.0,
        "quantity": 1,
        "stop_loss": 95.0,
        "take_profit": 120.0,
        "trailing_enabled": True,
    }
    manager = SimpleNamespace(
        active_positions={"NIFTY_FUT": position},
        trailing_enabled=True,
        update_trailing_stop=Mock(return_value=None),
        milestone_timebox_expired=Mock(return_value=False),
    )
    bot.intraday_manager = manager
    bot._is_option_dynamic_exit = Mock(return_value=False)
    bot._quote_validated_long_option = Mock(return_value=False)
    bot._close_position = Mock()

    result = bot._check_position_exit("NIFTY_FUT", 94.0)

    assert result == "STOP_LOSS"
    bot._close_position.assert_called_once_with("NIFTY_FUT", 94.0, "STOP_LOSS")


def test_listener_failure_is_retried_without_blocking_main_thread_commands():
    listener = _listener()
    listener._stop_event.wait = lambda _seconds: False
    polls = []

    def poll():
        polls.append(True)
        if len(polls) == 1:
            raise RuntimeError("simulated network failure")
        listener._stop_event.set()
        return []

    listener._poll_updates = poll
    worker = threading.Thread(target=listener._run)
    worker.start()

    command = TelegramCommand(
        chat_id="101",
        user_id="101",
        text="/pause",
        update_id=3,
        message_timestamp=time.time(),
    )
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot._telegram_entries_paused = False
    bot.intraday_manager = SimpleNamespace(active_positions={})
    bot.telegram_command_queue = queue.Queue()
    bot.telegram_reply_queue = queue.Queue()
    bot.telegram_command_queue.put(command)
    bot._process_telegram_commands()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert len(polls) == 2
    assert bot._telegram_entries_paused
    assert bot.telegram_reply_queue.get_nowait() == (
        "101",
        "New entries paused. Open trades: 0. Open trades remain managed.",
    )


def test_commands_are_processed_without_waiting_for_a_market_tick():
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot._telegram_entries_paused = False
    bot.intraday_manager = SimpleNamespace(active_positions={})
    bot._telegram_execution_lock = threading.RLock()
    bot.telegram_command_queue = queue.Queue()
    bot.telegram_reply_queue = queue.Queue()
    bot.telegram_command_queue.put(
        TelegramCommand(
            chat_id="101",
            user_id="101",
            text="/help",
            update_id=4,
            message_timestamp=time.time(),
        )
    )

    bot._process_telegram_commands()

    chat_id, reply = bot.telegram_reply_queue.get_nowait()
    assert chat_id == "101"
    assert reply.startswith("Commands:")


def test_read_only_commands_are_processed_without_market_ticks(tmp_path):
    bot, trade_id, _, _ = _trade_bot(tmp_path)
    bot.intraday_manager.contract_specs = {}
    bot.intraday_manager.MULTIPLIERS = {}
    for update_id, text in enumerate(
        (f"/exit {trade_id}", "/help", "/status"),
        start=10,
    ):
        bot.telegram_command_queue.put(
            TelegramCommand(
                chat_id="101",
                user_id="101",
                text=text,
                update_id=update_id,
                message_timestamp=time.time(),
            )
        )

    bot._process_telegram_commands(read_only_only=True)

    replies = [
        bot.telegram_reply_queue.get_nowait(),
        bot.telegram_reply_queue.get_nowait(),
    ]
    assert [reply[0] for reply in replies] == ["101", "101"]
    assert replies[0][1].startswith("Commands:")
    assert replies[1][1].startswith("State:")
    queued = bot.telegram_command_queue.get_nowait()
    assert queued.text == f"/exit {trade_id}"
    assert bot.trade_journal.read_trades()[0]["status"] == "open"


def test_telegram_trade_ids_are_persisted_and_increment_across_journal_reload(tmp_path):
    journal_path = tmp_path / "trades.jsonl"
    first_journal = TradeJournal(str(journal_path))

    first_id = first_journal.log_trade(
        {"ticker": "NIFTY_CE", "action": "BUY", "entry": 79.0}
    )
    second_id = first_journal.log_trade(
        {"ticker": "NIFTY_PE", "action": "BUY", "entry": 81.0}
    )
    reloaded_journal = TradeJournal(str(journal_path))
    third_id = reloaded_journal.log_trade(
        {"ticker": "BANKNIFTY_CE", "action": "BUY", "entry": 90.0}
    )

    assert (first_id, second_id, third_id) == (1, 2, 3)
    assert [
        trade["telegram_trade_id"] for trade in reloaded_journal.read_trades()
    ] == [1, 2, 3]


def _trade_bot(tmp_path, *, live=False):
    bot = KiteTradingBot.__new__(KiteTradingBot)
    symbol = "NIFTY_CE"
    position = {
        "direction": "BUY",
        "entry_price": 100.0,
        "quantity": 1,
        "stop_loss": 95.0,
        "take_profit": 150.0,
        "trailing_enabled": False,
    }
    journal = TradeJournal(str(tmp_path / "trades.jsonl"))
    trade_id = journal.log_trade(
        {
            "ticker": symbol,
            "action": "BUY",
            "entry": 100.0,
            "stop_loss": 95.0,
            "take_profit": 150.0,
            "quantity": 1,
        }
    )
    bot.trade_journal = journal
    bot.intraday_manager = SimpleNamespace(
        active_positions={symbol: position},
        trailing_enabled=False,
        update_trailing_stop=Mock(return_value=None),
        milestone_timebox_expired=Mock(return_value=False),
    )
    bot.latest_prices = {symbol: 101.0}
    bot.option_quote_cache = {}
    bot.mode = "LIVE" if live else "PAPER"
    bot.live_orders_enabled = live
    bot.telegram_control_live_orders = True
    bot.telegram_command_queue = queue.Queue()
    bot.telegram_reply_queue = queue.Queue()
    bot._telegram_execution_lock = threading.RLock()
    bot._is_option_dynamic_exit = Mock(return_value=False)
    bot._quote_validated_long_option = Mock(return_value=False)
    return bot, trade_id, symbol, position


def _queue_command(bot, text, chat_id="101"):
    bot.telegram_command_queue.put(
        TelegramCommand(
            chat_id=chat_id,
            user_id=chat_id,
            text=text,
            update_id=1,
            message_timestamp=time.time(),
        )
    )
    bot._process_telegram_commands()
    return bot.telegram_reply_queue.get_nowait()[1]


def _close_trade_for_test(bot, symbol, price, reason):
    position = bot.intraday_manager.active_positions.pop(symbol)
    position["manual_exit_price"] = None
    bot.trade_journal.close_trade(symbol, price, position["direction"], reason)


def test_exitat_closes_at_or_above_price_and_journals_manual_target(tmp_path):
    bot, trade_id, symbol, position = _trade_bot(tmp_path)
    bot._close_position = lambda s, price, reason: _close_trade_for_test(
        bot, s, price, reason
    )

    trigger_reply = _queue_command(bot, f"/exitat {trade_id} 105")
    assert "trigger set" in trigger_reply
    assert f"#{trade_id}" in trigger_reply
    assert "from none to 105.00" in trigger_reply
    assert bot._check_position_exit(symbol, 104.99) is None
    assert bot._check_position_exit(symbol, 105.0) == "MANUAL_TARGET"

    trade = bot.trade_journal.read_trades()[0]
    assert trade["exit_source"] == "MANUAL"
    assert trade["exit_reason"] == "MANUAL_TARGET"
    assert trade["manual_exit_price"] is None


def test_exitat_rejects_reached_target_and_cancel_clears_trigger(tmp_path):
    bot, trade_id, _, position = _trade_bot(tmp_path)

    assert "use /exit" in process_telegram_command(
        bot, f"/exitat {trade_id} 101"
    )
    trigger_reply = process_telegram_command(bot, f"/exitat {trade_id} 110")
    assert "trigger set" in trigger_reply
    assert f"#{trade_id}" in trigger_reply
    assert "from none to 110.00" in trigger_reply
    bot.latest_prices.clear()
    cancel_reply = process_telegram_command(bot, f"/cancel {trade_id}")
    assert "trigger cleared" in cancel_reply
    assert f"#{trade_id}" in cancel_reply
    assert "from 110.00 to none" in cancel_reply
    assert position["manual_exit_price"] is None


def test_strategy_stop_and_target_changes_are_audited(tmp_path):
    bot, _, symbol, position = _trade_bot(tmp_path)

    def update_trailing(_symbol, _price):
        position["trailing_stop"] = 102.0
        position["take_profit"] = 155.0
        return 102.0

    bot.intraday_manager.update_trailing_stop = Mock(side_effect=update_trailing)
    assert bot._check_position_exit(symbol, 110.0) is None

    history = bot.trade_journal.read_trades()[0]["risk_modifications"]
    assert {
        (change["field"], change["old_value"], change["new_value"], change["source"])
        for change in history
    } == {
        ("trailing_stop", None, 102.0, "BOT"),
        ("take_profit", 150.0, 155.0, "BOT"),
    }


def test_stop_loss_and_target_prices_must_be_valid_relative_to_ltp(tmp_path):
    bot, trade_id, _, _ = _trade_bot(tmp_path)

    assert "current market price" in process_telegram_command(
        bot, f"/sl {trade_id} 101"
    )
    assert "current LTP" in process_telegram_command(
        bot, f"/target {trade_id} 101"
    )
    target_reply = process_telegram_command(bot, f"/target {trade_id} 120")
    assert "updated" in target_reply
    assert f"#{trade_id}" in target_reply
    assert "150.00 to 120.00" in target_reply
    assert bot.trade_journal.read_trades()[0]["risk_modifications"][0]["field"] == (
        "take_profit"
    )


def test_trailing_stop_wins_before_manual_target_and_clears_trigger(tmp_path):
    bot, trade_id, symbol, position = _trade_bot(tmp_path)
    bot._close_position = lambda s, price, reason: _close_trade_for_test(
        bot, s, price, reason
    )
    assert "trigger set" in _queue_command(bot, f"/exitat {trade_id} 120")
    bot.intraday_manager.update_trailing_stop.return_value = 107.0

    assert bot._check_position_exit(symbol, 106.0) == "TRAILING_STOP"
    trade = bot.trade_journal.read_trades()[0]
    assert trade["reason"] == "TRAILING_STOP"
    assert trade["manual_exit_price"] is None


def test_repeated_exit_on_closed_trade_places_only_one_order(tmp_path):
    bot, trade_id, symbol, _ = _trade_bot(tmp_path, live=True)
    bot.config = {"max_exit_retries": 1}
    bot.kite_stream = SimpleNamespace(
        contract_symbols={},
        cancel_order=Mock(),
        place_market_order=Mock(return_value="exit-order-1"),
        wait_for_order_fill=Mock(return_value={"average_price": 102.0}),
        get_position_quantity=Mock(return_value=0),
    )
    def close_manager_position(*_args):
        bot.intraday_manager.active_positions.pop(symbol)
        return None

    bot.intraday_manager.close_position = Mock(
        side_effect=close_manager_position
    )
    bot.intraday_manager.record_trade_close = Mock()
    bot._persist_current_live_risk_state = Mock()
    bot._activate_daily_loss_shutdown = Mock()
    bot._options_enabled = Mock(return_value=False)
    bot.telegram_notifier = Mock()
    bot.telegram_notifier.format_close.return_value = {"message": "closed"}
    bot.telegram_notifier.build_message.return_value = "closed"

    assert "Confirm LIVE exit" in _queue_command(bot, f"/exit {trade_id}")
    assert "completed" in _queue_command(bot, "YES")
    assert "already closed" in _queue_command(bot, f"/exit {trade_id}")
    bot.kite_stream.place_market_order.assert_called_once_with(
        symbol, "SELL", 1
    )
    trade = bot.trade_journal.read_trades()[0]
    assert trade["exit_source"] == "MANUAL"
    assert trade["exit_reason"] == "MANUAL_EXIT"


def test_stop_loss_force_and_breakeven_requirements_and_modification_history(tmp_path):
    bot, trade_id, _, position = _trade_bot(tmp_path)

    assert "requires the force" in process_telegram_command(
        bot, f"/sl {trade_id} 90"
    )
    stop_reply = process_telegram_command(bot, f"/sl {trade_id} 90 force")
    assert "updated" in stop_reply
    assert f"#{trade_id}" in stop_reply
    assert "95.00 to 90.00" in stop_reply
    assert position["stop_loss"] == 90.0
    bot.latest_prices["NIFTY_CE"] = 100.0
    be_unavailable = process_telegram_command(bot, f"/be {trade_id}")
    assert f"#{trade_id}" in be_unavailable
    assert "Breakeven is available only when LTP is above entry." in be_unavailable

    bot.latest_prices["NIFTY_CE"] = 101.0
    be_updated = process_telegram_command(bot, f"/be {trade_id}")
    assert f"#{trade_id}" in be_updated
    assert "90.00 to 100.00" in be_updated
    trade = bot.trade_journal.read_trades()[0]
    assert trade["stop_loss"] == 100.0
    assert trade["risk_modifications"] == [
        {
            "field": "stop_loss",
            "old_value": 95.0,
            "new_value": 90.0,
            "time": trade["risk_modifications"][0]["time"],
            "source": "MANUAL",
        },
        {
            "field": "stop_loss",
            "old_value": 90.0,
            "new_value": 100.0,
            "time": trade["risk_modifications"][1]["time"],
            "source": "MANUAL",
        },
    ]


@pytest.mark.parametrize("confirmation", [False, True])
def test_live_exit_requires_confirmation_and_expired_confirmation_places_no_order(
    tmp_path, monkeypatch, confirmation
):
    bot, trade_id, _, _ = _trade_bot(tmp_path, live=True)
    order_layer = Mock()
    bot._close_position = order_layer

    prompt = _queue_command(bot, f"/exit {trade_id}")
    assert "Confirm LIVE exit" in prompt
    if confirmation:
        import market_bot.telegram_control.commands as commands

        pending = bot._telegram_pending_exit_confirmation
        monkeypatch.setattr(
            commands.time,
            "monotonic",
            lambda: pending["expires_at"] + 1,
        )
        response = _queue_command(bot, "YES")
        assert "expired" in response.lower() or "no pending" in response.lower()
    else:
        assert bot.intraday_manager.active_positions
    order_layer.assert_not_called()


def test_live_exit_confirmation_is_same_chat_and_executes_once(tmp_path):
    bot, trade_id, symbol, _ = _trade_bot(tmp_path, live=True)
    bot._close_position = lambda s, price, reason: _close_trade_for_test(
        bot, s, price, reason
    )

    assert "Confirm LIVE exit" in _queue_command(bot, f"/exit {trade_id}", "101")
    assert "No pending exit confirmation" in process_telegram_command(
        bot, "YES", chat_id="202"
    )
    assert bot.intraday_manager.active_positions
    assert "completed" in _queue_command(bot, "YES", "101")
    assert not bot.intraday_manager.active_positions
    assert "No pending" in process_telegram_command(bot, "YES", chat_id="101")


def test_live_exit_order_flag_disables_order_placement(tmp_path):
    bot, trade_id, _, _ = _trade_bot(tmp_path, live=True)
    bot.telegram_control_live_orders = False
    order_layer = Mock()
    bot._close_position = order_layer

    _queue_command(bot, f"/exit {trade_id}")
    response = _queue_command(bot, "YES")

    assert "disabled" in response
    order_layer.assert_not_called()


def test_live_risk_commands_are_gated_when_order_control_is_disabled(tmp_path):
    bot, trade_id, _, position = _trade_bot(tmp_path, live=True)
    bot.telegram_control_live_orders = False

    assert "disabled" in process_telegram_command(
        bot, f"/exitat {trade_id} 120"
    )
    assert "disabled" in process_telegram_command(
        bot, f"/target {trade_id} 120"
    )
    assert "manual_exit_price" not in position


def test_live_exit_failure_keeps_trade_open_flagged_and_notifies_error(tmp_path):
    bot, trade_id, symbol, position = _trade_bot(tmp_path, live=True)
    bot.config = {"max_exit_retries": 1}
    bot.kite_stream = SimpleNamespace(
        cancel_order=Mock(),
        place_market_order=Mock(side_effect=RuntimeError("broker rejected order")),
        get_position_quantity=Mock(return_value=1),
    )
    bot.telegram_notifier = Mock()
    bot._place_protective_stop = Mock(return_value=False)
    bot._entries_paused = False
    bot._risk_state_reconciled = True
    bot._close_position(symbol, 101.0, "MANUAL_EXIT")

    assert bot.intraday_manager.active_positions[symbol] is position
    assert position["telegram_exit_failed"]
    assert "broker rejected order" in position["telegram_exit_error"]
    journaled = bot.trade_journal.read_trades()[0]
    assert journaled["status"] == "open"
    assert journaled["telegram_exit_failed"]
    assert any(
        "broker rejected order" in str(call.args[0])
        for call in bot.telegram_notifier.send_message.call_args_list
    )


def test_unauthorized_chat_cannot_enqueue_any_trade_command():
    listener = _listener()
    for update_id, text in enumerate(
        (
            "/exit 1",
            "/exitat 1 105",
            "/cancel 1",
            "/sl 1 95",
            "/be 1",
            "/target 1 120",
        ),
        1,
    ):
        assert not listener.handle_update(_update(update_id, 202, text))
    assert listener._command_queue.empty()
    assert listener._reply_queue.empty()


def test_unknown_and_closed_trade_ids_report_not_found_or_closed(tmp_path):
    bot, trade_id, symbol, _ = _trade_bot(tmp_path)
    assert "not found or already closed" in process_telegram_command(bot, "/exit 999")
    bot.trade_journal.close_trade(symbol, 101.0, "BUY", "TEST")
    assert "already closed" in process_telegram_command(bot, f"/exit {trade_id}")


def test_commands_are_persisted_to_command_log(tmp_path):
    bot, _, _, _ = _trade_bot(tmp_path)

    _queue_command(bot, "/help")

    entries = [
        json.loads(line)
        for line in (tmp_path / "commands.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert entries[0]["text"] == "/help"
    assert entries[0]["chat_id"] == "101"
