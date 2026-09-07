import csv
from datetime import datetime

from market_bot.trade_journal import DecisionJournal, TradeJournal
from market_bot.weekly_report import write_daily_summary, write_weekly_review


def test_paper_journals_partition_csv_by_week_and_day(tmp_path):
    timestamp = datetime(2026, 9, 7, 10, 0).isoformat(timespec="seconds")
    paper_dir = tmp_path / "paper"
    trades = TradeJournal(str(tmp_path / "trades.jsonl"), str(paper_dir))
    decisions = DecisionJournal(str(tmp_path / "decision_log.jsonl"), str(paper_dir))

    decisions.log_decision({"timestamp": timestamp, "ticker": "NIFTY", "signal": "BUY"})
    trades.log_trade({
        "timestamp": timestamp,
        "ticker": "NIFTY",
        "action": "BUY",
        "entry": 100,
        "quantity": 50,
    })
    trades.close_trade("NIFTY", 101, "BUY", "TAKE_PROFIT")

    day_dir = paper_dir / "2026-09" / "week_37" / "day_07"
    with (day_dir / "trades.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "closed"
    assert rows[0]["exit_price"] == "101"
    assert (day_dir / "decisions.csv").exists()


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

    assert summary.name == "daily_summary.csv"
    assert review.name.startswith("weekly_review_")
    assert "negative" in review.read_text(encoding="utf-8")