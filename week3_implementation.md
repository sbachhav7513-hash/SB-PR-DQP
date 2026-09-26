# Week 3 Implementation Guide - Quality Recovery

## Evidence Used

Source: `weekly_report_2026_09_26.json`, seven-day paper-trading window.

- Closed trades: 2
- Winning trades: 0
- Losing trades: 2
- Win rate: 0.0%
- Total P&L: -3356.75
- Average loss: -1678.38
- Largest loss: -2528.75
- Profit factor: 0.0
- Decisions recorded: 111825
- Approved entries: 6
- Rejected entries: 5291

The sample is too small to prove a strategy edge or justify permanent symbol exclusions. Week 3 should therefore prioritize data quality, controlled exposure, and repeatable validation rather than parameter optimization.

## What The Report Shows

### Loss concentration

- `LT_PE`: 1 trade, 0 wins, -2528.75
- `BANKNIFTY_CE`: 1 trade, 0 wins, -828.00
- Reported hour `12`: 2 trades, 0 wins, -3356.75
- Both `12:BUY` and `12:SELL` setup windows lost.

These are warning signals, not enough evidence for a permanent blacklist. Confirm the timezone used by the journal before treating hour `12` as an IST session window.

### Entry and filter quality

- Volatility rejections: 412
- Confirmation rejections: 64
- Cooldown rejections: 34
- Trading-hours rejections: 9
- Threshold rejections: 33
- Option-filter rejections: 4736
- Risk rejections: 3
- Execution failures: 0

The system is evaluating a very large number of non-trading decisions, including `HOLD`, pre-market, and after-close outcomes. The next review must separate market-session decisions from operational noise.

## Week 3 Changes

### 1. Verify journal timestamps and report scope

Before changing strategy parameters:

1. Confirm that timestamps are stored consistently with timezone information.
2. Confirm whether report hours are UTC or IST.
3. Add or use a market-session filter when calculating entry quality.
4. Report closed trades, approved entries, rejected entries, and operational decisions separately.

Acceptance check: a seven-day report must identify the session timezone and must not treat pre-market or after-close events as live entry opportunities.

### 2. Keep the existing quality gates active

The report shows that the current filters are rejecting candidates, but there are not enough closed trades to measure whether the filters improve outcomes. Keep volatility, confirmation, cooldown, score, and trading-hours checks enabled while collecting a larger sample.

Do not lower thresholds to increase trade count. A minimum target for the next review is at least 10 closed paper trades before making another strategy change.

### 3. Add a conservative late-window guard

The two losses share the reported hour `12`, but the timezone must be verified first. Once confirmed, block only the affected market-session window through configuration or an explicit trading-hours filter. Keep the guard easy to disable and log the exact rejection reason.

Every blocked entry should record:

- symbol and direction
- timestamp and timezone
- signal score
- rejection reason
- whether the decision occurred during market hours

### 4. Add session-level symbol exposure limits

Use a maximum of one new trade per symbol per session while the sample is being rebuilt. After a closed loss, pause new entries for that symbol for the remainder of the session unless a separately logged override is approved.

Do not permanently exclude `LT_PE` or `BANKNIFTY_CE` yet. Revisit symbol-level rules after each has at least five closed trades or after a clearly repeated loss pattern.

### 5. Verify risk sizing and exits

The largest loss accounted for most of the weekly drawdown. Confirm that:

- protective stops are placed before or atomically with live entries;
- position sizing respects the configured per-trade risk cap;
- forced exits and stop-loss exits are distinguishable in the journal;
- a failed protective-stop placement blocks the trade and is surfaced as an execution failure.

Do not increase take-profit distance or loosen stop-loss settings based on this report. There are no winning trades in the current window to support that change.

### 6. Improve rejection observability

The report contains 111825 decisions but only 5291 classified rejections. Ensure every candidate has one normalized outcome and that the report aggregates rejection reasons without embedding dynamic premium values in each outcome key.

Recommended normalized categories:

- `market_closed`
- `premarket`
- `hold`
- `option_filter`
- `accuracy_filter`
- `risk_blocked`
- `trade_opened`
- `execution_failed`

This will make filter counts comparable from week to week.

## Validation Plan

Run the focused tests after each implementation slice:

```text
python -m pytest tests/test_weekly_report.py tests/test_intraday_manager.py -q
```

Before accepting the next report, verify:

1. No new entry is accepted outside the configured market session.
2. A second entry for the same symbol in one session is rejected and journaled.
3. A symbol with a closed loss is paused according to the session rule.
4. A failed protective stop prevents unprotected exposure.
5. Report totals reconcile: approved entries plus classified rejections plus non-entry operational decisions equal the decision count.
6. At least 10 closed paper trades are collected before changing score, volatility, stop-loss, or take-profit parameters.

## Week 3 Success Criteria

The goal is reliable measurement and controlled risk, not a promised win rate. At the next review, target:

- positive paper-trading P&L;
- win rate above 50% with at least 10 closed trades;
- profit factor above 1.0;
- zero unprotected entries;
- no unexplained execution failures;
- a report whose timezone and decision categories are explicit;
- evidence that the late-window and symbol exposure guards are actually being exercised.

If the next sample remains negative after these controls, reduce the traded universe and stop live entries until the journal and risk path have been reviewed.
