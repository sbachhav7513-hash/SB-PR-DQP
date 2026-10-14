import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from market_bot.trade_journal import PaperTradingRecorder
from market_bot.weekly_report import (
    build_weekly_report,
    summarize_best_setup_windows,
    write_weekly_report,
)


def test_weekly_report_does_not_recommend_a_profile_below_screening_sample(tmp_path):
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
    assert report["best_observed_profiles"] == []
    assert "4/10 closed trades" in report["recommendation"]
    assert report["learning_feedback"]["status"] == "collecting_evidence"
    assert report["learning_feedback"]["automatic_strategy_changes"] is False
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


def test_learning_feedback_surfaces_repeated_losses_without_tuning(tmp_path):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    trades = [
        {
            "timestamp": timestamp,
            "ticker": ticker,
            "action": "BUY",
            "status": "closed",
            "pnl": pnl,
            "pnl_rupees": pnl,
            "reason": "SIGNAL_WEAKEN",
        }
        for ticker, pnl in (
            ("RELIANCE_CE", -725.0),
            ("SBIN_CE", -1200.0),
            ("TCS_CE", -1496.25),
        )
    ]
    (tmp_path / "trades.jsonl").write_text(
        "\n".join(json.dumps(item) for item in trades) + "\n", encoding="utf-8"
    )

    feedback = build_weekly_report(str(tmp_path))["learning_feedback"]

    assert feedback["status"] == "collecting_evidence"
    assert feedback["closed_trades"] == 3
    assert feedback["recorded_pnl_before_costs"] == -3421.25
    assert feedback["automatic_strategy_changes"] is False
    assert feedback["loss_patterns_for_review"] == [
        {
            "exit_reason": "SIGNAL_WEAKEN",
            "trades": 3,
            "losses": 3,
            "recorded_pnl_before_costs": -3421.25,
            "average_recorded_pnl_before_costs": -1140.42,
        }
    ]
    assert "do not tune strategy settings" in feedback["recommendation"]


def test_learning_feedback_keeps_sample_floor_advisory_only(tmp_path):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    trades = [
        {
            "timestamp": timestamp,
            "ticker": f"SYMBOL_{index}",
            "action": "BUY",
            "status": "closed",
            "pnl": 10,
            "reason": "TAKE_PROFIT",
        }
        for index in range(10)
    ]
    (tmp_path / "trades.jsonl").write_text(
        "\n".join(json.dumps(item) for item in trades) + "\n", encoding="utf-8"
    )

    feedback = build_weekly_report(str(tmp_path))["learning_feedback"]

    assert feedback["status"] == "minimum_screening_sample_met"
    assert feedback["closed_trades"] == 10
    assert feedback["automatic_strategy_changes"] is False
    assert "not proof of an edge" in feedback["recommendation"]


def test_best_setup_windows_require_repeated_screening_samples(tmp_path):
    timestamp = datetime.now(timezone.utc)
    trades = []
    for index in range(10):
        trades.append(
            {
                "timestamp": timestamp.replace(hour=4, minute=index).isoformat(),
                "ticker": f"WIN_{index}",
                "action": "BUY",
                "status": "closed",
                "pnl": 10,
            }
        )
        trades.append(
            {
                "timestamp": timestamp.replace(hour=5, minute=index).isoformat(),
                "ticker": f"LOSS_{index}",
                "action": "BUY",
                "status": "closed",
                "pnl": -1,
            }
        )
    trades.extend(
        [
            {
                "timestamp": timestamp.replace(hour=3, minute=index).isoformat(),
                "ticker": f"SMALL_{index}",
                "action": "BUY",
                "status": "closed",
                "pnl": 100,
            }
            for index in range(2)
        ]
    )
    (tmp_path / "trades.jsonl").write_text(
        "\n".join(json.dumps(item) for item in trades) + "\n", encoding="utf-8"
    )

    windows = summarize_best_setup_windows(str(tmp_path))

    assert [window["label"] for window in windows] == ["09:BUY", "10:BUY"]
    assert all(window["trades"] == 10 for window in windows)


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


def test_weekly_report_separates_trend_shadow_paper_performance(tmp_path):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    paper_root = tmp_path / "paper"
    recorder = PaperTradingRecorder(str(paper_root))
    recorder.record_trade({
        "timestamp": timestamp,
        "ticker": "NIFTY",
        "action": "BUY",
        "status": "closed",
        "pnl": 20.0,
        "strategy_variant": "primary",
    })
    recorder.record_trade({
        "timestamp": timestamp,
        "ticker": "NIFTY",
        "action": "SELL",
        "status": "closed",
        "pnl": -5.0,
        "strategy_variant": "trend_shadow_paper",
    })

    report = build_weekly_report(str(tmp_path), paper_data_dir=str(paper_root))

    assert report["performance_by_strategy_variant"]["primary"]["total_pnl"] == 20.0
    assert report["performance_by_strategy_variant"]["trend_shadow_paper"]["total_pnl"] == -5.0