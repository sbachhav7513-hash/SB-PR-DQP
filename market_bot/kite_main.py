"""
Zerodha Kite Connect based trading bot with live market streaming.
Uses real-time ticks aggregated into bars, with intraday futures optimization.
"""

import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from .accuracy_filters import AccuracyFilters
from .bar_builder import BarBuilder, Bar
from .change_tracking import log_startup_identity
from .engine import (
    SupportResistanceReversal,
    aggregate_ohlcv_bars,
    detect_support_resistance_reversal,
    filter_signal_by_context,
    market_session_state,
    score_market,
)
from .ema_reentry import find_ema_reentry_signal
from .intraday_manager import (
    IntradayManager,
    PAPER_OPTION_ADAPTIVE_EXIT,
    PAPER_OPTION_TRAIL_RUNNER,
)
from .kite_provider import KiteConfig, KiteHistoricalProvider, KiteMarketStream, Tick
from .market_news import NewsMonitor, apply_news_filter
from .option_candle_store import OptionCandleRecorder
from .risk_manager import (
    MAX_TRADE_RISK_PCT,
    build_risk_plan,
)
from .strategy_config import (
    load_strategy_config,
    resolve_execution_mode,
    strategy_config_hash,
)
from .strategy import ema
from .telegram_notifier import TelegramNotifier
from .trade_journal import DecisionJournal, PaperShadowExitJournal, TradeJournal
from .weekly_report import (
    write_daily_review,
    write_daily_summary,
    write_weekly_report,
    write_weekly_review,
)


log_path = Path("kite_bot.log")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_path, mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
HEARTBEAT_INTERVAL_SECONDS = 30 * 60
OPTION_MIN_CANDLE_BODY_RATIO = 0.60
SIGNAL_WEAKEN_CONFIRMATIONS = 2


def _aligned_option_volume_history(
    signal_bars: list[Bar],
    option_bars: list[Bar],
    interval_seconds: int,
) -> list[Dict]:
    """Align each underlying bar with at most one nearby option-volume bar."""
    option_times = [bar.timestamp.timestamp() for bar in option_bars]
    unused_indices = set(range(len(option_bars)))
    tolerance_seconds = max(float(interval_seconds) / 2.0, 0.0)
    aligned = []

    for signal_bar in signal_bars:
        signal_time = signal_bar.timestamp.timestamp()
        best_index = None
        best_delta = tolerance_seconds
        for index in unused_indices:
            delta = abs(option_times[index] - signal_time)
            if delta < best_delta:
                best_index = index
                best_delta = delta
        if best_index is None:
            aligned.append({"volume": None})
        else:
            unused_indices.remove(best_index)
            aligned.append({"volume": option_bars[best_index].volume})
    return aligned


