from __future__ import annotations

import itertools
import json
import math
import sys
from collections import OrderedDict
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_bot.paper_costs import calculate_order_fees


OPTION_DIR = ROOT / "tmp" / "optdata"
INDEX_DIR = ROOT / "tmp" / "longhist" / "data"
FORECAST_PATH = ROOT / "tmp" / "longhist" / "unseen_study" / "range_forecast_oos.csv"
CONFIG_PATH = ROOT / "kite_config.json"
OUTPUT_DIR = ROOT / "reports" / "nifty_iron_condor_fixed_grid"

CAPITAL = 100_000.0
LOT_SIZE = 65
TICK_SIZE = 0.05
MIN_VOLUME = 200.0
MIN_OPEN_INTEREST = 400.0
BOOTSTRAP_REPLICATES = 5000
BOOTSTRAP_MEAN_BLOCK_WEEKS = 4.0
BASE_SEED = 681_220

PERIODS = {
    "DEVELOP": ("2021-11-22", "2024-12-31"),
    "VALIDATE": ("2025-01-01", "2025-12-31"),
    "CONFIRM": ("2026-01-01", "2026-11-20"),
}


def _read_options() -> pd.DataFrame:
    frames = []
    for path in sorted(OPTION_DIR.glob("NIFTY_options_*.parquet")):
        frame = pd.read_parquet(path)
        frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
        frame["expiry"] = pd.to_datetime(frame["expiry"]).dt.strftime("%Y-%m-%d")
        frames.append(frame)
    if not frames:
        raise FileNotFoundError(f"No NIFTY option parquet files in {OPTION_DIR}")
    options = pd.concat(frames, ignore_index=True)
    keys = ["date", "expiry", "strike", "option_type"]
    if options.duplicated(keys).any():
        raise ValueError("Duplicate date/expiry/strike/type rows in option data")
    return options.set_index(keys).sort_index()


def _read_minute_data() -> tuple[dict[str, dict[str, Any]], dict[str, float]]:
    nifty = pd.read_parquet(INDEX_DIR / "NIFTY_5y.parquet")
    nifty["date"] = nifty["timestamp"].dt.strftime("%Y-%m-%d")
    nifty_daily: dict[str, dict[str, Any]] = {}
    for day, group in nifty.groupby("date", sort=True):
        nifty_daily[day] = {
            "high": float(group["high"].max()),
            "low": float(group["low"].min()),
            "close": float(group.iloc[-1]["close"]),
        }

    vix = pd.read_parquet(INDEX_DIR / "INDIA_VIX_5y.parquet")
    vix["date"] = vix["timestamp"].dt.strftime("%Y-%m-%d")
    vix_open = {
        day: float(group.iloc[0]["open"])
        for day, group in vix.groupby("date", sort=True)
    }
    return nifty_daily, vix_open


def _read_forecast(end_date: str | None = None) -> dict[str, bool]:
    forecast = pd.read_csv(FORECAST_PATH)
    forecast = forecast.loc[forecast["target"] == "day_range"].copy()
    forecast["date"] = pd.to_datetime(forecast["date"]).dt.strftime("%Y-%m-%d")
    if end_date is not None:
        forecast = forecast.loc[forecast["date"] <= end_date]
    if forecast["date"].duplicated().any():
        raise ValueError("The fixed day_range forecast has duplicate dates")
    result = {}
    for row in forecast.itertuples(index=False):
        value = row.predicted_high_range
        if isinstance(value, str):
            value = value.strip().lower() in {"true", "1", "yes"}
        result[row.date] = bool(value)
    return result


def _entry_row(exp_chain: pd.DataFrame, strike: float, option_type: str):
    key = (float(strike), option_type)
    try:
        return exp_chain.loc[key]
    except KeyError:
        return None


def _mark_price(exp_chain: pd.DataFrame, strike: float, option_type: str):
    row = _entry_row(exp_chain, strike, option_type)
    if row is None:
        return None
    value = float(row["close"])
    return value if math.isfinite(value) and value > 0 else None


def _fill_price(mark: float, side: str, slippage: float) -> float:
    if side == "BUY":
        return mark + slippage
    return max(0.0, mark - slippage)


def _fees(orders: list[dict[str, Any]], charge_model: dict[str, Any]) -> float:
    fee_orders = [
        {
            "side": order["side"],
            "price": max(0.01, float(order["price"])),
            "quantity": float(order["quantity"]),
        }
        for order in orders
    ]
    return float(calculate_order_fees(fee_orders, charge_model)["total_fees"])


def _make_variants() -> list[dict[str, Any]]:
    variants = []
    for width, distance, dte_bucket, exit_policy, day_filter in itertools.product(
        (100, 200),
        (1.0, 1.25, 1.5),
        ((2, 3), (5, 7)),
        ("HOLD", "50PCT"),
        ("ALL", "NOT_HIGH"),
    ):
        distance_id = str(distance).replace(".", "p")
        variant_id = (
            f"IC_W{width}_D{distance_id}_DTE{dte_bucket[0]}-{dte_bucket[1]}_"
            f"{exit_policy}_{day_filter}"
        )
        variants.append(
            {
                "variant_id": variant_id,
                "width": width,
                "distance": distance,
                "dte_low": dte_bucket[0],
                "dte_high": dte_bucket[1],
                "exit_policy": exit_policy,
                "day_filter": day_filter,
            }
        )
    if len(variants) != 48:
        raise AssertionError(f"Expected 48 variants, found {len(variants)}")
    return variants


