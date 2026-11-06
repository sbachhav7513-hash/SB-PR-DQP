import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import market_bot.kite_main as kite_main
import market_bot.reporting_metrics as reporting_metrics
import market_bot.weekly_report as weekly_report
import market_bot.weekly_report_worker as weekly_report_worker
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
    hourly_dir = day_dir / "decisions"
    hourly_dir.mkdir()
    pd.DataFrame([{**common, "history": "hourly"}]).to_parquet(
        hourly_dir / "decisions_09.parquet", engine="fastparquet"
    )

    projected = read_decisions(day_dir, columns=["timestamp", "ticker", "signal"])
    hourly_projected = read_decisions(
        day_dir,
        columns=["timestamp", "ticker", "signal"],
        hourly_only=True,
    )

    assert len(projected) == 3
    assert len(hourly_projected) == 1
    assert list(hourly_projected.columns) == ["timestamp", "ticker", "signal"]
    assert weekly_report._decision_source_files(day_dir, hourly_only=True) == [
        hourly_dir / "decisions_09.parquet"
    ]


def test_weekly_report_budget_skip_is_synchronous_and_logged(
    tmp_path, monkeypatch, caplog
):
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot.config = {"weekly_report_days": 7}
    bot.paper_trading_dir = str(tmp_path / "paper_trading_data")
    bot.weekly_report_dir = tmp_path / "reports"
    bot.last_weekly_report_date = None
    bot._weekly_report_attempt_date = None
    bot._weekly_report_lock = threading.Lock()
    Path(bot.paper_trading_dir).mkdir()
    monkeypatch.setattr(kite_main, "WEEKLY_REPORT_TIME_BUDGET_SECONDS", 0.01)
    monkeypatch.setattr(
        kite_main, "WEEKLY_REPORT_MEMORY_BUDGET_BYTES", 1024**3
    )

    started = datetime(2026, 11, 6, 15, 30, tzinfo=IST)
    with caplog.at_level(logging.INFO, logger="market_bot.kite_main"):
        bot._run_weekly_report_if_due(started)

    assert "Automatic weekly report started" in caplog.text
    assert "Weekly report skipped on budget" in caplog.text
    assert "daily finalization and Telegram summary are unaffected" in caplog.text
    assert bot.last_weekly_report_date is None
    assert not list((tmp_path / "reports").glob("weekly_report_*.json"))
    assert not list((tmp_path / "reports").glob(".weekly_report_stage_*"))
    assert not list(
        (Path(bot.paper_trading_dir) / "2026-11" / "week_45").glob(
            ".weekly_review_stage_*.md"
        )
    )


