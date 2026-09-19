import json
from datetime import datetime
from unittest.mock import patch

from market_bot.accuracy_filters import AccuracyFilters
from market_bot.intraday_manager import IntradayManager
from market_bot.trade_journal import TradeJournal
from market_bot.weekly_report import summarize_best_setup_windows


def test_preclose_exit_and_market_close_are_distinct_boundaries():
    manager = IntradayManager()

    with patch("market_bot.intraday_manager.datetime") as clock:
        clock.now.return_value = datetime(2026, 9, 17, 15, 20)
        assert manager.should_exit_all_positions() is True
        assert manager.is_market_closed() is False

        clock.now.return_value = datetime(2026, 9, 17, 15, 30)
        assert manager.is_market_closed() is True


def test_index_quantity_uses_complete_lot_size():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)

    assert manager.calculate_position_size("NIFTY", 100.0, 90.0) == 100
    assert manager.calculate_position_size("BANKNIFTY", 100.0, 90.0) == 75


def test_position_size_skips_when_one_lot_exceeds_risk_budget():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)

    assert manager.calculate_position_size("NIFTY", 100.0, 70.0) == 0


def test_paper_position_size_simulates_one_lot_when_risk_budget_is_too_small():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)

    assert (
        manager.calculate_position_size(
            "NIFTY", 100.0, 70.0, allow_paper_lot=True
        )
        == 50
    )


def test_close_trade_records_exit_reason(tmp_path):
    path = tmp_path / "trades.jsonl"
    journal = TradeJournal(str(path))
    journal.log_trade({"ticker": "NIFTY", "action": "BUY", "entry": 100.0})

    journal.close_trade("NIFTY", 101.0, "BUY", "MARKET_CLOSE_FORCED_EXIT")

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["status"] == "closed"
    assert record["reason"] == "MARKET_CLOSE_FORCED_EXIT"


def test_consecutive_losses_trigger_circuit_breaker():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)
    manager.max_consecutive_losses = 2

    assert manager.can_open_trade("NIFTY", "BUY")[0] is True

    manager.record_trade_close("NIFTY", "STOP_LOSS", pnl=-200.0)
    assert manager.can_open_trade("NIFTY", "BUY")[0] is True

    manager.record_trade_close("NIFTY", "STOP_LOSS", pnl=-300.0)
    allowed, reason = manager.can_open_trade("NIFTY", "BUY")
    assert allowed is False
    assert "consecutive loss" in reason.lower()


def test_close_position_updates_daily_risk_state():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)
    manager.register_position("NIFTY", "BUY", 50, 100.0, 99.0, 102.0)

    closed = manager.close_position("NIFTY", 99.0, "STOP_LOSS")
    manager.record_trade_close("NIFTY", "STOP_LOSS", closed["pnl_rupees"])

    assert manager.daily_pnl == -50.0
    assert manager.consecutive_losses == 1


def test_adaptive_score_threshold_rises_for_weak_symbol_performance():
    filters = AccuracyFilters()

    assert filters.get_min_score(recent_trades=7, recent_win_rate=20.0) >= 92
    assert filters.get_min_score(recent_trades=7, recent_win_rate=72.0) <= 90


def test_symbol_win_rate_cap_blocks_weak_symbols():
    manager = IntradayManager(account_size=100_000, risk_per_trade_pct=1.0)
    manager.min_symbol_trades_for_cap = 5
    manager.symbol_min_win_rate = 35.0
    manager.symbol_performance["INFY_PE"] = {"wins": 1, "trades": 5, "win_rate": 20.0}

    allowed, reason = manager.can_open_trade("INFY_PE", "BUY")

    assert allowed is False
    assert "win-rate cap" in reason.lower()


def test_best_setup_windows_summary_prefers_high_win_rate_periods(tmp_path):
    trades_path = tmp_path / "trades.jsonl"
    trades_path.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-09-17T09:45:00+05:30", "ticker": "LT_CE", "action": "BUY", "pnl": 100.0, "status": "closed"}),
                json.dumps({"timestamp": "2026-09-17T09:50:00+05:30", "ticker": "LT_CE", "action": "BUY", "pnl": 80.0, "status": "closed"}),
                json.dumps({"timestamp": "2026-09-18T10:05:00+05:30", "ticker": "LT_CE", "action": "BUY", "pnl": -60.0, "status": "closed"}),
                json.dumps({"timestamp": "2026-09-16T11:10:00+05:30", "ticker": "INFY_PE", "action": "SELL", "pnl": -80.0, "status": "closed"}),
                json.dumps({"timestamp": "2026-09-16T11:05:00+05:30", "ticker": "INFY_PE", "action": "SELL", "pnl": 90.0, "status": "closed"}),
            ]
        ) + "\n",
        encoding="utf-8",
    )

    windows = summarize_best_setup_windows(str(tmp_path), days=7)

    assert windows
    assert windows[0]["label"] == "09:BUY"
    assert windows[0]["win_rate"] >= 50.0
