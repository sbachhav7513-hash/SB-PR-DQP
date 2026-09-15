import random
from datetime import datetime, timedelta

from market_bot.bar_builder import Bar, BarBuilder
from market_bot.engine import (
    filter_signal_by_context,
    market_context_signal,
    market_session_state,
    score_market,
)
from market_bot.strategy import analyze_history


def test_conservative_buy_signal_is_rejected_when_price_is_below_trend():
    history = [
        {"close": 100.0},
        {"close": 99.5},
        {"close": 99.0},
        {"close": 98.5},
        {"close": 98.0},
        {"close": 97.5},
        {"close": 97.0},
        {"close": 96.5},
        {"close": 96.0},
        {"close": 95.5},
        {"close": 95.0},
        {"close": 94.5},
        {"close": 94.0},
        {"close": 93.5},
        {"close": 93.0},
        {"close": 92.5},
        {"close": 92.0},
        {"close": 91.5},
        {"close": 91.0},
        {"close": 90.5},
        {"close": 90.0},
        {"close": 89.5},
        {"close": 89.0},
        {"close": 88.5},
        {"close": 88.0},
        {"close": 87.5},
        {"close": 87.0},
        {"close": 86.5},
        {"close": 86.0},
        {"close": 85.5},
        {"close": 85.0},
        {"close": 84.5},
        {"close": 84.0},
        {"close": 83.5},
        {"close": 83.0},
        {"close": 82.5},
        {"close": 82.0},
        {"close": 81.5},
        {"close": 81.0},
        {"close": 80.5},
        {"close": 80.0},
    ]

    signal = analyze_history(
        ticker="TEST",
        history=history,
        ema_fast=9,
        ema_slow=21,
        rsi_period=14,
        alert_rsi_low=30,
        alert_rsi_high=70,
    )

    assert signal is None


def test_weak_noisy_uptrend_does_not_trigger_buy_signal():
    random.seed(0)
    history = []
    current = 100.0
    for _ in range(80):
        current += random.uniform(-0.2, 0.2)
        history.append({"close": current})

    result = score_market("TEST", history)

    assert result.signal == "HOLD"
    assert result.score < 80


def test_bearish_benchmark_does_not_hard_block_a_buy_signal():
    benchmark_history = [{"close": 200.0 - index} for index in range(40)]

    signal, reason = filter_signal_by_context("BUY", benchmark_history)

    assert market_context_signal(benchmark_history) == "BEARISH"
    assert signal == "BUY"
    assert reason == "Benchmark trend bearish (soft context warning)"


def test_before_open_data_should_not_trigger_trade_signal():
    before_open_history = [
        {"time": datetime(2026, 9, 15, 9, 0, 0), "close": 100.0 + index * 0.8}
        for index in range(60)
    ]

    assert market_session_state(before_open_history) == "BEFORE_OPEN"

    result = score_market("TEST", before_open_history)

    assert result.signal == "HOLD"
    assert "before open" in result.reasons[0].lower()


def test_regular_session_data_can_trigger_buy_signal():
    regular_history = [
        {"time": datetime(2026, 9, 15, 9, 30 + index // 10, 0), "close": 100.0 + index * 1.2}
        for index in range(60)
    ]

    assert market_session_state(regular_history) == "REGULAR_SESSION"

    result = score_market("TEST", regular_history)

    assert result.signal == "BUY"
    assert result.score >= 60


def test_strong_bullish_trend_should_generate_buy_signal():
    history = [{"close": 100.0 + index * 1.2} for index in range(60)]

    result = score_market("TEST", history)

    assert result.signal == "BUY"
    assert result.score >= 60


def test_before_open_data_can_be_scored_for_premarkarket_signal():
    before_open_history = [
        {"time": datetime(2026, 9, 15, 8, 45 + index // 10, 0), "close": 100.0 + index * 1.2}
        for index in range(60)
    ]

    result = score_market("TEST", before_open_history, allow_before_open=True)

    assert result.signal == "BUY"
    assert result.score >= 60


def test_score_market_ignores_stale_previous_day_bars():
    today = datetime(2026, 9, 15, 9, 30)
    yesterday = today - timedelta(days=1)
    stale = [
        {"time": yesterday + timedelta(minutes=index), "close": 100.0 + index * 0.2}
        for index in range(30)
    ]
    fresh = [
        {"time": today + timedelta(minutes=index), "close": 100.0 + index * 1.3}
        for index in range(30)
    ]

    result = score_market("TEST", stale + fresh)

    assert result.signal == "BUY"
    assert result.score >= 60
