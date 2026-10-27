# Paper-trade winner/loser characteristics: 14-27 October 2026

## Executive summary

- **Sample:** 70 closed paper trades dated 14-Oct through 27-Oct 2026, from the journal and reconciled with date-partitioned trade Parquet files. The last recorded trade is 26-Oct; there are no 27-Oct closed trades. Outcomes are **30 winners, 39 losers, and 1 break-even**.
- **Recorded P/L:** gross winners INR 30,433.25; gross losers INR 26,570.50; net INR 3,862.75. Paper P/L excludes unmodeled execution costs.
- **Main result:** no tested numerical feature is statistically different at p<.05, nor after Benjamini-Hochberg correction. The CE/PE split is directionally different but its exact test and multiple-test-adjusted value are reported below. This sample does not establish a reliable pre-trade winner/loser rule.
- **Recommendation: A) Existing strategy can be improved** - keep it for controlled paper validation; do not replace it or deploy a new filter from this in-sample sample. A hindsight winner-envelope replay is shown only because requested; it is not evidence of forward performance.

## Scope and method

- Outcome is recorded `pnl_rupees`: >0 winner, <0 loser, =0 break-even. Break-even is kept separate rather than forced into either class.
- Entry timestamps are normalized to Asia/Kolkata. All 70 entries matched a `trade_opened` decision snapshot within 10 seconds, and all trade IDs reconcile to the date-partitioned Parquet records.
- Underlying minute bars are from the same-date Kite archive. For pre-entry context, only completed bars whose timestamp precedes the entry minute are used; the entry minute itself is excluded to avoid look-ahead. ADX and trend strength use the implementations/formula in `market_bot/engine.py`.
- `trend_strength_pct` is the strategy's absolute 20-bar close-to-close change. `momentum_aligned_5bar_pct` is signed 5-bar underlying return oriented by contract (CE positive, PE negative).
- VWAP distance uses the engine's rolling 20-bar volume-weighted calculation. It is unavailable when archived underlying volume is zero; coverage is 59/70.
- The paper journal does not save exact pivot-level support/resistance distances. The CSV therefore reports a transparent proxy: distance to the prior 10 completed underlying closes' high/low, aligned to resistance for CE and support for PE. Negative distance means price had crossed that prior boundary. Do not treat this proxy as exact pivot S/R.
- `option_entry_volume` and option candle body ratio are taken from the matched saved entry decision's option candle. Underlying candle ratio is the prior completed underlying candle's |close-open|/(high-low). Archived underlying volume includes 11 zero-valued records; use option entry volume for the recorded volume comparison.
- `entry_score_logged=0` is the range-breakout route's default/unscored value, not a measured weak underlying score. Score averages are shown as logged and the positive-score route subset is called out separately.
- These are observational associations, not causal conclusions. Mann-Whitney U tests compare winners and losers, excluding break-even; BH q values correct the listed tests for multiple comparisons. Numeric features with partial VWAP coverage use available observations only.

## 1-2. Average values of winners and losers

| Feature | Winners n | Winners mean | Winners median | Losers n | Losers mean | Losers median |
|---|---:|---:|---:|---:|---:|---:|
| Entry score (logged; 0 is unscored breakout route) | 30 | 46.33 | 65.00 | 39 | 37.18 | 0.00 |
| ADX (underlying, engine formula) | 30 | 33.36 | 33.12 | 39 | 34.88 | 33.37 |
| Trend strength (absolute 20-bar return, %) | 30 | 0.411 | 0.490 | 39 | 0.347 | 0.373 |
| Distance from rolling 20-bar VWAP (%) | 26 | 0.099 | 0.155 | 32 | -0.022 | -0.036 |
| Entry time (minute-of-day; see distributions) | 30 | 662.30 | 633.50 | 39 | 681.28 | 662.00 |
| Momentum aligned to CE/PE (5-bar return, %) | 30 | 0.225 | 0.218 | 39 | 0.197 | 0.146 |
| Distance to recent 10-bar support proxy (%) | 30 | 0.235 | 0.244 | 39 | 0.122 | -0.007 |
| Distance to recent 10-bar resistance proxy (%) | 30 | 0.073 | 0.004 | 39 | 0.141 | 0.097 |
| Relevant-side S/R proxy distance (%) | 30 | -0.038 | -0.045 | 39 | -0.046 | -0.027 |
| Option entry-bar volume (reported units) | 30 | 107,244 | 20,362 | 39 | 119,234 | 21,175 |
| Underlying completed-bar volume (archive; zero values present) | 30 | 45,480 | 22,715 | 39 | 57,394 | 14,415 |
| Underlying last-completed candle body/range | 30 | 0.586 | 0.607 | 39 | 0.632 | 0.682 |
| Option entry candle body/range | 30 | 0.563 | 0.551 | 39 | 0.660 | 0.684 |

**Positive-score subset (score 0 excluded because it is an unscored route):**
- Positive-score winners: n=18, mean 77.22, median 85.00; score mode 85 (11).
- Positive-score losers: n=19, mean 76.32, median 85.00; score mode 85 (10).

