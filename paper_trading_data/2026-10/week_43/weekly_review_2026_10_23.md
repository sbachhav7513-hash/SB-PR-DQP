# Paper Trading Review - 2026-10-23

## Observed Results
- Closed trades: 32
- Recorded P&L before unmodeled trading costs: -586.75
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
| fixed_20pct_baseline | 32 | 4.57 | 32 | -18.34 | -586.75 |
Legacy option trades without an exit-strategy tag are grouped as the fixed-20% baseline; compare sample counts before drawing conclusions.

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
