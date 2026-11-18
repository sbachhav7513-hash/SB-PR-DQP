# 17-Nov-2026 read-only equivalence replay

## Result

**FAIL - equivalence not demonstrated.** The current-code replay with the three new gates OFF produced 9,940 records (9,868 bar decisions and 72 confirmation events), versus 10,563 original parquet rows. It opened **0 trades** versus 5 original entries. The replay is not a sign-off-quality reconstruction: the local 17-Nov VPS JSONL is missing, the current replay harness does not seed active contract metadata, and the archive replay reconstructs callback timing from minute OHLC rather than exact original ticks.

## Step 1 - original data inventory

- Source: `paper_trading_data/2026-11/week_47/day_17/decisions/decisions_*.parquet` (8 shards).
- Rows: **10,563** (expected 10,563).
- Earliest/latest values in the parquet `timestamp` column, normalized to IST: **2026-11-17T08:52:25+05:30** / **2026-11-17T15:30:22+05:30**.
- Actions: **HOLD 9,730 / MARKET_CLOSE 412 / BUY 281 / SELL 140** (all requested counts match).
- Local JSONL search: root `decision_log.jsonl` contains only 2026-10-28/29 re-entry rows; `sim/decision_log.jsonl` contains 2026-11-01 rows. No 2026-11-17 VPS `decision_log.jsonl` copy was found.
- Therefore the requested 20-random-row parquet-vs-JSONL spot check **could not be done**, and JSONL-only fields cannot be enumerated from another date's log.
- Archived inputs exist: 18 compressed option quote files (23,076 rows), 18 option candle files (5,984 rows), and 9 underlying candle files (3,582 rows).

### Parquet columns

- `timestamp`
- `config_hash`
- `git_sha`
- `git_dirty`
- `ticker`
- `contract_id`
- `strike`
- `expiry`
- `lot_size`
- `underlying_price_at_selection`
- `signal`
- `outcome`
- `score`
- `reasons`
- `bars_available`
- `bar`
- `history`
- `outcome_detail`
- `rejection_reason`
- `market_session`
- `market_hours`
- `session_timezone`
- `trend_shadow_signal`
- `trend_shadow_rejection_reason`
- `strategy_variant`
- `entry_evaluation`
- `event`
- `ema_reentry_event`
- `original_trade_id`
- `stop_time`
- `reentry_signal_time`
- `reentry_reason`
- `reentry_vwap`
- `reentry_entry_price`
- `reentry_exit_price`
- `reentry_pnl`
- `reentry_outcome`
- `confirmation_event`
- `signal_id`
- `signal_uid`
- `entry_feature_values`
- `entry_feature_null_reasons`
- `order_time`
- `entry_mode`
- `route`
- `scorer_first_bar_time`
- `scorer_last_bar_time`
- `scorer_last_bar_ohlc`
- `scorer_last_bar_complete`
- `scorer_inputs`
- `score_components`
- `component_score`
- `gate_passed_at`
- `gate_state`
- `gate_state_v2`
- `gate_state_v2_changes`
- `gate_state_v2_full`
- `gate_state_v2_by_direction`
- `gate_state_v2_by_option_leg`
- `gate_state_v2_account_by_symbol`
- `gate_state_v2_warmup`
- `support_reversal_timing`
- `scorer_bar_payload`
- `signal_time`
- `signal_close`
- `signal_bar`
- `signal_premium`
- `signal_bid`
- `signal_ask`
- `signal_ltp`
- `signal_quote_age_seconds`
- `quote_source`
- `quote_age_seconds`
- `candle_age_seconds`
- `option_token`
- `last_tick_time`
- `tick_gap_seconds`
- `daily_tick_gaps_over_30s`
- `paper_change_flags`
- `paper_change_attributions`
- `body_ratio`
- `body_ratio_threshold`
- `paper_change_gate_evaluations`
- `would_pass_baseline`
- `body_ratio_source`
- `atr_pct`
- `effective_volatility_threshold_pct`
- `momentum_candle`
- `momentum_body_ratio`
- `momentum_body_ratio_threshold`
- `direction_rule`
- `active_paper_change_attributions`
- `confirmation_candle_time`
- `confirmation_close`
- `confirmation_result`
- `confirmation_delay_seconds`
- `confirmation_body_ratio`
- `confirmation_body_ratio_threshold`
- `confirmation_momentum_candle`
- `confirmation_momentum_body_ratio`
- `confirmation_momentum_body_ratio_threshold`
- `confirmation_bid`
- `confirmation_ask`
- `confirmation_ltp`
- `confirmation_quote_age_seconds`
- `order_premium`
- `order_bid`
- `order_ask`
- `order_ltp`
- `order_quote_age_seconds`
- `cancellation_reason`
- `cancellation_sub_reason`
- `filter_name`
- `support_resistance_level`
- `support_resistance_touches`
- `ema_fast_value`
- `ema_slow_value`
- `invested_amount`
- `lots`
- `quantity`
- `risk_amount`
- `risk_cap_rupees`
- `tier`
- `premium`
- `option_stop_pct`
- `proposed_invested_amount`
- `proposed_lots`
- `proposed_risk_amount`
- `max_capital_per_trade_pct`
- `max_capital_per_trade_amount`
- `banknifty_max_capital_per_trade_pct`
- `banknifty_max_capital_per_trade_amount`
- `max_capital_per_trade_used_pct`
- `max_capital_per_trade_used_amount`
- `max_open_risk_pct`
- `max_open_risk_amount`
- `open_risk_amount`
- `remaining_daily_risk_amount`
- `max_risk_per_trade_ignored`
- `max_lots`
- `premium_cap`
- `lots_reduced_reason`
- `capital_based_risk_v2`