## 3. Distribution by time of day

Time bands are fixed descriptive buckets in IST, not optimized cutoffs. Percentages are within winners/losers; break-even is reported separately in the CSV.

| Entry time (IST) | Winners | Winners % | Losers | Losers % |
|---|---:|---:|---:|---:|
| 09:15-10:15 | 12 | 40.0% | 9 | 23.1% |
| 10:15-12:00 | 12 | 40.0% | 20 | 51.3% |
| 12:00-14:00 | 6 | 20.0% | 8 | 20.5% |
| 14:00-15:30 | 0 | 0.0% | 2 | 5.1% |

Mean entry time: winners **11:02 IST**; losers **11:21 IST**.

## 4-5. Distribution by symbol and CE/PE

### Underlying symbol

| Symbol | Winners | Losers | Break-even |
|---|---:|---:|---:|
| BANKNIFTY | 3 | 3 | 0 |
| HDFCBANK | 3 | 2 | 0 |
| ICICIBANK | 3 | 4 | 0 |
| INFY | 1 | 2 | 0 |
| LT | 6 | 6 | 1 |
| NIFTY | 1 | 4 | 0 |
| RELIANCE | 7 | 4 | 0 |
| SBIN | 4 | 4 | 0 |
| TCS | 2 | 10 | 0 |

### Option type

| Option type | Winners | Losers | Break-even |
|---|---:|---:|---:|
| CE | 20 | 15 | 1 |
| PE | 10 | 24 | 0 |

## 6. Most common characteristics

- **Winners:** most common underlying is **RELIANCE (7)**; CE is the majority (20/30); the most common time band is **09:15-10:15 (12)**; primary variant has 18/30 wins. Among positive-score entries, 85 (11) is the modal logged score. Winner medians: ADX 33.12, 20-bar trend strength 0.490%, aligned momentum 0.218%, option volume 20,362, underlying candle body ratio 0.607.
- **Losers:** most common underlying is **TCS (10)**; PE is the majority (24/39); the most common time band is **10:15-12:00 (20)**; range-breakout variant has 20/39 losses. Among positive-score entries, 85 (10) is the modal logged score. Loser medians: ADX 33.37, 20-bar trend strength 0.373%, aligned momentum 0.146%, option volume 21,175, underlying candle body ratio 0.682.
- Route counts are descriptive: see strategy-variant distribution below. The unscored breakout route appears in both outcome groups and should not be mistaken for a score-0 directional signal.

### Strategy-variant outcome distribution (context only)

| Strategy variant | Winners | Losers | Break-even |
|---|---:|---:|---:|
| paper_option_range_breakout | 12 | 20 | 0 |
| paper_underlying_support_reversal | 0 | 1 | 0 |
| primary | 18 | 18 | 1 |

## 7-8. Descriptive winner and loser profiles

These are empirical summaries, not thresholds. The interval column uses observed min-max among that outcome; the median is more robust to outliers.

| Feature | Winners median | Winners observed range | Losers median | Losers observed range |
|---|---:|---:|---:|---:|
| Entry score (logged; 0 is unscored breakout route) | 65.00 | 0.00-85.00 | 0.00 | 0.00-85.00 |
| ADX (underlying, engine formula) | 33.12 | 15.45-63.33 | 33.37 | 11.15-86.55 |
| Trend strength (absolute 20-bar return, %) | 0.490 | 0.035-0.859 | 0.373 | 0.003-0.805 |
| Distance from rolling 20-bar VWAP (%) | 0.155 | -0.446-0.599 | -0.036 | -0.567-0.670 |
| Entry time (minute-of-day; see distributions) | 633.50 | 584.00-831.00 | 662.00 | 583.00-913.00 |
| Momentum aligned to CE/PE (5-bar return, %) | 0.218 | -0.026-0.485 | 0.146 | -0.389-0.638 |
| Distance to recent 10-bar support proxy (%) | 0.244 | -0.084-0.623 | -0.007 | -0.215-1.114 |
| Distance to recent 10-bar resistance proxy (%) | 0.004 | -0.203-0.650 | 0.097 | -0.295-0.772 |
| Relevant-side S/R proxy distance (%) | -0.045 | -0.203-0.118 | -0.027 | -0.295-0.516 |
| Option entry-bar volume (reported units) | 20,362 | 700-2,047,370 | 21,175 | 2,275-1,332,045 |
| Underlying completed-bar volume (archive; zero values present) | 22,715 | 0-220,049 | 14,415 | 0-466,681 |
| Underlying last-completed candle body/range | 0.607 | 0.022-1.000 | 0.682 | 0.091-1.000 |
| Option entry candle body/range | 0.551 | 0.000-1.000 | 0.684 | 0.100-1.000 |

### Ideal winner profile (descriptive)

- Typical trade in this sample: CE; most often RELIANCE; usually entered before noon; median ADX 33.12; median absolute 20-bar trend strength 0.490%; median CE/PE-aligned 5-bar momentum 0.218%; median relevant-side recent-range distance -0.045%; median underlying candle body ratio 0.607; median option entry volume 20,362. These are sample descriptions, not recommended thresholds.

