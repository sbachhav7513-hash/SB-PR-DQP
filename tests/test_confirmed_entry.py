import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from market_bot.bar_builder import Bar
from market_bot.intraday_manager import IntradayManager
from market_bot.kite_main import KiteTradingBot
from market_bot.trade_journal import DecisionJournal


IST = ZoneInfo("Asia/Kolkata")


def _pending(symbol, start, signal_close, score=80):
    leg = "CE" if symbol.endswith("_CE") else "PE"
    signal = "BUY" if leg == "CE" else "SELL"
    signal_bar = {
        "time": start,
        "open": signal_close - 1 if leg == "CE" else signal_close + 1,
        "high": signal_close + 0.5,
        "low": signal_close - 0.5,
        "close": signal_close,
        "volume": 1000,
    }
    return {
        "signal_id": f"{symbol}|{leg}|{start.isoformat()}",
        "symbol": symbol,
        "underlying": symbol.rsplit("_", 1)[0],
        "leg": leg,
        "signal": signal,
        "score": score,
        "route": "scored",
        "strategy_variant": None,
        "signal_time": start,
        "signal_bar": signal_bar,
        "signal_close": signal_close,
        "signal_bars": [
            {
                **signal_bar,
                "time": start - timedelta(minutes=1),
                "close": signal_close - 2 if leg == "CE" else signal_close + 2,
            },
            signal_bar,
        ],
        "history": [{"close": signal_close - 2}, {"close": signal_close}],
        "reasons": ["test signal"],
        "contract_id": f"NFO:{symbol}",
        "signal_premium": 20.0,
        "signal_bid": 19.9,
        "signal_ask": 20.1,
        "signal_ltp": 20.0,
        "signal_quote_age_seconds": 1.0,
        "support_resistance_level": None,
        "support_resistance_touches": None,
        "support_resistance_time": None,
        "ema_fast_value": 100.0,
        "ema_slow_value": 99.0,
        "minimum_signal_score": 70,
        "minimum_premium_override": None,
        "confirmation_start": start + timedelta(minutes=1),
    }


def _bot(tmp_path, pending, now):
    bot = object.__new__(KiteTradingBot)
    symbols = [entry["symbol"] for entry in pending]
    bot.config = {
        "trading_mode": "intraday_options",
        "instrument_tokens": {symbol: index + 1 for index, symbol in enumerate(symbols)},
        "option_quote_max_age_seconds": 60,
        "late_window_enabled": False,
        "option_min_candle_body_ratio": 0.2,
    }
    bot.entry_mode = "confirmed"
    bot._pending_entries = {
        (entry["symbol"], entry["leg"]): entry for entry in pending
    }
    bot.decision_journal = DecisionJournal(str(tmp_path / "decisions.jsonl"))
    bot.option_quote_cache = {
        symbol: {
            "timestamp": now - timedelta(seconds=1),
            "bid": 19.9,
            "ask": 20.1,
            "last_price": 20.0,
            "volume": 1000,
        }
        for symbol in symbols
    }
    bot.kite_stream = SimpleNamespace(
        contract_symbols={symbol: symbol for symbol in symbols},
        contract_exchanges={symbol: "NFO" for symbol in symbols},
    )
    bot.accuracy_filters = Mock()
    bot.accuracy_filters.validate_entry_with_reason.return_value = (True, "OK")
    bot._contract_id = lambda symbol: f"NFO:{symbol}"
    bot._option_leg_is_active = lambda *_: True
    bot._late_window_blocked = lambda _: False
    bot._live_entry_allowed = lambda _: True
    bot._can_open_trade_for_signal = Mock(return_value=(True, "OK"))
    bot._has_option_candle_momentum = Mock(return_value=True)
    bot._option_candle_min_body_ratio = lambda: 0.2
    bot._option_quality_gate = Mock(return_value=(True, "OK"))
    bot._handle_buy_signal = Mock(return_value="trade_opened")
    return bot


