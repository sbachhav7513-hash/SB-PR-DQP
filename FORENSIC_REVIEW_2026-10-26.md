# Paper Trading Forensic Review — 2026-10-26

## Executive summary

The paper journal contains **7 closed trades**: 2 winners, 4 losers, and 1 flat trade. Reported gross P&L was **+INR 1,324.75**, gross profit factor **1.95**, win rate **28.6%**, and average P&L **+INR 189.25 per trade**. Realized close-to-close maximum drawdown was **INR 1,337.25**. Fees, taxes, bid/ask spread, and a complete fill/slippage record are absent, so this is not cost-adjusted net P&L.

The primary trend cohort had 6 trades and +INR 1,822.00; the new paper support/reversal cohort had 1 trade and -INR 497.25. That one support/reversal trade is too small a sample to call the variant harmful. Three of four losses were bearish option entries made close to recent underlying lows; they lost INR 1,337.25 combined (96.4% of gross losses) between 10:27 and 10:31 IST. The evidence points most strongly to **entry timing / local exhaustion**, not a generally unsuitable market or weak ADX across the day.

**Verdict: INCONCLUSIVE** on whether recent changes improved strategy performance. Today's positive gross result is encouraging, but one session, seven trades, no costs, and no controlled previous-configuration replay cannot establish causality or a durable edge.

## Evidence and limits

Reviewed:

- `paper_trading_data/2026-10/week_44/day_26/trades.parquet` — 7 trades, 69 fields.
- `paper_trading_data/2026-10/week_44/day_26/decisions.parquet` — 10,623 logged rows.
- `data_uploads/kite_daily/2026-10-26/` — 9 underlying files and the available option minute files; the data manifest identifies Kite historical minute data.
- Active `kite_config.json`, its prior committed version, and the strategy/daily changelogs.

The paper decisions contain only the most recent 5 OHLCV bars per populated `history` record (5,344 records); `bars_available` can be much larger. Rejected candidates do not have complete follow-through/exit ledgers. The archive does not store a full per-session config snapshot, score-point attribution per component, bid/ask fills, or a tick-by-tick trail-stop history. Therefore exact counterfactual P&L for trades blocked by filters and a full 9-scenario replay are not identifiable. Technical indicators below are calculated on the corresponding underlying's one-minute bars as **market-context proxies**; they are not asserted to be the bot's option-series indicator values. NIFTY and BANKNIFTY index volume is zero in the supplied files, so an index VWAP cannot be calculated.

## Reconstructed timeline

All times are IST. A `SELL` signal on a PE row is a bearish underlying signal; the option position itself was bought.

| Entry | Exit | Instrument / signal | Score / variant | Entry → exit premium | P&L (INR) | Recorded exit |
|---|---|---|---|---:|---:|---|
| 09:55:26 | 09:55:52 | LT 3650 CE / BUY | 85 / primary | 30.85 → 30.85 | 0.00 | TRAILING_STOP |
| 09:55:29 | 09:59:55 | ICICIBANK 1390 CE / BUY | 85 / primary | 7.30 → 9.70 | +1,680.00 | TRAILING_STOP |
| 09:57:07 | 09:58:10 | BANKNIFTY 54400 CE / BUY | 85 / primary | 263.25 → 297.65 | +1,032.00 | TRAILING_STOP |
| 09:57:44 | 09:58:20 | RELIANCE 1190 CE / BUY | 85 / primary | 9.25 → 9.15 | -50.00 | TRAILING_STOP |
| 10:27:40 | 10:28:46 | TCS 2520 PE / SELL | 85 / primary | 17.00 → 15.25 | -393.75 | STOP_LOSS |
| 10:30:25 | 10:31:31 | LT 3650 PE / SELL | 85 / primary | 22.95 → 20.40 | -446.25 | STOP_LOSS |
| 10:31:09 | 10:31:29 | NIFTY 22550 PE / SELL | 80 / paper_underlying_support_reversal | 69.90 → 62.25 | -497.25 | STOP_LOSS |

There were no target exits or forced exits. All trade records have `target_stage=0` and `milestone_reached_pct=0`; four exits are labelled `TRAILING_STOP`, three `STOP_LOSS`. The 2,127 `forced_exit_check` decision rows are checks, not forced-exit fills. The records preserve each final trailing stop but not the sequence of stop movements.

