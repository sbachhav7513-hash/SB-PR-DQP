from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Callable, Dict, List, Optional

from .engine import TradingScore, score_market


@dataclass
class BacktestTrade:
    action: str
    entry_time: object
    exit_time: object
    entry_price: float
    exit_price: float
    return_pct: float
    exit_reason: str
    gross_return_pct: float = 0.0
    cost_pct: float = 0.0


@dataclass
class BacktestResult:
    trades: List[BacktestTrade]
    signal_counts: Dict[str, int] = field(default_factory=dict)
    reason_counts: Dict[str, int] = field(default_factory=dict)
    rejection_counts: Dict[str, int] = field(default_factory=dict)
    evaluated_bars: int = 0

    @property
    def total_return_pct(self) -> float:
        return sum(trade.return_pct for trade in self.trades)

    @property
    def win_rate_pct(self) -> Optional[float]:
        if not self.trades:
            return None
        return 100.0 * sum(trade.return_pct > 0 for trade in self.trades) / len(self.trades)


def run_backtest(
    ticker: str,
    history: List[Dict],
    stop_loss_pct: float = 0.75,
    take_profit_pct: float = 1.5,
    signal_fn: Callable[[str, List[Dict]], TradingScore] = score_market,
    entry_filter: Optional[Callable[[str, TradingScore, List[Dict]], Optional[str]]] = None,
    fee_bps_per_side: float = 0.0,
    slippage_bps_per_side: float = 0.0,
    market_close_time: Optional[str] = None,
    flatten_on_session_change: bool = False,
    max_trades_per_session: Optional[int] = None,
    trailing_enabled: bool = False,
    trailing_activation_ratio: float = 0.5,
    trailing_distance_ratio: float = 0.25,
    history_limit: Optional[int] = None,
) -> BacktestResult:
    """Replay completed-bar signals at the next open with optional live gates and costs."""
    if stop_loss_pct <= 0 or take_profit_pct <= 0:
        raise ValueError("stop_loss_pct and take_profit_pct must be positive")
    if fee_bps_per_side < 0 or slippage_bps_per_side < 0:
        raise ValueError("fee and slippage assumptions cannot be negative")
    if max_trades_per_session is not None and max_trades_per_session < 1:
        raise ValueError("max_trades_per_session must be positive")
    if trailing_activation_ratio < 0 or trailing_distance_ratio < 0:
        raise ValueError("trailing ratios cannot be negative")
    if history_limit is not None and history_limit < 1:
        raise ValueError("history_limit must be positive")

    close_at = time.fromisoformat(market_close_time) if market_close_time else None

    candles = [item for item in history if _valid_candle(item)]
    trades: List[BacktestTrade] = []
    position: Optional[dict] = None
    signal_counts: Counter = Counter()
    reason_counts: Counter = Counter()
    rejection_counts: Counter = Counter()
    session_entries: Counter = Counter()
    evaluated_bars = 0

    for index in range(1, len(candles)):
        candle = candles[index]
        if position is not None:
            previous_candle = candles[index - 1]
            previous_time = _bar_datetime(previous_candle)
            current_time = _bar_datetime(candle)
            crossed_session = (
                flatten_on_session_change
                and previous_time is not None
                and current_time is not None
                and previous_time.date() != current_time.date()
            )
            if crossed_session:
                trades.append(_close_trade(
                    position,
                    previous_candle,
                    float(previous_candle["close"]),
                    "SESSION_CLOSE",
                    fee_bps_per_side,
                    slippage_bps_per_side,
                ))
                position = None

        if position is not None:
            exit_price, exit_reason = _advance_position(
                position,
                candle,
                trailing_enabled,
                trailing_activation_ratio,
                trailing_distance_ratio,
            )
            if exit_price is not None:
                trades.append(_close_trade(
                    position, candle, exit_price, exit_reason,
                    fee_bps_per_side, slippage_bps_per_side,
                ))
                position = None
            elif close_at is not None:
                current_time = _bar_datetime(candle)
                if current_time is not None and current_time.time() >= close_at:
                    trades.append(_close_trade(
                        position,
                        candle,
                        float(candle["close"]),
                        "MARKET_CLOSE",
                        fee_bps_per_side,
                        slippage_bps_per_side,
                    ))
                    position = None

        if position is None:
            signal_history = candles[:index]
            if history_limit is not None:
                signal_history = signal_history[-history_limit:]
            decision = signal_fn(ticker, signal_history)
            evaluated_bars += 1
            signal_counts[decision.signal] += 1
            reason_counts.update(decision.reasons)
            if decision.signal in {"BUY", "SELL"}:
                entry_time = _bar_datetime(candle)
                if close_at is not None and entry_time is not None and entry_time.time() >= close_at:
                    rejection_counts["market_close"] += 1
                    continue
                session_key = entry_time.date() if entry_time is not None else None
                if (
                    max_trades_per_session is not None
                    and session_key is not None
                    and session_entries[session_key] >= max_trades_per_session
                ):
                    rejection_counts["session_trade_limit"] += 1
                    continue
                rejection = (
                    entry_filter(ticker, decision, signal_history)
                    if entry_filter is not None
                    else None
                )
                if rejection:
                    rejection_counts[rejection] += 1
                    continue
                entry_price = float(candle["open"])
                position = _open_position(decision.signal, candle, entry_price, stop_loss_pct, take_profit_pct)
                if session_key is not None:
                    session_entries[session_key] += 1
                exit_price, exit_reason = _advance_position(
                    position,
                    candle,
                    trailing_enabled,
                    trailing_activation_ratio,
                    trailing_distance_ratio,
                )
                if exit_price is not None:
                    trades.append(_close_trade(
                        position, candle, exit_price, exit_reason,
                        fee_bps_per_side, slippage_bps_per_side,
                    ))
                    position = None

    if position is not None:
        last_candle = candles[-1]
        trades.append(_close_trade(
            position,
            last_candle,
            float(last_candle["close"]),
            "END_OF_DATA",
            fee_bps_per_side,
            slippage_bps_per_side,
        ))

    return BacktestResult(
        trades=trades,
        signal_counts=dict(signal_counts),
        reason_counts=dict(reason_counts),
        rejection_counts=dict(rejection_counts),
        evaluated_bars=evaluated_bars,
    )


