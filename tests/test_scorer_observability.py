from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

import market_bot.kite_main as kite_main
from market_bot.bar_builder import Bar
from market_bot.engine import score_market
from market_bot.kite_main import KiteTradingBot
from market_bot.scorer_observability import (
    DIRECTIONAL_GATE_STATE_NAMES,
    GATE_STATE_NAMES,
    OPTION_SIDE_GATE_NAMES,
    build_independent_bar_gate_state,
    build_gate_state,
    encode_gate_state_v2,
    empty_gate_state,
    score_observation,
    scorer_inputs,
)
from market_bot.trade_journal import (
    DecisionJournal,
    PaperTradingRecorder,
    read_decisions,
    read_scorer_bars,
)


ROOT = Path(__file__).resolve().parents[1]
IST = ZoneInfo("Asia/Kolkata")


def _recorded_nifty_session():
    source = (
        ROOT
        / "data_uploads"
        / "kite_daily"
        / "2026-11-11"
        / "underlyings__NIFTY.csv"
    )
    if not source.exists():
        return []
    frame = pd.read_csv(source)
    return [
        {
            "time": datetime.fromisoformat(row.timestamp),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": int(row.volume),
        }
        for row in frame.itertuples(index=False)
    ]


def test_scorer_logging_toggle_preserves_scores_and_signals_on_recorded_session():
    bars = _recorded_nifty_session()
    assert bars, "Recorded NIFTY session is required for the equivalence test"
    config = json.loads((ROOT / "kite_config.example.json").read_text())
    disabled_results = []
    enabled_results = []
    for index in range(len(bars)):
        history = bars[max(0, index - 49):index + 1]
        score_kwargs = {
            "ema_fast": int(config.get("ema_fast", 9)),
            "ema_slow": int(config.get("ema_slow", 21)),
            "rsi_period": int(config.get("rsi_period", 14)),
            "hard_context_filter": bool(config.get("hard_context_filter", True)),
            "min_adx": float(config.get("min_adx", 18.0)),
            "sideways_range_pct": float(config.get("sideways_range_pct", 1.0)),
            "sideways_net_move_pct": float(
                config.get("sideways_net_move_pct", 1.0)
            ),
            "min_trend_strength": float(config.get("min_trend_strength", 0.02)),
            "trend_momentum_bonus_threshold": (
                float(config["trend_momentum_bonus_threshold"])
                if config.get("trend_momentum_bonus_threshold") is not None
                else None
            ),
            "signal_proximity_pct": float(config.get("signal_proximity_pct", 0.005)),
            "allow_trend_continuation": bool(
                config.get("allow_trend_continuation", False)
            ),
            "rsi_buy_block_above": float(
                config.get("rsi_buy_block_above", 80.0)
            ),
            "rsi_sell_block_below": float(
                config.get("rsi_sell_block_below", 25.0)
            ),
        }
        config["scorer_input_logging_v1"] = False
        disabled = score_market("NIFTY", history, **score_kwargs)
        disabled_results.append(disabled)

        config["scorer_input_logging_v1"] = True
        enabled = score_market("NIFTY", history, **score_kwargs)
        observation = score_observation("NIFTY", history, config)
        enabled_results.append(enabled)
        assert (
            observation["score"],
            observation["signal"],
            observation["reasons"],
        ) == (enabled.score, enabled.signal, enabled.reasons)

    assert enabled_results == disabled_results


