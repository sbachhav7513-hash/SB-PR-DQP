import json
from datetime import datetime, timedelta

from market_bot.trade_journal import (
    DecisionJournal,
    PaperTradingRecorder,
    RejectedSignalJournal,
    TradeJournal,
    read_rejected_signals,
    rejected_signal_updates_path,
)


def test_decision_journal_appends_json_without_changing_payload(tmp_path):
    path = tmp_path / "decisions.jsonl"
    journal = DecisionJournal(str(path))

    journal.log_decision({"ticker": "TEST", "signal": "HOLD", "history": [{"close": 100}]})

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["ticker"] == "TEST"
    assert record["signal"] == "HOLD"
    assert record["history"] == [{"close": 100}]
    assert record["timestamp"]
    assert record["contract_id"] == ""


def test_trade_journal_records_contract_id(tmp_path):
    path = tmp_path / "trades.jsonl"
    journal = TradeJournal(str(path))

    journal.log_trade(
        {
            "ticker": "NIFTY_CE",
            "trading_symbol": "NIFTY26OCT25000CE",
            "contract_id": "NFO:NIFTY26OCT25000CE",
        }
    )

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["contract_id"] == "NFO:NIFTY26OCT25000CE"
    assert record["timestamp"]
    assert record["entry_time"] == record["timestamp"]


