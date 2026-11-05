import json
import logging
import shutil
import threading
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import market_bot.kite_main as kite_main
import market_bot.weekly_report as weekly_report
from market_bot.kite_main import KiteTradingBot
from market_bot.trade_journal import PaperTradingRecorder, read_decisions
from migrate_legacy_decisions import migrate_legacy_day


IST = ZoneInfo("Asia/Kolkata")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_daily_reports_read_only_target_day_with_projected_columns(
    tmp_path, monkeypatch
):
    paper_root = tmp_path / "paper_trading_data"
    recorder = PaperTradingRecorder(str(paper_root))
    target_date = date(2026, 11, 4)
    target_timestamp = datetime(2026, 11, 4, 10, 0, tzinfo=IST).isoformat()
    previous_timestamp = datetime(2026, 11, 3, 10, 0, tzinfo=IST).isoformat()
    recorder.record_decision(
        {"timestamp": target_timestamp, "signal": "BUY", "history": "unused"}
    )
    recorder.record_decision(
        {"timestamp": previous_timestamp, "signal": "SELL", "history": "unused"}
    )
    recorder.record_trade(
        {
            "timestamp": target_timestamp,
            "ticker": "NIFTY",
            "status": "closed",
            "pnl": 5,
        }
    )

    calls = []
    original_reader = weekly_report.read_decisions

    def observe_reader(day_path, columns=None):
        calls.append((Path(day_path), columns))
        return original_reader(day_path, columns=columns)

    monkeypatch.setattr(weekly_report, "read_decisions", observe_reader)
    summary_path = weekly_report.write_daily_summary(
        str(tmp_path), str(paper_root), target_date
    )
    weekly_report.write_daily_review(
        str(tmp_path), str(paper_root), target_date
    )
    recorder.close_decisions(timeout=10)

    target_dir = (
        paper_root / "2026-11" / "week_45" / "day_04"
    ).resolve()
    assert calls
    assert all(path.resolve() == target_dir for path, _ in calls)
    assert all(columns is not None and "history" not in columns for _, columns in calls)
    summary = pd.read_parquet(summary_path, engine="fastparquet")
    values = dict(zip(summary["metric"], summary["value"]))
    assert values["decisions_recorded"] == "1"


def test_2026_11_04_content_matches_full_history_baseline(tmp_path, monkeypatch):
    source_day = (
        REPOSITORY_ROOT
        / "paper_trading_data"
        / "2026-11"
        / "week_45"
        / "day_04"
    )
    paper_root = tmp_path / "paper_trading_data"
    day_dir = paper_root / "2026-11" / "week_45" / "day_04"
    day_dir.parent.mkdir(parents=True)
    shutil.copytree(source_day, day_dir)

    empty_data = tmp_path / "empty_data"
    optimized_summary = weekly_report.write_daily_summary(
        str(empty_data),
        str(paper_root),
        date(2026, 11, 4),
    )
    optimized_review = weekly_report.write_daily_review(
        str(empty_data),
        str(paper_root),
        date(2026, 11, 4),
    )
    optimized_summary_frame = pd.read_parquet(
        optimized_summary, engine="fastparquet"
    ).sort_values("metric").reset_index(drop=True)
    optimized_review_content = optimized_review.read_bytes()

    def full_history_records(path, data_root, parquet_name, target_date):
        records = weekly_report._recent_parquet_records(
            data_root,
            parquet_name,
            days=3660,
            columns=weekly_report._daily_record_columns(parquet_name),
        )
        if not records:
            records = weekly_report._load_jsonl(path, days=3660)
        return [
            record
            for record in records
            if weekly_report.PaperTradingRecorder._event_datetime(
                record.get("timestamp")
            ).date()
            == target_date
        ]

    monkeypatch.setattr(weekly_report, "_date_records", full_history_records)
    baseline_summary = weekly_report.write_daily_summary(
        str(empty_data), str(paper_root), date(2026, 11, 4)
    )
    baseline_review = weekly_report.write_daily_review(
        str(empty_data), str(paper_root), date(2026, 11, 4)
    )
    baseline_summary_frame = pd.read_parquet(
        baseline_summary, engine="fastparquet"
    ).sort_values("metric").reset_index(drop=True)

    pd.testing.assert_frame_equal(
        optimized_summary_frame,
        baseline_summary_frame,
        check_dtype=False,
    )
    assert optimized_review_content == baseline_review.read_bytes()


