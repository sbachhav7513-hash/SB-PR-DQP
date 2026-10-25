# Paper Trading Review - 2026-10-25

## Observed Results
- Closed trades: 32
- Recorded P&L before unmodeled trading costs: -586.75
- Recorded expectancy before costs: -18.34 per trade
- Average win / loss: 605.03 / -568.37
- Profit factor before costs: 0.94
- Win rate: 46.88%
- Decisions recorded: 40525
- High-news-risk decisions: 0
- Entries suppressed by news filter: 0
- Learning feedback: minimum_screening_sample_met (32/10 trades)
- Feedback: The minimum screening count is met, not proof of an edge. Validate any candidate change with walk-forward replay and realistic costs; no strategy settings are changed automatically.
- Recorded paper P&L does not deduct brokerage, taxes, or slippage.

## Option Exit Strategy Comparison
| Strategy | Entries | Entries/day | Closed trades | Average recorded P&L/closed trade | Total recorded P&L |
| --- | ---: | ---: | ---: | ---: | ---: |
| paper_option_adaptive | 26 | 3.71 | 26 | 58.35 | 1517.00 |
| paper_range_breakout_2r | 6 | 0.86 | 6 | -350.63 | -2103.75 |
Legacy option trades without an exit-strategy tag are grouped as the fixed-20% baseline; compare sample counts before drawing conclusions.

## Performance by Entry Strategy
| Entry strategy | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| paper_option_range_breakout | 13 | 4 | 9 | -2558.75 |
| primary | 19 | 11 | 8 | 1972.00 |

## Loss Clusters
| Exit reason | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| STOP_LOSS | 14 | 0 | 14 | -9546.25 |
| TAKE_PROFIT | 1 | 1 | 0 | 1160.00 |
| TRAILING_STOP | 17 | 14 | 3 | 7799.50 |

### Symbols
| Symbol | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| SBIN_PE | 2 | 0 | 2 | -1650.00 |
| TCS_CE | 2 | 0 | 2 | -1035.00 |
| INFY_CE | 1 | 0 | 1 | -940.00 |
| ICICIBANK_CE | 1 | 0 | 1 | -735.00 |
| ICICIBANK_PE | 1 | 0 | 1 | -630.00 |

### Entry hour (IST)
| Hour | Closed trades | Wins | Losses | Recorded P&L |
| --- | ---: | ---: | ---: | ---: |
| 13:00 | 5 | 2 | 3 | -1044.50 |
| 10:00 | 12 | 5 | 7 | -559.75 |
| 11:00 | 9 | 4 | 5 | -271.25 |
| 9:00 | 3 | 2 | 1 | 166.25 |
| 12:00 | 3 | 2 | 1 | 1122.50 |

## Cost-data coverage
- Entry and exit bid/ask snapshots bracketed the recorded LTP for 9/32 closed trades. The quote-based P&L proxy on this subset is 1862.50; it is not a full-sample expectancy.
- Brokerage, taxes, and slippage are not included; do not treat the partial quote proxy as a net-performance result.
- 12/14 stop-loss exits exceeded their recorded initial risk by a total of 448.62; the paper exit is marked at the observed tick after the stop threshold, not guaranteed at the stop price.
- The available week-level records do not by themselves constitute an out-of-sample walk-forward replay; do not infer a parameter change from these aggregates.
- Keep score thresholds unchanged based on win rate alone.

## What Needs Attention
- The period finished negative at -586.75 P&L.
- Win rate was 46.88%; inspect loss clusters, not win rate alone.

## Recommended Improvements
- Review losing trades and validate one candidate change in a walk-forward replay with realistic costs before changing parameters.
- Compare expectancy and loss size after realistic costs; do not raise the score threshold from win rate alone.

## Review Before Changing
- Compare the daily trades.parquet files for the week, not just the aggregate P&L.
- Check whether losses cluster by symbol, BUY/SELL direction, time, or exit reason.
- Do not change a strategy or risk parameter from low-sample patterns; paper P&L is pre-cost.
- No parameter or live-order setting is changed automatically by learning feedback.
