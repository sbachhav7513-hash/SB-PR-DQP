from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_bot.index_history_export import (
    MAX_CHUNK_DAYS,
    _date_chunks,
    _missing_minutes_by_session,
    download_index_history,
)


IST = ZoneInfo("Asia/Kolkata")


def test_date_chunks_respect_kite_request_window():
    chunks = list(_date_chunks(date(2025, 1, 1), date(2025, 5, 1)))

    assert all((end - start).days + 1 <= MAX_CHUNK_DAYS for start, end in chunks)
    assert chunks[0][0] == date(2025, 1, 1)
    assert chunks[-1][1] == date(2025, 5, 1)
    assert all(chunks[index][1] + timedelta(days=1) == chunks[index + 1][0]
               for index in range(len(chunks) - 1))


def test_missing_minute_report_uses_375_regular_session_minutes():
    start = datetime(2026, 1, 5, 9, 15, tzinfo=IST)
    complete = [
        {"time": start + timedelta(minutes=minute)}
        for minute in range(375)
    ]

    assert _missing_minutes_by_session(complete) == {}
    incomplete = complete[:]
    del incomplete[30]

    assert _missing_minutes_by_session(incomplete) == {
        "2026-01-05": ["09:45"]
    }


def test_download_filters_outside_regular_session_and_writes_csv(tmp_path: Path):
    class FakeProvider:
        def fetch_history(self, token, from_date, to_date, interval):
            assert token == 256265
            assert interval == "minute"
            return [
                {
                    "time": datetime(2026, 1, 5, 9, 14, tzinfo=IST),
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 0,
                },
                {
                    "time": datetime(2026, 1, 5, 9, 15, tzinfo=IST),
                    "open": 2,
                    "high": 2,
                    "low": 2,
                    "close": 2,
                    "volume": 0,
                },
                {
                    "time": datetime(2026, 1, 5, 15, 30, tzinfo=IST),
                    "open": 3,
                    "high": 3,
                    "low": 3,
                    "close": 3,
                    "volume": 0,
                },
            ]

    report = download_index_history(
        FakeProvider(),
        {"NIFTY": 256265},
        date(2026, 1, 5),
        date(2026, 1, 5),
        tmp_path,
        request_delay=0,
    )
    csv_text = (tmp_path / "NIFTY.csv").read_text(encoding="utf-8")

    assert report["NIFTY"]["bars"] == 1
    assert report["NIFTY"]["sessions"] == 1
    assert "2026-01-05T09:15:00+05:30" in csv_text
    assert "09:14" not in csv_text
    assert "15:30" not in csv_text


def test_download_does_not_overwrite_existing_history_by_default(tmp_path: Path):
    (tmp_path / "NIFTY.csv").write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="history exports already exist"):
        download_index_history(
            provider=None,
            instruments={"NIFTY": 256265},
            start=date(2026, 1, 5),
            end=date(2026, 1, 5),
            output_dir=tmp_path,
            request_delay=0,
        )
