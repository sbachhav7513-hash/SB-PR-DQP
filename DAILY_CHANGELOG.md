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

### 2026-10-06

#### DLY-2026-10-07-01

- Reason: The October 6 paper archive recorded zero BUY/SELL signals across 9,859 decisions; the user requested a small strategy relaxation to improve the chance of producing paper candidates.
- Related prior entries checked: `DLY-2026-10-05-06` keeps one shared strategy for paper/live execution; `EXP-2026-10-05-03` documents the still-unmeasured paper risk-policy experiment. No live-specific signal path was added.
- Files:
  - `kite_config.json` and `kite_config.example.json` (modified): Widen `signal_proximity_pct` from 0.5% to 0.75%.
  - `tests/test_strategy.py` (modified): Verify the wider setting admits a nearby bearish setup while the old setting does not.
  - `STRATEGY_CHANGELOG.md` (modified): Record the change as a bounded paper experiment with a 10-session observation period.
- Validation and result: `tests/test_strategy.py` passed (`23 passed`); both Kite configs parse, the active config remains paper-enabled/live-disabled, and `git diff --check` passed. The archived bars are insufficient to estimate how many past setups the wider band would have admitted.
- Outcome / follow-up: Paper mode remains enabled and live orders remain disabled. More qualifying candidates are possible but neither daily trades nor profitability are guaranteed; evaluate rejection flow and performance with recorded evidence.

#### DLY-2026-10-07-02

- Reason: The user requested lowering the ADX threshold from 12 to 11 to modestly relax strategy eligibility.
- Related prior entries checked: `EXP-2026-10-02-02` documents a retired paper-shadow override; no shadow path is restored. The current paper/live scorer remains shared.
- Files:
  - `kite_config.json` and `kite_config.example.json` (modified): Set `min_adx` to 11.0.
  - `tests/test_strategy.py` (modified): Verify ADX 11.5 is rejected at a threshold of 12 but may qualify at 11.
  - `STRATEGY_CHANGELOG.md` (modified): Record this as a separate paper experiment.
- Validation and result: `tests/test_strategy.py` passed (`24 passed`); both Kite configs parse with `min_adx=11.0`, the active config remains paper-enabled/live-disabled, and `git diff --check` passed. Performance effects remain unmeasured.
- Outcome / follow-up: Other signal and risk controls remain unchanged; paper mode stays enabled and live orders stay disabled. More candidate eligibility is not a performance or daily-trade guarantee.

#### DLY-2026-10-07-03

- Reason: The October 6 daily archive has 4,897 repeated sideways-regime HOLD reason mentions, making the regime gate the most frequent identifiable strategy blocker. These are mentions, not distinct opportunities; underlying-context-only rows are not trade rejections.
- Related prior entries checked: `DLY-2026-10-07-01` and `DLY-2026-10-07-02` record separate proximity and ADX adjustments. This change touches only the sideways net-move threshold.
- Files:
  - `kite_config.json` (modified): Lower `sideways_net_move_pct` from 0.30% to 0.25%; keep `sideways_range_pct` at 0.30%.
  - `tests/test_strategy.py` (modified): Verify the regime gate allows a 0.27% 20-bar move at the new threshold but not the old threshold.
  - `STRATEGY_CHANGELOG.md` (modified): Record this as an isolated paper experiment and define a 10-session observation period.
- Validation and result: Pending focused strategy tests, config parsing, and diff checks.
- Outcome / follow-up: Paper mode remains enabled and live orders remain disabled. The gate relaxation may create more eligible candidates but does not guarantee trades or profitability; keep all downstream safeguards active.

#### DLY-2026-10-06-01

- Reason: A stale open AAPL paper journal record had no `last_price`, so the previously added stale-position recovery still stopped startup. The user approved closing such records at entry price with explicitly estimated zero P&L.
- Related prior entries checked: `DLY-2026-10-05-04` and `DLY-2026-10-05-05` document paper journal restoration and risk-state recovery; this is an operational correctness fix, not a strategy or risk-policy experiment.
- Files:
  - `market_bot/trade_journal.py` (modified): Persist active paper-position price marks at most once per minute for restart recovery.
  - `market_bot/kite_main.py` (modified): Recover stale open paper records at a valid persisted mark when available; otherwise close at entry and label the record `STALE_PAPER_POSITION_RECOVERY_AT_ENTRY_ESTIMATE`.
  - `tests/test_intraday_manager.py` (modified): Cover checkpoint throttling, tick-driven mark persistence, persisted-mark recovery, and the missing-mark entry-price estimate.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the recovery mark and estimated fallback, including their limitations.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record this operational correction separately from strategy experiments and performance claims.
- Validation and result: `tests/test_intraday_manager.py` passed (`59 passed`); Pylance reported no diagnostics in the touched Python files; `git diff --check` passed.
- Outcome / follow-up: Startup can recover legacy stale records with a valid positive entry price, but an entry-price exit is an estimate rather than an exchange close or realized return. No strategy-performance conclusion is implied.

### 2026-10-08

#### DLY-2026-10-08-01

- Reason: The October 7 paper review recorded 8,752 regular-session decisions but zero BUY/SELL signals and zero opened trades. The review named missing compression and breakout-candle confirmation among the recurring HOLD reasons; this was a signal-generation block, not an order-placement failure.
- Related prior entries checked: `DLY-2026-10-07-01` through `DLY-2026-10-07-03` and `EXP-2026-10-07-01` through `EXP-2026-10-07-03` record the proximity, ADX, and sideways-regime adjustments. This change relaxes two additional gates and is explicitly isolated to paper mode.
- Files:
  - `market_bot/engine.py` (modified): Add an opt-in paper trend-continuation path that skips only the compression and breakout-candle quality checks; retain ADX-rise, EMA expansion, VWAP, benchmark, and other gates.
  - `market_bot/kite_main.py` (modified): Enable the relaxed scorer option only when paper trading is active and the config flag is true.
  - `kite_config.json` (modified): Enable `paper_allow_trend_continuation`; paper trading stays enabled and live orders stay disabled.
  - `kite_config.example.json` (modified): Document the option disabled by default.
  - `tests/test_strategy.py` (modified): Verify strict mode rejects the setup and the paper option relaxes only the two named quality checks.
  - `TRADING_ACCURACY_GUIDE.md` (modified): Document the paper-only experiment and its safety limits.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record the change, evidence, validation, and pending outcome.
