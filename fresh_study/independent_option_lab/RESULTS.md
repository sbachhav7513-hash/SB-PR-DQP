# Independent strategy research results

## Decision

**No strategy is ready for shadow deployment based on this evidence.** The
best-looking recent variants have only a small apparent edge under a light,
assumed cost and turn negative under a higher cost assumption or after removing
their best session. The stronger historical candidates also have weak
underlying-only expectancy. Do not copy this research configuration into the
current bot or enable live orders.

The intent was a clean, separate study. The code in this folder reads the raw
CSV exports directly and does not import or modify the existing bot. It tests
whether an early opening-range breakout, a retest, or a failed-breakout reversal
could plausibly produce 5–10% option-premium moves while limiting adverse
movement. It did **not** find a robust, cost-tolerant result.

## Available data and what it can establish

| Dataset | Coverage | What it supports |
|---|---|---|
| `historical_data\NIFTY.csv` | 1,097,089 one-minute bars, 2,930 sessions, 2015-01-09 to 2026-11-23 | Long-horizon NIFTY underlying signal-path screening |
| `historical_data\BANKNIFTY.csv` | 1,097,042 one-minute bars, 2,930 sessions, 2015-01-09 to 2026-11-23 | Long-horizon BANKNIFTY underlying signal-path screening |
| `data_uploads\kite_daily` | 28 dates, 2026-10-14 to 2026-11-25; selected one-minute options and underlyings | Premium-level replay on a recent sample only |

Both long-history index files have zero volume on every row. They do not contain
historical option prices, implied volatility, or bid/ask quotes. Therefore,
they cannot prove five-year performance in option-premium returns. The long
history is used only to test whether the underlying signal direction tends to
reach a simple fixed price barrier before an adverse barrier.

The premium test used 20 sessions from 2026-10-27 through 2026-11-25. The
exports contain one-minute option OHLC candles for selected contracts, but no
historical bid/ask or implied volatility. Contract selection used the nearest
listed expiry not before the session and the strike nearest the prior-session
underlying close. This is a replay proxy, not a full reconstruction of every
contract the live process could have selected.

## Method

### Long-history signal screen

- Compared a small set of 5-, 15-, and 30-minute opening-range breakouts,
  aligned breakouts, 5-minute retests, and 15-minute failed-breakout reversals.
- Used NIFTY and BANKNIFTY only; one signal per symbol per session.
- Entered at the underlying's next-minute open after signal confirmation.
- Scored a +0.20% underlying target against a -0.10% stop, with a 60-minute
  maximum hold. If one candle touched both barriers, the stop was counted
  first.
- Used 2015–2024 as the historical training period and 2025 as a separate
  underlying-only validation year. These returns are **not option returns** and
  do not include execution costs.
- The 2025 slice was inspected during exploratory comparisons and influenced
  the shortlist. It is reported separately, but it is **not a pristine,
  untouched validation set**.

### Recent option-premium replay

- Evaluated option premium returns for 2026-10-27 through 2026-11-25.
- Entered at the selected option's next-minute candle open; exited at a modeled
  premium target/stop, an underlying invalidation, or the session close.
- Tested a -5% option-premium stop, +5% and +10% targets, and a trailing case:
  activate after +5%, trail 3% below the peak, cap at +10%.
- For ambiguous one-minute candles, modeled the protective stop and confirmed
  underlying invalidation before the profit target. On a structural
  invalidation, the modeled exit is the next minute's option open.
- Applied assumed friction of 0%, 0.25%, or 0.50% per side. These are sensitivity
  scenarios, **not measured spreads or full brokerage/tax costs**.
- Reported per-trade percentage returns. The CSV's sum of trade-return
  percentage points is not a compounded portfolio return and assumes neither
  equal capital allocation nor portfolio risk limits.

The research config and replay are reproducible with
[research_config.json](./research_config.json) and
[research.py](./research.py). The option-price outputs are in
[option_holdout_summary.csv](./results/option_holdout_summary.csv) and
[option_holdout_trades.csv](./results/option_holdout_trades.csv). The
underlying-only results are in
[underlying_proxy_summary.csv](./results/underlying_proxy_summary.csv).

## Long-history screen

The underlying proxy results below use 2015–2024 to screen and show 2025 as a
reported validation slice. Since 2025 was inspected during exploration, it is
not an untouched validation set. `R` is based on the proxy's 0.10% underlying
stop, not the option premium stop.

