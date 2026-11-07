import json
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from market_bot.bar_builder import Bar
from market_bot.kite_provider import Tick
from market_bot.kite_main import KiteTradingBot
from market_bot.option_capture import OptionCaptureWriter, load_option_capture


IST = ZoneInfo("Asia/Kolkata")


def _contract(token, leg):
    return {
        "instrument_token": token,
        "contract_id": f"NFO:NIFTY26NOV25000{leg}",
        "underlying": "NIFTY",
        "leg": leg,
        "strike": 25000,
        "expiry": "2026-11-26",
        "lot_size": 65,
        "underlying_price_at_selection": 25012.5,
        "resolved_at": "2026-10-28T09:00:00+05:30",
        "subscription_started_at": "2026-10-28T09:00:01+05:30",
    }


def test_rejected_signal_captures_both_legs_through_market_close_without_fill(tmp_path):
    start = datetime(2026, 10, 28, 9, 15, tzinfo=IST)
    call = _contract(101, "CE")
    put = _contract(102, "PE")
    writer = OptionCaptureWriter(
        tmp_path,
        config_hash="cfg",
        git_sha="sha",
        contracts_by_token={101: call, 102: put},
    )
    signal_id = "NIFTY_CE|CE|2026-10-28T09:15:00+05:30"
    assert writer.register_signal(signal_id, start, call, put)
    assert writer.flush()
    assert writer.update_signal_status(signal_id, pending=False, rejected=True)

    writer.record_tick(Tick(101, start + timedelta(seconds=30), 100.0, bid=99.9, ask=100.1))
    writer.record_tick(Tick(101, start + timedelta(minutes=1), 101.0, bid=100.9, ask=101.1))
    writer.record_tick(Tick(101, start + timedelta(minutes=1, seconds=30), 102.0))
    writer.record_tick(
        Tick(101, start.replace(hour=15, minute=30), 103.0, bid=102.9, ask=103.1)
    )
    assert writer.flush()
    writer.close()

    loaded = load_option_capture(
        tmp_path,
        "2026-10-28",
        {"contract_id": call["contract_id"]},
    )
    assert loaded["candles"]
    first = loaded["candles"][0]
    assert first["candle_start_time"].endswith("+05:30")
    assert first["contract_id"] == call["contract_id"]
    assert first["underlying"] == "NIFTY"
    assert first["leg"] == "CE"
    assert first["strike"] == "25000"
    assert first["expiry"] == "2026-11-26"
    assert first["config_hash"] == "cfg"
    assert first["git_sha"] == "sha"
    assert first["capture_all_evaluated_contracts"].lower() == "true"
    assert first["low_tick"].lower() == "true"
    assert first["gap"].lower() == "false"
    gap = next(row for row in loaded["candles"] if row["gap"].lower() == "true")
    assert gap["open"] == ""
    assert gap["close"] == ""
    assert any(row["candle_start_time"].startswith("2026-10-28T15:29:") for row in loaded["candles"])
    assert loaded["quotes"]
    assert loaded["quotes"][0]["time"].endswith("+05:30")
    assert "quote_age_seconds" in loaded["quotes"][0]

    put_capture = load_option_capture(
        tmp_path, "2026-10-28", {"contract_id": put["contract_id"]}
    )
    assert put_capture["candles"][0]["gap"].lower() == "true"
    report = json.loads(
        (tmp_path / "2026-10-28" / "capture_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["signals"] == 1
    assert report["signals_with_resolved_contract_id"] == 1
    assert report["signals_with_60_minutes_forward_candles"] == 1
    assert report["contracts_captured_count"] == 2
    assert (tmp_path / "2026-10-28" / "capture_report.txt").exists()
    assert list((tmp_path / "2026-10-28").glob("*.candles.csv.gz"))


def test_capture_queue_full_drops_without_waiting(tmp_path):
    start = datetime(2026, 10, 28, 9, 15, tzinfo=IST)
    contract = _contract(101, "CE")
    writer = OptionCaptureWriter(
        tmp_path,
        config_hash="cfg",
        git_sha="sha",
        contracts_by_token={101: contract},
        max_queue_size=1,
        auto_start=False,
    )
    assert writer.register_signal("signal", start, contract, None)

    before = time.perf_counter()
    accepted = writer.record_tick(Tick(101, start, 100.0))
    elapsed = time.perf_counter() - before

    assert not accepted
    assert elapsed < 0.1
    assert writer.dropped_rows == 1
    writer.close()


def test_underlying_candle_and_contract_capture_timing_are_persisted(tmp_path):
    start = datetime(2026, 10, 28, 9, 15, tzinfo=IST)
    contract = _contract(101, "CE")
    writer = OptionCaptureWriter(
        tmp_path / "option_candles",
        config_hash="cfg",
        git_sha="sha",
        contracts_by_token={101: contract},
    )
    assert writer.register_signal("signal", start, contract, None)
    writer.record_tick(Tick(101, start, 100.0, bid=99.9, ask=100.1))
    writer.record_tick(
        Tick(101, start + timedelta(minutes=1), 101.0, bid=100.9, ask=101.1)
    )
    writer.record_underlying_bar(
        "NIFTY", Bar(start, 25000.0, 25010.0, 24990.0, 25005.0, 1000)
    )
    writer.record_tick(
        Tick(101, start.replace(hour=15, minute=30), 102.0, bid=101.9, ask=102.1)
    )
    assert writer.flush()
    writer.close()

    timing = json.loads(
        (tmp_path / "option_candles" / "2026-10-28" / "capture_report.json").read_text(
            encoding="utf-8"
        )
    )["contract_capture_timing"][contract["contract_id"]]
    assert timing["registration_time"] == start.isoformat(timespec="seconds")
    assert timing["first_tick_time"] == start.isoformat(timespec="seconds")
    assert timing["first_candle_time"] == start.isoformat(timespec="seconds")
    underlying = (
        tmp_path
        / "underlying_candles"
        / "2026-10-28"
        / "NIFTY.candles.csv"
    )
    assert underlying.is_file()
    assert "25000.0" in underlying.read_text(encoding="utf-8")


def test_capture_failure_does_not_change_rejected_decision_fields(tmp_path):
    start = datetime(2026, 10, 28, 9, 15, tzinfo=IST)
    contract = _contract(101, "CE")
    decision_stream = [
        (start, "BUY", "OPTION_FILTER_STALE_QUOTE"),
        (
            start + timedelta(minutes=1),
            "SELL",
            "OPTION_FILTER_RISK_CAP",
        ),
    ]

    def run_decision(writer):
        rows = []
        bot = KiteTradingBot.__new__(KiteTradingBot)
        bot.config = {
            "trading_mode": "intraday_options",
            "bar_interval_seconds": 60,
            "instrument_tokens": {"NIFTY_CE": 101, "NIFTY_PE": 102},
        }
        put = _contract(102, "PE")
        bot.kite_stream = SimpleNamespace(
            capture_contracts_by_symbol={"NIFTY_CE": contract, "NIFTY_PE": put},
            capture_opposites_by_token={101: put, 102: contract},
            contract_symbols={"NIFTY_CE": "NIFTY26NOV25000CE"},
            contract_exchanges={"NIFTY_CE": "NFO"},
        )
        bot.option_capture_writer = writer
        bot.decision_journal = SimpleNamespace(log_decision=rows.append)
        bot._decision_gate_measurements = lambda *args: {}
        for timestamp, signal, outcome in decision_stream:
            bot._register_option_signal_capture(
                "NIFTY_CE", timestamp, signal=signal
            )
            bot._record_decision(
                "NIFTY_CE",
                Bar(timestamp, 100, 101, 99, 100, 10),
                [],
                None,
                signal,
                outcome,
            )
        fields = (
            "signal",
            "outcome",
            "score",
            "signal_id",
            "contract_id",
            "strike",
            "expiry",
            "lot_size",
            "underlying_price_at_selection",
        )
        return [{key: row.get(key) for key in fields} for row in rows], rows

    baseline, _ = run_decision(None)
    writer = OptionCaptureWriter(
        tmp_path,
        config_hash="cfg",
        git_sha="sha",
        contracts_by_token={101: contract},
        max_queue_size=1,
        auto_start=False,
    )
    writer.register_signal("fill-queue", start, contract, None)
    captured, rows = run_decision(writer)

    assert captured == baseline
    assert rows[0]["contract_id"] == contract["contract_id"]
    assert rows[0]["signal_id"] == "NIFTY_CE|CE|2026-10-28T09:15:00+05:30"
    assert rows[0]["outcome"] == "OPTION_FILTER_STALE_QUOTE"
    assert rows[1]["contract_id"] == _contract(102, "PE")["contract_id"]
    assert rows[1]["outcome"] == "OPTION_FILTER_RISK_CAP"
    writer.close()


def test_sell_signal_resolves_the_entry_put_before_gate_and_registers_call_too(
    tmp_path,
):
    start = datetime(2026, 10, 28, 9, 15, tzinfo=IST)
    call = _contract(101, "CE")
    put = _contract(102, "PE")
    writer = OptionCaptureWriter(
        tmp_path,
        config_hash="cfg",
        git_sha="sha",
        contracts_by_token={101: call, 102: put},
        auto_start=False,
    )
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "instrument_tokens": {"NIFTY_CE": 101, "NIFTY_PE": 102},
    }
    bot.option_capture_writer = writer
    bot.kite_stream = SimpleNamespace(
        capture_contracts_by_symbol={"NIFTY_CE": call, "NIFTY_PE": put},
        capture_opposites_by_token={101: put, 102: call},
    )

    bot._register_option_signal_capture("NIFTY_CE", start, signal="SELL")
    _, registration = writer._queue.get_nowait()

    assert registration["contract"]["contract_id"] == put["contract_id"]
    assert registration["opposite_contract"]["contract_id"] == call["contract_id"]
    writer.close()


def test_disk_failure_is_counted_by_background_writer(tmp_path):
    start = datetime.now(IST).replace(second=0, microsecond=0)
    contract = _contract(101, "CE")
    writer = OptionCaptureWriter(
        tmp_path,
        config_hash="cfg",
        git_sha="sha",
        contracts_by_token={101: contract},
    )
    writer._append_row = lambda *args: (_ for _ in ()).throw(OSError("disk full"))
    assert writer.register_signal("signal", start, contract, None)
    assert writer.flush()
    writer.record_tick(Tick(101, start + timedelta(seconds=1), 100.0))
    writer.record_tick(Tick(101, start + timedelta(minutes=1), 101.0))
    assert writer.flush()
    assert writer.dropped_rows >= 1
    writer.close()


def test_loader_refuses_contract_inference(tmp_path):
    try:
        load_option_capture(tmp_path, "2026-10-28", {"ticker": "NIFTY_CE"})
    except ValueError as exc:
        assert "contract_id" in str(exc)
    else:
        raise AssertionError("loader must not infer contract IDs")


def test_registered_flush_only_visits_dirty_token_between_minute_boundaries(
    tmp_path,
):
    now = datetime(2026, 10, 28, 9, 17, tzinfo=IST)
    minute = now.replace(second=0, microsecond=0)
    call = _contract(101, "CE")
    put = _contract(102, "PE")
    writer = OptionCaptureWriter(
        tmp_path,
        config_hash="cfg",
        git_sha="sha",
        contracts_by_token={101: call, 102: put},
        enabled=False,
        auto_start=False,
    )
    day = now.date().isoformat()
    writer._thread_state["registered"][day] = {101: call, 102: put}
    writer._thread_state["registered_flush_minute"][day] = minute
    writer._thread_state["next_minute"][(day, 101)] = minute - timedelta(minutes=1)
    writer._thread_state["next_minute"][(day, 102)] = minute
    writer._thread_state["flush_dirty"][day].add(101)
    writer._thread_state["completed_by_minute"][101][
        minute - timedelta(minutes=1)
    ] = {
        "candle_start_time": minute - timedelta(minutes=1),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1,
        "oi": None,
        "tick_count": 1,
        "last_tick_time": now,
        "bid": None,
        "ask": None,
        "low_tick": True,
        "gap": False,
    }
    appended = []

    def append_candle(day_key, token, candle):
        appended.append(token)
        return True

    writer._append_candle = append_candle

    writer._flush_registered(now)
    assert appended == [101]
    assert writer.telemetry()["last_flush_rows"] == 1

    writer._flush_registered(now)
    assert appended == [101]
    assert writer.telemetry()["last_flush_rows"] == 0
    writer.close()
