from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from market_bot.accuracy_filters import AccuracyFilters
from market_bot.bar_builder import Bar
from market_bot.engine import SupportResistanceReversal
from market_bot.intraday_manager import IntradayManager
from market_bot.kite_main import KiteTradingBot


IST = ZoneInfo("Asia/Kolkata")


def _option_bot(now, *, mode="PAPER", fallback=True):
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "mode": mode,
        "trading_mode": "intraday_options",
        "option_quote_max_age_seconds": 60,
        "option_min_premium": 12,
        "option_max_premium": 800,
        "option_min_volume": 200,
        "option_min_oi": 400,
        "option_iv_min": 0.08,
        "option_iv_max": 1.2,
        "stale_quote_candle_fallback": fallback,
        "option_candle_momentum": True,
        "index_persistence_pass": True,
        "instrument_tokens": {"NIFTY_CE": 123},
        "bar_interval_seconds": 60,
    }
    bot.paper_trading_enabled = mode == "PAPER"
    bot.live_orders_enabled = mode == "LIVE"
    bot.option_quote_cache = {
        "NIFTY_CE": {
            "last_price": 99,
            "bid": 104,
            "ask": 105,
            "volume": 500,
            "oi": 1000,
            "timestamp": now - timedelta(seconds=80),
        }
    }
    return bot


def test_stale_quote_fallback_uses_recent_completed_candle_and_conservative_fill():
    now = datetime(2026, 10, 30, 10, 0, tzinfo=IST)
    bot = _option_bot(now)
    candle = Bar(
        now - timedelta(minutes=1),
        100,
        103,
        99,
        101,
        1000,
    )

    allowed, reason = bot._option_quality_gate(
        "NIFTY_CE", "BUY", now=now, option_candle=candle
    )

    context = bot._option_gate_context["NIFTY_CE"]
    assert allowed is True
    assert reason == "OK"
    assert context["quote_source"] == "candle_fallback"
    assert context["quote_age_seconds"] == 80
    assert context["candle_age_seconds"] == 0
    assert context["gate_reference_price"] == 101.05
    assert context["fallback_fill_price"] == 105.05


def test_stale_quote_fallback_rejects_old_candle_and_is_paper_only():
    now = datetime(2026, 10, 30, 10, 0, tzinfo=IST)
    old_candle = Bar(now - timedelta(seconds=181), 100, 103, 99, 101, 1000)
    bot = _option_bot(now)

    allowed, reason = bot._option_quality_gate(
        "NIFTY_CE", "BUY", now=now, option_candle=old_candle
    )

    assert allowed is False
    assert reason.startswith("option quote stale")

    live_bot = _option_bot(now, mode="LIVE")
    recent_candle = Bar(now - timedelta(minutes=1), 100, 103, 99, 101, 1000)
    allowed, reason = live_bot._option_quality_gate(
        "NIFTY_CE", "BUY", now=now, option_candle=recent_candle
    )
    assert allowed is False
    assert reason.startswith("option quote stale")


def test_option_premium_rising_momentum_flag_is_paper_only():
    now = datetime(2026, 10, 30, 10, 0, tzinfo=IST)
    paper_bot = _option_bot(now)
    paper_bot.config["option_premium_rising_momentum_v2"] = True
    assert paper_bot._paper_change_enabled("option_premium_rising_momentum_v2")

    paper_bot.config["option_premium_rising_momentum_v2"] = False
    assert not paper_bot._paper_change_enabled(
        "option_premium_rising_momentum_v2"
    )

    live_bot = _option_bot(now, mode="LIVE")
    live_bot.config["option_premium_rising_momentum_v2"] = True
    assert not live_bot._paper_change_enabled(
        "option_premium_rising_momentum_v2"
    )


