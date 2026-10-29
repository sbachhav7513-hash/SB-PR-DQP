from datetime import date, datetime
from datetime import timezone
import json

import pandas as pd
from fastparquet import ParquetFile

from market_bot.trade_journal import DecisionJournal, PaperTradingRecorder, TradeJournal
from market_bot.weekly_report import (
    build_weekly_report,
    write_daily_review,
    write_daily_summary,
    write_weekly_review,
)


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
    })
    decisions.log_decision({"timestamp": timestamp, "ticker": "NIFTY", "signal": "HOLD"})
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
    assert (day_dir / "decisions.parquet").exists()
    decision_file = ParquetFile(day_dir / "decisions.parquet")
    assert decision_file.to_pandas()["signal"].tolist() == ["BUY", "HOLD"]
    assert decision_file.to_pandas()["config_hash"].tolist() == ["abc123", "abc123"]
    assert decision_file.to_pandas()["contract_id"].tolist() == [
        "NFO:NIFTY26SEP25000CE",
        "",
    ]
    assert decision_file.row_groups


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
    assert "Recorded P&L before unmodeled trading costs" in review_content
    assert "do not tune thresholds from this sample" in review_content
    assert "do not raise the score threshold from win rate alone" in review_content
    assert "No parameter or live-order setting is changed automatically" in review_content


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
    assert "Recorded P&L before unmodeled trading costs: -10.00" in content
    assert "Status: collecting_evidence (1/10 closed trades" in content
    assert "No strategy or configuration settings are changed automatically." in content
    assert (
        "| NIFTY | BUY | trend_shadow_paper | 60 | N/A | N/A | -10.00 | STOP_LOSS |"
        in content
    )
    assert "- BUY/SELL signals: 1" in content
    assert "- Unselected option-leg skips: 1" in content
    assert "- Side-eligible directional candidates: 0" in content
    assert "- Entries opened: 0" in content
    assert "accuracy_filter: 1" in content
    assert "accuracy_filter_rejected:volatility: 1" in content
    assert "Sideways regime: 1" in content
    assert "Directional candidates: 1" in content
    assert "confirmation: 1" in content


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

    rows = PaperTradingRecorder._read_parquet(path)
    assert len(rows) == 2
    assert rows[1]["outcome_detail"] == "accuracy_filter_rejected:volatility"
    assert rows[1]["market_session"] == "regular_session"
    assert rows[1]["trend_shadow_signal"] == "SELL"
    assert rows[1]["trend_shadow_rejection_reason"] == "confirmation"
    assert rows[1]["strategy_variant"] == "trend_shadow_paper"