import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class BotConfig:
    tickers: List[str] = field(default_factory=lambda: ["AAPL"])
    interval_seconds: int = 45
    lookback_bars: int = 30
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    alert_rsi_low: int = 35
    alert_rsi_high: int = 65
    stop_loss_pct: float = 1.5
    take_profit_pct: float = 3.0
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    @classmethod
    def load(cls, path: Optional[str] = None) -> "BotConfig":
        config_path = Path(path or "config.json")
        if not config_path.exists():
            raise FileNotFoundError(
                f"Missing config file: {config_path}. Please create config.json from config.example.json."
            )

        with config_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return cls(**data)
