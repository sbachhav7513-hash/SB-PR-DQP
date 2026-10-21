# Strategy and Accuracy Change Log

This is the detailed experiment record for strategy logic, accuracy filters, entry/exit rules, and their configuration. Read it before proposing or making one of these changes. Record every affected file in [DAILY_CHANGELOG.md](DAILY_CHANGELOG.md) as well; use this log for the experiment hypothesis, baseline, and measured outcome.

## Change Rules

- Append a record for every proposed experiment and its outcome. Never rewrite or delete an old record; correct it with a dated follow-up entry.
- Before changing anything, search this log for the same filter, parameter, problem, or hypothesis. Do not repeat a rejected or inconclusive change unless new evidence or a materially different test is recorded.
- Change one strategy or accuracy variable per experiment. Keep unrelated settings and the evaluation method unchanged so the result can be attributed.
- Record the current code/config version and baseline before the change. Compare using the same replay period or comparable paper-trading conditions, including costs where available.
- Collect at least 10 closed paper trades before a strategy decision, as required by `week3_implementation.md`. This is only a minimum screening sample, not proof of an edge. If evidence is insufficient or mixed, keep the result inconclusive and gather more data.
- Never describe a target or hypothesis as an achieved improvement. Keep the prior known-good behavior available so a failed or harmful trial can be reverted.
- Operational, security, or correctness fixes are not held back by this experiment process; test and record them, and keep them distinct from strategy-performance claims.

## Current Baseline

No historical strategy experiments have been reconstructed in this log. Do not infer past outcomes from old plans or projected performance claims. For the next proposed strategy change, capture the actual current code/config version and measured baseline before editing.

## Append-Only Experiment Record

Copy this template for each proposal. Keep the proposal and final outcome together, adding dated follow-up notes rather than replacing the original record.

```text
ID / proposed date:
Status: proposed | running | kept | reverted | inconclusive
Problem and evidence:
Prior related log entries checked:
Hypothesis (what should change and why):
Single variable being changed:
Code commit/version and config before:
Baseline period and metrics (trade count, net P&L after costs if available,
  expectancy, drawdown, win/loss sizes, and relevant filter counts):
Test method and fixed evaluation period/sample:
Change made (code/config) and date:
Results using the same metrics and method:
Decision and evidence:
Rollback/version if reverted:
Follow-up or reason to revisit:
```

## Experiment Records

No completed experiments recorded yet.

### EXP-2026-09-30-01
- Status: running; performance outcome is inconclusive until closed paper trades are recorded.
- Problem and evidence: Sept 28-30 archived sessions recorded zero BUY/SELL signals and zero opened trades. Sept 28 and 29 had 11,315 and 10,859 regular-session sideways-regime reason mentions. Sept 30 included repeated 85-point HOLDs citing missing volatility compression and breakout confirmation. Archived histories are truncated to five bars, so they cannot support a valid historical replay.
- Prior related log entries checked: No completed strategy experiment exists in this log; Week 3 guidance says retain safety gates and collect at least 10 closed paper trades before evaluating performance.
- Hypothesis: Promoting an already-scored trend-shadow candidate after all existing context, news, session, accuracy, option, and risk checks may produce a measurable paper sample without weakening those checks or changing live behavior.
- Single variable being changed: Permit validated trend-shadow candidates to enter through the existing order path only when paper mode is enabled and `paper_trade_trend_shadow_signals` is true.
- Code/config before: commit `504b6a4` plus the pre-existing uncommitted shadow instrumentation; `min_entry_score=75`, volatility range `0.05%-5.0%`, `paper_trading_enabled=true`, `live_orders_enabled=false`.
- Baseline period and metrics: Sept 28: 0 directional signals / 0 opened trades; Sept 29: 0 / 0; Sept 30: 0 / 0. The latest 7-day report recorded two closed losses (-₹3,356.75 total), too small to assess an edge.
- Test method and fixed sample: Keep existing filters/risk settings fixed; track the separately labeled paper variant until at least 10 closed trades. Do not infer a trade tomorrow or a performance gain.
- Change made: Opt-in paper-only promotion, source attribution in decision/trade archives, and separate weekly performance aggregation; dated 2026-09-30.
- Results: Pending paper-market observations; no backtest claim because archived histories are truncated.
- Decision: Running as a controlled paper experiment; do not enable for live orders.
- Rollback: Set `paper_trade_trend_shadow_signals` to `false` or revert the promotion change.
- Follow-up: Record closed-trade count, P&L, win rate, and rejection reasons after each session; keep the result inconclusive until the minimum sample is met.

### EXP-2026-09-30-02

- Status: running; performance outcome is inconclusive until closed paper trades are recorded.
- Problem and evidence: The prior paper-only shadow promotion still applies the global 75-point score floor twice, including after promotion, while recent sessions recorded zero opened trades.
- Prior related log entries checked: `EXP-2026-09-30-01`; this changes only the paper-shadow score floor and leaves its other gates unchanged.
- Hypothesis: Lowering only the paper-shadow score floor to 55, matching the scorer's existing minimum for a directional trend candidate, may produce more paper observations while the volatility, confirmation, context, news, session, option, sizing, and daily-loss gates remain active.
- Single variable being changed: `paper_shadow_min_entry_score`, from the primary floor of 75 to 55 for opted-in paper shadow trades only.
- Code/config before: commit `504b6a4` plus the uncommitted trend-shadow experiment; `paper_trading_enabled=true`, `paper_trade_trend_shadow_signals=true`, `live_orders_enabled=false`, and `min_entry_score=75`.
- Baseline period and metrics: Sept 28-30 recorded 0 directional signals / 0 opened trades per session in the prior baseline. Filter-level historical counts for this proposed threshold were not available; recent archived bars are insufficient for a valid historical replay.
- Test method and fixed evaluation period/sample: Keep every non-score gate and risk setting fixed; track separately attributed paper trades and rejection reasons until at least 10 closed paper trades. Do not infer a daily trade or performance gain.
- Change made: Added an opt-in paper-shadow-only score floor set to 55; primary and live score floors remain unchanged, dated 2026-09-30.
- Results: Pending paper-market observations.
- Decision: Running as a controlled paper experiment; do not enable for live orders.
- Rollback: Set `paper_shadow_min_entry_score` to 75 or disable `paper_trade_trend_shadow_signals`.
- Follow-up: Compare trade count, closed-trade P&L, win/loss sizes, and shadow rejection reasons with the prior baseline after each session; keep inconclusive until the minimum sample is met.

### EXP-2026-09-30-03

- Status: running; performance outcome is inconclusive until closed paper trades are recorded.
- Problem and evidence: Sept 29 recorded 10,859 regular-session mentions of the sideways-regime HOLD gate and zero directional signals/trades. The Sept 30 local archive also has zero directional signals/trades but lacks the shadow telemetry fields, so it cannot show whether the prior paper-shadow experiment was active.
- Prior related log entries checked: `EXP-2026-09-30-01` and `EXP-2026-09-30-02`; this experiment changes only whether an opted-in paper shadow candidate is evaluated past the sideways early return.
- Hypothesis: Evaluating directional candidates on sideways bars may increase paper observations while the primary signal remains HOLD and downstream score, context, volatility, confirmation, session, option, sizing, and daily-loss gates remain active.
- Single variable being changed: `paper_shadow_allow_sideways`, false/default-off to true in the paper config; only the shadow path bypasses the early regime return.
- Code/config before: commit `504b6a4` plus the uncommitted paper-shadow score-floor experiment; `paper_trading_enabled=true`, `paper_trade_trend_shadow_signals=true`, `paper_shadow_min_entry_score=55`, and `live_orders_enabled=false`.
- Baseline period and metrics: Sept 29: 0 BUY/SELL, 0 opened trades, and 10,859 sideways reason mentions. Sept 30 local archive: 0 BUY/SELL and 0 closed trades, but no shadow fields. Exact historical candidate counts at the proposed behavior are unavailable.
- Test method and fixed evaluation period/sample: Keep all other settings fixed; compare shadow candidate count, rejection reasons, and separately attributed closed-trade outcomes until at least 10 closed paper trades. Do not infer profitability or guarantee a daily entry.
- Change made: Allow opt-in paper-shadow evaluation past the sideways early return while forcing the primary signal to HOLD; dated 2026-09-30.
- Results: Pending paper-market observations.
- Decision: Running as a controlled paper-only experiment; do not enable for live orders.
- Rollback: Set `paper_shadow_allow_sideways` to `false` or disable `paper_trade_trend_shadow_signals`.
- Follow-up: After each session, inspect the daily review's shadow candidates and rejection reasons before changing any other gate.

### EXP-2026-09-30-04

- Status: proposed; performance outcome is unmeasured until closed paper trades are recorded.
- Problem and evidence: The configured option premium target was 40%, delaying profit protection; the existing staged-target and trailing logic already supports incremental target advances.
- Prior related log entries checked: `EXP-2026-09-30-01`, `EXP-2026-09-30-02`, and `EXP-2026-09-30-03`; no prior option-exit experiment exists.
- Hypothesis: Starting option profit-taking at 20% and retaining staged advances will protect gains earlier while allowing profitable moves to continue through trailing stops.
- Single variable being changed: `option_premium_target_pct`, from 0.40 to 0.20. Normal staged increments remain 0.10 and strong-signal increments remain 0.20.
- Code/config before: `option_premium_target_pct=0.40`, staged targets enabled, trailing enabled, trailing activation ratio 0.5, trailing distance ratio 0.25.
- Baseline period and metrics: No option-specific baseline was measured before this change; performance remains inconclusive until at least 10 closed paper trades are available.
- Test method and fixed evaluation period/sample: Compare option target-stage counts, trailing-stop exits, win/loss sizes, and net P&L over the next 10 closed paper option trades with all other entry and risk settings fixed.
- Change made: Set the initial option target to 20% in the active/example configs and code fallback; dated 2026-09-30.
- Results: Pending paper-market observations.
- Decision: Keep as a paper-only exit experiment; do not claim improved profitability without measured results.
- Rollback: Restore `option_premium_target_pct=0.40` and the corresponding code fallback.
- Follow-up: Review target advances and trailing-stop outcomes after each session.

### EXP-2026-10-01-01

- Status: proposed; performance outcome is unmeasured.
- Problem and evidence: The 2026-10-01 paper archive recorded 5 closed `trend_shadow_paper` futures trades, 2 wins, 3 losses, and net P&L of `-₹17,575`. The largest loss was `BANKNIFTY -₹12,870`. Paper lot simulation allowed full futures lots despite the configured `₹250` daily loss cap. The active mixed mode also produced no option executions.
- Prior related log entries checked: `EXP-2026-09-30-01` through `EXP-2026-09-30-04`; this is a risk-correction and execution-mode change based on the first closed shadow sample.
- Hypothesis: Options-only routing with strict premium stop-risk sizing will prevent oversized futures exposure and provide a lower-capital paper sample, while preserving the underlying signal and option quality gates.
- Single strategy variable being changed: Active execution mode from `intraday_both` to `intraday_options`; the paper-lot override removal is a separate risk correctness correction and is not treated as a performance improvement.
- Code/config before: `trading_mode=intraday_both`, `paper_trade_trend_shadow_signals=true`, `paper_shadow_allow_sideways=true`, `daily_max_loss=250.0`, and paper option/futures sizing could force one lot.
- Baseline period and metrics: 2026-10-01; 5 closed trades, 2 wins, 3 losses, 40% win rate, `-₹17,575` net P&L, 18 BUY signals, 5 SELL signals, and 0 option trades.
- Test method and fixed evaluation period/sample: Keep signal parameters and option quality thresholds fixed; collect at least 10 closed options paper trades and compare trade count, net P&L, average win/loss, maximum drawdown, option rejection reasons, and risk-per-trade compliance.
- Change made: Set both Kite configs to options-only, empty the dormant futures universe, disable futures discovery in the template, and disallow forced paper lots in option entry paths on 2026-10-01.
- Results: Code validation passed; focused sizing tests (`3 passed`), option provider tests (`8 passed`), full suite (`123 passed`), and both JSON config parses passed. Options-only paper performance remains pending.
- Decision: Keep futures implementation dormant behind the existing mode gate; do not enable live orders or claim improved profitability.
- Rollback: Restore `trading_mode` and the futures universe only after a deliberate risk review; retain strict risk-based sizing.
- Follow-up: Confirm the next archive contains only `*_CE`/`*_PE` trade symbols and that every opened option's estimated stop risk is at or below the configured per-trade budget.

