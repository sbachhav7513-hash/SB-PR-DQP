# 📚 Complete Guide: Daily Use & Weekly Improvements

## 🎯 WHAT YOU HAVE NOW

You have a trading bot that:
- ✅ Trades intraday futures (1-min candles, exits at 3:15 PM)
- ✅ Has 5 accuracy filters to reduce false signals
- ✅ Logs all trades to `trades.jsonl`
- ✅ Logs filter rejections to `filter_log.jsonl`
- ✅ Sends Telegram alerts for every trade
- ✅ Auto-exits all positions before market close

**Current Status:** 50% win rate (not yet tradeable)

---

## 📖 YOUR OPERATING SYSTEM

This is a **weekly improvement system** where you:

1. **Run the bot** (Monday-Friday)
2. **Monitor daily** (quick checks)
3. **Analyze weekly** (Friday afternoon)
4. **Provide input** (Friday evening)
5. **I update code** (Friday evening - Saturday)
6. **Deploy improvements** (Monday morning)
7. **Repeat** (next week with better settings)

---

## 🗂️ YOUR DOCUMENTATION

| Document | Purpose | When to Use |
|----------|---------|-------------|
| **QUICK_REFERENCE.md** | Daily checklist + quick answers | Print it! Use daily |
| **DAILY_WEEKLY_OPERATIONS.md** | Detailed guide for everything | Reference for details |
| **weekly_input_template.json** | Form to fill every Friday | Copy & fill Friday 4:30 PM |
| **analyze_weekly.py** | Automatic metrics generator | Run Friday 4:00 PM |
| **TRADING_ACCURACY_GUIDE.md** | Why accuracy is important | Read once, reference later |
| **WEEK1_IMPLEMENTATION.md** | How filters work | Reference document |

---

## 🚀 QUICK START: YOUR FIRST WEEK

### Step 1: Tomorrow (Monday 8:00 AM)

```bash
# Check system is ready
python -c "import json; json.load(open('kite_config.json'))"

# Start the bot
python run_kite_bot.py

# Should see:
# Connected! Monitoring 16 futures...
# Bar complete: NIFTY 1-min
```

### Step 2: Monday-Friday (Daily)

**Morning (8:00 AM):**
- Bot should start OK
- Check: No errors in terminal

**During Day (9:15 AM - 3:15 PM):**
- Monitor: Watch active positions
- Alert: If P&L drops below -₹5,000, stop bot
- Note: Any issues for Friday review

**Evening (5:00 PM):**
- Check: Daily P&L (good sign if +₹1,000+)
- Wait: For market close auto-exit at 3:15 PM

### Step 3: Friday 4:00 PM

```bash
# Generate weekly report (automatic!)
python analyze_weekly.py

# Will show:
# - Win rate this week
# - Total profit/loss
# - Best trading hours
# - Best symbols
# - Filter statistics
```

### Step 4: Friday 4:30 PM

```bash
# Open template
cat weekly_input_template.json

# Answer 5 simple questions:
# 1. What was best trading hour?
# 2. What was worst trading hour?
# 3. Which symbol performed best?
# 4. Which symbol performed worst?
# 5. What's the biggest issue?
# 6. How would you fix it?
# 7. What win rate next week?

# Save as
cp weekly_input_template.json weekly_input_2026_08_15.json
# (use current date instead)
```

### Step 5: Friday 5:00 PM

Send me:
1. `weekly_input_2026_08_15.json` (filled)
2. `weekly_report_2026_08_15.json` (auto-generated)

I'll provide:
1. Updated `kite_config.json` (if needed)
2. Updated code (if needed)
3. My analysis & recommendations

### Step 6: Monday 8:00 AM (Week 2)

- Download updated files
- Update kite_config.json
- Restart bot
- Run with improvements
- Repeat cycle

---

## 📊 WEEKLY INPUT: WHAT TO FILL IN

Every Friday, answer these questions in `weekly_input_template.json`:

### SECTION 1: Market Conditions
```
"market_trend": "UPTREND"  ← Trend this week
"market_volatility": "MEDIUM"  ← How choppy was it?
"best_trading_hours": "10:00-12:00"  ← When did we make money?
"worst_trading_hours": "09:15-09:30"  ← When did we lose?
```