def test_weekly_report_requires_legacy_decisions_to_be_migrated(tmp_path):
    paper_root = tmp_path / "paper_trading_data"
    day_dir = paper_root / "2026-11" / "week_45" / "day_03"
    day_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "timestamp": "2026-11-03T09:30:00+05:30",
                "ticker": "NIFTY",
                "signal": "HOLD",
            }
        ]
    ).to_parquet(day_dir / "decisions.parquet", engine="fastparquet")

    with pytest.raises(ValueError, match="requires hourly decision partitions"):
        weekly_report.build_weekly_report(
            str(tmp_path),
            paper_data_dir=str(paper_root),
            hourly_decisions_only=True,
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
    migration_root = tmp_path / "paper_trading_data"
    archive_root = tmp_path / "legacy_decisions_archive"
    for day in ("02", "03"):
        migrate_legacy_day(
            paper_root / "week_45" / f"day_{day}",
            archive_root,
            migration_root,
            confirm_copy=True,
        )

    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot.config = {"weekly_report_days": 7}
    bot.paper_trading_dir = str(tmp_path / "paper_trading_data")
    bot.weekly_report_dir = tmp_path / "reports"
    bot.last_weekly_report_date = None
    bot._weekly_report_attempt_date = None
    bot._weekly_report_lock = threading.Lock()

    friday = datetime(2026, 11, 6, 15, 30, tzinfo=IST)
    with caplog.at_level(logging.INFO, logger="market_bot.kite_main"):
        bot._run_weekly_report_if_due(friday)

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
    assert any(
        "Automatic weekly report started" in item.message
        for item in caplog.records
    )


def test_weekly_worker_memory_budget_logs_step_and_stops(
    tmp_path, monkeypatch, caplog
):
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    stage_dir = output_dir / ".weekly_report_stage_current"
    stage_dir.mkdir()
    review_dir = tmp_path / "paper" / "2026-11" / "week_45"
    review_dir.mkdir(parents=True)
    review_stage = review_dir / ".weekly_review_stage_current.md"
    review_stage.touch()
    result_file = tmp_path / "status.json"
    args = weekly_report_worker.argparse.Namespace(
        data_dir=str(tmp_path),
        paper_data_dir=str(tmp_path / "paper"),
        output_dir=output_dir,
        staging_dir=stage_dir,
        review_staging_path=review_stage,
        review_final_path=review_dir / "weekly_review_2026_11_06.md",
        days=7,
        result_file=result_file,
        memory_budget_bytes=100,
        time_budget_seconds=120,
    )

    def exceed_budget(**_kwargs):
        with reporting_metrics.ReportingStep(
            logging.getLogger("test.weekly"), "weekly_test_over_budget", []
        ):
            pass

    monkeypatch.setattr(weekly_report_worker, "build_weekly_report", exceed_budget)
    monkeypatch.setattr(reporting_metrics, "_working_set_bytes", lambda: 101)

    with caplog.at_level(logging.ERROR):
        result = weekly_report_worker._run(args)

    status = json.loads(result_file.read_text(encoding="utf-8"))
    assert result == 2
    assert status["status"] == "budget"
    assert status["step"] == "weekly_test_over_budget"
    assert "step=weekly_test_over_budget" in caplog.text
    assert not list(output_dir.glob("weekly_report_*.json"))
    assert not list(stage_dir.glob("weekly_report_*.json"))


def test_bot_memory_watchdog_logs_active_step_and_reaps_worker(
    tmp_path, monkeypatch, caplog
):
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot.config = {"weekly_report_days": 7}
    bot.paper_trading_dir = str(tmp_path / "paper")
    bot.weekly_report_dir = tmp_path / "reports"
    bot.last_weekly_report_date = None
    bot._weekly_report_attempt_date = None
    bot._weekly_report_lock = threading.Lock()
    Path(bot.paper_trading_dir).mkdir()
    real_popen = subprocess.Popen
    processes = []

    class OverBudgetWorker:
        pid = 123
        returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.returncode = -15
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

    def over_budget_worker(command, **kwargs):
        if command[0] != sys.executable or command[1] != "-c":
            return real_popen(command, **kwargs)
        Path(kwargs["env"]["WEEKLY_REPORT_STEP_FILE"]).write_text(
            "weekly_decisions_day_02", encoding="utf-8"
        )
        process = OverBudgetWorker()
        processes.append(process)
        return process

    monkeypatch.setattr(kite_main.subprocess, "Popen", over_budget_worker)
    monkeypatch.setattr(kite_main, "process_working_set_bytes", lambda _pid: 101)
    monkeypatch.setattr(kite_main, "WEEKLY_REPORT_MEMORY_BUDGET_BYTES", 100)

    with caplog.at_level(logging.ERROR, logger="market_bot.kite_main"):
        bot._run_weekly_report_if_due(datetime(2026, 11, 6, 15, 30, tzinfo=IST))

    assert processes and processes[0].returncode == -15
    assert "step=weekly_decisions_day_02" in caplog.text
    assert "Weekly report skipped on budget" in caplog.text
    assert not list((tmp_path / "reports").glob(".weekly_report_stage_*"))
    assert not list(Path(bot.paper_trading_dir).rglob(".weekly_review_stage_*"))


def test_weekly_worker_start_removes_stale_stage_paths(tmp_path, monkeypatch):
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    stage_dir = output_dir / ".weekly_report_stage_current"
    stage_dir.mkdir()
    stale_report_stage = output_dir / ".weekly_report_stage_stale"
    stale_report_stage.mkdir()
    (stale_report_stage / "partial").touch()
    review_dir = tmp_path / "paper" / "2026-11" / "week_45"
    review_dir.mkdir(parents=True)
    review_stage = review_dir / ".weekly_review_stage_current.md"
    review_stage.touch()
    stale_review_stage = review_dir / ".weekly_review_stage_stale.md"
    stale_review_stage.touch()
    result_file = tmp_path / "status.json"
    args = weekly_report_worker.argparse.Namespace(
        data_dir=str(tmp_path),
        paper_data_dir=str(tmp_path / "paper"),
        output_dir=output_dir,
        staging_dir=stage_dir,
        review_staging_path=review_stage,
        review_final_path=review_dir / "weekly_review_2026_11_06.md",
        days=7,
        result_file=result_file,
        memory_budget_bytes=10**9,
        time_budget_seconds=120,
    )
    monkeypatch.setattr(
        weekly_report_worker,
        "build_weekly_report",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("stop after cleanup")),
    )

    assert weekly_report_worker._run(args) == 1
    assert stage_dir.is_dir()
    assert review_stage.is_file()
    assert not stale_report_stage.exists()
    assert not stale_review_stage.exists()