| Candidate | 2015–24 trades | Mean R | Profit-factor proxy | Positive years | 2025 trades | 2025 mean R | 2025 PF proxy |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5m breakout | 4,840 | -0.035 | 0.946 | 3 / 10 | 484 | -0.002 | 0.997 |
| 5m aligned breakout | 3,966 | -0.033 | 0.949 | 3 / 10 | 385 | 0.014 | 1.023 |
| 15m aligned breakout | 3,541 | -0.045 | 0.930 | 3 / 10 | 373 | 0.030 | 1.050 |
| 30m breakout | 4,051 | -0.026 | 0.959 | 4 / 10 | 414 | -0.046 | 0.924 |
| 5m retest | 3,998 | 0.003 | 1.005 | 7 / 10 | 405 | 0.120 | 1.211 |
| 15m failed breakout | 3,636 | 0.023 | 1.038 | 8 / 10 | 355 | 0.029 | 1.048 |

The 15-minute failed-breakout reversal was the least inconsistent of these
historical candidates, but its edge is very small and the 2025 result is only
one validation year. The 5-minute retest's 2025 result is better, but its
2015–2024 mean is effectively flat. Neither is strong enough to call an edge.

## Recent option-premium results

At the 0.25%-per-side assumed friction:

| Entry | Exit | Trades | Mean net premium return | PF | Positive sessions | Sum of trade %-points | Excluding best session |
|---|---|---:|---:|---:|---:|---:|---:|
| 5m breakout | +5% target / -5% stop | 167 | -0.329% | 0.850 | 6 / 20 | -54.94 | -77.62 |
| 5m breakout | +10% target / -5% stop | 167 | -0.243% | 0.910 | 6 / 20 | -40.51 | -84.10 |
| 5m breakout | +5% trail / +10% cap | 167 | +0.109% | 1.050 | 12 / 20 | +18.18 | -3.45 |
| 5m retest | +5% target / -5% stop | 138 | -0.260% | 0.871 | 11 / 20 | -35.94 | -59.63 |
| 5m retest | +10% target / -5% stop | 138 | +0.175% | 1.074 | 8 / 20 | +24.11 | -24.51 |
| 5m retest | +5% trail / +10% cap | 138 | +0.129% | 1.064 | 11 / 20 | +17.76 | -30.87 |
| 15m failed breakout | +5% target / -5% stop | 119 | -0.819% | 0.629 | 6 / 20 | -97.48 | -107.14 |
| 15m failed breakout | +10% target / -5% stop | 119 | -0.271% | 0.889 | 10 / 20 | -32.19 | -47.64 |
| 15m failed breakout | +5% trail / +10% cap | 119 | -0.305% | 0.862 | 9 / 20 | -36.24 | -51.69 |

The apparently positive 5m retest +10% case is not dependable: it had only 8
positive sessions out of 20, and removing its best session makes the sum
negative. The 5m breakout trailing case is also small and fragile: its sum is
negative after removing the best session. At 0.50% per side, the profit factors
fall to 0.806 for 5m breakout trailing, 0.924 for 5m retest +10%, and 0.831 for
5m retest trailing. Historical quotes do not establish which friction
assumption is realistic.

The +5% target was reached by 65/167 5m breakouts, 49/138 5m retests, and
34/119 15m failed-breakout trades under the candle-touch model. The +10% target
was reached by 42/167, 35/138, and 26/119 respectively. Candle high/low touches
are not proof of executable fills.

These are exploratory comparisons among multiple entry/exit combinations, not
an untouched final holdout after model selection. Trades across symbols share
market exposure and are not independent observations. A few sessions have
large influence on the apparent aggregate.

## What this says about the requested goals

1. **5–10% per option trade:** Some candles reached those premium levels, but no
   tested configuration delivered a robust net edge after even modest assumed
   friction.
2. **Early entry:** The 5-minute variants enter earlier than the 15-minute
   variants, but early entries also had frequent losses and reversals. Earlier
   entry alone is not a demonstrated advantage.
3. **Avoiding opposite swings:** The option stop and underlying-range
   invalidation limited modeled exposure, but median adverse excursion on the
   0.25%-cost holdout remained roughly 2.5–2.9% of premium. The current sample
   does not justify relaxing protection or claiming reversals are solved.

## Recommendation

- Keep the existing bot unchanged and do not deploy this filter config.
- Do not create a shadow runner from these results yet; none clears a
  cost-tolerance and session-stability bar.
- Preserve the current research outputs as a baseline for later comparisons.
  Collect a longer forward period with exact option contract prices and
  timestamped bid/ask/fill data, then evaluate the frozen rules on sessions not
  used in this comparison. Only consider a 3–4-session shadow after that
  longer test has positive net expectancy across multiple sessions and remains
  positive under realistic transaction costs.
