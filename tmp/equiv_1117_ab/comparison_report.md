# 17-Nov-2026 OLD-vs-NEW equivalence replay

## Revisions and inputs

- OLD: `3ba2d4a17809265f3374590d2f00c1890bef7288`
- NEW: `4b8a3dcc4315298489def70044cf812ed5bea3f3`
- NEW flags: `tier_risk_counters_v1=false`, `symbol_side_stop_breaker_v1=false`, `same_side_cluster_limit_v1=false`, `stock_tier_enabled_v1=true`.
- Both runs used the same archived option quotes/candles and underlying candles. Contract IDs/exchanges were seeded in the scratch-only harness; lot sizes came from the decision parquet.
- The parquet supplied contract metadata only; OLD and NEW regenerated decisions from the tick/candle inputs rather than replaying parquet action rows directly.
- There is no local VPS `decision_log.jsonl` for 17-Nov, so the parquet-vs-JSONL spot check was not done.

## Results

| Comparison | Result | Evidence |
|---|---|---|
| Actions and reasons on rows emitted by both replays | **PASS, limited scope** | All 9,539 paired decision rows match action, outcome, and reason. Counts in both: HOLD 8,855; MARKET_CLOSE 396; BUY 159; SELL 129. |
| Rejected-signal parity | **FAIL** | 3,835 records per run; one signal's classification differs beyond the permitted reason rename (table below). |
| OLD vs NEW opened trades | **PASS** | Both opened one identical entry: INFY_CE, 2026-11-17 13:41:05 IST, `NFO:INFY26NOV1140CE`, 3 lots, entry 14.10. |
| OLD vs the original five entries | **FAIL** | OLD did not reproduce the five expected entries; it opened only the INFY_CE x3 entry above. |
| Full decision-row coverage | **FAIL / incomplete** | The source parquet has 10,563 total rows, including 10,493 `bar_decision` rows. Each replay emitted 9,539—954 fewer than the source bar-decision count. The row PASS above is only OLD-vs-NEW; baseline row keys were not matched one-to-one. |

### Rejection mismatch

| Timestamp | Symbol | Action | OLD reason / detail | NEW reason / detail | Likely cause |
|---|---|---|---|---|---|
| 2026-11-17 10:38:05 IST | INFY_PE | SELL | `stale_quote` / `stale_quote` | `quote_outside_spread` / `other_filter` | `kite_main.py` now emits `quote_outside_spread`; `trade_journal.py`'s `normalize_entry_confirmation_detail` recognizes stale-quote labels but not the new label, so the detail falls through to `other_filter`. |

### Entry telemetry and exclusions

- The only replayed entry has empty pivot telemetry (`entry_pivot_count` and `support_reclaim_result`); it does not establish pivot population for the five original entries, which were not reproduced.
- VIX is null on the replayed entry.
- Entry sizing telemetry also differs: OLD's `entry_feature_values.risk_cap` is 1,000; NEW's is 4,000, while NEW's top-level `risk_cap_rupees` is empty. This is outside the requested trade-identity comparison and is not one of the listed allowed field additions.
- The manual `/exitat` on NIFTY_CE was not synthesized; it is excluded from both runs.
- The optional tier-risk-counters-ON replay was skipped because the equivalence checks did not pass.

## Files

- [comparison_summary.json](./comparison_summary.json)
- [decision_mismatches.csv](./decision_mismatches.csv)
- [mismatch_table.csv](./mismatch_table.csv)
