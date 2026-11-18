# PAPER-mode pending items: implementation and validation

## Status

- Branch: `feat/paper-mode-pending-items`
- Base commit: `4b8a3dcc4315298489def70044cf812ed5bea3f3`
- No deployment or commit was made. Both new behavior flags remain OFF.
- `tmp/` is pre-existing untracked replay data and was not changed.

## Changes delivered

- T1: `quote_outside_spread` now normalizes to the same entry-confirmation detail instead of `other_filter`; a unit test covers it.
- T2: entry decisions record run-up status and fail-open cause; the daily review counts statuses and causes. The opt-in historical backfill uses asynchronous work and leaves the existing 8.0% threshold unchanged.
- T3: the opt-in 5-minute continuation gate is in the PAPER confirmed-entry flow. It waits for the aligned complete candle, revalidates the existing entry filters, uses a fresh quote, logs continuation and ask-drift fields, and journals rejected outcomes. `entry_5m_max_ask_drift_pct` is recorded but not applied.
- T4: the daily review includes runtime identity, flags, per-tier performance, run-up fail-open counts, and 5-minute outcomes. Empty `risk_cap_rupees` is handled; the 4,000 value is labeled as an open-risk limit.

### New PAPER controls

| Setting | Default | Rollback |
| --- | --- | --- |
| `run_up_lookback_backfill_v2` | `false` | Set this flag to `false` |
| `entry_5m_continuation_v1` | `false` | Set this flag to `false` |
| `entry_5m_max_ask_drift_pct` | `null` | Informational only; no drift limit is applied |

Startup logging reports the runtime flag values and commit SHA. Daily reviews persist the commit SHA, normalized config hash, and flag state.

## T2: archived lookback completeness

The archive contains 51 trades from 30-Oct through 16-Nov and five 17-Nov entries. Of the 51 earlier trades, 25 lack a complete 61-close lookback; the five 17-Nov entries have persisted complete 60-minute values.

| Classification | Count | Share of 56 entries | Evidence |
| --- | ---: | ---: | --- |
| (a) Before 61 session closes are available | 7 | 12.5% | Early-session entries, approximately 09:30–10:16 |
| (b) Missing minute | Not separately recoverable | Included in 18 unknown | Archived records lack a cause for the incomplete window |
| (c) Unmapped/new contract token | Not separately recoverable | Included in 18 unknown | Same limitation |
| (d) Bar-builder/read error | Not separately recoverable | Included in 18 unknown | Same limitation |
| (e) Warm-up after restart | Not separately recoverable | Included in 18 unknown | Same limitation |
| Incomplete, cause among (b)–(e) unknown | 18 | 32.1% | Cannot be split from the available archived metadata |
| Complete lookback | 31 | 55.4% | 26 of the original 51 plus all five 17-Nov entries |

Thus, the archive does **not** support the requested distinct counts for causes (b)–(e); those counts must not be interpreted as zero. For the seven early-session cases, an archive-limited calculation using available closes since the open was possible for three: SBIN `-0.8989%`, LT `-2.2919%`, and HDFCBANK_PE `+1.7921%`. None reaches the unchanged 8.0% threshold. Four cases did not have a usable archived partial window.

No archived historical-API backfill comparison was available, so the 0.10 percentage-point / 95% acceptance criterion and veto-flip count remain unverified. Provider behavior is covered with mocked tests only; no API call or credentials were used.

## T1 and OLD-vs-NEW parity

The 17-Nov signal at 10:38:05 IST (`INFY_PE SELL`) is journaled at its 10:40:05 confirmation event. Its detail was `other_filter` in baseline 4b8 and is now `quote_outside_spread`. The earlier 3ba-vs-4b comparison still has the raw reason rename `stale_quote` → `quote_outside_spread`; that rename predates this change and is not changed here.

For the required flags-OFF comparison against commit `4b8a3dcc4315298489def70044cf812ed5bea3f3`:

- All 9,549 paired rows have matching keys; action and reason fields are identical.
- Both runs produced the same single opened trade: INFY_CE, 13:41:05 IST, `NFO:INFY26NOV1140CE`, quantity 1,200, entry 14.10.
- Other differences are telemetry (`signal_uid`, gate-evaluation/run-up fields) plus the requested `outcome_detail` normalization for the INFY_PE signal. The confirmation-detail correction is the only semantic label change.