### Input completeness assessment

The parquet includes useful per-decision diagnostics: `signal_bid/ask/ltp` and quote-age/source fields; `bar`, `history`, scorer inputs/components; v2 gate snapshots; rejection/cancellation reasons; and confirmation/order quote snapshots. Counts show `bar` on 10,493 rows, `history` on 6,634, `scorer_inputs` on 6,178, `gate_state_v2` on 10,493, `gate_state_v2_full` on 27, and directional/option-leg v2 gate snapshots on 3,582 each. The legacy `gate_state` column is blank on all rows. Rejection reasons are populated where applicable (292 `rejection_reason`, 15 `cancellation_sub_reason`).

The parquet is not a standalone exact replay fixture: the original VPS JSONL is absent, `india_vix` is not a parquet column and no VIX archive was found, and the exact underlying tick-arrival sequence is not in the decision parquet. The archived quotes/candles provide market inputs, but differences from the original run cannot be attributed conclusively without the VPS log.

## Step 2 - replay setup

- Ran current `KiteTradingBot._on_tick` in PAPER simulation; used archived quote and candle inputs, not the fixed stop/target simulator.
- Reconstructed minute OHLC callback points from archived underlying and option candles, combined with archived option quote ticks. A runtime-only historical clock was used so session-bar filtering treated inputs as Nov 17. No repository code/config/data was edited.
- New flags in the generated scratch simulation config: `tier_risk_counters_v1=false`, `symbol_side_stop_breaker_v1=false`, `same_side_cluster_limit_v1=false`; `stock_tier_enabled_v1=true`.
- No `/exitat` was injected. The original NIFTY_CE manual exit is excluded; its entry remains part of the five-entry baseline.

## Step 3 - criteria

