# Trading Accuracy & Reliability Analysis

> **Evidence warning (2026-10-15):** This is a historical analysis draft, not
> validated strategy research. Its win-rate, confidence, risk, and profit
> estimates are not supported by reproducible out-of-sample or forward results;
> treat them as unverified, not as current measurements or live-trading
> guidance. See [README_RELIABILITY.md](README_RELIABILITY.md) for the current
> deployment verdict.

## Paper-only trend continuation experiment

`kite_config.json` enables `paper_allow_trend_continuation` for paper trading.
This allows a scored trend setup to proceed without the separate volatility
compression and breakout-candle checks that blocked candidates in the latest
paper review. The active paper config also sets `paper_min_entry_score` to 55
while `min_entry_score` remains 70; the lower floor only applies when paper
trading is enabled. Direction, trend strength, ADX, VWAP, benchmark,
confirmation, option quality, and risk checks still apply. Neither setting
authorizes live orders or guarantees a trade or profitable result. Compare the
next daily review before making any further changes.

## Current Strategy Assessment

### 🔴 **WARNING: NOT YET PRODUCTION-READY**

The current bot's live readiness and strategy performance have not been
established by the figures in this draft.

---

## Reliability Scoring

| Component | Evidence | Risk Level | Notes |
|-----------|-------------|-----------|-------|
| **Signal Generation** | Not measured | Unknown | Requires out-of-sample evaluation |
| **Risk Management** | Not independently validated | Unknown | Unit tests do not validate broker execution |
| **Entry Accuracy** | Not measured | Unknown | Requires forward paper-trade evidence |
| **Exit Logic** | Not independently validated | Unknown | Requires execution and recovery testing |
| **Overall** | Not established | Unknown | Not approved for live trading |

---

## 🔴 Critical Issues Found

### Issue 1: **Whipsaw Risk (CRITICAL)**
```
Problem:
- EMA crossovers happen frequently on 1-min candles
- RSI bounces between overbought/oversold
- Result: Multiple false BUY/SELL signals in 5-minute windows

Example:
09:15 → BUY signal (EMA+9 crosses EMA+21)
09:16 → Price drops 0.5% → STOP LOSS HIT (-₹500)
09:17 → Price bounces → BUY again
09:18 → Price drops again → STOP LOSS HIT (-₹500)

Loss: ₹1,000 in 4 minutes (commissions add up)
Cause: Too many signals on 1-min timeframe
```

**Solution**: Increase to 5-minute candles minimum, add cooldown period

---

### Issue 2: **Over-Optimized for Last Market Conditions**
```
Current Score Weights:
- EMA bullish: +25 points (too aggressive)
- RSI in zone: +20 points
- MACD improving: +18 points
- Price near high: +10 points

Problem:
- Heavily favors momentum continuation
- Doesn't adapt to range-bound markets
- False-signal rate in sideways markets has not been measured
```

**Solution**: Add volatility-based signal filters

---

### Issue 3: **No Market Context Awareness**
```
Current: Always tries to trade
- Does NOT check market volatility
- Does NOT check if in choppy vs trending market
- Does NOT adjust for liquidity conditions

Risk:
- May trade during opening or closing periods; the effect on accuracy and
  execution costs must be measured
- Misses best trading conditions (9:30-3:00 PM)
```

**Solution**: Add market condition filters

---

### Issue 4: **Score Threshold Too Low**
```
Current Thresholds:
- BUY/SELL at score >= 85 (needs refining)
- HOLD below that

Problem:
The strategy score is not a calibrated probability. No verified mapping from
score thresholds to win rate is available.
```

**Solution**: Increase threshold to 90, add confirmation filters

---

### Issue 5: **No Multiple Timeframe Confirmation**
```
Current: Only 1-minute candles
Problem:
- 1-min signals are too noisy
- No confirmation from 5-min or 15-min trends

Solution:
1-min candle: EMA crossover
5-min candle: Must also be in uptrend
15-min candle: Must not be overbought

Result: Unknown; test as a hypothesis on unseen data
```

---

## Performance Evidence

No verified current win rate, expectancy, or cost-adjusted P&L is established
here. The scenario figures previously in this section were assumptions, not
measured results, and have been removed. Measure each strategy variant on
unseen paper sessions and account for fees, spread, slippage, partial fills,
and drawdown before drawing conclusions.

---

## 🟡 Accuracy Issues & Solutions

### Issue 1: False Signals in Range-Bound Markets

