# Paper Trading Review - 2026-10-16

## Observed Results
- Closed trades: 36
- Recorded P&L before unmodeled trading costs: -474.00
- Win rate: 36.11%
- Decisions recorded: 48076
- High-news-risk decisions: 0
- Entries suppressed by news filter: 0
- Learning feedback: minimum_screening_sample_met (36/10 trades)
- Feedback: The minimum screening count is met, not proof of an edge. Validate any candidate change with walk-forward replay and realistic costs; no strategy settings are changed automatically.
- Recorded paper P&L does not deduct brokerage, taxes, or slippage.

## Option Exit Strategy Comparison
| Strategy | Entries | Entries/day | Closed trades | Average recorded P&L/closed trade | Total recorded P&L |
| --- | ---: | ---: | ---: | ---: | ---: |
| fixed_20pct_baseline | 8 | 1.14 | 8 | 793.53 | 6348.25 |
| paper_option_2r_trail_runner | 14 | 2.00 | 14 | -192.20 | -2690.75 |
| tiered_milestone | 14 | 2.00 | 14 | -295.11 | -4131.50 |
Legacy option trades without an exit-strategy tag are grouped as the fixed-20% baseline; compare sample counts before drawing conclusions.

## What Needs Attention
- The period finished negative at -474.00 P&L.
- Win rate was 36.11%; inspect loss clusters, not win rate alone.

## Recommended Improvements
- Review losing trades and validate one candidate change in a walk-forward replay with realistic costs before changing parameters.
- Compare expectancy and loss size after realistic costs; do not raise the score threshold from win rate alone.

## Review Before Changing
- Compare the daily trades.parquet files for the week, not just the aggregate P&L.
- Check whether losses cluster by symbol, BUY/SELL direction, time, or exit reason.
- Do not change a strategy or risk parameter from low-sample patterns; paper P&L is pre-cost.
- No parameter or live-order setting is changed automatically by learning feedback.
