#!/usr/bin/env python
"""Compare PAPER decision-writer and tick-callback costs across two revisions."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _read_csv(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed == parsed and abs(parsed) != float("inf") else None


def _restore_nested(value: Any) -> Any:
    if not isinstance(value, str) or not value or value[0] not in "[{":
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _load_decisions(decisions_dir: Path) -> list[dict[str, Any]]:
    import pandas as pd

    frames = [
        pd.read_parquet(path)
        for path in sorted(decisions_dir.glob("decisions_*.parquet"))
    ]
    if not frames:
        raise FileNotFoundError(f"No decisions_*.parquet files in {decisions_dir}")
    frame = pd.concat(frames, ignore_index=True)
    frame = frame[frame["event"].astype(str).eq("bar_decision")]
    frame = frame.sort_values(["timestamp", "ticker"], kind="stable")
    rows = []
    for raw in frame.to_dict(orient="records"):
        row = {}
        for key, value in raw.items():
            if pd.isna(value):
                row[key] = ""
            else:
                row[key] = _restore_nested(value)
        rows.append(row)
    if len(rows) != 10515:
        raise ValueError(f"Expected 10,515 archived bar decisions, found {len(rows)}")
    return rows


def _writer_replay(
    source_root: Path,
    decisions_dir: Path,
    config_path: Path,
    output_dir: Path,
    revision: str,
) -> dict[str, Any]:
    sys.path.insert(0, str(source_root))
    from market_bot.kite_main import KiteTradingBot
    from market_bot.bar_builder import Bar

    rows = _load_decisions(decisions_dir)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    symbols = sorted({str(row.get("ticker") or "") for row in rows})
    config["mode"] = "PAPER"
    config["trading_mode"] = "intraday_options"
    config["instrument_tokens"] = {
        symbol: 900000000 + index for index, symbol in enumerate(symbols)
    }
    config["capture_all_evaluated_contracts"] = False
    config_file = output_dir / "simulation_config.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    os.environ["BOT_SIM_MODE"] = "true"
    os.environ["BOT_SIM_DIR"] = str(output_dir / "simulation")
    os.environ["MODE"] = "PAPER"
    for name in (
        "KITE_API_KEY",
        "KITE_ACCESS_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_TRADE_CHAT_ID",
    ):
        os.environ.pop(name, None)

    bot = KiteTradingBot(str(config_file))
    bot._pending_entry_evaluations = {}

    def to_bar(value: Any) -> Any:
        if not isinstance(value, dict):
            raise ValueError(f"Expected archived bar object, got {type(value).__name__}")
        return Bar(
            timestamp=_parse_timestamp(str(value.get("time") or value.get("timestamp"))),
            open=float(value["open"]),
            high=float(value["high"]),
            low=float(value["low"]),
            close=float(value["close"]),
            volume=int(float(value.get("volume") or 0)),
        )

    journal_closed = False
    try:
        for row in rows:
            symbol = str(row.get("ticker") or "")
            bar = to_bar(row.get("bar"))
            history = [
                to_bar(item)
                for item in row.get("history", [])
                if isinstance(item, dict)
            ]
            score = _number(row.get("score"))
            reasons = row.get("reasons")
            bot._scorer_context_by_symbol[symbol] = {
                "scorer_first_bar_time": row.get("scorer_first_bar_time"),
                "scorer_last_bar_time": row.get("scorer_last_bar_time"),
                "scorer_last_bar_ohlc": row.get("scorer_last_bar_ohlc"),
                "scorer_last_bar_complete": row.get("scorer_last_bar_complete"),
                "scorer_inputs": row.get("scorer_inputs")
                if isinstance(row.get("scorer_inputs"), dict)
                else {},
                "score_components": row.get("score_components")
                if isinstance(row.get("score_components"), dict)
                else {},
                "component_score": row.get("component_score"),
            }
            if isinstance(row.get("entry_evaluation"), dict):
                bot._pending_entry_evaluations[symbol] = row["entry_evaluation"]
            ltp = _number(row.get("signal_ltp") or row.get("signal_premium"))
            if ltp is not None:
                bot.latest_prices[symbol] = ltp
                bot.option_quote_cache[symbol] = {
                    "last_price": ltp,
                    "bid": _number(row.get("signal_bid")) or 0.0,
                    "ask": _number(row.get("signal_ask")) or 0.0,
                    "timestamp": _parse_timestamp(str(row.get("signal_time") or bar.timestamp.isoformat())),
                }
            bot._bar_callback_time = bar.timestamp
            try:
                bot._record_decision(
                    symbol,
                    bar,
                    history,
                    SimpleNamespace(
                        score=int(score) if score is not None else None,
                        signal=str(row.get("signal") or ""),
                        reasons=reasons if isinstance(reasons, list) else [],
                        strategy_variant=str(row.get("strategy_variant") or "primary"),
                    ),
                    str(row.get("signal") or ""),
                    str(row.get("outcome") or ""),
                    strategy_variant=str(row.get("strategy_variant") or "primary"),
                )
            finally:
                bot._bar_callback_time = None
        if not bot.decision_journal.close(timeout=120):
            raise RuntimeError(f"Decision writer did not close cleanly for {revision}")
        journal_closed = True
        if hasattr(bot.trade_journal, "close"):
            bot.trade_journal.close()
    finally:
        if not journal_closed:
            bot.decision_journal.close(timeout=120)
    telemetry = bot.decision_journal.paper_recorder.decision_telemetry()
    jsonl_bytes = bot.decision_journal.path.stat().st_size
    if telemetry.get("drops") or telemetry.get("write_failures"):
        raise RuntimeError(f"Decision writer errors: {telemetry}")
    return {
        "decisions": len(rows),
        "jsonl_bytes": jsonl_bytes,
        "jsonl_bytes_per_decision": jsonl_bytes / len(rows),
        "writer_cpu_ms": telemetry["writer_cpu_ms"],
        "writer_drops": telemetry["drops"],
        "writer_failures": telemetry["write_failures"],
    }


def _load_tick_events(
    quotes_dir: Path, underlying_dir: Path, tick_type: Any
) -> tuple[list[Any], dict[str, int]]:
    symbols: set[str] = set()
    events: list[tuple[datetime, int, int, Any]] = []
    sequence = 0
    quote_rows = 0
    underlying_bars = 0

    for path in sorted(quotes_dir.glob("*.quotes.csv.gz")):
        for row in _read_csv(path):
            symbol = f"{row['underlying']}_{row['leg']}".upper()
            symbols.add(symbol)
            sequence += 1
            stamp = _parse_timestamp(row["time"])
            last_price = _number(row.get("ltp"))
            if last_price is None or last_price <= 0:
                continue
            tick = tick_type(
                instrument_token=0,
                timestamp=stamp,
                last_price=last_price,
                bid=_number(row.get("bid")) or 0.0,
                ask=_number(row.get("ask")) or 0.0,
                volume=0,
            )
            events.append((stamp, 1, sequence, (symbol, tick)))
            quote_rows += 1

    for path in sorted(underlying_dir.glob("*.candles.csv")):
        for row in _read_csv(path):
            symbol = str(row["symbol"]).upper()
            symbols.add(symbol)
            start = _parse_timestamp(row["candle_start_time"])
            values = [
                _number(row.get(name))
                for name in ("open", "high", "low", "close")
            ]
            if any(value is None or value <= 0 for value in values):
                continue
            for offset, price in zip((5, 20, 35, 50), values):
                sequence += 1
                stamp = start + timedelta(seconds=offset)
                tick = tick_type(
                    instrument_token=0,
                    timestamp=stamp,
                    last_price=float(price),
                    bid=float(price),
                    ask=float(price),
                    volume=0,
                )
                events.append((stamp, 0, sequence, (symbol, tick)))
            underlying_bars += 1

    token_map = {
        symbol: 900000000 + index
        for index, symbol in enumerate(sorted(symbols))
    }
    for index, (_, _, _, item) in enumerate(events):
        symbol, tick = item
        events[index] = (
            events[index][0],
            events[index][1],
            events[index][2],
            (symbol, tick_type(
                instrument_token=token_map[symbol],
                timestamp=tick.timestamp,
                last_price=tick.last_price,
                bid=tick.bid,
                ask=tick.ask,
                volume=tick.volume,
                oi=tick.oi,
                iv=tick.iv,
            )),
        )
    events.sort(key=lambda event: (event[0], event[1], event[2]))
    return [event[3] for event in events], {
        "quote_rows": quote_rows,
        "underlying_bars": underlying_bars,
        "callback_events": len(events),
        "symbols": len(symbols),
    }


def _tick_replay(
    source_root: Path,
    quotes_dir: Path,
    underlying_dir: Path,
    config_path: Path,
    output_dir: Path,
    revision: str,
) -> dict[str, Any]:
    sys.path.insert(0, str(source_root))
    from market_bot.kite_main import KiteTradingBot
    from market_bot.kite_provider import Tick

    events, counts = _load_tick_events(quotes_dir, underlying_dir, Tick)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    underlying_symbols = sorted(
        symbol
        for symbol in config.get("options_underlyings", [])
        if any(event_symbol.startswith(f"{symbol}_") for event_symbol, _ in events)
    )
    config["mode"] = "PAPER"
    config["trading_mode"] = "intraday_options"
    config["futures_underlyings"] = []
    config["options_underlyings"] = underlying_symbols
    config["instrument_tokens"] = {
        event_symbol: tick.instrument_token
        for event_symbol, tick in events
    }
    config["capture_all_evaluated_contracts"] = False
    config_file = output_dir / "simulation_config.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    env = os.environ
    env["BOT_SIM_MODE"] = "true"
    env["BOT_SIM_DIR"] = str(output_dir / "simulation")
    env["MODE"] = "PAPER"
    for name in (
        "KITE_API_KEY",
        "KITE_ACCESS_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_TRADE_CHAT_ID",
    ):
        env.pop(name, None)

    bot = KiteTradingBot(str(config_file))
    durations = []
    journal_closed = False
    try:
        for symbol, tick in events:
            bot.symbol_map[tick.instrument_token] = symbol
            started = time.perf_counter()
            bot._on_tick(tick)
            durations.append(time.perf_counter() - started)
        if not bot.decision_journal.close(timeout=120):
            raise RuntimeError(f"Decision journal did not close cleanly for {revision}")
        journal_closed = True
        if hasattr(bot.trade_journal, "close"):
            bot.trade_journal.close()
    finally:
        if not journal_closed:
            bot.decision_journal.close(timeout=120)
    counts["callback_max_ms"] = max(durations) * 1000 if durations else 0.0
    counts["callback_p95_ms"] = (
        sorted(durations)[int((len(durations) - 1) * 0.95)] * 1000
        if durations
        else 0.0
    )
    counts["callback_p99_ms"] = (
        sorted(durations)[int((len(durations) - 1) * 0.99)] * 1000
        if durations
        else 0.0
    )
    return counts


def _worker(args: argparse.Namespace) -> None:
    source_root = Path(args.source_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "revision": args.revision,
        "writer": _writer_replay(
            source_root,
            Path(args.decisions_dir).resolve(),
            Path(args.config).resolve(),
            output_dir / "writer",
            args.revision,
        ),
        "ticks": _tick_replay(
            source_root,
            Path(args.quotes_dir).resolve(),
            Path(args.underlying_dir).resolve(),
            Path(args.config).resolve(),
            output_dir / "ticks",
            args.revision,
        ),
    }
    print(json.dumps(result, indent=2))


def _run_revision(
    script: Path,
    source_root: Path,
    repo_root: Path,
    output_dir: Path,
    revision: str,
    data_paths: dict[str, Path],
) -> dict[str, Any]:
    command = [
            sys.executable,
            str(script),
            "--worker",
            "--source-root",
            str(source_root),
            "--repo-root",
            str(repo_root),
            "--output-dir",
            str(output_dir),
            "--revision",
            revision,
            "--decisions-dir",
            str(data_paths["decisions"]),
            "--quotes-dir",
            str(data_paths["quotes"]),
            "--underlying-dir",
            str(data_paths["underlying"]),
            "--config",
            str(data_paths["config"]),
        ]
    try:
        result = subprocess.run(
            command,
            cwd=str(source_root),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"Worker failed for {revision}:\n{error.stdout}\n{error.stderr}"
        ) from error
    return json.loads(result.stdout)


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline")
    parser.add_argument("--final")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--source-root")
    parser.add_argument("--output-dir")
    parser.add_argument("--revision")
    parser.add_argument("--decisions-dir")
    parser.add_argument("--quotes-dir")
    parser.add_argument("--underlying-dir")
    parser.add_argument("--config")
    args = parser.parse_args()
    if args.worker:
        _worker(args)
        return
    if not args.baseline or not args.final:
        parser.error("--baseline and --final are required")
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    repo_root = Path(args.repo_root).resolve()
    data_paths = {
        "decisions": repo_root
        / "paper_trading_data"
        / "2026-11"
        / "week_46"
        / "day_12"
        / "decisions",
        "quotes": repo_root / "paper_trading_data" / "option_candles" / "2026-11-12",
        "underlying": repo_root / "paper_trading_data" / "underlying_candles" / "2026-11-12",
        "config": repo_root / "kite_config.json",
    }
    temp_root = Path(tempfile.mkdtemp(prefix="gate-state-replay-"))
    worktrees: list[Path] = []
    results = []
    baseline_worktree = temp_root / "baseline"
    final_worktree = temp_root / "final"
    try:
        for worktree, revision in (
            (baseline_worktree, args.baseline),
            (final_worktree, args.final),
        ):
            subprocess.run(
                [
                    "git",
                    "worktree",
                    "add",
                    "--detach",
                    str(worktree),
                    revision,
                ],
                cwd=str(repo_root),
                check=True,
                capture_output=True,
                text=True,
            )
            worktrees.append(worktree)
        for index in range(args.repeats):
            results.append(
                {
                    "group": "comparison",
                    "label": "baseline",
                    "iteration": index + 1,
                    **_run_revision(
                        Path(__file__).resolve(),
                        baseline_worktree,
                        repo_root,
                        temp_root / f"output-baseline-{index + 1}",
                        args.baseline,
                        data_paths,
                    ),
                }
            )
            results.append(
                {
                    "group": "comparison",
                    "label": "final",
                    "iteration": index + 1,
                    **_run_revision(
                        Path(__file__).resolve(),
                        final_worktree,
                        repo_root,
                        temp_root / f"output-final-{index + 1}",
                        args.final,
                        data_paths,
                    ),
                }
            )
            results.append(
                {
                    "group": "aa_noise",
                    "label": "baseline",
                    "iteration": index + 1,
                    **_run_revision(
                        Path(__file__).resolve(),
                        baseline_worktree,
                        repo_root,
                        temp_root / f"output-aa-{index + 1}-a",
                        args.baseline,
                        data_paths,
                    ),
                }
            )
            results.append(
                {
                    "group": "aa_noise",
                    "label": "baseline",
                    "iteration": index + 1,
                    **_run_revision(
                        Path(__file__).resolve(),
                        baseline_worktree,
                        repo_root,
                        temp_root / f"output-aa-{index + 1}-b",
                        args.baseline,
                        data_paths,
                    ),
                }
            )

        def summarize(group: str, label: str | None, metrics: tuple[str, ...]) -> dict[str, Any]:
            selected = [
                result
                for result in results
                if result["group"] == group
                and (label is None or result["label"] == label)
            ]
            summaries = {}
            for metric in metrics:
                values = [
                    result["writer"][metric]
                    if metric.startswith("jsonl_") or metric == "writer_cpu_ms"
                    else result["ticks"][metric]
                    for result in selected
                ]
                summaries[metric] = {
                    "median": statistics.median(values),
                    "min": min(values),
                    "max": max(values),
                }
            return {"runs": len(selected), "metrics": summaries}

        output = {
            "run_order": [
                f'{result["group"]}:{result["label"]}:{result["iteration"]}'
                for result in results
            ],
            "comparison": {
                label: summarize(
                    "comparison",
                    label,
                    (
                        "jsonl_bytes_per_decision",
                        "writer_cpu_ms",
                        "callback_p95_ms",
                        "callback_p99_ms",
                    ),
                )
                for label in ("baseline", "final")
            },
            "aa_noise": summarize(
                "aa_noise",
                None,
                ("writer_cpu_ms", "callback_p95_ms", "callback_p99_ms"),
            ),
            "comparison_runs": [
                {
                    "label": result["label"],
                    "iteration": result["iteration"],
                    "callback_max_ms": result["ticks"]["callback_max_ms"],
                }
                for result in results
                if result["group"] == "comparison"
            ],
            "aa_runs": [
                {
                    "iteration": result["iteration"],
                    "writer_cpu_ms": result["writer"]["writer_cpu_ms"],
                    "callback_p95_ms": result["ticks"]["callback_p95_ms"],
                    "callback_p99_ms": result["ticks"]["callback_p99_ms"],
                }
                for result in results
                if result["group"] == "aa_noise"
            ],
        }
        print(json.dumps(output, indent=2))
    finally:
        for worktree in reversed(worktrees):
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=str(repo_root),
                check=False,
                capture_output=True,
                text=True,
            )
        import shutil

        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    _main()
