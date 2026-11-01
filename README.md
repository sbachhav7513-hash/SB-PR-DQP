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

Read [SECURITY.md](SECURITY.md) before adding Telegram or Kite credentials. Runtime secrets are read from environment variables and are not taken from JSON config files.

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
  "telegram_token": null,
  "telegram_chat_id": null,
  "telegram_trade_chat_id": null
}
```

For PowerShell, set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the terminal before running the bot. Do not commit or share those values.
Optionally set `TELEGRAM_TRADE_CHAT_ID` to send trade alerts to a separate Telegram
group as well as the existing chat. This setting is read from the environment, not
from the JSON configuration.

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
| `telegram_trade_chat_id` | Optional additional destination for trade alerts | `null` |

### 3. Running the Bot (Yahoo Finance - Polling)

```bash
python run_bot.py
```

The bot will start polling market data every 60 seconds and display trading signals in the console.

On every start it also refreshes the daily summary, weekly JSON report, and paper-trading review from the previous runs. During monitoring it records every BUY, SELL, and HOLD decision, including the score, reasons, and recent bars, in `decision_log.jsonl` and `paper_trading_data/`. The configured EMA, RSI, and lookback settings are used for each decision.

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

Kite execution uses one `mode` setting, `PAPER` or `LIVE`. Set `mode` in
`kite_config.json`, or override it for one process with `MODE`:

```bash
MODE=PAPER python run_kite_bot.py
```

After validating the same strategy in paper trading, select `LIVE` without
changing strategy settings:

```bash
MODE=LIVE python run_kite_bot.py
```

In PowerShell, use `$env:MODE = "PAPER"` (or `"LIVE"`) before running the
same command.

`MODE` changes order execution and broker interaction only. Strategy,
filters, thresholds, risk limits, and signal evaluation are shared. The
existing `live_orders_confirmed` safety gate must also be enabled in
`kite_config.json` before LIVE orders can start. `trading_mode` remains the
separate market-scope setting for futures/options/both.

#### Telegram command control (Phase 1)

Set the bot token and an explicit comma-separated allowlist in the process
environment. Never put the token in a committed config file:

```powershell
$env:TELEGRAM_BOT_TOKEN = "<bot-token>"
$env:TELEGRAM_ALLOWED_CHAT_IDS = "<your-chat-id>"
$env:TELEGRAM_CHAT_ID = "<your-chat-id>" # For existing outbound notifications
$env:TELEGRAM_TRADE_CHAT_ID = "<trade-group-chat-id>" # Optional trade-alert destination
python run_kite_bot.py
```

In a private chat, Telegram's chat and sender IDs are the same. In a group,
allowlist both the group chat ID and each permitted sender ID. Unauthorized
updates are ignored and logged by ID; old messages from before startup are
ignored. The listener only queues commands; the trading tick callback handles
them at the start of a tick so commands cannot race stop-loss/trailing
management. Queued commands wait for the next tick. If Telegram is unreachable,
trading continues.

Trade entry, exit, target-update, and watchlist alerts are sent to both
`TELEGRAM_CHAT_ID` and the optional `TELEGRAM_TRADE_CHAT_ID`. Daily trade
summaries are sent to both destinations. Status, connection/error alerts, and
command replies continue to use the existing chat.
The trade group is outbound-only: do not add its ID to
`TELEGRAM_ALLOWED_CHAT_IDS`; command access remains limited to the configured
allowlist.

If the bot is run as the included systemd service, set
`TELEGRAM_TRADE_CHAT_ID=<trade-group-chat-id>` in the service's `.env` file and
restart the service.

Available Phase 1 commands:

| Command | Behavior |
|---------|----------|
| `/help` | List available commands |
| `/status` | Show RUNNING/PAUSED state, mode, config hash, quote age, and open positions |
| `/pnl` | Show today's realized/unrealized P&L, closed trade count, wins/losses, and daily loss usage |
| `/trades` | List today's closed trades |
| `/health` | Show quote timestamps, stale quote count, websocket status, and last tick |
| `/pause` | Block new entries; existing positions continue to be managed |
| `/resume` | Resume new entries |

Telegram command control also supports:

| Command | Behavior |
|---------|----------|
| `/exit <id>` | Close an open trade; PAPER executes on the next tick, LIVE requires a same-chat `YES` confirmation within 30 seconds |
| `/exitat <id> <price>` | Set a long-option exit trigger; closes when LTP reaches the price unless an existing stop or target exits first |
| `/cancel <id>` | Clear the trade's manual exit trigger |
| `/sl <id> <price> [force]` | Change stop loss; a loosening change requires `force` |
| `/be <id>` | Move stop loss to entry when LTP is above entry |
| `/target <id> <price>` | Change target in the profitable direction relative to LTP |

Commands are validated and queued by the listener, then applied at the start of
a market tick. Commands and their responses are appended to `commands.jsonl`
beside the trade journal. Trade records retain manual exit source/reason and a
timestamped history of stop/target changes. `TELEGRAM_CONTROL_LIVE_ORDERS`
defaults to `false`; LIVE Telegram exits place no order unless explicitly set
to `true`. Test in `PAPER` mode first.

#### Telegram-control simulation (market-closed testing)

Set `BOT_SIM_MODE=true` to force PAPER mode and replace Kite quotes with a
local feed. Simulation startup does not require Kite credentials, create a Kite
client, or request broker data; selecting LIVE through config or `MODE` makes
startup fail. Trade journals, command logs, paper data, option captures, and
the bot log are written below `BOT_SIM_DIR` (default `sim`) rather than the
production journal or analysis directories.

An optional JSON or CSV feed can replay prices at the configured interval:

```powershell
$env:BOT_SIM_MODE = "true"
$env:BOT_SIM_FEED_FILE = ".\sim\prices.json"
$env:BOT_SIM_TICK_INTERVAL_SECONDS = "2" # Optional; defaults to 2 seconds
$env:BOT_SIM_DIR = ".\sim"
python run_kite_bot.py
```

JSON accepts `{"ticks":[{"symbol":"NIFTY_CE","price":10},{"symbol":"NIFTY_CE","price":12}]}`,
or a symbol-to-prices map such as `{"NIFTY_CE":[10,12]}`. CSV uses `symbol,price`
columns. `/simprice <symbol> <price>` publishes an immediate manual quote.
`/simopen <symbol> <CE|PE> <qty> <entry> [SL target]` opens a synthetic paper
option position through the normal position manager and journal; omitted SL
and target use the configured option exit rules. Both commands are rejected
unless SIM mode is enabled, and Telegram's configured chat allowlist still
applies.

Run the local command-handler scenarios with:

```powershell
python sim_scenarios.py
```

The script uses the actual Telegram update listener and command handlers with
no Telegram or broker connection, prints each scenario's replies and trade
journal rows, and stores each run under `sim/scenarios/<timestamp>`.

`entry_mode` defaults to `immediate`. The optional `confirmed` mode is
available only with `mode: "PAPER"` and an options trading mode. It waits for
the next fully closed one-minute underlying candle, requires a strict
directional close (CE higher, PE lower), then revalidates the entry filters
and uses the fresh option ask as the paper fill. Bar timestamps are the
one-minute bar start in IST. Pending entries are memory-only and are expired
and journaled if the process restarts before confirmation.

#### 4.3 Running the Kite-Based Bot

```bash
python run_kite_bot.py
```

This version:
- Connects to Zerodha Kite WebSocket for live tick data
- Aggregates ticks into configurable bar intervals
- Falls back to a valid tick `timestamp` when Kite's `exchange_timestamp` is invalid; drops the tick if both are invalid
- Evaluates signals on fresh live bars
- Sends Telegram alerts when conditions are met

**Key Differences from Yahoo Version:**
- True real-time streaming instead of polling
- Tick-level precision aggregated into bars
- Lower latency for signal generation
- Better suited for intraday trading

#### Shared EMA Stop-Loss Re-entry

When `ema_reentry_enabled` is true, an option trade that closes at a losing
`STOP_LOSS` starts a single 10-minute observation window for that original trade.
The same feature and settings apply in PAPER and LIVE. It requires 1-minute
underlying candles: CE setups use an EMA(5) cross above EMA(20) followed by a
later underlying close above the crossover candle high; PE setups use the inverse
cross and close below the crossover candle low. EMA alignment is checked again
at confirmation. The underlying session VWAP is recorded as context, not used
as an extra entry filter.

The re-entry uses the shared option sizing and exit rules; order placement alone
depends on `mode`. Trade rows and daily/weekly reports link it to the original
trade and record stop/signal times, reason, option-premium entry/exit, P&L,
outcome, and a baseline comparison. For an offline replay, set
`ema_reentry_enabled` in the supplied config and run:

```bash
python -m market_bot.replay underlying_1m.csv --ticker NIFTY --config kite_config.json --output ema_reentry_report.json
```

Offline replay signals use the underlying candles and its reported returns are
underlying-price directional proxies, not option-premium P&L. Paper reports use
the recorded option trade P&L.

The Kite paper runner and offline replay both load `kite_config.json` through
the shared strategy-config loader. Trade and decision audit records include a
SHA-256 `config_hash`; credentials and paper/live mode flags are excluded from
the hash. Existing journal rows are not retroactively assigned a hash, so
their configuration cannot be verified from the journal alone.

In option mode, `capture_all_evaluated_contracts` defaults to `true` and is
excluded from the strategy config hash. The selected contract and its opposite
CE/PE contract are registered before option-quality and subsequent entry gates.
Capture is read-only and uses a bounded background writer; queue/disk failures
drop capture rows and are logged without waiting on the tick or order path.
Trading subscriptions remain unchanged. capture-only opposite contracts are added in one startup WebSocket subscribe
request, capped at 128 extra tokens and the Kite limit of 3,000 instruments
per connection; skipped contracts are reported with their reason.

New daily files are written below
`paper_trading_data/option_candles/YYYY-MM-DD/`, one pair per exact
`EXCHANGE:TRADINGSYMBOL` (non-filename characters are replaced with `_`):

* `<contract>.candles.csv` (compressed to `.candles.csv.gz` after 15:30 IST):
  one completed IST minute per row with `contract_id`, underlying, leg, strike,
  expiry, `candle_start_time` (ISO `+05:30`), OHLCV, OI when present, tick
  count, last tick time, close bid/ask, config hash, git SHA,
  `capture_all_evaluated_contracts`, `low_tick`, and `gap`. Gaps have empty
  prices; prices are never forward-filled.
* `<contract>.quotes.csv` (compressed to `.quotes.csv.gz` after 15:30 IST):
  `time` (ISO `+05:30`), contract metadata, LTP, bid/ask, last tick time,
  `quote_age_seconds`, config hash, git SHA, and the capture flag. Snapshots are
  sampled at 5-second intervals while pending or for 10 minutes after
  rejection, otherwise 30 seconds; unchanged values are skipped except for a
  once-per-minute heartbeat.
* `capture_report.json` and `capture_report.txt`: signal resolution and forward
  coverage, match rate, captured/skipped contracts, tick/candle gaps, dropped
  rows, and subscription start delays.
  The combined daily capture files are capped at 256 MiB.

The loader uses `contract_id` only and never infers a contract:

```python
from market_bot.option_capture import load_option_capture

