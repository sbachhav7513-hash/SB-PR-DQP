# Daily & Weekly Operations Guide

> **Before any workspace edit:** check [DAILY_CHANGELOG.md](DAILY_CHANGELOG.md) for repeated work and record every file added, changed, or removed, then add the validation result. For strategy or accuracy changes, also follow [STRATEGY_CHANGELOG.md](STRATEGY_CHANGELOG.md), establish a measured baseline, and test one variable at a time. Do not treat a target as a result.

## 📊 DAILY USAGE (What to Do Every Trading Day)

### Paper-Trading Data Archive

When `run_kite_bot.py` runs, it keeps the existing JSONL logs and also writes a structured archive under `paper_trading_data`:

```text
paper_trading_data/
└── YYYY-MM/
    └── week_XX/
        ├── day_DD/
        │   ├── trades.parquet
        │   ├── decisions.parquet
        │   ├── daily_summary.parquet
        │   └── daily_review.md
        └── weekly_review_YYYY_MM_DD.md
```

The Parquet files use Snappy compression. `trades.parquet` contains the ticker, direction, quantity, entry, exit, stop-loss, take-profit, score, exit reason, point P&L, rupee P&L, and duration. `decisions.parquet` contains the signal, score, reasons, bar data, and available history, and is suitable for transferring large daily decision archives. After market close, the bot writes `daily_summary.parquet` and `daily_review.md`; the review reports closed-trade results, signal/outcome counts, HOLD reason mentions, filter rejections, and shadow-candidate rejections. Its learning-feedback section highlights repeated losing exit groups as review hypotheses, shows whether the 10-closed-trade minimum screening sample is met, and explicitly prevents automatic strategy/config changes. The weekly JSON and Markdown reviews use the same sample gate; low-sample “best profiles” are not promoted as recommendations. On Friday, the bot creates the broader Markdown review in that week's folder.

Paper journal P&L is the recorded simulated result and does not deduct brokerage, taxes, or slippage. Use realistic non-zero costs in historical replay before considering a strategy change. The 10-trade threshold is only a minimum screen, not evidence of a durable edge; patterns in the reports are descriptive, not causal, and the feedback layer never changes trading or live-order settings.

### Exporting Kite History for Offline Replay

The read-only exporter writes minute candles and a coverage manifest to `data_uploads/kite_history`; it never places orders. It reads `KITE_API_KEY` and `KITE_ACCESS_TOKEN` from the process environment or the local, ignored `.env` file. Refresh the daily access token with `python run_kite_bot.py --authorize-only` if required, then run for the desired date range:

```powershell
.\.venv\Scripts\python.exe -m market_bot.kite_history_export `
  --start-date 2026-08-01 `
  --end-date 2026-10-09 `
  --underlyings NIFTY BANKNIFTY RELIANCE HDFCBANK ICICIBANK SBIN INFY TCS LT
```

Underlying symbols default to the configured option roots and market benchmarks when `--underlyings` is omitted. To include options, create a CSV manifest containing the exact historical contract tokens:

```csv
underlying,tradingsymbol,expiry,strike,instrument_type,instrument_token,lot_size,active_from,active_to
NIFTY,NIFTY26OCT25000CE,2026-10-29,25000,CE,12345678,65,2026-10-01,2026-10-29
NIFTY,NIFTY26OCT25000PE,2026-10-29,25000,PE,12345679,65,2026-10-01,2026-10-29
```

Then add `--option-manifest data_uploads/kite_history/options.csv` to the command. Use a separate row for every contract/token and set `active_from`/`active_to` to the dates that contract should be exported; these two columns are optional. The exporter requests option OI and records returned coverage in `manifest.json`. Kite's current instrument list cannot reconstruct expired option tokens, so use a saved instrument-master/contract mapping for past expiries. The historical candle endpoint does not provide historical bid/ask or IV, and some old option contracts may not be retrievable; inspect the manifest and API errors rather than substituting a different contract. Existing output files are protected from accidental replacement; choose another directory or pass `--overwrite` deliberately.

#### Daily option-history collection for paper strategy research

For each trading session, save the configured-underlying NFO contract snapshot before market open, then export candles after the market closes. Use the same session date in both commands; the snapshot is required because expired contract tokens may disappear from a later instrument master. Run these from the repository root on Windows, with a valid `KITE_API_KEY` and refreshed `KITE_ACCESS_TOKEN` in `.env`:

```powershell
$session = Get-Date -Format "yyyy-MM-dd"

