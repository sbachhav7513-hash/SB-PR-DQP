#!/usr/bin/env python3
"""Offline migration of copied legacy decision journals into hourly parts."""

from __future__ import annotations

import argparse
import gc
import shutil
import tempfile
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pandas.testing import assert_frame_equal

from market_bot.trade_journal import read_decisions


IST = ZoneInfo("Asia/Kolkata")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def migrate_legacy_day(
    day_dir: Path,
    archive_dir: Path,
    data_root: Path,
    *,
    confirm_copy: bool,
) -> dict:
    day_dir = day_dir.resolve()
    archive_dir = archive_dir.resolve()
    data_root = data_root.resolve()
    if not confirm_copy:
        raise ValueError("Migration is allowed only after confirming the source is a copy")
    if not day_dir.is_dir():
        raise FileNotFoundError(f"Day directory does not exist: {day_dir}")
    if day_dir.name not in {"day_02", "day_03"}:
        raise ValueError("This migration tool is limited to day_02 and day_03 copies")
    if not _is_relative_to(day_dir, data_root):
        raise ValueError("The day directory must be inside the copied data root")
    if (
        day_dir.parent.name != "week_45"
        or day_dir.parents[1].name != "2026-11"
    ):
        raise ValueError("This migration tool is limited to Nov. 2 and Nov. 3, 2026")
    if _is_relative_to(archive_dir, data_root):
        raise ValueError("The archive directory must be outside the data tree")

    sources = []
    legacy = day_dir / "decisions.parquet"
    if legacy.is_file():
        sources.append(legacy)
    sources.extend(sorted(day_dir.glob("decisions_part*.parquet")))
    destination = day_dir / "decisions"
    if not sources:
        raise FileNotFoundError(f"No legacy decision files in {day_dir}")
    if destination.exists():
        raise FileExistsError(f"Hourly decisions already exist: {destination}")

    source_rows = 0
    columns = []
    for source in sources:
        parquet = pq.ParquetFile(source)
        source_rows += parquet.metadata.num_rows
        columns.extend(
            column for column in parquet.schema.names if column not in columns
        )
        del parquet
        gc.collect()
        pa.default_memory_pool().release_unused()
    original = read_decisions(day_dir, columns=columns)
    if len(original) > source_rows:
        raise RuntimeError("De-duplicated row count exceeds the source row count")
    if original.empty or "timestamp" not in original.columns:
        raise ValueError("Legacy decision data must contain timestamped rows")

    timestamps = pd.to_datetime(
        original["timestamp"], format="mixed", utc=True, errors="coerce"
    )
    if timestamps.isna().any():
        raise ValueError("Legacy decision data contains invalid timestamps")
    hours = timestamps.dt.tz_convert(IST).dt.hour
    staging = Path(tempfile.mkdtemp(prefix=".decisions_migration_", dir=day_dir))
    try:
        for hour in sorted(hours.unique()):
            frame = original.loc[hours == hour]
            frame.to_parquet(
                staging / f"decisions_{int(hour):02d}.parquet",
                engine="fastparquet",
                compression="SNAPPY",
                index=False,
            )

        staged_rows = sum(
            pq.ParquetFile(path).metadata.num_rows
            for path in staging.glob("decisions_*.parquet")
        )
        if staged_rows != len(original):
            raise RuntimeError(
                f"Hourly row count mismatch: wrote {staged_rows}, expected {len(original)}"
            )
        staging.rename(destination)
        migrated = read_decisions(day_dir, columns=columns)
        assert_frame_equal(
            original.reset_index(drop=True),
            migrated.reset_index(drop=True),
            check_dtype=False,
            check_categorical=False,
        )

        archived_day = (
            archive_dir
            / day_dir.parents[1].name
            / day_dir.parent.name
            / day_dir.name
        )
        archived_day.mkdir(parents=True, exist_ok=True)
        moved = []
        try:
            for source in sources:
                archived_source = archived_day / source.name
                if archived_source.exists():
                    raise FileExistsError(
                        f"Archived source already exists: {archived_source}"
                    )
                source.rename(archived_source)
                moved.append((archived_source, source))
            after_archive = read_decisions(day_dir, columns=columns)
            assert_frame_equal(
                original.reset_index(drop=True),
                after_archive.reset_index(drop=True),
                check_dtype=False,
                check_categorical=False,
            )
        except Exception:
            for archived_source, source in reversed(moved):
                archived_source.rename(source)
            shutil.rmtree(destination)
            raise

        return {
            "day_dir": str(day_dir),
            "source_rows": source_rows,
            "deduplicated_rows": len(original),
            "hourly_rows": staged_rows,
            "hourly_files": len(list(destination.glob("decisions_*.parquet"))),
            "archived_files": [str(path) for path, _ in moved],
        }
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if destination.exists():
            shutil.rmtree(destination)
        raise


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate legacy decisions to hourly part files. Use a copied data tree; "
            "the archive directory must be outside it."
        )
    )
    parser.add_argument(
        "--day-dir",
        action="append",
        required=True,
        help="Copied day_02 or day_03 directory (repeat for multiple days)",
    )
    parser.add_argument(
        "--data-root",
        required=True,
        help="Root of the copied paper_trading_data tree",
    )
    parser.add_argument(
        "--archive-dir",
        required=True,
        help="Archive path outside --data-root for original files",
    )
    parser.add_argument(
        "--confirm-copy",
        action="store_true",
        help="Confirm that --data-root is a copy, not the live data tree",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.confirm_copy:
        raise SystemExit("Refusing to migrate without --confirm-copy")
    for day_value in args.day_dir:
        result = migrate_legacy_day(
            Path(day_value),
            Path(args.archive_dir),
            Path(args.data_root),
            confirm_copy=True,
        )
        print(
            f"{result['day_dir']}: {result['source_rows']} source rows, "
            f"{result['deduplicated_rows']} parity-checked hourly rows in "
            f"{result['hourly_files']} files; archived {len(result['archived_files'])} originals"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
