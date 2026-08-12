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
    alert_rsi_low: int = 30
    alert_rsi_high: int = 70

    @classmethod
    def load(cls, path: Optional[str] = None) -> "BotConfig":
        config_path = Path(path or "config.json")
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return cls(**data)

        fallback = Path("config.example.json")
        if fallback.exists():
            with fallback.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return cls(**data)

        return cls()