Six additional one-lot entries were rejected by the INR 1,000 risk cap: five NIFTY CE checks with estimated one-lot risk from INR 1,052.35 to INR 1,804.08, and one BANKNIFTY PE at INR 1,039.65. Eleven later candidate checks cite the consecutive-loss circuit breaker after the three-stop-loss cluster. Eight EMA re-entry lifecycle events were recorded; no EMA re-entry trade was opened.

## Realized trade performance

| Measure | Result |
|---|---:|
| Closed trades / wins / losses / flat | 7 / 2 / 4 / 1 |
| Gross winners / gross losses | INR 2,712.00 / INR 1,387.25 |
| Reported P&L (gross; before costs) | **+INR 1,324.75** |
| Win rate / gross profit factor | 28.6% / 1.95 |
| Average winner / average loser | +INR 1,356.00 / -INR 346.81 |
| Average trade | +INR 189.25 |
| Realized close-to-close max drawdown | INR 1,337.25 |
| Average / shortest / longest holding time | 77.6s / 19.7s / 266.3s |

Max drawdown uses realized P&L in exit-time order. It excludes intratrade mark-to-market drawdown. The reported P&L is gross; costs are not in the journal.

## Losing trades

Underlying indicators are calculated through the last available one-minute candle at or before entry. Twenty-minute return/range and proximity are descriptive proxies; VWAP is the code's rolling 20-bar form where volume exists.

| Trade | Market and entry evidence | Root cause / exit assessment | Avoidable? | Suggested fix |
|---|---|---|---|---|
| **RELIANCE_CE** — 09:57:44–09:58:20, -INR 50.00 | Underlying ADX(14) 34.9; ATR 1.51 (0.127%); 20m +0.982%; EMA9/21 spread +0.192%; rolling VWAP gap +0.609%. The CE was entered near a fresh 20-bar high. Score 85 comprised EMA bullish (25), improving MACD (18), RSI trend zone (20), recent-high proximity (10), and trend momentum (12). | Very small trailing-stop loss, not a weak-trend failure. The first post-exit 09:59 minute reached INR 11.60; the contract later peaked at INR 17.20 at 13:39. Those highs occurred after the exit; one-minute OHLC cannot establish whether a wider stop could have captured them. Possible premature/noisy trail, not proven. | **No (not demonstrated)** | Do not widen the stop from this single case. Audit timestamped quotes and the stop sequence; test the trail against exact ticks before changing it. |
| **TCS_PE** — 10:27:40–10:28:46, -INR 393.75 | Underlying ADX 45.9; ATR 4.66 (0.184%); 20m -0.452%; EMA9/21 spread -0.045%; rolling VWAP gap -0.117%. Price was only 0.158% above the preceding 20-bar low. Score 85 and reason tags show bearish EMA/MACD, low proximity and trend momentum; paper continuation explicitly relaxed compression and breakout-candle checks. | Strong trend reading, but entry was late in the local downswing and close to support; a bounce/whipsaw stopped the long PE. Exit was at INR 0.05 below the static stop (about 2.9% beyond planned stop-risk in premium terms); minute candles do not distinguish fill slippage from simulated execution. | **Yes (plausible, unverified)** | Test a paper-only retest/pullback or maximum-distance-from-breakout rule; retain the current stop and risk cap. |
| **LT_PE** — 10:30:25–10:31:31, -INR 446.25 | Underlying ADX 37.2; ATR 4.90 (0.134%); 20m -0.617%; EMA9/21 spread -0.091%; rolling VWAP gap -0.358%. Entry was only 0.016% above the preceding 20-bar low. Score 85; same relaxed-continuation reason tags as TCS. | Strong downtrend signal but extremely extended into the local low; the premium rebounded through the stop. Exit was INR 0.255 below static stop (11.1% beyond planned stop-risk in premium terms). | **Yes (plausible, unverified)** | Same entry-location/retest experiment; avoid relaxing the stop to accommodate a late entry. |
| **NIFTY_PE** — 10:31:09–10:31:29, -INR 497.25 | Underlying ADX 18.1; ATR 18.98 (0.084%); EMA9/21 spread -0.004%; 20m -0.126%; 20m range 0.308%. The special support/reversal variant scored 80 and cited a rejection at 22,688.68 with three clustered pivots. Index VWAP is unavailable because volume is zero. | Weakest trend context of the four losses; the setup was near the sideways boundary and reversed quickly. Premium fell through the stop and exited INR 0.66 below it (9.4% beyond planned stop-risk). Stop protection was directionally appropriate; the one-minute bar cannot prove the exact fill path. | **Yes (plausible, unverified)** | Keep this distinct paper-only variant tagged. Do not promote based on one trade; validate level reclaim, higher-timeframe alignment, and quote/stop execution over the required sample. |

