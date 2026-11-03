import json
import logging
import queue
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import market_bot.trade_journal as trade_journal
from market_bot.trade_journal import (
    PaperTradingRecorder,
    read_decisions,
)
from market_bot.kite_main import KiteTradingBot
from merge_decisions_to_legacy import merge_day_to_legacy
from market_bot.weekly_report import _date_records


def _row(index, timestamp=None):
    return {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "ticker": f"TEST_{index}",
        "signal": "BUY",
        "outcome": "trade_opened",
        "history": [{"close": index}],
    }


def _parts_dir(root, timestamp):
    recorder = PaperTradingRecorder(str(root))
    day_dir = recorder._day_path(timestamp, "decisions.parquet").parent
    parts_dir = day_dir / "decisions"
    parts_dir.mkdir(parents=True, exist_ok=True)
    return recorder, day_dir, parts_dir


def test_normal_shutdown_flushes_all_queued_rows(tmp_path):
    recorder = PaperTradingRecorder(str(tmp_path / "paper"))
    timestamp = datetime.now(timezone.utc).isoformat()
    for index in range(201):
        recorder.record_decision(_row(index, timestamp))

    assert recorder.close_decisions(timeout=20)
    day_dir = next((tmp_path / "paper").glob("*/*/day_*"))
    frame = read_decisions(day_dir)
    assert len(frame) == 201
    assert frame["ticker"].nunique() == 201
    hour = datetime.fromisoformat(timestamp).astimezone(
        ZoneInfo("Asia/Kolkata")
    ).hour
    assert (day_dir / "decisions" / f"decisions_{hour:02d}.parquet").exists()
    assert not list((day_dir / "decisions").glob(f"decisions_{hour:02d}_*.parquet"))


def test_shutdown_drains_a_full_queue_within_twenty_seconds(tmp_path):
    recorder = PaperTradingRecorder(str(tmp_path / "paper"))
    timestamp = datetime.now(timezone.utc).isoformat()
    for index in range(trade_journal.DECISION_QUEUE_SIZE):
        recorder._decision_queue.put_nowait(
            ("decision", {"timestamp": timestamp, "ticker": str(index)})
        )
    assert recorder._decision_queue.full()
    recorder._decision_worker = threading.Thread(
        target=recorder._run_decision_writer,
        name="paper-decision-writer-test",
        daemon=True,
    )
    recorder._decision_worker.start()

    started = time.perf_counter()
    assert recorder.close_decisions(timeout=20)
    assert time.perf_counter() - started < 20
    day_dir = next((tmp_path / "paper").glob("*/*/day_*"))
    frame = read_decisions(day_dir)
    assert len(frame) == trade_journal.DECISION_QUEUE_SIZE
    assert frame["ticker"].nunique() == trade_journal.DECISION_QUEUE_SIZE


def test_queue_full_drop_is_counted_without_blocking_caller(tmp_path):
    recorder = PaperTradingRecorder(str(tmp_path / "paper"))
    recorder._decision_queue = queue.Queue(maxsize=1)
    release = threading.Event()
    recorder._decision_worker = threading.Thread(
        target=release.wait, name="blocked-decision-writer-test", daemon=True
    )
    recorder._decision_worker.start()

    recorder.record_decision(_row(1))
    started = time.perf_counter()
    recorder.record_decision(_row(2))
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert elapsed_ms < 2
    assert recorder.decision_telemetry()["drops"] == 1
    release.set()


def test_queued_row_is_a_deep_copy_of_the_decision(tmp_path):
    recorder = PaperTradingRecorder(str(tmp_path / "paper"))
    row = _row(1)
    original_history = json.dumps(row["history"])
    recorder.record_decision(row)
    row["history"][0]["close"] = -1

    assert recorder.flush_decisions(timeout=20)
    day_dir = next((tmp_path / "paper").glob("*/*/day_*"))
    assert json.loads(read_decisions(day_dir).iloc[0]["history"]) == json.loads(
        original_history
    )
    assert recorder.close_decisions(timeout=20)


def test_tick_callback_duration_is_measured_and_reported(caplog):
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot._telegram_execution_lock = None
    bot._tick_duration_lock = threading.Lock()
    bot._tick_duration_samples = deque(maxlen=10)
    bot._on_tick_serialized = lambda tick: time.sleep(0.005)

    bot._on_tick(None)

    assert bot._tick_duration_samples[0] >= 0.005
    with caplog.at_level(logging.INFO):
        bot._log_persistence_telemetry()
    assert "tick_callback_p95_ms=" in caplog.text
    assert "option_capture_sizes=" in caplog.text


