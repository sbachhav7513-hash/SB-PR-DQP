# SB-PR-DQP - Share Market Alert Bot

A real-time Python trading bot that monitors share market data and generates automated trading alerts using technical analysis. The bot fetches market data, applies EMA crossover and RSI indicators, evaluates risk metrics, and sends notifications via Telegram.

---

## 🎯 Features

- **Real-time Market Monitoring**: Polls stock market data at configurable intervals
- **Technical Analysis**: 
  - EMA (Exponential Moving Average) crossover signals
  - RSI (Relative Strength Index) for overbought/oversold detection
- **Risk Management**: Automatic stop-loss and take-profit level calculation
- **Telegram Notifications**: Real-time alerts and trade signals
- **Trade Journaling**: Logs all trades and signals to JSONL format
- **Configurable**: Support for multiple tickers and customizable parameters
- **Modular Architecture**: Clean separation of concerns with dedicated modules

---

## 📋 System Requirements

- Python 3.11+
- pip (Python package manager)
- Internet connection for market data fetching
- Telegram bot token (optional, for notifications)

---

## 🚀 Quick Start

### 1. Installation

Clone the repository and navigate to the project directory:

```bash
cd SB-PR-DQP
```

Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### 2. Configuration

Copy the example configuration:

```bash
cp config.example.json config.json
```

Edit `config.json` with your preferred settings:

```json
{
  "tickers": ["AAPL", "MSFT", "GOOG"],
  "interval_seconds": 60,
  "lookback_bars": 30,
  "ema_fast": 9,
  "ema_slow": 21,
  "rsi_period": 14,
  "alert_rsi_low": 35,
  "alert_rsi_high": 65,
  "stop_loss_pct": 1.5,
  "take_profit_pct": 3.0,
  "telegram_token": "YOUR_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID"
}
```

#### Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `tickers` | List of stock ticker symbols to monitor | `["AAPL"]` |
| `interval_seconds` | Time between market checks (in seconds) | 45 |
| `lookback_bars` | Number of historical bars for analysis | 30 |
| `ema_fast` | Fast EMA period | 9 |
| `ema_slow` | Slow EMA period | 21 |
| `rsi_period` | RSI calculation period | 14 |
| `alert_rsi_low` | RSI threshold for oversold signals | 35 |
| `alert_rsi_high` | RSI threshold for overbought signals | 65 |
| `stop_loss_pct` | Stop-loss percentage from entry price | 1.5 |
| `take_profit_pct` | Take-profit percentage from entry price | 3.0 |
| `telegram_token` | Telegram bot authentication token | `null` |
| `telegram_chat_id` | Telegram chat ID for notifications | `null` |

### 3. Running the Bot (Yahoo Finance - Polling)

```bash
python run_bot.py
```

The bot will start polling market data every 60 seconds and display trading signals in the console.

### 4. Alternative: Zerodha Kite Connect (Live Streaming)

For true real-time market data streaming instead of polling, you can use Zerodha Kite Connect:

#### 4.1 Prerequisites
- Active Zerodha/Upstox trading account
- API access enabled in your broker dashboard
- API Key and Access Token from your broker

#### 4.2 Setup Kite Configuration

Copy the Kite configuration template:

```bash
cp kite_config.example.json kite_config.json
```

Edit `kite_config.json` with your credentials:

```json
{
  "kite_api_key": "your_api_key_from_kite",
  "kite_access_token": "your_access_token_from_kite",
  "instrument_tokens": {
    "RELIANCE": 738561,
    "TCS": 2953217,
    "INFY": 1222041
  },
  "bar_interval_seconds": 60,
  "telegram_token": "YOUR_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID"
}
```

#### 4.3 Running the Kite-Based Bot

```bash
python run_kite_bot.py
```

This version:
- Connects to Zerodha Kite WebSocket for live tick data
- Aggregates ticks into configurable bar intervals
- Evaluates signals on fresh live bars
- Sends Telegram alerts when conditions are met

**Key Differences from Yahoo Version:**
- True real-time streaming instead of polling
- Tick-level precision aggregated into bars
- Lower latency for signal generation
- Better suited for intraday trading

---

## 📁 Project Structure

