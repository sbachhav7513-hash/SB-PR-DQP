# Daily & Weekly Operations Guide

## 📊 DAILY USAGE (What to Do Every Trading Day)

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
  "market_close_time": "15:15",
  "bar_interval_seconds": 60,
  "stop_loss_pct": 0.75,
  "take_profit_pct": 1.5,
  "account_size": 100000,
  "risk_per_trade_pct": 1.0
}
```

#### 3. **Start the Bot**
```bash
# Terminal 1: Start Kite bot (intraday futures)
python run_kite_bot.py

# Expected output:
# 2026-08-12 09:15:00 - Connecting to Zerodha Kite...
# 2026-08-12 09:15:15 - Connected! Monitoring 16 futures...
# 2026-08-12 09:16:00 - Bar complete: NIFTY 1-min
```

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

### Step 4: Update Code Based on Weekly Input

Example adjustments for `kite_config.json`:

```json
{
  "MONDAY CHANGES": {
    "stop_loss_pct": 0.85,     // Increased from 0.75 (was too tight)
    "take_profit_pct": 2.0,     // Increased from 1.5 (needs more room)
    "excluded_symbols": ["INFY", "WIPRO"],  // Add to skip list
    "skip_hours": [[9, 15, 9, 30], [15, 0, 15, 30]]  // Skip risky hours
  }
}
```

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
  - 3 specific fixes to try
  - Expected improvement target

☐ Configuration Changes
  - What parameters to adjust
  - Why each change needed
  - Expected impact
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