def test_archived_nov_12_13_scorer_replay_matches_baseline_row_for_row():
    expected_hashes = {
        "12": "11831503d8e884204f2fa22eb10b6b0eb52a6dae76fb95937642b8c997d8433f",
        "13": "ad7e2724c7fc2c66b93ae46628ddb817fbfedc9191236447beea25d330c9cec0",
    }
    config = json.loads((ROOT / "kite_config.json").read_text(encoding="utf-8"))
    expected_rows = {"12": 3609, "13": 3589}

    for day, expected_hash in expected_hashes.items():
        parts = (
            ROOT
            / "paper_trading_data"
            / "2026-11"
            / "week_46"
            / f"day_{day}"
            / "scorer_bars"
        )
        frame = pd.concat(
            [
                pd.read_parquet(path, engine="fastparquet")
                for path in sorted(parts.glob("*.parquet"))
            ],
            ignore_index=True,
        )
        frame["_timestamp_order"] = pd.to_datetime(
            frame["timestamp"], utc=True
        )
        frame = frame.sort_values(
            ["_timestamp_order", "ticker"], kind="stable"
        )
        histories = {}
        replay = []
        for row in frame.to_dict(orient="records"):
            history = histories.setdefault(row["ticker"], [])
            last_bar_time = row.get("last_bar_time")
            if not history or history[-1]["time"] != last_bar_time:
                ohlc = json.loads(row.get("last_bar_ohlc") or "{}")
                if ohlc:
                    history.append(
                        {"time": last_bar_time, "volume": 0, **ohlc}
                    )
            first_bar_time = row.get("first_bar_time")
            history_window = [
                bar
                for bar in history
                if not first_bar_time or bar["time"] >= first_bar_time
            ][-100:]
            result = score_observation(
                row["ticker"], history_window, config
            )
            replay.append(
                [
                    row["timestamp"],
                    row["ticker"],
                    result["score"],
                    result["signal"],
                    result["score_components"],
                    result["reasons"],
                ]
            )

        assert len(replay) == expected_rows[day]
        payload = json.dumps(
            replay, separators=(",", ":"), sort_keys=True, ensure_ascii=True
        )
        assert hashlib.sha256(payload.encode()).hexdigest() == expected_hash


def test_scorer_inputs_use_only_the_production_current_session_window():
    previous_session = [
        {
            "time": datetime(2026, 11, 10, 9, 15 + index, tzinfo=IST),
            "open": 900.0 + index,
            "high": 902.0 + index,
            "low": 899.0 + index,
            "close": 901.0 + index,
            "volume": 1,
        }
        for index in range(35)
    ]
    current_session = [
        {
            "time": datetime(2026, 11, 11, 9, 15 + index, tzinfo=IST),
            "open": 100.0 + index,
            "high": 102.0 + index,
            "low": 99.0 + index,
            "close": 101.0 + index,
            "volume": 1,
        }
        for index in range(35)
    ]
    config = json.loads((ROOT / "kite_config.example.json").read_text())

    assert scorer_inputs(previous_session + current_session, config) == (
        scorer_inputs(current_session, config)
    )
    combined = score_observation(
        "NIFTY", previous_session + current_session, config
    )
    current = score_observation("NIFTY", current_session, config)
    assert (combined["score"], combined["signal"], combined["reasons"]) == (
        current["score"],
        current["signal"],
        current["reasons"],
    )


def test_scorer_bar_reader_aligns_mixed_parquet_schemas(tmp_path):
    day = tmp_path / "2026-11-11"
    parts = day / "scorer_bars"
    parts.mkdir(parents=True)
    old_schema = pd.DataFrame(
        [
            {
                "timestamp": "2026-11-11T09:15:00+05:30",
                "ticker": "NIFTY",
                "first_bar_time": "2026-11-11T09:15:00+05:30",
                "last_bar_time": "2026-11-11T09:15:00+05:30",
                "bar_complete": "True",
                "inputs": "{}",
                "score_components": "{}",
                "component_score": "0",
                "score": "0",
                "signal": "HOLD",
                "reasons": "[]",
            }
        ]
    )
    new_schema = old_schema.assign(observation_cpu_us="12.5")
    old_schema.to_parquet(
        parts / "scorer_bars_09_100000_000001.parquet",
        engine="fastparquet",
    )
    new_schema.to_parquet(
        parts / "scorer_bars_09_100100_000002.parquet",
        engine="fastparquet",
    )

    result = read_scorer_bars(day)

    assert len(result) == 2
    assert list(result.columns) == PaperTradingRecorder.SCORER_BAR_COLUMNS
    assert pd.isna(result.iloc[0]["observation_cpu_us"])
    assert result.iloc[1]["observation_cpu_us"] == "12.5"


def test_scorer_bar_writer_flushes_one_row_and_reports_persistence(tmp_path):
    recorder = PaperTradingRecorder(
        str(tmp_path / "paper"),
        config_hash="test-config",
        git_sha="test-sha",
        git_dirty=False,
    )
    recorder.record_scorer_bar(
        {
            "timestamp": "2026-11-11T09:15:00+05:30",
            "ticker": "NIFTY",
            "first_bar_time": "2026-11-11T09:15:00+05:30",
            "last_bar_time": "2026-11-11T09:15:00+05:30",
            "last_bar_ohlc": {
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.5,
            },
            "bar_complete": True,
            "inputs": {"ema_fast_value": 100.2},
            "score_components": {"ema_trend": 25},
            "component_score": 25,
            "score": 25,
            "signal": "HOLD",
            "reasons": ["not enough data"],
            "observation_cpu_us": 12.5,
        }
    )

    assert recorder.close_decisions(timeout=20)
    day = tmp_path / "paper" / "2026-11" / "week_46" / "day_11"
    result = read_scorer_bars(day)
    telemetry = recorder.decision_telemetry()

    assert len(result) == 1
    assert result.iloc[0]["ticker"] == "NIFTY"
    assert result.iloc[0]["config_hash"] == "test-config"
    assert telemetry["scorer_bar_rows_enqueued"] == 1
    assert telemetry["scorer_bar_payload_bytes_enqueued"] > 0
    assert telemetry["scorer_bar_written_bytes"] > 0
    assert telemetry["scorer_bar_observation_cpu_us"] == 12.5