The three PE losses total INR 1,337.25 (96.4% of gross losing P&L). Their combined planned stop-risk was about INR 1,238.48; recorded exits exceeded those stop estimates by about INR 98.78. Since quote-side and execution timestamps are missing, this overrun cannot be assigned solely to slippage or to the paper simulator.

## Market context and missed moves

The session was not uniformly unsuitable for trend entries. From open to close, supplied underlyings returned approximately: INFY +4.12%, TCS +1.32%, RELIANCE +1.31%, NIFTY +0.86%, LT +0.57%, ICICIBANK +0.56%, BANKNIFTY +0.12%, SBIN +0.20%, and HDFCBANK -0.71%. NIFTY and BANKNIFTY made their session lows around 09:26 and many names reached early highs around 10:08. The losers clustered later, in a short local reversal window.

| Candidate move | Logged filter / reason ignored | Correctness and indicative profit |
|---|---|---|
| **TCS call, 09:56–09:59**: TCS_CE generated a score-85 BUY at 09:56:39 and was rejected for `OPTION_FILTER_WEAK_CANDLE_MOMENTUM`. The corresponding 2520 CE proxy moved from about INR 37.05 around the signal to a later high of INR 44.15 (+19.2% MFE); at 225 units that is a theoretical peak excursion of about INR 1,597.50. | Rejection is **plausibly correct**: the minute candle also fell to INR 33.20 after the signal, below a 10% stop near INR 33.35, before the later high. The sequence within the bar is unknown. The MFE is not a captured or expected profit; a stop-first replay would likely lose about INR 866 at that low for 225 units. |
| **INFY long, full session**: underlying rose +4.12% open-to-close and had a 4.90% high/low range. No INFY directional option signal or specific INFY filter rejection appears in the decision archive; INFY rows are context/exit-check records. | The supplied INFY 1160 CE never exceeded INR 11.55, below the active INR 12 minimum premium. This is a plausible eligibility explanation, not an explicit logged rejection. No option P&L estimate is supportable from the available contracts. |
| **RELIANCE CE re-entry checks, 10:07:45 / 10:09:44 / 10:11:45**: three BUY checks were blocked by the 15-minute stop-re-entry cooldown; scores were 85, 85, and 65. The matched 1190 CE minute closes were approximately INR 11.30, 11.20, and 13.05; that contract later reached INR 17.20 at 13:39. | These are not demonstrated missed trades: the first two prices were below the INR 12 premium floor, and the third score was below the re-entry floor of 75. The later high gives a theoretical ceiling of INR 2,075 from INR 13.05 at 500 units, not a feasible or expected P&L. The cooldown was redundant with other recorded gates for these checks. |

## False-positive classification

In hindsight, all four losing fills are false positives, but their causes differ. TCS and LT PE are best classified as **chasing/late entries at local support** rather than weak trend (combined loss INR 840.00). NIFTY PE is a **low-momentum / near-sideways special reversal** loss (INR 497.25). RELIANCE CE is a **small trailing-stop whipsaw** (INR 50.00). There is not enough evidence to label any loss as low-volume, against-higher-timeframe, or caused by a spread simulation bug. Index volume and bid/ask data are unavailable; TCS/LT trend ADX was high, so "weak trend" does not explain those two losses.

## Active strategy and filter audit

The active paper config has `mode=PAPER`, `live_orders_confirmed=false`, `min_entry_score=60`, `min_adx=11`, `sideways_range_pct=0.30`, `sideways_net_move_pct=0.25`, `min_trend_strength=0.005`, and `allow_trend_continuation=true`. The range-breakout pilot is disabled. In the immediately prior config, paper score floor was 60 with a separate general floor of 70; therefore the effective paper score floor appears unchanged, although the normalized key now applies to the general setting too. Do not reuse this paper config for live mode without separately validating the live score floor.

