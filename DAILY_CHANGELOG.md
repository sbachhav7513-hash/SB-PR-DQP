# Daily Workspace Change Log

Record every intentional workspace addition, modification, or removal here, including code, tests, configuration, and documentation. This is the day-to-day history for spotting repeated work; it complements `STRATEGY_CHANGELOG.md`, which tracks strategy experiment hypotheses and measured outcomes.

## Rules

- Before editing, check recent entries for the same issue or attempted change. Start an entry for the current session before or alongside the first edit.
- Record every intentional file addition, modification, or removal. Group related files in one entry, but identify each file and whether it was added, modified, or removed.
- Explain the reason and link related earlier entry IDs. If repeating a reverted or unsuccessful change, state what new evidence makes this attempt different.
- After validation, update the entry with the command/check and result. Record failures and reversions too; never erase history. Append a dated correction if an entry needs clarification.
- For strategy or accuracy changes, also follow `STRATEGY_CHANGELOG.md` and record the experiment outcome there.
- Do not record secrets. Do not claim a change improved bot performance without measured results.

## Entry Template

```text
ID: YYYY-MM-DD-NN
Session / date:
Reason or problem:
Related prior entries checked:
Files: path (added | modified | removed) - what changed
Validation and result:
Outcome / follow-up / rollback:
```

## Entries

### 2026-09-30

#### DLY-2026-09-30-01

- Reason: Preserve change history and prevent repeating strategy/accuracy edits without checking prior outcomes.
- Related prior entries checked: No daily entries existed; this is the initial record.
- Files:
  - `DAILY_CHANGELOG.md` (added): Created this append-only daily workspace ledger.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Added daily logging requirements and links to both logs; replaced the multi-change weekly example with a one-variable evidence-based workflow.
  - `STRATEGY_CHANGELOG.md` (added/modified): Added the strategy experiment record and linked it to the daily ledger.
- Validation and result: `git diff --check` passed; both linked log files exist and their references were verified.
- Outcome / follow-up / rollback: Use this ledger for every future workspace edit; strategy and accuracy experiments also require a detailed entry in `STRATEGY_CHANGELOG.md`.

#### DLY-2026-09-30-02

- Reason: Zero entries persisted; test a separately attributed trend-shadow paper variant while retaining every existing filter and live-order safeguard.
- Related prior entries checked: `DLY-2026-09-30-01`; no repeated strategy experiment exists. See `EXP-2026-09-30-01` in `STRATEGY_CHANGELOG.md`.
- Files:
  - `market_bot/engine.py` (modified): Add optional strategy-variant attribution.
  - `market_bot/kite_main.py` (modified): Promote only filter-passing shadow candidates when opted-in paper trading is active; attach variant to entries and decisions.
  - `market_bot/trade_journal.py` (modified): Persist strategy variant in Parquet decision and trade archives.
  - `market_bot/weekly_report.py` (modified): Report closed-trade performance by strategy variant.
  - `analyze_weekly.py` (modified): Add separately grouped variant metrics to the standalone weekly report.
  - `kite_config.json` (modified): Enable the experiment for this paper-only config; live orders remain disabled.
  - `kite_config.example.json` (modified): Document the experiment switch as disabled by default.
  - `tests/test_intraday_manager.py` (modified): Cover opt-in and paper-only promotion.
  - `tests/test_paper_reporting.py` (modified): Verify decision variant persistence.
  - `tests/test_weekly_report.py` (modified): Verify variant-separated weekly P&L.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document paper-only behavior and attribution.
  - `DAILY_CHANGELOG.md` (modified): Record this change.
  - `STRATEGY_CHANGELOG.md` (modified): Record baseline, hypothesis, single-variable experiment, and pending outcome.
- Validation and result: Full suite: `119 passed`; Pylance diagnostics clean for all changed Python files; both Kite config JSON files parse; `git diff --check` passed.
- Outcome / follow-up / rollback: Performance remains unmeasured. Do not infer tomorrow's trade count; keep live entries unaffected and evaluate after at least 10 closed paper trades.

#### DLY-2026-09-30-03

- Reason: The prior paper-only trend-shadow promotion continued to reject candidates below the primary 75-point floor in both validation passes, contributing to the zero-trade baseline.
- Related prior entries checked: `DLY-2026-09-30-02` and `EXP-2026-09-30-01`; this is a separate single-variable score-floor experiment.
- Files:
  - `market_bot/accuracy_filters.py` (modified): Support an optional per-validation score floor without changing the default.
  - `market_bot/kite_main.py` (modified): Apply the paper-shadow floor only to opted-in paper candidates and their promoted entry validation; live and primary signals keep the default floor.
  - `kite_config.json` (modified): Set the paper-shadow score floor to 55; paper enabled, live disabled.
  - `kite_config.example.json` (modified): Document the setting while keeping the experiment disabled by default.
  - `tests/test_intraday_manager.py` (modified): Verify the 60-point example fails the primary 75 floor and passes the shadow 55 floor.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the paper-only score exception and non-guarantee of daily trades.
  - `DAILY_CHANGELOG.md` (modified): Record this change.
  - `STRATEGY_CHANGELOG.md` (modified): Record the experiment baseline, hypothesis, and pending outcome.
