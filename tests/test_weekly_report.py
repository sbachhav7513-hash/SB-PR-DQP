import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from market_bot.trade_journal import PaperTradingRecorder
from market_bot.weekly_report import build_weekly_report, write_weekly_report


def test_weekly_report_selects_best_repeated_profile(tmp_path):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    trades = [
        {"timestamp": timestamp, "ticker": "GOOD", "action": "BUY", "status": "closed", "pnl": 10},
        {"timestamp": timestamp, "ticker": "GOOD", "action": "BUY", "status": "closed", "pnl": 20},
        {"timestamp": timestamp, "ticker": "BAD", "action": "SELL", "status": "closed", "pnl": -5},
        {"timestamp": timestamp, "ticker": "BAD", "action": "SELL", "status": "closed", "pnl": -1},
    ]
    decisions = [
        {"timestamp": timestamp, "signal": "BUY", "outcome": "trade_opened"},
        {"timestamp": timestamp, "signal": "HOLD", "outcome": "hold"},
    ]
    (tmp_path / "trades.jsonl").write_text(
        "\n".join(json.dumps(item) for item in trades) + "\n", encoding="utf-8"
    )
    (tmp_path / "decision_log.jsonl").write_text(
        "\n".join(json.dumps(item) for item in decisions) + "\n", encoding="utf-8"
    )

    report = build_weekly_report(str(tmp_path))
    output = write_weekly_report(str(tmp_path), output_dir=str(tmp_path))

    assert report["decisions_recorded"] == 2
    assert report["best_observed_profiles"][0]["profile"] == "GOOD:BUY"
    assert report["winning_trades"] == 2
    assert report["losing_trades"] == 2
    assert report["average_win"] == 15
    assert report["average_loss"] == -3
    assert report["profit_factor"] == 5
    assert report["performance_by_symbol"]["GOOD"]["total_pnl"] == 30
    local_hour = datetime.fromisoformat(timestamp).astimezone(
        ZoneInfo("Asia/Kolkata")
    ).hour
    assert report["performance_by_hour"][str(local_hour)]["trades"] == 4
    assert report["outcome_counts"]["trade_opened"] == 1
    assert report["session_timezone"] == "Asia/Kolkata"
    assert report["decision_reconciliation"]["matches_decisions_recorded"] is True
    assert report["decision_reconciliation"]["accounted_decisions"] == 2
    assert output.exists()


def test_weekly_report_prefers_parquet_and_counts_decision_rejections(tmp_path):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    paper_root = tmp_path / "paper"
    recorder = PaperTradingRecorder(str(paper_root))
    recorder.record_trade(
        {
            "timestamp": timestamp,
            "ticker": "NIFTY",
            "action": "BUY",
            "status": "closed",
            "pnl": 125.0,
        }
    )
    recorder.record_decision(
        {
            "timestamp": timestamp,
            "ticker": "NIFTY",
            "signal": "BUY",
            "outcome": "accuracy_filter_rejected:volatility",
            "reasons": ["volatility below configured floor"],
        }
    )
    recorder.record_decision(
        {
            "timestamp": timestamp,
            "ticker": "NIFTY",
            "signal": "BUY",
            "outcome": "trade_opened",
            "reasons": ["entry approved"],
        }
    )
    (tmp_path / "decision_log.jsonl").write_text(
        json.dumps({"timestamp": timestamp, "signal": "HOLD", "outcome": "hold"})
        + "\n",
        encoding="utf-8",
    )

    report = build_weekly_report(str(tmp_path), paper_data_dir=str(paper_root))

    assert report["closed_trades"] == 1
    assert report["decisions_recorded"] == 2
    assert report["filter_stats"]["volatility_rejected"] == 1
    assert report["filter_stats"]["approved_entries"] == 1
    assert report["outcome_counts"]["accuracy_filter"] == 1
    assert report["decision_reconciliation"]["classified_rejections"] == 1
    assert report["decision_reconciliation"]["non_entry_decisions"] == 0
    local_hour = datetime.fromisoformat(timestamp).astimezone(
        ZoneInfo("Asia/Kolkata")
    ).hour
    assert report["performance_by_hour"][str(local_hour)]["trades"] == 1