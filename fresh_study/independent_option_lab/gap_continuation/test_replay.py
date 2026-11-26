from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from replay import daily_atr_table, make_gap_signal, simulate_option


def minute_bars(prices):
    timestamps = pd.date_range(
        "2026-01-05 09:15",
        periods=len(prices),
        freq="min",
        tz="Asia/Kolkata",
    ).tz_convert("UTC")
    return pd.DataFrame(
        {
            "ts": timestamps,
            "open": [row[0] for row in prices],
            "high": [row[1] for row in prices],
            "low": [row[2] for row in prices],
            "close": [row[3] for row in prices],
        }
    )


def test_gap_signal_accepts_moderate_gap_with_directional_confirmation():
    bars = minute_bars(
        [
            (101, 101.2, 100.9, 101.1),
            (101.1, 101.4, 101.0, 101.3),
            (101.3, 101.6, 101.2, 101.5),
            (101.5, 101.8, 101.4, 101.7),
            (101.7, 102.0, 101.6, 101.9),
            (101.9, 102.1, 101.8, 102.0),
        ]
    )

    signal = make_gap_signal(
        bars,
        prior_close=100,
        prior_atr=4,
        confirmation_minutes=5,
        gap_atr_min=0.25,
        gap_atr_max_exclusive=0.75,
        minimum_confirmation_to_gap_ratio=0.0,
    )

    assert signal is not None
    assert signal.side == 1
    assert signal.entry_index == 5
    assert signal.gap_atr == pytest.approx(0.25)
    assert signal.confirmation_ratio > 0.5


def test_gap_signal_rejects_out_of_band_gap_reversal_and_missing_open_bar():
    bars = minute_bars(
        [
            (105, 105.1, 104.9, 105),
            (105, 105.1, 104.9, 105),
            (105, 105.1, 104.9, 105),
            (105, 105.1, 104.9, 105),
            (105, 105.1, 104.9, 105),
            (105, 105.1, 104.9, 105),
        ]
    )
    kwargs = {
        "prior_close": 100,
        "prior_atr": 10,
        "confirmation_minutes": 5,
        "gap_atr_min": 0.25,
        "gap_atr_max_exclusive": 0.75,
        "minimum_confirmation_to_gap_ratio": 0.0,
    }
    assert make_gap_signal(bars, **kwargs) is None  # Confirmation ratio is zero.

    weak_positive_confirmation = bars.copy()
    weak_positive_confirmation["close"] = weak_positive_confirmation[
        "close"
    ].astype(float)
    weak_positive_confirmation.loc[4, "close"] = 105.01
    assert make_gap_signal(weak_positive_confirmation, **kwargs) is not None

    large_gap_kwargs = dict(kwargs, prior_atr=4)
    assert make_gap_signal(bars, **large_gap_kwargs) is None

    missing = weak_positive_confirmation.copy()
    missing.loc[1, "ts"] += pd.Timedelta(minutes=1)
    assert make_gap_signal(missing, **kwargs) is None


def test_daily_atr_uses_only_completed_prior_sessions():
    sessions = []
    for index in range(23):
        day = pd.Timestamp("2026-01-01") + pd.Timedelta(days=index)
        close = 100.0 + index
        frame = pd.DataFrame(
            {
                "open": [close],
                "high": [close + 2],
                "low": [close - 2],
                "close": [close],
            }
        )
        sessions.append((day.date(), frame))

    table = daily_atr_table(sessions, lookback=20)

    assert pd.isna(table.iloc[19]["atr"])
    assert table.iloc[20]["atr"] == pytest.approx(4.0)
    assert table.iloc[21]["previous_close"] == pytest.approx(120.0)


def test_option_replay_requires_aligned_candles():
    options = minute_bars([(100, 100, 100, 100), (100, 100, 100, 100)])
    spot = options.copy()
    spot.loc[1, "ts"] += pd.Timedelta(minutes=1)

    from replay import GapSignal

    signal = GapSignal(4, 5, 1, 100, 0.4, 0.004, 0.003, 0.75)
    with pytest.raises(ValueError, match="timestamps must align"):
        simulate_option(
            options,
            spot,
            signal,
            prior_atr=4,
            underlying_stop_atr=0.25,
            option_stop_pct=5,
            fee_per_side_pct=0.25,
            policy="take5",
            max_holding_minutes=120,
            trailing_activation_pct=5,
            trailing_distance_pct=3,
            option_target_pct=5,
        )
