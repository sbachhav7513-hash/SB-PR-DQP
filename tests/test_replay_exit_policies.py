from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from tools import replay_exit_policies as replay


IST = ZoneInfo("Asia/Kolkata")


def _args():
    return SimpleNamespace(
        slippage=0.0,
        brokerage_per_order=0.0,
        stt_rate=0.0,
        exchange_rate=0.0,
        sebi_rate=0.0,
        stamp_rate=0.0,
        gst_rate=0.0,
    )


def _trade():
    entry_time = datetime(2026, 10, 28, 9, 15, tzinfo=IST)
    return {
        "trade_id": "trade-1",
        "ticker": "NIFTY_CE",
        "entry": 100.0,
        "stop_loss": 90.0,
        "quantity": 1.0,
        "_entry_time_parsed": entry_time,
    }


def _bar(start, high, low, close):
    return {
        "time": start,
        "open": 100.0,
        "high": high,
        "low": low,
        "close": close,
    }


def _quote(timestamp, bid, ask=None):
    return {
        "time": timestamp,
        "bid": bid,
        "ask": ask if ask is not None else bid + 0.2,
    }


def test_p4_columns_and_summary_use_only_eligible_trades():
    trades = [
        {"trade_id": "eligible"},
        {"trade_id": "not-eligible"},
    ]
    replays = {
        ("eligible", "P4_50"): replay.Replay(
            "P4_50", 10.0, 9.0, 0.9, 109.0, None, "partial", 1.0, True
        ),
        ("not-eligible", "P4_50"): replay.Replay(
            "P4_50", 50.0, 49.0, 4.9, 149.0, None, "partial", 1.0, True
        ),
    }
    eligible = {"eligible"}

    column_values = [
        replay.p4_column_result(trade, replays, eligible, "P4_50")
        for trade in trades
    ]
    summary, displayed_count = replay.p4_summary(
        trades, replays, eligible, "P4_50"
    )

    assert column_values == [replays[("eligible", "P4_50")], None]
    assert displayed_count == summary["n"] == 1
    assert summary["net"] == 9.0


def test_close_confirmation_ignores_wick_and_fills_next_sampled_bid():
    start = _trade()["_entry_time_parsed"]
    candles = [
        _bar(start, 120.0, 111.0, 115.0),
        _bar(start + timedelta(minutes=1), 112.0, 104.0, 106.0),
        _bar(start + timedelta(minutes=2), 111.0, 103.0, 104.0),
    ]
    quotes = [
        _quote(start + timedelta(minutes=3), 103.0),
        _quote(start.replace(hour=15, minute=29), 110.0),
    ]

    result = replay.simulate_policy(
        _trade(),
        candles,
        quotes,
        _args(),
        "close_confirm",
        runner_gap=1.5,
        close_confirm=True,
    )

    assert result.complete
    assert result.exit_reason == "runner_stop"
    assert result.exit_price == 103.0
    assert result.exit_time == start + timedelta(minutes=3)


def test_profit_lock_is_immediate_and_initial_stop_wins_same_candle():
    start = _trade()["_entry_time_parsed"]
    profit_lock_result = replay.simulate_policy(
        _trade(),
        [_bar(start, 105.0, 101.0, 102.0)],
        [_quote(start + timedelta(seconds=30), 101.5)],
        _args(),
        "profit_lock",
        profit_lock_r=0.15,
        close_confirm=True,
    )
    assert profit_lock_result.complete
    assert profit_lock_result.exit_reason == "profit_lock"
    assert profit_lock_result.exit_price == 101.5

    initial_stop_result = replay.simulate_policy(
        _trade(),
        [_bar(start, 120.0, 85.0, 108.0)],
        [_quote(start + timedelta(seconds=30), 90.0)],
        _args(),
        "same_candle",
        runner_gap=1.5,
        close_confirm=True,
    )
    assert initial_stop_result.complete
    assert initial_stop_result.exit_reason == "initial_stop"
    assert initial_stop_result.exit_price == 90.0


def test_two_consecutive_bid_variant_and_half_spread_cost_inputs():
    start = _trade()["_entry_time_parsed"]
    candles = [
        _bar(start, 120.0, 111.0, 115.0),
        _bar(start + timedelta(minutes=1), 112.0, 104.0, 110.0),
    ]
    quotes = [
        _quote(start + timedelta(minutes=1, seconds=10), 104.8),
        _quote(start + timedelta(minutes=1, seconds=20), 104.6),
        _quote(start + timedelta(minutes=2), 104.5),
    ]

    result = replay.simulate_policy(
        _trade(),
        candles,
        quotes,
        _args(),
        "two_bids",
        runner_gap=1.5,
        close_confirm=True,
        two_consecutive_bids=True,
    )

    assert result.complete
    assert result.exit_reason == "runner_stop"
    assert result.exit_price == 104.5
    assert replay.measured_half_spread_rate([_quote(start, 99.0, 101.0)]) == 0.01
