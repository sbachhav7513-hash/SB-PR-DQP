import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from market_bot.paper_recovery import build_recovery_record


IST = ZoneInfo("Asia/Kolkata")


def _write_rows(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_recovery_record_calculates_bids_r_reclaim_and_underlying_reversal(tmp_path):
    day = date(2026, 11, 6)
    exit_time = datetime(2026, 11, 6, 9, 15, tzinfo=IST)
    contract_id = "NFO:NIFTY26N0924650CE"
    option_rows = []
    underlying_rows = []
    for minute in range(9 * 60 + 14, 15 * 60 + 30):
        candle_time = datetime(2026, 11, 6, minute // 60, minute % 60, tzinfo=IST)
        high, low, close = 101.0, 99.0, 100.0
        if candle_time == exit_time + timedelta(minutes=5):
            high, low, close = 110.0, 98.0, 105.0
        option_rows.append(
            {
                "contract_id": contract_id,
                "candle_start_time": candle_time.isoformat(),
                "open": 100.0,
                "high": high,
                "low": low,
                "close": close,
                "gap": "false",
            }
        )
        underlying_rows.append(
            {
                "symbol": "NIFTY",
                "candle_start_time": candle_time.isoformat(),
                "open": 1000.0,
                "high": 1001.0,
                "low": 1000.0 if candle_time < exit_time + timedelta(minutes=2) else 999.0,
                "close": 1000.0,
            }
        )
    day_dir = tmp_path / "option_candles" / day.isoformat()
    _write_rows(
        day_dir / "NFO_NIFTY26N0924650CE.candles.csv",
        ["contract_id", "candle_start_time", "open", "high", "low", "close", "gap"],
        option_rows,
    )
    quote_rows = []
    for minutes in (5, 15, 30, 60):
        quote_time = exit_time + timedelta(minutes=minutes, seconds=10)
        quote_rows.append(
            {
                "contract_id": contract_id,
                "time": quote_time.isoformat(),
                "bid": 105.0,
                "ask": 105.2,
                "quote_age_seconds": 0.4,
            }
        )
    _write_rows(
        day_dir / "NFO_NIFTY26N0924650CE.quotes.csv",
        ["contract_id", "time", "bid", "ask", "quote_age_seconds"],
        quote_rows,
    )
    _write_rows(
        tmp_path / "underlying_candles" / day.isoformat() / "NIFTY.candles.csv",
        ["symbol", "candle_start_time", "open", "high", "low", "close"],
        underlying_rows,
    )

    record = build_recovery_record(
        {
            "trade_id": "trade-1",
            "ticker": "NIFTY_CE",
            "contract_id": contract_id,
            "action": "BUY",
            "entry": 100.0,
            "entry_time": (exit_time - timedelta(minutes=1)).isoformat(),
            "closed_at": exit_time.isoformat(),
            "reason": "STOP_LOSS",
            "initial_stop_loss": 90.0,
            "initial_risk_per_unit": 10.0,
            "underlying_price_at_entry": 1000.0,
        },
        tmp_path,
        day,
    )

    assert record is not None
    assert record["status"] == "complete"
    assert record["exit_type"] == "initial_stop"
    assert record["entry_to_exit_seconds"] == 60.0
    assert record["stop_within_5m"] is True
    assert record["bid_after_5m"]["bid"] == 105.0
    assert record["bid_after_5m"]["sample_offset_seconds"] == 10.0
    assert record["max_r_within_60m"] == 1.0
    assert record["reclaimed_entry"] is True
    assert record["reached_plus_1r"] is True
    assert record["underlying_reversed_within_60m"] is True

    underlying_path = (
        tmp_path
        / "underlying_candles"
        / day.isoformat()
        / "NIFTY.candles.csv"
    )
    underlying_rows.pop(10)
    _write_rows(
        underlying_path,
        ["symbol", "candle_start_time", "open", "high", "low", "close"],
        underlying_rows,
    )
    incomplete = build_recovery_record(
        {
            "trade_id": "trade-1",
            "ticker": "NIFTY_CE",
            "contract_id": contract_id,
            "action": "BUY",
            "entry": 100.0,
            "entry_time": (exit_time - timedelta(minutes=1)).isoformat(),
            "closed_at": exit_time.isoformat(),
            "reason": "STOP_LOSS",
            "initial_stop_loss": 90.0,
            "initial_risk_per_unit": 10.0,
            "underlying_price_at_entry": 1000.0,
        },
        tmp_path,
        day,
    )
    assert incomplete is not None
    assert incomplete["status"] == "incomplete"
    assert any("underlying capture" in reason for reason in incomplete["missing_reasons"])


def test_recovery_marks_missing_capture_incomplete(tmp_path):
    record = build_recovery_record(
        {
            "trade_id": "missing",
            "ticker": "NIFTY_CE",
            "contract_id": "NFO:NIFTY26N0924650CE",
            "action": "BUY",
            "entry": 100.0,
            "entry_time": "2026-11-06T09:14:00+05:30",
            "closed_at": "2026-11-06T09:15:00+05:30",
            "reason": "TRAILING_STOP",
            "initial_stop_loss": 90.0,
            "initial_risk_per_unit": 10.0,
            "exit_trigger_price": 100.0,
        },
        tmp_path,
        date(2026, 11, 6),
    )

    assert record is not None
    assert record["status"] == "incomplete"
    assert record["exit_type"] == "breakeven"
    assert "missing option candles" in record["missing_reasons"]
    assert record["underlying_reversed_to_close"] is None


def test_underlying_entry_fallback_uses_only_completed_candles(tmp_path):
    day = date(2026, 11, 6)
    _write_rows(
        tmp_path / "underlying_candles" / day.isoformat() / "NIFTY.candles.csv",
        ["symbol", "candle_start_time", "open", "high", "low", "close"],
        [
            {
                "symbol": "NIFTY",
                "candle_start_time": "2026-11-06T09:14:00+05:30",
                "open": 1000,
                "high": 1010,
                "low": 990,
                "close": 1005,
            }
        ],
    )

    record = build_recovery_record(
        {
            "trade_id": "no-lookahead",
            "ticker": "NIFTY_CE",
            "contract_id": "NFO:NIFTY26N0924650CE",
            "entry": 100.0,
            "entry_time": "2026-11-06T09:14:30+05:30",
            "closed_at": "2026-11-06T09:15:00+05:30",
            "reason": "STOP_LOSS",
            "initial_stop_loss": 90.0,
            "initial_risk_per_unit": 10.0,
        },
        tmp_path,
        day,
    )

    assert record is not None
    assert "missing underlying entry reference or candles" in record["missing_reasons"]