**Problem**:
```python
# Current logic triggers on ANY EMA crossover
if fast_ema > slow_ema:
    signal = "BUY"  # Even if range-bound!

# In sideways markets:
- EMA crosses up → BUY
- Price bounces down → STOP LOSS
- Price goes up → BUY again (whipsaw)
- Repeats 5+ times = multiple losses
```

**Fix - Add Volatility Filter**:
```python
# Calculate ATR (Average True Range)
atr = calculate_atr(history, period=14)
volatility = atr / close_price

if volatility < 0.01:  # Market is calm (< 1% movement)
    signal = "HOLD"  # Skip low-volatility trades
    
if volatility > 0.05:  # Market is wild (> 5% movement)
    signal = "HOLD"  # Skip high-volatility trades
    
# Only trade when 1% < volatility < 5% ✅
```

**Measured performance effect**: Not established

---

### Issue 2: Multiple Entries in Same Direction

**Problem**:
```
09:15 → BUY signal (entry)
09:16 → HOLD (already in position)
09:17 → BUY signal AGAIN! (bug?)
09:18 → Attempts to enter again (overleveraged)

Current code only prevents re-entry of SAME position.
But allows multiple entries in quick succession.
```

**Fix - Add Cooldown Period**:
```python
class TradeManager:
    last_entry_time = {}
    COOLDOWN_SECONDS = 300  # 5 minutes
    
    def can_enter_signal(self, symbol):
        if symbol not in last_entry_time:
            return True
        
        time_since_last = (now - last_entry_time[symbol]).total_seconds()
        if time_since_last < COOLDOWN_SECONDS:
            return False  # Skip signal during cooldown
        
        return True
```

**Measured performance effect**: Not established

---

### Issue 3: Bad Entry Prices

**Problem**:
```
Current: Enter at SIGNAL time
- Signal generated at end of bar
- By next bar, price already moved
- May enter AFTER trend reversal

Example:
09:15:00 → Bar closes, EMA crossover detected
09:15:01 → Signal sent, order placed
09:15:02 → Price already up 0.2%, entry gets 0.2% worse
```

**Fix - Wait for Confirmation Candle**:
```python
def validate_entry(self, signal, current_bar, previous_bar):
    if signal == "BUY":
        # Confirm price is actually going UP
        return current_bar.close > previous_bar.close  # ✅
    
    if signal == "SELL":
        # Confirm price is actually going DOWN
        return current_bar.close < previous_bar.close  # ✅
    
    return False
```

**Measured performance effect**: Not established

---

### Issue 4: Wrong Trade Direction Confirmations

**Problem**:
```
Current RSI logic:
"RSI 45-70 = trend zone" ✓ Good
"RSI < 35 = oversold" ✗ Problem!

For SELL signal:
- Need RSI to be HIGH (overbought)
- But code gives points when RSI is LOW (oversold)
- This causes SELL signals on rebounds (wrong direction)
```

**Fix - Direction-Aware RSI**:
```python
if signal == "BUY":
    # Only accept BUY if RSI not too high
    if rsi > 70:
        confidence -= 20  # Reduce score if overbought
    if rsi < 30:
        confidence += 15  # Increase if oversold (bounce expected)

if signal == "SELL":
    # Only accept SELL if RSI not too low
    if rsi < 30:
        confidence -= 20  # Reduce score if oversold
    if rsi > 70:
        confidence += 15  # Increase if overbought (pullback expected)
```

**Measured performance effect**: Not established

---

## ✅ Improvements Needed

### Priority 1 (CRITICAL - Implement First)

1. **Add Volatility Filter**
   - Skip trades when ATR/price < 1% or > 5%
   - Performance effect: unknown until independently evaluated

2. **Increase Score Threshold**
   - Change from 85 to 90+ for entry
   - Performance effect: unknown until independently evaluated

3. **Add Confirmation Candle**
   - Wait for next bar to confirm direction
   - Performance effect: unknown until independently evaluated

4. **Add Cooldown Period**
   - 5-minute wait between entries (same symbol)
   - Performance effect: unknown until independently evaluated

---

### Priority 2 (MEDIUM - Implement Next Week)

1. **Add Multiple Timeframe Confirmation**
   - 1-min + 5-min + 15-min alignment
   - Performance effect: unknown until independently evaluated

2. **Fix RSI Direction Logic**
   - Use different thresholds for BUY vs SELL
   - Performance effect: unknown until independently evaluated

3. **Add Time-Based Filters**
   - Avoid 9:15-9:30 (opening volatility)
   - Avoid 3:15-3:30 (closing volatility)
   - Performance effect: unknown until independently evaluated