### EXP-2026-10-01-02

- Status: correctness fix applied; option-strategy performance remains unmeasured.
- Problem and evidence: The active `intraday_options` mode did not enter the existing underlying-bar branch, so CE/PE premium histories drove directional signals. The options provider resolved spot tokens for ATM selection but returned only option tokens, preventing live underlying bars from being available. Standalone underlying callbacks also needed an explicit no-entry path, and a missing desired CE/PE leg must not fall back to the opposite side and permit a short option.
- Prior related log entries checked: `EXP-2026-10-01-01`; this corrects the data source and subscription required by the selected options-only mode, without changing indicator or accuracy-filter thresholds.
- Hypothesis: Both CE and PE entries will be evaluated from the same underlying directional signal when the underlying spot bars are subscribed, while option quote quality and premium-based risk controls continue to apply to the selected option contract.
- Single variable being changed: Signal-source/subscription routing for `intraday_options`; no strategy parameters, filter thresholds, expiry rules, or sizing values changed.
- Code/config before: Active local mode `intraday_options`; paper enabled and live orders disabled. The previous session had zero option executions; no options-only performance sample exists. Current strategy score floor is 75 and volatility bounds are 0.05%-5.0%.
- Baseline period and metrics: No valid options-only trade baseline. Prior mixed-mode session recorded 0 option trades; option expectancy and win rate are unknown.
- Test method and fixed evaluation period/sample: Verify provider token resolution, option validation history source, and no-entry handling for underlying context callbacks. Then gather at least 10 closed paper option trades and compare CE/PE counts, net P&L after costs, expectancy, average win/loss, drawdown, and rejection reasons. Do not infer an edge from test coverage or trade count.
- Change made: Preserve underlying spot tokens in options-mode subscriptions, use underlying bars for option signal evaluation in both option-enabled modes, and ignore underlying spot callbacks as direct entries in options-only mode; dated 2026-10-01.
- Results: Initial underlying-routing tests passed (`65 passed`); the two final fail-closed regressions passed (`2 passed`); final full suite passed (`126 passed`); Pylance reported no errors in touched Python files. Paper-market outcomes remain unknown.
- Decision: Keep the routing correction and fail-closed leg selection; performance remains inconclusive until the stated sample is collected.
- Rollback: Revert only the routing correction if it fails regression validation; retain the options-only mode and all risk controls pending review.
- Follow-up: Confirm paper decision histories are underlying spot bars and all opened positions are exact CE/PE option symbols before measuring results.

### EXP-2026-10-01-03

- Status: running; performance outcome is unmeasured.
- Problem and evidence: The primary accuracy score floor is 75 in the runtime and both Kite configs. The available 2026-09-29 review recorded 0 BUY/SELL signals and 0 opened trades; its maximum regular-session HOLD score was 73, but it had no classified accuracy-filter rejections, so that score distribution does not establish missed entries.
- Prior related log entries checked: `EXP-2026-09-30-02` lowered only the opt-in paper-shadow floor to 55; this experiment lowers the general primary floor to 70 and leaves that override unchanged.
- Hypothesis: Allowing primary directional signals with scores 70-74 through the score gate may increase validated entries, while all other strategy, accuracy, contract, and risk gates remain active.
- Single variable being changed: Primary `min_entry_score`, from 75 to 70. The paper-shadow override remains 55.
- Code/config before: Current workspace version before this change; active and example Kite configs set `min_entry_score=75`, `paper_shadow_min_entry_score=55`, paper trading enabled, and live orders disabled.
- Baseline period and metrics: 2026-09-29 recorded 0 BUY/SELL signals, 0 opened trades, and 0 classified filter rejections; regular-session HOLD score n=12,657, max=73. No baseline score-rejection sample or valid intraday replay is available. Historical 2026-10-01 futures results are not comparable to the current options-only setup.
- Test method and fixed evaluation period/sample: Verify exact 69/70 score boundaries, retain the 55 shadow behavior, and run the full suite. After deployment, compare score-rejection counts, opened/closed trade counts, net P&L after costs, expectancy, and drawdown; do not decide on performance before at least 10 closed paper trades.
- Change made: Set the primary accuracy floor to 70 in the filter constructor and standalone helper, Kite runtime fallback, replay fallback, and both Kite configs on 2026-10-01.
- Results: Focused score-floor tests passed (`3 passed`); full suite passed (`126 passed`); both Kite configs parsed with primary/shadow floors `70/55`; Pylance found no diagnostics in changed Python files. Paper-market observations remain pending, so strategy performance is still unmeasured.
- Decision: Keep as a controlled paper evaluation; no performance improvement is claimed and live orders remain disabled in the active config.
- Rollback: Restore primary `min_entry_score` and all four defaults to 75; leave `paper_shadow_min_entry_score` at 55.
- Follow-up: Review exact score-gate rejection counts and downstream rejection reasons after each session, then compare closed outcomes after the minimum sample.

### EXP-2026-10-01-04

- Status: running; performance outcome is unmeasured.
- Problem and evidence: The score awards the recent-high/low bonus within 0.5%, while the directional entry gate used a 0.3% default. A setup 0.3%-0.5% from the recent extreme could therefore receive the proximity score bonus but still remain HOLD. The 2026-10-01 local review recorded 4,306 decisions (4,087 HOLD, 18 BUY, 5 SELL) and 1,529 HOLD decisions scoring at least 70; 820 high-score HOLD rows included both `EMA bearish` and `Price near recent low`. Saved histories contain only five bars, preventing a reliable retrospective count of candidates in the mismatch band. Those futures/shadow observations are not a comparable performance baseline for the current options-only configuration.
- Prior related log entries checked: `EXP-2026-10-01-03` changed the accuracy floor only; no prior proximity experiment exists.
- Hypothesis: Making the recent-extreme bonus and entry gate use the same 0.5% proximity will allow bearish setups in the 0.3%-0.5% band to pass the proximity condition without relaxing downside-momentum or complete-OHLCV confirmations.
- Single variable being changed: `signal_proximity_pct` from 0.003 to 0.005, applied consistently to the score bonus and directional entry gate.
- Code/config before: Runtime, replay, and engine defaults used 0.003 for entry proximity; the score bonus was hard-coded at 0.005. The active config omitted the proximity override. Active paper mode is options-only with live orders disabled.
- Baseline period and metrics: The 2026-10-01 archive is descriptive only: 4,306 decisions, 4,087 HOLD, 18 BUY, 5 SELL; 1,529 HOLD scores >=70 and 820 such HOLD rows included bearish EMA plus recent-low reasons. Histories are truncated to five bars, and the archived losses are from the earlier futures shadow setup; no valid matched options replay or proximity-band performance estimate is available.
- Test method and fixed evaluation period/sample: Focused synthetic bearish and bullish cases place price 0.4% from the recent low/high, hold trend/score inputs fixed, and compare explicit 0.003 with the new 0.005 default. Then run the full suite. For paper evaluation, record candidate/HOLD counts by rejection reason and compare closed option outcomes after at least 10 trades; do not infer profitability from candidate count.
- Change made: Align the score bonus and entry gate to a configurable 0.5% proximity in the engine, Kite/replay defaults, and both configs on 2026-10-01.
- Results: Both focused boundary tests passed (`2 passed`); strategy suite passed (`24 passed`); full suite passed (`128 passed`); both Kite configs parsed at 0.005; Pylance found no diagnostics in changed Python files; `git diff --check` passed. Paper-market observations remain pending, so strategy performance is still unmeasured.
- Decision: Keep as a controlled paper experiment; no performance improvement is claimed. Downside momentum, complete-OHLCV confirmation, context, and order-risk safeguards remain active.
- Rollback: Restore the prior split by setting entry proximity to 0.003 and restoring the hard-coded 0.5% recent-extreme score bonus in the engine if the experiment is rejected.
- Follow-up: Inspect daily HOLD reasons and whether the additional candidates pass all later gates; evaluate closed-trade outcomes only with comparable options-paper data.

### EXP-2026-10-02-01

- Status: running; performance outcome is unmeasured.
- Problem and evidence: The option gate used 75%/80% of configured premium/volume/OI minima for strong signals, versus 65%/70% for ordinary signals, making those fallback checks stricter at high scores. Baseline option-provider tests passed (`28 passed`); active config bounds are premium 12-800, minimum volume 200, minimum OI 400, and IV 0.08-1.20. No comparable options-only closed-trade sample is available.
- Prior related log entries checked: `EXP-2026-10-01-01` and `EXP-2026-10-01-02`; neither changed option-quality thresholds.
- Hypothesis: Lower only the strong-signal fallback factors to 55% premium and 60% volume/OI, retaining ordinary factors and all absolute bounds, so the high-score fallback is actually softer without bypassing quote, expiry, or upper-bound checks.
- Single variable being changed: Strong-signal fallback factors for low premium, volume, and OI; ordinary-signal factors and configured absolute bounds remain unchanged.
- Code/config before: Workspace baseline at task start; strong factors 75%/80%, ordinary factors 65%/70%; active minimums premium 12, volume 200, OI 400. Focused test baseline: `28 passed`.
- Baseline period and metrics: No valid options-only paper sample; expectancy, P&L, and drawdown are unknown. Gate tests are correctness evidence, not performance evidence.
- Test method and fixed evaluation period/sample: Verify score-boundary cases for both CE and PE, then run focused and full suites. Keep other thresholds fixed; compare rejection reasons and closed outcomes after at least 10 paper trades.
- Change made: Strong fallback factors changed to 55% premium and 60% volume/OI; dated 2026-10-02.
- Results: Focused provider and entry-management tests passed (`70 passed`), followed by the live tick timestamp regression (`1 passed`); full suite passed (`132 passed`). Both configs parsed, diagnostics found no errors in changed Python files, and `git diff --check` passed. Paper-market results remain pending.
- Decision: Running as a controlled paper evaluation; no profitability claim.
- Rollback: Restore strong fallback factors to 75% premium and 80% volume/OI in `market_bot/kite_main.py`.
- Follow-up: Track CE/PE quote-age rejections, low premium/volume/OI reasons, opened trades, and closed outcomes separately; reassess only with a comparable options-paper sample.

### EXP-2026-10-02-02

- Status: running; historical performance is unbacktested.
- Problem and evidence: Recent archived sessions showed many weak-ADX HOLD decisions and zero opened trades on multiple days. A controlled count found 3,285 mentions of the exact `ADX too weak (0.0 < 12.0)` reason in the available decision archives. These were not all generated under the current options-only setup. No matched current-strategy option sample is available.
- Prior related log entries checked: `EXP-2026-09-30-01` through `EXP-2026-09-30-04`, `EXP-2026-10-01-01` through `EXP-2026-10-01-04`, and `EXP-2026-10-02-01`. Other paper experiments remain active; this trial is isolated to the paper-shadow ADX floor.
- Hypothesis: Evaluating otherwise-qualified paper-shadow candidates at ADX 10-12 may increase paper observations while preserving the primary/live ADX floor at 12 and retaining the other confirmation, context, option-quality, sizing, and loss controls.
- Single variable being changed: Paper-shadow minimum ADX from no override (effectively 12) to 10.0. Primary `min_adx` remains 12.0.
- Code/config before: Local options config had `min_adx=12.0`, `paper_trade_trend_shadow_signals=true`, `paper_shadow_allow_sideways=true`, and `live_orders_enabled=false`; no paper-shadow ADX override existed.
- Baseline period and metrics: Available recent paper summaries contain three zero-trade days and one five-trade day from an earlier, non-comparable futures/shadow setup. No valid matched options-only intraday replay exists; performance metrics for this trial are unavailable.
- Data limitation: The local NSE archive contains daily EOD candles only, not the bot's 1-minute underlying OHLCV; archived minute decision bars from Sept 28-29 have 1970 timestamps. Therefore a credible historical backtest cannot be run from current workspace data.
- Test method and fixed evaluation period/sample: Keep the primary ADX floor and all other strategy/risk settings fixed. Record shadow candidate counts, ADX rejection reasons, entries, and closed option outcomes; assess performance only after at least 10 closed paper option trades. Do not treat more candidates as evidence of profitability.
- Change made: Added an optional `paper_shadow_min_adx` engine/runtime setting; set it to 10.0 only in the active paper config, with live orders disabled; dated 2026-10-02.
- Results: Focused strategy/runtime tests passed (`66 passed`); full suite passed (`135 passed`); both configs parsed, Pylance diagnostics were clean, and all 27 `score_market` call sites are compatible. Historical performance remains unbacktested and paper-market observations are pending.
- Decision: User-approved unbacktested paper-only trial; do not enable for live orders based on this experiment.
- Rollback: Remove `paper_shadow_min_adx` from `kite_config.json` or disable `paper_trade_trend_shadow_signals`.
- Follow-up: Inspect the daily review for ADX/shadow candidate and rejection reasons, then compare closed options-only outcomes after the minimum sample.