def test_incomplete_temp_file_is_not_readable_before_atomic_rename(
    tmp_path, monkeypatch
):
    recorder, day_dir, parts_dir = _parts_dir(
        tmp_path / "paper", "2026-11-03T10:00:00+05:30"
    )
    recorder._write_decision_part(
        day_dir, 10, [_row(1, "2026-11-03T10:00:00+05:30")]
    )
    original_replace = trade_journal.os.replace

    def fail_before_rename(source, destination):
        if Path(destination).name == "decisions_10.parquet":
            raise OSError("simulated crash before rename")
        original_replace(source, destination)

    monkeypatch.setattr(trade_journal.os, "replace", fail_before_rename)
    with pytest.raises(OSError, match="simulated crash"):
        recorder._compact_decision_hour(day_dir, 10)

    assert not (parts_dir / "decisions_10.parquet").exists()
    assert not list(parts_dir.glob("*.tmp"))
    assert len(read_decisions(day_dir)) == 1


def test_part_temp_left_by_write_crash_is_not_readable(tmp_path, monkeypatch):
    recorder, day_dir, parts_dir = _parts_dir(
        tmp_path / "paper", "2026-11-03T10:00:00+05:30"
    )
    recorder._write_decision_part(
        day_dir, 10, [_row(1, "2026-11-03T10:00:00+05:30")]
    )
    original_replace = trade_journal.os.replace

    def fail_part_rename(source, destination):
        if Path(destination).name.startswith("decisions_10_"):
            raise OSError("simulated crash before part rename")
        original_replace(source, destination)

    monkeypatch.setattr(trade_journal.os, "replace", fail_part_rename)
    with pytest.raises(OSError, match="simulated crash"):
        recorder._write_decision_part(
            day_dir, 10, [_row(2, "2026-11-03T10:01:00+05:30")]
        )

    assert list(parts_dir.glob("*.tmp"))
    assert len(list(parts_dir.glob("decisions_*.parquet"))) == 1
    assert len(read_decisions(day_dir)) == 1


@pytest.mark.parametrize("crash_point", ["before_rename", "after_rename", "mid_delete"])
def test_compaction_crash_is_idempotent_and_reader_returns_rows_once(
    tmp_path, monkeypatch, crash_point
):
    recorder, day_dir, parts_dir = _parts_dir(
        tmp_path / "paper", "2026-11-03T10:00:00+05:30"
    )
    for index in range(2):
        recorder._write_decision_part(
            day_dir,
            10,
            [_row(index, f"2026-11-03T10:0{index}:00+05:30")],
        )

    if crash_point == "before_rename":
        original_replace = trade_journal.os.replace

        def fail_before_rename(source, destination):
            if Path(destination).name == "decisions_10.parquet":
                raise OSError("simulated crash before rename")
            original_replace(source, destination)

        monkeypatch.setattr(trade_journal.os, "replace", fail_before_rename)
    else:
        original_unlink = Path.unlink
        removed = 0

        def fail_while_deleting(path, *args, **kwargs):
            nonlocal removed
            if path.parent == parts_dir and path.name.startswith("decisions_10_"):
                removed += 1
                if crash_point == "after_rename" or removed == 2:
                    raise OSError("simulated crash during part deletion")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_while_deleting)

    with pytest.raises(OSError, match="simulated crash"):
        recorder._compact_decision_hour(day_dir, 10)

    rows = read_decisions(day_dir)
    assert len(rows) == 2
    assert set(rows["ticker"]) == {"TEST_0", "TEST_1"}
    monkeypatch.undo()
    assert recorder._compact_decision_hour(day_dir, 10)
    assert len(read_decisions(day_dir)) == 2


