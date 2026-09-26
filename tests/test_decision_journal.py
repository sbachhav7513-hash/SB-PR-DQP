import json

from market_bot.trade_journal import DecisionJournal


def test_decision_journal_appends_json_without_changing_payload(tmp_path):
    path = tmp_path / "decisions.jsonl"
    journal = DecisionJournal(str(path))

    journal.log_decision({"ticker": "TEST", "signal": "HOLD", "history": [{"close": 100}]})

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["ticker"] == "TEST"
    assert record["signal"] == "HOLD"
    assert record["history"] == [{"close": 100}]
    assert record["timestamp"]


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
        "signal": "BUY",
        "score": 82,
        "outcome": "accuracy_filter_rejected:volatility",
    })

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["outcome"] == "accuracy_filter"
    assert record["outcome_detail"] == "accuracy_filter_rejected:volatility"
    assert record["rejection_reason"] == "volatility"
    assert record["market_session"] == "regular_session"
    assert record["market_hours"] is True
    assert record["session_timezone"] == "Asia/Kolkata"