# Fixed ORB sanity baseline

## Result

BASELINE WORSE than the recorded PAPER traded mean under this fixed model.

This is a fixed, in-sample sanity baseline over 18 sessions, not an edge test. Eighteen sessions cannot prove an edge either way. No bot entry or exit change is proposed.

## Output order and integrity

The trade-level CSVs below were written and SHA-256 hashed before this summary was generated.

- 15-minute baseline: `orb_15m_trades.csv` SHA-256 `b44bb0a663ddcaede5dc64d57297b08fd2f6736214cdbc7f15df18612d8fbde9`
- 30-minute sensitivity: `orb_30m_sensitivity_trades.csv` SHA-256 `c0a346d2790c8df033fe0b158d753c6f4e4c518f668f327a739385bad323fb4a`
- Digests are also stored in `SHA256SUMS.txt`.

## Data and fixed rules

- Sessions: 18 (2026-10-14 through 2026-11-09); dates: 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-19, 2026-10-21, 2026-10-22, 2026-10-23, 2026-10-26, 2026-10-27, 2026-10-28, 2026-10-29, 2026-10-30, 2026-11-02, 2026-11-03, 2026-11-04, 2026-11-05, 2026-11-06, 2026-11-09. The 2026-10-20 no-data day is excluded.
- Underlyings: NIFTY, BANKNIFTY, RELIANCE, HDFCBANK, ICICIBANK, SBIN, INFY, TCS, LT. Opening-range bars and option bars use `Asia/Kolkata` minute timestamps.
- 15-minute range uses 09:15–09:29 start-stamped bars; signal scan begins with the 09:30 bar and ends with a signal bar starting by 14:45. The 30-minute sensitivity uses 09:15–09:44 and begins scanning at 09:45.
- The breakout is the first close strictly outside the range, one signal per underlying/day. Entry uses the next underlying bar's timestamp and the selected option candle's open.
- Contract selection uses the full per-day NFO snapshot: earliest expiry from the session date through +35 calendar days, then the strike nearest the underlying close on the breakout bar (ties choose lower strike). The exact selected contract must have a sampled option candle at the next-bar entry timestamp; otherwise it is counted as no option data and excluded from P&L.
- Primary option coverage: 92/153 signals had the selected-contract entry candle; 61 are no-option-data signals. Across included trades, 2869/2869 expected one-minute candles were present (100.0% overall where expected > 0).
- Each included trade is one lot. At +0.5R the stop is raised to +0.15R; the runner activates at +2R with a 1.5R gap. The current `partial_profit_v2` setting is 50% at +0.5R, but it is ineligible for these one-lot baseline positions (floor of half a lot is zero); no baseline partial is taken. The current stock +0.8R take-profit requires a valid live option bid and was not reproducible from these OHLC candles, so it is not modeled.
- `trail_close_confirm_v2` is represented by requiring a one-minute close beyond an already-active runner stop. A trailing stop updated from a candle's high applies from the following candle.
- Ambiguous intrabar sequences are handled conservatively: the stop active before the candle is checked first; newly reached locks/runner stops do not apply retroactively within that candle. A stop gap uses the candle open if it is beyond the stop; otherwise the stop level is used.
- Forced exit uses the last available option candle starting by 15:14 (15:15 close). Missing minutes are not interpolated; the observed/expected held-minute coverage appears per row.
- Entry and exit slippage: external fixed assumption of 1% of option premium on each side (entry premium +1%, exit premium −1%), as requested; it is not a bot setting.
- There are no historical bid/ask quotes in the candle dataset. This is candle-based and likely still slightly optimistic versus real fills.
- Fees use the checked-in PAPER flat brokerage mode: INR 20 per order; STT 0.15% on sell turnover; exchange 0.03553%; SEBI 0.0001%; stamp duty 0.003% on buy turnover; GST 18% on brokerage + exchange + SEBI. Round-trip brokerage is INR 40 before taxes/other charges.
- Net R divides net rupees by initial premium risk (10% of slipped entry premium × lot size). Profit factor is the ratio of positive to absolute negative net rupees.

## 15-minute baseline results

| Tier | Trades | Signals | No option data | Win rate | Mean net R | Profit factor | Net INR | Net INR excl. best | Mean R excl. best | Positive sessions | Mean candle coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|
| index | 32 | 35 | 3 | 25.0% | -0.1791 | 0.420 | -9,418.48 | -14,460.10 | -0.3513 | 2/18 | 100.0% |
| stock | 60 | 118 | 58 | 15.0% | -0.3272 | 0.330 | -19,591.72 | -23,526.63 | -0.3937 | 3/18 | 100.0% |
| combined | 92 | 153 | 61 | 18.5% | -0.2757 | 0.362 | -29,010.20 | -34,051.81 | -0.3354 | 4/18 | 100.0% |

