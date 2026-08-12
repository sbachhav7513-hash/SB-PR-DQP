from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .data_provider import MarketDataProvider


@dataclass
class MarketSnapshot:
    ticker: str
    history: List[Dict]
    last_price: Optional[float] = None


class LiveMarketFeed:
    def __init__(self, provider: Optional[MarketDataProvider] = None) -> None:
        self.provider = provider or MarketDataProvider()

    def fetch_snapshot(self, ticker: str, period: str = "1d", interval: str = "2m") -> Optional[MarketSnapshot]:
        history = self.provider.fetch_history(ticker, period=period, interval=interval)
        if not history:
            return None
        return MarketSnapshot(
            ticker=ticker,
            history=history,
            last_price=history[-1].get("close"),
        )