def _get_templates(
    variants: list[dict[str, Any]],
    option_index: pd.DataFrame,
    nifty_daily: dict[str, dict[str, Any]],
    vix_open: dict[str, float],
    forecast: dict[str, bool],
    entry_start: str,
    entry_end: str,
) -> tuple[dict[str, list[dict[str, Any]]], Counter]:
    option_dates = sorted(option_index.index.get_level_values("date").unique())
    option_dates = [
        day for day in option_dates if entry_start <= day <= entry_end
    ]
    expiries_by_date: dict[str, list[str]] = {}
    for day in option_dates:
        day_index = option_index.xs(day, level="date")
        expiries_by_date[day] = sorted(
            day_index.index.get_level_values("expiry").unique()
        )

    day_cache: dict[str, pd.DataFrame] = {}

    def day_chain(day: str) -> pd.DataFrame:
        if day not in day_cache:
            day_cache[day] = option_index.xs(day, level="date")
        return day_cache[day]

    candidates: dict[str, list[dict[str, Any]]] = {
        variant["variant_id"]: [] for variant in variants
    }
    skipped = Counter()
    for variant in variants:
        for entry_date in option_dates:
            if variant["day_filter"] == "NOT_HIGH":
                if entry_date not in forecast:
                    skipped["missing_forecast_sessions"] += 1
                    continue
                if forecast[entry_date]:
                    continue
            if entry_date not in nifty_daily or entry_date not in vix_open:
                skipped["missing_intraday_or_vix"] += 1
                continue
            expiries = [
                expiry
                for expiry in expiries_by_date[entry_date]
                if expiry > entry_date
            ]
            if not expiries:
                skipped["no_future_expiry"] += 1
                continue
            expiry = expiries[0]
            dte = (pd.Timestamp(expiry) - pd.Timestamp(entry_date)).days
            if not (variant["dte_low"] <= dte <= variant["dte_high"]):
                continue
            chain = day_chain(entry_date)
            exp_chain = chain.xs(expiry, level="expiry")
            spot_row = chain.iloc[0]
            spot = float(spot_row["underlying_close"])
            vix_value = float(vix_open[entry_date])
            if not math.isfinite(spot) or spot <= 0 or not math.isfinite(vix_value):
                skipped["invalid_spot_or_vix"] += 1
                continue
            sigma = (vix_value / 100.0) * math.sqrt(dte / 365.0) * spot
            call_strikes = np.asarray(
                exp_chain.xs("CE", level="option_type").index, dtype=float
            )
            put_strikes = np.asarray(
                exp_chain.xs("PE", level="option_type").index, dtype=float
            )
            call_candidates = call_strikes[call_strikes >= spot]
            put_candidates = put_strikes[put_strikes <= spot]
            if len(call_candidates) == 0 or len(put_candidates) == 0:
                skipped["no_otm_strike"] += 1
                continue
            call_target = spot + variant["distance"] * sigma
            put_target = spot - variant["distance"] * sigma
            short_call = float(
                call_candidates[np.argmin(np.abs(call_candidates - call_target))]
            )
            short_put = float(
                put_candidates[np.argmin(np.abs(put_candidates - put_target))]
            )
            legs = [
                (short_call, "CE", "SELL"),
                (short_call + variant["width"], "CE", "BUY"),
                (short_put, "PE", "SELL"),
                (short_put - variant["width"], "PE", "BUY"),
            ]
            rows = [
                _entry_row(exp_chain, strike, opt_type)
                for strike, opt_type, _ in legs
            ]
            if any(row is None for row in rows):
                skipped["missing_wing_contract"] += 1
                continue
            if any(
                not math.isfinite(float(row["volume"]))
                or not math.isfinite(float(row["open_interest"]))
                or float(row["volume"]) < MIN_VOLUME
                or float(row["open_interest"]) < MIN_OPEN_INTEREST
                for row in rows
            ):
                skipped["illiquid_leg"] += 1
                continue
            prices = [float(row["close"]) for row in rows]
            if any(not math.isfinite(price) or price <= 0 for price in prices):
                skipped["invalid_entry_close"] += 1
                continue
            template = {
                "entry_date": entry_date,
                "expiry": expiry,
                "dte": dte,
                "spot": spot,
                "vix_open": vix_value,
                "sigma": sigma,
                "short_call": short_call,
                "long_call": short_call + variant["width"],
                "short_put": short_put,
                "long_put": short_put - variant["width"],
                "legs": [
                    {
                        "strike": strike,
                        "option_type": option_type,
                        "side": side,
                        "entry_close": price,
                    }
                    for (strike, option_type, side), price in zip(legs, prices)
                ],
            }
            candidates[variant["variant_id"]].append(template)
    skipped["option_sessions"] = len(option_dates)
    skipped["sessions_with_forecast"] = sum(day in forecast for day in option_dates)
    skipped["sessions_without_forecast"] = sum(day not in forecast for day in option_dates)
    skipped["nifty_dates"] = len(nifty_daily)
    skipped["vix_dates"] = len(vix_open)
    return candidates, skipped