- Validation and result: Focused paper/live and threshold tests passed; `python -m pytest -q` passed (`120 passed`); both Kite config files parsed; Pylance diagnostics found no errors in changed Python files; `git diff --check` passed.
- Outcome / follow-up / rollback: Pending paper-market observations; revert by setting the shadow floor back to 75 or disabling the paper-shadow switch. Performance remains unmeasured.

#### DLY-2026-09-30-04
- Files:
  - `market_bot/weekly_report.py` (modified): Add an exact-date Markdown report for closed-trade outcomes, signal/rejection counts, HOLD reasons, and shadow flow.
  - `market_bot/kite_main.py` (modified): Generate the daily review alongside the existing close summary.
  - `tests/test_paper_reporting.py` (modified): Verify the report counts trade results and rejection/shadow reasons.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the new daily report artifact and contents.
  - `DAILY_CHANGELOG.md` (modified): Record this change.
- Validation and result: Focused Parquet-backed daily-review test passed; `python -m pytest -q` passed (`121 passed`); Pylance reported no diagnostics in `weekly_report.py` or `test_paper_reporting.py`; `kite_main.py` has two unrelated existing warnings; `git diff --check` passed.
- Outcome / follow-up / rollback: Reporting-only; no strategy performance claim. Inspect the daily report after each session and change at most one paper-only strategy/filter variable per experiment.

### 2026-10-02

#### DLY-2026-10-02-01

- Reason: The shared option-quality gate could accept stale price-only fallbacks, did not validate malformed numeric quote fields, and applied stricter low-premium/volume/OI floors to strong signals than ordinary signals.
- Related prior entries checked: `DLY-2026-10-01-01` and `DLY-2026-10-01-02`; no prior quote-freshness or strong-signal option-quality-gate correction was recorded.
- Files:
  - `market_bot/kite_main.py` (modified): Require a timestamped fresh quote, validate premium/liquidity/optional metadata, retain tick timestamps, and soften fallback floors for strong signals.
  - `tests/test_kite_provider.py` (modified): Cover quote freshness, invalid data, strong-score floors, live tick timestamp propagation, and CE/PE parity.
  - `tests/test_intraday_manager.py` (modified): Add a fresh timestamp to the direct quality-gate fixture.
  - `kite_config.json` (modified): Set the maximum option quote age to 60 seconds.
  - `kite_config.example.json` (modified): Document the 60-second quote freshness setting.
  - `DAILY_CHANGELOG.md` (modified): Record this change and validation outcome.
  - `STRATEGY_CHANGELOG.md` (modified): Record the isolated strong-signal threshold experiment and its unmeasured outcome.
- Validation and result: Baseline provider tests passed (`28 passed`); focused post-change provider and entry-management tests passed (`70 passed`), followed by the live tick timestamp regression (`1 passed`); full suite passed (`132 passed`). Both Kite configs parsed, diagnostics found no errors in changed Python files, and `git diff --check` passed.
- Outcome / follow-up / rollback: Freshness and malformed-data checks are correctness safeguards. Strong-signal fallback changes are a paper accuracy experiment; no performance improvement is claimed. Evaluate after at least 10 closed option trades.

- Reason: The sideways-regime early return prevented the paper-shadow experiment from evaluating candidate direction on sideways sessions, despite sideways HOLD mentions dominating the Sept 29 no-trade review.
- Related prior entries checked: `DLY-2026-09-30-02`, `DLY-2026-09-30-03`, `EXP-2026-09-30-01`, and `EXP-2026-09-30-02`; this is a separate sideways-gate experiment.
- Files:
  - `market_bot/engine.py` (modified): Allow explicitly opted-in paper-shadow evaluation past the sideways early return while retaining primary HOLD behavior.
  - `market_bot/kite_main.py` (modified): Enable the exception only when paper mode is active, shadow trading is opted in, the setting is enabled, and live orders are disabled.
  - `kite_config.json` (modified): Enable sideways evaluation for the local paper-shadow experiment.
  - `kite_config.example.json` (modified): Keep the new setting disabled by default.
  - `tests/test_strategy.py` (modified): Verify sideways shadow evaluation produces a candidate without changing the primary HOLD.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the scope of the paper-only setting.
  - `DAILY_CHANGELOG.md` (modified): Record this change.
  - `STRATEGY_CHANGELOG.md` (modified): Record baseline, hypothesis, and pending outcome.
- Validation and result: Focused sideways-shadow regression passed; `python -m pytest -q` passed (`122 passed`); both Kite configs parsed; Pylance reported no diagnostics in `engine.py`; `git diff --check` passed.
- Outcome / follow-up / rollback: Pending paper-market observations; disable by setting `paper_shadow_allow_sideways` to `false`. Other score, session, volatility, confirmation, context, option, sizing, and daily-loss controls remain unchanged.

#### DLY-2026-09-30-06

