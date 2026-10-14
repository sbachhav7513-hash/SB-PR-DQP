from datetime import date

import pytest

from market_bot.kite_daily_research_export import (
    _read_daily_master,
    _select_daily_options,
    _write_daily_master,
)


def _contract(root, expiry, strike, option_type, token):
    return {
        "name": root,
        "tradingsymbol": f"{root}{expiry:%y%b}{strike}{option_type}",
        "expiry": expiry,
        "strike": strike,
        "instrument_type": option_type,
        "instrument_token": token,
        "lot_size": 50,
    }


def test_daily_option_selection_uses_nearest_expiry_and_prior_close_strikes():
    target = date(2026, 10, 7)
    nearest = date(2026, 10, 27)
    farther = date(2026, 11, 24)
    rows = [
        _contract("NIFTY", nearest, strike, option_type, token)
        for token, strike, option_type in [
            (1, 24950, "CE"),
            (2, 24950, "PE"),
            (3, 25000, "CE"),
            (4, 25000, "PE"),
            (5, 25050, "CE"),
            (6, 25050, "PE"),
            (7, 25150, "CE"),
            (8, 25150, "PE"),
        ]
    ]
    rows.extend([
        _contract("NIFTY", farther, 25000, "CE", 9),
        _contract("NIFTY", date(2026, 10, 6), 25000, "CE", 10),
        _contract("OTHER", nearest, 25000, "CE", 11),
    ])
    config = {
        "options_underlyings": ["NIFTY"],
        "option_expiry_days": 21,
        "option_expiry_mode": "nearest",
        "option_strike_step": {"NIFTY": 50},
        "option_max_strike_distance_pct": 0.2,
    }

    selected, missing = _select_daily_options(
        rows,
        {"NIFTY": 25000},
        target,
        config,
    )

    assert {row["instrument_token"] for row in selected} == {1, 2, 3, 4, 5, 6}
    assert {row["expiry"] for row in selected} == {nearest.isoformat()}
    assert {row["active_from"] for row in selected} == {target.isoformat()}
    assert missing == []


def test_daily_option_selection_reports_roots_without_spot_or_expiry():
    target = date(2026, 10, 7)
    rows = [_contract("NIFTY", date(2026, 10, 27), 25000, "CE", 1)]
    config = {
        "options_underlyings": ["NIFTY", "BANKNIFTY"],
        "option_expiry_days": 21,
        "option_expiry_mode": "nearest",
        "option_strike_step": {"NIFTY": 50, "BANKNIFTY": 100},
        "option_max_strike_distance_pct": 0.5,
    }

    selected, missing = _select_daily_options(
        rows,
        {"NIFTY": 25000},
        target,
        config,
    )

    assert len(selected) == 1
    assert missing == ["BANKNIFTY"]


def test_daily_master_round_trips_dated_contract_mappings(tmp_path):
    snapshot_date = date(2026, 10, 14)
    path = tmp_path / "nfo_instruments_snapshot.csv"
    written = _write_daily_master(
        path,
        [
            _contract("NIFTY", date(2026, 10, 27), 25000, "CE", 12345),
            _contract("OTHER", date(2026, 10, 27), 25000, "CE", 67890),
        ],
        {"NIFTY"},
        snapshot_date,
    )

    rows = _read_daily_master(path, snapshot_date)

    assert written == 1
    assert rows == [{
        "name": "NIFTY",
        "tradingsymbol": "NIFTY26OCT25000CE",
        "expiry": date(2026, 10, 27),
        "strike": 25000.0,
        "instrument_type": "CE",
        "instrument_token": 12345,
        "lot_size": 50,
    }]


def test_daily_master_rejects_snapshot_for_another_session(tmp_path):
    path = tmp_path / "nfo_instruments_snapshot.csv"
    _write_daily_master(
        path,
        [_contract("NIFTY", date(2026, 10, 27), 25000, "CE", 12345)],
        {"NIFTY"},
        date(2026, 10, 14),
    )

    with pytest.raises(ValueError, match="different snapshot date"):
        _read_daily_master(path, date(2026, 10, 15))
