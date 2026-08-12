# 📋 Weekly Input Guide: Exactly What I Need From You

## Every Friday at 5:00 PM, Send Me 2 Files

### FILE 1: `weekly_input_2026_08_15.json` (FILLED BY YOU)
### FILE 2: `weekly_report_2026_08_15.json` (AUTO-GENERATED)

---

## How to Generate FILE 2 (Automatic)

### Friday 4:00 PM
```bash
# Run this ONE command
python analyze_weekly.py

# Output will be:
# ✅ Detailed report in terminal
# ✅ Saved to: weekly_report_2026_08_15.json
```

That's it! The report is automatically generated.

---

## How to Generate FILE 1 (You Fill This)

### Friday 4:30 PM

```bash
# Option A: Open template
cat weekly_input_template.json

# Option B: Edit in VS Code
code weekly_input_template.json

# Option C: View raw
type weekly_input_template.json  # Windows PowerShell
```

Copy the entire content, create new file named `weekly_input_2026_08_15.json` (use current date), and fill in your answers.

---

## What to Fill in weekly_input_YYYY_MM_DD.json

### PART 1: Market Conditions (Copy from your report!)

```json
"market_trend": "UPTREND",  
// Look at report → "Daily Range" was up/down/sideways?
// Values: UPTREND, DOWNTREND, SIDEWAYS, CHOPPY

"market_volatility": "MEDIUM",
// Look at report → "Largest Loss" was -300 points?
// Values: LOW (tiny moves), MEDIUM (1-2%), HIGH (2-5%), EXTREME (5%+)

"best_trading_hours": "10:00-12:00",
// Look at report → HOUR_STATS → Find highest profit hour
// Example: "10:00-12:00" or "13:00-14:30" (use IST format)

"worst_trading_hours": "09:15-09:30",
// Look at report → HOUR_STATS → Find lowest profit hour
// Example: "09:15-09:30" or "15:00-15:15"
```

**How to find this in the report:**
```
Report shows:
⏰ PERFORMANCE BY HOUR
   Hour      Trades  Wins  Win%    Profit
   09:00      4      1     25%    ₹-400
   10:00      5      4     80%    ₹2,100  ← BEST HOUR
   11:00      3      2     67%    ₹1,200
   ...
   15:00      2      0      0%    ₹-800  ← WORST HOUR
```

Copy the times from the "Profit" column!

---

### PART 2: Signal Quality (Copy from your report!)

```json
"false_signal_symbols": ["INFY", "WIPRO"],
// Look at report → SYMBOL_STATS → Find worst performers
// Copy symbols with lowest profit

"best_signal_symbols": ["NIFTY", "BANKNIFTY", "TCS"],
// Look at report → SYMBOL_STATS → Find best performers
// Copy symbols with highest profit

"signals_too_early": false,
// Did we enter and immediately bounce back down?
// YES = true, NO = false

"signals_too_late": true,
// Did we enter after the big move already happened?
// YES = true, NO = false
```

**How to find this in the report:**
```
Report shows:
📍 PERFORMANCE BY SYMBOL
   Symbol         Trades  Wins  Win%    Profit
   NIFTY              5     4     80%   ₹2,200  ← BEST
   BANKNIFTY          4     3     75%   ₹1,800
   TCS                3     2     67%   ₹900
   INFY               3     1     33%   ₹-350  ← WORST
   WIPRO              2     0      0%   ₹-200  ← WORST
```

Add best symbols to `best_signal_symbols`
Add worst symbols to `false_signal_symbols`

---

### PART 3: Trade Management (Count from trades.jsonl)

```json
"total_trades_this_week": 12,
// Count total lines in trades.jsonl

"winning_trades": 7,
// Count lines with "profit" > 0

"losing_trades": 5,
// Count lines with "profit" <= 0

"win_rate_percent": 58.3,
// Calculate: (winning_trades / total_trades) * 100

"stop_loss_hit_count": 3,
// Count lines with "exit_reason": "STOP_LOSS"

"take_profit_hit_count": 7,
// Count lines with "exit_reason": "TAKE_PROFIT"

"manual_exits_count": 2,
// Count lines with "exit_reason": "MANUAL"

"exit_too_early": true,
// Did most exits happen at take profit? YES = true
// Did we hit take profits but could have gone higher? true

"exit_too_late": false,
// Did we hold too long and hit stop loss? YES = true
```

**How to count in trades.jsonl:**
```bash
# Count winning trades (profit > 0)
grep -o '"profit": [0-9]*' trades.jsonl | wc -l

# Count stop loss hits
grep -c "STOP_LOSS" trades.jsonl

# Count take profit hits
grep -c "TAKE_PROFIT" trades.jsonl
```

Or just read the auto-generated report:
```
Report shows:
📈 PERFORMANCE SUMMARY
   Total Trades:        12
   Winning Trades:      7 (58.3%)
   Losing Trades:       5 (41.7%)
```

Copy these directly!

---

