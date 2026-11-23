# Daily Paper-Trading Review - 2026-11-23

## Results
- Closed trades: 0
- Wins / losses / breakeven: 0 / 0 / 0
- Gross recorded P&L before modeled fees: 0.00
- Win rate: 0.0%
- Decisions: 1187

## Runtime Identity and Flags
- Commit SHA: ea1c264e54ea7460dfb7bd0587583716b252e266
- Normalized config hash: 93d9165ecaca7f52eb6256bfc879a417755d3e5850a2b3e66779d0dea7a95dfc
- Flags: allow_trend_continuation=True, auto_discover_futures=False, banknifty_caps_v2=True, capital_based_risk_v2=True, capture_all_evaluated_contracts=True, ema_reentry_enabled=False, entry_5m_continuation_v1=False, entry_5m_max_ask_drift_pct=None, entry_feature_logging_v2=True, extend_option_timebox=True, gate_state_logging_v1=True, hard_context_filter=True, index_persistence_pass=True, late_window_enabled=False, level_stop_v2=False, live_orders_confirmed=False, news_enabled=False, nifty_range_gate_v1=False, nifty_vol_floor_v2=True, option_adaptive_exit_enabled=True, option_candle_momentum=True, option_premium_rising_momentum_v2=True, option_quote_validated_stops_enabled=True, option_range_breakout_enabled=False, partial_profit_v2=True, premarket_context_v1=True, premium_floor_v2=True, profit_lock_v2=True, reversal_confirm_v2=False, run_up_lookback_backfill_v2=False, run_up_veto_v2=True, runner_gap_v2=True, same_side_cluster_limit_v1=False, scorer_input_logging_v1=True, staged_option_targets_enabled=True, stale_quote_candle_fallback=True, stock_open_risk_share=1.0, stock_take_profit_v2=True, stock_tier_enabled_v1=False, stop_quote_validation_v2=True, stop_reentry_enabled=False, support_reversal_enabled=False, support_reversal_levels_diagnostics_v1=True, symbol_side_stop_breaker_v1=False, tier_risk_counters_v1=False, trail_close_confirm_v2=True, trailing_enabled=True, use_market_context=True

## Modeled Fees and Net Performance
- Gross P&L: 0.00
- Modeled fees: unavailable (0/0 trades)
- Net P&L: unavailable (0/0 trades)
- Human command affected at least one trade: no
- All fee figures are modeled from the configured paper charge model.

| Dimension | Group | Trades | Gross P&L | Modeled fees | Net P&L | R total | Average R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No closed trades | - | 0 | 0.00 | N/A | N/A | N/A | N/A |

## Per-tier Results

| Tier | Trades | Gross | Modeled fees | Net | Wins | Mean net R | Mean net R without best trade |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| STOCK | 0 | 0.00 | N/A | N/A | 0 | N/A | N/A |
| NIFTY | 0 | 0.00 | N/A | N/A | 0 | N/A | N/A |
| BANKNIFTY | 0 | 0.00 | N/A | N/A | 0 | N/A | N/A |
| STOCK (cumulative) | 132 | -15009.36 | 2436.36 (28/132) | -16673.86 (28/132) | 11 | -0.290 | -0.351 |

## One-Candle Entry Confirmation
- Signals generated: 0
- Direction confirmed: 0
- Rejected by confirmation (CE / PE): 0 / 0
- Filter failures after confirmation: {}
- Expired signals: 0
- Confirmed trades: 0
- Win rate: 0.0%
- Gross recorded P&L: 0.00
- After-cost P&L: unavailable (trade journal has no after-cost field)
- Average delay: 0.0s
- Average premium change from signal to fill: 0.000%

## Run-up Veto Status Counts
- passed: 0
- vetoed: 0
- failed_open: 0

## Run-up Veto Fail-Open Counts
- None recorded

## 5-minute Entry Continuation by Tier

| Tier | Reached | Passed | Failed | Expired | Data missing |
| --- | ---: | ---: | ---: | ---: | ---: |
| STOCK | 0 | 0 | 0 | 0 | 0 |
| NIFTY | 0 | 0 | 0 | 0 | 0 |
| BANKNIFTY | 0 | 0 | 0 | 0 | 0 |
- five_min_autodisabled: 0

## NIFTY Range Gate
- Blocked by tier (STOCK): 0
- Blocked by tier (NIFTY): 0
- Blocked by tier (BANKNIFTY): 0
- Data missing: 0

| Entry time | Symbol | Side | Tier | NIFTY range-so-far (%) |
| --- | --- | --- | --- | ---: |
| No gate-enabled entries recorded | - | - | - | - |

## EMA Stop-Loss Re-entry
- Eligible stop-loss trades: 0
- Confirmed signals: 0
- Windows expired without a signal: 0
- Signal entries rejected by other gates: 0
- Re-entries closed: 0
- Re-entry wins / losses / breakeven: 0 / 0 / 0
- Re-entry P&L: 0.00
- Baseline P&L: 0.00; with re-entries: 0.00

### Re-entry Trade Log
| Original trade ID | Symbol | Stop time | Signal time | Reason | Entry | Exit | P&L | Outcome |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |
| No re-entry trades recorded | - | - | - | - | - | - | 0.00 | - |

## Signals
- HOLD: 1142
- MARKET_CLOSE: 45

