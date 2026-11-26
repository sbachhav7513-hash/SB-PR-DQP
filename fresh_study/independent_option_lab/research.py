"""Independent, offline opening-range research; this module never places orders."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("research_config.json")
EXIT_POLICIES = ("take5", "take10", "trail5_10")


@dataclass(frozen=True)
class Signal:
    signal_index: int
    entry_index: int
    side: int
    range_high: float
    range_low: float
    setup: str
    invalidation: str


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


def detect_signal(
    bars: pd.DataFrame,
    *,
    opening_range_minutes: int,
    setup: str,
    aligned: bool = False,
    max_entry_index: int = 120,
    event_window_bars: int = 10,
) -> Signal | None:
    """Return one intraday signal; entry is always the following minute bar."""
    size = len(bars)
    if opening_range_minutes < 2 or size <= opening_range_minutes + 1:
        return None

    opens = bars["open"].to_numpy(dtype=float)
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    range_high = float(highs[:opening_range_minutes].max())
    range_low = float(lows[:opening_range_minutes].min())
    first_break: tuple[int, int] | None = None
    last_signal_index = min(max_entry_index, size - 2)

    for index in range(opening_range_minutes, last_signal_index + 1):
        direction = (
            1
            if closes[index] > range_high and closes[index - 1] <= range_high
            else -1
            if closes[index] < range_low and closes[index - 1] >= range_low
            else 0
        )

        if setup == "breakout":
            if not direction:
                continue
            if aligned:
                opening_direction = (
                    1
                    if closes[opening_range_minutes - 1] > opens[0]
                    else -1
                    if closes[opening_range_minutes - 1] < opens[0]
                    else 0
                )
                recent_direction = (
                    1
                    if closes[index] > closes[index - 5]
                    else -1
                    if closes[index] < closes[index - 5]
                    else 0
                )
                if direction != opening_direction or direction != recent_direction:
                    continue
            return Signal(
                index,
                index + 1,
                direction,
                range_high,
                range_low,
                setup,
                "range",
            )

        if setup not in {"retest", "failed_breakout_reversal"}:
            raise ValueError(f"unsupported setup: {setup}")

        if first_break is None:
            if direction:
                first_break = (index, direction)
            continue

        break_index, break_direction = first_break
        if index - break_index > event_window_bars:
            first_break = (index, direction) if direction else None
            continue

        if setup == "failed_breakout_reversal":
            failed = (
                closes[index] <= range_high
                if break_direction == 1
                else closes[index] >= range_low
            )
            if failed:
                return Signal(
                    index,
                    index + 1,
                    -break_direction,
                    range_high,
                    range_low,
                    setup,
                    "resume_up" if break_direction == 1 else "resume_down",
                )
        else:
            held_retest = (
                lows[index] <= range_high and closes[index] > range_high
                if break_direction == 1
                else highs[index] >= range_low and closes[index] < range_low
            )
            if held_retest:
                return Signal(
                    index,
                    index + 1,
                    break_direction,
                    range_high,
                    range_low,
                    setup,
                    "range",
                )

    return None


def simulate_underlying_proxy(
    bars: pd.DataFrame,
    signal: Signal,
    *,
    target_pct: float = 0.002,
    stop_pct: float = 0.001,
    max_holding_bars: int = 60,
) -> dict[str, Any]:
    """Score only the underlying path; this is not option or account P/L."""
    direction = signal.side
    entry = float(bars.iloc[signal.entry_index]["open"])
    target = entry * (1 + direction * target_pct)
    stop = entry * (1 - direction * stop_pct)
    last_index = min(len(bars) - 1, signal.entry_index + max_holding_bars)
    exit_price = float(bars.iloc[last_index]["close"])
    reason = "time"

    for index in range(signal.entry_index, last_index + 1):
        row = bars.iloc[index]
        stopped = (
            float(row["low"]) <= stop
            if direction == 1
            else float(row["high"]) >= stop
        )
        targeted = (
            float(row["high"]) >= target
            if direction == 1
            else float(row["low"]) <= target
        )
        if stopped:
            exit_price, reason = stop, "stop"
            break
        if targeted:
            exit_price, reason = target, "target"
            break

    result_pct = direction * (exit_price - entry) / entry
    return {
        "entry_price": entry,
        "exit_price": exit_price,
        "underlying_return_pct": result_pct * 100,
        "r_multiple": result_pct / stop_pct,
        "exit_reason": reason,
    }


def historical_proxy_replay(
    historical_dir: Path,
    config: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> pd.DataFrame:
    proxy = config["underlying_proxy"]
    records: list[dict[str, Any]] = []
    for symbol in proxy["symbols"]:
        path = historical_dir / f"{symbol}.csv"
        bars = read_bars(path)
        local_dates = bars["ts"].dt.tz_convert("Asia/Kolkata").dt.date
        bars = bars.assign(session=local_dates)
        for session, day_bars in bars.groupby("session", sort=True):
            day_bars = day_bars.reset_index(drop=True)
            for candidate in candidates:
                signal = detect_signal(
                    day_bars,
                    opening_range_minutes=candidate["opening_range_minutes"],
                    setup=candidate["setup"],
                    aligned=candidate.get(
                        "require_opening_range_and_recent_momentum_alignment",
                        False,
                    ),
                    event_window_bars=config["option_holdout"][
                        "max_retest_or_failure_window_bars"
                    ],
                )
                if signal is None:
                    continue
                outcome = simulate_underlying_proxy(
                    day_bars,
                    signal,
                    target_pct=proxy["target_return_pct"] / 100,
                    stop_pct=proxy["stop_return_pct"] / 100,
                    max_holding_bars=proxy["max_holding_bars"],
                )
                year = session.year
                if year > proxy["historical_validation_year"]:
                    continue
                records.append(
                    {
                        "symbol": symbol,
                        "session": session.isoformat(),
                        "year": year,
                        "candidate": candidate["name"],
                        "entry_time": day_bars.iloc[signal.entry_index]["ts"].isoformat(),
                        **outcome,
                    }
                )
    return pd.DataFrame.from_records(records)


def summarize_underlying_proxy(
    trades: pd.DataFrame,
    *,
    training_end_year: int,
    validation_year: int,
) -> pd.DataFrame:
    rows = []
    for (candidate, partition), group in trades.assign(
        partition=trades["year"].map(
            lambda year: "training"
            if year <= training_end_year
            else "validation"
            if year == validation_year
            else "outside"
        )
    ).groupby(["candidate", "partition"]):
        if partition == "outside":
            continue
        annual = group.groupby("year")["r_multiple"].sum()
        gains = group.loc[group["r_multiple"] > 0, "r_multiple"].sum()
        losses = -group.loc[group["r_multiple"] < 0, "r_multiple"].sum()
        rows.append(
            {
                "candidate": candidate,
                "partition": partition,
                "trades": len(group),
                "mean_r": group["r_multiple"].mean(),
                "profit_factor_proxy": gains / losses if losses else float("inf"),
                "positive_trade_rate": (group["r_multiple"] > 0).mean(),
                "positive_years": int((annual > 0).sum()),
                "years": len(annual),
                "mean_annual_r": annual.mean(),
            }
        )
    return pd.DataFrame(rows)


def _choose_contract(
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


def simulate_option_trade(
    option_bars: pd.DataFrame,
    aligned_spot_bars: pd.DataFrame,
    *,
    side: int,
    range_high: float,
    range_low: float,
    invalidation: str,
    policy: str,
    fee_per_side: float,
) -> dict[str, Any]:
    """Replay one long option using conservative minute-candle ordering."""
    if policy not in EXIT_POLICIES:
        raise ValueError(f"unsupported exit policy: {policy}")
    if option_bars.empty or len(option_bars) != len(aligned_spot_bars):
        raise ValueError("option and underlying candles must be non-empty and aligned")
    if not option_bars["ts"].reset_index(drop=True).equals(
        aligned_spot_bars["ts"].reset_index(drop=True)
    ):
        raise ValueError("option and underlying candle timestamps are not aligned")

    raw_entry = float(option_bars.iloc[0]["open"])
    if raw_entry <= 0:
        raise ValueError("option entry price must be positive")
    entry = raw_entry * (1 + fee_per_side)
    stop_level = entry * 0.95
    target = entry * (1.05 if policy == "take5" else 1.10)
    peak = entry
    minimum_low = float(option_bars.iloc[0]["low"])
    maximum_high = float(option_bars.iloc[0]["high"])
    exit_price = float(option_bars.iloc[-1]["close"])
    exit_reason = "session_close"
    exit_index = len(option_bars) - 1

    for index in range(len(option_bars)):
        option_row = option_bars.iloc[index]
        spot_row = aligned_spot_bars.iloc[index]
        low = float(option_row["low"])
        high = float(option_row["high"])
        minimum_low = min(minimum_low, low)
        maximum_high = max(maximum_high, high)

        trailing_active = policy == "trail5_10" and peak >= entry * 1.05
        active_stop = max(stop_level, peak * 0.97) if trailing_active else stop_level
        if low <= active_stop:
            exit_price = active_stop
            exit_reason = "trailing_stop" if active_stop > stop_level else "stop5"
            exit_index = index
            break

        spot_close = float(spot_row["close"])
        if invalidation == "resume_up":
            invalidated = spot_close >= range_high
        elif invalidation == "resume_down":
            invalidated = spot_close <= range_low
        elif side == 1:
            invalidated = spot_close <= range_high
        else:
            invalidated = spot_close >= range_low
        if invalidated:
            if index + 1 < len(option_bars):
                exit_price = float(option_bars.iloc[index + 1]["open"])
                exit_index = index + 1
                exit_reason = "underlying_invalidation"
            else:
                exit_price = float(option_row["close"])
                exit_index = index
                exit_reason = "underlying_invalidation_at_close"
            break

        if high >= target:
            exit_price = target
            exit_reason = "target5" if policy == "take5" else "target10"
            exit_index = index
            break
        if policy == "trail5_10":
            peak = max(peak, high)

    net_return = (exit_price * (1 - fee_per_side) - entry) / entry
    return {
        "entry_premium": entry,
        "exit_premium": exit_price,
        "net_return_pct": net_return * 100,
        "max_adverse_excursion_pct": (minimum_low - entry) / entry * 100,
        "max_favorable_excursion_pct": (maximum_high - entry) / entry * 100,
        "exit_reason": exit_reason,
    }


def option_replay(
    daily_dir: Path,
    candidates: list[dict[str, Any]],
    replay_config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, int]]:
    start = date.fromisoformat(replay_config["start_date"])
    end = date.fromisoformat(replay_config["end_date"])
    candidate_map = {item["name"]: item for item in candidates}
    cache: dict[Path, pd.DataFrame] = {}
    records: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}

    def cached_bars(path: Path) -> pd.DataFrame:
        if path not in cache:
            cache[path] = read_bars(path)
        return cache[path]

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

        underlying_instruments = {
            item["underlying"]: item
            for item in manifest.get("instruments", [])
            if item.get("kind") == "underlying"
        }
        options: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in manifest.get("instruments", []):
            if item.get("kind") == "option":
                options.setdefault(
                    (item.get("underlying", ""), item.get("instrument_type", "")), []
                ).append(item)

        prior_closes = manifest.get("prior_session_close", {})
        for symbol, underlying_item in underlying_instruments.items():
            spot_path = day_dir / underlying_item.get(
                "file", underlying_item.get("filename", "")
            )
            spot_bars = cached_bars(spot_path)
            if spot_bars.empty:
                continue

            for candidate_name in replay_config["entries_to_replay"]:
                candidate = candidate_map[candidate_name]
                signal = detect_signal(
                    spot_bars,
                    opening_range_minutes=candidate["opening_range_minutes"],
                    setup=candidate["setup"],
                    aligned=candidate.get(
                        "require_opening_range_and_recent_momentum_alignment",
                        False,
                    ),
                    max_entry_index=replay_config["max_entry_minute_after_open"],
                    event_window_bars=replay_config[
                        "max_retest_or_failure_window_bars"
                    ],
                )
                if signal is None:
                    continue

                leg = "CE" if signal.side == 1 else "PE"
                prior_close = prior_closes.get(symbol)
                contract = (
                    _choose_contract(
                        options.get((symbol, leg), []),
                        session,
                        float(prior_close),
                    )
                    if prior_close is not None
                    else None
                )
                if contract is None:
                    skipped["no_eligible_contract"] = (
                        skipped.get("no_eligible_contract", 0) + 1
                    )
                    continue
                option_path = day_dir / contract.get("file", contract.get("filename", ""))
                option_bars = cached_bars(option_path)
                if option_bars.empty:
                    skipped["empty_option_candles"] = (
                        skipped.get("empty_option_candles", 0) + 1
                    )
                    continue

                entry_time = spot_bars.iloc[signal.entry_index]["ts"]
                option_entry_indices = option_bars.index[
                    option_bars["ts"] == entry_time
                ].tolist()
                if not option_entry_indices:
                    skipped["no_exact_option_entry_minute"] = (
                        skipped.get("no_exact_option_entry_minute", 0) + 1
                    )
                    continue
                option_entry_index = option_entry_indices[0]
                option_after_entry = option_bars.iloc[option_entry_index:].reset_index(
                    drop=True
                )
                aligned = option_after_entry.merge(
                    spot_bars[["ts", "close"]].rename(
                        columns={"close": "spot_close"}
                    ),
                    on="ts",
                    how="inner",
                    validate="one_to_one",
                ).sort_values("ts").reset_index(drop=True)
                if aligned.empty or aligned.iloc[0]["ts"] != entry_time:
                    skipped["unaligned_entry_or_bars"] = (
                        skipped.get("unaligned_entry_or_bars", 0) + 1
                    )
                    continue
                aligned_option = aligned[
                    ["ts", "open", "high", "low", "close"]
                ].copy()
                aligned_spot = aligned[["ts", "spot_close"]].rename(
                    columns={"spot_close": "close"}
                )

                for fee_pct in replay_config["fee_scenarios_per_side_pct"]:
                    fee_per_side = float(fee_pct) / 100
                    for policy in EXIT_POLICIES:
                        outcome = simulate_option_trade(
                            aligned_option,
                            aligned_spot,
                            side=signal.side,
                            range_high=signal.range_high,
                            range_low=signal.range_low,
                            invalidation=signal.invalidation,
                            policy=policy,
                            fee_per_side=fee_per_side,
                        )
                        records.append(
                            {
                                "session": session.isoformat(),
                                "underlying": symbol,
                                "candidate": candidate_name,
                                "policy": policy,
                                "fee_per_side_pct": fee_pct,
                                "side": leg,
                                "contract": contract.get("tradingsymbol", ""),
                                "expiry": contract.get("expiry", ""),
                                "strike": contract.get("strike", ""),
                                "signal_time": spot_bars.iloc[
                                    signal.signal_index
                                ]["ts"].isoformat(),
                                "entry_time": entry_time.isoformat(),
                                **outcome,
                            }
                        )
    return pd.DataFrame.from_records(records), skipped


def summarize_options(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    groups = trades.groupby(
        ["candidate", "policy", "fee_per_side_pct"], sort=True
    )
    for (candidate, policy, fee), group in groups:
        positive = group.loc[group["net_return_pct"] > 0, "net_return_pct"].sum()
        negative = -group.loc[group["net_return_pct"] < 0, "net_return_pct"].sum()
        per_day = group.groupby("session")["net_return_pct"].sum()
        rows.append(
            {
                "candidate": candidate,
                "policy": policy,
                "fee_per_side_pct": fee,
                "trades": len(group),
                "win_rate": (group["net_return_pct"] > 0).mean(),
                "mean_net_return_pct": group["net_return_pct"].mean(),
                "median_net_return_pct": group["net_return_pct"].median(),
                "profit_factor": positive / negative if negative else float("inf"),
                "positive_sessions": int((per_day > 0).sum()),
                "sessions": len(per_day),
                "sum_trade_returns_pct_points_not_compounded": group[
                    "net_return_pct"
                ].sum(),
                "sum_ex_best_session_pct_points_not_compounded": (
                    per_day.sum() - per_day.max() if len(per_day) else 0
                ),
                "median_mae_pct": group["max_adverse_excursion_pct"].median(),
                "exit_reasons": json.dumps(
                    group["exit_reason"].value_counts().sort_index().to_dict(),
                    sort_keys=True,
                ),
            }
        )
    return pd.DataFrame(rows)


def run(
    historical_dir: Path,
    daily_dir: Path,
    output_dir: Path,
    config: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    config = config or load_config()
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = config["candidate_entries"]
    underlying = historical_proxy_replay(historical_dir, config, candidates)
    underlying_summary = summarize_underlying_proxy(
        underlying,
        training_end_year=config["underlying_proxy"][
            "historical_training_end_year"
        ],
        validation_year=config["underlying_proxy"]["historical_validation_year"],
    )
    options, skipped = option_replay(
        daily_dir, candidates, config["option_holdout"]
    )
    option_summary = summarize_options(options)

    underlying.to_csv(output_dir / "underlying_proxy_trades.csv", index=False)
    underlying_summary.to_csv(
        output_dir / "underlying_proxy_summary.csv", index=False
    )
    options.to_csv(output_dir / "option_holdout_trades.csv", index=False)
    option_summary.to_csv(output_dir / "option_holdout_summary.csv", index=False)
    (output_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "config": config,
                "skipped_option_entries": skipped,
                "underlying_proxy_trade_count": len(underlying),
                "option_replay_trade_rows_including_fee_scenarios_and_policies": len(
                    options
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
    return underlying_summary, option_summary, options, skipped


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-dir", type=Path, default=ROOT / "historical_data")
    parser.add_argument(
        "--daily-dir", type=Path, default=ROOT / "data_uploads" / "kite_daily"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("results"),
    )
    args = parser.parse_args(argv)
    underlying, options, _, skipped = run(
        args.historical_dir, args.daily_dir, args.output_dir
    )
    print("Underlying-only proxy summary:")
    print(underlying.to_string(index=False))
    print("\nActual recent option-candle summary:")
    print(options.to_string(index=False))
    print(f"\nSkipped option entry reasons: {json.dumps(skipped, sort_keys=True)}")
    print(f"Research outputs: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