def test_trade_journal_defaults_entry_time_and_persists_entry_telemetry(tmp_path):
    timestamp = "2026-10-30T09:30:00+05:30"
    paper_dir = tmp_path / "paper"
    recorder = PaperTradingRecorder(
        str(paper_dir),
        config_hash="cfg",
        git_sha="startup-sha",
        git_dirty=False,
    )
    journal = TradeJournal(
        str(tmp_path / "trades.jsonl"),
        str(paper_dir),
        config_hash="cfg",
        git_sha="startup-sha",
        git_dirty=False,
    )
    candle = {"time": timestamp, "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0}
    journal.log_trade(
        {
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "timestamp": timestamp,
            "trade_id": "trade-1",
            "signal_id": "NIFTY_CE|CE|2026-10-30T09:29:00+05:30",
            "atr_pct": 0.043,
            "effective_volatility_threshold_pct": 0.04,
            "momentum_candle": candle,
            "momentum_body_ratio": 0.5,
            "momentum_body_ratio_threshold": 0.2,
            "direction_rule": "option_premium_rising",
            "active_paper_change_attributions": ["option_candle_momentum"],
            "git_sha": "payload-sha",
            "git_dirty": True,
        }
    )

    record = json.loads((tmp_path / "trades.jsonl").read_text(encoding="utf-8"))
    assert record["entry_time"] == timestamp
    assert record["git_sha"] == "startup-sha"
    assert record["git_dirty"] is False
    [parquet_record] = recorder._read_parquet(
        next(paper_dir.glob("**/trades.parquet"))
    )
    assert parquet_record["signal_id"] == record["signal_id"]
    assert parquet_record["atr_pct"] == "0.043"
    assert json.loads(parquet_record["momentum_candle"]) == candle
    assert parquet_record["direction_rule"] == "option_premium_rising"
    assert json.loads(parquet_record["active_paper_change_attributions"]) == [
        "option_candle_momentum"
    ]


def test_bot_trade_exits_always_record_exit_reason(tmp_path):
    journal = TradeJournal(str(tmp_path / "trades.jsonl"))
    journal.log_trade(
        {
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "entry": 100.0,
            "stop_loss": 95.0,
            "take_profit": 105.0,
        }
    )

    journal.update_trade_pnl("NIFTY_CE", 95.0, "BUY")
    [trade] = journal.read_trades()
    assert trade["exit_reason"] == "STOP_LOSS"

    journal.log_trade(
        {
            "ticker": "BANKNIFTY_CE",
            "action": "BUY",
            "entry": 100.0,
        }
    )
    journal.close_trade("BANKNIFTY_CE", 101.0, "BUY", "SIGNAL_WEAKEN")
    trade = next(
        item for item in journal.read_trades() if item["ticker"] == "BANKNIFTY_CE"
    )
    assert trade["exit_reason"] == "SIGNAL_WEAKEN"


def test_profitable_manual_target_is_labeled_as_manual(tmp_path):
    journal = TradeJournal(str(tmp_path / "trades.jsonl"))
    journal.log_trade(
        {
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "entry": 100.0,
        }
    )

    journal.close_trade("NIFTY_CE", 105.0, "BUY", "MANUAL_TARGET")

    [trade] = journal.read_trades()
    assert trade["reason"] == "MANUAL_TARGET"
    assert trade["exit_source"] == "MANUAL"
    assert trade["manual_exit"] is True
    assert trade["manual_exit_reason"] == "MANUAL_TARGET"


def test_losing_manual_target_becomes_manual_exit_and_stays_manual(tmp_path):
    journal = TradeJournal(str(tmp_path / "trades.jsonl"))
    journal.log_trade(
        {
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "entry": 100.0,
        }
    )

    journal.close_trade("NIFTY_CE", 95.0, "BUY", "MANUAL_TARGET")

    [trade] = journal.read_trades()
    assert trade["reason"] == "MANUAL_EXIT"
    assert trade["exit_reason"] == "MANUAL_EXIT"
    assert trade["exit_source"] == "MANUAL"
    assert trade["manual_exit"] is True
    assert trade["manual_exit_reason"] == "MANUAL_EXIT"


def test_entry_confirmation_outcomes_are_normalized(tmp_path):
    path = tmp_path / "decisions.jsonl"
    paper_dir = tmp_path / "paper"
    journal = DecisionJournal(str(path), str(paper_dir))
    cases = [
        ("signal_generated", {}, "pending"),
        ("signal_ignored_pending", {}, "pending"),
        ("rejected_by_confirmation", {}, "confirmation_failed"),
        ("expired_signal", {}, "confirmation_failed"),
        (
            "filter_failed_after_confirmation",
            {"cancellation_sub_reason": "stale_quote"},
            "stale_quote",
        ),
        (
            "filter_failed_after_confirmation",
            {"cancellation_sub_reason": "risk_cap"},
            "risk_cap",
        ),
        (
            "filter_failed_after_confirmation",
            {"cancellation_sub_reason": "premium"},
            "other_filter",
        ),
        ("confirmed_trade", {}, "trade_opened"),
    ]
    for event, details, _ in cases:
        journal.log_decision(
            {
                "event": "entry_confirmation",
                "confirmation_event": event,
                "outcome": "UNKNOWN",
                "signal_id": "NIFTY_CE|CE|2026-10-30T09:29:00+05:30",
                "atr_pct": 0.043,
                "effective_volatility_threshold_pct": 0.04,
                "momentum_candle": {
                    "time": "2026-10-30T09:29:00+05:30",
                    "open": 10.0,
                    "high": 12.0,
                    "low": 9.0,
                    "close": 11.0,
                },
                "momentum_body_ratio": 1 / 3,
                "momentum_body_ratio_threshold": 0.2,
                "direction_rule": "option_premium_rising",
                "active_paper_change_attributions": ["option_candle_momentum"],
                **details,
            }
        )

    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["outcome_detail"] for record in records] == [
        expected for _, _, expected in cases
    ]
    assert journal.flush_decisions()
    parquet_rows = [
        row
        for partition in paper_dir.glob("**/decisions_*.parquet")
        for row in PaperTradingRecorder._read_parquet(partition)
    ]
    assert [row["outcome_detail"] for row in parquet_rows] == [
        expected for _, _, expected in cases
    ]
    assert parquet_rows[0]["signal_id"] == "NIFTY_CE|CE|2026-10-30T09:29:00+05:30"
    assert parquet_rows[0]["atr_pct"] == "0.043"
    assert json.loads(parquet_rows[0]["momentum_candle"])["open"] == 10.0
    assert parquet_rows[0]["direction_rule"] == "option_premium_rising"
    assert json.loads(parquet_rows[0]["active_paper_change_attributions"]) == [
        "option_candle_momentum"
    ]

def test_decision_journal_bounds_large_history_payloads(tmp_path):
    path = tmp_path / "decisions.jsonl"
    journal = DecisionJournal(str(path))
    history = [{"close": value} for value in range(10)]

    journal.log_decision({"ticker": "TEST", "history": history})

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["history"] == history[-DecisionJournal.MAX_HISTORY_BARS:]


