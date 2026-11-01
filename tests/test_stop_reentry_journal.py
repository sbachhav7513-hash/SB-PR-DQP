import csv
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market_bot.intraday_manager import IntradayManager
from market_bot.stop_reentry_journal import (
    STOP_EVENT_COLUMNS,
    StopReentryJournal,
    summarize_stop_events,
)
from market_bot.strategy_config import strategy_config_hash
from market_bot.weekly_report import write_daily_review, write_daily_summary


IST = ZoneInfo("Asia/Kolkata")


def _read_rows(path):
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _snapshot(
    *,
    timestamp,
    ticker,
    score,
    outcome,
    signal="BUY",
    reentry_opened=False,
):
    return {
        "timestamp": timestamp,
        "bar_time": timestamp,
        "ticker": ticker,
        "signal": signal,
        "score": score,
        "outcome": outcome,
        "reentry_opened": reentry_opened,
        "config": {
            "stop_reentry_enabled": True,
            "stop_reentry_min_score": 75,
            "stop_reentry_cooldown_minutes": 15,
            "ema_reentry_enabled": True,
            "trading_mode": "intraday_options",
            "min_entry_score": 70,
            "account_size": 100000,
            "max_open_risk_pct": 4,
        },
        "manager": {
            "session_trade_count": 1,
            "reentries_used": 0,
            "has_loss_stop": True,
            "reversal_locked": False,
            "consecutive_losses": 1,
            "max_consecutive_losses": 3,
            "daily_pnl": -820,
            "daily_realized_losses": 820,
            "daily_max_loss": 2000,
            "open_risk": 0,
            "available_daily_risk": 1000,
            "symbol_trades": 0,
            "symbol_win_rate": 100,
            "min_symbol_trades_for_cap": 5,
            "symbol_min_win_rate": 35,
        },
        "gate_measurements": {
            "quote_age_seconds": 1,
            "quote_age_threshold_seconds": 60,
            "ltp": 18.2,
            "body_ratio": 0.8,
            "body_ratio_threshold": 0.6,
            "body_ratio_passed": True,
            "volatility_pct": 0.2,
            "volatility_min_pct": 0.05,
            "volatility_max_pct": 5,
            "adx": 24,
            "adx_threshold": 18,
        },
        "entry_evaluation": {},
        "quote": {"last_price": 18.2, "volume": 1000, "oi": 1000, "iv": 0.2},
        "ema_reentry_state": {"status": "observing", "stop_out_low": 18.05},
        "underlying_history": [
            {
                "time": (timestamp - timedelta(minutes=31 - index)).isoformat(),
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 10,
            }
            for index in range(31)
        ],
    }


def test_infy_stop_check_records_score_failure_and_no_ema_cross(tmp_path):
    stop_time = datetime(2026, 10, 28, 11, 10, 23, tzinfo=IST)
    journal = StopReentryJournal(
        tmp_path, tmp_path / "option_candles", config_hash="infy-config"
    )
    try:
        event_id = journal.record_stop_event(
            {
                "trade_id": "INFY_CE-2026-10-28T10:51:23-BUY",
                "contract_id": "NFO-INFY26NOV1160CE",
                "underlying": "INFY",
                "leg": "CE",
                "stop_time": stop_time,
                "entry_price": 20.1,
                "stop_price": 18.09,
                "exit_price": 18.05,
                "exit_reason": "STOP_LOSS",
                "net_pnl": -820,
            }
        )
        assert event_id is not None
        decision_time = stop_time + timedelta(minutes=16)
        snapshot = _snapshot(
            timestamp=decision_time,
            ticker="INFY_CE",
            score=73,
            outcome="trade_blocked: stop re-entry requires score 75 or higher",
        )
        snapshot["underlying_history"] = [
            {
                "time": (decision_time - timedelta(minutes=31 - index)).isoformat(),
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
            }
            for index in range(31)
        ]
        assert journal.record_check(event_id, snapshot)
        assert journal.flush()

        stop_rows = _read_rows(tmp_path / "stop_events.jsonl")
        check_rows = _read_rows(tmp_path / "reentry_checks.jsonl")
        assert stop_rows[0]["original_trade_id"] == "INFY_CE-2026-10-28T10:51:23-BUY"
        assert stop_rows[0]["net_pnl"] == -820
        check = check_rows[0]
        assert check["contract_id"] == "NFO-INFY26NOV1160CE"
        assert check["conditions"]["stop_reentry_score"] == {
            "result": "fail",
            "value": 73.0,
            "threshold": 75.0,
        }
        assert check["conditions"]["ordinary_entry_score"]["result"] == "pass"
        assert check["conditions"]["ema_cross"]["value"]["cross"] is False
        assert check["first_failed_condition"] == "score"
        assert check["n_failed_conditions"] > 0
    finally:
        journal.close()


