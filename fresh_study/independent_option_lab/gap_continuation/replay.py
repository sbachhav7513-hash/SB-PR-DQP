"""Offline overnight-gap continuation research; no broker or order interfaces."""

from __future__ import annotations

import argparse
from bisect import bisect_right
import json
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = Path(__file__).with_name("config.json")
IST = "Asia/Kolkata"
OPTION_POLICIES = ("take5", "take10", "trail5_10")


@dataclass(frozen=True)
class GapSignal:
    signal_index: int
    entry_index: int
    side: int
    prior_close: float
    gap_atr: float
    gap_return: float
    first_move_return: float
    confirmation_ratio: float


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_bars(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    frame["ts"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["ts", "open", "high", "low", "close"]).copy()
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame = frame.sort_values("ts").reset_index(drop=True)
    if frame["ts"].duplicated().any():
        raise ValueError(f"{path} contains duplicate candle timestamps")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError(f"{path} contains non-positive OHLC prices")
    if (
        (frame["low"] > frame["high"])
        | (frame["low"] > frame[["open", "close"]].min(axis=1))
        | (frame["high"] < frame[["open", "close"]].max(axis=1))
    ).any():
        raise ValueError(f"{path} contains invalid OHLC ranges")
    return frame


def sessionize(frame: pd.DataFrame) -> list[tuple[date, pd.DataFrame]]:
    local_time = frame["ts"].dt.tz_convert(IST)
    sessions = frame.assign(
        session_date=local_time.dt.date,
        local_time=local_time.dt.time,
    )
    output = []
    for session_date, group in sessions.groupby("session_date", sort=True):
        group = group.sort_values("ts").reset_index(drop=True)
        market_bars = group[
            (group["local_time"] >= time(9, 15))
            & (group["local_time"] < time(15, 30))
        ].drop(columns=["session_date", "local_time"])
        output.append((session_date, market_bars.reset_index(drop=True)))
    return output


def daily_atr_table(
    sessions: list[tuple[date, pd.DataFrame]], lookback: int
) -> pd.DataFrame:
    """Calculate prior-session ATR; the current session is never in its ATR."""
    daily = []
    for session_date, bars in sessions:
        if bars.empty:
            continue
        daily.append(
            {
                "session": session_date,
                "open": float(bars.iloc[0]["open"]),
                "high": float(bars["high"].max()),
                "low": float(bars["low"].min()),
                "close": float(bars.iloc[-1]["close"]),
                "bar_count": len(bars),
            }
        )
    result = pd.DataFrame(daily)
    if result.empty:
        return result.assign(previous_close=pd.Series(dtype=float), atr=pd.Series(dtype=float))
    result["previous_close"] = result["close"].shift(1)
    result["true_range"] = result.apply(
        lambda row: max(
            row["high"] - row["low"],
            abs(row["high"] - row["previous_close"]),
            abs(row["low"] - row["previous_close"]),
        )
        if pd.notna(row["previous_close"])
        else row["high"] - row["low"],
        axis=1,
    )
    result["atr"] = result["true_range"].shift(1).rolling(
        lookback, min_periods=lookback
    ).mean()
    return result


def make_gap_signal(
    bars: pd.DataFrame,
    *,
    prior_close: float,
    prior_atr: float,
    confirmation_minutes: int,
    gap_atr_min: float,
    gap_atr_max_exclusive: float,
    minimum_confirmation_to_gap_ratio: float,
) -> GapSignal | None:
    """Confirm a directionally continuing overnight gap before entry."""
    features = describe_gap_setup(
        bars,
        prior_close=prior_close,
        prior_atr=prior_atr,
        confirmation_minutes=confirmation_minutes,
        gap_atr_min=gap_atr_min,
        gap_atr_max_exclusive=gap_atr_max_exclusive,
        minimum_confirmation_to_gap_ratio=minimum_confirmation_to_gap_ratio,
    )
    if features["decision"] != "accepted":
        return None

    gap_return = float(features["gap_return_pct"]) / 100
    gap_atr = float(features["gap_atr"])
    first_move_return = float(features["confirmation_return_pct"]) / 100
    confirmation_ratio = float(features["confirmation_ratio"])
    side = 1 if features["side"] == "up" else -1
    return GapSignal(
        signal_index=confirmation_minutes - 1,
        entry_index=confirmation_minutes,
        side=side,
        prior_close=prior_close,
        gap_atr=gap_atr,
        gap_return=gap_return,
        first_move_return=first_move_return,
        confirmation_ratio=confirmation_ratio,
    )


def describe_gap_setup(
    bars: pd.DataFrame,
    *,
    prior_close: float,
    prior_atr: float,
    confirmation_minutes: int,
    gap_atr_min: float,
    gap_atr_max_exclusive: float,
    minimum_confirmation_to_gap_ratio: float,
) -> dict[str, Any]:
    """Return causal setup features and an explicit accept/reject reason."""
    result: dict[str, Any] = {
        "decision": "rejected",
        "filter_reason": "",
        "gap_atr": None,
        "gap_return_pct": None,
        "confirmation_return_pct": None,
        "confirmation_ratio": None,
        "side": None,
        "entry_time": None,
    }
    if prior_close <= 0 or prior_atr <= 0:
        result["filter_reason"] = "invalid_prior_close_or_atr"
        return result
    if confirmation_minutes < 1 or len(bars) <= confirmation_minutes:
        result["filter_reason"] = "incomplete_opening_window"
        return result

    local = bars["ts"].dt.tz_convert(IST)
    expected_open = pd.Timestamp.combine(
        local.iloc[0].date(), time(9, 15)
    ).tz_localize(IST)
    expected = pd.Series(
        pd.date_range(
            expected_open,
            periods=confirmation_minutes + 1,
            freq="min",
            tz=IST,
        )
    )
    observed = local.iloc[: confirmation_minutes + 1].reset_index(drop=True)
    if not observed.equals(expected):
        result["filter_reason"] = "incomplete_or_misaligned_opening_window"
        return result

    open_price = float(bars.iloc[0]["open"])
    gap = open_price - prior_close
    if gap == 0:
        result["filter_reason"] = "no_overnight_gap"
        return result
    gap_atr = abs(gap) / prior_atr
    side = 1 if gap > 0 else -1
    first_move = float(bars.iloc[confirmation_minutes - 1]["close"]) - open_price
    first_move_return = first_move / open_price
    gap_return = gap / prior_close
    confirmation_ratio = first_move_return / gap_return
    result.update(
        {
            "gap_atr": gap_atr,
            "gap_return_pct": gap_return * 100,
            "confirmation_return_pct": first_move_return * 100,
            "confirmation_ratio": confirmation_ratio,
            "side": "up" if side == 1 else "down",
            "entry_time": bars.iloc[confirmation_minutes]["ts"].isoformat(),
        }
    )
    if gap_atr < gap_atr_min:
        result["filter_reason"] = "gap_below_minimum_atr"
    elif gap_atr >= gap_atr_max_exclusive:
        result["filter_reason"] = "gap_above_maximum_atr"
    elif confirmation_ratio <= 0:
        result["filter_reason"] = "opening_move_reversed_gap"
    elif confirmation_ratio < minimum_confirmation_to_gap_ratio:
        result["filter_reason"] = "weak_opening_confirmation"
    else:
        result["decision"] = "accepted"
        result["filter_reason"] = "gap_and_confirmation_passed"
    return result


def simulate_underlying(
    bars: pd.DataFrame,
    signal: GapSignal,
    *,
    prior_atr: float,
    stop_atr: float,
    target_r: float,
    max_holding_minutes: int,
) -> dict[str, Any]:
    entry = float(bars.iloc[signal.entry_index]["open"])
    risk_points = prior_atr * stop_atr
    if risk_points <= 0:
        raise ValueError("underlying stop distance must be positive")
    stop = entry - signal.side * risk_points
    target = entry + signal.side * risk_points * target_r
    final_index = min(
        len(bars) - 1,
        signal.entry_index + max_holding_minutes - 1,
    )
    exit_price = float(bars.iloc[final_index]["close"])
    reason = "time"

    for index in range(signal.entry_index, final_index + 1):
        row = bars.iloc[index]
        stopped = (
            float(row["low"]) <= stop
            if signal.side == 1
            else float(row["high"]) >= stop
        )
        targeted = (
            float(row["high"]) >= target
            if signal.side == 1
            else float(row["low"]) <= target
        )
        if stopped:
            exit_price, reason = stop, "underlying_atr_stop"
            break
        if targeted:
            exit_price, reason = target, "underlying_r_target"
            break

    return {
        "underlying_entry": entry,
        "underlying_exit": exit_price,
        "underlying_r": signal.side * (exit_price - entry) / risk_points,
        "underlying_exit_reason": reason,
    }


def historical_replay(
    historical_dir: Path, config: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lookback = int(config["daily_atr_lookback_sessions"])
    trades = []
    atr_rows = []
    decisions = []
    for symbol in config["symbols"]:
        sessions = sessionize(read_bars(historical_dir / f"{symbol}.csv"))
        atr_table = daily_atr_table(sessions, lookback)
        by_date = {day: bars for day, bars in sessions}
        for row in atr_table.itertuples():
            atr_rows.append(
                {
                    "symbol": symbol,
                    "session": row.session.isoformat(),
                    "prior_close": row.previous_close,
                    "prior_atr": row.atr,
                    "session_bars": row.bar_count,
                }
            )
            if pd.isna(row.previous_close) or pd.isna(row.atr):
                continue
            bars = by_date[row.session]
            for confirmation_minutes in config["confirmation_minutes_sensitivity"]:
                decision = describe_gap_setup(
                    bars,
                    prior_close=float(row.previous_close),
                    prior_atr=float(row.atr),
                    confirmation_minutes=int(confirmation_minutes),
                    gap_atr_min=float(config["gap_atr_min"]),
                    gap_atr_max_exclusive=float(config["gap_atr_max_exclusive"]),
                    minimum_confirmation_to_gap_ratio=0.0,
                )
                decisions.append(
                    {
                        "symbol": symbol,
                        "session": row.session.isoformat(),
                        "confirmation_minutes": confirmation_minutes,
                        **decision,
                    }
                )
                signal = make_gap_signal(
                    bars,
                    prior_close=float(row.previous_close),
                    prior_atr=float(row.atr),
                    confirmation_minutes=int(confirmation_minutes),
                    gap_atr_min=float(config["gap_atr_min"]),
                    gap_atr_max_exclusive=float(config["gap_atr_max_exclusive"]),
                    minimum_confirmation_to_gap_ratio=0.0,
                )
                if signal is None or signal.confirmation_ratio <= 0:
                    continue
                for minimum_ratio in config["confirmation_ratio_sensitivity"]:
                    if signal.confirmation_ratio < minimum_ratio:
                        continue
                    result = simulate_underlying(
                        bars,
                        signal,
                        prior_atr=float(row.atr),
                        stop_atr=float(config["underlying_stop_atr"]),
                        target_r=float(config["underlying_target_r"]),
                        max_holding_minutes=int(config["max_holding_minutes"]),
                    )
                    trades.append(
                        {
                            "symbol": symbol,
                            "session": row.session.isoformat(),
                            "year": row.session.year,
                            "confirmation_minutes": confirmation_minutes,
                            "filter_min_confirmation_ratio": minimum_ratio,
                            "gap_atr": signal.gap_atr,
                            "gap_return_pct": signal.gap_return * 100,
                            "confirmation_return_pct": signal.first_move_return * 100,
                            "confirmation_ratio": signal.confirmation_ratio,
                            "entry_time": bars.iloc[signal.entry_index]["ts"].isoformat(),
                            **result,
                        }
                    )
    return pd.DataFrame(trades), pd.DataFrame(atr_rows), pd.DataFrame(decisions)


def summarize_underlying(
    trades: pd.DataFrame, training_end_year: int, validation_year: int, recent_year: int
) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    partitions = trades.copy()
    partitions["partition"] = partitions["year"].map(
        lambda year: "training"
        if year <= training_end_year
        else "validation"
        if year == validation_year
        else "recent"
        if year == recent_year
        else "other"
    )
    rows = []
    for (minutes, ratio, partition), group in partitions.groupby(
        [
            "confirmation_minutes",
            "filter_min_confirmation_ratio",
            "partition",
        ]
    ):
        annual = group.groupby("year")["underlying_r"].sum()
        gains = group.loc[group["underlying_r"] > 0, "underlying_r"].sum()
        losses = -group.loc[group["underlying_r"] < 0, "underlying_r"].sum()
        rows.append(
            {
                "minimum_confirmation_ratio": ratio,
                "confirmation_minutes": minutes,
                "partition": partition,
                "trades": len(group),
                "mean_r": group["underlying_r"].mean(),
                "profit_factor_proxy": gains / losses if losses else float("inf"),
                "win_rate": (group["underlying_r"] > 0).mean(),
                "positive_years": int((annual > 0).sum()),
                "years": len(annual),
                "stop_rate": (
                    group["underlying_exit_reason"] == "underlying_atr_stop"
                ).mean(),
            }
        )
    return pd.DataFrame(rows)


def _select_option(
    contracts: list[dict[str, Any]], session: date, prior_close: float
) -> dict[str, Any] | None:
    eligible = [
        item
        for item in contracts
        if item.get("expiry") and item["expiry"] >= session.isoformat()
    ]
    if not eligible:
        return None
    expiry = min(item["expiry"] for item in eligible)
    same_expiry = [item for item in eligible if item["expiry"] == expiry]
    return min(same_expiry, key=lambda item: abs(float(item["strike"]) - prior_close))


def simulate_option(
    options: pd.DataFrame,
    spot: pd.DataFrame,
    signal: GapSignal,
    *,
    prior_atr: float,
    underlying_stop_atr: float,
    option_stop_pct: float,
    fee_per_side_pct: float,
    policy: str,
    max_holding_minutes: int,
    trailing_activation_pct: float,
    trailing_distance_pct: float,
    option_target_pct: float,
) -> dict[str, Any]:
    if options.empty or len(options) != len(spot):
        raise ValueError("option and underlying paths must be non-empty and aligned")
    if not options["ts"].reset_index(drop=True).equals(
        spot["ts"].reset_index(drop=True)
    ):
        raise ValueError("option and underlying timestamps must align exactly")
    if policy not in OPTION_POLICIES:
        raise ValueError(f"unsupported option exit policy: {policy}")
    if max_holding_minutes < 1:
        raise ValueError("max_holding_minutes must be positive")

    full_options = options
    bars_to_manage = min(len(options), max_holding_minutes)
    options = options.iloc[:bars_to_manage].reset_index(drop=True)
    spot = spot.iloc[:bars_to_manage].reset_index(drop=True)
    raw_entry = float(options.iloc[0]["open"])
    if raw_entry <= 0:
        raise ValueError("option entry price must be positive")
    fee = fee_per_side_pct / 100
    entry = raw_entry * (1 + fee)
    fixed_stop = entry * (1 - option_stop_pct / 100)
    target = entry * (1 + option_target_pct / 100)
    peak = entry
    max_high = float(options.iloc[0]["high"])
    min_low = float(options.iloc[0]["low"])
    underlying_entry = float(spot.iloc[0]["open"])
    underlying_stop = (
        underlying_entry
        - signal.side * prior_atr * underlying_stop_atr
    )
    exit_price = float(options.iloc[-1]["close"])
    reason = (
        "max_holding_time"
        if bars_to_manage < len(full_options)
        else "session_close"
    )
    exit_index = len(options) - 1

    for index, (option_row, spot_row) in enumerate(
        zip(options.itertuples(), spot.itertuples())
    ):
        low = float(option_row.low)
        high = float(option_row.high)
        min_low = min(min_low, low)
        max_high = max(max_high, high)
        trail_active = (
            policy == "trail5_10"
            and peak >= entry * (1 + trailing_activation_pct / 100)
        )
        active_stop = (
            max(fixed_stop, peak * (1 - trailing_distance_pct / 100))
            if trail_active
            else fixed_stop
        )
        if low <= active_stop:
            exit_price = active_stop
            reason = "trailing_stop" if active_stop > fixed_stop else "option_stop"
            exit_index = index
            break

        underlying_stopped = (
            float(spot_row.low) <= underlying_stop
            if signal.side == 1
            else float(spot_row.high) >= underlying_stop
        )
        if underlying_stopped:
            if index + 1 < len(full_options):
                exit_price = float(full_options.iloc[index + 1]["open"])
                reason = "underlying_atr_stop_next_open"
                exit_index = index + 1
            else:
                exit_price = float(option_row.close)
                reason = "underlying_atr_stop_at_close"
                exit_index = index
            break

        if high >= target:
            exit_price = target
            reason = f"option_target_{int(option_target_pct)}"
            exit_index = index
            break
        if policy == "trail5_10":
            peak = max(peak, high)

    net_return = (exit_price * (1 - fee) - entry) / entry
    return {
        "entry_premium": entry,
        "exit_premium": exit_price,
        "net_return_pct": net_return * 100,
        "max_adverse_excursion_pct": (min_low - entry) / entry * 100,
        "max_favorable_excursion_pct": (max_high - entry) / entry * 100,
        "exit_reason": reason,
    }


def option_replay(
    daily_dir: Path, historical_dir: Path, config: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    periods = config["research_periods"]
    start = date.fromisoformat(periods["option_start_date"])
    end = date.fromisoformat(periods["option_end_date"])
    atr_by_symbol: dict[str, tuple[list[date], list[float]]] = {}
    for symbol in config["symbols"]:
        sessions = sessionize(read_bars(historical_dir / f"{symbol}.csv"))
        table = daily_atr_table(sessions, int(config["daily_atr_lookback_sessions"]))
        atr_rows = [
            (row.session, float(row.atr))
            for row in table.itertuples()
            if pd.notna(row.atr)
        ]
        atr_by_symbol[symbol] = (
            [row[0] for row in atr_rows],
            [row[1] for row in atr_rows],
        )

    cache: dict[Path, pd.DataFrame] = {}

    def cached(path: Path) -> pd.DataFrame:
        if path not in cache:
            cache[path] = read_bars(path)
        return cache[path]

    all_candidates = []
    option_trades = []
    skipped: dict[str, int] = {}
    for day_dir in sorted(path for path in daily_dir.iterdir() if path.is_dir()):
        try:
            session = date.fromisoformat(day_dir.name)
        except ValueError:
            continue
        if not start <= session <= end:
            continue
        manifest_path = day_dir / "manifest.json"
        if not manifest_path.exists():
            skipped["missing_manifest"] = skipped.get("missing_manifest", 0) + 1
            continue
        with manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        instruments = manifest.get("instruments", [])
        underlying_items = {
            item["underlying"]: item
            for item in instruments
            if item.get("kind") == "underlying"
        }
        contracts: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in instruments:
            if item.get("kind") == "option":
                contracts.setdefault(
                    (item.get("underlying", ""), item.get("instrument_type", "")), []
                ).append(item)

        for symbol in config["symbols"]:
            item = underlying_items.get(symbol)
            atr_dates, atr_values = atr_by_symbol.get(symbol, ([], []))
            atr_index = bisect_right(atr_dates, session) - 1
            atr = atr_values[atr_index] if atr_index >= 0 else None
            prior_close = manifest.get("prior_session_close", {}).get(symbol)
            if item is None or atr is None or prior_close is None:
                skipped["missing_underlying_prior_close_or_atr"] = (
                    skipped.get("missing_underlying_prior_close_or_atr", 0) + 1
                )
                continue
            spot_path = day_dir / item.get("file", item.get("filename", ""))
            spot = cached(spot_path)
            features = describe_gap_setup(
                spot,
                prior_close=float(prior_close),
                prior_atr=atr,
                confirmation_minutes=int(config["entry_confirmation_minutes"]),
                gap_atr_min=0.0,
                gap_atr_max_exclusive=float("inf"),
                minimum_confirmation_to_gap_ratio=0.0,
            )
            if features["decision"] != "accepted":
                all_candidates.append(
                    {
                        "session": session.isoformat(),
                        "symbol": symbol,
                        **features,
                    }
                )
                continue
            passes_gap_band = (
                float(config["gap_atr_min"])
                <= float(features["gap_atr"])
                < float(config["gap_atr_max_exclusive"])
            )
            passes_strength = (
                float(features["confirmation_ratio"])
                >= float(config["minimum_confirmation_to_gap_ratio"])
            )
            selected = passes_gap_band and passes_strength
            filter_reason = (
                "gap_and_confirmation_passed"
                if selected
                else "gap_outside_atr_band"
                if not passes_gap_band
                else "weak_opening_confirmation"
            )
            row: dict[str, Any] = {
                "session": session.isoformat(),
                "symbol": symbol,
                **features,
                "decision": "accepted" if selected else "rejected",
                "filter_reason": filter_reason,
                "passes_gap_band": passes_gap_band,
                "passes_confirmation_strength": passes_strength,
                "selected_by_strategy_filter": selected,
            }
            all_candidates.append(row)

            signal = make_gap_signal(
                spot,
                prior_close=float(prior_close),
                prior_atr=atr,
                confirmation_minutes=int(config["entry_confirmation_minutes"]),
                gap_atr_min=0.0,
                gap_atr_max_exclusive=float("inf"),
                minimum_confirmation_to_gap_ratio=0.0,
            )
            if signal is None:
                raise RuntimeError(
                    "gap diagnostics accepted a setup that signal construction rejected"
                )
            leg = "CE" if signal.side == 1 else "PE"
            contract = _select_option(
                contracts.get((symbol, leg), []),
                session,
                float(prior_close),
            )
            if contract is None:
                skipped["no_eligible_option_contract"] = (
                    skipped.get("no_eligible_option_contract", 0) + 1
                )
                all_candidates[-1]["decision"] = "rejected"
                all_candidates[-1]["filter_reason"] = "no_eligible_option_contract"
                continue
            option_path = day_dir / contract.get("file", contract.get("filename", ""))
            option_bars = cached(option_path)
            entry_time = spot.iloc[signal.entry_index]["ts"]
            option_indices = option_bars.index[option_bars["ts"] == entry_time].tolist()
            if not option_indices:
                skipped["no_exact_option_entry_minute"] = (
                    skipped.get("no_exact_option_entry_minute", 0) + 1
                )
                all_candidates[-1]["decision"] = "rejected"
                all_candidates[-1]["filter_reason"] = "no_exact_option_entry_minute"
                continue
            option_bars = option_bars.iloc[option_indices[0] :].reset_index(drop=True)
            aligned = option_bars.merge(
                spot[["ts", "open", "high", "low", "close"]].rename(
                    columns={
                        "open": "spot_open",
                        "high": "spot_high",
                        "low": "spot_low",
                        "close": "spot_close",
                    }
                ),
                on="ts",
                how="inner",
                validate="one_to_one",
            ).sort_values("ts").reset_index(drop=True)
            if aligned.empty or aligned.iloc[0]["ts"] != entry_time:
                skipped["unaligned_option_and_underlying_path"] = (
                    skipped.get("unaligned_option_and_underlying_path", 0) + 1
                )
                all_candidates[-1]["decision"] = "rejected"
                all_candidates[-1]["filter_reason"] = (
                    "unaligned_option_and_underlying_path"
                )
                continue
            option_aligned = aligned[["ts", "open", "high", "low", "close"]].copy()
            spot_aligned = aligned[
                ["ts", "spot_open", "spot_high", "spot_low", "spot_close"]
            ].rename(
                columns={
                    "spot_open": "open",
                    "spot_high": "high",
                    "spot_low": "low",
                    "spot_close": "close",
                }
            )
            for fee in config["fee_scenarios_per_side_pct"]:
                for policy in OPTION_POLICIES:
                    target_pct = 5.0 if policy == "take5" else 10.0
                    result = simulate_option(
                        option_aligned,
                        spot_aligned,
                        signal,
                        prior_atr=atr,
                        underlying_stop_atr=float(config["underlying_stop_atr"]),
                        option_stop_pct=float(config["option_stop_pct"]),
                        fee_per_side_pct=float(fee),
                        policy=policy,
                        max_holding_minutes=int(config["max_holding_minutes"]),
                        trailing_activation_pct=float(
                            config["trailing_exit"]["activate_after_profit_pct"]
                        ),
                        trailing_distance_pct=float(
                            config["trailing_exit"]["trail_distance_pct"]
                        ),
                        option_target_pct=target_pct,
                    )
                    option_trades.append(
                        {
                            **row,
                            "contract": contract.get("tradingsymbol", ""),
                            "expiry": contract.get("expiry", ""),
                            "strike": contract.get("strike", ""),
                            "policy": policy,
                            "fee_per_side_pct": fee,
                            **result,
                        }
                    )
    return pd.DataFrame(all_candidates), pd.DataFrame(option_trades), skipped


def summarize_options(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    for (selected, policy, fee), group in trades.groupby(
        ["selected_by_strategy_filter", "policy", "fee_per_side_pct"], sort=True
    ):
        wins = group.loc[group["net_return_pct"] > 0, "net_return_pct"].sum()
        losses = -group.loc[group["net_return_pct"] < 0, "net_return_pct"].sum()
        days = group.groupby("session")["net_return_pct"].sum()
        rows.append(
            {
                "selected_by_strategy_filter": selected,
                "policy": policy,
                "fee_per_side_pct": fee,
                "trades": len(group),
                "win_rate": (group["net_return_pct"] > 0).mean(),
                "mean_net_return_pct": group["net_return_pct"].mean(),
                "profit_factor": wins / losses if losses else float("inf"),
                "positive_sessions": int((days > 0).sum()),
                "sessions": len(days),
                "sum_trade_returns_pct_points_not_compounded": group[
                    "net_return_pct"
                ].sum(),
                "sum_ex_best_session_pct_points_not_compounded": (
                    days.sum() - days.max() if len(days) else 0
                ),
                "exit_reasons": json.dumps(
                    group["exit_reason"].value_counts().sort_index().to_dict(),
                    sort_keys=True,
                ),
            }
        )
    return pd.DataFrame(rows)


def run(
    historical_dir: Path, daily_dir: Path, output_dir: Path
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    config = load_config()
    output_dir.mkdir(parents=True, exist_ok=True)
    underlying, atr_table, decisions = historical_replay(historical_dir, config)
    periods = config["research_periods"]
    underlying_summary = summarize_underlying(
        underlying,
        int(periods["training_end_year"]),
        int(periods["reported_validation_year"]),
        int(periods["recent_year"]),
    )
    candidates, options, skipped = option_replay(
        daily_dir, historical_dir, config
    )
    option_summary = summarize_options(options)
    confirmation_summaries = []
    for minutes in config["confirmation_minutes_sensitivity"]:
        minutes = int(minutes)
        if minutes == int(config["entry_confirmation_minutes"]):
            sensitivity_options = options
        else:
            sensitivity_config = dict(config)
            sensitivity_config["entry_confirmation_minutes"] = minutes
            _, sensitivity_options, _ = option_replay(
                daily_dir, historical_dir, sensitivity_config
            )
        sensitivity_summary = summarize_options(sensitivity_options)
        if not sensitivity_summary.empty:
            sensitivity_summary.insert(0, "confirmation_minutes", minutes)
            confirmation_summaries.append(sensitivity_summary)
    confirmation_summary = (
        pd.concat(confirmation_summaries, ignore_index=True)
        if confirmation_summaries
        else pd.DataFrame()
    )

    underlying.to_csv(output_dir / "gap_underlying_trades.csv", index=False)
    underlying_summary.to_csv(
        output_dir / "gap_underlying_summary.csv", index=False
    )
    atr_table.to_csv(output_dir / "daily_atr_inputs.csv", index=False)
    decisions.to_csv(
        output_dir / "gap_underlying_filter_decisions.csv", index=False
    )
    candidates.to_csv(output_dir / "gap_option_candidates.csv", index=False)
    options.to_csv(output_dir / "gap_option_trades.csv", index=False)
    option_summary.to_csv(output_dir / "gap_option_summary.csv", index=False)
    confirmation_summary.to_csv(
        output_dir / "gap_option_confirmation_sensitivity.csv", index=False
    )
    (output_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "config": config,
                "skipped_option_entries": skipped,
                "underlying_trade_rows_including_filter_sensitivities": len(
                    underlying
                ),
                "option_candidate_count": len(candidates),
                "option_trade_rows_including_fees_and_exit_policies": len(options),
                "option_confirmation_sensitivity_rows": len(
                    confirmation_summary
                ),
                "disclaimer": (
                    "Offline historical research only. No orders are created. "
                    "Underlying proxy returns are not option returns."
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return underlying_summary, candidates, option_summary, options, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-dir", type=Path, default=ROOT / "historical_data")
    parser.add_argument(
        "--daily-dir", type=Path, default=ROOT / "data_uploads" / "kite_daily"
    )
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("results"))
    args = parser.parse_args()
    underlying, candidates, options, _, skipped = run(
        args.historical_dir, args.daily_dir, args.output_dir
    )
    print("Underlying gap-continuation summary:")
    print(underlying.to_string(index=False))
    print("\nRecent option filter reasons:")
    print(candidates.groupby(["decision", "filter_reason"]).size().to_string())
    print("\nRecent option outcome summary:")
    print(options.to_string(index=False))
    print(f"\nSkipped candidates: {json.dumps(skipped, sort_keys=True)}")
    print(f"Outputs: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
