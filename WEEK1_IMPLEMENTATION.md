# Week 1 Implementation Guide - Accuracy Improvements

> **Evidence warning (2026-10-15):** This is a historical proposal, not a
> measured performance report. All win-rate, accuracy, trade-count, and rupee
> impact figures below are unsupported estimates and must not be treated as
> expected results or a live-trading approval. The current live-trading status
> is recorded in [README_RELIABILITY.md](README_RELIABILITY.md).

## Summary of Changes

Proposed filters for paper evaluation. Their effect on win rate and profitability
has not been established.

---

## What Changed

### 5 New Accuracy Filters Created

| Filter | Impact | Lines Changed |
|--------|--------|---------------|
| **1. Volatility Check** | Avoid choppy markets | 30 lines |
| **2. Confirmation Candle** | Wait for direction confirmation | 15 lines |
| **3. Score Threshold** | Raise from 85 → 90 | 5 lines |
| **4. Cooldown Period** | Prevent rapid re-entries (5 min) | 20 lines |
| **5. Trading Hours** | Avoid 9:15-9:30 & 3:15-3:30 AM | 20 lines |

**Total changes: ~90 lines of code**
**Time to implement: 2-3 hours**

---

## How to Integrate (Step by Step)

### Step 1: Copy accuracy_filters.py
File already created: `market_bot/accuracy_filters.py` ✅

### Step 2: Update kite_main.py

Add import at top:
```python
from .accuracy_filters import AccuracyFilters
```

Initialize in `__init__`:
```python
class KiteTradingBot:
    def __init__(self, config_path: str = "kite_config.json") -> None:
        # ... existing code ...
        self.accuracy_filters = AccuracyFilters()  # ADD THIS
```

### Step 3: Modify on_bar_complete

**Current code**:
```python
def on_bar_complete(self, token_str: str, bar: Bar) -> None:
    # ... existing code ...
    if market_score.signal == "BUY":
        self._handle_buy_signal(symbol, bar.close, market_score.score)
```

**New code**:
```python
def on_bar_complete(self, token_str: str, bar: Bar) -> None:
    # ... existing code ...
    
    # ADD ACCURACY FILTERS HERE
    bars = self.bar_builder.get_bars(token, limit=50)
    previous_bar = bars[-2].to_dict() if len(bars) > 1 else bar.to_dict()
    current_time = datetime.now().timestamp()
    hour = datetime.now().hour
    minute = datetime.now().minute
    
    # Validate with all filters
    can_trade = self.accuracy_filters.validate_entry(
        symbol=symbol,
        signal=market_score.signal,
        score=market_score.score,
        history=[b.to_dict() for b in bars],
        current_bar=bar.to_dict(),
        previous_bar=previous_bar,
        current_time=current_time,
        hour=hour,
        minute=minute
    )
    
    # Only enter if ALL filters pass
    if not can_trade:
        logger.info(f"[{symbol}] Signal rejected by accuracy filters")
        return
    
    # Original signal handling
    if market_score.signal == "BUY":
        self._handle_buy_signal(symbol, bar.close, market_score.score)
```

---

## Hypotheses to Measure — Not Performance Expectations

The filters may reduce the number of entries, but the magnitude and effect on
returns are unknown. Record accepted and rejected signals and evaluate them on
unseen paper sessions with fees, spread, and slippage included.

---

## Filter-by-Filter Impact

### Filter 1: Volatility Check

**What it does**:
- Calculates ATR (volatility indicator)
- Skips trades if ATR < 0.8% or > 5% of price
- Avoids choppy and dangerous markets

**Example**:
```
NIFTY at 19,200

Good volatility:
- ATR = 154 points
- % = 154/19200 = 0.8% ✓

Too low (choppy):
- ATR = 96 points (0.5%)
- Skipped ❌

Too high (dangerous):
- ATR = 1000 points (5.2%)
- Skipped ❌
```

**Measured performance effect**: Not established

---

### Filter 2: Confirmation Candle

**What it does**:
- Waits for next candle to confirm direction
- BUY signal valid only if next bar closes HIGHER
- SELL signal valid only if next bar closes LOWER

**Example**:
```
09:15 Bar closes:
- EMA crossover detected (BUY signal)

09:16 Bar closes:
- Price at 19,210 (higher than 09:15)
- Confirmation = YES ✅
- Trade entered

Alternative:
- Price at 19,190 (lower than 09:15)
- Confirmation = NO ❌
- Signal rejected (false alarm avoided)
```

**Measured performance effect**: Not established

---

### Filter 3: Score Threshold

**What it does**:
- Raises entry threshold from 85 to 90
- Only signals meeting the configured score threshold are considered

**Example**:
```
The score is not a calibrated probability; no verified mapping from score to
win rate is available.

Change: Only accept 90+
Result: Better signals, fewer false entries
```

**Measured performance effect**: Not established

---

### Filter 4: Cooldown Period

**What it does**:
- 5-minute wait between entries for same symbol
- Prevents whipsaws and over-trading

**Example**:
```
09:15 NIFTY → BUY signal (entry #1) ✅
09:16 NIFTY → Another BUY signal
        Cooldown active → Rejected ❌
09:17 NIFTY → Another BUY signal
        Cooldown active → Rejected ❌
        
09:20 NIFTY → Cooldown expired
        BUY signal (entry #2 allowed) ✅
```

