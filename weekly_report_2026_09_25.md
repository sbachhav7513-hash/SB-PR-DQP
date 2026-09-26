# Weekly Report - 2026-09-25

## Executive Summary

This week was a negative performance week for the strategy. The system generated 6 trades, won 2 of them, and closed the week at a loss of ₹2,175.50.

The main issues were concentrated in late-session entries and weak symbol performance. The strategy is still profitable on a few setups, but it is too permissive in poor market conditions.

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Total trades | 6 |
| Win rate | 33.3% |
| Total profit | -₹2,175.50 |
| Average win | ₹1,185.63 |
| Average loss | -₹1,136.69 |
| Profit factor | 0.52 |

---

## Symbol Performance

| Symbol | Wins | Losses | Profit | Trades |
|--------|------|--------|--------|--------|
| LT_CE | 1 | 1 | ₹1,391.25 | 2 |
| LT_PE | 1 | 1 | -₹1,898.75 | 2 |
| INFY_PE | 0 | 1 | -₹840.00 | 1 |
| BANKNIFTY_CE | 0 | 1 | -₹828.00 | 1 |

### Key finding

The strategy is still positive on LT_CE, but the overall outcome is dragged down by repeated losses in LT_PE, INFY_PE, and BANKNIFTY_CE.

---

## Hour-Level Analysis

| Hour | Wins | Losses | Profit | Trades |
|------|------|--------|--------|--------|
| 4 | 1 | 1 | ₹280.00 | 2 |
| 3 | 1 | 1 | ₹901.25 | 2 |
| 6 | 0 | 2 | -₹3,356.75 | 2 |

### Key finding

Hour 6 was the major problem this week. Two losing trades in that window wiped out most of the week’s gain potential. This suggests the system should avoid late-session entries or tighten the confirmations in that period.

---

## Main Causes

### 1. Timing risk

Late-session entries are causing outsized losses.

### 2. Symbol risk

A few symbols are repeatedly failing after a single loss. The system is not yet protecting itself from symbol-level drawdown.

### 3. Execution quality

The strategy still allows poor-quality entries that are not strong enough to justify risk.

---

## Recommended Actions for Week 3

1. Add a stricter late-session filter.
2. Block repeated losses on the same symbol.
3. Limit trades per symbol and per session.
4. Raise the minimum signal quality threshold.
5. Log every rejection reason in the decision journal.

This is the right moment to shift from a volume-driven strategy to a quality-driven strategy.

---

## Week 3 Goal

The target is to move from this weak performance to a more stable and repeatable system by focusing on:

- fewer trades
- better timing
- lower symbol risk
- stronger confirmation
- better exit discipline

If these changes hold, the strategy can recover toward the 60%+ win-rate objectives expected in the next weekly cycle.
