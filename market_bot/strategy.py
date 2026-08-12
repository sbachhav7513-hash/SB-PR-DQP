from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Signal:
    ticker: str
    action: str
    reason: str
    price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


def _trade_levels(price: float, action: str, stop_loss_pct: float, take_profit_pct: float) -> tuple[float, float]:
    if action == "BUY":
        stop_loss = price * (1 - (stop_loss_pct / 100.0))
        take_profit = price * (1 + (take_profit_pct / 100.0))
    else:
        stop_loss = price * (1 + (stop_loss_pct / 100.0))
        take_profit = price * (1 - (take_profit_pct / 100.0))
    return stop_loss, take_profit


def ema(series: List[float], period: int) -> List[float]:
    if len(series) < period:
        return []

    sma = sum(series[:period]) / period
    multiplier = 2 / (period + 1)
    emas = [sma]

    for price in series[period:]:
        next_ema = (price - emas[-1]) * multiplier + emas[-1]
        emas.append(next_ema)

    return emas


def rsi(series: List[float], period: int = 14) -> List[float]:
    if len(series) <= period:
        return []

    changes = [series[i] - series[i - 1] for i in range(1, len(series))]
    gains = [change if change > 0 else 0 for change in changes[:period]]
    losses = [-change if change < 0 else 0 for change in changes[:period]]

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    output: List[float] = []
    for change in changes[period:]:
        gain = change if change > 0 else 0
        loss = -change if change < 0 else 0
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period

        if average_loss == 0:
            output.append(100.0)
        else:
            rs = average_gain / average_loss
            output.append(100.0 - (100.0 / (1 + rs)))

    return output


def _sma(series: List[float], period: int) -> Optional[float]:
    if len(series) < period:
        return None
    return sum(series[-period:]) / period


def analyze_history(
    ticker: str,
    history: List[Dict],
    ema_fast: int,
    ema_slow: int,
    rsi_period: int,
    alert_rsi_low: int,
    alert_rsi_high: int,
    stop_loss_pct: float = 1.5,
    take_profit_pct: float = 3.0,
) -> Optional[Signal]:
    closes = [item["close"] for item in history]
    if len(closes) < max(ema_slow + 20, rsi_period + 20):
        return None

    fast_ema = ema(closes, ema_fast)
    slow_ema = ema(closes, ema_slow)
    latest_rsi = rsi(closes, rsi_period)

    if not fast_ema or not slow_ema or not latest_rsi:
        return None

    price = closes[-1]
    fast_now = fast_ema[-1]
    slow_now = slow_ema[-1]
    fast_prev = fast_ema[-2] if len(fast_ema) >= 2 else fast_now
    slow_prev = slow_ema[-2] if len(slow_ema) >= 2 else slow_now
    rsi_now = latest_rsi[-1]
    sma_20 = _sma(closes, 20)
    if sma_20 is None:
        return None

    bullish_trend = fast_now > slow_now and fast_now >= fast_prev and slow_now >= slow_prev
    bearish_trend = fast_now < slow_now and fast_now <= fast_prev and slow_now <= slow_prev
    in_uptrend = price > sma_20
    in_downtrend = price < sma_20

    recent_window = closes[-10:]
    recent_high = max(recent_window)
    recent_low = min(recent_window)
    breakout_up = price > recent_high * 1.01
    breakout_down = price < recent_low * 0.99

    if bullish_trend and in_uptrend and rsi_now > 45 and rsi_now < 70:
        if fast_prev <= slow_prev or breakout_up:
            stop_loss, take_profit = _trade_levels(price, "BUY", stop_loss_pct, take_profit_pct)
            return Signal(
                ticker=ticker,
                action="BUY",
                reason=f"Trend confirmed: EMA alignment bullish, price above SMA, RSI={rsi_now:.1f}",
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

    if bearish_trend and in_downtrend and rsi_now > 30 and rsi_now < 55:
        if fast_prev >= slow_prev or breakout_down:
            stop_loss, take_profit = _trade_levels(price, "SELL", stop_loss_pct, take_profit_pct)
            return Signal(
                ticker=ticker,
                action="SELL",
                reason=f"Trend confirmed: EMA alignment bearish, price below SMA, RSI={rsi_now:.1f}",
                price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

    if bullish_trend and in_uptrend and rsi_now <= alert_rsi_low and price > recent_low:
        stop_loss, take_profit = _trade_levels(price, "BUY", stop_loss_pct, take_profit_pct)
        return Signal(
            ticker=ticker,
            action="BUY",
            reason=f"Bullish recovery confirmed after oversold RSI={rsi_now:.1f}",
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    if bearish_trend and in_downtrend and rsi_now >= alert_rsi_high and price < recent_high:
        stop_loss, take_profit = _trade_levels(price, "SELL", stop_loss_pct, take_profit_pct)
        return Signal(
            ticker=ticker,
            action="SELL",
            reason=f"Bearish continuation confirmed after overbought RSI={rsi_now:.1f}",
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    return None
