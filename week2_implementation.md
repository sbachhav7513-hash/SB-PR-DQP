# Week 2 Implementation Guide - Stability & Execution Quality

> **Evidence warning (2026-10-15):** Any trade statistics and performance
> conclusions in this historical guide are preliminary, not proof of a durable
> edge. A small sample cannot validate profitability or justify live trading.
> See [README_RELIABILITY.md](README_RELIABILITY.md) for the current deployment
> verdict.

## Summary of Changes

Week 2 proposes execution and reporting changes for paper evaluation. This guide
does not establish that the strategy is profitable or that the changes improve it.

The objective is not to chase more trades - it is to improve trade quality, reduce avoidable losses, and make the strategy more robust across symbols and market conditions.

The weekly report shows:

- Total trades: 4
- Win rate: 50.0%
- Total profit: ₹1,181.25
- Average win: ₹1,185.63
- Average loss: ₹-595.00
- Profit factor: 1.99

This four-trade snapshot is descriptive only. Its sample size is too small to
validate an edge or establish a positive profit profile. Changes in this guide
must be evaluated prospectively with realistic costs before drawing conclusions.

---

## What Changed

### 5 Key Improvements for Week 2

| Improvement | Impact | Why it matters |
|-------------|--------|----------------|
| 1. Symbol-level loss guard | Prevent repeated losses on weak symbols | Avoids one bad symbol dragging down the week |
| 2. Session trade cap | Limits over-trading | Stops rapid churn and emotional entries |
| 3. Premium/volume tuning | Better quality candidates | Filters bad liquidity and low-value setups |
| 4. Timing / regime filter tightening | Avoids bad market windows | Reduces volatility and closing-hour damage |
| 5. Weekly review journal | Improves learning loop | Makes stats actionable instead of just descriptive |

**Total changes:** ~120 lines of logic + reporting improvements  
**Time to implement:** 2-4 hours  
**Hypothesis:** these changes may affect trade quality or churn; the effect is
unknown until independently evaluated.

---

## How to Integrate (Step by Step)

### Step 1: Add stricter symbol-level controls

The historical report contains symbol-level differences, but its small sample
does not establish persistent symbol quality. Any symbol-level gate is a paper
experiment, not evidence of improved profitability.

Add a tracker in the strategy or decision journal:

```python
# Example structure
self.symbol_stats = {
    "LT_CE": {"wins": 1, "losses": 1, "net_pnl": 1391.25},
    "LT_PE": {"wins": 1, "losses": 0, "net_pnl": 630.0},
    "INFY_PE": {"wins": 0, "losses": 1, "net_pnl": -840.0},
}
```

Then gate entries like this:

```python
if symbol in self.recent_loss_symbols and self.session_symbol_loss_count[symbol] >= 1:
    logger.info(f"[{symbol}] rejected: recent loss guard")
    return False
```

This prevents one weak symbol from dominating the strategy when the model is otherwise stable.

### Step 2: Add session-level execution cap

The system is evaluating many opportunities but only 6 trades were opened. That is a sign the strategy is selective, but not necessarily efficient. To keep quality high without becoming too conservative, impose a stricter session cap.

Example:

```python
MAX_TRADES_PER_SESSION = 2

if self.session_trade_count >= MAX_TRADES_PER_SESSION:
    logger.info(f"Session trade cap reached: {self.session_trade_count}/{MAX_TRADES_PER_SESSION}")
    return False
```

This keeps the strategy disciplined and avoids emotional stacking or over-trading during weak conditions.

### Step 3: Improve premium/volume validation

The report shows many rejections caused by premium and volume filters. That is an expected part of the system, but the weekly report suggests the strategy may be too permissive in some areas and too restrictive in others.

Add improved validation logic:

```python
if premium < 25.0 or premium > 300.0:
    logger.info(f"[{symbol}] rejected: premium out of range ({premium})")
    return False

if volume < 500:
    logger.info(f"[{symbol}] rejected: volume too low ({volume})")
    return False
```

