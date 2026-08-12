# Quick Reference: Daily & Weekly Workflow

## 🚀 START OF WEEK (Monday Morning)

```bash
# 1. Update configuration with last week's improvements
nano kite_config.json  # Apply changes from weekly input

# 2. Verify config is valid
python -c "import json; json.load(open('kite_config.json'))"

# 3. Start bot
python run_kite_bot.py

# 4. Monitor in another terminal
Get-Content trades.jsonl -Tail 5 -Wait  # PowerShell - watch trades in real-time
```

---

## 📅 DURING WEEK (Monday-Thursday)

| Time | What to Do | Why |
|------|-----------|-----|
| **8:00 AM** | Check bot starts OK | Catch any config errors early |
| **9:15 AM** | Monitor first 30 min | Opening hour is risky |
| **10:00 AM - 3:00 PM** | Light monitoring | Check P&L every 30 min |
| **3:10 PM** | Verify auto-exit ready | Ensure all positions close by 3:15 |
| **3:15 PM** | Bot closes all trades | Market close |
| **5:00 PM** | Check daily P&L | Note any anomalies |

### ⚠️ Stop Signals:
- Daily P&L drops below -₹5,000 → Stop bot immediately
- Bot crashes → Restart and add error to notes
- Telegram not sending alerts → Check token/chat_id
- Positions not closing at 3:15 PM → Manual exit + investigate

---

## 📊 END OF WEEK (Friday Afternoon)

### Step 1: Generate Metrics (4:00 PM Friday)

```bash
# Run analysis script
python analyze_weekly.py

# Output will show:
# ✅ Win rate this week
# ✅ Total P&L this week  
# ✅ Best trading hours
# ✅ Best performing symbols
# ✅ Filter rejection stats
```

### Step 2: Collect Input Data (4:30 PM Friday)

```bash
# Open template
cat weekly_input_template.json

# Fill in your observations:
# - Market trend this week
# - Best/worst symbols
# - Best/worst hours
# - Biggest issue
# - Suggested fixes

# Save as
weekly_input_2026_08_15.json  # Use correct date
```

### Step 3: Share with Me (5:00 PM Friday)

```
Send me:
1. weekly_input_2026_08_15.json
2. weekly_report_2026_08_15.json (auto-generated)
3. Any manual notes or observations

I will provide updated code/config by Monday 8:00 AM
```

---

## 🔄 WEEKLY IMPROVEMENT CYCLE

```
┌─────────────────────────────────────────────────┐
│ MONDAY: Apply Last Week's Improvements          │
│ - Update kite_config.json                       │
│ - Restart bot with new parameters               │
│ - Trade with new configuration                  │
└─────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│ MONDAY-FRIDAY: Collect Trade Data               │
│ - Bot logs all trades to trades.jsonl           │
│ - Bot logs filter rejections to filter_log.jsonl│
│ - Monitor daily P&L                             │
│ - Note issues/observations                      │
└─────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│ FRIDAY 4:00 PM: Analyze & Report                │
│ - Run analyze_weekly.py                         │
│ - Review metrics and statistics                 │
│ - Identify best/worst performers                │
└─────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│ FRIDAY 4:30 PM: Fill Weekly Input               │
│ - Answer questions in weekly_input_template.json│
│ - Provide observations & suggestions            │
│ - Identify biggest issues & fixes               │
└─────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│ FRIDAY 5:00 PM: Submit for Review               │
│ - Send weekly_input_YYYY_MM_DD.json             │
│ - Send weekly_report_YYYY_MM_DD.json            │
│ - Include any manual notes                      │
└─────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│ WEEKEND: Analysis & Code Updates                │
│ - I review your input                           │
│ - I analyze trade data                          │
│ - I update code/config for improvements         │
└─────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│ MONDAY 8:00 AM: Deploy Updates                  │
│ - Download updated kite_config.json             │
│ - Download updated code if any                  │
│ - Restart bot with improvements                 │
│ - Repeat cycle...                               │
└─────────────────────────────────────────────────┘
```