- Validation and result: `tests/test_strategy.py` passed (`26 passed`). Full-suite run excluding the unrelated partial-object fixture test `test_on_tick_stores_timestamp_required_by_option_quality_gate` passed (`162 passed, 1 skipped, 1 deselected`). Pylance reported no errors in changed Python files; both Kite config JSON files parse; `git diff --check` passed.
- Outcome / follow-up: This paper-only relaxation may produce additional directional signals but guarantees neither a trade nor profitability. Compare the next daily archive's directional signals, trade openings, remaining rejection reasons, and closed-trade outcomes; do not enable live orders based on this experiment.

#### DLY-2026-10-08-02

- Reason: The active scorer can produce a directional signal at score 55, while the final entry filter required 70. The user approved a separate lower score floor for paper entries to allow eligible lower-scored signals to reach the remaining safety gates.
- Related prior entries checked: `DLY-2026-10-08-01` enables paper-only trend continuation while keeping live scoring strict; `DLY-2026-10-05-06` documents the shared strategy baseline. This change only adjusts the final score floor in paper mode.
- Files:
  - `market_bot/kite_main.py` (modified): Add validated `paper_min_entry_score`; apply it only when paper trading is enabled, both to entry validation and the stored signal-health floor. Live continues using `min_entry_score`.
  - `kite_config.json` (modified): Set paper floor to 55; keep the standard floor at 70 and live orders disabled.
  - `kite_config.example.json` (modified): Document a conservative paper floor of 70 by default.
  - `tests/test_intraday_manager.py` (modified): Verify a score-60 option signal passes the paper score gate at 55, is rejected live at 70, and the position-health threshold follows the mode.
  - `TRADING_ACCURACY_GUIDE.md` (modified): Document both paper-only settings and unchanged downstream controls.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record this bounded experiment and its pending results.
- Validation and result: Focused runtime tests passed (`6 passed`); the full suite excluding the unrelated incomplete-fixture test `test_on_tick_stores_timestamp_required_by_option_quality_gate` passed (`162 passed, 1 skipped, 1 deselected`). Pylance reported no errors in changed Python files; both Kite configs parse and contain the expected 55 paper / 70 standard floors with live orders disabled; `git diff --check` passed.
- Outcome / follow-up: Paper-only; lower-scored entries can still be rejected by confirmation, option quality, position sizing, or risk controls. No trade or performance improvement is guaranteed. Review candidate and rejection counts tomorrow before considering another change.

#### DLY-2026-10-08-03

- Reason: The October 8 daily paper review recorded 49 BUY/SELL decisions and 25 side-eligible candidates but no opened trades; six side-eligible candidates were rejected as `position_size_zero`. The option sizing helper and both configs required a two-lot minimum even when the risk budget could cover one lot.
- Related prior entries checked: `DLY-2026-10-05-05` and `EXP-2026-10-05-03` record option premium sizing and a one-lot minimum-risk requirement; `DLY-2026-10-08-01` and `DLY-2026-10-08-02` document separate signal/entry-floor paper experiments. This change only makes the configured minimum lot one; existing risk calculations remain in force.
- Files:
  - `market_bot/kite_main.py` (modified): Set the option-sizing and lot-validation fallback minimum to one lot.
  - `kite_config.json` and `kite_config.example.json` (modified): Set `option_min_lots` to 1.
  - `tests/test_intraday_manager.py` (modified): Verify one TCS option lot is sized only when its planned risk fits the configured cap.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the one-lot minimum and continued risk-budget enforcement.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record the rationale, boundaries, and evaluation status.
- Validation and result: `tests/test_intraday_manager.py` passed (`59 passed`); Pylance reported no errors in the touched Python files; `git diff --check` passed.
- Outcome / follow-up: Removes the fixed two-lot minimum as a blocker, but does not bypass entry-quality or risk checks and does not guarantee a trade or profit. Review subsequent paper-session entry and rejection counts.

#### DLY-2026-10-08-04

- Reason: The user clarified the options risk policy: cap each trade at 10% of one lot's premium value and cap daily risk at 10% of account value.
- Related prior entries checked: `DLY-2026-10-08-03` records the one-lot minimum; `DLY-2026-10-05-05` and `EXP-2026-10-05-03` record the preceding 2% daily budget and 10% premium stop. This entry records the subsequent user-directed risk-policy change; it does not claim improved trading performance.
- Files:
  - `kite_config.json` and `kite_config.example.json` (modified): Set `daily_max_loss_pct` to 10%, leave the options `max_risk_per_trade` override unset, and set `option_max_risk_per_lot_pct` to 10%.
  - `market_bot/kite_main.py` (modified): Cap option sizing and entry/recovery risk checks at the lesser of remaining daily budget and 10% of one lot's premium notional; derive the options-mode daily trade-risk ceiling from the daily account-percentage budget.
  - `market_bot/intraday_manager.py` (modified): Avoid losing an exactly affordable option lot to floating-point division rounding.
  - `tests/test_intraday_manager.py` (modified): Verify the ₹10,000 daily cap on a ₹100,000 account, the 10%-of-lot-premium entry cap, and a TCS lot risk calculation.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the updated paper risk values and example.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record the risk-policy change and validation.
- Validation and result: `tests/test_intraday_manager.py` passed (`59 passed`); Pylance reported no errors in the touched Python files; active and example Kite JSON settings were checked; `git diff --check` passed.
- Outcome / follow-up: Paper trading remains enabled and live orders remain disabled. A 10% account daily loss cap is materially larger than the earlier 2% cap; actual fills, gaps, slippage, and fees can exceed planned stop-risk. Observe and review realized paper losses; no increased trade frequency or profitability is claimed.

#### DLY-2026-10-08-05