The goal is not to remove these checks. The goal is to use them more effectively so the model only enters when the opportunity is actually valid.

### Step 4: Add regime-aware timing checks

The historical report showed different results by hour, but that small-sample
pattern is not validated and should not be treated as a reliable timing edge.

Add a rule such as:

```python
if hour in {9, 10} and minute < 30:
    logger.info(f"[{symbol}] rejected: opening volatility window")
    return False

if hour in {15} and minute > 15:
    logger.info(f"[{symbol}] rejected: closing volatility window")
    return False
```

This reduces participation during churn-heavy periods and improves by keeping entries in the calmer zones where the strategy seems to work better.

### Step 5: Add decision review code to journal all rejected entries

The decision analysis is useful, but it should become an operational tool. Each rejected signal should be categorized so the system learns which filters are blocking valid trades.

Add logic like:

```python
if not can_trade:
    self.trade_journal.record_rejection(
        symbol=symbol,
        signal=market_score.signal,
        reason=reason,
        score=market_score.score,
        premium=premium,
        volume=volume,
        hour=hour,
        minute=minute,
    )
    return
```

This helps answer the real question: are we stopping bad trades, or are we missing good ones?

---

## Outcomes to Measure — Not Forecasts

### Trade Count Impact

The existing sample is too small to establish profitability or an edge.

Do not target a specific trade count. Record accepted and rejected signals and
compare the changes on unseen sessions.

Reason:
- Better filtering of low-quality setups
- Better symbol discipline
- More deliberate timing
- Lower random churn

### Win Rate Impact

The current win rate has not been independently validated. Do not use the
historical percentage below as a live-trading or scaling threshold.

```
Performance before/after: Not established
```

Whether fewer or better trades result is not established.

### Profit Factor Impact

The historical profit-factor figure is based on a small sample and is not
independently validated.

No target improvement is established:

```
Historical figure: 1.99 (four-trade snapshot; descriptive only)
Forward target: none established
```

Do not treat this value as a validated edge or use it to scale.

### Daily P&L Impact

The historical sample is small and does not establish a positive expectation or
support scaling.

```
Historical weekly P&L: +₹1,181.25 (four-trade snapshot; descriptive only)
Forward target: none established
```

Do not extrapolate this snapshot or tune to the same sample.

---

## Filter-by-Filter Impact

### Filter 1: Symbol-Loss Guard

**What it does**:
- Tracks recent losses for each symbol
- Rejects a second or third loss on the same symbol in a short period
- Prevents one weak ticker from dominating the week

**Example**:
```
INFY_PE loses once
Next INFY_PE entry within same session → rejected
```

**Measured performance effect**: Not established

---

### Filter 2: Session Trade Cap

**What it does**:
- Limits number of trades per session
- Prevents overtrading and emotional entries
- Forces quality over quantity

**Example**:
```
Session trade count = 2
New trade attempt = 3rd trade
Rejected
```

**Measured performance effect**: Not established

---

### Filter 3: Premium + Volume Quality Gate

**What it does**:
- Requires premium and volume to remain in the acceptable operating window
- Rejects cheap, thin, or low-liquidity trades
- Keeps the strategy from taking low-quality options exposure

**Example**:
```
Premium = ₹18.5 -> rejected
Volume = 420 -> rejected
```

**Measured performance effect**: Not established

---

### Filter 4: Timing / Regime Filter

**What it does**:
- Avoids opening volatility windows
- Avoids closing-hour chaos
- Focuses the model on the stronger middle period of the session

**Example**:
```
09:15 trade -> rejected
03:20 trade -> rejected
09:45 trade -> accepted
```

**Measured performance effect**: Not established

---

### Filter 5: Rejection Journal and Weekly Review

**What it does**:
- Logs reasons for every rejected setup
- Tracks repeated issues by filter type
- Creates a loop for consistent improvement

