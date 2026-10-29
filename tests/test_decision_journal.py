import json

from market_bot.trade_journal import DecisionJournal, TradeJournal


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