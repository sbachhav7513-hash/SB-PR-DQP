from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .engine import score_market
from .index_history_export import _local_timestamp, _missing_minutes_by_session


IST = ZoneInfo("Asia/Kolkata")
PERCENTILES = (50, 60, 70, 80, 90, 95)
HORIZONS = (15, 30)


def load_index_candles(history_dir: Path, symbol: str) -> List[Dict]:
    candidates = sorted(Path(history_dir).rglob(f"underlyings__{symbol}.csv"))
    candidates += sorted(Path(history_dir).rglob(f"{symbol}.csv"))
    if not candidates:
        raise FileNotFoundError(
            f"No {symbol} CSV history found under {history_dir}"
        )

    candles_by_time = {}
    for path in dict.fromkeys(candidates):
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                timestamp_value = row.get("timestamp") or row.get("time")
                if not timestamp_value:
                    raise ValueError(f"{path} has no timestamp value")
                timestamp = _local_timestamp(datetime.fromisoformat(timestamp_value))
                if not 9 * 60 + 15 <= timestamp.hour * 60 + timestamp.minute < 15 * 60 + 30:
                    continue
                try:
                    candle = {
                        "time": timestamp,
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(float(row.get("volume") or 0)),
                    }
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(f"{path} has invalid OHLCV values") from error
                if (
                    not all(math.isfinite(candle[field]) for field in ("open", "high", "low", "close"))
                    or min(candle["open"], candle["high"], candle["low"], candle["close"]) <= 0
                ):
                    raise ValueError(f"{path} has non-finite or non-positive OHLCV")
                candles_by_time[timestamp] = candle
    return [candles_by_time[timestamp] for timestamp in sorted(candles_by_time)]


def _bar_measurements(candles: List[Dict]) -> List[Dict]:
    candles_by_day: Dict[date, List[Dict]] = defaultdict(list)
    for candle in candles:
        timestamp = _local_timestamp(candle["time"])
        candles_by_day[timestamp.date()].append(
            {"time": timestamp, "close": float(candle["close"])}
        )

    measurements = []
    for session_date, bars in sorted(candles_by_day.items()):
        bars.sort(key=lambda item: item["time"])
        closes_by_time = {bar["time"]: bar["close"] for bar in bars}
        for index in range(19, len(bars)):
            bar = bars[index]
            reference = bars[index - 19]["close"]
            if reference <= 0:
                continue
            move = bar["close"] - reference
            future_closes = {
                horizon: closes_by_time.get(
                    bar["time"] + timedelta(minutes=horizon)
                )
                for horizon in HORIZONS
            }
            measurements.append(
                {
                    "day": session_date,
                    "time": bar["time"],
                    "spot": bar["close"],
                    "strength": abs(move) / reference,
                    "direction": 1 if move > 0 else -1 if move < 0 else 0,
                    "future": future_closes,
                    "forward": {
                        horizon: (
                            future_closes[horizon] / bar["close"] - 1
                            if future_closes[horizon] is not None
                            else None
                        )
                        for horizon in HORIZONS
                    },
                }
            )
    return measurements


def _threshold_signals(
    measurements: List[Dict], days: Iterable[date], threshold: float
) -> List[Dict]:
    allowed_days = set(days)
    selected = []
    last_signal_by_direction = {}
    for item in measurements:
        if item["day"] not in allowed_days or item["direction"] == 0:
            continue
        if item["strength"] <= threshold:
            continue
        previous = last_signal_by_direction.get(item["direction"])
        if previous is not None and item["time"] - previous < timedelta(minutes=15):
            continue
        selected.append(item)
        last_signal_by_direction[item["direction"]] = item["time"]
    return selected


