import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from market_bot.kite_main import KiteTradingBot
from market_bot.premarket_context import (
    PremarketContextStore,
    build_context_snapshot,
    calculate_live_range,
)
from market_bot.trade_journal import DecisionJournal, TradeJournal


IST = ZoneInfo("Asia/Kolkata")


def _daily_rows(start: date, count: int, open_price: float = 100.0):
    rows = []
    for offset in range(count):
        day = start + timedelta(days=offset)
        rows.append(
            {
                "date": datetime.combine(day, datetime.min.time()).replace(tzinfo=IST),
                "open": open_price + offset,
                "high": open_price + offset + 2,
                "low": open_price + offset - 2,
                "close": open_price + offset + 1,
            }
        )
    return rows


def test_context_snapshot_calculates_daily_metrics_and_prior_day_distances():
    history_start = date(2026, 11, 9)
    nifty_rows = _daily_rows(history_start, 5)
    banknifty_rows = _daily_rows(history_start, 5, open_price=200.0)
    vix_rows = [
        {
            "date": datetime(2026, 11, 12, tzinfo=IST),
            "open": 14,
            "high": 15,
            "low": 13,
            "close": 14,
        },
        {
            "date": datetime(2026, 11, 13, tzinfo=IST),
            "open": 15,
            "high": 16,
            "low": 14,
            "close": 15,
        },
    ]

    snapshot = build_context_snapshot(
        captured_at=datetime(2026, 11, 16, 9, 20, tzinfo=IST),
        stage="0920",
        symbols=["NIFTY", "BANKNIFTY"],
        daily_history={"NIFTY": nifty_rows, "BANKNIFTY": banknifty_rows},
        prices={"NIFTY": 108.0},
        session_opens={"NIFTY": 107.0},
        vix_history=vix_rows,
    )

    nifty = snapshot["underlyings"]["NIFTY"]
    assert len(nifty["previous_sessions"]) == 5
    assert set(nifty["previous_sessions"][-1]) >= {
        "open", "high", "low", "close", "range_pct"
    }
    assert nifty["average_range_pct_3_sessions"] == pytest.approx(
        sum(
            (row["high"] - row["low"]) / row["open"] * 100
            for row in nifty_rows[-3:]
        )
        / 3
    )
    assert nifty["average_range_pct_5_sessions"] == pytest.approx(
        sum(
            (row["high"] - row["low"]) / row["open"] * 100
            for row in nifty_rows
        )
        / 5
    )
    assert [row["direction"] for row in nifty["last_3_open_to_close_directions"]] == [
        "UP", "UP", "UP"
    ]
    assert nifty["gap_vs_prior_close_pct"] == pytest.approx(
        (107 / 105 - 1) * 100
    )
    assert nifty["distance_from_prior_day_levels_pct"]["high"] == pytest.approx(
        (108 / 106 - 1) * 100
    )
    assert nifty["relative_strength_vs_nifty_5d_pct_points"] == 0
    assert snapshot["india_vix"]["prior_close"] == 15
    assert snapshot["india_vix"]["change_1d_points"] == 1
    assert snapshot["india_vix"]["change_1d_pct"] == pytest.approx(
        (15 / 14 - 1) * 100
    )


def test_live_range_ratio_uses_five_prior_sessions_for_the_same_window():
    current_day = date(2026, 11, 16)
    candles = []
    for offset in range(6):
        day = current_day - timedelta(days=6 - offset)
        for minute, low, high in ((15, 99, 101), (20, 98, 102)):
            candles.append(
                {
                    "date": datetime.combine(
                        day, datetime.min.time()
                    ).replace(hour=9, minute=minute, tzinfo=IST),
                    "open": 100,
                    "high": high,
                    "low": low,
                    "close": 100,
                }
            )
    candles = [
        candle
        for candle in candles
        if candle["date"].date() != current_day
    ] + [
        {
            "date": datetime(2026, 11, 16, 9, minute, tzinfo=IST),
            "open": 100,
            "high": high,
            "low": low,
            "close": 100,
        }
        for minute, high, low in ((15, 103, 99), (20, 104, 98))
    ]

    result = calculate_live_range(candles, current_day)

    assert result["prior_sessions_available"] == 5
    assert result["average_range_pct_5_sessions_same_window"] == pytest.approx(4)
    assert result["live_range_pct"] == pytest.approx(6)
    assert result["ratio_to_5_session_average"] == pytest.approx(1.5)