- Reason: Option exits should secure profit from a 20% premium move, then trail gains through progressively higher targets instead of waiting for the prior 40% initial target.
- Related prior entries checked: `DLY-2026-09-30-05`; no prior option-target experiment was recorded.
- Files:
  - `market_bot/kite_main.py` (modified): Set the option target fallback to 20% while retaining staged trailing target advances.
  - `kite_config.json` (modified): Set the active option premium target to 20%.
  - `kite_config.example.json` (modified): Document the 20% option target.
  - `DAILY_CHANGELOG.md` (modified): Record this change.
  - `STRATEGY_CHANGELOG.md` (modified): Record the proposed exit-target experiment.
- Validation and result: Focused intraday suite passed (`36 passed`); `kite_main.py` compiled; both Kite configs parsed.
- Outcome / follow-up / rollback: Performance is unmeasured. Roll back by restoring `option_premium_target_pct` to `0.40` and the code fallback to `0.40`.

#### DLY-2026-10-02-01

- Reason: Replace the option premium's flat 20% initial target and distance-based trailing behavior with milestone profit-booking, explicit short-window exits, and Friday-review telemetry.
- Decisions fixed before coding: M1 +10% moves the strong-signal stop to breakeven; M2 +20% locks +10%; later locks advance by +10%. Existing 0-100 score is used; scores below 82 tighten locks by another 5 percentage points. Strong entries (score >=82) use 10-minute per-milestone windows; otherwise 5 minutes, restarting at each milestone. Retain entry direction and score/confirmation filters, and additionally require the latest underlying signal candle to match the signal direction with body/range >=60%. Target two lots and allow up to three only within the configured risk budget; skip if two lots exceed risk.
- Files:
  - `market_bot/intraday_manager.py` (modified): Add score-scaled milestone stops and per-milestone time-box state.
  - `market_bot/kite_main.py` (modified): Gate option entries on directional candle momentum, and wire signal weakening, risk-capped lot sizing, immediate time-box exits, journal telemetry, and live protective-stop ratchets; retain the 15:15 forced exit.
  - `market_bot/kite_provider.py` (modified): Modify existing broker protective-stop orders at milestone advances.
  - `market_bot/trade_journal.py` and `market_bot/weekly_report.py` (modified): Persist per-trade milestone/exit/holding fields and report frequency and average P&L by option exit cohort.
  - `kite_config.json` and `kite_config.example.json` (modified): Record agreed milestone, window, score, and lot settings.
  - `tests/test_intraday_manager.py`, `tests/test_kite_provider.py`, and `tests/test_paper_reporting.py` (modified): Cover candle momentum, milestone, timer, signal, sizing, broker-stop, and comparison behavior.
  - `INTRADAY_FUTURES_GUIDE.md` and `STRATEGY_CHANGELOG.md` (modified): Document operation and the unmeasured paper experiment.
- Baseline and outcome: No comparable options-only fixed-20% baseline exists in the workspace. The report groups historical option trades without an exit-strategy tag as the fixed-20% cohort; this is observational, not a matched replay. Focused `test_intraday_manager.py` passed (`47 passed`), the full suite passed (`147 passed`), Pylance found no errors in changed Python files, both Kite configs parsed, and `git diff --check` passed. Performance remains unmeasured pending paper trades.
- Rollback: Restore the prior option exit implementation and revert the associated sizing, journal, report, configuration, tests, and documentation changes together.

#### DLY-2026-09-30-07

- Reason: Deployment review found the paper/live option BUY path referenced an undefined `premium`, causing every option BUY entry to fail before position sizing.
- Related prior entries checked: `DLY-2026-09-30-06`; this is a correctness fix for the existing option path, not a strategy experiment.
- Files:
  - `market_bot/kite_main.py` (modified): Use the latest option quote, falling back to the signal price, for BUY-side option sizing.
  - `tests/test_intraday_manager.py` (modified): Add a regression test covering the option BUY sizing path.
  - `DAILY_CHANGELOG.md` (modified): Record the deployment blocker and validation.
- Validation and result: Focused regression passed; full suite passed (`123 passed`); Python compilation, JSON parsing, and `git diff --check` passed. `pip check` reports an unrelated environment conflict: `aiobotocore 2.4.0` requires `botocore<1.27.60,>=1.27.59`, while `botocore 1.27.70` is installed.
- Outcome / follow-up / rollback: Code fix is validated. Recreate or repair the VPS virtualenv from `requirements.txt` before deployment; no performance claim.

### 2026-10-01

#### DLY-2026-10-01-01

- Reason: The 2026-10-01 paper review showed five trend-shadow futures entries losing `₹17,575`; paper lot simulation bypassed the configured risk budget, and the active mixed-mode config did not focus execution on options.
- Related prior entries checked: `DLY-2026-09-30-02`, `DLY-2026-09-30-03`, `DLY-2026-09-30-05`, `DLY-2026-09-30-07`, and `EXP-2026-09-30-01` through `EXP-2026-09-30-04`.
- Files:
  - `kite_config.json` (modified): Set active trading mode to `intraday_options` and emptied the dormant futures universe.
  - `kite_config.example.json` (modified): Make the template options-only with futures discovery disabled.
  - `market_bot/kite_main.py` (modified): Stop forcing a paper option lot when it exceeds the configured premium stop-risk budget.
  - `tests/test_intraday_manager.py` (modified): Verify option sizing is called without the paper-lot bypass.
  - `tests/test_kite_provider.py` (modified): Verify options mode does not invoke futures discovery.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the active options-only mode and dormant futures switch.
  - `DAILY_CHANGELOG.md` (modified): Record this change.
  - `STRATEGY_CHANGELOG.md` (modified): Record the baseline, safety correction, and pending options-only evaluation.