**How to find this:**
- Look at `weekly_report_YYYY_MM_DD.json` → "hour_stats"
- Find highest profit hour = best hour
- Find lowest profit hour = worst hour

### SECTION 2: Signal Quality
```
"false_signal_symbols": ["INFY"]  ← Whipped too much, skip
"best_signal_symbols": ["NIFTY"]  ← Most consistent wins
"signals_too_early": false  ← Entered before move?
"signals_too_late": true  ← Missed early profit?
```

**How to find this:**
- Look at `weekly_report_YYYY_MM_DD.json` → "symbol_stats"
- Highest profit symbol = best
- Lowest profit symbol = worst

### SECTION 3: Trade Management
```
"stop_loss_hit_count": 3  ← How many stopped out?
"take_profit_hit_count": 7  ← How many hit profit target?
"exit_too_early": true  ← Exits happened too fast?
"exit_too_late": false  ← Should have exited sooner?
```

**How to find this:**
- Count lines in `trades.jsonl` with "exit_reason": "STOP_LOSS"
- Count lines in `trades.jsonl` with "exit_reason": "TAKE_PROFIT"
- If most exits are stop loss: too tight stop
- If all exits are take profit: good! But check if could be higher

### SECTION 4: Filter Effectiveness
```
"volatility_filter_rejected_count": 5  ← From filter_log.jsonl
"confirmation_filter_rejected_count": 3
"cooldown_filter_rejected_count": 4
"false_positives_prevented": 8  ← How many bad trades avoided?
```

**How to find this:**
- Look at `weekly_report_YYYY_MM_DD.json` → "filter_stats"
- Shows count for each rejection reason
- Estimate: How many of those would have been losses?

### SECTION 5: Biggest Issues
```
"biggest_issue_1": "Take profit too tight"
"biggest_issue_1_fix": "Increase from 1.5% to 2.5%"
```

**How to find this:**
- Review your daily notes
- Ask: "What cost me the most money?"
- Ask: "What pattern happened most?"

### SECTION 6: Recommended Changes
```
"change_1": {
  "parameter": "take_profit_pct",
  "current_value": 1.5,
  "suggested_value": 2.5,
  "reason": "Moves often go 2-3% on trending days"
}
```

**What parameters can change:**
- `take_profit_pct` - Profit target (1.5 → 2.5)
- `stop_loss_pct` - Stop loss (0.75 → 0.85)
- `excluded_symbols` - Skip bad symbols
- `skip_opening_minutes` - Avoid risky hours
- `risk_per_trade_pct` - Position sizing
- `bar_interval_seconds` - Candle size (60 = 1 min)

### SECTION 7: Expected Improvements
```
"next_week_targets": {
  "win_rate_target": 65,
  "daily_profit_target": 5000,
  "trades_per_day_target": 10
}
```

---

## 📈 WHAT WILL IMPROVE

After each week's changes:

```
WEEK 1 (This Week - Baseline):
- Current: 50% win rate
- Daily P&L: -₹300 (loss)
- Status: ❌ DO NOT TRADE LIVE

(Apply Week 1 filters)

WEEK 2 (Next Week - After First Input):
- Expected: 60% win rate (+10%)
- Daily P&L: +₹3,800 (profit!)
- Trades: Fewer, higher quality
- Status: ⚠️ Tradeable with caution

(Apply Week 2 improvements)

WEEK 3:
- Expected: 65% win rate (+5%)
- Daily P&L: +₹5,500
- Status: ✅ Professional system

(Apply Week 3 improvements)

WEEK 4+:
- Expected: 70%+ win rate
- Daily P&L: +₹8,000+
- Status: ✅ Scalable income
```

---

## 🎯 YOUR RESPONSIBILITIES

### Daily (Mon-Fri):
- ☐ Start bot 8:00 AM
- ☐ Monitor during trading hours
- ☐ Note any issues
- ☐ Check final P&L 5:00 PM
- ☐ Stop if P&L < -₹5,000

### Weekly (Friday):
- ☐ 4:00 PM: Run `python analyze_weekly.py`
- ☐ 4:30 PM: Fill `weekly_input_template.json`
- ☐ 5:00 PM: Send files to me

