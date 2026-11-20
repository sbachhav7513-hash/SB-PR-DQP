# Paper Trading Review - 2026-11-20

## Observed Results
- Closed trades: 19
- Gross recorded P&L before modeled fees: -11495.50
- Recorded expectancy before costs: -605.03 per trade
- Average win / loss: 862.04 / -1460.81
- Profit factor before costs: 0.34
- Win rate: 36.84%
- Decisions recorded: 52151
- High-news-risk decisions: 0
- Entries suppressed by news filter: 0
- Learning feedback: minimum_screening_sample_met (19/10 trades)
- Feedback: The minimum screening count is met, not proof of an edge. Validate any candidate change with walk-forward replay and realistic costs; no strategy settings are changed automatically.

## Modeled Fees and Net Performance
- Gross P&L: -11495.50
- Modeled fees: 1668.00 (19/19 trades)
- Net P&L (gross minus modeled fees; no slippage): -13163.50 (19/19 trades)
- Human command affected at least one trade: yes
- All fee figures are modeled from the configured paper charge model.

| Dimension | Group | Trades | Gross P&L | Modeled fees | Net P&L | R total | Average R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| tier | BANKNIFTY | 1 | -2121.00 | 92.08 (1/1) | -2213.08 (1/1) | N/A | N/A |
| tier | STOCK | 6 | -1426.25 | 520.40 (6/6) | -1946.65 (6/6) | 0.913 | 0.457 |
| tier | index | 3 | 2953.00 | 266.08 (3/3) | 2686.92 (3/3) | 0.232 | 0.232 |
| tier | stock | 9 | -10901.25 | 789.44 (9/9) | -11690.69 (9/9) | 0.626 | 0.626 |
| CE/PE | CE | 10 | -5971.75 | 869.42 (10/10) | -6841.17 (10/10) | 0.913 | 0.457 |
| CE/PE | PE | 9 | -5523.75 | 798.58 (9/9) | -6322.33 (9/9) | 0.858 | 0.429 |
| exit_trigger | bot stop | 9 | -16554.75 | 753.85 (9/9) | -17308.60 (9/9) | N/A | N/A |
| exit_trigger | bot_take_profit | 1 | 787.50 | 71.49 (1/1) | 716.01 (1/1) | N/A | N/A |
| exit_trigger | forced EOD | 1 | -900.00 | 86.58 (1/1) | -986.58 (1/1) | N/A | N/A |
| exit_trigger | human /exitat reached | 4 | 4508.50 | 383.45 (4/4) | 4125.05 (4/4) | 1.224 | 0.612 |
| exit_trigger | profit lock | 4 | 663.25 | 372.63 (4/4) | 290.62 (4/4) | 0.546 | 0.273 |

## Option Exit Strategy Comparison
| Strategy | Entries | Entries/day | Closed trades | Average recorded P&L/closed trade | Total recorded P&L |
| --- | ---: | ---: | ---: | ---: | ---: |
| paper_option_adaptive | 19 | 2.71 | 19 | -605.03 | -11495.50 |
Legacy option trades without an exit-strategy tag are grouped as the fixed-20% baseline; compare sample counts before drawing conclusions.

## Performance by Entry Strategy
| Entry strategy | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| paper_ema_stop_reentry | 1 | 0 | 1 | -1912.50 |
| paper_underlying_support_reversal | 13 | 6 | 7 | -5213.00 |
| paper_underlying_support_reversal_stop_reentry | 2 | 0 | 2 | -3150.00 |
| primary | 3 | 1 | 2 | -1220.00 |

## EMA Stop-Loss Re-entry Comparison
- Eligible stop-loss trades: 8
- Confirmed re-entry signals: 1
- Windows expired without a signal: 0
- Signal entries rejected by other gates: 0
- Closed re-entries: 1
- Re-entry wins / losses / breakeven: 0 / 1 / 0
- Baseline P&L: -9583.00; with re-entries: -11495.50
Paper-only comparison; the baseline excludes EMA re-entry trades, and all figures use recorded P&L.

## Stop-out Recovery
- Recovery records: 9
- Incomplete records: 9
- Exits within five minutes: 2
- Option reclaimed entry / reached +1R: 0 / 0
- Underlying reversed against the position: 9
Detailed per-trade checkpoint bids and R excursions are in each session's stop_out_recovery.parquet file.