def _score_base_candidates(
    candles: List[Dict],
    measurements: List[Dict],
    base_threshold: float,
    ticker: str,
    config: Dict,
) -> List[Dict]:
    measurements_by_time = {item["time"]: item for item in measurements}
    candles_by_day: Dict[date, List[Dict]] = defaultdict(list)
    for candle in candles:
        timestamp = _local_timestamp(candle["time"])
        candles_by_day[timestamp.date()].append({**candle, "time": timestamp})

    candidates = []
    for session_date, bars in sorted(candles_by_day.items()):
        bars.sort(key=lambda item: item["time"])
        for index in range(29, len(bars)):
            measurement = measurements_by_time.get(bars[index]["time"])
            if measurement is None or measurement["strength"] <= base_threshold:
                continue
            history = bars[max(0, index - 99):index + 1]
            result = score_market(
                ticker,
                history,
                ema_fast=int(config.get("ema_fast", 9)),
                ema_slow=int(config.get("ema_slow", 21)),
                rsi_period=int(config.get("rsi_period", 14)),
                hard_context_filter=bool(config.get("hard_context_filter", True)),
                min_adx=float(config.get("min_adx", 18.0)),
                sideways_range_pct=float(config.get("sideways_range_pct", 1.0)),
                sideways_net_move_pct=float(
                    config.get("sideways_net_move_pct", 1.0)
                ),
                sideways_er_threshold=None,
                sideways_range_multiple=float(
                    config.get("sideways_range_multiple", 0.6)
                ),
                sideways_overrides=config.get("sideways_overrides"),
                sideways_symbol=ticker,
                regime_hard_filter_overrides={ticker: False},
                min_trend_strength=base_threshold,
                trend_momentum_bonus_threshold=base_threshold,
                signal_proximity_pct=float(
                    config.get("signal_proximity_pct", 0.005)
                ),
                allow_trend_continuation=bool(
                    config.get("allow_trend_continuation", False)
                ),
                rsi_buy_block_above=float(
                    config.get("rsi_buy_block_above", 80.0)
                ),
                rsi_sell_block_below=float(
                    config.get("rsi_sell_block_below", 25.0)
                ),
            )
            if result.signal in {"BUY", "SELL"}:
                candidates.append(
                    {
                        **measurement,
                        "direction": 1 if result.signal == "BUY" else -1,
                    }
                )
    return candidates


def _horizon_statistics(
    signals: List[Dict],
    horizon: int,
    bootstrap_iterations: int,
    seed: int,
) -> Dict:
    eligible = [
        item for item in signals if item["forward"][horizon] is not None
    ]
    if not eligible:
        return {
            "n": 0,
            "mean": None,
            "hit_rate": None,
            "random_mean": None,
            "random_hit_rate": None,
            "delta_ci": (None, None),
        }

    by_day: Dict[date, List[Dict]] = defaultdict(list)
    for item in eligible:
        by_day[item["day"]].append(item)

    rng = random.Random(seed)
    daily_samples = []
    all_signal = []
    all_random = []
    for day in sorted(by_day):
        day_signals = by_day[day]
        labels = [item["direction"] for item in day_signals]
        rng.shuffle(labels)
        signal_values = [
            item["direction"] * item["forward"][horizon]
            for item in day_signals
        ]
        random_values = [
            label * item["forward"][horizon]
            for label, item in zip(labels, day_signals)
        ]
        daily_samples.append((signal_values, random_values))
        all_signal.extend(signal_values)
        all_random.extend(random_values)

    day_count = len(daily_samples)
    if day_count:
        signal_day_sums = np.array(
            [sum(sample[0]) for sample in daily_samples], dtype=np.float64
        )
        random_day_sums = np.array(
            [sum(sample[1]) for sample in daily_samples], dtype=np.float64
        )
        day_signal_counts = np.array(
            [len(sample[0]) for sample in daily_samples], dtype=np.int64
        )
        bootstrap_rng = np.random.default_rng(seed)
        sample_indices = bootstrap_rng.integers(
            0, day_count, size=(bootstrap_iterations, day_count)
        )
        sample_counts = day_signal_counts[sample_indices].sum(axis=1)
        differences = (
            signal_day_sums[sample_indices].sum(axis=1) / sample_counts
            - random_day_sums[sample_indices].sum(axis=1) / sample_counts
        )
        interval = tuple(
            float(value) for value in np.percentile(differences, [2.5, 97.5])
        )
    else:
        interval = (None, None)
    return {
        "n": len(eligible),
        "mean": sum(all_signal) / len(all_signal),
        "hit_rate": sum(value > 0 for value in all_signal) / len(all_signal),
        "random_mean": sum(all_random) / len(all_random),
        "random_hit_rate": sum(value > 0 for value in all_random) / len(all_random),
        "delta_ci": interval,
    }