- Validation and result: Focused sizing tests passed (`3 passed`); option provider tests passed (`8 passed`); full suite passed (`123 passed`); both Kite configs parsed as JSON and reported `intraday_options` with empty futures lists; `git diff --check` passed.
- Outcome / follow-up / rollback: Futures code remains available but inactive behind `trading_mode`; do not claim improved profitability until at least 10 closed options paper trades are measured. Roll back the mode only by an intentional config change to `intraday_futures` or `intraday_both` after risk review.

#### DLY-2026-10-01-02

- Reason: The active options-only mode scored option-premium bars instead of underlying bars, and the option provider dropped resolved underlying spot tokens before subscription. Underlying callbacks also needed to remain context-only, and missing directional legs must not fall back to an opposite contract that could be sold short.
- Related prior entries checked: `DLY-2026-10-01-01` and `EXP-2026-10-01-01`; this is a routing correctness fix, not a performance-tuning experiment.
- Files:
  - `market_bot/kite_provider.py` (modified): Keep resolved spot tokens in the options-mode subscription alongside CE/PE contracts.
  - `market_bot/kite_main.py` (modified): Use underlying bars for both options modes and prevent spot-context callbacks from opening standalone trades in options-only mode.
  - `tests/test_kite_provider.py` (modified): Verify spot tokens remain available in selected options mode.
  - `tests/test_intraday_manager.py` (modified): Cover underlying-based option validation and context-only spot callbacks.
  - `DAILY_CHANGELOG.md` (modified): Record this correctness fix and validation outcome.
  - `STRATEGY_CHANGELOG.md` (modified): Record the signal-source correction separately from strategy-performance claims.
- Validation and result: The initial provider/filter suite passed before the final fail-closed addition (`65 passed`); the two fail-closed regressions passed (`2 passed`); final full test suite passed (`126 passed`); Pylance reported no errors in the touched Python files.
- Outcome / follow-up / rollback: Paper option performance remains unmeasured. Verify that resulting decisions use underlying histories and that at least 10 closed option trades are recorded before evaluating strategy expectancy; live orders remain disabled.

#### DLY-2026-10-01-03

- Reason: Lower the primary accuracy-filter minimum score from 75 to 70 as requested, while retaining every non-score entry and risk gate.
- Related prior entries checked: `DLY-2026-09-30-03` and `DLY-2026-10-01-02`; the paper-shadow score override remains 55 and unchanged.
- Files:
  - `market_bot/accuracy_filters.py` (modified): Change the constructor and standalone score-helper defaults to 70.
  - `market_bot/kite_main.py` (modified): Change the runtime config fallback to 70.
  - `market_bot/replay.py` (modified): Keep replay's config fallback aligned at 70.
  - `kite_config.json` (modified): Set the active primary floor to 70.
  - `kite_config.example.json` (modified): Set the template primary floor to 70.
  - `tests/test_intraday_manager.py` (modified): Cover scores 69/70 through both validation paths and preserve the shadow override check.
  - `DAILY_CHANGELOG.md` (modified): Record this change and validation outcome.
  - `STRATEGY_CHANGELOG.md` (modified): Record the single-variable experiment and pending outcome.
- Validation and result: Focused score-floor tests passed (`3 passed`); full suite passed (`126 passed`); both Kite configs parsed with primary/shadow floors `70/55`; Pylance found no diagnostics in changed Python files; `git diff --check` passed.
- Outcome / follow-up / rollback: Strategy performance is unmeasured; track score rejections and closed paper outcomes. Roll back the primary floor to 75 in both configs and all four defaults if the trial is rejected.

#### DLY-2026-10-01-04

- Reason: Align the recent-extreme score bonus with the signal-entry proximity bound after identifying a 0.5% bonus versus 0.3% entry-gate mismatch that can produce high-score HOLDs.
- Related prior entries checked: `DLY-2026-10-01-03` / `EXP-2026-10-01-03`; no prior proximity-bound experiment was recorded.
- Files:
  - `market_bot/engine.py` (modified): Use one proximity threshold for the recent-high/low bonus and directional entry gate; set the default to 0.5%.
  - `market_bot/kite_main.py` (modified): Align the runtime fallback to 0.5%.
  - `market_bot/replay.py` (modified): Align the replay fallback to 0.5%.
  - `kite_config.json` (modified): Set `signal_proximity_pct` to 0.005.
  - `kite_config.example.json` (modified): Document the 0.005 default.
  - `tests/test_strategy.py` (modified): Cover bearish and bullish prices 0.4% from the recent extreme at both 0.3% and 0.5% bounds.
  - `DAILY_CHANGELOG.md` (modified): Record this change and validation outcome.
  - `STRATEGY_CHANGELOG.md` (modified): Record the one-variable experiment and pending outcome.
