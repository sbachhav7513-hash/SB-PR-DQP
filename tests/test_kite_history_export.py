import csv
from datetime import date, datetime
from unittest.mock import Mock

import pytest

from market_bot.kite_history_export import (
    _date_chunks,
    _read_option_manifest,
    _resolve_underlyings,
    export_history,
)


def test_date_chunks_cover_requested_dates_without_overlap():
    assert list(_date_chunks(date(2026, 1, 1), date(2026, 2, 24), 20)) == [
        (date(2026, 1, 1), date(2026, 1, 20)),
        (date(2026, 1, 21), date(2026, 2, 9)),
        (date(2026, 2, 10), date(2026, 2, 24)),
    ]


@pytest.mark.parametrize("chunk_days", [0, 56])
def test_date_chunks_reject_unsafe_chunk_lengths(chunk_days):
    with pytest.raises(ValueError, match="chunk-days"):
        list(_date_chunks(date(2026, 1, 1), date(2026, 1, 2), chunk_days))


def test_option_manifest_keeps_only_contracts_active_in_requested_period(tmp_path):
    path = tmp_path / "contracts.csv"
    path.write_text(
        "underlying,tradingsymbol,expiry,strike,instrument_type,"
        "instrument_token,lot_size,active_from,active_to\n"
        "NIFTY,NIFTY26OCT25000CE,2026-10-29,25000,CE,12345,65,"
        "2026-10-01,2026-10-29\n"
        "NIFTY,NIFTY26SEP25000PE,2026-09-24,25000,PE,12346,65,"
        "2026-09-01,2026-09-24\n",
        encoding="utf-8",
    )

    contracts = _read_option_manifest(
        path,
        date(2026, 10, 5),
        date(2026, 10, 20),
    )

    assert len(contracts) == 1
    assert contracts[0]["instrument_token"] == 12345
    assert contracts[0]["active_from"] == "2026-10-05"
    assert contracts[0]["active_to"] == "2026-10-20"


def test_option_manifest_requires_exact_contract_fields(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("tradingsymbol,instrument_token\nX,123\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required"):
        _read_option_manifest(path, date(2026, 10, 1), date(2026, 10, 2))


def test_option_manifest_skips_contracts_expired_before_requested_period(tmp_path):
    path = tmp_path / "contracts.csv"
    path.write_text(
        "underlying,tradingsymbol,expiry,strike,instrument_type,"
        "instrument_token,lot_size\n"
        "NIFTY,NIFTY26SEP25000PE,2026-09-24,25000,PE,12346,65\n",
        encoding="utf-8",
    )

    assert _read_option_manifest(
        path,
        date(2026, 10, 1),
        date(2026, 10, 2),
    ) == []


def test_underlying_resolution_uses_configured_index_token_when_master_has_no_name():
    kite = Mock()
    kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": 738561},
    ]

    result = _resolve_underlyings(
        kite,
        ["NIFTY", "RELIANCE"],
        {"NIFTY": 256265},
    )

    assert [item["instrument_token"] for item in result] == [256265, 738561]


def test_export_writes_sorted_ist_candles_and_preserves_option_oi(tmp_path):
    kite = Mock()
    kite.historical_data.return_value = [
        {
            "date": datetime(2026, 10, 5, 9, 16),
            "open": 10,
            "high": 12,
            "low": 9,
            "close": 11,
            "volume": 100,
            "oi": 5000,
        },
        {
            "date": datetime(2026, 10, 5, 9, 15),
            "open": 9,
            "high": 11,
            "low": 8,
            "close": 10,
            "volume": 90,
            "oi": 4900,
        },
    ]
    instrument = {
        "kind": "option",
        "underlying": "NIFTY",
        "tradingsymbol": "NIFTY26OCT25000CE",
        "expiry": "2026-10-29",
        "strike": 25000,
        "instrument_type": "CE",
        "instrument_token": 12345,
        "lot_size": 65,
        "filename": "options__NIFTY26OCT25000CE.csv",
    }

    manifest = export_history(
        kite,
        [instrument],
        date(2026, 10, 5),
        date(2026, 10, 5),
        tmp_path,
        request_delay=0,
    )

    output = tmp_path / "options__NIFTY26OCT25000CE.csv"
    with output.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert [row["timestamp"] for row in rows] == [
        "2026-10-05T09:15:00+05:30",
        "2026-10-05T09:16:00+05:30",
    ]
    assert [row["oi"] for row in rows] == ["4900", "5000"]
    kite.historical_data.assert_called_once()
    assert kite.historical_data.call_args.args[0] == 12345
    assert kite.historical_data.call_args.kwargs["oi"] is True
    assert manifest["instruments"][0]["sessions_with_bars"] == 1
    assert manifest["instruments"][0]["oi_bars"] == 2
    assert (tmp_path / "manifest.json").exists()


def test_export_refuses_to_overwrite_without_explicit_flag(tmp_path):
    (tmp_path / "underlyings__NIFTY.csv").write_text("keep", encoding="utf-8")
    kite = Mock()

    with pytest.raises(FileExistsError, match="--overwrite"):
        export_history(
            kite,
            [{
                "kind": "underlying",
                "underlying": "NIFTY",
                "tradingsymbol": "NIFTY",
                "instrument_token": 256265,
                "filename": "underlyings__NIFTY.csv",
            }],
            date(2026, 10, 5),
            date(2026, 10, 5),
            tmp_path,
            request_delay=0,
        )
    kite.historical_data.assert_not_called()
