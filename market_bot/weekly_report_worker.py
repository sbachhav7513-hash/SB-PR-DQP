from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Sequence

from .reporting_metrics import _peak_working_set_bytes
from .weekly_report import (
    build_weekly_report,
    write_weekly_report,
    write_weekly_review,
)


logger = logging.getLogger(__name__)


def _write_status(path: Path, result: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(result), encoding="utf-8")
    temporary.replace(path)


def _run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    try:
        report = build_weekly_report(
            data_dir=args.data_dir,
            paper_data_dir=args.paper_data_dir,
            days=args.days,
        )
        peak_rss_bytes = _peak_working_set_bytes()
        elapsed = time.monotonic() - started
        if peak_rss_bytes > args.memory_budget_bytes:
            _write_status(
                args.result_file,
                {
                    "status": "budget",
                    "error": (
                        f"peak RSS {peak_rss_bytes / (1024 * 1024):.1f} MB "
                        f"exceeded {args.memory_budget_bytes / (1024 * 1024):.0f} MB"
                    ),
                    "peak_rss_bytes": peak_rss_bytes,
                },
            )
            return 0
        if elapsed > args.time_budget_seconds:
            _write_status(
                args.result_file,
                {
                    "status": "budget",
                    "error": (
                        f"elapsed {elapsed:.1f}s exceeded "
                        f"{args.time_budget_seconds:.0f}s"
                    ),
                    "peak_rss_bytes": peak_rss_bytes,
                },
            )
            return 0

        report_path = write_weekly_report(
            data_dir=args.data_dir,
            paper_data_dir=args.paper_data_dir,
            days=args.days,
            output_dir=args.staging_dir,
            report=report,
        )
        final_review_path = args.review_final_path
        review_path = write_weekly_review(
            data_dir=args.data_dir,
            paper_data_dir=args.paper_data_dir,
            days=args.days,
            report=report,
            output_path=args.review_staging_path,
        )
        if not report_path.is_file() or not review_path.is_file():
            raise OSError("Weekly report or review staging output is missing")
        peak_rss_bytes = _peak_working_set_bytes()
        elapsed = time.monotonic() - started
        if peak_rss_bytes > args.memory_budget_bytes or elapsed > args.time_budget_seconds:
            error = (
                f"peak RSS {peak_rss_bytes / (1024 * 1024):.1f} MB exceeded "
                f"{args.memory_budget_bytes / (1024 * 1024):.0f} MB"
                if peak_rss_bytes > args.memory_budget_bytes
                else f"elapsed {elapsed:.1f}s exceeded {args.time_budget_seconds:.0f}s"
            )
            _write_status(
                args.result_file,
                {
                    "status": "budget",
                    "error": error,
                    "peak_rss_bytes": peak_rss_bytes,
                },
            )
            return 0

        final_report_path = args.output_dir / report_path.name
        report_path.replace(final_report_path)
        review_path.replace(final_review_path)
        _write_status(
            args.result_file,
            {
                "status": "ok",
                "report_path": str(final_report_path),
                "review_path": str(final_review_path),
                "peak_rss_bytes": peak_rss_bytes,
            },
        )
        return 0
    except Exception as exc:
        logger.exception("Weekly report worker failed")
        try:
            _write_status(
                args.result_file,
                {
                    "status": "error",
                    "error": repr(exc),
                    "peak_rss_bytes": _peak_working_set_bytes(),
                },
            )
        except OSError:
            logger.exception("Could not write weekly report worker status")
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--paper-data-dir", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--staging-dir", required=True, type=Path)
    parser.add_argument("--review-staging-path", required=True, type=Path)
    parser.add_argument("--review-final-path", required=True, type=Path)
    parser.add_argument("--days", required=True, type=int)
    parser.add_argument("--result-file", required=True, type=Path)
    parser.add_argument("--memory-budget-bytes", required=True, type=int)
    parser.add_argument("--time-budget-seconds", required=True, type=float)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
    )
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
