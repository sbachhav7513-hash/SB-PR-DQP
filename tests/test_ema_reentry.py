from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from market_bot.backtest import run_backtest
from market_bot.ema_reentry import find_ema_reentry_signal
from market_bot.engine import TradingScore
from market_bot.intraday_manager import IntradayManager
from market_bot.kite_main import KiteTradingBot
from market_bot.trade_journal import DecisionJournal, TradeJournal
from market_bot.weekly_report import (
    _ema_reentry_summary,
    build_weekly_report,
    write_daily_review,
)


IST = ZoneInfo("Asia/Kolkata")


def _candles(closes, start=None, volume=100):
    start = start or datetime(2026, 10, 26, 10, 0, tzinfo=IST)
    return [
        {
            "time": start + timedelta(minutes=index),
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": volume,
        }
        for index, close in enumerate(closes)
    ]


def test_ce_reentry_requires_bullish_cross_then_later_close_above_cross_high():
    candles = _candles([120 - index for index in range(21)] + [
        99, 98, 99, 101, 104, 108, 113, 119, 126
    ])
    stop_time = candles[20]["time"] + timedelta(seconds=30)

    signal = find_ema_reentry_signal(candles, "CE", stop_time)

    assert signal is not None
    assert signal.signal == "BUY"
    assert signal.crossover_time > stop_time
    assert signal.signal_time > signal.crossover_time
    assert signal.confirmation_close > signal.crossover_level
    assert signal.vwap is not None


def test_pe_reentry_requires_bearish_cross_then_later_close_below_cross_low():
    candles = _candles([100 + index for index in range(21)] + [
        121, 122, 121, 119, 116, 112, 107, 101, 94
    ])
    stop_time = candles[20]["time"] + timedelta(seconds=30)

    signal = find_ema_reentry_signal(candles, "PE", stop_time)

    assert signal is not None
    assert signal.signal == "SELL"
    assert signal.crossover_time > stop_time
    assert signal.signal_time > signal.crossover_time
    assert signal.confirmation_close < signal.crossover_level


def test_reentry_can_confirm_after_ten_minutes_but_not_after_entry_cutoff():
    candles = _candles([120 - index for index in range(21)] + [
        99, 98, 99, 101, 104, 108, 113, 119, 126, 134
    ])
    stop_time = candles[20]["time"] - timedelta(minutes=10)

    signal = find_ema_reentry_signal(candles, "CE", stop_time)
    assert signal is not None
    assert (signal.signal_time - stop_time).total_seconds() > 10 * 60
    assert find_ema_reentry_signal(
        candles,
        "CE",
        stop_time - timedelta(minutes=3),
        valid_until=signal.signal_time,
    ) is None


def test_ema_reentry_uses_same_underlying_signal_in_both_modes():
    candles = _candles([120 - index for index in range(21)] + [
        99, 98, 99, 101, 104, 108, 113, 119, 126
    ])
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "ema_reentry_enabled": True,
        "trading_mode": "intraday_options",
        "bar_interval_seconds": 60,
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.intraday_manager = SimpleNamespace(active_positions={})
    bot.trade_journal = SimpleNamespace(annotate_trade=lambda *args, **kwargs: True)
    bot._ema_reentry_states = {
        "NIFTY_CE": {
            "original_trade_id": "original-1",
            "stop_time": candles[20]["time"] + timedelta(seconds=30),
            "status": "observing",
        }
    }

    signal = bot._ema_reentry_candidate("NIFTY_CE", candles)

    assert signal is not None
    assert signal["original_trade_id"] == "original-1"
    assert signal["signal"] == "BUY"
    assert signal["vwap"] is not None

    bot._ema_reentry_states["NIFTY_CE"]["status"] = "observing"
    bot.live_orders_enabled = True
    assert bot._ema_reentry_candidate("NIFTY_CE", candles) == signal


def test_paper_reentry_gate_allows_one_stop_retry_and_blocks_a_second():
    manager = IntradayManager()
    manager.record_trade_open("NIFTY_CE", "BUY")
    manager.record_trade_close("NIFTY_CE", "STOP_LOSS", -100)
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "ema_reentry_enabled": True,
        "trading_mode": "intraday_options",
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.intraday_manager = manager

    assert bot._can_open_trade_for_signal(
        "NIFTY_CE",
        "BUY",
        70,
        ema_reentry_confirmed=True,
    ) == (True, "OK")

    manager.record_trade_open("NIFTY_CE", "BUY")
    manager.record_trade_close("NIFTY_CE", "TAKE_PROFIT", 100)
    allowed, reason = bot._can_open_trade_for_signal(
        "NIFTY_CE",
        "BUY",
        70,
        ema_reentry_confirmed=True,
    )

    assert allowed is False
    assert "one stop-loss re-entry" in reason.lower()