def test_option_momentum_measurement_uses_last_completed_option_candle():
    now = datetime(2026, 10, 30, 10, 0, tzinfo=IST)
    bot = _option_bot(now)
    underlying_candle = Bar(now - timedelta(minutes=1), 100, 110, 90, 101, 100)
    option_candle = Bar(now - timedelta(minutes=1), 100, 104, 100, 103, 1000)
    bot.bar_builder = SimpleNamespace(
        get_bars=lambda token, limit: [underlying_candle]
    )
    bot.option_quote_cache["NIFTY_CE"]["timestamp"] = now

    measurements = bot._decision_gate_measurements(
        "NIFTY_CE",
        [option_candle],
        "BUY",
        75,
        "primary",
        option_candle,
    )

    assert measurements["body_ratio"] == 0.75
    assert measurements["body_ratio_threshold"] == 0.6
    assert measurements["body_ratio_source"] == "last_completed_option_candle"
    assert measurements["body_ratio_passed"] is True


def test_index_persistence_requires_three_signals_premium_rise_and_confirmed_level():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "index_persistence_pass": True,
        "mode": "PAPER",
        "trading_mode": "intraday_options",
    }
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    candidate = SupportResistanceReversal(
        signal="BUY",
        level=25000,
        touches=3,
        bars_since_touch=1,
        bar_time=datetime(2026, 10, 30, 10, 0, tzinfo=IST),
    )

    assert not bot._index_persistence_pass(
        "NIFTY_CE",
        "BUY",
        datetime(2026, 10, 30, 10, 0, tzinfo=IST),
        100,
        None,
    )
    assert not bot._index_persistence_pass(
        "NIFTY_CE",
        "BUY",
        datetime(2026, 10, 30, 10, 2, tzinfo=IST),
        102,
        None,
    )
    assert bot._index_persistence_pass(
        "NIFTY_CE",
        "BUY",
        datetime(2026, 10, 30, 10, 4, tzinfo=IST),
        104,
        candidate,
    )


def _quality_bot(symbol, premium, *, mode="PAPER", **overrides):
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "mode": mode,
        "trading_mode": "intraday_options",
        "option_quote_max_age_seconds": 60,
        "option_min_premium": 12,
        "support_reversal_min_premium": 5,
        "support_reversal_enabled": True,
        "option_max_premium": 800,
        "option_min_volume": 200,
        "option_min_oi": 400,
        "option_iv_min": 0.08,
        "option_iv_max": 1.2,
        "premium_floor_v2": True,
        "banknifty_caps_v2": True,
        "nifty_vol_floor_v2": True,
        **overrides,
    }
    bot.paper_trading_enabled = mode == "PAPER"
    bot.live_orders_enabled = mode == "LIVE"
    bot.option_quote_cache = {
        symbol: {
            "last_price": premium,
            "bid": premium - 1,
            "ask": premium,
            "volume": 1000,
            "oi": 1000,
            "timestamp": datetime.now(IST),
        }
    }
    return bot


def test_premium_floor_v2_enforces_general_and_support_reversal_boundaries():
    bot = _quality_bot("NIFTY_CE", 14.9)
    assert bot._option_quality_gate("NIFTY_CE", "BUY") == (
        False,
        "premium too low: 14.9 < 15.0",
    )
    bot.option_quote_cache["NIFTY_CE"]["last_price"] = 15.0
    assert bot._option_quality_gate("NIFTY_CE", "BUY") == (True, "OK")

    bot.option_quote_cache["NIFTY_CE"]["last_price"] = 11.9
    assert bot._option_quality_gate(
        "NIFTY_CE", "BUY", minimum_premium_override=5.0
    ) == (False, "premium too low: 11.9 < 12.0")
    bot.option_quote_cache["NIFTY_CE"]["last_price"] = 12.0
    assert bot._option_quality_gate(
        "NIFTY_CE", "BUY", minimum_premium_override=5.0
    ) == (True, "OK")


def test_banknifty_premium_cap_is_scoped_to_banknifty():
    banknifty = _quality_bot("BANKNIFTY_CE", 950)
    assert banknifty._option_quality_gate("BANKNIFTY_CE", "BUY") == (True, "OK")
    banknifty.option_quote_cache["BANKNIFTY_CE"]["last_price"] = 1050
    assert "premium too high" in banknifty._option_quality_gate(
        "BANKNIFTY_CE", "BUY"
    )[1]

    for symbol in ("NIFTY_CE", "TCS_CE"):
        bot = _quality_bot(symbol, 900)
        assert "premium too high" in bot._option_quality_gate(symbol, "BUY")[1]