---

## 📋 DAILY MONITORING CHECKLIST

Print this and check off each day:

```
═══════════════════════════════════════════════════════
DAILY CHECKLIST - Print & Laminate This
═══════════════════════════════════════════════════════

DATE: _______________

MORNING (8:00 AM):
☐ Check system is ready (python environment OK)
☐ Verify config files are valid JSON
☐ Start bot: python run_kite_bot.py
☐ Check: "Connected! Monitoring X futures"

DURING DAY (9:15 AM - 3:15 PM):
☐ Monitor first 15 minutes for errors
☐ Check active positions (should be 1-3 max)
☐ Monitor daily P&L (stop if < -₹5,000)
☐ Verify Telegram alerts arriving
☐ Note any unusual trades

SPECIFIC TIMES:
☐ 9:15 AM  - Market open (risky period)
☐ 12:00 PM - Mid-day check
☐ 2:00 PM  - Afternoon check
☐ 3:10 PM  - Pre-close check (all positions ready to exit?)
☐ 3:15 PM  - Market close (verify all closed)

EVENING (5:00 PM):
☐ Check final daily P&L
☐ Note any issues encountered
☐ Review last 10 trades in trades.jsonl
☐ If P&L > ₹5,000: ✅ Great day!
☐ If P&L between 0-5,000: ✅ Good day
☐ If P&L between -1,000-0: ⚠️ Average day
☐ If P&L < -1,000: ❌ Review what went wrong

NOTES:
_________________________________________________________________
_________________________________________________________________

═══════════════════════════════════════════════════════
```

---

## 🎯 WEEKLY INPUT TEMPLATE - QUICK VERSION

Just answer these 5 questions by Friday 5 PM:

```json
{
  "1_BEST_HOUR": "10:00-12:00",
  "1_BEST_HOUR_WHY": "Trending nicely, good entry points",
  
  "2_WORST_HOUR": "09:15-09:30",
  "2_WORST_HOUR_WHY": "Very volatile, lots of noise",
  
  "3_BEST_SYMBOL": "NIFTY",
  "3_BEST_SYMBOL_WHY": "Most consistent wins, 7/8 profitable",
  
  "4_WORST_SYMBOL": "INFY",
  "4_WORST_SYMBOL_WHY": "Whipsaws, 1/3 profitable",
  
  "5_BIGGEST_ISSUE": "Take profit target too tight (1.5%)",
  "5_BIGGEST_ISSUE_FIX": "Increase to 2.5%, moves often go 2-3%",
  
  "6_FILTER_FEEDBACK": "Filters rejected 12 signals, about 8 would have lost. Filters working!",
  
  "7_WIN_RATE": 60,
  "7_DAILY_PROFIT": 3800,
  "7_NEXT_WEEK_TARGET_WIN_RATE": 65,
  "7_NEXT_WEEK_TARGET_PROFIT": 5000
}
```

---

## 🔧 FILES YOU'LL USE

| File | When | What To Do |
|------|------|-----------|
| `kite_config.json` | Monday AM | Update with last week's changes |
| `trades.jsonl` | Every day | Auto-generated by bot |
| `filter_log.jsonl` | Every day | Auto-generated by bot (shows rejections) |
| `analyze_weekly.py` | Friday 4 PM | Run this: `python analyze_weekly.py` |
| `weekly_report_YYYY_MM_DD.json` | Friday 4 PM | Auto-generated report |
| `weekly_input_template.json` | Friday 4:30 PM | Copy & fill this in |
| `weekly_input_YYYY_MM_DD.json` | Friday 5 PM | Submit to me |
| `DAILY_WEEKLY_OPERATIONS.md` | Anytime | Reference guide (this folder) |

---

## 📞 COMMUNICATION SCHEDULE