# Before market open: preserve date-correct option symbols, expiries, strikes,
# tokens and lot sizes. Do not rerun this for an existing date.
.\.venv\Scripts\python.exe -m market_bot.kite_daily_research_export `
  --date $session `
  --snapshot-only

# After market close: export underlying and option minute OHLCV/OI.
.\.venv\Scripts\python.exe -m market_bot.kite_daily_research_export `
  --date $session
```

Each session is written under `data_uploads/kite_daily/YYYY-MM-DD/` and is ignored by Git. The collector uses the prior session close, the configured expiry mode/lookahead and strike steps, and exports the ATM strike plus all listed strikes within `option_max_strike_distance_pct` (currently 0.5%) for both CE and PE in the chosen expiry. It also stores the dated NFO option-master snapshot and a manifest of requested contracts and returned bars. If the session was a holiday or a configured root has no eligible contracts, check the manifest/output message rather than treating missing bars as zero-activity trades. Keep the daily bot decision/trade archives as well; candles alone do not capture every runtime rejection or actual paper fill.

This is a forward data-collection set, not a shortcut to historical expired contracts. Two calendar weeks usually produce about ten market sessions and may not produce ten closed trades. Use it for an initial diagnostic only; continue collecting through at least 30-60 sessions and retain a separate chronological holdout before selecting or promoting a filter. Kite candles provide no historical bid/ask or IV, so replay costs must remain explicit estimates and positive modeled P&L is not confirmation of executable profitability. Keep all changes paper-only until the held-out sample and forward paper results support them.


## Execution mode and shared strategy

Set `mode` to `PAPER` or `LIVE` in `kite_config.json`, or override it for one
process with `MODE`. Both modes read the same strategy, signal, filter, sizing,
risk, entry, and exit settings. The mode controls execution/broker interaction
and position handling only. LIVE additionally requires
`live_orders_confirmed: true`; do not change strategy values when moving from
paper validation to LIVE. The `paper_*` strategy keys described in older
entries below are historical names, not current configuration fields.

The `SIGNAL_WEAKEN` exit requires two consecutive adverse-premium checks in
both modes. The earlier live-immediate behavior was removed to keep exit rules
identical; the historical October 14 counterfactual is not validation of the
shared rule.

The option range-breakout variant is controlled by the shared
`option_range_breakout_enabled` setting and is currently disabled in both
checked-in Kite configs. When enabled, it checks the previous 15 completed
one-minute candles for each configured CE/PE contract and requires a breakout
close above that rolling high, followed by one completed one-minute close that
remains above it; the live quote must still be above the range high at entry.
Breakout-candle volume must be positive and at least the average volume of the
preceding 15 candles. It does not require an underlying directional score or
use the normal 12:00–13:00 late-entry window. It still requires regular market
hours, a fresh quote passing the option-quality gate, and normal position/risk
limits. Stop is one contract tick below the prior range low; target is 2R from
the entry-to-stop distance. This variant keeps its fixed 2R exit regardless
of mode. Review historical paper results as evidence only; do not infer a
durable edge from the October 14 candle replay.

The shared `stop_reentry_enabled` setting allows one same-symbol retry after
an eligible negative stop exit, subject to its configured cooldown and minimum
score. Existing direction/RSI, option quote-quality, quantity, stop-risk,
daily-loss, and consecutive-loss checks still apply. Retry state and timestamps
are restored from the journal after restart. Paper exit records may include
`paper_exit_quote_timestamp` to audit quote freshness; this is execution
telemetry, not a separate strategy rule.

The shared `support_reversal_enabled` setting controls the underlying-derived
support/reversal variant in both modes. It uses complete one-minute bars
aggregated into five-minute candles, clustered support/resistance pivots, a
recent level retest, directional confirmation, the shared minimum score and
cooldown, option-quality and accuracy gates, and the configured
`support_reversal_min_premium` override. It does not bypass quantity, stop,
per-trade risk, daily-loss, or loss-circuit rules. Review counts and rejection
reasons separately; do not infer performance from the October 23 candle replay.

On the October 14 ICICIBANK 1360 PE minute candles, the first range break with candle-volume and one-lot risk proxies passing those gates was 10:01: close ₹26.20, prior-15 high ₹26.00, prior-15 low ₹24.15, stop ₹24.10, and 2R target ₹30.40. The target was touched by the 13:03 candle (high ₹30.50), modeling ₹2,940 gross for the 700-unit lot before costs. This is a single-contract minute-OHLC counterfactual, not proof of a fresh live quote, executable fill, net profit, or durable edge; earlier breakout candidates failed the configured one-lot risk check. Keep the pilot paper-only and evaluate a larger chronological sample before changing or promoting it. Configure the shared score, ADX, trend, context, volatility, and risk thresholds once in `kite_config.json`. Paper records from earlier shadow experiments remain in archived reports for historical comparison, but the bot no longer generates or promotes shadow candidates.

