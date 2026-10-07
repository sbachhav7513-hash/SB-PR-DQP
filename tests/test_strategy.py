import random
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from market_bot.bar_builder import Bar, BarBuilder
from market_bot.engine import (
    calculate_adx,
    calculate_atr,
    calculate_vwap,
    breakout_quality,
    classify_price_regime,
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


def test_flat_market_history_is_rejected_by_regime_filter():
    history = [{"close": 100.0 + index * 0.05} for index in range(80)]

    signal = analyze_history(
        ticker="TEST",
        history=history,
        ema_fast=9,
        ema_slow=21,
        rsi_period=14,
        alert_rsi_low=35,
        alert_rsi_high=65,
    )

    assert signal is None


def test_close_only_regime_classifier_identifies_sideways_market():
    history = [100.0 + (index % 2) * 0.1 for index in range(30)]

    assert classify_price_regime(history) == "SIDEWAYS"
    result = score_market("TEST", [{"close": close} for close in history])

    assert result.signal == "HOLD"
    assert "Sideways regime" in result.reasons[0]
    assert "recent range" in result.reasons[0]
    assert "20-bar move" in result.reasons[0]


def test_lower_sideways_net_move_threshold_admits_modest_directional_move():
    step = 0.27 / 19
    closes = [100.0] * 10 + [100.0 + index * step for index in range(20)]

    strict_regime = classify_price_regime(
        closes,
        sideways_range_pct=0.3,
        sideways_net_move_pct=0.3,
    )
    relaxed_regime = classify_price_regime(
        closes,
        sideways_range_pct=0.3,
        sideways_net_move_pct=0.25,
    )

    assert strict_regime == "SIDEWAYS"
    assert relaxed_regime == "TRENDING"


def test_bearish_setup_near_recent_high_does_not_get_proximity_bonus():
    closes = [102.0 - index * 0.05 for index in range(30)]
    closes.extend(
        [100.0, 99.9, 99.8, 100.0, 100.2, 100.3, 100.2, 100.4, 100.49, 100.49]
    )
    history = [{"close": close} for close in closes]
    fast = [100.0] * (len(closes) - 1) + [99.0]
    slow = [100.0] * len(closes)

    with patch("market_bot.engine.ema", side_effect=[fast, slow]), \
        patch("market_bot.engine.rsi", return_value=[40.0] * len(closes)), \
        patch("market_bot.engine.calculate_adx", return_value=None), \
        patch("market_bot.engine.classify_price_regime", return_value="TRENDING"):
        result = score_market("TEST", history, min_trend_strength=0.005)

    assert result.score == 75
    assert result.signal == "HOLD"
    assert "Price near recent high" not in result.reasons


def test_bearish_recent_low_bonus_and_entry_use_same_proximity():
    closes = [100.0] * 21 + [90.0] + [90.5 + index * 0.1 for index in range(9)]
    closes.append(90.36)
    fast = [99.5] * (len(closes) - 1) + [99.0]
    slow = [100.0] * len(closes)

    with patch(
        "market_bot.engine.ema",
        side_effect=lambda values, period: fast if period == 9 else slow,
    ), patch("market_bot.engine.rsi", return_value=[40.0] * len(closes)), \
        patch("market_bot.engine.calculate_adx", return_value=None), \
        patch("market_bot.engine.classify_price_regime", return_value="TRENDING"):
        strict_result = score_market(
            "TEST",
            [{"close": close} for close in closes],
            min_trend_strength=0.005,
            signal_proximity_pct=0.003,
            session_state="REGULAR_SESSION",
        )
        default_result = score_market(
            "TEST",
            [{"close": close} for close in closes],
            min_trend_strength=0.005,
            session_state="REGULAR_SESSION",
        )

    assert strict_result.score == 75
    assert strict_result.signal == "HOLD"
    assert default_result.score == 85
    assert default_result.signal == "SELL"


def test_slightly_wider_proximity_admits_nearby_bearish_setup():
    closes = [100.0] * 21 + [90.0]
    closes.extend(90.5 + index * 0.1 for index in range(9))
    closes.append(90.6)
    fast = [99.5] * (len(closes) - 1) + [99.0]
    slow = [100.0] * len(closes)

    with patch(
        "market_bot.engine.ema",
        side_effect=lambda values, period: fast if period == 9 else slow,
    ), patch("market_bot.engine.rsi", return_value=[40.0] * len(closes)), \
        patch("market_bot.engine.calculate_adx", return_value=None), \
        patch("market_bot.engine.classify_price_regime", return_value="TRENDING"):
        previous_result = score_market(
            "TEST",
            [{"close": close} for close in closes],
            min_trend_strength=0.005,
            signal_proximity_pct=0.005,
            session_state="REGULAR_SESSION",
        )
        relaxed_result = score_market(
            "TEST",
            [{"close": close} for close in closes],
            min_trend_strength=0.005,
            signal_proximity_pct=0.0075,
            session_state="REGULAR_SESSION",
        )

    assert previous_result.signal == "HOLD"
    assert relaxed_result.signal == "SELL"
    assert "Price near recent low" in relaxed_result.reasons


def test_bullish_recent_high_bonus_and_entry_use_same_proximity():
    closes = [90.0] * 21 + [100.0]
    closes.extend([99.8 - index * 0.1 for index in range(9)])
    closes.append(99.6)
    fast = [90.5] * (len(closes) - 1) + [91.0]
    slow = [90.0] * len(closes)

    with patch(
        "market_bot.engine.ema",
        side_effect=lambda values, period: fast if period == 9 else slow,
    ), patch("market_bot.engine.rsi", return_value=[60.0] * len(closes)), \
        patch("market_bot.engine.calculate_adx", return_value=None), \
        patch("market_bot.engine.classify_price_regime", return_value="TRENDING"):
        strict_result = score_market(
            "TEST",
            [{"close": close} for close in closes],
            min_trend_strength=0.005,
            signal_proximity_pct=0.003,
            session_state="REGULAR_SESSION",
        )
        default_result = score_market(
            "TEST",
            [{"close": close} for close in closes],
            min_trend_strength=0.005,
            session_state="REGULAR_SESSION",
        )

    assert strict_result.score == 75
    assert strict_result.signal == "HOLD"
    assert default_result.score == 85
    assert default_result.signal == "BUY"


def test_trend_momentum_bonus_defaults_to_min_trend_strength():
    history = [{"close": 100.0 + index * 0.04} for index in range(40)]

    default_result = score_market(
        "TEST",
        history,
        min_trend_strength=0.005,
        sideways_range_pct=0.1,
        sideways_net_move_pct=0.1,
    )
    explicit_default_result = score_market(
        "TEST",
        history,
        min_trend_strength=0.005,
        trend_momentum_bonus_threshold=0.02,
        sideways_range_pct=0.1,
        sideways_net_move_pct=0.1,
    )

    assert default_result.score == explicit_default_result.score + 12
    assert default_result.signal == "BUY"
    assert explicit_default_result.signal == "HOLD"


def test_compression_breakout_can_pass_sideways_regime_gate():
    history = [
        {
            "open": 100.0 + index * 1.2 + index * index * 0.01,
            "high": 100.5 + index * 1.2 + index * index * 0.01,
            "low": 99.5 + index * 1.2 + index * index * 0.01,
            "close": 100.0 + index * 1.2 + index * index * 0.01,
            "volume": 100,
        }
        for index in range(60)
    ]

    with patch("market_bot.engine.classify_price_regime", return_value="SIDEWAYS"), \
        patch("market_bot.engine.is_compression_breakout", return_value=True), \
        patch("market_bot.engine.breakout_quality", return_value=True), \
        patch("market_bot.engine.calculate_adx", side_effect=[30.0, 20.0]):
        result = score_market("TEST", history, min_adx=0.0)

    assert result.score > 0
    assert "Sideways regime" not in result.reasons


def test_min_adx_threshold_can_admit_setup_at_adx_11():
    history = [{"close": 100.0 + index * 0.1} for index in range(40)]

    with patch("market_bot.engine.calculate_adx", return_value=11.5):
        rejected = score_market(
            "TEST",
            history,
            min_adx=12.0,
            min_trend_strength=0.005,
            sideways_range_pct=0.1,
            sideways_net_move_pct=0.1,
        )
        admitted = score_market(
            "TEST",
            history,
            min_adx=11.0,
            min_trend_strength=0.005,
            sideways_range_pct=0.1,
            sideways_net_move_pct=0.1,
        )

    assert rejected.signal == "HOLD"
    assert "ADX too weak (11.5 < 12.0)" in rejected.reasons
    assert admitted.signal == "BUY"


def test_close_only_regime_classifier_rejects_single_bar_exhaustion():
    history = [100.0 + index * 0.1 for index in range(29)]
    history.append(105.0)

    assert classify_price_regime(history) == "EXTENDED"
    result = score_market("TEST", [{"close": close} for close in history])

    assert result.signal == "HOLD"
    assert "Extended move" in result.reasons[0]


def test_breakout_quality_requires_close_volume_and_atr_sized_candle():
    history = [
        {
            "open": 100.0,
            "high": 100.4,
            "low": 99.6,
            "close": 100.0,
            "volume": 100,
        }
        for _ in range(35)
    ]
    history.append(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 100.0,
            "close": 100.8,
            "volume": 250,
        }
    )

    assert abs(calculate_atr(history[:-1]) - 0.8) < 1e-9
    assert breakout_quality(history, "BUY") is True

    history[-1]["close"] = 100.2
    assert breakout_quality(history, "BUY") is False