def test_scorer_queue_drop_does_not_count_as_enqueued(tmp_path):
    recorder = PaperTradingRecorder(str(tmp_path / "paper"))
    assert recorder.close_decisions(timeout=20)

    recorder.record_scorer_bar(
        {
            "timestamp": "2026-11-11T09:15:00+05:30",
            "ticker": "NIFTY",
            "observation_cpu_us": 12.5,
        }
    )

    telemetry = recorder.decision_telemetry()
    assert telemetry["drops"] == 1
    assert telemetry["scorer_bar_rows_enqueued"] == 0
    assert telemetry["scorer_bar_payload_bytes_enqueued"] == 0
    assert telemetry["scorer_bar_observation_cpu_us"] == 0


def test_decision_archive_persists_score_components(tmp_path):
    recorder = PaperTradingRecorder(str(tmp_path / "paper"))
    recorder.record_decision(
        {
            "timestamp": "2026-11-11T09:15:00+05:30",
            "ticker": "NIFTY_CE",
            "signal": "BUY",
            "score": 75,
            "score_components": {
                "ema_trend": 25,
                "support_reversal_adjustment": 50,
            },
            "component_score": 75,
        }
    )
    assert recorder.close_decisions(timeout=20)

    day = tmp_path / "paper" / "2026-11" / "week_46" / "day_11"
    decision = read_decisions(day).iloc[0]
    assert json.loads(decision["score_components"]) == {
        "ema_trend": 25,
        "support_reversal_adjustment": 50,
    }
    assert decision["component_score"] == "75"


def test_trade_journal_defaults_order_time_to_entry_time(tmp_path):
    recorder = PaperTradingRecorder(str(tmp_path / "paper"))
    recorder.record_trade(
        {
            "trade_id": "test-trade",
            "timestamp": "2026-11-11T10:00:00+05:30",
            "entry_time": "2026-11-11T09:59:58+05:30",
            "ticker": "NIFTY_CE",
            "action": "BUY",
        }
    )

    path = (
        tmp_path
        / "paper"
        / "2026-11"
        / "week_46"
        / "day_11"
        / "trades.parquet"
    )
    trade = pd.read_parquet(path, engine="fastparquet").iloc[0]
    assert trade["order_time"] == "2026-11-11T09:59:58+05:30"
    assert json.loads(trade["gate_passed_at"])["order"] == trade["order_time"]


def test_scorer_bar_exception_does_not_interrupt_bar_decision(
    monkeypatch, tmp_path
):
    now = datetime(2026, 11, 11, 9, 15, tzinfo=IST)
    bar = Bar(now, 100.0, 101.0, 99.0, 100.5, 1)
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "scorer_input_logging_v1": True,
        "bar_interval_seconds": 60,
        "trading_mode": "intraday_futures",
        "instrument_tokens": {"NIFTY": 1},
    }
    bot.symbol_map = {1: "NIFTY"}
    bot.option_capture_writer = None
    bot.intraday_manager = SimpleNamespace(
        should_exit_all_positions=lambda: False
    )
    bot.bar_builder = SimpleNamespace(get_bars=lambda *_args, **_kwargs: [])
    bot._try_option_range_breakout = lambda *_args, **_kwargs: None
    bot._record_decision = lambda *args, **kwargs: decisions.append(args)
    decisions = []
    monkeypatch.setattr(
        kite_main,
        "score_observation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("injected scorer telemetry failure")
        ),
    )

    bot.on_bar_complete("1", bar)

    assert len(decisions) == 1
    assert decisions[0][4] == "HOLD"
    assert bot._feature_observation_error_counts["scorer_bar_observation"] == 1


