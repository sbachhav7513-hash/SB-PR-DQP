import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import market_bot.kite_main as kite_main
from market_bot.bar_builder import Bar
from market_bot.kite_main import KiteTradingBot
from market_bot.trade_journal import TradeJournal


IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize(
    "failure_site",
    ["feature_assembly", "bid_excursions", "journal_feature_write"],
)
def test_observational_failures_do_not_stop_tick_entry_exit_or_journaling(
    tmp_path, monkeypatch, failure_site
):
    now = datetime(2026, 11, 10, 10, 0, tzinfo=IST)
    symbol = "NIFTY_CE"
    events = []
    position = {
        "trade_id": "existing-trade",
        "entry_price": 100.0,
        "initial_risk_distance": 5.0,
        "direction": "BUY",
        "quantity": 1,
        "mfe_r": 0.0,
        "mae_r": 0.0,
        "entry_feature_values": {"signal_uid": "existing-uid"},
        "entry_feature_null_reasons": {},
    }
    manager = SimpleNamespace(
        active_positions={symbol: position},
        should_exit_all_positions=lambda: False,
    )
    journal = TradeJournal(
        str(tmp_path / "trades.jsonl"),
        str(tmp_path / "paper"),
        config_hash="test-config",
        git_sha="test-sha",
        git_dirty=False,
    )
    journal.update_trade_mark = lambda *args: None
    journal.log_trade(
        {
            "trade_id": "existing-trade",
            "ticker": symbol,
            "action": "BUY",
            "timestamp": now.isoformat(),
            "entry": 100.0,
            "status": "open",
            "entry_feature_values": position["entry_feature_values"],
            "entry_feature_null_reasons": {},
        }
    )
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "entry_feature_logging_v2": True,
        "instrument_tokens": {symbol: 1},
        "option_quote_max_age_seconds": 60,
    }
    bot.mode = "PAPER"
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.simulation_mode = False
    bot.symbol_map = {1: symbol}
    bot.latest_prices = {}
    bot.option_quote_cache = {}
    bot._telegram_execution_lock = None
    bot._option_capture_signal_ids = {}
    bot._signal_change_attributions = {}
    bot._pending_entry_feature_snapshots = {}
    bot.intraday_manager = manager
    bot.trade_journal = journal
    bot._process_telegram_commands = lambda: None
    bot._update_paper_shadow_runner = lambda *_: None
    bot._quote_validated_long_option = lambda *_: False
    bot._expire_pending_confirmed_entries = lambda *_: None
    bot._paper_change_enabled = lambda *_: False
    bot._option_candle_min_body_ratio = lambda: 0.2
    bot._handle_buy_signal = Mock(return_value="trade_opened")
    bot._entry_feature_snapshot = lambda *args, **kwargs: (
        {"signal_uid": kwargs["signal_uid"]},
        {},
    )

    def exit_check(ticker, price):
        events.append("exit_evaluated")
        journal.log_trade(
            {
                "trade_id": "existing-trade",
                "ticker": ticker,
                "action": "BUY",
                "timestamp": now.isoformat(),
                "entry": 100.0,
                "exit_price": price,
                "status": "closed",
                "entry_feature_values": position["entry_feature_values"],
                "entry_feature_null_reasons": position[
                    "entry_feature_null_reasons"
                ],
            }
        )

    bot._check_position_exit = exit_check
    signal_bar = Bar(now, 100.0, 101.0, 99.0, 100.5, 100)

    def process_tick(tick):
        events.append("tick_processed")
        telemetry = bot._entry_signal_telemetry(
            symbol,
            "BUY",
            80,
            [signal_bar],
            [{"close": 100.0}, {"close": 100.5}],
            signal_bar,
            None,
            {"ltp": 100.5, "bid": 100.4, "ask": 100.6},
        )
        result = bot._handle_buy_signal(
            symbol, 100.5, 80, entry_telemetry=telemetry
        )
        events.append(result)
        journal.log_trade(
            {
                "trade_id": "new-entry",
                "ticker": symbol,
                "action": "BUY",
                "timestamp": now.isoformat(),
                "entry": 100.5,
                "status": "open",
                **telemetry,
            }
        )

    bot.bar_builder = SimpleNamespace(process_tick=process_tick)
    tick = SimpleNamespace(
        instrument_token=1,
        timestamp=now,
        last_price=100.5,
        bid=100.4,
        ask=100.6,
        volume=100,
        oi=None,
        iv=None,
    )
    bot.option_quote_cache[symbol] = {
        "timestamp": now,
        "last_price": tick.last_price,
        "bid": tick.bid,
        "ask": tick.ask,
    }

    if failure_site == "feature_assembly":
        def fail_assembly(*args, **kwargs):
            raise RuntimeError("injected feature assembly failure")

        monkeypatch.setattr(bot, "_entry_feature_snapshot", fail_assembly)
    elif failure_site == "bid_excursions":
        def fail_excursions(*args, **kwargs):
            raise RuntimeError("injected bid excursion failure")

        monkeypatch.setattr(
            bot, "_record_bid_excursions_impl", fail_excursions
        )
    else:
        original_parquet_value = journal.paper_recorder._parquet_value

        def fail_feature_value(value):
            if isinstance(value, dict) and value.get("signal_uid"):
                raise RuntimeError("injected journal feature write failure")
            return original_parquet_value(value)

        monkeypatch.setattr(
            journal.paper_recorder, "_parquet_value", fail_feature_value
        )

    bot._on_tick(tick)

    assert "tick_processed" in events
    assert "exit_evaluated" in events
    assert "trade_opened" in events
    bot._handle_buy_signal.assert_called_once()
    trade_files = list((tmp_path / "paper").glob("**/trades.parquet"))
    assert len(trade_files) == 1
    trades = pd.read_parquet(trade_files[0], engine="fastparquet")
    assert {"existing-trade", "new-entry"}.issubset(set(trades["trade_id"]))

    if failure_site == "feature_assembly":
        row = trades.loc[trades["trade_id"] == "new-entry"].iloc[0]
        assert "feature_error:RuntimeError" in json.loads(
            row["entry_feature_null_reasons"]
        )["feature_error"]
        assert bot._feature_observation_error_counts["feature_assembly"] == 1
    elif failure_site == "bid_excursions":
        row = trades.loc[trades["trade_id"] == "existing-trade"].iloc[0]
        assert "feature_error:RuntimeError" in json.loads(
            row["entry_feature_null_reasons"]
        )["feature_error"]
        assert bot._feature_observation_error_counts["bid_excursions"] == 1
    else:
        row = trades.loc[trades["trade_id"] == "new-entry"].iloc[0]
        assert "feature_error:RuntimeError" in json.loads(
            row["entry_feature_null_reasons"]
        )["feature_error"]
        assert (
            journal.paper_recorder.feature_telemetry()[
                "trade_feature_write_errors"
            ]
            > 0
        )


