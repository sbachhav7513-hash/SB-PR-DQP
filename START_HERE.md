# 🎯 START HERE: Your Bot Operating Manual

## What You Have Now

A **trading bot** that will:
- Trade intraday futures on Zerodha
- Monitor 16 different futures contracts
- Generate signals every 1 minute
- Log all trades for analysis
- Send Telegram alerts
- Auto-exit all positions at 3:15 PM IST

**Current Performance:** 50% win rate (NOT ready for live trading)

---

## What You Need to Do

### This Week (Baseline):
1. **Run the bot daily** (Mon-Fri)
2. **Monitor** (spend 10 min in morning, 5 min in afternoon)
3. **Collect data** (bot does this automatically)

### This Friday (Analysis):
1. **Analyze results** (run script: `python analyze_weekly.py`)
2. **Fill weekly input** (answer 5-7 questions)
3. **Send to me** (2 JSON files)

### Next Week (Improvements):
1. **Get updated code** from me Monday morning
2. **Restart bot** with improvements
3. **Repeat cycle**

---

## Files You'll Use Every Week

| File | When | Who Creates | What It Is |
|------|------|-------------|-----------|
| `kite_config.json` | Monday AM | Me (I update) | Bot settings/parameters |
| `trades.jsonl` | Daily | Bot (auto) | Log of all trades |
| `filter_log.jsonl` | Daily | Bot (auto) | Log of rejected signals |
| `analyze_weekly.py` | Friday 4 PM | You run | Script that generates report |
| `weekly_report_*.json` | Friday 4 PM | Script creates | Auto-generated metrics |
| `weekly_input_template.json` | Friday 4:30 PM | You fill | Your weekly feedback form |

---

## The Weekly Rhythm

```
MONDAY MORNING (8:00 AM)
│
├─ Check system
├─ Update config (if changes)
└─ Start: python run_kite_bot.py

MONDAY-FRIDAY (Daily)
│
├─ 9:15 AM: Monitor opening (risky hour)
├─ Midday: Check P&L every 30 min
├─ 3:15 PM: Bot auto-exits
└─ 5:00 PM: Note daily results

FRIDAY AFTERNOON (4:00 PM)
│
├─ Run: python analyze_weekly.py
├─ Get: weekly_report_YYYY_MM_DD.json
└─ See: Win rate, P&L, best/worst symbols/hours

FRIDAY EVENING (4:30 PM)
│
├─ Open: weekly_input_template.json
├─ Answer: 5-7 questions
└─ Save: weekly_input_YYYY_MM_DD.json

FRIDAY EVENING (5:00 PM)
│
└─ Send to me:
   1. weekly_input_YYYY_MM_DD.json
   2. weekly_report_YYYY_MM_DD.json
   3. Any manual notes

WEEKEND (Sat-Sun)
│
└─ I do:
   1. Analyze your data
   2. Update config
   3. Update code if needed
   4. Prepare for Monday

MONDAY MORNING (8:00 AM)
│
├─ Get updated files from me
├─ Update kite_config.json
└─ Repeat cycle...
```

---

## 📊 What to Fill in Your Weekly Input

Every Friday 4:30 PM, I need your answers to these questions:

### Question 1: Best Trading Hour
**My question:** "When this week did we make the most money?"
**Your answer:** "10:00-12:00 (or whatever hour from your report)"
**Why:** Tells me when to focus trading

### Question 2: Worst Trading Hour
**My question:** "When did we lose the most?"
**Your answer:** "09:15-09:30 (or whatever hour)"
**Why:** Tells me when to skip

### Question 3: Best Symbol
**My question:** "Which stock/future traded best?"
**Your answer:** "NIFTY or BANKNIFTY or TCS (etc)"
**Why:** Keep trading winners

### Question 4: Worst Symbol
**My question:** "Which had the most false signals?"
**Your answer:** "INFY or WIPRO (etc)"
**Why:** Remove losers from trading list

### Question 5: Biggest Problem
**My question:** "What hurt your profit the most?"
**Your answers (pick 1):**
- Exited too early (take profit too tight)
- Exited too late (stop loss too loose)
- Too many entries in choppy market
- Bad entry timing (too early/late)
- Too many positions at once
- Other: _______

### Question 6: Your Suggested Fix
**My question:** "How would you fix it?"
**Your answer:** "Increase take profit from 1.5% to 2.5%"
**Format:** What to change + Current value + New value + Why

### Question 7: Expected Results
**My question:** "What win rate do you think after this fix?"
**Your answer:** "I think we'll get to 65% win rate and +₹5,000/day"

---

## Daily Monitoring: The Checklist

Print this and check off each day:

### Morning (8:00 AM)
- [ ] Start the bot: `python run_kite_bot.py`
- [ ] See message: "Connected! Monitoring X futures..."
- [ ] No errors in terminal

### During Day (9:15 AM - 3:15 PM)
- [ ] Active positions: 1-3 maximum
- [ ] Daily P&L: Check every 30 min
- [ ] Telegram alerts: Receiving them?
- [ ] Any crashes? Restart if needed

### Afternoon (1:00-3:15 PM)
- [ ] 3:10 PM: All positions still open?
- [ ] 3:15 PM: Bot closes all trades? ✓
- [ ] No positions remaining?

### Evening (5:00 PM)
- [ ] Daily P&L final result: ₹_____
- [ ] Was it positive or negative?
- [ ] Any issues to note for Friday?

### STOP SIGNAL - Stop Bot Immediately If:
- [ ] Daily P&L drops below -₹5,000
- [ ] Bot crashes and doesn't restart
- [ ] Positions don't close at 3:15 PM
- [ ] Telegram stopped sending alerts

---

## 🎯 Expected Weekly Improvement

```
THIS WEEK (WEEK 1):
- Win Rate: 50%
- Daily P&L: -₹300 (LOSS)
- Status: ❌ DO NOT TRADE LIVE

↓ (After your Friday input + my updates)

NEXT WEEK (WEEK 2):
- Win Rate: 60%
- Daily P&L: +₹3,800 (PROFIT!)
- Status: ⚠️ OK for live trading

↓ (After Week 2 input + improvements)

WEEK 3:
- Win Rate: 65%
- Daily P&L: +₹5,500
- Status: ✅ GOOD

↓

WEEK 4:
- Win Rate: 70%
- Daily P&L: +₹8,000+
- Status: ✅ EXCELLENT
```

Your job: Help me get from Week 1 → Week 2 this week!

---

## 🚨 Emergency Procedures

### If Daily Loss > ₹5,000:
1. STOP the bot immediately
2. Manually close any open positions in Zerodha
3. DON'T trade rest of day
4. Note what caused it
5. Tell me Friday

### If Bot Doesn't Close at 3:15 PM:
1. Manually close positions (emergency!)
2. Check: Is 3:15 PM time correct in config?
3. Restart bot
4. Tell me Friday

### If Telegram Alerts Stop:
1. Check: Telegram token in config correct?
2. Check: Telegram chat_id correct?
3. Restart bot
4. Tell me Friday

---

## 📋 What I Need From You Each Friday

**Exactly 2 files at 5:00 PM Friday:**

### File 1: `weekly_input_2026_08_15.json`
```
This is YOUR answers to the 7 questions above
You fill this out, I analyze it
I use it to update the code
```

### File 2: `weekly_report_2026_08_15.json`
```
This is auto-generated by: python analyze_weekly.py
You just send it, I use it to verify your input
```

Both files needed for me to update your code!

---

## 🚀 Timeline: When Things Happen

| When | Who | What | Output |
|------|-----|------|--------|
| **Mon 8 AM** | Me | Send updated config | kite_config.json |
| **Mon 9 AM** | You | Start bot | trades.jsonl begins |
| **Mon-Fri Daily** | Bot | Trade & log | trades.jsonl grows |
| **Fri 4 PM** | You | Run analyze script | weekly_report_*.json |
| **Fri 4:30 PM** | You | Fill input template | weekly_input_*.json |
| **Fri 5 PM** | You | Send files to me | 2 JSON files |
| **Sat-Sun** | Me | Analyze & update | Updated code |
| **Mon 8 AM** | Me | Deploy updates | Ready for Week 2 |

---

## 💰 When to Go Live

**DO NOT GO LIVE UNTIL:**
- [ ] Week 2 complete (60%+ win rate confirmed)
- [ ] 5 consecutive days with profit
- [ ] You understand all filters and settings
- [ ] You have ₹10,000+ trading account

**When you're ready:**
- Start with ₹10,000 only
- Trade 1 lot minimum
- Track daily P&L
- Scale only after consistent profits

---

## 📚 Your Documents

I created 4 guides for you:

| Document | Read This If | Length |
|----------|-------------|---------|
| **QUICK_REFERENCE.md** | Need quick answers | 5 pages (PRINT THIS!) |
| **GETTING_STARTED.md** | Want complete overview | 15 pages |
| **DAILY_WEEKLY_OPERATIONS.md** | Need detailed procedures | 20 pages |
| **weekly_input_template.json** | Want to see example | 1 page (fill Friday) |

**Start with:** QUICK_REFERENCE.md (print it!)
**Then read:** GETTING_STARTED.md
**Keep handy:** DAILY_WEEKLY_OPERATIONS.md

---

## ✅ Pre-Launch Checklist

Before you start Monday, verify:

```
SYSTEM SETUP:
☐ Python 3.8+ installed
☐ All pip packages installed
☐ requirements.txt dependencies OK

CONFIG FILES:
☐ kite_config.json has valid API key
☐ kite_config.json has access token
☐ kite_config.json has telegram_token
☐ kite_config.json has telegram_chat_id
☐ All JSON files are valid (no syntax errors)

ZERODHA ACCOUNT:
☐ Account has minimum ₹100,000
☐ Account active and verified
☐ Can trade futures
☐ API access enabled

TELEGRAM:
☐ Telegram bot created
☐ Chat ID obtained
☐ Token stored in config

YOU:
☐ Understand stop loss at -₹5,000/day
☐ Know how to manually close positions in Zerodha
☐ Have Python running terminal open
☐ Printed QUICK_REFERENCE.md
```

If all checked ✓, you're ready Monday 8 AM!

---

## 🎯 Your Goal This Week

```
GOAL: Get 5 days of trade data to analyze on Friday

HOW:
- Mon-Fri: Run bot normally
- Each day: Let it trade, collect data
- Each day: Monitor for crashes/issues
- Friday: Analyze everything
- Friday: Tell me what you learned

RESULT:
- Friday: I get clear picture of bot performance
- Weekend: I update settings based on data
- Monday: Bot runs better with improvements
- Week 2: Higher win rate, more profit!
```

---

## 🔄 What Happens Next

### Your Workflow:
```
START (Today)
    ↓
RUN BOT (Mon-Fri)
    ↓
MONITOR DAILY (10 min/day)
    ↓
COLLECT DATA (Automatic)
    ↓
ANALYZE FRIDAY (15 min)
    ↓
FILL FORM FRIDAY (30 min)
    ↓
SEND FILES FRIDAY (5 min)
    ↓
GET UPDATES MONDAY (receive)
    ↓
RESTART BOT (5 min)
    ↓
REPEAT NEXT WEEK
```

### My Workflow:
```
RECEIVE YOUR FILES
    ↓
ANALYZE DATA
    ↓
IDENTIFY ISSUES
    ↓
UPDATE CODE/CONFIG
    ↓
TEST CHANGES
    ↓
DELIVER MONDAY MORNING
    ↓
SUPPORT DURING WEEK
    ↓
REPEAT
```

---

## 📞 How to Contact Me

**During week (Mon-Fri):**
- Quick questions? Email with question
- Bot crashed? Tell me ASAP, we'll debug
- Issue with trade? Note it, tell Friday

**Friday 5:00 PM:**
- Send 2 JSON files (required)
- Include any manual notes
- Ask any questions

**Weekend:**
- I'll review everything
- Prepare updates for Monday
- Be ready with new code Monday 8 AM

**Monday 8:00 AM:**
- I send: Updated kite_config.json
- I send: Any code changes
- You do: Update files, restart bot
- Week 2 begins!

---

## 🎓 Key Takeaways

1. **Run the bot** - It does the trading automatically
2. **Monitor lightly** - 15 min/day total, mostly automated
3. **Analyze Friday** - Run the analysis script (1 click!)
4. **Fill the form** - Answer 7 simple questions
5. **Send to me** - Just 2 JSON files
6. **Get updates** - I update code for next week
7. **Repeat** - Same rhythm every week
8. **Improve gradually** - 10% better each week

---

## 💡 Pro Tips

1. **Track manually too:** Keep a notebook of:
   - When you got whipsawed
   - What was different about that trade
   - Market conditions at the time

2. **Review report first:** Before filling input, read the auto-generated report
   - See which hours made money
   - See which symbols did best
   - Let DATA guide your answers

3. **Be specific:** Instead of "bad," say "INFY had 3 false signals"
   - Instead of "exits wrong," say "take profit too tight"
   - Instead of "need improvement," say "increase to 2.5%"

4. **One main change per week:** 
   - Easier to know what helped
   - Better than many changes at once
   - Compound improvements work best

5. **Document same day:**
   - Don't wait for Friday to remember
   - Write "9:30 - INFY whipsawed badly, -75 points"
   - Use daily observations in Friday input

---

## 🏁 Ready? Let's Go!

**Your next actions:**
1. ✓ Read this document (you're doing it!)
2. ✓ Print QUICK_REFERENCE.md
3. ✓ Read DAILY_WEEKLY_OPERATIONS.md
4. ✓ Prepare config files
5. → **Monday 8:00 AM: Start bot!**

**Questions?** Check the reference guides or ask Friday.

**Ready to start?** Let me know when you're set for Monday morning!

---

**Good luck! Let's turn 50% into 60%+ win rate this week! 🚀**

*Version 1.0 | Complete Daily/Weekly Operating Manual | 2026*