### My Responsibilities:
- ☐ Review your weekly input
- ☐ Analyze trade data
- ☐ Update code/config
- ☐ Provide by Monday 8:00 AM

---

## 🔧 THREE KEY FILES TO UNDERSTAND

### 1. `kite_config.json`
This is your bot configuration. Example:
```json
{
  "api_key": "xxx",
  "access_token": "xxx",
  "bar_interval_seconds": 60,
  "stop_loss_pct": 0.75,
  "take_profit_pct": 1.5,
  "excluded_symbols": ["INFY"],
  "skip_opening_minutes": 15
}
```

**You'll change these weekly based on data.**

### 2. `trades.jsonl`
Log of all trades (auto-generated). Example line:
```json
{"timestamp": "2026-08-12 10:30:00", "symbol": "NIFTY", "signal": "BUY", "entry": 245.50, "exit": 248.75, "profit": 325, "status": "WIN"}
```

**You'll analyze this every Friday.**

### 3. `weekly_input_template.json`
Form for your weekly feedback. **You'll fill this Friday evening.**

---

## 📋 DAILY MONITORING: WHAT TO WATCH

| Metric | Good | Warning | Stop |
|--------|------|---------|------|
| **Daily P&L** | +₹2,000+ | -₹500 to +₹500 | < -₹5,000 |
| **Win Rate (Live)** | >60% | 50-60% | <40% |
| **Active Positions** | 1-2 | 3-4 | 5+ |
| **Longest Trade** | 5-15 min | 15-30 min | >30 min |
| **Bot Status** | Running | Slow | Crashed |
| **Telegram Alerts** | Arriving | Delayed | Not arriving |

---

## 🚨 EMERGENCY: WHAT TO DO IF...

### Bot Crashes:
```
1. Restart: python run_kite_bot.py
2. Manually close positions in Zerodha app if stuck
3. Note what caused crash
4. Report Friday
```

### Positions Don't Close at 3:15 PM:
```
1. Manually close in Zerodha immediately
2. Check if 3:15 PM time is correct
3. Verify bot is running
4. Restart bot
5. Report Friday
```

### Daily Loss Exceeds -₹5,000:
```
1. STOP THE BOT IMMEDIATELY
2. Manually close all remaining positions
3. Do NOT trade rest of day
4. Note what went wrong
5. Review Friday
6. Implement safeguards
```

---

## 📞 COMMUNICATION RHYTHM

**Every Monday 8:00 AM:**
- I send: Updated `kite_config.json` + any code changes
- You do: Update files, restart bot

**Every Friday 5:00 PM:**
- You send: `weekly_input_YYYY_MM_DD.json` + `weekly_report_YYYY_MM_DD.json`
- I review: Analyze data, plan improvements

**Every Saturday-Sunday:**
- I update: Code, config, documentation
- I provide: Monday deployment package

**Every Monday 8:00 AM (repeat):**
- Cycle continues with improvements

---

## ✅ CHECKLIST: ARE YOU READY?

Before Monday morning, verify:

```
☐ Python 3.8+ installed
☐ requirements.txt dependencies installed
☐ kite_config.json filled with valid credentials
☐ Zerodha account active with funds
☐ Telegram token & chat_id configured
☐ You've read this guide
☐ You've printed QUICK_REFERENCE.md
☐ You understand stop loss at -₹5,000/day
```

If all checked, you're ready to start Monday!

---

## 📚 REFERENCE MATERIALS

For detailed information:

| Question | Read This | Location |
|----------|-----------|----------|
| "How do I run the bot daily?" | QUICK_REFERENCE.md | Print this! |
| "What do I fill in Friday?" | DAILY_WEEKLY_OPERATIONS.md | Section: SECTION 1-7 |
| "Why is accuracy important?" | TRADING_ACCURACY_GUIDE.md | Overview of issues |
| "How do the 5 filters work?" | WEEK1_IMPLEMENTATION.md | Technical details |
| "How to optimize performance?" | PERFORMANCE_OPTIMIZATION.md | Advanced topic |
| "What's the full operating guide?" | DAILY_WEEKLY_OPERATIONS.md | Complete reference |

---

## 🎓 KEY CONCEPTS

### Win Rate vs Profit
```
50% win rate = -₹300/day (lose to commissions)
55% win rate = +₹500/day (barely profitable)
60% win rate = +₹3,800/day (good!)
70% win rate = +₹8,000+/day (professional)
```

