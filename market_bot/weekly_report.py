from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


def _load_jsonl(path: Path, days: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days)
    records: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    timestamp = datetime.fromisoformat(record.get("timestamp", ""))
                    if timestamp > cutoff:
                        records.append(record)
                except (json.JSONDecodeError, TypeError, ValueError):
                    logger.warning("Skipping invalid record in %s at line %s", path, line_number)
    except OSError:
        logger.exception("Could not read %s", path)
    return records


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_weekly_report(data_dir: str = ".", days: int = 7) -> Dict[str, Any]:
    root = Path(data_dir)
    trades = [
        trade for trade in _load_jsonl(root / "trades.jsonl", days)
        if trade.get("status") == "closed"
    ]
    decisions = _load_jsonl(root / "decision_log.jsonl", days)

    grouped: Dict[str, List[float]] = defaultdict(list)
    for trade in trades:
        key = f"{trade.get('ticker', 'UNKNOWN')}:{trade.get('action', 'UNKNOWN')}"
        grouped[key].append(_number(trade.get("pnl", trade.get("profit", 0))))

    profiles: List[Dict[str, Any]] = []
    for key, pnls in grouped.items():
        if len(pnls) < 2:
            continue
        wins = sum(1 for pnl in pnls if pnl > 0)
        profiles.append({
            "profile": key,
            "trades": len(pnls),
            "win_rate": round(wins / len(pnls) * 100, 2),
            "total_pnl": round(sum(pnls), 2),
            "average_pnl": round(sum(pnls) / len(pnls), 2),
        })
    profiles.sort(key=lambda item: item["average_pnl"], reverse=True)

    pnl_values = [_number(trade.get("pnl", trade.get("profit", 0))) for trade in trades]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "period_days": days,
        "closed_trades": len(trades),
        "total_pnl": round(sum(pnl_values), 2),
        "win_rate": round(
            sum(1 for pnl in pnl_values if pnl > 0) / len(pnl_values) * 100, 2
        ) if pnl_values else 0.0,
        "decisions_recorded": len(decisions),
        "signal_counts": {
            signal: sum(1 for item in decisions if item.get("signal") == signal)
            for signal in ("BUY", "SELL", "HOLD", "ERROR")
        },
        "best_observed_profiles": profiles[:5],
        "recommendation": (
            f"Best observed profile: {profiles[0]['profile']} "
            f"({profiles[0]['trades']} trades, {profiles[0]['win_rate']}% wins, "
            f"average P&L {profiles[0]['average_pnl']:.2f})."
            if profiles else
            "Not enough repeated closed trades to recommend a profile."
        ),
    }


def write_weekly_report(
    data_dir: str = ".", days: int = 7, output_dir: str = "."
) -> Path:
    report = build_weekly_report(data_dir, days)
    destination = Path(output_dir) / f"weekly_report_{datetime.now():%Y_%m_%d}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        temporary.replace(destination)
    except OSError:
        logger.exception("Could not publish weekly report to %s", destination)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return destination