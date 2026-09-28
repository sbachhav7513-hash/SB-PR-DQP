"""Offline replay for historical OHLCV data; this module never places orders."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from .accuracy_filters import AccuracyFilters
from .backtest import BacktestResult, run_backtest
from .engine import TradingScore, score_market

IST = ZoneInfo("Asia/Kolkata")


def _as_ist(value: object) -> Optional[datetime]:
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


def load_candles(path: str | Path) -> List[Dict]:
    """Load sorted OHLCV rows from a CSV or Parquet file.

    Naive timestamps are interpreted as Asia/Kolkata. Required columns are
    timestamp (or time/date), open, high, low, close, and volume.
    """
    source = Path(path)
    if source.suffix.lower() in {".parquet", ".pq"}:
        frame = pd.read_parquet(source)
    elif source.suffix.lower() == ".csv":
        frame = pd.read_csv(source)
    else:
        raise ValueError("OHLCV input must be a .csv or .parquet file")

    frame.columns = [str(column).strip().lower() for column in frame.columns]
    time_column = next(
        (column for column in ("time", "timestamp", "datetime", "date") if column in frame),
        None,
    )
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if time_column is None or missing:
        expected = "time, open, high, low, close, volume"
        raise ValueError(f"{source} must contain {expected}; missing {sorted(missing)}")

    candles = []
    for row in frame.to_dict(orient="records"):
        timestamp = _as_ist(row.get(time_column))
        if timestamp is None or pd.isna(timestamp):
            continue
        try:
            candle = {
                "time": timestamp,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
            for field in ("bid", "ask", "last"):
                if field in row and not pd.isna(row[field]):
                    candle[field] = float(row[field])
        except (TypeError, ValueError):
            continue
        candles.append(candle)

    candles.sort(key=lambda candle: candle["time"])
    return candles


def validate_production_data(
    candles: List[Dict],
    ticker: str,
    expected_symbol: str,
    minimum_history_days: int = 183,
    sustained_zero_volume_bars: int = 5,
) -> Dict:
    """Validate exact-contract, quote-bearing minute data for strict replay."""
    if not expected_symbol or ticker != expected_symbol:
        raise ValueError(
            "Replay ticker does not match required production symbol: "
            f"ticker={ticker!r}, expected={expected_symbol!r}"
        )
    if minimum_history_days < 1 or sustained_zero_volume_bars < 1:
        raise ValueError("history and zero-volume validation thresholds must be positive")
    if not candles:
        raise ValueError("production replay dataset is empty")

    timestamps = []
    zero_volume_rows = 0
    zero_volume_streak = 0
    gaps = []
    previous_timestamp = None
    for index, candle in enumerate(candles):
        timestamp = _as_ist(candle.get("time", candle.get("date")))
        if timestamp is None:
            raise ValueError(f"production candle {index} has an invalid timestamp")
        if timestamp.second or timestamp.microsecond:
            raise ValueError(f"production candle {index} is not aligned to a minute")
        if previous_timestamp is not None:
            delta = timestamp - previous_timestamp
            if delta.total_seconds() <= 0:
                raise ValueError("production candle timestamps must be strictly increasing")
            if delta > timedelta(minutes=1):
                gaps.append({
                    "from": previous_timestamp.isoformat(),
                    "to": timestamp.isoformat(),
                    "missing_minutes": max(1, int(delta.total_seconds() // 60) - 1),
                })
            if delta == timedelta(minutes=1) and float(candle.get("volume", 0)) == 0:
                zero_volume_streak += 1
            elif float(candle.get("volume", 0)) == 0:
                zero_volume_streak = 1
            else:
                zero_volume_streak = 0
        elif float(candle.get("volume", 0)) == 0:
            zero_volume_streak = 1

        try:
            volume = float(candle["volume"])
            quote = {field: float(candle[field]) for field in ("bid", "ask", "last")}
            prices = [float(candle[field]) for field in ("open", "high", "low", "close")]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"production candle {index} must include OHLCV, bid, ask, and last"
            ) from error
        if not all(math.isfinite(value) for value in [volume, *quote.values(), *prices]):
            raise ValueError(f"production candle {index} contains a non-finite value")
        if volume < 0 or any(value <= 0 for value in [*quote.values(), *prices]):
            raise ValueError(f"production candle {index} contains non-positive market data")
        if quote["bid"] > quote["ask"]:
            raise ValueError(f"production candle {index} has a crossed bid/ask quote")
        if volume == 0:
            zero_volume_rows += 1
        if zero_volume_streak >= sustained_zero_volume_bars:
            raise ValueError(
                f"instrument {expected_symbol} has sustained zero volume "
                f"({zero_volume_streak} consecutive minute bars)"
            )
        timestamps.append(timestamp)
        previous_timestamp = timestamp

    history_days = (timestamps[-1] - timestamps[0]).total_seconds() / 86400
    if history_days < minimum_history_days:
        raise ValueError(
            f"production replay requires at least {minimum_history_days} days of history; "
            f"received {history_days:.1f} days"
        )
    return {
        "symbol": expected_symbol,
        "history_days": history_days,
        "bar_count": len(candles),
        "zero_volume_rows": zero_volume_rows,
        "gaps": gaps,
        "timezone": "Asia/Kolkata",
        "granularity": "1m",
    }


def prepare_production_candles(
    candles: List[Dict],
    ticker: str,
    expected_symbol: str,
    minimum_history_days: int = 183,
    sustained_zero_volume_bars: int = 5,
) -> tuple[List[Dict], Dict]:
    """Validate raw strict-mode data, then remove isolated zero-volume artifacts."""
    diagnostics = validate_production_data(
        candles,
        ticker,
        expected_symbol,
        minimum_history_days=minimum_history_days,
        sustained_zero_volume_bars=sustained_zero_volume_bars,
    )
    filtered = [candle for candle in candles if float(candle["volume"]) > 0]
    diagnostics["removed_zero_volume_rows"] = len(candles) - len(filtered)
    return filtered, diagnostics


def _context_before(
    contexts: Dict[str, List[Dict]], signal_time: Optional[datetime]
) -> Dict[str, List[Dict]]:
    if signal_time is None:
        return {}
    signal_timestamp = signal_time.timestamp()
    available = {}
    for symbol, bars in contexts.items():
        eligible = []
        for bar in reversed(bars):
            bar_time = _as_ist(bar.get("time", bar.get("date")))
            if bar_time is not None and bar_time.timestamp() <= signal_timestamp:
                eligible.append(bar)
                if len(eligible) == 100:
                    break
        available[symbol] = list(reversed(eligible))
    return available


def run_replay(
    ticker: str,
    candles: List[Dict],
    config: Dict,
    context_histories: Optional[Dict[str, List[Dict]]] = None,
    fee_bps_per_side: float = 0.0,
    slippage_bps_per_side: float = 0.0,
    signal_fn: Optional[Callable[[str, List[Dict]], TradingScore]] = None,
) -> BacktestResult:
    """Replay the strategy and shared accuracy filters without broker access."""
    contexts = context_histories or {}
    use_context = bool(config.get("use_market_context", True))
    accuracy_filters = AccuracyFilters(
        min_entry_score=int(config.get("min_entry_score", 75)),
        min_volatility_pct=float(config.get("min_volatility_pct", 0.05)),
        max_volatility_pct=float(config.get("max_volatility_pct", 5.0)),
    )

    def evaluate(symbol: str, history: List[Dict]) -> TradingScore:
        signal_time = _as_ist(history[-1].get("time", history[-1].get("date"))) if history else None
        score_function = signal_fn or score_market
        if signal_fn is not None:
            return score_function(symbol, history)
        available_contexts = _context_before(contexts, signal_time) if use_context else {}
        available_contexts = {
            name: bars
            for name, bars in available_contexts.items()
            if name.upper() != symbol.upper()
        }
        return score_function(
            symbol,
            history,
            ema_fast=int(config.get("ema_fast", 9)),
            ema_slow=int(config.get("ema_slow", 21)),
            rsi_period=int(config.get("rsi_period", 14)),
            context_histories=available_contexts or None,
            hard_context_filter=bool(config.get("hard_context_filter", True)),
            min_adx=float(config.get("min_adx", 18.0)),
            sideways_range_pct=float(config.get("sideways_range_pct", 1.0)),
            sideways_net_move_pct=float(config.get("sideways_net_move_pct", 1.0)),
            min_trend_strength=float(config.get("min_trend_strength", 0.02)),
            trend_momentum_bonus_threshold=float(
                config.get("trend_momentum_bonus_threshold", 0.02)
            ),
            signal_proximity_pct=float(config.get("signal_proximity_pct", 0.003)),
        )

    def entry_filter(
        symbol: str, decision: TradingScore, history: List[Dict]
    ) -> Optional[str]:
        if len(history) < 2:
            return "not_enough_bars_for_confirmation"
        now = _as_ist(history[-1].get("time", history[-1].get("date")))
        if now is None:
            return "missing_timestamp"
        if bool(config.get("late_window_enabled", True)):
            start = time.fromisoformat(str(config.get("late_window_start", "12:00")))
            end = time.fromisoformat(str(config.get("late_window_end", "13:00")))
            if start != end and (start <= now.time() < end if start < end else now.time() >= start or now.time() < end):
                return "late_window"

        allowed, reason = accuracy_filters.validate_entry_with_reason(
            symbol=symbol,
            signal=decision.signal,
            score=decision.score,
            history=history,
            current_bar=history[-1],
            previous_bar=history[-2],
            current_time=now.timestamp(),
            hour=now.hour,
            minute=now.minute,
        )
        return None if allowed else reason

    return run_backtest(
        ticker,
        candles,
        stop_loss_pct=float(config.get("stop_loss_pct", 0.75)),
        take_profit_pct=float(config.get("take_profit_pct", 1.5)),
        signal_fn=evaluate,
        entry_filter=entry_filter,
        fee_bps_per_side=fee_bps_per_side,
        slippage_bps_per_side=slippage_bps_per_side,
        market_close_time=str(config.get("market_close_time", "15:15")),
        flatten_on_session_change=True,
        max_trades_per_session=1,
        trailing_enabled=bool(config.get("trailing_enabled", True)),
        trailing_activation_ratio=float(config.get("trailing_activation_ratio", 0.5)),
        trailing_distance_ratio=float(config.get("trailing_distance_ratio", 0.25)),
        history_limit=50,
    )


def _summary(result: BacktestResult) -> Dict:
    returns = [trade.return_pct for trade in result.trades]
    equity = 1.0
    peak = 1.0
    maximum_drawdown = 0.0
    for trade_return in returns:
        equity *= 1.0 + trade_return / 100.0
        peak = max(peak, equity)
        if peak > 0:
            maximum_drawdown = max(maximum_drawdown, (peak - equity) / peak * 100.0)

    gains = sum(value for value in returns if value > 0)
    losses = abs(sum(value for value in returns if value < 0))
    return {
        "evaluated_bars": result.evaluated_bars,
        "signal_counts": result.signal_counts,
        "strategy_reason_counts": result.reason_counts,
        "entry_rejections": result.rejection_counts,
        "trade_count": len(result.trades),
        "win_rate_pct": result.win_rate_pct,
        "net_total_return_pct": (equity - 1.0) * 100.0 if returns else 0.0,
        "expectancy_pct_per_trade": sum(returns) / len(returns) if returns else None,
        "profit_factor": gains / losses if losses else None,
        "maximum_drawdown_pct": maximum_drawdown if returns else None,
        "trades": [asdict(trade) for trade in result.trades],
    }


def _zero_signal_diagnostics(result: BacktestResult) -> Dict:
    actionable = result.signal_counts.get("BUY", 0) + result.signal_counts.get("SELL", 0)
    if actionable:
        return {}
    diagnostics = ["no_entry_triggers"]
    if any("volume" in reason.lower() for reason in result.rejection_counts):
        diagnostics.append("volume_filter_too_strict")
    return {
        "zero_signal_diagnostics": diagnostics,
        "recommended_relaxations": [
            {"action": "relax_entry_proximity_pct", "amount": 0.2},
            {"action": "lower_min_volume", "amount": 50000},
        ],
    }


def _parse_context_arg(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("context must use SYMBOL=FILE")
    symbol, path = value.split("=", 1)
    if not symbol.strip() or not path.strip():
        raise argparse.ArgumentTypeError("context must use SYMBOL=FILE")
    return symbol.strip().upper(), path.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay strategy signals on local OHLCV data; never places orders.")
    parser.add_argument("data", help="CSV or Parquet with time, OHLC, and volume columns")
    parser.add_argument("--ticker", required=True, help="Instrument name used in the replay")
    parser.add_argument("--config", default="kite_config.json", help="Strategy config JSON; secrets are not used or printed")
    parser.add_argument("--context", action="append", type=_parse_context_arg, default=[], metavar="SYMBOL=FILE")
    parser.add_argument("--fee-bps-per-side", type=float, default=0.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=0.0)
    parser.add_argument(
        "--production-symbol",
        help="Require this exact exchange contract symbol and strict 1-minute production data checks",
    )
    parser.add_argument("--minimum-history-days", type=int, default=183)
    parser.add_argument("--sustained-zero-volume-bars", type=int, default=5)
    parser.add_argument("--output", help="Optional path for the JSON report")
    args = parser.parse_args()

    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        candles = load_candles(args.data)
        data_quality = None
        if args.production_symbol:
            candles, data_quality = prepare_production_candles(
                candles,
                ticker=args.ticker,
                expected_symbol=args.production_symbol,
                minimum_history_days=args.minimum_history_days,
                sustained_zero_volume_bars=args.sustained_zero_volume_bars,
            )
        contexts = {symbol: load_candles(path) for symbol, path in args.context}
        if len(candles) < 2:
            raise ValueError("at least two valid OHLCV candles are required")
        result = run_replay(
            args.ticker,
            candles,
            config,
            context_histories=contexts,
            fee_bps_per_side=args.fee_bps_per_side,
            slippage_bps_per_side=args.slippage_bps_per_side,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        parser.error(str(error))

    report = {
        "ticker": args.ticker,
        "data_file": str(Path(args.data)),
        "bars": len(candles),
        "first_bar": candles[0]["time"].isoformat(),
        "last_bar": candles[-1]["time"].isoformat(),
        "cost_assumptions_bps_per_side": {
            "fee": args.fee_bps_per_side,
            "slippage": args.slippage_bps_per_side,
        },
        "scope": "strategy, AccuracyFilters, one-entry-per-session rule, and simulated exits; excludes broker fills, option contract handling, news, and portfolio risk sizing",
        "warnings": [],
        "results": _summary(result),
    }
    if data_quality is not None:
        report["data_quality"] = data_quality
        report["production_validation"] = "passed"
        report.update(_zero_signal_diagnostics(result))
    zero_signal_failure = data_quality is not None and "zero_signal_diagnostics" in report
    if use_context := bool(config.get("use_market_context", True)):
        expected_contexts = {
            str(symbol).upper()
            for symbol in config.get(
                "benchmark_symbols",
                [config.get("benchmark_symbol", "NIFTY"), "BANKNIFTY"],
            )
        }
        expected_contexts.discard(args.ticker.upper())
        missing_contexts = sorted(expected_contexts.difference(contexts))
        if missing_contexts:
            report["warnings"].append(
                "Market context is enabled but these benchmark histories were not supplied: "
                + ", ".join(missing_contexts)
            )
    if args.fee_bps_per_side == 0 or args.slippage_bps_per_side == 0:
        report["warnings"].append("Set fee and slippage assumptions to realistic non-zero values before relying on returns.")

    serialized = json.dumps(report, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(serialized + "\n", encoding="utf-8")
        print(f"Replay report written to {args.output}")
    else:
        print(serialized)
    if zero_signal_failure:
        parser.error("production replay produced zero actionable BUY/SELL signals; see diagnostics")


if __name__ == "__main__":
    main()