def _bar_datetime(candle: Dict) -> Optional[datetime]:
    value = candle.get("time", candle.get("date"))
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _valid_candle(candle: Dict) -> bool:
    try:
        prices = [float(candle[field]) for field in ("open", "high", "low", "close")]
    except (KeyError, TypeError, ValueError):
        return False
    return all(price > 0 for price in prices) and float(candle["high"]) >= float(candle["low"])


def _open_position(action: str, candle: Dict, entry_price: float, stop_loss_pct: float, take_profit_pct: float) -> dict:
    if action == "BUY":
        stop_loss = entry_price * (1 - stop_loss_pct / 100.0)
        take_profit = entry_price * (1 + take_profit_pct / 100.0)
    else:
        stop_loss = entry_price * (1 + stop_loss_pct / 100.0)
        take_profit = entry_price * (1 - take_profit_pct / 100.0)
    return {
        "action": action,
        "entry_time": candle.get("time", candle.get("date")),
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "initial_target_distance": abs(take_profit - entry_price),
        "highest_price": entry_price,
        "lowest_price": entry_price,
        "trailing_stop": None,
        "trailing_active": False,
    }


def _intrabar_exit(position: dict, candle: Dict) -> tuple[Optional[float], Optional[str]]:
    high = float(candle["high"])
    low = float(candle["low"])
    if position["action"] == "BUY":
        if low <= position["stop_loss"]:
            return position["stop_loss"], "STOP_LOSS"
        if high >= position["take_profit"]:
            return position["take_profit"], "TAKE_PROFIT"
    else:
        if high >= position["stop_loss"]:
            return position["stop_loss"], "STOP_LOSS"
        if low <= position["take_profit"]:
            return position["take_profit"], "TAKE_PROFIT"
    return None, None


def _advance_position(
    position: dict,
    candle: Dict,
    trailing_enabled: bool,
    trailing_activation_ratio: float,
    trailing_distance_ratio: float,
) -> tuple[Optional[float], Optional[str]]:
    if not trailing_enabled:
        return _intrabar_exit(position, candle)

    high = float(candle["high"])
    low = float(candle["low"])
    if position["action"] == "BUY":
        if low <= position["stop_loss"]:
            return position["stop_loss"], "STOP_LOSS"
        previous_stop = position["trailing_stop"]
        if previous_stop is not None and low <= previous_stop:
            return previous_stop, "TRAILING_STOP"
        position["highest_price"] = max(float(position["highest_price"]), high)
        favorable_move = position["highest_price"] - position["entry_price"]
        if favorable_move >= position["initial_target_distance"] * trailing_activation_ratio:
            position["trailing_active"] = True
        if position["trailing_active"]:
            candidate = position["highest_price"] - (
                position["initial_target_distance"] * trailing_distance_ratio
            )
            position["trailing_stop"] = (
                candidate
                if previous_stop is None
                else max(float(previous_stop), candidate)
            )
    else:
        if high >= position["stop_loss"]:
            return position["stop_loss"], "STOP_LOSS"
        previous_stop = position["trailing_stop"]
        if previous_stop is not None and high >= previous_stop:
            return previous_stop, "TRAILING_STOP"
        position["lowest_price"] = min(float(position["lowest_price"]), low)
        favorable_move = position["entry_price"] - position["lowest_price"]
        if favorable_move >= position["initial_target_distance"] * trailing_activation_ratio:
            position["trailing_active"] = True
        if position["trailing_active"]:
            candidate = position["lowest_price"] + (
                position["initial_target_distance"] * trailing_distance_ratio
            )
            position["trailing_stop"] = (
                candidate
                if previous_stop is None
                else min(float(previous_stop), candidate)
            )

    return None, None


def _close_trade(
    position: dict,
    candle: Dict,
    exit_price: float,
    exit_reason: str,
    fee_bps_per_side: float = 0.0,
    slippage_bps_per_side: float = 0.0,
) -> BacktestTrade:
    entry_price = position["entry_price"]
    direction = 1 if position["action"] == "BUY" else -1
    gross_return_pct = direction * (exit_price - entry_price) / entry_price * 100.0
    cost_pct = 2.0 * (fee_bps_per_side + slippage_bps_per_side) / 100.0
    return BacktestTrade(
        action=position["action"],
        entry_time=position["entry_time"],
        exit_time=candle.get("time", candle.get("date")),
        entry_price=entry_price,
        exit_price=exit_price,
        return_pct=gross_return_pct - cost_pct,
        exit_reason=exit_reason,
        gross_return_pct=gross_return_pct,
        cost_pct=cost_pct,
    )