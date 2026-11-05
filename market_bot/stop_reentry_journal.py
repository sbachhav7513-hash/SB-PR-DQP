from __future__ import annotations

import json
import logging
import math
import queue
import threading
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from .option_capture import load_option_capture
from .reporting_metrics import ReportingStep

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
REENTRY_WINDOW_SECONDS = 90 * 60
PRICE_PATH_CHECKPOINTS = (15, 30, 60)

STOP_EVENT_COLUMNS = (
    "record_type",
    "stop_event_id",
    "original_trade_id",
    "contract_id",
    "underlying",
    "leg",
    "stop_time",
    "entry_price",
    "stop_price",
    "exit_price",
    "exit_reason",
    "net_pnl",
    "config_hash",
    "checkpoint_minutes",
    "highest_price_since_stop",
    "lowest_price_since_stop",
    "pre_stop_5m_high",
    "closed_above_entry",
    "first_close_above_entry_time",
    "closed_above_pre_stop_5m_high",
    "first_close_above_pre_stop_5m_high_time",
    "closed_above_both",
    "first_close_above_both_time",
    "candles_missing",
    "reentry_opened",
    "reentry_trade_id",
)
REENTRY_CHECK_COLUMNS = (
    "timestamp",
    "stop_event_id",
    "original_trade_id",
    "contract_id",
    "underlying",
    "leg",
    "decision_bar_time",
    "signal",
    "signal_direction",
    "reentry_route",
    "score",
    "decision_outcome",
    "conditions",
    "first_failed_condition",
    "n_failed_conditions",
    "reentry_opened",
    "config_hash",
)
FAILURE_BUCKETS = (
    "cooldown",
    "score",
    "no EMA cross",
    "premium-low cancel",
    "lock",
    "risk guard",
    "option filter",
    "accuracy filter",
    "other",
)