### EXP-2026-10-02-03

- Status: running; strategy performance remains unmeasured.
- Problem and evidence: `get_min_score` was not called by the application and could return 88-92, while `score_market` produces scores no higher than 85. The current replay reports zero trades; no matched production option-minute data with historical quotes is available.
- Prior related log entries checked: `EXP-2026-09-30-01`, `EXP-2026-09-30-02`, and `EXP-2026-10-02-02`; this changes only how the existing score floor adapts to recent outcomes.
- Hypothesis: A modest score-floor adjustment derived from the latest ten closed trades of the same strategy variant can make paper scoring responsive to observed outcomes without changing live entries or mixing primary and shadow performance.
- Single variable being changed: The paper-only score floor after at least ten same-variant closed trades: +2 below 35% wins, +1 below 45%, unchanged below 55%, and -1 at or above 55%, always clamped to 0-85.
- Code/config before: Current primary paper floor is 75, paper-shadow floor is 55, the scorer maximum is 85, the adaptive helper is unused, and live orders are disabled in the active local config.
- Baseline period and metrics: No valid matched option replay or adequate closed-trade sample exists. Prior underlying/index proxy replays had zero trades; they cannot establish win rate or option P&L.
- Test method and fixed evaluation period/sample: Verify score bounds, sample threshold, same-variant isolation, and live-mode fixed-floor behavior. Track candidate counts and closed paper outcomes; assess performance only after at least ten closed trades for a variant.
- Change made: Corrected `get_min_score` so its thresholds stay within the configured floor and 0-85 score range, then wired it to paper primary/shadow entry validation using the latest 10 closed trades of the same variant. Paper floors remain fixed below 10 valid trades; live validation continues to use the configured fixed floor. Dated 2026-10-02.
- Results: Focused strategy/runtime/replay tests passed (`83 passed`) and the full suite passed (`136 passed`). Pylance found no diagnostics in `accuracy_filters.py`, and all call sites are signature-compatible. No historical options-only backtest or performance sample is available, so accuracy impact remains unmeasured.
- Decision: Experimental paper-only behavior; no performance improvement is claimed, and live thresholds remain fixed.
- Rollback: Remove the runtime adaptive-floor calls while retaining the configured fixed floors.
- Follow-up: Compare against a comparable paper baseline after the minimum sample; do not treat a higher trade count alone as evidence of better accuracy.

### EXP-2026-10-02-04

- Status: running; performance outcome is unmeasured.
- Problem and evidence: All 375 NIFTY and BANKNIFTY index candles in the available single-day Kite extract had zero volume; the same-day selected option CE/PE candles had nonzero volume. In the live options path, signal OHLC is sourced from the underlying while breakout volume confirmation previously read that zero index volume.
- Prior related log entries checked: `EXP-2026-10-02-02` and `EXP-2026-10-02-03`; this changes only the data source for the existing relative-volume check.
- Hypothesis: Using the selected option contract's volume, matched to the underlying signal bars by timestamp, will preserve the volume-confirmation requirement while avoiding an unusable zero-volume index series. This confirms traded-contract activity, not underlying-market breadth.
- Single variable being changed: Volume input to breakout confirmation for option signals; underlying OHLC, ATR, all other strategy gates, and entry-risk controls remain unchanged.
- Code/config before: Option-mode `score_market` received underlying bars only; `breakout_quality` returned false when average volume was zero. No same-symbol index futures volume series was configured.
- Baseline period and metrics: The 2026-09-29 report contains 375 zero-volume bars for each index and nonzero volume for both option contracts. The index proxy recorded zero trades, but that replay does not isolate this gate from sideways/ADX gates and cannot establish a missed-trade or accuracy baseline.
- Test method and fixed evaluation period/sample: Verify that the same underlying breakout passes the volume sub-check only when aligned option volume exceeds its trailing average; verify unmatched/missing volume remains rejected. Replay needs timestamp-matched underlying OHLC and selected-option volume data. Assess accuracy only after at least 10 closed option trades.
- Change made: `score_market` and `breakout_quality` now accept a separate aligned volume series. In options mode the bot passes volume from the selected option contract matched to underlying bars within half an interval; offline replay accepts `--volume-confirmation-data` and matches exact timestamps without forward filling. Underlying price/ATR confirmation remains unchanged. Dated 2026-10-02.
- Results: Focused `test_intraday_manager.py`, `test_strategy.py`, and `test_backtest.py` passed (`85 passed`); full suite passed (`138 passed`). Pylance confirmed compatibility for 27 `score_market`, 8 `breakout_quality`, and 4 `run_replay` call sites. The historical option dataset shows nonzero option volume, but no paired multi-session run or filled-trade sample was available; performance remains unmeasured.
- Decision: Keep the existing volume requirement; change only its source for options-mode confirmation. No profitability claim.
- Rollback: Stop passing the option volume series and restore the underlying history as the volume source.
- Follow-up: Compare paired-data replay rejection reasons and paper outcomes, while remembering option relative volume is not a substitute for futures/index-wide participation.

### EXP-2026-10-02-05

- Status: running; strategy performance is unmeasured.
- Problem and evidence: The option exit begins at a 20% premium target and uses a distance-based trailing stop. There is no valid options-only matched replay or measured baseline for changing that exit.
- Prior related log entries checked: `DLY-2026-09-30-06` and `EXP-2026-10-02-01` through `EXP-2026-10-02-04`; this replaces the current option exit progression and adds a directional candle-momentum entry gate without changing the score floor.
- Hypothesis: Tiered 10% premium milestones, signal-score-scaled stop locks, a score-based per-milestone time box, explicit signal-weakening exits, and a 60% directional candle-body gate will produce reviewable option trades and may improve average P&L per trade.
- Strategy package being changed: Option exits move from the fixed 20% initial target with distance-based trail to tiered milestones, while option entries additionally require the underlying signal candle body to cover at least 60% of its high-low range in the signal direction. Position size is constrained to 2-3 lots by the existing risk budget; the score floor and other confirmation gates remain unchanged. Cohort results will measure the combined package, not isolate the exit policy's effect.
- Code/config before: Active paper config used `option_premium_target_pct=0.20`, staged targets enabled, `strong_signal_score=82`, `paper_trading_enabled=true`, and `live_orders_enabled=false`. No tagged option-exit frequency or expectancy baseline was recorded.
- Baseline period and metrics: No comparable option-only trade sample or matched option-premium replay is available; baseline trade frequency and average P&L are unknown.
- Test method and fixed evaluation period/sample: Validate CE/PE milestone math, time-box resets and score thresholds, stop exits, signal weakening, lot-risk behavior, journal fields, and weekly cohort metrics. Review closed paper trades and compare frequency and average P&L with the historical fixed-20% cohort; require at least 10 closed paper option trades before judging performance.
- Change made: Added the directional 60% option-entry candle-body gate, 10% milestone progression, the agreed strong/weak score lock rules, 5/10-minute windows that restart per milestone, signal-weakening exits, 2-3-lot risk-capped sizing, broker stop ratchets, per-trade exit telemetry, and weekly fixed-20% cohort comparison. Dated 2026-10-02.
- Results: Focused `test_intraday_manager.py` passed (`47 passed`), followed by the full suite (`147 passed`). Changed Python files have no Pylance errors; changed entry and position APIs have compatible call sites; both Kite configs parse and `git diff --check` passes. Paper-market performance remains unmeasured.
- Decision: Run only under the existing paper-trading configuration; do not infer profitability or enable live orders from the change alone.
- Rollback: Restore the previous option target/trailing logic and the corresponding option sizing and journal/report changes as a single change.
- Follow-up: Inspect Friday's tagged trade frequency, average realized P&L, milestone, hold duration, and exit reason against the fixed-20% cohort; classify results as inconclusive if the sample is small or not comparable.

### EXP-2026-10-05-01

- Status: running; strategy performance is unmeasured.
- Problem and evidence: The paper-shadow path required both the general candle-confirmation check and option candle-momentum confirmation. No quantified baseline of candidates rejected specifically by these checks was recorded before this change.
- Prior related log entries checked: `EXP-2026-10-02-05`, which added directional candle confirmation for option entries; this experiment relaxes confirmation only for the separately attributed paper-shadow variant and leaves the primary/live path unchanged.
- Hypothesis: Allowing opted-in paper-shadow candidates to proceed without these confirmation checks may provide observations about the variant's trade flow; it does not imply improved accuracy or profitability.
- Single variable being changed: `paper_shadow_relax_entry_confirmation`, enabled in the active paper config and disabled in the example config. When enabled for `trend_shadow_paper`, it skips the general candle-confirmation check and option candle-momentum check; the score floor and other entry/risk controls remain active.
- Code/config before: Commit `c7f7f2f` had confirmation required; paper shadow remained enabled in the active config, live orders were disabled, and the primary score floor was 70.
- Baseline period and metrics: No count of confirmation-specific candidate rejections or comparable trade sample was recorded; trade frequency, expectancy, and accuracy baseline are unknown.
- Test method and fixed evaluation period/sample: Confirm through `test_intraday_manager.py` that the relaxation is opt-in and paper-only, the score floor remains enforced, and primary/live behavior is not relaxed. Track separately attributed closed paper trades and require at least 10 before evaluating performance.
- Change made: Added the confirmation toggle and gated both confirmation bypasses to the explicitly enabled paper-shadow variant; dated 2026-10-05.
- Results: Focused provider and intraday tests passed (`83 passed, 1 skipped`); no paper-market performance sample is available.
- Decision: Keep this as a paper-only experiment with live orders disabled; do not claim a performance improvement.
- Rollback: Set `paper_shadow_relax_entry_confirmation` to `false` or disable `paper_trade_trend_shadow_signals`.
- Follow-up: Compare confirmation-rejection counts and closed-trade outcomes for the tagged variant after at least 10 closed paper trades; keep the result inconclusive if the sample is not available or comparable.

### EXP-2026-10-05-01

- Status: proposed; performance outcome is unmeasured.
- Problem and evidence: The October 5 log excerpt showed repeated score-55 HOLDs with 20-bar moves around 0.005%-0.136%, below the active 0.5% primary trend-strength requirement. The excerpt does not include shadow rejection lines or a complete daily trade baseline.
- Prior related log entries checked: `EXP-2026-09-30-01` through `EXP-2026-09-30-03`, `EXP-2026-10-02-03`, and `EXP-2026-10-02-05`; prior paper-shadow floors cover score, sideways regime, and ADX, not the directional-move threshold.
- Hypothesis: Letting the paper-shadow candidate path use a 0.1% 20-bar directional move threshold may allow some lower-magnitude bullish/bearish candidates to reach the existing downstream paper filters, while preserving the primary 0.5% threshold and live-order guard.
- Single variable being changed: `paper_shadow_min_trend_strength`, from no override (same as primary `min_trend_strength=0.005`) to `0.001` for opted-in paper-shadow candidates only.
- Code/config before: Revision `4207332`; active local config has `min_trend_strength=0.005`, `paper_trade_trend_shadow_signals=true`, `paper_shadow_allow_sideways=true`, `paper_shadow_min_adx=10.0`, `paper_shadow_min_entry_score=55`, paper mode enabled, and live orders disabled.
- Baseline period and metrics: The provided October 5 excerpt includes no opened trades or candidate/rejection summary. It shows example moves of 0.005%-0.136% and repeated primary HOLDs; exact shadow candidates, fills, and P&L are unavailable.
- Test method and fixed evaluation period/sample: Verify BUY and SELL candidate selection at the lower floor and unchanged primary HOLD behavior; then collect shadow candidate/rejection counts and separately attributed paper outcomes. Do not judge performance until at least 10 closed paper trades; compare costs, net P&L, win/loss sizes, and drawdown when available.
- Change made: Added a separately gated paper-shadow trend-strength override at 0.1%; primary, live, score, volatility, and risk thresholds remain unchanged. Dated 2026-10-05.
- Results: The initial combined regression run failed because the paper-mode test fixture lacked `trade_journal`; after correcting that fixture, focused strategy/runtime tests passed (`80 passed`) and the full suite passed (`153 passed, 1 skipped`). Both configs parsed, `git diff --check` passed, and Pylance reported no engine diagnostics. No matched historical option replay or performance outcome is available.
- Decision: Paper-only experiment, not a claim of increased profitability or guaranteed entries.
- Rollback: Remove `paper_shadow_min_trend_strength` from the active config or disable `paper_trade_trend_shadow_signals`.
- Follow-up: Review the daily report's shadow candidate/rejection counts and closed trades after each session; keep this single-variable trial isolated until the sample threshold is met.