The archived OLD-vs-NEW harness report compares 3ba to 4b and has narrower source coverage: 9,539 paired bar decisions, one opened trade, and one raw rejection-reason rename. It does not reproduce the original five expected entries. See [the archived comparison report](./tmp/equiv_1117_ab/comparison_report.md).

## T3: paired replay and gaps

The archived 51-trade sample uses `entry_mode=confirmed` and covers `support_reversal` (46), `scored` (4), and `ema_reentry` (1). It does not cover immediate/range-breakout entries. The historical paired replay figures are reproduced in [the replay report](./PAPER_RUN_UP_AND_5M_REPLAY_2026-10-30_to_2026-11-16.md), but that offline simulator starts its candle window at signal time; it is not an end-to-end replay of the new bot path.

| Sample | Baseline mean net R | 5m mean net R | n | 5m outcomes noted |
| --- | ---: | ---: | ---: | --- |
| 30-Oct–11-Nov | 0.2028 | 0.1682 | 33 | 16 non-continuations; 1 incomplete |
| 12-Nov–16-Nov | -0.4653 | -0.0690 | 17 | 10 non-continuations; none incomplete |
| 51 trades, without best trade | -0.0723 | 0.0894 | 49 | Best baseline trade excluded from both arms |
| 17-Nov, exact runtime assembler | — | Not an R comparison | 5 signals | 0 pass; 0 fail; 0 expired; 5 data_missing |
| 17-Nov, legacy replay window | — | Not an R comparison | 5 signals | 2 pass; both stop out (legacy acceptance figure) |

The legacy replay starts from signal time and is not the runtime path. An earlier offline confirmation-aligned analysis reported 3/5 on 17-Nov, but it did not use the exact runtime assembler; the strict replay below supersedes it and finds 5/5 data_missing because the archived minute bars are offset from clock boundaries. The required 2-of-5 result is therefore not reproduced, and the archive does not demonstrate live-path outcome parity.

The evaluation rule is not met or failed yet: the flag is OFF and there are no executed flag-ON trades/sessions to evaluate. Keep it OFF pending a correctly aligned replay and the required minimum live-paper sample.

## Validation

- Focused suite: **89 passed** (confirmed-entry, decision journal, replay, reporting, run-up, and runtime isolation tests).
- Full suite: **661 passed, 1 skipped, 1 failed**. The failure is `tests/test_scorer_observability.py::test_selected_option_legs_evaluate_candle_quote_risk_and_capital_gates`; its `SimpleNamespace` fixture lacks `available_daily_risk`. The call site is present in baseline commit 4b8 (`git blame`); the failing test and fixture were not changed.
- `git diff --check`: passed.
- Reporting tests cover empty `risk_cap_rupees` and assert the 4,000 value is labeled `risk/open-risk limit`.

The remaining evidence gaps are the distinct T2 (b)–(e) cause counts, historical backfill accuracy/flip counts, full original-five-entry parity, and T3’s confirmation-aligned 17-Nov replay. No new behavior flag should be enabled until these gaps are addressed and the stated acceptance criteria pass.

## Follow-up verification (18-Nov-2026)

### Scorer fixture on a clean baseline

The failing test was run from a separate detached, clean worktree at
`4b8a3dcc4315298489def70044cf812ed5bea3f3`:

- Result: **FAIL**, same `AttributeError: 'types.SimpleNamespace' object has no attribute 'available_daily_risk'`.
- The baseline implementation already calls `manager.available_daily_risk()` in `_option_bar_gate_measurements`; the fixture supplies no such method. The scorer test and that call site were unchanged by this branch. This is a baseline test-fixture failure, not a regression from the PAPER changes.

### Implemented confirmation-aligned replay

The 51 archived trades were replayed against the same 10%-stop / 20%-target fixed simulator, but the variant used the current implementation’s clock-window calculation: confirmation candle timestamp plus one minute for the confirmation close, then the next clock-aligned 5-minute start, and an exact set of five minute-bar timestamps. The variant fails closed when those five bars are unavailable.

All 51 signals reached the pending 5-minute stage. **None** formed a complete aligned candle from the archived one-minute timestamps: all archive bar timestamps have nonzero seconds (for example `10:10:18`), while the implementation requests exact clock starts such as `10:10:00`. Consequently, all 51 variant outcomes are `data_missing`; there were no passes, failures, expiries, or variant fills. Variant means are therefore **N/A**, not zero. This demonstrates that the archived data cannot validate continuation outcomes and that the flag must remain OFF.