**Measured performance effect**: Not established

---

### Filter 5: Trading Hours

**What it does**:
- Skips 9:15-9:30 AM (opening volatility)
- Skips 3:15-3:30 PM (closing rush)
- Trades only during stable hours: 9:30 AM - 3:15 PM

**Example**:
```
09:15 Signal arrives → Rejected ❌
      (Opening hour volatility)

09:45 Signal arrives → Accepted ✅
      (Stable trading hours)

03:20 Signal arrives → Rejected ❌
      (Closing hour rush)
```

**Measured performance effect**: Not established

---

## Step-by-Step Integration

### Phase 1: Add Filters Module (30 minutes)
```bash
# Already done: accuracy_filters.py created
# Just need to copy to market_bot/
```

### Phase 2: Update kite_main.py (1 hour)
```python
# 1. Add import
from .accuracy_filters import AccuracyFilters

# 2. Initialize in __init__
self.accuracy_filters = AccuracyFilters()

# 3. Add validation in on_bar_complete
can_trade = self.accuracy_filters.validate_entry(...)
if not can_trade:
    return
```

### Phase 3: Test with Paper Trading (1+ week)
```bash
# Run bot on paper trading account
# Track trade count, win rate, costs, drawdown, and rejected signals against a
# predeclared baseline. No improvement is assumed.
```

### Phase 4: Live-trading decision

Do not use a win-rate threshold alone to authorize live orders. The figures in
this historical guide are not validated. Live use requires independent review
of cost-adjusted forward results, risk limits, broker execution and recovery,
and an explicit operator decision. See
[README_RELIABILITY.md](README_RELIABILITY.md); the current verdict is NO-GO.

---

## Testing Checklist

- [ ] accuracy_filters.py created
- [ ] Import added to kite_main.py
- [ ] AccuracyFilters initialized
- [ ] validate_entry called in on_bar_complete
- [ ] Previous bar tracking added
- [ ] Time extraction added
- [ ] Filters properly reject weak signals
- [ ] Paper trading run for 3+ days
- [ ] Record performance and costs without treating a minimum win rate as proof
- [ ] Trade journal shows expected pattern
- [ ] All features working without errors

---

## Monitoring After Implementation

### Daily Checks
```
1. Open bot logs
2. Count trades and compare with the predeclared baseline
3. Review cost-adjusted P&L; do not assume it will be positive
4. Verify filters working (see reject messages)
```

### Weekly Review
```python
# Review trades.jsonl
import json

wins = 0
losses = 0
with open('trades.jsonl') as f:
    for line in f:
        trade = json.loads(line)
        if trade['pnl'] > 0:
            wins += 1
        else:
            losses += 1

win_rate = wins / (wins + losses) * 100
print(f"Win rate: {win_rate:.1f}%")  # Descriptive metric, not a go-live gate
```

### Monthly Analysis
```
Track:
- Total trades (fewer, high quality)
- Win rate (>60%)
- Average win (higher)
- Average loss (lower)
- Profit factor (>1.5)
- Sharpe ratio (>1.0)
```

---

## Troubleshooting

### Issue: Too Few Trades (<5 per day)
```
Cause: Filters too strict
Fix: Adjust thresholds:
- Lower score threshold to 88 (from 90)
- Increase volatility range to 0.7-5.5%
- Reduce cooldown to 300 seconds (already minimum)
```

### Issue: No measurable performance improvement

```
Cause: The filter hypothesis was not supported by the observed sample
Fix: Preserve the result, check data quality and costs, and avoid tuning on the
same evaluation sessions
```

### Issue: Missing Good Trades
```
Cause: Confirmation candle too strict
Fix: Adjust confirmation criteria:
- Allow 95% candle confirmation (vs 100%)
- Accept close within 0.05% of previous
```

### Issue: Filters Not Working
```
Debug: Check logs for messages:
"Volatility filter rejected: X%"
"Confirmation filter rejected"
"Score filter rejected: X/100"
"Cooldown period active: X seconds"
"Opening/Closing hour filter"

If no messages: Filters not being called
Check: validate_entry() called in on_bar_complete
```

---

## Quick Start Command

```bash
# After making all changes:
python run_kite_bot.py

# Expected output:
# [2024-01-15 09:30:00] INFO: Signal rejected by accuracy filters
# [2024-01-15 09:31:00] INFO: [NIFTY] Signal accepted, entering trade
# [2024-01-15 09:32:00] INFO: Volatility filter rejected: 0.45% (range: 0.8-5%)
```

---

## Next Steps

1. **After Week 1 (Today)**
   - Implement these 5 filters
   - Run paper trading 3+ days
   - Record costs, drawdown, sample size, and outcomes; do not use one win-rate
     threshold as proof of profitability or live-trading approval

2. **After Week 2**
   - Add multi-timeframe confirmation
   - Fix RSI direction logic
   - Add liquidity checks

3. **After Week 3**
   - Add ML enhancement
   - Optimize parameters
   - Ready for scaling

---

**Estimated time to implement: 2-3 hours**
**Measured performance effect: none established**
**Difficulty: Easy to Medium**

Ready to implement? This is the critical first step! 🚀
