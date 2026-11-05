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


def test_trade_journal_persists_entry_telemetry_time_and_bot_exit_reason(tmp_path):
    path = tmp_path / "trades.jsonl"
    paper_data_dir = tmp_path / "paper"
    journal = TradeJournal(str(path), str(paper_data_dir))
    entry_time = "2026-10-30T10:00:00+05:30"

    journal.log_trade(
        {
            "timestamp": entry_time,
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "entry": 100.0,
            "signal_id": "NIFTY_CE|CE|2026-10-30T10:00:00+05:30",
            "atr_pct": 0.043,
            "effective_volatility_threshold_pct": 0.04,
            "momentum_candle": {
                "time": entry_time,
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 104.0,
            },
            "momentum_body_ratio": 0.65,
            "momentum_body_ratio_threshold": 0.6,
            "direction_rule": "option_premium_rising_momentum_v2",
            "active_paper_change_attributions": [
                "option_premium_rising_momentum_v2"
            ],
        }
    )
    journal.close_trade("NIFTY_CE", 90.0, "BUY", "STOP_LOSS")

    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert record["entry_time"] == entry_time
    assert record["signal_id"] == "NIFTY_CE|CE|2026-10-30T10:00:00+05:30"
    assert record["atr_pct"] == 0.043
    assert record["direction_rule"] == "option_premium_rising_momentum_v2"
    assert record["exit_reason"] == "STOP_LOSS"

    parquet_path = next(paper_data_dir.rglob("trades.parquet"))
    parquet_record = PaperTradingRecorder._read_parquet(parquet_path)[0]
    assert parquet_record["signal_id"] == record["signal_id"]
    assert parquet_record["atr_pct"] == "0.043"
    assert parquet_record["effective_volatility_threshold_pct"] == "0.04"
    assert json.loads(parquet_record["momentum_candle"])["open"] == 100.0
    assert parquet_record["momentum_body_ratio"] == "0.65"
    assert (
        parquet_record["momentum_body_ratio_threshold"] == "0.6"
    )
    assert parquet_record["direction_rule"] == record["direction_rule"]
    assert json.loads(
        parquet_record["active_paper_change_attributions"]
    ) == ["option_premium_rising_momentum_v2"]
    assert parquet_record["entry_time"] == entry_time
    assert parquet_record["exit_reason"] == "STOP_LOSS"


def test_trade_journal_update_pnl_records_bot_exit_reason(tmp_path):
    path = tmp_path / "trades.jsonl"
    journal = TradeJournal(str(path))
    journal.log_trade(
        {
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "entry": 100.0,
            "stop_loss": 90.0,
            "take_profit": 120.0,
        }
    )

    journal.update_trade_pnl("NIFTY_CE", 89.0, "BUY")

    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert record["status"] == "closed"
    assert record["reason"] == "STOP_LOSS"
    assert record["exit_reason"] == "STOP_LOSS"


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


def test_entry_confirmation_outcomes_are_normalized(tmp_path):
    path = tmp_path / "decisions.jsonl"
    journal = DecisionJournal(str(path))
    outcomes = [
        ("signal_generated", {}, "pending"),
        ("rejected_by_confirmation", {}, "confirmation_failed"),
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

    for event, details, _ in outcomes:
        journal.log_decision(
            {
                "event": "entry_confirmation",
                "confirmation_event": event,
                "outcome": "UNKNOWN",
                **details,
            }
        )

    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["outcome_detail"] for record in records] == [
        expected for _, _, expected in outcomes
    ]
    assert all(record["outcome_detail"] != "UNKNOWN" for record in records)


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

    record = read_rejected_signals(tmp_path / "rejected_signals.jsonl")[0]
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

    assert journal.flush_decisions()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = read_rejected_signals(path)[0]
    assert record["forward_15m_mfe_pct"] == 10.0
    assert record["forward_15m_mae_pct"] == -5.0
    assert record["forward_30m_mfe_pct"] == 20.0
    assert record["forward_30m_mae_pct"] == -10.0
    assert record["forward_60m_mfe_pct"] == 30.0
    assert record["forward_60m_mae_pct"] == -20.0
    assert record["forward_60m_candles"] == 60
    assert record["forward_60m_status"] == "complete"
    assert journal.close()


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

    record = read_rejected_signals(tmp_path / "rejected_signals.jsonl")[0]
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

    record = read_rejected_signals(tmp_path / "rejected_signals.jsonl")[0]
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

    record = read_rejected_signals(tmp_path / "rejected_signals.jsonl")[0]
    assert record["gate"] == "sideways regime"
    assert record["signal"] == "HOLD"
    assert record["reason"].startswith("Sideways regime:")


def test_rejected_signal_reader_merges_updates_without_rewriting_legacy_file(
    tmp_path,
):
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
    updated = dict(original)
    updated.update(
        {
            "forward_15m_status": "complete",
            "forward_15m_mfe_pct": 12.5,
        }
    )

    assert journal._write_updates({"signal-1": updated})
    journal.pending["signal-1"] = updated

    assert journal.flush()
    assert path.read_text(encoding="utf-8") == original_text
    assert read_rejected_signals(path) == [updated]
    update_lines = rejected_signal_updates_path(path).read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(update_lines) == 1
    assert json.loads(update_lines[0]) == {
        "signal_id": "signal-1",
        "patch": {
            "forward_15m_status": "complete",
            "forward_15m_mfe_pct": 12.5,
        },
    }
    assert journal.close()


def test_rejected_signal_partial_update_tail_is_ignored_and_repaired(tmp_path):
    path = tmp_path / "rejected_signals.jsonl"
    path.write_text(
        json.dumps(
            {
                "signal_id": "signal-1",
                "contract_id": "NFO:TEST",
                "forward_15m_status": "pending",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    journal = RejectedSignalJournal(path)
    updates_path = rejected_signal_updates_path(path)
    updates_path.write_text('{"signal_id":"signal-1","patch":', encoding="utf-8")

    assert read_rejected_signals(path)[0]["forward_15m_status"] == "pending"
    assert journal._append_update_records(
        [
            {
                "signal_id": "signal-1",
                "patch": {"forward_15m_status": "complete"},
            }
        ]
    )

    assert updates_path.read_text(encoding="utf-8").endswith("\n")
    assert read_rejected_signals(path)[0]["forward_15m_status"] == "complete"
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


def test_rejected_signal_append_repairs_partial_base_row(tmp_path):
    path = tmp_path / "rejected_signals.jsonl"
    first = {
        "signal_id": "signal-1",
        "contract_id": "NFO:TEST",
        "forward_15m_status": "unmatched",
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

    rows = read_rejected_signals(path)
    assert [row["signal_id"] for row in rows] == ["signal-1", "signal-2"]
    assert journal.close()