### PART 4: Filter Effectiveness

```json
"volatility_filter_rejected_count": 5,
// Look at report → FILTER_STATISTICS
// Shows how many signals were rejected by each filter

"confirmation_filter_rejected_count": 3,
"cooldown_filter_rejected_count": 4,
"trading_hours_filter_rejected_count": 0,

"total_signals_rejected": 12,
// Sum of all rejected counts above

"false_positives_prevented": 8,
// Estimate: Of the 12 rejected signals, how many would have LOST?
// Look at the trends and guess
// Conservative: Assume half (12 ÷ 2 = 6)
// Realistic: Estimate based on market (could be 5-10)

"filters_helped": true
// Did filters prevent more losses than they prevented wins?
// YES = true, NO = false
```

**How to find this in the report:**
```
Report shows:
🔍 FILTER STATISTICS
   Volatility Rejected:       5
   Confirmation Rejected:     3
   Cooldown Rejected:         4
   Hours Rejected:            0
   Threshold Rejected:        0
   Total Rejected:           12
   Approved Entries:          6
```

Copy these numbers directly!

---

### PART 5: Biggest Issues (Your Opinion!)

```json
"biggest_issue_1": "Take profit too tight",
// What caused most losses? Think about it.
// Examples:
// - "Take profit target too tight (1.5%)"
// - "Entries on INFY whipsawed too much"
// - "Trading 9:15-9:30 AM volatile"
// - "Too many positions open at once"
// - "Stop loss hitting too often"

"biggest_issue_1_impact": "Missed moves that went to 2-3%",
// How did this hurt? (1-2 sentences)

"biggest_issue_1_priority": "HIGH"
// Is this important? HIGH, MEDIUM, LOW
```

**How to identify issues:**
1. Review your daily notes
2. Think: "What cost me the most money this week?"
3. Write that down

Examples:
- Lost ₹1,200 on whipsaws? → "Too many entries in choppy hours"
- Missed profitable moves? → "Exit too early - take profit tight"
- Got stopped out multiple times? → "Stop loss too tight"

---

### PART 6: Recommended Changes (Based on Issues)

```json
"change_1": {
  "parameter": "take_profit_pct",
  "current_value": 1.5,
  "suggested_value": 2.5,
  "reason": "Moves often go 2-3% on trending days. 1.5% too tight."
}
```

**For change_1, I'll ask you:**
- **What parameter:** What config setting needs to change?
- **Current value:** What is it now? (from kite_config.json)
- **Suggested value:** What should it be?
- **Reason:** Why? (1-2 sentences)

**What parameters can change:**
```
"take_profit_pct": 1.5      → Change to 2.0, 2.5, 3.0, etc
"stop_loss_pct": 0.75       → Change to 0.85, 0.95, etc
"bar_interval_seconds": 60  → Change to 300 (5-min) if too noisy
"excluded_symbols": []      → Add ["INFY", "WIPRO"] to skip
"skip_opening_minutes": 15  → Change to 20, 30 if opening too bad
```

**Example fills:**
```json
"change_2": {
  "parameter": "excluded_symbols",
  "current_value": [],
  "suggested_value": ["INFY", "WIPRO"],
  "reason": "Both had poor signal quality. INFY: 1/3 profitable. WIPRO: 0/2 profitable. Skip both."
}

"change_3": {
  "parameter": "skip_opening_minutes",
  "current_value": 0,
  "suggested_value": 20,
  "reason": "First 20 minutes (9:15-9:35) very volatile. Lost ₹400 in opening trades. Better to wait for market to settle."
}
```

---

### PART 7: Expected Improvements (Your Prediction!)

```json
"current_metrics": {
  "win_rate": 58.3,
  "daily_profit": 3200,
  "trades_per_day": 12
},

"next_week_targets": {
  "win_rate_target": 65,
  // If we make these changes, what win rate do you expect?
  // Conservative: +5% (so 58% → 63%)
  // Realistic: +7% (so 58% → 65%)
  // Optimistic: +10% (so 58% → 68%)

  "daily_profit_target": 5000,
  // Expected daily profit next week (₹)

  "trades_per_day_target": 10,
  // Expected trade count (quality over quantity)

  "confidence_level": "HIGH"
  // Do you believe in these changes? HIGH, MEDIUM, LOW
}
```

**How to estimate:**
- Conservative: Add 5% to current
- Realistic: Add 7-10% based on the changes
- Optimistic: Add 12-15% if very confident

Example:
```
This week:  58.3% win rate
Add 7%:     65.3% win rate (realistic target)
Add 5%:     63.3% win rate (conservative)
Add 10%:    68.3% win rate (if very confident)

Pick one for "next_week_targets"
```

---

## Example: Completed weekly_input_2026_08_15.json