### EXP-2026-10-05-02

- Status: running; execution-frequency and performance outcomes are unmeasured.
- Problem and evidence: The October 5, 2026 daily paper review recorded 42 `position_size_zero` rejections. The active ₹250 `daily_max_loss` also caps per-trade sizing; two NIFTY lots at the configured ₹12 minimum premium and 20% stop have ₹312 estimated stop risk (65-unit lot).
- Prior related log entries checked: `EXP-2026-10-02-04` and `EXP-2026-10-02-05` document the paper-only option sizing and entry-confirmation controls. This change does not alter signal thresholds, option quality filters, lot bounds, or live execution.
- Hypothesis: Raising only the configured loss/risk budget to ₹350 should allow a minimum-premium two-lot NIFTY entry to pass risk sizing when sufficient aggregate daily budget remains; higher-risk contracts and entries exceeding the combined open-risk/realized-loss budget remain ineligible.
- Single variable being changed: Active `daily_max_loss`, from ₹250 to ₹350.
- Code commit/version and config before: Revision `5a449fd`; active paper-only config had account size ₹100,000, per-trade risk 1%, two-lot minimum, 20% option stop, ₹250 daily loss cap, and live orders disabled.
- Baseline period and metrics: October 5 daily review: 9,683 decisions, 270 BUY/SELL signals, zero closed trades, and 42 `position_size_zero` outcomes. Comparable entry and P&L performance by premium/underlying is unavailable.
- Test method and fixed evaluation period/sample: Verify two 65-unit NIFTY lots at ₹12 premium require ₹312 and fit the ₹350 budget. After the next 10 comparable paper sessions, compare zero-size rejections, opened and closed trades, risk at entry, realized P&L, and drawdown; do not infer profitability from trade frequency.
- Change made: Set active `daily_max_loss` to ₹350; paper mode stays on and live orders stay off. Dated 2026-10-05.
- Results: `tests/test_intraday_manager.py` passes (`50 passed`); config/diff validation passes. Paper-market frequency and P&L observations are pending.
- Decision and evidence: The selected cap covers this specified minimum-risk example with ₹38 headroom; the follow-up implementation now reserves aggregate open stop-risk and realized daily losses against the same ₹350 cap. This does not guarantee an entry or establish strategy profitability.
- Rollback/version if reverted: Set `daily_max_loss` back to ₹250.
- Follow-up or reason to revisit: Review simultaneous open-position exposure and the paper daily P&L cap behavior; revisit the cap only with explicit risk approval and measured results.

#### Risk policy clarification — 2026-10-05

- Correction: The ₹350 setting is a maximum planned loss per individual trade, not the daily stop. The active config now sets `max_risk_per_trade` to ₹350 and `daily_max_loss_pct` to 2% of `account_size` (₹2,000 for ₹100,000).
- Behavior: A ₹350 loss alone does not stop new trades. Realized daily losses reaching the 2% stop block new entries; open-position stop-risk is also reserved against that daily budget.
- Validation: Regression tests verify another trade remains eligible after a ₹350 loss and that the cumulative daily stop blocks entries.
- Paper performance remains unmeasured; this risk-policy correction does not promise a trade every day or profitability.

#### Single strategy across paper and live modes — 2026-10-05

- Decision: Retire the paper-only trend-shadow strategy and its relaxed filters following the user's request to maintain one strategy and use configuration only to select paper or live execution.
- Implementation: Paper and live modes now share the same scorer, configured score floor, directional confirmation, option-candle confirmation, and risk/quality gates. Removed shadow signal promotion, per-variant adaptive paper floors, and shadow-specific config keys.
- Historical records: Earlier shadow experiment entries, trade rows, and archived candidate telemetry are retained as historical data; they no longer define active runtime behavior.
- Validation: Focused strategy/runtime/reporting tests passed (`86 passed`); the full suite passed (`152 passed, 1 skipped`). Both Kite configs parse and `git diff --check` passed.
- Performance outcome: Unmeasured. This is a consistency/maintenance change, not a claim of improved strategy performance.

### EXP-2026-10-05-03

- Status: running; frequency and performance outcomes are unmeasured.
- Problem and evidence: The October 5 decision archive contains 270 BUY/SELL decision rows but no `trade_opened` outcome; the same-day review reports zero closed trades. The decision flow includes 165 unselected option-leg skips, 42 `position_size_zero` outcomes, 56 option-quality rejections, and 7 `position_updated` outcomes. These rows are repeated bar decisions, not 270 independent opportunities. This archive predates retirement of the paper-only shadow strategy, so it is diagnostic rather than a comparable baseline for the current unified strategy.
- Prior related log entries checked: `EXP-2026-10-02-04` and `EXP-2026-10-02-05` describe option signal confirmation and sizing; `EXP-2026-10-05-02` documented the earlier ₹350 sizing cap and was superseded by the distinct ₹2,000 daily-stop policy. The current code uses option premium and contract lot size to estimate stop-risk.
- Hypothesis: A 10% premium stop and a per-trade ceiling equal to the remaining ₹2,000 daily risk budget may admit some otherwise-valid ATM option entries while preserving the aggregate daily stop-risk limit.
- Single policy being changed: Option stop-risk budget policy, from a fixed ₹350 per-trade cap and 20% premium stop to a 10% premium stop sized up to the remaining 2% daily budget. The 10% staged first target remains unchanged, making the nominal first-stage reward-to-risk 1:1 before costs.
- Code/config before: Active config was paper-enabled/live-disabled, account size ₹100,000, `max_risk_per_trade=350`, `daily_max_loss_pct=2`, two-lot minimum, 20% option stop, and 10% first milestone.
- Baseline period and metrics: 2026-10-05; 9,683 decisions, 270 BUY/SELL decision rows, no `trade_opened` outcome, and 0 closed trades. Entry flow: 165 unselected-leg skips, 42 sizing rejects, 56 option-quality rejects, and 7 position updates. This predates shadow-strategy retirement, so it is not a matched current-strategy baseline. The 42 sizing rows do not preserve premium/lot risk detail, so the exact entry increase cannot be replayed from this archive.
- Test method and fixed evaluation period/sample: Keep universe, signal score, trend/context filters, confirmation, quote freshness, contract-quality floors, lot bounds, and exits unchanged. Compare entry-flow counts and stop-risk utilization across the next 10 paper sessions; evaluate P&L, fees/slippage, drawdown, win/loss size, and expectancy only after at least 10 closed trades. Keep live orders disabled.
- Change made: Set `max_risk_per_trade=2000` and `option_premium_stop_pct=0.10` in the active and example configs. Align paper entry price, sizing premium, and stop/target reference to the latest option price; live entries continue recalculating from broker fill price.
- Results: Focused manager/provider tests passed (`90 passed, 1 skipped`); both JSON configs parse and `git diff --check` passes. Paper-market frequency and performance remain pending.
- Decision: User-approved paper risk experiment only. A stopped position may consume nearly the entire ₹2,000 daily stop; daily loss and aggregate open-risk checks remain enabled. No daily trade or profitability is guaranteed.
- Rollback: Restore `max_risk_per_trade=350` and `option_premium_stop_pct=0.20` in the configs; revert the latest-premium alignment change if its regression test fails.
- Follow-up: Review the actual number of opened trades and stop-risk utilization, then closed-trade metrics. Never treat increased frequency by itself as an improvement.

## Operational and correctness notes (not strategy experiments)

### 2026-10-06 — Stale paper-position recovery

- Classification: Operational correctness fix; no strategy signal, entry/exit rule, or performance experiment changed.
- Change: Active paper positions persist periodic price marks. On restart, stale open records close at a valid saved mark; if no valid mark exists, recovery closes at entry price and labels the journal outcome as an estimated zero-P&L exit.
- Validation: `tests/test_intraday_manager.py` passed (`59 passed`).
- Performance outcome: Not measured and not applicable; the entry-price fallback is an accounting estimate, not evidence of actual execution or profitability.

### EXP-2026-10-07-01

- Status: running; trade frequency and performance outcomes are unmeasured.
- Problem and evidence: The October 6 archive recorded 9,207 HOLD decisions and zero BUY/SELL signals. The current active signal proximity is 0.5%; directional scoring and entry require price to be near the recent high/low as well as trend and momentum confirmation.
- Prior related log entries checked: `EXP-2026-10-05-03` records the unified paper/live strategy and pending paper risk-policy evaluation. No prior experiment widened the unified strategy's configured signal proximity.
- Hypothesis: Widening the recent-extreme proximity from 0.5% to 0.75% may admit otherwise trend- and momentum-confirmed setups that are slightly farther from the recent high/low, without changing risk, option-quality, or live-order controls.
- Single variable being changed: `signal_proximity_pct`, from `0.005` to `0.0075`.
- Code/config before: Current unified scorer with active paper trading enabled and live orders disabled; active signal proximity was `0.005`.
- Baseline period and metrics: October 6, 2026; 9,859 archived decisions, 0 BUY/SELL signals, and 0 opened trades. Archived bar history is truncated and cannot support a reliable replay of this parameter change.
- Test method and fixed evaluation period/sample: Keep all other strategy/configuration variables unchanged. Observe the next 10 comparable paper sessions and record directional candidates, entries, rejection flow, closed-trade P&L after costs, win/loss sizes, and drawdown. Do not infer an edge from more signals; assess performance only after at least 10 closed trades.
- Change made: Set `signal_proximity_pct` to `0.0075` in active and example configs and added a regression test for a bearish setup admitted by the wider band. Paper mode remains enabled and live orders remain disabled.
- Results: `tests/test_strategy.py` passed (`23 passed`); both Kite configs parse with `signal_proximity_pct=0.0075`, paper trading enabled, and live orders disabled. `git diff --check` passed. Archived bar history is insufficient for a reliable retrospective signal-count estimate, so market-frequency and performance outcomes remain pending.
- Decision and evidence: Keep as a bounded paper-only experiment pending session results. This increases eligibility, not a guaranteed trade or profitability.
- Rollback/version if reverted: Restore `signal_proximity_pct` to `0.005` in both configs.
- Follow-up or reason to revisit: Review actual candidates, opened/closed trades, all rejection reasons, costs, P&L, and drawdown after each session; revert if the change admits poor-quality entries.

### EXP-2026-10-07-02

