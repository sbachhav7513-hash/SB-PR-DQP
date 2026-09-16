"""
Intraday Futures Trading Manager
Handles position sizing, time-based exits, and leverage management
"""

from datetime import datetime, time as time_type
from typing import Optional, Dict
import logging
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class IntradayManager:
    """Manages intraday futures trading with automatic market close exits."""
    
    # Market timings (IST)
    MARKET_OPEN = time_type(9, 15)
    MARKET_CLOSE = time_type(15, 30)
    AUTO_EXIT_TIME = time_type(15, 15)  # Exit 15 minutes before close
    
    # Leverage & sizing for futures
    NIFTY_LOT_SIZE = 50  # 1 NIFTY lot = 50 units
    BANKNIFTY_LOT_SIZE = 15  # 1 BANKNIFTY lot = 15 units
    LOT_SIZES = {
        "NIFTY": NIFTY_LOT_SIZE,
        "BANKNIFTY": BANKNIFTY_LOT_SIZE,
    }
    
    # Quantity already contains the complete lot size, so futures use one
    # rupee of P&L per price point per unit unless the broker provides specs.
    MULTIPLIERS = {
        "NIFTY": 1,
        "BANKNIFTY": 1,
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
        self.contract_specs: Dict[str, dict] = {}

        self.daily_trade_count = 0
        self.daily_max_trades = 2
        self.daily_max_loss = max(account_size * 0.02, 250.0)
        self.daily_pnl = 0.0
        self.session_trade_symbols: set[str] = set()
        self.session_reversal_symbols: set[str] = set()
        self.trade_history: list[dict] = []

    def set_contract_specs(self, specs: Dict[str, dict]) -> None:
        self.contract_specs = dict(specs)
    
    def is_trading_hours(self) -> bool:
        """Check if current time is within trading hours."""
        now = datetime.now(IST).time()
        return self.MARKET_OPEN <= now < self.MARKET_CLOSE
    
    def should_exit_all_positions(self) -> bool:
        """Check if it's time to exit all positions (3:15 PM)."""
        now = datetime.now(IST).time()
        return now >= self.AUTO_EXIT_TIME
    
    def calculate_position_size(
        self, 
        symbol: str, 
        entry_price: float, 
        stop_loss_price: float,
        allow_paper_lot: bool = False,
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
        multiplier = self.contract_specs.get(symbol, {}).get(
            "multiplier", self.MULTIPLIERS.get(symbol, 1)
        )
        
        lot_size = self.contract_specs.get(symbol, {}).get(
            "lot_size", self.LOT_SIZES.get(symbol, 1)
        )
        # Futures risk is based on the complete lot, not one index point unit.
        risk_per_lot = risk_points * multiplier * lot_size
        
        # Paper mode can observe one complete lot without changing live risk rules.
        if risk_per_lot <= 0:
            return 0
        lots = int(self.max_risk_per_trade / risk_per_lot)
        if lots < 1:
            if allow_paper_lot:
                logger.info(
                    "[%s] Paper position sizing: simulating one lot; "
                    "estimated risk %.2f exceeds budget %.2f",
                    symbol,
                    risk_per_lot,
                    self.max_risk_per_trade,
                )
                return lot_size
            logger.warning(
                "[%s] One lot risks %.2f, above the configured limit of %.2f; skipping",
                symbol,
                risk_per_lot,
                self.max_risk_per_trade,
            )
            return 0

        # Cap the number of lots as an additional safety limit.
        lots = min(lots, 5)
        quantity = lots * lot_size
        
        logger.info(
            f"[{symbol}] Position Size Calc: Entry={entry_price:.2f}, "
            f"SL={stop_loss_price:.2f}, Risk={risk_points:.2f}pts, "
            f"Lots={lots}, Quantity={quantity}"
        )
        
        return quantity
    
    def can_open_trade(self, symbol: str, direction: str) -> tuple[bool, str]:
        """Policy gate for one option trade per symbol per session and daily caps."""
        if symbol in self.session_reversal_symbols:
            return False, f"{symbol} already reversed this session; no new trade allowed"
        if symbol in self.session_trade_symbols:
            return False, f"{symbol} already traded this session; only one trade per symbol per session is allowed"
        if self.daily_trade_count >= self.daily_max_trades:
            return False, f"Daily option trade cap reached ({self.daily_trade_count}/{self.daily_max_trades})"
        if self.daily_pnl <= -self.daily_max_loss:
            return False, f"Daily loss cap reached ({self.daily_pnl:.0f} <= -{self.daily_max_loss:.0f})"
        return True, "OK"

    def record_trade_open(self, symbol: str, direction: str) -> None:
        self.daily_trade_count += 1
        self.session_trade_symbols.add(symbol)
        logger.info("[%s] Recorded open trade for %s; daily_trade_count=%d", symbol, direction, self.daily_trade_count)

    def record_trade_close(self, symbol: str, reason: str, pnl: float) -> None:
        self.daily_pnl += pnl
        self.trade_history.append({"symbol": symbol, "reason": reason, "pnl": pnl, "time": datetime.now(IST)})
        if symbol in self.session_trade_symbols:
            self.session_trade_symbols.discard(symbol)
        if reason == "SIGNAL_REVERSAL":
            self.session_reversal_symbols.add(symbol)
        if pnl < 0 and abs(pnl) >= self.daily_max_loss * 0.5:
            self.session_reversal_symbols.add(symbol)

    def register_position(self, symbol: str, direction: str, quantity: int, 
                         entry_price: float, stop_loss: float, take_profit: float) -> None:
        """Register a new position."""
        self.active_positions[symbol] = {
            "direction": direction,
            "quantity": quantity,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_time": datetime.now(IST),
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
        multiplier = self.contract_specs.get(symbol, {}).get(
            "multiplier", self.MULTIPLIERS.get(symbol, 1)
        )
        
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
            "duration": (datetime.now(IST) - pos["entry_time"]).total_seconds(),
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

    def calculate_option_size(
        self,
        symbol: str,
        premium: float,
        max_risk_per_trade: Optional[float] = None,
        premium_stop_pct: float = 0.35,
    ) -> int:
        """Premium-based sizing for options: risk = premium * quantity * stop_pct."""
        if premium <= 0:
            return 0
        risk_budget = max_risk_per_trade if max_risk_per_trade is not None else self.max_risk_per_trade
        if risk_budget <= 0:
            return 0
        stop_value = premium * premium_stop_pct
        max_contracts = int(risk_budget / max(stop_value, 1e-6))
        return max(1, min(max_contracts, 5)) if max_contracts >= 1 else 0
