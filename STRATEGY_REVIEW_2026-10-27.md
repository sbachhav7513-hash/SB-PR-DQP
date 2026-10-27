# Strategy Review — 2026-10-27

## Executive result

The paper session's reported zero option entries is explained by an expiry-selection mismatch, not by the core trend filters:

- The active config is in `intraday_options` mode with `option_expiry_mode="nearest"`.
- `avoid_option_expiry_day` is absent from the active config; the runtime and example config default it to `true`.
- The option provider selected the nearest expiry, while `_option_quality_gate` rejects contracts expiring on or before the current date.
- The 2026-10-27 export contains 66 option contracts and all 66 expire on 2026-10-27.

The offline core replay is not the live options pipeline. It found five underlying-proxy trades on 27-Oct (two wins, three losses), but has no option contract selection, tick quote freshness, bid/ask, IV, or option-premium exits. It therefore neither disproves the user's zero-option-entry observation nor supplies deployable option P&L.

I fixed the picker/gate mismatch without disabling the expiry safeguard: in `nearest` mode, when expiry-day avoidance is enabled, the provider now selects the nearest expiry strictly after today. This only repairs contract selection. The later-expiry 2026-10-27 options are not in the archive, so this fix has not been performance-replayed and is not a profitability claim.

No score, ADX, sideways, trend, RSI, volume, context, or time threshold change passed both the 27-Oct and prior-session tests. No strategy threshold change is recommended.

## Scope and reproducibility

- Baseline code revision: `f1d5c32`.
- Dataset: `data_uploads/kite_daily/2026-10-14`, `15`, `16`, `19`, `21`, `22`, `23`, `26`, and `27`; 1-minute underlying candles, plus option candles and NFO snapshots where present.
- 27-Oct underlying coverage: NIFTY and BANKNIFTY 375 bars each; seven cash underlyings 360 bars each. Both index volume series are zero for every bar; the seven cash-underlying volume series are non-zero.
- 27-Oct option coverage: 66 option files; manifest records expiry `2026-10-27` for all 66. It contains no later-expiry option candles.
- Earlier expiry fallback coverage: the 2026-10-19 manifest includes 50 option contracts expiring on 2026-10-27, so the nearest-later contract was present in that session's archive. The 2026-10-27 archive does not contain the next expiry.
- Replay: repository `market_bot.replay.run_replay` and its actual configured scorer, `AccuracyFilters`, one-entry-per-symbol/session rule, trailing exits, and underlying directional OHLC proxy. No fees or slippage were included because no reliable execution-cost/quote stream is archived.
- Historical comparison: eight earlier sessions, same replay and config. Returns are sums of underlying percentage returns, not account-weighted rupee P&L.
- Full option replay limitation: archives do not retain timestamped bid/ask quotes, quote freshness at decision time, IV, selected live strike/token at each decision, portfolio/risk state, or later-expiry options on 27-Oct.

## 27-Oct candidate audit

The scorer's behavior was reconstructed at each completed one-minute bar using the replay's 50-bar history, benchmark context, and exact config defaults. It produced 23 directional signal bars across five symbols. They are repeated bar-level signals, not 23 independent trades. Every one scored 73:

| Score component | Contribution |
|---|---:|
| EMA direction | 25 |
| MACD direction/momentum | 18 |
| RSI trend-zone confirmation | 20 |
| Price near recent high/low | 10 |
| **Total** | **73** |

Trend-momentum bonus was absent. The candidates had passed the configured ADX, sideways/regime, trend-strength, proximity, and benchmark-context decisions. The continuation setting was enabled, so compression-breakout and breakout-volume/ATR confirmation were intentionally relaxed by the existing strategy.

`AccuracyFilters` accepted 19/23 candidate bars and rejected four on candle confirmation. The option candle-body check at 0.60 accepted nine; all nine also passed the replay accuracy checks. The production option-quality check runs after this candle check and before `AccuracyFilters`. For those nine, if a fresh quote existed, the same-day expiry gate would reject the option. The historical files do not establish whether a fresh quote existed at each candidate.