def test_reentry_checks_are_deduplicated_per_bar(tmp_path):
    stop_time = datetime(2026, 10, 28, 11, 10, 23, tzinfo=IST)
    journal = StopReentryJournal(
        tmp_path, tmp_path / "option_candles", config_hash="infy-config"
    )
    try:
        event_id = journal.record_stop_event(
            {
                "trade_id": "INFY_CE-2026-10-28T10:51:23-BUY",
                "contract_id": "NFO-INFY26NOV1160CE",
                "underlying": "INFY",
                "leg": "CE",
                "stop_time": stop_time,
                "entry_price": 20.1,
                "stop_price": 18.09,
                "exit_price": 18.05,
                "exit_reason": "STOP_LOSS",
                "net_pnl": -820,
            }
        )
        assert event_id is not None
        bar_time = stop_time + timedelta(minutes=16)
        first = _snapshot(
            timestamp=bar_time,
            ticker="INFY_CE",
            score=73,
            outcome="first evaluation",
        )
        second = _snapshot(
            timestamp=bar_time,
            ticker="INFY_CE",
            score=75,
            outcome="duplicate evaluation",
        )
        assert journal.record_check(event_id, first)
        assert journal.record_check(event_id, second)
        assert journal.flush()

        rows = _read_rows(tmp_path / "reentry_checks.jsonl")
        assert len(rows) == 1
        assert rows[0]["decision_outcome"] == "first evaluation"
    finally:
        journal.close()


def test_checks_continue_after_price_path_checkpoints_until_reentry_window_ends(
    tmp_path,
):
    stop_time = datetime(2026, 10, 28, 11, 10, 23, tzinfo=IST)
    journal = StopReentryJournal(
        tmp_path, tmp_path / "option_candles", config_hash="infy-config"
    )
    try:
        event_id = journal.record_stop_event(
            {
                "trade_id": "INFY_CE-2026-10-28T10:51:23-BUY",
                "contract_id": "NFO-INFY26NOV1160CE",
                "underlying": "INFY",
                "leg": "CE",
                "stop_time": stop_time,
                "entry_price": 20.1,
                "stop_price": 18.09,
                "exit_price": 18.05,
                "exit_reason": "STOP_LOSS",
                "net_pnl": -820,
            }
        )
        assert event_id is not None
        assert journal.record_path_poll(
            event_id, stop_time + timedelta(minutes=63)
        )
        assert journal.record_check(
            event_id,
            _snapshot(
                timestamp=stop_time + timedelta(minutes=75),
                ticker="INFY_CE",
                score=73,
                outcome="trade_blocked: stop re-entry requires score 75 or higher",
            ),
        )
        assert journal.flush()

        assert _read_rows(tmp_path / "reentry_checks.jsonl")
    finally:
        journal.close()


