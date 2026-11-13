from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

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
    "regime_breakout",
    "ema",
    "adx",
    "rsi",
    "macd",
    "score_threshold",
    "pivot_touches",
    "support_reversal_detector",
    "option_candle_momentum_direction",
    "option_candle_momentum_body",
    "volatility_band",
    "premium_range",
    "quote_freshness",
    "risk_cap",
    "capital_cap",
    "confirmation",
    "order",
)


def empty_gate_state(timestamp: Optional[str]) -> Dict[str, Dict[str, Any]]:
    return {
        name: {
            "state": "not_evaluated",
            "observed_value": None,
            "threshold": None,
            "evaluation_timestamp": timestamp,
        }
        for name in GATE_STATE_NAMES
    }


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
    ) -> None:
        if not evaluated or passed is None:
            return
        result[name] = {
            "state": "pass" if passed else "fail",
            "observed_value": observed,
            "threshold": threshold,
            "evaluation_timestamp": timestamp,
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
    if candidate and volatility is not None:
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

    return result


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