def test_zero_index_volume_can_use_separate_option_relative_volume():
    history = [
        {
            "open": 100.0,
            "high": 100.4,
            "low": 99.6,
            "close": 100.0,
            "volume": 0,
        }
        for _ in range(35)
    ]
    history.append(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 100.0,
            "close": 100.8,
            "volume": 0,
        }
    )
    option_volume_history = [{"volume": 100}] * 35 + [{"volume": 250}]

    assert breakout_quality(history, "BUY") is False
    assert breakout_quality(
        history, "BUY", volume_history=option_volume_history
    ) is True
    assert breakout_quality(
        history, "BUY", volume_history=option_volume_history[:-1]
    ) is False


def test_vwap_is_available_for_volume_weighted_direction_check():
    history = [
        {
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 100,
        },
        {
            "high": 103.0,
            "low": 101.0,
            "close": 102.0,
            "volume": 300,
        },
    ]

    assert calculate_vwap(history, period=2) == 101.5


def test_bearish_benchmark_does_not_hard_block_a_buy_signal():
    benchmark_history = [{"close": 200.0 - index} for index in range(40)]

    signal, reason = filter_signal_by_context("BUY", benchmark_history)

    assert market_context_signal(benchmark_history) == "BEARISH"
    assert signal == "BUY"
    assert reason == "Benchmark trend bearish (soft context warning)"