def test_reader_aligns_legacy_and_part_schemas_with_nulls(tmp_path):
    timestamp = "2026-11-03T09:30:00+05:30"
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    legacy = pd.DataFrame([
        {"timestamp": timestamp, "ticker": "NIFTY", "signal": "BUY"},
        {"timestamp": "2026-11-03T09:31:00+05:30", "ticker": "NIFTY", "signal": "HOLD"},
    ])
    legacy.to_parquet(legacy_dir / "decisions.parquet", engine="fastparquet")
    legacy_read = read_decisions(legacy_dir)
    assert legacy_read[["timestamp", "ticker", "signal"]].to_dict("records") == (
        legacy[["timestamp", "ticker", "signal"]].to_dict("records")
    )

    same_new_dir = tmp_path / "same_new"
    same_parts = same_new_dir / "decisions"
    same_parts.mkdir(parents=True)
    for index, row in enumerate(legacy.to_dict(orient="records")):
        pd.DataFrame([row]).to_parquet(
            same_parts / f"decisions_09_3{index}0000_{index + 1:06d}.parquet",
            engine="fastparquet",
        )
    same_new = read_decisions(same_new_dir)
    assert same_new[["timestamp", "ticker", "signal"]].to_dict("records") == (
        legacy_read[["timestamp", "ticker", "signal"]].to_dict("records")
    )

    new_dir = tmp_path / "new"
    parts_dir = new_dir / "decisions"
    parts_dir.mkdir(parents=True)
    pd.DataFrame(
        [{
            "timestamp": timestamp,
            "ticker": "NIFTY",
            "score": 3,
            "event_at": pd.Timestamp(timestamp).tz_convert("UTC"),
        }]
    ).to_parquet(
        parts_dir / "decisions_09_300000_000001.parquet", engine="fastparquet"
    )
    pd.DataFrame([{"timestamp": "2026-11-03T09:31:00+05:30", "signal": "HOLD"}]).to_parquet(
        parts_dir / "decisions_09_310000_000002.parquet", engine="fastparquet"
    )

    aligned = read_decisions(new_dir)
    assert len(aligned) == 2
    assert pd.isna(aligned.loc[0, "signal"])
    assert pd.isna(aligned.loc[1, "ticker"])
    assert aligned["timestamp"].is_monotonic_increasing
    assert str(aligned["score"].dtype) == "Int64"
    assert str(aligned["event_at"].dtype) == "datetime64[ns, UTC]"


def test_hour_boundary_splits_decision_parts_by_ist_hour(tmp_path):
    recorder = PaperTradingRecorder(str(tmp_path / "paper"))
    recorder._flush_decision_batch([
        _row(1, "2026-11-03T14:59:59+05:30"),
        _row(2, "2026-11-03T15:00:00+05:30"),
    ])
    day_dir = next((tmp_path / "paper").glob("*/*/day_*"))
    parts = sorted((day_dir / "decisions").glob("decisions_*.parquet"))
    assert len(parts) == 2
    assert any(path.name.startswith("decisions_14_") for path in parts)
    assert any(path.name.startswith("decisions_15_") for path in parts)
    assert len(read_decisions(day_dir)) == 2


def test_end_of_day_reader_flushes_pending_decisions_before_reading(tmp_path):
    paper_root = tmp_path / "paper"
    journal = trade_journal.DecisionJournal(
        str(tmp_path / "decision_log.jsonl"), str(paper_root)
    )
    timestamps = [
        "2026-11-03T09:30:00+05:30",
        "2026-11-03T09:31:00+05:30",
    ]
    for index, timestamp in enumerate(timestamps):
        journal.log_decision(_row(index, timestamp))
    day_dir = journal.paper_recorder._day_path(
        timestamps[0], "decisions.parquet"
    ).parent

    records = _date_records(
        tmp_path / "decision_log.jsonl",
        paper_root,
        "decisions.parquet",
        datetime.fromisoformat(timestamps[0]).date(),
    )

    assert len(records) == 2
    assert len(read_decisions(day_dir)) == 2
    assert journal.close(timeout=20)


def test_rollback_tool_merges_parts_to_legacy_with_row_count_check(tmp_path):
    recorder, day_dir, _ = _parts_dir(
        tmp_path / "paper", "2026-11-03T10:00:00+05:30"
    )
    recorder._write_decision_part(
        day_dir,
        10,
        [
            _row(1, "2026-11-03T10:00:00+05:30"),
            _row(2, "2026-11-03T10:01:00+05:30"),
        ],
    )

    legacy_path, rows_written = merge_day_to_legacy(day_dir)

    assert legacy_path == day_dir / "decisions.parquet"
    assert rows_written == 2
    assert len(pd.read_parquet(legacy_path, engine="fastparquet")) == 2
    assert len(read_decisions(day_dir)) == 2
    assert legacy_path.exists()