For options-mode breakout confirmation, underlying OHLC/ATR remain the signal basis, but relative volume is read from the selected option contract and matched to each underlying bar within half the configured bar interval. Unmatched bars are not forward-filled and fail the volume check. Offline replay can use the same separation with `--volume-confirmation-data <option-bars.csv|parquet>`; its timestamps must exactly match the underlying signal candles. Option volume confirms activity in that contract, not market-wide underlying participation.

The archive location can be changed in `kite_config.json` with:

```json
{
  "paper_trading_dir": "paper_trading_data"
}
```

### Morning Pre-Market Setup (8:00-9:15 AM)

#### 1. **Check System Health**
```bash
# Verify Python environment and dependencies
python -m pip list | grep -E "requests|websocket|pandas"

# Check config files are valid
python -c "import json; json.load(open('kite_config.json'))"
python -c "import json; json.load(open('config.json'))"
```

#### 2. **Verify Configuration**
Open `kite_config.json` and check:
```json
{
  "api_key": "your_key_here",
  "access_token": "valid_token",
  "market_close_time": "15:30",
  "bar_interval_seconds": 60,
  "stop_loss_pct": 0.75,
  "take_profit_pct": 1.5,
  "account_size": 100000,
  "risk_per_trade_pct": 1.0
}
```

#### 3. **Start the Bot**
```bash
# Terminal 1: Start Kite bot (intraday options; active config)
python run_kite_bot.py

# Expected output:
# 2026-08-12 09:15:00 - Connecting to Zerodha Kite...
# 2026-08-12 09:15:15 - Connected! Monitoring configured option contracts...
# 2026-08-12 09:16:00 - Bar complete: NIFTY 1-min
```

The active `kite_config.json` is options-only: `trading_mode` is
`intraday_options`, `futures_underlyings` is empty, and futures discovery is
disabled. The futures implementation remains available behind the existing
mode gate for a deliberate future migration back to `intraday_futures`.
Option paper positions must pass the configured premium stop-risk budget;
paper mode does not force an oversized minimum lot. The minimum is one lot,
but a one-lot position is still rejected whenever its planned stop-risk exceeds
the remaining per-trade or daily risk budget.
The active ₹100,000 paper account uses a 10% daily loss limit (₹10,000).
Option sizing uses the shared `max_risk_per_trade` cap, the configured option
premium-risk percentage, quantity bounds, and remaining daily risk. With the
current 10% premium stop and premium-risk percentage, a 65-unit NIFTY option at
₹100 premium has ₹650 planned stop risk, before the per-trade and daily limits
are applied. This sizing applies to PAPER and LIVE. Broker fills, slippage,
gaps, and costs can make realized losses exceed planned stop-risk; LIVE also
has execution-time post-fill safeguards. The staged first target is 10%, so
the nominal initial reward-to-risk is 1:1 before costs. After a restart,
same-session open paper
positions and realized losses are restored from the trade journal. Active
paper positions persist a price mark at most once per minute. Prior-session
open paper records are closed using the last persisted price and its update
time as a recovery mark when valid. If no valid mark exists, the bot closes
the record at its entry price as a zero-P&L estimate and labels the journal
reason accordingly. Neither recovery value is guaranteed to be the exchange's
official session-close price or actual realized performance.

Risk limits are enforced identically in PAPER and LIVE: an option stop may
not risk more than 10% of its deployed premium value, and the daily realized
loss ceiling may not exceed 10% of account capital. A stricter rupee
`max_risk_per_trade` or daily limit is allowed; configuration above either
10% ceiling is rejected. Daily realized losses accumulate gross losing-trade
P&L and are not offset by winners. At the daily limit, entries remain disabled
through the current IST session; LIVE cancels pending non-protective orders
and preserves protective stops attached to open positions. A failed
cancellation is logged and sent as an urgent notification. Stop execution,
gaps, costs, and slippage are not guaranteed to stay within the planned cap.

The shared option signal candle body/range ratio is 60%
(`option_min_candle_body_ratio`) in both modes. A prior 40% trial was reverted
after a two-session historical replay showed worse P/L and did not improve
trade count on the second session. Review rejection counts, entries, exits,
and P/L before deciding whether another strategy change is warranted. Signal
direction, option quote/quality, entry validation, and risk limits continue to
apply; the threshold does not guarantee an entry or demonstrate an edge.