def _banknifty_sizing_bot():
    bot = _quality_bot("BANKNIFTY_CE", 600)
    bot.config.update(
        {
            "account_size": 100000,
            "max_risk_per_trade": 1000,
            "max_open_risk_pct": 3.0,
            "capital_based_risk_v2": False,
            "option_min_lots": 1,
            "option_max_lots": 3,
            "option_premium_stop_pct": 0.10,
        }
    )
    manager = IntradayManager(
        account_size=100000,
        max_risk_per_trade=1000,
        daily_max_loss_pct=10.0,
    )
    manager.set_contract_specs(
        {"BANKNIFTY_CE": {"lot_size": 30, "multiplier": 1}}
    )
    bot.intraday_manager = manager
    return bot


def test_banknifty_risk_cap_boundary_and_exactly_one_lot():
    bot = _banknifty_sizing_bot()
    premium_at_cap = 2500 / (30 * 0.10)
    assert bot._calculate_option_quantity(
        "BANKNIFTY_CE", premium_at_cap, 0.10
    ) == 30
    assert abs(
        bot._pending_entry_evaluations["BANKNIFTY_CE"][
            "estimated_initial_risk_rupees"
        ]
        - 2500
    ) < 1e-9

    assert bot._calculate_option_quantity(
        "BANKNIFTY_CE", 600, 0.10
    ) == 30
    assert bot._pending_entry_evaluations["BANKNIFTY_CE"][
        "option_lot_size"
    ] == 30

    assert bot._calculate_option_quantity(
        "BANKNIFTY_CE", premium_at_cap + 0.01, 0.10
    ) == 0
    assert bot._pending_entry_evaluations["BANKNIFTY_CE"][
        "rejection_reason"
    ] == "one_lot_exceeds_trade_risk_cap"


def test_banknifty_checks_remaining_aggregate_and_open_risk_budgets():
    bot = _banknifty_sizing_bot()
    bot.intraday_manager.daily_max_loss = 2000
    assert bot._calculate_option_quantity("BANKNIFTY_CE", 740, 0.10) == 0
    assert bot._pending_entry_evaluations["BANKNIFTY_CE"][
        "rejection_reason"
    ] == "aggregate_daily_risk_budget_exceeded"

    bot = _banknifty_sizing_bot()
    bot.intraday_manager.set_contract_specs(
        {
            "BANKNIFTY_CE": {"lot_size": 30, "multiplier": 1},
            "NIFTY_CE": {"lot_size": 1, "multiplier": 1},
        }
    )
    bot.intraday_manager.register_position(
        "NIFTY_CE", "BUY", 100, 100, 90, 120
    )
    assert bot._calculate_option_quantity("BANKNIFTY_CE", 740, 0.10) == 0
    assert bot._pending_entry_evaluations["BANKNIFTY_CE"][
        "rejection_reason"
    ] == "max_open_risk_pct_exceeded"


def _capital_sizing_bot(symbol, lot_size, *, mode="PAPER", flag=True):
    bot = _quality_bot(
        symbol,
        150,
        mode=mode,
        capital_based_risk_v2=flag,
        account_size=100000,
        max_capital_per_trade_pct=20.0,
        banknifty_max_capital_per_trade_pct=30.0,
        max_open_risk_pct=4.0,
        option_min_lots=1,
        option_max_lots=3,
        option_premium_stop_pct=0.10,
    )
    manager = IntradayManager(
        account_size=100000,
        max_risk_per_trade=1000,
        daily_max_loss_pct=10.0,
    )
    manager.set_contract_specs({symbol: {"lot_size": lot_size, "multiplier": 1}})
    bot.intraday_manager = manager
    return bot


def test_capital_based_sizing_uses_invested_capital_for_nifty():
    bot = _capital_sizing_bot("NIFTY_CE", 65)
    assert bot._calculate_option_quantity("NIFTY_CE", 150, 0.10) == 130
    evaluation = bot._pending_entry_evaluations["NIFTY_CE"]
    assert evaluation["lots"] == 2
    assert evaluation["invested_amount"] == 19_500
    assert evaluation["risk_amount"] == 1_950
    assert evaluation["max_capital_per_trade_used_amount"] == 20_000
    assert evaluation["lots_reduced_reason"] == "max_capital_per_trade_cap"

    assert bot._calculate_option_quantity("NIFTY_CE", 160, 0.10) == 65
    assert bot._pending_entry_evaluations["NIFTY_CE"]["lots"] == 1
    assert bot._calculate_option_quantity("NIFTY_CE", 310, 0.10) == 0
    assert (
        bot._pending_entry_evaluations["NIFTY_CE"]["rejection_reason"]
        == "ONE_LOT_EXCEEDS_CAPITAL_CAP"
    )