| Period / sample | Reached | Passed | Failed | Expired | Data missing | Baseline fills | Baseline mean net R | Baseline mean net ₹ | Baseline total net ₹ | Implemented fills / mean net R / mean net ₹ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 30-Oct–11-Nov | 34 | 0 | 0 | 0 | 34 | 34 | 0.1660 | 261.67 | 8,896.81 | 0 / N/A / N/A |
| 12-Nov–16-Nov | 17 | 0 | 0 | 0 | 17 | 17 | -0.4653 | -820.36 | -13,946.04 | 0 / N/A / N/A |
| All 51 | 51 | 0 | 0 | 0 | 51 | 51 | -0.0444 | -99.00 | -5,049.23 | 0 / N/A / N/A |
| All 51, excluding the best baseline trade | 50 | 0 | 0 | 0 | 50 | 50 | -0.0918 | -171.46 | -8,572.88 | 0 / N/A / N/A |
| 30-Oct–11-Nov, excluding best | 33 | 0 | 0 | 0 | 33 | 33 | 0.1006 | 162.82 | 5,373.17 | 0 / N/A / N/A |
| 12-Nov–16-Nov, excluding best | 17 | 0 | 0 | 0 | 17 | 17 | -0.4653 | -820.36 | -13,946.04 | 0 / N/A / N/A |

The excluded best baseline trade is `LT_CE-2026-11-09T10:04:22.638133+05:30-BUY`. The older legacy paired replay’s 30-Oct–11-Nov baseline mean (0.2028) used only 33 paired trades; the complete baseline-only cohort here contains 34 trades. Its reported no-best pair (49 trades) is likewise not comparable to the 50-trade baseline-only no-best figure above.

In the list below, every implemented status is `data_missing`; each difference is caused by **candle alignment/timing**, not by a different reference close. Both replays use the recorded `confirmation_close`. Legacy windows start at `signal_time` and preserve the archive’s sub-minute offset; the implemented window is clock-aligned and therefore has no exact five-bar match. The one legacy-incomplete case is listed too because its specific reason changes to the implementation’s `data_missing`.