### Config v2 option quote execution

For long option positions, config v2 evaluates initial, breakeven, and trailing
stops against a fresh quote: bid must be at or below the stop, quote age must
be no more than 60 seconds, and LTP must be inside the bid/ask spread. Invalid
quotes are ignored. A stale quote at a stop holds for one check; a second
consecutive stale check exits at the last valid bid with reason
`feed_failure_exit`.

Paper entries use ask and paper exits use bid when the quote is valid. LIVE
continues to use MARKET orders; actual broker fills are recorded and may differ
from the displayed ask or bid. Quote-validated LIVE stops are application
managed, not broker-side orders. A Kite disconnect pauses entries and warns
that open quote-managed options need manual protection until quote monitoring
is restored.

EMA re-entry keeps the existing crossover and close-confirmation rules. After
a stop-out, at most one re-entry is eligible until the configured entry cutoff;
a fresh option premium below the stop-out low cancels it. Re-entry trades are
tagged `ema_reentry`. Config v2 changes the strategy config hash; do not
compare its trade records as though they used the prior quote/stop behavior.

For the paper period, do not include SENSEX or TATAMOTORS in
`options_underlyings`. SENSEX BFO/BSE and TATAMOTORS option routing remains
available in code for future configuration; other configured option
underlyings use NFO contracts.

The configured entry cutoff is 45 minutes before the 15:30 IST close: no new
entries are allowed from 14:45 IST onward, including at 14:45. Existing
positions continue to be managed and follow the configured 15:15 IST forced
exit.

### VPS systemd setup

If using systemd on the VPS, install the service unit once, adjusting `User`,
`WorkingDirectory`, and the `/opt/sb-pr-dqp` paths in
`kite-trading-bot.service` if the repository is located elsewhere. Start the
service manually only after refreshing the daily Kite token:

```bash
sudo cp kite-trading-bot.service /etc/systemd/system/kite-trading-bot.service
sudo systemctl daemon-reload
```

Kite access tokens expire daily. Each trading day, refresh the token
interactively on the VPS first:

```bash
python run_kite_bot.py --authorize-only
```

The login callback listens on `127.0.0.1:8000`; when authorizing over SSH, keep
the existing SSH tunnel to that port open and complete the login in a local
browser. The fresh token is saved to `.env` for the systemd service. After
authorization succeeds, start the bot manually:

```bash
sudo systemctl start kite-trading-bot.service
```

Alternatively, run `python run_kite_bot.py` directly after refreshing the token.
Do not configure an automatic daily service start: the Kite token must be
refreshed first. If the token is not refreshed, service startup will fail closed
rather than place orders with an invalid session.

After installing the service, verify its settings:

```bash
systemctl show kite-trading-bot.service -p ExecStart -p Restart -p User -p WorkingDirectory
```

The bot exits normally after the 15:15 IST forced position exit, the 15:30 IST
market-close check, daily summary, and Friday weekly analysis have completed.
The unit uses `Restart=on-failure`, so clean end-of-day exits remain inactive while
crashes and unexpected network failures are retried:

```bash
systemctl status kite-trading-bot.service
journalctl -u kite-trading-bot.service -e
```

Keep the VPS service active from before 09:15 IST until the post-close report
finishes. Stopping or restarting it before then interrupts that run; the bot
does not publish a completed daily summary on interruption. The service sends
an interruption alert (including IST market phase and accepted-tick, completed
bar, and decision counts) when it receives the configured SIGINT stop signal.
Use these commands to confirm that the VPS actually ran through the session and
published the report:

```bash
journalctl -u kite-trading-bot.service --since "today 09:00" --until "today 16:15"
find paper_trading_data -path '*/day_*/daily_review.md' -printf '%T@ %p\n' | sort -nr | head
```

Use `systemctl stop kite-trading-bot.service` to stop it after close. `systemctl
restart kite-trading-bot.service` always starts a new process, even when the
previous process exited normally, so do not use `restart` as the end-of-day
stop command. Start it again manually only after refreshing the token for the
next session.

#### 4. **Monitor Real-Time Dashboard**
While bot runs, monitor:

| Metric | What to Watch | Action if Bad |
|--------|---------------|---------------|
| **Active Positions** | Count of open trades | Should be 1-3 max |
| **Last Trade Price** | Entry price vs current | If -2%, consider manual stop |
| **Win Rate (Live)** | % of closed trades won | Should be >50% |
| **Daily P&L** | Cumulative profit/loss | If -₹5,000, stop trading |
| **Telegram Alerts** | Receiving notifications? | Check token/chat_id if not |