- Validation and result: Both focused boundary tests passed (`2 passed`); strategy suite passed (`24 passed`); full suite passed (`128 passed`); both Kite configs parsed at 0.005; Pylance found no diagnostics in changed Python files; `git diff --check` passed.
- Outcome / follow-up / rollback: Downside momentum, ADX, breakout, EMA-spread, VWAP, higher-timeframe, context, and risk checks remain unchanged. Performance is unmeasured; rollback by restoring a 0.003 entry proximity and the prior hard-coded 0.005 score bonus.

#### DLY-2026-10-02-02

- Reason: Reduce zero-trade risk from the primary ADX floor without weakening the primary/live entry gate; the user approved an unbacktested paper-only trial after historical-data limitations were identified.
- Related prior entries checked: `DLY-2026-09-30-02`, `DLY-2026-09-30-03`, `DLY-2026-09-30-05`, `DLY-2026-10-01-02`, `DLY-2026-10-01-03`, and `DLY-2026-10-01-04`; this trial changes only the paper-shadow ADX floor.
- Files:
  - `market_bot/engine.py` (modified): Let eligible paper-shadow evaluation continue from ADX 10 while keeping the primary signal HOLD below `min_adx`.
  - `market_bot/kite_main.py` (modified): Pass the shadow floor only when paper mode is enabled and live orders are off.
  - `kite_config.json` (modified): Set `paper_shadow_min_adx=10.0`; primary `min_adx` remains 12, shadow is enabled for paper, live orders remain disabled.
  - `kite_config.example.json` (modified): Document the threshold while keeping shadow promotion disabled by default.
  - `tests/test_strategy.py` (modified): Cover paper-shadow candidate eligibility, primary HOLD preservation, stricter sub-10 rejection, and threshold validation.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document paper-only scope and unbacktested status.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record rationale, limits, and follow-up.
- Validation and result: Focused strategy/runtime tests passed (`66 passed`); full suite passed (`135 passed`). Both configs parsed with active primary/shadow ADX floors `12/10`, and live orders disabled. Pylance found no diagnostics, all 27 `score_market` call sites remain signature-compatible, and `git diff --check` passed. No performance backtest was possible with the available data.
- Outcome / follow-up / rollback: Trial is unbacktested, paper-only, and not a promise of daily trades or profitability. Disable by removing `paper_shadow_min_adx` from `kite_config.json` or by disabling `paper_trade_trend_shadow_signals`; live orders stay off.

#### DLY-2026-10-02-03

- Reason: `AccuracyFilters.get_min_score` had no runtime call sites and returned thresholds as high as 92 although the strategy score is capped at 85; directly wiring it would reject every trade after its sample threshold.
- Related prior entries checked: `DLY-2026-09-30-02`, `DLY-2026-09-30-03`, and `DLY-2026-10-02-02`; this keeps the existing primary/live score floor and shadow score-floor experiment otherwise unchanged.
- Files:
  - `market_bot/accuracy_filters.py` (modified): Bound adaptive floors to the producer's 0-85 score range, preserve configured floors, and wait for ten observations.
  - `market_bot/kite_main.py` (modified): Apply adaptive floors only to paper entries, using the latest ten closed trades from the same strategy variant; keep live validation fixed.
  - `tests/test_intraday_manager.py` (modified): Cover adaptation boundaries, per-variant samples, and live-mode exclusion.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the paper-only adaptive score behavior and sample requirement.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record implementation and experiment outcome.
- Validation and result: Focused `test_intraday_manager.py`, `test_strategy.py`, and `test_backtest.py` passed (`83 passed`); full suite passed (`136 passed`). Pylance found no diagnostics in `accuracy_filters.py`; `kite_main.py` retains two unrelated warnings. All 7 `get_min_score` call sites are signature-compatible and `git diff --check` passed.
- Outcome / follow-up / rollback: No historical options-only replay with fills or a closed paper sample is available; this does not establish improved accuracy. Review after at least 10 closed trades per variant and keep live floors unchanged.

#### DLY-2026-10-02-04

- Reason: Kite index candles have zero volume, and the primary breakout-quality gate requires nonzero relative volume; in options mode the bot scores the underlying index while it has the selected option's actual volume bars available.
- Related prior entries checked: `DLY-2026-10-02-01` through `DLY-2026-10-02-03`; the user selected the selected option contract's own relative volume, not a disabled volume gate.
- Files:
  - `market_bot/engine.py` (modified): Support a separate aligned volume series for breakout-volume confirmation while retaining underlying OHLC/ATR checks.
  - `market_bot/kite_main.py` (modified): Align option volume bars to underlying signal bars and pass the series for options signals.
  - `market_bot/replay.py` (modified): Accept an optional separate volume-confirmation data file for production-like offline evaluation.
  - `tests/test_strategy.py`, `tests/test_intraday_manager.py`, and `tests/test_backtest.py` (modified): Cover zero-index-volume handling, timestamp alignment, and replay input alignment.
  - `DAILY_WEEKLY_OPERATIONS.md`, `DAILY_CHANGELOG.md`, and `STRATEGY_CHANGELOG.md` (modified): Document the selected volume source, experiment, and validation.
