# Paper Trading Review - 2026-11-13

## Observed Results
- Closed trades: 23
- Gross recorded P&L before modeled fees: -3017.00
- Recorded expectancy before costs: -131.17 per trade
- Average win / loss: 697.44 / -1208.37
- Profit factor before costs: 0.75
- Win rate: 56.52%
- Decisions recorded: 41700
- High-news-risk decisions: 0
- Entries suppressed by news filter: 0
- Learning feedback: minimum_screening_sample_met (23/10 trades)
- Feedback: The minimum screening count is met, not proof of an edge. Validate any candidate change with walk-forward replay and realistic costs; no strategy settings are changed automatically.

## Modeled Fees and Net Performance
- Gross P&L: -3017.00
- Modeled fees: 1375.85 (16/23 trades)
- Net P&L (gross minus modeled fees; no slippage): -5924.35 (16/23 trades)
- Human command affected at least one trade: yes
- All fee figures are modeled from the configured paper charge model.

| Dimension | Group | Trades | Gross P&L | Modeled fees | Net P&L | R total | Average R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| tier | index | 3 | -2638.50 | 249.33 (3/3) | -2887.83 (3/3) | N/A | N/A |
| tier | nan | 7 | 1531.50 | N/A | N/A | N/A | N/A |
| tier | stock | 13 | -1910.00 | 1126.52 (13/13) | -3036.52 (13/13) | 1.722 | 0.574 |
| CE/PE | CE | 12 | -2163.75 | 655.10 (8/12) | -4407.60 (8/12) | 0.677 | 0.677 |
| CE/PE | PE | 11 | -853.25 | 720.75 (8/11) | -1516.75 (8/11) | 1.045 | 0.522 |
| exit_trigger | bot stop | 7 | -9930.00 | 530.84 (7/7) | -10460.84 (7/7) | N/A | N/A |
| exit_trigger | bot_take_profit | 4 | 4755.00 | 390.17 (4/4) | 4364.83 (4/4) | 1.421 | 0.711 |
| exit_trigger | forced EOD | 1 | -580.00 | 71.93 (1/1) | -651.93 (1/1) | N/A | N/A |
| exit_trigger | nan | 7 | 1531.50 | N/A | N/A | N/A | N/A |
| exit_trigger | profit lock | 4 | 1206.50 | 382.91 (4/4) | 823.59 (4/4) | 0.301 | 0.301 |

## Option Exit Strategy Comparison
| Strategy | Entries | Entries/day | Closed trades | Average recorded P&L/closed trade | Total recorded P&L |
| --- | ---: | ---: | ---: | ---: | ---: |
| paper_option_adaptive | 23 | 3.29 | 23 | -131.17 | -3017.00 |
Legacy option trades without an exit-strategy tag are grouped as the fixed-20% baseline; compare sample counts before drawing conclusions.

## Performance by Entry Strategy
| Entry strategy | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| paper_underlying_support_reversal | 23 | 13 | 10 | -3017.00 |

## EMA Stop-Loss Re-entry Comparison
- Eligible stop-loss trades: 8
- Confirmed re-entry signals: 1
- Windows expired without a signal: 0
- Signal entries rejected by other gates: 1
- Closed re-entries: 0
- Re-entry wins / losses / breakeven: 0 / 0 / 0
- Baseline P&L: -3017.00; with re-entries: -3017.00
Paper-only comparison; the baseline excludes EMA re-entry trades, and all figures use recorded P&L.

## Stop-out Recovery
- Recovery records: 8
- Incomplete records: 8
- Exits within five minutes: 0
- Option reclaimed entry / reached +1R: 0 / 0
- Underlying reversed against the position: 8
Detailed per-trade checkpoint bids and R excursions are in each session's stop_out_recovery.parquet file.