def test_scorer_adjustments_are_exposed_without_changing_score_values():
    bot = object.__new__(KiteTradingBot)
    bot.config = {"scorer_input_logging_v1": True}
    bot._scorer_context_by_symbol = {
        "LT_CE": {
            "score_components": {"ema_trend": 25, "rsi": 20},
            "component_score": 45,
            "scorer_inputs": {"pivot_levels": []},
        }
    }

    bot._record_scorer_score_adjustment(
        "LT_CE",
        "support_reversal_adjustment",
        30,
        pivot_level=4098.0,
        pivot_touches=2,
        pivot_kind="support",
    )

    context = bot._scorer_context_by_symbol["LT_CE"]
    assert context["score_components"] == {
        "ema_trend": 25,
        "rsi": 20,
        "support_reversal_adjustment": 30,
    }
    assert context["component_score"] == 75
    assert context["scorer_inputs"]["pivot_levels"] == [
        {"kind": "support", "level": 4098.0, "touches": 2}
    ]


def test_gate_state_reconstructs_first_pass_time_for_one_logged_option_leg(
    tmp_path,
):
    journal_path = tmp_path / "decision_log.jsonl"
    journal = DecisionJournal(str(journal_path))
    bot = object.__new__(KiteTradingBot)
    bot.mode = "PAPER"
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.config = {}
    timestamps = [
        "2026-11-12T09:30:00+05:30",
        "2026-11-12T09:31:00+05:30",
        "2026-11-12T09:32:00+05:30",
    ]
    for index, timestamp in enumerate(timestamps):
        state = bot._gate_state_for_decision(
            symbol="NIFTY_CE",
            signal="BUY",
            outcome="trade_opened" if index == 2 else "hold",
            timestamp=timestamp,
            score=75,
            reasons=[],
            scorer_context={
                "scorer_inputs": {
                    "regime_label": "TRENDING",
                    "ema_fast_value": 101 if index else 99,
                    "ema_slow_value": 100,
                    "adx_value": 25,
                    "rsi_value": 60,
                    "macd_value": 2,
                    "macd_previous_value": 1,
                }
            },
            measurements={
                "adx_threshold": 18,
                "score_threshold": 70,
                "quote_age_seconds": 70 if index == 0 else 10,
                "quote_age_threshold_seconds": 60,
            },
            entry_evaluation=None,
        )
        journal.log_decision(
            {
                "event": "bar_decision",
                "timestamp": timestamp,
                "ticker": "NIFTY_CE",
                "signal": "BUY",
                "outcome": "trade_opened" if index == 2 else "hold",
                **state,
            }
        )
    assert journal.close()

    records = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
    ]
    first_passed = {}
    for record in records:
        timestamp, codes = record["gate_state_v2"].split("|", 1)
        assert len(codes) == len(GATE_STATE_NAMES)
        for name, code in zip(GATE_STATE_NAMES, codes):
            if code == "P":
                first_passed.setdefault(name, timestamp)

    assert first_passed == {
        "regime_breakout": timestamps[0],
        "adx": timestamps[0],
        "rsi": timestamps[0],
        "macd": timestamps[0],
        "score_threshold": timestamps[0],
        "ema": timestamps[1],
        "quote_freshness": timestamps[1],
        "order": timestamps[2],
    }
    assert "gate_state_v2_full" in records[0]
    assert "gate_state_v2_full" not in records[1]
    assert set(records[0]["gate_state_v2_full"]) == set(
        empty_gate_state(timestamps[0])
    )
    assert set(records[1]["gate_state_v2_changes"]) == {
        "ema",
        "quote_freshness",
    }
    assert set(records[1]["gate_state_v2_changes"]["ema"]) == {
        "observed_value",
        "threshold",
        "reason_code",
    }
    assert set(records[2]["gate_state_v2_changes"]) == {"order"}
    assert "gate_state" not in records[0]


def test_gate_state_v2_scopes_prior_state_by_direction_and_day():
    bot = object.__new__(KiteTradingBot)
    bot.mode = "PAPER"
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.config = {}

    def evaluate(signal, timestamp):
        return bot._gate_state_for_decision(
            symbol="NIFTY_CE",
            signal=signal,
            outcome="hold",
            timestamp=timestamp,
            score=None,
            reasons=[],
            scorer_context={},
            measurements={},
            entry_evaluation=None,
        )

    first = evaluate("BUY", "2026-11-12T09:30:00+05:30")
    other_direction = evaluate("SELL", "2026-11-12T09:31:00+05:30")
    same_direction = evaluate("SELL", "2026-11-12T09:32:00+05:30")
    next_day = evaluate("SELL", "2026-11-13T09:30:00+05:30")

    assert "gate_state_v2_full" in first
    assert "gate_state_v2_full" not in other_direction
    assert set(other_direction["gate_state_v2_changes"]) == set(
        GATE_STATE_NAMES
    )
    assert "gate_state_v2_changes" not in same_direction
    assert "gate_state_v2_full" in next_day