def test_legacy_migration_preserves_reader_rows_and_archives_sources(tmp_path):
    data_root = tmp_path / "paper_trading_data"
    day_dir = data_root / "2026-11" / "week_45" / "day_03"
    day_dir.mkdir(parents=True)
    shared = {
        "timestamp": "2026-11-03T09:30:00.123456+05:30",
        "ticker": "NIFTY",
        "signal": "BUY",
        "outcome": "trade_opened",
    }
    legacy_rows = [
        shared,
        {
            "timestamp": "2026-11-03T10:00:00+05:30",
            "ticker": "BANKNIFTY",
            "signal": "SELL",
            "outcome": "hold",
        },
    ]
    part_rows = [
        shared,
        {
            "timestamp": "2026-11-03T11:00:00.1+05:30",
            "ticker": "SENSEX",
            "signal": "HOLD",
            "outcome": "hold",
        },
    ]
    pd.DataFrame(legacy_rows).to_parquet(
        day_dir / "decisions.parquet", engine="fastparquet"
    )
    pd.DataFrame(part_rows).to_parquet(
        day_dir / "decisions_part1_until_1257IST.parquet",
        engine="fastparquet",
    )
    before = read_decisions(day_dir)

    result = migrate_legacy_day(
        day_dir,
        tmp_path / "archive",
        data_root,
        confirm_copy=True,
    )
    after = read_decisions(day_dir)

    pd.testing.assert_frame_equal(
        before, after, check_dtype=False, check_categorical=False
    )
    assert result["source_rows"] == 4
    assert result["deduplicated_rows"] == result["hourly_rows"] == 3
    assert result["hourly_files"] == 3
    assert len(result["archived_files"]) == 2
    assert not (day_dir / "decisions.parquet").exists()
    assert not (day_dir / "decisions_part1_until_1257IST.parquet").exists()


def test_projected_legacy_reader_preserves_distinct_unprojected_rows(tmp_path):
    day_dir = tmp_path / "day_03"
    day_dir.mkdir()
    common = {
        "timestamp": "2026-11-03T09:30:00+05:30",
        "ticker": "NIFTY",
        "signal": "HOLD",
    }
    pd.DataFrame([{**common, "history": "first"}]).to_parquet(
        day_dir / "decisions.parquet", engine="fastparquet"
    )
    pd.DataFrame([{**common, "history": "second"}]).to_parquet(
        day_dir / "decisions_part1_until_1257IST.parquet",
        engine="fastparquet",
    )

    projected = read_decisions(day_dir, columns=["timestamp", "ticker", "signal"])

    assert len(projected) == 2


def test_weekly_report_budget_skip_is_asynchronous_and_logged(
    tmp_path, monkeypatch, caplog
):
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot.config = {"weekly_report_days": 7}
    bot.paper_trading_dir = str(tmp_path / "paper_trading_data")
    bot.weekly_report_dir = tmp_path / "reports"
    bot.last_weekly_report_date = None
    bot._weekly_report_attempt_date = None
    bot._weekly_report_lock = threading.Lock()
    bot._weekly_report_thread = None
    Path(bot.paper_trading_dir).mkdir()
    monkeypatch.setattr(kite_main, "WEEKLY_REPORT_TIME_BUDGET_SECONDS", 0.01)
    monkeypatch.setattr(
        kite_main, "WEEKLY_REPORT_MEMORY_BUDGET_BYTES", 1024**3
    )

    started = datetime(2026, 11, 6, 15, 30, tzinfo=IST)
    with caplog.at_level(logging.ERROR):
        bot._run_weekly_report_if_due(started)
        bot._weekly_report_thread.join(timeout=20)

    assert not bot._weekly_report_thread.is_alive()
    assert "Weekly report skipped: budget exceeded" in caplog.text
    assert "daily finalization and Telegram summary are unaffected" in caplog.text
    assert bot.last_weekly_report_date is None
    assert not list((tmp_path / "reports").glob("weekly_report_*.json"))
    assert not list((tmp_path / "reports").glob(".weekly_report_stage_*"))
    assert not list(
        (Path(bot.paper_trading_dir) / "2026-11" / "week_45").glob(
            ".weekly_review_stage_*.md"
        )
    )


def test_budgeted_weekly_worker_finishes_on_week45_copy(tmp_path, caplog):
    source_week = (
        REPOSITORY_ROOT
        / "paper_trading_data"
        / "2026-11"
        / "week_45"
    )
    paper_root = tmp_path / "paper_trading_data" / "2026-11"
    paper_root.mkdir(parents=True)
    shutil.copytree(source_week, paper_root / "week_45")

    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot.config = {"weekly_report_days": 7}
    bot.paper_trading_dir = str(tmp_path / "paper_trading_data")
    bot.weekly_report_dir = tmp_path / "reports"
    bot.last_weekly_report_date = None
    bot._weekly_report_attempt_date = None
    bot._weekly_report_lock = threading.Lock()
    bot._weekly_report_thread = None

    friday = datetime(2026, 11, 6, 15, 30, tzinfo=IST)
    with caplog.at_level(logging.INFO, logger="market_bot.kite_main"):
        bot._run_weekly_report_if_due(friday)
        bot._weekly_report_thread.join(timeout=120)

    assert not bot._weekly_report_thread.is_alive()
    assert bot.last_weekly_report_date == friday.date()
    assert list((tmp_path / "reports").glob("weekly_report_*.json"))
    assert not list((tmp_path / "reports").glob(".weekly_report_stage_*"))
    assert not list(
        (Path(bot.paper_trading_dir) / "2026-11" / "week_45").glob(
            ".weekly_review_stage_*.md"
        )
    )
    completion = next(
        record.message
        for record in caplog.records
        if "Automatic weekly report written" in record.message
    )
    assert float(completion.split("peak_rss_mb=")[1]) < 600
    assert float(completion.split("elapsed=")[1].split("s")[0]) < 120