## PAPER Exit Rollback Checks
| Flag | Tagged trades | Checks | Result |
| --- | ---: | --- | --- |
| runner_gap_v2 | 23 | runner_drawdowns=0 closed_trade_sessions=5/5; risk_overruns=0 days_at_or_below_-6000=0 | no rollback trigger |
| profit_lock_v2 | 23 | risk_overruns=0 days_at_or_below_-6000=0; first_ten_old_rule_better=0 paired=10/10 missing=0 tagged=23/10 | no rollback trigger |
| trail_close_confirm_v2 | 23 | risk_overruns=0 days_at_or_below_-6000=0; first_ten_old_rule_better=0 paired=10/10 missing=0 tagged=23/10 | no rollback trigger |
| partial_profit_v2 | 16 | executed=0 accounting_errors=0 duplicate_partials=0 days_at_daily_loss_limit=0; first_ten_partial_off_better=0 paired=0/10 missing=0 eligible=0/10 | no rollback trigger |
| stop_quote_validation_v2 | 16 | exit_fill_gap_rupees=0.2516; exit_fill_gap_pct=0.3576; guarded_quotes=0; fills_more_than_3pct_below_stop=1 | trade HDFCBANK_PE-2026-11-13T10:12:13.629137+05:30-BUY filled more than 3% below its stop trigger |
| stock_take_profit_v2 | 13 | take_profit_exits=4 fill_minus_trigger_gap_avg=0.2440; capped_winner_exits_bid_more_than_0.5R_within_30m=3 quote_missing=0; tagged_daily_loss=2026-11-11:655.00, 2026-11-12:-792.50, 2026-11-13:-1772.50 days_at_limit=0; first_ten_paired_stock_pnl_delta_avg=NA paired=0/10 missing=10 eligible=13/10 | no rollback trigger |
If a threshold triggers, set that flag to false, stop and restart the PAPER bot, then verify the next trade's paper_exit_flags_at_entry omits the flag. LIVE behavior is unaffected.

## Loss Clusters
| Exit reason | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| STOP_LOSS | 8 | 0 | 8 | -11470.00 |
| MARKET_CLOSE_FORCED_EXIT | 2 | 0 | 2 | -613.75 |
| PROFIT_LOCK | 7 | 7 | 0 | 1655.50 |
| MANUAL_TARGET | 2 | 2 | 0 | 2656.25 |
| TAKE_PROFIT_V2 | 4 | 4 | 0 | 4755.00 |

### Symbols
| Symbol | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| ICICIBANK_PE | 2 | 0 | 2 | -3045.00 |
| BANKNIFTY_CE | 1 | 0 | 1 | -1560.00 |
| INFY_CE | 3 | 1 | 2 | -1500.00 |
| HDFCBANK_PE | 2 | 1 | 1 | -1072.50 |
| BANKNIFTY_PE | 3 | 2 | 1 | -799.50 |

### Entry hour (IST)
| Hour | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| 14:00 | 2 | 0 | 2 | -1922.50 |
| 11:00 | 2 | 1 | 1 | -1575.00 |
| 10:00 | 9 | 5 | 4 | -1401.00 |
| 12:00 | 5 | 3 | 2 | -200.00 |
| 13:00 | 5 | 4 | 1 | 2081.50 |

## Cost-data coverage
- Entry and exit bid/ask snapshots bracketed the recorded LTP for 16/23 closed trades. The quote-based P&L proxy on this subset is -4791.00; it is not a full-sample expectancy.
- Brokerage, taxes, and slippage are not included; do not treat the partial quote proxy as a net-performance result.
- 7/8 stop-loss exits exceeded their recorded initial risk by a total of 693.05; the paper exit is marked at the observed tick after the stop threshold, not guaranteed at the stop price.
- The available week-level records do not by themselves constitute an out-of-sample walk-forward replay; do not infer a parameter change from these aggregates.
- Keep score thresholds unchanged based on win rate alone.

## What Needs Attention
- The period finished negative at -3017.00 P&L.

## Recommended Improvements
- Review losing trades and validate one candidate change in a walk-forward replay with realistic costs before changing parameters.

## Review Before Changing
- Compare the daily trades.parquet files for the week, not just the aggregate P&L.
- Check whether losses cluster by symbol, BUY/SELL direction, time, or exit reason.
- Do not change a strategy or risk parameter from low-sample patterns; paper P&L is pre-cost.
- No parameter or live-order setting is changed automatically by learning feedback.