- Validation and result: Focused `test_intraday_manager.py`, `test_strategy.py`, and `test_backtest.py` passed (`85 passed`); full suite passed (`138 passed`). Pylance confirmed compatibility at 27 `score_market`, 8 `breakout_quality`, and 4 `run_replay` call sites; no diagnostics in `engine.py`, with only pre-existing warnings elsewhere. `git diff --check` passed.
- Outcome / follow-up / rollback: This may allow some index-option candidates through the volume gate, but does not establish better accuracy or profitability. Replay paired underlying/option data before changing live rollout decisions.

### 2026-10-05

#### DLY-2026-10-05-01

- Reason: Backfill the daily ledger for the October 5 changes already committed in `c760a8b`, `c7f7f2f`, and `60c98dc`.
- Related prior entries checked: `DLY-2026-10-02-04` and `EXP-2026-10-02-05`; the former documents the existing option data path, and the latter records the prior option-entry confirmation requirements.
- Files:
  - `market_bot/kite_provider.py` (modified): Include the end of the current calendar month in the option-expiry lookahead and normalize naïve datetime objects from the host-local timezone to IST.
  - `INTRADAY_FUTURES_GUIDE.md` (modified): Explain the month-end expiry lookahead and its limitations.
  - `tests/test_kite_provider.py` (modified): Cover month-end expiry selection and naïve timestamp conversion.
  - `market_bot/accuracy_filters.py` (modified): Allow callers to explicitly skip candle confirmation while retaining the default confirmation requirement.
  - `market_bot/kite_main.py` (modified): Apply the optional confirmation relaxation, including option candle-momentum confirmation, only to the opted-in paper-shadow variant when paper trading is enabled and live orders are disabled.
  - `kite_config.json` (modified): Enable the confirmation-relaxation experiment for the active paper-shadow config; live orders remain disabled.
  - `kite_config.example.json` (modified): Document the experiment as disabled by default.
  - `tests/test_intraday_manager.py` (modified): Verify the relaxation is opt-in/paper-only and that the score floor remains enforced.
  - `DAILY_CHANGELOG.md` (modified): Record these changes and their validation.
  - `STRATEGY_CHANGELOG.md` (modified): Record the paper-only confirmation experiment.
- Validation and result: `python -m pytest -q tests\test_kite_provider.py tests\test_intraday_manager.py` passed (`83 passed, 1 skipped`).
- Outcome / follow-up / rollback: The expiry and timestamp changes are covered by focused tests. The confirmation relaxation is a paper-only experiment; no improvement in trade frequency, accuracy, or profitability is established. Disable it with `paper_shadow_relax_entry_confirmation=false` or by disabling the paper-shadow strategy.

#### DLY-2026-10-05-02

- Reason: The October 5 logs showed score-55 HOLDs with 20-bar moves below the primary 0.5% directional threshold; the user approved a paper-only trial to evaluate more low-magnitude trend candidates.
- Related prior entries checked: `DLY-2026-09-30-02`, `DLY-2026-09-30-03`, `DLY-2026-10-02-02`, and `EXP-2026-10-02-05`; this changes only the paper-shadow directional-move threshold.
- Files:
  - `market_bot/engine.py` (modified): Evaluate an independently configured lower trend-strength floor for paper-shadow BUY/SELL candidates without changing the primary signal.
  - `market_bot/kite_main.py` (modified): Pass the lower floor only when paper shadow is enabled, paper mode is active, and live orders are disabled.
  - `kite_config.json` (modified): Set the active paper-shadow trend-strength floor to 0.1%; retain the primary 0.5% floor and live-orders-disabled setting.
  - `kite_config.example.json` (modified): Document the opt-in shadow threshold while keeping shadow promotion disabled by default.
  - `tests/test_strategy.py` (modified): Verify bullish and bearish paper-shadow candidates below the primary threshold preserve primary HOLD and reject invalid threshold configurations.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the paper-only threshold and its experimental status.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record rationale, baseline, and pending evaluation.
- Validation and result: The first combined regression run exposed an incomplete paper-mode test fixture (`trade_journal` was missing); after completing the fixture, focused strategy/runtime tests passed (`80 passed`) and the full suite passed (`153 passed, 1 skipped`). Both configs parsed, `git diff --check` passed, and Pylance reported no engine diagnostics; `kite_main.py` retains two existing warnings.
- Outcome / follow-up / rollback: This changes candidate eligibility only; no increase in trades or profit is claimed. Compare shadow candidate/rejection counts and separately attributed closed-trade outcomes; disable by removing `paper_shadow_min_trend_strength` or turning off `paper_trade_trend_shadow_signals`.

#### DLY-2026-10-05-03

