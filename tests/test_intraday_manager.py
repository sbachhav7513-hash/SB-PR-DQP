import json

from market_bot.intraday_manager import IntradayManager
from market_bot.trade_journal import TradeJournal


def test_index_quantity_uses_complete_lot_size():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)

    assert manager.calculate_position_size("NIFTY", 100.0, 90.0) == 0
    assert manager.calculate_position_size("BANKNIFTY", 100.0, 90.0) == 0


def test_position_size_skips_when_one_lot_exceeds_risk_budget():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)

    assert manager.calculate_position_size("NIFTY", 100.0, 99.0) == 0


def test_close_trade_records_exit_reason(tmp_path):
    path = tmp_path / "trades.jsonl"
    journal = TradeJournal(str(path))
    journal.log_trade({"ticker": "NIFTY", "action": "BUY", "entry": 100.0})

    journal.close_trade("NIFTY", 101.0, "BUY", "MARKET_CLOSE_FORCED_EXIT")

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["status"] == "closed"
    assert record["reason"] == "MARKET_CLOSE_FORCED_EXIT"