## PAPER Exit Rollback Checks
| Flag | Tagged trades | Checks | Result |
| --- | ---: | --- | --- |
| runner_gap_v2 | 42 | runner_drawdowns=0 closed_trade_sessions=5/5; risk_overruns=0 days_at_or_below_-6000=0 | no rollback trigger |
| profit_lock_v2 | 42 | risk_overruns=0 days_at_or_below_-6000=0; first_ten_old_rule_better=0 paired=10/10 missing=0 tagged=42/10 | no rollback trigger |
| trail_close_confirm_v2 | 42 | risk_overruns=0 days_at_or_below_-6000=0; first_ten_old_rule_better=0 paired=10/10 missing=0 tagged=42/10 | no rollback trigger |
| partial_profit_v2 | 35 | executed=0 accounting_errors=0 duplicate_partials=0 days_at_daily_loss_limit=0; first_ten_partial_off_better=0 paired=0/10 missing=0 eligible=0/10 | no rollback trigger |
| stop_quote_validation_v2 | 35 | exit_fill_gap_rupees=0.2406; exit_fill_gap_pct=0.4674; guarded_quotes=0; fills_more_than_3pct_below_stop=2 | trade HDFCBANK_PE-2026-11-13T10:12:13.629137+05:30-BUY filled more than 3% below its stop trigger |
| stock_take_profit_v2 | 28 | take_profit_exits=5 fill_minus_trigger_gap_avg=0.2024; capped_winner_exits_bid_more_than_0.5R_within_30m=3 quote_missing=0; tagged_daily_loss=2026-11-11:655.00, 2026-11-12:-792.50, 2026-11-13:-1772.50, 2026-11-16:-7035.00, 2026-11-17:-3866.25, 2026-11-18:-3132.50, 2026-11-19:918.75, 2026-11-20:787.50 days_at_limit=1; first_ten_paired_stock_pnl_delta_avg=NA paired=0/10 missing=10 eligible=28/10 | stock_take_profit_v2 tagged daily loss reached INR 6000.00 on 2026-11-16 (P&L -7035.00) |
If a threshold triggers, set that flag to false, stop and restart the PAPER bot, then verify the next trade's paper_exit_flags_at_entry omits the flag. LIVE behavior is unaffected.

## Loss Clusters
| Exit reason | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| STOP_LOSS | 9 | 0 | 9 | -16554.75 |
| MARKET_CLOSE_FORCED_EXIT | 1 | 0 | 1 | -900.00 |
| PROFIT_LOCK | 4 | 2 | 2 | 663.25 |
| TAKE_PROFIT_V2 | 1 | 1 | 0 | 787.50 |
| MANUAL_TARGET | 4 | 4 | 0 | 4508.50 |

### Symbols
| Symbol | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| TCS_CE | 3 | 0 | 3 | -5557.50 |
| RELIANCE_PE | 3 | 0 | 3 | -4425.00 |
| INFY_CE | 2 | 0 | 2 | -2580.00 |
| INFY_PE | 2 | 0 | 2 | -1560.00 |
| BANKNIFTY_PE | 2 | 1 | 1 | -702.00 |

### Entry hour (IST)
| Hour | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| 11:00 | 2 | 0 | 2 | -3930.00 |
| 10:00 | 10 | 5 | 5 | -3908.75 |
| 12:00 | 2 | 0 | 2 | -3585.00 |
| 14:00 | 1 | 0 | 1 | -1286.25 |
| 9:00 | 1 | 0 | 1 | -75.00 |
| 13:00 | 3 | 2 | 1 | 1289.50 |

## Cost-data coverage
- Entry and exit bid/ask snapshots bracketed the recorded LTP for 10/19 closed trades. The quote-based P&L proxy on this subset is -3397.75; it is not a full-sample expectancy.
- Brokerage, taxes, and slippage are not included; do not treat the partial quote proxy as a net-performance result.
- 9/9 stop-loss exits exceeded their recorded initial risk by a total of 1335.13; the paper exit is marked at the observed tick after the stop threshold, not guaranteed at the stop price.
- The available week-level records do not by themselves constitute an out-of-sample walk-forward replay; do not infer a parameter change from these aggregates.
- Keep score thresholds unchanged based on win rate alone.

## What Needs Attention
- The period finished negative at -11495.50 P&L.
- Win rate was 36.84%; inspect loss clusters, not win rate alone.

## Recommended Improvements
- Review losing trades and validate one candidate change in a walk-forward replay with realistic costs before changing parameters.
- Compare expectancy and loss size after realistic costs; do not raise the score threshold from win rate alone.

## Review Before Changing
- Compare the daily trades.parquet files for the week, not just the aggregate P&L.
- Check whether losses cluster by symbol, BUY/SELL direction, time, or exit reason.
- Do not change a strategy or risk parameter from low-sample patterns; paper P&L is pre-cost.
- No parameter or live-order setting is changed automatically by learning feedback.