- Reason: The October 5 paper review recorded 42 `position_size_zero` rejections. The user selected retaining the two-lot minimum and increasing the daily risk budget enough to permit a minimum-risk NIFTY option entry.
- Related prior entries checked: `DLY-2026-10-02-04`, `DLY-2026-10-05-01`, and `DLY-2026-10-05-02`; prior option sizing requires two risk-qualified lots and caps exposure at three lots.
- Files:
  - `kite_config.json` (modified): Raise `daily_max_loss` from ₹250 to ₹350; paper trading remains enabled and live orders remain disabled.
  - `tests/test_intraday_manager.py` (modified): Verify two 65-unit NIFTY lots at ₹12 premium and a 20% stop fit within the ₹350 risk budget (₹312 estimated stop risk).
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document how the daily-loss setting also caps per-trade sizing and the minimum option risk calculation.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record the approved risk-setting change, evidence, and pending paper evaluation.
- Validation and result: `tests/test_intraday_manager.py` passes (`50 passed`). Both Kite JSON configs parse, the active paper/live guards were checked, and `git diff --check` passes.
- Outcome / follow-up / rollback: This permits sizing only when contract-specific risk remains within budget; it does not guarantee an entry, a daily trade, or profitability. Compare future zero-size rejections and realized losses. Restore `daily_max_loss` to ₹250 to revert.

#### DLY-2026-10-05-04

- Reason: Complete operational follow-up for the stale option quote and missing scheduled daily start: archived decisions showed quote/bar timestamps 19,800 seconds behind decision time, the bot currently needs a fresh daily Kite token, and the documented service had no weekday timer.
- Related prior entries checked: `DLY-2026-10-05-01` already records normalization of Kite's naïve host-local timestamps; `DLY-2026-10-02-01` documents the service's clean end-of-day exit behavior.
- Files:
  - `market_bot/kite_provider.py` (not modified): Retain the existing timezone-normalization fix and stale-quote rejection; archived stale rows precede that fix and do not justify weakening freshness checks.
  - `market_bot/intraday_manager.py` (modified): Reserve open-position stop-risk and restored realized losses against the aggregate daily budget, reset daily counters at session rollover, fail closed on invalid same-day realized P&L, and stop paper sizing from simulating lots above that budget.
  - `market_bot/kite_main.py` (modified): Restore same-session open paper positions, enforce aggregate risk after broker fills, and apply remaining risk to new position sizing.
  - `market_bot/weekly_report.py` (modified): Add entry-flow totals that distinguish BUY/SELL bar signals and expected unselected option-leg skips from side-eligible candidates and opened entries.
  - `run_kite_bot.py` (modified): Add mutually exclusive `--authorize-only` mode to refresh and save the daily token without launching another bot process.
  - `kite-trading-bot.service` (modified): Correct its generic mode description.
  - `kite-trading-bot.timer` (added): Schedule weekday 08:45 IST startup without replaying a missed start after downtime.
  - `tests/test_kite_provider.py` (modified): Cover conversion of Kite SDK naïve local datetimes to IST on the current host timezone.
  - `tests/test_intraday_manager.py` (modified): Cover aggregate risk allocation, realized-loss restoration, daily counter rollover, invalid journal P&L, paper position restoration, post-fill risk rejection, and strict option sizing without a paper-only risk bypass.
  - `tests/test_paper_reporting.py` (modified): Verify daily entry-flow reporting separates an unselected option leg from eligible candidates.
  - `tests/test_run_kite_bot.py` (added): Verify authorize-only exits without starting the bot and rejects conflicting auth modes.
  - `tests/test_kite_provider.py` (modified): Verify option sizing returns no position when the risk budget cannot cover a lot.
  - `DAILY_WEEKLY_OPERATIONS.md` and `DAILY_CHANGELOG.md` (modified): Document timer installation, manual daily token refresh, and the remaining interactive SSH-tunnel requirement.
- Validation and result: Focused regressions passed (`100 passed, 1 skipped`); the full suite passed (`163 passed, 1 skipped`). Pylance reported no diagnostics in the changed Python files, both Kite JSON configs parse, and `git diff --check` passed. Systemd unit/timer parsing must still be confirmed on the target VPS because systemd is unavailable on the Windows development host.
- Outcome / follow-up / rollback: The timer schedules startup but does not automate Kite login or exchange holidays. Refresh the token before each scheduled session and verify the timer on the VPS. Remove the timer and restore manual startup if the deployment does not use systemd.

#### DLY-2026-10-05-05

- Reason: Clarify the risk policy: ₹350 is the maximum planned risk per individual trade, while the daily realized-loss stop should be 2% of the configured options-trading account balance.
- Related prior entries checked: `DLY-2026-10-05-03` and `DLY-2026-10-05-04`; this corrects the earlier configuration that incorrectly used ₹350 as the daily stop.
- Files:
  - `kite_config.json` (modified): Set `max_risk_per_trade` to ₹350 and `daily_max_loss_pct` to 2%; for `account_size` ₹100,000 the daily stop is ₹2,000. Paper trading remains enabled and live orders remain disabled.
  - `kite_config.example.json` (modified): Document both separate risk settings.
  - `market_bot/intraday_manager.py` and `market_bot/kite_main.py` (modified): Apply the separate per-trade cap and account-percentage daily stop while continuing to reserve open-position risk against the daily budget.
  - `tests/test_intraday_manager.py` (modified): Verify a ₹350 loss does not block another eligible trade and the cumulative 2% daily stop does block new entries.
  - `DAILY_WEEKLY_OPERATIONS.md` and `DAILY_CHANGELOG.md` (modified): Document the corrected policy.