| Trade | Legacy result | Implemented result | Reason |
| --- | --- | --- | --- |
| NIFTY_PE-2026-10-30T10:07:21.189181+05:30-BUY | pass | data_missing | candle alignment/timing |
| RELIANCE_CE-2026-11-03T09:58:37.552708+05:30-BUY | pass | data_missing | candle alignment/timing |
| HDFCBANK_CE-2026-11-03T13:00:31.294452+05:30-BUY | fail | data_missing | candle alignment/timing |
| INFY_CE-2026-11-03T13:26:35.553817+05:30-BUY | pass | data_missing | candle alignment/timing |
| LT_PE-2026-11-04T10:19:50.401341+05:30-BUY | fail | data_missing | candle alignment/timing |
| RELIANCE_CE-2026-11-04T12:27:49.645890+05:30-BUY | pass | data_missing | candle alignment/timing |
| SBIN_CE-2026-11-04T13:19:49.413291+05:30-BUY | pass | data_missing | candle alignment/timing |
| TCS_CE-2026-11-04T14:25:53.154906+05:30-BUY | pass | data_missing | candle alignment/timing |
| HDFCBANK_CE-2026-11-05T11:31:03.340974+05:30-BUY | pass | data_missing | candle alignment/timing |
| RELIANCE_CE-2026-11-05T13:43:03.335864+05:30-BUY | fail | data_missing | candle alignment/timing |
| LT_PE-2026-11-05T14:22:08.089786+05:30-BUY | fail | data_missing | candle alignment/timing |
| SBIN_CE-2026-11-06T10:05:04.001399+05:30-BUY | incomplete | data_missing | candle alignment/timing; reason label differs |
| NIFTY_PE-2026-11-06T10:41:37.273817+05:30-BUY | fail | data_missing | candle alignment/timing |
| HDFCBANK_PE-2026-11-06T10:41:37.464399+05:30-BUY | fail | data_missing | candle alignment/timing |
| TCS_PE-2026-11-06T10:53:36.280612+05:30-BUY | pass | data_missing | candle alignment/timing |
| INFY_PE-2026-11-06T10:55:37.279923+05:30-BUY | pass | data_missing | candle alignment/timing |
| INFY_CE-2026-11-06T11:48:38.033746+05:30-BUY | fail | data_missing | candle alignment/timing |
| BANKNIFTY_CE-2026-11-06T12:11:37.532648+05:30-BUY | pass | data_missing | candle alignment/timing |
| LT_CE-2026-11-06T13:16:34.530139+05:30-BUY | pass | data_missing | candle alignment/timing |
| TCS_CE-2026-11-06T13:16:36.537440+05:30-BUY | pass | data_missing | candle alignment/timing |
| INFY_CE-2026-11-06T14:33:37.782767+05:30-BUY | fail | data_missing | candle alignment/timing |
| LT_CE-2026-11-09T10:04:22.638133+05:30-BUY | fail | data_missing | candle alignment/timing |
| ICICIBANK_PE-2026-11-09T10:36:22.341814+05:30-BUY | fail | data_missing | candle alignment/timing |
| RELIANCE_CE-2026-11-09T11:28:22.855071+05:30-BUY | pass | data_missing | candle alignment/timing |
| TCS_PE-2026-11-09T12:16:22.846458+05:30-BUY | pass | data_missing | candle alignment/timing |
| INFY_CE-2026-11-09T12:51:24.338410+05:30-BUY | fail | data_missing | candle alignment/timing |
| BANKNIFTY_PE-2026-11-09T13:16:57.381000+05:30-BUY | fail | data_missing | candle alignment/timing |
| TCS_CE-2026-11-09T13:59:23.086457+05:30-BUY | fail | data_missing | candle alignment/timing |
| HDFCBANK_CE-2026-11-11T11:33:05.261555+05:30-BUY | pass | data_missing | candle alignment/timing |
| TCS_PE-2026-11-11T12:06:05.294871+05:30-BUY | pass | data_missing | candle alignment/timing |
| LT_PE-2026-11-11T13:39:05.480164+05:30-BUY | pass | data_missing | candle alignment/timing |
| RELIANCE_PE-2026-11-11T13:41:05.981460+05:30-BUY | fail | data_missing | candle alignment/timing |
| INFY_CE-2026-11-11T14:01:05.495244+05:30-BUY | fail | data_missing | candle alignment/timing |
| BANKNIFTY_PE-2026-11-11T14:21:21.479640+05:30-BUY | fail | data_missing | candle alignment/timing |
| HDFCBANK_PE-2026-11-12T10:11:04.590286+05:30-BUY | fail | data_missing | candle alignment/timing |
| BANKNIFTY_PE-2026-11-12T10:27:19.572005+05:30-BUY | fail | data_missing | candle alignment/timing |
| HDFCBANK_CE-2026-11-12T10:48:04.318098+05:30-BUY | fail | data_missing | candle alignment/timing |
| ICICIBANK_PE-2026-11-12T12:06:04.624825+05:30-BUY | pass | data_missing | candle alignment/timing |
| RELIANCE_CE-2026-11-12T12:49:04.584964+05:30-BUY | pass | data_missing | candle alignment/timing |
| LT_CE-2026-11-12T13:09:06.550071+05:30-BUY | pass | data_missing | candle alignment/timing |
| RELIANCE_CE-2026-11-13T10:07:14.146387+05:30-BUY | pass | data_missing | candle alignment/timing |
| HDFCBANK_PE-2026-11-13T10:12:13.629137+05:30-BUY | fail | data_missing | candle alignment/timing |
| INFY_CE-2026-11-13T10:35:15.396028+05:30-BUY | fail | data_missing | candle alignment/timing |
| BANKNIFTY_CE-2026-11-13T10:50:29.411239+05:30-BUY | fail | data_missing | candle alignment/timing |
| TCS_PE-2026-11-16T10:25:13.642973+05:30-BUY | pass | data_missing | candle alignment/timing |
| NIFTY_PE-2026-11-16T10:31:49.833340+05:30-BUY | pass | data_missing | candle alignment/timing |
| BANKNIFTY_PE-2026-11-16T10:31:50.201800+05:30-BUY | pass | data_missing | candle alignment/timing |
| RELIANCE_PE-2026-11-16T10:35:14.102813+05:30-BUY | fail | data_missing | candle alignment/timing |
| RELIANCE_PE-2026-11-16T11:21:13.795869+05:30-BUY | fail | data_missing | candle alignment/timing |
| TCS_CE-2026-11-16T12:16:13.670355+05:30-BUY | fail | data_missing | candle alignment/timing |
| INFY_PE-2026-11-16T12:53:13.327157+05:30-BUY | fail | data_missing | candle alignment/timing |

### Parity row-count clarification

