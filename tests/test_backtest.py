import pytest
from datetime import datetime, timedelta

from market_bot.backtest import run_backtest
from market_bot.engine import TradingScore
from market_bot.replay import (
    _context_before,
    load_candles,
    prepare_production_candles,
    run_replay,
    _zero_signal_diagnostics,
    validate_production_data,
)


def candle(open_price, high, low, close, index):
    return {
        "time": index,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def test_backtest_enters_on_next_open_and_takes_target():
    history = [
        candle(100, 101, 99, 100, 0),
        candle(110, 112, 109, 111, 1),
        candle(111, 113, 110, 112, 2),
    ]

    def buy_signal(ticker, previous_candles):
        action = "BUY" if len(previous_candles) == 1 else "HOLD"
        return TradingScore(ticker, 90, action)

    result = run_backtest(
        "TEST",
        history,
        stop_loss_pct=1,
        take_profit_pct=1,
        signal_fn=buy_signal,
    )

    assert len(result.trades) == 1
    assert result.trades[0].entry_price == 110
    assert result.trades[0].exit_price == 111.1
    assert result.trades[0].exit_reason == "TAKE_PROFIT"


def test_backtest_uses_stop_when_stop_and_target_hit_same_bar():
    history = [
        candle(100, 100, 100, 100, 0),
        candle(100, 102, 98, 100, 1),
    ]

    result = run_backtest(
        "TEST",
        history,
        stop_loss_pct=1,
        take_profit_pct=1,
        signal_fn=lambda ticker, previous: TradingScore(ticker, 90, "BUY"),
    )

    assert result.trades[0].exit_reason == "STOP_LOSS"
    assert result.trades[0].return_pct == -1


def test_backtest_skips_malformed_candles():
    result = run_backtest("TEST", [{"close": 100}, {"open": "bad"}])

    assert result.trades == []


def test_backtest_counts_entry_filter_rejections():
    history = [
        candle(100, 100.5, 99.5, 100, 0),
        candle(100, 100.5, 99.5, 100, 1),
    ]

    result = run_backtest(
        "TEST",
        history,
        signal_fn=lambda ticker, previous: TradingScore(ticker, 90, "BUY"),
        entry_filter=lambda ticker, decision, previous: "score<95",
    )

    assert result.trades == []
    assert result.rejection_counts == {"score<95": 1}
    assert result.signal_counts == {"BUY": 1}


def test_backtest_deducts_round_trip_fee_and_slippage():
    history = [
        candle(100, 100, 100, 100, 0),
        candle(100, 102, 99.5, 101, 1),
    ]

    result = run_backtest(
        "TEST",
        history,
        stop_loss_pct=2,
        take_profit_pct=1,
        signal_fn=lambda ticker, previous: TradingScore(ticker, 90, "BUY"),
        fee_bps_per_side=10,
        slippage_bps_per_side=5,
    )

    assert result.trades[0].gross_return_pct == 1
    assert result.trades[0].cost_pct == 0.3
    assert abs(result.trades[0].return_pct - 0.7) < 1e-9


def test_backtest_flattens_open_position_at_market_close():
    history = [
        {
            **candle(100, 100.2, 99.8, 100, index),
            "time": f"2026-09-28T15:{minute}:00+05:30",
        }
        for index, minute in enumerate((12, 13, 14, 15))
    ]
    result = run_backtest(
        "TEST",
        history,
        signal_fn=lambda ticker, previous: TradingScore(
            ticker, 90, "BUY" if len(previous) == 1 else "HOLD"
        ),
        market_close_time="15:15",
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "MARKET_CLOSE"
    assert result.trades[0].exit_time == history[-1]["time"]


def test_backtest_enforces_one_entry_per_session():
    history = [
        {
            **candle(100, high, 99.8, 100, index),
            "time": f"2026-09-28T10:0{index}:00+05:30",
        }
        for index, high in enumerate((100.2, 102, 100.2, 102))
    ]
    result = run_backtest(
        "TEST",
        history,
        stop_loss_pct=1,
        take_profit_pct=1,
        signal_fn=lambda ticker, previous: TradingScore(
            ticker, 90, "BUY" if len(previous) in {1, 2, 3} else "HOLD"
        ),
        max_trades_per_session=1,
    )

    assert len(result.trades) == 1
    assert result.rejection_counts == {"session_trade_limit": 2}


def test_backtest_trailing_stop_closes_after_activation():
    history = [
        candle(100, 100.2, 99.8, 100, 0),
        candle(100, 103, 99.8, 102, 1),
        candle(102, 102.5, 101.5, 102, 2),
    ]
    result = run_backtest(
        "TEST",
        history,
        stop_loss_pct=5,
        take_profit_pct=4,
        signal_fn=lambda ticker, previous: TradingScore(
            ticker, 90, "BUY" if len(previous) == 1 else "HOLD"
        ),
        trailing_enabled=True,
        trailing_activation_ratio=0.5,
        trailing_distance_ratio=0.25,
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "TRAILING_STOP"
    assert result.trades[0].exit_price == 102


def test_backtest_limits_signal_history_to_live_window():
    history = [candle(100, 101, 99, 100, index) for index in range(8)]
    observed_lengths = []

    def hold_signal(ticker, previous):
        observed_lengths.append(len(previous))
        return TradingScore(ticker, 0, "HOLD")

    run_backtest("TEST", history, signal_fn=hold_signal, history_limit=3)

    assert observed_lengths == [1, 2, 3, 3, 3, 3, 3]


def test_replay_benchmark_context_matches_live_100_bar_limit():
    from datetime import datetime, timedelta

    start = datetime(2026, 9, 28, 9, 15)
    bars = [{"time": start + timedelta(minutes=index), "close": 100 + index} for index in range(150)]
    context = _context_before({"NIFTY": bars}, bars[120]["time"])

    assert len(context["NIFTY"]) == 100
    assert context["NIFTY"][0]["close"] == 121
    assert context["NIFTY"][-1]["close"] == 220


def test_strategy_replay_reports_zero_trade_win_rate_as_unavailable():
    history = [
        {
            **candle(100, 100.5, 99.5, 100, index),
            "time": f"2026-09-28T10:{index:02d}:00+05:30",
            "volume": 100,
        }
        for index in range(3)
    ]
    result = run_replay(
        "TEST",
        history,
        {"late_window_enabled": False},
        signal_fn=lambda ticker, previous: TradingScore(ticker, 50, "HOLD", ["test hold"]),
    )

    assert result.trades == []
    assert result.win_rate_pct is None
    assert result.evaluated_bars == 2
    assert result.reason_counts == {"test hold": 2}


def test_replay_loader_sorts_and_normalizes_csv_timestamps(tmp_path):
    path = tmp_path / "bars.csv"
    path.write_text(
        "date,open,high,low,close,volume,bid,ask,last\n"
        "2026-09-28 10:01:00,100,101,99,100.5,150,100.4,100.6,100.5\n"
        "2026-09-28 10:00:00,99,100,98,99.5,120,99.4,99.6,99.5\n",
        encoding="utf-8",
    )

    candles = load_candles(path)

    assert len(candles) == 2
    assert candles[0]["time"].isoformat() == "2026-09-28T10:00:00+05:30"
    assert candles[0]["volume"] == 120
    assert candles[0]["bid"] == 99.4
    assert candles[0]["ask"] == 99.6
    assert candles[0]["last"] == 99.5


def test_strategy_replay_records_accuracy_score_rejection():
    history = [
        {
            **candle(100, 100.5, 99.5, close, index),
            "time": f"2026-09-28T10:0{index}:00+05:30",
            "volume": 100,
        }
        for index, close in enumerate((100, 100.1, 100.2))
    ]
    result = run_replay(
        "TEST",
        history,
        {"late_window_enabled": False, "min_entry_score": 75},
        signal_fn=lambda ticker, previous: TradingScore(
            ticker,
            70,
            "BUY" if len(previous) == 2 else "HOLD",
        ),
    )

    assert result.trades == []
    assert result.rejection_counts == {"score<75": 1}


def test_production_data_validation_reports_gaps_and_zero_volume_rows():
    start = datetime(2026, 3, 1, 9, 15)
    candles = [
        {
            "time": start + timedelta(minutes=index),
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 0 if index == 1 else 10,
            "bid": 99.9,
            "ask": 100.1,
            "last": 100,
        }
        for index in range(3)
    ]
    candles[-1]["time"] = start + timedelta(days=184)

    diagnostics = validate_production_data(
        candles,
        ticker="NIFTY_FUT_20261028",
        expected_symbol="NIFTY_FUT_20261028",
    )

    assert diagnostics["zero_volume_rows"] == 1
    assert diagnostics["gaps"]
    assert diagnostics["history_days"] >= 183
    prepared, prepared_diagnostics = prepare_production_candles(
        candles,
        ticker="NIFTY_FUT_20261028",
        expected_symbol="NIFTY_FUT_20261028",
    )
    assert len(prepared) == 2
    assert prepared_diagnostics["removed_zero_volume_rows"] == 1


def test_production_data_validation_rejects_proxy_symbols_and_sustained_zero_volume():
    start = datetime(2026, 3, 1, 9, 15)
    candles = [
        {
            "time": start + timedelta(days=184, minutes=index),
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 0,
            "bid": 99.9,
            "ask": 100.1,
            "last": 100,
        }
        for index in range(5)
    ]

    with pytest.raises(ValueError, match="does not match required production symbol"):
        validate_production_data(
            candles,
            ticker="NIFTY",
            expected_symbol="NIFTY_FUT_20261028",
        )

    with pytest.raises(ValueError, match="sustained zero volume"):
        validate_production_data(
            candles,
            ticker="NIFTY_FUT_20261028",
            expected_symbol="NIFTY_FUT_20261028",
        )


def test_zero_signal_diagnostics_recommend_without_changing_strategy():
    from market_bot.backtest import BacktestResult

    result = BacktestResult(
        trades=[],
        signal_counts={"HOLD": 12},
        rejection_counts={"volume_filter": 3},
    )

    diagnostics = _zero_signal_diagnostics(result)

    assert diagnostics["zero_signal_diagnostics"] == [
        "no_entry_triggers",
        "volume_filter_too_strict",
    ]
    assert diagnostics["recommended_relaxations"][0]["amount"] == 0.2
    result.signal_counts["BUY"] = 1
    assert _zero_signal_diagnostics(result) == {}