| Day | Time | Action | Details |
|-----|------|--------|---------|
| **Monday** | 8:00 AM | Deploy | I send updated config/code |
| **Monday** | 9:00 AM | Start | You start bot with new config |
| **Tue-Thu** | Anytime | Support | You can ask questions |
| **Friday** | 4:00 PM | Analyze | You run analyze_weekly.py |
| **Friday** | 4:30 PM | Input | You fill weekly_input template |
| **Friday** | 5:00 PM | Submit | You send files to me |
| **Weekend** | - | Update | I analyze and prepare updates |

---

## 🎯 SUCCESS METRICS

Track these to see improvement:

```
WEEK 1 (Current):  50% win rate  → -₹300/day  (❌ Not tradeable)
WEEK 2 (Target):   60% win rate  → +₹3,800/day  (✅ Tradeable)
WEEK 3 (Target):   65% win rate  → +₹5,500/day  (✅ Good)
WEEK 4 (Target):   70% win rate  → +₹8,000/day  (✅ Professional)
```

Your goal: Get from Week 1 to Week 2 this week!

---

## ❓ COMMON QUESTIONS

**Q: What if the bot crashes during trading?**
A: Restart immediately: `python run_kite_bot.py`. It will auto-exit any open positions at 3:15 PM.

**Q: What if I lose ₹5,000+ in a day?**
A: Stop the bot. Note the losses. Share with me on Friday for analysis. We'll adjust filters.

**Q: What if a signal looks wrong, should I manually exit?**
A: Yes, if you see a bad setup, manually close it. Note it in daily notes for Friday review.

**Q: How often will I need to make changes?**
A: Every week, 2-3 small tweaks based on data. You just fill the template, I do the coding.

**Q: When can I go live with real money?**
A: After Week 2 minimum (60% win rate confirmed). Start with ₹10,000 only.

---

## 🚨 EMERGENCY PROCEDURES

### If Daily P&L < -₹5,000:
```
1. STOP BOT IMMEDIATELY
2. Close all open positions manually
3. Note what went wrong
4. Restart next day with investigation
5. Report to me on Friday
```

### If Bot Doesn't Close Positions at 3:15 PM:
```
1. Check if 3:15 PM time is correct
2. Manually close all positions in Zerodha
3. Verify Telegram alert received
4. Check error logs in terminal
5. Restart bot
6. Report issue on Friday
```

### If Telegram Alerts Stop Arriving:
```
1. Verify token is correct in kite_config.json
2. Verify chat_id is correct
3. Test manually: send test message to bot
4. Restart bot
5. If still fails, note on Friday for debugging
```

---

## 📈 EXPECTED PROGRESS

```
Timeline of Improvements:

WEEK 1 (NOW):
- Current: 50% win rate, -₹300/day
- Action: Implement Week 1 filters
- Result: NOT TRADING YET (paper trading only)

WEEK 2 (Next):
- Target: 60% win rate, +₹3,800/day
- Action: Live trading starts (₹10,000 account)
- Result: Consistent small profits

WEEK 3:
- Target: 65% win rate, +₹5,500/day
- Action: Scale to ₹25,000 account
- Result: Professional-grade system

WEEK 4+:
- Target: 70%+ win rate, +₹8,000+/day
- Action: Scale as desired
- Result: Consistent income stream
```

---

## 📞 HOW TO REACH ME

When you submit your weekly input, include:
1. `weekly_input_YYYY_MM_DD.json` (filled answers)
2. `weekly_report_YYYY_MM_DD.json` (auto-generated)
3. Any manual notes or questions

I'll review and provide:
1. Updated `kite_config.json` (if parameters changed)
2. Updated code (if filters need adjustment)
3. Analysis & recommendations

Turnaround: By Monday 8:00 AM

---

## ✅ YOU'RE READY!

You now have:
- ✅ Daily operations guide
- ✅ Weekly analysis process
- ✅ Automated metrics script
- ✅ Input template for improvements
- ✅ Clear success metrics
- ✅ Emergency procedures

**Next Step:** Run the bot on Monday morning with your current setup!

Questions? Check DAILY_WEEKLY_OPERATIONS.md for detailed explanations.