- Reason: The October 8 review recorded 15 `OPTION_FILTER_WEAK_CANDLE_MOMENTUM` rejections among 25 side-eligible directional candidates. The user approved one more controlled change to this execution filter after earlier paper-only sizing/risk changes.
- Related prior entries checked: `DLY-2026-10-08-01` and `DLY-2026-10-08-02` record paper-only continuation and score-floor trials; `DLY-2026-10-08-03` and `DLY-2026-10-08-04` record the one-lot option sizing and revised risk budget. This trial changes only the minimum option signal candle body/range ratio.
- Files:
  - `market_bot/kite_main.py` (modified): Add a validated paper candle-body ratio setting; use it only for paper entries and preserve the 60% requirement for live/default behavior.
  - `kite_config.json` (modified): Set the active paper-only candle-body ratio to 40%; live orders remain disabled.
  - `kite_config.example.json` (modified): Keep the example/default ratio at 60%.
  - `tests/test_intraday_manager.py` (modified): Verify 40% versus 60% candle qualification and paper-only threshold selection.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the experiment, unchanged live threshold, remaining gates, and limitations.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record baseline, hypothesis, and evaluation plan.
- Validation and result: `tests/test_intraday_manager.py` passed (`60 passed`); Pylance reported no errors in the touched Python files; `kite_config.json` and `kite_config.example.json` parsed successfully; `git diff --check` passed.
- Outcome / follow-up: Paper-only experiment; this can admit additional directional candles but does not bypass the other entry or risk checks and cannot guarantee trades or profitability. Compare the next session's candle rejection count, remaining rejection reasons, entries, and closed-trade results before changing another strategy variable.

#### DLY-2026-10-09-01

- Reason: Complete the requested historical evaluation of the whole current paper options strategy; the 40% candle-body threshold is only one setting in the comparison.
- Evaluation: Read-only Kite historical minute OHLCV and OI replay for October 7-8, 2026, comparing the active 40% paper candle-body threshold with a controlled 60% run. The replay applied the active scorer and paper trend-continuation/score-floor settings, option selection and premium/volume/OI gates, accuracy/cooldown and timing checks, one-trade-per-leg/session control, 10%-of-one-lot-premium risk sizing, 10%-of-account daily risk budget, and paper exits/timeboxes. No orders were placed.
- Whole-strategy result at 40%: 10 closed trades, 2 winners (20%); gross P/L -INR 3,496.25. Estimated net: -INR 3,896.25 with INR 40 brokerage per round trip and no slippage; -INR 4,200.75 at 5 bps slippage per side; -INR 4,505.25 at 10 bps; -INR 5,114.25 at 20 bps. Session gross P/L: October 7 -INR 2,360 (7 trades); October 8 -INR 1,136.25 (3 trades). The daily realized-equity drawdown estimate at zero slippage was 3.20% and 1.26%, respectively; maximum reserved stop risk was INR 4,143.50 and INR 2,087.80, each below the INR 10,000 daily budget.
- Threshold comparison: The 60% run produced 9 trades, 2 winners (22.22%), gross P/L -INR 3,237.50, and estimated net P/L -INR 3,597.50 at zero slippage plus brokerage. Reducing the candle threshold admitted one additional October 7 trade, but worsened gross P/L by INR 258.75 and did not add a trade on October 8. Neither run was profitable in this sample.
- Files:
  - `paper_trading_data/backtests/kite_option_replay_2026-10-07_08.json` (added): Full per-session/per-threshold metrics, trade ledger, rejection counts, cost sensitivities, contract coverage, and caveats.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record the complete replay outcome and limitations.
- Limitations and decision: This is a two-session counterfactual, not actual historical bot trades or enough data to estimate strategy expectancy. Minute bars cannot reproduce tick order or executable bid/ask fills; historical option IV and spreads are unavailable, brokerage/tax estimates are incomplete, and the configured TATAMOTORS contracts were unavailable. Do not infer a durable edge or live readiness. Keep live orders disabled; review a longer sample before further strategy changes.
- Validation: Confirmed the saved JSON parses and its four scenario trade counts, daily P/L, cost estimates, and contract-coverage caveats reconcile with the replay output.

#### DLY-2026-10-09-02

- Reason: The user requested monitoring today's paper session with the 60% candle-body threshold after the full-strategy two-session replay showed no benefit from 40%.
- Change: Restored `kite_config.json` `paper_option_min_candle_body_ratio` from 0.40 to 0.60. Paper mode remains enabled and live orders remain disabled; no other strategy setting was changed.
- Monitoring plan: Review October 9 paper decisions and trades after the session, including signal counts, each rejection reason, contracts, entry/exit times and prices, gross/net P/L, and risk/drawdown. Use that evidence to decide any further strategy change; do not infer performance from trade count alone.
- Documentation: Updated `DAILY_WEEKLY_OPERATIONS.md` to identify 60% as the active threshold and explain the monitoring plan.
- Validation: Active and example Kite JSON parsed; active threshold is 0.60, paper trading is enabled, and live orders are disabled. `git diff --check` passed.

#### DLY-2026-10-09-03

- Reason: The user requested a thorough backtest of the full current paper options strategy on the previous completed week, not another isolated candle-threshold comparison.
- Related prior entries checked: `DLY-2026-10-09-01` records the October 7-8 full-strategy comparison; `DLY-2026-10-09-02` records restoration of the active paper threshold to 60%.
- Evaluation: Read-only Kite minute OHLCV/OI proxy replay for September 28-October 1, 2026, using the current 60% paper threshold and current paper scorer, option gates, accuracy/timing/cooldown filters, one-trade-per-leg/session control, risk sizing, and paper exits. Four sessions and nine underlying roots were replayed; October 2 had no bars in the available dataset. No orders were placed and no strategy/config behavior was changed.
- Results: 14 closed one-lot trades, 8 winners and 6 losers (57.14%); gross P/L +INR 760. Session gross P/L: Sep 28 INR 0 (3 trades), Sep 29 +INR 303.75 (2), Sep 30 +INR 95 (3), and Oct 1 +INR 361.25 (6). Aggregate gross profit factor 1.2734; gross realized trade-close max drawdown INR 1,862.50 (1.8625% of the configured INR 100,000 account); longest losing streak 2. Estimated net P/L: +INR 200 with INR 40 round-trip brokerage and zero slippage; -INR 76.61 at 5 bps per side; -INR 353.21 at 10 bps; and -INR 906.42 at 20 bps. The result turns negative with modest illustrative slippage.
- Risk and gate observations: Maximum reserved stop risk was INR 3,975.25 against the configured INR 10,000 daily budget. Reported gate counters include 52 weak-candle, 60 late-window, and 35 unavailable-contract rejections. The replay used 46 unique proxy option symbols; TATAMOTORS was excluded because matching options were absent from the current instrument master.
- Files:
  - `paper_trading_data/backtests/kite_option_proxy_replay_2026-09-28_10-01.json` (added): Full settings snapshot, selected later-expiry proxy contracts, daily results, trade ledger, rejection counters, cost scenarios, limitations, and independently reconciled ledger/drawdown audit.
  - `DAILY_CHANGELOG.md` (modified): Recorded this evaluation and its caveats.
  - `STRATEGY_CHANGELOG.md` (modified): Recorded the full-strategy proxy result as inconclusive evidence, not a strategy change.
