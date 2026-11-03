#!/usr/bin/env python3
"""Merge a day's decision parts into the legacy single-file Parquet layout."""

import argparse
import os
from pathlib import Path

import pandas as pd

from market_bot.trade_journal import PaperTradingRecorder, read_decisions


def merge_day_to_legacy(day_path: str | Path) -> tuple[Path, int]:
    directory = Path(day_path)
    decisions = read_decisions(directory)
    if decisions.empty:
        raise FileNotFoundError(f"No decision rows found in {directory}")

    columns = list(decisions.columns)
    records_frame = decisions.astype(object).where(decisions.notna(), None)
    records = records_frame.to_dict(orient="records")
    destination = directory / "decisions.parquet"
    temporary = directory / ".decisions.rollback.tmp.parquet"
    if temporary.exists():
        temporary.unlink()
    PaperTradingRecorder._write_parquet(temporary, records, columns)
    actual_rows = len(pd.read_parquet(temporary, engine="fastparquet"))
    if actual_rows != len(decisions):
        temporary.unlink(missing_ok=True)
        raise IOError(
            f"Legacy merge row-count mismatch for {directory}: "
            f"{actual_rows} != {len(decisions)}"
        )
    os.replace(temporary, destination)
    return destination, actual_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge one day's decisions/ files into decisions.parquet."
    )
    parser.add_argument("day_path", type=Path, help="Path to a day_DD directory")
    args = parser.parse_args()
    destination, rows = merge_day_to_legacy(args.day_path)
    print(f"Wrote {destination} ({rows} rows; row-count verified)")


if __name__ == "__main__":
    main()
