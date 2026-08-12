import random

from market_bot.engine import score_market
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