## 30-minute sensitivity (reported separately; not selected)

| Tier | Trades | Signals | No option data | Win rate | Mean net R | Profit factor | Net INR | Net INR excl. best | Mean R excl. best | Positive sessions | Mean candle coverage |
|---|---|---|---|---|---|---|---|---|---|---|---|
| index | 30 | 33 | 3 | 40.0% | +0.5249 | 1.804 | +9,623.32 | +3,794.29 | +0.3006 | 6/18 | 100.0% |
| stock | 57 | 118 | 61 | 12.3% | -0.1931 | 0.443 | -12,089.77 | -16,024.68 | -0.2608 | 4/18 | 100.0% |
| combined | 87 | 151 | 64 | 21.8% | +0.0545 | 0.927 | -2,466.45 | -8,295.48 | -0.0266 | 6/18 | 100.0% |

No better-performing range is selected; 30 minutes is a single predeclared sensitivity only.

## Bot results on the same underlyings and dates

- Actual closed PAPER journal trades (not replay): **102**; mean gross R **+0.0923**; mean net R **+0.0035**; win rate **45.1%**; net rupees **+5,546.56**; profit factor **1.145**.
- Actual trade P&L comes from closed rows in `trades.jsonl`; recorded fills already incorporate the bot's paper bid/ask handling. The checked-in modeled fees above were deducted, with no second slippage deduction on those actual fills. Net R uses `paper_entry_risk_rupees` when available, otherwise initial-risk/stop fields and the earliest logged stop modification.
- Actual PAPER trades by recorded strategy variant: `primary`: 41 trades, mean net R +0.0920; `paper_option_range_breakout`: 32 trades, mean net R -0.1342; `paper_underlying_support_reversal`: 27 trades, mean net R -0.0144; `paper_underlying_support_reversal_stop_reentry`: 2 trades, mean net R +0.6318. The journal includes actual `paper_option_range_breakout` entries even though the checked-in current config disables that feature; all actual variants are included in the aggregate, and this is not a pure primary-only cohort.
- Actual journal risk-denominator sources: `paper_entry_risk_rupees` for 71 trades and stop-based fallback for 31.
- Rejected episodes: 474 deduplicated primary decision episodes; exact option candle contract and next-minute entry data were available for 22 (452 unmatched). The matched counterfactual mean net R is **-1.2186** on 22 episodes (net INR -8,069.49).
- Rejected-episode outcomes are a counterfactual replay, not bot trades or observed PAPER P&L. Episodes are formed from contiguous same-day/symbol/direction/rejection decision rows separated by no more than five minutes; only cases whose decision-bar OHLC matches exactly one sampled option contract (or an identical-match tie resolved by nearest spot) are assigned an outcome.
- ORB reconciliation (primary 153 signals): 33 coincide within ±5 minutes and same direction with a distinct bot signal episode; 9 with an actual bot trade timestamp; 33 with a rejected bot episode. These categories can overlap.
- Decision archive rows considered: 163709 primary deduplicated rows; bot signal episodes: 366; rejected episodes: 474. Matching compares option ticker suffix to ORB direction (BUY/CE, SELL/PE).

## Trades by underlying day direction

| ORB direction | Day direction | Trades | Share within ORB direction |
|---|---:|---:|---:|
| CE | up | 37 | 72.5% |
| CE | down | 14 | 27.5% |
| CE | flat | 0 | 0.0% |
| PE | up | 15 | 36.6% |
| PE | down | 26 | 63.4% |
| PE | flat | 0 | 0.0% |

Day direction is underlying first 09:15 bar open to its last available session close (stocks' underlying files end at 15:14; index files run later). The table includes only baseline trades with entry option data.

## Data gaps and limitations

- Option candles are sampled contracts, not complete chains. Selected contracts with no entry candle are counted but excluded; a missing bar during a held trade reduces the reported coverage and is not reconstructed.
- No bid/ask history, quote freshness, intrabar tick order, queue position, latency, market impact, or executable fill confirmation is available. The 1% one-way slippage assumption is fixed as specified, but cannot prove actual execution costs.
- The bot's actual journal does not provide complete immutable strategy state for every trade. Its net R is post-hoc modeled from the recorded entry, exit, stop, quantity, and checked-in fees; any recorded partial exit legs are used when present.
- Rejected decisions do not retain exact option-contract identifiers in the decision schema. Rejected counterfactuals are therefore restricted to a candle-value match against sampled option files; unmatched episodes have no outcome and are not in the mean.
- The stock +0.8R target cannot be faithfully reproduced without live bid validation. No standalone +0.5R breakeven is modeled: the fixed requested/current PAPER interpretation is the +0.15R lock at +0.5R.
- This sample is small, clustered by day and underlying, and includes a majority-up market period. Descriptive results do not establish predictive power.
