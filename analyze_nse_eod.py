"""Summarize NSE daily F&O bhavcopies without treating them as intraday data."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

FUTURE_TYPES = {"STF", "IDF"}
OPTION_TYPES = {"STO", "IDO"}
REQUIRED_COLUMNS = {
    "TradDt",
    "TckrSymb",
    "FinInstrmTp",
    "XpryDt",
    "FininstrmActlXpryDt",
    "FinInstrmNm",
    "OptnTp",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "LastPric",
    "TtlTradgVol",
    "OpnIntrst",
}


def load_rows(data_dir: Path) -> pd.DataFrame:
    files = sorted(data_dir.glob("*.csv.gz"))
    if not files:
        raise FileNotFoundError(f"No .csv.gz NSE EOD files found under {data_dir}")

    frames = []
    for path in files:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            frame = pd.read_csv(handle)
        missing = REQUIRED_COLUMNS.difference(frame.columns)
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
        frame["source_file"] = path.name
        frames.append(frame)

    data = pd.concat(frames, ignore_index=True)
    data["TradDt"] = pd.to_datetime(data["TradDt"], errors="coerce")
    data["XpryDt"] = pd.to_datetime(data["XpryDt"], errors="coerce")
    data["FininstrmActlXpryDt"] = pd.to_datetime(
        data["FininstrmActlXpryDt"], errors="coerce"
    )
    for column in (
        "OpnPric",
        "HghPric",
        "LwPric",
        "ClsPric",
        "LastPric",
        "TtlTradgVol",
        "OpnIntrst",
        "StrkPric",
    ):
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    data["TckrSymb"] = data["TckrSymb"].astype(str).str.strip().str.upper()
    data["FinInstrmTp"] = data["FinInstrmTp"].astype(str).str.strip().str.upper()
    data["OptnTp"] = data["OptnTp"].fillna("").astype(str).str.strip().str.upper()
    data["FinInstrmNm"] = data["FinInstrmNm"].astype(str).str.strip().str.upper()
    return data


def make_front_future_series(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    futures = data.loc[
        data["FinInstrmTp"].isin(FUTURE_TYPES)
        & data["TradDt"].notna()
        & data["XpryDt"].notna()
        & data["ClsPric"].gt(0)
        & data["TtlTradgVol"].gt(0)
    ].copy()
    futures = futures.loc[futures["XpryDt"] >= futures["TradDt"]]
    futures = futures.sort_values(
        ["TckrSymb", "FinInstrmNm", "TradDt"], kind="stable"
    )
    futures["prior_same_contract_close"] = futures.groupby(
        ["TckrSymb", "FinInstrmNm"], sort=False
    )["ClsPric"].shift(1)
    futures["prior_same_contract_date"] = futures.groupby(
        ["TckrSymb", "FinInstrmNm"], sort=False
    )["TradDt"].shift(1)

    front = futures.sort_values(
        ["TradDt", "TckrSymb", "XpryDt", "TtlTradgVol"],
        ascending=[True, True, True, False],
        kind="stable",
    ).drop_duplicates(["TradDt", "TckrSymb"], keep="first")
    front = front.sort_values(["TckrSymb", "TradDt"], kind="stable").copy()
    front["daily_return_pct"] = (
        front["ClsPric"] / front["prior_same_contract_close"] - 1.0
    ) * 100.0
    front["open_to_close_pct"] = (
        front["ClsPric"] / front["OpnPric"] - 1.0
    ) * 100.0
    front["high_low_range_pct_of_open"] = (
        (front["HghPric"] - front["LwPric"]) / front["OpnPric"] * 100.0
    )
    previous_contract = front.groupby("TckrSymb", sort=False)["FinInstrmNm"].shift()
    front["is_contract_roll"] = previous_contract.notna() & front[
        "FinInstrmNm"
    ].ne(previous_contract)
    front["daily_return_pct"] = front["daily_return_pct"].where(
        front["prior_same_contract_close"].gt(0)
    )
    output_columns = [
        "TradDt",
        "TckrSymb",
        "FinInstrmNm",
        "FinInstrmTp",
        "XpryDt",
        "FininstrmActlXpryDt",
        "OpnPric",
        "HghPric",
        "LwPric",
        "ClsPric",
        "LastPric",
        "TtlTradgVol",
        "OpnIntrst",
        "prior_same_contract_date",
        "prior_same_contract_close",
        "daily_return_pct",
        "open_to_close_pct",
        "high_low_range_pct_of_open",
        "is_contract_roll",
    ]
    daily = front[output_columns].rename(
        columns={
            "TradDt": "date",
            "TckrSymb": "underlying",
            "FinInstrmNm": "contract_symbol",
            "FinInstrmTp": "contract_type",
            "XpryDt": "expiry_date",
            "FininstrmActlXpryDt": "actual_expiry_date",
            "OpnPric": "open",
            "HghPric": "high",
            "LwPric": "low",
            "ClsPric": "close",
            "LastPric": "last",
            "TtlTradgVol": "volume",
            "OpnIntrst": "open_interest",
            "prior_same_contract_date": "prior_same_contract_date",
            "prior_same_contract_close": "prior_same_contract_close",
        }
    )
    summaries = []
    for underlying, group in daily.groupby("underlying", sort=True):
        returns = group["daily_return_pct"].dropna()
        equity = (1.0 + returns / 100.0).cumprod()
        drawdown = (equity / equity.cummax() - 1.0) * 100.0 if not equity.empty else equity
        volumes = group["volume"].dropna()
        summaries.append(
            {
                "underlying": underlying,
                "observations": len(group),
                "return_observations": len(returns),
                "first_date": group["date"].min(),
                "last_date": group["date"].max(),
                "roll_days": int(group["is_contract_roll"].sum()),
                "mean_daily_return_pct": returns.mean(),
                "median_daily_return_pct": returns.median(),
                "positive_return_days_pct": (returns.gt(0).mean() * 100.0) if len(returns) else None,
                "daily_return_std_pct": returns.std(ddof=1),
                "annualized_realized_volatility_pct": returns.std(ddof=1) * (252**0.5),
                "compounded_return_pct": ((equity.iloc[-1] - 1.0) * 100.0) if not equity.empty else None,
                "max_drawdown_pct": drawdown.min() if not drawdown.empty else None,
                "mean_open_to_close_pct": group["open_to_close_pct"].mean(),
                "mean_high_low_range_pct_of_open": group["high_low_range_pct_of_open"].mean(),
                "mean_daily_volume": volumes.mean(),
                "median_daily_volume": volumes.median(),
                "mean_daily_open_interest": group["open_interest"].mean(),
            }
        )
    summary = pd.DataFrame(summaries)
    return daily, summary


def summarize_options(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    options = data.loc[
        data["FinInstrmTp"].isin(OPTION_TYPES)
        & data["OptnTp"].isin(["CE", "PE"])
        & data["TradDt"].notna()
    ].copy()
    options["TtlTradgVol"] = options["TtlTradgVol"].fillna(0)
    options["OpnIntrst"] = options["OpnIntrst"].fillna(0)
    options["traded_contract"] = options["TtlTradgVol"].gt(0)

    daily = (
        options.groupby(["TradDt", "TckrSymb", "OptnTp"], as_index=False)
        .agg(
            listed_contracts=("FinInstrmNm", "size"),
            traded_contracts=("traded_contract", "sum"),
            total_reported_volume=("TtlTradgVol", "sum"),
            total_reported_open_interest=("OpnIntrst", "sum"),
            expiries=("XpryDt", "nunique"),
        )
        .rename(
            columns={
                "TradDt": "date",
                "TckrSymb": "underlying",
                "OptnTp": "option_type",
            }
        )
    )
    summaries = []
    for (underlying, option_type), group in options.groupby(
        ["TckrSymb", "OptnTp"], sort=True
    ):
        traded = group.loc[group["traded_contract"]]
        daily_group = daily.loc[
            (daily["underlying"] == underlying)
            & (daily["option_type"] == option_type)
        ]
        contract_volumes = traded.groupby("FinInstrmNm")["TtlTradgVol"].sum()
        top_contract = contract_volumes.idxmax() if not contract_volumes.empty else None
        summaries.append(
            {
                "underlying": underlying,
                "option_type": option_type,
                "contract_day_rows": len(group),
                "traded_contract_days": len(traded),
                "contract_days_with_volume_pct": (
                    len(traded) / len(group) * 100.0 if len(group) else None
                ),
                "distinct_contract_symbols": group["FinInstrmNm"].nunique(),
                "total_reported_volume": group["TtlTradgVol"].sum(),
                "mean_daily_reported_volume": daily_group["total_reported_volume"].mean(),
                "mean_daily_traded_contracts": daily_group["traded_contracts"].mean(),
                "mean_daily_reported_open_interest": daily_group[
                    "total_reported_open_interest"
                ].mean(),
                "max_single_contract_daily_volume": group["TtlTradgVol"].max(),
                "highest_cumulative_volume_contract": top_contract,
                "highest_cumulative_volume": (
                    int(contract_volumes.max()) if not contract_volumes.empty else 0
                ),
            }
        )
    summary = pd.DataFrame(summaries)
    daily.to_csv(index=False)
    summary.to_csv(index=False)
    return daily, summary


def fmt(value: object, digits: int = 2) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{float(value):,.{digits}f}"


def write_report(
    data: pd.DataFrame,
    futures_daily: pd.DataFrame,
    futures_summary: pd.DataFrame,
    options_daily: pd.DataFrame,
    options_summary: pd.DataFrame,
    manifest_path: Path,
    configured_underlyings: Iterable[str],
    output_path: Path,
) -> None:
    manifest = pd.read_csv(manifest_path)
    configured = sorted(set(configured_underlyings))
    present = sorted(data["TckrSymb"].unique())
    absent = sorted(set(configured) - set(present))
    futures_rows = data.loc[data["FinInstrmTp"].isin(FUTURE_TYPES)]
    options_rows = data.loc[data["FinInstrmTp"].isin(OPTION_TYPES)]

    lines = [
        "# NSE F&O Daily Contract Analysis",
        "",
        f"Coverage: {data['TradDt'].min().date()} to {data['TradDt'].max().date()} "
        f"({data['TradDt'].nunique()} dates; {len(manifest)} weekdays checked).",
        f"Rows: {len(data):,} total; {len(futures_rows):,} futures; {len(options_rows):,} options.",
        f"NSE files: {(manifest['status'] == 'downloaded').sum()} downloaded; "
        f"{(manifest['status'] == 'http_404').sum()} dates returned HTTP 404; "
        f"{(~manifest['status'].isin(['downloaded', 'http_404'])).sum()} other errors.",
        f"Configured underlyings present: {', '.join(present)}.",
        f"Configured underlyings absent from this export: {', '.join(absent) if absent else 'none'}.",
        "",
        "## Futures: nearest actively traded expiry",
        "The daily series selects the nearest unexpired futures contract with positive reported volume. "
        "A return is calculated against the previous available close of that same contract, not the "
        "previous day's selected contract, to avoid including the calendar-spread jump as a return. "
        "On roll days this is a descriptive same-contract return, not an investable continuous-contract fill.",
        "",
        "| Underlying | Sessions | Rolls | Mean daily return | Daily volatility | Compounded return | Max drawdown | Mean range |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in futures_summary.itertuples(index=False):
        lines.append(
            f"| {row.underlying} | {row.observations} | {row.roll_days} | "
            f"{fmt(row.mean_daily_return_pct)}% | {fmt(row.daily_return_std_pct)}% | "
            f"{fmt(row.compounded_return_pct)}% | {fmt(row.max_drawdown_pct)}% | "
            f"{fmt(row.mean_high_low_range_pct_of_open)}% |"
        )

    lines.extend(
        [
            "",
            "Annualized realized volatility is in `futures_daily_summary.csv`; it is computed from "
            "daily same-contract returns and scaled by $\\sqrt{252}$.",
            "",
            "## Options: daily activity by side",
            "Volume/open-interest totals are sums of NSE-reported contract rows and should be compared "
            "within the same underlying and option side. They are not a measure of executable liquidity "
            "because historical bid/ask depth is absent.",
            "",
            "| Underlying | Side | Contract-days | With volume | Active % | Mean daily volume | Mean daily OI | Top cumulative-volume contract |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in options_summary.itertuples(index=False):
        lines.append(
            f"| {row.underlying} | {row.option_type} | {row.contract_day_rows:,} | "
            f"{row.traded_contract_days:,} | {fmt(row.contract_days_with_volume_pct)}% | "
            f"{fmt(row.mean_daily_reported_volume, 0)} | "
            f"{fmt(row.mean_daily_reported_open_interest, 0)} | "
            f"{row.highest_cumulative_volume_contract or 'n/a'} |"
        )

    lines.extend(
        [
            "",
            "## What this supports",
            "- Daily futures price, range, volume, open-interest, and roll-aware descriptive analysis.",
            "- Daily options activity and contract-coverage comparisons by underlying, CE/PE side, strike, and expiry.",
            "- Exploratory daily-bar hypotheses, provided they are treated as a different timeframe and strategy.",
            "",
            "## What this does not support",
            "- The production 1-minute signal and entry/exit replay.",
            "- Bid/ask spreads, historical quote-based fills, latency, partial fills, or realistic slippage.",
            "- The requested five-minute missed-opportunity definition or production option execution model.",
            "- Claims that the live configuration passes out-of-sample or tomorrow-risk criteria.",
            "",
            "Zero-volume option rows are retained in the activity denominator; their zero/missing prices are "
            "not interpreted as executable quotes. Data is NSE daily EOD only.",
            "",
            "Outputs: `futures_front_month_daily.csv`, `futures_daily_summary.csv`, "
            "`options_daily_activity.csv`, and `options_activity_summary.csv`.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data_uploads/nse_eod/daily_contract_rows")
    parser.add_argument("--manifest", default="data_uploads/nse_eod/manifest.csv")
    parser.add_argument("--out-dir", default="backtest_artifacts/nse_eod_analysis")
    parser.add_argument(
        "--underlyings",
        default="NIFTY,BANKNIFTY,RELIANCE,HDFCBANK,ICICIBANK,SBIN,INFY,TCS,LT,TATAMOTORS",
    )
    args = parser.parse_args()

    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data = load_rows(Path(args.data_dir))
    futures_daily, futures_summary = make_front_future_series(data)
    futures_daily.to_csv(output_dir / "futures_front_month_daily.csv", index=False)
    futures_summary.to_csv(output_dir / "futures_daily_summary.csv", index=False)
    options_daily, options_summary = summarize_options(data)
    options_daily.to_csv(output_dir / "options_daily_activity.csv", index=False)
    options_summary.to_csv(output_dir / "options_activity_summary.csv", index=False)
    write_report(
        data,
        futures_daily,
        futures_summary,
        options_daily,
        options_summary,
        Path(args.manifest),
        (symbol.strip().upper() for symbol in args.underlyings.split(",")),
        output_dir / "daily_analysis.md",
    )
    print(
        json.dumps(
            {
                "rows": len(data),
                "futures_rows": int(data["FinInstrmTp"].isin(FUTURE_TYPES).sum()),
                "options_rows": int(data["FinInstrmTp"].isin(OPTION_TYPES).sum()),
                "futures_underlyings": len(futures_summary),
                "options_underlying_sides": len(options_summary),
                "outputs": str(output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