def test_context_store_merges_snapshots_into_one_daily_file(tmp_path):
    store = PremarketContextStore(tmp_path / "premarket")
    first = build_context_snapshot(
        captured_at=datetime(2026, 11, 16, 8, 45, tzinfo=IST),
        stage="0845",
        symbols=["NIFTY"],
        daily_history={"NIFTY": _daily_rows(date(2026, 11, 9), 5)},
    )
    second = build_context_snapshot(
        captured_at=datetime(2026, 11, 16, 9, 20, tzinfo=IST),
        stage="0920",
        symbols=["NIFTY"],
        daily_history={"NIFTY": _daily_rows(date(2026, 11, 9), 5)},
    )

    store.write_snapshot(first)
    destination = store.write_snapshot(second)

    record = json.loads(destination.read_text(encoding="utf-8"))
    assert list((tmp_path / "premarket").glob("*.json")) == [destination]
    assert set(record["snapshots"]) == {"0845", "0920"}
    assert store.context_for("NIFTY_CE")["stage"] == "0920"
    assert store.completed_stages(date(2026, 11, 16)) == {"0845", "0920"}


def test_capture_fetches_spot_daily_history_and_available_vix(tmp_path):
    now = datetime(2026, 11, 16, 9, 20, tzinfo=IST)
    daily = _daily_rows(date(2026, 11, 9), 5)
    vix = [
        {
            "date": datetime(2026, 11, 13, tzinfo=IST),
            "open": 14,
            "high": 15,
            "low": 13,
            "close": 14,
        }
    ]
    intraday = [
        {
            "date": datetime(2026, 11, 16, 9, 15, tzinfo=IST),
            "open": 107,
            "high": 108,
            "low": 106,
            "close": 107.5,
        }
    ]
    client = Mock()
    client.instruments.return_value = [
        {
            "tradingsymbol": "NIFTY 50",
            "name": "NIFTY 50",
            "instrument_token": 111,
        },
        {
            "tradingsymbol": "INDIA VIX",
            "name": "INDIA VIX",
            "instrument_token": 222,
        },
    ]

    def historical_data(token, from_date, to_date, interval):
        assert from_date < to_date
        if token == 111 and interval == "day":
            return daily
        if token == 111 and interval == "5minute":
            return intraday
        if token == 222 and interval == "day":
            return vix
        raise AssertionError(f"Unexpected history request: {token}, {interval}")

    client.historical_data.side_effect = historical_data
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "options_underlyings": ["NIFTY"],
        "futures_underlyings": [],
        "instrument_tokens": {},
    }
    bot.kite_stream = SimpleNamespace(kite=client, contract_symbols={})
    bot.latest_prices = {"NIFTY": 108}
    bot.premarket_context_store = PremarketContextStore(tmp_path / "premarket")
    bot.telegram_notifier = Mock()

    snapshot = bot._capture_premarket_context("0920", now)

    assert snapshot["underlyings"]["NIFTY"]["gap_vs_prior_close_pct"] == pytest.approx(
        (107 / 105 - 1) * 100
    )
    assert snapshot["india_vix"]["prior_close"] == 14
    assert client.historical_data.call_count == 3
    assert (tmp_path / "premarket" / "2026-11-16.json").is_file()
    bot.telegram_notifier.send_message.assert_not_called()


def test_schedule_is_paper_only_once_per_stage_and_fails_open():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"premarket_context_v1": True}
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot._premarket_context_attempts = {}
    bot.premarket_context_store = Mock()
    bot.premarket_context_store.completed_stages.return_value = set()
    bot._capture_premarket_context = Mock(
        side_effect=[RuntimeError("history unavailable"), {}, {}]
    )

    bot._run_premarket_context_if_due(datetime(2026, 11, 16, 8, 44, tzinfo=IST))
    bot._run_premarket_context_if_due(datetime(2026, 11, 16, 8, 45, tzinfo=IST))
    bot._run_premarket_context_if_due(datetime(2026, 11, 16, 9, 20, tzinfo=IST))
    bot._run_premarket_context_if_due(datetime(2026, 11, 16, 10, 30, tzinfo=IST))
    bot._run_premarket_context_if_due(datetime(2026, 11, 16, 10, 31, tzinfo=IST))

    assert [call.args[0] for call in bot._capture_premarket_context.call_args_list] == [
        "0845", "0920", "1030"
    ]

    bot.config["premarket_context_v1"] = False
    bot._run_premarket_context_if_due(datetime(2026, 11, 17, 8, 45, tzinfo=IST))
    assert bot._capture_premarket_context.call_count == 3
    bot.config["premarket_context_v1"] = True
    bot.paper_trading_enabled = False
    bot._run_premarket_context_if_due(datetime(2026, 11, 18, 8, 45, tzinfo=IST))
    assert bot._capture_premarket_context.call_count == 3


