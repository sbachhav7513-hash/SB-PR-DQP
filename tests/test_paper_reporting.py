from datetime import date, datetime
from datetime import timezone
import json
from zoneinfo import ZoneInfo

import pandas as pd

from market_bot.trade_journal import (
    DecisionJournal,
    PaperTradingRecorder,
    TradeJournal,
    read_decisions,
)
from market_bot.weekly_report import (
    _tier_review_metrics,
    _date_records,
    build_weekly_report,
    write_daily_review,
    write_daily_summary,
    write_weekly_review,
)


def test_tier_review_excludes_highest_net_r_for_without_best_mean():
    metrics = _tier_review_metrics(
        [
            {"net_pnl": 100.0, "fees_rupees": 0.0, "risk_amount": 1000.0},
            {"net_pnl": 50.0, "fees_rupees": 0.0, "risk_amount": 100.0},
        ]
    )

    assert metrics["mean_net_r"] == 0.3
    assert metrics["mean_net_r_without_best"] == 0.1


def test_paper_journals_partition_parquet_by_week_and_day(tmp_path):
    timestamp = datetime(2026, 9, 7, 10, 0).isoformat(timespec="seconds")
    paper_dir = tmp_path / "paper"
    trades = TradeJournal(
        str(tmp_path / "trades.jsonl"), str(paper_dir), config_hash="abc123"
    )
    decisions = DecisionJournal(
        str(tmp_path / "decision_log.jsonl"), str(paper_dir), config_hash="abc123"
    )

    decisions.log_decision({
        "timestamp": timestamp,
        "ticker": "NIFTY",
        "contract_id": "NFO:NIFTY26SEP25000CE",
        "signal": "BUY",
        "effective_min_trend_strength": 0.0022,
    })
    decisions.log_decision({"timestamp": timestamp, "ticker": "NIFTY", "signal": "HOLD"})
    assert decisions.flush_decisions()
    trades.log_trade({
        "timestamp": timestamp,
        "ticker": "NIFTY",
        "trading_symbol": "NIFTY26SEP25000CE",
        "contract_id": "NFO:NIFTY26SEP25000CE",
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
    assert rows[0]["config_hash"] == "abc123"
    trade_records = [
        json.loads(line)
        for line in (tmp_path / "trades.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    decision_records = [
        json.loads(line)
        for line in (tmp_path / "decision_log.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert trade_records[0]["config_hash"] == "abc123"
    assert all(record["config_hash"] == "abc123" for record in decision_records)
    assert rows[0]["exit_price"] == "101"
    assert rows[0]["trading_symbol"] == "NIFTY26SEP25000CE"
    assert rows[0]["contract_id"] == "NFO:NIFTY26SEP25000CE"
    assert (day_dir / "decisions").is_dir()
    decision_frame = read_decisions(day_dir)
    assert decision_frame["signal"].tolist() == ["BUY", "HOLD"]
    assert decision_frame["config_hash"].tolist() == ["abc123", "abc123"]
    assert decision_frame["contract_id"].tolist() == [
        "NFO:NIFTY26SEP25000CE",
        "",
    ]
    assert decision_frame["effective_min_trend_strength"].tolist() == [
        "0.0022",
        "",
    ]
    daily_decisions = _date_records(
        tmp_path / "decision_log.jsonl",
        paper_dir,
        "decisions.parquet",
        date(2026, 9, 7),
    )
    assert daily_decisions[0]["effective_min_trend_strength"] == "0.0022"
    assert list((day_dir / "decisions").glob("decisions_*.parquet"))


def test_weekly_analyzer_separates_strategy_variant_metrics():
    from analyze_weekly import analyze_trades

    analysis = analyze_trades([
        {"ticker": "NIFTY", "pnl": 20.0, "strategy_variant": "primary"},
        {"ticker": "NIFTY", "pnl": -5.0, "strategy_variant": "trend_shadow_paper"},
    ])

    assert analysis["strategy_variant_stats"]["primary"]["win_rate"] == 100.0
    assert analysis["strategy_variant_stats"]["trend_shadow_paper"]["win_rate"] == 0.0
    assert analysis["strategy_variant_stats"]["trend_shadow_paper"]["profit"] == -5.0


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
    review_content = review.read_text(encoding="utf-8")
    assert "negative" in review_content
    assert "Gross recorded P&L before modeled fees" in review_content
    assert "do not tune thresholds from this sample" in review_content
    assert "do not raise the score threshold from win rate alone" in review_content
    assert "No parameter or live-order setting is changed automatically" in review_content


def test_daily_review_prefers_startup_hash_over_dated_artifact_hash(tmp_path):
    timestamp = "2026-11-25T10:00:00+05:30"
    (tmp_path / "decision_log.jsonl").write_text(
        json.dumps(
            {
                "timestamp": timestamp,
                "signal": "HOLD",
                "config_hash": "dated-artifact-hash",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    review = write_daily_review(
        str(tmp_path),
        str(tmp_path / "paper"),
        target_date=date(2026, 11, 25),
        config_hash="startup-loaded-hash",
    )
    content = review.read_text(encoding="utf-8")

    assert "Startup config hash: startup-loaded-hash" in content
    assert "dated-artifact-hash" not in content
    assert content.count("Startup config hash:") == 1


def test_daily_review_reports_trade_results_rejections_and_shadow_flow(tmp_path):
    timestamp = "2026-09-30T10:00:00+05:30"
    paper_dir = tmp_path / "paper"
    recorder = PaperTradingRecorder(str(paper_dir))
    recorder.record_trade(
        {
            "timestamp": timestamp,
            "ticker": "NIFTY",
            "action": "BUY",
            "status": "closed",
            "score": 60,
            "pnl": -10,
            "reason": "STOP_LOSS",
            "strategy_variant": "trend_shadow_paper",
        }
    )
    recorder.record_decision(
        {
            "timestamp": timestamp,
            "signal": "HOLD",
            "outcome": "hold",
            "score": 60,
            "reasons": ["Sideways regime"],
            "trend_shadow_signal": "BUY",
            "trend_shadow_rejection_reason": "confirmation",
        }
    )
    recorder.record_decision(
        {
            "timestamp": timestamp,
            "signal": "HOLD",
            "outcome": "accuracy_filter_rejected:volatility",
            "rejection_reason": "volatility",
            "reasons": ["confirmation"],
        }
    )
    recorder.record_decision(
        {
            "timestamp": timestamp,
            "signal": "SELL",
            "outcome": "OPTION_LEG_SKIPPED",
            "reasons": ["non-preferred option leg"],
        }
    )

    review = write_daily_review(
        str(tmp_path), str(paper_dir), target_date=date(2026, 9, 30)
    )
    content = review.read_text(encoding="utf-8")

    assert review.name == "daily_review.md"
    assert "Closed trades: 1" in content
    assert "Gross recorded P&L before modeled fees: -10.00" in content
    assert "Status: collecting_evidence (1/10 closed trades" in content
    assert "No strategy or configuration settings are changed automatically." in content
    assert (
        "| NIFTY | BUY | trend_shadow_paper | 60 | N/A | -10.00 | STOP_LOSS |"
        in content
    )
    assert "Flags at entry → exit" in content
    assert "Trigger price/source" in content
    assert "- BUY/SELL signals: 1" in content
    assert "- Unselected option-leg skips: 1" in content
    assert "- Side-eligible directional candidates: 0" in content
    assert "- Entries opened: 0" in content
    assert "accuracy_filter: 1" in content
    assert "accuracy_filter_rejected:volatility: 1" in content
    assert "Sideways regime: 1" in content
    assert "Directional candidates: 1" in content
    assert "confirmation: 1" in content


def test_daily_review_includes_runtime_identity_flags_and_veto_counts(tmp_path):
    timestamp = "2026-09-30T10:00:00+05:30"
    trade = {
        "timestamp": timestamp,
        "closed_at": timestamp,
        "ticker": "TCS_CE",
        "tier": "STOCK",
        "action": "BUY",
        "status": "closed",
        "gross_pnl_rupees": 10.0,
        "fees_rupees": 1.0,
        "net_pnl": 9.0,
        "risk_amount": 100.0,
        "risk_cap_rupees": "",
        "entry_feature_values": {
            "risk_amount": 100.0,
            "risk_cap": 4000.0,
        },
    }
    decisions = [
        {
            "timestamp": timestamp,
            "event": "entry_confirmation",
            "confirmation_event": "confirmation_waiting_5m",
            "signal_id": "signal-1",
            "ticker": "TCS_CE",
            "tier": "STOCK",
            "signal": "BUY",
            "run_up_veto_status": "failed_open",
            "run_up_fail_open_cause": "missing_minute",
            "five_min_continuation_status": "reached",
        },
        {
            "timestamp": timestamp,
            "event": "entry_confirmation",
            "confirmation_event": "expired_signal",
            "signal_id": "signal-1",
            "ticker": "TCS_CE",
            "tier": "STOCK",
            "five_min_continuation_status": "data_missing",
            "five_min_autodisabled": True,
            "cancellation_reason": "five_min_data_missing",
        },
        {
            "timestamp": timestamp,
            "event": "entry_confirmation",
            "confirmation_event": "confirmed_trade",
            "signal_id": "signal-2",
            "ticker": "TCS_CE",
            "signal": "BUY",
            "run_up_veto_status": "passed",
        },
        {
            "timestamp": timestamp,
            "event": "entry_confirmation",
            "confirmation_event": "rejected_by_confirmation",
            "signal_id": "signal-3",
            "ticker": "TCS_CE",
            "signal": "BUY",
            "run_up_veto_status": "vetoed",
        },
    ]
    (tmp_path / "trades.jsonl").write_text(
        json.dumps(trade) + "\n", encoding="utf-8"
    )
    (tmp_path / "decision_log.jsonl").write_text(
        "\n".join(json.dumps(row) for row in decisions) + "\n",
        encoding="utf-8",
    )

    review = write_daily_review(
        str(tmp_path),
        str(tmp_path / "paper"),
        target_date=date(2026, 9, 30),
        config_hash="normalized-config-hash",
        git_sha="commit-sha",
        flag_values={"entry_5m_continuation_v1": False},
    )
    content = review.read_text(encoding="utf-8")

    assert "Commit SHA: commit-sha" in content
    assert "Startup config hash: normalized-config-hash" in content
    assert "entry_5m_continuation_v1=False" in content
    assert "- passed: 1" in content
    assert "- vetoed: 1" in content
    assert "- failed_open: 1" in content
    assert "missing_minute: 1" in content
    assert "| STOCK | 1 | 0 | 0 | 0 | 1 |" in content
    assert "- five_min_autodisabled: 1" in content
    assert "risk/open-risk limit=100.0/4000.0" in content


def test_daily_review_counts_breakeven_separately_from_losses(tmp_path):
    timestamp = "2026-09-30T10:00:00+05:30"
    trades = [
        {
            "timestamp": timestamp,
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "status": "closed",
            "pnl": pnl,
        }
        for pnl in (25.0, -10.0, 0.0)
    ]
    (tmp_path / "trades.jsonl").write_text(
        "\n".join(json.dumps(trade) for trade in trades) + "\n",
        encoding="utf-8",
    )

    review = write_daily_review(
        str(tmp_path),
        str(tmp_path / "paper"),
        target_date=date(2026, 9, 30),
    )

    assert "Wins / losses / breakeven: 1 / 1 / 1" in review.read_text(
        encoding="utf-8"
    )


def test_trade_opened_outcome_detail_counts_as_an_entry_in_all_reports(tmp_path):
    from analyze_weekly import analyze_decisions, load_filter_stats

    timestamp = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")
    decision = {
        "timestamp": timestamp,
        "ticker": "NIFTY_CE",
        "signal": "BUY",
        "outcome": "operational",
        "outcome_detail": "trade_opened",
    }
    (tmp_path / "decision_log.jsonl").write_text(
        json.dumps(decision) + "\n", encoding="utf-8"
    )

    daily_review = write_daily_review(
        str(tmp_path),
        str(tmp_path / "paper"),
        target_date=datetime.fromisoformat(timestamp).date(),
    )
    weekly_report = build_weekly_report(str(tmp_path))
    analysis = analyze_decisions([decision])

    assert "- Entries opened: 1" in daily_review.read_text(encoding="utf-8")
    assert "reason is exactly STOP_LOSS" in daily_review.read_text(encoding="utf-8")
    assert weekly_report["outcome_counts"]["trade_opened"] == 1
    assert "operational" not in weekly_report["outcome_counts"]
    assert weekly_report["filter_stats"]["approved_entries"] == 1
    assert weekly_report["decision_reconciliation"]["approved_entries"] == 1
    assert analysis["outcome_counts"]["trade_opened"] == 1
    assert "operational" not in analysis["outcome_counts"]
    assert analysis["decision_reconciliation"]["approved_entries"] == 1
    assert load_filter_stats(decisions=[decision])["approved_entries"] == 1


def test_weekly_report_groups_option_exit_strategies_separately(tmp_path):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    trades_path = tmp_path / "trades.jsonl"
    trades_path.write_text(
        "\n".join(
            json.dumps(trade)
            for trade in (
                {
                    "timestamp": timestamp,
                    "ticker": "NIFTY_CE",
                    "action": "BUY",
                    "status": "closed",
                    "pnl": 10.0,
                },
                {
                    "timestamp": timestamp,
                    "ticker": "NIFTY_PE",
                    "action": "BUY",
                    "status": "closed",
                    "pnl_rupees": 30.0,
                    "pnl": 20.0,
                    "exit_strategy": "tiered_milestone",
                },
                {
                    "timestamp": timestamp,
                    "ticker": "BANKNIFTY_CE",
                    "action": "BUY",
                    "status": "open",
                    "pnl": 0.0,
                    "exit_strategy": "tiered_milestone",
                },
                {
                    "timestamp": timestamp,
                    "ticker": "INFY_CE",
                    "action": "BUY",
                    "status": "closed",
                    "pnl_rupees": 45.0,
                    "exit_strategy": "paper_option_2r_trail_runner",
                },
                {
                    "timestamp": timestamp,
                    "ticker": "BANKNIFTY_PE",
                    "action": "BUY",
                    "status": "closed",
                    "pnl": -12.0,
                    "exit_strategy": "paper_option_adaptive",
                    "strategy_variant": "adaptive_entry",
                },
                {
                    "timestamp": timestamp,
                    "ticker": "TCS_CE",
                    "action": "BUY",
                    "status": "closed",
                    "pnl": -15.0,
                    "exit_strategy": "paper_range_breakout_2r",
                    "strategy_variant": "breakout_entry",
                    "reason": "STOP_LOSS",
                    "quantity": 10,
                    "entry": 10.0,
                    "exit_price": 8.0,
                    "paper_entry_bid": 9.9,
                    "paper_entry_ask": 10.0,
                    "paper_exit_ltp": 8.0,
                    "paper_exit_bid": 7.9,
                    "paper_exit_ask": 8.1,
                    "paper_entry_risk_rupees": 14.0,
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_weekly_report(str(tmp_path), days=7)

    assert report["option_exit_comparison"]["fixed_20pct_baseline"][
        "closed_trades"
    ] == 1
    assert report["option_exit_comparison"]["fixed_20pct_baseline"][
        "trade_entries"
    ] == 1
    assert report["option_exit_comparison"]["fixed_20pct_baseline"][
        "average_pnl_per_trade"
    ] == 10.0
    assert report["option_exit_comparison"]["tiered_milestone"][
        "average_pnl_per_trade"
    ] == 30.0
    assert report["option_exit_comparison"]["tiered_milestone"][
        "trade_entries"
    ] == 2
    assert report["option_exit_comparison"]["paper_option_2r_trail_runner"][
        "closed_trades"
    ] == 1
    assert report["option_exit_comparison"]["paper_option_2r_trail_runner"][
        "average_pnl_per_trade"
    ] == 45.0
    assert report["option_exit_comparison"]["paper_option_adaptive"][
        "total_pnl"
    ] == -12.0
    assert report["option_exit_comparison"]["paper_range_breakout_2r"][
        "total_pnl"
    ] == -15.0
    assert report["performance_by_strategy_variant"]["breakout_entry"][
        "total_pnl"
    ] == -15.0
    assert report["performance_by_exit_reason"]["STOP_LOSS"]["losses"] == 1
    assert report["quote_cost_coverage"] == {
        "closed_trades": 5,
        "quote_consistent_trades": 1,
        "quote_based_pnl": -21.0,
    }
    assert report["stop_risk_overruns"] == {
        "stop_losses_with_risk_data": 1,
        "overrun_trades": 1,
        "total_overrun_rupees": 1.0,
    }
    review = write_weekly_review(
        str(tmp_path), str(tmp_path / "paper"), days=7
    ).read_text(encoding="utf-8")
    assert "Performance by Entry Strategy" in review
    assert "Loss Clusters" in review
    assert "1/5 closed trades" in review
    assert "do not by themselves constitute an out-of-sample walk-forward replay" in review


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
            "paper_exit_quote_timestamp": timestamp,
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

    loaded_trades = load_trades()
    assert len(loaded_trades) == 1
    assert loaded_trades[0]["paper_exit_quote_timestamp"] == timestamp
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
        "trend_shadow_signal": "SELL",
        "trend_shadow_rejection_reason": "confirmation",
        "strategy_variant": "trend_shadow_paper",
    })

    rows = read_decisions(path.parent).to_dict(orient="records")
    assert len(rows) == 2
    new_row = next(row for row in rows if row["signal"] == "BUY")
    assert new_row["outcome_detail"] == "accuracy_filter_rejected:volatility"
    assert new_row["market_session"] == "regular_session"
    assert new_row["trend_shadow_signal"] == "SELL"
    assert new_row["trend_shadow_rejection_reason"] == "confirmation"
    assert new_row["strategy_variant"] == "trend_shadow_paper"


def test_daily_review_tier_totals_reconcile_and_show_cumulative_stock_row(tmp_path):
    timestamp = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")
    trades = [
        {
            "timestamp": timestamp,
            "closed_at": timestamp,
            "ticker": "TCS_CE",
            "tier": "STOCK",
            "action": "BUY",
            "status": "closed",
            "gross_pnl_rupees": 100.0,
            "fees_rupees": 10.0,
            "net_pnl": 90.0,
            "risk_amount": 100.0,
        },
        {
            "timestamp": timestamp,
            "closed_at": timestamp,
            "ticker": "INFY_PE",
            "tier": "STOCK",
            "action": "BUY",
            "status": "closed",
            "gross_pnl_rupees": -20.0,
            "fees_rupees": 5.0,
            "net_pnl": -25.0,
            "risk_amount": 50.0,
        },
        {
            "timestamp": timestamp,
            "closed_at": timestamp,
            "ticker": "NIFTY_CE",
            "tier": "NIFTY",
            "action": "BUY",
            "status": "closed",
            "gross_pnl_rupees": 40.0,
            "fees_rupees": 2.0,
            "net_pnl": 38.0,
            "risk_amount": 20.0,
        },
        {
            "timestamp": timestamp,
            "closed_at": timestamp,
            "ticker": "BANKNIFTY_PE",
            "tier": "BANKNIFTY",
            "action": "BUY",
            "status": "closed",
            "gross_pnl_rupees": -10.0,
            "fees_rupees": 1.0,
            "net_pnl": -11.0,
            "risk_amount": 10.0,
        },
    ]
    (tmp_path / "trades.jsonl").write_text(
        "\n".join(json.dumps(trade) for trade in trades) + "\n",
        encoding="utf-8",
    )

    review = write_daily_review(
        str(tmp_path),
        str(tmp_path / "paper"),
        target_date=datetime.fromisoformat(timestamp).date(),
    )
    content = review.read_text(encoding="utf-8")

    expected_stock_row = (
        "| STOCK | 2 | 80.00 | 15.00 (2/2) | 65.00 (2/2) | "
        "1 | 0.200 | -0.500 |"
    )
    assert expected_stock_row in content
    assert expected_stock_row.replace("| STOCK |", "| STOCK (cumulative) |") in content
    assert "| NIFTY | 1 | 40.00 | 2.00 (1/1) | 38.00 (1/1) | 1 |" in content
    assert "| BANKNIFTY | 1 | -10.00 | 1.00 (1/1) | -11.00 (1/1) | 0 |" in content