def test_weekly_worker_lock_excludes_concurrent_run(tmp_path):
    lock_path = tmp_path / ".weekly_report_worker.lock"
    with weekly_report_worker._worker_lock(lock_path):
        with pytest.raises(RuntimeError, match="Another weekly report worker"):
            with weekly_report_worker._worker_lock(lock_path):
                pass


def test_sigint_during_weekly_wait_reaps_worker_and_cleans_stages(
    tmp_path, monkeypatch
):
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot.config = {"weekly_report_days": 7}
    bot.paper_trading_dir = str(tmp_path / "paper")
    bot.weekly_report_dir = tmp_path / "reports"
    bot.last_weekly_report_date = None
    bot._weekly_report_attempt_date = None
    bot._weekly_report_lock = threading.Lock()
    Path(bot.paper_trading_dir).mkdir()

    marker = tmp_path / "worker_started"
    real_popen = subprocess.Popen
    processes = []

    class InterruptWhenWorkerStarts:
        def __init__(self, process):
            self.process = process
            self.interrupted = False

        @property
        def pid(self):
            return self.process.pid

        @property
        def returncode(self):
            return self.process.returncode

        def poll(self):
            return self.process.poll()

        def wait(self, timeout=None):
            if not self.interrupted:
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert marker.exists()
                self.interrupted = True
                raise KeyboardInterrupt
            return self.process.wait(timeout=timeout)

        def terminate(self):
            self.process.terminate()

        def kill(self):
            self.process.kill()

    def delayed_worker(command, **kwargs):
        if command[0] != sys.executable or command[1] != "-c":
            return real_popen(command, **kwargs)
        test_code = (
            "import os,time; "
            "from market_bot import weekly_report_worker as worker; "
            "worker.build_weekly_report=lambda **kwargs: "
            "(open(os.environ['WEEKLY_TEST_MARKER'],'w').close(), "
            "time.sleep(60))[1]; "
            "raise SystemExit(worker.main())"
        )
        command = list(command)
        command[2] = test_code
        environment = dict(kwargs["env"])
        environment["WEEKLY_TEST_MARKER"] = str(marker)
        kwargs["env"] = environment
        process = InterruptWhenWorkerStarts(real_popen(command, **kwargs))
        processes.append(process)
        return process

    monkeypatch.setattr(kite_main.subprocess, "Popen", delayed_worker)
    monkeypatch.setattr(kite_main, "process_working_set_bytes", lambda _pid: 1)

    try:
        bot._run_weekly_report_if_due(datetime(2026, 11, 6, 15, 30, tzinfo=IST))
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("SIGINT was not propagated")

    assert processes and processes[0].poll() is not None
    assert not list((tmp_path / "reports").glob(".weekly_report_stage_*"))
    assert not list((Path(bot.paper_trading_dir)).rglob(".weekly_review_stage_*"))
    assert not list((tmp_path / "reports").glob("weekly_report_*.json"))