def test_backtest_adds_at_most_one_reentry_after_stop_and_reports_baseline():
    start = datetime(2026, 10, 26, 10, 0, tzinfo=IST)
    closes = [120 - index for index in range(21)] + [
        99, 98, 99, 101, 104, 108, 113, 119, 126, 128, 128, 128
    ]
    candles = _candles(closes, start)
    candles[21].update({"open": 100, "high": 100.2, "low": 98, "close": 99})
    for index in range(30, len(candles)):
        candles[index].update(
            {"open": 127, "high": 128, "low": 126.5, "close": 128}
        )

    result = run_backtest(
        "NIFTY",
        candles,
        stop_loss_pct=1,
        take_profit_pct=20,
        signal_fn=lambda ticker, history: TradingScore(
            ticker, 80, "BUY" if len(history) == 21 else "HOLD"
        ),
        max_trades_per_session=1,
        ema_stop_reentry_enabled=True,
    )

    assert len(result.trades) == 2
    original, reentry = result.trades
    assert original.exit_reason == "STOP_LOSS"
    assert reentry.is_ema_reentry is True
    assert reentry.original_trade_id == original.trade_id
    assert reentry.stop_time == original.exit_time
    assert reentry.reentry_signal_time > reentry.stop_time
    assert reentry.reentry_entry_price == reentry.entry_price
    assert reentry.reentry_exit_price == reentry.exit_price
    assert reentry.reentry_outcome == "WIN"
    assert reentry.route == "ema_reentry"
    assert result.ema_reentry_statistics["reentries"] == 1
    assert result.ema_reentry_statistics["baseline_total_return_pct"] == -1
    assert result.ema_reentry_statistics["combined_total_return_pct"] > -1


def test_ema_reentry_report_compares_baseline_to_reentry_pnl():
    summary = _ema_reentry_summary(
        [
            {
                "status": "closed",
                "pnl": -100,
                "reason": "STOP_LOSS",
                "ema_reentry_eligible": True,
            },
            {
                "status": "closed",
                "pnl": 50,
                "is_ema_reentry": True,
                "original_trade_id": "original-1",
            },
        ],
        [
            {"ema_reentry_event": "SIGNAL_CONFIRMED"},
            {"ema_reentry_event": "WINDOW_EXPIRED"},
        ],
    )

    assert summary["eligible_stop_losses"] == 1
    assert summary["signals_confirmed"] == 1
    assert summary["windows_expired"] == 1
    assert summary["reentries_closed"] == 1
    assert summary["baseline_comparison"]["baseline_pnl"] == -100
    assert summary["baseline_comparison"]["strategy_pnl"] == -50


def test_paper_journals_and_reviews_keep_reentry_attribution(tmp_path):
    timestamp = datetime.now(IST).isoformat()
    paper_dir = tmp_path / "paper"
    trades = TradeJournal(str(tmp_path / "trades.jsonl"), str(paper_dir))
    decisions = DecisionJournal(str(tmp_path / "decision_log.jsonl"), str(paper_dir))
    trades.log_trade(
        {
            "trade_id": "original-1",
            "timestamp": timestamp,
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "entry": 10.0,
            "quantity": 1,
        }
    )
    trades.close_trade(
        "NIFTY_CE", 8.0, "BUY", "STOP_LOSS", closed_at=timestamp
    )
    trades.annotate_trade(
        "NIFTY_CE",
        {
            "pnl_rupees": -2.0,
            "ema_reentry_eligible": True,
            "ema_reentry_stop_time": timestamp,
        },
        action="BUY",
    )
    trades.log_trade(
        {
            "trade_id": "reentry-1",
            "timestamp": timestamp,
            "ticker": "NIFTY_CE",
            "action": "BUY",
            "entry": 9.0,
            "quantity": 1,
            "strategy_variant": "paper_ema_stop_reentry",
            "is_ema_reentry": True,
            "original_trade_id": "original-1",
            "ema_reentry_stop_time": timestamp,
            "reentry_signal_time": timestamp,
            "reentry_reason": "EMA(5) crossed above EMA(20), then close above crossover high",
            "reentry_entry_price": 9.0,
        }
    )
    trades.close_trade(
        "NIFTY_CE", 11.0, "BUY", "TAKE_PROFIT", closed_at=timestamp
    )
    trades.annotate_trade(
        "NIFTY_CE",
        {
            "pnl_rupees": 2.0,
            "reentry_exit_price": 11.0,
            "reentry_pnl": 2.0,
            "reentry_outcome": "WIN",
        },
        action="BUY",
    )
    decisions.log_decision(
        {
            "timestamp": timestamp,
            "event": "ema_stop_reentry",
            "ema_reentry_event": "SIGNAL_CONFIRMED",
            "ticker": "NIFTY_CE",
            "signal": "BUY",
            "outcome": "signal_confirmed",
        }
    )

    report = build_weekly_report(
        str(tmp_path), days=7, paper_data_dir=str(paper_dir)
    )
    daily_review = write_daily_review(
        str(tmp_path), str(paper_dir), target_date=datetime.now(IST).date()
    )

    assert report["ema_reentry_summary"]["eligible_stop_losses"] == 1
    assert report["ema_reentry_summary"]["reentries_closed"] == 1
    assert report["ema_reentry_summary"]["trade_log"][0]["original_trade_id"] == (
        "original-1"
    )
    assert report["ema_reentry_summary"]["baseline_comparison"]["pnl_change"] == 2
    assert "Re-entry Trade Log" in daily_review.read_text(encoding="utf-8")
    assert "original-1" in daily_review.read_text(encoding="utf-8")
