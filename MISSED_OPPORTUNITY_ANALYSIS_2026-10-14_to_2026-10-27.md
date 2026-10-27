# Missed Opportunity Analysis — 14-Oct-2026 to 27-Oct-2026

## Executive conclusion

**No new strategy change is accepted or recommended by this analysis.** The workspace supports a partial, evidence-backed review, but it does not support the requested complete option-level replay. In particular, it cannot establish a full list of profitable missed CE/PE trades, their option-premium P/L, or whether any filter change improves both training and validation performance.

The most detailed measured counterfactual is the existing underlying-price proxy replay. It is not an options replay. On 27-Oct it produced five underlying-proxy trades, two winners and three losers, with a summed directional return of **-1.0017 percentage points**. Two signals were proxy winners that encountered production blockers, but neither is a validated missed options trade. Their option contracts, executable fills, and premium P/L are not established by the archived data.

The current paper journal contains 70 closed rows dated 14-Oct through 26-Oct: recorded gross P/L **+₹3,862.75**, 30 winners, 39 losers and one flat trade. It has no 27-Oct closed trade row. This is realized paper-journal history, not the baseline of a complete counterfactual option replay; fees, slippage and quote executability are not consistently established.

Accordingly:

- Confirmed profitable missed option trades: **not determinable**.
- Option P/L left in the market: **not determinable**.
- Accepted strategy changes from this analysis: **none**.
- Interactions, proper walk-forward validation and option-level regression counts: **not run / not measurable**.
- Production recommendation: **no parameter change based on these data; do not promote a strategy change or enable live trading on proxy evidence**.

## Scope and evidence available

The latest dated archive and bot log in this workspace are for 27-Oct-2026. The uploaded Kite archive contains these nine sessions:

| Date | Underlying candle rows | Underlying symbols | Option candle files |
|---|---:|---:|---:|
| 14-Oct | 3,270 | 9 | 28 |
| 15-Oct | 3,270 | 9 | 72 |
| 16-Oct | 3,270 | 9 | 66 |
| 19-Oct | 3,270 | 9 | 68 |
| 21-Oct | 3,270 | 9 | 66 |
| 22-Oct | 3,270 | 9 | 68 |
| 23-Oct | 3,270 | 9 | 66 |
| 26-Oct | 3,270 | 9 | 62 |
| 27-Oct | 3,270 | 9 | 66 |

No uploaded archive or paper decision folder for 20-Oct was found. This report does not infer whether that date was a trading session. The source option files contain one-minute OHLCV and open interest, but not historical bid/ask quotes, quote freshness, IV or executable fills. The 27-Oct option archive has 66 contracts and all expire that day; it has no later-expiry option candles. The decision records retain only a short recent-bar history per record rather than a complete timestamped production state.

The codebase's offline replay uses an underlying directional-price proxy. It does not reproduce the live/paper option contract selection, option-premium entry/exit, quote quality, portfolio state or all risk gates. The 27-Oct review also reports zero actual option trades for that session. Thus underlying signals and trade returns below are **leads for investigation**, not actual or simulated option P/L.

Reviewed evidence:

- `STRATEGY_REVIEW_2026-10-27.md` — 27-Oct signal/gate reconstruction, underlying-proxy replay and one-variable experiments.
- `PAPER_OPTION_REPLAY_COMPARISON.md` — limitations of the historical paper-vs-replay comparison.
- `backtest_artifacts/BASELINE_CURRENT_PROXY_REPLAY_REPORT.md` — proxy baseline context.
- `backtest_artifacts/LOSING_TRADE_ROOT_CAUSE_REPORT.md` — journal/path limitations for realized losses.
- `trades.jsonl`, `kite_bot.log`, `data_uploads/kite_daily/`, `paper_trading_data/2026-10/`, `kite_config.json`, and the replay/strategy code.

## Phase 1 — Market timeline reconstruction

The archive provides underlying and option minute OHLCV on the nine listed dates. Existing analysis recomputed the configured underlying scorer for the 27-Oct review and reports 23 directional candidate bars, each scoring 73. Those are repeated signal bars, not 23 distinct, independently executable trades. Indicators such as EMA, ADX, VWAP and support/resistance can be reconstructed from available underlying candles where the required input exists; NIFTY and BANKNIFTY index volume is zero in the archive, so their volume-weighted VWAP is unavailable.

The available data do not reconstruct every minute's complete production state. In particular, current option quotes, quote age/spread, selected live contract/token at each entry, IV, account/risk state, full entry-score snapshots, and exact order/fill timing are not archived for every decision. The requested question “would this minute eventually have generated a profitable CE and PE trade under production target/stop logic?” therefore has no complete option-level answer from these files.

## Phase 2 — Candidate missed-trade leads (27-Oct only)

The table below is the complete five-row **underlying-proxy replay ledger** documented for 27-Oct. “Return” is the underlying directional proxy result, not option return or expected rupees. The two positive rows are not confirmed missed option trades. Option MFE, option score-to-fill path, premium P/L and option win/loss are unavailable.