| Criterion | Result | Evidence |
|---|---|---|
| a) Same action for all 10,563 decisions | **FAIL** | Replay: 9,940 rows; HOLD 9,139 / BUY 239 / SELL 151 / MARKET_CLOSE 411. Only 9,480 rows could be paired by event + symbol + minute bucket; 166 paired actions differ, 1,083 source rows have no same-minute replay row, and 460 replay rows have no same-minute source row. Exact timestamp/event/symbol overlap is 726. |
| b) Same five entries, timestamps, instruments, lots, prices | **FAIL** | Current replay opened 0 trades; baseline has the five entries below. |
| c) Same 33 signals / 20 confirmed / 5 trades / 15 blocked with exact reasons | **FAIL** | Baseline: 33 signal IDs, 20 passed confirmation, 13 failed confirmation, 15 post-confirmation filters (8 stale quote, 5 run-up veto, 2 max-open-risk), 5 trades. Replay: 36 signal IDs, 19 passed, 17 failed, 19 post-confirmation failures (all `instrument`), 0 trades. |
| d) Only differences are telemetry fields and stale_quote label rename | **FAIL** | There are action, reason, and timestamp differences beyond the allowed rename. The full row-level mismatch table contains 10,632 rows. |

### Original five entries (manual exit excluded)

| Original entry time (IST) | Instrument / lots | Contract | Entry price |
|---|---|---|---:|
| 2026-11-17 10:40:25.403337 | INFY_PE x3 | NFO:INFY26NOV1140PE | 16.30 |
| 2026-11-17 11:09:24.652838 | INFY_CE x2 | NFO:INFY26NOV1140CE | 20.10 |
| 2026-11-17 13:42:40.414732 | NIFTY_CE x1 | NFO:NIFTY26NOV25300CE | 265.15 |
| 2026-11-17 13:44:24.405269 | INFY_CE x3 | NFO:INFY26NOV1140CE | 14.45 |
| 2026-11-17 14:04:25.147124 | LT_CE x1 | NFO:LT26NOV4150CE | 73.15 |

In the replay, 19 signals passed confirmation but were then blocked as `instrument`. This is consistent with the harness not seeding active contract-symbol metadata: `tools/benchmark_gate_state_replay.py::_tick_replay` builds token mappings, while `market_bot/kite_main.py::_confirmed_entry_filter_failure` also requires the symbol to be in the stream's `contract_symbols` and active option-leg state. This is the likely direct cause of zero simulated entries; it is not evidence that the five entries were behaviorally evaluated correctly.

### Mismatch table

Every same-minute paired mismatch, missing source row, and replay-only row is in [`decision_mismatches.csv`](./decision_mismatches.csv). It includes original/replay timestamps, symbol, event, action/reason, mismatch type, and likely cause. Mismatch classes:

| Mismatch type | Rows |
|---|---:|
| `timestamp` | 6198 |
| `missing_in_replay` | 1083 |
| `action+reason+timestamp` | 139 |
| `unexpected_in_replay` | 460 |
| `reason+timestamp` | 2460 |
| `reason` | 265 |
| `action+reason` | 27 |

Minute alignment was used for candidate pairing because reconstructed callback timestamps differ from original timestamps. Exact timestamp matches are reported separately above; this timing difference itself is recorded in the CSV.

## Step 4 - requested findings

- Pivot telemetry on all five current entries: **not demonstrated**; there were no current replay entries. The original day review reports pivot fields empty on 0/5 entries.
- VIX non-null: **No** - 0/9,940 replay records have non-null `india_vix`; no VIX input archive was available.
- Decisions that could not be replayed one-to-one: source has 10,493 `bar_decision`, 66 `entry_confirmation`, and 4 `ema_stop_reentry` events; replay has 9,868 `bar_decision` and 72 `entry_confirmation`, with no `ema_stop_reentry`. This leaves 625 fewer bar decisions, 4 missing re-entry events, and 6 extra confirmations (net 623 fewer rows). Candidate decisions also differ in actions/reasons as detailed in the CSV.
- Optional tier-risk-counters-ON replay: **skipped** because Step 3 did not pass. `tier_risk_counters_v1` is implemented and default OFF.
- Worktree: no code/config/source-data modifications. All generated files are under `tmp/equiv_1117/`.

## Output artifacts

- [`equivalence_metrics.json`](./equivalence_metrics.json)
- [`decision_mismatches.csv`](./decision_mismatches.csv)
- Replay outputs: `replay_clocked/` (all scratch-only)
