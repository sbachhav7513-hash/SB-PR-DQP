from __future__ import annotations

import json
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class PaperTradingRecorder:
    """Store paper-trading events in date-partitioned CSV files."""

    TRADE_COLUMNS = [
        "trade_id", "timestamp", "ticker", "action", "quantity", "entry",
        "exit_price", "stop_loss", "take_profit", "status", "pnl", "pnl_points",
        "pnl_rupees", "duration_seconds", "reason", "score", "closed_at", "updated_at",
    ]
    DECISION_COLUMNS = [
        "timestamp", "ticker", "signal", "outcome", "score", "reasons",
        "bars_available", "bar", "history",
    ]

    def __init__(self, root: str = "paper_trading_data") -> None:
        self.root = Path(root)

    @staticmethod
    def _event_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            event_time = value
        else:
            try:
                event_time = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                event_time = datetime.now(timezone.utc)
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        return event_time.astimezone(IST)

    def _day_path(self, timestamp: Any, filename: str) -> Path:
        event_time = self._event_datetime(timestamp)
        iso_week = event_time.isocalendar().week
        directory = (
            self.root
            / event_time.strftime("%Y-%m")
            / f"week_{iso_week:02d}"
            / f"day_{event_time.day:02d}"
        )
        directory.mkdir(parents=True, exist_ok=True)
        return directory / filename

    @staticmethod
    def _csv_value(value: Any) -> str:
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, default=str, separators=(",", ":"))
        return "" if value is None else str(value)

    def _append(self, path: Path, record: Dict[str, Any], columns: List[str]) -> None:
        exists = path.exists() and path.stat().st_size > 0
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            writer.writerow({column: self._csv_value(record.get(column)) for column in columns})

    def record_decision(self, payload: Dict[str, Any]) -> None:
        timestamp = payload.get("timestamp", datetime.utcnow().isoformat(timespec="seconds"))
        self._append(self._day_path(timestamp, "decisions.csv"), payload, self.DECISION_COLUMNS)

    def record_trade(self, payload: Dict[str, Any]) -> None:
        timestamp = payload.get("timestamp", datetime.utcnow().isoformat(timespec="seconds"))
        path = self._day_path(timestamp, "trades.csv")
        rows: List[Dict[str, str]] = []
        if path.exists():
            with path.open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        trade_id = str(payload.get("trade_id", ""))
        updated = False
        for index, row in enumerate(rows):
            if trade_id and row.get("trade_id") == trade_id:
                rows[index] = {column: self._csv_value(payload.get(column)) for column in self.TRADE_COLUMNS}
                updated = True
                break
        if not updated:
            rows.append({column: self._csv_value(payload.get(column)) for column in self.TRADE_COLUMNS})
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.TRADE_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)


class DecisionJournal:
    """Append-only audit log for market data and strategy decisions."""

    def __init__(self, path: str = "decision_log.jsonl", paper_data_dir: Optional[str] = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.paper_recorder = PaperTradingRecorder(paper_data_dir) if paper_data_dir else None

    def log_decision(self, payload: Dict[str, Any]) -> None:
        entry = dict(payload)
        entry.setdefault("timestamp", datetime.utcnow().isoformat(timespec="seconds"))
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, default=str) + "\n")
            if self.paper_recorder:
                self.paper_recorder.record_decision(entry)
        except (OSError, TypeError, ValueError):
            # Observability must never interrupt live order handling.
            logger.exception("Could not write decision audit record to %s", self.path)


