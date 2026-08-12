"""
Intraday Futures Trading Manager
Handles position sizing, time-based exits, and leverage management
"""

from datetime import datetime, time as time_type
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class IntradayManager:
    """Manages intraday futures trading with automatic market close exits."""
    
    # Market timings (IST)
    MARKET_OPEN = time_type(9, 15)
    MARKET_CLOSE = time_type(15, 30)
    AUTO_EXIT_TIME = time_type(15, 15)  # Exit 15 minutes before close
    
    # Leverage & sizing for futures
    NIFTY_LOT_SIZE = 50  # 1 NIFTY lot = 50 units
    BANKNIFTY_LOT_SIZE = 15  # 1 BANKNIFTY lot = 15 units
    
    # Instrument multipliers (per point value in INR)
    MULTIPLIERS = {
        "NIFTY": 100,
        "BANKNIFTY": 100,
        "TCS": 1,
        "INFY": 1,
        "WIPRO": 1,
        "RELIANCE": 1,
        "HDFCBANK": 1,
        "ICICIBANK": 1,
        "AXISBANK": 1,
        "INDUSINDBK": 1,
        "SBIN": 1,
        "HDFC": 1,
        "MARUTI": 1,
        "BAJAJFINSV": 1,
        "LT": 1,
        "SUNPHARMA": 1,
    }
    
    def __init__(self, account_size: float = 100000, risk_per_trade_pct: float = 1.0):
        """
        Initialize the intraday manager.
        
        Args:
            account_size: Total account size in rupees
            risk_per_trade_pct: Risk per trade as percentage of account (default 1%)
        """
        self.account_size = account_size
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_risk_per_trade = (account_size * risk_per_trade_pct) / 100.0
        self.active_positions: Dict[str, dict] = {}
    
    def is_trading_hours(self) -> bool:
        """Check if current time is within trading hours."""
        now = datetime.now().time()
        return self.MARKET_OPEN <= now < self.MARKET_CLOSE
    
    def should_exit_all_positions(self) -> bool:
        """Check if it's time to exit all positions (3:15 PM)."""
        now = datetime.now().time()
        return now >= self.AUTO_EXIT_TIME
    
    def calculate_position_size(
        self, 
        symbol: str, 
        entry_price: float, 
        stop_loss_price: float
    ) -> int:
        """
        Calculate position size for futures based on risk management.
        
        Args:
            symbol: Trading symbol (e.g., "NIFTY", "BANKNIFTY")
            entry_price: Entry price
            stop_loss_price: Stop loss price
            
        Returns:
            Number of contracts/lots to trade
        """
        # Calculate risk in points
        risk_points = abs(entry_price - stop_loss_price)
        
        if risk_points == 0:
            logger.warning(f"[{symbol}] Stop loss too close, cannot calculate position size")
            return 0
        
        # Get multiplier for this symbol
        multiplier = self.MULTIPLIERS.get(symbol, 1)
        
        # Calculate risk in rupees per contract
        risk_per_contract = risk_points * multiplier
        
        # Calculate contracts based on max risk
        if risk_per_contract > 0:
            contracts = int(self.max_risk_per_trade / risk_per_contract)
        else:
            contracts = 0
        
        # Minimum 1 contract, maximum safety limit
        contracts = max(1, min(contracts, 5))
        
        logger.info(
            f"[{symbol}] Position Size Calc: Entry={entry_price:.2f}, "
            f"SL={stop_loss_price:.2f}, Risk={risk_points:.2f}pts, "
            f"Contracts={contracts}"
        )
        
        return contracts
    
    def register_position(self, symbol: str, direction: str, quantity: int, 
                         entry_price: float, stop_loss: float, take_profit: float) -> None:
        """Register a new position."""
        self.active_positions[symbol] = {
            "direction": direction,
            "quantity": quantity,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_time": datetime.now(),
        }
        logger.info(
            f"[{symbol}] Position registered: {direction} {quantity} "
            f"@ {entry_price:.2f} | SL={stop_loss:.2f} TP={take_profit:.2f}"
        )
    
    def close_position(self, symbol: str, exit_price: float, reason: str = "SIGNAL") -> Optional[dict]:
        """
        Close a position and calculate P&L.
        
        Args:
            symbol: Trading symbol
            exit_price: Exit price
            reason: Reason for exit (SIGNAL, TAKE_PROFIT, STOP_LOSS, MARKET_CLOSE)
            
        Returns:
            Position details with P&L
        """
        if symbol not in self.active_positions:
            return None
        
        pos = self.active_positions.pop(symbol)
        multiplier = self.MULTIPLIERS.get(symbol, 1)
        
        # Calculate P&L
        if pos["direction"] == "BUY":
            pnl_points = exit_price - pos["entry_price"]
        else:  # SELL
            pnl_points = pos["entry_price"] - exit_price
        
        pnl_rupees = pnl_points * multiplier * pos["quantity"]
        pnl_pct = (pnl_rupees / self.max_risk_per_trade * 100) if self.max_risk_per_trade > 0 else 0
        
        exit_details = {
            "symbol": symbol,
            "direction": pos["direction"],
            "quantity": pos["quantity"],
            "entry_price": pos["entry_price"],
            "exit_price": exit_price,
            "pnl_points": pnl_points,
            "pnl_rupees": pnl_rupees,
            "pnl_pct": pnl_pct,
            "reason": reason,
            "duration": (datetime.now() - pos["entry_time"]).total_seconds(),
        }
        
        logger.info(
            f"[{symbol}] Position closed: {exit_details['direction']} "
            f"P&L: ₹{pnl_rupees:.0f} ({pnl_pct:.2f}%) | Reason: {reason}"
        )
        
        return exit_details
    
    def get_open_positions_count(self) -> int:
        """Get count of open positions."""
        return len(self.active_positions)
    
    def get_all_open_positions(self) -> Dict:
        """Get all open positions."""
        return self.active_positions.copy()