def test_gate_state_records_failed_score_for_hold_evaluation():
    timestamp = "2026-11-12T09:30:00+05:30"
    state = build_gate_state(
        symbol="NIFTY",
        signal="HOLD",
        outcome="hold",
        timestamp=timestamp,
        score=62,
        reasons=["score below entry threshold"],
        scorer_inputs={},
        measurements={"score_threshold": 70},
        support_evaluation={},
        entry_evaluation={},
        config={},
    )

    assert state["score_threshold"] == {
        "state": "fail",
        "observed_value": 62,
        "threshold": 70,
        "evaluation_timestamp": timestamp,
        "reason_code": "evaluated",
    }


def test_independent_gate_evaluation_does_not_short_circuit_on_score_failure():
    history = [
        {
            "time": datetime(2026, 11, 12, 9, 15 + index, tzinfo=IST),
            "open": 100.0 + index * 0.1,
            "high": 100.2 + index * 0.1,
            "low": 99.9 + index * 0.1,
            "close": 100.1 + index * 0.1,
            "volume": 1,
        }
        for index in range(15)
    ]
    scorer_inputs = {
        "regime_label": "TRENDING",
        "ema_fast_value": 101.0,
        "ema_slow_value": 100.0,
        "adx_value": 30.0,
        "rsi_value": 90.0,
        "macd_value": 2.0,
        "macd_previous_value": 1.0,
        "pivot_levels": [],
    }
    support_evaluation = {
        "evaluated": True,
        "candidate": False,
        "touches": 1,
    }
    config = {
        "min_entry_score": 70,
        "min_adx": 18,
        "rsi_buy_block_above": 80,
        "rsi_sell_block_below": 25,
        "support_reversal_min_touches": 2,
    }

    buy = build_independent_bar_gate_state(
        symbol="NIFTY",
        direction="BUY",
        timestamp="2026-11-12T09:29:00+05:30",
        score=45,
        reasons=[],
        scorer_inputs=scorer_inputs,
        history=history,
        support_evaluation=support_evaluation,
        config=config,
    )
    sell = build_independent_bar_gate_state(
        symbol="NIFTY",
        direction="SELL",
        timestamp="2026-11-12T09:29:00+05:30",
        score=45,
        reasons=[],
        scorer_inputs=scorer_inputs,
        history=history,
        support_evaluation=support_evaluation,
        config=config,
    )

    for state in (buy, sell):
        assert state["score_threshold"]["state"] == "fail"
        assert state["ema"]["state"] != "not_evaluated"
        assert state["adx"]["state"] == "pass"
        assert state["rsi"]["state"] != "not_evaluated"
        assert state["macd"]["state"] != "not_evaluated"
        assert state["pivot_touches"]["state"] == "fail"
        assert state["support_reversal_detector"]["state"] == "fail"
        assert state["volatility_band"]["state"] != "not_evaluated"
        assert state["confirmation"]["state"] != "not_evaluated"
    assert buy["ema"]["state"] == "pass"
    assert buy["rsi"]["state"] == "fail"
    assert buy["confirmation"]["state"] == "pass"
    assert sell["ema"]["state"] == "fail"
    assert sell["rsi"]["state"] == "pass"
    assert sell["confirmation"]["state"] == "fail"
    for name in (
        "option_candle_momentum_direction",
        "option_candle_momentum_body",
        "premium_range",
        "quote_freshness",
        "risk_cap",
        "capital_cap",
        "order",
    ):
        assert buy[name]["state"] == "not_evaluated"
        assert sell[name]["state"] == "not_evaluated"