def test_feature_logging_switch_disables_assembly_and_tracking_but_keeps_uid():
    now = datetime(2026, 11, 10, 10, 0, tzinfo=IST)
    bot = object.__new__(KiteTradingBot)
    bot.config = {"entry_feature_logging_v2": False}
    bot.mode = "PAPER"
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot._option_capture_signal_ids = {}
    bot._paper_change_enabled = lambda *_: False
    bot._option_candle_min_body_ratio = lambda: 0.2
    bot._entry_feature_snapshot = Mock(
        side_effect=AssertionError("feature assembly must be disabled")
    )
    bot._record_bid_excursions_impl = Mock(
        side_effect=AssertionError("bid tracking must be disabled")
    )
    bar = Bar(now, 100.0, 101.0, 99.0, 100.5, 100)

    telemetry = bot._entry_signal_telemetry(
        "NIFTY_CE",
        "BUY",
        80,
        [bar],
        [{"close": 100.0}, {"close": 100.5}],
        bar,
        None,
        {"ltp": 100.5, "bid": 100.4, "ask": 100.6},
    )
    bot._record_bid_excursions("NIFTY_CE", SimpleNamespace())

    assert telemetry["signal_uid"]
    assert telemetry["entry_feature_values"] == {}
    bot._entry_feature_snapshot.assert_not_called()
    bot._record_bid_excursions_impl.assert_not_called()


def test_signal_uid_generation_failure_is_counted_and_rate_limited(
    monkeypatch, caplog
):
    now = datetime(2026, 11, 10, 10, 0, tzinfo=IST)
    bot = object.__new__(KiteTradingBot)
    bot.config = {"entry_feature_logging_v2": False}
    bot.mode = "PAPER"
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot._option_capture_signal_ids = {}
    bot._paper_change_enabled = lambda *_: False
    bot._option_candle_min_body_ratio = lambda: 0.2
    bar = Bar(now, 100.0, 101.0, 99.0, 100.5, 100)

    def fail_uid():
        raise RuntimeError("injected UID failure")

    monkeypatch.setattr(kite_main, "uuid4", fail_uid)
    with caplog.at_level("WARNING", logger="market_bot.kite_main"):
        results = [
            bot._entry_signal_telemetry(
                "NIFTY_CE",
                "BUY",
                80,
                [bar],
                [{"close": 100.0}, {"close": 100.5}],
                bar,
                None,
                {"ltp": 100.5, "bid": 100.4, "ask": 100.6},
            )
            for _ in range(3)
        ]

    assert all(result["signal_uid"].startswith("fallback-") for result in results)
    assert all(
        result["entry_feature_null_reasons"]["signal_uid_generation"]
        == "feature_error:RuntimeError"
        for result in results
    )
    assert bot._feature_observation_error_counts["signal_uid_generation"] == 3
    assert caplog.text.count("call_site=signal_uid_generation") == 1


def test_entry_feature_finalization_failure_preserves_partial_exit_metadata():
    now = datetime(2026, 11, 10, 10, 0, tzinfo=IST)
    position = {"quantity": 2}
    bot = object.__new__(KiteTradingBot)
    bot.config = {"partial_profit_r": 0.5, "partial_profit_fraction": 0.5}
    bot.intraday_manager = SimpleNamespace(
        active_positions={"NIFTY_CE": position}
    )
    bot._finalize_entry_feature_snapshot = Mock(
        side_effect=RuntimeError("injected finalization failure")
    )
    alert = {"quantity": 2}

    bot._finalize_entry_feature_snapshot_fail_open(alert, "NIFTY_CE", now)

    assert alert["partial_profit_r"] == 0.5
    assert alert["partial_profit_fraction"] == 0.5
    assert alert["entry_feature_null_reasons"]["feature_error"] == (
        "feature_error:RuntimeError"
    )
    assert position["mfe_r"] == 0.0
    assert bot._feature_observation_error_counts["entry_feature_finalization"] == 1
