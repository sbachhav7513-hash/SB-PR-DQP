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