| Signal time IST | Symbol | Direction | Score | Core score breakdown | Option candle body >= 0.60 | Accuracy filter | Next observable gate |
|---|---|---:|---:|---|---|---|---|
| 10:20 | TCS | SELL | 73 | 25+18+20+10 | Pass | Pass | Expiry-day block if quote is fresh |
| 10:21 | TCS | SELL | 73 | 25+18+20+10 | Fail | Pass | Weak-candle block |
| 10:22 | HDFCBANK | SELL | 73 | 25+18+20+10 | Fail | Pass | Weak-candle block |
| 10:22 | ICICIBANK | SELL | 73 | 25+18+20+10 | Pass | Pass | Expiry-day block if quote is fresh |
| 10:23 | HDFCBANK | SELL | 73 | 25+18+20+10 | Fail | Pass | Weak-candle block |
| 10:23 | ICICIBANK | SELL | 73 | 25+18+20+10 | Fail | Pass | Weak-candle block |
| 10:24 | HDFCBANK | SELL | 73 | 25+18+20+10 | Fail | Pass | Weak-candle block |
| 10:24 | ICICIBANK | SELL | 73 | 25+18+20+10 | Fail | Confirmation | Weak candle (also fails confirmation later) |
| 10:41 | TCS | BUY | 73 | 25+18+20+10 | Fail | Pass | Weak-candle block |
| 10:42 | TCS | BUY | 73 | 25+18+20+10 | Pass | Pass | Expiry-day block if quote is fresh |
| 10:43 | TCS | BUY | 73 | 25+18+20+10 | Fail | Confirmation | Weak candle (also fails confirmation later) |
| 10:44 | TCS | BUY | 73 | 25+18+20+10 | Pass | Pass | Expiry-day block if quote is fresh |
| 10:48 | TCS | BUY | 73 | 25+18+20+10 | Fail | Pass | Weak-candle block |
| 12:49 | RELIANCE | BUY | 73 | 25+18+20+10 | Pass | Pass | Expiry-day block if quote is fresh |
| 13:01 | RELIANCE | SELL | 73 | 25+18+20+10 | Pass | Pass | Expiry-day block if quote is fresh |
| 13:02 | RELIANCE | SELL | 73 | 25+18+20+10 | Fail | Confirmation | Weak candle (also fails confirmation later) |
| 13:03 | RELIANCE | SELL | 73 | 25+18+20+10 | Pass | Pass | Expiry-day block if quote is fresh |
| 13:06 | RELIANCE | SELL | 73 | 25+18+20+10 | Pass | Pass | Expiry-day block if quote is fresh |
| 13:08 | RELIANCE | SELL | 73 | 25+18+20+10 | Fail | Pass | Weak-candle block |
| 13:09 | RELIANCE | SELL | 73 | 25+18+20+10 | Fail | Confirmation | Weak candle (also fails confirmation later) |
| 13:10 | RELIANCE | SELL | 73 | 25+18+20+10 | Fail | Pass | Weak-candle block |
| 13:11 | RELIANCE | SELL | 73 | 25+18+20+10 | Pass | Pass | Expiry-day block if quote is fresh |
| 14:14 | LT | SELL | 73 | 25+18+20+10 | Fail | Pass | Weak-candle block |

### Replay trade ledger (underlying proxy only)

| Signal time | Next-bar entry | Symbol | Direction | Exit time | Exit reason | Return |
|---|---|---|---|---|---|---:|
| 10:20 | 10:21 | TCS | SELL | 11:47 | Stop loss | -0.7500% |
| 10:22 | 10:23 | HDFCBANK | SELL | 14:37 | Trailing stop | +0.6315% |
| 10:22 | 10:23 | ICICIBANK | SELL | 14:22 | Trailing stop | +0.6168% |
| 12:49 | 12:50 | RELIANCE | BUY | 13:08 | Stop loss | -0.7500% |
| 14:14 | 14:15 | LT | SELL | 14:54 | Stop loss | -0.7500% |

The replay's per-symbol/session limit prevents later same-symbol signals becoming additional trades. The two positive rows are underlying-proxy winners, not proof of profitable CE/PE trades. HDFCBANK's listed 0.60 body checks fail at its candidate bars; ICICIBANK's 10:22 signal passes body and accuracy but would be stopped at the expiry gate if a fresh quote existed.