Other changes/settings active and relevant today:

- **Support/reversal:** new, separately tagged paper variant, minimum score 75, 15-minute same-level cooldown, 0.20 candle-body ratio, and INR 5 premium floor. It produced one trade today, NIFTY PE, at score 80 and -INR 497.25. One result is not a performance verdict.
- **Adaptive exits:** active on all 7 trades (0.5R breakeven, 1R trail activation with 0.5R gap, 2R runner with 1R gap). Previous config used legacy paper trail keys (1R activation / 2R gap). Two winners realized INR 2,712 combined; four exits were labelled trailing stop, but no controlled prior-exit replay is available.
- **Risk cap:** explicit INR 1,000 per-trade cap; six one-lot checks exceeded it. It prevented oversized entries but the blocked trades' subsequent outcomes are unknown.
- **Late window:** active 12:00–13:00; 79 rejection mentions. Their counterfactual outcomes are unknown.
- **Trend continuation:** still enabled, with the journal explicitly saying compression and breakout-candle checks were relaxed for the six primary fills. Those six netted +INR 1,822; this is an observed cohort, not proof the relaxation improved results.
- **EMA re-entry and stop re-entry:** active; no re-entry trade opened. Recorded cooldown rejections had other apparent disqualifiers as described above.
- **Unchanged controls:** ADX/sideways thresholds, option candle-body threshold 0.60, RSI bounds 80/25, support thresholds from the prior paper config, and range-breakout disabled. No exact evidence here establishes their causal contribution.

### Filter event counts and effectiveness limits

There were 350 BUY/SELL decision rows (248 BUY, 102 SELL) and 7 opens. Rows are repeated evaluations, not unique independent candidate trades. Reason/outcome mentions include:

| Gate / status | Logged mentions | Measured outcome attribution |
|---|---:|---|
| Sideways regime reason | 3,343 | No blocked-trade outcome ledger |
| ADX too weak | 78 | No blocked-trade outcome ledger |
| Extended move | 48 | No blocked-trade outcome ledger |
| Weak option candle momentum | 117 | Includes the TCS call example; other outcomes unobserved |
| Late window | 79 | Counterfactual P&L unknown |
| Option filter outcomes (all reasons) | 152 | Overlapping reason categories; not unique candidates |
| Risk-blocked outcomes | 98 | Includes multiple controls, not a single filter |
| Per-trade risk-cap rejections | 6 | Subsequent P&L unknown |
| Consecutive-loss circuit-breaker rejections | 11 | Post-loss protection; subsequent P&L unknown |
| Accuracy cooldown rejections | 3 | Subsequent P&L unknown |
| Trade opens | 7 | 2 wins / 4 losses / 1 flat; aggregate PF 1.95 |

Per-filter before/after win rate, profit factor, and average trade cannot be computed because denied signals have no matched position lifecycle, the filters overlap, and repeated log rows are not unique opportunities. Consequently the evidence-supported ranking is limited: **risk cap and loss circuit breaker are the clearest risk controls**; weak-candle and late-window gates are active but unvalidated; the support/reversal variant is the worst observed cohort (n=1), not a proven harmful filter; the re-entry cooldown was redundant with other gates in three checks. No filter can be confidently ranked as statistically useful, harmful, or redundant for the strategy overall.

## Root cause

**Primary cause: B. Entry timing issue.**

Evidence: 3 of 4 losing trades were PEs entered within 0.02%–0.16% of the preceding 20-bar low; they account for 96.4% of gross losses and stopped within 20–66 seconds. TCS and LT had high underlying ADX (45.9 and 37.2), so their losses are not explained by weak trend detection. NIFTY's ADX was lower (18.1) and its 20-minute context was near sideways thresholds, making the support/reversal entry less robust. Stop exits limited each loss, although three fills exceeded the static stop price slightly.

## What-if scenarios

Only the current run is a measured whole-strategy scenario. The following subset arithmetic removes trades after observing their outcomes; it is **not** a replay and is highly vulnerable to selection bias.