def test_nifty_stop_event_marks_successful_reentry(tmp_path):
    stop_time = datetime(2026, 10, 29, 9, 57, 23, tzinfo=IST)
    journal = StopReentryJournal(
        tmp_path, tmp_path / "option_candles", config_hash="nifty-config"
    )
    try:
        event_id = journal.record_stop_event(
            {
                "trade_id": "NIFTY_CE-2026-10-29T09:55:58-BUY",
                "contract_id": "NFO-NIFTY26N0322950CE",
                "underlying": "NIFTY",
                "leg": "CE",
                "stop_time": stop_time,
                "entry_price": 79,
                "stop_price": 71.1,
                "exit_price": 70.7,
                "exit_reason": "STOP_LOSS",
                "net_pnl": -539.5,
            }
        )
        assert event_id is not None
        opened_at = datetime(2026, 10, 29, 10, 12, 57, tzinfo=IST)
        assert journal.record_check(
            event_id,
            _snapshot(
                timestamp=opened_at,
                ticker="NIFTY_CE",
                score=75,
                outcome="trade_opened",
                reentry_opened=True,
            ),
        )
        assert journal.record_reentry_opened(
            event_id, "NIFTY-CONTINUATION-TRADE", opened_at
        )
        assert journal.flush()

        event_rows = _read_rows(tmp_path / "stop_events.jsonl")
        check_rows = _read_rows(tmp_path / "reentry_checks.jsonl")
        assert event_rows[0]["contract_id"] == "NFO-NIFTY26N0322950CE"
        assert event_rows[1]["record_type"] == "reentry_opened"
        assert event_rows[1]["reentry_trade_id"] == "NIFTY-CONTINUATION-TRADE"
        assert check_rows[0]["reentry_opened"] is True
        summary = summarize_stop_events(tmp_path, stop_time.date())
        assert summary["stop_events"] == 1
        assert summary["stop_events_reentered"] == 1
    finally:
        journal.close()


def test_after_stop_path_uses_captured_contract_candles(tmp_path):
    capture_root = tmp_path / "option_candles"
    day_path = capture_root / "2026-10-28"
    day_path.mkdir(parents=True)
    contract_id = "NFO-INFY26NOV1160CE"
    candle_path = day_path / "NFO-INFY26NOV1160CE.candles.csv"
    columns = ["contract_id", "candle_start_time", "high", "low", "close"]
    stop_time = datetime(2026, 10, 28, 10, 0, tzinfo=IST)
    with candle_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for offset in range(-5, 15):
            candle_time = stop_time + timedelta(minutes=offset)
            close = 25 if offset == 3 else 19
            writer.writerow(
                {
                    "contract_id": contract_id,
                    "candle_start_time": candle_time.isoformat(),
                    "high": max(close, 22),
                    "low": min(close, 18),
                    "close": close,
                }
            )

    journal = StopReentryJournal(
        tmp_path, capture_root, config_hash="path-config"
    )
    try:
        row = journal._path_record(
            {
                "stop_event_id": "event-1",
                "trade_id": "trade-1",
                "contract_id": contract_id,
                "underlying": "INFY",
                "leg": "CE",
                "stop_time": stop_time,
                "entry_price": 20,
                "stop_price": 18,
                "exit_price": 18,
                "exit_reason": "STOP_LOSS",
                "net_pnl": -100,
            },
            15,
        )
        assert row["candles_missing"] is False
        assert row["highest_price_since_stop"] == 25
        assert row["lowest_price_since_stop"] == 18
        assert row["closed_above_entry"] is True
        assert row["closed_above_pre_stop_5m_high"] is True
        assert row["first_close_above_both_time"] == (
            stop_time + timedelta(minutes=4)
        ).isoformat()
    finally:
        journal.close()


