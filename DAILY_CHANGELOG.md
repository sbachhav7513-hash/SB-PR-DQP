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

- Reason: Daily close currently writes aggregate counts/P&L, while human-readable filter and shadow-candidate diagnostics are only available through a weekly review or manual analysis.
- Related prior entries checked: `DLY-2026-09-30-02` and `DLY-2026-09-30-03`; this is a reporting-only change and does not alter entry or risk behavior.
- Files:
  - `market_bot/weekly_report.py` (modified): Add an exact-date Markdown report for closed-trade outcomes, signal/rejection counts, HOLD reasons, and shadow flow.
  - `market_bot/kite_main.py` (modified): Generate the daily review alongside the existing close summary.
  - `tests/test_paper_reporting.py` (modified): Verify the report counts trade results and rejection/shadow reasons.
  - `DAILY_WEEKLY_OPERATIONS.md` (modified): Document the new daily report artifact and contents.
  - `DAILY_CHANGELOG.md` (modified): Record this change.
- Validation and result: Focused Parquet-backed daily-review test passed; `python -m pytest -q` passed (`121 passed`); Pylance reported no diagnostics in `weekly_report.py` or `test_paper_reporting.py`; `kite_main.py` has two unrelated existing warnings; `git diff --check` passed.
- Outcome / follow-up / rollback: Reporting-only; no strategy performance claim. Inspect the daily report after each session and change at most one paper-only strategy/filter variable per experiment.

#### DLY-2026-09-30-05

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