| Scenario | Trades | Win rate | PF | P&L (INR) | Max DD (INR) | Interpretation |
|---|---:|---:|---:|---:|---:|---|
| 1. Current configuration | 7 | 28.6% | 1.95 | +1,324.75 | 1,337.25 | Measured gross result |
| 2. Previous configuration | N/A | N/A | N/A | N/A | N/A | Legacy exit/risk/score behavior cannot be replayed from 5-bar histories and missing quote/fill paths |
| 3. No sideways filter | N/A | N/A | N/A | N/A | N/A | 3,343 reason mentions do not reveal unique candidates or outcomes |
| 4. Higher ADX (20) | 6* | 33.3%* | 3.05* | +1,822.00* | 840.00* | Underlying-proxy cohort only: removes NIFTY support trade at ADX 18.1; actual scorer/history path not replayed |
| 5. Lower ADX (8) | 7* | 28.6%* | 1.95* | +1,324.75* | 1,337.25* | All 7 underlying-proxy ADX values exceed 8; not a whole-filter replay |
| 6. Higher score (85) | 6* | 33.3%* | 3.05* | +1,822.00* | 840.00* | Uniform threshold would remove the single score-80 reversal; post-hoc cohort |
| 7. Lower score (55) | 7* | 28.6%* | 1.95* | +1,324.75* | 1,337.25* | No 55–59 directional-score rows; no new observed trade identified |
| 8. Trend-only | 6* | 33.3%* | 3.05* | +1,822.00* | 840.00* | Six primary fills only; excludes the one reversal fill |
| 9. Best combination | N/A | N/A | N/A | N/A | N/A | Cannot discover/validate an optimal combination from 7 fills and censored rejected signals |

`*` Observed-trade subset metrics only; not predictive and not an execution replay. PF is gross.

## Recommendations for tomorrow

**Do not change multiple strategy variables or loosen controls based on this sample.** Exact configuration recommendation: keep `min_adx=11`, `sideways_range_pct=0.30`, `sideways_net_move_pct=0.25`, `min_entry_score=60`, `option_min_candle_body_ratio=0.60`, `max_risk_per_trade=1000`, `option_premium_stop_pct=0.10`, and the current adaptive exit ladder unchanged; keep `mode=PAPER` and live orders disabled. Keep the support/reversal variant distinctly tagged and paper-only while it accumulates the previously specified minimum of 10 closed tagged trades.

| Recommendation | Confidence | Expected effect |
|---|---|---|
| Keep per-trade risk cap, stops, loss circuit breaker, and live-order safeguards | High for risk containment | No defensible forward win-rate/PF/P&L estimate; avoids weakening measured risk controls |
| Make no threshold or exit-tuning change tomorrow | High, given insufficient evidence | Expected metric deltas unknown; current 7-trade gross baseline is not a forecast |
| Run an isolated paper retest/entry-distance study on the local-low PE losses | Medium that it targets the observed failure mode; low on profitability | Trade count could fall; expected win rate/PF/P&L impact unknown until replay/forward sample |
| Continue support/reversal only as a tagged paper trial; do not promote or disable solely from this one loss | High on evidence discipline; low on variant edge | No reliable expectation; the single observed trade was -INR 497.25 |
| Persist full per-decision config snapshot, selected option contract, component scores, full history, and timestamped bid/ask/stop changes | High for improving auditability | No direct strategy-P&L effect; enables valid future counterfactuals |

## Final verdict

- **Biggest mistake today:** bearish option entries near local lows, especially TCS/LT PE, followed by the low-strength NIFTY reversal entry.
- **Best-performing filter:** none can be causally established. Risk cap/circuit breaker are the clearest safety controls; the primary cohort was positive but not a filter comparison.
- **Worst observed variant:** support/reversal, one trade at -INR 497.25; insufficient sample to label the change harmful.
- **Changes that appear helpful:** adaptive trailing exits booked two winners and the risk controls limited accepted trade risk; causality is not established.
- **Changes that appear harmful:** the one support/reversal fill lost; no evidence that a broader recent change degraded total performance.
- **Getting better or worse after recent modifications?** **INCONCLUSIVE.** Today's result is gross-positive, but the seven-trade sample, missing execution costs, different market day, and absent previous-config replay do not support YES or NO.