def test_hard_context_filter_blocks_buy_against_bearish_benchmark():
    symbol_history = [{"close": 100.0 + index * 1.2} for index in range(60)]
    benchmark_history = [{"close": 200.0 - index * 1.2} for index in range(60)]

    result = score_market(
        "TEST",
        symbol_history,
        context_history=benchmark_history,
        hard_context_filter=True,
    )

    assert result.signal == "HOLD"
    assert "BUY blocked" in " ".join(result.reasons)


def test_adx_rejects_flat_ohlc_and_accepts_directional_ohlc():
    flat_history = [
        {"high": 100.1, "low": 99.9, "close": 100.0}
        for _ in range(40)
    ]
    rising_history = [
        {
            "high": 100.5 + index * 1.2,
            "low": 99.5 + index * 1.2,
            "close": 100.0 + index * 1.2,
        }
        for index in range(40)
    ]

    assert calculate_adx(flat_history) < 18.0
    assert calculate_adx(rising_history) >= 18.0


def test_before_open_data_should_not_trigger_trade_signal():
    before_open_history = [
        {"time": datetime(2026, 9, 15, 9, 0, 0), "close": 100.0 + index * 0.8}
        for index in range(60)
    ]

    assert market_session_state(before_open_history) == "BEFORE_OPEN"

    result = score_market("TEST", before_open_history)

    assert result.signal == "HOLD"
    assert "before open" in result.reasons[0].lower()


def test_live_session_state_uses_current_ist_clock_for_stale_bar_timestamps():
    stale_history = [
        {"time": datetime(2026, 9, 22, 9, 0, 0), "close": 100.0 + index * 1.2}
        for index in range(60)
    ]

    assert (
        market_session_state(stale_history, now=datetime(2026, 9, 22, 10, 0, 0))
        == "REGULAR_SESSION"
    )
    result = score_market(
        "TEST",
        stale_history,
        session_state="REGULAR_SESSION",
    )

    assert result.signal == "BUY"
    assert "before open" not in " ".join(result.reasons).lower()


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