def study_underlying(
    candles: List[Dict],
    ticker: str = "NIFTY",
    config: Optional[Dict] = None,
    percentiles: Iterable[int] = PERCENTILES,
    train_fraction: float = 0.7,
    bootstrap_iterations: int = 2000,
    seed: int = 20261124,
) -> Dict:
    if not 0 < train_fraction < 1:
        raise ValueError("train fraction must be strictly between zero and one")
    if bootstrap_iterations < 1:
        raise ValueError("bootstrap iterations must be positive")
    measurements = _bar_measurements(candles)
    days = sorted({item["day"] for item in measurements})
    split_index = int(len(days) * train_fraction)
    if split_index < 1 or split_index >= len(days):
        raise ValueError("history must contain enough sessions for train and OOS splits")
    train_days = days[:split_index]
    oos_days = days[split_index:]
    train_strengths = [
        item["strength"] for item in measurements if item["day"] in set(train_days)
    ]
    if not train_strengths:
        raise ValueError("no valid 20-bar trend strength values in training sessions")

    thresholds = {
        percentile: float(np.percentile(train_strengths, percentile))
        for percentile in percentiles
    }
    base_candidates = _score_base_candidates(
        candles,
        measurements,
        min(thresholds.values()),
        ticker,
        config or {},
    )
    results = {"thresholds": thresholds, "train_days": train_days, "oos_days": oos_days}
    for period, period_days in (("train", train_days), ("oos", oos_days)):
        table = []
        for percentile, threshold in thresholds.items():
            signals = _threshold_signals(
                base_candidates, period_days, threshold
            )
            row = {
                "percentile": percentile,
                "threshold": threshold,
                "signals_per_day": len(signals) / len(period_days),
                "n_signals": len(signals),
            }
            for horizon in HORIZONS:
                row[horizon] = _horizon_statistics(
                    signals,
                    horizon,
                    bootstrap_iterations,
                    seed + percentile * 100 + horizon,
                )
            table.append(row)
        results[period] = table
    return results


def _number(row: Dict, *fields: str) -> Optional[float]:
    for field in fields:
        value = row.get(field)
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(result) and result > 0:
            return result
    return None


def _fees_rupees(row: Dict) -> Optional[float]:
    value = _number(row, "fees_rupees")
    if value is not None:
        return value
    raw = row.get("fees")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    return _number(raw, "total_fees") if isinstance(raw, dict) else None


def paper_trade_costs(trades: Iterable[Dict]) -> Dict[str, Dict]:
    values = {"NIFTY": [], "BANKNIFTY": []}
    coverage = {
        symbol: {"closed_trades": 0, "modeled_fees": 0, "quoted_round_trips": 0}
        for symbol in values
    }
    for row in trades:
        if str(row.get("status", "")).lower() != "closed":
            continue
        searchable = " ".join(
            str(row.get(key) or "").upper()
            for key in ("ticker", "trading_symbol", "contract_id", "tier")
        )
        symbol = next(
            (name for name in ("BANKNIFTY", "NIFTY") if name in searchable),
            None,
        )
        if symbol is None:
            continue
        coverage[symbol]["closed_trades"] += 1
        fees = _fees_rupees(row)
        if fees is None:
            continue
        coverage[symbol]["modeled_fees"] += 1
        entry = _number(
            row, "fill_premium", "entry", "entry_quote_ltp",
            "paper_entry_ltp", "entry_price",
        )
        quantity = _number(row, "entry_quantity", "quantity")
        entry_bid = _number(row, "fill_bid", "paper_entry_bid", "entry_quote_bid")
        entry_ask = _number(row, "fill_ask", "paper_entry_ask", "entry_quote_ask")
        exit_bid = _number(row, "paper_exit_bid", "exit_bid")
        exit_ask = _number(row, "paper_exit_ask", "exit_ask")
        if (
            entry is None
            or quantity is None
            or entry_bid is None
            or entry_ask is None
            or exit_bid is None
            or exit_ask is None
            or entry_ask < entry_bid
            or exit_ask < exit_bid
        ):
            continue

        coverage[symbol]["quoted_round_trips"] += 1
        round_trip_spread = (
            (entry_ask - entry_bid) + (exit_ask - exit_bid)
        ) * 0.5 * quantity
        values[symbol].append(
            100.0 * (fees + round_trip_spread) / (entry * quantity)
        )

    return {
        symbol: {
            **coverage[symbol],
            "mean_pct": (
                sum(values[symbol]) / len(values[symbol])
                if values[symbol]
                else None
            ),
            "median_pct": (
                float(np.median(values[symbol])) if values[symbol] else None
            ),
            "trades_used": len(values[symbol]),
        }
        for symbol in values
    }