### Ideal loser profile (descriptive)

- Typical loser in this sample: PE; most often TCS; most often entered 10:15-12:00; median ADX 33.37; median absolute 20-bar trend strength 0.373%; median aligned momentum 0.146%; median relevant-side recent-range distance -0.027%; median underlying candle body ratio 0.682; median option entry volume 21,175. Large overlap with winners is present.

## 9. Features statistically different between winners and losers

| Feature | Winner n | Loser n | Winner mean | Loser mean | Raw p | BH q |
|---|---:|---:|---:|---:|---:|---:|
| Recorded entry score | 30 | 39 | 46.33 | 37.18 | 0.3186 | 0.5006 |
| ADX | 30 | 39 | 33.36 | 34.88 | 0.9277 | 0.9759 |
| Trend strength | 30 | 39 | 0.41 | 0.35 | 0.2629 | 0.5006 |
| Distance from rolling VWAP | 26 | 32 | 0.10 | -0.02 | 0.1571 | 0.4871 |
| Aligned 5-bar momentum | 30 | 39 | 0.23 | 0.20 | 0.1771 | 0.4871 |
| Relevant recent-range S/R distance | 30 | 39 | -0.04 | -0.05 | 0.5653 | 0.6909 |
| Underlying candle body ratio | 30 | 39 | 0.59 | 0.63 | 0.5369 | 0.6909 |
| Option entry volume | 30 | 39 | 107,244.33 | 119,234.49 | 0.9759 | 0.9759 |
| Option entry candle body ratio | 30 | 39 | 0.56 | 0.66 | 0.1529 | 0.4871 |
| Entry time (minute of day) | 30 | 39 | 662.30 | 681.28 | 0.2813 | 0.5006 |
| CE versus PE (Fisher exact) | 30 | 39 | n/a | n/a | 0.0290 | 0.3185 |

**Finding:** none of the tested features meets p<0.05; no feature remains significant after BH adjustment (q<0.05). The sample is small and in-sample, so absence of significance does not prove equivalence. Symbol-specific comparisons are shown descriptively only because this sample has sparse symbol cells. The CE/PE Fisher exact test is included in the table; interpret it with the multiple-test correction, not its raw p value alone.

## 10-13. Winner-envelope replay

For a mechanical retrospective estimate, the **winner-observed envelope** uses the min-max of winning trades for each of the following fully covered features: ADX, 20-bar trend strength, aligned 5-bar momentum, relevant-side recent-range distance, underlying candle body ratio, option entry volume, and option candle body ratio. A trade passes only if all seven are inside those observed winner ranges. Score is excluded because zero is the breakout route's unscored default; VWAP is excluded because it is unavailable on some underlying/index records. The envelope is deliberately not optimized.

| Feature | Winner-observed range used in replay |
|---|---:|
| adx | 15.4511 to 63.3298 |
| trend_strength_pct | 0.0348 to 0.8593 |
| momentum_aligned_5bar_pct | -0.0263 to 0.4847 |
| sr_relevant_distance_pct | -0.2031 to 0.1178 |
| underlying_candle_body_ratio | 0.0217 to 1.0000 |
| option_entry_volume | 700.0000 to 2,047,370.0000 |
| option_entry_body_ratio | 0.0000 to 1.0000 |

**Estimated historical losers rejected:** 15/39 (38.5%) on the same trades used to define the envelope. By construction, every winner is within its own observed sample envelope. This is therefore a hindsight/in-sample ceiling, not a prospective estimate; no out-of-sample or walk-forward replay is available here.

| Replay | Trades | Wins | Losses | Win rate* | Profit factor | Net P/L | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|
| All paper trades | 70 | 30 | 39 | 43.5% | 1.145 | INR 3,862.75 | INR 8,233.50 |
| Winner-envelope replay | 54 | 30 | 24 | 55.6% | 1.976 | INR 15,029.00 | INR 2,631.00 |

*Win rate = wins/(wins+losses); break-even trades are included in Trades but excluded from the denominator. Drawdown is peak-to-trough on chronological recorded P/L, starting at zero. Profit factor is gross winning P/L divided by absolute gross losing P/L. No fees, slippage, or bid/ask costs are modeled.

## Final recommendation

**A) Existing strategy can be improved.** Do not replace it based on this evidence, and do not deploy the winner envelope as a filter: no numerical feature is statistically separated at the stated significance level, several requested values are proxies/partially missing, and the attractive replay is in-sample by construction. Keep existing behavior unchanged; use this report as a discovery baseline and require a separately collected holdout before considering any strategy change.

## Trade-level data

Every paper trade and the reconstructed entry features are in [PAPER_TRADE_CHARACTERISTICS_2026-10-14_to_2026-10-27.csv](PAPER_TRADE_CHARACTERISTICS_2026-10-14_to_2026-10-27.csv). The CSV includes per-trade outcome/P&L, time, symbol/type, entry score, ADX, trend strength, VWAP distance, aligned momentum, S/R proxy distances, candle ratios, both underlying and option volume, source bar timestamp, decision match delta, and envelope membership.