def test_context_is_attached_to_trade_decision_and_rejection_rows(tmp_path):
    context = {
        "version": "premarket_context_v1",
        "status": "available",
        "underlying": "NIFTY",
        "average_range_pct_5_sessions": 1.25,
    }
    trade_journal = TradeJournal(
        str(tmp_path / "trades.jsonl"),
        str(tmp_path / "paper"),
        git_sha="test",
        git_dirty=False,
    )
    trade_journal.premarket_context_provider = Mock(return_value=context)
    trade_journal.log_trade(
        {
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "entry": 100,
            "timestamp": "2026-11-16T09:30:00+05:30",
        }
    )
    trade = json.loads(
        (tmp_path / "trades.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    [trade_row] = trade_journal.paper_recorder._read_parquet(
        next((tmp_path / "paper").glob("**/trades.parquet"))
    )
    assert trade["premarket_context_v1"] == context
    assert json.loads(trade_row["premarket_context_v1"]) == context

    decision_path = tmp_path / "decision_log.jsonl"
    decision_journal = DecisionJournal(str(decision_path))
    decision_journal.premarket_context_provider = Mock(return_value=context)
    decision_journal.log_decision(
        {
            "event": "bar_decision",
            "ticker": "NIFTY_CE",
            "signal": "BUY",
            "outcome": "accuracy_filter_rejected:volatility",
            "score": 60,
            "timestamp": "2026-11-16T09:30:00+05:30",
            "forward_reference_time": "2026-11-16T09:30:00+05:30",
        }
    )
    decision = json.loads(
        decision_path.read_text(encoding="utf-8").splitlines()[0]
    )
    rejected = json.loads(
        (tmp_path / "rejected_signals.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert decision["premarket_context_v1"] == context
    assert rejected["premarket_context_v1"] == context
    trade_journal.paper_recorder.close_decisions()
    decision_journal.close()


@pytest.mark.parametrize(
    ("month", "week", "day"),
    [(11, 46, 12), (11, 46, 13), (11, 47, 16)],
)
def test_archived_decision_replay_preserves_decision_fields(
    tmp_path, month, week, day
):
    repo_root = Path(__file__).resolve().parents[1]
    session_dir = (
        repo_root
        / "paper_trading_data"
        / f"2026-{month:02d}"
        / f"week_{week}"
        / f"day_{day:02d}"
        / "decisions"
    )
    decision_files = sorted(session_dir.glob("decisions_*.parquet"))
    assert decision_files, f"Archived replay is missing: {session_dir}"
    source_rows = []
    for decision_file in decision_files:
        frame = pd.read_parquet(
            decision_file,
            columns=["timestamp", "ticker", "signal", "outcome", "score", "event"],
        )
        source_rows.extend(
            frame.loc[frame["event"].astype(str).eq("bar_decision")].to_dict(
                orient="records"
            )
        )
    assert source_rows

    journal_path = tmp_path / f"replayed-{day}.jsonl"
    journal = DecisionJournal(str(journal_path))
    journal.premarket_context_provider = lambda ticker: {
        "version": "premarket_context_v1",
        "status": "available",
        "underlying": str(ticker).split("_", 1)[0],
    }
    for row in source_rows:
        journal.log_decision(row)
    assert journal.close()
    replayed_rows = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
    ]

    assert len(replayed_rows) == len(source_rows)
    for source, replayed in zip(source_rows, replayed_rows):
        assert replayed["timestamp"] == str(source["timestamp"])
        assert replayed["ticker"] == source["ticker"]
        assert replayed["signal"] == source["signal"]
        assert replayed["outcome"] == source["outcome"]
        assert replayed["score"] == source["score"]
        assert replayed["event"] == source["event"]
        assert replayed["premarket_context_v1"]["version"] == "premarket_context_v1"