- Limitations and outcome: The user-approved later-expiry contracts are not the historical nearest-expiry contracts; premium path, liquidity, greeks, and P/L may differ materially. This is only four sessions, with no October 2 bars; minute OHLC approximates fills and cannot reproduce tick sequencing, historical spreads, IV, taxes, or all execution costs. The October 1 archived `trend_shadow_paper` trades are a different strategy and are not included. Do not infer a durable edge from this proxy; keep live orders disabled and make no new strategy changes based on this sample alone.
- Validation: Parsed the JSON; independently reconciled all 14 trade rows to reported counts and gross P/L, checked each P/L against entry/exit/quantity and each quantity against its lot size, recomputed win rate/profit factor/drawdown/loss streak, reconciled transaction-cost scenarios, and confirmed reserved stop risk stayed below the daily budget. `git diff --check` passed.

#### DLY-2026-10-09-04

- Reason: The user correctly noted that the prior-week proxy trade ledger showed `signal: SELL` beside PE contracts without recording the option transaction side, making bearish underlying signals look like short option entries.
- Related prior entry checked: `DLY-2026-10-09-03` records the replay and its original ledger. Production routing in `market_bot/kite_main.py` maps a bearish `SELL` signal to the PE leg and converts the option action to BUY; `tests/test_kite_provider.py` verifies PE+SELL maps to a BUY action.
- Files:
  - `paper_trading_data/backtests/kite_option_proxy_replay_2026-09-28_10-01.json` (modified): Added per-trade underlying signal, option type, BUY entry action, long-option position type, SELL exit action, and a root-level explanation. Existing `signal` fields and P/L were preserved.
  - `DAILY_CHANGELOG.md` (modified): Recorded this report-clarity correction.
  - `STRATEGY_CHANGELOG.md` (modified): Appended an auditability clarification without changing the strategy or replay metrics.
- Validation: Verified all 14 rows map bearish SELL signals to PE and bullish BUY signals to CE, all use BUY entry / LONG_OPTION / SELL exit, and their existing P/L remains `(exit premium - entry premium) * quantity`. Parsed the JSON and ran `git diff --check`.
- Outcome: No strategy or configuration behavior changed; live orders remain disabled.

#### DLY-2026-10-12-01

- Reason: The user asked whether the revised option signal-weakening rule would change the losing exits in Friday's October 9 paper session.
- Evaluation: Read the five closed trades and archived one-minute option candles/signal scores from `paper_trading_data/2026-10/week_41/day_09`. Both recorded `SIGNAL_WEAKEN` exits (ICICIBANK_CE and RELIANCE_CE) remained above their 5%-below-entry adverse thresholds through their decision windows, so the revised rule would defer them to their existing 10-minute `TIME_BOX`. The TCS trailing-stop exit and INFY/HDFCBANK time-box exits are unchanged.
- Counterfactual estimate: Using the closes of the one-minute candles containing the deferred deadlines gives approximately +INR 385 for ICICIBANK_CE and +INR 125 for RELIANCE_CE. Keeping the other three actual fills unchanged gives an estimated Friday total of +INR 272.50 versus the recorded -INR 142.50. The changed exits' full-candle OHLC bounds produce a combined day-P&L range of approximately -INR 122.50 to +INR 412.50.
- Code correction: Treat deterioration according to position action, not CE/PE contract name. Both CE and PE trades are bought options, so a falling premium is adverse for either; added a regression covering a falling PE premium and a rising PE premium.
- Limitations and decision: The archive contains minute OHLC, not the tick quote at each timer deadline or executable bid/ask fills. The counterfactual exit prices and P&L are estimates, not an exact tick replay or evidence of durable strategy improvement. This Friday sample contains CE trades only; PE behavior is unit-tested but not empirically covered by this session. Continue observing a larger paper sample and keep live orders disabled.
- Validation: The focused `tests/test_intraday_manager.py` suite passed (60 tests). The full suite had 163 passes and 1 skip, with one separate `_on_tick` test failing because its fixture lacks `paper_trading_enabled`; the failing assertion does not invoke the edited exit rule.

#### DLY-2026-10-13-01

- Reason: The user requested checking prior change logs and testing the paper score floor change from 55 to 60 against historical trades, without changing the daily loss cap.
- Related entries checked: `DLY-2026-10-08-02` / `EXP-2026-10-08-02` (paper entry floor 55), `DLY-2026-10-09-01` (October 7-8 historical replay), `DLY-2026-10-09-03` (September 28-October 1 proxy replay), and `EXP-2026-10-12-01` (option exit counterfactual method).
- Files: `kite_config.json` remains at `paper_min_entry_score=60` and `daily_max_loss_pct=10.0`; no strategy code or risk-cap change was made. This entry records the historical evaluation.
- Evaluation: October 13's 80 directional decision rows scored 65 or 85; all three opened trades scored 65. Across the 33 closed trades in the saved historical replay ledgers, scores were also only 65 or 85. No logged entry would be excluded by a 60 rather than 55 entry floor. Replaying the production option signal-health check over today's decision snapshots showed SBIN_CE and TCS_CE exit at the same event, while RELIANCE_CE would trigger earlier at floor 60 on the 09:37:46 IST score-55 / INR 25.95 bar-close snapshot. That mark estimates -INR 925 versus the recorded -INR 725 exit at floor 55; a same-method bar-close comparison estimates INR 100 additional loss.
- Limitations and outcome: The score floor is shared by entry validation and signal-health exit logic, so it can change an already-open trade even when all entries remain eligible. Minute decision snapshots do not provide the exact tick quote or executable fill; this is a counterfactual estimate, not an exact replay. The saved older option replay ledgers lack their raw input bars for rerunning these exits. No orders were placed; the 10% daily loss cap was not changed.
- Validation: Called the production `_check_option_signal_health` method for both floors on the archived October 13 trade intervals and checked every saved historical replay trade score. Results do not support claiming that floor 60 improves profitability.

