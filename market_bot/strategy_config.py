import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Optional


logger = logging.getLogger(__name__)

LEGACY_PAPER_STRATEGY_KEYS = {
    "paper_allow_trend_continuation": "allow_trend_continuation",
    "paper_min_entry_score": "min_entry_score",
    "paper_rsi_buy_block_above": "rsi_buy_block_above",
    "paper_rsi_sell_block_below": "rsi_sell_block_below",
    "paper_option_min_candle_body_ratio": "option_min_candle_body_ratio",
    "paper_stop_reentry_enabled": "stop_reentry_enabled",
    "paper_stop_reentry_cooldown_minutes": "stop_reentry_cooldown_minutes",
    "paper_stop_reentry_min_score": "stop_reentry_min_score",
    "paper_ema_reentry_enabled": "ema_reentry_enabled",
    "paper_support_reversal_enabled": "support_reversal_enabled",
    "paper_support_reversal_min_premium": "support_reversal_min_premium",
    "paper_support_reversal_min_score": "support_reversal_min_score",
    "paper_support_reversal_cooldown_minutes": "support_reversal_cooldown_minutes",
    "paper_support_reversal_min_candle_body_ratio": "support_reversal_min_candle_body_ratio",
    "paper_option_range_breakout_enabled": "option_range_breakout_enabled",
    "paper_option_range_lookback_bars": "option_range_lookback_bars",
    "paper_option_range_confirmation_bars": "option_range_confirmation_bars",
    "paper_option_range_target_r": "option_range_target_r",
    "paper_option_adaptive_exit_enabled": "option_adaptive_exit_enabled",
    "paper_option_adaptive_breakeven_r": "option_adaptive_breakeven_r",
    "paper_option_adaptive_trail_activation_r": "option_adaptive_trail_activation_r",
    "paper_option_adaptive_trail_gap_r": "option_adaptive_trail_gap_r",
    "paper_option_adaptive_runner_activation_r": "option_adaptive_runner_activation_r",
    "paper_option_adaptive_runner_gap_r": "option_adaptive_runner_gap_r",
    "paper_max_risk_per_trade": "max_risk_per_trade",
    "paper_entry_cutoff_minutes_before_close": "entry_cutoff_minutes_before_close",
    "paper_extend_option_timebox": "extend_option_timebox",
}

NON_STRATEGY_CONFIG_KEYS = {
    "kite_api_key",
    "kite_access_token",
    "telegram_token",
    "telegram_chat_id",
    "mode",
    "paper_trading_enabled",
    "live_orders_enabled",
    "live_orders_confirmed",
}


def load_strategy_config(path: str | Path) -> Dict:
    """Load and normalize the shared paper/replay strategy configuration."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Strategy configuration file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError(
            f"Strategy configuration must be a JSON object: {config_path}"
        )
    return normalize_strategy_config(config)


def strategy_config_hash(config: Dict) -> str:
    """Return a stable SHA-256 hash of normalized strategy settings."""
    strategy_config = normalize_strategy_config(config)
    for key in NON_STRATEGY_CONFIG_KEYS:
        strategy_config.pop(key, None)
    canonical = json.dumps(
        strategy_config,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_strategy_config(config: Dict) -> Dict:
    normalized = dict(config)
    for legacy_key, strategy_key in LEGACY_PAPER_STRATEGY_KEYS.items():
        if legacy_key not in normalized:
            continue
        legacy_value = normalized.pop(legacy_key)
        if (
            strategy_key in normalized
            and normalized[strategy_key] != legacy_value
        ):
            logger.warning(
                "Both %s and %s are configured with different values; "
                "using the former paper strategy value for both modes",
                strategy_key,
                legacy_key,
            )
        normalized[strategy_key] = legacy_value
    return normalized


def resolve_execution_mode(config: Dict, environment_mode: Optional[str]) -> str:
    configured_mode = (
        environment_mode if environment_mode is not None else config.get("mode")
    )
    if configured_mode is None:
        paper_enabled = bool(config.get("paper_trading_enabled", True))
        live_enabled = bool(config.get("live_orders_enabled", False))
        if paper_enabled == live_enabled:
            raise ValueError(
                "Set mode to PAPER or LIVE; legacy paper/live flags are "
                "missing or conflicting"
            )
        configured_mode = "PAPER" if paper_enabled else "LIVE"

    mode = str(configured_mode).strip().upper()
    if mode not in {"PAPER", "LIVE"}:
        raise ValueError("MODE must be PAPER or LIVE")
    return mode