## Funnel and gate impact

| Stage / gate | 27-Oct evidence | Outcome |
|---|---:|---|
| Evaluated underlying bars in replay | 2,597 | Replay skips evaluation while a simulated position is open |
| Directional scorer bars when evaluated continuously | 23 | All score 73 |
| ADX / trend / sideways / regime / context | 23 pass | No one-variable relaxation at nearby thresholds changed 27-Oct results |
| Entry score floor 60 | 23 pass score | 60→59/58/55 and 60→61/62 made no difference |
| Option candle body threshold 0.60 | 9 pass, 14 fail | A real upstream suppressor; loosening it was not validated for option profitability |
| Accuracy confirmation | 19 pass, 4 fail | The four fails did not pass the body gate either |
| Fresh quote / expiry / option quality | Not replayable from quote history | If a fresh quote exists, expiry check rejects all selected same-day contracts |
| Final core underlying-proxy trades | 5 | Does not equal the live options trade count |
| Final option entries reported by operator | 0 | Consistent with same-day contracts being rejected |

The exact highest-impact production gate is **avoid-option-expiry-day**, because every option contract in the 27-Oct archive expires that day and the active nearest-expiry picker selected that date. It suppresses every otherwise-eligible option contract on that date. The number of valid fresh-quote entries actually reaching that line cannot be reconstructed from minute OHLCV alone. The 0.60 candle-body gate is the largest measurable upstream bar-level rejection (14/23), but those are repeated signal bars, not unique missed trades.

### Filter purpose, test, and decision

| Filter / control | Why it exists | Evidence on this sample | Decision |
|---|---|---|---|
| Same-day expiry avoidance | Avoid expiry-day option risk | 66/66 archived 27-Oct options expire that day; nearest picker/gate conflict proved in code | Keep enabled; fix selector to pick later expiry |
| ADX floor 11 | Avoid weak-trend signals | 11→10→9 and prior 12 produced identical metrics | Keep; no evidence it caused zero |
| Sideways / regime thresholds | Avoid chop and extended moves | Small threshold variants and prior net-move 0.30 produced identical metrics | Keep; no measurable 27-Oct suppression among accepted signals |
| Trend strength 0.005 | Require measurable trend | 0.0045/0.004 improved prior proxy returns but worsened 27-Oct; 0.0055/0.006 reduced trades; 0.02 yielded zero | Keep current; do not relax/tighten on this sample |
| Minimum score 60 | Suppress lower-confidence signals | Candidate scores 73; score variants had no impact | Keep; not today's bottleneck |
| RSI veto 80/25 | Avoid extreme counter-momentum entries | All 23 candidate reasons showed RSI trend-zone, not veto | Keep; not today's bottleneck |
| Continuation true | Relax compression and breakout-volume/ATR checks for continuation | Turning it off produced zero 27-Oct trades and one prior proxy trade | Keep current paper setting; accuracy remains unvalidated |
| Context hard filter | Prevent benchmark-opposed entries | Soft mode added one 27-Oct proxy trade but remained negative and reduced prior net | Keep hard filter |
| Late window | Avoid configured midday interval | Current local config has it disabled; turning it on changed no 27-Oct result and reduced historical returns | Not a cause today; preserve current local setting |
| Volatility floor/cap | Avoid exceptionally low/high ATR | Disabling/widening and small tightening had no effect in underlying proxy | No removal justified; option quote/P&L evidence missing |
| Candle momentum 0.60 | Require directional signal candle | 14/23 bars failed, 9 passed | Keep; no evidence to lower for profitability |
| 5-minute accuracy cooldown | Limit rapid repeated entries | Runtime validates with `record_entry=False`; actual accepted-entry state is not in archive | Not separately quantified; do not remove |
| One trade per symbol/session / stop retry | Limit repeated risk; bounded paper retry | Core replay generated one trade per symbol; three stop re-entry windows expired without signal | Not a cause of zero initial option entries; keep risk limits |
| Support/reversal (added Oct 26) | Separate support/reclaim paper setup | Detector was exercised on 27-Oct bars, but repeated rolling detections are not unique trades; quote/selected-contract path is missing | Do not remove or promote on detector counts; same expiry guard still applies |

