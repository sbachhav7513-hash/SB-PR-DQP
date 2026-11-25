import json
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from market_bot.kite_main import KiteTradingBot
from market_bot.trade_journal import OPTION_TRADE_LOG_FIELDS, TradeJournal


IST = ZoneInfo("Asia/Kolkata")


def _option_bot():
    bot = KiteTradingBot.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "paper_entry_slippage_pct": 0.4,
        "paper_exit_slippage_pct": 1.0,
    }
    bot.simulation_mode = False
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    contract = {
        "contract_id": "NFO:NIFTY26NOV25000CE",
        "underlying": "NIFTY",
        "leg": "CE",
        "strike": 25000,
        "expiry": date(2026, 11, 26),
    }
    bot.kite_stream = SimpleNamespace(
        capture_contracts_by_symbol={"NIFTY_CE": contract},
        contract_symbols={"NIFTY_CE": "NIFTY26NOV25000CE"},
        contract_exchanges={"NIFTY_CE": "NFO"},
        contract_expiries={"NIFTY_CE": date(2026, 11, 26)},
    )
    bot.intraday_manager = SimpleNamespace(
        contract_specs={"NIFTY_CE": {"multiplier": 1}}
    )
    return bot


def test_option_trade_log_fields_record_contract_quote_dte_and_slippage():
    bot = _option_bot()
    fields = bot._option_trade_log_fields(
        "NIFTY_CE",
        {"bid": 100.0, "ask": 102.0},
        entry_time=datetime(2026, 11, 25, 10, 0, tzinfo=IST),
        entry_price=102.0,
        quantity=65,
    )

    assert fields["option_symbol"] == "NIFTY26NOV25000CE"
    assert fields["type"] == "CE"
    assert fields["strike"] == 25000
    assert fields["expiry"] == "2026-11-26"
    assert fields["dte_at_entry"] == 1
    assert fields["entry_bid"] == 100.0
    assert fields["entry_ask"] == 102.0
    assert fields["entry_mid"] == 101.0
    assert fields["entry_slippage_pct"] == 0.4
    assert fields["exit_slippage_pct"] == 1.0
    assert fields["entry_slippage_rupees"] == pytest.approx(26.52)


def test_startup_option_logging_check_rejects_missing_contract_metadata():
    bot = _option_bot()
    bot.config["instrument_tokens"] = {"NIFTY_CE": 101}
    bot.kite_stream.capture_contracts_by_symbol["NIFTY_CE"].pop("strike")

    with pytest.raises(RuntimeError, match="strike"):
        bot._validate_option_trade_logging_metadata()


def test_trade_journal_writes_required_fields_for_every_trade(tmp_path):
    path = tmp_path / "trades.jsonl"
    journal = TradeJournal(str(path))

    journal.log_trade(
        {
            "ticker": "NIFTY_CE",
            "trading_symbol": "NIFTY26NOV25000CE",
            "contract_id": "NFO:NIFTY26NOV25000CE",
            "option_symbol": "NIFTY26NOV25000CE",
            "type": "CE",
            "strike": 25000,
            "expiry": "2026-11-26",
            "dte_at_entry": 1,
            "entry_quote_bid": 100.0,
            "entry_quote_ask": 102.0,
        }
    )

    trade = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert OPTION_TRADE_LOG_FIELDS.issubset(trade)
    assert trade["option_symbol"] == "NIFTY26NOV25000CE"
    assert trade["type"] == "CE"
    assert trade["entry_mid"] == 101.0
    assert trade["exit_mid"] is None
    assert trade["fees"] is None
    assert trade["net_pnl"] is None
