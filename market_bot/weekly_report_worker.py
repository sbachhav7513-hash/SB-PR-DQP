from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Iterator, Sequence

from .reporting_metrics import ReportingBudgetExceeded, _peak_working_set_bytes
from .weekly_report import (
    build_weekly_report,
    write_weekly_report,
    write_weekly_review,
)


logger = logging.getLogger(__name__)


@contextmanager
def _worker_lock(path: Path) -> Iterator[None]:
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("Another weekly report worker is active") from exc
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Another weekly report worker is active") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_status(path: Path, result: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(result), encoding="utf-8")
    temporary.replace(path)


def _remove_stale_staging_files(args: argparse.Namespace) -> None:
    current_report_stage = args.staging_dir.resolve()
    for path in args.output_dir.glob(".weekly_report_stage_*"):
        if path.resolve() == current_report_stage:
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()

    current_review_stage = args.review_staging_path.resolve()
    for path in args.review_final_path.parent.glob(".weekly_review_stage_*"):
        if path.resolve() != current_review_stage:
            path.unlink()


def _run_locked(args: argparse.Namespace) -> int:
    started = time.monotonic()
    previous_budget = os.environ.get("WEEKLY_REPORT_MEMORY_BUDGET_BYTES")
    os.environ["WEEKLY_REPORT_MEMORY_BUDGET_BYTES"] = str(
        args.memory_budget_bytes
    )
    try:
        _remove_stale_staging_files(args)
        report = build_weekly_report(
            data_dir=args.data_dir,
            paper_data_dir=args.paper_data_dir,
            days=args.days,
            hourly_decisions_only=True,
        )
        peak_rss_bytes = _peak_working_set_bytes()
        elapsed = time.monotonic() - started
        if peak_rss_bytes > args.memory_budget_bytes:
            error = (
                f"step=weekly_report_build peak RSS "
                f"{peak_rss_bytes / (1024 * 1024):.1f} MB exceeded "
                f"{args.memory_budget_bytes / (1024 * 1024):.0f} MB"
            )
            logger.error("Weekly report memory budget exceeded: %s", error)
            _write_status(
                args.result_file,
                {
                    "status": "budget",
                    "error": error,
                    "peak_rss_bytes": peak_rss_bytes,
                },
            )
            return 2
        if elapsed > args.time_budget_seconds:
            error = (
                f"elapsed {elapsed:.1f}s exceeded "
                f"{args.time_budget_seconds:.0f}s"
            )
            logger.error("Weekly report time budget exceeded: %s", error)
            _write_status(
                args.result_file,
                {
                    "status": "budget",
                    "error": error,
                    "peak_rss_bytes": peak_rss_bytes,
                },
            )
            return 2

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
                f"step=weekly_report_finalize peak RSS "
                f"{peak_rss_bytes / (1024 * 1024):.1f} MB exceeded "
                f"{args.memory_budget_bytes / (1024 * 1024):.0f} MB"
                if peak_rss_bytes > args.memory_budget_bytes
                else f"elapsed {elapsed:.1f}s exceeded {args.time_budget_seconds:.0f}s"
            )
            logger.error("Weekly report budget exceeded: %s", error)
            _write_status(
                args.result_file,
                {
                    "status": "budget",
                    "error": error,
                    "peak_rss_bytes": peak_rss_bytes,
                },
            )
            return 2

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
    except ReportingBudgetExceeded as exc:
        logger.error("Weekly report memory budget exceeded: %s", exc)
        try:
            _write_status(
                args.result_file,
                {
                    "status": "budget",
                    "step": exc.step,
                    "error": str(exc),
                    "peak_rss_bytes": exc.peak_rss_bytes,
                },
            )
        except OSError:
            logger.exception("Could not write weekly report budget status")
        return 2
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
    finally:
        if previous_budget is None:
            os.environ.pop("WEEKLY_REPORT_MEMORY_BUDGET_BYTES", None)
        else:
            os.environ["WEEKLY_REPORT_MEMORY_BUDGET_BYTES"] = previous_budget


def _run(args: argparse.Namespace) -> int:
    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        lock_path = args.review_final_path.parent / ".weekly_report_worker.lock"
        with _worker_lock(lock_path):
            return _run_locked(args)
    except Exception as exc:
        logger.exception("Could not start weekly report worker: %s", exc)
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


def _apply_address_space_limit(memory_budget_bytes: int) -> None:
    if os.name != "posix":
        return
    import resource

    _soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_AS)
    limit = memory_budget_bytes
    if hard_limit != resource.RLIM_INFINITY:
        limit = min(limit, hard_limit)
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


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
    try:
        _apply_address_space_limit(args.memory_budget_bytes)
    except (OSError, ValueError) as exc:
        logger.exception("Could not enforce weekly report address-space limit")
        return 1
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