def test_decision_journal_normalizes_outcome_and_records_ist_session(tmp_path):
    path = tmp_path / "decisions.jsonl"
    journal = DecisionJournal(str(path))

    journal.log_decision({
        "timestamp": "2026-09-26T06:45:00+00:00",
        "ticker": "NIFTY",
        "contract_id": "NFO:NIFTY26OCT25000CE",
        "signal": "BUY",
        "score": 82,
        "outcome": "accuracy_filter_rejected:volatility",
    })

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["outcome"] == "accuracy_filter"
    assert record["contract_id"] == "NFO:NIFTY26OCT25000CE"
    assert record["outcome_detail"] == "accuracy_filter_rejected:volatility"
    assert record["rejection_reason"] == "volatility"
    assert record["market_session"] == "regular_session"
    assert record["market_hours"] is True
    assert record["session_timezone"] == "Asia/Kolkata"


def test_decision_journal_normalizes_shared_risk_and_cutoff_outcomes(tmp_path):
    path = tmp_path / "decisions.jsonl"
    journal = DecisionJournal(str(path))

    journal.log_decision({
        "ticker": "TCS_CE",
        "signal": "BUY",
        "outcome": "paper_risk_cap_blocked:one_lot_exceeds_1000_rupees",
        "entry_evaluation": {
            "paper_risk_cap_rupees": 1000.0,
            "option_risk_per_lot_rupees": 2486.25,
            "accepted": False,
        },
    })
    journal.log_decision({
        "ticker": "NIFTY_PE",
        "signal": "SELL",
        "outcome": "paper_entry_cutoff_blocked:45m_before_close",
    })
    journal.log_decision({
        "ticker": "BANKNIFTY_CE",
        "signal": "BUY",
        "outcome": "risk_cap_blocked:one_lot_exceeds_1000_rupees",
        "entry_evaluation": {
            "risk_cap_rupees": 1000.0,
            "option_risk_per_lot_rupees": 1200.0,
            "accepted": False,
        },
    })
    journal.log_decision({
        "ticker": "BANKNIFTY_PE",
        "signal": "SELL",
        "outcome": "entry_cutoff_blocked:45m_before_close",
    })

    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["outcome"] == "paper_risk_cap"
    assert records[0]["rejection_reason"] == "one lot exceeds 1000 rupees"
    assert records[0]["entry_evaluation"]["option_risk_per_lot_rupees"] == 2486.25
    assert records[1]["outcome"] == "paper_entry_cutoff"
    assert records[1]["rejection_reason"] == "45m before close"
    assert records[2]["outcome"] == "paper_risk_cap"
    assert records[2]["entry_evaluation"]["risk_cap_rupees"] == 1000.0
    assert records[3]["outcome"] == "paper_entry_cutoff"
    assert records[3]["rejection_reason"] == "45m before close"


def test_rejected_signal_journal_records_gate_measurements_in_ist(tmp_path):
    journal = DecisionJournal(str(tmp_path / "decisions.jsonl"), config_hash="cfg")

    journal.log_decision(
        {
            "timestamp": "2026-10-30T04:00:00+00:00",
            "ticker": "NIFTY_CE",
            "contract_id": "NFO:NIFTY26N0322950CE",
            "signal": "BUY",
            "outcome": "accuracy_filter_rejected:volatility",
            "score": 75,
            "gate_measurements": {
                "body_ratio": 0.42,
                "body_ratio_threshold": 0.60,
                "body_ratio_source": "underlying_signal_candle",
                "quote_age_seconds": 72.0,
                "quote_age_threshold_seconds": 60.0,
                "volatility_pct": 5.2,
                "volatility_min_pct": 0.05,
                "volatility_max_pct": 5.0,
                "adx": 21.0,
                "adx_threshold": 18.0,
                "score_threshold": 70,
                "bid": 100.0,
                "ask": 101.0,
                "ltp": 100.5,
                "option_bar_close": 100.5,
            },
        }
    )

    record = json.loads(
        (tmp_path / "rejected_signals.jsonl").read_text(encoding="utf-8")
    )
    assert record["ist_time"] == "2026-10-30T09:30:00+05:30"
    assert record["contract_id"] == "NFO:NIFTY26N0322950CE"
    assert record["config_hash"] == "cfg"
    assert record["gate"] == "volatility"
    assert record["body_ratio"] == 0.42
    assert record["quote_age_seconds"] == 72.0
    assert record["volatility_pct"] == 5.2
    assert record["adx"] == 21.0
    assert record["score"] == 75
    assert record["forward_15m_status"] == "pending"


