"""
Week 1 Accuracy Improvements
Quick fixes to improve win rate from 50% to 60%
"""

from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class AccuracyFilters:
    """Filters to reduce false signals and improve trade accuracy."""
    
    def __init__(self):
        self.last_entry_time: Dict[str, float] = {}
        self.COOLDOWN_SECONDS = 300  # 5 minutes between entries
    
    # ========== FILTER 1: Volatility Check ==========
    @staticmethod
    def calculate_atr(history: List[Dict], period: int = 14) -> float:
        """
        Calculate Average True Range (volatility indicator).
        
        Args:
            history: List of OHLC bars
            period: ATR period (default 14)
            
        Returns:
            ATR value
        """
        if len(history) < period:
            return 0.0
        
        true_ranges = []
        for i in range(len(history)):
            if i == 0:
                tr = history[i].get("high", 0) - history[i].get("low", 0)
            else:
                high = history[i].get("high", 0)
                low = history[i].get("low", 0)
                close_prev = history[i-1].get("close", 0)
                
                tr = max(
                    high - low,
                    abs(high - close_prev),
                    abs(low - close_prev)
                )
            true_ranges.append(tr)
        
        return sum(true_ranges[-period:]) / period
    
    @staticmethod
    def is_volatility_acceptable(
        history: List[Dict],
        min_volatility_pct: float = 0.8,
        max_volatility_pct: float = 5.0
    ) -> bool:
        """
        Check if market volatility is in acceptable range.
        
        Too low volatility = choppy, many false signals
        Too high volatility = dangerous, wide spreads, slippage
        
        Args:
            history: List of bars
            min_volatility_pct: Minimum acceptable volatility (%)
            max_volatility_pct: Maximum acceptable volatility (%)
            
        Returns:
            True if volatility is acceptable for trading
        """
        if len(history) < 14:
            return True  # Not enough data, allow
        
        atr = AccuracyFilters.calculate_atr(history, period=14)
        current_price = history[-1].get("close", 1)
        
        if current_price == 0:
            return False
        
        volatility_pct = (atr / current_price) * 100
        
        is_valid = min_volatility_pct <= volatility_pct <= max_volatility_pct
        
        if not is_valid:
            logger.debug(
                f"Volatility filter rejected: {volatility_pct:.2f}% "
                f"(range: {min_volatility_pct}-{max_volatility_pct}%)"
            )
        
        return is_valid
    
    # ========== FILTER 2: Confirmation Candle Check ==========
    @staticmethod
    def has_confirmation(
        signal: str,
        current_bar: Dict,
        previous_bar: Dict
    ) -> bool:
        """
        Confirm signal direction with current candle movement.
        
        BUY signal is more valid if current bar is closing HIGHER
        SELL signal is more valid if current bar is closing LOWER
        
        Args:
            signal: "BUY", "SELL", or "HOLD"
            current_bar: Latest completed bar
            previous_bar: Previous bar
            
        Returns:
            True if signal direction is confirmed
        """
        if signal == "HOLD":
            return True  # No confirmation needed for HOLD
        
        current_close = current_bar.get("close", 0)
        previous_close = previous_bar.get("close", 0)
        
        if signal == "BUY":
            # Confirm BUY: current bar should close higher
            return current_close > previous_close
        
        elif signal == "SELL":
            # Confirm SELL: current bar should close lower
            return current_close < previous_close
        
        return False
    
    # ========== FILTER 3: Score Threshold Adjustment ==========
    @staticmethod
    def should_enter_trade(
        signal: str,
        score: int,
        volatility_acceptable: bool,
        confirmation: bool
    ) -> bool:
        """
        Final gate to decide if we should actually enter trade.
        
        Combines all filters:
        1. Signal type (not HOLD)
        2. Score threshold (raised from 85 to 90)
        3. Volatility acceptable
        4. Confirmation candle
        
        Args:
            signal: "BUY", "SELL", or "HOLD"
            score: Signal score (0-100)
            volatility_acceptable: From volatility filter
            confirmation: From confirmation candle filter
            
        Returns:
            True if ALL filters pass
        """
        # Check 1: Must have clear signal
        if signal == "HOLD":
            return False
        
        # Check 2: RAISED THRESHOLD from 85 to 90
        if score < 90:
            logger.debug(f"Score filter rejected: {score}/100 (need 90+)")
            return False
        
        # Check 3: Volatility must be acceptable
        if not volatility_acceptable:
            return False
        
        # Check 4: Confirmation candle must pass
        if not confirmation:
            logger.debug(f"Confirmation filter rejected")
            return False
        
        return True
    
    # ========== FILTER 4: Cooldown Period ==========
    def can_enter_signal(self, symbol: str, current_time: float) -> bool:
        """
        Check if enough time has passed since last entry (cooldown).
        
        Prevents multiple entries in rapid succession (whipsaws).
        
        Args:
            symbol: Trading symbol (e.g., "NIFTY")
            current_time: Current time (Unix timestamp)
            
        Returns:
            True if cooldown period has passed
        """
        if symbol not in self.last_entry_time:
            return True
        
        time_since_last = current_time - self.last_entry_time[symbol]
        
        if time_since_last < self.COOLDOWN_SECONDS:
            logger.debug(
                f"Cooldown period active for {symbol}: "
                f"{self.COOLDOWN_SECONDS - time_since_last:.0f}s remaining"
            )
            return False
        
        return True
    
    def record_entry(self, symbol: str, current_time: float) -> None:
        """Record that we entered a trade for this symbol."""
        self.last_entry_time[symbol] = current_time
        logger.info(f"[{symbol}] Entry recorded, cooldown started (5 minutes)")
    
    # ========== FILTER 5: Time-Based Filters ==========
    @staticmethod
    def is_trading_hour_good(hour: int, minute: int) -> bool:
        """
        Avoid problematic trading hours:
        - 9:15-9:30 AM: Opening volatility spike
        - 3:15-3:30 PM: Closing rush, forced exits
        
        Args:
            hour: Current hour (0-23)
            minute: Current minute (0-59)
            
        Returns:
            True if trading at this hour is advisable
        """
        current_min = hour * 60 + minute
        
        # Opening hour (9:15-9:30 AM IST)
        opening_start = 9 * 60 + 15  # 555 minutes
        opening_end = 9 * 60 + 30    # 570 minutes
        
        if opening_start <= current_min <= opening_end:
            logger.debug("Opening hour filter (9:15-9:30): Skipping")
            return False
        
        # Closing hour (3:15-3:30 PM IST)
        closing_start = 15 * 60 + 15  # 915 minutes
        closing_end = 15 * 60 + 30    # 930 minutes
        
        if closing_start <= current_min <= closing_end:
            logger.debug("Closing hour filter (3:15-3:30): Skipping")
            return False
        
        return True
    
    # ========== COMPOSITE FILTER ==========
    def validate_entry(
        self,
        symbol: str,
        signal: str,
        score: int,
        history: List[Dict],
        current_bar: Dict,
        previous_bar: Dict,
        current_time: float,
        hour: int,
        minute: int
    ) -> bool:
        """
        All filters combined for final entry decision.
        
        Returns: True ONLY if ALL filters pass
        """
        # Filter 1: Volatility
        volatility_ok = self.is_volatility_acceptable(history)
        if not volatility_ok:
            return False
        
        # Filter 2: Confirmation candle
        confirmation = self.has_confirmation(signal, current_bar, previous_bar)
        if not confirmation:
            return False
        
        # Filter 3: Score threshold & signal
        should_enter = self.should_enter_trade(signal, score, volatility_ok, confirmation)
        if not should_enter:
            return False
        
        # Filter 4: Cooldown period
        can_enter = self.can_enter_signal(symbol, current_time)
        if not can_enter:
            return False
        
        # Filter 5: Trading hours
        good_hour = self.is_trading_hour_good(hour, minute)
        if not good_hour:
            return False
        
        # ALL FILTERS PASSED ✅
        self.record_entry(symbol, current_time)
        return True
