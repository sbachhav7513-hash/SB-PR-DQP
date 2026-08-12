from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from .kite_provider import Tick


logger = logging.getLogger(__name__)


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def to_dict(self) -> Dict:
        return {
            "time": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


class BarBuilder:
    """Aggregates ticks into OHLC bars at a specified interval with memory limits."""

    def __init__(
        self,
        interval_seconds: int = 60,
        on_bar_callback: Optional[Callable[[str, Bar], None]] = None,
        max_bars_per_symbol: int = 100,
    ) -> None:
        self.interval_seconds = interval_seconds
        self.on_bar_callback = on_bar_callback
        self.max_bars_per_symbol = max_bars_per_symbol  # Limit memory usage
        self.bars: Dict[int, List[Bar]] = defaultdict(list)
        self.current_bar: Dict[int, dict] = {}
        self.last_bar_time: Dict[int, datetime] = {}

    def process_tick(self, tick: Tick) -> None:
        """Process a single tick and aggregate into bars."""
        token = tick.instrument_token
        price = tick.last_price
        timestamp = tick.timestamp

        if token not in self.last_bar_time:
            self.last_bar_time[token] = timestamp
            self.current_bar[token] = {
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": tick.volume,
                "start_time": timestamp,
            }
            return

        # Check if we need to start a new bar
        bar_start = self.last_bar_time[token]
        bar_end = bar_start + timedelta(seconds=self.interval_seconds)

        if timestamp >= bar_end:
            # Emit the completed bar
            completed = self.current_bar.get(token)
            if completed:
                bar = Bar(
                    timestamp=bar_start,
                    open=completed["open"],
                    high=completed["high"],
                    low=completed["low"],
                    close=completed["close"],
                    volume=completed["volume"],
                )
                self.bars[token].append(bar)
                
                # Keep only max_bars_per_symbol to limit memory usage
                if len(self.bars[token]) > self.max_bars_per_symbol:
                    self.bars[token].pop(0)
                
                if self.on_bar_callback:
                    self.on_bar_callback(str(token), bar)
                logger.debug(f"Bar completed for token {token}: {bar}")

            # Start a new bar
            self.last_bar_time[token] = bar_end
            self.current_bar[token] = {
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": tick.volume,
                "start_time": bar_end,
            }
        else:
            # Update the current bar
            bar = self.current_bar[token]
            bar["high"] = max(bar["high"], price)
            bar["low"] = min(bar["low"], price)
            bar["close"] = price
            bar["volume"] += tick.volume

    def get_bars(self, token: int, limit: int = 50) -> List[Bar]:
        """Get the most recent bars for a token."""
        return self.bars[token][-limit:]

    def get_latest_bar(self, token: int) -> Optional[Bar]:
        """Get the latest completed bar for a token."""
        bars = self.bars.get(token)
        if bars:
            return bars[-1]
        return None

    def clear_bars(self, token: int) -> None:
        """Clear stored bars for a token."""
        if token in self.bars:
            self.bars[token] = []