def _simulate(
    template: dict[str, Any],
    variant: dict[str, Any],
    option_index: pd.DataFrame,
    option_dates: pd.Index,
    day_cache: OrderedDict,
    nifty_daily: dict[str, dict[str, Any]],
    charge_model: dict[str, Any],
    slippage_multiple: int,
    data_end: str,
) -> dict[str, Any] | None:
    slippage = TICK_SIZE * slippage_multiple
    entry_orders = []
    entry_prices = []
    for leg in template["legs"]:
        fill = _fill_price(leg["entry_close"], leg["side"], slippage)
        entry_prices.append(fill)
        entry_orders.append(
            {"side": leg["side"], "price": fill, "quantity": LOT_SIZE}
        )
    credit = entry_prices[0] + entry_prices[2] - entry_prices[1] - entry_prices[3]
    if not math.isfinite(credit) or credit <= 0 or credit >= variant["width"]:
        return None
    max_loss = (variant["width"] - credit) * LOT_SIZE
    entry_fees = _fees(entry_orders, charge_model)

    start_index = option_dates.searchsorted(template["entry_date"], side="right")
    end_date = min(template["expiry"], data_end)
    expiry_date = template["expiry"]
    trade_days = []
    for day in option_dates[start_index:]:
        if day > end_date:
            break
        trade_days.append(day)
    if not trade_days or trade_days[-1] < expiry_date:
        return None

    def day_chain(day: str) -> pd.DataFrame:
        if day not in day_cache:
            day_cache[day] = option_index.xs(day, level="date")
            if len(day_cache) > 40:
                day_cache.popitem(last=False)
        else:
            day_cache.move_to_end(day)
        return day_cache[day]

    standard_pnl = None
    standard_exit_date = None
    exit_reason = None
    touch_date = None
    stress_pnl = None
    stress_exit_date = None
    strikes = [leg["strike"] for leg in template["legs"]]
    option_types = [leg["option_type"] for leg in template["legs"]]
    sides = [leg["side"] for leg in template["legs"]]

    for day in trade_days:
        bars = nifty_daily.get(day)
        if touch_date is None and bars is not None:
            if bars["high"] >= template["short_call"] or bars["low"] <= template["short_put"]:
                touch_date = day
                stop_marks = [price * 2.0 for price in entry_prices]
                stop_fills = [
                    _fill_price(mark, "BUY" if side == "SELL" else "SELL", slippage)
                    for mark, side in zip(stop_marks, sides)
                ]
                stop_debit = stop_fills[0] + stop_fills[2] - stop_fills[1] - stop_fills[3]
                stop_orders = [
                    {
                        "side": "BUY" if side == "SELL" else "SELL",
                        "price": fill,
                        "quantity": LOT_SIZE,
                    }
                    for side, fill in zip(sides, stop_fills)
                ]
                stress_pnl = (
                    (credit - stop_debit) * LOT_SIZE
                    - entry_fees
                    - _fees(stop_orders, charge_model)
                )
                stress_exit_date = day

        chain = day_chain(day)
        try:
            exp_chain = chain.xs(expiry_date, level="expiry")
        except KeyError:
            exp_chain = pd.DataFrame()
        marks = [
            _mark_price(exp_chain, strike, option_type)
            for strike, option_type in zip(strikes, option_types)
        ]
        if all(mark is not None for mark in marks):
            close_debit = marks[0] + marks[2] - marks[1] - marks[3]
            if variant["exit_policy"] == "50PCT":
                if close_debit <= credit * 0.5:
                    exit_reason = "50pct_credit"
            if exit_reason is None and close_debit >= credit * 2.0:
                exit_reason = "2x_credit_stop"
            if exit_reason is not None:
                close_sides = ["BUY" if side == "SELL" else "SELL" for side in sides]
                close_fills = [
                    _fill_price(mark, side, slippage)
                    for mark, side in zip(marks, close_sides)
                ]
                close_debit_filled = (
                    close_fills[0] + close_fills[2] - close_fills[1] - close_fills[3]
                )
                close_orders = [
                    {"side": side, "price": fill, "quantity": LOT_SIZE}
                    for side, fill in zip(close_sides, close_fills)
                ]
                standard_pnl = (
                    (credit - close_debit_filled) * LOT_SIZE
                    - entry_fees
                    - _fees(close_orders, charge_model)
                )
                standard_exit_date = day
                break

        if day == expiry_date:
            settlement_spot = bars["close"] if bars else float(chain.iloc[0]["underlying_close"])
            intrinsic = []
            for strike, option_type in zip(strikes, option_types):
                if option_type == "CE":
                    intrinsic.append(max(0.0, settlement_spot - strike))
                else:
                    intrinsic.append(max(0.0, strike - settlement_spot))
            expiry_debit = intrinsic[0] + intrinsic[2] - intrinsic[1] - intrinsic[3]
            exercise_stt = (
                sum(value for value in intrinsic if value > 0)
                * LOT_SIZE
                * float(charge_model["stt_sell_rate"])
            )
            standard_pnl = (credit - expiry_debit) * LOT_SIZE - entry_fees - exercise_stt
            standard_exit_date = day
            exit_reason = "expiry_settlement"
            if touch_date is None:
                stress_pnl = standard_pnl
                stress_exit_date = day
            break

    if standard_pnl is None or standard_exit_date is None:
        return None
    if stress_pnl is None:
        stress_pnl = standard_pnl
        stress_exit_date = standard_exit_date
    return {
        **template,
        "variant_id": variant["variant_id"],
        "slippage_multiple": slippage_multiple,
        "credit_points": credit,
        "max_loss_rupees": max_loss,
        "entry_fees_rupees": entry_fees,
        "pnl_rupees": standard_pnl,
        "exit_date": standard_exit_date,
        "exit_reason": exit_reason,
        "intraday_short_touch": touch_date is not None,
        "first_touch_date": touch_date,
        "stress_pnl_rupees": stress_pnl,
        "stress_exit_date": stress_exit_date,
    }


def _metrics(frame: pd.DataFrame, pnl_column: str) -> dict[str, Any]:
    if frame.empty:
        return {
            "trade_count": 0,
            "total_net_pnl_rupees": 0.0,
            "net_expectancy_rupees": float("nan"),
            "mean_pnl_pct_max_loss": float("nan"),
            "win_rate_pct": float("nan"),
            "profit_factor": float("nan"),
            "worst_trade_rupees": float("nan"),
            "worst_month_rupees": float("nan"),
            "worst_month_pct_capital": float("nan"),
            "max_drawdown_rupees": float("nan"),
            "max_drawdown_pct_capital": float("nan"),
            "cvar5_rupees": float("nan"),
            "longest_losing_streak": 0,
        }
    pnl = frame[pnl_column].astype(float)
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    month_pnl = frame.assign(
        month=pd.to_datetime(frame["exit_date"]).dt.to_period("M")
    ).groupby("month")[pnl_column].sum()
    daily = frame.groupby("exit_date")[pnl_column].sum().sort_index()
    equity = CAPITAL + daily.cumsum()
    peaks = np.maximum.accumulate(np.r_[CAPITAL, equity.to_numpy()])[1:]
    drawdowns = equity.to_numpy() - peaks
    ordered = frame.sort_values(["entry_date", "exit_date"])
    longest = current = 0
    for value in ordered[pnl_column]:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    tail_count = max(1, int(math.ceil(len(pnl) * 0.05)))
    cvar = float(pnl.nsmallest(tail_count).mean())
    return {
        "trade_count": int(len(frame)),
        "total_net_pnl_rupees": float(pnl.sum()),
        "net_expectancy_rupees": float(pnl.mean()),
        "mean_pnl_pct_max_loss": float((pnl / frame["max_loss_rupees"]).mean() * 100.0),
        "win_rate_pct": float((pnl > 0).mean() * 100.0),
        "profit_factor": float(wins / losses) if losses > 0 else float("inf"),
        "worst_trade_rupees": float(pnl.min()),
        "worst_month_rupees": float(month_pnl.min()),
        "worst_month_pct_capital": float(month_pnl.min() / CAPITAL * 100.0),
        "max_drawdown_rupees": float(drawdowns.min()),
        "max_drawdown_pct_capital": float(drawdowns.min() / CAPITAL * 100.0),
        "cvar5_rupees": cvar,
        "longest_losing_streak": int(longest),
    }