capture = load_option_capture(
    "paper_trading_data/option_candles",
    "2026-10-30",
    decision_row,
)
```

`python backfill_option_contract_ids.py` reads the 29-Oct and 30-Oct decision
Parquet journals and writes separate `decisions.contract-id-backfilled.parquet`
files only when an exact fill is available. It fills only rows joined by a
unique `signal_id` to an existing contract-bearing row; ambiguous or unmapped
rows remain blank, and original journals are read-only. If there are no safe
fills, it reports that no output was needed.

Rejected option signals are also recorded in `rejected_signals.jsonl` beside
the decision log. Rows include the IST signal/rejection times, contract and
config hash, measured gate values and quote, and forward 15/30/60-minute
premium MFE/MAE; unavailable candle outcomes are marked unmatched.

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

## PAPER option-entry recovery gates

The `stale_quote_candle_fallback`, `option_candle_momentum`, and
`index_persistence_pass` settings are included in the strategy config hash and
apply only in `PAPER`; they do not change `LIVE` behavior. The example and
current PAPER config enable all three. No shadow execution mode is used.

The stale-quote fallback keeps the 60-second freshness limit. When a quote is
older than that, PAPER may use the last completed one-minute option candle only
while its close is no more than 120 seconds old. The gate reference is candle
close + INR 0.05. The conservative entry fill is
`max(candle close, last known ask) + INR 0.05`. Quote source, quote/candle age,
option token, per-token last tick time, and daily tick-gap count are recorded on
decision and trade rows. Historical 14–30 Oct exports contain minute OHLC but
not tick-level quotes/asks; stale-quote results are therefore only a
sensitivity estimate using the next one-minute candle open as the unavailable
ask proxy, with the conservative maximum rule retained. They are not historical
validation of this change.

Run the PAPER rollback check once per trading day:

```powershell
python paper_change_rollback_check.py --config kite_config.json --trades trades.jsonl --decisions decision_log.jsonl
```

For each change, the script prints attributed-trade count, active PAPER session
count, net P/L, and profit factor. After 15 added trades or 5 trading days,
whichever comes first, it switches that config key off if net P/L after costs
is below zero or profit factor is below 1.0. The fallback cost model is INR 98
per round trip plus INR 0.05 per unit per side; it does not use the
paper-shadow fee fields. A config change takes effect after the bot is restarted.