#### DLY-2026-10-13-02

- Reason: The user requested a self-learning feedback loop after repeated strategy/filter changes failed to establish sustained improvement. Existing weekly reporting could identify a “best” profile after only two trades and suggested raising the score threshold for a sub-50% win rate, despite the strategy log requiring at least 10 closed trades before a strategy decision.
- Related entries checked: `DLY-2026-10-09-01` / `EXP-2026-10-09-01` (negative two-session replay), `DLY-2026-10-09-03` / `EXP-2026-10-09-03` (four-session cost-sensitive proxy replay), `DLY-2026-10-12-01` / `EXP-2026-10-12-01` (estimated exit counterfactual), and `DLY-2026-10-13-01` / `EXP-2026-10-13-01` (score-floor evaluation).
- Baseline: October 12-13 archives contain five closed paper trades, all losses, with recorded P&L of -INR 3,598.75 before separately modeled brokerage, taxes, or slippage. Three October 13 `SIGNAL_WEAKEN` exits total -INR 3,421.25. This is a descriptive two-session sample, not evidence that the exit reason caused the losses or that another rule would improve results.
- Files:
  - `market_bot/weekly_report.py` (modified): Add sample-gated learning feedback and repeated losing-exit summaries; remove low-sample profile selection and win-rate-based threshold-change advice; disclose that recorded paper P&L excludes unmodeled execution costs.
  - `tests/test_weekly_report.py` (modified): Verify repeated-loss attribution is surfaced descriptively, recommendations remain blocked below the 10-trade screening floor, and only sufficiently repeated setup windows are shown.
  - `tests/test_paper_reporting.py` (modified): Verify daily feedback, sample gating, and pre-cost P&L labeling.
  - `tests/test_intraday_manager.py` (modified): Verify low-sample setup windows are withheld while preserving the pre-existing score-floor assertion.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the advisory-only feedback and evidence requirements.
  - `DAILY_CHANGELOG.md` (modified): Record this work.
- Validation: The focused reporting/setup-window tests passed (`10 passed, 66 deselected`). The full suite passed with the known unrelated `_on_tick` fixture test excluded (`169 passed, 1 skipped, 1 deselected`); an unfiltered run confirms that fixture still fails because it omits `paper_trading_enabled`. Pylance reported no diagnostics in `weekly_report.py`, `test_weekly_report.py`, or `test_paper_reporting.py`; the touched `test_intraday_manager.py` has two pre-existing unused-`limit` warnings. `git diff --check` passed. Running the feedback helper against the October 12-13 trade Parquet files returned 5/10 screening trades, recorded P&L -INR 3,598.75 before costs, and the two observed losing-exit groups; it recommended no strategy tuning.
- Outcome / follow-up: No strategy, risk, or live-order setting is changed. The learning layer can surface review hypotheses but never edits config or auto-promotes a strategy. Keep live orders disabled and collect more paper data; reaching 10 trades is only a screening minimum, not proof of an edge.

#### DLY-2026-10-13-03

- Reason: The user asked for a local way to export Kite history for offline strategy replay.
- Related entries checked: `DLY-2026-10-09-01` and `DLY-2026-10-09-03` document the limitations of current historical replay data and reconstructed option contracts.
- Files:
  - `market_bot/kite_history_export.py` (added): Add a read-only CLI for exporting configured underlying and exact-manifest option minute candles, retaining returned OI and writing a coverage/contract manifest. Credentials are read from environment or `.env`; output defaults to `data_uploads/kite_history`; existing files are protected unless `--overwrite` is passed.
  - `tests/test_kite_history_export.py` (added): Cover date chunking, option manifest validation and expiry clipping, underlying-token resolution, timestamp/OI export, and overwrite protection.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the Windows command, exact option manifest columns, credential handling, and historical-data limitations.
  - `DAILY_CHANGELOG.md` (modified): Record this exporter work.
- Validation: `python -m pytest -q tests\test_kite_history_export.py` passed (9 tests); `python -m market_bot.kite_history_export --help` succeeded; Pylance reported no errors and the syntax check passed for the exporter. `git diff --check` passed. The adjacent combined Kite/provider test run reported 45 passed, 1 skipped, and one pre-existing `_on_tick` fixture failure because that test does not initialize `paper_trading_enabled`; exporter tests pass independently.
- Outcome / follow-up: Exporter is ready for local use; no credentials were read into the report, no API export was executed, and no orders or strategy/config changes were made. Old option contracts still require their exact saved instrument tokens, and Kite historical candles do not provide bid/ask or IV.

#### DLY-2026-10-14-01

- Reason: Locate dated Kite option-token mappings after the user created an empty exporter manifest.
- Related entries checked: `DLY-2026-10-09-01` records the October 7-8 whole-strategy replay and selected-contract metadata; `DLY-2026-10-13-03` documents the exporter and its exact-token requirement.
- Files:
  - `data_uploads/kite_history/options.csv` (modified): Populate 28 unique option contracts covering the 30 dated selections recorded in `paper_trading_data/backtests/kite_option_replay_2026-10-07_08.json`; combine the two unchanged BANKNIFTY tokens across October 7-8.
  - `DAILY_CHANGELOG.md` (modified): Record the source, scope, and limitation of this recovered mapping.
- Validation: The exporter's `_read_option_manifest` parsed all 28 rows for October 7-8 with 28 unique tokens across eight underlyings; PowerShell checks confirmed valid CE/PE types, positive tokens/lot sizes, and ordered active dates. `git diff --check` passed. The Kite API export was not run.
- Outcome / follow-up: The report only records selected contracts for October 7-8, 2026. This is not an exhaustive contract universe or dated mapping for August-October and cannot support a full-period options replay; export only these two sessions with an output directory separate from the existing user export.

