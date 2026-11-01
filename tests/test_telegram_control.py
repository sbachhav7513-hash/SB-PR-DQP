import queue
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

from market_bot.kite_main import KiteTradingBot
from market_bot.trade_journal import TradeJournal
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