```
market_bot/
├── __init__.py              # Package initialization
├── config.py                # Configuration loader for Yahoo version
├── data_provider.py         # Yahoo Finance data fetcher
├── engine.py                # Market scoring and analysis engine
├── live_feed.py             # Real-time market feed manager
├── main.py                  # Main bot orchestration (Yahoo version)
├── risk_manager.py          # Risk plan calculation (stop-loss, take-profit)
├── strategy.py              # Trading signals and technical indicators
├── telegram_notifier.py     # Telegram alert sender
├── trade_journal.py         # Trade logging to JSONL
├── kite_provider.py         # Zerodha Kite WebSocket connection handler
├── bar_builder.py           # Tick-to-bar aggregation for live data
└── kite_main.py             # Main bot orchestration (Kite version)

tests/
└── test_strategy.py         # Unit tests for strategy module

Root files:
├── run_bot.py               # Entry point (Yahoo version)
├── run_kite_bot.py          # Entry point (Kite version)
├── config.json              # Bot configuration for Yahoo version (user-specific)
├── config.example.json      # Configuration template for Yahoo version
├── kite_config.json         # Bot configuration for Kite version (user-specific)
├── kite_config.example.json # Configuration template for Kite version
├── requirements.txt         # Python dependencies
├── trades.jsonl             # Trade log (auto-generated)
└── demo_trades.jsonl        # Sample trade data
```

---

## 🔧 Module Descriptions

### `config.py`
Loads and manages bot configuration from `config.json`. Provides the `BotConfig` dataclass with all bot parameters.

### `data_provider.py`
Fetches historical OHLCV (Open, High, Low, Close, Volume) market data from Yahoo Finance via the yfinance API.

### `strategy.py`
Implements technical analysis:
- **EMA Calculation**: Computes exponential moving averages for trend detection
- **Signal Generation**: Creates buy/sell signals based on EMA crossovers and RSI
- **Signal Dataclass**: Represents a trading signal with action, price, and reason

### `risk_manager.py`
Calculates risk metrics for each trade:
- **Stop-Loss**: Exit level to limit losses
- **Take-Profit**: Exit level to secure gains
- **RiskPlan Dataclass**: Encapsulates entry price, stop-loss, and take-profit levels

### `live_feed.py`
Manages real-time market data fetching and snapshot aggregation. Fetches data at the specified interval and period.

### `engine.py`
Scores market conditions and generates trading signals based on configured indicators and thresholds.

### `telegram_notifier.py`
Sends formatted trading alerts and signals to a Telegram chat using the Telegram Bot API.

### `trade_journal.py`
Logs all trades and signals to a JSONL file for historical analysis and record-keeping.

### `main.py`
Main bot loop that:
1. Fetches market data for configured tickers
2. Analyzes data using the strategy engine
3. Generates trading signals
4. Sends notifications
5. Logs trades
6. Repeats at configured intervals

---

## 📊 Technical Indicators

### EMA (Exponential Moving Average)
- **Fast EMA (Default: 9)**: Short-term trend indicator
- **Slow EMA (Default: 21)**: Long-term trend indicator
- **Signal**: BUY when fast EMA crosses above slow EMA; SELL when it crosses below

### RSI (Relative Strength Index)
- **Default Period**: 14 bars
- **Overbought Threshold**: 65 (potential sell signal)
- **Oversold Threshold**: 35 (potential buy signal)
- **Range**: 0-100 scale

---

## 🧪 Testing

Run unit tests for the strategy module:

```bash
python -m pytest tests/test_strategy.py -v
```

Or with coverage:

```bash
python -m pytest tests/test_strategy.py --cov=market_bot --cov-report=html
```

---

## 📝 Output Files

- **`trades.jsonl`**: Contains all generated trading signals and executed trades in JSON Lines format
- **`demo_trades.jsonl`**: Sample data for testing and demonstration

---

## ⚠️ Important Notes

- **Educational Purpose**: This bot is designed as a proof-of-concept and educational tool
- **Not Investment Advice**: Trading signals are for reference only and should not be the sole basis for trading decisions
- **Risk Disclaimer**: Paper trading is recommended before using with real funds
- **Manual Review**: Always review signals before executing trades
- **Market Risk**: Stock market trading involves significant risk of loss

---

## 🔮 Future Enhancements

- [ ] Support for websocket-based real-time data feeds
- [ ] Integration with broker APIs for automated execution (Interactive Brokers, Alpaca)
- [ ] More technical indicators (MACD, Bollinger Bands, Stochastic)
- [ ] Machine learning-based signal filtering
- [ ] Web dashboard for monitoring
- [ ] Database persistence for trade history
- [ ] Email and SMS notifications
- [ ] Portfolio tracking and performance analysis

---

## 📚 Dependencies

See `requirements.txt` for all dependencies. Core packages:
- `requests`: HTTP library for API calls
- `yfinance`: Yahoo Finance data fetcher
- `python-telegram-bot`: Telegram notifications

---

## 📧 Support & Contribution

For issues, feature requests, or contributions, please open an issue or submit a pull request.

---

## 📄 License

This project is provided as-is for educational purposes.