The news gate was disabled in the active config. The option files contain minute OHLCV and OI, but not tick quote freshness/spread, timestamped bid/ask, IV, or contemporaneous portfolio/risk state; those runtime gates cannot be fully counterfactually attributed.

## Controlled replay iterations

All rows below changed one setting at a time from the same baseline, then replayed 27-Oct and all eight prior sessions. `Net` and drawdown are summed/compounded underlying percentage returns from the repository proxy, not option returns or rupee P&L. The 31 tests produced no threshold candidate that was both profitable on 27-Oct and non-degrading historically.

| Iteration | Single change | 27-Oct trades / wins / net% / DD% | Prior trades / wins / net% / DD% | Verdict |
|---:|---|---|---|---|
| 0 | Baseline | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | Baseline, underlying proxy |
| 1 | ADX 11→10 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 2 | ADX 11→9 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 3 | Sideways range 0.30→0.28 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 4 | Sideways range 0.30→0.25 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 5 | Sideways net move 0.25→0.23 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 6 | Sideways net move 0.25→0.20 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 7 | Score floor 60→59 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 8 | Score floor 60→58 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 9 | Score floor 60→55 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 10 | Trend floor 0.005→0.0045 | 5 / 1 / -2.3685 / 2.3537 | 53 / 32 / +6.6328 / 3.9954 | Reject: worse target day |
| 11 | Trend floor 0.005→0.0040 | 6 / 1 / -2.6167 / 2.5960 | 64 / 38 / +10.5988 / 3.5674 | Reject: worse target day |
| 12 | Proximity 0.0075→0.0080 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 13 | Proximity 0.0075→0.0085 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 14 | Continuation true→false | 0 / 0 / — / — | 1 / 1 / +0.9853 / 0.0000 | Reject: removes all target-day signals |
| 15 | Hard context→soft | 6 / 3 / -0.4853 / 1.4944 | 47 / 24 / +0.7270 / 6.8957 | Reject: still negative today; historical net falls |
| 16 | Late window false→true | 5 / 2 / -1.0017 / 1.4944 | 46 / 23 / +0.1655 / 7.1223 | Reject: no target gain; prior return/DD worse |
| 17 | Volatility minimum 0.05→0 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 18 | Volatility maximum 5→10 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 19 | ADX 11→12 (prior value) | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact; prior change not causal |
| 20 | Sideways net move 0.25→0.30 (prior value) | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact; prior change not causal |
| 21 | Score floor 60→61 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 22 | Score floor 60→62 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 23 | Trend floor 0.005→0.0055 | 5 / 2 / -1.0017 / 1.4944 | 40 / 21 / -0.1300 / 5.1721 | Reject: prior proxy turns negative |
| 24 | Trend floor 0.005→0.0060 | 3 / 1 / -0.8832 / 0.8868 | 34 / 17 / -1.4355 / 3.8114 | Reject: lower counts, negative history |
| 25 | Trend floor 0.005→0.020 (prior default) | 0 / 0 / — / — | 0 / 0 / — / — | Reject: zero signals both samples |
| 26 | Proximity 0.0075→0.0070 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 27 | Proximity 0.0075→0.0065 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 28 | RSI vetoes 80/25→75/28 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 29 | RSI vetoes 80/25→70/30 (prior values) | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact; prior change not causal |
| 30 | Volatility minimum 0.05→0.06 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |
| 31 | Volatility maximum 5→4.9 | 5 / 2 / -1.0017 / 1.4944 | 47 / 25 / +1.1167 / 6.8470 | No impact |

## Prior-session comparison

| Session | Proxy trades | Wins | Win rate | Sum return % |
|---|---:|---:|---:|---:|
| 2026-10-14 | 3 | 1 | 33.3% | -0.6378 |
| 2026-10-15 | 4 | 4 | 100.0% | +2.0844 |
| 2026-10-16 | 4 | 1 | 25.0% | -1.3235 |
| 2026-10-19 | 8 | 4 | 50.0% | +0.3330 |
| 2026-10-21 | 5 | 0 | 0.0% | -3.7500 |
| 2026-10-22 | 8 | 3 | 37.5% | -2.0103 |
| 2026-10-23 | 6 | 5 | 83.3% | +3.0468 |
| 2026-10-26 | 9 | 7 | 77.8% | +3.3742 |
| **Prior total** | **47** | **25** | **53.2%** | **+1.1167** |

