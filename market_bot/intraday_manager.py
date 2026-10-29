"""
Intraday Futures Trading Manager
Handles position sizing, time-based exits, and leverage management
"""

from datetime import datetime, time as time_type, timedelta, timezone
from typing import Optional, Dict
import logging
import math
from zoneinfo import ZoneInfo

from .risk_manager import MAX_DAILY_LOSS_PCT, MAX_TRADE_RISK_PCT

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
PAPER_OPTION_TRAIL_RUNNER = "paper_option_2r_trail_runner"
PAPER_OPTION_ADAPTIVE_EXIT = "paper_option_adaptive"


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
    
    def __init__(
        self,
        account_size: float = 100000,
        risk_per_trade_pct: float = 1.0,
        trailing_enabled: bool = True,
        trailing_activation_ratio: float = 0.5,
        trailing_distance_ratio: float = 0.25,
        daily_max_loss: Optional[float] = None,
        daily_max_loss_pct: float = 2.0,
        max_risk_per_trade: Optional[float] = None,
    ):
        """
        Initialize the intraday manager.
        
        Args:
            account_size: Total account size in rupees
            risk_per_trade_pct: Risk per trade as percentage of account (default 1%)
        """
        self.account_size = account_size
        self.risk_per_trade_pct = risk_per_trade_pct
        if not math.isfinite(float(account_size)) or account_size <= 0:
            raise ValueError("account_size must be finite and positive")
        if (
            not math.isfinite(float(daily_max_loss_pct))
            or not 0 <= float(daily_max_loss_pct) <= MAX_DAILY_LOSS_PCT
        ):
            raise ValueError(
                f"daily_max_loss_pct must be between 0 and {MAX_DAILY_LOSS_PCT:g}"
            )
        configured_trade_risk = (
            (account_size * risk_per_trade_pct) / 100.0
            if max_risk_per_trade is None
            else max(float(max_risk_per_trade), 0.0)
        )
        maximum_daily_loss = account_size * MAX_DAILY_LOSS_PCT / 100.0
        if daily_max_loss is None:
            self.daily_max_loss = max(
                account_size * daily_max_loss_pct / 100.0, 0.0
            )
        else:
            daily_max_loss = float(daily_max_loss)
            if (
                not math.isfinite(daily_max_loss)
                or not 0 <= daily_max_loss <= maximum_daily_loss
            ):
                raise ValueError(
                    "daily_max_loss must be between 0 and 10% of account_size"
                )
            self.daily_max_loss = daily_max_loss
        self.max_risk_per_trade = min(configured_trade_risk, self.daily_max_loss)
        self.trailing_enabled = trailing_enabled
        self.trailing_activation_ratio = trailing_activation_ratio
        self.trailing_distance_ratio = trailing_distance_ratio
        self.active_positions: Dict[str, dict] = {}
        self.contract_specs: Dict[str, dict] = {}

        self.daily_trade_count = 0
        self.max_consecutive_losses = 3
        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        self.daily_realized_losses = 0.0
        self.loss_cooldown_seconds = 1800
        self.min_symbol_trades_for_cap = 5
        self.symbol_min_win_rate = 35.0
        self.symbol_performance: Dict[str, Dict[str, float]] = {}
        self.recent_loss_symbols: Dict[str, datetime] = {}
        self.session_trade_symbols: set[str] = set()
        self.session_trade_counts: Dict[str, int] = {}
        self.session_loss_stop_times: Dict[str, datetime] = {}
        self.session_reversal_symbols: set[str] = set()
        self._session_date = datetime.now(IST).date()
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

    def is_market_closed(self) -> bool:
        """Check if the regular market session has ended (3:30 PM)."""
        now = datetime.now(IST).time()
        return now >= self.MARKET_CLOSE
    
    def calculate_position_size(
        self, 
        symbol: str, 
        entry_price: float, 
        stop_loss_price: float,
        max_risk_per_trade: Optional[float] = None,
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
        risk_budget = self.available_daily_risk()
        if max_risk_per_trade is not None:
            max_risk_per_trade = float(max_risk_per_trade)
            if not math.isfinite(max_risk_per_trade) or max_risk_per_trade < 0:
                raise ValueError("max_risk_per_trade must be finite and non-negative")
            risk_budget = min(risk_budget, max_risk_per_trade)
        lots = int(risk_budget / risk_per_lot)
        if lots < 1:
            logger.warning(
                "[%s] One lot risks %.2f, above the configured limit of %.2f; skipping",
                symbol,
                risk_per_lot,
                risk_budget,
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
    
    def can_open_trade(
        self,
        symbol: str,
        direction: str,
        *,
        allow_stop_reentry: bool = False,
        stop_reentry_cooldown_seconds: int = 900,
        signal_score: Optional[int] = None,
        minimum_stop_reentry_score: int = 75,
    ) -> tuple[bool, str]:
        """Apply session, optional paper stop-retry, and risk policies."""
        self._refresh_session()
        if symbol in self.session_reversal_symbols:
            return False, f"{symbol} already reversed this session; no new trade allowed"
        if symbol in self.session_trade_symbols:
            if not allow_stop_reentry:
                return False, f"{symbol} already traded this session; only one trade per symbol per session is allowed"
            if self.session_trade_counts.get(symbol, 1) != 1:
                return False, f"{symbol} already used its one stop-loss re-entry this session"
            stopped_at = self.session_loss_stop_times.get(symbol)
            if stopped_at is None:
                return False, f"{symbol} has no qualifying loss stop for re-entry"
            if stop_reentry_cooldown_seconds < 0:
                raise ValueError("stop_reentry_cooldown_seconds must be non-negative")
            elapsed = (datetime.now(IST) - stopped_at).total_seconds()
            if elapsed < stop_reentry_cooldown_seconds:
                remaining = stop_reentry_cooldown_seconds - elapsed
                return False, (
                    f"{symbol} stop re-entry cooldown active: "
                    f"{remaining:.0f}s remaining"
                )
            if signal_score is None or signal_score < minimum_stop_reentry_score:
                return False, (
                    f"{symbol} stop re-entry requires score "
                    f"{minimum_stop_reentry_score} or higher"
                )
        if self.daily_pnl <= -self.daily_max_loss:
            return False, f"Daily loss cap reached ({self.daily_pnl:.0f} <= -{self.daily_max_loss:.0f})"
        if self.daily_loss_limit_reached():
            return False, (
                "Daily loss cap reached "
                f"({self.daily_realized_losses:.0f} >= {self.daily_max_loss:.0f})"
            )
        available_risk = self.available_daily_risk()
        if available_risk <= 1e-6:
            return False, (
                "Aggregate daily risk budget exhausted "
                f"(open risk plus realized losses reach the {self.daily_max_loss:.0f} cap)"
            )
        if self.consecutive_losses >= self.max_consecutive_losses:
            return False, (
                f"Consecutive loss circuit breaker triggered "
                f"({self.consecutive_losses}/{self.max_consecutive_losses})"
            )
        perf = self.symbol_performance.get(symbol, {})
        trades = int(perf.get("trades", 0))
        win_rate = float(perf.get("win_rate", 100.0))
        if trades >= self.min_symbol_trades_for_cap and win_rate < self.symbol_min_win_rate:
            return False, (
                f"Win-rate cap active for {symbol}: "
                f"{win_rate:.1f}% over {trades} trades below {self.symbol_min_win_rate:.0f}%"
            )
        if symbol in self.recent_loss_symbols and self.consecutive_losses >= 2:
            last_loss_at = self.recent_loss_symbols[symbol]
            elapsed = (datetime.now(IST) - last_loss_at).total_seconds()
            if elapsed < self.loss_cooldown_seconds:
                remaining = self.loss_cooldown_seconds - elapsed
                return False, (
                    f"Recent loss cooldown active for {symbol}: "
                    f"{remaining:.0f}s remaining"
                )
        return True, "OK"

    def estimate_trade_risk(
        self, symbol: str, quantity: int, entry_price: float, stop_loss_price: float
    ) -> float:
        multiplier = self.contract_specs.get(symbol, {}).get(
            "multiplier", self.MULTIPLIERS.get(symbol, 1)
        )
        return abs(entry_price - stop_loss_price) * multiplier * quantity

    def open_position_risk(self) -> float:
        return sum(
            self.estimate_trade_risk(
                symbol,
                abs(int(position.get("quantity", 0) or 0)),
                float(position["entry_price"]),
                float(position["stop_loss"]),
            )
            for symbol, position in self.active_positions.items()
        )

    def available_daily_risk(self) -> float:
        self._refresh_session()
        remaining_daily_budget = (
            self.daily_max_loss
            - self.daily_realized_losses
            - self.open_position_risk()
        )
        return max(0.0, min(self.max_risk_per_trade, remaining_daily_budget))

    def daily_risk_exceeded(self) -> bool:
        self._refresh_session()
        return (
            self.daily_realized_losses + self.open_position_risk()
            > self.daily_max_loss + 1e-6
        )

    def daily_loss_limit_reached(self) -> bool:
        self._refresh_session()
        return self.daily_realized_losses >= self.daily_max_loss

    def record_trade_open(self, symbol: str, direction: str) -> None:
        self._refresh_session()
        self.daily_trade_count += 1
        self.session_trade_symbols.add(symbol)
        self.session_trade_counts[symbol] = self.session_trade_counts.get(symbol, 0) + 1
        logger.info("[%s] Recorded open trade for %s; daily_trade_count=%d", symbol, direction, self.daily_trade_count)

    def restore_session_trades(self, trades: list[dict]) -> None:
        """Restore today's symbol exposure and realized P&L from the journal."""
        self._refresh_session()
        self.session_trade_symbols.clear()
        self.session_trade_counts.clear()
        self.session_loss_stop_times.clear()
        closed_today = []
        for trade in trades:
            symbol = trade.get("ticker") or trade.get("symbol")
            try:
                timestamp = datetime.fromisoformat(
                    str(trade.get("timestamp", "")).replace("Z", "+00:00")
                )
            except (TypeError, ValueError):
                timestamp = None
            if timestamp is not None:
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                timestamp = timestamp.astimezone(IST)
            if (
                symbol
                and timestamp is not None
                and timestamp.date() == self._session_date
            ):
                symbol = str(symbol)
                self.session_trade_symbols.add(symbol)
                self.session_trade_counts[symbol] = (
                    self.session_trade_counts.get(symbol, 0) + 1
                )
            if trade.get("status") != "closed":
                continue
            try:
                closed_at = datetime.fromisoformat(
                    str(trade.get("closed_at", "")).replace("Z", "+00:00")
                )
            except (TypeError, ValueError):
                continue
            if closed_at.tzinfo is None:
                closed_at = closed_at.replace(tzinfo=timezone.utc)
            closed_at = closed_at.astimezone(IST)
            if closed_at.date() == self._session_date:
                try:
                    pnl = float(trade["pnl"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise RuntimeError(
                        "Cannot restore aggregate daily risk from a closed journal "
                        "trade with invalid P&L"
                    ) from exc
                if not math.isfinite(pnl):
                    raise RuntimeError(
                        "Cannot restore aggregate daily risk from a closed journal "
                        "trade with non-finite P&L"
                    )
                symbol = trade.get("ticker") or trade.get("symbol")
                reason = str(trade.get("reason", "")).upper()
                if (
                    symbol
                    and pnl < 0
                    and reason in {"STOP_LOSS", "TRAILING_STOP"}
                ):
                    self.session_loss_stop_times[str(symbol)] = closed_at
                closed_today.append((closed_at, pnl))

        closed_today.sort(key=lambda item: item[0])
        self.daily_pnl = sum(pnl for _, pnl in closed_today)
        self.daily_realized_losses = sum(
            max(-pnl, 0.0) for _, pnl in closed_today
        )
        self.consecutive_losses = 0
        for _, pnl in reversed(closed_today):
            if pnl < 0:
                self.consecutive_losses += 1
            else:
                break

    def record_trade_close(self, symbol: str, reason: str, pnl: float) -> None:
        self._refresh_session()
        pnl = float(pnl)
        if not math.isfinite(pnl):
            raise ValueError("Closed-trade P&L must be finite")
        self.daily_pnl += pnl
        self.daily_realized_losses += max(-pnl, 0.0)
        self.trade_history.append({"symbol": symbol, "reason": reason, "pnl": pnl, "time": datetime.now(IST)})
        if pnl < 0 and reason in {"STOP_LOSS", "TRAILING_STOP"}:
            self.session_loss_stop_times[symbol] = datetime.now(IST)
        if reason == "SIGNAL_REVERSAL":
            self.session_reversal_symbols.add(symbol)
        if pnl < 0 and abs(pnl) >= self.daily_max_loss * 0.5:
            self.session_reversal_symbols.add(symbol)

        perf = self.symbol_performance.setdefault(symbol, {"trades": 0, "wins": 0, "win_rate": 100.0})
        perf["trades"] = int(perf.get("trades", 0)) + 1
        if pnl > 0:
            perf["wins"] = int(perf.get("wins", 0)) + 1
        perf["win_rate"] = (perf["wins"] / perf["trades"]) * 100.0

        if pnl < 0:
            self.consecutive_losses += 1
            self.recent_loss_symbols[symbol] = datetime.now(IST)
        else:
            self.consecutive_losses = 0
            self.recent_loss_symbols.pop(symbol, None)

    def _refresh_session(self) -> None:
        session_date = datetime.now(IST).date()
        if session_date == self._session_date:
            return
        self._session_date = session_date
        self.daily_trade_count = 0
        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        self.daily_realized_losses = 0.0
        self.session_trade_symbols.clear()
        self.session_trade_counts.clear()
        self.session_loss_stop_times.clear()
        self.session_reversal_symbols.clear()

    def register_position(
        self,
        symbol: str,
        direction: str,
        quantity: int,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        signal_score: Optional[int] = None,
        staged_targets_enabled: bool = False,
        target_increment_pct: float = 0.10,
        minimum_signal_score: Optional[int] = None,
        strong_signal_score: int = 82,
        weak_signal_lockin_pct: float = 0.05,
        milestone_window_minutes: int = 5,
        strong_milestone_window_minutes: int = 10,
        entry_time: Optional[datetime] = None,
        milestone_started_at: Optional[datetime] = None,
        target_stage: int = 0,
        trailing_stop: Optional[float] = None,
        current_signal_score: Optional[int] = None,
        decision_window_minutes: Optional[int] = None,
        weak_signal_adverse_checks: int = 0,
        trailing_enabled: Optional[bool] = None,
        exit_strategy: Optional[str] = None,
        runner_activation_r: Optional[float] = None,
        runner_gap_r: Optional[float] = None,
        adaptive_breakeven_r: Optional[float] = None,
        adaptive_trail_activation_r: Optional[float] = None,
        adaptive_trail_gap_r: Optional[float] = None,
        adaptive_runner_activation_r: Optional[float] = None,
        adaptive_runner_gap_r: Optional[float] = None,
        adaptive_exit_mode: Optional[str] = None,
        max_favorable_r: float = 0.0,
        highest_price: Optional[float] = None,
        lowest_price: Optional[float] = None,
        trailing_active: bool = False,
    ) -> None:
        """Register a new position."""
        target_distance = abs(take_profit - entry_price)
        initial_risk_distance = abs(entry_price - stop_loss)
        if exit_strategy == PAPER_OPTION_TRAIL_RUNNER:
            runner_activation_r = float(
                1.0 if runner_activation_r is None else runner_activation_r
            )
            runner_gap_r = float(2.0 if runner_gap_r is None else runner_gap_r)
            if (
                not math.isfinite(runner_activation_r)
                or runner_activation_r <= 0
                or not math.isfinite(runner_gap_r)
                or runner_gap_r <= 0
                or not math.isfinite(initial_risk_distance)
                or initial_risk_distance <= 0
            ):
                raise ValueError("Invalid risk or R multiple for option trail runner")
        if exit_strategy == PAPER_OPTION_ADAPTIVE_EXIT:
            adaptive_values = (
                0.5
                if adaptive_breakeven_r is None
                else float(adaptive_breakeven_r),
                1.0
                if adaptive_trail_activation_r is None
                else float(adaptive_trail_activation_r),
                1.0
                if adaptive_trail_gap_r is None
                else float(adaptive_trail_gap_r),
                2.0
                if adaptive_runner_activation_r is None
                else float(adaptive_runner_activation_r),
                1.0
                if adaptive_runner_gap_r is None
                else float(adaptive_runner_gap_r),
            )
            (
                adaptive_breakeven_r,
                adaptive_trail_activation_r,
                adaptive_trail_gap_r,
                adaptive_runner_activation_r,
                adaptive_runner_gap_r,
            ) = adaptive_values
            if (
                not all(
                    math.isfinite(value) and value > 0
                    for value in adaptive_values
                )
                or adaptive_breakeven_r > adaptive_trail_activation_r
                or adaptive_trail_activation_r >= adaptive_runner_activation_r
                or not math.isfinite(initial_risk_distance)
                or initial_risk_distance <= 0
                or not math.isfinite(max_favorable_r)
                or max_favorable_r < 0
            ):
                raise ValueError(
                    "Invalid risk or R thresholds for adaptive option exit"
                )
        registered_at = self._normalize_position_time(entry_time)
        strong_threshold = int(strong_signal_score)
        entry_score = int(signal_score) if signal_score is not None else None
        chosen_window = decision_window_minutes
        if chosen_window is None:
            chosen_window = (
                strong_milestone_window_minutes
                if entry_score is not None and entry_score >= strong_threshold
                else milestone_window_minutes
            )
        self.active_positions[symbol] = {
            "direction": direction,
            "quantity": quantity,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "initial_target_distance": target_distance,
            "initial_risk_distance": initial_risk_distance,
            "signal_score": entry_score,
            "current_signal_score": (
                int(current_signal_score)
                if current_signal_score is not None
                else entry_score
            ),
            "staged_targets_enabled": staged_targets_enabled,
            "target_increment_pct": max(float(target_increment_pct), 0.0),
            "minimum_signal_score": minimum_signal_score,
            "strong_signal_score": strong_threshold,
            "weak_signal_lockin_pct": max(float(weak_signal_lockin_pct), 0.0),
            "weak_signal_adverse_checks": max(int(weak_signal_adverse_checks), 0),
            "trailing_enabled": trailing_enabled,
            "exit_strategy": exit_strategy,
            "runner_activation_r": runner_activation_r,
            "runner_gap_r": runner_gap_r,
            "adaptive_breakeven_r": adaptive_breakeven_r,
            "adaptive_trail_activation_r": adaptive_trail_activation_r,
            "adaptive_trail_gap_r": adaptive_trail_gap_r,
            "adaptive_runner_activation_r": adaptive_runner_activation_r,
            "adaptive_runner_gap_r": adaptive_runner_gap_r,
            "adaptive_exit_mode": adaptive_exit_mode or "initial_stop",
            "max_favorable_r": max(float(max_favorable_r), 0.0),
            "milestone_window_minutes": max(int(milestone_window_minutes), 1),
            "strong_milestone_window_minutes": max(
                int(strong_milestone_window_minutes), 1
            ),
            "decision_window_minutes": max(int(chosen_window), 1),
            "target_stage": max(int(target_stage), 0),
            "milestone_reached_pct": max(int(target_stage), 0)
            * max(float(target_increment_pct), 0.0)
            * 100.0,
            "highest_price": (
                entry_price if highest_price is None else float(highest_price)
            ),
            "lowest_price": (
                entry_price if lowest_price is None else float(lowest_price)
            ),
            "trailing_stop": trailing_stop,
            "trailing_active": bool(trailing_active),
            "entry_time": registered_at,
            "milestone_started_at": self._normalize_position_time(
                milestone_started_at or registered_at
            ),
        }
        logger.info(
            f"[{symbol}] Position registered: {direction} {quantity} "
            f"@ {entry_price:.2f} | SL={stop_loss:.2f} TP={take_profit:.2f}"
        )

    def update_trailing_stop(
        self, symbol: str, price: float, now: Optional[datetime] = None
    ) -> Optional[float]:
        """Update and return a ratcheting stop after a favorable move."""
        position = self.active_positions.get(symbol)
        trailing_enabled = (
            bool(position.get("trailing_enabled"))
            if position and position.get("trailing_enabled") is not None
            else self.trailing_enabled
        )
        if not position or (
            not trailing_enabled and not position.get("staged_targets_enabled")
        ):
            return None

        position["target_advanced"] = False
        if (
            position.get("staged_targets_enabled")
            and position.get("exit_strategy") != PAPER_OPTION_TRAIL_RUNNER
        ):
            return self._update_milestone_stop(position, price, now)

        entry_price = float(position["entry_price"])
        if position.get("exit_strategy") == PAPER_OPTION_TRAIL_RUNNER:
            risk_distance = float(position["initial_risk_distance"])
            activation_distance = (
                risk_distance * float(position["runner_activation_r"])
            )
            trailing_distance = risk_distance * float(position["runner_gap_r"])

            if position["direction"] == "BUY":
                position["highest_price"] = max(
                    float(position["highest_price"]), price
                )
                if position["highest_price"] - entry_price >= activation_distance:
                    position["trailing_active"] = True
                if not position["trailing_active"]:
                    return None
                candidate = max(
                    float(position["stop_loss"]),
                    position["highest_price"] - trailing_distance,
                )
                previous = position["trailing_stop"]
                position["trailing_stop"] = (
                    candidate
                    if previous is None
                    else max(float(previous), candidate)
                )
            else:
                position["lowest_price"] = min(
                    float(position["lowest_price"]), price
                )
                if entry_price - position["lowest_price"] >= activation_distance:
                    position["trailing_active"] = True
                if not position["trailing_active"]:
                    return None
                candidate = min(
                    float(position["stop_loss"]),
                    position["lowest_price"] + trailing_distance,
                )
                previous = position["trailing_stop"]
                position["trailing_stop"] = (
                    candidate
                    if previous is None
                    else min(float(previous), candidate)
                )
            return float(position["trailing_stop"])

        if position.get("exit_strategy") == PAPER_OPTION_ADAPTIVE_EXIT:
            risk_distance = float(position["initial_risk_distance"])
            if position["direction"] == "BUY":
                position["highest_price"] = max(
                    float(position["highest_price"]), price
                )
                favorable_distance = float(position["highest_price"]) - entry_price
            else:
                position["lowest_price"] = min(
                    float(position["lowest_price"]), price
                )
                favorable_distance = entry_price - float(position["lowest_price"])

            max_favorable_r = max(
                float(position.get("max_favorable_r", 0.0)),
                favorable_distance / risk_distance,
            )
            position["max_favorable_r"] = max_favorable_r
            breakeven_r = float(position["adaptive_breakeven_r"])
            activation_r = float(position["adaptive_trail_activation_r"])
            runner_r = float(position["adaptive_runner_activation_r"])
            if max_favorable_r >= runner_r:
                mode = "runner"
                trailing_gap_r = float(position["adaptive_runner_gap_r"])
            elif max_favorable_r >= activation_r:
                mode = "profit_trail"
                trailing_gap_r = float(position["adaptive_trail_gap_r"])
            elif max_favorable_r >= breakeven_r:
                mode = "breakeven"
                trailing_gap_r = 0.0
            else:
                mode = "initial_stop"
                trailing_gap_r = 0.0

            if mode == "initial_stop":
                return None

            position["adaptive_exit_mode"] = mode
            position["trailing_active"] = True
            peak_price = (
                float(position["highest_price"])
                if position["direction"] == "BUY"
                else float(position["lowest_price"])
            )
            if mode == "breakeven":
                candidate = entry_price
            elif position["direction"] == "BUY":
                candidate = peak_price - trailing_gap_r * risk_distance
            else:
                candidate = peak_price + trailing_gap_r * risk_distance
            if position["direction"] == "BUY":
                candidate = max(float(position["stop_loss"]), candidate)
                previous = position["trailing_stop"]
                position["trailing_stop"] = (
                    candidate
                    if previous is None
                    else max(float(previous), candidate)
                )
            else:
                candidate = min(float(position["stop_loss"]), candidate)
                previous = position["trailing_stop"]
                position["trailing_stop"] = (
                    candidate
                    if previous is None
                    else min(float(previous), candidate)
                )
            return float(position["trailing_stop"])

        take_profit = float(position["take_profit"])
        target_distance = float(position.get("initial_target_distance", 0.0))
        if target_distance <= 0:
            return None

        activation_distance = target_distance * self.trailing_activation_ratio
        trailing_distance = target_distance * self.trailing_distance_ratio

        if position["direction"] == "BUY":
            position["highest_price"] = max(float(position["highest_price"]), price)
            if position.get("staged_targets_enabled") and price >= take_profit:
                position["target_stage"] = int(position.get("target_stage", 0)) + 1
                next_target = entry_price * (
                    1.0
                    + (target_distance / entry_price)
                    + position["target_stage"] * float(position["target_increment_pct"])
                )
                position["take_profit"] = max(take_profit, next_target)
                position["target_advanced"] = True
            if price - entry_price >= activation_distance:
                position["trailing_active"] = True
            if not position["trailing_active"]:
                return None
            candidate = position["highest_price"] - trailing_distance
            previous = position["trailing_stop"]
            position["trailing_stop"] = (
                candidate if previous is None else max(float(previous), candidate)
            )
        else:
            position["lowest_price"] = min(float(position["lowest_price"]), price)
            if position.get("staged_targets_enabled") and price <= take_profit:
                position["target_stage"] = int(position.get("target_stage", 0)) + 1
                next_target = entry_price * (
                    1.0
                    - (target_distance / entry_price)
                    - position["target_stage"] * float(position["target_increment_pct"])
                )
                position["take_profit"] = min(take_profit, next_target)
                position["target_advanced"] = True
            if entry_price - price >= activation_distance:
                position["trailing_active"] = True
            if not position["trailing_active"]:
                return None
            candidate = position["lowest_price"] + trailing_distance
            previous = position["trailing_stop"]
            position["trailing_stop"] = (
                candidate if previous is None else min(float(previous), candidate)
            )

        return float(position["trailing_stop"])

    def _update_milestone_stop(
        self, position: dict, price: float, now: Optional[datetime] = None
    ) -> Optional[float]:
        entry_price = float(position["entry_price"])
        step_pct = float(position.get("target_increment_pct", 0.0))
        if entry_price <= 0 or step_pct <= 0:
            return position.get("trailing_stop")

        direction = 1.0 if position["direction"] == "BUY" else -1.0
        favorable_change_pct = direction * (price - entry_price) / entry_price
        stage = int(position.get("target_stage", 0))
        now = self._normalize_position_time(now)
        advanced = False

        while favorable_change_pct >= (stage + 1) * step_pct:
            stage += 1
            score = position.get("current_signal_score")
            strong_threshold = int(position.get("strong_signal_score", 82))
            lockin_pct = max((stage - 1) * step_pct, 0.0)
            if score is None or int(score) < strong_threshold:
                lockin_pct += float(position.get("weak_signal_lockin_pct", 0.05))

            candidate = round(entry_price * (1.0 + direction * lockin_pct), 10)
            previous = position.get("trailing_stop")
            if previous is None:
                position["trailing_stop"] = candidate
            elif direction > 0:
                position["trailing_stop"] = max(float(previous), candidate)
            else:
                position["trailing_stop"] = min(float(previous), candidate)

            position["target_stage"] = stage
            position["milestone_reached_pct"] = stage * step_pct * 100.0
            position["milestone_started_at"] = now
            position["target_advanced"] = True
            advanced = True

        if advanced:
            next_stage = int(position["target_stage"]) + 1
            position["take_profit"] = round(
                entry_price * (1.0 + direction * next_stage * step_pct), 10
            )

        return (
            float(position["trailing_stop"])
            if position.get("trailing_stop") is not None
            else None
        )

    def milestone_timebox_expired(
        self, symbol: str, now: Optional[datetime] = None
    ) -> bool:
        """Return whether the current milestone decision window has elapsed."""
        position = self.active_positions.get(symbol)
        if not position or not position.get("staged_targets_enabled"):
            return False

        window_minutes = int(position.get("decision_window_minutes", 5))
        started_at = self._normalize_position_time(
            position.get("milestone_started_at")
        )
        current_time = self._normalize_position_time(now)
        return current_time >= started_at + timedelta(minutes=window_minutes)

    def extend_milestone_timebox(
        self, symbol: str, now: Optional[datetime] = None
    ) -> Optional[datetime]:
        """Start another decision window for an open staged position."""
        position = self.active_positions.get(symbol)
        if not position or not position.get("staged_targets_enabled"):
            return None

        extended_at = self._normalize_position_time(now)
        position["milestone_started_at"] = extended_at
        return extended_at

    @staticmethod
    def _normalize_position_time(value: Optional[datetime]) -> datetime:
        current_time = value or datetime.now(IST)
        if current_time.tzinfo is None:
            return current_time.replace(tzinfo=IST)
        return current_time.astimezone(IST)
    
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
        premium_stop_pct: float = MAX_TRADE_RISK_PCT / 100.0,
    ) -> int:
        """Premium-based sizing for options: risk = premium * quantity * stop_pct."""
        if (
            not math.isfinite(premium)
            or premium <= 0
            or not math.isfinite(premium_stop_pct)
            or premium_stop_pct <= 0
            or premium_stop_pct > MAX_TRADE_RISK_PCT / 100.0
        ):
            logger.warning(
                "[%s] Option sizing rejected: premium and stop risk must be "
                "positive and stop risk cannot exceed %.1f%% of deployed capital",
                symbol,
                MAX_TRADE_RISK_PCT,
            )
            return 0
        risk_budget = (
            max_risk_per_trade
            if max_risk_per_trade is not None
            else self.available_daily_risk()
        )
        if risk_budget <= 0:
            return 0
        specs = self.contract_specs.get(symbol, {})
        lot_size = int(specs.get("lot_size", 1))
        multiplier = float(specs.get("multiplier", self.MULTIPLIERS.get(symbol, 1)))
        if lot_size <= 0 or not math.isfinite(multiplier) or multiplier <= 0:
            raise ValueError(f"Option contract {symbol} has invalid risk specifications")
        stop_value_per_lot = premium * premium_stop_pct * lot_size * multiplier
        max_lots = math.floor(
            risk_budget / max(stop_value_per_lot, 1e-6) + 1e-12
        )
        if max_lots < 1:
            return 0
        return min(max_lots, 5) * lot_size