def test_completed_underlying_bar_logs_both_directions_without_scorer_logging(
    monkeypatch,
):
    timestamp = datetime(2026, 11, 12, 9, 15, tzinfo=IST)
    bars = [
        Bar(
            timestamp + pd.Timedelta(minutes=index),
            100 + index,
            101 + index,
            99 + index,
            100.5 + index,
            1,
        )
        for index in range(30)
    ]
    observation = {
        "ema_fast_value": 120.0,
        "ema_slow_value": 119.0,
        "rsi_value": 60.0,
        "adx_value": 25.0,
        "macd_value": 2.0,
        "macd_previous_value": 1.0,
        "regime_label": "TRENDING",
        "regime_range_pct": 0.2,
        "regime_20_bar_move_pct": 0.5,
        "near_recent_high": False,
        "near_recent_low": False,
        "recent_high": 129.0,
        "recent_low": 120.0,
        "pivot_levels": [],
        "score_components": {},
        "component_score": 0,
        "score": 45,
        "signal": "HOLD",
        "reasons": [],
    }

    def detect_without_candidate(_history, *, diagnostics=None):
        diagnostics.update(
            {
                "evaluated": True,
                "pivot_touches": 1,
                "levels": [
                    {
                        "level": 99.8,
                        "kind": "support",
                        "touches": 2,
                        "distance_pct": 0.1,
                        "passed_distance_limit": True,
                        "passed_touch_minimum": True,
                    }
                ],
                "thresholds": {
                    "minimum_touches": 2,
                    "maximum_entry_distance_pct": 0.4,
                },
            }
        )
        return None

    bot = object.__new__(KiteTradingBot)
    bot.mode = "PAPER"
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.config = {
        "bar_interval_seconds": 60,
        "instrument_tokens": {"NIFTY": 1},
        "scorer_input_logging_v1": False,
        "gate_state_logging_v1": True,
        "min_entry_score": 70,
    }
    bot.bar_builder = SimpleNamespace(
        get_bars=lambda _token, limit: bars[-limit:]
    )
    bot.decision_journal = SimpleNamespace(paper_recorder=None)

    monkeypatch.setattr(kite_main, "score_observation", lambda *_args: observation)
    monkeypatch.setattr(kite_main, "aggregate_ohlcv_bars", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        kite_main,
        "detect_support_resistance_reversal",
        detect_without_candidate,
    )

    bot._record_completed_scorer_bar("NIFTY", bars[-1])
    recorded = bot._take_gate_state_for_bar("NIFTY", bars[-1])
    directions = recorded["gate_state_v2_by_direction"]

    assert set(directions) == {"BUY", "SELL"}
    assert "gate_state_v2_full" in directions["BUY"]
    assert "gate_state_v2_full" not in directions["SELL"]
    support_observed = directions["BUY"]["gate_state_v2_full"][
        "support_reversal_detector"
    ]["observed_value"]
    assert support_observed["levels"][0]["kind"] == "support"
    assert support_observed["thresholds"] == {
        "minimum_touches": 2,
        "maximum_entry_distance_pct": 0.4,
    }
    for direction_state in directions.values():
        _, codes = direction_state["gate_state_v2"].split("|", 1)
        assert len(codes) == len(DIRECTIONAL_GATE_STATE_NAMES)
        assert direction_state.get("gate_state_v2_changes") or direction_state.get(
            "gate_state_v2_full"
        )
    assert bot._take_gate_state_for_bar("NIFTY", bars[-1]) == {}


def test_support_reversal_timing_and_warmup_are_recorded_per_bar():
    timestamp = datetime(2026, 11, 12, 9, 15, tzinfo=IST)
    history = [
        {
            "time": timestamp + pd.Timedelta(minutes=index),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1,
        }
        for index in range(5)
    ]
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "bar_interval_seconds": 60,
        "support_reversal_enabled": True,
    }

    timing = bot._support_reversal_timing(
        history,
        history[-1]["time"],
        completed_aggregation_bars=1,
        minimum_aggregation_bars=10,
    )

    assert timing["boundary_time"] == "2026-11-12T09:15:00+05:30"
    assert timing["next_evaluation_time"] == "2026-11-12T09:20:00+05:30"
    assert timing["minutes_to_next_evaluation"] == 0
    assert [
        item["minutes_to_next_evaluation"]
        for item in timing["completed_bars"]
    ] == [4, 3, 2, 1, 0]
    assert timing["completed_aggregation_bars"] == 1
    assert timing["minimum_aggregation_bars"] == 10


