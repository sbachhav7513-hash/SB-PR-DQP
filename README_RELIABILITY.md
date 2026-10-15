# Reliability & Live-Trading Readiness

## Current verdict: NO-GO for live orders

The repository's local Kite configuration is paper-only: paper trading is
enabled, live orders are disabled, and live-order confirmation is disabled.
Keep it that way until the live-trading gates below have been independently
reviewed and approved. This validation did not connect to a broker, submit an
order, or verify a live market session.

## What was verified

- Full project test suite: 203 passed, 1 skipped. The skipped test requires
  POSIX timezone control, which is unavailable on this Windows environment.
- Test environment: project virtual environment, Python 3.10.6. Confirm the
  deployment host uses a supported and matching runtime.
- Python bytecode compilation: passed for `market_bot`, `tests`, and both bot
  entry points.
- `git diff --check`: passed.
- Active config safety flags: paper enabled; live orders and live confirmation
  disabled.

These checks establish test and configuration facts only. They do not establish
signal profitability, broker readiness, execution quality, or operational
reliability under a live market.

## Performance evidence

There is no verified, cost-adjusted out-of-sample or forward-trading result in
this validation that supports a current win rate, expectancy, or expected rupee
profit. Win-rate increases, accuracy improvements, whipsaw reductions, and
daily/monthly profit projections in older guides are unverified estimates, not
measured outcomes. Do not use them as a reason to enable live orders or scale
capital.

Evaluate each strategy variant separately on a predeclared, unseen paper sample.
Record closed trades, realized P&L, fees, spread, slippage, rejected/partial
orders, drawdown, and outages. A small sample is screening evidence only, not
proof of an edge. Do not tune and evaluate on the same sessions.

## Open live-trading gates

1. Keep live orders disabled; the current configuration and code have not been
   validated with real orders or a broker-connected end-to-end session.
2. Review the configured daily loss limit and per-trade risk with the account
   owner before any live use. The current local configuration allows a daily
   loss limit of 10% of configured account size; this validation does not endorse
   that exposure.
3. Verify current instrument tokens, contract lot sizes, expiry selection,
   quotes, and market-session handling against the broker's current instrument
   master before the session.
4. Confirm the deployment host's Python version and dependencies match the
   tested environment.
5. Exercise broker-side order placement, partial fills, rejections, protective
   stop creation/modification/cancellation, restart/reconciliation, disconnect
   recovery, and emergency exits in a broker-approved non-production test
   environment. Unit tests with mocks are not a substitute.
6. Establish a monitored paper-trading record with realistic transaction costs
   and an explicit independent review before considering live authorization.

## Tomorrow's deployment decision

The verified state is suitable only for a controlled paper-trading run, subject
to normal operator checks. It is **not approved for live trading**. Do not turn
on `live_orders_enabled` or `live_orders_confirmed` based on this test result or
the projections in older strategy documents.
