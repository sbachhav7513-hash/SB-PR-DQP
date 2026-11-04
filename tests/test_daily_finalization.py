import logging
import threading
import time
from datetime import datetime, time as time_type
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import market_bot.kite_main as kite_main
from market_bot.kite_main import KiteTradingBot


IST = ZoneInfo("Asia/Kolkata")


def _bot(tmp_path):
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot._telegram_execution_lock = threading.RLock()
    bot.intraday_manager = SimpleNamespace(
        get_all_open_positions=lambda: {},
        MARKET_CLOSE=time_type(15, 30),
    )
    bot._handle_market_close_exit = Mock()
    bot.live_orders_enabled = False
    bot.telegram_notifier = SimpleNamespace(
        send_daily_summary=Mock(return_value=True),
        send_message=Mock(return_value=True),
    )
    bot._ema_reentry_states = {}
    bot.trade_journal = SimpleNamespace(
        read_trades=lambda: [],
        annotate_trade=Mock(),
    )
    bot.kite_stream = SimpleNamespace(stop=Mock())
    bot.decision_journal = SimpleNamespace(
        flush_decisions=Mock(return_value=True),
    )
    bot.stop_reentry_journal = None
    bot._stop_event_check_state = {}
    bot.paper_trading_dir = str(tmp_path)
    bot.last_daily_summary_date = None
    bot._run_weekly_report_if_due = Mock()
    bot._finalization_attempts = 0
    bot._next_finalization_attempt_at = 0.0
    bot._finalization_complete = False
    return bot


def _write_report(path):
    def write(*_args, **_kwargs):
        path.write_text("written", encoding="utf-8")
        return path

    return write


def test_report_write_failure_returns_failure_and_can_retry(tmp_path, monkeypatch, caplog):
    bot = _bot(tmp_path)
    summary_path = tmp_path / "daily_summary.parquet"
    review_path = tmp_path / "daily_review.md"
    calls = []

    def write_summary(*_args, **_kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise OSError("disk unavailable")
        summary_path.write_text("written", encoding="utf-8")
        return summary_path

    summary_write = Mock(side_effect=write_summary)
    monkeypatch.setattr(kite_main, "write_daily_summary", summary_write)
    monkeypatch.setattr(kite_main, "write_daily_review", _write_report(review_path))
    now = datetime(2026, 11, 3, 15, 30, tzinfo=IST)

    with caplog.at_level(logging.ERROR):
        assert not bot._finalize_daily_session(now)
    assert bot._finalize_daily_session(now)

    assert summary_write.call_count == 2
    assert bot.telegram_notifier.send_daily_summary.call_count == 1
    assert "Daily finalization failed" in caplog.text
    assert "OSError: disk unavailable" in caplog.text


def test_retries_stop_after_ten_retries_and_log_final_error(tmp_path, caplog):
    bot = _bot(tmp_path)
    bot._finalize_daily_session = Mock(return_value=False)
    now = datetime(2026, 11, 3, 15, 30, tzinfo=IST)

    with caplog.at_level(logging.ERROR):
        for attempt in range(11):
            bot._attempt_daily_finalization(now, attempt * 60.0)

    assert bot._finalize_daily_session.call_count == 11
    assert bot._finalization_attempts == 11
    assert "Daily finalization failed after 10 retries" in caplog.text
    assert bot._next_finalization_attempt_at == 600.0


def test_shutdown_after_market_close_attempts_finalization_within_budget(tmp_path):
    bot = _bot(tmp_path)
    called = []

    def finalize(now):
        called.append((threading.current_thread().name, now))
        return True

    bot._finalize_daily_session = finalize
    now = datetime(2026, 11, 3, 15, 45, tzinfo=IST)
    started = time.monotonic()

    assert bot._attempt_shutdown_finalization(now)

    assert time.monotonic() - started < 15
    assert called == [("daily-finalization-shutdown", now)]
    assert bot._finalization_complete


def test_finalization_logs_steps_in_order(tmp_path, monkeypatch, caplog):
    bot = _bot(tmp_path)
    summary_path = tmp_path / "daily_summary.parquet"
    review_path = tmp_path / "daily_review.md"
    monkeypatch.setattr(kite_main, "write_daily_summary", _write_report(summary_path))
    monkeypatch.setattr(kite_main, "write_daily_review", _write_report(review_path))
    now = datetime(2026, 11, 3, 15, 30, tzinfo=IST)
    expected = [
        "Daily finalization started",
        "Daily finalization exits done",
        "Daily finalization no open positions",
        "Daily finalization stream stopped",
        "Daily finalization journals flushed",
        f"Daily finalization summary written: {summary_path}",
        f"Daily finalization review written: {review_path}",
        "Daily finalization Telegram queued",
    ]

    with caplog.at_level(logging.INFO):
        assert bot._finalize_daily_session(now)

    lines = [record.getMessage() for record in caplog.records]
    indexes = [next(i for i, line in enumerate(lines) if line == step) for step in expected]
    assert indexes == sorted(indexes)
    assert bot.decision_journal.flush_decisions.call_args_list[0].kwargs == {
        "timeout": 20.0,
        "compact_final_hour": True,
    }
