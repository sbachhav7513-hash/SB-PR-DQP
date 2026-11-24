from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import market_bot.index_edge_study as index_edge_study
from market_bot.index_edge_study import (
    _score_base_candidates,
    _threshold_signals,
    paper_trade_costs,
    study_underlying,
)


IST = ZoneInfo("Asia/Kolkata")


def _session(day, close_values):
    start = datetime.combine(day, datetime.min.time(), IST).replace(
        hour=9, minute=15
    )
    return [
        {
            "time": start + timedelta(minutes=index),
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": 0,
        }
        for index, close in enumerate(close_values)
    ]


def test_study_splits_days_and_reports_threshold_sweep():
    candles = []
    for offset in range(10):
        day = date(2026, 1, 5) + timedelta(days=offset)
        close_values = [100 + index * (0.1 if offset % 2 == 0 else -0.1)
                        for index in range(130)]
        candles.extend(_session(day, close_values))

    result = study_underlying(candles, bootstrap_iterations=50, seed=5)

    assert len(result["train_days"]) == 7
    assert len(result["oos_days"]) == 3
    assert [row["percentile"] for row in result["train"]] == [
        50, 60, 70, 80, 90, 95
    ]
    assert len(result["oos"]) == 6


def test_base_candidates_use_score_market_with_regime_gate_disabled(monkeypatch):
    candles = _session(
        date(2026, 1, 5),
        [100 + index * 0.1 for index in range(50)],
    )
    measurements = [
        {
            "day": date(2026, 1, 5),
            "time": candle["time"],
            "strength": 0.02,
            "direction": 1,
            "forward": {15: 0.001, 30: 0.002},
        }
        for candle in candles[19:]
    ]
    calls = []

    def fake_score_market(ticker, history, **kwargs):
        calls.append((ticker, kwargs))
        return SimpleNamespace(signal="BUY")

    monkeypatch.setattr(index_edge_study, "score_market", fake_score_market)

    candidates = _score_base_candidates(
        candles, measurements, 0.01, "NIFTY", {}
    )

    assert candidates
    assert all(candidate["direction"] == 1 for candidate in candidates)
    assert calls[0][0] == "NIFTY"
    assert calls[0][1]["min_trend_strength"] == 0.01
    assert calls[0][1]["trend_momentum_bonus_threshold"] == 0.01
    assert calls[0][1]["regime_hard_filter_overrides"] == {"NIFTY": False}


def test_same_direction_cooldown_does_not_remove_opposite_direction():
    day = date(2026, 1, 5)
    signals = _threshold_signals(
        [
            {"day": day, "time": datetime(2026, 1, 5, 9, 15, tzinfo=IST),
             "strength": 0.02, "direction": 1},
            {"day": day, "time": datetime(2026, 1, 5, 9, 20, tzinfo=IST),
             "strength": 0.03, "direction": 1},
            {"day": day, "time": datetime(2026, 1, 5, 9, 25, tzinfo=IST),
             "strength": 0.02, "direction": -1},
        ],
        [day],
        0.01,
    )

    assert [item["direction"] for item in signals] == [1, -1]


def test_paper_trade_cost_includes_modeled_fees_and_round_trip_spread():
    costs = paper_trade_costs(
        [
            {
                "status": "closed",
                "ticker": "NIFTY_CE",
                "fill_premium": 100,
                "entry_quantity": 50,
                "fees_rupees": 100,
                "fill_bid": 99,
                "fill_ask": 101,
                "paper_exit_bid": 109,
                "paper_exit_ask": 111,
            }
        ]
    )

    assert costs["NIFTY"]["trades_used"] == 1
    assert costs["NIFTY"]["mean_pct"] == 4.0
    assert costs["BANKNIFTY"]["mean_pct"] is None