| Signal time | Underlying proxy | CE/PE direction | Proxy exit | Proxy return | Recorded production-path evidence | Classification |
|---|---|---|---|---:|---|---|
| 10:20 | TCS | PE | Stop loss | -0.7500% | Weak option-candle body gate | Not a profitable proxy opportunity |
| 10:22 | HDFCBANK | PE | Trailing stop | +0.6315% | Failed the 0.60 candle-body check; expiry gate would also reject if a fresh quote existed | Unverified option candidate; multiple blockers |
| 10:22 | ICICIBANK | PE | Trailing stop | +0.6168% | Passed the body and accuracy checks; expiry gate would reject if a fresh quote existed | Unverified option candidate; no later-expiry candle or fresh-quote evidence |
| 12:49 | RELIANCE | CE | Stop loss | -0.7500% | Expiry gate would reject if a fresh quote existed | Not a profitable proxy opportunity |
| 14:14 | LT | PE | Stop loss | -0.7500% | Weak option-candle body gate | Not a profitable proxy opportunity |

The proxy replay's one-trade-per-symbol/session rule also differs from the production option portfolio. The entries above cannot be used to calculate the number of captured or missed actual options trades.

## Phase 3 — Rejection causes

### Measured 27-Oct decision-event counts

The option decision journal reports 347 directional events and these event-level rejection counts. Events may repeat for a symbol/setup; these are **not unique trades or labelled profitable opportunities**.

| Rejection cause | Decision events | Missed-trade win rate | Potential option P/L lost |
|---|---:|---:|---:|
| Weak candle momentum | 149 | Not measurable | Not measurable |
| Expiry-day risk | 69 | Not measurable | Not measurable |
| Late-window restriction | 67 | Not measurable | Not measurable |
| Stale quote | 38 | Not measurable | Not measurable |
| Other / not attributable as a unique opportunity | Not reconciled | Not measurable | Not measurable |

Separately, among the 23 reconstructed scorer candidate bars, 14 failed the 0.60 option candle-body check and nine passed it. Four candidate bars failed accuracy confirmation; those four also failed the body check. This bar-level funnel must not be added to the 347 journal event counts.

The archived evidence supports the following causal statement only for the 27-Oct session: the nearest-expiry selection and the default-enabled same-day expiry guard were incompatible when all 66 archived contracts expired that day. It does **not** show which exact fresh quotes would have reached that guard, nor identify the missed-option P/L. Other requested causes—volume, momentum, cooldown, open-position/daily-loss risk blocks, paper/live mismatch and bugs—cannot be consistently attributed for all dates at unique-opportunity level from the retained data.

The ranked table above is a count of logged events, not a ranking by potential P/L. A “top causes by impact” ranking and win rate for missed trades cannot be calculated without labelled opportunity outcomes and matched option replay.

## Phase 4 — Improvement candidates

Existing experiments tested one setting at a time with the underlying replay. They do not prove option profitability.

| Candidate tested | Proxy evidence | Decision from this analysis |
|---|---|---|
| Entry score floor 60→65 or 70 | Across 14–27 archived sessions, 52 trades, 27 wins, 51.9% win rate, +0.115 summed return percentage points, PF 1.006 and 6.847% max drawdown for each floor | No proxy change in performance; no option-level approval |
| Entry score floor 75 | Zero proxy trades in the tested sample | Reject; removes all tested entries |
| Relax ADX 11→10 or 9 | No change in measured proxy trades/returns | No measured benefit |
| Loosen sideways thresholds | No change in measured proxy trades/returns | No measured benefit |
| Relax trend-strength floor to 0.0045 or 0.0040 | More proxy trades but worse 27-Oct net proxy return (-2.3685% / -2.6167%) | Reject |
| Change hard market context to soft | 27-Oct remains negative (-0.4853%); historical proxy net falls versus baseline | Reject |
| Enable the late window | No 27-Oct improvement; prior proxy net and drawdown worsen | Reject |
| Disable continuation | Zero 27-Oct proxy trades and one prior proxy trade | Reject |
| Adjust proximity, RSI or volatility thresholds | No measured proxy impact in tested variants | No measured benefit |

The current `kite_config.json` has `min_entry_score` 70 and paper mode enabled. The score-floor proxy tests show no difference between 60, 65 and 70, while the recorded-option score cohort is retrospective and does not simulate alternate fills, replacement entries or overlap. It is not evidence that 70 improves live or paper option expectancy. This report does not change or endorse a new threshold.

## Phase 5 — Individual candidate replay

An option-level baseline and candidate replay cannot be reproduced from the archived evidence. The option candles are useful for historical premium paths, but the missing selected-contract/quote/risk state prevents an exact production replay and reliable executable fill model. One-minute OHLC also cannot disambiguate intrabar target-versus-stop order when both are touched.