Prior replay maximum drawdown was 6.8470%. The mixed daily outcomes, small sample, underlying-only return basis, and zero-cost assumption do not establish an option-strategy edge.

## Exact change and final configuration

| Setting / behavior | Before | Final | Evidence |
|---|---|---|---|
| `avoid_option_expiry_day` | Effective default `true`; active config omitted key | Still `true`; expiry guard retained | 27-Oct manifest: 66/66 contracts expire on 27-Oct |
| `option_expiry_mode` | `nearest` | Unchanged (`nearest`) | No config change |
| Nearest-expiry provider selection | Could select today's expiry even while expiry gate rejects it | With avoidance enabled, excludes expiry `<= today` and picks nearest later expiry; errors if none | Two provider tests cover enabled and disabled behavior |
| ADX, score, trend, sideways, proximity, RSI, volatility, continuation | Current values | Unchanged | 31 one-at-a-time counterfactuals; no robust target-day improvement |

This code correction is not an instruction to trade a specific contract and is not a final profitability recommendation. The 2026-10-27 replay cannot be rerun on the later expiry because its OHLCV is absent. The deployment recommendation is to keep the strategy paper-only, preserve expiry-day avoidance and all risk controls, and collect later-expiry contract OHLCV plus timestamped bid/ask/IV and actual decision/rejection logs before measuring performance or enabling live orders.

## Acceptance questions answered

1. **Why zero trades on 27-Oct?** The options path chose the nearest contract expiring on 27-Oct while the default-on expiry quality gate rejects that contract. No exact live quote/rejection log was archived, so the precise runtime rejection reason per ticker cannot be independently reconciled.
2. **Largest suppression?** The same-day expiry gate: all 66 archived option contracts expire 27-Oct. ADX, sideways, and score settings did not cause zero in the controlled underlying replay.
3. **Which blocked later winners?** ICICIBANK SELL at 10:22 passed the 0.60 body and accuracy checks and produced +0.6168% on the underlying proxy before a trailing exit; it would be blocked by expiry if a fresh quote existed. HDFCBANK SELL at 10:22 was also a proxy winner (+0.6315%) but failed the 0.60 body check at the candidate bars. Neither result proves option profitability.
4. **Filters to remove entirely?** None. The expiry risk control remains; the selector is fixed to find a permitted later expiry. The remaining filters lack sufficient matched-option evidence for removal.
5. **Filters to relax?** None of the tested signal thresholds. Trend relaxations were negative on 27-Oct; soft context remained negative and reduced prior returns.
6. **Minimum change?** One provider-selection correction; no strategy/config threshold change.
7. **Trades after tuning?** Core replay: five underlying-proxy trades. Final actual-option trade count after the provider correction is unknown and cannot be replayed from this archive.
8. **Final net P/L?** Core 27-Oct replay: -1.0017 summed underlying percentage points, 40% wins, before costs. Rupee/option net P&L is unavailable.
9. **Historical effect?** Prior core proxy: 47 trades, 25 wins, +1.1167 summed return points, 6.8470% max drawdown. No parameter iteration was retained. Later-expiry option selection cannot be performance-validated for 27-Oct because those contracts are missing.
10. **Deployment recommendation?** Do not promote to live. Keep paper mode and expiry avoidance; collect complete contract/quote logs and re-evaluate after a valid later-expiry replay.
11. **Did recent changes contribute?** Tested prior ADX 12, sideways net move 0.30, and RSI 70/30 values: no change in replay. Continuation-off eliminated 27-Oct proxy trades, so keep continuation enabled as configured. The Oct-26 support/reversal feature is outside the core replay and cannot be credited with a trade; it cannot bypass the expiry gate.
12. **Exact code/config change?** `KiteConfig` now carries `avoid_option_expiry_day` (default true), `KiteTradingBot` passes the active setting to the provider, and nearest-expiry selection skips today's date when avoidance is enabled. No active strategy threshold was changed.
