# Paper Trading Review - 2026-10-09

## Observed Results
- Closed trades: 5
- Total P&L: -142.50
- Win rate: 40.00%
- Decisions recorded: 47779
- High-news-risk decisions: 0
- Entries suppressed by news filter: 0

## Option Exit Strategy Comparison
| Strategy | Entries | Entries/day | Closed trades | Average P&L/closed trade | Total P&L |
| --- | ---: | ---: | ---: | ---: | ---: |
| tiered_milestone | 5 | 0.71 | 5 | -28.50 | -142.50 |
Legacy option trades without an exit-strategy tag are grouped as the fixed-20% baseline; compare sample counts before drawing conclusions.

## What Needs Attention
- The period finished negative at -142.50 P&L.
- Win rate was 40.00%, below the 50% baseline.

## Recommended Improvements
- Review losing trades by symbol, direction, signal score, and exit reason before changing parameters.
- Raise the entry-quality threshold or add confirmation rather than increasing trade frequency.

## Review Before Changing
- Compare the daily trades.parquet files for the week, not just the aggregate P&L.
- Check whether losses cluster by symbol, BUY/SELL direction, time, or exit reason.
- Change one strategy or risk parameter at a time and continue paper trading.