## Entry Flow
- BUY/SELL signals: 0
- Unselected option-leg skips: 0
- Side-eligible directional candidates: 0
- Entries opened: 0

## Outcomes
- hold: 684
- operational: 503
- trade_opened: 0

## Closed Trades
| Symbol | Direction | Variant | Score | Held (s) | P&L | Exit | Manual | Flags at entry → exit | Signal/order/fill premium | Fill bid/ask/LTP/age | Fill Δ% | Trigger price/source | Capture |
| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | ---: | --- | --- |
| No closed trades | - | - | - | - | 0.00 | - | - | - | - | - | - | - | - |

## Entry Features
- No closed trades.

## Stop-out recovery

Option R uses initial per-unit risk and one-minute option OHLC; checkpoint bids are the nearest valid archived quote after exit to each checkpoint, with quote age and sample offset shown. Underlying reversal means the captured one-minute range crossed the entry-time underlying reference against the option direction.

| Trade | Exit type | Entry→exit seconds | ≤5m | Bid @ 5m | Bid @ 15m | Bid @ 30m | Bid @ 60m | Max/min R 60m | Max/min R close | Reclaimed entry | Reached +1R | Underlying reversed | Capture |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| No initial-stop, trailing-stop, or breakeven exits | - | - | - | - | - | - | - | - | - | - | - | - | - |

## Paper exit flag results

| Flag | Tagged trades (W/L/BE) | Tagged P&L | Untagged trades (W/L/BE) | Untagged P&L |
| --- | ---: | ---: | ---: | ---: |
| runner_gap_v2 | 0 (0/0/0) | 0.00 | 0 (0/0/0) | 0.00 |
| profit_lock_v2 | 0 (0/0/0) | 0.00 | 0 (0/0/0) | 0.00 |
| trail_close_confirm_v2 | 0 (0/0/0) | 0.00 | 0 (0/0/0) | 0.00 |
| partial_profit_v2 | 0 (0/0/0) | 0.00 | 0 (0/0/0) | 0.00 |
| stop_quote_validation_v2 | 0 (0/0/0) | 0.00 | 0 (0/0/0) | 0.00 |
| stock_take_profit_v2 | 0 (0/0/0) | 0.00 | 0 (0/0/0) | 0.00 |

## Paper exit flag rollback checks

| Flag | Tagged trades | Threshold checks | Status |
| --- | ---: | --- | --- |
| runner_gap_v2 | 42 | runner_drawdowns=0 closed_trade_sessions=5/5; risk_overruns=0 days_at_or_below_-6000=0 | no rollback trigger |
| profit_lock_v2 | 42 | risk_overruns=0 days_at_or_below_-6000=0; first_ten_old_rule_better=0 paired=10/10 missing=0 tagged=42/10 | no rollback trigger |
| trail_close_confirm_v2 | 42 | risk_overruns=0 days_at_or_below_-6000=0; first_ten_old_rule_better=0 paired=10/10 missing=0 tagged=42/10 | no rollback trigger |
| partial_profit_v2 | 35 | executed=0 accounting_errors=0 duplicate_partials=0 days_at_daily_loss_limit=0; first_ten_partial_off_better=0 paired=0/10 missing=0 eligible=0/10 | no rollback trigger |
| stop_quote_validation_v2 | 35 | exit_fill_gap_rupees=0.2406; exit_fill_gap_pct=0.4674; guarded_quotes=0; fills_more_than_3pct_below_stop=2 | trade HDFCBANK_PE-2026-11-13T10:12:13.629137+05:30-BUY filled more than 3% below its stop trigger |
| stock_take_profit_v2 | 28 | take_profit_exits=5 fill_minus_trigger_gap_avg=0.2024; capped_winner_exits_bid_more_than_0.5R_within_30m=3 quote_missing=0; tagged_daily_loss=2026-11-11:655.00, 2026-11-12:-792.50, 2026-11-13:-1772.50, 2026-11-16:-7035.00, 2026-11-17:-3866.25, 2026-11-18:-3132.50, 2026-11-19:918.75, 2026-11-20:787.50 days_at_limit=1; first_ten_paired_stock_pnl_delta_avg=NA paired=0/10 missing=10 eligible=28/10 | stock_take_profit_v2 tagged daily loss reached INR 6000.00 on 2026-11-16 (P&L -7035.00) |

## Learning Feedback
- Status: no_closed_trades (0/10 closed trades for the minimum screening sample).
- No closed-trade outcomes are available; keep collecting paper evidence. No strategy settings are changed automatically.
- No repeated losing exit pattern (at least two losses) in this sample.
- These patterns are descriptive, not causal; paper P&L excludes unmodeled brokerage, taxes, and slippage.
- No strategy or configuration settings are changed automatically.

### Entry Rejections
- None recorded