#### DLY-2026-10-14-02

- Reason: Screen additional entry/symbol filters against the available options replay ledgers at the user's request.
- Related entries checked: `DLY-2026-10-09-01`, `DLY-2026-10-09-03`, `DLY-2026-10-14-01`, and `EXP-2026-10-13-01`; the user-requested active paper score floor remains 60.
- Files:
  - `STRATEGY_CHANGELOG.md` (modified): Record score-floor and symbol-exclusion sensitivities, costs, caveats, and the no-change decision as `EXP-2026-10-14-01`.
  - `DAILY_CHANGELOG.md` (modified): Record this analysis and its outcome.
- Validation: Recomputed the archived 60% candle-body trade subsets from both JSON ledgers. A post-hoc score floor of 80 was profitable only in the three-trade later-expiry proxy (+INR 2,540.26 net at 10 bps/side plus INR 40 brokerage) and lost on the later exact-contract sample (-INR 562.73 on four trades). Excluding SBIN and RELIANCE yielded only INR 17.72 estimated net on four hindsight-selected trades at the same costs. No strategy code or config changed; no orders were placed.
- Outcome / follow-up: Findings are inconclusive and do not justify implementing a strategy filter. Keep the active score floor at 60 and live orders disabled. Reassess with a predeclared candidate and independent, adequately sized exact-contract holdout or forward paper sample.
- Follow-up validation: Added preselected 09:30/10:00 entry-time sensitivity. 09:30 removed no trades; 10:00 still lost on the exact-contract sample (-INR 3,602.68 estimated net including assumed brokerage and 10 bps per-side slippage). The proxy's 10:00 slice was barely positive (+INR 46.50) and did not transfer. No candidate has repeatable positive net evidence.

#### DLY-2026-10-14-03

- Reason: Prevent local historical market-data uploads from being committed or pushed to the repository.
- Related entries checked: `DLY-2026-10-14-01` records recovered option mappings and local history files; no existing rule ignored the full upload directory.
- Files:
  - `.gitignore` (modified): Ignore `/data_uploads/` at the repository root.
  - `DAILY_CHANGELOG.md` (modified): Record the ignore rule and tracked-file handling.
- Validation: `git check-ignore` confirms the current Kite and NSE upload files are ignored. Two previously tracked NSE metadata CSV/JSON files were removed from the Git index while preserved in the working directory.
- Outcome / follow-up: Uploads remain available locally but will not be included in future commits. Existing history that was already pushed to earlier commits is not rewritten.

#### DLY-2026-10-14-04

- Reason: Provide a repeatable, exact-token Kite data capture workflow for building a forward options replay dataset.
- Related entries checked: `DLY-2026-10-13-03` documents the general exact-token exporter; `DLY-2026-10-14-01` records the limited two-session recovered map; `DLY-2026-10-14-02` records that current replay evidence does not justify filter changes.
- Files:
  - `market_bot/kite_daily_research_export.py` (added): Add a two-stage daily collector that snapshots configured-root NFO option mappings before the session and exports underlying plus near-ATM selected-expiry minute OHLCV/OI candles after market close.
  - `tests/test_kite_daily_research_export.py` (added): Cover nearest-expiry/strike selection, unavailable roots, dated snapshot round-trip, and snapshot date validation.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the pre-market snapshot and post-market export commands, stored files, selection scope, and minimum evidence caveats.
  - `DAILY_CHANGELOG.md` (modified): Record this workflow.
- Validation: `python -m pytest -q tests\test_kite_daily_research_export.py tests\test_kite_history_export.py` passed (13 tests); CLI `--help` succeeded; Pylance syntax checks and Problems reported no errors in the new module/tests; focused runtime selection returned both CE/PE contracts; `git diff --check` passed. Ran the pre-market snapshot command for 2026-10-14: saved 3,938 unique configured-root option mappings for nine roots (CE/PE) and confirmed the output is ignored by Git. The after-close historical-candle export remains to be run after the session.
- Outcome / follow-up: The collector records a prior-close near-ATM proxy universe, not every runtime chain change; users should keep the bot's decision/trade archives alongside the candles and collect at least 30-60 sessions. Do not promote strategy filters from two weeks or a small trade count alone.

#### DLY-2026-10-14-05

- Reason: The user requested a paper-only implementation and same-day counterfactual replay of a delayed `SIGNAL_WEAKEN` exit against the four October 14 losses and exact-token option candles.
- Related entries checked: `DLY-2026-10-12-01` / `EXP-2026-10-12-01` (adverse-premium gate counterfactual), `DLY-2026-10-14-02` (no entry/symbol filter promoted from small samples), and `DLY-2026-10-14-04` (daily exact-token candle export).
- Files:
  - `market_bot/kite_main.py` (modified): Require two consecutive weak-signal plus existing 5%-adverse checks in paper mode; keep live behavior unchanged and persist the check count.
  - `market_bot/intraday_manager.py` (modified): Initialize and restore the confirmation count on a position.
  - `market_bot/trade_journal.py` (modified): Include the confirmation count in paper trade records.
  - `tests/test_intraday_manager.py` (modified): Verify paper confirmation, reset, live immediacy, and state restoration.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the paper-only exit confirmation and the inconclusive same-day result.
  - `DAILY_CHANGELOG.md` (modified): Record this implementation and the measured replay outcome after validation.
  - `STRATEGY_CHANGELOG.md` (modified): Record this single-variable paper experiment, baseline, and outcome after validation.
- Validation: Focused `test_intraday_manager.py` and `test_paper_reporting.py` passed (72 tests); Pylance Problems reported no issues in the changed Python files; `git diff --check` passed. Replayed the patched production exit method against the archived October 14 score decisions and exact option contracts using only the last completed minute close at each event. All four two-check exits occurred without a candle touch of the recorded stop-loss or take-profit. Counterfactual gross P&L was -INR 5,074.50 versus the recorded -INR 3,853.25 (delta -INR 1,221.25).
- Outcome / follow-up: None of the four trades became positive; all four counterfactual losses were larger. This is minute-close counterfactual evidence, not executable tick-fill evidence: historical bid/ask, within-minute sequencing, and costs are unavailable. Keep the change paper-only and live behavior unchanged; do not describe it as loss-minimizing or promote it from this four-trade sample. Gather forward paper evidence or revert if the user does not want to continue the experiment.