- Status: running; trade frequency and performance outcomes are unmeasured.
- Problem and evidence: The October 6 paper review counted 8 ADX-below-12 rejection mentions and zero BUY/SELL signals. These mentions are not independent opportunities, and the archived intraday history is insufficient for a reliable replay.
- Prior related log entries checked: `EXP-2026-10-02-02` concerns a retired paper-shadow ADX override and does not apply to the current unified scorer; `EXP-2026-10-05-06` keeps paper and live on the same strategy. This trial lowers the shared configured floor by one point and does not reintroduce shadow logic.
- Hypothesis: Lowering `min_adx` from 12 to 11 may admit some otherwise-qualified setups with ADX from 11 up to (but not including) 12 while retaining all other trend, proximity, confirmation, option-quality, and risk controls.
- Single variable being changed: `min_adx`, from `12.0` to `11.0`.
- Code/config before: The active paper config had `min_adx=12.0`, paper trading enabled, and live orders disabled; the example config used `18.0`.
- Baseline period and metrics: October 6, 2026; 9,859 decisions, zero BUY/SELL signals, zero opened trades, and 8 ADX-too-weak reason mentions below 12. These counts do not estimate the number of unique candidates this change would admit.
- Test method and fixed evaluation period/sample: Keep other strategy and risk settings fixed. Observe the next 10 comparable paper sessions; record ADX rejection counts, candidates, entries, closed-trade P&L after costs, win/loss sizes, and drawdown. Do not infer an edge from increased frequency; assess performance only after at least 10 closed trades.
- Change made: Set `min_adx=11.0` in active and example configs and add a regression test showing an ADX 11.5 setup is rejected at 12 but can qualify at 11.
- Results: `tests/test_strategy.py` passed (`24 passed`); both Kite configs parse with `min_adx=11.0`, paper trading enabled, and live orders disabled. `git diff --check` passed. Historical candidate/frequency and performance effects remain unmeasured.
- Decision and evidence: Keep as a bounded paper experiment pending session evidence. It may increase candidate eligibility but does not guarantee a trade or profitability.
- Rollback/version if reverted: Restore `min_adx` to `12.0` in the active config; restore the example config's previous documented default if reverting the template.
- Follow-up or reason to revisit: Review daily ADX rejection counts and actual entry/closed-trade outcomes; revert if the additional candidates degrade measured results.

### EXP-2026-10-07-03

- Status: running; trade frequency and performance outcomes are unmeasured.
- Problem and evidence: The October 6 archive contains 4,897 repeated HOLD reason mentions for the sideways-regime gate, versus 50 ADX-below-floor mentions. The archived rows are repeated symbol/bar evaluations, not unique opportunities; operational `underlying_context_only` rows are not rejected trades.
- Prior related log entries checked: `EXP-2026-10-07-01` widened signal proximity and `EXP-2026-10-07-02` lowered the ADX floor. This experiment changes only the sideways 20-bar net-move threshold; the range threshold, trend rules, confirmations, option filters, and risk settings remain fixed.
- Hypothesis: Lowering `sideways_net_move_pct` from 0.30% to 0.25% may allow setups with a modest 20-bar directional move to proceed past the sideways-regime early gate when the recent range is otherwise under 0.30%.
- Single variable being changed: Active `sideways_net_move_pct`, from `0.30` to `0.25`.
- Code/config before: Active paper config had `sideways_range_pct=0.30`, `sideways_net_move_pct=0.30`, `min_adx=11.0`, and `signal_proximity_pct=0.0075`; paper enabled, live orders disabled.
- Baseline period and metrics: October 6, 2026, before the October 7 threshold changes; 9,859 decisions, zero BUY/SELL signals, zero opened trades, and 4,897 sideways reason mentions. This is a reason-mention count, not a unique missed-trade count; truncated bar history prevents reliable replay.
- Test method and fixed evaluation period/sample: Keep every other active variable fixed. Observe the next 10 comparable paper sessions, tracking directional candidates, entries, rejection reasons, closed-trade P&L after costs, win/loss sizes, and drawdown. Do not infer an edge from trade frequency; assess performance only after at least 10 closed trades.
- Change made: Set active `sideways_net_move_pct=0.25` and add a regression test that a 0.27% 20-bar move passes this regime gate while it remains sideways at the former 0.30% floor.
- Results: Focused strategy tests and config validation pending.
- Decision and evidence: Keep as a bounded paper experiment pending market observations. The change relaxes only the regime gate; downstream signal, context, option-quality, and risk gates remain in force.
- Rollback/version if reverted: Restore active `sideways_net_move_pct` to `0.30`.
- Follow-up or reason to revisit: Compare the next 10 sessions' candidate and entry flow, then evaluate measured outcomes; revert if the extra candidates degrade risk-adjusted results.

### EXP-2026-10-08-01

- Status: running; trade frequency and performance outcomes are unmeasured.
- Problem and evidence: The October 7 paper review contains 9,474 decisions, including 8,752 regular-session decisions, 8,881 HOLDs, zero BUY/SELL signals, and zero opened or closed trades. It recorded 141 mentions of missing volatility compression and 114 mentions of insufficient breakout close/volume/ATR confirmation. These are repeated reason mentions, not distinct missed-trade opportunities.
- Prior related log entries checked: `EXP-2026-10-07-01` widened signal proximity, `EXP-2026-10-07-02` lowered the ADX floor, and `EXP-2026-10-07-03` relaxed the sideways net-move gate. Unlike the October 5 unified-strategy decision, this experiment intentionally adds an isolated paper-only exception; live scoring remains strict.
- Hypothesis: Allowing otherwise-qualified directional trend setups through without requiring prior volatility compression and breakout-candle close/volume/ATR confirmation may yield paper candidates while retaining trend, score, ADX, EMA-expansion, VWAP, benchmark, option-quality, entry confirmation, and risk controls.
- Single policy being changed: In paper mode only, bypass the scorer's volatility-compression and breakout-candle quality requirements for scored directional trend setups. All other strategy and execution settings remain unchanged.
- Code/config before: The scorer required both compression and breakout-candle quality for every full-OHLCV BUY/SELL signal. The October 7 active config was paper-enabled and live-orders-disabled.
- Baseline period and metrics: October 7, 2026; 9,474 decisions, 8,752 regular-session decisions, zero BUY/SELL signals, zero opened trades, and zero closed trades. The archive contains repeated reason mentions and is not evidence of distinct missed opportunities or strategy edge.
- Test method and fixed evaluation period/sample: Observe the next 10 comparable paper sessions. Record directional candidates, opened trades, all rejection reasons, quote/option quality, stop-risk usage, and closed-trade results after fees/slippage. Assess expectancy and drawdown only with an adequate closed-trade sample; do not treat higher frequency as improvement.
- Change made: Add `paper_allow_trend_continuation`, defaulting off in the example config and enabled in the active paper config. The runtime passes it to the scorer only when paper trading is enabled. Live order settings remain disabled; this setting does not authorize live trading.
- Results: `tests/test_strategy.py` passed (`26 passed`). Full-suite run excluding the unrelated partial-object fixture test `test_on_tick_stores_timestamp_required_by_option_quality_gate` passed (`162 passed, 1 skipped, 1 deselected`). Both Kite configs parse and `git diff --check` passed. Forward paper frequency and performance are pending.
- Decision and evidence: Keep this as a user-approved paper-only experiment. No trade or profitability is guaranteed; the October 7 baseline has no BUY/SELL rows and cannot quantify the hypothetical entry increase.
- Rollback/version if reverted: Set `paper_allow_trend_continuation` to `false` in `kite_config.json`; the scorer default and example config remain strict.
- Follow-up or reason to revisit: Review the next 10 sessions' signal and rejection flow, entries, costs, P&L, and drawdown. Disable the flag if the additional signals fail the remaining quality/risk checks or measured results deteriorate; do not promote to live without separate validation and approval.

### EXP-2026-10-08-02

- Status: running; entry frequency and performance outcomes are unmeasured.
- Problem and evidence: `score_market` can return directional signals at score 55, but the active final `AccuracyFilters` entry floor was 70. Therefore, paper signals scoring 55-69 could not reach subsequent entry checks. No claim is made that the October 7 archive contains distinct lower-score candidates; its decision rows are repeated evaluations.
- Prior related log entries checked: `EXP-2026-10-08-01` relaxes only paper compression and breakout-candle checks; `EXP-2026-10-07-01` through `EXP-2026-10-07-03` record the prior signal-gate experiments. This is a separate final-entry-floor experiment, not a change to the signal-generation threshold or a live override.
- Hypothesis: Lowering the final paper entry floor from 70 to 55 may allow more scored paper signals to reach directional confirmation, option quality, sizing, and risk gates, creating observations for subsequent evaluation.
- Single policy being changed: Effective entry score floor for paper trading, from 70 to 55. Live and default `min_entry_score` remain 70.
- Code/config before: `min_entry_score=70` in the active config and runtime; paper trading enabled and live orders disabled.
- Baseline period and metrics: October 7, 2026; zero BUY/SELL signals and zero opened trades before `EXP-2026-10-08-01`. The archive cannot measure hypothetical post-relaxation scores 55-69 reliably.
- Test method and fixed evaluation period/sample: Observe the next 10 comparable paper sessions. Count 55-69 and 70+ directional signals separately, record which pass confirmation/option/risk gates and open, and evaluate realized paper P&L after costs, win/loss size, and drawdown only with enough closed trades. Do not treat entries or higher frequency as evidence of better performance.
- Change made: Add `paper_min_entry_score`, validate it in the range 0-85, and apply `min(paper_min_entry_score, min_entry_score)` only in paper mode to both entry validation and position signal-health monitoring. Active config sets it to 55; example config keeps it at 70. Live/default floor remains 70.
- Results: Focused runtime tests passed (`6 passed`); the full suite excluding the unrelated incomplete-fixture test `test_on_tick_stores_timestamp_required_by_option_quality_gate` passed (`162 passed, 1 skipped, 1 deselected`). Pylance reported no errors in changed Python files; both configs parse and `git diff --check` passed. Forward entry frequency and performance are unmeasured.
- Decision and evidence: User-approved paper-only trial. The lower floor does not bypass candle confirmation, option quote/quality checks, sizing, or risk limits and does not guarantee a trade or profit.
- Rollback/version if reverted: Set `paper_min_entry_score` back to 70 or remove the setting; live `min_entry_score` remains 70.
- Follow-up or reason to revisit: Review the next session's score-band counts, rejection reasons, actual opened trades, costs, P&L, and drawdown. Keep live orders disabled and revert if the added lower-score entries do not meet the remaining safeguards or outcomes deteriorate.

### EXP-2026-10-08-03

- Status: running; paper-trade frequency and performance outcomes are unmeasured.
- Problem and evidence: The October 8 paper review recorded 49 BUY/SELL decisions, 25 side-eligible candidates, zero opened entries, and six `position_size_zero` rejections. The active options policy previously capped daily loss at 2% of a ₹100,000 account and used a fixed ₹2,000 per-trade ceiling; the one-lot sizing gate and 10% option stop also need to be interpreted against the user's clarified per-lot premium risk policy.
- Prior related log entries checked: `EXP-2026-10-05-03` documents the earlier 10% premium stop and 2% daily budget; `DLY-2026-10-08-03` documents allowing one risk-qualified lot; `EXP-2026-10-08-01` and `EXP-2026-10-08-02` record separate signal and score-floor experiments. This entry records only the later options risk-policy definition.
- Hypothesis: Sizing to at most 10% of one contract lot's premium notional per entry, while reserving a 10%-of-account daily risk budget for open stop-risk and realized losses, will align paper position sizing with the clarified risk instruction. It does not guarantee entries or positive returns.
- Risk policy being changed: Options-mode daily loss budget from 2% to 10% of account size; per-entry risk ceiling is 10% of one lot's premium notional, additionally limited by remaining daily risk. With a 10% premium stop, this ceiling allows at most one lot when the daily budget is available.
- Code/config before: Paper enabled and live orders disabled; account size ₹100,000; daily loss budget 2% (₹2,000); fixed `max_risk_per_trade=₹2,000`; option stop 10% of premium; one-lot minimum.
- Baseline period and metrics: October 8 daily review: 8,726 decisions, 49 BUY/SELL rows, 25 side-eligible candidates, zero opened trades, six `position_size_zero` rejections, 15 option-filter rejections, four accuracy-filter rejections, and no closed trades. Decision/rejection rows are repeated evaluations, not independent opportunities; no matched risk-policy replay or performance estimate is available.
- Test method and fixed evaluation period/sample: Verify deterministic lot sizing for the active contract lot sizes and premium stop, confirm open risk and realized losses reduce remaining daily budget, and observe subsequent paper sessions. Evaluate strategy performance only after at least 10 closed trades, including costs, drawdown, and loss sizes; do not treat an increased daily cap or entry count as evidence of improvement.
- Change made: Set `daily_max_loss_pct=10`, set the options-mode fixed `max_risk_per_trade` override to null, and add `option_max_risk_per_lot_pct=10`. Apply the lesser of the one-lot premium-based per-entry ceiling and available daily budget to option sizing and enforce the same ceiling on filled/recovered options. Keep the 10% premium stop, paper mode, and live-order-disabled setting unchanged.
- Results: `tests/test_intraday_manager.py` passed (`59 passed`); Pylance reported no errors in the touched Python files; active/example configs and `git diff --check` passed. Forward paper frequency and performance are pending.
- Decision and evidence: Apply as a user-directed paper risk-policy change, not as a strategy-performance experiment. The daily loss ceiling is materially higher than before; slippage, gaps, fees, or execution failures can cause actual losses to exceed planned limits.
- Rollback/version if reverted: Restore `daily_max_loss_pct=2`, the prior `max_risk_per_trade` value, remove `option_max_risk_per_lot_pct`, and revert the associated sizing and enforcement logic.
- Follow-up or reason to revisit: Review daily realized paper P&L and remaining risk after every session; reduce or revert the 10% daily budget if observed drawdown is unacceptable. Keep live orders disabled unless separately reviewed and authorized.

