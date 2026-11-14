from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .accuracy_filters import AccuracyFilters
from .engine import (
    _current_session_history,
    calculate_adx,
    classify_price_regime,
    score_market,
)
from .strategy import ema, rsi


def _finite_closes(history: List[Dict[str, Any]]) -> List[float]:
    closes = []
    for bar in history:
        try:
            value = float(bar["close"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(value) and value > 0:
            closes.append(value)
    return closes


def scorer_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the same current-session window used by the production scorer."""
    return _current_session_history(history)


def score_components(reasons: List[str]) -> Dict[str, int]:
    """Translate the scorer's existing reason tags into their point contributions."""
    components = {
        "ema_trend": 0,
        "macd": 0,
        "rsi": 0,
        "near_extreme": 0,
        "trend_momentum": 0,
    }
    for reason in reasons:
        if reason in {"EMA bullish", "EMA bearish"}:
            components["ema_trend"] = 25
        elif reason in {"MACD improving", "MACD weakening"}:
            components["macd"] = 18
        elif reason == "RSI in trend zone":
            components["rsi"] = 20
        elif reason == "RSI oversold":
            components["rsi"] = 15
        elif reason == "RSI overbought":
            components["rsi"] = 12
        elif reason in {"Price near recent high", "Price near recent low"}:
            components["near_extreme"] = 10
        elif reason == "Trend momentum present":
            components["trend_momentum"] = 12
    return components


def scorer_inputs(
    history: List[Dict[str, Any]], config: Dict[str, Any]
) -> Dict[str, Any]:
    history = scorer_history(history)
    closes = _finite_closes(history)
    fast_period = int(config.get("ema_fast", 9))
    slow_period = int(config.get("ema_slow", 21))
    rsi_period = int(config.get("rsi_period", 14))
    fast_values = ema(closes, fast_period)
    slow_values = ema(closes, slow_period)
    rsi_values = rsi(closes, rsi_period)
    fast = fast_values[-1] if fast_values else None
    slow = slow_values[-1] if slow_values else None
    macd = fast - slow if fast is not None and slow is not None else None
    previous_macd = (
        fast_values[-2] - slow_values[-2]
        if len(fast_values) >= 2 and len(slow_values) >= 2
        else macd
    )
    close = closes[-1] if closes else None
    recent = closes[-11:-1]
    regime_window = closes[-10:-1]
    recent_high = max(recent) if recent else None
    recent_low = min(recent) if recent else None
    regime_range_pct = (
        (max(regime_window) - min(regime_window)) / max(close, 1e-9) * 100.0
        if len(closes) >= 21 and close is not None
        else None
    )
    net_move_pct = (
        abs(close - closes[-20]) / max(closes[-20], 1e-9) * 100.0
        if len(closes) >= 21 and close is not None
        else None
    )
    proximity = float(config.get("signal_proximity_pct", 0.005))
    return {
        "ema_fast_value": fast,
        "ema_slow_value": slow,
        "rsi_value": rsi_values[-1] if rsi_values else None,
        "adx_value": calculate_adx(history),
        "macd_value": macd,
        "macd_previous_value": previous_macd,
        "regime_label": classify_price_regime(
            closes,
            sideways_range_pct=float(config.get("sideways_range_pct", 1.0)),
            sideways_net_move_pct=float(
                config.get("sideways_net_move_pct", 1.0)
            ),
        ),
        "regime_range_pct": regime_range_pct,
        "regime_20_bar_move_pct": net_move_pct,
        "near_recent_high": (
            close >= recent_high * (1.0 - proximity)
            if close is not None and recent_high is not None
            else None
        ),
        "near_recent_low": (
            close <= recent_low * (1.0 + proximity)
            if close is not None and recent_low is not None
            else None
        ),
        "recent_high": recent_high,
        "recent_low": recent_low,
        "pivot_levels": [],
    }


def score_observation(
    ticker: str,
    history: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute read-only scorer telemetry without changing TradingScore."""
    inputs = scorer_inputs(history, config)
    score = score_market(
        ticker,
        history,
        ema_fast=int(config.get("ema_fast", 9)),
        ema_slow=int(config.get("ema_slow", 21)),
        rsi_period=int(config.get("rsi_period", 14)),
        hard_context_filter=bool(config.get("hard_context_filter", True)),
        min_adx=float(config.get("min_adx", 18.0)),
        sideways_range_pct=float(config.get("sideways_range_pct", 1.0)),
        sideways_net_move_pct=float(config.get("sideways_net_move_pct", 1.0)),
        min_trend_strength=float(config.get("min_trend_strength", 0.02)),
        trend_momentum_bonus_threshold=(
            float(config["trend_momentum_bonus_threshold"])
            if config.get("trend_momentum_bonus_threshold") is not None
            else None
        ),
        signal_proximity_pct=float(config.get("signal_proximity_pct", 0.005)),
        allow_trend_continuation=bool(
            config.get("allow_trend_continuation", False)
        ),
        rsi_buy_block_above=float(config.get("rsi_buy_block_above", 80.0)),
        rsi_sell_block_below=float(config.get("rsi_sell_block_below", 25.0)),
    )
    components = score_components(score.reasons)
    return {
        **inputs,
        "score_components": components,
        "component_score": sum(components.values()),
        "score": score.score,
        "signal": score.signal,
        "reasons": list(score.reasons),
    }


def add_score_adjustment(
    components: Dict[str, int], name: str, adjustment: int
) -> Dict[str, int]:
    """Include a non-engine strategy adjustment in the observational breakdown."""
    updated = dict(components)
    updated[name] = int(adjustment)
    return updated


GATE_STATE_NAMES = (
    "entry_window",
    "bar_warmup",
    "indicator_availability",
    "trend_setup",
    "breakout_quality",
    "regime_breakout",
    "ema",
    "adx",
    "rsi",
    "macd",
    "score_threshold",
    "benchmark_context",
    "news_filter",
    "pivot_touches",
    "support_reversal_detector",
    "support_reversal_eligibility",
    "ema_stop_reentry",
    "option_candle_momentum_direction",
    "option_candle_momentum_body",
    "option_leg",
    "option_contract",
    "option_expiry",
    "option_market_quality",
    "volatility_band",
    "premium_range",
    "quote_freshness",
    "accuracy_confirmation",
    "cooldown",
    "pending_entry_lock",
    "confirmation_window",
    "manual_entry_pause",
    "stop_reentry",
    "option_range_breakout",
    "position_size",
    "lot_size",
    "risk_cap",
    "capital_cap",
    "session_trade_lock",
    "daily_loss",
    "consecutive_loss",
    "open_risk_limit",
    "symbol_win_rate",
    "confirmation",
    "order",
)

SYMBOL_STATE_GATE_NAMES = (
    "session_trade_lock",
    "cooldown",
    "daily_loss",
    "consecutive_loss",
    "open_risk_limit",
    "symbol_win_rate",
)
OPTION_SIDE_GATE_NAMES = (
    "option_candle_momentum_direction",
    "option_candle_momentum_body",
    "option_leg",
    "option_contract",
    "option_expiry",
    "option_market_quality",
    "premium_range",
    "quote_freshness",
    "stop_reentry",
    "ema_stop_reentry",
    "option_range_breakout",
    "position_size",
    "lot_size",
    "risk_cap",
    "capital_cap",
)
DIRECTIONAL_GATE_STATE_NAMES = tuple(
    name for name in GATE_STATE_NAMES if name not in SYMBOL_STATE_GATE_NAMES
)

GATE_STATE_CODES = {
    "pass": "P",
    "fail": "F",
    "not_evaluated": "N",
}
GATE_STATE_LABELS = {code: state for state, code in GATE_STATE_CODES.items()}

_GATE_MISSING_REASON_CODES = {
    "entry_window": "entry_window_not_checked",
    "bar_warmup": "bar_count_unavailable",
    "indicator_availability": "required_indicators_unavailable",
    "trend_setup": "no_candidate_signal",
    "breakout_quality": "no_candidate_signal",
    "regime_breakout": "regime_unavailable",
    "ema": "ema_unavailable",
    "adx": "adx_unavailable",
    "rsi": "rsi_unavailable",
    "macd": "macd_unavailable",
    "score_threshold": "score_unavailable",
    "benchmark_context": "benchmark_context_unavailable",
    "news_filter": "news_context_unavailable",
    "pivot_touches": "pivot_data_unavailable",
    "support_reversal_detector": "support_reversal_not_evaluated",
    "support_reversal_eligibility": "support_reversal_not_applicable",
    "ema_stop_reentry": "ema_reentry_not_applicable",
    "option_candle_momentum_direction": "no_option_candle",
    "option_candle_momentum_body": "no_option_candle",
    "option_leg": "no_option_leg",
    "option_contract": "option_contract_unavailable",
    "option_expiry": "option_expiry_unavailable",
    "option_market_quality": "no_quote",
    "volatility_band": "volatility_unavailable",
    "premium_range": "no_quote",
    "quote_freshness": "no_quote",
    "accuracy_confirmation": "confirmation_bars_unavailable",
    "cooldown": "cooldown_state_unavailable",
    "pending_entry_lock": "pending_entry_state_unavailable",
    "confirmation_window": "confirmation_not_pending",
    "manual_entry_pause": "entry_pause_state_unavailable",
    "stop_reentry": "stop_reentry_state_unavailable",
    "option_range_breakout": "range_breakout_not_applicable",
    "position_size": "position_size_unavailable",
    "lot_size": "lot_size_unavailable",
    "risk_cap": "risk_inputs_unavailable",
    "capital_cap": "capital_inputs_unavailable",
    "session_trade_lock": "session_trade_state_unavailable",
    "daily_loss": "daily_loss_state_unavailable",
    "consecutive_loss": "loss_streak_state_unavailable",
    "open_risk_limit": "open_risk_state_unavailable",
    "symbol_win_rate": "symbol_performance_unavailable",
    "confirmation": "confirmation_not_evaluated",
    "order": "paper_order_not_attempted",
}


def empty_gate_state(timestamp: Optional[str]) -> Dict[str, Dict[str, Any]]:
    return {
        name: {
            "state": "not_evaluated",
            "observed_value": None,
            "threshold": None,
            "evaluation_timestamp": timestamp,
            "reason_code": _GATE_MISSING_REASON_CODES[name],
        }
        for name in GATE_STATE_NAMES
    }


def encode_gate_state_v2(
    gate_state: Dict[str, Dict[str, Any]],
    timestamp: Optional[str],
    previous_states: Optional[Dict[str, str]],
    *,
    first_seen: bool,
    previous_reason_codes: Optional[Dict[str, str]] = None,
    gate_names: tuple[str, ...] = GATE_STATE_NAMES,
) -> tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
    """Encode fixed-order gate states and sparse value/threshold details."""
    current_states: Dict[str, str] = {}
    current_reason_codes: Dict[str, str] = {}
    ordered_gates = {}
    for name in gate_names:
        gate = gate_state.get(name, {})
        gate = gate if isinstance(gate, dict) else {}
        state = gate.get("state", "not_evaluated")
        code = GATE_STATE_CODES.get(state, "N")
        current_states[name] = code
        current_reason_codes[name] = str(
            gate.get("reason_code") or _GATE_MISSING_REASON_CODES[name]
        )
        ordered_gates[name] = {
            "state": GATE_STATE_LABELS[code],
            "observed_value": gate.get("observed_value"),
            "threshold": gate.get("threshold"),
            "reason_code": current_reason_codes[name],
        }

    fields: Dict[str, Any] = {
        "gate_state_v2": (
            f"{timestamp or ''}|"
            + "".join(current_states[name] for name in gate_names)
        )
    }
    if first_seen:
        fields["gate_state_v2_full"] = ordered_gates
    else:
        changed = {
            name: {
                "observed_value": ordered_gates[name]["observed_value"],
                "threshold": ordered_gates[name]["threshold"],
            }
            for name in gate_names
            if previous_states is None
            or previous_states.get(name) != current_states[name]
            or (
                previous_reason_codes is not None
                and previous_reason_codes.get(name) != current_reason_codes[name]
            )
        }
        if changed:
            fields["gate_state_v2_changes"] = {
                name: (
                    {
                        "observed_value": ordered_gates[name]["observed_value"],
                        "threshold": ordered_gates[name]["threshold"],
                        "reason_code": current_reason_codes[name],
                    }
                    if previous_states is None
                    or previous_states.get(name) != current_states[name]
                    else {"reason_code": current_reason_codes[name]}
                )
                for name in changed
            }
    return fields, current_states, current_reason_codes


def build_gate_state(
    *,
    symbol: str,
    signal: str,
    outcome: str,
    timestamp: Optional[str],
    score: Optional[int],
    reasons: List[str],
    scorer_inputs: Dict[str, Any],
    measurements: Dict[str, Any],
    support_evaluation: Dict[str, Any],
    entry_evaluation: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Build read-only, per-evaluation status for the existing entry gates."""
    result = empty_gate_state(timestamp)
    scorer_inputs = scorer_inputs if isinstance(scorer_inputs, dict) else {}
    measurements = measurements if isinstance(measurements, dict) else {}
    support_evaluation = (
        support_evaluation if isinstance(support_evaluation, dict) else {}
    )
    entry_evaluation = (
        entry_evaluation if isinstance(entry_evaluation, dict) else {}
    )
    config = config if isinstance(config, dict) else {}
    reasons = reasons if isinstance(reasons, list) else []
    reason_text = " ".join(str(reason) for reason in reasons).lower()
    normalized_signal = str(signal or "").upper()
    normalized_outcome = str(outcome or "").lower()
    candidate = normalized_signal in {"BUY", "SELL"}

    def set_gate(
        name: str,
        passed: Optional[bool],
        observed: Any,
        threshold: Any,
        *,
        evaluated: bool = True,
        reason_code: Optional[str] = None,
    ) -> None:
        if not evaluated or passed is None:
            if reason_code:
                result[name]["reason_code"] = reason_code
            return
        result[name] = {
            "state": "pass" if passed else "fail",
            "observed_value": observed,
            "threshold": threshold,
            "evaluation_timestamp": timestamp,
            "reason_code": reason_code or "evaluated",
        }

    regime = scorer_inputs.get("regime_label")
    breakout_outcome = normalized_outcome.startswith("paper_range_breakout")
    regime_blocked = any(
        marker in reason_text for marker in ("sideways regime", "extended move")
    )
    if breakout_outcome:
        set_gate(
            "regime_breakout",
            normalized_outcome == "paper_range_breakout_trade_opened",
            {"regime": regime, "outcome": outcome},
            {
                "sideways_range_pct": config.get("sideways_range_pct"),
                "sideways_net_move_pct": config.get("sideways_net_move_pct"),
                "lookback_bars": config.get("option_range_lookback_bars"),
                "confirmation_bars": config.get("option_range_confirmation_bars"),
            },
        )
    elif regime is not None:
        set_gate(
            "regime_breakout",
            not regime_blocked and str(regime).upper() not in {"SIDEWAYS", "EXTENDED"},
            {"regime": regime, "blocked_by_reason": regime_blocked},
            {
                "sideways_range_pct": config.get("sideways_range_pct"),
                "sideways_net_move_pct": config.get("sideways_net_move_pct"),
            },
        )

    fast = scorer_inputs.get("ema_fast_value")
    slow = scorer_inputs.get("ema_slow_value")
    if candidate and fast is not None and slow is not None:
        aligned = fast > slow if normalized_signal == "BUY" else fast < slow
        set_gate(
            "ema",
            aligned,
            {"fast": fast, "slow": slow, "direction": normalized_signal},
            "fast > slow for BUY; fast < slow for SELL",
        )

    adx = scorer_inputs.get("adx_value", measurements.get("adx"))
    adx_threshold = measurements.get(
        "adx_threshold", config.get("min_adx", 18.0)
    )
    if adx is not None and score is not None:
        set_gate(
            "adx",
            float(adx) >= float(adx_threshold),
            adx,
            adx_threshold,
        )

    rsi_value = scorer_inputs.get("rsi_value")
    rsi_direction = normalized_signal
    if not candidate:
        if "rsi overbought against buy" in reason_text:
            rsi_direction = "BUY"
        elif "rsi oversold against sell" in reason_text:
            rsi_direction = "SELL"
        else:
            rsi_direction = ""
    rsi_threshold = (
        config.get("rsi_buy_block_above", 80.0)
        if rsi_direction == "BUY"
        else config.get("rsi_sell_block_below", 25.0)
    )
    if rsi_direction and rsi_value is not None:
        set_gate(
            "rsi",
            (
                float(rsi_value) <= float(rsi_threshold)
                if rsi_direction == "BUY"
                else float(rsi_value) >= float(rsi_threshold)
            ),
            {"value": rsi_value, "direction": rsi_direction},
            {"block_above_buy": config.get("rsi_buy_block_above", 80.0),
             "block_below_sell": config.get("rsi_sell_block_below", 25.0)},
        )

    macd = scorer_inputs.get("macd_value")
    previous_macd = scorer_inputs.get("macd_previous_value")
    if candidate and macd is not None and previous_macd is not None:
        macd_passed = (
            float(macd) >= 0 and float(macd) >= float(previous_macd) - 1e-9
            if normalized_signal == "BUY"
            else float(macd) <= 0 and float(macd) <= float(previous_macd) + 1e-9
        )
        set_gate(
            "macd",
            macd_passed,
            {"value": macd, "previous_value": previous_macd,
             "direction": normalized_signal},
            "nonnegative and nondecreasing for BUY; nonpositive and nonincreasing for SELL",
        )

    score_threshold = measurements.get(
        "score_threshold", config.get("min_entry_score", 70)
    )
    score_gate_evaluated = candidate or (
        score is not None
        and score_threshold is not None
        and float(score) < float(score_threshold)
    ) or "score" in reason_text
    if score_gate_evaluated and score is not None and score_threshold is not None:
        set_gate(
            "score_threshold",
            float(score) >= float(score_threshold),
            score,
            score_threshold,
        )

    pivot_levels = scorer_inputs.get("pivot_levels") or []
    pivot_touches = support_evaluation.get("touches")
    if pivot_touches is None and pivot_levels:
        pivot_touches = max(
            (
                level.get("touches")
                for level in pivot_levels
                if isinstance(level, dict) and level.get("touches") is not None
            ),
            default=None,
        )
    if pivot_touches is not None:
        set_gate(
            "pivot_touches",
            int(pivot_touches) >= 2,
            pivot_touches,
            config.get("support_reversal_min_touches", 2),
        )
    support_was_evaluated = bool(support_evaluation.get("evaluated"))
    if support_was_evaluated:
        detected = bool(support_evaluation.get("candidate"))
        set_gate(
            "support_reversal_detector",
            detected,
            {
                "detected": detected,
                "signal": support_evaluation.get("signal"),
                "level": support_evaluation.get("level"),
                "touches": support_evaluation.get("touches"),
                "levels": support_evaluation.get("levels", []),
                "thresholds": support_evaluation.get("thresholds", {}),
            },
            "support/reversal candidate detected",
        )
        if pivot_touches is None and detected:
            pivot_touches = support_evaluation.get("touches")
        if pivot_touches is not None:
            set_gate(
                "pivot_touches",
                int(pivot_touches) >= 2,
                pivot_touches,
                config.get("support_reversal_min_touches", 2),
            )
    elif support_evaluation.get("reason_code"):
        result["support_reversal_detector"]["reason_code"] = str(
            support_evaluation["reason_code"]
        )

    body_applies = (
        symbol.endswith(("_CE", "_PE"))
        and measurements.get("body_ratio_gate_applies") is True
    )
    direction_matches = measurements.get("body_ratio_direction_matches")
    if body_applies and direction_matches is not None:
        set_gate(
            "option_candle_momentum_direction",
            bool(direction_matches),
            direction_matches,
            True,
        )
    body_ratio = measurements.get("body_ratio")
    body_threshold = measurements.get("body_ratio_threshold")
    if body_applies and body_ratio is not None and body_threshold is not None:
        set_gate(
            "option_candle_momentum_body",
            float(body_ratio) >= float(body_threshold),
            body_ratio,
            body_threshold,
        )

    volatility = measurements.get("volatility_pct")
    volatility_min = measurements.get(
        "volatility_min_pct", config.get("min_volatility_pct", 0.05)
    )
    volatility_max = measurements.get(
        "volatility_max_pct", config.get("max_volatility_pct", 5.0)
    )
    volatility_passed = measurements.get("volatility_passed")
    if candidate and isinstance(volatility_passed, bool):
        set_gate(
            "volatility_band",
            volatility_passed,
            measurements.get("volatility_observed", volatility),
            {"minimum_pct": volatility_min, "maximum_pct": volatility_max},
        )
    elif candidate and volatility is not None:
        volatility_rejected = "accuracy_filter_rejected:volatility" in normalized_outcome
        set_gate(
            "volatility_band",
            (
                False
                if volatility_rejected
                else float(volatility_min) <= float(volatility) <= float(volatility_max)
            ),
            volatility,
            {"minimum_pct": volatility_min, "maximum_pct": volatility_max},
        )

    change_gates = measurements.get("paper_change_gate_evaluations")
    change_gates = change_gates if isinstance(change_gates, dict) else {}
    premium_eval = change_gates.get("premium_floor_v2")
    premium_eval = premium_eval if isinstance(premium_eval, dict) else {}
    banknifty_eval = change_gates.get("banknifty_caps_v2")
    banknifty_eval = banknifty_eval if isinstance(banknifty_eval, dict) else {}
    premium = premium_eval.get(
        "premium", measurements.get("ltp", measurements.get("signal_premium"))
    )
    premium_floor = premium_eval.get(
        "floor", config.get("option_min_premium", 12.0)
    )
    premium_cap = (
        banknifty_eval.get("premium_cap")
        if banknifty_eval.get("applies")
        else config.get("option_max_premium", 800.0)
    )
    if (
        symbol.endswith(("_CE", "_PE"))
        and premium is not None
        and premium_floor is not None
        and premium_cap is not None
    ):
        premium_passed = float(premium) >= float(premium_floor) and float(
            premium
        ) <= float(premium_cap)
        if premium_eval.get("applies") and premium_eval.get("passed") is False:
            premium_passed = False
        set_gate(
            "premium_range",
            premium_passed,
            premium,
            {"minimum": premium_floor, "maximum": premium_cap},
        )
    elif not symbol.endswith(("_CE", "_PE")):
        for name in ("option_leg", "option_contract", "option_expiry",
                     "option_market_quality", "premium_range",
                     "quote_freshness", "option_candle_momentum_direction",
                     "option_candle_momentum_body", "risk_cap", "capital_cap",
                     "position_size", "lot_size"):
            result[name]["reason_code"] = "not_option_contract"
    elif premium is None:
        result["premium_range"]["reason_code"] = str(
            measurements.get("premium_missing_reason", "no_quote_and_no_candle")
        )

    quote_age = measurements.get("quote_age_seconds")
    quote_age_threshold = measurements.get(
        "quote_age_threshold_seconds",
        config.get("option_quote_max_age_seconds", 60),
    )
    if (
        symbol.endswith(("_CE", "_PE"))
        and quote_age is not None
        and quote_age_threshold is not None
    ):
        set_gate(
            "quote_freshness",
            float(quote_age) <= float(quote_age_threshold),
            quote_age,
            quote_age_threshold,
        )
    elif symbol.endswith(("_CE", "_PE")):
        result["quote_freshness"]["reason_code"] = str(
            measurements.get("quote_missing_reason", "no_quote")
        )
    if symbol.endswith(("_CE", "_PE")) and body_applies:
        if direction_matches is None:
            result["option_candle_momentum_direction"]["reason_code"] = str(
                measurements.get("option_candle_missing_reason", "no_candle")
            )
        if body_ratio is None or body_threshold is None:
            result["option_candle_momentum_body"]["reason_code"] = str(
                measurements.get("option_candle_missing_reason", "no_candle")
            )

    risk_amount = next(
        (
            entry_evaluation.get(key)
            for key in (
                "risk_amount", "risk_inr", "option_risk_per_lot_rupees",
                "proposed_risk_amount",
            )
            if entry_evaluation.get(key) is not None
        ),
        None,
    )
    risk_cap = next(
        (
            entry_evaluation.get(key)
            for key in ("risk_cap_rupees", "risk_cap_inr", "hard_risk_cap_inr")
            if entry_evaluation.get(key) is not None
        ),
        banknifty_eval.get("risk_cap_inr"),
    )
    rejection = str(entry_evaluation.get("rejection_reason") or normalized_outcome)
    risk_rejected = any(
        marker in rejection.lower()
        for marker in (
            "risk",
            "one_lot_exceeds",
            "loss_cap",
        )
    )
    if risk_amount is not None and risk_cap is not None:
        set_gate(
            "risk_cap",
            float(risk_amount) <= float(risk_cap),
            risk_amount,
            risk_cap,
        )
    elif entry_evaluation.get("accepted") is True:
        set_gate("risk_cap", True, risk_amount, risk_cap)
    elif risk_rejected:
        set_gate("risk_cap", False, risk_amount, risk_cap)

    invested = next(
        (
            entry_evaluation.get(key)
            for key in (
                "proposed_invested_amount", "invested_amount",
                "max_capital_per_trade_used_amount",
            )
            if entry_evaluation.get(key) is not None
        ),
        None,
    )
    capital_cap = next(
        (
            entry_evaluation.get(key)
            for key in (
                "max_capital_per_trade_used_amount",
                "banknifty_max_capital_per_trade_amount",
                "max_capital_per_trade_amount",
            )
            if entry_evaluation.get(key) is not None
        ),
        None,
    )
    capital_rejected = any(
        marker in rejection.lower()
        for marker in ("capital_cap", "capital limit", "invested amount")
    )
    if invested is not None and capital_cap is not None:
        set_gate(
            "capital_cap",
            float(invested) <= float(capital_cap),
            invested,
            capital_cap,
        )
    elif entry_evaluation.get("accepted") is True:
        set_gate("capital_cap", True, invested, capital_cap)
    elif capital_rejected:
        set_gate("capital_cap", False, invested, capital_cap)

    confirmation = (
        entry_evaluation.get("confirmation_result")
        or measurements.get("confirmation_result")
    )
    if confirmation in {"passed", "failed"}:
        set_gate(
            "confirmation",
            confirmation == "passed",
            confirmation,
            "passed",
        )
    elif "rejected_by_confirmation" in normalized_outcome:
        set_gate("confirmation", False, "rejected", "passed")

    if normalized_outcome in {
        "trade_opened",
        "paper_range_breakout_trade_opened",
    } or measurements.get("order_time"):
        set_gate(
            "order",
            True,
            measurements.get("order_time") or outcome,
            "order accepted",
        )
    elif any(
        marker in normalized_outcome
        for marker in ("execution_failed", "live_order_failed", "order_failed")
    ):
        set_gate("order", False, outcome, "order accepted")

    gate_reasons = measurements.get("gate_reasons")
    if isinstance(gate_reasons, dict):
        for name, reason_code in gate_reasons.items():
            if name in result and result[name]["state"] == "not_evaluated":
                result[name]["reason_code"] = str(reason_code)

    blocker_results = measurements.get("blocker_results")
    if isinstance(blocker_results, dict):
        for name, evaluation in blocker_results.items():
            if name not in result or not isinstance(evaluation, dict):
                continue
            passed = evaluation.get("passed")
            set_gate(
                name,
                passed if isinstance(passed, bool) else None,
                evaluation.get("observed_value"),
                evaluation.get("threshold"),
                reason_code=evaluation.get("reason_code"),
            )

    bar_count = measurements.get("bar_count")
    if bar_count is not None:
        minimum_bars = measurements.get("warmup_min_bars", 30)
        set_gate(
            "bar_warmup",
            int(bar_count) >= int(minimum_bars),
            bar_count,
            minimum_bars,
        )
    indicator_availability = measurements.get("indicator_availability")
    if isinstance(indicator_availability, dict):
        required = indicator_availability.get("required", [])
        available = indicator_availability.get("available", [])
        set_gate(
            "indicator_availability",
            len(required) > 0 and len(required) == len(available),
            available,
            required,
            reason_code=(
                "evaluated"
                if len(required) == len(available)
                else "missing_required_indicators"
            ),
        )

    if normalized_signal not in {"BUY", "SELL"}:
        for name in (
            "trend_setup",
            "breakout_quality",
            "accuracy_confirmation",
            "pending_entry_lock",
        ):
            if result[name]["state"] == "not_evaluated":
                result[name]["reason_code"] = "no_candidate_signal"

    return result


def build_independent_bar_gate_state(
    *,
    symbol: str,
    direction: str,
    timestamp: Optional[str],
    score: Optional[int],
    reasons: List[str],
    scorer_inputs: Dict[str, Any],
    history: List[Dict[str, Any]],
    support_evaluation: Dict[str, Any],
    config: Dict[str, Any],
    extra_measurements: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Evaluate gates derivable from a completed underlying bar without entry flow."""
    measurements: Dict[str, Any] = {
        "score_threshold": max(
            0, min(int(config.get("min_entry_score", 70)), 85)
        )
    }
    if isinstance(extra_measurements, dict):
        measurements.update(extra_measurements)
    if history:
        volatility_min = max(float(config.get("min_volatility_pct", 0.05)), 0.0)
        volatility_max = max(
            float(config.get("max_volatility_pct", 5.0)), volatility_min
        )
        measurements["volatility_min_pct"] = volatility_min
        measurements["volatility_max_pct"] = volatility_max
        if len(history) < 14:
            measurements["volatility_passed"] = True
            measurements["volatility_observed"] = {
                "reason": "insufficient_history",
                "bars": len(history),
            }
        else:
            atr = AccuracyFilters.calculate_atr(history, period=14)
            close = float(history[-1].get("close", 1))
            if close == 0:
                volatility_pct = None
                volatility_passed = False
            else:
                volatility_pct = atr / close * 100.0
                volatility_passed = (
                    volatility_min <= volatility_pct <= volatility_max
                )
            measurements["volatility_pct"] = volatility_pct
            measurements["volatility_passed"] = volatility_passed
            measurements["volatility_observed"] = volatility_pct

    if len(history) >= 2:
        confirmation_passed = AccuracyFilters.has_confirmation(
            direction, history[-1], history[-2]
        )
        measurements["confirmation_result"] = (
            "passed" if confirmation_passed else "failed"
        )
        measurements["accuracy_confirmation_passed"] = confirmation_passed
        measurements["accuracy_confirmation_observed"] = {
            "current_close": history[-1].get("close"),
            "previous_close": history[-2].get("close"),
            "direction": direction,
        }
    else:
        measurements.setdefault("gate_reasons", {})[
            "accuracy_confirmation"
        ] = "confirmation_bars_unavailable"
    measurements["bar_count"] = len(history)

    return build_gate_state(
        symbol=symbol,
        signal=direction,
        outcome="independent_bar_evaluation",
        timestamp=timestamp,
        score=score,
        reasons=reasons,
        scorer_inputs=scorer_inputs,
        measurements=measurements,
        support_evaluation=support_evaluation,
        entry_evaluation={},
        config=config,
    )


def first_passed_gate_times(
    *,
    signal: str,
    timestamp: Optional[str],
    outcome: str,
    reasons: List[str],
    score: Optional[int],
    measurements: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Optional[str]]:
    """Return timestamps only for gates observed to pass for this candidate."""
    result: Dict[str, Optional[str]] = {
        "regime": None,
        "ema_adx_rsi": None,
        "option_momentum": None,
        "score": None,
        "confirmation": None,
        "order": None,
    }
    if not timestamp or signal not in {"BUY", "SELL"}:
        return result
    reason_text = " ".join(reasons).lower()
    regime_passed = not any(
        marker in reason_text
        for marker in ("sideways regime", "extended move")
    )
    indicators = measurements.get("scorer_inputs", {})
    fast = indicators.get("ema_fast_value")
    slow = indicators.get("ema_slow_value")
    adx = indicators.get("adx_value")
    rsi_value = indicators.get("rsi_value")
    ema_aligned = (
        fast is not None
        and slow is not None
        and (fast > slow if signal == "BUY" else fast < slow)
    )
    adx_passed = adx is None or adx >= float(config.get("min_adx", 18.0))
    rsi_passed = (
        rsi_value is None
        or (
            rsi_value <= float(config.get("rsi_buy_block_above", 80.0))
            if signal == "BUY"
            else rsi_value >= float(config.get("rsi_sell_block_below", 25.0))
        )
    )
    if regime_passed:
        result["regime"] = timestamp
    if ema_aligned and adx_passed and rsi_passed:
        result["ema_adx_rsi"] = timestamp
    if measurements.get("body_ratio_gate_applies"):
        if measurements.get("body_ratio_passed") is True:
            result["option_momentum"] = timestamp
    elif measurements.get("direction_rule"):
        result["option_momentum"] = timestamp
    threshold = measurements.get("score_threshold")
    if score is not None and threshold is not None and score >= threshold:
        result["score"] = timestamp
    if measurements.get("confirmation_result") == "passed":
        result["confirmation"] = measurements.get(
            "confirmation_candle_time", timestamp
        )
    normalized_outcome = str(outcome).lower()
    if "trade_opened" in normalized_outcome or normalized_outcome == "confirmed_trade":
        result["order"] = measurements.get("order_time", timestamp)
    return result