def test_option_gate_logging_reports_missing_inputs_and_available_lot_size():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "bar_interval_seconds": 60,
        "instrument_tokens": {"NIFTY_CE": 101},
        "options_underlyings": ["NIFTY"],
    }
    bot.option_quote_cache = {}
    bot.kite_stream = SimpleNamespace(contract_symbols={})
    bot.intraday_manager = SimpleNamespace(
        contract_specs={"NIFTY_CE": {"lot_size": 50}},
    )

    measured = bot._option_bar_gate_measurements(
        "NIFTY_CE",
        "BUY",
        datetime(2026, 11, 12, 9, 30, tzinfo=IST),
        None,
    )
    results = measured["blocker_results"]

    assert results["option_leg"]["passed"] is True
    assert results["lot_size"]["passed"] is True
    assert results["premium_range"]["reason_code"] == "no_quote"
    assert results["risk_cap"]["reason_code"] == "no_quote"
    assert results["capital_cap"]["reason_code"] == "no_quote"
    assert results["position_size"]["reason_code"] == "no_quote"
    assert results["option_contract"]["reason_code"] == (
        "contract_metadata_unavailable"
    )
    assert measured["option_candle_missing_reason"] == "no_candle"


def test_entry_window_observation_matches_actual_session_and_cutoff_rules():
    bot = object.__new__(KiteTradingBot)
    bot.config = {
        "entry_cutoff_minutes_before_close": 45,
        "late_window_enabled": False,
    }

    def entry_window_at(bar_minute):
        return bot._bar_blocker_measurements(
            "NIFTY",
            "BUY",
            datetime(2026, 11, 12, 9, 0, tzinfo=IST)
            + pd.Timedelta(minutes=bar_minute),
            [],
            {},
            [],
            support_evaluation={},
            benchmark_context={},
        )["blocker_results"]["entry_window"]

    opening_start = entry_window_at(14)
    opening_end = entry_window_at(29)
    after_open = entry_window_at(30)
    at_cutoff = entry_window_at(344)
    closing_start = entry_window_at(359)
    closing_end = entry_window_at(389)
    after_close = entry_window_at(390)

    assert opening_start["passed"] is False
    assert opening_start["observed_value"]["accuracy_filter_block"] == "opening_block"
    assert opening_end["passed"] is False
    assert opening_end["observed_value"]["accuracy_filter_block"] == "opening_block"
    assert after_open["passed"] is True
    assert opening_start["threshold"]["entry_cutoff_time"] == "14:45"
    assert at_cutoff["passed"] is False
    assert closing_start["passed"] is False
    assert closing_start["observed_value"]["accuracy_filter_block"] == "closing_block"
    assert closing_end["passed"] is False
    assert closing_end["observed_value"]["accuracy_filter_block"] == "closing_block"
    assert after_close["passed"] is False
    assert after_close["observed_value"]["accuracy_filter_block"] is None


def test_selected_option_legs_evaluate_candle_quote_risk_and_capital_gates():
    evaluation_time = datetime(2026, 11, 12, 9, 31, tzinfo=IST)
    bot = object.__new__(KiteTradingBot)
    bot.mode = "PAPER"
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.config = {
        "trading_mode": "intraday_options",
        "instrument_tokens": {"NIFTY_CE": 101, "NIFTY_PE": 102},
        "account_size": 100_000,
        "option_min_premium": 12,
        "option_max_premium": 800,
        "option_premium_stop_pct": 0.05,
        "option_max_risk_per_lot_pct": 10,
        "option_min_lots": 1,
        "option_max_lots": 3,
        "option_min_candle_body_ratio": 0.6,
        "option_min_volume": 200,
        "option_min_oi": 400,
        "option_iv_min": 0.08,
        "option_iv_max": 1.2,
        "option_quote_max_age_seconds": 60,
        "option_premium_rising_momentum_v2": True,
        "premium_floor_v2": False,
        "banknifty_caps_v2": False,
        "capital_based_risk_v2": False,
    }
    bot.option_quote_cache = {
        symbol: {
            "last_price": 100,
            "bid": 99.5,
            "ask": 100.5,
            "volume": 500,
            "oi": 1_000,
            "iv": 0.5,
            "timestamp": evaluation_time,
        }
        for symbol in ("NIFTY_CE", "NIFTY_PE")
    }
    bot.kite_stream = SimpleNamespace(
        contract_symbols={"NIFTY_CE": "NIFTY26NOV25000CE", "NIFTY_PE": "NIFTY26NOV25000PE"},
        contract_expiries={
            "NIFTY_CE": datetime(2026, 11, 17).date(),
            "NIFTY_PE": datetime(2026, 11, 17).date(),
        },
    )
    bot.intraday_manager = SimpleNamespace(
        contract_specs={
            "NIFTY_CE": {"lot_size": 50},
            "NIFTY_PE": {"lot_size": 50},
        },
        max_risk_per_trade=1_000,
        open_position_risk=lambda: 0,
    )
    option_bar = Bar(
        datetime(2026, 11, 12, 9, 30, tzinfo=IST),
        100,
        112,
        98,
        110,
        500,
    )

    for symbol, direction in (("NIFTY_CE", "BUY"), ("NIFTY_PE", "SELL")):
        measured = bot._option_bar_gate_measurements(
            symbol,
            direction,
            option_bar.timestamp,
            option_bar,
        )
        results = measured["blocker_results"]

        assert results["option_candle_momentum_direction"]["passed"] is True
        assert results["option_candle_momentum_body"]["passed"] is True
        assert results["option_expiry"]["passed"] is True
        assert results["option_market_quality"]["passed"] is True
        assert results["premium_range"]["passed"] is True
        assert results["quote_freshness"]["passed"] is True
        assert results["risk_cap"]["passed"] is True
        assert results["capital_cap"]["passed"] is True
        assert results["position_size"]["passed"] is True
        assert results["lot_size"]["passed"] is True

        state = build_gate_state(
            symbol=symbol,
            signal=direction,
            outcome="independent_option_bar_evaluation",
            timestamp=option_bar.timestamp.isoformat(),
            score=75,
            reasons=[],
            scorer_inputs={},
            measurements=measured,
            support_evaluation={},
            entry_evaluation={},
            config=bot.config,
        )
        fields, _, _ = encode_gate_state_v2(
            state,
            option_bar.timestamp.isoformat(),
            None,
            first_seen=True,
            gate_names=OPTION_SIDE_GATE_NAMES,
        )
        assert len(fields["gate_state_v2"].split("|", 1)[1]) == len(
            OPTION_SIDE_GATE_NAMES
        )