def _as_ist(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def _number(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _condition(result: str, value: Any = None, threshold: Any = None) -> dict:
    return {"result": result, "value": value, "threshold": threshold}


def _ema_reentry_context(history: list[dict], leg: str, stop_time: datetime) -> dict:
    rows = []
    for candle in history:
        timestamp = _as_ist(candle.get("time", candle.get("timestamp")))
        close = _number(candle.get("close"))
        high = _number(candle.get("high"))
        low = _number(candle.get("low"))
        if timestamp is not None and close is not None and high is not None and low is not None:
            rows.append((timestamp, close, high, low))
    if len(rows) < 21:
        return {"cross": False, "cross_candle_time": None, "confirmation": None}

    closes = [row[1] for row in rows]

    def ema(period: int) -> list[Optional[float]]:
        values: list[Optional[float]] = [None] * len(closes)
        if len(closes) >= period:
            previous = sum(closes[:period]) / period
            values[period - 1] = previous
            multiplier = 2.0 / (period + 1)
            for index in range(period, len(closes)):
                previous += multiplier * (closes[index] - previous)
                values[index] = previous
        return values

    fast = ema(5)
    slow = ema(20)
    bullish = leg == "CE"
    for index in range(20, len(rows)):
        candle_time = rows[index][0] + timedelta(minutes=1)
        if candle_time <= stop_time:
            continue
        prior_fast, prior_slow = fast[index - 1], slow[index - 1]
        current_fast, current_slow = fast[index], slow[index]
        if None in (prior_fast, prior_slow, current_fast, current_slow):
            continue
        crossed = (
            prior_fast <= prior_slow and current_fast > current_slow
            if bullish
            else prior_fast >= prior_slow and current_fast < current_slow
        )
        if not crossed:
            continue
        level = rows[index][2] if bullish else rows[index][3]
        confirmation = None
        for later in range(index + 1, len(rows)):
            close = rows[later][1]
            trend_valid = (
                fast[later] is not None
                and slow[later] is not None
                and (
                    fast[later] > slow[later]
                    if bullish
                    else fast[later] < slow[later]
                )
            )
            crossed_level = close > level if bullish else close < level
            if trend_valid and crossed_level:
                confirmation = {
                    "close": close,
                    "candle_high_or_low": level,
                    "time": (rows[later][0] + timedelta(minutes=1)).isoformat(),
                }
                break
        return {
            "cross": True,
            "cross_candle_time": candle_time.isoformat(),
            "confirmation": confirmation,
        }
    return {"cross": False, "cross_candle_time": None, "confirmation": None}


def _failure_category(outcome: str, conditions: dict) -> Optional[str]:
    lowered = outcome.lower()
    if outcome == "trade_opened":
        return None
    if any(token in lowered for token in ("cooldown", "remaining")):
        return "cooldown"
    if "score 75" in lowered or "score" in lowered and "minimum" in lowered:
        return "score"
    if "premium_new_low" in lowered or "cancelled_new_low" in lowered:
        return "premium-low cancel"
    if any(token in lowered for token in ("already traded", "already reversed", "reversal lock", "one stop-loss")):
        return "lock"
    if any(token in lowered for token in ("risk", "budget", "loss cap", "consecutive loss", "capital cap")):
        return "risk guard"
    if "option_filter" in lowered or "option filter" in lowered or "quote stale" in lowered:
        return "option filter"
    if any(token in lowered for token in ("accuracy_filter", "volatility", "adx", "trading hours", "entry_cutoff", "late_window")):
        return "accuracy filter"
    if conditions.get("premium_low_cancel", {}).get("result") == "fail":
        return "premium-low cancel"
    if conditions.get("one_per_symbol_lock", {}).get("result") == "fail" or conditions.get(
        "reversal_lock", {}
    ).get("result") == "fail":
        return "lock"
    if (
        conditions.get("signal_present", {}).get("result") == "pass"
        and conditions.get("cooldown", {}).get("result") == "fail"
    ):
        return "cooldown"
    if (
        conditions.get("signal_present", {}).get("result") == "pass"
        and conditions.get("stop_reentry_score", {}).get("result") == "fail"
    ):
        return "score"
    if any(
        conditions.get(name, {}).get("result") == "fail"
        for name in (
            "daily_loss_guard",
            "consecutive_losses_guard",
            "open_risk_guard",
            "capital_cap_guard",
            "aggregate_budget_guard",
            "recent_loss_cooldown",
            "win_rate_cap",
        )
    ):
        return "risk guard"
    if any(
        conditions.get(name, {}).get("result") == "fail"
        for name in (
            "quote_freshness",
            "premium_range",
            "body_ratio",
            "volume",
            "open_interest",
            "implied_volatility",
        )
    ):
        return "option filter"
    if any(
        conditions.get(name, {}).get("result") == "fail"
        for name in ("volatility", "adx", "trading_hours", "entry_cutoff")
    ):
        return "accuracy filter"
    if conditions.get("ema_cross", {}).get("result") == "fail":
        return "no EMA cross"
    return "other"


def _build_reentry_check(
    event: dict, snapshot: dict, config_hash: str
) -> dict:
    now = _as_ist(snapshot.get("timestamp"))
    stop_time = _as_ist(event.get("stop_time"))
    if now is None or stop_time is None:
        raise ValueError("Re-entry check requires valid IST timestamps")
    leg = str(event.get("leg") or "")
    config = snapshot.get("config") or {}
    manager = snapshot.get("manager") or {}
    gates = snapshot.get("gate_measurements") or {}
    entry_evaluation = snapshot.get("entry_evaluation") or {}
    quote = snapshot.get("quote") or {}
    signal = str(snapshot.get("signal") or "HOLD").upper()
    expected_signal = "BUY" if leg == "CE" else "SELL" if leg == "PE" else None
    score = _number(snapshot.get("score"))
    ordinary_floor = _number(config.get("min_entry_score", 70))
    if ordinary_floor is None:
        ordinary_floor = 70
    stop_floor = _number(config.get("stop_reentry_min_score", 75))
    if stop_floor is None:
        stop_floor = 75
    elapsed = max((now - stop_time).total_seconds(), 0.0)
    cooldown_threshold = _number(config.get("stop_reentry_cooldown_minutes", 15))
    cooldown_threshold = (cooldown_threshold or 15) * 60
    ema_enabled = bool(config.get("ema_reentry_enabled", True)) and config.get(
        "trading_mode"
    ) in {"intraday_options", "intraday_both"}
    ema_reentry_confirmed = bool(snapshot.get("ema_reentry_confirmed"))
    ema_context = _ema_reentry_context(
        snapshot.get("underlying_history") or [], leg, stop_time
    )
    reentry_state = snapshot.get("ema_reentry_state") or {}
    stop_out_low = _number(reentry_state.get("stop_out_low"))
    premium = _number(quote.get("last_price", quote.get("ltp")))
    if premium is None:
        premium = _number(gates.get("ltp"))
    premium_cancelled = (
        bool(reentry_state.get("status") == "cancelled")
        or (
            stop_out_low is not None
            and premium is not None
            and premium < stop_out_low
        )
    )
    conditions: dict[str, dict] = {
        "cooldown": _condition(
            "not_applicable"
            if ema_reentry_confirmed
            else "pass"
            if elapsed >= cooldown_threshold
            else "fail",
            elapsed,
            cooldown_threshold,
        ),
        "signal_present": _condition(
            "pass" if signal == expected_signal else "fail",
            {"signal": signal, "expected_direction": expected_signal},
            expected_signal,
        ),
        "stop_reentry_score": _condition(
            "not_applicable" if score is None else "pass" if score >= stop_floor else "fail",
            score,
            stop_floor,
        ),
        "ordinary_entry_score": _condition(
            "not_applicable" if score is None else "pass" if score >= ordinary_floor else "fail",
            score,
            ordinary_floor,
        ),
        "ema_cross": _condition(
            "not_applicable" if not ema_enabled else "pass" if ema_context["cross"] else "fail",
            {
                "cross": ema_context["cross"],
                "cross_candle_time": ema_context["cross_candle_time"],
            },
            "directional EMA(5)/EMA(20) cross after stop",
        ),
        "confirming_underlying_close": _condition(
            "not_applicable"
            if not ema_enabled or not ema_context["cross"]
            else "pass" if ema_context["confirmation"] else "fail",
            ema_context["confirmation"],
            "close above crossover high (CE) or below crossover low (PE)",
        ),
        "premium_low_cancel": _condition(
            "not_applicable" if stop_out_low is None else "fail" if premium_cancelled else "pass",
            {"new_low": premium if premium_cancelled else None, "stop_out_low": stop_out_low},
            f"premium >= {stop_out_low}" if stop_out_low is not None else None,
        ),
    }

    trade_count = int(manager.get("session_trade_count", 0) or 0)
    allow_stop_reentry = bool(
        config.get("stop_reentry_enabled", False) or ema_reentry_confirmed
    )
    valid_stop_lock = trade_count == 1 and bool(manager.get("has_loss_stop"))
    lock_passed = (
        trade_count == 0
        or (
            allow_stop_reentry
            and valid_stop_lock
            and int(manager.get("reentries_used", 0) or 0) == 0
        )
    )
    conditions["one_per_symbol_lock"] = _condition(
        "pass" if lock_passed else "fail",
        {
            "session_trade_count": trade_count,
            "reentries_used": min(
                int(manager.get("reentries_used", 0) or 0), 1
            ),
        },
        "at most one stop re-entry per symbol per session",
    )
    reversal_locked = bool(manager.get("reversal_locked"))
    conditions["reversal_lock"] = _condition(
        "fail" if reversal_locked else "pass",
        reversal_locked,
        False,
    )

    recent_loss_elapsed = manager.get("recent_loss_elapsed_seconds")
    recent_loss_threshold = _number(manager.get("loss_cooldown_seconds", 1800)) or 1800
    recent_loss_active = (
        int(manager.get("consecutive_losses", 0) or 0) >= 2
        and recent_loss_elapsed is not None
        and float(recent_loss_elapsed) < recent_loss_threshold
    )
    conditions["recent_loss_cooldown"] = _condition(
        "fail" if recent_loss_active else "pass",
        recent_loss_elapsed,
        recent_loss_threshold,
    )
    trades_count = int(manager.get("symbol_trades", 0) or 0)
    win_rate = _number(manager.get("symbol_win_rate"))
    win_rate_threshold = _number(manager.get("symbol_min_win_rate", 35.0)) or 35.0
    win_rate_blocked = trades_count >= int(manager.get("min_symbol_trades_for_cap", 5)) and (
        win_rate is not None and win_rate < win_rate_threshold
    )
    conditions["win_rate_cap"] = _condition(
        "fail" if win_rate_blocked else "pass",
        {"win_rate": win_rate, "trades": trades_count},
        {"minimum_trades": manager.get("min_symbol_trades_for_cap", 5), "minimum_win_rate": win_rate_threshold},
    )

    daily_pnl = _number(manager.get("daily_pnl"))
    max_daily_loss = _number(manager.get("daily_max_loss"))
    realized_losses = _number(manager.get("daily_realized_losses"))
    daily_loss_blocked = (
        daily_pnl is not None
        and max_daily_loss is not None
        and daily_pnl <= -max_daily_loss
    ) or (
        realized_losses is not None
        and max_daily_loss is not None
        and realized_losses >= max_daily_loss
    )
    conditions["daily_loss_guard"] = _condition(
        "not_applicable" if daily_pnl is None or max_daily_loss is None else "fail" if daily_loss_blocked else "pass",
        {"daily_pnl": daily_pnl, "realized_losses": realized_losses},
        {"daily_pnl_floor": -max_daily_loss if max_daily_loss is not None else None, "realized_loss_cap": max_daily_loss},
    )
    consecutive = int(manager.get("consecutive_losses", 0) or 0)
    consecutive_limit = int(manager.get("max_consecutive_losses", 3) or 3)
    conditions["consecutive_losses_guard"] = _condition(
        "pass" if consecutive < consecutive_limit else "fail",
        consecutive,
        consecutive_limit,
    )

    open_risk = _number(entry_evaluation.get("open_risk_rupees", manager.get("open_risk")))
    max_open_risk = _number(entry_evaluation.get("max_open_risk_rupees"))
    proposed_open_risk = _number(entry_evaluation.get("proposed_total_open_risk_rupees"))
    if max_open_risk is None:
        account_size = _number(config.get("account_size"))
        open_risk_pct = _number(config.get("max_open_risk_pct", 4.0))
        if account_size is not None and open_risk_pct is not None:
            max_open_risk = account_size * open_risk_pct / 100.0
    if proposed_open_risk is None:
        proposed_open_risk = open_risk
    open_risk_blocked = (
        proposed_open_risk is not None
        and max_open_risk is not None
        and proposed_open_risk > max_open_risk
    )
    conditions["open_risk_guard"] = _condition(
        "not_applicable" if open_risk is None and proposed_open_risk is None else "fail" if open_risk_blocked else "pass",
        {"open_risk": open_risk, "proposed_total": proposed_open_risk},
        max_open_risk,
    )
    capital_used = _number(entry_evaluation.get("proposed_invested_amount"))
    capital_cap = _number(entry_evaluation.get("max_capital_per_trade_amount"))
    capital_blocked = capital_used is not None and capital_cap is not None and capital_used > capital_cap
    conditions["capital_cap_guard"] = _condition(
        "not_applicable" if capital_used is None or capital_cap is None else "fail" if capital_blocked else "pass",
        capital_used,
        capital_cap,
    )
    aggregate_budget = _number(
        entry_evaluation.get(
            "remaining_aggregate_daily_risk_rupees",
            manager.get("available_daily_risk"),
        )
    )
    risk_budget = _number(entry_evaluation.get("entry_risk_budget_rupees"))
    aggregate_blocked = aggregate_budget is not None and aggregate_budget <= 1e-6
    conditions["aggregate_budget_guard"] = _condition(
        "not_applicable" if aggregate_budget is None else "fail" if aggregate_blocked else "pass",
        {"remaining_budget": aggregate_budget, "entry_budget": risk_budget},
        "> 0",
    )

    quote_age = _number(gates.get("quote_age_seconds"))
    quote_age_limit = _number(gates.get("quote_age_threshold_seconds"))
    quote_fresh = quote_age is not None and quote_age_limit is not None and 0 <= quote_age <= quote_age_limit
    conditions["quote_freshness"] = _condition(
        "fail"
        if signal == expected_signal and quote_age is None
        else "not_applicable"
        if quote_age is None or quote_age_limit is None
        else "pass"
        if quote_fresh
        else "fail",
        quote_age if quote_age is not None else "quote unavailable",
        quote_age_limit,
    )
    flags = set(gates.get("paper_change_flags") or [])
    min_premium = _number(config.get("option_min_premium", 12.0))
    min_premium = 12.0 if min_premium is None else min_premium
    if "support_reversal" in str(snapshot.get("strategy_variant") or ""):
        support_minimum = _number(config.get("support_reversal_min_premium", 5.0))
        min_premium = 5.0 if support_minimum is None else support_minimum
    if "premium_floor_v2" in flags:
        min_premium = max(
            min_premium,
            12.0 if "support_reversal" in str(snapshot.get("strategy_variant") or "") else 15.0,
        )
    max_premium = (
        1000.0
        if event.get("underlying") == "BANKNIFTY"
        and flags.intersection({"banknifty_caps_v2", "capital_based_risk_v2"})
        else _number(config.get("option_max_premium", 800.0))
    )
    strong_threshold = _number(config.get("strong_signal_score", 82))
    strong_signal = score is not None and score >= int(
        82 if strong_threshold is None else strong_threshold
    )
    premium_floor = min_premium * (0.55 if strong_signal else 0.65)
    configured_volume = _number(config.get("option_min_volume", 200))
    configured_oi = _number(config.get("option_min_oi", 400))
    min_volume = int(200 if configured_volume is None else configured_volume)
    min_oi = int(400 if configured_oi is None else configured_oi)
    volume_floor = max(int(min_volume * (0.6 if strong_signal else 0.7)), 150)
    oi_floor = max(int(min_oi * (0.6 if strong_signal else 0.7)), 300)
    premium_in_range = (
        premium is not None
        and max_premium is not None
        and premium <= max_premium
        and (
            premium >= min_premium
            or (
                "premium_floor_v2" not in flags
                and premium >= premium_floor
            )
        )
    )
    has_oi = quote.get("oi") is not None
    if premium is not None and premium < min_premium and not premium_in_range:
        premium_in_range = False
    conditions["premium_range"] = _condition(
        "not_applicable"
        if signal != expected_signal or premium is None
        else "pass"
        if premium_in_range
        else "fail",
        premium,
        {"minimum": min_premium, "maximum": max_premium},
    )
    body_ratio = _number(gates.get("body_ratio"))
    body_threshold = _number(gates.get("body_ratio_threshold"))
    body_passed = gates.get("body_ratio_passed")
    conditions["body_ratio"] = _condition(
        "not_applicable"
        if (
            signal != expected_signal
            or snapshot.get("ema_reentry_confirmed")
            or gates.get("body_ratio_gate_applies") is False
            or body_ratio is None
            or body_threshold is None
        )
        else "pass"
        if body_passed is True or body_ratio >= body_threshold
        else "fail",
        body_ratio,
        body_threshold,
    )
    volume = _number(quote.get("volume", 0))
    oi = _number(quote.get("oi"))
    iv = _number(quote.get("iv"))
    iv_min = _number(config.get("option_iv_min", 0.08))
    iv_max = _number(config.get("option_iv_max", 1.20))
    soft_volume_pass = (
        volume is not None
        and volume >= volume_floor
        and premium is not None
        and premium >= premium_floor
        and (not has_oi or (oi is not None and oi >= oi_floor))
    )
    soft_oi_pass = (
        oi is not None
        and oi >= oi_floor
        and premium is not None
        and premium >= premium_floor
        and volume is not None
        and volume >= volume_floor
    )
    conditions["volume"] = _condition(
        "not_applicable"
        if signal != expected_signal or volume is None
        else "pass"
        if volume >= min_volume or soft_volume_pass
        else "fail",
        volume,
        min_volume,
    )
    conditions["open_interest"] = _condition(
        "not_applicable"
        if signal != expected_signal or not has_oi or oi is None
        else "pass"
        if oi >= min_oi or soft_oi_pass
        else "fail",
        oi,
        min_oi,
    )
    iv_pass = (
        iv_min is not None
        and iv_max is not None
        and (
            iv_min <= iv <= iv_max
            or (
                strong_signal
                and iv_min * 0.7 <= iv <= iv_max * 1.25
            )
        )
    ) if iv is not None else False
    conditions["implied_volatility"] = _condition(
        "not_applicable"
        if signal != expected_signal or iv is None
        else "pass"
        if iv_pass
        else "fail",
        iv,
        {"minimum": iv_min, "maximum": iv_max},
    )
    volatility = _number(gates.get("volatility_pct"))
    volatility_min = _number(gates.get("volatility_min_pct"))
    volatility_max = _number(gates.get("volatility_max_pct"))
    conditions["volatility"] = _condition(
        "not_applicable"
        if signal != expected_signal or volatility is None
        else "pass"
        if (volatility_min is None or volatility >= volatility_min)
        and (volatility_max is None or volatility <= volatility_max)
        else "fail",
        volatility,
        {"minimum": volatility_min, "maximum": volatility_max},
    )
    adx = _number(gates.get("adx"))
    adx_threshold = _number(gates.get("adx_threshold"))
    conditions["adx"] = _condition(
        "not_applicable"
        if signal != expected_signal or adx is None or adx_threshold is None
        else "pass"
        if adx >= adx_threshold
        else "fail",
        adx,
        adx_threshold,
    )
    market_time = now.time()
    in_hours = time(9, 15) <= market_time < time(15, 30)
    conditions["trading_hours"] = _condition(
        "pass" if in_hours else "fail",
        now.isoformat(),
        "09:15-15:30 IST",
    )
    cutoff_reason = snapshot.get("entry_cutoff_reason")
    cutoff_minutes = _number(config.get("entry_cutoff_minutes_before_close", 45))
    cutoff_minutes = 45 if cutoff_minutes is None else cutoff_minutes
    cutoff_time = time(15, 30)
    if 0 < cutoff_minutes <= 375:
        cutoff_time = (
            datetime.combine(now.date(), cutoff_time, tzinfo=IST)
            - timedelta(minutes=cutoff_minutes)
        ).time()
    cutoff_active = (
        0 < cutoff_minutes <= 375
        and time(9, 15) <= market_time < time(15, 30)
        and market_time >= cutoff_time
    )
    conditions["entry_cutoff"] = _condition(
        "fail" if cutoff_reason or cutoff_active else "pass",
        cutoff_reason or (cutoff_time.isoformat() if cutoff_active else None),
        f"{cutoff_minutes:g} minutes before 15:30 IST",
    )

    failed_count = sum(
        item["result"] == "fail" for item in conditions.values()
    )
    first_failed = _failure_category(str(snapshot.get("outcome") or ""), conditions)
    if first_failed is not None and first_failed not in FAILURE_BUCKETS:
        first_failed = "other"
    return {
        "timestamp": now.isoformat(timespec="seconds"),
        "stop_event_id": event["stop_event_id"],
        "original_trade_id": event.get(
            "original_trade_id", event.get("trade_id")
        ),
        "contract_id": event.get("contract_id") or "",
        "underlying": event.get("underlying") or "",
        "leg": leg,
        "decision_bar_time": _as_ist(snapshot.get("bar_time")).isoformat(timespec="seconds"),
        "signal": signal,
        "signal_direction": expected_signal,
        "reentry_route": (
            "ema_reentry"
            if ema_reentry_confirmed
            else "stop_reentry"
            if config.get("stop_reentry_enabled", False)
            else None
        ),
        "score": score,
        "decision_outcome": snapshot.get("outcome"),
        "conditions": conditions,
        "first_failed_condition": first_failed,
        "n_failed_conditions": failed_count,
        "reentry_opened": bool(snapshot.get("reentry_opened")),
        "config_hash": config_hash,
    }


class StopReentryJournal:
    """Best-effort asynchronous stop and re-entry telemetry."""

    def __init__(
        self,
        root: str | Path,
        capture_root: str | Path,
        *,
        config_hash: str,
        max_queue_size: int = 10000,
    ) -> None:
        self.root = Path(root)
        self.capture_root = Path(capture_root)
        self.config_hash = config_hash
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._closed = False
        self._worker = threading.Thread(
            target=self._run, name="stop-reentry-journal", daemon=True
        )
        self._worker.start()

    def _enqueue(self, item: dict, row_type: str) -> bool:
        if self._closed:
            logger.warning("Dropping %s telemetry row: journal is closed", row_type)
            return False
        try:
            self._queue.put_nowait(item)
            return True
        except queue.Full:
            logger.warning("Dropping %s telemetry row: writer queue is full", row_type)
        except Exception:
            logger.exception("Dropping %s telemetry row: could not enqueue", row_type)
        return False

    def record_stop_event(self, payload: dict) -> Optional[str]:
        event_id = str(uuid.uuid4())
        event = dict(payload)
        event["original_trade_id"] = event.get(
            "original_trade_id", event.get("trade_id")
        )
        event.update(
            {
                "record_type": "stop_event",
                "stop_event_id": event_id,
                "stop_time": (
                    _as_ist(event.get("stop_time")) or datetime.now(IST)
                ).isoformat(timespec="seconds"),
                "config_hash": self.config_hash,
            }
        )
        return event_id if self._enqueue(("stop", event), "stop_event") else None

    def record_check(self, event_id: str, snapshot: dict) -> bool:
        return self._enqueue(
            ("check", event_id, snapshot), "reentry_check"
        )

    def record_path_poll(self, event_id: str, timestamp: Any) -> bool:
        return self._enqueue(
            ("path_poll", event_id, timestamp), "after-stop price path"
        )

    def record_reentry_opened(
        self, event_id: str, trade_id: Optional[str], timestamp: Any
    ) -> bool:
        return self._enqueue(
            ("reentry_opened", event_id, trade_id, timestamp),
            "re-entry-opened",
        )

    def end_session(self, timestamp: Any) -> bool:
        return self._enqueue(("end_session", timestamp), "session-end")

    def flush(self, timeout: float = 1.0) -> bool:
        completed = threading.Event()
        if not self._enqueue(("flush", completed), "flush"):
            return False
        return completed.wait(max(timeout, 0.0))

    def close(self, timeout: float = 1.0) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put_nowait(("close",))
        except queue.Full:
            logger.warning("Stop/re-entry journal queue full while closing")
            return
        self._worker.join(max(timeout, 0.0))

    @staticmethod
    def _json_row(path: Path, columns: tuple[str, ...], payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {column: payload.get(column) for column in columns}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, default=str, separators=(",", ":")) + "\n")

    def _write_stop_row(self, payload: dict) -> None:
        self._json_row(self.root / "stop_events.jsonl", STOP_EVENT_COLUMNS, payload)

    def _write_check_row(self, payload: dict) -> None:
        self._json_row(
            self.root / "reentry_checks.jsonl", REENTRY_CHECK_COLUMNS, payload
        )

    def _path_record(self, event: dict, minutes: int) -> dict:
        stop_time = _as_ist(event.get("stop_time"))
        if stop_time is None:
            raise ValueError("Stop event has an invalid stop timestamp")
        target_time = stop_time + timedelta(minutes=minutes)
        capture = load_option_capture(
            self.capture_root,
            stop_time.date(),
            {"contract_id": event.get("contract_id")},
        )
        candles = []
        for row in capture["candles"]:
            candle_time = _as_ist(row.get("candle_start_time"))
            high, low, close = (
                _number(row.get("high")),
                _number(row.get("low")),
                _number(row.get("close")),
            )
            if candle_time is None or high is None or low is None or close is None:
                continue
            candles.append((candle_time, high, low, close))
        before_stop = [
            row
            for row in candles
            if stop_time - timedelta(minutes=5) <= row[0]
            and row[0] + timedelta(minutes=1) <= stop_time
        ]
        after_stop = [
            row for row in candles if stop_time <= row[0] < target_time
        ]
        entry_price = _number(event.get("entry_price"))
        pre_stop_high = max((row[1] for row in before_stop), default=None)
        valid_after = bool(after_stop)
        above_entry = [
            row for row in after_stop
            if entry_price is not None and row[3] > entry_price
        ]
        above_pre_stop = [
            row for row in after_stop
            if pre_stop_high is not None and row[3] > pre_stop_high
        ]
        above_both = [
            row for row in after_stop
            if entry_price is not None
            and pre_stop_high is not None
            and row[3] > entry_price
            and row[3] > pre_stop_high
        ]
        return {
            "record_type": "after_stop_price_path",
            "stop_event_id": event["stop_event_id"],
            "original_trade_id": event.get(
                "original_trade_id", event.get("trade_id")
            ),
            "contract_id": event.get("contract_id") or "",
            "underlying": event.get("underlying") or "",
            "leg": event.get("leg") or "",
            "stop_time": event.get("stop_time"),
            "entry_price": event.get("entry_price"),
            "stop_price": event.get("stop_price"),
            "exit_price": event.get("exit_price"),
            "exit_reason": event.get("exit_reason"),
            "net_pnl": event.get("net_pnl"),
            "config_hash": self.config_hash,
            "checkpoint_minutes": minutes,
            "highest_price_since_stop": (
                max((row[1] for row in after_stop), default=None)
                if valid_after
                else None
            ),
            "lowest_price_since_stop": (
                min((row[2] for row in after_stop), default=None)
                if valid_after
                else None
            ),
            "pre_stop_5m_high": pre_stop_high,
            "closed_above_entry": bool(above_entry) if valid_after else None,
            "first_close_above_entry_time": (
                (above_entry[0][0] + timedelta(minutes=1)).isoformat()
                if above_entry
                else None
            ),
            "closed_above_pre_stop_5m_high": (
                bool(above_pre_stop) if valid_after else None
            ),
            "first_close_above_pre_stop_5m_high_time": (
                (above_pre_stop[0][0] + timedelta(minutes=1)).isoformat()
                if above_pre_stop
                else None
            ),
            "closed_above_both": bool(above_both) if valid_after else None,
            "first_close_above_both_time": (
                (above_both[0][0] + timedelta(minutes=1)).isoformat()
                if above_both
                else None
            ),
            "candles_missing": not valid_after,
            "reentry_trade_id": None,
        }

    def _write_path_updates(
        self,
        events: dict[str, dict],
        timestamp: Any,
        *,
        only_event_id: Optional[str] = None,
        session_end: bool = False,
    ) -> None:
        now = _as_ist(timestamp) or datetime.now(IST)
        for event_id, event in list(events.items()):
            if (
                only_event_id is not None
                and only_event_id != event.get("stop_event_id")
            ):
                continue
            stop_time = _as_ist(event.get("stop_time"))
            if stop_time is None:
                continue
            elapsed = (now - stop_time).total_seconds()
            for minutes in PRICE_PATH_CHECKPOINTS:
                if minutes in event.setdefault("path_checkpoints", set()):
                    continue
                if elapsed < minutes * 60:
                    continue
                try:
                    row = self._path_record(event, minutes)
                except Exception:
                    logger.exception(
                        "Could not read option candles for stop event %s at %s minutes",
                        event_id,
                        minutes,
                    )
                    row = {
                        "record_type": "after_stop_price_path",
                        "stop_event_id": event_id,
                        "original_trade_id": event.get(
                            "original_trade_id", event.get("trade_id")
                        ),
                        "contract_id": event.get("contract_id") or "",
                        "underlying": event.get("underlying") or "",
                        "leg": event.get("leg") or "",
                        "stop_time": event.get("stop_time"),
                        "entry_price": event.get("entry_price"),
                        "stop_price": event.get("stop_price"),
                        "exit_price": event.get("exit_price"),
                        "exit_reason": event.get("exit_reason"),
                        "net_pnl": event.get("net_pnl"),
                        "config_hash": self.config_hash,
                        "checkpoint_minutes": minutes,
                        "candles_missing": True,
                    }
                if (
                    row.get("candles_missing")
                    and not session_end
                    and elapsed < minutes * 60 + 120
                ):
                    continue
                self._write_stop_row(row)
                event["path_checkpoints"].add(minutes)
            if (
                len(event["path_checkpoints"]) == len(PRICE_PATH_CHECKPOINTS)
                and (
                    event.get("reentry_opened")
                    or elapsed > REENTRY_WINDOW_SECONDS
                    or session_end
                )
            ):
                events.pop(event_id, None)

    def _run(self) -> None:
        events: dict[str, dict] = {}
        while True:
            item = self._queue.get()
            try:
                command = item[0]
                if command == "close":
                    return
                if command == "flush":
                    item[1].set()
                    continue
                if command == "stop":
                    event = item[1]
                    self._write_stop_row(event)
                    event["path_checkpoints"] = set()
                    event["check_bar_times"] = set()
                    event["reentry_trade_id"] = None
                    events[event["stop_event_id"]] = event
                elif command == "check":
                    _, event_id, snapshot = item
                    event = events.get(event_id)
                    if event is None or event.get("reentry_opened"):
                        continue
                    now = _as_ist(snapshot.get("timestamp"))
                    stop_time = _as_ist(event.get("stop_time"))
                    if now is None or stop_time is None:
                        raise ValueError("Re-entry check has invalid event timestamps")
                    if now.date() != stop_time.date() or (
                        now - stop_time
                    ).total_seconds() > REENTRY_WINDOW_SECONDS:
                        continue
                    bar_time = _as_ist(snapshot.get("bar_time"))
                    bar_key = (
                        bar_time.isoformat()
                        if bar_time is not None
                        else str(snapshot.get("bar_time") or "")
                    )
                    checked_bars = event.setdefault("check_bar_times", set())
                    if bar_key in checked_bars:
                        continue
                    checked_bars.add(bar_key)
                    try:
                        check = _build_reentry_check(
                            event, snapshot, self.config_hash
                        )
                    except Exception:
                        logger.exception(
                            "Could not compute re-entry checks for stop event %s",
                            event_id,
                        )
                        check = {
                            "timestamp": now.isoformat(timespec="seconds"),
                            "stop_event_id": event_id,
                            "original_trade_id": event.get(
                                "original_trade_id", event.get("trade_id")
                            ),
                            "contract_id": event.get("contract_id") or "",
                            "underlying": event.get("underlying") or "",
                            "leg": event.get("leg") or "",
                            "decision_bar_time": snapshot.get("bar_time"),
                            "signal": None,
                            "signal_direction": None,
                            "score": None,
                            "decision_outcome": snapshot.get("outcome"),
                            "conditions": None,
                            "first_failed_condition": None,
                            "n_failed_conditions": None,
                            "reentry_opened": bool(snapshot.get("reentry_opened")),
                            "config_hash": self.config_hash,
                        }
                    self._write_check_row(check)
                elif command == "path_poll":
                    _, path_event_id, timestamp = item
                    self._write_path_updates(
                        events, timestamp, only_event_id=path_event_id
                    )
                elif command == "reentry_opened":
                    _, event_id, trade_id, timestamp = item
                    event = events.get(event_id)
                    if event is not None:
                        event["reentry_opened"] = True
                        event["reentry_trade_id"] = trade_id or ""
                        self._write_stop_row(
                            {
                                **event,
                                "record_type": "reentry_opened",
                                "reentry_trade_id": trade_id,
                                "config_hash": self.config_hash,
                            }
                        )
                    self._write_path_updates(events, timestamp)
                elif command == "end_session":
                    self._write_path_updates(events, item[1], session_end=True)
                else:
                    logger.warning("Dropping unknown stop/re-entry journal command %r", command)
            except Exception:
                logger.exception("Dropping stop/re-entry journal row after writer failure")
            finally:
                self._queue.task_done()


def summarize_stop_events(
    root: str | Path, target_date: date, *, warn_missing: bool = True
) -> dict[str, Any]:
    root_path = Path(root)
    stop_path = root_path / "stop_events.jsonl"
    check_path = root_path / "reentry_checks.jsonl"
    events: dict[str, dict] = {}
    checks: dict[str, list[dict]] = {}
    paths = [path for path in (stop_path, check_path) if path.is_file()]
    with ReportingStep(
        logger,
        "stop_out_diagnostics",
        paths,
        [
            "stop_time", "timestamp", "stop_event_id", "record_type",
            "checkpoint_minutes", "first_failed_condition",
        ],
    ) as step:
        rows_read = 0
        for path, target in ((stop_path, events), (check_path, checks)):
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        rows_read += 1
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning(
                                "Skipping malformed telemetry row in %s", path
                            )
                            continue
                        timestamp = _as_ist(
                            row.get("stop_time") or row.get("timestamp")
                        )
                        if timestamp is None or timestamp.date() != target_date:
                            continue
                        event_id = str(row.get("stop_event_id") or "")
                        if not event_id:
                            continue
                        if target is events:
                            event = events.setdefault(event_id, {})
                            if row.get("record_type") == "stop_event":
                                event.update(row)
                            elif row.get("record_type") == "reentry_opened":
                                event["reentry_trade_id"] = row.get(
                                    "reentry_trade_id"
                                )
                            elif row.get("record_type") == "after_stop_price_path":
                                event.setdefault("price_paths", {})[
                                    int(row.get("checkpoint_minutes") or 0)
                                ] = row
                        else:
                            checks.setdefault(event_id, []).append(row)
            except OSError:
                logger.exception("Could not read stop/re-entry journal %s", path)
        step.rows = rows_read

    recovered_30 = recovered_60 = candles_missing_events = reentered = 0
    first_failures = {bucket: 0 for bucket in FAILURE_BUCKETS}
    for event_id, event in events.items():
        if event.get("reentry_opened") or event.get("reentry_trade_id"):
            reentered += 1
        paths = event.get("price_paths", {})
        if any(row.get("candles_missing") for row in paths.values()):
            candles_missing_events += 1
        path_30 = paths.get(30, {})
        path_60 = paths.get(60, {})
        recovered_30 += bool(path_30.get("closed_above_entry"))
        recovered_60 += bool(path_60.get("closed_above_entry"))
        event_checks = sorted(
            checks.get(event_id, []),
            key=lambda row: str(row.get("decision_bar_time") or ""),
        )
        if event_checks:
            bucket = event_checks[0].get("first_failed_condition") or "other"
            first_failures[bucket if bucket in first_failures else "other"] += 1
        else:
            first_failures["other"] += 1

    count = len(events)
    if warn_missing and count and candles_missing_events / count > 0.10:
        logger.warning(
            "%.1f%% of stop events have missing option candles (%d/%d)",
            candles_missing_events / count * 100,
            candles_missing_events,
            count,
        )
    return {
        "stop_events": count,
        "stop_events_reentered": reentered,
        "stop_events_recovered_above_entry_30m": recovered_30,
        "stop_events_recovered_above_entry_60m": recovered_60,
        "stop_events_candles_missing": candles_missing_events,
        "stop_events_first_failed_condition": first_failures,
    }