def _format_percent(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{100 * value:.3f}%"


def _format_table(rows: List[Dict]) -> str:
    headers = [
        "Train pctl",
        "Threshold",
        "Signals/day",
        "n(+15/+30)",
        "Signal mean +15",
        "Signal hit +15",
        "Random mean +15",
        "Random hit +15",
        "Delta +15 95% CI",
        "Signal mean +30",
        "Signal hit +30",
        "Random mean +30",
        "Random hit +30",
        "Delta +30 95% CI",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        stats15, stats30 = row[15], row[30]
        ci15, ci30 = stats15["delta_ci"], stats30["delta_ci"]
        lines.append(
            "| "
            + " | ".join(
                [
                    f"p{row['percentile']}",
                    _format_percent(row["threshold"]),
                    f"{row['signals_per_day']:.2f}",
                    f"{stats15['n']}/{stats30['n']}",
                    _format_percent(stats15["mean"]),
                    _format_percent(stats15["hit_rate"]),
                    _format_percent(stats15["random_mean"]),
                    _format_percent(stats15["random_hit_rate"]),
                    f"[{_format_percent(ci15[0])}, {_format_percent(ci15[1])}]",
                    _format_percent(stats30["mean"]),
                    _format_percent(stats30["hit_rate"]),
                    _format_percent(stats30["random_mean"]),
                    _format_percent(stats30["random_hit_rate"]),
                    f"[{_format_percent(ci30[0])}, {_format_percent(ci30[1])}]",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def build_report(
    histories: Dict[str, List[Dict]],
    costs: Dict[str, Dict],
    source_label: str,
    config: Optional[Dict] = None,
    bootstrap_iterations: int = 2000,
    retrieval_note: Optional[str] = None,
) -> str:
    sections = [
        "# Index Trend-Strength Edge Study",
        "",
        f"History source: {source_label}. The regime gate is not applied.",
        "",
    ]
    if retrieval_note:
        sections.extend(["## Retrieval status", "", retrieval_note, ""])
    sections.extend(
        [
            "## History coverage",
            "",
            "| Underlying | First date | Last date | Sessions | Bars | Days with missing minutes |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for symbol in ("NIFTY", "BANKNIFTY"):
        candles = histories[symbol]
        session_days = sorted({candle["time"].date() for candle in candles})
        missing = _missing_minutes_by_session(candles)
        missing_text = (
            ", ".join(f"{day} ({len(minutes)})" for day, minutes in missing.items())
            if missing
            else "none"
        )
        sections.append(
            "| "
            + " | ".join(
                [
                    symbol,
                    session_days[0].isoformat() if session_days else "n/a",
                    session_days[-1].isoformat() if session_days else "n/a",
                    str(len(session_days)),
                    str(len(candles)),
                    missing_text,
                ]
            )
            + " |"
        )

    sections.extend(
        [
            "",
            "Missing-minute counts compare observed timestamps with 375 regular-session "
            "minute slots (09:15-15:29). Shortened/special trading sessions are also "
            "listed as incomplete; calendar dates with no bars are not classified as "
            "holidays or missing sessions.",
        ]
    )
    sections.extend(
        [
            "",
            "## Method",
            "",
            f"Thresholds are the training-period p50/p60/p70/p80/p90/p95 of "
            "absolute close-to-close 20-bar strength. Days are split chronologically "
            "70% train / 30% OOS; thresholds are learned only from train days. "
            "Signals are produced by score_market using the active paper scoring "
            "configuration, with the regime hard gate disabled; threshold levels are "
            "then applied to the signal set. A 15-minute same-direction cooldown is "
            "applied. Forward returns use the exact +15/+30-minute "
            "close on the same session. Random controls shuffle signs within each day "
            "while preserving that day's BUY/SELL ratio. CIs resample trading days "
            f"({bootstrap_iterations} bootstrap replicates over active signal days); "
            "differences are signal "
            "mean minus random mean. Returns and CI bounds are percentages.",
            "",
            "## Paper option round-trip costs",
            "",
            "Spread cost is half the observed entry spread plus half the observed exit "
            "spread, multiplied by filled quantity; modeled journal fees are added and "
            "divided by entry premium times quantity. Only closed trades with fee and "
            "consistent entry/exit bid-ask snapshots are included.",
            "The edge returns are underlying spot returns, while the cost percentage "
            "uses option premium; these are a friction-scale comparison, not direct "
            "option P&L or a break-even calculation.",
            "",
            "| Underlying | Average cost (% entry premium) | Median | Trades used / closed | Modeled-fee coverage | Quoted round-trip coverage |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for symbol in ("NIFTY", "BANKNIFTY"):
        item = costs[symbol]
        sections.append(
            f"| {symbol} | "
            f"{item['mean_pct']:.3f}% | {item['median_pct']:.3f}% | "
            f"{item['trades_used']} / {item['closed_trades']} | "
            f"{item['modeled_fees']} / {item['closed_trades']} | "
            f"{item['quoted_round_trips']} / {item['closed_trades']} |"
            if item["mean_pct"] is not None
            else f"| {symbol} | n/a | n/a | 0 / {item['closed_trades']} | "
            f"{item['modeled_fees']} / {item['closed_trades']} | "
            f"{item['quoted_round_trips']} / {item['closed_trades']} |"
        )

    for symbol in ("NIFTY", "BANKNIFTY"):
        study = study_underlying(
            histories[symbol],
            ticker=symbol,
            config=config,
            bootstrap_iterations=bootstrap_iterations,
        )
        sections.extend(
            [
                "",
                f"## {symbol}",
                "",
                f"Training: {study['train_days'][0]} to {study['train_days'][-1]} "
                f"({len(study['train_days'])} sessions).",
                "",
                _format_table(study["train"]),
                "",
                f"Out of sample: {study['oos_days'][0]} to "
                f"{study['oos_days'][-1]} ({len(study['oos_days'])} sessions).",
                "",
                _format_table(study["oos"]),
            ]
        )
    return "\n".join(sections) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run an offline index trend edge study.")
    parser.add_argument("--history-dir", type=Path, default=Path("historical_data"))
    parser.add_argument("--paper-dir", type=Path, default=Path("paper_trading_data"))
    parser.add_argument("--config", type=Path, default=Path("kite_config.json"))
    parser.add_argument(
        "--source-label",
        default="KiteHistoricalProvider one-minute CSV export",
    )
    parser.add_argument("--retrieval-note")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/INDEX_TREND_STRENGTH_EDGE_STUDY.md"),
    )
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    args = parser.parse_args(argv)
    histories = {
        symbol: load_index_candles(args.history_dir, symbol)
        for symbol in ("NIFTY", "BANKNIFTY")
    }
    config = json.loads(args.config.read_text(encoding="utf-8"))
    trades = []
    for path in sorted(args.paper_dir.rglob("trades.parquet")):
        trades.extend(pd.read_parquet(path).to_dict("records"))
    costs = paper_trade_costs(trades)
    report = build_report(
        histories,
        costs,
        args.source_label,
        config=config,
        bootstrap_iterations=args.bootstrap_iterations,
        retrieval_note=args.retrieval_note,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(f"Wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
