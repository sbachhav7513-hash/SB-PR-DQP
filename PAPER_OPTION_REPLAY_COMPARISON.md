# Historical Paper P/L vs. New-Rule Replay

## Correction and verified EMA result

The earlier seven-day comparison generated in this chat is **not valid** and
its reported new-strategy total of -₹14,100.45 is withdrawn. It did not
reproduce the exact-contract recovery backtest documented in
`backtest_artifacts/STOP_LOSS_RECOVERY_BACKTEST_REPORT.md`.

The existing exact-contract report is the relevant source for the user's
reported result. It tests 5/20 EMA-cross re-entry signals within 10 completed
one-minute bars after the original option stop, across 21 matched
stop-losses, using exact archived contracts and original-trade risk sizing.

| Measure | Value |
|---|---:|
| Existing 73-trade portfolio P/L | -₹1,203.25 |
| EMA re-entry P/L added (7 entries) | +₹7,997.60 |
| Combined portfolio P/L (80 trades) | **+₹6,794.35** |
| Combined portfolio profit factor | **1.209** |
| Largest re-entry-only win rate in the report | 42.86% |

The arithmetic reconciles: **-₹1,203.25 + ₹7,997.60 = +₹6,794.35**.
Therefore, ₹6,794.35 is the combined portfolio result, not the re-entry-only
increment. The report's 1.209 is the combined portfolio profit factor.

The earlier replay's error was not evidence that EMA re-entry performs
differently. It selected a near-the-money contract at session open, fixed
sizing at one lot, reduced each underlying to a selected entry, and did not
reproduce the exact-contract backtest's original-risk sizing, trade universe,
or exit variants. It compared that approximate result to journal P/L from a
different set of trades and dates. Its day table should not be used.

The journal baseline is paper-trade data, not broker-confirmed fills
(`live_orders_enabled` is false). The separate `market_bot/backtest.py` EMA
re-entry metric also uses underlying OHLC directional returns and explicitly
labels its price basis as an underlying proxy; it is not the source of the
exact-contract rupee result above.

## Requirements for a valid comparison

For any new day-wise comparison, the replay must retain the exact-contract
report's scope or explicitly explain any change: chronological underlying
signals, matching option-premium candles and exact contracts, original-trade
risk sizing, and the tested exit variants. The report's aggregate result
cannot be split into daily EMA-vs-baseline P/L from its summary table alone;
those daily trade-level replay records would be needed.

The report covers the October 9–23 sample and notes important limitations:
same-period in-sample evaluation, only 21 matched stop-loss trades, one-minute
OHLC fill/order ambiguity, missing costs and executable quotes, and no
holdout/walk-forward validation. It is a historical counterfactual, not a
guaranteed result.