### EXP-2026-10-08-04

- Status: running; frequency and performance outcomes are unmeasured.
- Problem and evidence: The October 8 daily paper report recorded 49 directional BUY/SELL decision rows, 25 side-eligible candidates, zero entries, and 15 `OPTION_FILTER_WEAK_CANDLE_MOMENTUM` rejections. These are repeated decision rows rather than necessarily distinct opportunities. The report predates the latest risk-policy adjustment, so its six `position_size_zero` results do not establish post-change sizing behavior.
- Prior related log entries checked: `EXP-2026-10-08-01` and `EXP-2026-10-08-02` cover separate scorer/entry-score paper trials; `EXP-2026-10-08-03` records the 10%-of-one-lot-premium entry cap and 10%-of-account daily risk budget. This trial changes only the option candle-body threshold; all other settings stay fixed.
- Hypothesis: Reducing the required signal candle body/range from 60% to 40% for paper entries only may let some directionally aligned candles proceed to existing option quote/quality, entry validation, and risk gates, providing a paper sample without changing live behavior.
- Single variable being changed: Paper option signal candle body/range minimum: 60% to 40%. Direction must still match the signal; flat or counter-direction candles remain rejected.
- Code/config before: The option-entry path required a matching-direction candle body/range of at least 60%; active paper enabled, live orders disabled, one-lot option sizing, per-entry limit 10% of lot premium notional, daily loss budget 10% of account.
- Baseline period and metrics: October 8, 2026 daily review: 8,726 decisions, 49 BUY/SELL rows, 25 side-eligible candidates, 15 weak-candle rejections, six sizing rejections before the latest sizing-policy change, four accuracy-filter rejections, zero entries, and zero closed trades. Repeated rows are not unique candidate counts; archived data does not establish how many candle-rejected rows would have passed subsequent gates.
- Test method and fixed evaluation period/sample: Unit-test candles below/above both ratios, prove live/default remains at 60% and paper uses 40%, and retain the direction check. Observe the next 10 comparable sessions for rejection counts, option-quality and risk outcomes, entries, and closed trades; assess expectancy/drawdown only after at least 10 closed trades and after costs. Do not treat a higher entry count as evidence of an edge.
- Change made: Add validated `paper_option_min_candle_body_ratio`; set active config to 0.40 and example config to 0.60. Use the lower threshold only when paper mode is enabled. No scorer, signal-direction, option quality, accuracy, sizing, daily-risk, or live threshold is relaxed.
- Results: The option-candle and paper/live threshold regressions passed within `tests/test_intraday_manager.py` (`60 passed` total); active/example config JSON parsing, touched-file Pylance diagnostics, and `git diff --check` passed. Paper-market frequency and performance observations remain pending.
- Decision and evidence: User-approved paper-only experiment. A weaker candle-body threshold can increase exposure to noisy candles; other existing entry/risk gates remain required. No daily trade or profitability is guaranteed.
- Rollback/version if reverted: Remove `paper_option_min_candle_body_ratio` from active config or set it to 0.60; restore the prior fixed helper behavior if the paper/live threshold regression tests fail.
- Follow-up or reason to revisit: Review next-session decision and trade archives for weak-candle rejection reduction, downstream reject rates, actual entries, realized losses, and drawdown. Keep live orders disabled and do not relax another strategy/filter variable until this change has been observed.

#### EXP-2026-10-09-01 — Full paper-strategy historical replay

- Question: Does the complete current paper options strategy produce trades and positive P/L, and did changing the paper candle-body threshold from 60% to 40% improve the outcome?
- Method: Read-only counterfactual Kite minute OHLCV/OI replay for October 7-8, 2026. Both threshold runs used the current paper scorer, trend-continuation and score-floor settings, contract mapping and option premium/volume/OI gates, accuracy/cooldown and timing filters, one-trade-per-leg/session control, 10%-of-one-lot-premium risk sizing, 10%-of-account daily risk budget, and configured paper exits/timeboxes. No live or paper broker orders were placed.
- Full strategy at the active 40% threshold: 10 closed trades; 2 winners (20%); gross P/L -INR 3,496.25; gross profit factor approximately 0.262. Estimated net P/L was -INR 3,896.25 with INR 40 round-trip brokerage and no slippage, -INR 4,200.75 at 5 bps slippage per side, -INR 4,505.25 at 10 bps, and -INR 5,114.25 at 20 bps. October 7: 7 trades, gross -INR 2,360, 28.57% wins. October 8: 3 trades, gross -INR 1,136.25, no winners.
- Controlled 60% comparison: 9 trades; 2 winners (22.22%); gross P/L -INR 3,237.50; estimated net P/L -INR 3,597.50 with INR 40 brokerage and no slippage. The 40% setting added one October 7 trade that lost INR 258.75 gross, with no change in October 8 trade count.
- Risk observations: At 40%, maximum reserved stop risk was INR 4,143.50 on October 7 and INR 2,087.80 on October 8, below the configured INR 10,000 daily budget. Per-session realized-equity drawdown estimates at zero slippage were 3.20% and 1.26%. These replay estimates do not guarantee live execution will respect those bounds.
- Result/decision: The complete strategy was loss-making in both sessions under both thresholds; the 40% threshold did not improve the sample. Do not treat more entries as an improvement or as evidence of edge. This two-session result is far too small for expectancy conclusions; keep live orders disabled and gather a longer, representative sample before changing other filters.
- Limitations: Counterfactual settings are applied to historical sessions, not the actual decisions/trades from those dates. Minute OHLC cannot establish tick-level event order or fill prices; entry assumes the signal-minute option close. Historical bid/ask spread and IV are missing, so the conditional IV check cannot be replayed; cost cases use illustrative slippage and INR 40 brokerage only and omit applicable taxes/fees. Historical contract selection uses the current instrument master, and TATAMOTORS had no matching contract. Underlying-bar score-health updates may not synchronize exactly with production callbacks.
- Evidence: `paper_trading_data/backtests/kite_option_replay_2026-10-07_08.json` contains all four session/threshold result sets, full trade ledgers, rejection counts, costs, coverage, and caveats; JSON parsing and scenario totals were checked.

#### EXP-2026-10-09-02 — Restore 60% for today's paper monitoring

- Trigger: The whole-strategy replay for October 7-8 was negative at both thresholds; 40% added one losing trade on October 7 and did not add trades on October 8.
- Change: Restore the active paper `paper_option_min_candle_body_ratio` from 0.40 to 0.60 for the October 9 session. No other strategy setting changes; live orders remain disabled.
- Evaluation plan: After today's session, review signal/decision counts, gate rejection counts, selected contracts, entries and exits, P/L after estimated costs, and risk/drawdown. Make any subsequent filter or strategy decision only after examining this session's actual paper data.
- Documentation/config: Updated `kite_config.json` and `DAILY_WEEKLY_OPERATIONS.md`; the 60% default/example and live threshold are unchanged.
- Validation: Active and example Kite JSON parsed; active threshold is 0.60, paper trading is enabled, and live orders are disabled. `git diff --check` passed.

#### EXP-2026-10-09-03 — Previous-week full-strategy proxy replay

- Status: inconclusive; replay evidence only, no strategy/config variable changed.
- Question: How did the complete active paper options strategy perform over the previous completed week, including trade count, P/L after illustrative costs, drawdown, risk usage, and entry rejections?
- Related prior entries checked: `EXP-2026-10-09-01` compares the full paper strategy at 40% and 60% on October 7-8; `EXP-2026-10-09-02` records the active threshold being restored to 60%.
- Strategy/config used: Current 60% candle-body threshold, paper trend-continuation/scoring and score floor, option selection and premium/volume/OI gates, accuracy/confirmation/cooldown/timing filters, one trade per leg/session, 10%-of-one-lot-premium risk sizing, 10%-of-account daily risk budget, and configured paper exits/timeboxes. Live orders remained disabled.
- Test method and period: Read-only counterfactual replay of Kite minute OHLCV/OI for September 28-October 1, 2026. The user approved substituting contracts from the current NFO master because the exact expired historical expiry series were unavailable. Four sessions and 46 unique later-expiry option symbols were replayed; October 2 had no bars in the available dataset. Option fills approximate the signal-minute close.
- Results: 14 closed trades; 8 winners (57.14%), 6 losers; gross P/L +INR 760; gross profit factor 1.2734. Daily gross P/L/trades: Sep 28 INR 0/3, Sep 29 +INR 303.75/2, Sep 30 +INR 95/3, Oct 1 +INR 361.25/6. Average winner +INR 442.50; average loser -INR 463.33; largest winner +INR 1,541.25; largest loser -INR 1,687.50. Maximum gross realized trade-close drawdown was INR 1,862.50 (1.8625% of the configured INR 100,000 starting account), with a maximum losing streak of 2; this drawdown excludes intratrade movement and costs.
- Cost sensitivity: Estimated net P/L was +INR 200 after INR 40 round-trip brokerage per trade with zero slippage, -INR 76.61 at 5 bps per side, -INR 353.21 at 10 bps, and -INR 906.42 at 20 bps. The gross edge in this short proxy is erased under the 5 bps scenario.
- Risk and filters: Maximum reserved stop risk was INR 3,975.25 against the INR 10,000 daily budget. Reported gate counters include 52 weak-candle, 60 late-window, and 35 unavailable-contract rejections. TATAMOTORS was excluded because no matching options were available in the current instrument master.
- Decision/evidence: Four sessions are not enough to establish robust expectancy, and the later-expiry instruments are not the exact contracts the strategy would have selected at the time. The positive zero-slippage net estimate is cost-sensitive; the 5 bps and higher estimates are negative. Treat this as an inconclusive proxy result, not proof of profitability or a reason to relax filters. Keep live orders disabled and do not make another strategy change from this evidence alone.
- Limitations: Minute OHLC cannot reproduce tick-level ordering or executable bid/ask fills; historical spreads and IV are missing, IV checks are skipped without IV, and brokerage/slippage cases exclude taxes and other fees. The October 1 archived `trend_shadow_paper` result belongs to a different strategy and was not combined.
- Evidence and validation: `paper_trading_data/backtests/kite_option_proxy_replay_2026-09-28_10-01.json` contains daily metrics, trade ledger, selected proxy contracts, coverage, rejection counters, cost cases, and caveats. JSON parsing and independent trade-row P/L, lot-size, gross-total, win-rate, profit-factor, drawdown, loss-streak, cost, and risk-budget reconciliations passed.

#### Auditability clarification — 2026-10-09

- User review found that the replay ledger displayed bearish underlying `signal: SELL` beside PE contracts but omitted the option transaction action. This presentation was ambiguous and could be read as shorting the PE.
- Production routing was checked: `SELL` underlying signal selects the PE leg; `_option_trade_action` returns `BUY` for a valid options leg and routes it to the BUY handler. Existing tests verify `NIFTY_PE` with `SELL` signal returns action `BUY`.
- The saved replay computes each trade as `(option exit premium - option entry premium) * quantity`, consistent with a long option, and its existing P/L values reconcile. The report now records `underlying_signal`, `option_type`, `entry_action: BUY`, `position_type: LONG_OPTION`, and `exit_action: SELL` for every row. No strategy behavior or metrics changed.
- Validation: All 14 ledger rows checked for correct signal-to-leg mapping and explicit BUY-to-open / SELL-to-close actions; JSON parsing and `git diff --check` passed.

#### EXP-2026-10-12-01 — Friday option-exit counterfactual