```json
{
  "week_ending": "2026-08-15",
  "submitted_by": "Your Name",
  
  "market_trend": "UPTREND",
  "market_volatility": "MEDIUM",
  "best_trading_hours": "10:00-12:00, 13:00-14:30",
  "worst_trading_hours": "09:15-09:30, 15:00-15:15",
  
  "false_signal_symbols": ["INFY", "WIPRO"],
  "best_signal_symbols": ["NIFTY", "BANKNIFTY", "TCS"],
  "signals_too_early": false,
  "signals_too_late": true,
  
  "total_trades_this_week": 12,
  "winning_trades": 7,
  "losing_trades": 5,
  "win_rate_percent": 58.3,
  "stop_loss_hit_count": 3,
  "take_profit_hit_count": 7,
  "manual_exits_count": 2,
  "exit_too_early": true,
  "exit_too_late": false,
  
  "volatility_filter_rejected_count": 5,
  "confirmation_filter_rejected_count": 3,
  "cooldown_filter_rejected_count": 4,
  "trading_hours_filter_rejected_count": 0,
  "false_positives_prevented": 8,
  
  "biggest_issue_1": "Exit too early - take profit target too tight",
  "biggest_issue_1_impact": "Missed moves that went to 2-3%, only captured 1.5%",
  
  "biggest_issue_2": "Entries on INFY whipsawed too much",
  "biggest_issue_2_impact": "3 trades on INFY, only 1 win, 2 losses. Skip INFY completely.",
  
  "change_1": {
    "parameter": "take_profit_pct",
    "current_value": 1.5,
    "suggested_value": 2.5,
    "reason": "Moves often go 2-3% on trending days. 1.5% too tight. Should capture more."
  },
  
  "change_2": {
    "parameter": "excluded_symbols",
    "current_value": [],
    "suggested_value": ["INFY", "WIPRO"],
    "reason": "INFY: 1/3 profitable. WIPRO: 0/2 profitable. Both whipsaw. Skip them."
  },
  
  "change_3": {
    "parameter": "skip_opening_minutes",
    "current_value": 0,
    "suggested_value": 20,
    "reason": "First 20 min very volatile. 9:15-9:35 lost ₹400. Better to wait for settle."
  },
  
  "next_week_targets": {
    "win_rate_target": 65,
    "daily_profit_target": 5000,
    "trades_per_day_target": 10,
    "confidence_level": "HIGH"
  },
  
  "manual_notes": "Week was good overall, but exiting too early cost a lot. INFY especially bad. Opening hour very choppy. If we make these 3 changes, should be much better next week."
}
```

---

## The Two Files Side by Side

| File 1: YOUR INPUT | File 2: AUTO-GENERATED |
|------------------|----------------------|
| `weekly_input_2026_08_15.json` | `weekly_report_2026_08_15.json` |
| You fill this Friday 4:30 PM | Script generates Friday 4:00 PM |
| Your answers & observations | Metrics & statistics |
| What you think was good/bad | What the data shows |
| Your suggestions for changes | Proof of the changes needed |
| 7 sections to answer | 3 sections: metrics, symbols, hours |

**I need BOTH to:**
1. Verify your observations match data
2. Understand your thinking
3. Make smart code updates
4. Track improvement week-to-week

---

## Friday 5:00 PM Submission Template

When you send me both files:

```
Subject: Weekly Trading Input - Week of 2026-08-15

Attached files:
1. weekly_input_2026_08_15.json (filled by you)
2. weekly_report_2026_08_15.json (auto-generated)

Any questions/concerns:
- (Optional manual notes)

Expected next week:
- 65% win rate
- ₹5,000+ daily profit
```

---

## Checklist: What I Check When You Send Files

When you send weekly input, I verify:

```
✓ File 1: weekly_input_YYYY_MM_DD.json
  ✓ Valid JSON format
  ✓ All 7 sections filled
  ✓ Answers are specific (not vague)
  ✓ Numbers match the report

✓ File 2: weekly_report_YYYY_MM_DD.json
  ✓ Auto-generated (has metrics)
  ✓ Shows win rate & P&L
  ✓ Shows best/worst hours & symbols
  ✓ Shows filter rejections

✓ Data Quality
  ✓ At least 5 trades in the report
  ✓ Weekly P&L is clear
  ✓ Your input matches data
  ✓ Changes are reasonable
```

If everything checks out:
- I update code/config
- Deliver by Monday 8 AM
- You restart bot with improvements

---

## Next Steps

**This Week (Mon-Fri):**
1. Run bot normally
2. Collect data automatically
3. Don't worry about anything else

**Friday 4:00 PM:**
```bash
python analyze_weekly.py
# Creates: weekly_report_2026_08_15.json
```

**Friday 4:30 PM:**
1. Copy `weekly_input_template.json`
2. Name it `weekly_input_2026_08_15.json`
3. Fill in all sections (use this guide!)
4. Save it

**Friday 5:00 PM:**
Send me both JSON files

**Monday 8:00 AM:**
Get updated config from me
Restart bot
Repeat!

---

**You're ready! Just fill this form every Friday and I'll handle the rest! 🎯**