#### DLY-2026-10-14-06

- Reason: The user asked to test earlier premium-breakout entries after the ICICIBANK 1360 PE entered late, and approved a separate paper-only pilot for configured CE/PE legs.
- Related entries checked: `DLY-2026-10-14-05` / `EXP-2026-10-14-02` (distinct two-check `SIGNAL_WEAKEN` exit experiment and negative four-trade result); `DLY-2026-10-14-04` (daily exact-token candle export).
- Single experimental variant: Enter a configured option contract when a completed premium candle closes above the high of the previous 15 completed one-minute candles, independent of underlying score and the normal late-entry block. Keep normal quote-quality and aggregate/per-trade risk gates. Stop one tick below the range low; target 2R. Keep one trade per contract per session and use the existing shared daily risk budget across CE/PE contracts. Keep this separate from the existing exit-delay experiment.
- Files:
  - `market_bot/kite_main.py` (modified): Add the separately tagged paper-only entry path, dynamic range-based stop/2R target, and fixed-target exits; leave the legacy and live entry paths unchanged.
  - `market_bot/intraday_manager.py` (modified): Store a per-position trailing override and exit variant so the pilot's target survives the global trailing policy and paper restart.
  - `market_bot/trade_journal.py` (modified): Persist the exit policy and classify the pilot's decision outcomes.
  - `kite_config.json` (modified): Enable the forward paper pilot with a 15-bar lookback and 2R target; live orders remain disabled.
  - `kite_config.example.json` (modified): Keep the pilot disabled by default.
  - `tests/test_intraday_manager.py` (modified): Cover breakout detection, range stop/2R sizing, fixed target handling, live-mode exclusion, and decision classification.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the pilot and the October 14 replay limits.
- October 14 ICICIBANK 1360 PE counterfactual: Earlier breakouts at 09:39 and 09:41 exceed the configured one-lot premium-risk cap. First candle-volume/risk-qualified break is 10:01: close ₹26.20 above prior-15 high ₹26.00; prior-15 low ₹24.15 gives stop ₹24.10 and 2R target ₹30.40. The 13:03 candle reached ₹30.50. At the archived 700-unit lot, the target-touch estimate is +₹2,940 gross before costs. This is an OHLC estimate; quote freshness, spread, sequencing, and actual fill are unavailable.
- Validation: Focused `test_intraday_manager.py` and `test_paper_reporting.py` passed (77 passed); changed Python files have no Pylance problems or syntax errors; active/example configuration JSON and `git diff --check` passed. The unfiltered suite reported 193 passed, 1 skipped, and 1 unrelated fixture failure in `test_on_tick_stores_timestamp_required_by_option_quality_gate` (`test_kite_provider.py`): its manually constructed bot omits `paper_trading_enabled`, which `_on_tick` reads. The suite excluding that test passed (193 passed, 1 skipped, 1 deselected).
- Outcome / follow-up: The replay shows the rule could enter this one contract earlier and model a positive gross result, but one contract/session does not establish profitability. Continue a paper-only forward sample; live orders remain disabled.

#### DLY-2026-10-14-07

- Reason: Add a breakout-candle participation check to the separate paper-only 15-bar option breakout pilot after the historical replay showed failed breakouts on zero-volume candles.
- Related entries checked: `DLY-2026-10-14-06` / `EXP-2026-10-14-03` (paper breakout pilot and single-contract counterfactual); `EXP-2026-10-14-04` (volume-confirmation experiment and replay results).
- Change: Require the breakout candle to have positive volume at least equal to the mean volume of the preceding 15 completed candles. This applies only to the paper range-breakout path; entry trigger, contract selection, stop/target, sizing, legacy behavior, and live-order controls are unchanged. Invalid or negative volume data fails closed.
- Files:
  - `market_bot/kite_main.py` (modified): Apply the breakout-candle volume check and record a specific rejection reason.
  - `tests/test_intraday_manager.py` (modified): Cover a passing candle at the prior-volume average and rejection of below-average and zero-volume breakouts.
  - `BREAKOUT_HISTORICAL_REPLAY_REPORT.md` (added): Preserve the three-session baseline and end-to-end volume-filter replay, including per-session outcomes and methodology.
  - `STRATEGY_CHANGELOG.md` (modified): Record the controlled paper experiment, aggregate and per-session results, rollback, and limitations as `EXP-2026-10-14-04`.
- Historical finding: Across October 7, 8, and 14, the end-to-end replay modeled gross P/L of +INR 7,873.00 with the filter versus +INR 1,436.75 baseline (40 versus 37 trades). The filtered result remained negative on October 7 (-INR 8,499.00); only three sessions were available.
- Validation: Added focused breakout-volume acceptance/rejection cases; `git diff --check` passed.
- Limitations / avoid: This is in-sample evidence from the same three sessions used to motivate the filter, not an independent test or proof of a durable edge. The replay uses candle OHLC, excludes fees, spread, slippage, latency, and partial fills, and cannot establish executable returns. Do not promote the filter beyond paper trading or infer profitability from the positive aggregate.
- Follow-up: Keep live orders disabled. Track separately tagged paper breakout acceptances/rejections and closed trades over a predeclared, unseen forward sample; compare gross and cost-adjusted outcomes before reconsidering the rule.

#### DLY-2026-10-15-01

- Reason: Add an R-based trailing exit policy for paper option trades, building on the separate range-breakout pilot's need for exits that can follow favorable premium moves.
- Related entries checked: `DLY-2026-10-14-06` / `EXP-2026-10-14-03` (paper option range-breakout pilot); `DLY-2026-10-14-07` / `EXP-2026-10-14-04` (breakout-candle volume confirmation). Their replay results are not evidence for this distinct exit policy.
- Files:
  - `market_bot/intraday_manager.py` (modified): Track runner activation and high/low-water state; activate after a favorable 1R move and ratchet the stop at a 2R gap, never loosening past the initial stop.
  - `market_bot/kite_main.py` (modified): Apply the runner to paper CE/PE entries only when paper trading is active and live orders are disabled; bypass staged targets, the reference target/timebox, and reversal exits for runner positions. The normal market-close exit remains.
  - `market_bot/trade_journal.py` (modified): Persist runner state with open paper trades.
  - `market_bot/weekly_report.py` (modified): Report closed-trade results grouped by the runner exit strategy.
  - `kite_config.json` and `kite_config.example.json` (modified): Set runner activation to 1R and trailing gap to 2R.
  - `tests/test_intraday_manager.py` and `tests/test_paper_reporting.py` (modified): Cover runner activation, ratcheting, persistence, exit handling, and report grouping.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record this change and its evidence status.
