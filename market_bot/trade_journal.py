from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class DecisionJournal:
    """Append-only audit log for market data and strategy decisions."""

    def __init__(self, path: str = "decision_log.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log_decision(self, payload: Dict[str, Any]) -> None:
        entry = dict(payload)
        entry.setdefault("timestamp", datetime.utcnow().isoformat(timespec="seconds"))
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, default=str) + "\n")
        except (OSError, TypeError, ValueError):
            # Observability must never interrupt live order handling.
            logger.exception("Could not write decision audit record to %s", self.path)


class TradeJournal:
    def __init__(self, path: str = "trades.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write_trades(self, trades: List[Dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            for trade in trades:
                handle.write(json.dumps(trade, default=str) + "\n")

    def log_trade(self, payload: Dict[str, Any]) -> None:
        entry = dict(payload)
        entry.setdefault("timestamp", datetime.utcnow().isoformat(timespec="seconds"))
        entry.setdefault("status", "open")
        entry.setdefault("pnl", 0.0)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")

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
                    return trade["pnl"]
                if current_price >= take_profit:
                    trade["status"] = "closed"
                    trade["exit_price"] = current_price
                    trade["pnl"] = take_profit - entry_price
                    trade["closed_at"] = datetime.utcnow().isoformat(timespec="seconds")
                    trade["reason"] = "TAKE_PROFIT"
                    self._write_trades(trades)
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
                    return trade["pnl"]
                if current_price <= take_profit:
                    trade["status"] = "closed"
                    trade["exit_price"] = current_price
                    trade["pnl"] = entry_price - take_profit
                    trade["closed_at"] = datetime.utcnow().isoformat(timespec="seconds")
                    trade["reason"] = "TAKE_PROFIT"
                    self._write_trades(trades)
                    return trade["pnl"]
            else:
                pnl = 0.0

            trade["pnl"] = pnl
            trade["last_price"] = current_price
            trade["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
            self._write_trades(trades)
            return pnl

        return 0.0

    def close_trade(self, ticker: str, exit_price: float, action: Optional[str] = None) -> float:
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
            self._write_trades(trades)
            return pnl

        return 0.0

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