class KiteTradingBot:
    def _late_window_blocked(self, now: Optional[datetime] = None) -> bool:
        if not self.config.get("late_window_enabled", True):
            return False
        start = datetime.strptime(
            str(self.config.get("late_window_start", "12:00")), "%H:%M"
        ).time()
        end = datetime.strptime(
            str(self.config.get("late_window_end", "13:00")), "%H:%M"
        ).time()
        if start == end:
            return False
        now = now or datetime.now(IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        else:
            now = now.astimezone(IST)
        current = now.time()
        return start <= current < end if start < end else current >= start or current < end

    def _options_enabled(self) -> bool:
        return self.config.get("trading_mode") in {"intraday_options", "intraday_both"}

    def _option_adaptive_exit_enabled(self, symbol: str) -> bool:
        return (
            self._options_enabled()
            and symbol.endswith(("_CE", "_PE"))
            and self.config.get("option_adaptive_exit_enabled", True)
        )

    def _option_adaptive_exit_r_values(
        self,
    ) -> tuple[float, float, float, float, float]:
        values = (
            float(self.config.get("option_adaptive_breakeven_r", 0.5)),
            float(self.config.get("option_adaptive_trail_activation_r", 1.0)),
            float(self.config.get("option_adaptive_trail_gap_r", 1.0)),
            float(self.config.get("option_adaptive_runner_activation_r", 2.0)),
            float(self.config.get("option_adaptive_runner_gap_r", 1.0)),
        )
        breakeven_r, activation_r, _, runner_r, _ = values
        if (
            not all(math.isfinite(value) and value > 0 for value in values)
            or breakeven_r > activation_r
            or activation_r >= runner_r
        ):
            raise ValueError("Invalid adaptive-exit R thresholds")
        return values

    def _entry_risk_cap(self) -> Optional[float]:
        configured_cap = self.config.get("max_risk_per_trade")
        if configured_cap is None:
            return None
        cap = float(configured_cap)
        if not math.isfinite(cap) or cap <= 0:
            raise ValueError("max_risk_per_trade must be finite and positive")
        return cap

    def _calculate_position_size(
        self, symbol: str, entry_price: float, stop_loss_price: float
    ) -> int:
        if (
            not math.isfinite(float(entry_price))
            or entry_price <= 0
            or not math.isfinite(float(stop_loss_price))
        ):
            raise ValueError(
                "Entry and stop prices must be finite and entry must be positive"
            )
        stop_risk_pct = abs(entry_price - stop_loss_price) / entry_price * 100.0
        if stop_risk_pct > MAX_TRADE_RISK_PCT + 1e-9:
            evaluations = getattr(self, "_pending_entry_evaluations", None)
            if evaluations is None:
                evaluations = {}
                self._pending_entry_evaluations = evaluations
            evaluations[symbol] = {
                "accepted": False,
                "rejection_reason": "stop_risk_exceeds_deployed_capital_limit",
                "stop_risk_pct": stop_risk_pct,
            }
            return 0
        risk_cap = self._entry_risk_cap()
        if risk_cap is None:
            return self.intraday_manager.calculate_position_size(
                symbol, entry_price, stop_loss_price
            )

        specs = self.intraday_manager.contract_specs.get(symbol, {})
        lot_size = int(
            specs.get(
                "lot_size",
                self.intraday_manager.LOT_SIZES.get(symbol, 1),
            )
        )
        multiplier = float(
            specs.get(
                "multiplier",
                self.intraday_manager.MULTIPLIERS.get(symbol, 1),
            )
        )
        risk_per_lot = (
            abs(float(entry_price) - float(stop_loss_price))
            * lot_size
            * multiplier
        )
        quantity = self.intraday_manager.calculate_position_size(
            symbol,
            entry_price,
            stop_loss_price,
            max_risk_per_trade=risk_cap,
        )
        evaluations = getattr(self, "_pending_entry_evaluations", None)
        if evaluations is None:
            evaluations = {}
            self._pending_entry_evaluations = evaluations
        evaluation = {
            "max_risk_per_trade": risk_cap,
            "contract_lot_size": lot_size,
            "risk_per_lot_rupees": risk_per_lot,
            "proposed_quantity": quantity,
            "accepted": quantity > 0,
        }
        if quantity == 0 and risk_per_lot > risk_cap:
            evaluation["rejection_reason"] = "one_lot_exceeds_trade_risk_cap"
        elif quantity == 0:
            evaluation["rejection_reason"] = (
                "remaining_session_risk_below_one_lot"
            )
        elif quantity > 0:
            evaluation["estimated_initial_risk_rupees"] = (
                risk_per_lot * (quantity // max(lot_size, 1))
            )
        evaluations[symbol] = evaluation
        return quantity

    def _entry_cutoff_reason(
        self, now: Optional[datetime] = None
    ) -> Optional[str]:
        minutes = int(
            self.config.get("entry_cutoff_minutes_before_close", 45)
        )
        if not 0 <= minutes <= 375:
            raise ValueError(
                "entry_cutoff_minutes_before_close must be between 0 and 375"
            )
        if minutes == 0:
            return None

        now = now or datetime.now(IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        else:
            now = now.astimezone(IST)
        market_open = getattr(
            self.intraday_manager, "MARKET_OPEN", datetime.strptime("09:15", "%H:%M").time()
        )
        market_close = getattr(
            self.intraday_manager, "MARKET_CLOSE", datetime.strptime("15:30", "%H:%M").time()
        )
        if not market_open <= now.time() < market_close:
            return None

        close_at = datetime.combine(now.date(), market_close, tzinfo=IST)
        if now >= close_at - timedelta(minutes=minutes):
            return f"entry_cutoff_blocked:{minutes}m_before_close"
        return None

    def _ema_reentry_cutoff(self, trade_date) -> datetime:
        minutes = int(
            self.config.get("entry_cutoff_minutes_before_close", 45)
        )
        if not 0 <= minutes <= 375:
            raise ValueError(
                "entry_cutoff_minutes_before_close must be between 0 and 375"
            )
        market_close = getattr(
            self.intraday_manager,
            "MARKET_CLOSE",
            datetime.strptime("15:30", "%H:%M").time(),
        )
        close_at = datetime.combine(trade_date, market_close, tzinfo=IST)
        return close_at - timedelta(minutes=minutes)

    @staticmethod
    def _is_option_dynamic_exit(position: Optional[dict]) -> bool:
        return bool(position) and position.get("exit_strategy") in {
            PAPER_OPTION_TRAIL_RUNNER,
            PAPER_OPTION_ADAPTIVE_EXIT,
        }

    def _option_target_increment(self) -> float:
        """Return the fixed option-premium milestone size as a fraction."""
        return float(self.config.get("option_milestone_pct", 0.10))

    def _staged_option_targets_enabled(self, symbol: str) -> bool:
        return (
            self._options_enabled()
            and "_" in symbol
            and self.config.get("staged_option_targets_enabled", True)
        )

    def _option_entry_target_pct(self, staged_targets_enabled: bool) -> float:
        if staged_targets_enabled:
            return float(self.config.get("option_milestone_pct", 0.10))
        return float(self.config.get("option_premium_target_pct", 0.20))

    def _option_candle_min_body_ratio(self) -> float:
        return float(
            self.config.get(
                "option_min_candle_body_ratio", OPTION_MIN_CANDLE_BODY_RATIO
            )
        )

    @staticmethod
    def _has_option_candle_momentum(
        signal: str,
        candle: Dict,
        minimum_body_ratio: float = OPTION_MIN_CANDLE_BODY_RATIO,
    ) -> bool:
        """Require a directional candle body to meet the configured range ratio."""
        try:
            candle_open = float(candle["open"])
            candle_high = float(candle["high"])
            candle_low = float(candle["low"])
            candle_close = float(candle["close"])
        except (KeyError, TypeError, ValueError):
            return False

        values = (candle_open, candle_high, candle_low, candle_close)
        if not all(math.isfinite(value) for value in values):
            return False

        candle_range = candle_high - candle_low
        if (
            candle_range <= 0
            or candle_high < max(candle_open, candle_close)
            or candle_low > min(candle_open, candle_close)
        ):
            return False

        direction_matches = (
            candle_close > candle_open
            if signal == "BUY"
            else candle_close < candle_open
            if signal == "SELL"
            else False
        )
        body_ratio = abs(candle_close - candle_open) / candle_range
        return (
            math.isfinite(minimum_body_ratio)
            and 0 < minimum_body_ratio <= 1
            and direction_matches
            and body_ratio >= minimum_body_ratio
        )

    def _calculate_option_quantity(
        self, symbol: str, premium: float, premium_stop_pct: float
    ) -> int:
        lot_size = int(self.intraday_manager.contract_specs.get(symbol, {}).get("lot_size", 1))
        minimum_lots = int(self.config.get("option_min_lots", 1))
        maximum_lots = int(self.config.get("option_max_lots", 3))
        if lot_size <= 0 or minimum_lots < 1 or maximum_lots < minimum_lots:
            raise ValueError("Option lot sizing requires valid lot bounds and contract specs")

        multiplier = float(
            self.intraday_manager.contract_specs.get(symbol, {}).get(
                "multiplier", self.intraday_manager.MULTIPLIERS.get(symbol, 1)
            )
        )
        if not math.isfinite(multiplier) or multiplier <= 0:
            raise ValueError(f"Option contract {symbol} has an invalid multiplier")
        unit_risk = max(premium, 0.01) * premium_stop_pct * multiplier
        per_lot_risk = unit_risk * lot_size
        risk_cap = self._entry_risk_cap()
        risk_budget = min(
            self.intraday_manager.available_daily_risk(),
            self._option_trade_risk_limit(symbol, premium),
        )
        if risk_cap is not None:
            risk_budget = min(risk_budget, risk_cap)

        evaluations = getattr(self, "_pending_entry_evaluations", None)
        if evaluations is None:
            evaluations = {}
            self._pending_entry_evaluations = evaluations
        evaluation = {
            "risk_cap_rupees": risk_cap,
            "option_lot_size": lot_size,
            "option_risk_per_lot_rupees": per_lot_risk,
            "entry_risk_budget_rupees": risk_budget,
        }
        if (
            not math.isfinite(premium_stop_pct)
            or premium_stop_pct <= 0
            or premium_stop_pct > MAX_TRADE_RISK_PCT / 100.0
        ):
            evaluation["accepted"] = False
            evaluation["rejection_reason"] = (
                "stop_risk_exceeds_deployed_capital_limit"
            )
            evaluations[symbol] = evaluation
            return 0
        if not math.isfinite(per_lot_risk) or per_lot_risk <= 0:
            evaluation["accepted"] = False
            evaluation["rejection_reason"] = "invalid_entry_stop_risk"
            evaluations[symbol] = evaluation
            return 0
        if risk_cap is not None and per_lot_risk > risk_cap:
            evaluation["accepted"] = False
            evaluation["rejection_reason"] = "one_lot_exceeds_trade_risk_cap"
            evaluations[symbol] = evaluation
            logger.info(
                "[%s] Entry rejected: one lot risks %.2f, above the %.2f cap",
                symbol,
                per_lot_risk,
                risk_cap,
            )
            return 0

        risk_sized_quantity = self.intraday_manager.calculate_option_size(
            symbol,
            premium=max(premium, 0.01),
            max_risk_per_trade=risk_budget,
            premium_stop_pct=premium_stop_pct,
        )
        risk_sized_lots = risk_sized_quantity // lot_size
        if risk_cap is not None:
            risk_sized_lots = min(
                risk_sized_lots,
                math.floor(risk_budget / per_lot_risk + 1e-12),
            )
        if risk_sized_lots < minimum_lots:
            if risk_cap is not None:
                evaluation["accepted"] = False
                evaluation["rejection_reason"] = "available_risk_budget_below_one_lot"
                evaluations[symbol] = evaluation
            return 0
        quantity = min(risk_sized_lots, maximum_lots) * lot_size
        evaluation.update(
            {
                "accepted": True,
                "proposed_quantity": quantity,
                "estimated_initial_risk_rupees": unit_risk * quantity,
            }
        )
        if risk_cap is not None:
            evaluations[symbol] = evaluation
        return quantity

    def _try_option_range_breakout(
        self, symbol: str, bars: list[Bar]
    ) -> Optional[str]:
        """Open a long option after a confirmed premium range breakout."""
        if (
            not self.config.get("option_range_breakout_enabled", False)
            or not self._options_enabled()
            or not symbol.endswith(("_CE", "_PE"))
        ):
            return None

        try:
            lookback = int(self.config.get("option_range_lookback_bars", 15))
            confirmation_bars = int(
                self.config.get("option_range_confirmation_bars", 0)
            )
            target_r = float(self.config.get("option_range_target_r", 2.0))
        except (TypeError, ValueError, OverflowError):
            logger.error("[%s] Invalid option range-breakout settings", symbol)
            return "PAPER_RANGE_BREAKOUT_INVALID_SETTINGS"
        if (
            lookback < 2
            or confirmation_bars not in {0, 1}
            or not math.isfinite(target_r)
            or target_r <= 0
        ):
            logger.error("[%s] Invalid option range-breakout settings", symbol)
            return "PAPER_RANGE_BREAKOUT_INVALID_SETTINGS"
        if len(bars) < lookback + confirmation_bars + 1:
            return None

        breakout_offset = confirmation_bars + 1
        prior_range = bars[
            -(lookback + confirmation_bars + 1) : -breakout_offset
        ]
        breakout_bar = bars[-breakout_offset]
        previous_bar = bars[-breakout_offset - 1]
        latest_bar = bars[-1]
        range_high = max(item.high for item in prior_range)
        range_low = min(item.low for item in prior_range)
        if not (
            math.isfinite(range_high)
            and math.isfinite(range_low)
            and breakout_bar.close > range_high
            and previous_bar.close <= range_high
        ):
            return None
        if confirmation_bars and latest_bar.close <= range_high:
            return (
                "PAPER_RANGE_BREAKOUT_REJECTED:"
                "follow_through_close_below_range"
            )

        try:
            breakout_volume = float(breakout_bar.volume)
            prior_volumes = [float(item.volume) for item in prior_range]
        except (TypeError, ValueError, OverflowError):
            logger.error("[%s] Invalid volume in option range-breakout bars", symbol)
            return "PAPER_RANGE_BREAKOUT_REJECTED:invalid_volume_data"
        if (
            not math.isfinite(breakout_volume)
            or breakout_volume < 0
            or any(not math.isfinite(volume) or volume < 0 for volume in prior_volumes)
        ):
            logger.error("[%s] Invalid volume in option range-breakout bars", symbol)
            return "PAPER_RANGE_BREAKOUT_REJECTED:invalid_volume_data"
        average_prior_volume = sum(prior_volumes) / lookback
        if breakout_volume <= 0 or breakout_volume < average_prior_volume:
            logger.info(
                "[%s] Paper range breakout rejected by volume gate: "
                "breakout=%.0f prior_%d_bar_average=%.0f",
                symbol,
                breakout_volume,
                lookback,
                average_prior_volume,
            )
            return (
                "PAPER_RANGE_BREAKOUT_REJECTED:"
                f"breakout_volume_below_{lookback}_bar_average"
            )

        session_state = market_session_state(
            [item.to_dict() for item in bars], now=datetime.now(IST)
        )
        if session_state != "REGULAR_SESSION":
            return "PAPER_RANGE_BREAKOUT_REJECTED:outside_regular_session"

        manager = getattr(self, "intraday_manager", None)
        if symbol in getattr(manager, "active_positions", {}):
            return "PAPER_RANGE_BREAKOUT_REJECTED:position_already_open"

        signal = "BUY" if symbol.endswith("_CE") else "SELL"
        allowed, quality_reason = self._option_quality_gate(
            symbol, signal, score=None
        )
        if not allowed:
            logger.info(
                "[%s] Paper option range breakout rejected by quote-quality gate: %s",
                symbol,
                quality_reason,
            )
            return f"PAPER_RANGE_BREAKOUT_REJECTED:{quality_reason}"
        self._capture_eligible_option_candles(symbol, bars)

        quote = getattr(self, "option_quote_cache", {}).get(symbol, {})
        raw_entry_price = quote.get("last_price", quote.get("premium"))
        if raw_entry_price is None:
            raw_entry_price = latest_bar.close
        try:
            entry_price = float(raw_entry_price)
        except (TypeError, ValueError, OverflowError):
            return "PAPER_RANGE_BREAKOUT_REJECTED:invalid_quote_price"
        if not math.isfinite(entry_price) or entry_price <= range_high:
            return "PAPER_RANGE_BREAKOUT_REJECTED:price_retreated_below_range"

        stream = getattr(self, "kite_stream", None)
        try:
            tick_size = float(
                getattr(stream, "contract_tick_sizes", {}).get(symbol, 0.05) or 0.05
            )
        except (TypeError, ValueError, OverflowError):
            tick_size = 0.05
        if not math.isfinite(tick_size) or tick_size <= 0:
            tick_size = 0.05
        stop_price = range_low - tick_size
        risk_per_unit = entry_price - stop_price
        if (
            not math.isfinite(stop_price)
            or not math.isfinite(risk_per_unit)
            or stop_price <= 0
            or risk_per_unit <= 0
        ):
            logger.error("[%s] Invalid range-breakout stop calculation", symbol)
            return "PAPER_RANGE_BREAKOUT_REJECTED:invalid_stop"

        outcome = self._handle_buy_signal(
            symbol,
            entry_price,
            0,
            strategy_variant="option_range_breakout",
            minimum_signal_score=0,
            paper_range_stop=stop_price,
            paper_range_target_r=target_r,
        )
        logger.info(
            "[%s] Paper range breakout: high=%.2f low=%.2f entry=%.2f "
            "stop=%.2f target=%.2f outcome=%s",
            symbol,
            range_high,
            range_low,
            entry_price,
            stop_price,
            entry_price + risk_per_unit * target_r,
            outcome,
        )
        return f"PAPER_RANGE_BREAKOUT_{outcome.upper()}"

    def _support_reversal_candidate(
        self, symbol: str, underlying_bars: list[Bar]
    ) -> Optional[SupportResistanceReversal]:
        """Find a deduplicated reversal from completed underlying bars."""
        if (
            not self.config.get("support_reversal_enabled", False)
            or not self._options_enabled()
            or not symbol.endswith(("_CE", "_PE"))
        ):
            return None

        underlying = symbol.rsplit("_", 1)[0].upper()
        try:
            source_interval = int(self.config.get("bar_interval_seconds", 60))
            cooldown_minutes = int(
                self.config.get("support_reversal_cooldown_minutes", 15)
            )
        except (TypeError, ValueError, OverflowError):
            logger.error("[%s] Invalid support-reversal settings", symbol)
            return None
        if (
            source_interval <= 0
            or source_interval >= 300
            or 300 % source_interval != 0
            or not 1 <= cooldown_minutes <= 120
        ):
            logger.error("[%s] Invalid support-reversal settings", symbol)
            return None

        history = aggregate_ohlcv_bars(
            [item.to_dict() for item in underlying_bars],
            source_interval_seconds=source_interval,
            target_interval_seconds=300,
        )
        candidate = detect_support_resistance_reversal(history)
        if candidate is None:
            return None
        preferred = self._preferred_option_symbol(underlying, candidate.signal)
        if symbol != preferred:
            return None

        timestamp = candidate.bar_time or history[-1]["time"]
        last_candidates = getattr(self, "_support_reversal_last_candidate", {})
        previous = last_candidates.get(underlying)
        if previous is not None:
            previous_time, previous_signal, previous_level = previous
            elapsed = (timestamp - previous_time).total_seconds()
            same_setup = (
                previous_time.date() == timestamp.date()
                and previous_signal == candidate.signal
                and abs(previous_level - candidate.level) / candidate.level <= 0.002
            )
            if same_setup and 0 <= elapsed < cooldown_minutes * 60:
                return None
        return candidate

    def _mark_support_reversal_attempt(
        self, symbol: str, candidate: SupportResistanceReversal
    ) -> None:
        underlying = symbol.rsplit("_", 1)[0].upper()
        last_candidates = getattr(self, "_support_reversal_last_candidate", {})
        last_candidates[underlying] = (
            candidate.bar_time or datetime.now(IST),
            candidate.signal,
            candidate.level,
        )
        self._support_reversal_last_candidate = last_candidates

    def _option_trade_risk_limit(self, symbol: str, premium: float) -> float:
        specs = self.intraday_manager.contract_specs.get(symbol, {})
        lot_size = int(specs.get("lot_size", 1))
        if lot_size <= 0:
            raise ValueError(f"Option contract {symbol} has an invalid lot size")
        multiplier = float(
            specs.get("multiplier", self.intraday_manager.MULTIPLIERS.get(symbol, 1))
        )
        if not math.isfinite(multiplier) or multiplier <= 0:
            raise ValueError(f"Option contract {symbol} has an invalid multiplier")
        max_risk_per_lot_pct = float(
            self.config.get("option_max_risk_per_lot_pct", 10.0)
        )
        if (
            not math.isfinite(max_risk_per_lot_pct)
            or not 0 < max_risk_per_lot_pct <= MAX_TRADE_RISK_PCT
        ):
            raise ValueError(
                "option_max_risk_per_lot_pct must be greater than 0 and "
                f"at most {MAX_TRADE_RISK_PCT:g}"
            )
        return (
            max(premium, 0.01)
            * lot_size
            * multiplier
            * max_risk_per_lot_pct
            / 100.0
        )

    def _entry_risk_limit(self, symbol: str, premium: float) -> float:
        risk_limit = float(self.intraday_manager.max_risk_per_trade)
        if self._options_enabled() and "_" in symbol:
            risk_limit = min(risk_limit, self._option_trade_risk_limit(symbol, premium))
        trade_risk_cap = self._entry_risk_cap()
        if trade_risk_cap is not None:
            risk_limit = min(risk_limit, trade_risk_cap)
        return risk_limit

    def _option_quantity_within_lot_bounds(self, symbol: str, quantity: int) -> bool:
        lot_size = int(self.intraday_manager.contract_specs.get(symbol, {}).get("lot_size", 1))
        minimum_lots = int(self.config.get("option_min_lots", 1))
        maximum_lots = int(self.config.get("option_max_lots", 3))
        return (
            lot_size > 0
            and quantity > 0
            and quantity % lot_size == 0
            and minimum_lots <= quantity // lot_size <= maximum_lots
        )

    @staticmethod
    def _journal_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Ignoring invalid journal timestamp %r", value)
            return None
        return timestamp.replace(tzinfo=IST) if timestamp.tzinfo is None else timestamp.astimezone(IST)

    @staticmethod
    def _journal_optional_bool(value) -> Optional[bool]:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes"}
        return bool(value)

    def __init__(self, config_path: str = "kite_config.json") -> None:
        self.config_path = Path(config_path)
        self.config = load_strategy_config(self.config_path)
        self.config["kite_api_key"] = os.getenv("KITE_API_KEY")
        self.config["kite_access_token"] = os.getenv("KITE_ACCESS_TOKEN")
        self.config["telegram_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
        self.config["telegram_chat_id"] = os.getenv("TELEGRAM_CHAT_ID")
        self.entry_mode = str(self.config.get("entry_mode", "immediate")).strip().lower()
        if self.entry_mode not in {"immediate", "confirmed"}:
            raise ValueError("entry_mode must be immediate or confirmed")
        self.config_hash = strategy_config_hash(self.config)
        self.git_identity = log_startup_identity(self.config_hash)
        if not self.config["kite_api_key"] or not self.config["kite_access_token"]:
            raise RuntimeError(
                "KITE_API_KEY and KITE_ACCESS_TOKEN must be set as environment variables."
            )
        self.mode = resolve_execution_mode(self.config, os.getenv("MODE"))
        if self.entry_mode == "confirmed" and self.mode != "PAPER":
            raise ValueError("entry_mode=confirmed is available only in PAPER mode")
        self.config.pop("paper_trading_enabled", None)
        self.config.pop("live_orders_enabled", None)
        self.paper_trading_enabled = self.mode == "PAPER"
        self.live_orders_enabled = self.mode == "LIVE"
        self.paper_trading_dir = self.config.get(
            "paper_trading_dir", "paper_trading_data"
        )
        self.option_candle_recorder = OptionCandleRecorder(
            Path(self.paper_trading_dir) / "option_candles",
            config_hash=self.config_hash,
        )

        daily_max_loss_pct = self.config.get("daily_max_loss_pct", 2.0)
        options_mode = self.config.get("trading_mode") in {
            "intraday_options",
            "intraday_both",
        }
        if (
            self.entry_mode == "confirmed"
            and options_mode
            and int(self.config.get("bar_interval_seconds", 60)) != 60
        ):
            raise ValueError("entry_mode=confirmed requires 1-minute bars")
        if self.entry_mode == "confirmed" and not options_mode:
            raise ValueError(
                "entry_mode=confirmed requires intraday_options or intraday_both"
            )
        if options_mode:
            option_risk_pct = float(
                self.config.get("option_max_risk_per_lot_pct", MAX_TRADE_RISK_PCT)
            )
            option_stop_pct = float(self.config.get("option_premium_stop_pct", 0.10))
            if (
                not math.isfinite(option_risk_pct)
                or not 0 < option_risk_pct <= MAX_TRADE_RISK_PCT
            ):
                raise ValueError(
                    "option_max_risk_per_lot_pct must be greater than 0 and "
                    f"at most {MAX_TRADE_RISK_PCT:g}"
                )
            if (
                not math.isfinite(option_stop_pct)
                or not 0 < option_stop_pct <= MAX_TRADE_RISK_PCT / 100.0
            ):
                raise ValueError(
                    "option_premium_stop_pct must be greater than 0 and "
                    f"at most {MAX_TRADE_RISK_PCT / 100.0:g}"
                )
        max_risk_per_trade = self.config.get("max_risk_per_trade")

        # Initialize intraday manager; option entries apply their premium-based cap below.
        self.intraday_manager = IntradayManager(
            account_size=self.config.get("account_size", 100000),
            risk_per_trade_pct=self.config.get("risk_per_trade_pct", 1.0),
            trailing_enabled=self.config.get("trailing_enabled", True),
            trailing_activation_ratio=self.config.get("trailing_activation_ratio", 0.5),
            trailing_distance_ratio=self.config.get("trailing_distance_ratio", 0.25),
            daily_max_loss=self.config.get("daily_max_loss"),
            daily_max_loss_pct=daily_max_loss_pct,
            max_risk_per_trade=max_risk_per_trade,
        )

        self.bar_builder = BarBuilder(
            interval_seconds=self.config.get("bar_interval_seconds", 60),
            on_bar_callback=self.on_bar_complete,
        )
        self.kite_stream = KiteMarketStream(
            KiteConfig(
                api_key=self.config["kite_api_key"],
                access_token=self.config["kite_access_token"],
                trading_mode=self.config.get("trading_mode", "intraday_futures"),
                instrument_tokens=self.config["instrument_tokens"],
                futures_underlyings=self.config.get("futures_underlyings", []),
                auto_discover_futures=self.config.get("auto_discover_futures", False),
                max_futures=self.config.get("max_futures", 20),
                min_futures_volume=self.config.get("min_futures_volume", 0),
                options_underlyings=self.config.get("options_underlyings", []),
                option_expiry_days=self.config.get("option_expiry_days", 14),
                option_expiry_mode=self.config.get("option_expiry_mode", "nearest"),
                avoid_option_expiry_day=self.config.get(
                    "avoid_option_expiry_day", True
                ),
                option_strike_step=self.config.get("option_strike_step", {}),
                min_options_volume=self.config.get("min_options_volume", 0),
            ),
            on_tick_callback=self._on_tick,
            on_connection_change=self._on_connection_change,
        )
        self.config["instrument_tokens"] = self.kite_stream.refresh_instrument_tokens()
        if (
            self.config.get("ema_reentry_enabled", True)
            and options_mode
            and int(self.config.get("bar_interval_seconds", 60)) != 60
        ):
            raise ValueError(
                "ema_reentry_enabled requires 1-minute underlying bars"
            )
        if self.live_orders_enabled and not self.config.get("live_orders_confirmed", False):
            raise RuntimeError(
                "LIVE mode requires live_orders_confirmed=true in kite_config.json"
            )
        self.intraday_manager.set_contract_specs(self.kite_stream.contract_specs)
        self._warm_up_bars()
        self.telegram_notifier = TelegramNotifier(
            token=self.config.get("telegram_token"),
            chat_id=self.config.get("telegram_chat_id"),
        )
        self.trade_journal = TradeJournal(
            "trades.jsonl",
            self.paper_trading_dir,
            config_hash=self.config_hash,
            git_sha=self.git_identity.sha,
            git_dirty=self.git_identity.dirty,
        )
        self.paper_shadow_exit_journal = (
            PaperShadowExitJournal(
                str(Path(self.paper_trading_dir) / "shadow_runner_1r.jsonl"),
                config_hash=self.config_hash,
                git_sha=self.git_identity.sha,
                git_dirty=self.git_identity.dirty,
            )
            if self.paper_trading_enabled and not self.live_orders_enabled
            else None
        )
        self.paper_shadow_positions = {
            trade_id: record
            for trade_id, record in (
                self.paper_shadow_exit_journal.latest.items()
                if self.paper_shadow_exit_journal
                else []
            )
            if record.get("status") == "open"
        }
        session_trades = self.trade_journal.read_trades()
        self.intraday_manager.restore_session_trades(session_trades)
        self._ema_reentry_states: Dict[str, dict] = {}
        self._restore_ema_reentry_states(session_trades)
        if self.paper_trading_enabled:
            self._restore_paper_positions(session_trades)
        self.decision_journal = DecisionJournal(
            self.config.get("decision_log_path", "decision_log.jsonl"),
            self.paper_trading_dir,
            config_hash=self.config_hash,
            git_sha=self.git_identity.sha,
            git_dirty=self.git_identity.dirty,
        )
        self._pending_entries: Dict[tuple[str, str], dict] = {}
        self._expire_unfinished_confirmed_entries()
        for symbol, state in self._ema_reentry_states.items():
            if state.get("status") == "expired":
                self._log_ema_reentry_event(
                    symbol,
                    state,
                    "ENTRY_CUTOFF",
                    current_time=datetime.now(IST),
                    outcome="entry_cutoff",
                )
        self.weekly_report_dir = Path(
            self.config.get("weekly_report_dir", ".")
        )
        self.last_weekly_report_date = None
        self.last_daily_summary_date = None
        self._entries_paused = False
        self._risk_state_reconciled = not self.live_orders_enabled
        self._daily_shutdown_date = None
        self._daily_shutdown_cancel_complete = False
        if self.live_orders_enabled:
            self._reconcile_live_state()
        else:
            self._activate_daily_loss_shutdown()
        self.symbol_map = {v: k for k, v in self.config["instrument_tokens"].items()}
        self.latest_prices: Dict[str, float] = {}
        self.option_quote_cache: Dict[str, dict] = {}
        self.premarkarket_candidates: list[tuple[str, str, int, str]] = []
        self.benchmark_symbol = self.config.get("benchmark_symbol", "NIFTY")
        self.use_market_context = self.config.get("use_market_context", True)
        self.accuracy_filters = AccuracyFilters(
            min_entry_score=int(self.config.get("min_entry_score", 70)),
            min_volatility_pct=float(self.config.get("min_volatility_pct", 0.05)),
            max_volatility_pct=float(self.config.get("max_volatility_pct", 5.0)),
        )
        self.stop_reentry_min_score = int(
            self.config.get("stop_reentry_min_score", 75)
        )
        if not 0 <= self.stop_reentry_min_score <= 85:
            raise ValueError("stop_reentry_min_score must be between 0 and 85")
        self.stop_reentry_cooldown_minutes = int(
            self.config.get("stop_reentry_cooldown_minutes", 15)
        )
        if not 1 <= self.stop_reentry_cooldown_minutes <= 240:
            raise ValueError(
                "stop_reentry_cooldown_minutes must be between 1 and 240"
            )
        self.option_min_candle_body_ratio = float(
            self.config.get(
                "option_min_candle_body_ratio",
                OPTION_MIN_CANDLE_BODY_RATIO,
            )
        )
        if (
            not math.isfinite(self.option_min_candle_body_ratio)
            or not 0 < self.option_min_candle_body_ratio <= 1
        ):
            raise ValueError(
                "option_min_candle_body_ratio must be greater than 0 and at most 1"
            )
        self.news_monitor = NewsMonitor(
            feeds=self.config.get("news_feeds"),
            refresh_seconds=self.config.get("news_refresh_seconds", 900),
        ) if self.config.get("news_enabled", True) else None

    def _entry_score_floor(self) -> int:
        """Return the shared strategy entry-score floor."""
        return getattr(
            getattr(self, "accuracy_filters", None),
            "min_score_floor",
            int(self.config.get("min_entry_score", 70)),
        )

    def _can_open_trade_for_signal(
        self,
        symbol: str,
        direction: str,
        score: int,
        *,
        ema_reentry_confirmed: bool = False,
    ) -> tuple[bool, str]:
        if ema_reentry_confirmed and self._ema_reentry_enabled():
            return self.intraday_manager.can_open_trade(
                symbol,
                direction,
                allow_stop_reentry=True,
                stop_reentry_cooldown_seconds=0,
                signal_score=score,
                minimum_stop_reentry_score=0,
            )
        allow_stop_reentry = (
            self.config.get("stop_reentry_enabled", False)
            and self._options_enabled()
            and symbol.endswith(("_CE", "_PE"))
        )
        if not allow_stop_reentry:
            return self.intraday_manager.can_open_trade(symbol, direction)
        return self.intraday_manager.can_open_trade(
            symbol,
            direction,
            allow_stop_reentry=True,
            stop_reentry_cooldown_seconds=self.stop_reentry_cooldown_minutes * 60,
            signal_score=score,
            minimum_stop_reentry_score=self.stop_reentry_min_score,
        )

    def _ema_reentry_enabled(self) -> bool:
        config = getattr(self, "config", {})
        return (
            bool(config.get("ema_reentry_enabled", True))
            and config.get("trading_mode") in {"intraday_options", "intraday_both"}
        )

    def _restore_ema_reentry_states(self, trades: list[dict]) -> None:
        if not self._ema_reentry_enabled():
            return
        child_original_ids = {
            str(trade.get("original_trade_id"))
            for trade in trades
            if trade.get("is_ema_reentry") and trade.get("original_trade_id")
        }
        now = datetime.now(IST)
        for trade in trades:
            if (
                trade.get("status") != "closed"
                or trade.get("reason") != "STOP_LOSS"
                or not trade.get("ema_reentry_eligible")
                or str(trade.get("trade_id")) in child_original_ids
            ):
                continue
            symbol = str(trade.get("ticker", ""))
            if not symbol.endswith(("_CE", "_PE")):
                continue
            stop_time = self._journal_datetime(trade.get("ema_reentry_stop_time"))
            original_trade_id = str(trade.get("trade_id", ""))
            if stop_time is None or not original_trade_id:
                continue
            if stop_time.date() != now.date():
                continue
            state = {
                "original_trade_id": original_trade_id,
                "stop_time": stop_time,
                "stop_out_low": self._positive_quote_value(
                    trade.get("ema_reentry_stop_out_low")
                ),
                "status": "observing",
            }
            if now >= self._ema_reentry_cutoff(stop_time.date()):
                state["status"] = "expired"
                state["outcome"] = "ENTRY_CUTOFF"
                self.trade_journal.annotate_trade(
                    symbol,
                    {"ema_reentry_outcome": "ENTRY_CUTOFF"},
                    action="BUY",
                )
            self._ema_reentry_states[symbol] = state

    def _ema_reentry_candidate(
        self, symbol: str, underlying_history: list[dict]
    ) -> Optional[dict]:
        active_positions = getattr(
            getattr(self, "intraday_manager", None), "active_positions", {}
        )
        if (
            not self._ema_reentry_enabled()
            or not symbol.endswith(("_CE", "_PE"))
            or (
                isinstance(active_positions, dict)
                and symbol in active_positions
            )
        ):
            return None
        state = getattr(self, "_ema_reentry_states", {}).get(symbol)
        if not state or state.get("status") != "observing":
            return None

        current_time = self._journal_datetime(
            str(underlying_history[-1].get("time", ""))
            if underlying_history
            else None
        )
        stop_time = state["stop_time"]
        if current_time is None:
            return None
        if current_time.date() != stop_time.date():
            return None
        current_bar_end = current_time + timedelta(minutes=1)
        cutoff = self._ema_reentry_cutoff(stop_time.date())
        if current_bar_end >= cutoff:
            state["status"] = "expired"
            state["outcome"] = "ENTRY_CUTOFF"
            self.trade_journal.annotate_trade(
                symbol,
                {"ema_reentry_outcome": "ENTRY_CUTOFF"},
                action="BUY",
            )
            self._log_ema_reentry_event(
                symbol,
                state,
                "ENTRY_CUTOFF",
                current_time=current_bar_end,
            )
            return None

        if self._ema_reentry_premium_made_new_low(symbol, state):
            return None

        signal = find_ema_reentry_signal(
            underlying_history,
            "CE" if symbol.endswith("_CE") else "PE",
            stop_time,
            valid_until=cutoff,
        )
        if signal is None:
            return None
        state["status"] = "triggered"
        state["signal_time"] = signal.signal_time
        state["reentry_reason"] = signal.reason
        return {
            "original_trade_id": state["original_trade_id"],
            "stop_time": signal.stop_time.isoformat(),
            "signal_time": signal.signal_time.isoformat(),
            "crossover_time": signal.crossover_time.isoformat(),
            "reentry_reason": signal.reason,
            "crossover_level": signal.crossover_level,
            "confirmation_close": signal.confirmation_close,
            "vwap": signal.vwap,
            "signal": signal.signal,
            "route": "ema_reentry",
        }

    def _ema_reentry_premium_made_new_low(self, symbol: str, state: dict) -> bool:
        stop_out_low = self._positive_quote_value(state.get("stop_out_low"))
        if stop_out_low is None:
            return False
        quote = getattr(self, "option_quote_cache", {}).get(symbol, {})
        metrics = self._option_quote_metrics(quote)
        premium = metrics["ltp"]
        if not metrics["valid"] or premium is None or premium >= stop_out_low:
            return False

        current_time = metrics["timestamp"] or datetime.now(IST)
        state["status"] = "cancelled"
        state["outcome"] = "PREMIUM_NEW_LOW"
        state["new_premium_low"] = premium
        self.trade_journal.annotate_trade(
            symbol,
            {
                "ema_reentry_outcome": "PREMIUM_NEW_LOW",
                "ema_reentry_new_low": premium,
            },
            action="BUY",
        )
        self._log_ema_reentry_event(
            symbol,
            state,
            "CANCELLED_NEW_LOW",
            current_time=current_time,
            signal={"premium_new_low": premium},
            outcome="premium_new_low",
        )
        return True

    def _log_ema_reentry_event(
        self,
        symbol: str,
        state: dict,
        event: str,
        *,
        current_time: datetime,
        signal: Optional[dict] = None,
        outcome: Optional[str] = None,
    ) -> None:
        journal = getattr(self, "decision_journal", None)
        if journal is None:
            return
        journal.log_decision(
            {
                "timestamp": current_time.isoformat(),
                "event": "ema_stop_reentry",
                "ema_reentry_event": event,
                "ticker": symbol,
                "contract_id": self._contract_id(symbol),
                "signal": (signal or {}).get("signal", "HOLD"),
                "outcome": outcome or event.lower(),
                "strategy_variant": "paper_ema_stop_reentry",
                "route": "ema_reentry",
                "original_trade_id": state.get("original_trade_id"),
                "stop_time": str(state.get("stop_time")),
                "stop_out_low": state.get("stop_out_low"),
                "reentry_signal_time": (signal or {}).get("signal_time"),
                "reentry_reason": (signal or {}).get("reentry_reason"),
                "reentry_vwap": (signal or {}).get("vwap"),
                "reentry_entry_price": (signal or {}).get("entry_price"),
                "reentry_exit_price": (signal or {}).get("exit_price"),
                "reentry_pnl": (signal or {}).get("pnl"),
                "reentry_outcome": (signal or {}).get("reentry_outcome"),
                "reasons": [(signal or {}).get("reentry_reason", event)],
            }
        )

    def _complete_ema_reentry_attempt(
        self, symbol: str, signal: dict, outcome: str
    ) -> None:
        state = getattr(self, "_ema_reentry_states", {}).get(symbol, {})
        opened = outcome == "trade_opened"
        state["status"] = "opened" if opened else "rejected"
        state["outcome"] = outcome
        self.trade_journal.annotate_trade(
            symbol,
            {
                "ema_reentry_outcome": (
                    "REENTRY_OPENED" if opened else "REENTRY_REJECTED"
                ),
                "ema_reentry_signal_time": signal["signal_time"],
                "ema_reentry_reason": signal["reentry_reason"],
                "route": "ema_reentry",
            },
            action="BUY",
        )
        self._log_ema_reentry_event(
            symbol,
            state,
            "ENTRY_OPENED" if opened else "ENTRY_REJECTED",
            current_time=self._journal_datetime(signal["signal_time"])
            or datetime.now(IST),
            signal=signal,
            outcome=outcome,
        )

    def _on_connection_change(self, connected: bool, reason: str) -> None:
        self._entries_paused = not connected
        if not connected:
            logger.error("Kite connection lost; pausing new entries: %s", reason)
            notifier = getattr(self, "telegram_notifier", None)
            if notifier:
                message = (
                    "URGENT: Kite connection lost; new entries paused."
                )
                positions = getattr(
                    getattr(self, "intraday_manager", None),
                    "active_positions",
                    {},
                )
                quote_managed = [
                    symbol
                    for symbol, position in positions.items()
                    if self._quote_validated_long_option(symbol, position)
                    and not position.get("protection_order_id")
                ]
                if quote_managed:
                    message += (
                        "\nOpen option positions have no broker-side stop and "
                        "require quote monitoring/manual protection: "
                        + ", ".join(sorted(quote_managed))
                    )
                notifier.send_message(f"{message}\n{reason}")
            return

        logger.info("Kite connection restored; reconciling broker state")
        try:
            if self.live_orders_enabled:
                self._reconcile_live_state()
            self._entries_paused = False
            notifier = getattr(self, "telegram_notifier", None)
            if notifier:
                notifier.send_message("Kite connection restored; broker state reconciled.")
        except Exception as exc:
            self._entries_paused = True
            logger.exception("Broker reconciliation failed after reconnect")
            notifier = getattr(self, "telegram_notifier", None)
            if notifier:
                notifier.send_message(f"URGENT: broker reconciliation failed; trading paused.\n{exc}")

    def _restore_paper_positions(self, trades: list[dict]) -> None:
        today = datetime.now(IST).date()
        for trade in trades:
            if trade.get("status") != "open":
                continue
            symbol = trade.get("ticker") or trade.get("symbol")
            timestamp = self._journal_datetime(trade.get("timestamp"))
            if not symbol or timestamp is None:
                raise RuntimeError(
                    "Cannot safely restore an open paper position outside today's "
                    f"session: {symbol or 'unknown'}"
                )
            if timestamp.date() != today:
                self._close_stale_paper_position(trade, str(symbol), timestamp)
                continue
            try:
                direction = str(trade.get("action", "")).upper()
                quantity = int(trade.get("quantity", 0))
                entry_price = float(trade["entry"])
                stop_loss = float(trade["stop_loss"])
                take_profit = float(trade["take_profit"])
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise RuntimeError(
                    f"Open paper position {symbol} has invalid journal risk fields"
                ) from exc
            if (
                direction not in {"BUY", "SELL"}
                or quantity <= 0
                or entry_price <= 0
                or stop_loss <= 0
                or take_profit <= 0
                or not all(
                    math.isfinite(value)
                    for value in (entry_price, stop_loss, take_profit)
                )
            ):
                raise RuntimeError(
                    f"Open paper position {symbol} has invalid journal risk fields"
                )
            if str(symbol) in self.intraday_manager.active_positions:
                raise RuntimeError(
                    f"Multiple open paper journal entries found for {symbol}"
                )

            self.intraday_manager.register_position(
                str(symbol),
                direction,
                quantity,
                entry_price,
                stop_loss,
                take_profit,
                signal_score=(
                    int(trade["score"]) if trade.get("score") is not None else None
                ),
                staged_targets_enabled=(
                    trade.get("exit_strategy") == "tiered_milestone"
                ),
                target_increment_pct=float(
                    trade.get(
                        "option_milestone_pct",
                        self.config.get("option_milestone_pct", 0.10),
                    )
                ),
                minimum_signal_score=(
                    int(trade["minimum_signal_score"])
                    if trade.get("minimum_signal_score") is not None
                    else None
                ),
                strong_signal_score=int(self.config.get("strong_signal_score", 82)),
                entry_time=self._journal_datetime(trade.get("entry_time")) or timestamp,
                milestone_started_at=self._journal_datetime(
                    trade.get("milestone_started_at")
                ),
                target_stage=int(trade.get("target_stage", 0) or 0),
                trailing_stop=(
                    float(trade["trailing_stop"])
                    if trade.get("trailing_stop") is not None
                    else None
                ),
                current_signal_score=(
                    int(trade["current_signal_score"])
                    if trade.get("current_signal_score") is not None
                    else None
                ),
                decision_window_minutes=(
                    int(trade["decision_window_minutes"])
                    if trade.get("decision_window_minutes") is not None
                    else None
                ),
                trailing_enabled=self._journal_optional_bool(
                    trade.get("trailing_enabled")
                ),
                exit_strategy=trade.get("exit_strategy"),
                runner_activation_r=(
                    float(trade["runner_activation_r"])
                    if trade.get("runner_activation_r") is not None
                    else None
                ),
                runner_gap_r=(
                    float(trade["runner_gap_r"])
                    if trade.get("runner_gap_r") is not None
                    else None
                ),
                adaptive_breakeven_r=(
                    float(trade["adaptive_breakeven_r"])
                    if trade.get("adaptive_breakeven_r") is not None
                    else None
                ),
                adaptive_trail_activation_r=(
                    float(trade["adaptive_trail_activation_r"])
                    if trade.get("adaptive_trail_activation_r") is not None
                    else None
                ),
                adaptive_trail_gap_r=(
                    float(trade["adaptive_trail_gap_r"])
                    if trade.get("adaptive_trail_gap_r") is not None
                    else None
                ),
                adaptive_runner_activation_r=(
                    float(trade["adaptive_runner_activation_r"])
                    if trade.get("adaptive_runner_activation_r") is not None
                    else None
                ),
                adaptive_runner_gap_r=(
                    float(trade["adaptive_runner_gap_r"])
                    if trade.get("adaptive_runner_gap_r") is not None
                    else None
                ),
                adaptive_exit_mode=trade.get("adaptive_exit_mode"),
                max_favorable_r=float(trade.get("max_favorable_r", 0.0) or 0.0),
                highest_price=(
                    float(trade["highest_price"])
                    if trade.get("highest_price") is not None
                    else None
                ),
                lowest_price=(
                    float(trade["lowest_price"])
                    if trade.get("lowest_price") is not None
                    else None
                ),
                trailing_active=bool(
                    self._journal_optional_bool(trade.get("trailing_active"))
                ),
            )

        if self.intraday_manager.daily_risk_exceeded():
            raise RuntimeError(
                "Restored paper positions and realized losses exceed the aggregate "
                f"daily risk cap of {self.intraday_manager.daily_max_loss:.2f}"
            )

    def _close_stale_paper_position(
        self, trade: dict, symbol: str, entry_time: datetime
    ) -> None:
        try:
            entry_price = float(trade["entry"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError(
                f"Cannot auto-close stale paper position {symbol}: "
                "journal has no valid entry price for recovery"
            ) from exc
        if (
            not math.isfinite(entry_price)
            or entry_price <= 0
        ):
            raise RuntimeError(
                f"Cannot auto-close stale paper position {symbol}: "
                "journal has no valid entry price for recovery"
            )

        direction = str(trade.get("action", "")).upper()
        if direction not in {"BUY", "SELL"}:
            raise RuntimeError(
                f"Cannot auto-close stale paper position {symbol}: "
                "journal has an invalid action"
            )
        now = datetime.now(IST)
        mark_time = self._journal_datetime(trade.get("updated_at"))
        try:
            last_price = float(trade["last_price"])
        except (KeyError, TypeError, ValueError, OverflowError):
            last_price = None
        has_valid_mark = (
            last_price is not None
            and math.isfinite(last_price)
            and last_price > 0
            and mark_time is not None
            and entry_time <= mark_time <= now
        )
        if has_valid_mark:
            exit_price = last_price
            closed_at = mark_time.isoformat(timespec="seconds")
            reason = "STALE_PAPER_POSITION_RECOVERY_AT_LAST_MARK"
            logger.warning(
                "[%s] Auto-closing stale paper position at last persisted mark "
                "%.4f from %s",
                symbol,
                exit_price,
                closed_at,
            )
        else:
            exit_price = entry_price
            closed_at = now.isoformat(timespec="seconds")
            reason = "STALE_PAPER_POSITION_RECOVERY_AT_ENTRY_ESTIMATE"
            logger.warning(
                "[%s] No valid persisted price mark; estimating stale paper exit "
                "at entry price %.4f (zero estimated P&L)",
                symbol,
                exit_price,
            )

        trade_id = str(trade.get("trade_id")) if trade.get("trade_id") else None
        if not trade_id:
            matching_open_trades = [
                item
                for item in self.trade_journal.read_trades()
                if item.get("status") == "open"
                and (item.get("ticker") or item.get("symbol")) == symbol
                and str(item.get("action", "")).upper() == direction
            ]
            if len(matching_open_trades) != 1:
                raise RuntimeError(
                    f"Cannot safely identify stale paper journal entry for {symbol}"
                )

        self.trade_journal.close_trade(
            symbol,
            exit_price,
            direction,
            reason,
            trade_id=trade_id,
            closed_at=closed_at,
        )
        journal_after_close = self.trade_journal.read_trades()
        if trade_id:
            closed = any(
                str(item.get("trade_id")) == trade_id
                and item.get("status") == "closed"
                and item.get("reason") == reason
                and item.get("closed_at") == closed_at
                and item.get("exit_price") == exit_price
                for item in journal_after_close
            )
        else:
            closed = any(
                (item.get("ticker") or item.get("symbol")) == symbol
                and str(item.get("action", "")).upper() == direction
                and item.get("timestamp") == trade.get("timestamp")
                and item.get("status") == "closed"
                and item.get("reason") == reason
                and item.get("closed_at") == closed_at
                and item.get("exit_price") == exit_price
                for item in journal_after_close
            )
        if not closed:
            raise RuntimeError(
                f"Failed to persist stale paper position recovery for {symbol}"
            )

    def _persist_risk_state(self, positions: list[dict], orders: list[dict]) -> None:
        target_date = datetime.now(IST).date().isoformat()
        realized_pnl = sum(
            float(row.get("realised", row.get("realized", 0.0)) or 0.0)
            for row in positions
        )
        unrealized_pnl = sum(
            float(
                row.get(
                    "unrealised",
                    row.get("unrealized", row.get("pnl", 0.0)),
                )
                or 0.0
            )
            for row in positions
        )
        state_dir = Path(self.config.get("risk_state_dir", "."))
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / f"risk_state_{target_date}.json"
        path.write_text(
            json.dumps(
                {
                    "trading_date": target_date,
                    "broker_positions": positions,
                    "completed_orders": orders,
                    "realized_pnl": realized_pnl,
                    "unrealized_pnl": unrealized_pnl,
                    "daily_pnl": realized_pnl,
                    "active_positions": self.intraday_manager.get_all_open_positions(),
                    "updated_at": datetime.now(IST).isoformat(timespec="seconds"),
                },
                default=str,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _reconcile_live_state(self) -> None:
        positions = self.kite_stream.get_positions()
        orders = self.kite_stream.get_completed_orders()
        broker_symbol_map = {
            trading_symbol: symbol
            for symbol, trading_symbol in self.kite_stream.contract_symbols.items()
        }
        broker_positions = {}
        for row in positions:
            if int(row.get("quantity", 0) or 0) == 0:
                continue
            broker_symbol = row.get("tradingsymbol")
            if not isinstance(broker_symbol, str) or not broker_symbol:
                raise RuntimeError(
                    "Broker returned an open position without a trading symbol"
                )
            symbol = broker_symbol_map.get(broker_symbol, broker_symbol)
            broker_positions[symbol] = row
        open_trades = {
            trade.get("ticker"): trade
            for trade in self.trade_journal.read_trades()
            if trade.get("status") == "open"
        }
        if set(broker_positions) != set(open_trades):
            raise RuntimeError(
                "Broker positions and open trade journal cannot be reconciled: "
                f"broker={sorted(broker_positions)}, journal={sorted(open_trades)}"
            )

        self.intraday_manager.active_positions.clear()
        for symbol, broker_position in broker_positions.items():
            trade = open_trades[symbol]
            quantity = abs(int(broker_position.get("quantity", 0) or 0))
            direction = "BUY" if int(broker_position.get("quantity", 0) or 0) > 0 else "SELL"
            entry_price = float(trade.get("entry", broker_position.get("average_price", 0.0)))
            stop_loss = float(trade.get("stop_loss", entry_price))
            take_profit = float(trade.get("take_profit", entry_price))
            if (
                entry_price <= 0
                or stop_loss <= 0
                or take_profit <= 0
                or not all(
                    math.isfinite(value)
                    for value in (entry_price, stop_loss, take_profit)
                )
            ):
                raise RuntimeError(f"Open trade {symbol} has incomplete risk levels")
            if not trade.get("protection_order_id"):
                raise RuntimeError(f"Open trade {symbol} has no recorded protective stop")
            estimated_risk = self.intraday_manager.estimate_trade_risk(
                symbol, quantity, entry_price, stop_loss
            )
            if estimated_risk > self._entry_risk_limit(symbol, entry_price) + 1e-6:
                raise RuntimeError(
                    f"Open trade {symbol} exceeds the per-trade risk cap: "
                    f"{estimated_risk:.2f} > {self._entry_risk_limit(symbol, entry_price):.2f}"
                )
            entry_score = (
                int(trade["score"]) if trade.get("score") is not None else None
            )
            self.intraday_manager.register_position(
                symbol, direction, quantity, entry_price, stop_loss, take_profit,
                signal_score=entry_score,
                trailing_enabled=self._journal_optional_bool(
                    trade.get("trailing_enabled")
                ),
                exit_strategy=trade.get("exit_strategy"),
            )
            position = self.intraday_manager.active_positions[symbol]
            current_score_value = trade.get("current_signal_score")
            if current_score_value is None:
                current_score_value = entry_score
            decision_window = trade.get("decision_window_minutes")
            if decision_window is None:
                strong_threshold = int(self.config.get("strong_signal_score", 82))
                decision_window = (
                    self.config.get("strong_option_milestone_window_minutes", 10)
                    if entry_score is not None and entry_score >= strong_threshold
                    else self.config.get("option_milestone_window_minutes", 5)
                )
            position.update(
                {
                    "current_signal_score": (
                        int(current_score_value)
                        if current_score_value is not None
                        else None
                    ),
                    "staged_targets_enabled": (
                        trade.get("exit_strategy") == "tiered_milestone"
                    ),
                    "target_increment_pct": float(
                        trade.get(
                            "option_milestone_pct",
                            self.config.get("option_milestone_pct", 0.10),
                        )
                    ),
                    "minimum_signal_score": (
                        int(trade["minimum_signal_score"])
                        if trade.get("minimum_signal_score") is not None
                        else None
                    ),
                    "strong_signal_score": int(
                        self.config.get("strong_signal_score", 82)
                    ),
                    "weak_signal_lockin_pct": float(
                        self.config.get("option_weak_signal_lockin_pct", 0.05)
                    ),
                    "milestone_window_minutes": int(
                        self.config.get("option_milestone_window_minutes", 5)
                    ),
                    "strong_milestone_window_minutes": int(
                        self.config.get("strong_option_milestone_window_minutes", 10)
                    ),
                    "decision_window_minutes": int(decision_window),
                    "weak_signal_adverse_checks": int(
                        trade.get("weak_signal_adverse_checks", 0) or 0
                    ),
                    "target_stage": int(trade.get("target_stage", 0) or 0),
                    "milestone_reached_pct": float(
                        trade.get("milestone_reached_pct", 0.0) or 0.0
                    ),
                    "trailing_stop": (
                        float(trade["trailing_stop"])
                        if trade.get("trailing_stop") is not None
                        else None
                    ),
                }
            )
            journal_entry_time = self._journal_datetime(trade.get("entry_time"))
            if journal_entry_time:
                position["entry_time"] = journal_entry_time
            journal_milestone_time = self._journal_datetime(
                trade.get("milestone_started_at")
            )
            if journal_milestone_time:
                position["milestone_started_at"] = journal_milestone_time
            if trade.get("protection_order_id"):
                self.intraday_manager.active_positions[symbol]["protection_order_id"] = (
                    trade["protection_order_id"]
                )
        self._persist_risk_state(positions, orders)
        realized_pnl = sum(
            float(row.get("realised", row.get("realized", 0.0)) or 0.0)
            for row in positions
        )
        self.intraday_manager.daily_pnl = realized_pnl
        self.intraday_manager.daily_realized_losses = max(
            self.intraday_manager.daily_realized_losses,
            max(-realized_pnl, 0.0),
        )
        self._activate_daily_loss_shutdown()
        if self.intraday_manager.daily_risk_exceeded():
            raise RuntimeError(
                "Broker positions and realized losses exceed the aggregate daily "
                f"risk cap of {self.intraday_manager.daily_max_loss:.2f}"
            )
        self._risk_state_reconciled = True

    def _reconcile_after_order_failure(self, symbol: str) -> None:
        self._entries_paused = True
        try:
            self._reconcile_live_state()
            self._entries_paused = False
        except Exception as exc:
            logger.exception("[%s] Broker state remains uncertain after order failure", symbol)
            self.telegram_notifier.send_message(
                f"URGENT: {symbol} order result is uncertain; trading paused.\n{exc}"
            )

    def _persist_current_live_risk_state(self) -> None:
        if not self.live_orders_enabled:
            return
        try:
            self._persist_risk_state(
                self.kite_stream.get_positions(),
                self.kite_stream.get_completed_orders(),
            )
        except Exception:
            logger.exception("Could not persist current broker risk state")

    def _preferred_option_symbol(self, underlying: str, signal: str) -> Optional[str]:
        """Map a directional signal to the correct option contract for one underlying."""
        if not self._options_enabled():
            return None
        if not underlying:
            return None
        preferred_map = {
            "BUY": "CE",
            "SELL": "PE",
        }
        required_type = preferred_map.get(signal)
        if required_type is None:
            return None
        option_key = f"{underlying.upper()}_{required_type}"
        if option_key in self.config.get("instrument_tokens", {}):
            return option_key
        return None

    def _option_leg_is_active(self, symbol: str, signal: str) -> bool:
        """Only allow the preferred option leg to trade for a given underlying."""
        if not self._options_enabled():
            return True
        if "_" not in symbol:
            return True
        underlying = symbol.rsplit("_", 1)[0].upper()
        preferred = self._preferred_option_symbol(underlying, signal)
        return preferred is not None and symbol == preferred

    def _option_trade_action(self, symbol: str, signal: str) -> str:
        """Buy the trend-aligned option leg and never short an option."""
        if self._options_enabled() and symbol.endswith(("_CE", "_PE")):
            if signal not in {"BUY", "SELL"} or not self._option_leg_is_active(
                symbol, signal
            ):
                return "HOLD"
            return "BUY"
        return signal

    def _option_quality_gate(
        self,
        symbol: str,
        signal: str,
        score: Optional[int] = None,
        minimum_premium_override: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> tuple[bool, str]:
        """Require a fresh option quote and enforce contract-quality limits."""
        if not self._options_enabled():
            return True, "OK"
        now = now or datetime.now(IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        else:
            now = now.astimezone(IST)

        quote_data = getattr(self, "option_quote_cache", {}).get(symbol, {})
        if not quote_data:
            return False, "option quote unavailable"

        quote_timestamp = quote_data.get("timestamp")
        if not isinstance(quote_timestamp, datetime):
            return False, "option quote timestamp unavailable"
        if quote_timestamp.tzinfo is None:
            quote_timestamp = quote_timestamp.replace(tzinfo=IST)
        else:
            quote_timestamp = quote_timestamp.astimezone(IST)
        try:
            max_quote_age = float(self.config.get("option_quote_max_age_seconds", 60))
        except (TypeError, ValueError, OverflowError):
            return False, "invalid option quote age setting"
        if not math.isfinite(max_quote_age) or max_quote_age <= 0:
            return False, "invalid option quote age setting"
        quote_age = (now - quote_timestamp).total_seconds()
        if quote_age < 0 or quote_age > max_quote_age:
            return False, f"option quote stale: {quote_age:.1f}s"

        stream = getattr(self, "kite_stream", None)
        expiry = getattr(stream, "contract_expiries", {}).get(symbol)
        if (
            expiry is not None
            and self.config.get("avoid_option_expiry_day", True)
            and expiry <= now.date()
        ):
            return False, "option expiry-day risk"

        has_oi = quote_data.get("oi") is not None
        has_iv = quote_data.get("iv") is not None
        try:
            premium_value = quote_data.get("last_price", quote_data.get("premium"))
            if premium_value is None:
                return False, "invalid option quote"
            premium = float(premium_value)
            volume = int(quote_data.get("volume", 0) or 0)
            oi = int(quote_data["oi"]) if has_oi else 0
            iv = float(quote_data["iv"]) if has_iv else 0.0
        except (TypeError, ValueError, OverflowError):
            return False, "invalid option quote"
        if (
            not math.isfinite(premium)
            or premium <= 0
            or volume < 0
            or oi < 0
            or (has_iv and (not math.isfinite(iv) or iv < 0))
        ):
            return False, "invalid option quote"

        min_premium = float(self.config.get("option_min_premium", 12.0))
        if minimum_premium_override is not None:
            if (
                not self.config.get("support_reversal_enabled", False)
                or not self._options_enabled()
                or not symbol.endswith(("_CE", "_PE"))
            ):
                return False, "support-reversal premium override unavailable"
            try:
                min_premium = float(minimum_premium_override)
            except (TypeError, ValueError, OverflowError):
                return False, "invalid support-reversal premium floor"
            if not math.isfinite(min_premium) or min_premium <= 0:
                return False, "invalid support-reversal premium floor"
        max_premium = float(self.config.get("option_max_premium", 800.0))
        min_volume = int(self.config.get("option_min_volume", 200))
        min_oi = int(self.config.get("option_min_oi", 400))
        iv_min = float(self.config.get("option_iv_min", 0.08))
        iv_max = float(self.config.get("option_iv_max", 1.20))

        strong_signal = score is not None and score >= int(self.config.get("strong_signal_score", 82))
        premium_floor = min_premium * (0.55 if strong_signal else 0.65)
        volume_floor = max(int(min_volume * (0.6 if strong_signal else 0.7)), 150)
        oi_floor = max(int(min_oi * (0.6 if strong_signal else 0.7)), 300)

        if premium < min_premium:
            if (
                premium >= premium_floor
                and volume >= volume_floor
                and (not has_oi or oi >= oi_floor)
            ):
                pass
            else:
                return False, f"premium too low: {premium} < {min_premium}"
        if premium > max_premium:
            return False, f"premium too high: {premium} > {max_premium}"
        if volume < min_volume:
            if (
                volume >= volume_floor
                and premium >= premium_floor
                and (not has_oi or oi >= oi_floor)
            ):
                pass
            else:
                return False, f"volume too low: {volume} < {min_volume}"
        if has_oi and oi < min_oi:
            if oi >= oi_floor and premium >= premium_floor and volume >= volume_floor:
                pass
            else:
                return False, f"open interest too low: {oi} < {min_oi}"
        if has_iv:
            iv_current = iv
            if not iv_min <= iv_current <= iv_max:
                if strong_signal and iv_min * 0.7 <= iv_current <= iv_max * 1.25:
                    pass
                else:
                    iv = iv_current
                    return False, f"IV out of range: {iv} not in [{iv_min}, {iv_max}]"
        return True, "OK"

    def _contract_id(self, symbol: str) -> str:
        stream = getattr(self, "kite_stream", None)
        if stream is None:
            return ""
        trading_symbol = getattr(stream, "contract_symbols", {}).get(symbol)
        exchange = getattr(stream, "contract_exchanges", {}).get(symbol)
        if not trading_symbol or not exchange:
            return ""
        return f"{exchange}:{trading_symbol}"

    def _capture_eligible_option_candles(
        self,
        symbol: str,
        bars: list[Bar],
        *,
        signal_time: Optional[datetime] = None,
        contract_id: Optional[str] = None,
    ) -> None:
        if not self._options_enabled() or not symbol.endswith(("_CE", "_PE")):
            return
        if int(self.config.get("bar_interval_seconds", 60)) != 60:
            logger.error(
                "[%s] Cannot archive option candles: bar_interval_seconds must be 60",
                symbol,
            )
            return
        recorder = getattr(self, "option_candle_recorder", None)
        if recorder is None:
            logger.error("[%s] Option candle recorder is unavailable", symbol)
            return
        try:
            recorder.capture_eligible(
                symbol,
                bars,
                signal_time or datetime.now(IST),
                contract_id if contract_id is not None else self._contract_id(symbol),
            )
        except OSError:
            logger.exception(
                "[%s] Could not persist eligible option candles", symbol
            )

    def _record_active_option_candle(self, symbol: str, bar: Bar) -> None:
        recorder = getattr(self, "option_candle_recorder", None)
        if (
            recorder is None
            or not self._options_enabled()
            or not symbol.endswith(("_CE", "_PE"))
            or int(self.config.get("bar_interval_seconds", 60)) != 60
        ):
            return
        try:
            recorder.record_active(symbol, bar, self._contract_id(symbol))
        except OSError:
            logger.exception("[%s] Could not persist option candle", symbol)

    def _log_entry_confirmation_event(
        self, pending: dict, event: str, timestamp: datetime, **fields
    ) -> None:
        journal = getattr(self, "decision_journal", None)
        if journal is None:
            logger.error(
                "[%s] Cannot journal confirmed-entry event %s",
                pending.get("symbol"),
                event,
            )
            return
        payload = {
            "timestamp": timestamp.isoformat(),
            "event": "entry_confirmation",
            "confirmation_event": event,
            "signal_id": pending["signal_id"],
            "ticker": pending["symbol"],
            "contract_id": pending["contract_id"],
            "signal": pending["signal"],
            "score": pending["score"],
            "route": pending["route"],
            "entry_mode": "confirmed",
            "signal_time": pending["signal_time"].isoformat(),
            "signal_close": pending["signal_close"],
            "signal_bar": pending["signal_bar"],
            "signal_premium": pending["signal_premium"],
            "signal_bid": pending["signal_bid"],
            "signal_ask": pending["signal_ask"],
            "signal_ltp": pending["signal_ltp"],
            "signal_quote_age_seconds": pending["signal_quote_age_seconds"],
            "reasons": pending["reasons"],
            "support_resistance_level": pending["support_resistance_level"],
            "support_resistance_touches": pending["support_resistance_touches"],
            "ema_fast_value": pending["ema_fast_value"],
            "ema_slow_value": pending["ema_slow_value"],
            **fields,
        }
        journal.log_decision(payload)

    def _expire_unfinished_confirmed_entries(self) -> None:
        """Log in-memory pending signals left unfinished by the prior process."""
        journal = getattr(self, "decision_journal", None)
        path = getattr(journal, "path", None)
        if path is None or not path.exists():
            return

        pending_signals: Dict[str, dict] = {}
        terminal_events = {
            "confirmed_trade",
            "rejected_by_confirmation",
            "filter_failed_after_confirmation",
            "expired_signal",
            "confirmation_error",
        }
        try:
            with path.open("r", encoding="utf-8") as source:
                for line_number, line in enumerate(source, 1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Skipping invalid decision journal line %s during "
                            "pending-entry recovery",
                            line_number,
                        )
                        continue
                    signal_id = record.get("signal_id")
                    event = record.get("confirmation_event")
                    if not signal_id or not event:
                        continue
                    if event == "signal_generated":
                        pending_signals[str(signal_id)] = record
                    elif event in terminal_events:
                        pending_signals.pop(str(signal_id), None)
        except OSError:
            logger.exception("Could not inspect pending-entry journal on startup")
            return

        now = datetime.now(IST)
        for record in pending_signals.values():
            signal_time = self._journal_datetime(record.get("signal_time"))
            if signal_time is None:
                logger.error(
                    "Cannot expire prior confirmed-entry signal with invalid time: %s",
                    record.get("signal_id"),
                )
                continue
            pending = {
                **record,
                "symbol": str(record.get("ticker", "")),
                "contract_id": str(record.get("contract_id", "")),
                "signal": str(record.get("signal", "")),
                "score": int(record.get("score") or 0),
                "route": str(record.get("route", "scored")),
                "signal_id": str(record["signal_id"]),
                "signal_time": signal_time,
                "signal_close": record.get("signal_close"),
                "signal_bar": record.get("signal_bar", {}),
                "signal_premium": record.get("signal_premium"),
                "signal_bid": record.get("signal_bid"),
                "signal_ask": record.get("signal_ask"),
                "signal_ltp": record.get("signal_ltp"),
                "signal_quote_age_seconds": record.get("signal_quote_age_seconds"),
                "reasons": record.get("reasons", []),
                "support_resistance_level": record.get(
                    "support_resistance_level"
                ),
                "support_resistance_touches": record.get(
                    "support_resistance_touches"
                ),
                "ema_fast_value": record.get("ema_fast_value"),
                "ema_slow_value": record.get("ema_slow_value"),
            }
            self._log_entry_confirmation_event(
                pending,
                "expired_signal",
                now,
                cancellation_reason="expired_signal",
                cancellation_sub_reason="restart",
            )

    def _queue_confirmed_entry(
        self,
        *,
        symbol: str,
        score: int,
        signal: str,
        strategy_variant: Optional[str],
        signal_bars: list[Bar],
        history: list[dict],
        reasons: list[str],
        support_candidate: Optional[SupportResistanceReversal],
        now: datetime,
    ) -> str:
        leg = "CE" if symbol.endswith("_CE") else "PE"
        key = (symbol, leg)
        existing = getattr(self, "_pending_entries", {}).get(key)
        if existing is not None:
            self._log_entry_confirmation_event(
                existing,
                "signal_ignored_pending",
                now,
                ignored_signal_time=signal_bars[-1].timestamp.isoformat(),
                ignored_score=score,
            )
            return "signal_ignored_pending"
        if not signal_bars:
            logger.error("[%s] Cannot queue confirmed entry without a signal bar", symbol)
            return "signal_missing_bar"

        signal_bar = signal_bars[-1]
        signal_time = self._journal_datetime(signal_bar.timestamp)
        if signal_time is None:
            logger.error("[%s] Cannot queue confirmed entry with invalid bar time", symbol)
            return "signal_invalid_time"
        closes = [float(item["close"]) for item in history if "close" in item]
        fast_values = ema(closes, int(self.config.get("ema_fast", 9)))
        slow_values = ema(closes, int(self.config.get("ema_slow", 21)))
        quote = getattr(self, "option_quote_cache", {}).get(symbol, {})
        quote_metrics = self._option_quote_metrics(quote, now=now)
        contract_id = self._contract_id(symbol)
        signal_id = f"{symbol}|{leg}|{signal_time.isoformat()}"
        support_route = strategy_variant == "paper_underlying_support_reversal"
        signal_bar_payload = signal_bar.to_dict()
        signal_bar_payload["time"] = signal_time
        pending = {
            "signal_id": signal_id,
            "symbol": symbol,
            "underlying": symbol.rsplit("_", 1)[0].upper(),
            "leg": leg,
            "signal": signal,
            "score": int(score),
            "route": "support_reversal" if support_route else "scored",
            "strategy_variant": strategy_variant,
            "signal_time": signal_time,
            "signal_bar": signal_bar_payload,
            "signal_close": float(signal_bar.close),
            "signal_bars": [item.to_dict() for item in signal_bars],
            "history": list(history),
            "reasons": list(reasons),
            "contract_id": contract_id,
            "signal_premium": quote_metrics["ltp"],
            "signal_bid": quote_metrics["bid"],
            "signal_ask": quote_metrics["ask"],
            "signal_ltp": quote_metrics["ltp"],
            "signal_quote_age_seconds": quote_metrics["age_seconds"],
            "support_resistance_level": (
                support_candidate.level if support_route and support_candidate else None
            ),
            "support_resistance_touches": (
                support_candidate.touches if support_route and support_candidate else None
            ),
            "support_resistance_time": (
                support_candidate.bar_time
                if support_route and support_candidate
                else None
            ),
            "ema_fast_value": fast_values[-1] if fast_values else None,
            "ema_slow_value": slow_values[-1] if slow_values else None,
            "minimum_signal_score": self._entry_score_floor(),
            "minimum_premium_override": (
                self.config.get("support_reversal_min_premium", 5.0)
                if support_route
                else None
            ),
            "confirmation_start": signal_time + timedelta(minutes=1),
        }
        self._capture_eligible_option_candles(
            symbol,
            getattr(self, "bar_builder", None).get_bars(
                self.config["instrument_tokens"].get(symbol), limit=50
            )
            if getattr(self, "bar_builder", None)
            and self.config.get("instrument_tokens", {}).get(symbol) is not None
            else [],
            signal_time=signal_time,
            contract_id=contract_id,
        )
        self._pending_entries[key] = pending
        self._log_entry_confirmation_event(
            pending,
            "signal_generated",
            now,
            confirmation_result="pending",
        )
        logger.info(
            "[%s] Pending confirmed entry queued: leg=%s score=%s signal_bar_start=%s "
            "contract=%s",
            symbol,
            leg,
            score,
            signal_time.isoformat(),
            contract_id,
        )
        return "entry_pending_confirmation"

    def _cancel_confirmed_entry(
        self,
        key: tuple[str, str],
        pending: dict,
        now: datetime,
        *,
        reason: str,
        sub_reason: Optional[str] = None,
        confirmation_bar: Optional[Bar] = None,
        confirmation_close: Optional[float] = None,
        confirmation_result: Optional[str] = None,
        confirmation_quote: Optional[dict] = None,
    ) -> None:
        metrics = self._option_quote_metrics(
            confirmation_quote
            if confirmation_quote is not None
            else getattr(self, "option_quote_cache", {}).get(pending["symbol"], {}),
            now=now,
        )
        event = (
            "rejected_by_confirmation"
            if reason.startswith("confirmation_failed_")
            else "expired_signal"
            if reason == "expired_signal"
            else "filter_failed_after_confirmation"
            if reason == "filter_failed_after_confirmation"
            else "confirmation_error"
        )
        confirmation_bar_time = (
            self._journal_datetime(confirmation_bar.timestamp)
            if confirmation_bar is not None
            else None
        )
        self._pending_entries.pop(key, None)
        self._log_entry_confirmation_event(
            pending,
            event,
            now,
            confirmation_candle_time=(
                confirmation_bar_time.isoformat()
                if confirmation_bar_time is not None
                else None
            ),
            confirmation_close=confirmation_close,
            confirmation_result=confirmation_result or "cancelled",
            confirmation_bid=metrics["bid"],
            confirmation_ask=metrics["ask"],
            confirmation_ltp=metrics["ltp"],
            confirmation_quote_age_seconds=metrics["age_seconds"],
            cancellation_reason=reason,
            cancellation_sub_reason=sub_reason,
        )

    def _confirmed_entry_filter_failure(
        self, pending: dict, now: datetime
    ) -> Optional[str]:
        symbol = pending["symbol"]
        if now.time() >= datetime.strptime("14:45", "%H:%M").time():
            return "cutoff"
        if market_session_state([], now=now) != "REGULAR_SESSION":
            return "filter"
        if self._late_window_blocked(now):
            return "filter"

        if self._contract_id(symbol) != pending["contract_id"] or not pending[
            "contract_id"
        ]:
            return "instrument"
        stream = getattr(self, "kite_stream", None)
        if (
            stream is None
            or symbol not in getattr(stream, "contract_symbols", {})
            or symbol not in self.config.get("instrument_tokens", {})
            or not self._option_leg_is_active(symbol, pending["signal"])
        ):
            return "instrument"

        quote = getattr(self, "option_quote_cache", {}).get(symbol, {})
        metrics = self._option_quote_metrics(quote, now=now)
        if not metrics["valid"] or metrics["ask"] is None:
            return "stale_quote"

        signal_bars = pending["signal_bars"]
        if len(signal_bars) < 2:
            return "filter"
        current_bar = pending["signal_bar"]
        previous_bar = signal_bars[-2]
        allowed, reason = self.accuracy_filters.validate_entry_with_reason(
            symbol=symbol,
            signal=pending["signal"],
            score=pending["score"],
            history=pending["history"],
            current_bar=current_bar,
            previous_bar=previous_bar,
            current_time=now.timestamp(),
            hour=now.hour,
            minute=now.minute,
            record_entry=False,
            min_score=pending["minimum_signal_score"],
        )
        if not allowed:
            return "filter"
        if not self._has_option_candle_momentum(
            pending["signal"],
            current_bar,
            minimum_body_ratio=(
                float(self.config.get("support_reversal_min_candle_body_ratio", 0.20))
                if pending["route"] == "support_reversal"
                else self._option_candle_min_body_ratio()
            ),
        ):
            return "filter"
        allowed, _ = self._option_quality_gate(
            symbol,
            pending["signal"],
            pending["score"],
            minimum_premium_override=pending["minimum_premium_override"],
            now=now,
        )
        if not allowed:
            return "premium"

        if not self._live_entry_allowed(symbol):
            return "filter"
        can_open, reason = self._can_open_trade_for_signal(
            symbol, "BUY", pending["score"]
        )
        if not can_open:
            lowered = reason.lower()
            if "daily loss cap" in lowered or "risk budget" in lowered:
                return "loss_cap"
            if "already traded" in lowered or "position" in lowered:
                return "position_limit"
            return "filter"
        return None

    def _process_confirmed_entries(
        self, underlying: str, confirmation_bar: Bar, now: datetime
    ) -> None:
        confirmation_time = self._journal_datetime(confirmation_bar.timestamp)
        if confirmation_time is None:
            logger.error("[%s] Ignoring confirmation with invalid bar timestamp", underlying)
            return
        due = sorted(
            (
                (key, pending)
                for key, pending in getattr(self, "_pending_entries", {}).items()
                if pending["underlying"] == underlying
                and confirmation_time >= pending["confirmation_start"]
            ),
            key=lambda item: (-item[1]["score"], item[1]["signal_time"]),
        )
        for key, pending in due:
            expected_start = pending["confirmation_start"]
            expected_close = expected_start + timedelta(minutes=1)
            if confirmation_time > expected_start:
                self._cancel_confirmed_entry(
                    key,
                    pending,
                    now,
                    reason="expired_signal",
                    sub_reason="missing_candle",
                )
                continue
            if now < expected_close:
                continue
            if (now - expected_close).total_seconds() > 5:
                self._cancel_confirmed_entry(
                    key,
                    pending,
                    now,
                    reason="expired_signal",
                    sub_reason="missing_candle",
                    confirmation_bar=confirmation_bar,
                )
                continue
            if now.time() >= datetime.strptime("14:45", "%H:%M").time():
                self._cancel_confirmed_entry(
                    key,
                    pending,
                    now,
                    reason="expired_signal",
                    sub_reason="cutoff",
                    confirmation_bar=confirmation_bar,
                    confirmation_close=confirmation_bar.close,
                    confirmation_result="not_evaluated_cutoff",
                )
                continue
            try:
                close = float(confirmation_bar.close)
                if not math.isfinite(close):
                    raise ValueError("confirmation close is not finite")
            except (TypeError, ValueError, OverflowError):
                logger.exception(
                    "[%s] Invalid confirmation close; cancelling pending signal",
                    pending["symbol"],
                )
                self._cancel_confirmed_entry(
                    key,
                    pending,
                    now,
                    reason="confirmation_error",
                    sub_reason="invalid_confirmation_close",
                    confirmation_bar=confirmation_bar,
                )
                continue
            passed = (
                close > pending["signal_close"]
                if pending["leg"] == "CE"
                else close < pending["signal_close"]
            )
            if not passed:
                self._cancel_confirmed_entry(
                    key,
                    pending,
                    now,
                    reason=f"confirmation_failed_{pending['leg'].lower()}",
                    confirmation_bar=confirmation_bar,
                    confirmation_close=close,
                    confirmation_result="failed",
                )
                continue

            try:
                failure = self._confirmed_entry_filter_failure(pending, now)
            except Exception:
                logger.exception(
                    "[%s] Confirmation revalidation failed; cancelling without retry",
                    pending["symbol"],
                )
                self._cancel_confirmed_entry(
                    key,
                    pending,
                    now,
                    reason="confirmation_error",
                    sub_reason="revalidation_exception",
                    confirmation_bar=confirmation_bar,
                    confirmation_close=close,
                    confirmation_result="passed",
                )
                continue
            if failure is not None:
                self._cancel_confirmed_entry(
                    key,
                    pending,
                    now,
                    reason="filter_failed_after_confirmation",
                    sub_reason=failure,
                    confirmation_bar=confirmation_bar,
                    confirmation_close=close,
                    confirmation_result="passed",
                )
                continue

            quote = self.option_quote_cache[pending["symbol"]]
            metrics = self._option_quote_metrics(quote, now=now)
            delay = max(
                0.0,
                (now - (pending["signal_time"] + timedelta(minutes=1))).total_seconds(),
            )
            metadata = {
                "entry_mode": "confirmed",
                "route": pending["route"],
                "contract_id": pending["contract_id"],
                "signal_time": pending["signal_time"].isoformat(),
                "signal_close": pending["signal_close"],
                "signal_premium": pending["signal_premium"],
                "signal_bid": pending["signal_bid"],
                "signal_ask": pending["signal_ask"],
                "signal_ltp": pending["signal_ltp"],
                "signal_quote_age_seconds": pending["signal_quote_age_seconds"],
                "confirmation_candle_time": confirmation_time.isoformat(),
                "confirmation_close": close,
                "confirmation_result": "passed",
                "confirmation_bid": metrics["bid"],
                "confirmation_ask": metrics["ask"],
                "confirmation_ltp": metrics["ltp"],
                "confirmation_quote_age_seconds": metrics["age_seconds"],
                "confirmation_delay_seconds": delay,
                "order_premium": metrics["ask"],
                "order_bid": metrics["bid"],
                "order_ask": metrics["ask"],
                "order_ltp": metrics["ltp"],
                "order_quote_age_seconds": metrics["age_seconds"],
            }
            try:
                outcome = self._handle_buy_signal(
                    pending["symbol"],
                    float(metrics["ltp"]),
                    pending["score"],
                    strategy_variant=pending["strategy_variant"],
                    minimum_signal_score=pending["minimum_signal_score"],
                    confirmed_entry_metadata=metadata,
                    force_ask_fill=True,
                )
            except Exception:
                logger.exception(
                    "[%s] Confirmed entry failed; cancelling without retry",
                    pending["symbol"],
                )
                self._cancel_confirmed_entry(
                    key,
                    pending,
                    now,
                    reason="confirmation_error",
                    sub_reason="entry_exception",
                    confirmation_bar=confirmation_bar,
                    confirmation_close=close,
                    confirmation_result="passed",
                    confirmation_quote=quote,
                )
                continue
            if outcome != "trade_opened":
                lowered = outcome.lower()
                if "cutoff" in lowered:
                    sub_reason = "cutoff"
                elif "risk_cap" in lowered or "one_lot_exceeds" in lowered:
                    sub_reason = "risk_cap"
                elif "daily loss" in lowered:
                    sub_reason = "loss_cap"
                elif "position" in lowered or "trade_blocked" in lowered:
                    sub_reason = "position_limit"
                else:
                    sub_reason = "filter"
                self._cancel_confirmed_entry(
                    key,
                    pending,
                    now,
                    reason="filter_failed_after_confirmation",
                    sub_reason=sub_reason,
                    confirmation_bar=confirmation_bar,
                    confirmation_close=close,
                    confirmation_result="passed",
                    confirmation_quote=quote,
                )
                continue

            self._pending_entries.pop(key, None)
            self._log_entry_confirmation_event(
                pending,
                "confirmed_trade",
                now,
                confirmation_candle_time=confirmation_time.isoformat(),
                confirmation_close=close,
                confirmation_result="passed",
                confirmation_bid=metrics["bid"],
                confirmation_ask=metrics["ask"],
                confirmation_ltp=metrics["ltp"],
                confirmation_quote_age_seconds=metrics["age_seconds"],
                confirmation_delay_seconds=delay,
                order_premium=metrics["ask"],
                order_bid=metrics["bid"],
                order_ask=metrics["ask"],
                order_ltp=metrics["ltp"],
                order_quote_age_seconds=metrics["age_seconds"],
                outcome_detail=outcome,
            )
            self.accuracy_filters.record_entry(
                pending["symbol"], now.timestamp()
            )
            if pending["route"] == "support_reversal":
                self._mark_support_reversal_attempt(
                    pending["symbol"],
                    SupportResistanceReversal(
                        signal=pending["signal"],
                        level=float(pending["support_resistance_level"]),
                        touches=int(pending["support_resistance_touches"]),
                        bars_since_touch=0,
                        bar_time=pending["support_resistance_time"]
                        or pending["signal_time"],
                    ),
                )

    def _expire_pending_confirmed_entries(self, now: datetime) -> None:
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        else:
            now = now.astimezone(IST)
        for key, pending in list(getattr(self, "_pending_entries", {}).items()):
            expected_close = pending["confirmation_start"] + timedelta(minutes=1)
            if (now - expected_close).total_seconds() > 5:
                self._cancel_confirmed_entry(
                    key,
                    pending,
                    now,
                    reason="expired_signal",
                    sub_reason="missing_candle",
                )

    def _warm_up_bars(self) -> None:
        """Load recent candles so signals do not wait for a fresh session's bars."""
        provider = KiteHistoricalProvider(
            self.config["kite_api_key"], self.config["kite_access_token"]
        )
        to_date = datetime.now(IST)
        from_date = to_date - timedelta(days=5)
        interval_seconds = self.config.get("bar_interval_seconds", 60)
        interval = "minute" if interval_seconds == 60 else f"{interval_seconds // 60}minute"
        seeded = 0
        for symbol, token in self.config["instrument_tokens"].items():
            try:
                history = provider.fetch_history(
                    token, from_date, to_date, interval=interval
                )
                bars = [
                    Bar(
                        timestamp=item["time"],
                        open=item["open"],
                        high=item["high"],
                        low=item["low"],
                        close=item["close"],
                        volume=item["volume"],
                    )
                    for item in history
                ]
                self.bar_builder.seed_bars(token, bars)
                seeded += len(bars)
                logger.info("[%s] Warmed up %d historical bars", symbol, len(bars))
            except Exception:
                logger.exception(
                    "[%s] Historical warm-up failed; live bars will still be used", symbol
                )
        logger.info("Historical warm-up complete: %d bars loaded", seeded)

    def on_bar_complete(self, token_str: str, bar: Bar) -> None:
        """Called when a new bar is completed."""
        token = int(token_str)
        symbol = self.symbol_map.get(token, f"TOKEN_{token}")
        self._record_active_option_candle(symbol, bar)

        # Check if it's time to exit all positions (3:15 PM)
        if self.intraday_manager.should_exit_all_positions():
            self._handle_market_close_exit()
            self._record_decision(symbol, bar, [], None, "MARKET_CLOSE", "forced_exit_check")
            return

        if self._options_enabled() and not symbol.endswith(("_CE", "_PE")):
            callback_time = getattr(self, "_bar_callback_time", None)
            self._process_confirmed_entries(
                symbol.upper(),
                bar,
                self._journal_datetime(callback_time) or datetime.now(IST),
            )

        logger.info(
            f"[{symbol}] Bar: O={bar.open:.2f} H={bar.high:.2f} L={bar.low:.2f} C={bar.close:.2f} V={bar.volume}"
        )

        if (
            self.config.get("trading_mode") == "intraday_options"
            and symbol.upper()
            in {str(item).upper() for item in self.config.get("options_underlyings", [])}
        ):
            self._record_decision(
                symbol, bar, [], None, "HOLD", "underlying_context_only"
            )
            return

        # Get last N bars for signal evaluation
        bars = self.bar_builder.get_bars(token, limit=50)
        range_outcome = self._try_option_range_breakout(symbol, bars)
        if range_outcome is not None:
            self._record_decision(
                symbol,
                bar,
                bars,
                None,
                "BUY",
                range_outcome,
                strategy_variant="option_range_breakout",
            )
            if range_outcome == "PAPER_RANGE_BREAKOUT_TRADE_OPENED":
                self.accuracy_filters.record_entry(symbol, time.time())
                return
        if len(bars) < 30:
            logger.debug(f"[{symbol}] Not enough bars yet ({len(bars)}/30)")
            self._record_decision(
                symbol,
                bar,
                bars,
                None,
                "HOLD",
                "not_enough_bars",
            )
            return

        signal_bars = bars
        support_underlying_bars: list[Bar] = []
        if self._options_enabled() and "_" in symbol:
            underlying = symbol.rsplit("_", 1)[0].upper()
            underlying_token = self.config["instrument_tokens"].get(underlying)
            underlying_bars = (
                self.bar_builder.get_bars(underlying_token, limit=50)
                if underlying_token is not None
                else []
            )
            if len(underlying_bars) < 30:
                logger.info(
                    "[%s] Skipping option signal until %s has enough underlying bars",
                    symbol,
                    underlying,
                )
                self._record_decision(
                    symbol,
                    bar,
                    bars,
                    None,
                    "HOLD",
                    "underlying_signal_unavailable",
                )
                return
            signal_bars = underlying_bars
            if self.config.get("support_reversal_enabled", False):
                support_underlying_bars = self.bar_builder.get_bars(
                    underlying_token, limit=100
                )

        # Convert bars to history format for engine
        history = [b.to_dict() for b in signal_bars]
        volume_confirmation_history = None
        if self._options_enabled() and "_" in symbol:
            volume_confirmation_history = _aligned_option_volume_history(
                signal_bars,
                bars,
                self.config.get("bar_interval_seconds", 60),
            )
        session_state = market_session_state(history, now=datetime.now(IST))
        session_label = {
            "BEFORE_OPEN": "before open",
            "REGULAR_SESSION": "regular session",
            "AFTER_CLOSE": "after close",
        }.get(session_state, "unknown")
        logger.info(f"[{symbol}] status={session_label}")

        if session_state == "AFTER_CLOSE":
            reason = "Market is after close; no live trading signal"
            self._record_decision(symbol, bar, bars, None, "HOLD", reason)
            logger.info(f"[{symbol}] status={session_label} | {reason}")
            return

        context_histories = {}
        benchmark_symbols = self.config.get(
            "benchmark_symbols", [self.benchmark_symbol, "BANKNIFTY"]
        )
        if self.use_market_context:
            for benchmark_symbol in dict.fromkeys(benchmark_symbols):
                benchmark_token = self.config["instrument_tokens"].get(benchmark_symbol)
                if benchmark_token is None or benchmark_symbol == symbol:
                    continue
                benchmark_bars = self.bar_builder.get_bars(benchmark_token, limit=100)
                if benchmark_bars:
                    context_histories[benchmark_symbol] = [
                        b.to_dict() for b in benchmark_bars
                    ]

        try:
            market_score = score_market(
                symbol,
                history,
                ema_fast=self.config.get("ema_fast", 9),
                ema_slow=self.config.get("ema_slow", 21),
                rsi_period=self.config.get("rsi_period", 14),
                context_histories=context_histories,
                allow_before_open=(session_state == "BEFORE_OPEN"),
                session_state=session_state,
                hard_context_filter=bool(self.config.get("hard_context_filter", True)),
                min_adx=float(self.config.get("min_adx", 18.0)),
                sideways_range_pct=float(self.config.get("sideways_range_pct", 1.0)),
                sideways_net_move_pct=float(
                    self.config.get("sideways_net_move_pct", 1.0)
                ),
                min_trend_strength=float(
                    self.config.get("min_trend_strength", 0.02)
                ),
                trend_momentum_bonus_threshold=(
                    float(self.config["trend_momentum_bonus_threshold"])
                    if self.config.get("trend_momentum_bonus_threshold") is not None
                    else None
                ),
                signal_proximity_pct=float(
                    self.config.get("signal_proximity_pct", 0.005)
                ),
                volume_confirmation_history=volume_confirmation_history,
                allow_trend_continuation=bool(
                    self.config.get("allow_trend_continuation", False)
                ),
                rsi_buy_block_above=float(
                    self.config.get("rsi_buy_block_above", 80.0)
                ),
                rsi_sell_block_below=float(
                    self.config.get("rsi_sell_block_below", 25.0)
                ),
            )
        except Exception:
            logger.exception("[%s] Strategy evaluation failed", symbol)
            self._record_decision(symbol, bar, bars, None, "ERROR", "strategy_error")
            return
        news_context = self.news_monitor.snapshot() if self.news_monitor else None
        if news_context:
            filtered_signal, news_reason = apply_news_filter(
                market_score.signal, news_context
            )
            if news_reason:
                market_score.signal = filtered_signal
                market_score.reasons.append(news_reason)

        support_candidate: Optional[SupportResistanceReversal] = None
        if (
            session_state == "REGULAR_SESSION"
            and support_underlying_bars
            and symbol.endswith(("_CE", "_PE"))
        ):
            support_candidate = self._support_reversal_candidate(
                symbol, support_underlying_bars
            )
            active_positions = getattr(
                getattr(self, "intraday_manager", None), "active_positions", {}
            )
            underlying_prefix = f"{symbol.rsplit('_', 1)[0].upper()}_"
            underlying_position_active = (
                isinstance(active_positions, dict)
                and any(
                    position_symbol.startswith(underlying_prefix)
                    for position_symbol in active_positions
                )
            )
            if (
                support_candidate is not None
                and isinstance(active_positions, dict)
                and not underlying_position_active
                and market_score.signal in {"HOLD", support_candidate.signal}
            ):
                context_block = None
                for context_name, context_history in context_histories.items():
                    filtered_signal, context_reason = filter_signal_by_context(
                        support_candidate.signal,
                        context_history,
                        ema_fast=int(self.config.get("ema_fast", 9)),
                        ema_slow=int(self.config.get("ema_slow", 21)),
                        hard_block=bool(self.config.get("hard_context_filter", True)),
                    )
                    if context_reason:
                        market_score.reasons.append(
                            f"{context_name}: {context_reason}"
                        )
                    if filtered_signal != support_candidate.signal:
                        context_block = context_reason or "context filter blocked signal"
                        break

                news_block = False
                if news_context:
                    filtered_signal, news_reason = apply_news_filter(
                        support_candidate.signal, news_context
                    )
                    if filtered_signal != support_candidate.signal:
                        market_score.reasons.append(
                            news_reason or "News filter blocked support reversal"
                        )
                        news_block = True

                try:
                    support_min_score = int(
                        self.config.get("support_reversal_min_score", 75)
                    )
                except (TypeError, ValueError, OverflowError):
                    support_min_score = 86
                support_score = min(
                    85,
                    max(
                        market_score.score,
                        65 + 5 * support_candidate.touches,
                    ),
                )
                if context_block:
                    logger.info(
                        "[%s] Paper support reversal blocked: %s",
                        symbol,
                        context_block,
                    )
                elif news_block:
                    logger.info("[%s] Paper support reversal blocked by news", symbol)
                elif (
                    "RSI overbought against BUY" in market_score.reasons
                    if support_candidate.signal == "BUY"
                    else "RSI oversold against SELL" in market_score.reasons
                ):
                    logger.info(
                        "[%s] Paper support reversal blocked by RSI extreme",
                        symbol,
                    )
                elif not 55 <= support_min_score <= 85:
                    logger.error(
                        "[%s] Invalid support_reversal_min_score", symbol
                    )
                elif support_score >= support_min_score:
                    market_score.signal = support_candidate.signal
                    market_score.score = support_score
                    market_score.strategy_variant = (
                        "paper_underlying_support_reversal"
                    )
                    market_score.reasons.append(
                        "Paper underlying support/reversal confirmed at "
                        f"{support_candidate.level:.2f} "
                        f"({support_candidate.touches} clustered pivots)"
                    )

        ema_reentry_context = self._ema_reentry_candidate(symbol, history)
        if ema_reentry_context is not None:
            market_score.signal = ema_reentry_context["signal"]
            market_score.score = max(
                market_score.score,
                self._entry_score_floor(),
            )
            market_score.strategy_variant = "paper_ema_stop_reentry"
            market_score.reasons.append(ema_reentry_context["reentry_reason"])
            state = self._ema_reentry_states[symbol]
            self._log_ema_reentry_event(
                symbol,
                state,
                "SIGNAL_CONFIRMED",
                current_time=self._journal_datetime(
                    ema_reentry_context["signal_time"]
                )
                or datetime.now(IST),
                signal=ema_reentry_context,
                outcome="signal_confirmed",
            )

        logger.info(
            "[%s] Score=%s Signal=%s Reasons=%s",
            symbol,
            market_score.score,
            market_score.signal,
            "; ".join(market_score.reasons) or "none",
        )

        active_positions = getattr(self.intraday_manager, "active_positions", None)
        if (
            self._options_enabled()
            and symbol.endswith(("_CE", "_PE"))
            and isinstance(active_positions, dict)
            and symbol in active_positions
        ):
            position = active_positions[symbol]
            if position.get("exit_strategy") not in {
                PAPER_OPTION_TRAIL_RUNNER,
                "paper_range_breakout_2r",
            }:
                minimum_signal_score = int(
                    position.get(
                        "minimum_signal_score",
                        self.accuracy_filters.min_score_floor,
                    )
                )
                self._check_option_signal_health(
                    symbol,
                    market_score.signal,
                    market_score.score,
                    minimum_signal_score,
                    price=self.latest_prices.get(symbol, bar.close),
                )

        if session_state == "BEFORE_OPEN":
            if ema_reentry_context is not None:
                self._complete_ema_reentry_attempt(
                    symbol, ema_reentry_context, "pre_market_blocked"
                )
            logger.info(
                "[%s] pre-market analysis: score=%s signal=%s (no orders until regular session)",
                symbol,
                market_score.score,
                market_score.signal,
            )
            if market_score.signal in {"BUY", "SELL"}:
                self.premarkarket_candidates.append(
                    (
                        symbol,
                        market_score.signal,
                        market_score.score,
                        "; ".join(market_score.reasons[:3]),
                    )
                )
            self._record_decision(
                symbol,
                bar,
                bars,
                market_score,
                market_score.signal,
                "PREMARKET_WATCHLIST",
                news_context,
            )
            return

        if (
            market_score.signal in {"BUY", "SELL"}
            and self._late_window_blocked(datetime.now(IST))
        ):
            if ema_reentry_context is not None:
                self._complete_ema_reentry_attempt(
                    symbol, ema_reentry_context, "late_window_blocked"
                )
            logger.info(
                "[%s] Entry blocked by configured late-window guard at %s IST",
                symbol,
                datetime.now(IST).strftime("%H:%M"),
            )
            self._record_decision(
                symbol,
                bar,
                bars,
                market_score,
                market_score.signal,
                "late_window_blocked",
                news_context,
            )
            return

        if (
            self._options_enabled()
            and "_" in symbol
            and market_score.signal in {"BUY", "SELL"}
        ):
            underlying = symbol.rsplit("_", 1)[0].upper()
            preferred = self._preferred_option_symbol(underlying, market_score.signal)
            if preferred is None:
                if ema_reentry_context is not None:
                    self._complete_ema_reentry_attempt(
                        symbol,
                        ema_reentry_context,
                        "option_leg_unavailable",
                    )
                logger.info(
                    "[%s] No eligible option leg for %s signal; skipping entry",
                    symbol,
                    market_score.signal,
                )
                self._record_decision(
                    symbol,
                    bar,
                    bars,
                    market_score,
                    market_score.signal,
                    "OPTION_FILTER_LEG_UNAVAILABLE",
                    news_context,
                )
                return
            if symbol != preferred:
                if ema_reentry_context is not None:
                    self._complete_ema_reentry_attempt(
                        symbol, ema_reentry_context, "option_leg_skipped"
                    )
                logger.info(
                    "[%s] Skipping %s because %s is the active option leg for %s signal",
                    symbol,
                    symbol,
                    preferred,
                    market_score.signal,
                )
                self._record_decision(
                    symbol,
                    bar,
                    bars,
                    market_score,
                    market_score.signal,
                    "OPTION_LEG_SKIPPED",
                    news_context,
                )
                return

            minimum_body_ratio = self._option_candle_min_body_ratio()
            if (
                getattr(market_score, "strategy_variant", None)
                == "paper_underlying_support_reversal"
            ):
                try:
                    minimum_body_ratio = float(
                        self.config.get(
                            "support_reversal_min_candle_body_ratio", 0.20
                        )
                    )
                except (TypeError, ValueError, OverflowError):
                    minimum_body_ratio = float("nan")
                if (
                    not math.isfinite(minimum_body_ratio)
                    or not 0 < minimum_body_ratio <= 1
                ):
                    logger.error(
                        "[%s] Invalid support-reversal candle body ratio",
                        symbol,
                    )
                    self._record_decision(
                        symbol,
                        bar,
                        bars,
                        market_score,
                        market_score.signal,
                        "PAPER_SUPPORT_REVERSAL_INVALID_BODY_RATIO",
                        news_context,
                    )
                    return
            if ema_reentry_context is None and not self._has_option_candle_momentum(
                market_score.signal,
                signal_bars[-1].to_dict(),
                minimum_body_ratio=minimum_body_ratio,
            ):
                logger.info(
                    "[%s] Option entry rejected: signal candle lacks directional momentum",
                    symbol,
                )
                self._record_decision(
                    symbol,
                    bar,
                    bars,
                    market_score,
                    market_score.signal,
                    "OPTION_FILTER_WEAK_CANDLE_MOMENTUM",
                    news_context,
                )
                return

            if (
                getattr(self, "entry_mode", "immediate") == "confirmed"
                and ema_reentry_context is None
                and market_score.signal in {"BUY", "SELL"}
            ):
                self._capture_eligible_option_candles(
                    symbol,
                    bars,
                    signal_time=self._journal_datetime(signal_bars[-1].timestamp),
                    contract_id=self._contract_id(symbol),
                )

            if (
                getattr(market_score, "strategy_variant", None)
                == "paper_underlying_support_reversal"
            ):
                allowed, option_reason = self._option_quality_gate(
                    symbol,
                    market_score.signal,
                    market_score.score,
                    minimum_premium_override=self.config.get(
                        "support_reversal_min_premium", 5.0
                    ),
                )
            else:
                allowed, option_reason = self._option_quality_gate(
                    symbol,
                    market_score.signal,
                    market_score.score,
                )
            if not allowed:
                if ema_reentry_context is not None:
                    self._complete_ema_reentry_attempt(
                        symbol,
                        ema_reentry_context,
                        f"option_quality_rejected:{option_reason}",
                    )
                logger.info("[%s] Option quality reject: %s", symbol, option_reason)
                self._record_decision(
                    symbol,
                    bar,
                    bars,
                    market_score,
                    market_score.signal,
                    f"OPTION_FILTER_{option_reason.upper().replace(' ', '_')}",
                    news_context,
                )
                return
            if (
                getattr(self, "entry_mode", "immediate") != "confirmed"
                or ema_reentry_context is not None
            ):
                self._capture_eligible_option_candles(symbol, bars)

        if self.premarkarket_candidates:
            self.premarkarket_candidates.clear()

        if market_score.signal in {"BUY", "SELL"}:
            previous_bar = (
                signal_bars[-2].to_dict()
                if len(signal_bars) > 1
                else signal_bars[-1].to_dict()
            )
            current_time = time.time()
            now = datetime.now(IST)
            position_minimum_score = self._entry_score_floor()
            if ema_reentry_context is not None:
                allowed, rejection_reason = True, "ema_reentry_confirmation"
            else:
                allowed, rejection_reason = self.accuracy_filters.validate_entry_with_reason(
                    symbol=symbol,
                    signal=market_score.signal,
                    score=market_score.score,
                    history=history,
                    current_bar=signal_bars[-1].to_dict(),
                    previous_bar=previous_bar,
                    current_time=current_time,
                    hour=now.hour,
                    minute=now.minute,
                    record_entry=False,
                    min_score=position_minimum_score,
                )
            if not allowed:
                logger.info(
                    "[%s] Signal rejected by accuracy filter (%s): score=%s signal=%s",
                    symbol,
                    rejection_reason,
                    market_score.score,
                    market_score.signal,
                )
                self._record_decision(
                    symbol,
                    bar,
                    bars,
                    market_score,
                    market_score.signal,
                    f"accuracy_filter_rejected:{rejection_reason}",
                    news_context,
                )
                return
            if (
                support_candidate is not None
                and getattr(market_score, "strategy_variant", None)
                == "paper_underlying_support_reversal"
                and getattr(self, "entry_mode", "immediate") != "confirmed"
            ):
                self._mark_support_reversal_attempt(
                    symbol, support_candidate
                )

        trade_action = self._option_trade_action(symbol, market_score.signal)
        if trade_action == "BUY":
            if (
                getattr(self, "entry_mode", "immediate") == "confirmed"
                and self._options_enabled()
                and symbol.endswith(("_CE", "_PE"))
                and ema_reentry_context is None
            ):
                outcome = self._queue_confirmed_entry(
                    symbol=symbol,
                    score=market_score.score,
                    signal=market_score.signal,
                    strategy_variant=market_score.strategy_variant,
                    signal_bars=signal_bars,
                    history=history,
                    reasons=market_score.reasons,
                    support_candidate=support_candidate,
                    now=now,
                )
            else:
                if ema_reentry_context is not None:
                    outcome = self._handle_buy_signal(
                        symbol,
                        bar.close,
                        market_score.score,
                        strategy_variant=market_score.strategy_variant,
                        minimum_signal_score=position_minimum_score,
                        ema_reentry_context=ema_reentry_context,
                    )
                else:
                    outcome = self._handle_buy_signal(
                        symbol,
                        bar.close,
                        market_score.score,
                        strategy_variant=market_score.strategy_variant,
                        minimum_signal_score=position_minimum_score,
                    )
        elif trade_action == "SELL":
            outcome = self._handle_sell_signal(
                symbol,
                bar.close,
                market_score.score,
                strategy_variant=market_score.strategy_variant,
                minimum_signal_score=position_minimum_score,
            )
        else:
            logger.debug(f"[{symbol}] HOLD - not enough confidence")
            outcome = "hold"

        if ema_reentry_context is not None:
            self._complete_ema_reentry_attempt(
                symbol, ema_reentry_context, outcome
            )

        if outcome == "trade_opened":
            self.accuracy_filters.record_entry(symbol, current_time)

        self._record_decision(
            symbol,
            bar,
            bars,
            market_score,
            market_score.signal,
            outcome,
            news_context,
            ema_reentry_context=ema_reentry_context,
        )

    def _start_paper_shadow_runner(
        self,
        symbol: str,
        trade_id: str,
        entry_price: float,
        stop_loss: float,
        quantity: int,
        entry_time: Optional[str] = None,
    ) -> None:
        journal = getattr(self, "paper_shadow_exit_journal", None)
        if (
            journal is None
            or not getattr(self, "paper_trading_enabled", False)
            or getattr(self, "live_orders_enabled", False)
            or not self._options_enabled()
            or not symbol.endswith(("_CE", "_PE"))
            or not self.config.get("paper_shadow_1r_runner_enabled", True)
        ):
            return

        quote = getattr(self, "option_quote_cache", {}).get(symbol, {})
        bid = self._positive_quote_value(quote.get("bid"))
        ask = self._positive_quote_value(quote.get("ask"))
        quote_timestamp = quote.get("timestamp")
        if isinstance(quote_timestamp, datetime):
            quote_timestamp = (
                quote_timestamp.replace(tzinfo=IST)
                if quote_timestamp.tzinfo is None
                else quote_timestamp.astimezone(IST)
            )
        else:
            quote_timestamp = None
        max_quote_age = float(self.config.get("option_quote_max_age_seconds", 60))
        quote_age = (
            (datetime.now(IST) - quote_timestamp).total_seconds()
            if quote_timestamp is not None
            else None
        )
        quote_is_fresh = (
            quote_age is not None
            and math.isfinite(max_quote_age)
            and max_quote_age > 0
            and 0 <= quote_age <= max_quote_age
        )
        quote_is_valid = (
            bid is not None
            and ask is not None
            and ask >= bid
            and quote_is_fresh
        )
        entry_fill = ask if quote_is_valid else float(entry_price)
        fill_source = "best_ask" if quote_is_valid else "last_price_fallback"
        risk_distance = float(entry_fill) - float(stop_loss)
        if not math.isfinite(risk_distance) or risk_distance <= 0:
            logger.error(
                "[%s] Cannot start 1R shadow runner with invalid initial stop distance",
                symbol,
            )
            return

        fee_per_order = float(
            self.config.get("paper_shadow_fee_per_order", 0.0)
        )
        fee_bps = float(
            self.config.get("paper_shadow_fee_bps_per_side", 0.0)
        )
        slippage_bps = float(
            self.config.get("paper_shadow_slippage_bps_per_side", 0.0)
        )
        if (
            not math.isfinite(fee_per_order)
            or fee_per_order < 0
            or not math.isfinite(fee_bps)
            or fee_bps < 0
            or not math.isfinite(slippage_bps)
            or slippage_bps < 0
        ):
            raise ValueError(
                "Paper shadow fees and slippage assumptions must be finite and non-negative"
            )
        state = {
            "trade_id": str(trade_id),
            "ticker": symbol,
            "status": "open",
            "entry_time": entry_time or datetime.now(IST).isoformat(),
            "entry_ltp": float(entry_price),
            "entry_bid": bid,
            "entry_ask": ask,
            "entry_spread_rupees": (
                ask - bid if quote_is_valid else None
            ),
            "entry_quote_time": (
                quote_timestamp.isoformat() if quote_timestamp is not None else None
            ),
            "entry_quote_age_seconds": quote_age,
            "entry_quote_is_fresh": quote_is_fresh,
            "entry_fill_price": float(entry_fill),
            "entry_fill_source": fill_source,
            "stop_loss": float(stop_loss),
            "risk_distance": risk_distance,
            "quantity": int(quantity),
            "runner_activation_r": 1.0,
            "runner_gap_r": 1.0,
            "highest_price": float(entry_fill),
            "trailing_stop": float(stop_loss),
            "trailing_active": False,
            "fee_per_order": fee_per_order,
            "fee_bps_per_side": fee_bps,
            "slippage_bps_per_side": slippage_bps,
            "last_observed_ltp": float(entry_price),
            "last_observed_bid": bid,
            "last_observed_ask": ask,
            "last_observed_at": datetime.now(IST).isoformat(),
            "last_persisted_at": datetime.now(IST).isoformat(),
        }
        try:
            journal.start(state)
        except OSError:
            logger.exception("[%s] Could not start the 1R shadow runner journal", symbol)
            return
        positions = getattr(self, "paper_shadow_positions", None)
        if positions is None:
            positions = {}
            self.paper_shadow_positions = positions
        positions[str(trade_id)] = state
        logger.info(
            "[%s] Started 1R shadow runner: qty=%d entry_ref=%.2f entry_fill=%.2f "
            "stop=%.2f risk=%.2f fill_source=%s",
            symbol,
            quantity,
            entry_price,
            entry_fill,
            stop_loss,
            risk_distance,
            fill_source,
        )

    @staticmethod
    def _positive_quote_value(value) -> Optional[float]:
        try:
            quote = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return quote if math.isfinite(quote) and quote > 0 else None

    def _option_quote_metrics(
        self, quote: dict, now: Optional[datetime] = None
    ) -> dict:
        bid = self._positive_quote_value(quote.get("bid"))
        ask = self._positive_quote_value(quote.get("ask"))
        ltp = self._positive_quote_value(
            quote.get("last_price", quote.get("premium"))
        )
        timestamp = self._journal_datetime(quote.get("timestamp"))
        now = now or datetime.now(IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        else:
            now = now.astimezone(IST)
        age_seconds = (
            (now - timestamp).total_seconds() if timestamp is not None else None
        )
        try:
            configured_age = float(
                getattr(self, "config", {}).get(
                    "option_quote_max_age_seconds", 60
                )
            )
        except (TypeError, ValueError, OverflowError):
            configured_age = 0.0
        max_age = min(configured_age, 60.0)
        fresh = (
            age_seconds is not None
            and math.isfinite(max_age)
            and max_age > 0
            and 0 <= age_seconds <= max_age
        )
        in_spread = (
            bid is not None
            and ask is not None
            and ask >= bid
            and ltp is not None
            and bid <= ltp <= ask
        )
        return {
            "bid": bid,
            "ask": ask,
            "ltp": ltp,
            "timestamp": timestamp,
            "age_seconds": age_seconds,
            "fresh": fresh,
            "in_spread": in_spread,
            "valid": fresh and in_spread,
        }

    def _quote_validated_long_option(self, symbol: str, position: dict) -> bool:
        return (
            bool(
                getattr(self, "config", {}).get(
                    "option_quote_validated_stops_enabled", False
                )
            )
            and symbol.endswith(("_CE", "_PE"))
            and str(position.get("direction", "")).upper() == "BUY"
        )

    def _paper_shadow_quote_is_fresh(self, quote: dict) -> bool:
        return self._option_quote_metrics(quote)["fresh"]

    def _update_paper_shadow_runner(self, symbol: str, tick: Tick) -> None:
        positions = getattr(self, "paper_shadow_positions", {})
        journal = getattr(self, "paper_shadow_exit_journal", None)
        if journal is None:
            return
        state = next(
            (
                record for record in positions.values()
                if record.get("ticker") == symbol and record.get("status") == "open"
            ),
            None,
        )
        if state is None:
            return

        try:
            tick_time = tick.timestamp
            if tick_time.tzinfo is None:
                tick_time = tick_time.replace(tzinfo=IST)
            else:
                tick_time = tick_time.astimezone(IST)
        except (AttributeError, TypeError, ValueError):
            tick_time = datetime.now(IST)
        try:
            entry_time = datetime.fromisoformat(
                str(state["entry_time"]).replace("Z", "+00:00")
            )
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=IST)
            else:
                entry_time = entry_time.astimezone(IST)
        except (KeyError, TypeError, ValueError):
            logger.error("[%s] Shadow runner has an invalid entry timestamp", symbol)
            return

        bid = self._positive_quote_value(tick.bid)
        ask = self._positive_quote_value(tick.ask)
        ltp = self._positive_quote_value(tick.last_price)
        if ltp is None:
            logger.warning("[%s] Ignoring invalid tick for paper shadow runner", symbol)
            return
        mark = bid if bid is not None else ltp
        fill_source = "best_bid" if bid is not None else "last_price_fallback"

        if tick_time.date() != entry_time.date():
            mark = self._positive_quote_value(state.get("last_observed_bid")) or float(
                state.get("last_observed_ltp", ltp)
            )
            self._close_paper_shadow_runner(
                state,
                mark,
                mark,
                bid,
                ask,
                tick_time,
                "SESSION_GAP_FORCED_EXIT",
                "last_observed_quote",
            )
            return

        current_stop = float(state["trailing_stop"])
        if mark <= current_stop:
            self._close_paper_shadow_runner(
                state, ltp, mark, bid, ask, tick_time, "SHADOW_TRAILING_STOP", fill_source
            )
            return

        previous_active = bool(state["trailing_active"])
        previous_stop = current_stop
        state["highest_price"] = max(float(state["highest_price"]), mark)
        if (
            float(state["highest_price"]) - float(state["entry_fill_price"])
            >= float(state["risk_distance"])
        ):
            state["trailing_active"] = True
        if state["trailing_active"]:
            state["trailing_stop"] = max(
                current_stop,
                float(state["highest_price"]) - float(state["risk_distance"]),
            )

        state.update(
            {
                "last_observed_ltp": ltp,
                "last_observed_bid": bid,
                "last_observed_ask": ask,
                "last_observed_at": tick_time.isoformat(),
            }
        )
        should_exit = getattr(
            self.intraday_manager, "should_exit_all_positions", None
        )
        if should_exit and should_exit():
            self._close_paper_shadow_runner(
                state, ltp, mark, bid, ask, tick_time,
                "MARKET_CLOSE_FORCED_EXIT", fill_source
            )
            return

        previous_persisted = datetime.fromisoformat(
            str(state.get("last_persisted_at", state["entry_time"])).replace(
                "Z", "+00:00"
            )
        )
        if previous_persisted.tzinfo is None:
            previous_persisted = previous_persisted.replace(tzinfo=IST)
        else:
            previous_persisted = previous_persisted.astimezone(IST)
        persist_state = (
            state["trailing_active"] != previous_active
            or state["trailing_stop"] != previous_stop
            or (tick_time - previous_persisted).total_seconds() >= 30
        )
        if persist_state:
            state["last_persisted_at"] = tick_time.isoformat()
            try:
                persisted = journal.update(str(state["trade_id"]), state)
            except OSError:
                logger.exception(
                    "[%s] Could not persist 1R shadow-runner state", symbol
                )
                return
            if not persisted:
                logger.error(
                    "[%s] Could not persist 1R shadow-runner state", symbol
                )

    def _close_paper_shadow_runner(
        self,
        state: dict,
        exit_ltp: float,
        exit_fill: float,
        bid: Optional[float],
        ask: Optional[float],
        exit_time: datetime,
        reason: str,
        fill_source: str,
    ) -> None:
        journal = getattr(self, "paper_shadow_exit_journal", None)
        if journal is None:
            return
        quantity = int(state["quantity"])
        entry_fill = float(state["entry_fill_price"])
        fee_cost = (
            2.0 * float(state["fee_per_order"])
            + (entry_fill + float(exit_fill))
            * float(state["fee_bps_per_side"])
            / 10000.0
            * quantity
        )
        slippage_cost = (
            (entry_fill + float(exit_fill))
            * float(state["slippage_bps_per_side"])
            / 10000.0
            * quantity
        )
        gross_pnl = (float(exit_fill) - entry_fill) * quantity
        actual_gross = state.get("actual_gross_pnl_rupees")
        actual_fee_cost = None
        actual_slippage_cost = None
        actual_net = None
        actual_bid_ask_gross = None
        if state.get("actual_exit_price") is not None:
            actual_exit_bid = self._positive_quote_value(
                state.get("actual_exit_bid")
            )
            actual_entry_ask = (
                self._positive_quote_value(state.get("entry_ask"))
                if state.get("entry_quote_is_fresh")
                else None
            )
            has_actual_quotes = (
                actual_entry_ask is not None and actual_exit_bid is not None
            )
            actual_quote_entry = (
                actual_entry_ask
                if has_actual_quotes
                else float(state.get("actual_entry_ltp", state["entry_ltp"]))
            )
            actual_quote_exit = (
                actual_exit_bid
                if has_actual_quotes
                else float(state["actual_exit_price"])
            )
            actual_fee_cost = (
                2.0 * float(state["fee_per_order"])
                + (actual_quote_entry + actual_quote_exit)
                * float(state["fee_bps_per_side"])
                / 10000.0
                * quantity
            )
            actual_slippage_cost = (
                (actual_quote_entry + actual_quote_exit)
                * float(state["slippage_bps_per_side"])
                / 10000.0
                * quantity
            )
            actual_net = (
                float(actual_gross) - actual_fee_cost - actual_slippage_cost
            )
            if has_actual_quotes:
                actual_bid_ask_gross = (
                    actual_exit_bid - actual_entry_ask
                ) * quantity
                actual_net = (
                    actual_bid_ask_gross
                    - float(actual_fee_cost)
                    - actual_slippage_cost
                )

        state.update(
            {
                "exit_time": exit_time.isoformat(),
                "exit_reason": reason,
                "exit_ltp": float(exit_ltp),
                "exit_bid": bid,
                "exit_ask": ask,
                "exit_spread_rupees": (
                    ask - bid if bid is not None and ask is not None and ask >= bid
                    else None
                ),
                "exit_fill_price": float(exit_fill),
                "exit_fill_source": fill_source,
                "gross_pnl_rupees": gross_pnl,
                "estimated_fee_rupees": fee_cost,
                "estimated_extra_slippage_rupees": slippage_cost,
                "net_pnl_estimate_rupees": gross_pnl - fee_cost - slippage_cost,
                "actual_gross_pnl_rupees": actual_gross,
                "actual_estimated_fee_rupees": actual_fee_cost,
                "actual_estimated_extra_slippage_rupees": actual_slippage_cost,
                "actual_bid_ask_gross_pnl_rupees": actual_bid_ask_gross,
                "actual_net_pnl_estimate_rupees": actual_net,
                "last_observed_ltp": float(exit_ltp),
                "last_observed_bid": bid,
                "last_observed_ask": ask,
                "last_observed_at": exit_time.isoformat(),
            }
        )
        try:
            persisted = journal.close(str(state["trade_id"]), state)
        except OSError:
            logger.exception(
                "[%s] Could not persist 1R shadow-runner exit",
                state.get("ticker"),
            )
            state["status"] = "closed"
            return
        if not persisted:
            logger.error(
                "[%s] Could not persist 1R shadow-runner exit", state.get("ticker")
            )
            return
        state["status"] = "closed"
        logger.info(
            "[%s] 1R shadow exit %s at %.2f; gross=%.2f net_estimate=%.2f "
            "actual_ltp_gross=%s actual_net_estimate=%s",
            state["ticker"],
            reason,
            exit_fill,
            gross_pnl,
            gross_pnl - fee_cost - slippage_cost,
            f"{actual_gross:.2f}" if actual_gross is not None else "pending",
            f"{actual_net:.2f}" if actual_net is not None else "pending",
        )

    def _record_paper_shadow_actual_exit(
        self,
        trade: Optional[dict],
        exit_price: float,
        reason: str,
    ) -> None:
        journal = getattr(self, "paper_shadow_exit_journal", None)
        if journal is None or not trade or not trade.get("trade_id"):
            return
        if str(trade.get("action", "")).upper() != "BUY":
            return
        ticker = str(trade.get("ticker", ""))
        if not ticker.endswith(("_CE", "_PE")):
            return
        quote = getattr(self, "option_quote_cache", {}).get(ticker, {})
        quantity = int(trade.get("quantity", 0) or 0)
        entry = float(trade.get("entry", 0.0) or 0.0)
        actual_gross = (float(exit_price) - entry) * quantity
        fee_per_order = float(
            self.config.get("paper_shadow_fee_per_order", 0.0)
        )
        fee_bps = float(
            self.config.get("paper_shadow_fee_bps_per_side", 0.0)
        )
        slippage_bps = float(
            self.config.get("paper_shadow_slippage_bps_per_side", 0.0)
        )
        state = next(
            (
                record for record in getattr(self, "paper_shadow_positions", {}).values()
                if str(record.get("trade_id")) == str(trade["trade_id"])
            ),
            journal.latest.get(str(trade["trade_id"]), {}),
        )
        if not state:
            return
        entry_ask = (
            self._positive_quote_value(trade.get("paper_entry_ask"))
            if trade.get("paper_entry_quote_is_fresh")
            else None
        )
        exit_bid = self._positive_quote_value(quote.get("bid"))
        has_quotes = entry_ask is not None and exit_bid is not None
        quote_entry = entry_ask if has_quotes else entry
        quote_exit = exit_bid if has_quotes else float(exit_price)
        bid_ask_gross = (
            (quote_exit - quote_entry) * quantity if has_quotes else None
        )
        fee_cost = (
            2.0 * fee_per_order
            + (quote_entry + quote_exit) * fee_bps / 10000.0 * quantity
        )
        slippage_cost = (
            (quote_entry + quote_exit) * slippage_bps / 10000.0 * quantity
        )
        fields = {
            **state,
            "actual_exit_time": datetime.now(IST).isoformat(),
            "actual_exit_reason": reason,
            "actual_exit_price": float(exit_price),
            "actual_exit_bid": self._positive_quote_value(quote.get("bid")),
            "actual_exit_ask": self._positive_quote_value(quote.get("ask")),
            "actual_gross_pnl_rupees": actual_gross,
            "actual_entry_ltp": entry,
            "actual_entry_bid": self._positive_quote_value(trade.get("paper_entry_bid")),
            "actual_entry_ask": entry_ask,
            "actual_estimated_fee_rupees": fee_cost,
            "actual_estimated_extra_slippage_rupees": slippage_cost,
            "actual_bid_ask_gross_pnl_rupees": bid_ask_gross,
            "actual_net_pnl_estimate_rupees": (
                (bid_ask_gross if bid_ask_gross is not None else actual_gross)
                - fee_cost
                - slippage_cost
            ),
        }
        try:
            if not journal.annotate_actual_exit(str(trade["trade_id"]), fields):
                logger.error(
                    "[%s] Could not attach actual paper exit to shadow runner",
                    ticker,
                )
        except OSError:
            logger.exception(
                "[%s] Could not persist actual paper exit for shadow comparison",
                ticker,
            )
        positions = getattr(self, "paper_shadow_positions", {})
        if str(trade["trade_id"]) in positions:
            positions[str(trade["trade_id"])].update(fields)

    def _on_tick(self, tick: Tick) -> None:
        """Monitor risk levels on every quote before aggregating the tick."""
        symbol = self.symbol_map.get(tick.instrument_token, f"TOKEN_{tick.instrument_token}")
        self.latest_prices[symbol] = tick.last_price
        self.option_quote_cache[symbol] = {
            "last_price": float(tick.last_price),
            "bid": float(getattr(tick, "bid", 0.0)),
            "ask": float(getattr(tick, "ask", 0.0)),
            "volume": int(tick.volume),
            "timestamp": tick.timestamp,
        }
        self._update_paper_shadow_runner(symbol, tick)
        position = self.intraday_manager.active_positions.get(symbol)
        if position and self._quote_validated_long_option(symbol, position):
            quote_metrics = self._option_quote_metrics(
                self.option_quote_cache[symbol]
            )
            if quote_metrics["valid"] and quote_metrics["ltp"] is not None:
                previous_low = self._positive_quote_value(
                    position.get("lowest_option_premium")
                )
                position["lowest_option_premium"] = min(
                    quote_metrics["ltp"],
                    previous_low if previous_low is not None else quote_metrics["ltp"],
                )
        if self.paper_trading_enabled and position:
            self.trade_journal.update_trade_mark(
                symbol, tick.last_price, str(position["direction"])
            )
        if tick.oi is not None:
            self.option_quote_cache[symbol]["oi"] = int(tick.oi)
        if tick.iv is not None:
            self.option_quote_cache[symbol]["iv"] = float(tick.iv)
        reentry_state = getattr(self, "_ema_reentry_states", {}).get(symbol)
        if reentry_state and reentry_state.get("status") in {
            "observing",
            "triggered",
        }:
            self._ema_reentry_premium_made_new_low(symbol, reentry_state)
        if self.intraday_manager.should_exit_all_positions():
            self._handle_market_close_exit()
        else:
            self._check_position_exit(symbol, tick.last_price)
        self._expire_pending_confirmed_entries(tick.timestamp)
        self._bar_callback_time = tick.timestamp
        try:
            self.bar_builder.process_tick(tick)
        finally:
            self._bar_callback_time = None

    def _extend_option_timebox(self, symbol: str, position: dict) -> bool:
        if not self.config.get("extend_option_timebox", False):
            return False

        extended_at = self.intraday_manager.extend_milestone_timebox(symbol)
        if extended_at is None:
            return False

        persisted = self.trade_journal.update_open_trade(
            symbol,
            {"milestone_started_at": extended_at.isoformat()},
            str(position["direction"]),
        )
        if not persisted:
            logger.error("[%s] Could not persist time-box extension", symbol)
        logger.info(
            "[%s] Time-box checkpoint extended by %d minutes",
            symbol,
            int(position.get("decision_window_minutes", 5)),
        )
        return True

    def _check_position_exit(self, symbol: str, price: float) -> Optional[str]:
        position = self.intraday_manager.active_positions.get(symbol)
        if not position:
            return None

        runner_state_before = None
        if self._is_option_dynamic_exit(position):
            runner_state_before = (
                position.get("highest_price"),
                position.get("lowest_price"),
                position.get("trailing_stop"),
                position.get("trailing_active"),
                position.get("adaptive_exit_mode"),
                position.get("max_favorable_r"),
            )
        previous_adaptive_mode = position.get("adaptive_exit_mode")
        trailing_enabled = (
            bool(position.get("trailing_enabled"))
            if position.get("trailing_enabled") is not None
            else self.intraday_manager.trailing_enabled
        )
        quote_validated_option = self._quote_validated_long_option(
            symbol, position
        )
        quote_metrics = None
        if quote_validated_option:
            quote_metrics = self._option_quote_metrics(
                getattr(self, "option_quote_cache", {}).get(symbol, {})
            )
            if not quote_metrics["valid"]:
                bid = quote_metrics["bid"]
                stop_loss = self._positive_quote_value(position.get("stop_loss"))
                trailing_level = self._positive_quote_value(
                    position.get("trailing_stop")
                )
                previous_stale_checks = int(
                    position.get("stale_stop_trigger_checks", 0)
                )
                stale_stop_trigger = (
                    not quote_metrics["fresh"]
                    and bid is not None
                    and (
                        (stop_loss is not None and bid <= stop_loss)
                        or (
                            trailing_level is not None
                            and bid <= trailing_level
                        )
                    )
                )
                if stale_stop_trigger or (
                    not quote_metrics["fresh"] and previous_stale_checks > 0
                ):
                    stale_checks = previous_stale_checks + 1
                    position["stale_stop_trigger_checks"] = stale_checks
                    if stale_checks >= 2:
                        last_valid_bid = self._positive_quote_value(
                            position.get("last_valid_bid")
                        )
                        if last_valid_bid is None:
                            logger.error(
                                "[%s] Repeated stale stop quote but no last valid "
                                "bid is available; position remains open",
                                symbol,
                            )
                            return None
                        self._close_position(
                            symbol, last_valid_bid, "feed_failure_exit"
                        )
                        return "feed_failure_exit"
                    logger.warning(
                        "[%s] Stop reached on stale quote; holding for one "
                        "subsequent quote check",
                        symbol,
                    )
                    return None
                position["stale_stop_trigger_checks"] = 0
                return None

            position["stale_stop_trigger_checks"] = 0
            position["last_valid_bid"] = quote_metrics["bid"]

        trailing_stop = self.intraday_manager.update_trailing_stop(symbol, price)
        if runner_state_before is not None:
            runner_state_after = (
                position.get("highest_price"),
                position.get("lowest_price"),
                position.get("trailing_stop"),
                position.get("trailing_active"),
                position.get("adaptive_exit_mode"),
                position.get("max_favorable_r"),
            )
            if (
                self._is_option_dynamic_exit(position)
                and position.get("adaptive_exit_mode") != previous_adaptive_mode
            ):
                logger.info(
                    "[%s] Paper adaptive exit changed to %s at %.2fR MFE; stop=%.2f",
                    symbol,
                    position["adaptive_exit_mode"],
                    position.get("max_favorable_r", 0.0),
                    position.get("trailing_stop")
                    if position.get("trailing_stop") is not None
                    else position["stop_loss"],
                )
            if (
                runner_state_before != runner_state_after
                or position.get("runner_persistence_pending")
            ):
                self._persist_paper_option_exit_state(symbol, position)
        if position.get("target_advanced"):
            if not self._publish_target_update(symbol, position, trailing_stop):
                self._close_position(symbol, price, "TRAILING_STOP_UPDATE_FAILED")
                return "TRAILING_STOP_UPDATE_FAILED"

        if position["direction"] == "BUY":
            stop_price = (
                quote_metrics["bid"]
                if quote_validated_option and quote_metrics is not None
                else price
            )
            if stop_price <= position["stop_loss"]:
                reason = "STOP_LOSS"
            elif trailing_stop is not None and stop_price <= trailing_stop:
                reason = "TRAILING_STOP"
            elif (
                not trailing_enabled
                and not position.get("staged_targets_enabled")
                and price >= position["take_profit"]
            ):
                reason = "TAKE_PROFIT"
            elif (
                not self._is_option_dynamic_exit(position)
                and position.get("exit_strategy") != "paper_range_breakout_2r"
                and self.intraday_manager.milestone_timebox_expired(symbol)
            ):
                if                 self._extend_option_timebox(symbol, position):
                    return "TIME_BOX_EXTENDED"
                reason = "TIME_BOX"
            else:
                return None
        else:
            if price >= position["stop_loss"]:
                reason = "STOP_LOSS"
            elif trailing_stop is not None and price >= trailing_stop:
                reason = "TRAILING_STOP"
            elif (
                not trailing_enabled
                and not position.get("staged_targets_enabled")
                and price <= position["take_profit"]
            ):
                reason = "TAKE_PROFIT"
            elif (
                not self._is_option_dynamic_exit(position)
                and position.get("exit_strategy") != "paper_range_breakout_2r"
                and self.intraday_manager.milestone_timebox_expired(symbol)
            ):
                if self._extend_option_timebox(symbol, position):
                    return "TIME_BOX_EXTENDED"
                reason = "TIME_BOX"
            else:
                return None

        exit_price = (
            quote_metrics["bid"]
            if quote_validated_option
            and quote_metrics is not None
            and quote_metrics["bid"] is not None
            else price
        )
        self._close_position(symbol, exit_price, reason)
        return reason

    def _persist_paper_option_exit_state(
        self, symbol: str, position: dict
    ) -> None:
        journal = getattr(self, "trade_journal", None)
        fields = {
            "runner_activation_r": position.get("runner_activation_r"),
            "runner_gap_r": position.get("runner_gap_r"),
            "adaptive_breakeven_r": position.get("adaptive_breakeven_r"),
            "adaptive_trail_activation_r": position.get("adaptive_trail_activation_r"),
            "adaptive_trail_gap_r": position.get("adaptive_trail_gap_r"),
            "adaptive_runner_activation_r": position.get("adaptive_runner_activation_r"),
            "adaptive_runner_gap_r": position.get("adaptive_runner_gap_r"),
            "adaptive_exit_mode": position.get("adaptive_exit_mode"),
            "max_favorable_r": position.get("max_favorable_r"),
            "highest_price": position["highest_price"],
            "lowest_price": position["lowest_price"],
            "trailing_stop": position["trailing_stop"],
            "trailing_active": position["trailing_active"],
            "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
        }
        persisted = bool(
            journal
            and journal.update_open_trade(
                symbol, fields, str(position["direction"])
            )
        )
        if not persisted:
            position["runner_persistence_pending"] = True
            logger.error(
                "[%s] Could not persist paper option exit state; retrying on next tick",
                symbol,
            )
            if not position.get("runner_persistence_alerted"):
                notifier = getattr(self, "telegram_notifier", None)
                if notifier:
                    notifier.send_message(
                        f"WARNING: {symbol} paper exit state could not be saved; "
                        "restart recovery may lose its trailing state."
                    )
                position["runner_persistence_alerted"] = True
            return

        position["runner_persistence_pending"] = False
        position["runner_persistence_alerted"] = False

    def _option_signal_exit_threshold(self, position: dict) -> Optional[float]:
        """Percent-based deterioration threshold for option signal-health exits."""
        try:
            entry_price = float(position.get("entry_price", 0.0))
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(entry_price) or entry_price <= 0:
            return None

        lockin_pct = float(position.get("weak_signal_lockin_pct", 0.05))
        if not math.isfinite(lockin_pct) or lockin_pct <= 0:
            lockin_pct = 0.05

        direction = str(position.get("direction", "")).upper()
        if direction == "BUY":
            return entry_price * (1.0 - lockin_pct)
        if direction == "SELL":
            return entry_price * (1.0 + lockin_pct)
        return None

    def _check_option_signal_health(
        self,
        symbol: str,
        signal: str,
        score: int,
        minimum_signal_score: int,
        price: float,
    ) -> Optional[str]:
        position = self.intraday_manager.active_positions.get(symbol)
        if not position or not position.get("staged_targets_enabled"):
            return None

        try:
            current_price = float(price)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(current_price):
            return None

        position["current_signal_score"] = int(score)
        expected_signal = "BUY" if symbol.endswith("_CE") else "SELL" if symbol.endswith("_PE") else None
        threshold = self._option_signal_exit_threshold(position)
        direction = str(position.get("direction", "")).upper()
        adverse_price_move = (
            current_price <= threshold
            if threshold is not None and direction == "BUY"
            else current_price >= threshold
            if threshold is not None and direction == "SELL"
            else False
        )

        reason = None
        weak_signal = int(score) < minimum_signal_score
        reversed_signal = (
            signal in {"BUY", "SELL"}
            and expected_signal is not None
            and signal != expected_signal
        )
        exit_condition = adverse_price_move and (weak_signal or reversed_signal)

        previous_checks = int(position.get("weak_signal_adverse_checks", 0) or 0)
        confirmation_checks = previous_checks + 1 if exit_condition else 0
        position["weak_signal_adverse_checks"] = confirmation_checks
        trade_journal = getattr(self, "trade_journal", None)
        if trade_journal is None:
            logger.error(
                "[%s] Cannot persist signal-exit confirmation state",
                symbol,
            )
        elif confirmation_checks != previous_checks:
            if not trade_journal.update_open_trade(
                symbol,
                {"weak_signal_adverse_checks": confirmation_checks},
                str(position["direction"]),
            ):
                logger.warning(
                    "[%s] Could not persist signal-exit confirmation state",
                    symbol,
                )
        if confirmation_checks >= SIGNAL_WEAKEN_CONFIRMATIONS:
            reason = "SIGNAL_WEAKEN"

        if reason:
            self._close_position(symbol, current_price, reason)
        return reason

    def _activate_daily_loss_shutdown(self) -> bool:
        """Block the rest of the session and cancel pending non-protective orders."""
        if not self.intraday_manager.daily_loss_limit_reached():
            return False

        today = datetime.now(IST).date()
        is_new_shutdown = getattr(self, "_daily_shutdown_date", None) != today
        if is_new_shutdown:
            self._daily_shutdown_date = today
            self._daily_shutdown_cancel_complete = False

        if getattr(self, "live_orders_enabled", False) and not getattr(
            self, "_daily_shutdown_cancel_complete", False
        ):
            protected_order_ids = {
                str(position["protection_order_id"])
                for position in self.intraday_manager.active_positions.values()
                if position.get("protection_order_id")
            }
            try:
                cancelled = self.kite_stream.cancel_pending_non_protective_orders(
                    protected_order_ids
                )
                self._daily_shutdown_cancel_complete = True
            except Exception:
                logger.exception(
                    "Daily loss limit reached; pending-order cancellation failed"
                )
                self.telegram_notifier.send_message(
                    "URGENT: daily loss limit reached; entries are disabled, but "
                    "pending-order cancellation failed. Verify Kite orders manually."
                )
                return True
        else:
            cancelled = []
            self._daily_shutdown_cancel_complete = True

        if is_new_shutdown:
            message = (
                "Daily realized-loss limit reached: "
                f"₹{self.intraday_manager.daily_realized_losses:.2f} / "
                f"₹{self.intraday_manager.daily_max_loss:.2f}. "
                "New entries are disabled until the next session."
            )
            if getattr(self, "live_orders_enabled", False):
                message += (
                    f" Cancelled {len(cancelled)} pending non-protective order(s); "
                    "active protective stops remain in place."
                )
            logger.warning(message)
            self.telegram_notifier.send_message(message)
        return True

    def _live_entry_allowed(self, symbol: str) -> bool:
        if not getattr(self, "live_orders_enabled", False):
            return True
        if self.intraday_manager.daily_loss_limit_reached():
            self._activate_daily_loss_shutdown()
            logger.warning(
                "[%s] Entry blocked by the daily realized-loss shutdown", symbol
            )
            return False
        if getattr(self, "_daily_shutdown_date", None) == datetime.now(IST).date():
            logger.warning("[%s] Entry blocked until the next trading session", symbol)
            return False
        if getattr(self, "_entries_paused", False) or not getattr(self, "_risk_state_reconciled", False):
            logger.warning("[%s] Live entry blocked until broker state is safe", symbol)
            return False
        if not getattr(self.kite_stream, "is_connected", False):
            logger.warning("[%s] Live entry blocked while Kite is disconnected", symbol)
            return False
        return True

    def _place_protective_stop(self, symbol: str, position: dict) -> bool:
        if self._quote_validated_long_option(symbol, position):
            position["quote_validated_stop_monitoring"] = True
            logger.info(
                "[%s] Using quote-validated synthetic stop monitoring; "
                "native LTP-triggered stop is disabled",
                symbol,
            )
            return True
        try:
            order_id = self.kite_stream.place_protective_stop_order(
                symbol,
                position["direction"],
                int(position["quantity"]),
                float(position["stop_loss"]),
            )
            position["protection_order_id"] = order_id
            self.trade_journal.update_open_trade(
                symbol,
                {"protection_order_id": order_id},
                position["direction"],
            )
            return True
        except Exception as exc:
            logger.exception("[%s] Protective stop could not be placed", symbol)
            self.telegram_notifier.send_message(
                f"URGENT: protective stop failed for {symbol}; emergency exit required.\n{exc}"
            )
            return False

    def _abort_live_entry(self, symbol: str, price: float, reason: str) -> None:
        self._entries_paused = True
        self._risk_state_reconciled = False
        position = self.intraday_manager.active_positions.get(symbol)
        if position and not self.trade_journal.get_open_trade(
            symbol, position["direction"]
        ):
            try:
                self.trade_journal.log_trade({
                    "ticker": symbol,
                    "contract_id": self._contract_id(symbol),
                    "action": position["direction"],
                    "entry": position["entry_price"],
                    "stop_loss": position["stop_loss"],
                    "take_profit": position["take_profit"],
                    "quantity": position["quantity"],
                    "score": position.get("signal_score"),
                    "protection_order_id": position.get("protection_order_id"),
                    "status": "open",
                })
            except Exception:
                logger.exception("[%s] Could not journal an aborted live entry", symbol)
        self._close_position(symbol, price, reason)
        self._reconcile_after_order_failure(symbol)

    def _publish_target_update(
        self, symbol: str, position: dict, trailing_stop: Optional[float]
    ) -> bool:
        """Persist and announce each staged target advance once."""
        action = position["direction"]
        if (
            getattr(self, "live_orders_enabled", False)
            and not self._quote_validated_long_option(symbol, position)
        ):
            protection_order_id = position.get("protection_order_id")
            if not protection_order_id or trailing_stop is None:
                logger.error("[%s] Cannot ratchet a missing protective stop", symbol)
                self.telegram_notifier.send_message(
                    f"URGENT: {symbol} reached a profit milestone but has no modifiable protective stop."
                )
                return False
            try:
                self.kite_stream.modify_protective_stop_order(
                    symbol,
                    action,
                    str(protection_order_id),
                    float(trailing_stop),
                )
            except Exception:
                logger.exception("[%s] Could not move broker protective stop", symbol)
                self.telegram_notifier.send_message(
                    f"URGENT: failed to move {symbol} protective stop after a milestone; "
                    "attempting an immediate market exit."
                )
                return False

        fields = {
            "take_profit": position["take_profit"],
            "target_stage": position["target_stage"],
            "milestone_reached_pct": position["milestone_reached_pct"],
            "milestone_started_at": position["milestone_started_at"].isoformat(),
            "trailing_stop": trailing_stop,
            "current_signal_score": position.get("current_signal_score"),
            "decision_window_minutes": position["decision_window_minutes"],
            "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
        }
        self.trade_journal.update_open_trade(symbol, fields, action)
        trailing_text = f"{trailing_stop:.2f}" if trailing_stop is not None else "not active"
        self.telegram_notifier.send_message(
            f"Target advanced: {action} {symbol}\n"
            f"Stage: {position['target_stage']}\n"
            f"Next target: {position['take_profit']:.2f}\n"
            f"Trailing stop: {trailing_text}"
        )
        return True

    def _close_position(self, symbol: str, price: float, reason: str) -> None:
        position = self.intraday_manager.active_positions.get(symbol)
        action = position["direction"] if position else None
        if self.live_orders_enabled and position:
            exit_side = "SELL" if action == "BUY" else "BUY"
            protection_order_id = position.get("protection_order_id")
            protection_cancelled = not protection_order_id
            if protection_order_id:
                try:
                    self.kite_stream.cancel_order(protection_order_id)
                    protection_cancelled = True
                except Exception:
                    logger.warning("[%s] Protective stop %s was already active or unavailable", symbol, protection_order_id)
            remaining = abs(int(position["quantity"]))
            max_attempts = int(self.config.get("max_exit_retries", 3))
            for attempt in range(1, max_attempts + 1):
                try:
                    exit_order_id = self.kite_stream.place_market_order(symbol, exit_side, remaining)
                    fill = self.kite_stream.wait_for_order_fill(exit_order_id, remaining)
                    price = float(fill["average_price"])
                    broker_remaining = abs(self.kite_stream.get_position_quantity(symbol))
                    if broker_remaining == 0:
                        break
                    remaining = broker_remaining
                    logger.warning("[%s] Exit attempt %d left %d units; retrying", symbol, attempt, remaining)
                except Exception:
                    logger.exception("[%s] Live exit attempt %d failed", symbol, attempt)
                    try:
                        remaining = abs(self.kite_stream.get_position_quantity(symbol))
                    except Exception:
                        logger.exception("[%s] Could not verify broker quantity after exit failure", symbol)
                        remaining = -1
                    if remaining == 0:
                        break
                if remaining <= 0:
                    break
            if remaining != 0:
                protection_restored = False
                if remaining > 0 and protection_cancelled:
                    position["quantity"] = remaining
                    protection_restored = self._place_protective_stop(symbol, position)
                    protection_restored = (
                        protection_restored
                        and bool(position.get("protection_order_id"))
                    )
                self._entries_paused = True
                self._risk_state_reconciled = False
                if protection_restored:
                    protection_state = "broker protective stop was restored"
                elif self._quote_validated_long_option(symbol, position):
                    protection_state = (
                        "no broker-side stop is active; quote monitoring requires "
                        "a live feed and manual protection is required during outages"
                    )
                else:
                    protection_state = (
                        "protective stop status is uncertain; manual protection "
                        "is required"
                    )
                self.telegram_notifier.send_message(
                    f"URGENT: {symbol} is not flat after {max_attempts} exit attempts; "
                    f"{protection_state}. New entries are paused."
                )
                logger.error("[%s] Broker position remains open after exit retries", symbol)
                if protection_restored:
                    self._reconcile_after_order_failure(symbol)
                return
        trade = self.trade_journal.get_open_trade(symbol, action)
        quote = getattr(self, "option_quote_cache", {}).get(symbol, {})
        quote_metrics = self._option_quote_metrics(quote)
        if (
            reason != "feed_failure_exit"
            and getattr(self, "config", {}).get(
                "option_quote_validated_stops_enabled", False
            )
            and symbol.endswith(("_CE", "_PE"))
            and quote_metrics["valid"]
            and quote_metrics["bid"] is not None
        ):
            price = quote_metrics["bid"]
        logger.info(
            "[%s] Exit quote bid=%s ask=%s LTP=%s timestamp=%s reason=%s",
            symbol,
            quote_metrics["bid"],
            quote_metrics["ask"],
            quote_metrics["ltp"],
            (
                quote_metrics["timestamp"].isoformat()
                if quote_metrics["timestamp"] is not None
                else None
            ),
            reason,
        )
        if getattr(self, "paper_trading_enabled", False) and not getattr(
            self, "live_orders_enabled", False
        ):
            self._record_paper_shadow_actual_exit(trade, price, reason)
        closed_at = datetime.now(IST)
        journal_pnl = self.trade_journal.close_trade(
            symbol,
            price,
            action,
            reason,
            closed_at=closed_at.isoformat(),
        )
        exit_info = self.intraday_manager.close_position(symbol, price, reason)
        if not trade and not exit_info:
            return

        pnl = exit_info["pnl_rupees"] if exit_info else journal_pnl
        if exit_info is not None or trade is not None:
            if pnl is None:
                raise RuntimeError(
                    f"Closed trade {symbol} has no realized P&L for daily risk tracking"
                )
            self.intraday_manager.record_trade_close(symbol, reason, float(pnl))
            self._activate_daily_loss_shutdown()
        if exit_info:
            is_ema_reentry = bool((trade or {}).get("is_ema_reentry"))
            ema_reentry_eligible = (
                self._ema_reentry_enabled()
                and reason == "STOP_LOSS"
                and pnl < 0
                and not is_ema_reentry
                and bool((trade or {}).get("trade_id"))
            )
            exit_annotation = {
                "pnl": exit_info["pnl_rupees"],
                "pnl_points": exit_info["pnl_points"],
                "pnl_rupees": exit_info["pnl_rupees"],
                "duration_seconds": exit_info["duration"],
                "holding_time_seconds": exit_info["duration"],
                "quantity": exit_info["quantity"],
                "target_stage": position.get("target_stage", 0) if position else 0,
                "milestone_reached_pct": (
                    position.get("milestone_reached_pct", 0.0) if position else 0.0
                ),
                "exit_reason_category": self._exit_reason_category(reason),
                "exit_strategy": (
                    "tiered_milestone"
                    if position and position.get("staged_targets_enabled")
                    else (
                        (trade or {}).get("exit_strategy")
                        or (
                            "fixed_20pct"
                            if self._options_enabled() and "_" in symbol
                            else None
                        )
                    )
                ),
                "score": position.get("signal_score") if position else None,
                "current_signal_score": (
                    position.get("current_signal_score") if position else None
                ),
                "weak_signal_adverse_checks": (
                    position.get("weak_signal_adverse_checks", 0)
                    if position
                    else 0
                ),
                "paper_exit_ltp": (
                    quote_metrics["ltp"]
                    if quote_metrics["ltp"] is not None
                    else float(price)
                ),
                "exit_quote_ltp": quote_metrics["ltp"],
                "exit_quote_bid": quote_metrics["bid"],
                "exit_quote_ask": quote_metrics["ask"],
                "exit_quote_timestamp": (
                    quote_metrics["timestamp"].isoformat()
                    if quote_metrics["timestamp"] is not None
                    else None
                ),
                "paper_exit_fill_source": (
                    "best_bid"
                    if quote_metrics["valid"]
                    else (
                        "last_valid_bid"
                        if reason == "feed_failure_exit"
                        else "existing_exit_reference"
                    )
                ),
                "paper_exit_bid": self._positive_quote_value(
                    quote.get("bid")
                ),
                "paper_exit_ask": self._positive_quote_value(
                    quote.get("ask")
                ),
                "paper_exit_quote_timestamp": (
                    str(quote["timestamp"])
                    if quote.get("timestamp") is not None
                    else None
                ),
            }
            if is_ema_reentry:
                reentry_outcome = (
                    "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"
                )
                exit_annotation.update(
                    {
                        "reentry_exit_price": float(price),
                        "reentry_pnl": float(pnl),
                        "reentry_outcome": reentry_outcome,
                    }
                )
            if ema_reentry_eligible:
                stop_out_low = self._positive_quote_value(
                    position.get("lowest_option_premium")
                    if position
                    else None
                )
                exit_annotation.update(
                    {
                        "ema_reentry_eligible": True,
                        "ema_reentry_stop_time": closed_at.isoformat(),
                        "ema_reentry_stop_out_low": stop_out_low,
                        "ema_reentry_outcome": "PENDING",
                    }
                )
            self.trade_journal.annotate_trade(
                symbol,
                exit_annotation,
                action,
            )
            if ema_reentry_eligible:
                state = {
                    "original_trade_id": str(trade["trade_id"]),
                    "stop_time": closed_at,
                    "stop_out_low": stop_out_low,
                    "status": "observing",
                }
                self._ema_reentry_states[symbol] = state
                self._log_ema_reentry_event(
                    symbol,
                    state,
                    "OBSERVATION_STARTED",
                    current_time=closed_at,
                    outcome="observing",
                )
            elif is_ema_reentry:
                state = getattr(self, "_ema_reentry_states", {}).get(
                    symbol,
                    {
                        "original_trade_id": (trade or {}).get(
                            "original_trade_id"
                        ),
                        "stop_time": (trade or {}).get(
                            "ema_reentry_stop_time"
                        ),
                    },
                )
                state["status"] = "completed"
                state["outcome"] = (
                    "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"
                )
                self._log_ema_reentry_event(
                    symbol,
                    state,
                    "TRADE_CLOSED",
                    current_time=closed_at,
                    signal={
                        "signal": "BUY",
                        "signal_time": (trade or {}).get("reentry_signal_time"),
                        "reentry_reason": (trade or {}).get("reentry_reason"),
                        "vwap": (trade or {}).get("reentry_vwap"),
                        "entry_price": (trade or {}).get("entry"),
                        "exit_price": float(price),
                        "pnl": float(pnl),
                        "reentry_outcome": state["outcome"],
                    },
                    outcome=state["outcome"].lower(),
                )
        self._persist_current_live_risk_state()
        mode = "intraday_options" if self._options_enabled() else "futures"
        option_leg = "CE" if symbol.endswith("_CE") else "PE" if symbol.endswith("_PE") else None
        trading_symbol = self.kite_stream.contract_symbols.get(symbol, symbol)
        close_alert = self.telegram_notifier.format_close(
            ticker=symbol,
            action=action or (trade or {}).get("action", "UNKNOWN"),
            exit_price=price,
            pnl=pnl,
            reason=reason,
            mode=mode,
            option_leg=option_leg,
            trading_symbol=trading_symbol,
        )
        logger.info(self.telegram_notifier.build_message(close_alert))
        self.telegram_notifier.send_trade_alert(close_alert)

    @staticmethod
    def _exit_reason_category(reason: str) -> str:
        if reason in {"STOP_LOSS", "TRAILING_STOP"}:
            return "SL"
        if reason == "MARKET_CLOSE_FORCED_EXIT":
            return "EOD"
        if reason in {"TIME_BOX", "SIGNAL_WEAKEN"}:
            return reason
        return reason

    def _record_decision(
        self,
        symbol: str,
        bar: Bar,
        bars: list,
        market_score,
        signal: str,
        outcome: str,
        news_context=None,
        strategy_variant: Optional[str] = None,
        ema_reentry_context: Optional[dict] = None,
    ) -> None:
        reasons = list(market_score.reasons) if market_score else []
        if not reasons:
            reasons = [outcome]
        entry_evaluations = getattr(self, "_pending_entry_evaluations", {})
        entry_evaluation = entry_evaluations.pop(symbol, None)
        self.decision_journal.log_decision(
            {
                "event": "bar_decision",
                "bar": bar.to_dict(),
                "ticker": symbol,
                "contract_id": self._contract_id(symbol),
                "signal": signal,
                "outcome": outcome,
                "bars_available": len(bars),
                "history": [item.to_dict() for item in bars],
                "score": market_score.score if market_score else None,
                "reasons": reasons,
                "strategy_variant": (
                    strategy_variant
                    or getattr(market_score, "strategy_variant", None)
                    or "primary"
                ),
                "news_risk": news_context.risk_level if news_context else "DISABLED",
                "news_sentiment": news_context.sentiment if news_context else "DISABLED",
                "news_headlines": news_context.headlines[:5] if news_context else [],
                "entry_evaluation": entry_evaluation,
                "original_trade_id": (
                    ema_reentry_context.get("original_trade_id")
                    if ema_reentry_context
                    else None
                ),
                "stop_time": (
                    ema_reentry_context.get("stop_time")
                    if ema_reentry_context
                    else None
                ),
                "reentry_signal_time": (
                    ema_reentry_context.get("signal_time")
                    if ema_reentry_context
                    else None
                ),
                "reentry_reason": (
                    ema_reentry_context.get("reentry_reason")
                    if ema_reentry_context
                    else None
                ),
                "reentry_vwap": (
                    ema_reentry_context.get("vwap")
                    if ema_reentry_context
                    else None
                ),
                "ema_reentry_event": (
                    "ENTRY_DECISION" if ema_reentry_context else None
                ),
                "route": (
                    "ema_reentry" if ema_reentry_context else None
                ),
            }
        )

    def _handle_buy_signal(
        self,
        symbol: str,
        price: float,
        score: int,
        strategy_variant: Optional[str] = None,
        minimum_signal_score: Optional[int] = None,
        paper_range_stop: Optional[float] = None,
        paper_range_target_r: Optional[float] = None,
        ema_reentry_context: Optional[dict] = None,
        confirmed_entry_metadata: Optional[dict] = None,
        force_ask_fill: bool = False,
    ) -> str:
        """Handle a BUY signal."""
        entry_quote = getattr(self, "option_quote_cache", {}).get(symbol, {})
        entry_quote_metrics = self._option_quote_metrics(entry_quote)
        entry_fill_source = "last_price"
        open_trade = self.trade_journal.get_open_trade(symbol, "BUY")
        opposite_trade = self.trade_journal.get_open_trade(symbol, "SELL")
        if opposite_trade or (
            symbol in self.intraday_manager.active_positions
            and self.intraday_manager.active_positions[symbol]["direction"] == "SELL"
        ):
            opposite_position = self.intraday_manager.active_positions.get(symbol)
            if self._is_option_dynamic_exit(opposite_position):
                return "runner_position_active"
            self._close_position(symbol, price, "SIGNAL_REVERSAL")
            if (
                symbol in self.intraday_manager.active_positions
                or self.trade_journal.get_open_trade(symbol, "SELL")
            ):
                return "reversal_close_failed"
        if open_trade is None:
            cutoff_reason = self._entry_cutoff_reason()
            if cutoff_reason:
                logger.info("[%s] Entry rejected: %s", symbol, cutoff_reason)
                return cutoff_reason
            if not self._live_entry_allowed(symbol):
                return "live_entry_paused"
            allowed, reason = self._can_open_trade_for_signal(
                symbol,
                "BUY",
                score,
                ema_reentry_confirmed=ema_reentry_context is not None,
            )
            if not allowed:
                logger.info("[%s] Trade blocked: %s", symbol, reason)
                return f"trade_blocked:{reason}"
            if (
                symbol in self.intraday_manager.session_trade_symbols
                and strategy_variant != "paper_ema_stop_reentry"
            ):
                strategy_variant = (
                    "paper_underlying_support_reversal_stop_reentry"
                    if strategy_variant == "paper_underlying_support_reversal"
                    else "paper_stop_reentry"
                )
            range_breakout_plan = (
                paper_range_stop is not None or paper_range_target_r is not None
            )
            if range_breakout_plan and (
                paper_range_stop is None
                or paper_range_target_r is None
                or not self._options_enabled()
                or "_" not in symbol
            ):
                raise ValueError("Range-breakout exit plans require option contracts")
            option_adaptive_exit = (
                not range_breakout_plan
                and self._option_adaptive_exit_enabled(symbol)
            )
            adaptive_exit_values = None
            if option_adaptive_exit:
                try:
                    adaptive_exit_values = (
                        self._option_adaptive_exit_r_values()
                    )
                except (TypeError, ValueError, OverflowError):
                    logger.exception("[%s] Invalid adaptive-exit settings", symbol)
                    return "invalid_option_adaptive_exit_config"
            staged_option_targets = (
                False
                if range_breakout_plan or option_adaptive_exit
                else self._staged_option_targets_enabled(symbol)
            )
            if self._options_enabled() and "_" in symbol:
                premium_stop_pct = float(self.config.get("option_premium_stop_pct", 0.20))
                premium_target_pct = self._option_entry_target_pct(
                    staged_option_targets
                )
                premium = float(self.latest_prices.get(symbol, price))
                if force_ask_fill and (
                    not entry_quote_metrics["valid"]
                    or entry_quote_metrics["ask"] is None
                ):
                    return "stale_quote"
                if (
                    force_ask_fill
                    or self.config.get("option_quote_validated_stops_enabled", False)
                ):
                    if (
                        entry_quote_metrics["valid"]
                        and entry_quote_metrics["ask"] is not None
                    ):
                        price = entry_quote_metrics["ask"]
                        entry_fill_source = "best_ask"
                    else:
                        logger.warning(
                            "[%s] Entry quote is not fresh and inside its spread; "
                            "using the existing LTP entry reference",
                            symbol,
                        )
                else:
                    price = premium
                if force_ask_fill and entry_quote_metrics["ltp"] is not None:
                    premium = entry_quote_metrics["ltp"]
                if range_breakout_plan:
                    stop_loss = float(paper_range_stop)
                    if (
                        not math.isfinite(price)
                        or price <= 0
                        or not math.isfinite(premium)
                        or premium <= 0
                    ):
                        return "invalid_risk"
                    risk_per_unit = price - stop_loss
                    sizing_risk_per_unit = premium - stop_loss
                    if (
                        not math.isfinite(stop_loss)
                        or not math.isfinite(paper_range_target_r)
                        or stop_loss <= 0
                        or risk_per_unit <= 0
                        or sizing_risk_per_unit <= 0
                        or paper_range_target_r <= 0
                    ):
                        return "invalid_risk"
                    premium_stop_pct = sizing_risk_per_unit / premium
                    if adaptive_exit_values is not None:
                        take_profit = (
                            price + risk_per_unit * adaptive_exit_values[3]
                        )
                    else:
                        take_profit = price + risk_per_unit * paper_range_target_r
                else:
                    stop_loss = max(price * (1.0 - premium_stop_pct), 0.01)
                    risk_per_unit = price - stop_loss
                    if adaptive_exit_values is not None:
                        take_profit = (
                            price + risk_per_unit * adaptive_exit_values[3]
                        )
                    else:
                        take_profit = price * (1.0 + premium_target_pct)
                quantity = self._calculate_option_quantity(
                    symbol, premium, premium_stop_pct
                )
            else:
                risk_plan = build_risk_plan(
                    price,
                    "BUY",
                    stop_loss_pct=self.config.get("stop_loss_pct", 0.75),
                    take_profit_pct=self.config.get("take_profit_pct", 1.5),
                )
                stop_loss = risk_plan.stop_loss
                take_profit = risk_plan.take_profit
                quantity = self._calculate_position_size(
                    symbol,
                    price,
                    stop_loss,
                )

            if quantity == 0:
                logger.warning(f"[{symbol}] Cannot calculate position size, skipping trade")
                evaluation = getattr(self, "_pending_entry_evaluations", {}).get(
                    symbol, {}
                )
                if evaluation.get("rejection_reason") == "one_lot_exceeds_trade_risk_cap":
                    cap = float(evaluation["risk_cap_rupees"])
                    return (
                        "risk_cap_blocked:"
                        f"one_lot_exceeds_{cap:g}_rupees"
                    )
                if evaluation.get("rejection_reason") == (
                    "stop_risk_exceeds_deployed_capital_limit"
                ):
                    return "risk_blocked:stop_risk_exceeds_deployed_capital_limit"
                return "position_size_zero"

            order_id = None
            if self.live_orders_enabled:
                try:
                    order_id = self.kite_stream.place_market_order(
                        symbol, "BUY", quantity
                    )
                    fill = self.kite_stream.wait_for_order_fill(order_id, quantity)
                    quantity = int(fill["filled_quantity"])
                    price = float(fill["average_price"])
                    entry_fill_source = "broker_fill"
                    if self._options_enabled() and "_" in symbol:
                        stop_loss = max(price * (1.0 - premium_stop_pct), 0.01)
                        take_profit = price * (1.0 + premium_target_pct)
                    else:
                        risk_plan = build_risk_plan(
                            price,
                            "BUY",
                            stop_loss_pct=self.config.get("stop_loss_pct", 0.75),
                            take_profit_pct=self.config.get("take_profit_pct", 1.5),
                        )
                        stop_loss = risk_plan.stop_loss
                        take_profit = risk_plan.take_profit
                except Exception:
                    logger.exception("[%s] Live BUY order was not filled", symbol)
                    self._reconcile_after_order_failure(symbol)
                    return "live_order_failed"

            # Register position in intraday manager
            self.intraday_manager.register_position(
                symbol,
                "BUY",
                quantity,
                price,
                stop_loss,
                take_profit,
                signal_score=score,
                staged_targets_enabled=staged_option_targets,
                target_increment_pct=self._option_target_increment(),
                minimum_signal_score=(
                    minimum_signal_score
                    if minimum_signal_score is not None
                    else self._entry_score_floor()
                ),
                strong_signal_score=int(self.config.get("strong_signal_score", 82)),
                weak_signal_lockin_pct=float(
                    self.config.get("option_weak_signal_lockin_pct", 0.05)
                ),
                trailing_enabled=(
                    True if option_adaptive_exit
                    else False if range_breakout_plan
                    else None
                ),
                exit_strategy=(
                    PAPER_OPTION_ADAPTIVE_EXIT if option_adaptive_exit
                    else "paper_range_breakout_2r" if range_breakout_plan
                    else None
                ),
                adaptive_breakeven_r=(
                    adaptive_exit_values[0] if adaptive_exit_values else None
                ),
                adaptive_trail_activation_r=(
                    adaptive_exit_values[1] if adaptive_exit_values else None
                ),
                adaptive_trail_gap_r=(
                    adaptive_exit_values[2] if adaptive_exit_values else None
                ),
                adaptive_runner_activation_r=(
                    adaptive_exit_values[3] if adaptive_exit_values else None
                ),
                adaptive_runner_gap_r=(
                    adaptive_exit_values[4] if adaptive_exit_values else None
                ),
                milestone_window_minutes=int(
                    self.config.get("option_milestone_window_minutes", 5)
                ),
                strong_milestone_window_minutes=int(
                    self.config.get("strong_option_milestone_window_minutes", 10)
                ),
            )
            if self._quote_validated_long_option(
                symbol, self.intraday_manager.active_positions[symbol]
            ):
                position = self.intraday_manager.active_positions[symbol]
                position["lowest_option_premium"] = float(
                    entry_quote_metrics["ltp"]
                    if entry_quote_metrics["ltp"] is not None
                    else price
                )
                if entry_quote_metrics["valid"]:
                    position["last_valid_bid"] = entry_quote_metrics["bid"]
            self.intraday_manager.record_trade_open(symbol, "BUY")
            if self.live_orders_enabled and not self._place_protective_stop(
                symbol, self.intraday_manager.active_positions[symbol]
            ):
                self._abort_live_entry(symbol, price, "PROTECTION_FAILED")
                return "protective_stop_failed"
            if (
                self.live_orders_enabled
                and self._options_enabled()
                and "_" in symbol
                and not self._option_quantity_within_lot_bounds(symbol, quantity)
            ):
                self._abort_live_entry(symbol, price, "OPTION_FILL_OUTSIDE_LOT_BOUNDS")
                return "option_fill_outside_lot_bounds"
            if (
                self.live_orders_enabled
                and self.intraday_manager.estimate_trade_risk(
                    symbol, quantity, price, stop_loss
                ) > self._entry_risk_limit(symbol, price) + 1e-6
            ):
                self._abort_live_entry(symbol, price, "RISK_LIMIT_EXCEEDED")
                return "risk_blocked:filled_risk_exceeds_limit"
            if (
                self.live_orders_enabled
                and self.intraday_manager.daily_risk_exceeded()
            ):
                self._abort_live_entry(
                    symbol, price, "AGGREGATE_RISK_LIMIT_EXCEEDED"
                )
                return "risk_blocked:filled_risk_exceeds_aggregate_limit"

            mode = "intraday_options" if self._options_enabled() else "futures"
            option_leg = "CE" if symbol.endswith("_CE") else "PE" if symbol.endswith("_PE") else None
            trading_symbol = self.kite_stream.contract_symbols.get(symbol, symbol)
            alert = self.telegram_notifier.format_trade(
                ticker=symbol,
                action="BUY",
                score=score,
                entry=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                mode=mode,
                option_leg=option_leg,
                trading_symbol=trading_symbol,
                trailing_enabled=(
                    True
                    if option_adaptive_exit
                    else False
                    if range_breakout_plan
                    else self.intraday_manager.trailing_enabled
                ),
            )
            alert["pnl"] = 0.0
            alert["status"] = "open"
            alert["stop_loss"] = stop_loss
            alert["take_profit"] = take_profit
            alert["quantity"] = quantity
            alert["strategy_variant"] = strategy_variant or "primary"
            if ema_reentry_context is not None:
                alert.update(
                    {
                        "is_ema_reentry": True,
                        "route": "ema_reentry",
                        "original_trade_id": ema_reentry_context[
                            "original_trade_id"
                        ],
                        "ema_reentry_stop_time": ema_reentry_context["stop_time"],
                        "reentry_signal_time": ema_reentry_context[
                            "signal_time"
                        ],
                        "reentry_reason": ema_reentry_context[
                            "reentry_reason"
                        ],
                        "reentry_vwap": ema_reentry_context.get("vwap"),
                        "reentry_entry_price": float(price),
                    }
                )
            if getattr(self, "paper_trading_enabled", False):
                quote = entry_quote
                alert["timestamp"] = datetime.now(IST).isoformat()
                alert["trade_id"] = (
                    f"{symbol}-{alert['timestamp']}-BUY"
                )
                alert["paper_entry_ltp"] = (
                    entry_quote_metrics["ltp"]
                    if entry_quote_metrics["ltp"] is not None
                    else float(price)
                )
                alert["paper_entry_bid"] = self._positive_quote_value(
                    quote.get("bid")
                )
                alert["paper_entry_ask"] = self._positive_quote_value(
                    quote.get("ask")
                )
                alert["paper_entry_quote_is_fresh"] = bool(
                    entry_quote_metrics["fresh"]
                )
                alert["paper_entry_risk_rupees"] = (
                    self.intraday_manager.estimate_trade_risk(
                        symbol, quantity, price, stop_loss
                    )
                )
                alert["risk_cap_rupees"] = self._entry_risk_cap()
            alert["entry_quote_ltp"] = entry_quote_metrics["ltp"]
            alert["entry_quote_bid"] = entry_quote_metrics["bid"]
            alert["entry_quote_ask"] = entry_quote_metrics["ask"]
            alert["entry_quote_timestamp"] = (
                entry_quote_metrics["timestamp"].isoformat()
                if entry_quote_metrics["timestamp"] is not None
                else None
            )
            alert["entry_fill_source"] = entry_fill_source
            if staged_option_targets:
                position = self.intraday_manager.active_positions[symbol]
                alert.update(
                    {
                        "exit_strategy": "tiered_milestone",
                        "option_milestone_pct": position["target_increment_pct"],
                        "target_stage": position["target_stage"],
                        "milestone_reached_pct": position["milestone_reached_pct"],
                        "milestone_started_at": position["milestone_started_at"].isoformat(),
                        "entry_time": position["entry_time"].isoformat(),
                        "minimum_signal_score": position["minimum_signal_score"],
                        "decision_window_minutes": position["decision_window_minutes"],
                        "current_signal_score": position["current_signal_score"],
                    }
                )
            elif self._options_enabled() and "_" in symbol:
                if option_adaptive_exit:
                    alert["exit_strategy"] = PAPER_OPTION_ADAPTIVE_EXIT
                    alert["trailing_enabled"] = True
                elif range_breakout_plan:
                    alert["exit_strategy"] = "paper_range_breakout_2r"
                    alert["trailing_enabled"] = False
                else:
                    alert["exit_strategy"] = "fixed_20pct"
            if order_id:
                alert["order_id"] = order_id
            protection_order_id = self.intraday_manager.active_positions[symbol].get(
                "protection_order_id"
            )
            if protection_order_id:
                alert["protection_order_id"] = protection_order_id

            if option_adaptive_exit:
                position = self.intraday_manager.active_positions[symbol]
                alert.update(
                    {
                        "adaptive_breakeven_r": position["adaptive_breakeven_r"],
                        "adaptive_trail_activation_r": position["adaptive_trail_activation_r"],
                        "adaptive_trail_gap_r": position["adaptive_trail_gap_r"],
                        "adaptive_runner_activation_r": position["adaptive_runner_activation_r"],
                        "adaptive_runner_gap_r": position["adaptive_runner_gap_r"],
                        "adaptive_exit_mode": position["adaptive_exit_mode"],
                        "max_favorable_r": position["max_favorable_r"],
                        "highest_price": position["highest_price"],
                        "lowest_price": position["lowest_price"],
                        "trailing_active": position["trailing_active"],
                        "trailing_stop": position["trailing_stop"],
                    }
                )
            alert["contract_id"] = self._contract_id(symbol)
            alert["entry_mode"] = (
                "confirmed"
                if confirmed_entry_metadata is not None
                else "ema_reentry"
                if ema_reentry_context is not None
                else "immediate"
                if strategy_variant == "option_range_breakout"
                else getattr(self, "entry_mode", "immediate")
            )
            alert["route"] = (
                "ema_reentry"
                if ema_reentry_context is not None
                else "option_range_breakout"
                if strategy_variant == "option_range_breakout"
                else "support_reversal"
                if strategy_variant == "paper_underlying_support_reversal"
                else "scored"
            )
            if confirmed_entry_metadata is not None:
                alert.update(confirmed_entry_metadata)
            self.trade_journal.log_trade(alert)
            logger.info(
                "[%s] Entry quote bid=%s ask=%s LTP=%s timestamp=%s fill=%s",
                symbol,
                entry_quote_metrics["bid"],
                entry_quote_metrics["ask"],
                entry_quote_metrics["ltp"],
                alert["entry_quote_timestamp"],
                entry_fill_source,
            )
            if option_adaptive_exit:
                self._start_paper_shadow_runner(
                    symbol,
                    str(alert["trade_id"]),
                    price,
                    stop_loss,
                    quantity,
                    str(alert["timestamp"]),
                )
            self._persist_current_live_risk_state()
            target_label = "adaptive_exit_ref" if option_adaptive_exit else "TP"
            logger.info(
                f"[{symbol}] BUY ALERT -> {quantity} qty @ {alert['entry']:.2f}, "
                f"SL={alert['stop_loss']:.2f}, "
                f"{target_label}={alert['take_profit']:.2f}"
            )
            logger.info(self.telegram_notifier.build_message(alert))
            self.telegram_notifier.send_trade_alert(alert)
            return "trade_opened"
        else:
            logger.info(f"[{symbol}] BUY OPEN -> current={price:.2f}")
            return "position_updated"

    def _handle_sell_signal(
        self,
        symbol: str,
        price: float,
        score: int,
        strategy_variant: Optional[str] = None,
        minimum_signal_score: Optional[int] = None,
    ) -> str:
        """Handle a SELL signal."""
        open_trade = self.trade_journal.get_open_trade(symbol, "SELL")
        opposite_trade = self.trade_journal.get_open_trade(symbol, "BUY")
        if opposite_trade or (
            symbol in self.intraday_manager.active_positions
            and self.intraday_manager.active_positions[symbol]["direction"] == "BUY"
        ):
            opposite_position = self.intraday_manager.active_positions.get(symbol)
            if self._is_option_dynamic_exit(opposite_position):
                return "runner_position_active"
            self._close_position(symbol, price, "SIGNAL_REVERSAL")
            if (
                symbol in self.intraday_manager.active_positions
                or self.trade_journal.get_open_trade(symbol, "BUY")
            ):
                return "reversal_close_failed"
        if open_trade is None:
            cutoff_reason = self._entry_cutoff_reason()
            if cutoff_reason:
                logger.info("[%s] Entry rejected: %s", symbol, cutoff_reason)
                return cutoff_reason
            if not self._live_entry_allowed(symbol):
                return "live_entry_paused"
            allowed, reason = self._can_open_trade_for_signal(symbol, "SELL", score)
            if not allowed:
                logger.info("[%s] Trade blocked: %s", symbol, reason)
                return f"trade_blocked:{reason}"
            if symbol in self.intraday_manager.session_trade_symbols:
                strategy_variant = (
                    "paper_underlying_support_reversal_stop_reentry"
                    if strategy_variant == "paper_underlying_support_reversal"
                    else "paper_stop_reentry"
                )
            option_adaptive_exit = self._option_adaptive_exit_enabled(symbol)
            adaptive_exit_values = None
            if option_adaptive_exit:
                try:
                    adaptive_exit_values = (
                        self._option_adaptive_exit_r_values()
                    )
                except (TypeError, ValueError, OverflowError):
                    logger.exception("[%s] Invalid adaptive-exit settings", symbol)
                    return "invalid_option_adaptive_exit_config"
            staged_option_targets = (
                False
                if option_adaptive_exit
                else self._staged_option_targets_enabled(symbol)
            )
            if self._options_enabled() and "_" in symbol:
                premium_stop_pct = float(self.config.get("option_premium_stop_pct", 0.20))
                premium_target_pct = self._option_entry_target_pct(
                    staged_option_targets
                )
                premium = float(self.latest_prices.get(symbol, price))
                price = premium
                stop_loss = min(price * (1.0 + premium_stop_pct), 1e9)
                risk_per_unit = stop_loss - price
                if adaptive_exit_values is not None:
                    take_profit = max(
                        price - risk_per_unit * adaptive_exit_values[3],
                        0.01,
                    )
                else:
                    take_profit = max(
                        price * (1.0 - premium_target_pct),
                        0.01,
                    )
                quantity = self._calculate_option_quantity(
                    symbol, premium, premium_stop_pct
                )
            else:
                risk_plan = build_risk_plan(
                    price,
                    "SELL",
                    stop_loss_pct=self.config.get("stop_loss_pct", 0.75),
                    take_profit_pct=self.config.get("take_profit_pct", 1.5),
                )
                stop_loss = risk_plan.stop_loss
                take_profit = risk_plan.take_profit
                quantity = self._calculate_position_size(
                    symbol,
                    price,
                    stop_loss,
                )

            if quantity == 0:
                logger.warning(f"[{symbol}] Cannot calculate position size, skipping trade")
                evaluation = getattr(self, "_pending_entry_evaluations", {}).get(
                    symbol, {}
                )
                if evaluation.get("rejection_reason") == "one_lot_exceeds_trade_risk_cap":
                    cap = float(evaluation["risk_cap_rupees"])
                    return (
                        "risk_cap_blocked:"
                        f"one_lot_exceeds_{cap:g}_rupees"
                    )
                if evaluation.get("rejection_reason") == (
                    "stop_risk_exceeds_deployed_capital_limit"
                ):
                    return "risk_blocked:stop_risk_exceeds_deployed_capital_limit"
                return "position_size_zero"

            order_id = None
            if self.live_orders_enabled:
                try:
                    order_id = self.kite_stream.place_market_order(
                        symbol, "SELL", quantity
                    )
                    fill = self.kite_stream.wait_for_order_fill(order_id, quantity)
                    quantity = int(fill["filled_quantity"])
                    price = float(fill["average_price"])
                    if self._options_enabled() and "_" in symbol:
                        stop_loss = min(price * (1.0 + premium_stop_pct), 1e9)
                        take_profit = max(price * (1.0 - premium_target_pct), 0.01)
                    else:
                        risk_plan = build_risk_plan(
                            price,
                            "SELL",
                            stop_loss_pct=self.config.get("stop_loss_pct", 0.75),
                            take_profit_pct=self.config.get("take_profit_pct", 1.5),
                        )
                        stop_loss = risk_plan.stop_loss
                        take_profit = risk_plan.take_profit
                except Exception:
                    logger.exception("[%s] Live SELL order was not filled", symbol)
                    self._reconcile_after_order_failure(symbol)
                    return "live_order_failed"

            # Register position in intraday manager
            self.intraday_manager.register_position(
                symbol,
                "SELL",
                quantity,
                price,
                stop_loss,
                take_profit,
                signal_score=score,
                staged_targets_enabled=staged_option_targets,
                target_increment_pct=self._option_target_increment(),
                minimum_signal_score=(
                    minimum_signal_score
                    if minimum_signal_score is not None
                    else self._entry_score_floor()
                ),
                strong_signal_score=int(self.config.get("strong_signal_score", 82)),
                weak_signal_lockin_pct=float(
                    self.config.get("option_weak_signal_lockin_pct", 0.05)
                ),
                trailing_enabled=True if option_adaptive_exit else None,
                exit_strategy=(
                    PAPER_OPTION_ADAPTIVE_EXIT if option_adaptive_exit else None
                ),
                adaptive_breakeven_r=(
                    adaptive_exit_values[0] if adaptive_exit_values else None
                ),
                adaptive_trail_activation_r=(
                    adaptive_exit_values[1] if adaptive_exit_values else None
                ),
                adaptive_trail_gap_r=(
                    adaptive_exit_values[2] if adaptive_exit_values else None
                ),
                adaptive_runner_activation_r=(
                    adaptive_exit_values[3] if adaptive_exit_values else None
                ),
                adaptive_runner_gap_r=(
                    adaptive_exit_values[4] if adaptive_exit_values else None
                ),
                milestone_window_minutes=int(
                    self.config.get("option_milestone_window_minutes", 5)
                ),
                strong_milestone_window_minutes=int(
                    self.config.get("strong_option_milestone_window_minutes", 10)
                ),
            )
            self.intraday_manager.record_trade_open(symbol, "SELL")
            if self.live_orders_enabled and not self._place_protective_stop(
                symbol, self.intraday_manager.active_positions[symbol]
            ):
                self._abort_live_entry(symbol, price, "PROTECTION_FAILED")
                return "protective_stop_failed"
            if (
                self.live_orders_enabled
                and self._options_enabled()
                and "_" in symbol
                and not self._option_quantity_within_lot_bounds(symbol, quantity)
            ):
                self._abort_live_entry(symbol, price, "OPTION_FILL_OUTSIDE_LOT_BOUNDS")
                return "option_fill_outside_lot_bounds"
            if (
                self.live_orders_enabled
                and self.intraday_manager.estimate_trade_risk(
                    symbol, quantity, price, stop_loss
                ) > self._entry_risk_limit(symbol, price) + 1e-6
            ):
                self._abort_live_entry(symbol, price, "RISK_LIMIT_EXCEEDED")
                return "risk_blocked:filled_risk_exceeds_limit"
            if (
                self.live_orders_enabled
                and self.intraday_manager.daily_risk_exceeded()
            ):
                self._abort_live_entry(
                    symbol, price, "AGGREGATE_RISK_LIMIT_EXCEEDED"
                )
                return "risk_blocked:filled_risk_exceeds_aggregate_limit"

            mode = "intraday_options" if self._options_enabled() else "futures"
            option_leg = "CE" if symbol.endswith("_CE") else "PE" if symbol.endswith("_PE") else None
            trading_symbol = self.kite_stream.contract_symbols.get(symbol, symbol)
            alert = self.telegram_notifier.format_trade(
                ticker=symbol,
                action="SELL",
                score=score,
                entry=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                mode=mode,
                option_leg=option_leg,
                trading_symbol=trading_symbol,
                trailing_enabled=(
                    True
                    if option_adaptive_exit
                    else self.intraday_manager.trailing_enabled
                ),
            )
            alert["pnl"] = 0.0
            alert["status"] = "open"
            alert["stop_loss"] = stop_loss
            alert["take_profit"] = take_profit
            alert["quantity"] = quantity
            alert["strategy_variant"] = strategy_variant or "primary"
            if staged_option_targets:
                position = self.intraday_manager.active_positions[symbol]
                alert.update(
                    {
                        "exit_strategy": "tiered_milestone",
                        "option_milestone_pct": position["target_increment_pct"],
                        "target_stage": position["target_stage"],
                        "milestone_reached_pct": position["milestone_reached_pct"],
                        "milestone_started_at": position["milestone_started_at"].isoformat(),
                        "entry_time": position["entry_time"].isoformat(),
                        "minimum_signal_score": position["minimum_signal_score"],
                        "decision_window_minutes": position["decision_window_minutes"],
                        "current_signal_score": position["current_signal_score"],
                    }
                )
            elif self._options_enabled() and "_" in symbol:
                if option_adaptive_exit:
                    alert["exit_strategy"] = PAPER_OPTION_ADAPTIVE_EXIT
                    alert["trailing_enabled"] = True
                else:
                    alert["exit_strategy"] = "fixed_20pct"
            if order_id:
                alert["order_id"] = order_id
            protection_order_id = self.intraday_manager.active_positions[symbol].get(
                "protection_order_id"
            )
            if protection_order_id:
                alert["protection_order_id"] = protection_order_id

            if option_adaptive_exit:
                position = self.intraday_manager.active_positions[symbol]
                alert.update(
                    {
                        "adaptive_breakeven_r": position["adaptive_breakeven_r"],
                        "adaptive_trail_activation_r": position["adaptive_trail_activation_r"],
                        "adaptive_trail_gap_r": position["adaptive_trail_gap_r"],
                        "adaptive_runner_activation_r": position["adaptive_runner_activation_r"],
                        "adaptive_runner_gap_r": position["adaptive_runner_gap_r"],
                        "adaptive_exit_mode": position["adaptive_exit_mode"],
                        "max_favorable_r": position["max_favorable_r"],
                        "highest_price": position["highest_price"],
                        "lowest_price": position["lowest_price"],
                        "trailing_active": position["trailing_active"],
                        "trailing_stop": position["trailing_stop"],
                    }
                )
            alert["contract_id"] = self._contract_id(symbol)
            alert["entry_mode"] = getattr(self, "entry_mode", "immediate")
            alert["route"] = (
                "support_reversal"
                if strategy_variant == "paper_underlying_support_reversal"
                else "scored"
            )
            self.trade_journal.log_trade(alert)
            self._persist_current_live_risk_state()
            target_label = "adaptive_exit_ref" if option_adaptive_exit else "TP"
            logger.info(
                f"[{symbol}] SELL ALERT -> {quantity} qty @ {alert['entry']:.2f}, "
                f"SL={alert['stop_loss']:.2f}, "
                f"{target_label}={alert['take_profit']:.2f}"
            )
            logger.info(self.telegram_notifier.build_message(alert))
            self.telegram_notifier.send_trade_alert(alert)
            return "trade_opened"
        else:
            logger.info(f"[{symbol}] SELL OPEN -> current={price:.2f}")
            return "position_updated"

    def _handle_market_close_exit(self) -> None:
        """Force exit all positions before market close (3:15 PM)."""
        positions = self.intraday_manager.get_all_open_positions()
        if positions:
            logger.warning(f"Market close time (3:15 PM) - Force closing all positions")
            for pos_symbol, pos_details in positions.items():
                price = self.latest_prices.get(pos_symbol, pos_details["entry_price"])
                self._close_position(pos_symbol, price, "MARKET_CLOSE_FORCED_EXIT")

    def _finalize_daily_session(self, now: datetime) -> bool:
        """Complete post-close reporting only after the broker confirms flatness."""
        self._handle_market_close_exit()
        if self.intraday_manager.get_all_open_positions():
            self.telegram_notifier.send_message(
                "URGENT: session cannot complete; local positions remain open after exit retries."
            )
            return False
        if self.live_orders_enabled:
            try:
                open_positions = [
                    position
                    for position in self.kite_stream.get_positions()
                    if int(position.get("quantity", 0) or 0) != 0
                ]
                if open_positions:
                    self.telegram_notifier.send_message(
                        "URGENT: session cannot complete; broker account is not flat: "
                        + ", ".join(
                            str(position.get("tradingsymbol", "unknown"))
                            for position in open_positions
                        )
                    )
                    return False
            except Exception as exc:
                logger.exception("Could not confirm broker flatness at session close")
                self.telegram_notifier.send_message(
                    f"URGENT: session cannot complete; broker flatness is unknown.\n{exc}"
                )
                return False
        for symbol, state in getattr(self, "_ema_reentry_states", {}).items():
            if state.get("status") != "observing":
                continue
            state["status"] = "expired"
            state["outcome"] = "NO_SIGNAL"
            self.trade_journal.annotate_trade(
                symbol,
                {"ema_reentry_outcome": "NO_SIGNAL"},
                action="BUY",
            )
            self._log_ema_reentry_event(
                symbol,
                state,
                "SESSION_ENDED",
                current_time=now,
                outcome="no_signal",
            )
        self._write_daily_summary_if_due()
        self._run_weekly_report_if_due(now)
        return True

    def _write_daily_summary_if_due(self) -> None:
        """Publish one daily paper-trading summary after the session closes."""
        today = datetime.now(IST).date()
        if self.last_daily_summary_date == today:
            return
        try:
            today_trades = [
                trade
                for trade in self.trade_journal.read_trades()
                if trade.get("status") == "closed"
                and str(trade.get("closed_at", "")).startswith(today.isoformat())
            ]
            pnls = [float(trade.get("pnl", 0.0)) for trade in today_trades]
            summary_path = write_daily_summary(
                data_dir=".", paper_data_dir=self.paper_trading_dir, target_date=today
            )
            review_path = write_daily_review(
                data_dir=".", paper_data_dir=self.paper_trading_dir, target_date=today
            )
            self.last_daily_summary_date = today
            logger.info(
                "Daily paper-trading summary written to %s; review written to %s",
                summary_path,
                review_path,
            )
            self.telegram_notifier.send_daily_summary(
                summary_date=today.isoformat(),
                closed_trades=len(today_trades),
                winning_trades=sum(1 for pnl in pnls if pnl > 0),
                losing_trades=sum(1 for pnl in pnls if pnl <= 0),
                total_pnl=sum(pnls),
            )
        except Exception:
            logger.exception("Daily paper-trading summary failed; trading remains active")

    def run(self) -> None:
        """Start the bot and stream market data with intraday monitoring."""
        logger.info(
            "Starting Kite Trading Bot - %s MODE",
            self.config.get("trading_mode", "intraday_futures").upper(),
        )
        logger.info(
            "Execution mode: %s",
            "REALTIME PAPER TRADING" if self.paper_trading_enabled else "LIVE ORDERS",
        )
        logger.info(f"Instruments: {list(self.config['instrument_tokens'].keys())}")
        logger.info(f"Bar interval: {self.config.get('bar_interval_seconds', 60)}s")
        logger.info(f"Market close exit time: {self.intraday_manager.AUTO_EXIT_TIME}")
        logger.info(f"Risk per trade: {self.intraday_manager.risk_per_trade_pct}%")

        try:
            if self.news_monitor:
                self.news_monitor.start()
            self.kite_stream.start()
            logger.info("Waiting for WebSocket connection...")
            if self.kite_stream.wait_for_connection(timeout=15):
                logger.info("WebSocket connected, streaming live data...")
                self.telegram_notifier.send_heartbeat(
                    instruments=len(self.config["instrument_tokens"]),
                    bar_interval_seconds=self.config.get("bar_interval_seconds", 60),
                    mode=self.config.get("trading_mode", "intraday_futures"),
                )
                last_heartbeat = time.monotonic()
                last_close_check = datetime.now(IST)

                while True:
                    now_monotonic = time.monotonic()
                    if now_monotonic - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                        self.telegram_notifier.send_heartbeat(
                            instruments=len(self.config["instrument_tokens"]),
                            bar_interval_seconds=self.config.get("bar_interval_seconds", 60),
                            mode=self.config.get("trading_mode", "intraday_futures"),
                        )
                        last_heartbeat = now_monotonic

                    # Check every 30 seconds if it's time to force exit
                    now = datetime.now(IST)
                    if (now - last_close_check).total_seconds() >= 30:
                        if self.intraday_manager.is_market_closed():
                            if self._finalize_daily_session(now):
                                logger.info("Market session complete; shutting down bot.")
                                break
                        if self.intraday_manager.should_exit_all_positions():
                            self._handle_market_close_exit()
                        last_close_check = now

                    time.sleep(1)
            else:
                logger.error("Failed to connect to Kite WebSocket")
                sys.exit(1)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            if self.news_monitor:
                self.news_monitor.stop()
            self.kite_stream.stop()
            logger.info("Bot shutdown complete")

    def _run_weekly_report_if_due(self, now: datetime) -> None:
        """Publish one protected weekly report after Friday's close check."""
        if now.weekday() != 4 or self.last_weekly_report_date == now.date():
            return
        try:
            report_path = write_weekly_report(
                data_dir=".",
                days=self.config.get("weekly_report_days", 7),
                output_dir=str(self.weekly_report_dir),
                paper_data_dir=self.paper_trading_dir,
            )
            review_path = write_weekly_review(
                data_dir=".",
                paper_data_dir=self.paper_trading_dir,
                days=self.config.get("weekly_report_days", 7),
            )
            if report_path.exists():
                self.last_weekly_report_date = now.date()
                logger.info(
                    "Automatic weekly report written to %s; review written to %s",
                    report_path,
                    review_path,
                )
            else:
                logger.error("Weekly report was not published; it will be retried")
        except Exception:
            logger.exception("Weekly analytics failed; trading remains active")


def main() -> None:
    """Entry point for the Kite-based bot."""
    try:
        bot = KiteTradingBot()
        bot.run()
    except FileNotFoundError as exc:
        logger.error(f"Configuration error: {exc}")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"Fatal error: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