| Metric requested | Valid option-level baseline vs candidate result |
|---|---|
| Total trades / win rate | Not determinable |
| Profit factor / gross profit / gross loss / net P&L | Not determinable |
| Max drawdown / average trade | Not determinable |
| CE and PE results | Not determinable |

For orientation only, the **underlying proxy** baseline over the nine archived sessions reports 52 trades, 27 wins, 51.9% win rate, +0.115 summed return percentage points, PF 1.006 and 6.847% max drawdown. It is not rupee P/L and does not describe option performance.

The separate paper journal contains 70 closed rows dated 14-Oct through 26-Oct: gross recorded winners ₹30,433.25, gross recorded losers ₹26,570.50, net ₹3,862.75, 30 wins, 39 losses and one flat (42.86% win rate; PF 1.145). It contains no 27-Oct closed row. These are historical journal outcomes—not a replay baseline, not cost-adjusted, and not a candidate comparison.

## Phase 6 — Interaction analysis

No A+B, A+C, B+C or A+B+C option-level interaction replay is reported. The single-variable proxy results above do not establish three improvements that independently pass the required option-P/L gate. Defining and combining speculative candidates would not meet the requirement for historical replay evidence. Interaction performance, overtrading, and combined drawdown are therefore **not measured**.

## Phase 7 — Forward robustness

No option-level walk-forward split is accepted. A chronological split of the small, incomplete option archive would still lack the matched quote/contract/fill state needed to compute the requested outcome. The prior proxy comparison of 27-Oct against earlier sessions is not a robust, predeclared training/validation exercise and does not meet the rule that both periods improve on option P/L and drawdown.

| Test | Result |
|---|---|
| Training improvement on option P/L | Not measured |
| Validation improvement on option P/L | Not measured |
| Both periods improve | Not established; no accepted candidate |

## Phase 8 — Regression check

Option-level trades improved/unchanged/degraded counts are not available. The score-floor proxy variants 60, 65 and 70 produced identical aggregate proxy results (52 trades, 27 wins and the same return/PF/drawdown), but that does not prove that individual option trades, high-confidence entries, EMA re-entries or support/resistance behavior are unchanged. No regression approval is issued.

## Phase 9 — Optimization loop and recommendation

The measured single-variable proxy candidates either had no effect or degraded at least one tested result. No candidate meets the user's acceptance criteria of higher option net P/L **and** acceptable drawdown on both training and validation. The optimization loop therefore stops without accepting a change; this is a data limitation and a conservative stop, not proof that no better strategy exists.

### Final answers

1. **All missed opportunities:** Not determinable. Two 27-Oct proxy-winning signals are listed above as unverified option candidates; they are not confirmed missed CE/PE trades.
2. **Exact rejection reasons:** Event-level counts are available for four 27-Oct gates only; per-opportunity causal attribution across all sessions is unavailable.
3. **Potential profit left:** Not determinable in option P/L or rupees. Do not substitute underlying proxy returns.
4. **Top rejection causes:** 27-Oct event counts: weak candle 149, expiry risk 69, late window 67, stale quote 38. These are not unique trades and cannot be ranked by lost P/L.
5. **Best performing strategy changes:** None validated on actual option replay.
6–10. **Before/after win rate, net P/L, profit factor and drawdown:** No valid option candidate comparison exists. Proxy metrics are explicitly marked above and must not be represented as option metrics.
11. **Additional option trades generated:** Not determinable.
12. **Accepted improvements:** None.
13. **Rejected / unproven candidates:** Trend relaxation, soft context and late-window variants degraded proxy results in at least one comparison; threshold variants with no impact are not improvements; remaining changes lack option-level validation.
14. **Final production configuration:** No new configuration is recommended. Do not promote any candidate or enable live trading based on this report. Keep changes gated to paper until a valid exact-contract replay is available. The active configuration is not altered by this analysis.
15. **Confidence:** High confidence in the listed archive coverage, journal arithmetic and documented proxy outputs; low confidence that proxy signals correspond to profitable options; no confidence claim is possible for missed-option P/L or an untested strategy change.

## Data required to complete the requested analysis

Collect and preserve, for every decision and entry attempt:

- Timestamped exact selected option symbol/token, expiry/strike/right, and matching full-session option candles.
- Bid, ask, LTP, quote timestamp/freshness, IV and volume/open interest used by the option-quality gate.
- Full per-minute underlying and option indicator/score component snapshots, including S/R, EMA, VWAP and ADX.
- Every gate result and all failed conditions, plus cooldown, open-position, daily-loss and portfolio-risk state.
- Order intent, fill/mark price, quantity, stop/target/trailing updates, exit cause, fees, taxes and slippage assumptions.
- Later-expiry option candles and quotes for 27-Oct if testing the expiry-safe contract-selection path.

With those artifacts, rerun baseline and candidates over the same dates, freeze candidates before a chronological validation window, test interactions only after single-candidate validation, and report trade-level regression counts before considering production changes.