def test_capital_based_risk_uses_the_configured_ten_percent_stop():
    bot = _capital_sizing_bot("NIFTY_CE", 65)
    assert bot._calculate_option_quantity("NIFTY_CE", 100, 0.06) == 195
    evaluation = bot._pending_entry_evaluations["NIFTY_CE"]
    assert evaluation["option_stop_pct"] == 0.10
    assert evaluation["risk_amount"] == 1_950


def test_capital_based_sizing_handles_sbin_banknifty_and_premium_cap():
    sbin = _capital_sizing_bot("SBIN_CE", 750)
    assert sbin._calculate_option_quantity("SBIN_CE", 25, 0.10) == 750
    sbin_evaluation = sbin._pending_entry_evaluations["SBIN_CE"]
    assert sbin_evaluation["lots"] == 1
    assert sbin_evaluation["invested_amount"] == 18_750
    assert sbin_evaluation["risk_amount"] == 1_875

    banknifty = _capital_sizing_bot("BANKNIFTY_CE", 30)
    assert banknifty._calculate_option_quantity("BANKNIFTY_CE", 850, 0.10) == 30
    banknifty_evaluation = banknifty._pending_entry_evaluations["BANKNIFTY_CE"]
    assert banknifty_evaluation["lots"] == 1
    assert banknifty_evaluation["invested_amount"] == 25_500
    assert banknifty_evaluation["risk_amount"] == 2_550
    assert banknifty_evaluation["max_capital_per_trade_used_amount"] == 30_000
    banknifty.config["banknifty_caps_v2"] = False
    assert banknifty._calculate_option_quantity("BANKNIFTY_CE", 850, 0.10) == 30
    banknifty.option_quote_cache["BANKNIFTY_CE"]["last_price"] = 1050
    assert banknifty._option_quality_gate("BANKNIFTY_CE", "BUY") == (
        False,
        "premium too high: 1050.0 > 1000.0",
    )


def test_capital_sizing_reduces_for_daily_budget_and_enforces_four_percent_open_cap():
    reduced = _capital_sizing_bot("NIFTY_CE", 65)
    reduced.intraday_manager.daily_max_loss = 1200
    assert reduced._calculate_option_quantity("NIFTY_CE", 150, 0.10) == 65
    reduced_evaluation = reduced._pending_entry_evaluations["NIFTY_CE"]
    assert reduced_evaluation["lots"] == 1
    assert reduced_evaluation["lots_reduced_reason"] == (
        "aggregate_daily_risk_budget"
    )

    no_daily_risk = _capital_sizing_bot("NIFTY_CE", 65)
    no_daily_risk.intraday_manager.daily_max_loss = 900
    assert no_daily_risk._calculate_option_quantity("NIFTY_CE", 150, 0.10) == 0
    assert (
        no_daily_risk._pending_entry_evaluations["NIFTY_CE"]["rejection_reason"]
        == "AGGREGATE_DAILY_RISK_BUDGET_EXCEEDED"
    )

    blocked = _capital_sizing_bot("NIFTY_CE", 65)
    blocked.intraday_manager.set_contract_specs(
        {
            "NIFTY_CE": {"lot_size": 65, "multiplier": 1},
            "NIFTY_PE": {"lot_size": 65, "multiplier": 1},
        }
    )
    blocked.intraday_manager.register_position(
        "NIFTY_PE", "BUY", 195, 120, 110, 150
    )
    assert blocked._calculate_option_quantity("NIFTY_CE", 150, 0.10) == 0
    assert (
        blocked._pending_entry_evaluations["NIFTY_CE"]["rejection_reason"]
        == "MAX_OPEN_RISK_PCT_EXCEEDED"
    )
    assert (
        blocked._pending_entry_evaluations["NIFTY_CE"]["max_open_risk_amount"]
        == 4_000
    )