def test_writer_failure_is_dropped_without_escaping(tmp_path, caplog):
    class FailingJournal(StopReentryJournal):
        def _write_stop_row(self, payload):
            raise OSError("disk unavailable")

    journal = FailingJournal(
        tmp_path, tmp_path / "option_candles", config_hash="unchanged"
    )
    stop_time = datetime.now(IST)
    with caplog.at_level(logging.WARNING):
        event_id = journal.record_stop_event(
            {
                "trade_id": "trade-failure",
                "contract_id": "NFO-FAILCE",
                "underlying": "FAIL",
                "leg": "CE",
                "stop_time": stop_time,
                "entry_price": 10,
                "stop_price": 9,
                "exit_price": 9,
                "exit_reason": "STOP_LOSS",
                "net_pnl": -1,
            }
        )
        assert event_id is not None
        assert journal.flush()
    journal.close()
    assert "writer failure" in caplog.text


def test_logging_does_not_change_manager_decisions_or_config_hash(tmp_path):
    config = {
        "stop_reentry_enabled": True,
        "stop_reentry_cooldown_minutes": 15,
        "stop_reentry_min_score": 75,
    }
    original_hash = strategy_config_hash(config)
    journal = StopReentryJournal(
        tmp_path, tmp_path / "option_candles", config_hash=original_hash
    )
    try:
        managers = [
            IntradayManager(account_size=100000, daily_max_loss=10000)
            for _ in range(2)
        ]
        for manager in managers:
            manager.record_trade_open("INFY_CE", "BUY")
            manager.record_trade_close("INFY_CE", "STOP_LOSS", -100)
            manager.session_loss_stop_times["INFY_CE"] = (
                datetime.now(IST) - timedelta(minutes=16)
            )
        decisions = [
            manager.can_open_trade(
                "INFY_CE",
                "BUY",
                allow_stop_reentry=True,
                stop_reentry_cooldown_seconds=900,
                signal_score=73,
                minimum_stop_reentry_score=75,
            )
            for manager in managers
        ]
        assert decisions[0] == decisions[1]
        assert decisions[0][0] is False
        assert strategy_config_hash(config) == original_hash
        assert STOP_EVENT_COLUMNS[-1] == "reentry_trade_id"
    finally:
        journal.close()


def test_daily_reports_include_stop_event_reentry_metrics(tmp_path):
    day = datetime(2026, 10, 29, tzinfo=IST).date()
    paper_root = tmp_path / "paper_trading_data"
    paper_root.mkdir()
    event = {
        "record_type": "stop_event",
        "stop_event_id": "nifty-stop",
        "original_trade_id": "nifty-original",
        "contract_id": "NFO-NIFTY-CE",
        "underlying": "NIFTY",
        "leg": "CE",
        "stop_time": datetime(2026, 10, 29, 9, 57, tzinfo=IST).isoformat(),
        "entry_price": 79,
        "stop_price": 71,
        "exit_price": 70.7,
        "exit_reason": "STOP_LOSS",
        "net_pnl": -539.5,
        "config_hash": "report-config",
    }
    opened = {
        **event,
        "record_type": "reentry_opened",
        "reentry_opened": True,
        "reentry_trade_id": "nifty-reentry",
    }
    check = {
        "timestamp": datetime(2026, 10, 29, 10, 13, tzinfo=IST).isoformat(),
        "stop_event_id": "nifty-stop",
        "first_failed_condition": "score",
        "decision_bar_time": datetime(2026, 10, 29, 10, 13, tzinfo=IST).isoformat(),
    }
    (paper_root / "stop_events.jsonl").write_text(
        "\n".join(json.dumps(row) for row in (event, opened)) + "\n",
        encoding="utf-8",
    )
    (paper_root / "reentry_checks.jsonl").write_text(
        json.dumps(check) + "\n", encoding="utf-8"
    )

    summary_path = write_daily_summary(
        data_dir=str(tmp_path), paper_data_dir=str(paper_root), target_date=day
    )
    review_path = write_daily_review(
        data_dir=str(tmp_path), paper_data_dir=str(paper_root), target_date=day
    )

    assert summary_path.exists()
    report_text = review_path.read_text(encoding="utf-8")
    assert "Stop events: 1" in report_text
    assert "Stop events followed by a re-entry: 1" in report_text
    assert '"score": 1' in report_text