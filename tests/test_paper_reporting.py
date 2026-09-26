from datetime import datetime
from datetime import timezone

import pandas as pd
from fastparquet import ParquetFile

from market_bot.trade_journal import DecisionJournal, PaperTradingRecorder, TradeJournal
from market_bot.weekly_report import write_daily_summary, write_weekly_review


def test_paper_journals_partition_parquet_by_week_and_day(tmp_path):
    timestamp = datetime(2026, 9, 7, 10, 0).isoformat(timespec="seconds")
    paper_dir = tmp_path / "paper"
    trades = TradeJournal(str(tmp_path / "trades.jsonl"), str(paper_dir))
    decisions = DecisionJournal(str(tmp_path / "decision_log.jsonl"), str(paper_dir))

    decisions.log_decision({"timestamp": timestamp, "ticker": "NIFTY", "signal": "BUY"})
    decisions.log_decision({"timestamp": timestamp, "ticker": "NIFTY", "signal": "HOLD"})
    trades.log_trade({
        "timestamp": timestamp,
        "ticker": "NIFTY",
        "action": "BUY",
        "entry": 100,
        "quantity": 50,
    })
    trades.close_trade("NIFTY", 101, "BUY", "TAKE_PROFIT")

    day_dir = paper_dir / "2026-09" / "week_37" / "day_07"
    rows = pd.read_parquet(day_dir / "trades.parquet", engine="fastparquet").to_dict(
        orient="records"
    )
    assert rows[0]["status"] == "closed"
    assert rows[0]["exit_price"] == "101"
    assert (day_dir / "decisions.parquet").exists()
    decision_file = ParquetFile(day_dir / "decisions.parquet")
    assert decision_file.to_pandas()["signal"].tolist() == ["BUY", "HOLD"]
    assert decision_file.row_groups


def test_daily_and_weekly_documents_are_written(tmp_path):
    timestamp = datetime.now().isoformat(timespec="seconds")
    (tmp_path / "trades.jsonl").write_text(
        '{"timestamp": "' + timestamp + '", "ticker": "NIFTY", "action": "BUY", '
        '"status": "closed", "pnl": -25, "reason": "STOP_LOSS"}\n',
        encoding="utf-8",
    )
    (tmp_path / "decision_log.jsonl").write_text(
        '{"timestamp": "' + timestamp + '", "signal": "SELL"}\n', encoding="utf-8"
    )

    summary = write_daily_summary(str(tmp_path), str(tmp_path / "paper"))
    review = write_weekly_review(str(tmp_path), str(tmp_path / "paper"))

    assert summary.name == "daily_summary.parquet"
    assert review.name.startswith("weekly_review_")
    assert "negative" in review.read_text(encoding="utf-8")


def test_weekly_analyzer_reads_partitioned_parquet_journals(tmp_path, monkeypatch):
    from analyze_weekly import iter_decisions, load_filter_stats, load_trades

    monkeypatch.chdir(tmp_path)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    recorder = PaperTradingRecorder(str(tmp_path / "paper_trading_data"))
    recorder.record_trade(
        {
            "timestamp": timestamp,
            "ticker": "NIFTY",
            "action": "BUY",
            "status": "closed",
            "pnl": 100.0,
        }
    )
    decisions_journal = DecisionJournal(
        str(tmp_path / "decision_log.jsonl"), str(tmp_path / "paper_trading_data")
    )
    decisions_journal.log_decision(
        {
            "timestamp": timestamp,
            "ticker": "NIFTY",
            "signal": "BUY",
            "outcome": "accuracy_filter_rejected:volatility",
        }
    )

    assert len(load_trades()) == 1
    decisions = list(iter_decisions())
    assert len(decisions) == 1
    assert decisions[0]["outcome"] == "accuracy_filter"
    assert decisions[0]["outcome_detail"] == "accuracy_filter_rejected:volatility"
    assert load_filter_stats(decisions=iter_decisions())["volatility_rejected"] == 1


def test_decision_parquet_schema_migrates_when_new_session_fields_are_added(tmp_path):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    recorder = PaperTradingRecorder(str(tmp_path / "paper"))
    path = recorder._day_path(timestamp, "decisions.parquet")
    legacy_columns = [
        "timestamp", "ticker", "signal", "outcome", "score", "reasons",
        "bars_available", "bar", "history",
    ]
    recorder._write_parquet(
        path,
        [{"timestamp": timestamp, "ticker": "NIFTY", "signal": "HOLD", "outcome": "hold"}],
        legacy_columns,
    )

    recorder.record_decision({
        "timestamp": timestamp,
        "ticker": "NIFTY",
        "signal": "BUY",
        "outcome": "accuracy_filter",
        "outcome_detail": "accuracy_filter_rejected:volatility",
        "market_session": "regular_session",
        "session_timezone": "Asia/Kolkata",
    })

    rows = PaperTradingRecorder._read_parquet(path)
    assert len(rows) == 2
    assert rows[1]["outcome_detail"] == "accuracy_filter_rejected:volatility"
    assert rows[1]["market_session"] == "regular_session"