def test_gate_state_assembly_exception_is_fail_open(monkeypatch):
    bot = object.__new__(KiteTradingBot)
    bot.mode = "PAPER"
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.config = {"gate_state_logging_v1": True}

    def fail_assembly(**_kwargs):
        raise RuntimeError("injected gate-state failure")

    monkeypatch.setattr(kite_main, "build_gate_state", fail_assembly)
    timestamp = "2026-11-12T09:30:00+05:30"

    state = bot._gate_state_for_decision(
        symbol="NIFTY_CE",
        signal="HOLD",
        outcome="hold",
        timestamp=timestamp,
        score=None,
        reasons=[],
        scorer_context={},
        measurements={},
        entry_evaluation=None,
    )

    assert state["gate_state_v2"] == (
        f"{timestamp}|{'N' * len(GATE_STATE_NAMES)}"
    )
    assert {
        name: gate["state"]
        for name, gate in state["gate_state_v2_full"].items()
    } == {
        name: "not_evaluated" for name in GATE_STATE_NAMES
    }
    assert bot._feature_observation_error_counts["gate_state_logging"] == 1
    assert bot._feature_observation_exception_counts[
        "feature_error:RuntimeError"
    ] == 1


def test_gate_state_serialization_exception_is_fail_open(monkeypatch):
    bot = object.__new__(KiteTradingBot)
    bot.mode = "PAPER"
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.config = {"gate_state_logging_v1": True}

    def fail_serialization(*_args, **_kwargs):
        raise RuntimeError("injected gate-state serialization failure")

    monkeypatch.setattr(kite_main.json, "dumps", fail_serialization)
    timestamp = "2026-11-12T09:30:00+05:30"

    state = bot._gate_state_for_decision(
        symbol="NIFTY_CE",
        signal="HOLD",
        outcome="hold",
        timestamp=timestamp,
        score=None,
        reasons=[],
        scorer_context={},
        measurements={},
        entry_evaluation=None,
    )

    assert state["gate_state_v2"] == (
        f"{timestamp}|{'N' * len(GATE_STATE_NAMES)}"
    )
    assert "gate_state_v2_full" in state
    assert bot._feature_observation_exception_counts[
        "feature_error:RuntimeError"
    ] == 1


def test_gate_state_logging_is_paper_only_and_kill_switch_defaults_on():
    bot = object.__new__(KiteTradingBot)
    bot.mode = "PAPER"
    bot.paper_trading_enabled = True
    bot.live_orders_enabled = False
    bot.config = {}
    assert bot._gate_state_logging_enabled()

    bot.config["gate_state_logging_v1"] = False
    assert not bot._gate_state_logging_enabled()

    bot.config["gate_state_logging_v1"] = True
    bot.mode = "LIVE"
    bot.paper_trading_enabled = False
    bot.live_orders_enabled = True
    assert not bot._gate_state_logging_enabled()