- Validation and result: Focused manager tests passed (`57 passed`); full suite passed (`164 passed, 1 skipped`). Changed-file diagnostics reported no errors, both Kite JSON configs parse, the active config computes a ₹2,000 daily stop from 2% of ₹100,000, and `git diff --check` passed.
- Outcome / follow-up: The daily stop scales with `account_size`; the per-trade cap remains ₹350. Reassess only when the options-trading capital or approved risk policy changes.

#### DLY-2026-10-05-06

- Reason: Remove the separate paper-only trend-shadow strategy and filter overrides so paper and live executions evaluate the same signals using the same configured filters.
- Related prior entries checked: `EXP-2026-09-30-01` through `EXP-2026-10-05-01` describe the now-retired shadow experiments. Their historical records and archived trade reports are retained.
- Files:
  - `market_bot/engine.py` (modified): Remove the shadow candidate path and paper-specific ADX, sideways-regime, and trend-strength thresholds.
  - `market_bot/kite_main.py` (modified): Remove shadow promotion, paper-only relaxed confirmation, and adaptive paper score floors; keep mode flags for execution routing.
  - `market_bot/accuracy_filters.py` (modified): Require directional confirmation and use the configured score floor consistently.
  - `kite_config.json` and `kite_config.example.json` (modified): Remove obsolete shadow-only settings.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document that trading mode changes execution only.
  - `tests/test_strategy.py` and `tests/test_intraday_manager.py` (modified): Remove shadow-specific expectations and verify shared strategy/filter behavior.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record retirement of the experiment; retain prior entries as history.
- Validation and result: Focused strategy/runtime/reporting tests passed (`86 passed`); the full suite passed (`152 passed, 1 skipped`). Both Kite configs parse, changed Python files have no reported problems, and `git diff --check` passed.
- Outcome / follow-up: One strategy and shared entry filters now apply in paper and live modes; paper/live enable flags continue to select execution mode. No performance improvement is claimed.

#### DLY-2026-10-05-07

- Reason: Correct the automatic-start setup because Kite access tokens must be refreshed manually every trading day before the bot can start.
- Related prior entries checked: `DLY-2026-10-05-04` added a weekday timer while noting the daily token refresh requirement; this change removes that timer rather than risking startup with a stale token.
- Files:
  - `kite-trading-bot.timer` (removed): Remove the automatic weekday bot startup.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document manual token refresh followed by manual systemd-service or direct bot startup; remove timer installation and verification instructions.
  - `DAILY_CHANGELOG.md` (modified): Record this correction.
- Validation and result: `git diff --check` passed; a repository search found no remaining operational timer installation or scheduling references.
- Outcome / follow-up: Start the bot manually only after the daily Kite token refresh succeeds.

#### DLY-2026-10-05-08

- Reason: The October 5 archived paper session recorded 270 directional decision rows but no `trade_opened` outcome; the daily review reports zero closed trades. The flow includes 165 expected unselected option-leg skips, 42 `position_size_zero`, 56 option-quality rejections, and 7 `position_updated` rows. The user selected a 10% option-premium stop with per-trade planned risk limited by the remaining ₹2,000 daily budget.
- Related prior entries checked: `DLY-2026-10-05-05` defines the ₹2,000 daily loss stop and `DLY-2026-10-05-06` keeps paper and live signal logic aligned. October 5 is a pre-change baseline; no performance inference is made.
- Files:
  - `kite_config.json` and `kite_config.example.json` (modified): Set the paper risk ceiling to ₹2,000 and option premium stop to 10%; the active config remains paper-enabled and live-orders-disabled.
  - `market_bot/kite_main.py` (modified): Use the latest option premium consistently as the paper entry reference for sizing, stop, and target; live fills continue to reset these levels to fill price.
  - `tests/test_intraday_manager.py` (modified): Verify latest-premium entry/stop alignment and that a three-lot NIFTY position at ₹100 premium reserves ₹1,950, leaving only ₹50 under the daily cap.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the 1:1 nominal first target/stop relationship and the possibility that one stopped trade consumes nearly the entire daily budget.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record the user-selected risk-policy experiment and its pending paper evaluation.
- Validation and result: `tests/test_intraday_manager.py` and `tests/test_kite_provider.py` passed (`90 passed, 1 skipped`); both Kite config JSON files parse; `git diff --check` passed. Pylance found only two existing `kite_main.py` warnings outside the edited entry path (`datetime.utcnow` deprecation and an unused `signal` parameter).
- Outcome / follow-up: Paper-only; collect at least 10 comparable closed trades and report stop slippage, costs, P&L, drawdown, and all entry-flow outcomes. Do not enable live orders or claim a performance gain based on increased entries.
