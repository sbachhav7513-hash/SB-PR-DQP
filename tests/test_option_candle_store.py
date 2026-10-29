import csv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market_bot.bar_builder import Bar, BarBuilder
from market_bot.kite_provider import Tick
from market_bot.option_candle_store import OptionCandleRecorder


IST = ZoneInfo("Asia/Kolkata")


def test_recorder_saves_minute_candles_quotes_and_config_hash_once(tmp_path):
    timestamp = datetime(2026, 10, 27, 10, 0, tzinfo=IST)
    bars = [
        Bar(timestamp, 100, 103, 99, 102, 1500, bid=101.95, ask=102.05),
        Bar(
            timestamp + timedelta(minutes=1),
            102,
            104,
            101,
            103,
            1700,
            bid=None,
            ask=None,
        ),
    ]
    recorder = OptionCandleRecorder(tmp_path, config_hash="abc123")

    assert recorder.capture_eligible("NIFTY26OCT25000CE", bars, timestamp) == 2
    assert recorder.capture_eligible("NIFTY26OCT25000CE", bars, timestamp) == 0
    assert recorder.record_active("NIFTY26OCT25000CE", bars[1]) is False

    path = tmp_path / "2026-10-27" / "NIFTY26OCT25000CE.csv"
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 2
    assert rows[0]["bid"] == "101.95"
    assert rows[0]["ask"] == "102.05"
    assert rows[1]["bid"] == ""
    assert rows[1]["ask"] == ""
    assert {row["contract_id"] for row in rows} == {""}
    assert {row["config_hash"] for row in rows} == {"abc123"}


def test_recorder_uses_contract_id_in_filename_and_rows(tmp_path):
    timestamp = datetime(2026, 10, 27, 10, 0, tzinfo=IST)
    contract_id = "NFO:NIFTY26OCT25000CE"
    recorder = OptionCandleRecorder(tmp_path, config_hash="abc123")

    assert recorder.capture_eligible(
        "NIFTY_CE",
        [Bar(timestamp, 100, 103, 99, 102, 1500)],
        timestamp,
        contract_id,
    ) == 1

    path = (
        tmp_path
        / "2026-10-27"
        / "NFO_NIFTY26OCT25000CE__NIFTY_CE.csv"
    )
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 1
    assert rows[0]["contract_id"] == contract_id


def test_recorder_resumes_contract_capture_from_existing_session_file(tmp_path):
    timestamp = datetime.now(IST).replace(second=0, microsecond=0)
    existing = OptionCandleRecorder(tmp_path, config_hash="oldhash")
    existing.capture_eligible("NIFTY26OCT25000CE", [], timestamp)
    path = tmp_path / timestamp.date().isoformat() / "NIFTY26OCT25000CE.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "timestamp,open,high,low,close,volume,bid,ask,config_hash\n",
        encoding="utf-8",
    )

    resumed = OptionCandleRecorder(tmp_path, config_hash="newhash")
    next_bar = Bar(
        timestamp + timedelta(minutes=1), 100, 101, 99, 100.5, 1200
    )

    assert resumed.record_active("NIFTY26OCT25000CE", next_bar)
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows[0]["config_hash"] == "newhash"
    assert rows[0]["contract_id"] == ""


def test_recorder_partitions_by_ist_date_and_skips_other_dates(tmp_path):
    day_one = datetime(2026, 10, 27, 10, 0, tzinfo=IST)
    day_two = day_one + timedelta(days=1)
    recorder = OptionCandleRecorder(tmp_path, config_hash="abc123")

    assert (
        recorder.capture_eligible(
            "NIFTY26OCT25000CE",
            [
                Bar(day_one, 100, 101, 99, 100, 10),
                Bar(day_two, 101, 102, 100, 101, 12),
            ],
            day_two,
        )
        == 1
    )
    assert not (tmp_path / "2026-10-27").exists()
    assert (tmp_path / "2026-10-28" / "NIFTY26OCT25000CE.csv").exists()


def test_bar_builder_tracks_last_minute_bid_and_ask_quotes():
    start = datetime.now(IST).replace(second=0, microsecond=0)
    builder = BarBuilder(interval_seconds=60)

    builder.process_tick(Tick(10, start, 100, bid=99.95, ask=100.05))
    builder.process_tick(
        Tick(10, start + timedelta(seconds=30), 101, bid=100.95, ask=101.05)
    )
    builder.process_tick(
        Tick(10, start + timedelta(minutes=1), 102, bid=101.95, ask=102.05)
    )

    bar = builder.get_bars(10)[0]
    assert bar.open == 100
    assert bar.high == 101
    assert bar.low == 100
    assert bar.close == 101
    assert bar.bid == 100.95
    assert bar.ask == 101.05