class TradeJournal:
    def __init__(self, path: str = "trades.jsonl", paper_data_dir: Optional[str] = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.paper_recorder = PaperTradingRecorder(paper_data_dir) if paper_data_dir else None

    def _write_trades(self, trades: List[Dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            for trade in trades:
                handle.write(json.dumps(trade, default=str) + "\n")

    def log_trade(self, payload: Dict[str, Any]) -> None:
        entry = dict(payload)
        entry.setdefault("timestamp", datetime.utcnow().isoformat(timespec="seconds"))
        entry.setdefault("status", "open")
        entry.setdefault("pnl", 0.0)
        entry.setdefault("trade_id", f"{entry['ticker']}-{entry['timestamp']}-{entry.get('action', 'UNKNOWN')}")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")
        if self.paper_recorder:
            self.paper_recorder.record_trade(entry)

    def read_trades(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []

        trades: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                line = line.strip()
                if line:
                    try:
                        trades.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping invalid trade journal line %s", line_number)
        return trades

    def get_open_trade(self, ticker: str, action: Optional[str] = None) -> Optional[Dict[str, Any]]:
        for trade in reversed(self.read_trades()):
            if trade.get("ticker") != ticker:
                continue
            if trade.get("status") != "open":
                continue
            if action and trade.get("action") != action:
                continue
            return trade
        return None

    def update_trade_pnl(self, ticker: str, current_price: float, action: Optional[str] = None) -> float:
        trades = self.read_trades()
        for trade in reversed(trades):
            if trade.get("ticker") != ticker:
                continue
            if trade.get("status") != "open":
                continue
            if action and trade.get("action") != action:
                continue

            entry_price = float(trade.get("entry", 0.0))
            stop_loss = float(trade.get("stop_loss", 0.0))
            take_profit = float(trade.get("take_profit", 0.0))

            if trade.get("action") == "BUY":
                pnl = current_price - entry_price
                if current_price <= stop_loss:
                    trade["status"] = "closed"
                    trade["exit_price"] = current_price
                    trade["pnl"] = stop_loss - entry_price
                    trade["closed_at"] = datetime.utcnow().isoformat(timespec="seconds")
                    trade["reason"] = "STOP_LOSS"
                    self._write_trades(trades)
                    if self.paper_recorder:
                        self.paper_recorder.record_trade(trade)
                    return trade["pnl"]
                if current_price >= take_profit:
                    trade["status"] = "closed"
                    trade["exit_price"] = current_price
                    trade["pnl"] = take_profit - entry_price
                    trade["closed_at"] = datetime.utcnow().isoformat(timespec="seconds")
                    trade["reason"] = "TAKE_PROFIT"
                    self._write_trades(trades)
                    if self.paper_recorder:
                        self.paper_recorder.record_trade(trade)
                    return trade["pnl"]
            elif trade.get("action") == "SELL":
                pnl = entry_price - current_price
                if current_price >= stop_loss:
                    trade["status"] = "closed"
                    trade["exit_price"] = current_price
                    trade["pnl"] = entry_price - stop_loss
                    trade["closed_at"] = datetime.utcnow().isoformat(timespec="seconds")
                    trade["reason"] = "STOP_LOSS"
                    self._write_trades(trades)
                    if self.paper_recorder:
                        self.paper_recorder.record_trade(trade)
                    return trade["pnl"]
                if current_price <= take_profit:
                    trade["status"] = "closed"
                    trade["exit_price"] = current_price
                    trade["pnl"] = entry_price - take_profit
                    trade["closed_at"] = datetime.utcnow().isoformat(timespec="seconds")
                    trade["reason"] = "TAKE_PROFIT"
                    self._write_trades(trades)
                    if self.paper_recorder:
                        self.paper_recorder.record_trade(trade)
                    return trade["pnl"]
            else:
                pnl = 0.0

            trade["pnl"] = pnl
            trade["last_price"] = current_price
            trade["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
            self._write_trades(trades)
            if self.paper_recorder:
                self.paper_recorder.record_trade(trade)
            return pnl

        return 0.0

    def close_trade(
        self,
        ticker: str,
        exit_price: float,
        action: Optional[str] = None,
        reason: str = "SIGNAL",
    ) -> float:
        trades = self.read_trades()
        for trade in reversed(trades):
            if trade.get("ticker") != ticker:
                continue
            if trade.get("status") != "open":
                continue
            if action and trade.get("action") != action:
                continue

            entry_price = float(trade.get("entry", 0.0))
            if trade.get("action") == "BUY":
                pnl = exit_price - entry_price
            elif trade.get("action") == "SELL":
                pnl = entry_price - exit_price
            else:
                pnl = 0.0

            trade["pnl"] = pnl
            trade["exit_price"] = exit_price
            trade["status"] = "closed"
            trade["closed_at"] = datetime.utcnow().isoformat(timespec="seconds")
            trade["reason"] = reason
            self._write_trades(trades)
            if self.paper_recorder:
                self.paper_recorder.record_trade(trade)
            return pnl

        return 0.0

    def annotate_trade(
        self, ticker: str, fields: Dict[str, Any], action: Optional[str] = None
    ) -> bool:
        """Add execution details calculated by the intraday position manager."""
        trades = self.read_trades()
        for trade in reversed(trades):
            if trade.get("ticker") != ticker or trade.get("status") != "closed":
                continue
            if action and trade.get("action") != action:
                continue
            trade.update(fields)
            self._write_trades(trades)
            if self.paper_recorder:
                self.paper_recorder.record_trade(trade)
            return True
        return False

    def current_pnl(self) -> float:
        trades = self.read_trades()
        pnl = 0.0
        for trade in trades:
            pnl += float(trade.get("pnl", 0.0))
        return pnl

    def portfolio_summary(self) -> Dict[str, float]:
        trades = self.read_trades()
        closed = sum(float(t.get("pnl", 0.0)) for t in trades if t.get("status") == "closed")
        open_trades = sum(float(t.get("pnl", 0.0)) for t in trades if t.get("status") == "open")
        return {"closed_pnl": closed, "open_pnl": open_trades, "total_pnl": closed + open_trades}