- Question and sample: Would the revised adverse-premium gate alter the two `SIGNAL_WEAKEN` exits recorded on October 9, 2026? Read all five closed trades and the day's archived one-minute option candles and signal decisions.
- Rule result: ICICIBANK_CE's 5% adverse threshold was INR 27.455 versus a minimum archived premium of INR 28.05; RELIANCE_CE's threshold was INR 21.66 versus a minimum of INR 21.95. Neither would satisfy the new gate, so both would remain open until the configured 10-minute `TIME_BOX`. TCS_CE remains a `TRAILING_STOP`; INFY_CE and HDFCBANK_CE remain time-box exits.
- Counterfactual: Deadline-candle closes estimate the deferred exits at +INR 385 and +INR 125. With other recorded fills held unchanged, the estimated daily total changes from -INR 142.50 to +INR 272.50. OHLC bounds for only the deferred exits give an estimated daily range of -INR 122.50 to +INR 412.50.
- Implementation correction: The adverse threshold now follows the held position direction rather than treating PE's underlying bearish signal as a rising-premium risk. A long PE, like a long CE, loses value when its premium falls. The Friday data contains no PE positions; test coverage, not this historical sample, validates PE behavior.
- Limitations: No tick-level quotes are persisted. Minute bars cannot determine the precise timer-trigger quote, intraminute path, or executable fill, so the counterfactual is an OHLC-based estimate, not an exact replay. Five trades in one session are insufficient to establish expectancy or a durable edge; continue paper-only monitoring and do not infer profitability from this result.
- Validation: `tests/test_intraday_manager.py` passed (60 tests). The full suite produced 163 passes, 1 skip, and one unrelated `_on_tick` fixture failure (`paper_trading_enabled` missing).

#### EXP-2026-10-13-01 - paper entry/health score floor 55 to 60 evaluation

- Related experiment: Follow-up to `EXP-2026-10-08-02`; the user requested a paper score floor of 60. The 10% daily loss cap was left unchanged.
- Configuration: `paper_min_entry_score=60`, standard `min_entry_score=70`, `daily_max_loss_pct=10.0`; live orders remain disabled.
- Historical entry result: All 80 recorded directional decision rows on October 13 scored either 65 (62 rows) or 85 (18 rows); the three opened trades scored 65. The 33 trades in the saved September 28-October 1 and October 7-8 replay ledgers scored 65 or 85. Thus, in these recorded trade ledgers, raising the entry floor from 55 to 60 would not remove an opened trade. Decision rows are repeated evaluations, not independent opportunities.
- Historical exit counterfactual: Replayed the production `_check_option_signal_health` method over the October 13 archived decision snapshots at floors 55 and 60. SBIN_CE and TCS_CE first meet the signal-health exit condition at the same recorded event under either floor. RELIANCE_CE would meet it earlier at floor 60: the 09:37:46 IST snapshot has score 55 and a bar close of INR 25.95, compared with the recorded exit at INR 26.35 and actual P&L of -INR 725 under floor 55. The earlier bar-close mark estimates -INR 925, about INR 200 worse than the recorded fill. On the same snapshot-only method, floor 55 would first trigger at the post-close decision snapshot at INR 26.15, so the like-for-like bar-close estimate is INR 100 worse at floor 60.
- Decision and limitations: This is evidence that the setting affects exits as well as entries; it did not improve the one changed exit in this session. Keep the user-requested value for now, but treat the result as a one-session warning, not a strategy conclusion. The archive stores decision snapshots, not tick-by-tick executable quotes; counterfactual marks cannot establish actual fills. The older full-option replay ledgers do not retain raw inputs for rerunning exits at floor 60. Continue paper-only monitoring and evaluate with a larger comparable sample.
- Validation: Ran both score floors through the production signal-health method against the October 13 archived decision sequence and checked entry scores in the saved historical replay ledgers. No orders were placed and no strategy code was changed.

#### EXP-2026-10-14-01 — Score and symbol-filter sensitivity on available option ledgers

- Status: inconclusive; no strategy/config change.
- Question: Does raising the paper score floor or excluding loss-heavy underlyings turn the available historical option results profitable?
- Prior related entries checked: `EXP-2026-10-09-01` (exact-token October 7-8 replay), `EXP-2026-10-09-03` (September 28-October 1 later-expiry proxy), and `EXP-2026-10-13-01` (score-floor effects on entries and exits).
- Method and evidence: Recomputed post-hoc trade-ledger subsets from the saved 60% candle-body scenarios. Exact selected contracts were used for October 7-8 (9 trades). September 28-October 1 used later-expiry proxy contracts (14 trades); the report explicitly warns these are not the historical contracts the strategy would have selected. Cost sensitivity subtracts INR 40 round-trip brokerage/trade and illustrative 5 or 10 bps slippage per side, calculated on entry plus exit notional. This is a ledger sensitivity, not a fresh full strategy replay: removing trades can change cooldown, position/risk reservations, and signal-health exits.
- Baseline: Exact October 7-8: 9 trades, 2 winners, gross -INR 3,237.50; estimated net -INR 3,597.50 with brokerage only and -INR 3,874.13 at 10 bps per side. Proxy September 28-October 1: 14 trades, 8 winners, gross +INR 760; estimated net +INR 200 with brokerage only and -INR 353.21 at 10 bps per side.
- Score-floor sensitivity: Keeping only score-85 trades (proxy score floor 80) retains 3 winners on September 30 and October 1, gross +INR 2,783.75 and estimated net +INR 2,540.26 at 10 bps per side. The same post-hoc floor on exact October 7-8 keeps 4 trades (1 winner), gross -INR 290 and estimated net -INR 562.73 at 10 bps per side. The proxy profit is only three trades, confined to two sessions, and fails to repeat on the later exact-contract sample.
- Symbol sensitivity: Excluding SBIN alone from October 7-8 still loses (7 trades; gross -INR 593.75; estimated net -INR 1,091.23 at 10 bps per side). Excluding both SBIN and RELIANCE, selected after observing their losses, yields 4 trades, gross +INR 306.25 and estimated net +INR 17.72 at 10 bps per side. Adding a NIFTY exclusion leaves 3 trades, gross +INR 972.50 and estimated net +INR 765.06 at 10 bps per side. These are plainly hindsight-selected symbol exclusions, not independent evidence of a persistent symbol effect.
- Decision: Do not raise the configured score floor to 80 or exclude symbols. No tested candidate shows repeatable net profit across the two datasets; the one positive score-filter result is a three-trade later-expiry proxy that is contradicted by the exact-contract dates. Preserve the active floor 60 and all current filters, with live orders disabled.
- Limitations/follow-up: The score subsets do not recompute entry eligibility, concurrent positions, risk reservation, or score-dependent exits. The exact sample is two sessions and the proxy has four sessions; neither satisfies the existing ten-closed-trade minimum as an independent holdout. Re-run only when more exact-contract intraday history or forward paper trades are available, using a predeclared threshold and holdout period.
- Validation: Parsed both archived JSON ledgers and independently recomputed trade counts, gross P&L, profit factor, brokerage, and slippage subsets. No code/config change or order was made.
- Follow-up sensitivity: Also screened entry times at 09:30 and 10:00, plus score >=80 combined with each time cutoff. The 09:30 cutoff excluded no trades. The 10:00 cutoff left 12 proxy trades (gross +INR 980; estimated +INR 46.50 at the stated costs) but the exact-contract sample still had 8 trades, gross -INR 3,037.50 and estimated -INR 3,602.68. On a chronological split, score >=80 had zero trades in the Sep 28-29 proxy tuning slice and three winning trades in the Sep 30-Oct 1 slice; this is not a valid selected-on-training candidate and it is contradicted by the exact-contract sample (four trades, one winner, net -INR 562.73). No tested filter survives the cross-sample check.

#### EXP-2026-10-14-02 — Two-check paper signal-weakening confirmation

- Status: running; outcome remains inconclusive pending a larger forward paper sample.
- Problem and evidence: On October 14, all four recorded `SIGNAL_WEAKEN` trades were losses totaling -INR 3,853.25 before costs. Their exits occurred after signal deterioration and an adverse premium move beyond the existing 5% threshold. The same-day exported exact-token option minute candles and decision snapshots are available for counterfactual replay.
- Prior related entries checked: `EXP-2026-10-12-01` evaluates the existing adverse-premium gate on October 9; `EXP-2026-10-14-01` cautions that small historical option samples have not supported stable filters.
- Hypothesis: Requiring the existing weak-signal and 5%-adverse conditions to be true on two consecutive signal decision checks in paper trading may avoid an exit on a transient breach.
- Single variable being changed: Paper `SIGNAL_WEAKEN` confirmation count, from one qualifying check to two. The threshold, entry scoring, score floor, decision-window lengths, stop/target rules, and all live behavior remain unchanged.
- Code/config before: Working-tree baseline before this patch; active config has 5% adverse premium threshold, paper trading enabled, and live orders disabled. Recorded baseline: 4/4 losses, -INR 3,853.25 gross.
- Test method and fixed sample: Re-run the production signal-health logic over October 14 archived decision events and the exact selected option contract minute candles. Use only completed candle prices available before each decision event; report minute-bar close-based estimates separately from unavailable executable tick fills and transaction costs.
- Change made: Require two consecutive qualifying checks in paper mode only; no config file changed. `DAILY_WEEKLY_OPERATIONS.md` now distinguishes the paper exit experiment from unchanged live exits.
- Results: The patched production method's first two-check counterfactual exits were INFY_CE INR 44.25 / -INR 1,060 (10:24:45 IST), TCS_PE INR 27.85 / -INR 450 (11:52:54), ICICIBANK_PE INR 29.70 / -INR 1,925 (13:48:12), and BANKNIFTY_PE INR 640.00 / -INR 1,639.50 (13:44:28). Combined gross P&L is -INR 5,074.50 versus the recorded -INR 3,853.25, a -INR 1,221.25 change; all four remain losers. Recorded stop-loss and take-profit levels were not touched by the completed candles before those estimated exits.
- Decision: The hypothesis did not improve this fixed four-trade sample; the estimate is materially worse. Do not claim the policy minimizes losses. Keep it paper-only for a prospective, explicitly monitored experiment (or revert before further paper use); live exit behavior is unchanged. This four-trade result is too small to infer a durable effect.
- Limitations: Replay uses archived decision scores and the close of the last completed one-minute option candle available at each decision event. It cannot reproduce tick-level event ordering, actual fills, bid/ask spreads, slippage, or fees, and it does not establish a net-profit outcome.
- Validation: `tests/test_intraday_manager.py` and `tests/test_paper_reporting.py` passed (72 tests, including the final reset assertion); Pylance reported no diagnostics in changed Python files; `git diff --check` passed. The production method replay used the recorded score decisions and each exact contract's last completed minute close before the event.
- Rollback: Restore one-check behavior in `_check_option_signal_health`; all other strategy settings remain untouched.
- Follow-up: Report each trade's counterfactual exit time/price and gross P&L, retain original trade results, and continue collecting a larger chronological paper sample with live orders disabled.

#### EXP-2026-10-14-03 — Paper option 15-bar range breakout with 2R exit

