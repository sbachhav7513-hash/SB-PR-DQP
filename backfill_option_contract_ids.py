from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Dict, Iterable

import pandas as pd


BACKFILL_DATES = (date(2026, 10, 29), date(2026, 10, 30))


def _day_directory(root: Path, target_date: date) -> Path:
    week = target_date.isocalendar().week
    return (
        root
        / target_date.strftime("%Y-%m")
        / f"week_{week:02d}"
        / f"day_{target_date.day:02d}"
    )


def _exact_signal_mappings(frames: Iterable[pd.DataFrame]) -> Dict[str, str]:
    candidates: Dict[str, set[str]] = {}
    for frame in frames:
        if not {"signal_id", "contract_id"}.issubset(frame.columns):
            continue
        for signal_id, contract_id in zip(frame["signal_id"], frame["contract_id"]):
            signal = "" if pd.isna(signal_id) else str(signal_id).strip()
            contract = "" if pd.isna(contract_id) else str(contract_id).strip()
            if signal and contract:
                candidates.setdefault(signal, set()).add(contract)
    return {
        signal_id: next(iter(contracts))
        for signal_id, contracts in candidates.items()
        if len(contracts) == 1
    }


def backfill_day(
    root: str | Path, target_date: date
) -> tuple[Path | None, int, int]:
    """Write a new Parquet copy, filling only unique exact signal_id mappings."""
    directory = _day_directory(Path(root), target_date)
    source_path = directory / "decisions.parquet"
    output_path = directory / "decisions.contract-id-backfilled.parquet"
    trades_path = directory / "trades.parquet"
    if not source_path.exists():
        raise FileNotFoundError(f"Decision journal not found: {source_path}")
    decisions = pd.read_parquet(source_path, engine="fastparquet")
    mapping_frames = [decisions]
    if trades_path.exists():
        mapping_frames.append(pd.read_parquet(trades_path, engine="fastparquet"))
    exact_mappings = _exact_signal_mappings(mapping_frames)
    if "contract_id" not in decisions.columns:
        decisions["contract_id"] = ""
    updated = 0
    for index, row in decisions.iterrows():
        contract_value = row.get("contract_id")
        signal_value = row.get("signal_id")
        existing = "" if pd.isna(contract_value) else str(contract_value).strip()
        signal_id = "" if pd.isna(signal_value) else str(signal_value).strip()
        if existing or not signal_id:
            continue
        mapped = exact_mappings.get(signal_id)
        if mapped:
            decisions.at[index, "contract_id"] = mapped
            updated += 1

    if not updated:
        return None, 0, len(decisions)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite backfill output: {output_path}")
    decisions.to_parquet(output_path, engine="fastparquet", index=False)
    return output_path, updated, len(decisions)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill exact option contract IDs into separate Parquet files."
    )
    parser.add_argument(
        "--paper-dir", default="paper_trading_data", help="Paper data root directory"
    )
    args = parser.parse_args()
    for target_date in BACKFILL_DATES:
        output_path, updated, total = backfill_day(args.paper_dir, target_date)
        if output_path is None:
            print(f"{target_date}: no uniquely mapped missing contract IDs; no output written")
        else:
            print(
                f"{target_date}: wrote {output_path} ({updated} contract IDs added "
                f"to {total} rows)"
            )


if __name__ == "__main__":
    main()