## HOLD Reasons
- underlying_context_only: 400
- not_enough_bars: 58
- EMA bearish: 56
- Price near recent low: 56
- RSI in trend zone: 56
- MACD weakening: 32
- Trend momentum present: 22
- EMA bullish: 12
- Price near recent high: 12
- MACD improving: 8
- RSI oversold against SELL: 8
- ADX too weak (10.8 < 11.0): 4
- ADX too weak (9.2 < 11.0): 4
- Sideways regime: recent range 0.093% < 0.300% and 20-bar move 0.142% < 0.250%: 4
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.087% < 0.250%: 4
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.153% < 0.250%: 4
- ADX too weak (10.7 < 11.0): 2
- ADX too weak (10.9 < 11.0): 2
- ADX too weak (11.0 < 11.0): 2
- ADX too weak (9.6 < 11.0): 2
- Sideways regime: recent range 0.024% < 0.300% and 20-bar move 0.130% < 0.250%: 2
- Sideways regime: recent range 0.041% < 0.300% and 20-bar move 0.098% < 0.250%: 2
- Sideways regime: recent range 0.044% < 0.300% and 20-bar move 0.124% < 0.250%: 2
- Sideways regime: recent range 0.045% < 0.300% and 20-bar move 0.048% < 0.250%: 2
- Sideways regime: recent range 0.045% < 0.300% and 20-bar move 0.090% < 0.250%: 2
- Sideways regime: recent range 0.045% < 0.300% and 20-bar move 0.102% < 0.250%: 2
- Sideways regime: recent range 0.046% < 0.300% and 20-bar move 0.100% < 0.250%: 2
- Sideways regime: recent range 0.046% < 0.300% and 20-bar move 0.159% < 0.250%: 2
- Sideways regime: recent range 0.048% < 0.300% and 20-bar move 0.132% < 0.250%: 2
- Sideways regime: recent range 0.050% < 0.300% and 20-bar move 0.005% < 0.250%: 2
- Sideways regime: recent range 0.050% < 0.300% and 20-bar move 0.047% < 0.250%: 2
- Sideways regime: recent range 0.050% < 0.300% and 20-bar move 0.072% < 0.250%: 2
- Sideways regime: recent range 0.050% < 0.300% and 20-bar move 0.085% < 0.250%: 2
- Sideways regime: recent range 0.050% < 0.300% and 20-bar move 0.093% < 0.250%: 2
- Sideways regime: recent range 0.051% < 0.300% and 20-bar move 0.022% < 0.250%: 2
- Sideways regime: recent range 0.051% < 0.300% and 20-bar move 0.026% < 0.250%: 2
- Sideways regime: recent range 0.051% < 0.300% and 20-bar move 0.043% < 0.250%: 2
- Sideways regime: recent range 0.051% < 0.300% and 20-bar move 0.097% < 0.250%: 2
- Sideways regime: recent range 0.051% < 0.300% and 20-bar move 0.101% < 0.250%: 2
- Sideways regime: recent range 0.052% < 0.300% and 20-bar move 0.104% < 0.250%: 2
- Sideways regime: recent range 0.052% < 0.300% and 20-bar move 0.177% < 0.250%: 2
- Sideways regime: recent range 0.053% < 0.300% and 20-bar move 0.191% < 0.250%: 2
- Sideways regime: recent range 0.055% < 0.300% and 20-bar move 0.018% < 0.250%: 2
- Sideways regime: recent range 0.055% < 0.300% and 20-bar move 0.028% < 0.250%: 2
- Sideways regime: recent range 0.055% < 0.300% and 20-bar move 0.033% < 0.250%: 2
- Sideways regime: recent range 0.055% < 0.300% and 20-bar move 0.062% < 0.250%: 2
- Sideways regime: recent range 0.055% < 0.300% and 20-bar move 0.096% < 0.250%: 2
- Sideways regime: recent range 0.058% < 0.300% and 20-bar move 0.033% < 0.250%: 2
- Sideways regime: recent range 0.058% < 0.300% and 20-bar move 0.056% < 0.250%: 2
- Sideways regime: recent range 0.058% < 0.300% and 20-bar move 0.061% < 0.250%: 2
- Sideways regime: recent range 0.058% < 0.300% and 20-bar move 0.065% < 0.250%: 2
- Sideways regime: recent range 0.059% < 0.300% and 20-bar move 0.018% < 0.250%: 2
- Sideways regime: recent range 0.059% < 0.300% and 20-bar move 0.130% < 0.250%: 2
- Sideways regime: recent range 0.059% < 0.300% and 20-bar move 0.139% < 0.250%: 2
- Sideways regime: recent range 0.060% < 0.300% and 20-bar move 0.186% < 0.250%: 2
- Sideways regime: recent range 0.061% < 0.300% and 20-bar move 0.020% < 0.250%: 2
- Sideways regime: recent range 0.061% < 0.300% and 20-bar move 0.044% < 0.250%: 2
- Sideways regime: recent range 0.061% < 0.300% and 20-bar move 0.206% < 0.250%: 2
- Sideways regime: recent range 0.062% < 0.300% and 20-bar move 0.020% < 0.250%: 2
- Sideways regime: recent range 0.062% < 0.300% and 20-bar move 0.041% < 0.250%: 2
- Sideways regime: recent range 0.062% < 0.300% and 20-bar move 0.117% < 0.250%: 2
- Sideways regime: recent range 0.062% < 0.300% and 20-bar move 0.119% < 0.250%: 2
- Sideways regime: recent range 0.062% < 0.300% and 20-bar move 0.134% < 0.250%: 2
- Sideways regime: recent range 0.063% < 0.300% and 20-bar move 0.045% < 0.250%: 2
- Sideways regime: recent range 0.063% < 0.300% and 20-bar move 0.055% < 0.250%: 2
- Sideways regime: recent range 0.063% < 0.300% and 20-bar move 0.060% < 0.250%: 2
- Sideways regime: recent range 0.063% < 0.300% and 20-bar move 0.124% < 0.250%: 2
- Sideways regime: recent range 0.064% < 0.300% and 20-bar move 0.005% < 0.250%: 2
- Sideways regime: recent range 0.064% < 0.300% and 20-bar move 0.055% < 0.250%: 2
- Sideways regime: recent range 0.064% < 0.300% and 20-bar move 0.062% < 0.250%: 2
- Sideways regime: recent range 0.064% < 0.300% and 20-bar move 0.117% < 0.250%: 2
- Sideways regime: recent range 0.064% < 0.300% and 20-bar move 0.147% < 0.250%: 2
- Sideways regime: recent range 0.064% < 0.300% and 20-bar move 0.148% < 0.250%: 2
- Sideways regime: recent range 0.065% < 0.300% and 20-bar move 0.028% < 0.250%: 2
- Sideways regime: recent range 0.065% < 0.300% and 20-bar move 0.047% < 0.250%: 2
- Sideways regime: recent range 0.065% < 0.300% and 20-bar move 0.057% < 0.250%: 2
- Sideways regime: recent range 0.065% < 0.300% and 20-bar move 0.077% < 0.250%: 2
- Sideways regime: recent range 0.065% < 0.300% and 20-bar move 0.082% < 0.250%: 2
- Sideways regime: recent range 0.065% < 0.300% and 20-bar move 0.109% < 0.250%: 2
- Sideways regime: recent range 0.066% < 0.300% and 20-bar move 0.112% < 0.250%: 2
- Sideways regime: recent range 0.067% < 0.300% and 20-bar move 0.056% < 0.250%: 2
- Sideways regime: recent range 0.067% < 0.300% and 20-bar move 0.079% < 0.250%: 2
- Sideways regime: recent range 0.068% < 0.300% and 20-bar move 0.006% < 0.250%: 2
- Sideways regime: recent range 0.068% < 0.300% and 20-bar move 0.015% < 0.250%: 2
- Sideways regime: recent range 0.069% < 0.300% and 20-bar move 0.029% < 0.250%: 2
- Sideways regime: recent range 0.069% < 0.300% and 20-bar move 0.115% < 0.250%: 2
- Sideways regime: recent range 0.071% < 0.300% and 20-bar move 0.039% < 0.250%: 2
- Sideways regime: recent range 0.071% < 0.300% and 20-bar move 0.045% < 0.250%: 2
- Sideways regime: recent range 0.071% < 0.300% and 20-bar move 0.103% < 0.250%: 2
- Sideways regime: recent range 0.072% < 0.300% and 20-bar move 0.006% < 0.250%: 2
- Sideways regime: recent range 0.072% < 0.300% and 20-bar move 0.033% < 0.250%: 2
- Sideways regime: recent range 0.073% < 0.300% and 20-bar move 0.022% < 0.250%: 2
- Sideways regime: recent range 0.075% < 0.300% and 20-bar move 0.008% < 0.250%: 2
- Sideways regime: recent range 0.075% < 0.300% and 20-bar move 0.019% < 0.250%: 2
- Sideways regime: recent range 0.075% < 0.300% and 20-bar move 0.029% < 0.250%: 2
- Sideways regime: recent range 0.075% < 0.300% and 20-bar move 0.048% < 0.250%: 2
- Sideways regime: recent range 0.076% < 0.300% and 20-bar move 0.058% < 0.250%: 2
- Sideways regime: recent range 0.076% < 0.300% and 20-bar move 0.112% < 0.250%: 2
- Sideways regime: recent range 0.076% < 0.300% and 20-bar move 0.159% < 0.250%: 2
- Sideways regime: recent range 0.077% < 0.300% and 20-bar move 0.245% < 0.250%: 2
- Sideways regime: recent range 0.078% < 0.300% and 20-bar move 0.054% < 0.250%: 2
- Sideways regime: recent range 0.078% < 0.300% and 20-bar move 0.075% < 0.250%: 2
- Sideways regime: recent range 0.078% < 0.300% and 20-bar move 0.084% < 0.250%: 2
- Sideways regime: recent range 0.079% < 0.300% and 20-bar move 0.148% < 0.250%: 2
- Sideways regime: recent range 0.079% < 0.300% and 20-bar move 0.164% < 0.250%: 2
- Sideways regime: recent range 0.080% < 0.300% and 20-bar move 0.043% < 0.250%: 2
- Sideways regime: recent range 0.080% < 0.300% and 20-bar move 0.242% < 0.250%: 2
- Sideways regime: recent range 0.081% < 0.300% and 20-bar move 0.022% < 0.250%: 2
- Sideways regime: recent range 0.081% < 0.300% and 20-bar move 0.237% < 0.250%: 2
- Sideways regime: recent range 0.082% < 0.300% and 20-bar move 0.047% < 0.250%: 2
- Sideways regime: recent range 0.082% < 0.300% and 20-bar move 0.166% < 0.250%: 2
- Sideways regime: recent range 0.083% < 0.300% and 20-bar move 0.017% < 0.250%: 2
- Sideways regime: recent range 0.083% < 0.300% and 20-bar move 0.053% < 0.250%: 2
- Sideways regime: recent range 0.083% < 0.300% and 20-bar move 0.207% < 0.250%: 2
- Sideways regime: recent range 0.084% < 0.300% and 20-bar move 0.012% < 0.250%: 2
- Sideways regime: recent range 0.084% < 0.300% and 20-bar move 0.024% < 0.250%: 2
- Sideways regime: recent range 0.084% < 0.300% and 20-bar move 0.112% < 0.250%: 2
- Sideways regime: recent range 0.084% < 0.300% and 20-bar move 0.171% < 0.250%: 2
- Sideways regime: recent range 0.085% < 0.300% and 20-bar move 0.037% < 0.250%: 2
- Sideways regime: recent range 0.085% < 0.300% and 20-bar move 0.056% < 0.250%: 2
- Sideways regime: recent range 0.086% < 0.300% and 20-bar move 0.041% < 0.250%: 2
- Sideways regime: recent range 0.086% < 0.300% and 20-bar move 0.091% < 0.250%: 2
- Sideways regime: recent range 0.087% < 0.300% and 20-bar move 0.016% < 0.250%: 2
- Sideways regime: recent range 0.087% < 0.300% and 20-bar move 0.100% < 0.250%: 2
- Sideways regime: recent range 0.087% < 0.300% and 20-bar move 0.112% < 0.250%: 2
- Sideways regime: recent range 0.087% < 0.300% and 20-bar move 0.148% < 0.250%: 2
- Sideways regime: recent range 0.088% < 0.300% and 20-bar move 0.092% < 0.250%: 2
- Sideways regime: recent range 0.088% < 0.300% and 20-bar move 0.138% < 0.250%: 2
- Sideways regime: recent range 0.088% < 0.300% and 20-bar move 0.214% < 0.250%: 2
- Sideways regime: recent range 0.089% < 0.300% and 20-bar move 0.032% < 0.250%: 2
- Sideways regime: recent range 0.089% < 0.300% and 20-bar move 0.039% < 0.250%: 2
- Sideways regime: recent range 0.089% < 0.300% and 20-bar move 0.103% < 0.250%: 2
- Sideways regime: recent range 0.089% < 0.300% and 20-bar move 0.111% < 0.250%: 2
- Sideways regime: recent range 0.089% < 0.300% and 20-bar move 0.157% < 0.250%: 2
- Sideways regime: recent range 0.090% < 0.300% and 20-bar move 0.014% < 0.250%: 2
- Sideways regime: recent range 0.090% < 0.300% and 20-bar move 0.113% < 0.250%: 2
- Sideways regime: recent range 0.090% < 0.300% and 20-bar move 0.123% < 0.250%: 2
- Sideways regime: recent range 0.090% < 0.300% and 20-bar move 0.227% < 0.250%: 2
- Sideways regime: recent range 0.092% < 0.300% and 20-bar move 0.028% < 0.250%: 2
- Sideways regime: recent range 0.092% < 0.300% and 20-bar move 0.070% < 0.250%: 2
- Sideways regime: recent range 0.092% < 0.300% and 20-bar move 0.075% < 0.250%: 2
- Sideways regime: recent range 0.092% < 0.300% and 20-bar move 0.175% < 0.250%: 2
- Sideways regime: recent range 0.092% < 0.300% and 20-bar move 0.190% < 0.250%: 2
- Sideways regime: recent range 0.093% < 0.300% and 20-bar move 0.002% < 0.250%: 2
- Sideways regime: recent range 0.093% < 0.300% and 20-bar move 0.025% < 0.250%: 2
- Sideways regime: recent range 0.093% < 0.300% and 20-bar move 0.071% < 0.250%: 2
- Sideways regime: recent range 0.093% < 0.300% and 20-bar move 0.083% < 0.250%: 2
- Sideways regime: recent range 0.093% < 0.300% and 20-bar move 0.086% < 0.250%: 2
- Sideways regime: recent range 0.093% < 0.300% and 20-bar move 0.092% < 0.250%: 2
- Sideways regime: recent range 0.093% < 0.300% and 20-bar move 0.110% < 0.250%: 2
- Sideways regime: recent range 0.094% < 0.300% and 20-bar move 0.001% < 0.250%: 2
- Sideways regime: recent range 0.094% < 0.300% and 20-bar move 0.035% < 0.250%: 2
- Sideways regime: recent range 0.094% < 0.300% and 20-bar move 0.048% < 0.250%: 2
- Sideways regime: recent range 0.094% < 0.300% and 20-bar move 0.145% < 0.250%: 2
- Sideways regime: recent range 0.094% < 0.300% and 20-bar move 0.216% < 0.250%: 2
- Sideways regime: recent range 0.094% < 0.300% and 20-bar move 0.244% < 0.250%: 2
- Sideways regime: recent range 0.096% < 0.300% and 20-bar move 0.115% < 0.250%: 2
- Sideways regime: recent range 0.097% < 0.300% and 20-bar move 0.014% < 0.250%: 2
- Sideways regime: recent range 0.097% < 0.300% and 20-bar move 0.039% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.018% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.032% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.051% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.063% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.071% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.075% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.085% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.117% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.121% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.126% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.174% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.183% < 0.250%: 2
- Sideways regime: recent range 0.099% < 0.300% and 20-bar move 0.239% < 0.250%: 2
- Sideways regime: recent range 0.101% < 0.300% and 20-bar move 0.044% < 0.250%: 2
- Sideways regime: recent range 0.101% < 0.300% and 20-bar move 0.108% < 0.250%: 2
- Sideways regime: recent range 0.101% < 0.300% and 20-bar move 0.156% < 0.250%: 2
- Sideways regime: recent range 0.101% < 0.300% and 20-bar move 0.191% < 0.250%: 2
- Sideways regime: recent range 0.101% < 0.300% and 20-bar move 0.192% < 0.250%: 2
- Sideways regime: recent range 0.103% < 0.300% and 20-bar move 0.009% < 0.250%: 2
- Sideways regime: recent range 0.103% < 0.300% and 20-bar move 0.022% < 0.250%: 2
- Sideways regime: recent range 0.103% < 0.300% and 20-bar move 0.080% < 0.250%: 2
- Sideways regime: recent range 0.103% < 0.300% and 20-bar move 0.081% < 0.250%: 2
- Sideways regime: recent range 0.103% < 0.300% and 20-bar move 0.120% < 0.250%: 2
- Sideways regime: recent range 0.103% < 0.300% and 20-bar move 0.159% < 0.250%: 2
- Sideways regime: recent range 0.103% < 0.300% and 20-bar move 0.195% < 0.250%: 2
- Sideways regime: recent range 0.104% < 0.300% and 20-bar move 0.041% < 0.250%: 2
- Sideways regime: recent range 0.105% < 0.300% and 20-bar move 0.002% < 0.250%: 2
- Sideways regime: recent range 0.105% < 0.300% and 20-bar move 0.022% < 0.250%: 2
- Sideways regime: recent range 0.105% < 0.300% and 20-bar move 0.026% < 0.250%: 2
- Sideways regime: recent range 0.105% < 0.300% and 20-bar move 0.035% < 0.250%: 2
- Sideways regime: recent range 0.105% < 0.300% and 20-bar move 0.247% < 0.250%: 2
- Sideways regime: recent range 0.107% < 0.300% and 20-bar move 0.055% < 0.250%: 2
- Sideways regime: recent range 0.108% < 0.300% and 20-bar move 0.011% < 0.250%: 2
- Sideways regime: recent range 0.108% < 0.300% and 20-bar move 0.179% < 0.250%: 2
- Sideways regime: recent range 0.108% < 0.300% and 20-bar move 0.192% < 0.250%: 2
- Sideways regime: recent range 0.108% < 0.300% and 20-bar move 0.211% < 0.250%: 2
- Sideways regime: recent range 0.109% < 0.300% and 20-bar move 0.190% < 0.250%: 2
- Sideways regime: recent range 0.110% < 0.300% and 20-bar move 0.106% < 0.250%: 2
- Sideways regime: recent range 0.110% < 0.300% and 20-bar move 0.145% < 0.250%: 2
- Sideways regime: recent range 0.110% < 0.300% and 20-bar move 0.150% < 0.250%: 2
- Sideways regime: recent range 0.110% < 0.300% and 20-bar move 0.163% < 0.250%: 2
- Sideways regime: recent range 0.112% < 0.300% and 20-bar move 0.032% < 0.250%: 2
- Sideways regime: recent range 0.112% < 0.300% and 20-bar move 0.209% < 0.250%: 2
- Sideways regime: recent range 0.113% < 0.300% and 20-bar move 0.136% < 0.250%: 2
- Sideways regime: recent range 0.114% < 0.300% and 20-bar move 0.197% < 0.250%: 2
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.009% < 0.250%: 2
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.010% < 0.250%: 2
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.036% < 0.250%: 2
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.058% < 0.250%: 2
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.085% < 0.250%: 2
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.099% < 0.250%: 2
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.104% < 0.250%: 2
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.118% < 0.250%: 2
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.121% < 0.250%: 2
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.149% < 0.250%: 2
- Sideways regime: recent range 0.116% < 0.300% and 20-bar move 0.183% < 0.250%: 2
- Sideways regime: recent range 0.117% < 0.300% and 20-bar move 0.100% < 0.250%: 2
- Sideways regime: recent range 0.118% < 0.300% and 20-bar move 0.073% < 0.250%: 2
- Sideways regime: recent range 0.120% < 0.300% and 20-bar move 0.171% < 0.250%: 2
- Sideways regime: recent range 0.120% < 0.300% and 20-bar move 0.208% < 0.250%: 2
- Sideways regime: recent range 0.125% < 0.300% and 20-bar move 0.021% < 0.250%: 2
- Sideways regime: recent range 0.126% < 0.300% and 20-bar move 0.093% < 0.250%: 2
- Sideways regime: recent range 0.126% < 0.300% and 20-bar move 0.245% < 0.250%: 2
- Sideways regime: recent range 0.127% < 0.300% and 20-bar move 0.189% < 0.250%: 2
- Sideways regime: recent range 0.128% < 0.300% and 20-bar move 0.140% < 0.250%: 2
- Sideways regime: recent range 0.129% < 0.300% and 20-bar move 0.167% < 0.250%: 2
- Sideways regime: recent range 0.130% < 0.300% and 20-bar move 0.172% < 0.250%: 2
- Sideways regime: recent range 0.135% < 0.300% and 20-bar move 0.035% < 0.250%: 2
- Sideways regime: recent range 0.135% < 0.300% and 20-bar move 0.074% < 0.250%: 2
- Sideways regime: recent range 0.135% < 0.300% and 20-bar move 0.102% < 0.250%: 2
- Sideways regime: recent range 0.135% < 0.300% and 20-bar move 0.213% < 0.250%: 2
- Sideways regime: recent range 0.137% < 0.300% and 20-bar move 0.049% < 0.250%: 2
- Sideways regime: recent range 0.138% < 0.300% and 20-bar move 0.095% < 0.250%: 2
- Sideways regime: recent range 0.138% < 0.300% and 20-bar move 0.161% < 0.250%: 2
- Sideways regime: recent range 0.138% < 0.300% and 20-bar move 0.202% < 0.250%: 2
- Sideways regime: recent range 0.141% < 0.300% and 20-bar move 0.041% < 0.250%: 2
- Sideways regime: recent range 0.142% < 0.300% and 20-bar move 0.058% < 0.250%: 2
- Sideways regime: recent range 0.144% < 0.300% and 20-bar move 0.031% < 0.250%: 2
- Sideways regime: recent range 0.144% < 0.300% and 20-bar move 0.111% < 0.250%: 2
- Sideways regime: recent range 0.145% < 0.300% and 20-bar move 0.056% < 0.250%: 2
- Sideways regime: recent range 0.146% < 0.300% and 20-bar move 0.024% < 0.250%: 2
- Sideways regime: recent range 0.146% < 0.300% and 20-bar move 0.084% < 0.250%: 2
- Sideways regime: recent range 0.147% < 0.300% and 20-bar move 0.030% < 0.250%: 2
- Sideways regime: recent range 0.148% < 0.300% and 20-bar move 0.007% < 0.250%: 2
- Sideways regime: recent range 0.148% < 0.300% and 20-bar move 0.063% < 0.250%: 2
- Sideways regime: recent range 0.148% < 0.300% and 20-bar move 0.077% < 0.250%: 2
- Sideways regime: recent range 0.148% < 0.300% and 20-bar move 0.122% < 0.250%: 2
- Sideways regime: recent range 0.148% < 0.300% and 20-bar move 0.230% < 0.250%: 2
- Sideways regime: recent range 0.149% < 0.300% and 20-bar move 0.002% < 0.250%: 2
- Sideways regime: recent range 0.149% < 0.300% and 20-bar move 0.007% < 0.250%: 2
- Sideways regime: recent range 0.149% < 0.300% and 20-bar move 0.055% < 0.250%: 2
- Sideways regime: recent range 0.149% < 0.300% and 20-bar move 0.086% < 0.250%: 2
- Sideways regime: recent range 0.149% < 0.300% and 20-bar move 0.131% < 0.250%: 2
- Sideways regime: recent range 0.150% < 0.300% and 20-bar move 0.156% < 0.250%: 2
- Sideways regime: recent range 0.153% < 0.300% and 20-bar move 0.165% < 0.250%: 2
- Sideways regime: recent range 0.154% < 0.300% and 20-bar move 0.143% < 0.250%: 2
- Sideways regime: recent range 0.154% < 0.300% and 20-bar move 0.155% < 0.250%: 2
- Sideways regime: recent range 0.154% < 0.300% and 20-bar move 0.206% < 0.250%: 2
- Sideways regime: recent range 0.155% < 0.300% and 20-bar move 0.140% < 0.250%: 2
- Sideways regime: recent range 0.155% < 0.300% and 20-bar move 0.163% < 0.250%: 2
- Sideways regime: recent range 0.156% < 0.300% and 20-bar move 0.012% < 0.250%: 2
- Sideways regime: recent range 0.156% < 0.300% and 20-bar move 0.119% < 0.250%: 2
- Sideways regime: recent range 0.157% < 0.300% and 20-bar move 0.232% < 0.250%: 2
- Sideways regime: recent range 0.158% < 0.300% and 20-bar move 0.025% < 0.250%: 2
- Sideways regime: recent range 0.158% < 0.300% and 20-bar move 0.075% < 0.250%: 2
- Sideways regime: recent range 0.158% < 0.300% and 20-bar move 0.122% < 0.250%: 2
- Sideways regime: recent range 0.158% < 0.300% and 20-bar move 0.147% < 0.250%: 2
- Sideways regime: recent range 0.158% < 0.300% and 20-bar move 0.213% < 0.250%: 2
- Sideways regime: recent range 0.160% < 0.300% and 20-bar move 0.075% < 0.250%: 2
- Sideways regime: recent range 0.160% < 0.300% and 20-bar move 0.142% < 0.250%: 2
- Sideways regime: recent range 0.161% < 0.300% and 20-bar move 0.069% < 0.250%: 2
- Sideways regime: recent range 0.161% < 0.300% and 20-bar move 0.150% < 0.250%: 2
- Sideways regime: recent range 0.162% < 0.300% and 20-bar move 0.128% < 0.250%: 2
- Sideways regime: recent range 0.162% < 0.300% and 20-bar move 0.129% < 0.250%: 2
- Sideways regime: recent range 0.165% < 0.300% and 20-bar move 0.207% < 0.250%: 2
- Sideways regime: recent range 0.166% < 0.300% and 20-bar move 0.121% < 0.250%: 2
- Sideways regime: recent range 0.168% < 0.300% and 20-bar move 0.126% < 0.250%: 2
- Sideways regime: recent range 0.169% < 0.300% and 20-bar move 0.161% < 0.250%: 2
- Sideways regime: recent range 0.170% < 0.300% and 20-bar move 0.118% < 0.250%: 2
- Sideways regime: recent range 0.172% < 0.300% and 20-bar move 0.165% < 0.250%: 2
- Sideways regime: recent range 0.172% < 0.300% and 20-bar move 0.172% < 0.250%: 2
- Sideways regime: recent range 0.182% < 0.300% and 20-bar move 0.027% < 0.250%: 2
- Sideways regime: recent range 0.182% < 0.300% and 20-bar move 0.074% < 0.250%: 2
- Sideways regime: recent range 0.183% < 0.300% and 20-bar move 0.222% < 0.250%: 2
- Sideways regime: recent range 0.186% < 0.300% and 20-bar move 0.140% < 0.250%: 2
- Sideways regime: recent range 0.188% < 0.300% and 20-bar move 0.056% < 0.250%: 2
- Sideways regime: recent range 0.188% < 0.300% and 20-bar move 0.216% < 0.250%: 2
- Sideways regime: recent range 0.190% < 0.300% and 20-bar move 0.221% < 0.250%: 2
- Sideways regime: recent range 0.208% < 0.300% and 20-bar move 0.236% < 0.250%: 2
- Sideways regime: recent range 0.222% < 0.300% and 20-bar move 0.201% < 0.250%: 2
- Sideways regime: recent range 0.224% < 0.300% and 20-bar move 0.134% < 0.250%: 2
- Sideways regime: recent range 0.230% < 0.300% and 20-bar move 0.184% < 0.250%: 2
- Sideways regime: recent range 0.230% < 0.300% and 20-bar move 0.212% < 0.250%: 2
- Sideways regime: recent range 0.239% < 0.300% and 20-bar move 0.111% < 0.250%: 2
- Sideways regime: recent range 0.242% < 0.300% and 20-bar move 0.078% < 0.250%: 2
- Sideways regime: recent range 0.244% < 0.300% and 20-bar move 0.177% < 0.250%: 2
- Sideways regime: recent range 0.251% < 0.300% and 20-bar move 0.203% < 0.250%: 2
- Sideways regime: recent range 0.258% < 0.300% and 20-bar move 0.187% < 0.250%: 2
- Sideways regime: recent range 0.260% < 0.300% and 20-bar move 0.177% < 0.250%: 2
- Sideways regime: recent range 0.260% < 0.300% and 20-bar move 0.222% < 0.250%: 2
- Sideways regime: recent range 0.262% < 0.300% and 20-bar move 0.125% < 0.250%: 2
- Sideways regime: recent range 0.262% < 0.300% and 20-bar move 0.129% < 0.250%: 2
- Sideways regime: recent range 0.262% < 0.300% and 20-bar move 0.154% < 0.250%: 2
- Sideways regime: recent range 0.262% < 0.300% and 20-bar move 0.174% < 0.250%: 2
- Sideways regime: recent range 0.263% < 0.300% and 20-bar move 0.121% < 0.250%: 2
- Sideways regime: recent range 0.263% < 0.300% and 20-bar move 0.125% < 0.250%: 2
- Sideways regime: recent range 0.263% < 0.300% and 20-bar move 0.159% < 0.250%: 2
- Sideways regime: recent range 0.287% < 0.300% and 20-bar move 0.143% < 0.250%: 2
- Sideways regime: recent range 0.296% < 0.300% and 20-bar move 0.009% < 0.250%: 2
- Sideways regime: recent range 0.296% < 0.300% and 20-bar move 0.014% < 0.250%: 2
- Sideways regime: recent range 0.296% < 0.300% and 20-bar move 0.061% < 0.250%: 2
- Sideways regime: recent range 0.296% < 0.300% and 20-bar move 0.088% < 0.250%: 2
- Sideways regime: recent range 0.296% < 0.300% and 20-bar move 0.091% < 0.250%: 2
- Sideways regime: recent range 0.298% < 0.300% and 20-bar move 0.146% < 0.250%: 2
- Sideways regime: recent range 0.298% < 0.300% and 20-bar move 0.182% < 0.250%: 2

## Paper Shadow
- Directional candidates: 0
- Rejection reasons:
- None recorded

## Stop-Out Re-entry Diagnostics
- Stop events: 0
- Stop events followed by a re-entry: 0
- Recovered above entry within 30 / 60 minutes: 0 / 0
- Stop events with missing option candles: 0
- First failed condition by stop event: {"accuracy filter": 0, "cooldown": 0, "lock": 0, "no EMA cross": 0, "option filter": 0, "other": 0, "premium-low cancel": 0, "risk guard": 0, "score": 0}

## Review Notes
- Reason counts are mentions; one decision may contain multiple reasons.
- Stop-loss exits count only records whose reason is exactly STOP_LOSS; TRAILING_STOP is excluded even when exit_reason_category is SL.
- With no closed trades, assess candidate and rejection flow only; do not infer strategy accuracy.
- Change at most one paper-only strategy/filter variable after a cost-aware, out-of-sample review.