4. **Add Liquidity Check**
   - Skip illiquid symbols (BANKNIFTY after 3 PM)
   - Performance effect: unknown until independently evaluated

---

### Priority 3 (NICE TO HAVE - Future)

1. **Machine Learning Signal Enhancement**
   - Combine with technical indicators
   - Performance effect: unknown until independently evaluated

2. **Sentiment Analysis**
   - Combine with market news/social signals
   - Performance effect: unknown until independently evaluated

3. **Trade Statistics Dashboard**
   - Real-time win rate monitoring
   - Daily P&L tracking

---

## Evaluation Roadmap

Treat each proposed filter or strategy change as an experiment. Change one
variable at a time, preserve an untouched evaluation period, report sample
size and uncertainty, and include realistic trading costs and adverse
execution. No particular win rate, profit, or timeline is forecast by this
guide.

---

## 🧪 How to Test Accuracy

### Test 1: Backtesting (2-3 hours of historical data)
```bash
# Create test data from past trades
python backtest.py --symbol NIFTY --date 2024-01-15 --hours 3

# Expected output:
# Total trades: 25
# Winning trades: 12 (48%)
# Losing trades: 13 (52%)
# Profit factor: 0.92 (need 1.2+)
```

### Test 2: Paper Trading (1-2 weeks)
```bash
# Use Zerodha's paper trading account
# Run bot with real data but no real money

# Track metrics:
- Win rate
- Average win/loss
- Maximum drawdown
- Sharpe ratio
```

### Test 3: Live trading

Live trading is not approved by this guide. Do not enable live orders based on
the scenarios or thresholds below. See
[README_RELIABILITY.md](README_RELIABILITY.md) for the current deployment gate.

---

## ✋ Minimum Requirements Before Live Trading

### ✅ Required:
1. **Backtesting Results**
   - Use a predeclared, unseen evaluation sample and realistic fees, spread,
     slippage, and partial-fill assumptions
   - Report expectancy, drawdown, sample size, and uncertainty; no win-rate
     threshold by itself proves profitability

2. **Paper Trading**
   - 2+ weeks of testing
   - Review cost-adjusted results, drawdown, operational failures, and sample
     size; do not treat a short paper run as proof of an edge

3. **Code Review**
   - All risk management in place
   - Position sizing working
   - Stop losses enforced

4. **Monitoring Plan**
   - Daily tracking of P&L
   - Weekly review of trades
   - Ready to pause if issues

### ❌ NOT Recommended For:
- Live trading with current code
- Large account (>₹1 lac) without improvements
- Leaving unmonitored for hours
- Trading during first/last 30 minutes

---

## 🛡️ Risk Mitigation Strategies

### Strategy 1: Start Small
Keep position sizing within the independently approved per-trade and daily risk
limits. Do not increase size based on a short profitable period or this guide.

### Strategy 2: Trade Only High-Liquidity Symbols
```
✅ Safe: NIFTY, BANKNIFTY (high volume)
⚠️ Caution: INFY, TCS, RELIANCE (medium volume)
❌ Avoid: Smaller stocks (low volume, wide spreads)
```

### Strategy 3: Limit Daily Loss
```
Max daily loss = Account × 2%
If hit: Stop trading for the day
Prevents cascading losses
```

### Strategy 4: Trade Only During Peak Hours
```
✅ 9:30 AM - 3:00 PM IST (best liquidity)
❌ Avoid: 9:15-9:30 AM (opening volatility)
❌ Avoid: 3:15-3:30 PM (closing rush)
```

---

## 📋 Checklist Before Going Live

- [ ] Implement Week 1 fixes (volatility filter, cooldown, threshold)
- [ ] Run an out-of-sample backtest with costs; report results without treating
      a threshold as proof of profitability
- [ ] Paper trade for 2 weeks (confirm signals)
- [ ] Setup daily monitoring & alerts
- [ ] Risk management configured (1% per trade)
- [ ] Stop losses enforced in code
- [ ] Reviewed trades.jsonl logs
- [ ] Ready to pause bot if issues arise
- [ ] Broker account verified & funded
- [ ] Telegram alerts tested

---

## Summary

| Aspect | Status | Action |
|--------|--------|--------|
| **Strategy performance** | Not established | No profitability claim |
| **Automated test suite** | Does not validate live execution | Paper-only until further review |

**Recommendation**: Do not enable live orders based on this guide or a win-rate
threshold. See [README_RELIABILITY.md](README_RELIABILITY.md) for the current
NO-GO verdict and remaining validation gates.

Do you want me to implement these improvements? Start with Week 1 fixes?