def test_capital_based_risk_flag_is_paper_only_and_defaults_on():
    paper = _capital_sizing_bot("NIFTY_CE", 65)
    assert paper._paper_change_enabled("capital_based_risk_v2")
    assert paper._calculate_option_quantity("NIFTY_CE", 150, 0.10) == 130

    disabled = _capital_sizing_bot("NIFTY_CE", 65, flag=False)
    assert disabled._calculate_option_quantity("NIFTY_CE", 150, 0.10) == 65

    live = _capital_sizing_bot("NIFTY_CE", 65, mode="LIVE", flag=True)
    assert not live._paper_change_enabled("capital_based_risk_v2")
    assert live._calculate_option_quantity("NIFTY_CE", 150, 0.10) == 65


def test_nifty_volatility_floor_is_scoped_and_flag_gated():
    history = [
        {"high": 100.041, "low": 100.0, "close": 100.0}
        for _ in range(14)
    ]
    filters = AccuracyFilters(min_volatility_pct=0.05, max_volatility_pct=5)

    bot = _quality_bot("NIFTY_CE", 100)
    bot.accuracy_filters = filters
    assert bot._minimum_volatility_pct("NIFTY_CE") == 0.04
    assert filters.validate_entry_with_reason(
        "NIFTY_CE", "BUY", 75, history, {"close": 101}, {"close": 100},
        0, 10, 0, record_entry=False,
        min_volatility_pct=bot._minimum_volatility_pct("NIFTY_CE"),
    )[0]
    low_history = [
        {"high": 100.039, "low": 100.0, "close": 100.0}
        for _ in range(14)
    ]
    assert not filters.validate_entry_with_reason(
        "NIFTY_CE", "BUY", 75, low_history, {"close": 101}, {"close": 100},
        0, 10, 0, record_entry=False,
        min_volatility_pct=bot._minimum_volatility_pct("NIFTY_CE"),
    )[0]
    assert bot._minimum_volatility_pct("TCS_CE") == 0.05
    assert not filters.validate_entry_with_reason(
        "TCS_CE", "BUY", 75, history, {"close": 101}, {"close": 100},
        0, 10, 0, record_entry=False,
        min_volatility_pct=bot._minimum_volatility_pct("TCS_CE"),
    )[0]


def test_disabled_and_live_flags_preserve_baseline_gate_thresholds():
    disabled = _quality_bot(
        "NIFTY_CE",
        14.9,
        premium_floor_v2=False,
        nifty_vol_floor_v2=False,
    )
    assert disabled._option_quality_gate("NIFTY_CE", "BUY") == (True, "OK")
    assert disabled._minimum_volatility_pct("NIFTY_CE") == 0.05

    live = _quality_bot("BANKNIFTY_CE", 950, mode="LIVE")
    assert not live._paper_change_enabled("premium_floor_v2")
    assert not live._paper_change_enabled("banknifty_caps_v2")
    assert not live._paper_change_enabled("nifty_vol_floor_v2")
    assert "premium too high" in live._option_quality_gate(
        "BANKNIFTY_CE", "BUY"
    )[1]


def test_all_new_flags_off_replay_the_baseline_gate_decision_stream():
    decision_stream = [
        ("NIFTY_CE", 14.9, True),
        ("BANKNIFTY_CE", 950, False),
        ("TCS_CE", 900, False),
    ]
    results = []
    for symbol, premium, _ in decision_stream:
        bot = _quality_bot(
            symbol,
            premium,
            premium_floor_v2=False,
            banknifty_caps_v2=False,
            nifty_vol_floor_v2=False,
            capital_based_risk_v2=False,
        )
        results.append(bot._option_quality_gate(symbol, "BUY")[0])

    assert results == [expected for _, _, expected in decision_stream]

    bot = _quality_bot(
        "NIFTY_CE",
        100,
        premium_floor_v2=False,
        banknifty_caps_v2=False,
        nifty_vol_floor_v2=False,
    )
    assert bot._minimum_volatility_pct("NIFTY_CE") == 0.05
    assert bot._minimum_volatility_pct("TCS_CE") == 0.05
