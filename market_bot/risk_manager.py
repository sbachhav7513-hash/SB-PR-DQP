from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RiskPlan:
    entry_price: float
    stop_loss: float
    take_profit: float
    side: str


def build_risk_plan(entry_price: float, side: str, stop_loss_pct: float = 1.5, take_profit_pct: float = 3.0) -> RiskPlan:
    if side == "BUY":
        stop_loss = entry_price * (1 - (stop_loss_pct / 100.0))
        take_profit = entry_price * (1 + (take_profit_pct / 100.0))
    elif side == "SELL":
        stop_loss = entry_price * (1 + (stop_loss_pct / 100.0))
        take_profit = entry_price * (1 - (take_profit_pct / 100.0))
    else:
        raise ValueError(f"Unsupported side: {side}")

    return RiskPlan(
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        side=side,
    )
