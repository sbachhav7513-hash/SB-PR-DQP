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