# Independent option strategy research

This is a stand-alone, offline study. It reads raw historical index candles and
dated Kite option-candle exports; it does not import the current bot, change its
configuration, connect to Kite, or place orders.

Run from the repository root:

```powershell
python fresh_study\independent_option_lab\research.py
python -m pytest fresh_study\independent_option_lab\test_research.py -q
```

`research_config.json` contains the research-only entry filters, risk/exit
scenarios, and test periods. The run writes trade-level CSVs, summaries, and
metadata into `results\`. The current evidence and limitations are in
[RESULTS.md](./RESULTS.md).

The option replay approximates entry with the next minute's option-candle open.
Its fee scenarios are sensitivity assumptions, not observed bid/ask spreads or
broker costs. Treat all outputs as exploratory paper research, not a deployable
strategy.

The separate [gap-continuation study](./gap_continuation/RESULTS.md) tests an
overnight-gap and first-minutes confirmation hypothesis. It has its own replay,
configuration, tests, and results; it does not reuse the opening-range rules.
