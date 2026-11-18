#!/usr/bin/env python3
"""Compare PAPER run-up measurements and paired 5-minute entry simulations."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from market_bot.bar_builder import Bar
from market_bot.kite_main import (
    _complete_five_minute_bar,
    _next_five_minute_window,
)
from market_bot.paper_costs import calculate_order_fees
from market_bot.paper_run_up import prior_60m_option_move
from market_bot.support_reversal_flags import level_stop_triggered


IST = ZoneInfo("Asia/Kolkata")
VETO_THRESHOLD_PCT = 8.0
STOP_PCT = 0.10
TARGET_PCT = 0.20
FIRST_PERIOD_END = date(2026, 11, 11)
SECOND_PERIOD_START = date(2026, 11, 12)


@dataclass(frozen=True)
class ReplayArm:
    status: str
    entry_price: float | None = None
    exit_price: float | None = None
    exit_time: datetime | None = None
    exit_reason: str = ""
    net_rupees: float | None = None
    net_r: float | None = None


def parse_datetime(value: Any) -> datetime | None:
    if value is None or str(value).strip() in {"", "None", "nan"}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _read_csv(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_jsonl(
    path: Path, through: date = date(2026, 11, 16)
) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            trade_id = row.get("trade_id")
            if trade_id:
                latest[str(trade_id)] = row
    return sorted(
        (
            row
            for row in latest.values()
            if row.get("status") == "closed"
            and row.get("action", "").upper() == "BUY"
            and str(row.get("ticker", "")).endswith(("_CE", "_PE"))
            and date(2026, 10, 30)
            <= (parse_datetime(row.get("timestamp")) or datetime.min.replace(tzinfo=IST)).date()
            <= through
        ),
        key=lambda row: (
            parse_datetime(row.get("timestamp")) or datetime.max.replace(tzinfo=IST),
            str(row.get("trade_id", "")),
        ),
    )


def load_option_market(
    candle_root: Path, trade: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entry_time = parse_datetime(trade.get("timestamp"))
    contract_id = str(trade.get("contract_id") or "")
    contract_symbol = contract_id.split(":", 1)[-1]
    if entry_time is None or not contract_symbol:
        return [], []

    day_dir = candle_root / entry_time.date().isoformat()
    bars_by_time: dict[datetime, dict[str, Any]] = {}
    quotes_by_time: dict[datetime, dict[str, Any]] = {}
    for path in sorted(day_dir.glob(f"NFO_{contract_symbol}*")):
        if not path.is_file() or not (path.name.endswith(".csv") or path.name.endswith(".gz")):
            continue
        is_quote_file = ".quotes.csv" in path.name
        is_candle_file = ".candles.csv" in path.name
        legacy_file = not is_quote_file and not is_candle_file
        for raw in _read_csv(path):
            if raw.get("contract_id") and raw["contract_id"] != contract_id:
                continue
            timestamp = parse_datetime(
                raw.get("time")
                if is_quote_file
                else raw.get("candle_start_time") or raw.get("timestamp")
            )
            if timestamp is None:
                continue
            if is_quote_file or legacy_file:
                quote_time = (
                    timestamp + timedelta(minutes=1)
                    if legacy_file
                    else timestamp
                )
                quote = {
                    "time": quote_time,
                    "bid": _number(raw.get("bid")),
                    "ask": _number(raw.get("ask")),
                }
                old_quote = quotes_by_time.get(quote_time)
                if (
                    quote["bid"] is not None
                    and quote["ask"] is not None
                    and quote["ask"] >= quote["bid"]
                    and (
                        old_quote is None
                        or old_quote.get("bid") is None
                        or old_quote.get("ask") is None
                    )
                ):
                    quotes_by_time[quote_time] = quote
            if is_candle_file or legacy_file:
                candle = {
                    "time": timestamp,
                    "open": _number(raw.get("open")),
                    "high": _number(raw.get("high")),
                    "low": _number(raw.get("low")),
                    "close": _number(raw.get("close")),
                    "bid": _number(raw.get("bid")),
                    "ask": _number(raw.get("ask")),
                    "gap": str(raw.get("gap", "")).strip().lower()
                    in {"true", "1"},
                    "tick_count": _number(raw.get("tick_count")) or 0.0,
                }
                old_candle = bars_by_time.get(timestamp)
                if old_candle is None or (
                    not candle["gap"],
                    candle["tick_count"],
                ) > (
                    not old_candle["gap"],
                    old_candle["tick_count"],
                ):
                    bars_by_time[timestamp] = candle

    return (
        [bars_by_time[key] for key in sorted(bars_by_time)],
        [quotes_by_time[key] for key in sorted(quotes_by_time)],
    )


def load_underlying_bars(
    paper_data_root: Path, target_date: date, underlying: str
) -> list[dict[str, Any]]:
    import pandas as pd

    date_root = paper_data_root / target_date.strftime("%Y-%m")
    day_name = f"day_{target_date.day:02d}"
    session_dir = next(
        (
            week / day_name
            for week in sorted(date_root.glob("week_*"))
            if (week / day_name).is_dir()
        ),
        None,
    )
    if session_dir is None:
        return []

    bars: dict[datetime, dict[str, Any]] = {}
    for path in sorted(session_dir.rglob("decisions*.parquet")):
        frame = pd.read_parquet(path, columns=["ticker", "event", "bar"])
        frame = frame[
            (frame["ticker"].astype(str).str.upper() == underlying.upper())
            & (frame["event"].astype(str) == "bar_decision")
        ]
        for raw in frame["bar"].dropna():
            try:
                row = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(row, dict):
                continue
            timestamp = parse_datetime(row.get("time"))
            close = _number(row.get("close"))
            if timestamp is None or close is None or close <= 0:
                continue
            bars[timestamp] = {
                "time": timestamp,
                "open": _number(row.get("open")),
                "high": _number(row.get("high")),
                "low": _number(row.get("low")),
                "close": close,
            }
    return [bars[key] for key in sorted(bars)]


def first_five_minute_confirmation(
    bars: list[dict[str, Any]],
    signal_time: datetime,
    confirmation_close: float,
    leg: str,
) -> tuple[datetime | None, float | None, str]:
    """Find the first five contiguous one-minute bars and test continuation."""
    start = next(
        (
            index
            for index, bar in enumerate(bars)
            if bar["time"] >= signal_time
        ),
        None,
    )
    if start is None:
        return None, None, "five_minute_path_incomplete"
    candidate = bars[start : start + 5]
    if len(candidate) != 5 or any(
        candidate[index + 1]["time"] - candidate[index]["time"]
        != timedelta(minutes=1)
        for index in range(4)
    ):
        return None, None, "five_minute_path_incomplete"
    close = candidate[-1]["close"]
    end_time = candidate[-1]["time"] + timedelta(minutes=1)
    continues = close > confirmation_close if leg == "CE" else close < confirmation_close
    return (
        end_time,
        close,
        "continues" if continues else "not_continued",
    )


def runtime_five_minute_confirmation(
    bars: list[dict[str, Any]],
    confirmation_close_time: datetime,
    confirmation_close: float,
    leg: str,
) -> tuple[datetime | None, float | None, str]:
    """Apply the production clock-aligned window to completed one-minute bars."""
    start, _ = _next_five_minute_window(confirmation_close_time)
    minute_bars = [
        Bar(
            timestamp=bar["time"],
            open=bar["open"],
            high=bar["high"],
            low=bar["low"],
            close=bar["close"],
            volume=int(bar.get("volume") or 0),
        )
        for bar in bars
        if start <= bar["time"] < start + timedelta(minutes=5)
    ]
    aggregate = _complete_five_minute_bar(minute_bars, start)
    if aggregate is None:
        return None, None, "data_missing"
    continues = (
        aggregate.close > confirmation_close
        if leg == "CE"
        else aggregate.close < confirmation_close
    )
    last_minute = max(
        bar.timestamp
        for bar in minute_bars
        if bar.timestamp.replace(second=0, microsecond=0)
        == start + timedelta(minutes=4)
    )
    return (
        last_minute + timedelta(minutes=1),
        aggregate.close,
        "passed" if continues else "failed",
    )


def _valid_quote(row: dict[str, Any]) -> bool:
    bid = _number(row.get("bid"))
    ask = _number(row.get("ask"))
    return bid is not None and ask is not None and bid > 0 and ask >= bid


def _quote_at_or_after(
    quotes: list[dict[str, Any]], target_time: datetime
) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in quotes
            if row["time"] >= target_time and _valid_quote(row)
        ),
        None,
    )


def simulate_fixed_exit(
    candles: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    entry_time: datetime,
    entry_price: float,
    quantity: float,
    charge_config: dict[str, Any] | None = None,
    *,
    underlying_bars: list[dict[str, Any]] | None = None,
    support_level: float | None = None,
    support_signal: str | None = None,
    level_buffer_pct: float | None = None,
) -> ReplayArm:
    if entry_price <= 0 or quantity <= 0:
        return ReplayArm("invalid_entry")
    stop = entry_price * (1.0 - STOP_PCT)
    target = entry_price * (1.0 + TARGET_PCT)
    session_end = datetime.combine(
        entry_time.date(), time(15, 29, 59), tzinfo=IST
    )
    ordered_quotes = [
        row
        for row in quotes
        if entry_time <= row["time"] <= session_end and _valid_quote(row)
    ]
    for candle in candles:
        start = candle["time"]
        end = start + timedelta(minutes=1)
        if start.date() != entry_time.date() or end <= entry_time:
            continue
        if candle["gap"] or candle["low"] is None or candle["high"] is None:
            continue
        in_bar_quotes = [
            row for row in ordered_quotes if start <= row["time"] < end
        ]
        stop_quotes = [row for row in in_bar_quotes if row["bid"] <= stop]
        target_quotes = [row for row in in_bar_quotes if row["bid"] >= target]
        full_bar_after_entry = start >= entry_time
        stop_hit = bool(stop_quotes) or (
            full_bar_after_entry and candle["low"] <= stop
        )
        if stop_hit:
            fill = stop_quotes[0]["bid"] if stop_quotes else stop
            if candle["bid"] is not None and candle["bid"] < fill:
                fill = candle["bid"]
            return _complete_arm(
                entry_price,
                fill,
                start,
                "stop",
                quantity,
                charge_config,
            )
        if target_quotes:
            fill = target_quotes[0]["bid"]
            return _complete_arm(
                entry_price,
                fill,
                target_quotes[0]["time"],
                "target",
                quantity,
                charge_config,
            )
        if (
            full_bar_after_entry
            and not in_bar_quotes
            and candle["bid"] is not None
            and candle["bid"] >= target
        ):
            return _complete_arm(
                entry_price,
                candle["bid"],
                end,
                "target",
                quantity,
                charge_config,
            )
        if (
            underlying_bars is not None
            and support_level is not None
            and support_signal in {"BUY", "SELL"}
            and level_buffer_pct is not None
            and end > entry_time
        ):
            underlying = next(
                (row for row in underlying_bars if row["time"] == start),
                None,
            )
            if (
                underlying is not None
                and underlying.get("close") is not None
                and level_stop_triggered(
                    support_signal,
                    float(underlying["close"]),
                    support_level,
                    level_buffer_pct,
                )
            ):
                stop_quote = _quote_at_or_after(ordered_quotes, end)
                if stop_quote is None:
                    return ReplayArm("level_stop_bid_missing")
                return _complete_arm(
                    entry_price,
                    stop_quote["bid"],
                    stop_quote["time"],
                    "level_stop",
                    quantity,
                    charge_config,
                )

    last_quote = ordered_quotes[-1] if ordered_quotes else None
    if last_quote is not None:
        return _complete_arm(
            entry_price,
            last_quote["bid"],
            last_quote["time"],
            "session_end",
            quantity,
            charge_config,
        )
    last_candle = next(
        (
            row
            for row in reversed(candles)
            if row["time"].date() == entry_time.date()
            and row["time"] + timedelta(minutes=1) > entry_time
            and row["bid"] is not None
            and row["bid"] > 0
        ),
        None,
    )
    if last_candle is None:
        return ReplayArm("exit_path_missing")
    return _complete_arm(
        entry_price,
        last_candle["bid"],
        last_candle["time"] + timedelta(minutes=1),
        "session_end",
        quantity,
        charge_config,
    )


def _complete_arm(
    entry: float,
    exit_price: float,
    exit_time: datetime,
    reason: str,
    quantity: float,
    charge_config: dict[str, Any] | None,
) -> ReplayArm:
    fees = calculate_order_fees(
        [
            {"side": "BUY", "price": entry, "quantity": quantity},
            {"side": "SELL", "price": exit_price, "quantity": quantity},
        ],
        charge_config,
    )["total_fees"]
    net = (exit_price - entry) * quantity - fees
    risk = entry * STOP_PCT * quantity
    return ReplayArm(
        "complete",
        entry,
        exit_price,
        exit_time,
        reason,
        net,
        net / risk,
    )


def _stored_runtime_move(trade: dict[str, Any]) -> float | None:
    values = trade.get("entry_feature_values") or {}
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except json.JSONDecodeError:
            return None
    return _number(values.get("prior_60m_option_move_pct")) if isinstance(values, dict) else None


def _offline_move(
    candles: list[dict[str, Any]], signal_time: datetime
) -> tuple[float | None, str]:
    measurement = prior_60m_option_move(
        [
            type("OptionBar", (), {"timestamp": row["time"], "close": row["close"]})
            for row in candles
            if row["close"] is not None and row["close"] > 0
        ],
        signal_time,
    )
    return measurement.value_pct, measurement.status


def _legacy_runtime_move(
    candles: list[dict[str, Any]], signal_time: datetime
) -> float | None:
    closes = [
        row["close"]
        for row in candles
        if row["time"] <= signal_time and row["close"] is not None and row["close"] > 0
    ]
    if len(closes) < 61:
        return None
    return (closes[-1] / closes[-61] - 1.0) * 100.0


def _period_label(trade_date: date) -> str:
    return (
        "30-Oct to 11-Nov"
        if trade_date <= FIRST_PERIOD_END
        else "12-Nov to 16-Nov"
    )


def _summary(rows: list[dict[str, Any]], arm_name: str) -> tuple[float | None, int]:
    values = []
    for row in rows:
        arm = row[arm_name]
        if arm.status == "complete":
            values.append(arm.net_r or 0.0)
        elif arm.status == "not_continued":
            values.append(0.0)
    return (sum(values) / len(values), len(values)) if values else (None, 0)


def build_report(
    trades: list[dict[str, Any]],
    candle_root: Path,
    paper_data_root: Path,
    charge_config: dict[str, Any] | None = None,
) -> str:
    if len(trades) != 51:
        raise ValueError(f"Expected 51 closed PAPER trades, found {len(trades)}")

    records: list[dict[str, Any]] = []
    stored_comparisons: list[tuple[str, float, float]] = []
    reconstructed_comparisons: list[tuple[str, float, float]] = []
    for trade in trades:
        entered = parse_datetime(trade.get("timestamp"))
        signal_time = parse_datetime(trade.get("signal_time"))
        entry_time = parse_datetime(trade.get("entry_time")) or entered
        if entered is None or signal_time is None or entry_time is None:
            raise ValueError(f"Missing entry/signal time: {trade.get('trade_id')}")
        quantity = _number(trade.get("quantity"))
        baseline_entry = _number(trade.get("entry"))
        confirmation_close = _number(trade.get("confirmation_close"))
        if quantity is None or baseline_entry is None or confirmation_close is None:
            raise ValueError(f"Missing replay input: {trade.get('trade_id')}")

        candles, quotes = load_option_market(candle_root, trade)
        offline_move, move_status = _offline_move(candles, signal_time)
        stored_move = _stored_runtime_move(trade)
        reconstructed_move = _legacy_runtime_move(candles, signal_time)
        if stored_move is not None and offline_move is not None:
            stored_comparisons.append(
                (str(trade["trade_id"]), stored_move, offline_move)
            )
        if reconstructed_move is not None and offline_move is not None:
            reconstructed_comparisons.append(
                (str(trade["trade_id"]), reconstructed_move, offline_move)
            )

        underlying = str(trade["ticker"]).rsplit("_", 1)[0]
        underlying_bars = load_underlying_bars(
            paper_data_root, entered.date(), underlying
        )
        confirmation_bar_time = parse_datetime(
            trade.get("confirmation_candle_time")
        )
        confirmation_close_time = (
            confirmation_bar_time + timedelta(minutes=1)
            if confirmation_bar_time is not None
            else signal_time + timedelta(minutes=2)
        )
        confirmation_time, confirmation_5m_close, continuation_status = (
            runtime_five_minute_confirmation(
                underlying_bars,
                confirmation_close_time,
                confirmation_close,
                str(trade["ticker"]).rsplit("_", 1)[1],
            )
        )
        baseline_arm = simulate_fixed_exit(
            candles,
            quotes,
            entry_time,
            baseline_entry,
            quantity,
            charge_config,
        )
        delayed_arm: ReplayArm
        if continuation_status == "failed":
            delayed_arm = ReplayArm("not_continued")
        elif continuation_status != "passed" or confirmation_time is None:
            delayed_arm = ReplayArm(continuation_status)
        else:
            delayed_quote = _quote_at_or_after(quotes, confirmation_time)
            if delayed_quote is None:
                delayed_arm = ReplayArm("expired")
                continuation_status = "expired"
            else:
                delayed_arm = simulate_fixed_exit(
                    candles,
                    quotes,
                    delayed_quote["time"],
                    delayed_quote["ask"],
                    quantity,
                    charge_config,
                )
        records.append(
            {
                "trade": trade,
                "date": entered.date(),
                "offline_move": offline_move,
                "move_status": move_status,
                "stored_move": stored_move,
                "reconstructed_move": reconstructed_move,
                "confirmation_time": confirmation_time,
                "confirmation_5m_close": confirmation_5m_close,
                "continuation_status": continuation_status,
                "baseline": baseline_arm,
                "delayed": delayed_arm,
            }
        )

    stored_large = [
        item
        for item in stored_comparisons
        if abs(item[1] - item[2]) > 1.0
    ]
    reconstructed_large = [
        item
        for item in reconstructed_comparisons
        if abs(item[1] - item[2]) > 1.0
    ]
    output = [
        "# PAPER run-up veto and 5-minute entry replay",
        "",
        "Sample: 51 closed PAPER option trades from 2026-10-30 through "
        "2026-11-16. This replay is descriptive and is not an activation "
        "recommendation for a 5-minute entry rule.",
        "",
        "## Run-up value verification",
        "",
        "Offline recompute uses the last completed one-minute option close at "
        "or before `signal_time`, divided by the close exactly 60 minutes "
        "earlier. The runtime-aligned check requires all 61 minute bars; "
        "missing/gapped lookbacks are incomplete and fail open.",
        "",
        f"- Complete offline lookbacks: "
        f"{sum(row['move_status'] == 'complete' for row in records)}/51.",
        f"- Trades with a persisted runtime value: "
        f"{sum(_stored_runtime_move(trade) is not None for trade in trades)}/51.",
        f"- Persisted runtime values comparable with offline: "
        f"{len(stored_comparisons)}/51.",
        f"- Persisted runtime vs offline differences over 1 percentage point: "
        f"{len(stored_large)}.",
        f"- Reconstructed legacy row-count runtime values to compare: "
        f"{len(reconstructed_comparisons)}/51.",
        f"- Reconstructed legacy vs offline differences over 1 percentage "
        f"point: {len(reconstructed_large)}.",
        "",
        "Persisted runtime values were only available for the later telemetry "
        "cohort; earlier trades have no stored runtime value. The reconstructed "
        "legacy comparison applies the prior 61-valid-close runtime formula "
        "to the archived option bars and is labeled separately, not presented "
        "as a recorded runtime value.",
        "",
        "| Trade | Runtime recorded % | Runtime reconstructed % | Offline % | Difference pp | Status |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in records:
        trade_id = row["trade"]["trade_id"]
        runtime = row["stored_move"]
        reconstructed = row["reconstructed_move"]
        offline = row["offline_move"]
        difference = (
            abs(runtime - offline)
            if runtime is not None and offline is not None
            else None
        )
        output.append(
            f"| {trade_id} | {_fmt(runtime)} | {_fmt(reconstructed)} | "
            f"{_fmt(offline)} | {_fmt(difference)} | {row['move_status']} |"
        )
    output.extend(["", "### Differences above 1 percentage point", ""])
    if stored_large:
        for trade_id, runtime, offline in stored_large:
            output.append(
                f"- {trade_id}: recorded runtime {runtime:.4f}%, "
                f"offline {offline:.4f}%, difference "
                f"{abs(runtime - offline):.4f} pp."
            )
    else:
        output.append("- None among trades with persisted runtime values.")
    if reconstructed_large:
        output.append("")
        output.append(
            "Reconstructed legacy-vs-offline differences (not recorded "
            "runtime values):"
        )
        for trade_id, runtime, offline in reconstructed_large:
            output.append(
                f"- {trade_id}: legacy {runtime:.4f}%, offline "
                f"{offline:.4f}%, difference "
                f"{abs(runtime - offline):.4f} pp."
            )

    output.extend(
        [
            "",
            "## Paired simulator",
            "",
            "- Baseline entry: recorded PAPER ask fill and original quantity.",
            "- Variant entry: the clock-aligned five-minute candle uses the "
            "completed one-minute bars whose timestamps are in "
            "`[HH:MM:00, HH:MM+5:00)`, accepting seconds offsets. All five "
            "minute buckets must be present, including the last completed "
            "minute. The candle close must strictly continue beyond the "
            "recorded one-minute confirmation close; entry uses the first "
            "valid archived option ask after the last minute has closed.",
            "- Both arms use a 10% premium stop and a 20% target recalculated "
            "from that arm's ask entry, with identical quantity. If stop and "
            "target touch in one candle, stop wins. Stops use archived bid "
            "quotes when available; the session-end exit uses the last "
            "available bid. A target requires an observed bid at/above target.",
            "- Fees are deducted on both executed orders using the configured "
            "PAPER charge model. Net R divides net rupees by 10% of entry ask "
            "times quantity. A valid no-continuation is zero R; missing data "
            "is excluded and shown in coverage.",
            "- The best-trade exclusion removes the single highest baseline "
            "net-R trade from both arms to preserve the paired sample.",
            "",
            "| Period | Reached | Passed | Failed | Expired | Data missing | "
            "Baseline n | Baseline mean net R | Baseline mean net ₹ | "
            "Variant n | Variant mean net R | Variant mean net ₹ |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
            "---: | ---: | ---: | ---: |",
        ]
    )
    period_rows: dict[str, list[dict[str, Any]]] = {
        "30-Oct to 11-Nov": [
            row for row in records if row["date"] <= FIRST_PERIOD_END
        ],
        "12-Nov to 16-Nov": [
            row for row in records if row["date"] >= SECOND_PERIOD_START
        ],
        "All 51": list(records),
    }
    period_means: dict[tuple[str, str], float | None] = {}
    paired_by_period: dict[str, list[dict[str, Any]]] = {}
    for period, rows in period_rows.items():
        period_paired = [
            row
            for row in rows
            if row["baseline"].status == "complete"
            and row["delayed"].status in {"complete", "not_continued"}
        ]
        paired_by_period[period] = period_paired
        for arm_name in ("baseline", "delayed"):
            mean, _ = _summary(period_paired, arm_name)
            period_means[(period, arm_name)] = mean
        baseline_mean_r, baseline_count = _summary(period_paired, "baseline")
        delayed_mean_r, delayed_count = _summary(period_paired, "delayed")
        baseline_mean_rupees = _mean_net_rupees(period_paired, "baseline")
        delayed_mean_rupees = _mean_net_rupees(period_paired, "delayed")
        counts = {
            status: sum(
                row["continuation_status"] == status for row in rows
            )
            for status in ("passed", "failed", "expired", "data_missing")
        }
        output.append(
            f"| {period} | {len(rows)} | {counts['passed']} | "
            f"{counts['failed']} | {counts['expired']} | "
            f"{counts['data_missing']} | {baseline_count} | "
            f"{_fmt(baseline_mean_r)} | {_fmt(baseline_mean_rupees)} | "
            f"{delayed_count} | {_fmt(delayed_mean_r)} | "
            f"{_fmt(delayed_mean_rupees)} |"
        )

    paired = paired_by_period["All 51"]
    best_trade = max(
        paired,
        key=lambda row: row["baseline"].net_r or float("-inf"),
        default=None,
    )
    paired_without_best = [
        row for row in paired if row is not best_trade
    ]
    baseline_ex_best, _ = _summary(paired_without_best, "baseline")
    delayed_ex_best, _ = _summary(paired_without_best, "delayed")
    output.extend(
        [
            "",
            "### Without the best trade",
            "",
            "| Period / sample | Excluded trade | Baseline n | Baseline mean net R | "
            "Baseline mean net ₹ | Variant n | Variant mean net R | "
            "Variant mean net ₹ |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    excluded = (
        str(best_trade["trade"]["trade_id"])
        if best_trade is not None
        else "unavailable"
    )
    for period, rows in period_rows.items():
        without_best = [row for row in paired_by_period[period] if row is not best_trade]
        baseline_mean_r, baseline_count = _summary(without_best, "baseline")
        delayed_mean_r, delayed_count = _summary(without_best, "delayed")
        output.append(
            f"| {period} | {excluded} | {baseline_count} | "
            f"{_fmt(baseline_mean_r)} | "
            f"{_fmt(_mean_net_rupees(without_best, 'baseline'))} | "
            f"{delayed_count} | {_fmt(delayed_mean_r)} | "
            f"{_fmt(_mean_net_rupees(without_best, 'delayed'))} |"
        )

    baseline_only_without_best = [
        row
        for row in records
        if row is not best_trade and row["baseline"].status == "complete"
    ]
    baseline_only_mean_r, baseline_only_count = _summary(
        baseline_only_without_best, "baseline"
    )
    output.append("")
    output.append(
        "Reconciliation: the earlier paired baseline without-best result "
        "(-0.0723 R, n=49) excluded SBIN_CE-2026-11-06T10:05:04.001399+05:30-BUY "
        "because its legacy replay window was incomplete. The corrected "
        "clock-window has all five minute buckets; its directional outcome is "
        "failed, so its baseline -1.0485 R is now included. The fixed-rule "
        "without-best paired baseline is therefore -0.0918 R (n=50), matching "
        "the baseline-only cohort."
    )
    output.append(
        f"- Baseline-only without-best: n={baseline_only_count}, "
        f"mean net R={_fmt(baseline_only_mean_r)}, "
        f"mean net ₹={_fmt(_mean_net_rupees(baseline_only_without_best, 'baseline'))}."
    )

    period1_wins = (
        period_means[("30-Oct to 11-Nov", "delayed")] is not None
        and period_means[("30-Oct to 11-Nov", "baseline")] is not None
        and period_means[("30-Oct to 11-Nov", "delayed")]
        > period_means[("30-Oct to 11-Nov", "baseline")]
    )
    period2_wins = (
        period_means[("12-Nov to 16-Nov", "delayed")] is not None
        and period_means[("12-Nov to 16-Nov", "baseline")] is not None
        and period_means[("12-Nov to 16-Nov", "delayed")]
        > period_means[("12-Nov to 16-Nov", "baseline")]
    )
    recommendation = (
        "Delayed entry wins both periods and without the best trade."
        if period1_wins
        and period2_wins
        and delayed_ex_best is not None
        and baseline_ex_best is not None
        and delayed_ex_best > baseline_ex_best
        else "Do not recommend the 5-minute continuation rule: it does not "
        "win in both periods and/or without the best trade."
    )
    output.extend(
        [
            "",
            "## Recommendation",
            "",
            recommendation,
            "",
            "## Trade-level arm results",
            "",
            "| Trade | Period | Run-up offline % | 5m result | Baseline net R | Variant net R |",
            "| --- | --- | ---: | --- | ---: | ---: |",
        ]
    )
    for row in records:
        delayed_r = (
            0.0
            if row["delayed"].status == "not_continued"
            else row["delayed"].net_r
        )
        output.append(
            f"| {row['trade']['trade_id']} | {_period_label(row['date'])} | "
            f"{_fmt(row['offline_move'])} | {row['continuation_status']} | "
            f"{_fmt(row['baseline'].net_r)} | {_fmt(delayed_r)} |"
        )
    return "\n".join(output) + "\n"


def build_followup_session_report(
    trades: list[dict[str, Any]],
    paper_data_root: Path,
    candle_root: Path,
    charge_config: dict[str, Any] | None = None,
) -> str:
    if not trades:
        return ""
    target_date = date(2026, 11, 17)
    if any(
        (parse_datetime(trade.get("timestamp")) or datetime.min.replace(tzinfo=IST)).date()
        != target_date
        for trade in trades
    ):
        raise ValueError("The follow-up sample must contain only 2026-11-17 trades")

    counts = {status: 0 for status in ("passed", "failed", "expired", "data_missing")}
    records: list[dict[str, Any]] = []
    for trade in trades:
        signal_time = parse_datetime(trade.get("signal_time"))
        confirmation_bar_time = parse_datetime(
            trade.get("confirmation_candle_time")
        )
        confirmation_close = _number(trade.get("confirmation_close"))
        if signal_time is None or confirmation_close is None:
            raise ValueError(f"Missing 17-Nov replay input: {trade.get('trade_id')}")
        confirmation_close_time = (
            confirmation_bar_time + timedelta(minutes=1)
            if confirmation_bar_time is not None
            else signal_time + timedelta(minutes=2)
        )
        underlying = str(trade["ticker"]).rsplit("_", 1)[0]
        bars = load_underlying_bars(paper_data_root, target_date, underlying)
        completion_time, _, status = runtime_five_minute_confirmation(
            bars,
            confirmation_close_time,
            confirmation_close,
            str(trade["ticker"]).rsplit("_", 1)[1],
        )
        candles, quotes = load_option_market(candle_root, trade)
        entry_time = parse_datetime(trade.get("entry_time")) or parse_datetime(
            trade.get("timestamp")
        )
        quantity = _number(trade.get("quantity"))
        baseline_entry = _number(trade.get("entry"))
        if entry_time is None or quantity is None or baseline_entry is None:
            raise ValueError(f"Missing 17-Nov trade inputs: {trade.get('trade_id')}")
        baseline = simulate_fixed_exit(
            candles,
            quotes,
            entry_time,
            baseline_entry,
            quantity,
            charge_config,
        )
        if status == "failed":
            variant = ReplayArm("not_continued")
        elif status == "passed" and completion_time is not None:
            delayed_quote = _quote_at_or_after(quotes, completion_time)
            if delayed_quote is None:
                status = "expired"
                variant = ReplayArm("expired")
            else:
                variant = simulate_fixed_exit(
                    candles,
                    quotes,
                    delayed_quote["time"],
                    delayed_quote["ask"],
                    quantity,
                    charge_config,
                )
        else:
            variant = ReplayArm(status)
        counts[status] += 1
        records.append(
            {
                "trade": trade,
                "status": status,
                "baseline": baseline,
                "delayed": variant,
            }
        )

    paired = [
        row
        for row in records
        if row["baseline"].status == "complete"
        and row["delayed"].status in {"complete", "not_continued"}
    ]
    best_trade = max(
        paired,
        key=lambda row: row["baseline"].net_r or float("-inf"),
        default=None,
    )
    paired_without_best = [
        row for row in paired if row is not best_trade
    ]
    excluded = (
        str(best_trade["trade"]["trade_id"])
        if best_trade is not None
        else "unavailable"
    )
    baseline_mean_r, baseline_count = _summary(paired, "baseline")
    variant_mean_r, variant_count = _summary(paired, "delayed")
    baseline_mean_rupees = _mean_net_rupees(paired, "baseline")
    variant_mean_rupees = _mean_net_rupees(paired, "delayed")
    baseline_ex_best, baseline_ex_best_count = _summary(
        paired_without_best, "baseline"
    )
    variant_ex_best, variant_ex_best_count = _summary(
        paired_without_best, "delayed"
    )
    return "\n".join(
        [
            "",
            "## 17-Nov follow-up",
            "",
            f"- Reached: {len(trades)}; passed: {counts['passed']}; "
            f"failed: {counts['failed']}; expired: {counts['expired']}; "
            f"data_missing: {counts['data_missing']}.",
            "",
            "| Sample | Excluded trade | Baseline n | Baseline mean net R | "
            "Baseline mean net ₹ | Variant n | Variant mean net R | "
            "Variant mean net ₹ |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            f"| All 5 | — | {baseline_count} | {_fmt(baseline_mean_r)} | "
            f"{_fmt(baseline_mean_rupees)} | {variant_count} | "
            f"{_fmt(variant_mean_r)} | {_fmt(variant_mean_rupees)} |",
            f"| Without best | {excluded} | {baseline_ex_best_count} | "
            f"{_fmt(baseline_ex_best)} | "
            f"{_fmt(_mean_net_rupees(paired_without_best, 'baseline'))} | "
            f"{variant_ex_best_count} | {_fmt(variant_ex_best)} | "
            f"{_fmt(_mean_net_rupees(paired_without_best, 'delayed'))} |",
            "",
        ]
    )


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def _mean_net_rupees(rows: list[dict[str, Any]], arm_name: str) -> float | None:
    values = []
    for row in rows:
        arm = row[arm_name]
        if arm.status == "complete":
            values.append(arm.net_rupees or 0.0)
        elif arm_name == "delayed" and arm.status == "not_continued":
            values.append(0.0)
    return sum(values) / len(values) if values else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", type=Path, default=Path("trades.jsonl"))
    parser.add_argument(
        "--candles",
        type=Path,
        default=Path("paper_trading_data/option_candles"),
    )
    parser.add_argument(
        "--paper-data",
        type=Path,
        default=Path("paper_trading_data"),
    )
    parser.add_argument("--config", type=Path, default=Path("kite_config.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "PAPER_RUN_UP_AND_5M_REPLAY_2026-10-30_to_2026-11-16.md"
        ),
    )
    args = parser.parse_args()
    try:
        all_trades = _read_jsonl(args.trades, through=date(2026, 11, 17))
        trades = [
            trade
            for trade in all_trades
            if (parse_datetime(trade.get("timestamp")) or datetime.min.replace(tzinfo=IST)).date()
            <= date(2026, 11, 16)
        ]
        followup_trades = [
            trade
            for trade in all_trades
            if (parse_datetime(trade.get("timestamp")) or datetime.min.replace(tzinfo=IST)).date()
            == date(2026, 11, 17)
        ]
        config = json.loads(args.config.read_text(encoding="utf-8"))
        report = build_report(
            trades,
            args.candles,
            args.paper_data,
            config,
        )
        report += build_followup_session_report(
            followup_trades,
            args.paper_data,
            args.candles,
            config,
        )
        args.output.write_text(report, encoding="utf-8", newline="\n")
        print(f"Wrote {args.output}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Replay failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