The earlier `9,539` count included only `bar_decision` rows. The later exact-key comparison also included 10 `entry_confirmation` telemetry rows, so it counted `9,539 + 10 = 9,549` rows. Both the baseline 4b replay and the flags-OFF worktree emitted 9,539 bar decisions plus the same 10 confirmation events; no bar-decision rows were added.

## Follow-up correction — clock-aligned 5-minute gate (18-Nov-2026)

This follow-up starts from branch commit `78afb45` and supersedes the
confirmation-aligned replay assumptions and results above. It does not rewrite
the historical entries.

### Production timestamp and window behavior

`BarBuilder.process_tick` in `market_bot/bar_builder.py` timestamps each
completed one-minute bar with its interval's stored `bar_start`, set from the
first tick in that interval. It is not stamped with the closing tick time.
Consequently, a completed 10:09 bar can be stamped `10:09:18`; the next
interval is still clock-aligned at the minute level.

`_complete_five_minute_bar` in `market_bot/kite_main.py` now selects the five
clock-minute buckets represented by timestamps in `[HH:MM:00, HH:MM+5:00)`,
ignoring seconds and microseconds when identifying each bucket. The window end
is exclusive; all five buckets must exist. Open comes from the first minute
bar and close from the fifth. The pending-entry path waits for the completed
final-minute bar before evaluating the candle. CE and PE continuation checks
remain strict inequalities.

Three consecutive `data_missing` continuation outcomes now disable
`entry_5m_continuation_v1` for the rest of the IST session date. The trip logs
`five_min_autodisabled`, is stored on the triggering decision, and is counted
in the daily review. The daily decision journal restores the streak/tripped
state after process restart. The config flag remains false by default and is
not changed by the breaker.

### Corrected paired replay

The fixed rule was replayed on the 51-trade sample with the same baseline and
variant exit model. All reported means are after fees; failed continuation
signals contribute a zero-R variant outcome, and this run had no data-missing
outcomes.

| Period | Reached | Passed | Failed | Expired | Data missing | Baseline mean net R / ₹ | Variant mean net R / ₹ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30-Oct to 11-Nov | 34 | 19 | 15 | 0 | 0 | 0.1660 / 261.6707 | -0.0823 / -84.7654 |
| 12-Nov to 16-Nov | 17 | 6 | 11 | 0 | 0 | -0.4653 / -820.3553 | -0.1753 / -274.0812 |
| All 51 | 51 | 25 | 26 | 0 | 0 | -0.0444 / -99.0046 | -0.1133 / -147.8707 |

Without the best baseline trade (`LT_CE`, 9-Nov), the all-51 baseline is
n=50, **-0.0918 R / -171.4575 ₹**, and the paired variant is
n=50, **-0.1155 R / -150.8281 ₹**. The earlier paired baseline (-0.0723 R,
n=49) omitted `SBIN_CE` on 6-Nov because the old replay marked its five-minute
window incomplete. Under the corrected clock-window it has all five bars,
fails the continuation check, and contributes its baseline -1.0485 R; this
produces the reconciled n=50 baseline.

The 17-Nov underlying and option archives do contain usable candle/quote
records; the prior statement that option candles were unavailable was
incorrect. The same fixed-rule replay reached 5, passed 3, failed 2, expired
0, and had 0 data-missing outcomes. Baseline mean net was -1.0673 R /
-1766.1820 ₹; variant mean net was -0.6671 R / -1040.8070 ₹. Excluding the
best baseline trade (`INFY_CE`, 13:44), n=4 baseline was -1.1142 R /
-1826.3400 ₹ and variant was -0.8339 R / -1301.0087 ₹. This five-trade
follow-up is descriptive, not evidence of an edge. Full per-period and
trade-level outputs are in
[the regenerated replay report](./PAPER_RUN_UP_AND_5M_REPLAY_2026-10-30_to-2026-11-16.md).

### Validation and operations

- Focused regression tests: **78 passed**.
- Full suite: **667 passed, 1 skipped**.
- The scorer-observability test fixture now supplies `available_daily_risk`;
  this resolves the previously documented fixture-only failure.
- `entry_5m_continuation_v1` remains false. Deployment steps are documented in
  `DAILY_WEEKLY_OPERATIONS.md`; no merge, push, or deployment is authorized by
  this follow-up.
- OLD-vs-NEW flags-OFF parity is to be rerun against the final committed SHA
  and recorded as post-commit evidence.
