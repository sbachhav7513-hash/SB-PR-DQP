import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from market_bot.trade_journal import PaperTradingRecorder, TradeJournal
from market_bot.weekly_report import (
    _daily_record_columns,
    _option_capture_window_status,
    build_weekly_report,
    summarize_best_setup_windows,
    write_daily_review,
    write_weekly_report,
    write_weekly_review,
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


def test_daily_review_reports_confirmed_entry_evaluation_metrics(tmp_path):
    timezone = ZoneInfo("Asia/Kolkata")
    now = datetime.now(timezone).replace(microsecond=0)
    trades = [
        {
            "timestamp": now.isoformat(),
            "ticker": "NIFTY_CE",
            "status": "closed",
            "entry_mode": "confirmed",
            "pnl_rupees": 10.0,
            "after_cost_pnl": 8.0,
            "confirmation_delay_seconds": 62,
            "signal_premium": 20.0,
            "order_premium": 21.0,
        },
        {
            "timestamp": now.isoformat(),
            "ticker": "NIFTY_PE",
            "status": "closed",
            "entry_mode": "confirmed",
            "pnl_rupees": -5.0,
            "after_cost_pnl": -6.0,
            "confirmation_delay_seconds": 64,
            "signal_premium": 10.0,
            "order_premium": 11.0,
        },
    ]
    decisions = [
        {
            "timestamp": now.isoformat(),
            "event": "entry_confirmation",
            "confirmation_event": "signal_generated",
        },
        {
            "timestamp": now.isoformat(),
            "event": "entry_confirmation",
            "confirmation_event": "rejected_by_confirmation",
            "cancellation_reason": "confirmation_failed_ce",
        },
        {
            "timestamp": now.isoformat(),
            "event": "entry_confirmation",
            "confirmation_event": "filter_failed_after_confirmation",
            "confirmation_result": "passed",
            "cancellation_sub_reason": "stale_quote",
        },
        {
            "timestamp": now.isoformat(),
            "event": "entry_confirmation",
            "confirmation_event": "expired_signal",
            "cancellation_sub_reason": "missing_candle",
        },
    ]
    (tmp_path / "trades.jsonl").write_text(
        "\n".join(json.dumps(item) for item in trades) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "decision_log.jsonl").write_text(
        "\n".join(json.dumps(item) for item in decisions) + "\n",
        encoding="utf-8",
    )

    review_path = write_daily_review(
        str(tmp_path),
        paper_data_dir=str(tmp_path / "paper"),
        target_date=now.date(),
    )
    review = review_path.read_text(encoding="utf-8")

    assert "- Signals generated: 1" in review
    assert "- Direction confirmed: 1" in review
    assert "Rejected by confirmation (CE / PE): 1 / 0" in review
    assert '{"stale_quote": 1}' in review
    assert "- Expired signals: 1" in review
    assert "- Confirmed trades: 2" in review
    assert "- Gross recorded P&L: 5.00" in review
    assert "- After-cost P&L: 2.00" in review


def test_daily_and_weekly_reviews_group_modeled_fees_net_pnl_and_r(tmp_path):
    timezone = ZoneInfo("Asia/Kolkata")
    now = datetime.now(timezone).replace(microsecond=0)
    trade = {
        "trade_id": "costed-trade",
        "timestamp": now.isoformat(),
        "closed_at": now.isoformat(),
        "ticker": "NIFTY_CE",
        "action": "BUY",
        "status": "closed",
        "pnl_rupees": 100.0,
        "gross_pnl_rupees": 100.0,
        "fees": {
            "brokerage": 40.0,
            "stt": 1.0,
            "total_fees": 10.0,
            "fee_model_status": "modeled",
        },
        "fees_rupees": 10.0,
        "fee_model_status": "modeled",
        "after_cost_pnl": 90.0,
        "net_pnl": 90.0,
        "tier": "A",
        "exit_trigger": "bot stop",
        "r_multiple": 1.5,
        "manual_exit_events": [
            {"event": "set", "text": "/exitat 4 110", "chat_id": "101"}
        ],
    }
    (tmp_path / "trades.jsonl").write_text(
        json.dumps(trade) + "\n", encoding="utf-8"
    )

    daily_path = write_daily_review(
        str(tmp_path),
        paper_data_dir=str(tmp_path / "paper"),
        target_date=now.date(),
    )
    daily_review = daily_path.read_text(encoding="utf-8")
    weekly_report = build_weekly_report(
        str(tmp_path),
        days=7,
        paper_data_dir=str(tmp_path / "paper"),
    )
    weekly_path = write_weekly_review(
        str(tmp_path),
        str(tmp_path / "paper"),
        days=7,
        report=weekly_report,
        output_path=tmp_path / "weekly.md",
    )
    weekly_review = weekly_path.read_text(encoding="utf-8")

    assert "- Gross P&L: 100.00" in daily_review
    assert "- Modeled fees: 10.00 (1/1 trades)" in daily_review
    assert "Net P&L (gross minus modeled fees; no slippage): 90.00" in daily_review
    assert "- Human command affected at least one trade: yes" in daily_review
    assert "| CE/PE | CE | 1 | 100.00 | 10.00 (1/1) | 90.00" in daily_review
    assert "| tier | A | 1 | 100.00 | 10.00 (1/1) | 90.00" in weekly_review
    assert "| exit_trigger | bot stop | 1 | 100.00 | 10.00 (1/1) | 90.00" in weekly_review
    assert weekly_report["cost_performance"]["CE/PE"]["CE"]["average_r"] == 1.5
    assert weekly_report["human_command_affected_trade"] is True


def test_daily_review_marks_successful_human_command_from_command_archive(tmp_path):
    timezone = ZoneInfo("Asia/Kolkata")
    now = datetime.now(timezone).replace(microsecond=0)
    journal = TradeJournal(
        str(tmp_path / "trades.jsonl"),
        paper_data_dir=str(tmp_path / "paper"),
    )
    journal.log_command(
        {
            "chat_id": "101",
            "user_id": "202",
            "text": "/exitat 42 110",
            "update_id": 42,
            "message_timestamp": now.timestamp(),
            "response": "Trade #42: manual exit trigger set from none to 110.00.",
        }
    )

    review_path = write_daily_review(
        str(tmp_path),
        paper_data_dir=str(tmp_path / "paper"),
        target_date=now.date(),
    )

    assert "- Human command affected at least one trade: yes" in (
        review_path.read_text(encoding="utf-8")
    )


def test_daily_review_shows_fill_age_manual_label_and_exit_flag_comparisons(tmp_path):
    timezone = ZoneInfo("Asia/Kolkata")
    now = datetime.now(timezone).replace(microsecond=0)
    trades = [
        {
            "trade_id": "paper-lock",
            "timestamp": now.isoformat(),
            "entry_time": now.isoformat(),
            "closed_at": now.isoformat(),
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "status": "closed",
            "reason": "PROFIT_LOCK",
            "pnl_rupees": 15.0,
            "signal_premium": 100.0,
            "order_premium": 101.0,
            "fill_premium": 101.0,
            "fill_bid": 100.5,
            "fill_ask": 101.0,
            "fill_ltp": 100.75,
            "fill_quote_age_seconds": 2.5,
            "fill_percent_change_from_signal": 1.0,
            "paper_exit_flags_at_entry": ["profit_lock_v2"],
            "paper_exit_flags_at_exit": ["profit_lock_v2"],
            "manual_exit": False,
            "exit_trigger_price": 100.15,
            "exit_trigger_source": "option_bid",
            "signal_uid": "uid-paper-lock",
            "entry_feature_values": {
                "regime_label": "trending",
                "regime_range_pct": 1.2,
                "regime_20_bar_move_pct": 0.8,
                "signal_uid": "uid-paper-lock",
                "mfe_r": 0.75,
                "mfe_time": now.isoformat(),
                "mae_r": -0.2,
                "mae_time": now.isoformat(),
            },
        },
        {
            "trade_id": "manual-stop",
            "timestamp": now.isoformat(),
            "entry_time": now.isoformat(),
            "closed_at": now.isoformat(),
            "ticker": "BANKNIFTY_CE",
            "action": "BUY",
            "status": "closed",
            "reason": "STOP_LOSS",
            "pnl_rupees": -10.0,
            "paper_exit_flags_at_entry": [],
            "paper_exit_flags_at_exit": [],
            "manual_exit": True,
            "manual_exit_reason": "operator_request",
        },
    ]
    (tmp_path / "trades.jsonl").write_text(
        "\n".join(json.dumps(item) for item in trades) + "\n",
        encoding="utf-8",
    )

    review_path = write_daily_review(
        str(tmp_path),
        paper_data_dir=str(tmp_path / "paper"),
        target_date=now.date(),
    )
    review = review_path.read_text(encoding="utf-8")

    assert "Signal/order/fill premium" in review
    assert "100.0/101.0/101.0" in review
    assert "100.5/101.0/100.75/2.5s" in review
    assert "yes: operator_request" in review
    assert "| profit_lock_v2 | 1 (1/0/0) | 15.00 | 1 (0/1/0) | -10.00 |" in review
    assert "## Entry Features" in review
    assert "regime=trending/1.2%/0.8%" in review
    assert "MFE/MAE=0.75@" in review
    assert "| regime_label | 1/2 | 50.0% |" in review
    recovery = build_weekly_report(
        str(tmp_path), paper_data_dir=str(tmp_path / "paper")
    )["stop_out_recovery"]
    assert recovery["trades"] == 1
    assert recovery["incomplete"] == 1
    assert recovery["stop_within_5m"] == 1


def test_weekly_report_counts_partial_trade_once_using_aggregate_pnl(tmp_path):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    trade = {
        "trade_id": "partial-trade",
        "timestamp": timestamp,
        "entry_time": timestamp,
        "closed_at": timestamp,
        "ticker": "NIFTY_CE",
        "action": "BUY",
        "status": "closed",
        "quantity": 100,
        "entry_quantity": 100,
        "partial_status": "executed",
        "partial_exit_done": True,
        "pnl": 200.0,
        "pnl_rupees": 200.0,
        "exit_legs": [
            {"leg_type": "partial", "quantity": 50, "gross_pnl_rupees": 250.0},
            {"leg_type": "final", "quantity": 50, "gross_pnl_rupees": -50.0},
        ],
    }
    (tmp_path / "trades.jsonl").write_text(
        json.dumps(trade) + "\n", encoding="utf-8"
    )
    (tmp_path / "decision_log.jsonl").write_text("", encoding="utf-8")

    report = build_weekly_report(str(tmp_path))

    assert report["closed_trades"] == 1
    assert report["winning_trades"] == 1
    assert report["losing_trades"] == 0
    assert report["performance_by_symbol"]["NIFTY_CE"]["total_pnl"] == 200.0


def test_daily_capture_window_and_trade_columns_include_exit_telemetry(tmp_path):
    day = datetime(2026, 10, 28, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata")).date()
    trade = {
        "contract_id": "NFO:NIFTY26NOV25000CE",
        "signal_time": "2026-10-28T09:15:00+05:30",
        "entry_time": "2026-10-28T09:15:30+05:30",
        "closed_at": "2026-10-28T09:16:10+05:30",
    }
    candle_dir = tmp_path / "option_candles" / day.isoformat()
    candle_dir.mkdir(parents=True)
    candle_path = candle_dir / "NFO_NIFTY26NOV25000CE.candles.csv"
    candle_path.write_text(
        "contract_id,candle_start_time,gap\n"
        "NFO:NIFTY26NOV25000CE,2026-10-28T09:15:00+05:30,false\n",
        encoding="utf-8",
    )
    assert _option_capture_window_status(trade, tmp_path, day) == (
        "incomplete: 1/2 minutes"
    )
    with candle_path.open("a", encoding="utf-8") as handle:
        handle.write(
            "NFO:NIFTY26NOV25000CE,2026-10-28T09:16:00+05:30,false\n"
        )
    assert _option_capture_window_status(trade, tmp_path, day) == "complete"
    required = {
        "fill_bid",
        "fill_ask",
        "fill_ltp",
        "fill_quote_age_seconds",
        "fill_percent_change_from_signal",
        "paper_change_flags_at_entry",
        "paper_change_flags_at_exit",
        "exit_trigger_price",
        "exit_trigger_source",
    }
    assert required.issubset(set(_daily_record_columns("trades.parquet")))