def test_rejected_signal_forward_outcomes_update_the_original_row(tmp_path):
    path = tmp_path / "rejected_signals.jsonl"
    journal = DecisionJournal(str(tmp_path / "decisions.jsonl"))
    journal.log_decision(
        {
            "timestamp": "2026-10-30T09:30:00+05:30",
            "forward_reference_time": "2026-10-30T09:30:00+05:30",
            "ticker": "NIFTY_CE",
            "contract_id": "NFO:NIFTY26N0322950CE",
            "signal": "BUY",
            "outcome": "OPTION_FILTER_WEAK_CANDLE_MOMENTUM",
            "gate_measurements": {"option_bar_close": 100.0},
        }
    )
    candles = []
    start = datetime.fromisoformat("2026-10-30T09:30:00+05:30")
    for index in range(60):
        high, low = (
            (110.0, 95.0)
            if index < 15
            else (120.0, 90.0)
            if index < 30
            else (130.0, 80.0)
        )
        candles.append(
            {
                "time": (start + timedelta(minutes=index)).isoformat(),
                "high": high,
                "low": low,
            }
        )

    journal.rejected_signal_journal.observe_forward_candles(
        "NFO:NIFTY26N0322950CE",
        candles,
        start + timedelta(minutes=60),
    )

    assert journal.rejected_signal_journal.flush()
    record = read_rejected_signals(path)[0]
    assert record["forward_15m_mfe_pct"] == 10.0
    assert record["forward_15m_mae_pct"] == -5.0
    assert record["forward_30m_mfe_pct"] == 20.0
    assert record["forward_30m_mae_pct"] == -10.0
    assert record["forward_60m_mfe_pct"] == 30.0
    assert record["forward_60m_mae_pct"] == -20.0
    assert record["forward_60m_candles"] == 60
    assert record["forward_60m_status"] == "complete"


def test_rejected_signal_updates_merge_and_preserve_legacy_file(tmp_path):
    path = tmp_path / "rejected_signals.jsonl"
    original = {
        "signal_id": "signal-1",
        "contract_id": "NFO:TEST",
        "forward_15m_status": "pending",
        "forward_30m_status": "pending",
        "forward_60m_status": "pending",
        "forward_15m_mfe_pct": None,
    }
    original_text = json.dumps(original) + "\n"
    path.write_text(original_text, encoding="utf-8")
    journal = RejectedSignalJournal(path)
    updated = {
        **original,
        "forward_15m_status": "complete",
        "forward_15m_mfe_pct": 12.5,
    }

    assert journal._write_updates({"signal-1": updated})
    journal.pending["signal-1"] = updated
    assert journal.flush()

    assert path.read_text(encoding="utf-8") == original_text
    assert read_rejected_signals(path) == [updated]
    update_lines = rejected_signal_updates_path(path).read_text(
        encoding="utf-8"
    ).splitlines()
    assert json.loads(update_lines[0]) == {
        "signal_id": "signal-1",
        "patch": {
            "forward_15m_status": "complete",
            "forward_15m_mfe_pct": 12.5,
        },
    }
    assert journal.close()


def test_rejected_signal_shutdown_flushes_queued_updates(tmp_path):
    path = tmp_path / "rejected_signals.jsonl"
    original = {
        "signal_id": "signal-1",
        "contract_id": "NFO:TEST",
        "forward_15m_status": "pending",
    }
    path.write_text(json.dumps(original) + "\n", encoding="utf-8")
    journal = RejectedSignalJournal(path)
    updated = {**original, "forward_15m_status": "complete"}

    assert journal._write_updates({"signal-1": updated})
    journal.pending["signal-1"] = updated
    assert journal.close()

    assert read_rejected_signals(path) == [updated]


