"""
Performance-Optimized Strategy Calculations
Uses incremental calculations and caching for fast indicator updates.
"""

from typing import List, Optional, Dict, Tuple


class OptimizedIndicators:
    """Incrementally calculate indicators for O(1) updates instead of O(n)."""
    
    def __init__(self, max_history: int = 100):
        """
        Initialize with max history to keep in memory.
        
        Args:
            max_history: Maximum number of bars to store (default 100)
        """
        self.max_history = max_history
        self.closes: List[float] = []
        
        # Cache for EMA values
        self.ema_fast_values: List[float] = []
        self.ema_slow_values: List[float] = []
        self.ema_fast_last: Optional[float] = None
        self.ema_slow_last: Optional[float] = None
        
        # Cache for RSI
        self.rsi_values: List[float] = []
        self.rsi_last: Optional[float] = None
        self.avg_gain: Optional[float] = None
        self.avg_loss: Optional[float] = None
        
        # Multipliers
        self.ema_fast_period = 9
        self.ema_slow_period = 21
        self.rsi_period = 14
        
        self.ema_fast_mult = 2 / (self.ema_fast_period + 1)
        self.ema_slow_mult = 2 / (self.ema_slow_period + 1)
    
    def add_price(self, price: float) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Add new price and incrementally update all indicators.
        
        Returns:
            (ema_fast, ema_slow, rsi)
        """
        self.closes.append(price)
        
        # Keep only max_history
        if len(self.closes) > self.max_history:
            self.closes.pop(0)
            self.ema_fast_values.pop(0)
            self.ema_slow_values.pop(0)
            self.rsi_values.pop(0)
        
        # Update EMA
        self._update_ema()
        
        # Update RSI
        self._update_rsi()
        
        return self.ema_fast_last, self.ema_slow_last, self.rsi_last
    
    def _update_ema(self) -> None:
        """Update EMA incrementally."""
        if len(self.closes) < self.ema_slow_period:
            # Need enough data for slow EMA
            return
        
        # Fast EMA
        if len(self.closes) == self.ema_fast_period:
            # First EMA is SMA
            self.ema_fast_last = sum(self.closes[:self.ema_fast_period]) / self.ema_fast_period
        elif len(self.closes) > self.ema_fast_period:
            # Incremental update
            price = self.closes[-1]
            self.ema_fast_last = (price - self.ema_fast_last) * self.ema_fast_mult + self.ema_fast_last
        
        self.ema_fast_values.append(self.ema_fast_last)
        
        # Slow EMA
        if len(self.closes) == self.ema_slow_period:
            # First EMA is SMA
            self.ema_slow_last = sum(self.closes[:self.ema_slow_period]) / self.ema_slow_period
        elif len(self.closes) > self.ema_slow_period:
            # Incremental update
            price = self.closes[-1]
            self.ema_slow_last = (price - self.ema_slow_last) * self.ema_slow_mult + self.ema_slow_last
        
        self.ema_slow_values.append(self.ema_slow_last)
    
    def _update_rsi(self) -> None:
        """Update RSI incrementally."""
        if len(self.closes) < 2:
            return
        
        change = self.closes[-1] - self.closes[-2]
        gain = max(change, 0)
        loss = max(-change, 0)
        
        if len(self.closes) == self.rsi_period + 1:
            # First RSI calculation
            changes = [self.closes[i] - self.closes[i-1] for i in range(1, len(self.closes))]
            gains = [max(c, 0) for c in changes]
            losses = [max(-c, 0) for c in changes]
            self.avg_gain = sum(gains) / self.rsi_period
            self.avg_loss = sum(losses) / self.rsi_period
        elif len(self.closes) > self.rsi_period + 1:
            # Incremental update
            self.avg_gain = (self.avg_gain * (self.rsi_period - 1) + gain) / self.rsi_period
            self.avg_loss = (self.avg_loss * (self.rsi_period - 1) + loss) / self.rsi_period
        
        if self.avg_gain is not None and self.avg_loss is not None:
            if self.avg_loss == 0:
                self.rsi_last = 100.0
            else:
                rs = self.avg_gain / self.avg_loss
                self.rsi_last = 100.0 - (100.0 / (1 + rs))
            
            self.rsi_values.append(self.rsi_last)
    
    def get_closes(self, count: Optional[int] = None) -> List[float]:
        """Get last N closes (or all if count is None)."""
        if count is None:
            return self.closes.copy()
        return self.closes[-count:] if len(self.closes) >= count else self.closes.copy()
    
    def get_ema_fast(self) -> Optional[float]:
        """Get current fast EMA."""
        return self.ema_fast_last
    
    def get_ema_slow(self) -> Optional[float]:
        """Get current slow EMA."""
        return self.ema_slow_last
    
    def get_rsi(self) -> Optional[float]:
        """Get current RSI."""
        return self.rsi_last
    
    def is_ready(self) -> bool:
        """Check if enough data for all indicators."""
        return len(self.closes) > self.rsi_period
