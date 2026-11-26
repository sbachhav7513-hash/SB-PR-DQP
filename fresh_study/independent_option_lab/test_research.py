from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from research import detect_signal, simulate_option_trade


def bars(rows):
    return pd.DataFrame(
        rows,
        columns=["ts", "open", "high", "low", "close"],
    ).assign(ts=lambda frame: pd.to_datetime(frame["ts"], utc=True))


def test_breakout_signal_enters_on_following_minute_not_breakout_close():
    frame = bars(
        [
            ("2026-01-01T03:45:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:46:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:47:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:48:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:49:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:50:00Z", 101, 103, 100, 102),
            ("2026-01-01T03:51:00Z", 102, 104, 101, 103),
        ]
    )

    signal = detect_signal(
        frame,
        opening_range_minutes=5,
        setup="breakout",
    )

    assert signal is not None
    assert signal.signal_index == 5
    assert signal.entry_index == 6
    assert signal.side == 1


def test_failed_breakout_reversal_invalidation_tracks_original_break_level():
    frame = bars(
        [
            ("2026-01-01T03:45:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:46:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:47:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:48:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:49:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:50:00Z", 101, 103, 100, 102),
            ("2026-01-01T03:51:00Z", 101, 102, 99, 100),
            ("2026-01-01T03:52:00Z", 100, 101, 99, 100),
        ]
    )

    signal = detect_signal(
        frame,
        opening_range_minutes=5,
        setup="failed_breakout_reversal",
    )

    assert signal is not None
    assert signal.side == -1
    assert signal.invalidation == "resume_up"
    assert signal.entry_index == 7


def test_failed_upper_break_does_not_invalidate_put_inside_opening_range():
    option = bars(
        [
            ("2026-01-01T03:50:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:51:00Z", 100, 102, 99, 101),
            ("2026-01-01T03:52:00Z", 110, 111, 109, 110),
        ]
    )
    spot = bars(
        [
            ("2026-01-01T03:50:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:51:00Z", 101, 102, 100, 101),
            ("2026-01-01T03:52:00Z", 103, 104, 102, 103),
        ]
    )

    outcome = simulate_option_trade(
        option,
        spot,
        side=-1,
        range_high=102,
        range_low=98,
        invalidation="resume_up",
        policy="take10",
        fee_per_side=0.0,
    )

    assert outcome["exit_reason"] == "underlying_invalidation_at_close"
    assert outcome["exit_premium"] == pytest.approx(110)


def test_same_candle_stop_and_target_uses_stop_first():
    option = bars(
        [
            ("2026-01-01T03:50:00Z", 100, 111, 90, 100),
            ("2026-01-01T03:51:00Z", 100, 100, 99, 100),
        ]
    )
    spot = bars(
        [
            ("2026-01-01T03:50:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:51:00Z", 100, 101, 99, 100),
        ]
    )

    outcome = simulate_option_trade(
        option,
        spot,
        side=1,
        range_high=105,
        range_low=95,
        invalidation="range",
        policy="take10",
        fee_per_side=0.0,
    )

    assert outcome["exit_reason"] == "stop5"
    assert outcome["exit_premium"] == pytest.approx(95)


def test_option_and_underlying_candles_must_align_exactly():
    option = bars(
        [
            ("2026-01-01T03:50:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:51:00Z", 100, 101, 99, 100),
        ]
    )
    spot = bars(
        [
            ("2026-01-01T03:50:00Z", 100, 101, 99, 100),
            ("2026-01-01T03:52:00Z", 100, 101, 99, 100),
        ]
    )

    with pytest.raises(ValueError, match="timestamps are not aligned"):
        simulate_option_trade(
            option,
            spot,
            side=1,
            range_high=105,
            range_low=95,
            invalidation="range",
            policy="take5",
            fee_per_side=0.0,
        )
