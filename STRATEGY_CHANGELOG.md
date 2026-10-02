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