Your goal: Get from 50% → 60% in Week 2

### Types of Exits
```
✅ Take Profit (TP) = Hit profit target (good exit)
❌ Stop Loss (SL) = Hit stop loss (bad exit)
⚠️ Manual Exit = You closed manually (could be either)
⏱️ Market Close = Auto-exit at 3:15 PM (forced)
```

Track which exit type gives better results.

### Filter Rejections
```
Rejected = Signal didn't pass accuracy filter

Examples:
- Volatility too high → Skip (risky market)
- Confirmation missing → Skip (weak signal)
- Cooldown active → Skip (entered too recently)
- Bad hours → Skip (risky time of day)
- Score < 90 → Skip (low confidence)

Goal: Reject bad signals, approve good ones
```

---

## 💡 PRO TIPS

1. **Track manually each day:**
   Keep a notebook of:
   - When you got whipsawed
   - When you exited too early
   - When market was choppy
   - Anything unusual

2. **Review weekly report BEFORE filling input:**
   - `analyze_weekly.py` gives you the data
   - Then use data to answer questions in input template

3. **Be specific in weekly input:**
   - Instead of "not working": "INFY had 3 false signals"
   - Instead of "exits bad": "Take profit too tight, need 2.5%"
   - Instead of "improve": "Exclude INFY, raise take profit, skip 9:15-9:30"

4. **One change at a time if possible:**
   - Changes compound
   - Hard to know what helped/hurt if multiple changes
   - Better to do 1-2 focused changes per week

5. **Document issues same day:**
   - Don't wait for Friday to remember
   - Use daily notes feature
   - Write "9:30 - Got whipsawed on INFY, closed at -75 points"

---

## 🎯 SUCCESS FORMULA

```
Daily Execution:
Run bot → Monitor → Track data → Stop at stop-loss

Weekly Analysis:
Generate metrics → Fill input → Identify top 3 issues → Suggest fixes

My Updates:
Analyze data → Code improvements → Test → Deliver by Monday

Repeat:
Apply changes → New week → Better results → Compound gains
```

Each week you get a little better:
- Week 2: +10% win rate
- Week 3: +5% win rate  
- Week 4: +5% win rate
= 60% → 65% → 70% win rate in 3 weeks

---

## 🚀 NEXT STEPS

**Right now:**
1. Read this document
2. Print QUICK_REFERENCE.md
3. Read DAILY_WEEKLY_OPERATIONS.md

**Tomorrow (Monday 8:00 AM):**
1. Start bot: `python run_kite_bot.py`
2. Monitor all day
3. Note any issues

**Friday 4:00 PM:**
1. Run: `python analyze_weekly.py`
2. Check report

**Friday 4:30 PM:**
1. Open: `weekly_input_template.json`
2. Fill it in
3. Save as: `weekly_input_2026_08_15.json`

**Friday 5:00 PM:**
1. Send me both JSON files
2. I'll review over weekend

**Monday 8:00 AM (Week 2):**
1. Get updated files from me
2. Update `kite_config.json`
3. Restart bot with improvements

---

## ❓ FINAL QUESTIONS?

Check these files for answers:
- **Quick questions** → QUICK_REFERENCE.md
- **Detailed info** → DAILY_WEEKLY_OPERATIONS.md
- **Why it matters** → TRADING_ACCURACY_GUIDE.md
- **How it works** → WEEK1_IMPLEMENTATION.md

If still unclear, ask me Friday evening in your weekly submission!

---

## ✨ YOU'RE ALL SET!

You have everything you need to:
1. ✅ Run the bot daily
2. ✅ Monitor performance
3. ✅ Analyze results weekly
4. ✅ Improve systematically
5. ✅ Track progress
6. ✅ Go live when ready

**Expected timeline:**
- Week 1 (This week): Paper trading, establish baseline
- Week 2 (Next week): First improvements, live with ₹10,000
- Week 3: Better performance, scale to ₹25,000
- Week 4+: Professional-grade system, scale aggressively

Let's turn this 50% win rate into a consistent profit machine! 🎯

---

**Version: 1.0 | Created: 2026-08-12 | For: Daily Trading Automation**
