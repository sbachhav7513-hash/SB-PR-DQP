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