def _worst_days(
    frame: pd.DataFrame,
    pnl_column: str,
    variant_id: str,
    period: str,
    slippage_multiple: int,
    stress_mode: bool,
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    daily = (
        frame.groupby("exit_date")
        .agg(net_pnl_rupees=(pnl_column, "sum"), trade_count=(pnl_column, "size"))
        .sort_values("net_pnl_rupees")
    )
    daily = daily.head(10)
    return [
        {
            "variant_id": variant_id,
            "period": period,
            "slippage_multiple": slippage_multiple,
            "stress_mode": stress_mode,
            "date": date,
            "trade_count": int(row.trade_count),
            "net_pnl_rupees": float(row.net_pnl_rupees),
        }
        for date, row in daily.iterrows()
    ]


def _stationary_bootstrap(
    frame: pd.DataFrame,
    pnl_column: str,
    seed: int,
) -> tuple[float, float, float]:
    if frame.empty:
        return float("nan"), float("nan"), float("nan")
    values = frame[[pnl_column, "entry_date"]].copy()
    values["week"] = pd.to_datetime(values["entry_date"]).dt.to_period("W-SUN")
    grouped = values.groupby("week")[pnl_column].agg(["sum", "count"])
    week_grid = pd.period_range(grouped.index.min(), grouped.index.max(), freq="W-SUN")
    grouped = grouped.reindex(week_grid, fill_value=0)
    sums = grouped["sum"].to_numpy(dtype=float)
    counts = grouped["count"].to_numpy(dtype=float)
    n_weeks = len(sums)
    if n_weeks < 2:
        mean = float(values[pnl_column].mean())
        return mean, mean, mean
    rng = np.random.default_rng(seed)
    samples = np.empty(BOOTSTRAP_REPLICATES, dtype=float)
    restart_probability = 1.0 / BOOTSTRAP_MEAN_BLOCK_WEEKS
    indices = np.empty((BOOTSTRAP_REPLICATES, n_weeks), dtype=np.int32)
    indices[:, 0] = rng.integers(0, n_weeks, size=BOOTSTRAP_REPLICATES)
    for col in range(1, n_weeks):
        restart = rng.random(BOOTSTRAP_REPLICATES) < restart_probability
        next_index = (indices[:, col - 1] + 1) % n_weeks
        next_index[restart] = rng.integers(0, n_weeks, size=int(restart.sum()))
        indices[:, col] = next_index
    sampled_sums = sums[indices].sum(axis=1)
    sampled_counts = counts[indices].sum(axis=1)
    samples[:] = np.divide(
        sampled_sums,
        sampled_counts,
        out=np.zeros_like(sampled_sums),
        where=sampled_counts > 0,
    )
    point = float(values[pnl_column].mean())
    centered_samples = samples - point
    p_value = float((1 + np.count_nonzero(centered_samples >= point)) / (BOOTSTRAP_REPLICATES + 1))
    lower, upper = np.quantile(samples, [0.025, 0.975])
    return float(lower), float(upper), p_value


def _holm(p_values: dict[str, float]) -> dict[str, float]:
    valid = [(key, value) for key, value in p_values.items() if math.isfinite(value)]
    ordered = sorted(valid, key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for index, (key, p_value) in enumerate(ordered):
        running = max(running, min(1.0, (total - index) * p_value))
        adjusted[key] = running
    return adjusted


def _markdown_report(
    variants: list[dict[str, Any]],
    metrics: pd.DataFrame,
    worst_days: pd.DataFrame,
    skipped: Counter,
    chosen: dict[str, Any],
    input_coverage: dict[str, Any],
    charge_model: dict[str, Any],
) -> str:
    primary = metrics.loc[
        (metrics["scenario"] == "standard") & (metrics["slippage_multiple"] == 1)
    ].copy()
    develop = primary.loc[primary["period"] == "DEVELOP"].set_index("variant_id")
    validate = primary.loc[primary["period"] == "VALIDATE"].set_index("variant_id")
    dev_rank = develop["net_expectancy_rupees"].rank(method="min", ascending=False)
    val_rank = validate["net_expectancy_rupees"].rank(method="min", ascending=False)
    primary = primary.assign(
        rank_develop=primary["variant_id"].map(dev_rank),
        rank_validate=primary["variant_id"].map(val_rank),
    )
    chosen_id = chosen["variant_id"]
    chosen_dev = develop.loc[chosen_id]
    chosen_val = validate.loc[chosen_id]
    chosen_rank_dev = int(dev_rank.loc[chosen_id])
    chosen_rank_val = int(val_rank.loc[chosen_id])

    c2_dev = metrics.loc[
        (metrics.variant_id == chosen_id)
        & (metrics.period == "DEVELOP")
        & (metrics.slippage_multiple == 2)
        & (metrics.scenario == "standard")
    ].iloc[0]
    c2_val = metrics.loc[
        (metrics.variant_id == chosen_id)
        & (metrics.period == "VALIDATE")
        & (metrics.slippage_multiple == 2)
        & (metrics.scenario == "standard")
    ].iloc[0]
    chosen_stress_dev = metrics.loc[
        (metrics.variant_id == chosen_id)
        & (metrics.period == "DEVELOP")
        & (metrics.slippage_multiple == 1)
        & (metrics.scenario == "intraday_touch_stop")
    ].iloc[0]
    chosen_stress_val = metrics.loc[
        (metrics.variant_id == chosen_id)
        & (metrics.period == "VALIDATE")
        & (metrics.slippage_multiple == 1)
        & (metrics.scenario == "intraday_touch_stop")
    ].iloc[0]

    gates = {
        "a": (
            chosen_dev.net_expectancy_rupees > 0
            and chosen_val.net_expectancy_rupees > 0
            and chosen_dev.ci95_low_rupees > 0
        ),
        "b": (
            chosen_dev.worst_month_pct_capital >= -15.0
            and chosen_val.worst_month_pct_capital >= -15.0
            and chosen_dev.max_drawdown_pct_capital >= -25.0
            and chosen_val.max_drawdown_pct_capital >= -25.0
        ),
        "c": (
            c2_dev.net_expectancy_rupees > 0 and c2_val.net_expectancy_rupees > 0
        ),
        "d": (
            chosen_dev.expectancy_after_best5_rupees > 0
            and chosen_val.expectancy_after_best5_rupees > 0
        ),
        "e": chosen_rank_dev <= 12 and chosen_rank_val <= 12,
    }
    result = "PASS" if all(gates.values()) else "FAIL"

    variant_rows = []
    ordered_variants = sorted(variants, key=lambda item: item["variant_id"])
    for variant in ordered_variants:
        variant_id = variant["variant_id"]
        drow = develop.loc[variant_id]
        vrow = validate.loc[variant_id]
        d2 = metrics.loc[
            (metrics.variant_id == variant_id)
            & (metrics.period == "DEVELOP")
            & (metrics.slippage_multiple == 2)
            & (metrics.scenario == "standard")
        ].iloc[0]
        v2 = metrics.loc[
            (metrics.variant_id == variant_id)
            & (metrics.period == "VALIDATE")
            & (metrics.slippage_multiple == 2)
            & (metrics.scenario == "standard")
        ].iloc[0]
        variant_rows.append(
            f"| {variant_id} | {int(drow.trade_count)} | {drow.net_expectancy_rupees:.0f} "
            f"| {drow.ci95_low_rupees:.0f} | {int(dev_rank.loc[variant_id])} "
            f"| {int(vrow.trade_count)} | {vrow.net_expectancy_rupees:.0f} "
            f"| {int(val_rank.loc[variant_id])} | {d2.net_expectancy_rupees:.0f} "
            f"| {v2.net_expectancy_rupees:.0f} |"
        )

    chosen_rows = []
    for period in ("DEVELOP", "VALIDATE", "CONFIRM"):
        for slippage in (1, 2):
            row = metrics.loc[
                (metrics.variant_id == chosen_id)
                & (metrics.period == period)
                & (metrics.slippage_multiple == slippage)
                & (metrics.scenario == "standard")
            ]
            if row.empty:
                continue
            row = row.iloc[0]
            chosen_rows.append(
                f"| {period} | {slippage}x | {int(row.trade_count)} | "
                f"{row.total_net_pnl_rupees:.0f} | {row.net_expectancy_rupees:.0f} | "
                f"{row.mean_pnl_pct_max_loss:.2f}% | {row.win_rate_pct:.1f}% | "
                f"{row.profit_factor:.2f} | {row.worst_trade_rupees:.0f} | "
                f"{row.worst_month_rupees:.0f} ({row.worst_month_pct_capital:.2f}%) | "
                f"{row.max_drawdown_rupees:.0f} ({row.max_drawdown_pct_capital:.2f}%) | "
                f"{row.cvar5_rupees:.0f} | {int(row.longest_losing_streak)} |"
            )

    chosen_worst = worst_days.loc[
        (worst_days.variant_id == chosen_id)
        & (worst_days.slippage_multiple == 1)
        & (~worst_days.stress_mode)
        & (worst_days.period.isin(["DEVELOP", "VALIDATE"]))
    ]
    worst_table = []
    for period in ("DEVELOP", "VALIDATE"):
        rows = chosen_worst.loc[chosen_worst.period == period]
        for row in rows.itertuples(index=False):
            worst_table.append(
                f"| {period} | {row.date} | {row.trade_count} | {row.net_pnl_rupees:.0f} |"
            )

    confirm_lines = []
    for slippage in (1, 2):
        standard = metrics.loc[
            (metrics.variant_id == chosen_id)
            & (metrics.period == "CONFIRM")
            & (metrics.slippage_multiple == slippage)
            & (metrics.scenario == "standard")
        ]
        stress = metrics.loc[
            (metrics.variant_id == chosen_id)
            & (metrics.period == "CONFIRM")
            & (metrics.slippage_multiple == slippage)
            & (metrics.scenario == "intraday_touch_stop")
        ]
        if standard.empty:
            continue
        s = standard.iloc[0]
        st = stress.iloc[0]
        confirm_lines.append(
            f"| {slippage}x | {int(s.trade_count)} | {s.total_net_pnl_rupees:.0f} | "
            f"{s.net_expectancy_rupees:.0f} | {s.win_rate_pct:.1f}% | "
            f"{s.max_drawdown_pct_capital:.2f}% | "
            f"{int(st.intraday_touch_trade_count)} | "
            f"{st.net_expectancy_rupees:.0f} | {st.win_rate_pct:.1f}% |"
        )

    missing_forecast_sessions = skipped["sessions_without_forecast"]
    selected_dev_p = chosen_dev.holm_pvalue
    top_dev = develop.sort_values("net_expectancy_rupees", ascending=False).iloc[0]
    top_dev_id = top_dev.name
    top_dev_adj = top_dev.holm_pvalue
    return f"""# NIFTY Iron Condor Fixed-Grid Backtest

**Decision: {result}.** All five pre-registered conditions are conjunctive; a missed condition is a FAIL.

## Scope and locked assumptions

- Data: `tmp/optdata/NIFTY_options_2021.parquet` through `NIFTY_options_2026.parquet`; `tmp/longhist/data/NIFTY_5y.parquet`; `tmp/longhist/data/INDIA_VIX_5y.parquet`; and the fixed OOS forecast in `tmp/longhist/unseen_study/range_forecast_oos.csv`.
- Periods are assigned by **entry date**: DEVELOP {PERIODS["DEVELOP"][0]}–{PERIODS["DEVELOP"][1]}, VALIDATE {PERIODS["VALIDATE"][0]}–{PERIODS["VALIDATE"][1]}, CONFIRM {PERIODS["CONFIRM"][0]}–{PERIODS["CONFIRM"][1]}. To prevent split leakage, trades must mature by their assigned period end; boundary-crossing and unexpired/censored trades are omitted.
- Forecast filter uses only the existing `target == day_range` / `predicted_high_range` prediction. A predicted-high day is skipped; missing forecast dates are not treated as predicted-low. The forecast covers {input_coverage["forecast_start"]}–{input_coverage["forecast_end"]}; {missing_forecast_sessions} option sessions lack a forecast and are unavailable to filtered variants.
- Entry spot is the option bhavcopy `underlying_close`; sigma is VIX at the entry session’s first 09:15 bar divided by 100, times sqrt(calendar DTE/365), times spot. Select short call at the nearest listed OTM strike at/above spot + distance×sigma; select short put at the nearest listed OTM strike at/below spot − distance×sigma. Wings are exactly 100/200 points.
- Expiry is the earliest listed expiry strictly after entry date (same-day expiry excluded); only entries whose nearest expiry falls in the configured calendar-DTE bucket trade.
- Entry and early-exit prices are the bhavcopy `close` (not `settle_price`). Early exits are checked at each available EOD close: close when the condor debit is <=50% of entry credit; stop when debit is >=2x credit. Otherwise settle at expiry using NIFTY’s last 1-minute close and intrinsic value.
- Every entry leg must have bhavcopy volume >= {MIN_VOLUME:.0f} and open interest >= {MIN_OPEN_INTEREST:.0f} (data-field units), positive close price, and available wing contract; any failed leg skips the trade. Lot size is {LOT_SIZE}.
- Since bid/ask quotes are unavailable, slippage is an adverse one-tick proxy ({TICK_SIZE:.2f} point per leg per executed side at entry and early close); sensitivity uses {2*TICK_SIZE:.2f} points. Entry involves four orders; early close adds four orders; expiration does not add exit orders. Fees use the configured paper model: flat brokerage ₹{charge_model["brokerage_flat_inr"]:.2f}/order, sell STT {100*charge_model["stt_sell_rate"]:.3f}%, exchange {100*charge_model["exchange_rate"]:.4f}%, SEBI {charge_model["sebi_rate"]:.6f}%, buy stamp {100*charge_model["stamp_buy_rate"]:.3f}%, and GST {100*charge_model["gst_rate"]:.0f}% on brokerage/exchange/SEBI. Zero-priced sell fills use ₹0.01 only for the fee helper’s positive-price validation. At expiry, a conservative settlement-STT proxy applies the configured sell-STT rate to intrinsic value on every ITM leg; no brokerage/exit order is added.
- Intraday stress scans every 1-minute NIFTY bar after entry through the standard exit/expiry. Any short-strike touch forces a same-day 2x-credit stop. Since intraday option marks are unavailable, stress-exit leg marks scale each entry leg by 2x before the same adverse slippage and configured exit-order fees.
- Return as % max loss is the mean per-trade net P&L divided by each trade’s defined max loss, which is (wing width − filled credit)×65 before fees. Worst months and drawdown use realized exit-date portfolio P&L and ₹100,000 starting capital; drawdown does not include interim unrealized marks. CVaR 5% is the mean of the worst ceil(5%×n) trade outcomes.
- Expectancy intervals and p-values use a stationary bootstrap of entry-week trade clusters, mean contiguous block length 4 weeks, {BOOTSTRAP_REPLICATES:,} resamples. The one-sided DEVELOP null p-values for positive expectancy are Holm-adjusted across all 48 variants (family-wise alpha 5%).

## Selected variant and pre-registered decision

Selection rule (no confirm tuning): highest 1x-slippage mean net expectancy in DEVELOP. This selected **{chosen_id}** ({chosen["width"]}-point wings, {chosen["distance"]}σ, {chosen["dte_low"]}–{chosen["dte_high"]} DTE, {chosen["exit_policy"]}, {chosen["day_filter"]}). DEVELOP rank {chosen_rank_dev}/48; VALIDATE rank {chosen_rank_val}/48. The best DEVELOPMENT expectancy is {top_dev_id} at ₹{top_dev.net_expectancy_rupees:.2f}/trade (raw bootstrap p={top_dev.bootstrap_pvalue:.4f}; Holm-adjusted p={top_dev_adj:.4f}).

| Gate | Result | Evidence |
|---|---|---|
| (a) Positive DEVELOP and VALIDATE expectancy; DEVELOP 95% lower bound > 0 | {"PASS" if gates["a"] else "FAIL"} | DEV ₹{chosen_dev.net_expectancy_rupees:.2f}/trade, 95% CI [₹{chosen_dev.ci95_low_rupees:.2f}, ₹{chosen_dev.ci95_high_rupees:.2f}]; VAL ₹{chosen_val.net_expectancy_rupees:.2f}/trade |
| (b) Worst month >= −15% capital and max drawdown >= −25% in DEVELOP and VALIDATE | {"PASS" if gates["b"] else "FAIL"} | DEV month {chosen_dev.worst_month_pct_capital:.2f}%, MDD {chosen_dev.max_drawdown_pct_capital:.2f}%; VAL month {chosen_val.worst_month_pct_capital:.2f}%, MDD {chosen_val.max_drawdown_pct_capital:.2f}% |
| (c) Positive expectancy at 2x slippage in DEVELOP and VALIDATE | {"PASS" if gates["c"] else "FAIL"} | DEV ₹{c2_dev.net_expectancy_rupees:.2f}/trade; VAL ₹{c2_val.net_expectancy_rupees:.2f}/trade |
| (d) Positive expectancy after removing the 5 best trades in both periods | {"PASS" if gates["d"] else "FAIL"} | DEV ₹{chosen_dev.expectancy_after_best5_rupees:.2f}/trade; VAL ₹{chosen_val.expectancy_after_best5_rupees:.2f}/trade |
| (e) Top quartile (rank <=12) in both DEVELOP and VALIDATE | {"PASS" if gates["e"] else "FAIL"} | DEV {chosen_rank_dev}/48; VAL {chosen_rank_val}/48 |

### Selected-variant core metrics

| Period | Slippage | Trades | Net P&L (₹) | Expectancy/trade (₹) | Mean % max loss | Win rate | Profit factor | Worst trade (₹) | Worst month (₹; % capital) | Max drawdown (₹; % capital) | CVaR 5% (₹) | Longest losing streak |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(chosen_rows)}

### Selected-variant intraday touch stress (1x slippage)

| Period | Touch trades | Standard expectancy (₹) | Stopped-at-2x expectancy (₹) | Standard win rate | Stressed win rate |
|---|---:|---:|---:|---:|---:|
| DEVELOP | {int(chosen_stress_dev.intraday_touch_trade_count)} | {chosen_dev.net_expectancy_rupees:.2f} | {chosen_stress_dev.net_expectancy_rupees:.2f} | {chosen_dev.win_rate_pct:.1f}% | {chosen_stress_dev.win_rate_pct:.1f}% |
| VALIDATE | {int(chosen_stress_val.intraday_touch_trade_count)} | {chosen_val.net_expectancy_rupees:.2f} | {chosen_stress_val.net_expectancy_rupees:.2f} | {chosen_val.win_rate_pct:.1f}% | {chosen_stress_val.win_rate_pct:.1f}% |

## All 48 variants

The table gives 1x expectancy and DEVELOPMENT lower confidence bound, ranks, and 2x sensitivity expectancy. Full requested risk metrics for both standard and intraday-stress scenarios, both slippage levels, and both periods are in `variant_metrics.csv`; worst 10 realized-P&L dates per combination are in `worst_days.csv`.

| Variant | DEV n | DEV E (₹) | DEV CI low (₹) | DEV rank | VAL n | VAL E (₹) | VAL rank | DEV 2x E (₹) | VAL 2x E (₹) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(variant_rows)}

## Selected variant’s 10 worst realized-P&L days

If fewer than 10 days lost money, the remaining rows are net-gain days because they are still among the 10 worst daily outcomes.

| Period | Exit date | Trades | Net P&L (₹) |
|---|---|---:|---:|
{chr(10).join(worst_table)}

## CONFIRM (selected variant only; no grid search)

| Slippage | Trades | Net P&L (₹) | Expectancy/trade (₹) | Win rate | MDD % capital | Touch trades | Intraday-stress expectancy (₹) | Stressed win rate |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(confirm_lines)}

CONFIRM is descriptive only and was not used for selection or retuning. Confirm metrics are computed for the selected variant only.

## Data/replay diagnostics

- Option sessions: {skipped["option_sessions"]}; NIFTY minute dates: {skipped["nifty_dates"]}; VIX minute dates: {skipped["vix_dates"]}.
- Forecast dates: {input_coverage["forecast_days"]}; coverage {input_coverage["forecast_start"]}–{input_coverage["forecast_end"]}.
- Boundary-censored candidate entries omitted: {skipped["boundary_censored_trades"]} across the grid in DEVELOP/VALIDATE plus the selected CONFIRM variant.
- Skipped candidate-leg/coverage counts (reasons can overlap across variants): {dict(skipped)}.
- The complete trade ledger, including strikes, credits, exit dates/reasons, short-touch flags, standard P&L, and stressed P&L, is in `trade_ledger.csv`.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    charge_model = config["paper_charge_model"]
    min_volume = float(config.get("option_min_volume", MIN_VOLUME))
    min_oi = float(config.get("option_min_oi", MIN_OPEN_INTEREST))
    if min_volume != MIN_VOLUME or min_oi != MIN_OPEN_INTEREST:
        raise ValueError(
            "Configured option liquidity filters changed; update the registered "
            f"thresholds explicitly (found volume={min_volume}, OI={min_oi})"
        )
    option_index = _read_options()
    nifty_daily, vix_open = _read_minute_data()
    variants = _make_variants()
    forecast_devval = _read_forecast(end_date=PERIODS["VALIDATE"][1])
    templates, skipped = _get_templates(
        variants,
        option_index,
        nifty_daily,
        vix_open,
        forecast_devval,
        PERIODS["DEVELOP"][0],
        PERIODS["VALIDATE"][1],
    )
    data_end = max(option_index.index.get_level_values("date").unique())
    option_dates = option_index.index.get_level_values("date").unique()
    option_days = sorted(option_dates)
    expiry_days = sorted(option_index.index.get_level_values("expiry").unique())
    input_coverage: dict[str, Any] = {
        "data_end": data_end,
        "option_start": min(option_days),
        "option_end": max(option_days),
        "last_expiry": max(expiry_days),
    }

    template_by_variant = {variant["variant_id"]: variant for variant in variants}
    simulated: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for variant in variants:
        variant_id = variant["variant_id"]
        for period in ("DEVELOP", "VALIDATE"):
            period_start, period_end = PERIODS[period]
            period_templates = [
                template
                for template in templates[variant_id]
                if period_start <= template["entry_date"] <= period_end
            ]
            eligible = [
                template
                for template in period_templates
                if template["expiry"] <= period_end
            ]
            skipped["boundary_censored_trades"] += len(period_templates) - len(eligible)
            for slip_multiple in (1, 2):
                rows = []
                day_cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
                for template in eligible:
                    row = _simulate(
                        template,
                        variant,
                        option_index,
                        option_dates,
                        day_cache,
                        nifty_daily,
                        charge_model,
                        slip_multiple,
                        period_end,
                    )
                    if row is not None:
                        rows.append(row)
                simulated[(variant_id, slip_multiple, period)] = rows

    metrics_rows: list[dict[str, Any]] = []
    worst_rows: list[dict[str, Any]] = []
    ledger_rows: list[dict[str, Any]] = []
    bootstrap_p: dict[str, float] = {}
    for index, variant in enumerate(variants):
        variant_id = variant["variant_id"]
        for slip_multiple in (1, 2):
            for period in ("DEVELOP", "VALIDATE"):
                period_trades = pd.DataFrame(
                    simulated[(variant_id, slip_multiple, period)]
                )
                for scenario, pnl_column, exit_column in (
                    ("standard", "pnl_rupees", "exit_date"),
                    ("intraday_touch_stop", "stress_pnl_rupees", "stress_exit_date"),
                ):
                    scenario_frame = period_trades.copy()
                    if not scenario_frame.empty:
                        scenario_frame["exit_date"] = scenario_frame[exit_column]
                    metric_values = _metrics(scenario_frame, pnl_column)
                    metric_row = {
                        "variant_id": variant_id,
                        "period": period,
                        "slippage_multiple": slip_multiple,
                        "scenario": scenario,
                        **metric_values,
                        "intraday_touch_trade_count": (
                            int(period_trades["intraday_short_touch"].sum())
                            if not period_trades.empty
                            else 0
                        ),
                    }
                    if scenario == "standard":
                        best_five = period_trades[pnl_column].nlargest(5).index if not period_trades.empty else []
                        remaining = period_trades.drop(index=best_five)
                        metric_row["expectancy_after_best5_rupees"] = (
                            float(remaining[pnl_column].mean()) if not remaining.empty else float("nan")
                        )
                    else:
                        metric_row["expectancy_after_best5_rupees"] = float("nan")
                    if period == "DEVELOP" and slip_multiple == 1 and scenario == "standard":
                        lower, upper, pvalue = _stationary_bootstrap(
                            period_trades,
                            pnl_column,
                            BASE_SEED + index,
                        )
                        metric_row["ci95_low_rupees"] = lower
                        metric_row["ci95_high_rupees"] = upper
                        metric_row["bootstrap_pvalue"] = pvalue
                        bootstrap_p[variant_id] = pvalue
                    else:
                        metric_row["ci95_low_rupees"] = float("nan")
                        metric_row["ci95_high_rupees"] = float("nan")
                        metric_row["bootstrap_pvalue"] = float("nan")
                    metrics_rows.append(metric_row)
                    worst_frame = scenario_frame.copy()
                    worst_rows.extend(
                        _worst_days(
                            worst_frame,
                            pnl_column,
                            variant_id,
                            period,
                            slip_multiple,
                            scenario == "intraday_touch_stop",
                        )
                    )
            for period in ("DEVELOP", "VALIDATE"):
                for row in simulated[(variant_id, slip_multiple, period)]:
                    ledger_rows.append(
                        {
                            "variant_id": variant_id,
                            "slippage_multiple": slip_multiple,
                            "period": period,
                            "entry_date": row["entry_date"],
                            "expiry": row["expiry"],
                            "dte": row["dte"],
                            "spot": row["spot"],
                            "vix_open": row["vix_open"],
                            "sigma": row["sigma"],
                            "short_call": row["short_call"],
                            "long_call": row["long_call"],
                            "short_put": row["short_put"],
                            "long_put": row["long_put"],
                            "credit_points": row["credit_points"],
                            "max_loss_rupees": row["max_loss_rupees"],
                            "exit_date": row["exit_date"],
                            "exit_reason": row["exit_reason"],
                            "net_pnl_rupees": row["pnl_rupees"],
                            "intraday_short_touch": row["intraday_short_touch"],
                            "first_touch_date": row["first_touch_date"],
                            "stressed_exit_date": row["stress_exit_date"],
                            "stressed_net_pnl_rupees": row["stress_pnl_rupees"],
                        }
                    )

    adjusted = _holm(bootstrap_p)
    metrics = pd.DataFrame(metrics_rows)
    metrics["holm_pvalue"] = metrics.apply(
        lambda row: adjusted.get(row.variant_id, float("nan"))
        if row.period == "DEVELOP" and row.slippage_multiple == 1 and row.scenario == "standard"
        else float("nan"),
        axis=1,
    )

    primary_dev = metrics.loc[
        (metrics.period == "DEVELOP")
        & (metrics.slippage_multiple == 1)
        & (metrics.scenario == "standard")
    ].sort_values(["net_expectancy_rupees", "variant_id"], ascending=[False, True])
    chosen_id = primary_dev.iloc[0]["variant_id"]
    chosen = template_by_variant[chosen_id]

    # CONFIRM input is read only after the development winner is fixed.
    forecast_all = _read_forecast()
    confirm_templates, confirm_skipped = _get_templates(
        [chosen],
        option_index,
        nifty_daily,
        vix_open,
        forecast_all,
        PERIODS["CONFIRM"][0],
        PERIODS["CONFIRM"][1],
    )
    skipped.update(confirm_skipped)
    skipped["option_sessions"] = len(option_days)
    skipped["sessions_with_forecast"] = sum(day in forecast_all for day in option_days)
    skipped["sessions_without_forecast"] = len(option_days) - skipped["sessions_with_forecast"]
    skipped["nifty_dates"] = len(nifty_daily)
    skipped["vix_dates"] = len(vix_open)
    input_coverage.update(
        {
            "forecast_start": min(forecast_all),
            "forecast_end": max(forecast_all),
            "forecast_days": len(forecast_all),
        }
    )
    confirm_metrics_rows = []
    confirm_worst_rows = []
    skipped["boundary_censored_trades"] += sum(
        template["expiry"] > PERIODS["CONFIRM"][1]
        for template in confirm_templates[chosen_id]
    )
    for slip_multiple in (1, 2):
        confirm_trades = []
        day_cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
        for template in confirm_templates[chosen_id]:
            if template["expiry"] > PERIODS["CONFIRM"][1]:
                continue
            row = _simulate(
                template,
                chosen,
                option_index,
                option_dates,
                day_cache,
                nifty_daily,
                charge_model,
                slip_multiple,
                PERIODS["CONFIRM"][1],
            )
            if row is not None:
                confirm_trades.append(row)
                ledger_rows.append(
                    {
                        "variant_id": chosen_id,
                        "slippage_multiple": slip_multiple,
                        "period": "CONFIRM",
                        "entry_date": row["entry_date"],
                        "expiry": row["expiry"],
                        "dte": row["dte"],
                        "spot": row["spot"],
                        "vix_open": row["vix_open"],
                        "sigma": row["sigma"],
                        "short_call": row["short_call"],
                        "long_call": row["long_call"],
                        "short_put": row["short_put"],
                        "long_put": row["long_put"],
                        "credit_points": row["credit_points"],
                        "max_loss_rupees": row["max_loss_rupees"],
                        "exit_date": row["exit_date"],
                        "exit_reason": row["exit_reason"],
                        "net_pnl_rupees": row["pnl_rupees"],
                        "intraday_short_touch": row["intraday_short_touch"],
                        "first_touch_date": row["first_touch_date"],
                        "stressed_exit_date": row["stress_exit_date"],
                        "stressed_net_pnl_rupees": row["stress_pnl_rupees"],
                    }
                )
        confirm_frame = pd.DataFrame(confirm_trades)
        for scenario, pnl_column, exit_column in (
            ("standard", "pnl_rupees", "exit_date"),
            ("intraday_touch_stop", "stress_pnl_rupees", "stress_exit_date"),
        ):
            scenario_frame = confirm_frame.copy()
            if not scenario_frame.empty:
                scenario_frame["exit_date"] = scenario_frame[exit_column]
            confirm_metrics_rows.append(
                {
                    "variant_id": chosen_id,
                    "period": "CONFIRM",
                    "slippage_multiple": slip_multiple,
                    "scenario": scenario,
                    **_metrics(scenario_frame, pnl_column),
                    "intraday_touch_trade_count": (
                        int(confirm_frame["intraday_short_touch"].sum())
                        if not confirm_frame.empty
                        else 0
                    ),
                    "expectancy_after_best5_rupees": float("nan"),
                    "ci95_low_rupees": float("nan"),
                    "ci95_high_rupees": float("nan"),
                    "bootstrap_pvalue": float("nan"),
                    "holm_pvalue": float("nan"),
                }
            )
            confirm_worst_rows.extend(
                _worst_days(
                    scenario_frame,
                    pnl_column,
                    chosen_id,
                    "CONFIRM",
                    slip_multiple,
                    scenario == "intraday_touch_stop",
                )
            )
    metrics = pd.concat(
        [metrics, pd.DataFrame(confirm_metrics_rows)], ignore_index=True
    )
    worst_days = pd.concat(
        [pd.DataFrame(worst_rows), pd.DataFrame(confirm_worst_rows)],
        ignore_index=True,
    )

    metrics_path = OUTPUT_DIR / "variant_metrics.csv"
    worst_path = OUTPUT_DIR / "worst_days.csv"
    ledger_path = OUTPUT_DIR / "trade_ledger.csv"
    metrics.to_csv(metrics_path, index=False)
    worst_days.to_csv(worst_path, index=False)
    pd.DataFrame(ledger_rows).to_csv(ledger_path, index=False)
    report = _markdown_report(
        variants,
        metrics,
        worst_days,
        skipped,
        chosen,
        input_coverage,
        charge_model,
    )
    report_path = OUTPUT_DIR / "report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Selected: {chosen_id}")
    print(f"Report: {report_path}")
    print(f"Metrics: {metrics_path}")
    print(f"Worst days: {worst_path}")
    print(f"Trade ledger: {ledger_path}")
    print(report.splitlines()[2])


if __name__ == "__main__":
    main()