def _events(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


@pytest.mark.parametrize(
    ("leg", "signal_close", "confirmation_close", "passes"),
    [
        ("CE", 100.0, 100.1, True),
        ("CE", 100.0, 100.0, False),
        ("CE", 100.0, 99.9, False),
        ("PE", 100.0, 99.9, True),
        ("PE", 100.0, 100.0, False),
        ("PE", 100.0, 100.1, False),
    ],
)
def test_confirmation_requires_strict_leg_direction(
    tmp_path, leg, signal_close, confirmation_close, passes
):
    start = datetime(2026, 10, 29, 9, 54, tzinfo=IST)
    symbol = f"NIFTY_{leg}"
    signal = _pending(symbol, start, signal_close)
    close_time = start + timedelta(minutes=2)
    bot = _bot(tmp_path, [signal], close_time)
    confirmation = Bar(
        start + timedelta(minutes=1),
        confirmation_close,
        confirmation_close,
        confirmation_close,
        confirmation_close,
        1000,
    )

    bot._process_confirmed_entries("NIFTY", confirmation, close_time)

    if passes:
        bot._handle_buy_signal.assert_called_once()
        assert not bot._pending_entries
    else:
        bot._handle_buy_signal.assert_not_called()
        assert not bot._pending_entries
        outcome = _events(tmp_path / "decisions.jsonl")[-1]
        assert outcome["confirmation_event"] == "rejected_by_confirmation"
        assert outcome["cancellation_reason"] == f"confirmation_failed_{leg.lower()}"
        bot.accuracy_filters.record_entry.assert_not_called()


def test_no_entry_until_confirmation_candle_has_closed(tmp_path):
    start = datetime(2026, 10, 29, 9, 54, tzinfo=IST)
    signal = _pending("NIFTY_CE", start, 22_759.30)
    bot = _bot(tmp_path, [signal], start)
    confirmation = Bar(
        start + timedelta(minutes=1),
        22_758.35,
        22_760.0,
        22_757.0,
        22_758.35,
        1000,
    )

    bot._process_confirmed_entries(
        "NIFTY", confirmation, start + timedelta(minutes=1, seconds=59)
    )
    bot._handle_buy_signal.assert_not_called()
    assert bot._pending_entries

    bot._process_confirmed_entries(
        "NIFTY", confirmation, start + timedelta(minutes=2)
    )
    bot._handle_buy_signal.assert_not_called()
    assert not bot._pending_entries
    event = _events(tmp_path / "decisions.jsonl")[-1]
    assert event["confirmation_event"] == "rejected_by_confirmation"
    assert event["confirmation_candle_time"] == confirmation.timestamp.isoformat()


def test_29_oct_nifty_ce_replay_examples(tmp_path):
    first_signal = datetime(2026, 10, 29, 9, 54, tzinfo=IST)
    second_signal = datetime(2026, 10, 29, 10, 11, tzinfo=IST)
    first_bot = _bot(
        tmp_path,
        [_pending("NIFTY_CE", first_signal, 22_759.30, score=80)],
        first_signal + timedelta(minutes=2),
    )
    # The first signal fails at the next underlying close (09:55 bar label).
    first_bot._process_confirmed_entries(
        "NIFTY",
        Bar(
            first_signal + timedelta(minutes=1),
            22_759.0,
            22_760.0,
            22_758.0,
            22_758.35,
            1000,
        ),
        first_signal + timedelta(minutes=2),
    )
    assert ("NIFTY_CE", "CE") not in first_bot._pending_entries

    # 10:12 is the confirmation bar start; its close passes strictly.
    bot = _bot(
        tmp_path / "second",
        [_pending("NIFTY_CE", second_signal, 22_789.55, score=82)],
        second_signal + timedelta(minutes=2, seconds=3),
    )
    bot._process_confirmed_entries(
        "NIFTY",
        Bar(
            second_signal + timedelta(minutes=1),
            22_790.0,
            22_794.0,
            22_789.0,
            22_793.40,
            1000,
        ),
        second_signal + timedelta(minutes=2, seconds=3),
    )
    bot._handle_buy_signal.assert_called_once()
    metadata = bot._handle_buy_signal.call_args.kwargs["confirmed_entry_metadata"]
    assert metadata["confirmation_close"] == 22_793.40
    assert metadata["confirmation_delay_seconds"] == pytest.approx(63.0)


def test_stale_quote_after_confirmation_cancels_with_specific_reason(tmp_path):
    start = datetime(2026, 10, 29, 10, 0, tzinfo=IST)
    now = start + timedelta(minutes=2)
    signal = _pending("NIFTY_CE", start, 100.0)
    bot = _bot(tmp_path, [signal], now)
    bot.option_quote_cache["NIFTY_CE"]["timestamp"] = now - timedelta(seconds=61)

    bot._process_confirmed_entries(
        "NIFTY",
        Bar(start + timedelta(minutes=1), 101.0, 102.0, 100.0, 101.0, 1000),
        now,
    )

    bot._handle_buy_signal.assert_not_called()
    event = _events(tmp_path / "decisions.jsonl")[-1]
    assert event["confirmation_event"] == "filter_failed_after_confirmation"
    assert event["cancellation_reason"] == "filter_failed_after_confirmation"
    assert event["cancellation_sub_reason"] == "stale_quote"


def test_confirmation_after_1445_expires_signal(tmp_path):
    start = datetime(2026, 10, 29, 14, 43, tzinfo=IST)
    now = datetime(2026, 10, 29, 14, 45, 1, tzinfo=IST)
    signal = _pending("NIFTY_CE", start, 100.0)
    bot = _bot(tmp_path, [signal], now)

    bot._process_confirmed_entries(
        "NIFTY",
        Bar(
            start + timedelta(minutes=1),
            101.0,
            102.0,
            100.0,
            101.0,
            1000,
        ),
        now,
    )

    bot._handle_buy_signal.assert_not_called()
    event = _events(tmp_path / "decisions.jsonl")[-1]
    assert event["confirmation_event"] == "expired_signal"
    assert event["cancellation_sub_reason"] == "cutoff"


def test_missing_confirmation_candle_expires_without_cooldown(tmp_path):
    start = datetime(2026, 10, 29, 10, 0, tzinfo=IST)
    signal = _pending("NIFTY_CE", start, 100.0)
    bot = _bot(tmp_path, [signal], start + timedelta(minutes=2, seconds=6))

    bot._expire_pending_confirmed_entries(start + timedelta(minutes=2, seconds=6))

    bot._handle_buy_signal.assert_not_called()
    bot.accuracy_filters.record_entry.assert_not_called()
    assert not bot._pending_entries
    event = _events(tmp_path / "decisions.jsonl")[-1]
    assert event["confirmation_event"] == "expired_signal"
    assert event["cancellation_sub_reason"] == "missing_candle"


def test_cancelled_signal_does_not_consume_cooldown_and_later_signal_is_queued(
    tmp_path,
):
    start = datetime(2026, 10, 29, 10, 0, tzinfo=IST)
    bot = _bot(
        tmp_path,
        [_pending("NIFTY_CE", start, 100.0)],
        start + timedelta(minutes=2),
    )
    bot._process_confirmed_entries(
        "NIFTY",
        Bar(start + timedelta(minutes=1), 99, 100, 98, 99, 1000),
        start + timedelta(minutes=2),
    )
    bot.accuracy_filters.record_entry.assert_not_called()

    bot._entry_score_floor = Mock(return_value=70)
    bot._capture_eligible_option_candles = Mock()
    bot.option_quote_cache = {
        "NIFTY_CE": {
            "timestamp": start + timedelta(minutes=3),
            "bid": 19.9,
            "ask": 20.1,
            "last_price": 20.0,
        }
    }
    later_signal = Bar(
        start + timedelta(minutes=3),
        100,
        102,
        99,
        101,
        1000,
    )
    assert bot._queue_confirmed_entry(
        symbol="NIFTY_CE",
        score=80,
        signal="BUY",
        strategy_variant=None,
        signal_bars=[later_signal],
        history=[
            {"close": 98, "high": 99, "low": 97},
            {"close": 101, "high": 102, "low": 99},
        ],
        reasons=["new signal"],
        support_candidate=None,
        now=start + timedelta(minutes=3),
    ) == "entry_pending_confirmation"
    assert ("NIFTY_CE", "CE") in bot._pending_entries


def test_second_same_leg_signal_is_logged_and_ignored_while_pending(tmp_path):
    start = datetime(2026, 10, 29, 10, 0, tzinfo=IST)
    original = _pending("NIFTY_CE", start, 100.0)
    bot = _bot(tmp_path, [original], start + timedelta(minutes=1))
    bot._entry_score_floor = Mock(return_value=70)
    bot._capture_eligible_option_candles = Mock()
    later_bar = Bar(
        start + timedelta(minutes=1),
        101,
        103,
        100,
        102,
        1000,
    )

    outcome = bot._queue_confirmed_entry(
        symbol="NIFTY_CE",
        score=82,
        signal="BUY",
        strategy_variant=None,
        signal_bars=[later_bar],
        history=[{"close": 100}, {"close": 102}],
        reasons=["later signal"],
        support_candidate=None,
        now=start + timedelta(minutes=1),
    )

    assert outcome == "signal_ignored_pending"
    assert bot._pending_entries[("NIFTY_CE", "CE")]["signal_id"] == original[
        "signal_id"
    ]
    assert _events(tmp_path / "decisions.jsonl")[-1][
        "confirmation_event"
    ] == "signal_ignored_pending"


def test_confirmation_exception_cancels_without_retry(tmp_path):
    start = datetime(2026, 10, 29, 10, 0, tzinfo=IST)
    now = start + timedelta(minutes=2)
    signal = _pending("NIFTY_CE", start, 100.0)
    bot = _bot(tmp_path, [signal], now)
    bot.accuracy_filters.validate_entry_with_reason.side_effect = RuntimeError(
        "simulated validation failure"
    )

    bot._process_confirmed_entries(
        "NIFTY",
        Bar(start + timedelta(minutes=1), 101, 102, 100, 101, 1000),
        now,
    )

    bot._handle_buy_signal.assert_not_called()
    assert not bot._pending_entries
    event = _events(tmp_path / "decisions.jsonl")[-1]
    assert event["confirmation_event"] == "confirmation_error"
    assert event["cancellation_sub_reason"] == "revalidation_exception"


def test_order_uses_fresh_ask_and_calculates_risk_from_fill_price():
    now = datetime.now(IST)
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "trading_mode": "intraday_options",
        "entry_cutoff_minutes_before_close": 0,
        "option_quote_validated_stops_enabled": False,
        "option_premium_stop_pct": 0.10,
        "option_premium_target_pct": 0.20,
        "option_max_risk_per_lot_pct": 10.0,
        "option_min_lots": 1,
        "option_max_lots": 3,
    }
    bot.entry_mode = "confirmed"
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.latest_prices = {"NIFTY_CE": 18.25}
    bot.option_quote_cache = {
        "NIFTY_CE": {
            "timestamp": now,
            "bid": 18.20,
            "ask": 18.30,
            "last_price": 18.25,
        }
    }
    manager = IntradayManager()
    manager.set_contract_specs({"NIFTY_CE": {"lot_size": 1, "multiplier": 1}})
    bot.intraday_manager = manager
    bot.trade_journal = Mock()
    bot.trade_journal.get_open_trade.return_value = None
    bot.telegram_notifier = Mock()
    bot.telegram_notifier.format_trade.side_effect = lambda **fields: {
        "ticker": "NIFTY_CE",
        "entry": fields["entry"],
        "stop_loss": fields["stop_loss"],
        "take_profit": fields["take_profit"],
    }
    bot.kite_stream = SimpleNamespace(contract_symbols={})
    bot._entry_cutoff_reason = Mock(return_value=None)
    bot._live_entry_allowed = Mock(return_value=True)
    bot._can_open_trade_for_signal = Mock(return_value=(True, "OK"))
    bot._options_enabled = Mock(return_value=True)
    bot._option_adaptive_exit_enabled = Mock(return_value=False)
    bot._staged_option_targets_enabled = Mock(return_value=False)
    bot._option_entry_target_pct = Mock(return_value=0.20)
    bot._calculate_option_quantity = Mock(return_value=1)
    bot._option_target_increment = Mock(return_value=0.10)
    bot._entry_score_floor = Mock(return_value=70)
    bot._entry_risk_cap = Mock(return_value=1000.0)
    bot._persist_current_live_risk_state = Mock()

    result = bot._handle_buy_signal(
        "NIFTY_CE",
        18.25,
        80,
        confirmed_entry_metadata={
            "entry_mode": "confirmed",
            "route": "scored",
            "signal_time": now.isoformat(),
            "signal_close": 100.0,
            "confirmation_candle_time": (now + timedelta(minutes=1)).isoformat(),
            "confirmation_close": 101.0,
            "confirmation_result": "passed",
        },
        force_ask_fill=True,
    )

    assert result == "trade_opened"
    position = manager.active_positions["NIFTY_CE"]
    assert position["entry_price"] == 18.30
    assert position["stop_loss"] == pytest.approx(18.30 * 0.9)
    assert position["take_profit"] == pytest.approx(18.30 * 1.2)
    bot._calculate_option_quantity.assert_called_once_with(
        "NIFTY_CE", 18.25, 0.10
    )
    trade = bot.trade_journal.log_trade.call_args.args[0]
    assert trade["entry_mode"] == "confirmed"
    assert trade["route"] == "scored"
    assert trade["entry"] == 18.30
    assert trade["entry_quote_bid"] == 18.20
    assert trade["entry_quote_ask"] == 18.30


