from datetime import date, datetime, time
from types import SimpleNamespace

import pandas as pd
import pytest

from tools import nightly_index_vix_archive as archive


def _instrument_rows():
    return [
        {
            "tradingsymbol": "NIFTY 50",
            "name": "NIFTY 50",
            "instrument_token": 11,
        },
        {
            "tradingsymbol": "NIFTY BANK",
            "name": "NIFTY BANK",
            "instrument_token": 22,
        },
        {
            "tradingsymbol": "INDIA VIX",
            "name": "INDIA VIX",
            "instrument_token": 33,
        },
    ]


def _candle(session_day, minute, *, close=10.0, volume=0):
    return {
        "date": datetime.combine(session_day, time(9, minute)),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": volume,
    }


def test_archive_session_fetches_sequentially_and_appends_idempotently(
    tmp_path, monkeypatch
):
    session_day = date(2026, 11, 23)
    calls = []
    sleeps = []

    def historical_data(token, start, end, interval):
        calls.append((token, start, end, interval))
        return [_candle(session_day, 15, close=float(token), volume=1)]

    kite = SimpleNamespace(
        instruments=lambda exchange: _instrument_rows(),
        historical_data=historical_data,
    )
    for symbol, filename, _ in archive.INSTRUMENTS:
        columns = ["timestamp", "open", "high", "low", "close"]
        row = {
            "timestamp": pd.Timestamp("2026-11-20T09:15:00+05:30"),
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
        }
        if symbol != "INDIA VIX":
            columns.append("volume")
            row["volume"] = 0
        pd.DataFrame([row], columns=columns).to_parquet(
            tmp_path / filename, index=False
        )

    monkeypatch.setattr(archive.time, "sleep", sleeps.append)
    counts = archive.archive_session(kite, tmp_path, session_day)

    assert counts == {"NIFTY": 1, "BANKNIFTY": 1, "INDIA VIX": 1}
    assert [call[0] for call in calls] == [11, 22, 33]
    assert all(call[1].date() == session_day for call in calls)
    assert all(call[2].date() == session_day for call in calls)
    assert all(call[3] == "minute" for call in calls)
    assert sleeps == [archive.REQUEST_DELAY_SECONDS] * 3

    for _, filename, _ in archive.INSTRUMENTS:
        frame = pd.read_parquet(tmp_path / filename)
        assert len(frame) == 2
        assert frame["timestamp"].is_monotonic_increasing

    archive.archive_session(kite, tmp_path, session_day, request_delay=0)
    for _, filename, _ in archive.INSTRUMENTS:
        frame = pd.read_parquet(tmp_path / filename)
        assert len(frame) == 2


def test_archive_session_does_not_write_if_one_symbol_has_no_candles(
    tmp_path,
):
    session_day = date(2026, 11, 23)
    original = {}
    for symbol, filename, _ in archive.INSTRUMENTS:
        columns = ["timestamp", "open", "high", "low", "close"]
        row = {
            "timestamp": pd.Timestamp("2026-11-20T09:15:00+05:30"),
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
        }
        if symbol != "INDIA VIX":
            columns.append("volume")
            row["volume"] = 0
        path = tmp_path / filename
        pd.DataFrame([row], columns=columns).to_parquet(path, index=False)
        original[path] = pd.read_parquet(path)

    def historical_data(token, start, end, interval):
        if token == 22:
            return []
        return [_candle(session_day, 15)]

    kite = SimpleNamespace(
        instruments=lambda exchange: _instrument_rows(),
        historical_data=historical_data,
    )

    with pytest.raises(RuntimeError, match="Session data was incomplete"):
        archive.archive_session(kite, tmp_path, session_day, request_delay=0)

    for path, before in original.items():
        pd.testing.assert_frame_equal(pd.read_parquet(path), before)
