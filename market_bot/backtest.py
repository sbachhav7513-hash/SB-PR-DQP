from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class BacktestResult:
    trades: List[BacktestTrade]

    @property
    def total_return_pct(self) -> float:
        return sum(trade.return_pct for trade in self.trades)

    @property
    def win_rate_pct(self) -> float:
        if not self.trades:
            return 0.0
        return 100.0 * sum(trade.return_pct > 0 for trade in self.trades) / len(self.trades)


def run_backtest(
    ticker: str,
    history: List[Dict],
    stop_loss_pct: float = 0.75,
    take_profit_pct: float = 1.5,
    signal_fn: Callable[[str, List[Dict]], TradingScore] = score_market,
) -> BacktestResult:
    """Replay signals using next-bar-open entries and OHLC stop/target checks."""
    if stop_loss_pct <= 0 or take_profit_pct <= 0:
        raise ValueError("stop_loss_pct and take_profit_pct must be positive")

    candles = [item for item in history if _valid_candle(item)]
    trades: List[BacktestTrade] = []
    position: Optional[dict] = None

    for index in range(1, len(candles)):
        candle = candles[index]
        if position is not None:
            exit_price, exit_reason = _intrabar_exit(position, candle)
            if exit_price is not None:
                trades.append(_close_trade(position, candle, exit_price, exit_reason))
                position = None

        if position is None:
            decision = signal_fn(ticker, candles[:index])
            if decision.signal in {"BUY", "SELL"}:
                entry_price = float(candle["open"])
                position = _open_position(decision.signal, candle, entry_price, stop_loss_pct, take_profit_pct)
                exit_price, exit_reason = _intrabar_exit(position, candle)
                if exit_price is not None:
                    trades.append(_close_trade(position, candle, exit_price, exit_reason))
                    position = None

    if position is not None:
        last_candle = candles[-1]
        trades.append(_close_trade(position, last_candle, float(last_candle["close"]), "END_OF_DATA"))

    return BacktestResult(trades=trades)


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


def _close_trade(position: dict, candle: Dict, exit_price: float, exit_reason: str) -> BacktestTrade:
    entry_price = position["entry_price"]
    direction = 1 if position["action"] == "BUY" else -1
    return BacktestTrade(
        action=position["action"],
        entry_time=position["entry_time"],
        exit_time=candle.get("time", candle.get("date")),
        entry_price=entry_price,
        exit_price=exit_price,
        return_pct=direction * (exit_price - entry_price) / entry_price * 100.0,
        exit_reason=exit_reason,
    )