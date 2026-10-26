# Trading Accuracy & Reliability Analysis

> **Evidence warning (2026-10-15):** This is a historical analysis draft, not
> validated strategy research. Its win-rate, confidence, risk, and profit
> estimates are not supported by reproducible out-of-sample or forward results;
> treat them as unverified, not as current measurements or live-trading
> guidance. See [README_RELIABILITY.md](README_RELIABILITY.md) for the current
> deployment verdict. Configuration names and mode-specific behavior described
> below are historical snapshots; current PAPER and LIVE use shared strategy
> keys and rules documented in `README.md`.

## Paper-only trend continuation experiment

`kite_config.json` enables `paper_allow_trend_continuation` for paper trading.
This allows a scored trend setup to proceed without the separate volatility
compression and breakout-candle checks that blocked candidates in the latest
paper review. The active paper config also sets `paper_min_entry_score` to 60
while `min_entry_score` remains 70; the lower floor only applies when paper
trading is enabled. Direction, trend strength, ADX, VWAP, benchmark,
confirmation, option quality, and risk checks still apply. Neither setting
authorizes live orders or guarantees a trade or profitable result. Compare the
next daily review before making any further changes.

## October 23 TCS PE trade review

The journal records a TCS_PE SELL signal at 10:24:56 IST with score 65 and the
reason `RSI oversold against SELL`. The paper floor of 60 admitted this signal
while the paper continuation setting relaxed breakout-candle checks. The
position entered at 12.45, reached 13.10 (+0.522R), then hit the adaptive
breakeven stop at 12.45 and exited at 12.35 after 59 seconds (-INR 22.50 before
costs). The option later rose, but widening the stop is not a safe conclusion:
uploaded minute candles show it first trading below the initial stop.

A symmetric RSI-extreme signal gate now holds BUY signals above RSI 70 and SELL
signals below RSI 30. This would have blocked the recorded signal. It is an
unvalidated strategy trial, not proof that future trades will improve; review
rejected candidates and cost-adjusted outcomes over forward paper sessions.
Keep live orders disabled.

## October 23 SBIN PE stop and re-entry review

The journal records SBIN26OCT970PE bought at ₹12.20 for 750 units, stopped at
₹10.85 at 10:08:18 IST for a gross loss of ₹1,012.50. The initial stop was
₹10.98, and the exact-contract 10:08 candle reached ₹10.60, so the stop was
crossed; simply widening or ignoring it would have increased risk.

Archived decisions then show range-breakout candidates at 10:32, 10:33, 10:36,
and 10:37 blocked by the one-trade-per-symbol-per-session rule. Later standard
SELL candidates scored 65 and cited “RSI oversold against SELL”; the symmetric
RSI-extreme gate now holds such signals. The range-breakout path is currently
disabled in the active config, so the blocked historical candidates are not a
valid claim that the current strategy would have re-entered. Exact-contract
minute bars later reached ₹21.85 and crossed the recorded ₹14.64 target, but
those highs are hindsight OHLC observations, not executable fills.

The exit journal also records LTP ₹10.85 alongside bid ₹11.20 and ask ₹11.25.
That quote/LTP relationship is inconsistent, and the historical quote timestamp
was not retained, so neither the bid nor the LTP can be treated as a verified
executable fill. New paper exits now persist the quote timestamp for freshness
audits; the mark-to-LTP execution behavior itself is unchanged.

Across 14 losing trades with matching exact-contract minute data from Oct 19-23,
9 later candles retested the entry and 6 later reached the recorded 20% target.
Three additional losses lacked matching exact-contract data. These counts do
not account for whether the strategy would have generated a valid fresh signal,
bid/ask spread, quote freshness, slippage, or the intraminute path.

A paper-only re-entry trial now permits at most one retry per option symbol
after a negative stop exit, with a 15-minute cooldown and a fresh score of at
least 75. The normal option-quality, sizing, stop, daily-risk, and loss-circuit
checks still apply. Accepted retries are tagged `paper_stop_reentry`. The trial
does not widen the original stop or enable the currently disabled range-breakout
strategy. It is enabled only in the active paper config; live orders remain
disabled. Evaluate signal/rejection counts,
fills, costs, P&L, and drawdown over a forward sample before drawing conclusions.

## October 23 ICICIBANK 1400 CE support/reversal review

The October 23 ICICIBANK 1400 CE entry at ₹9.45 was a score-85 bullish
underlying-trend signal at 09:43, not a premium-support entry. It exited at
₹8.40 for a recorded -₹735. At 10:04, the bearish PE candidate scored 65 but
was rejected because the proposed one-lot stop risk exceeded the ₹1,000 paper
cap; its reasons also included “RSI oversold against SELL.” CE and PE are
selected directionally from the underlying signal, not opened together as a
straddle.

The cited ₹5.29 support and ₹8.90/₹9.78 resistance are option-premium levels.
The primary scorer uses the underlying and did not calculate support/resistance
on either series. The underlying reached ₹1,377.90 at 13:15. The 1400 CE
traded below ₹5.29, reaching ₹4.95 at 13:16, so the displayed support did not
hold on its first touch. A chart high or later bounce cannot establish a
fillable entry.

A separate paper-only underlying support/reversal trial now uses complete,
contiguous five-minute bars aggregated from one-minute underlying candles. It
requires two clustered pivots, a recent retest, a directional close through the
prior bar, and proximity to the level. On this session it identified a BUY
candidate on the 13:25 five-minute bar at an underlying level near ₹1,378.95
(two pivots; close ₹1,381.00). The underlying's 13:30 one-minute candle then
closed higher at ₹1,381.70 with a 0.273 body/range ratio. The trial's
support-specific 0.20 momentum floor permits that candle while the existing
one-minute directional confirmation still applies. The exact-contract CE
closed at ₹5.55 at 13:29 and ₹5.90 at 13:30; these are candle observations,
not an entry fill or a counterfactual profit.

The export has no matched benchmark series or timestamped historical bid/ask
snapshot for the option, so the hard-context and fresh-quote gates cannot be
fully replayed for this candidate. The paper feature must pass both at runtime.

The October 23 replay produced 10 raw detector candidates across the full
ICICIBANK session; applying a 15-minute same-level cooldown to each detected
setup as a replay screen reduces that count to 7. Runtime cooldown is recorded
only after option-quality and accuracy checks pass. Candidate frequency still
needs monitoring; this is not a performance backtest. Promotion also requires
the configured score and hard benchmark context, news, regular-session,
accuracy, fresh option-quote, contract quality/liquidity, quantity, stop, and
risk checks. Only this strategy may use
the ₹5 premium floor; the normal ₹12 floor is unchanged. The usual per-trade
₹1,000 paper risk cap and standard adaptive exit remain in force. The strategy
is enabled only in the active paper config, disabled in the example config,
and cannot run when live orders are enabled. Continue as a reversible paper
trial and assess at least 10 closed trades with costs before drawing a
performance conclusion.

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

### Issue 2: Same-symbol re-entry after a stop

The session guard already prevents a second same-symbol trade, including a
fresh setup after a stop. That protects against repeated losses but can also
block a later, independently validated option setup. A separate paper-only
trial allows one retry only after a losing stop, a 15-minute cooldown, and a
score of at least 75; all standard quality and risk gates remain mandatory.
This is an unvalidated policy trial, not evidence that re-entry will improve
performance.

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

The candidate changes above are not validated. Continue paper-only evaluation
and do not enable live orders based on this guide.