- Validation: The focused VS Code test runner first returned “No tests found”; rerunning through the project venv with `python -m pytest -q tests\test_intraday_manager.py tests\test_paper_reporting.py` passed (86 tests). `git diff --check` passed before this log entry was added.
- Outcome / follow-up: This is an implemented paper-only exit experiment, not a measured improvement. No historical replay or prospective closed-trade outcome for this exit policy is recorded yet. Keep live orders disabled; track runner trades separately and evaluate at least the existing 10-closed-paper-trade screening minimum, with transaction costs where available.

### 2026-10-16

#### DLY-2026-10-16-01

- Reason: Record the completed breakout-confirmation replay of recorded and hypothetical entries, and preserve its evidence limits for future strategy decisions.
- Related prior entries checked: `DLY-2026-10-14-06` / `EXP-2026-10-14-03` (paper range-breakout pilot); `DLY-2026-10-14-07` / `EXP-2026-10-14-04` (breakout volume confirmation); `DLY-2026-10-15-01` / `EXP-2026-10-15-01` (paper trailing-exit experiment).
- Files:
  - `DAILY_CHANGELOG.md` (modified): Record replay method, results, and caveats.
  - `STRATEGY_CHANGELOG.md` (modified): Add the breakout confirmation replay as an inconclusive experiment.
- Replay results: For Oct 15–16, the direction-confirmation scenario returned ₹5,534.75 gross and the direction-plus-delayed-close scenario returned ₹8,134.00 gross; cutoff-matched recorded P&L was ₹4,183.75 and existing-path candle replay was ₹4,018.50. Both proposed scenarios selected 14 entries and Oct 16 remained negative. Hypothetical entries contributed -₹404.75 and -₹992.25, respectively.
- Validation: Confirmed candidate-level CSV exists and checked replay totals against the recorded summary. No code or configuration behavior changed.
- Outcome / follow-up / rollback: Exploratory two-session replay only, not a validated edge. Results exclude fees, spread, slippage, portfolio concurrency, and recalculated circuit-breaker state. Continue paper observation with realistic costs and a larger out-of-sample period; do not enable the filters based on this replay alone. Detailed rows and rejection reasons are in `paper_trading_data/backtests/breakout_filters_all_logged_candidates_2026-10-14_to_2026-10-16.csv`.

### 2026-10-19

#### DLY-2026-10-19-01

- Reason: The user requested a concrete paper-strategy improvement using the uploaded historical data and prior strategy/change logs.
- Related entries checked: `EXP-2026-10-14-03` / `EXP-2026-10-14-04` (15-bar range breakout and breakout-volume gate); `EXP-2026-10-15-01` (adaptive paper option exits); `EXP-2026-10-16-01` (direction and delayed-close replay).
- Historical evidence: The October 15-16 replay used the uploaded minute options/underlying candles and covered 703 logged candidates. Direction-only selected 14 trades for ₹5,534.75 gross; direction plus one-minute follow-through selected 14 (9 recorded and 5 hypothetical) for ₹8,134 gross, a ₹2,599.25 uplift in this two-session sample. The combined scenario was +₹10,486.25 on October 15 and -₹2,352.25 on October 16; the five hypothetical entries contributed -₹992.25. A coarse ₹40/trade round-trip brokerage estimate reduces combined gross to ₹7,574, before spread, slippage, taxes, or portfolio-concurrency effects. This is not cost-adjusted proof of an edge and does not produce positive P&L every day.
- October 19 finding: The seven recorded option trades netted -₹455 before unmodeled costs. Four initial stop-loss exits lost ₹2,851.25; three trailing-stop winners made ₹2,396.25. The records showed the range-breakout variant using the generic adaptive exit even though the range-breakout pilot was specified as fixed stop/2R.
- October 19 candle check: Compared those entries with the exact-contract daily option candles and corresponding underlying candles under `data_uploads/kite_daily/2026-10-19/`. Minute bars did not reproduce every tick-time entry/quote exactly, so this was not used to claim a precise counterfactual P&L; it supports testing a completed-bar confirmation but cannot validate the resulting strategy.
- Changes:
  - `market_bot/kite_main.py` (modified): Add a configurable one-completed-bar follow-through check to the paper-only range-breakout path. The active setting requires the confirmation close and entry quote to remain above the original 15-bar range high; breakout volume is still checked on the breakout bar. Ensure the range-breakout exit plan uses its specified fixed 2R target rather than inheriting the adaptive exit enabled for other paper options.
  - `kite_config.json` (modified): Enable one follow-through confirmation bar for the active paper breakout pilot. Live orders remain disabled.
  - `kite_config.example.json` (modified): Document the confirmation setting while keeping the breakout pilot disabled by default.
  - `tests/test_intraday_manager.py` (modified): Cover confirmed and rejected follow-throughs and ensure adaptive settings do not override the breakout's fixed 2R exit.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the active one-bar confirmation and distinct fixed exit policy.
  - `DAILY_CHANGELOG.md` and `STRATEGY_CHANGELOG.md` (modified): Record evidence, limitations, and rollback guidance.
- Validation: `python -m pytest -q tests\test_intraday_manager.py` passed (95 tests); the full suite passed (221 passed, 1 skipped); `python -m compileall -q market_bot tests`, configuration JSON parsing, and `git diff --check` passed.
- Decision / limitation: This is a reversible paper-only trial, not a promise of daily profits or live authorization. The two-session replay combines direction agreement with delayed confirmation and includes hypothetical trades; it does not isolate all interactions or model executable bid/ask fills. Keep live orders disabled. To roll back the entry filter, set `paper_option_range_confirmation_bars` to `0`; retain the fixed 2R exit for this separately defined variant.