def test_prior_process_pending_signal_is_logged_as_expired_on_restart(tmp_path):
    path = tmp_path / "decisions.jsonl"
    journal = DecisionJournal(str(path))
    start = datetime(2026, 10, 29, 10, 0, tzinfo=IST)
    journal.log_decision(
        {
            "timestamp": start.isoformat(),
            "event": "entry_confirmation",
            "confirmation_event": "signal_generated",
            "signal_id": "NIFTY_CE|CE|test",
            "ticker": "NIFTY_CE",
            "contract_id": "NFO:NIFTY_CE",
            "signal": "BUY",
            "score": 80,
            "route": "scored",
            "signal_time": start.isoformat(),
            "signal_close": 100.0,
            "signal_bar": {"time": start.isoformat(), "close": 100.0},
            "signal_premium": 20.0,
        }
    )
    bot = object.__new__(KiteTradingBot)
    bot.entry_mode = "confirmed"
    bot.decision_journal = DecisionJournal(str(path))
    bot._pending_entries = {}

    bot._expire_unfinished_confirmed_entries()

    event = _events(path)[-1]
    assert event["confirmation_event"] == "expired_signal"
    assert event["cancellation_sub_reason"] == "restart"


def test_confirmation_signals_are_processed_by_score(tmp_path):
    start = datetime(2026, 10, 29, 10, 0, tzinfo=IST)
    now = start + timedelta(minutes=2)
    signals = [
        _pending("NIFTY_CE", start, 100.0, score=75),
        _pending("NIFTY_PE", start, 200.0, score=85),
    ]
    bot = _bot(tmp_path, signals, now)
    bot._handle_buy_signal = Mock(
        side_effect=["trade_opened", "trade_opened"]
    )

    bot._process_confirmed_entries(
        "NIFTY",
        Bar(start + timedelta(minutes=1), 150, 151, 149, 150, 1000),
        now,
    )

    assert [
        call.args[0] for call in bot._handle_buy_signal.call_args_list
    ] == ["NIFTY_PE", "NIFTY_CE"]