- Status: forward paper pilot enabled; not validated for profitability.
- Problem and evidence: The October 14 ICICIBANK 1360 PE entry opened at ₹32.45 around 13:13 after a prior premium consolidation and early breakout had passed. The user requested earlier entry and chose a rolling 15-completed-candle premium breakout, a range-low stop, and dynamic 2R target.
- Prior related entries checked: `EXP-2026-10-14-01` cautions against promoting filters from small option samples; `EXP-2026-10-14-02` records the separate, negative four-trade `SIGNAL_WEAKEN` exit-delay replay.
- Single experimental variant: Paper-only long CE/PE premium entry on a completed close above the previous 15 completed one-minute candle highs, independent of the underlying score and exempt only from the normal 12:00–13:00 entry block. Existing fresh-quote, option-quality, and shared risk checks still apply. Stop one tick below the previous range low and target 2R; retain one trade per option symbol per session and the shared daily risk cap across CE/PE contracts. For this variant, staged targets, global trailing, the milestone timebox, and signal-weakening exits are disabled so its stop/target policy remains deterministic. Legacy and live behavior remain unchanged.
- Code/config: Add a separately attributed `paper_option_range_breakout` variant. Enable it in active `kite_config.json` with a 15-bar window and 2.0R target; keep it disabled in the example config and keep live orders disabled.
- Fixed-sample method: Apply the completed-candle trigger to the exact October 14 `ICICIBANK26OCT1360PE` minute export. Use minute candle volume as a quote-quality proxy and configured one-lot risk to screen candidates; use next observed candle OHLC to identify stop/target touches. Do not treat this as executable tick-fill replay.
- Results: 09:39 and 09:41 crossovers fail the configured one-lot risk budget. At 10:01 the close is ₹26.20 versus prior-15 high ₹26.00; the prior-15 low is ₹24.15, yielding a ₹24.10 stop and ₹30.40 target. The 13:03 candle reaches ₹30.50. At the 700-unit lot size, the modeled target-touch gross result is +₹2,940 before costs. If the first 10:01 candidate had failed the fresh runtime quote gate, historical candles cannot determine whether a later candidate would have passed.
- Decision: This demonstrates a plausible earlier entry on one exact contract only. It does not establish repeatable or net profitability. Keep paper-only, gather a longer chronological sample, and do not enable live orders.
- Limitations: Historical candle volume is not an archived live quote; exact quote age, bid/ask, event ordering, actual fill, slippage, fees, and interaction with other concurrent underlyings cannot be reconstructed. The 2R counterfactual uses the configured stop and 700-unit lot and assumes a target fill at its level.
- Validation: Focused `tests/test_intraday_manager.py` and `tests/test_paper_reporting.py` passed (77 tests); Pylance diagnostics/syntax, active/example JSON parsing, and `git diff --check` passed. The unfiltered suite reported 193 passed, 1 skipped, and 1 unrelated fixture failure in `test_on_tick_stores_timestamp_required_by_option_quality_gate` (`test_kite_provider.py`), whose manually constructed bot omits `paper_trading_enabled`. The suite excluding that test passed (193 passed, 1 skipped, 1 deselected).
- Rollback: Set `paper_option_range_breakout_enabled` to `false` in `kite_config.json`; the code path remains isolated from legacy and live entries.
- Follow-up: Review separately tagged breakout decisions and closed trades over a predeclared forward sample; compare gross and cost-adjusted outcomes without combining them with the prior exit-delay experiment.

#### EXP-2026-10-14-04 — Breakout-candle volume confirmation

- Status: implemented in the paper-only option range-breakout path; live orders remain disabled.
- Motivation: The three-session candle replay showed several failed premium breakouts, including two October 7 losses with zero reported volume on the breakout minute. Cumulative day volume in the runtime quality gate does not guarantee participation on the breakout candle.
- Single variable: Require each otherwise-qualified range breakout candle to have positive volume at least equal to the average volume of the same preceding lookback candles. With the active 15-bar lookback, this is the previous-15-bar mean. Breakout trigger, contract selection, stop, target, sizing, and all legacy strategy rules are unchanged.
- Historical comparison: An end-to-end offline replay on the available October 7, October 8, and October 14 candles, recalculating later entries and shared risk, modeled gross P/L of +₹7,873.00 with the filter versus +₹1,436.75 baseline. October 7 itself remained negative at -₹8,499.00 versus -₹9,225.25. This is in-sample and excludes spread, fees, slippage, and executable-fill effects; it is not proof of an edge.
- Runtime behavior: A breakout with zero or below-average candle volume records `PAPER_RANGE_BREAKOUT_REJECTED:breakout_volume_below_<lookback>_bar_average`; malformed or negative bar volumes fail closed with `invalid_volume_data`.
- Validation: Added positive/equality and below-average/zero-volume tests; run focused strategy tests and `git diff --check`.
- Rollback: Remove the breakout-volume condition in `_try_paper_option_range_breakout`; do not change the separate breakout enable switch or live-order controls.
- Follow-up: Treat as a forward paper experiment, record accepted/rejected breakouts, and evaluate a predeclared unseen sample with estimated transaction costs before adoption beyond paper trading.

#### EXP-2026-10-15-01 — Paper option R-based trailing exit

- Status: implemented for paper option entries; outcome not yet measured.
- Problem and evidence: The earlier `EXP-2026-10-14-03` breakout pilot used a fixed 2R exit plan. A separate exit policy is now being tested to allow favorable premium moves to continue while retaining the original stop as a hard floor. Prior breakout entry/volume replay results do not measure this exit policy.
- Prior related entries checked: `EXP-2026-10-14-03` (paper option range-breakout entry and exit pilot) and `EXP-2026-10-14-04` (breakout-candle volume filter).
- Hypothesis: For paper CE/PE trades, activating a trailing stop after a favorable 1R move and maintaining a 2R gap from the best premium reached may capture further favorable movement while retaining the initial stop as the maximum-risk floor.
- Single variable being changed: Paper option exit policy. Entry signals, sizing, and initial stop rules remain as before; runner positions do not use staged targets, the reference take-profit/timebox, or signal-reversal exits. The market-close exit remains in force.
- Code/config before: Paper options used their existing staged-target or configured fixed-target exit behavior. Existing runner parameters are now set to `paper_option_trail_activation_r: 1.0` and `paper_option_trail_gap_r: 2.0`; runner behavior is gated to paper trading with live orders disabled.
- Baseline period and metrics: No comparable closed-trade baseline for this specific runner policy was computed when recorded. Do not use the earlier breakout entry/volume replay P&L as its baseline or outcome.
- Test method and fixed evaluation period/sample: No historical exit replay has yet been run. Evaluate separately tagged forward paper runner trades against the prior exit policy on comparable trades, including costs where available; collect at least 10 closed paper trades as the minimum screening sample, not as proof of an edge.
- Change made: Paper option positions track favorable high/low-water marks; the trailing state activates at the configured R threshold and ratchets at the configured R gap without crossing the initial stop. State is persisted for reporting/recovery. Live-order behavior is unchanged.
- Results: None available yet. No profitability, loss-reduction, or expectancy claim is made.
- Decision and evidence: Keep as a paper-only experiment while collecting prospective evidence. The policy changes exit behavior beyond the previous breakout-only context, so keep runner trades separately identifiable and do not combine their results with the prior breakout-volume experiment.
- Rollback: Restore the previous paper option exit selection in `_handle_buy_signal` and `_handle_sell_signal`; leave entry filters, sizing, and live-order controls unchanged.
- Follow-up: Review separately tagged closed runner trades and compare exit prices/P&L against the prior exit policy under the same sample and cost assumptions. Reconsider only after recording the sample size, gross and cost-adjusted metrics, and any adverse cases.

#### EXP-2026-10-16-01 — Breakout direction and delayed-close confirmation replay

- Status: inconclusive; offline replay only, no strategy or configuration change made.
- Problem and evidence: Logged breakout candidates included both recorded entries and candidates blocked or not selected by the existing path. The replay request was to test whether underlying/benchmark direction agreement and, separately, a delayed one-minute close confirmation would have changed outcomes.
- Prior related entries checked: `EXP-2026-10-14-03` (paper option range breakout); `EXP-2026-10-14-04` (breakout-candle volume confirmation); `EXP-2026-10-15-01` (paper option trailing exit).
- Hypothesis: Requiring CE/PE direction to agree with the underlying and NIFTY, and separately requiring a subsequent one-minute close to hold the breakout, may avoid some failed premium breakouts. This replay evaluates those filters separately and in combination; it does not establish causality or profitability.
- Single variable being changed: No runtime variable changed. Offline scenarios were direction confirmation alone and direction plus delayed one-minute close confirmation.
- Baseline period and metrics: Oct 15–16 cutoff-matched recorded P&L was ₹4,183.75 (Oct 15 ₹6,348.25; Oct 16 -₹2,164.50). Existing-path candle replay was ₹4,018.50 (Oct 15 ₹6,176.00; Oct 16 -₹2,157.50). Oct 14 had no logged breakout-candidate records.
- Test method and fixed evaluation period/sample: Replayed all 703 logged candidate events, including recorded opens and eligible hypothetical entries. Direction checks use completed underlying and NIFTY bars before the candidate minute. The combined rule waits for the next one-minute option close at/above the preceding 15-bar range high. Applied a 14:45 cutoff and existing observable gates; selected at most one entry per ticker/day per scenario. Stop-first handling was used for ambiguous OHLC bars and positions were closed by 15:15.
- Results: Direction confirmation selected 14 entries (10 recorded, 4 hypothetical) for ₹5,534.75 gross: Oct 15 ₹8,043.00 and Oct 16 -₹2,508.25. Direction plus delayed close selected 14 (9 recorded, 5 hypothetical) for ₹8,134.00 gross: Oct 15 ₹10,486.25 and Oct 16 -₹2,352.25. Hypothetical entries contributed -₹404.75 and -₹992.25, respectively. The combined variant exceeded the cutoff-matched recorded total by ₹3,950.25 in this replay, but this is not a cost-adjusted or complete portfolio result.
- Decision and evidence: Keep the finding inconclusive. The sample is only two sessions; hypothetical fills are candle estimates, and the replay excludes fees, spread, slippage, portfolio concurrency, and counterfactual circuit-breaker recalculation. The positive aggregate is not evidence of a validated edge. Do not enable either filter based on this replay alone.
- Rollback/version if reverted: Not applicable; no code/config change was made.
- Follow-up: Continue in paper/shadow evaluation with candidate and rejection logging, realistic fill costs, full portfolio/risk-state simulation, and a predeclared out-of-sample period before considering adoption.

#### EXP-2026-10-19-01 — Paper breakout follow-through and exit isolation

- Status: implemented as a reversible paper-only trial; performance remains unvalidated.
- Problem and evidence: The October 19 paper review showed 7 range-breakout trades netting -₹455 before costs (4 initial-stop losses totaling -₹2,851.25; 3 trailing-stop winners totaling +₹2,396.25). Their records showed `paper_option_adaptive` exits, although the breakout experiment specifies a fixed range stop and 2R target. In `_handle_buy_signal`, the general paper adaptive-exit setting had taken precedence over the breakout exit plan.
- Prior evidence reviewed: `EXP-2026-10-14-03` / `EXP-2026-10-14-04` (range-breakout and volume pilot); `EXP-2026-10-15-01` (adaptive option exits); `EXP-2026-10-16-01` (historical breakout filter replay).
- Historical replay: Across October 15-16 uploaded exact-contract minute candles, direction-only selected 14 trades for ₹5,534.75 gross; direction plus delayed one-minute close selected 14 (9 recorded and 5 hypothetical) for ₹8,134.00 gross. October 15 was +₹10,486.25; October 16 remained negative at -₹2,352.25. The combined scenario's hypothetical trades contributed -₹992.25. A rough ₹40 round-trip brokerage estimate leaves ₹7,574 before spread, slippage, taxes, and other fees. This two-session replay is small, includes hypothetical entries, and does not isolate interactions outside the paired direction-confirmed scenarios.
- Change: Add `paper_option_range_confirmation_bars` (only 0 or 1 supported); set it to 1 in the active paper config. At 1, a breakout is eligible only after the next completed one-minute candle closes above the original range high and the live entry quote remains above that level. The volume test remains on the breakout candle. The separate range-breakout plan now bypasses the generic adaptive exit and uses its existing range stop / 2R target; other paper option entries retain their adaptive exit behavior. Live entry handling is unchanged.
- Files: `market_bot/kite_main.py`, `kite_config.json`, `kite_config.example.json`, `tests/test_intraday_manager.py`, and `DAILY_WEEKLY_OPERATIONS.md`; this entry and `DLY-2026-10-19-01` document the trial.
- Validation: Focused strategy tests passed (95); full project suite passed (221 passed, 1 skipped); Python compilation and active/example config parsing passed; `git diff --check` passed.
- Decision and limitations: This is a paper-only trial selected as a plausible false-breakout filter, not evidence that expectancy is now positive. A spot-check against October 19 exact-contract minute candles could not reproduce every tick-time entry/quote, so it does not establish a same-day counterfactual P&L. The October 16 scenario stayed negative, the replay uses minute OHLC proxy fills, and the October 19 seven-trade sample is small. No daily-positive result is guaranteed; do not enable live orders. Monitor accepted/rejected breakout counts, exit-policy labels, cost-adjusted P&L, and drawdown separately. Roll back only the new entry confirmation by setting `paper_option_range_confirmation_bars` to `0`; keep the breakout's fixed 2R policy consistent with its original specification.