#### 5. **Log File Monitoring**
Create a simple monitoring setup:

```bash
# Terminal 2: Watch trades in real-time
Get-Content trades.jsonl -Tail 5 -Wait  # PowerShell

# Look for entries like:
# {"timestamp": "2026-08-12 10:30:00", "symbol": "NIFTY24AUG22600CE", "signal": "BUY", "entry_price": 245.50, "quantity": 1}
```

#### 6. **Track Metrics on Spreadsheet**
Create `trading_log.csv`:

```
Date,Symbol,Time,EntryPrice,ExitPrice,Profit,PercentReturn,Signal,Status
2026-08-12,NIFTY,10:30,245.50,248.75,325,1.33,BUY,WIN
2026-08-12,BANKNIFTY,11:45,500.00,498.50,-150,-0.30,BUY,LOSS
```

---

## 📈 WEEKLY REVIEW (Every Friday End-of-Day)

### Step 1: Extract Weekly Metrics (Friday 3:30 PM)

Create `analyze_weekly.py`:

```python
import json
import pandas as pd
from datetime import datetime, timedelta

def analyze_trades():
    trades = []
    
    # Read all trades from this week
    with open('trades.jsonl', 'r') as f:
        for line in f:
            trade = json.loads(line)
            trade_date = datetime.strptime(trade['timestamp'], '%Y-%m-%d %H:%M:%S')
            if (datetime.now() - trade_date).days <= 7:  # Last 7 days
                trades.append(trade)
    
    df = pd.DataFrame(trades)
    
    # Calculate metrics
    print(f"""
    ===== WEEKLY ANALYSIS ({datetime.now().strftime('%Y-%m-%d')}  =====
    
    PERFORMANCE METRICS:
    - Total Trades: {len(df)}
    - Winning Trades: {len(df[df['profit'] > 0])} ({len(df[df['profit'] > 0])/len(df)*100:.1f}%)
    - Losing Trades: {len(df[df['profit'] <= 0])} ({len(df[df['profit'] <= 0])/len(df)*100:.1f}%)
    - Win Rate: {len(df[df['profit'] > 0])/len(df)*100:.1f}%
    
    PROFITABILITY:
    - Total Profit: ₹{df['profit'].sum():.2f}
    - Average Win: ₹{df[df['profit'] > 0]['profit'].mean():.2f}
    - Average Loss: ₹{df[df['profit'] <= 0]['profit'].mean():.2f}
    - Profit Factor: {df[df['profit'] > 0]['profit'].sum() / abs(df[df['profit'] <= 0]['profit'].sum()):.2f}
    
    RISK ANALYSIS:
    - Largest Win: ₹{df['profit'].max():.2f}
    - Largest Loss: ₹{df['profit'].min():.2f}
    - Average Trade Size: {df['quantity'].mean():.2f} lots
    
    BY SYMBOL:
    """)
    
    for symbol in df['symbol'].unique():
        sym_trades = df[df['symbol'] == symbol]
        win_rate = len(sym_trades[sym_trades['profit'] > 0]) / len(sym_trades) * 100
        print(f"  {symbol}: {len(sym_trades)} trades, {win_rate:.1f}% win, ₹{sym_trades['profit'].sum():.2f}")
    
    return df

if __name__ == '__main__':
    analyze_trades()
```

Run it:
```bash
python analyze_weekly.py > weekly_report.txt
```

### Step 2: Collect Input Data (Friday Evening)

Create `weekly_input_template.json`:

```json
{
  "week_ending": "2026-08-15",
  
  "SECTION 1: Market Conditions",
  "market_trend": "UPTREND",  // UPTREND / DOWNTREND / SIDEWAYS
  "market_volatility": "MEDIUM",  // LOW / MEDIUM / HIGH / EXTREME
  "best_trading_hours": "10:00-12:00, 13:00-14:30",  // When most wins occurred
  "worst_trading_hours": "09:15-09:30, 15:00-15:30",  // When most losses occurred
  "notes_on_market": "Week was choppy Wed-Thu, better Fri. Avoid opening hour.",
  
  "SECTION 2: Signal Quality",
  "false_signal_symbols": [
    "INFY",    // Too many whipsaws (stop using)
    "WIPRO"    // Wrong trend calls
  ],
  "best_signal_symbols": [
    "NIFTY",   // Consistent 65% win rate
    "BANKNIFTY"  // Good trending movement
  ],
  "signals_too_early": true,  // Entering before real move starts?
  "signals_too_late": false,   // Missing moves?
  
  "SECTION 3: Trade Management",
  "stop_loss_hit_count": 5,   // Number of trades hit stop loss
  "take_profit_hit_count": 8,  // Number of trades hit take profit
  "exit_too_early": true,      // Profit target too tight?
  "exit_too_late": false,      // Should have exited earlier?
  "manual_exits_count": 2,     // Trades manually exited by you
  "manual_exit_reason": "Gap risk at 3:10 PM",
  
  "SECTION 4: Filter Effectiveness",
  "volatility_filter_rejected": 15,  // Good signal rejected by volatility
  "confirmation_filter_rejected": 8,  // Good signal rejected by confirmation
  "cooldown_filter_rejected": 12,     // Entry prevented by cooldown
  "trading_hours_filter_rejected": 0, // Entries filtered out
  "false_positives_prevented": 20,    // Filters saved you from bad trades
  
  "SECTION 5: Improvements Needed",
  "biggest_issue": "Too many entries in sideways market",  // What hurt most
  "suggested_fix_1": "Add RSI divergence check",
  "suggested_fix_2": "Lower entry signal threshold on ranging days",
  "suggested_fix_3": "Add multi-timeframe confirmation (5-min trend)",
  
  "SECTION 6: Configuration Changes",
  "changes_to_make": [
    {
      "parameter": "stop_loss_pct",
      "current_value": 0.75,
      "suggested_value": 0.85,
      "reason": "Too tight, stopped out during normal pullbacks"
    },
    {
      "parameter": "take_profit_pct",
      "current_value": 1.5,
      "suggested_value": 2.0,
      "reason": "Moves often go to 2%+ on trending days"
    }
  ],
  
  "SECTION 7: Next Week Plan",
  "focus_areas": [
    "Reduce entries during 9:15-9:30 AM",
    "Skip INFY and WIPRO completely",
    "Increase take profit target",
    "Add liquidity check (volume-based)"
  ],
  "expected_improvement": {
    "win_rate_target": "65%",  // Current: 60%
    "trade_count_target": "10-12",  // Should be quality over quantity
    "daily_profit_target": "₹4,500"
  },
  
  "MANUAL NOTES": "This week was noisy. Wed-Thu saw 3 failed trades in choppy sideways market. Should improve with better volatility filter. Telegram notifications working well."
}
```

### Step 3: Fill Input Data (Friday 4:00-5:00 PM)

**Where to get this information:**

| Input | Where to Find | How to Measure |
|-------|---------------|----------------|
| **Best Trading Hours** | Look at `trades.jsonl` → Group by time → Calculate win% per hour | Excel pivot table |
| **Market Volatility** | Check Zerodha charts → ATR indicator → Compare to 30-day avg | High = >2% daily range |
| **False Signal Symbols** | Review trades → Which had most rapid reversals | Loss within 5 min of entry |
| **Stop Loss Hit Count** | Search `trades.jsonl` for `"exit_reason": "STOP_LOSS"` | Count occurrences |
| **Filter Effectiveness** | Add logging to accuracy_filters.py (see below) | Print rejection reasons |
| **Biggest Issue** | Review manual notes from the week | Ask: What hurt most? |

### Step 4: Evaluate Before Changing Code

Weekly suggestions are hypotheses, not instructions to bundle several edits. Before changing strategy or accuracy behavior:

1. Check [STRATEGY_CHANGELOG.md](STRATEGY_CHANGELOG.md) for the same issue or proposed change. Do not repeat a reverted or inconclusive experiment without new evidence and a documented reason.
2. Record the current code/config version, measured baseline, hypothesis, and one variable to change.
3. Make one change, then compare it against the same replay period or comparable paper-trading conditions. Record the outcome, including an inconclusive result, in the change log.
4. Keep or revert based on measured evidence, not an expected win rate or profit target. Do not move a strategy experiment to live trading based only on this review.

The existing weekly implementation guidance calls for at least 10 closed paper trades before a strategy change. Treat that as a minimum screening sample, not proof that a change improves performance; gather more data when results are mixed or uncertain.

---

## 📋 REQUIRED WEEKLY INPUT CHECKLIST

### Every Friday, You Need to Provide:

```
☐ Market Condition Assessment
  - Trend (UPTREND/DOWNTREND/SIDEWAYS)
  - Volatility level (LOW/MEDIUM/HIGH/EXTREME)
  - Best and worst trading hours

☐ Signal Quality Review
  - Which symbols had most false signals
  - Which symbols were most reliable
  - Were entries too early/late?

☐ Trade Management Analysis
  - How many stops vs. profits hit?
  - Exit prices: too tight or too loose?
  - Manual exits: why?

☐ Filter Performance
  - How many good signals were rejected?
  - Did filters prevent bad trades?
  - Any false rejections?

☐ Improvement Requests
  - Biggest issue that week
  - Candidate hypothesis and evidence (not a promised outcome)
  - Check STRATEGY_CHANGELOG.md for repeated or previously rejected changes

☐ Configuration Changes
  - Record current values and baseline before changing anything
  - Select at most one strategy/accuracy variable for the experiment
  - Record measured outcome and keep/revert/inconclusive decision in STRATEGY_CHANGELOG.md
```

---

## 🔧 ADD THIS LOGGING TO accuracy_filters.py

Modify to track filter rejections:

```python
# At top of accuracy_filters.py
import json
from datetime import datetime

class AccuracyFilters:
    def __init__(self):
        self.filter_stats = {
            'volatility_rejected': 0,
            'confirmation_rejected': 0,
            'cooldown_rejected': 0,
            'hours_rejected': 0,
            'threshold_rejected': 0,
            'approved_entries': 0
        }
    
    def validate_entry(self, symbol, signal, score, history, current_bar, previous_bar, current_time, hour, minute):
        """With logging for weekly analysis"""
        
        # Check each filter and log rejections
        volatility_ok = self.is_volatility_acceptable(history)
        if not volatility_ok:
            self.filter_stats['volatility_rejected'] += 1
            self.log_rejection(symbol, 'VOLATILITY', score)
            return False
        
        confirmation = self.has_confirmation(signal, current_bar, previous_bar)
        if not confirmation:
            self.filter_stats['confirmation_rejected'] += 1
            self.log_rejection(symbol, 'CONFIRMATION', score)
            return False
        
        should_enter = self.should_enter_trade(signal, score, volatility_ok, confirmation)
        if not should_enter:
            self.filter_stats['threshold_rejected'] += 1
            self.log_rejection(symbol, 'THRESHOLD', score)
            return False
        
        can_enter = self.can_enter_signal(symbol, current_time)
        if not can_enter:
            self.filter_stats['cooldown_rejected'] += 1
            self.log_rejection(symbol, 'COOLDOWN', score)
            return False
        
        good_hour = self.is_trading_hour_good(hour, minute)
        if not good_hour:
            self.filter_stats['hours_rejected'] += 1
            self.log_rejection(symbol, 'HOURS', score)
            return False
        
        # All filters passed
        self.filter_stats['approved_entries'] += 1
        self.log_approval(symbol, score)
        self.record_entry(symbol, current_time)
        return True
    
    def log_rejection(self, symbol, filter_name, score):
        """Log rejected signals for weekly review"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'filter': filter_name,
            'score': score,
            'action': 'REJECTED'
        }
        with open('filter_log.jsonl', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def log_approval(self, symbol, score):
        """Log approved signals"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'score': score,
            'action': 'APPROVED'
        }
        with open('filter_log.jsonl', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def get_weekly_stats(self):
        """Get filter statistics for weekly input"""
        return self.filter_stats

# In kite_main.py, at end of trading day:
# Print stats to console
# print(self.accuracy_filters.get_weekly_stats())
```

---

## 📊 WEEKLY IMPROVEMENT WORKFLOW

### Friday 4:00 PM: Data Collection
```bash
# 1. Generate weekly report
python analyze_weekly.py

# 2. Check filter statistics
grep -c "REJECTED" filter_log.jsonl
grep -c "APPROVED" filter_log.jsonl

# 3. Review all trades this week
tail -50 trades.jsonl
```

### Friday 5:00 PM: Analysis & Input
```bash
# Fill weekly_input_template.json with your observations
# Questions to answer:
# - Which 2-3 symbols worked best? (focus on these)
# - Which 1-2 symbols should we skip? (exclude from config)
# - What's the biggest problem? (1 specific issue)
# - What will fix it? (1-2 concrete changes)
```

### Monday 8:00 AM: Implementation
```bash
# Apply changes from weekly input
# 1. Update kite_config.json with new parameters
# 2. Add/remove symbols from configuration
# 3. Adjust filters in accuracy_filters.py if needed
# 4. Restart bot with new config
```