**Example**:
```
Reject reason: volume too low
Reject reason: premium out of range
Reject reason: same symbol repeat loss
```

**Benefit**: Turns filtering from a black box into a measurable system

---

## Paper-Only Risk and Exit Experiment

The bot now supports a forward paper experiment for the controls reviewed in
October. These controls do not alter live orders:

- Paper entries are capped at ₹1,000 initial stop risk. If one complete option
  lot exceeds the cap, the candidate is rejected rather than rounded up.
- A common paper-entry cutoff rejects new positions from 14:45 IST onward
  (45 minutes before the 15:30 regular market close). Existing positions can
  still be managed and exited.
- Candidate decisions, accepted entries, and rejection reasons are written to
  the decision journal. The paper risk evaluation records lot size, risk per
  lot, proposed quantity, risk budget, and cap rejection reason.
- New paper option positions use a path-dependent adaptive exit; live-order
  exits are unchanged. The initial hard stop remains in place until the trade
  reaches +0.5R, when the stop moves to breakeven. At +1R, the stop trails the
  best price by 0.5R; after +2R, it uses a 1R gap. The stop only ratchets
  toward profit and never loosens. The selected mode, maximum favorable R,
  and stop are persisted for restart recovery and audit.
- The 1R-activation / 1R-gap runner is still recorded independently in
  `paper_trading_data/shadow_runner_1r.jsonl` for comparison; it does not
  control the primary adaptive paper exit.
- Recent ledger outcomes varied by session: Oct 14 was -₹1,264 across 7
  trades, Oct 15 was +₹7,079.50 across 10 trades, and Oct 16 was -₹2,690.75
  across 14 trades, before unmodeled costs. This 31-trade, three-session
  sample is too small and regime-dependent to establish an optimal exit. The
  adaptive thresholds are a conservative paper experiment, not a learned or
  proven profitable policy.
- The shadow runner records paper LTP references and observed best bid/ask.
  It estimates a marketable entry at ask and exit at bid when valid quotes are
  available, falling back to LTP when quotes are missing. The comparison also
  records gross P&L, fees, additional slippage assumption, and estimated net
  P&L. Configure `paper_shadow_fee_per_order`,
  `paper_shadow_fee_bps_per_side`, and
  `paper_shadow_slippage_bps_per_side` for the broker/cost model; all example
  defaults are zero, so those defaults are not a realistic all-in cost model.

This is prospective paper evidence, not a profitability claim. Review it across
multiple sessions and symbols, including missed/blocked candidates, before
changing any live policy.

---

## Implementation Checklist

### Must-do items

- [ ] Add symbol loss guard
- [ ] Add session trading cap
- [ ] Improve premium/volume validation
- [x] Paper-test a common 14:45 entry cutoff on every entry path
- [x] Paper-test a ₹1,000 per-trade initial-risk cap, keeping the daily loss
  guard separate
- [x] Log candidate evaluations and rejection reasons
- [x] Test a path-dependent adaptive exit as the primary paper option exit
- [x] Compare the 1R runner with primary paper exits using quote-aware shadow
  fills and configurable cost assumptions
- [ ] Track weekly changes in win rate / profit factor / trade count

### Nice-to-have items

- [ ] Add per-symbol trailing stats dashboard
- [ ] Track best and worst execution times
- [ ] Create a weekly decision summary report
- [ ] Measure filter effectiveness over a 30-day window

---

## Expected Risk Profile

Week 2 should not be a high-risk expansion week.

Instead, it should aim for:

- more consistent execution
- fewer low-quality setups
- better risk control
- stronger repeatability

Do not assume profitability. Measure risk and operational outcomes without
extrapolating from a small sample.

---

## Final Conclusion

The available small-sample report does not establish a profitable structure or
durable edge. Week 2 changes are experiments only; evaluate them on unseen
paper sessions with realistic costs before making any live-trading decision.

These changes do not guarantee a cleaner, more scalable, or profitable system.
Keep them in paper evaluation until independently reviewed.