def test_rejected_signal_append_repairs_partial_base_and_update_rows(tmp_path):
    path = tmp_path / "rejected_signals.jsonl"
    first = {
        "signal_id": "signal-1",
        "contract_id": "NFO:TEST",
        "forward_15m_status": "pending",
        "forward_30m_status": "pending",
        "forward_60m_status": "pending",
    }
    path.write_text(
        json.dumps(first) + "\n" + '{"signal_id":"partial"',
        encoding="utf-8",
    )
    journal = RejectedSignalJournal(path)
    journal.record_rejection(
        {
            "signal_id": "signal-2",
            "timestamp": "2026-10-30T09:30:00+05:30",
            "ticker": "NIFTY_CE",
            "contract_id": "NFO:TEST",
            "signal": "BUY",
            "outcome": "option_filter",
            "outcome_detail": "OPTION_FILTER_WEAK_CANDLE_MOMENTUM",
            "gate_measurements": {"option_bar_close": 100.0},
        }
    )
    journal.updates_path.write_text('{"signal_id":"signal-1","patch":', encoding="utf-8")
    assert journal._write_updates(
        {"signal-1": {**first, "forward_15m_status": "complete"}}
    )
    assert journal.pending["signal-1"]["forward_15m_status"] == "pending"
    assert journal.close()

    rows = read_rejected_signals(path)
    assert [row["signal_id"] for row in rows] == ["signal-1", "signal-2"]
    assert rows[0]["forward_15m_status"] == "complete"


def test_confirmation_rejection_keeps_signal_and_rejection_times_distinct(tmp_path):
    journal = DecisionJournal(str(tmp_path / "decisions.jsonl"))
    journal.log_decision(
        {
            "timestamp": "2026-10-30T10:02:05+05:30",
            "signal_time": "2026-10-30T10:00:00+05:30",
            "event": "entry_confirmation",
            "confirmation_event": "rejected_by_confirmation",
            "signal_id": "NIFTY_CE|CE|2026-10-30T10:00:00+05:30",
            "ticker": "NIFTY_CE",
            "contract_id": "NFO:NIFTY26N0322950CE",
            "signal": "BUY",
            "signal_premium": 98.0,
            "signal_ltp": 98.0,
            "confirmation_ltp": 103.0,
            "gate_measurements": {"option_bar_close": 95.0},
        }
    )

    record = json.loads(
        (tmp_path / "rejected_signals.jsonl").read_text(encoding="utf-8")
    )
    assert record["ist_time"] == "2026-10-30T10:00:00+05:30"
    assert record["signal_time_ist"] == "2026-10-30T10:00:00+05:30"
    assert record["rejected_at_ist"] == "2026-10-30T10:02:05+05:30"
    assert record["forward_reference_time_ist"] == "2026-10-30T10:02:05+05:30"
    assert record["premium_at_signal"] == 98.0
    assert record["forward_reference_premium"] == 103.0
    assert record["forward_reference_premium_source"] == "ltp"


def test_support_reversal_body_ratio_rejection_is_logged(tmp_path):
    journal = DecisionJournal(str(tmp_path / "decisions.jsonl"))
    journal.log_decision(
        {
            "timestamp": "2026-10-30T10:02:05+05:30",
            "ticker": "NIFTY_CE",
            "contract_id": "NFO:NIFTY26N0322950CE",
            "signal": "BUY",
            "outcome": "PAPER_SUPPORT_REVERSAL_INVALID_BODY_RATIO",
            "gate_measurements": {
                "body_ratio": 0.18,
                "body_ratio_threshold": 0.20,
            },
        }
    )

    record = json.loads(
        (tmp_path / "rejected_signals.jsonl").read_text(encoding="utf-8")
    )
    assert record["gate"] == "weak candle momentum"
    assert record["reason"] == "PAPER_SUPPORT_REVERSAL_INVALID_BODY_RATIO"
    assert record["body_ratio"] == 0.18


def test_sideways_hold_is_logged_for_future_option_outcome_measurement(tmp_path):
    journal = DecisionJournal(str(tmp_path / "decisions.jsonl"))
    journal.log_decision(
        {
            "timestamp": "2026-10-30T10:02:05+05:30",
            "ticker": "NIFTY_CE",
            "contract_id": "NFO:NIFTY26N0322950CE",
            "signal": "HOLD",
            "outcome": "hold",
            "reasons": [
                "Sideways regime: recent range 0.200% < 1.000% and 20-bar move 0.100% < 1.000%"
            ],
            "gate_measurements": {"ltp": 103.0},
        }
    )

    record = json.loads(
        (tmp_path / "rejected_signals.jsonl").read_text(encoding="utf-8")
    )
    assert record["gate"] == "sideways regime"
    assert record["signal"] == "HOLD"
    assert record["reason"].startswith("Sideways regime:")