### Results Tracking (End of Week 2)
```
Week 1:  50% win rate  →  Week 2: 60% win rate  (+10%)
Week 2:  60% win rate  →  Week 3: 65% win rate  (+5%)
Week 3:  65% win rate  →  Week 4: 70% win rate  (+5%)
```

---

## 🎯 SAMPLE WEEKLY INPUT FILLED IN

Here's what you'll submit each Friday:

```json
{
  "week_ending": "2026-08-15",
  "market_trend": "UPTREND",
  "market_volatility": "MEDIUM",
  "best_trading_hours": "10:00-12:00",
  "worst_trading_hours": "09:15-09:30, 15:00-15:15",
  "false_signal_symbols": ["INFY", "WIPRO"],
  "best_signal_symbols": ["NIFTY", "BANKNIFTY", "TCS"],
  "signals_too_early": false,
  "signals_too_late": true,
  "stop_loss_hit_count": 4,
  "take_profit_hit_count": 12,
  "exit_too_early": false,
  "exit_too_late": true,
  "volatility_filter_rejected": 8,
  "confirmation_filter_rejected": 5,
  "cooldown_filter_rejected": 3,
  "false_positives_prevented": 16,
  "biggest_issue": "Exiting too early, missing big moves",
  "changes_to_make": [
    {
      "parameter": "take_profit_pct",
      "current_value": 1.5,
      "suggested_value": 2.5,
      "reason": "Moves go to 2-3% on trending days"
    }
  ],
  "expected_improvement": {
    "win_rate_target": "65%",
    "daily_profit_target": "₹5,000"
  }
}
```

---

## ✅ DAILY CHECKLIST

```
MORNING (8:00 AM):
☐ Check system dependencies
☐ Verify config files (valid JSON)
☐ Start bot with python run_kite_bot.py
☐ Monitor first 15 minutes for errors

DURING TRADING (9:15 AM - 3:15 PM):
☐ Watch active positions (max 3)
☐ Monitor daily P&L (stop if -₹5,000)
☐ Check Telegram alerts arriving
☐ Note any anomalies in trades.jsonl

CLOSING TIME (3:15 PM):
☐ Verify bot auto-exits all positions
☐ Check final daily P&L
☐ Note tomorrow's focus areas

EVENING (5:00 PM):
☐ Log manual observations in notebook
☐ Review filter_log.jsonl for rejections
☐ Spot any patterns (time, symbols, conditions)
```

---

## ✅ WEEKLY CHECKLIST (Every Friday)

```
ANALYSIS (4:00 PM):
☐ Run python analyze_weekly.py
☐ Extract key metrics (win rate, profit, trades)
☐ Group trades by symbol (which performed best)
☐ Group trades by time (which hours best)
☐ Review filter rejections (filter_log.jsonl)

INPUT COLLECTION (4:30 PM):
☐ Assess market condition (trend, volatility)
☐ Identify best 3 symbols (keep these)
☐ Identify worst 2 symbols (remove these)
☐ List biggest problem (1 specific issue)
☐ Suggest 2-3 fixes (concrete changes)
☐ Estimate improvement (new target metrics)

SUBMISSION (5:00 PM):
☐ Fill weekly_input_template.json
☐ Save as weekly_input_2026_08_15.json (use date)
☐ Share with me for code updates

IMPLEMENTATION (Monday 8:00 AM):
☐ Update kite_config.json with suggested changes
☐ Restart bot with new configuration
☐ Monitor first trades for improvements
```

---

## 📞 NEXT STEPS

**Today:**
1. Create `weekly_input_template.json` in your workspace
2. Add filter logging to `accuracy_filters.py` (code provided above)
3. Create `analyze_weekly.py` for automated metrics

**Tomorrow - Friday:**
1. Run bot normally all day
2. Collect data in `trades.jsonl` and `filter_log.jsonl`
3. At 4:00 PM, run analysis
4. Fill weekly input template

**Monday:**
1. Share weekly input with me
2. I'll provide updated code/config
3. You restart bot with improvements

**Weekly Cycle Repeats:**
Each Friday → Analysis → Input → Monday → Implementation → Improvement

---

## Questions I'll Ask You Weekly

When you submit weekly input, I'll review:

1. **Which symbols to KEEP** (Best performers)
2. **Which symbols to REMOVE** (Most false signals)
3. **What configuration to CHANGE** (Stop loss, take profit, hours)
4. **What filter to ADD/ADJUST** (New rules needed)
5. **Expected impact** (Target win rate, daily profit)

Then I'll give you updated code to use the following Monday.

---

**Ready to start? First daily run is tomorrow!** 🚀
