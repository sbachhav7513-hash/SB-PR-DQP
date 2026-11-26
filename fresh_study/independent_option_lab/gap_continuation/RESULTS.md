# Overnight gap-continuation study

## Decision

**Do not deploy or shadow this candidate yet.** The five-minute version
produced attractive modeled option results in a very small recent sample, but
the result does not survive even a basic confirmation-window sensitivity check.
The five-minute window was selected after comparing 5, 15, and 30 minutes on
the same recent option sample, so its apparent premium edge is exploratory,
not an untouched test. No orders were enabled and the current bot was not
modified.

This is a distinct strategy family from the existing EMA/VWAP/breakout logic
and from the separate opening-range study. It tests overnight-gap continuation
confirmed by early-session price action.

## Global research: rationale, not proof

- Gao, Han, Li, and Zhou, [“Market Intraday Momentum”](https://doi.org/10.1016/j.jfineco.2018.05.009),
  *Journal of Financial Economics* 129 (2018), 394–414. Their study reports
  that the first half-hour market return predicted the final half-hour return
  in high-frequency S&P 500 ETF data and in ten other domestic and international
  ETFs. This motivates testing early-session continuation, but does not validate
  a five-minute signal, Indian index options, or an overnight-gap entry.
- Xu, [“Reversal, Momentum and Intraday Returns”](https://doi.org/10.2139/ssrn.2991183)
  (SSRN working paper, 2017). The abstract reports morning continuation and
  afternoon reversal in its stock-trade data. This is working-paper evidence
  from a different market and instrument set, not a deployable rule.
- Akbas et al., [“Overnight returns, daytime reversals, and future stock returns”](https://doi.org/10.1016/j.jfineco.2021.09.019),
  *Journal of Financial Economics* 145 (2022), 850–870, is relevant
  counter-evidence to treating overnight and intraday direction as universally
  persistent. The existence of continuation and reversal findings makes local
  out-of-sample testing essential.

These sources informed the hypothesis only. They are not direct evidence for
NIFTY/BANKNIFTY option profitability.

## Data and method

- Underlying minute bars: NIFTY and BANKNIFTY, 2015-01-09 through 2026-11-23.
  Their volume fields are zero; these data support only underlying-price
  screening.
- Option candles: selected one-minute contracts on 28 dates, 2026-10-14 through
  2026-11-25. They have no historical bid/ask, implied volatility, or verified
  executable fills. The premium sample is therefore limited and does not
  establish long-run option returns.
- Prior ATR is the average true range of the previous 20 completed sessions;
  the current session is excluded. A candidate gap is 0.25 to less than 0.75
  prior ATR from the prior close.
- At 09:20 IST, enter at the next-minute open only if the first five-minute
  close moved in the same direction as the 09:15 opening gap. No minimum
  confirmation-strength threshold is used: testing showed that adding one can
  remove winners as well as losses.
- The underlying proxy uses a 0.25 ATR protective stop, a 1.5R target, and a
  120-minute maximum hold. Option scenarios use a 5% premium stop, 5% or 10%
  target, or a 5%-activation/3%-trail/10%-cap exit.
- Option entry is modeled at the next minute's candle open. Costs of 0%,
  0.25%, and 0.50% per side are assumptions, not measured spread or complete
  taxes/fees. The 10% target and 5% stop cases are candle-path simulations.
- Underlying records are not option returns. Per-trade percentage points are
  not compounded portfolio returns. Trades on the same day and across indices
  may be correlated.

The exploration included multiple gap, confirmation-strength, and time-window
thresholds. Consequently, 2025/2026 and recent option results were inspected
during selection; none should be described as a pristine, untouched final
holdout.

## Long-history underlying proxy

For the direction-only confirmation rule (minimum confirmation/gap ratio 0),
the underlying barrier replay was modestly positive at five minutes but weak
out of sample. `R` is the underlying-price result normalized by the 0.25 ATR
stop, not an option-premium return.

| Confirmation | Partition | Trades | Mean R | PF proxy | Positive years |
|---|---|---:|---:|---:|---:|
| 5 min | 2015–2024 | 788 | +0.116 | 1.293 | 8 / 10 |
| 5 min | 2025 | 52 | +0.078 | 1.161 | 1 / 1 |
| 5 min | 2026 YTD | 71 | +0.037 | 1.090 | 1 / 1 |
| 15 min | 2015–2024 | 831 | +0.047 | 1.117 | 6 / 10 |
| 15 min | 2025 | 62 | +0.138 | 1.352 | 1 / 1 |
| 15 min | 2026 YTD | 75 | -0.111 | 0.756 | 0 / 1 |
| 30 min | 2015–2024 | 819 | +0.042 | 1.115 | 5 / 10 |
| 30 min | 2025 | 73 | -0.174 | 0.664 | 0 / 1 |
| 30 min | 2026 YTD | 77 | -0.164 | 0.625 | 0 / 1 |

This is not a robust cross-window or cross-period result. More selective
confirmation ratios improved historical training statistics but reduced trade
counts and weakened or reversed 2025 results. For example, at a 0.75
confirmation/gap ratio, the five-minute rule had only nine 2025 trades. This is
why no such stronger threshold was promoted as a reliable filter.

## Recent option outcomes and the iteration that changed the conclusion

At 0.25% assumed cost per side, the five-minute gap-band filter selected five
modeled option trades across four sessions. The 10% target/5% stop case had
four target exits and one stop, 80% wins, +6.73% mean net return per trade, and
PF 7.43. These numbers are **not a stable performance estimate**: five trades
are far too few, the filters were explored on this same sample, and no
historical spreads or IV were available. Net target exits model to +9.725%;
the stop models to -5.2375%.

| Date | Symbol | Gap / prior ATR | First-5m alignment ratio | Modeled net return | Exit |
|---|---|---:|---:|---:|---|
| 2026-10-21 | NIFTY | 0.448 | 0.182 | +9.725% | 10% target |
| 2026-10-22 | NIFTY | 0.413 | 0.630 | +9.725% | 10% target |
| 2026-10-22 | BANKNIFTY | 0.324 | 0.125 | -5.238% | 5% stop |
| 2026-11-02 | NIFTY | 0.535 | 0.262 | +9.725% | 10% target |
| 2026-11-13 | NIFTY | 0.263 | 0.983 | +9.725% | 10% target |

The 21 direction-aligned option candidates rejected for being outside the gap
band averaged -2.10% under the same exit/cost case. That initially looked like
useful filtering, but does not by itself validate the filter: the same small
recent sample was used to inspect and choose the band.

The more important follow-up was to repeat the option replay with 15- and
30-minute confirmation rather than trusting the initial five-minute result.
Only trades that passed the same gap-band and direction filters are shown:

| Confirmation | Trades | Wins | Mean net, +10% target / -5% stop | PF | Positive sessions |
|---|---:|---:|---:|---:|---:|
| 5 min | 5 | 4 / 5 | +6.73% | 7.43 | 4 / 4 |
| 15 min | 7 | 1 / 7 | -3.10% | 0.31 | 1 / 5 |
| 30 min | 8 | 2 / 8 | -1.50% | 0.62 | 1 / 5 |

The sharp performance change across closely related confirmation windows is
strong evidence of sample sensitivity. In particular, picking five minutes
because it won on this same handful of option sessions creates selection bias.
Do not treat the five-minute result, its 80% win rate, or its PF as confirmation
of a real 5–10% strategy.

## What this says about the requested goals

1. **5–10% premium gains:** The simulation reached a 10% target in four of five
   selected five-minute trades, but the sample and fill assumptions cannot
   establish repeatable gains.
2. **Early entry:** The five-minute rule enters at 09:20, but its results do
   not hold at the tested 15/30-minute windows. Earlier entry is not itself an
   edge.
3. **Avoiding adverse swings:** The option stop limited modeled loss to about
   5.24% net at the assumed cost, but one loss among five trades is not enough
   to validate reversal control. The underlying proxy and candle data also
   cannot resolve intrabar execution or option repricing accurately.

## Recommendation and reproducibility

- Keep the current bot unchanged. The research replay has no broker or order
  interface and `orders_enabled` remains false.
- Do not create a shadow runner yet. The rule has not passed a genuinely
  untouched, cost-observed option test, and the 5/15/30-minute comparison is
  unstable.
- Freeze a rule before collecting another forward sample; capture actual
  selected contracts, bid/ask, timestamps, and simulated fills. Review only
  after a materially larger sample across many sessions, then consider a
  separate shadow-only runner if the net edge remains stable. A 3–4-session
  trial is not enough to establish that edge.

Run the offline replay and focused tests from the repository root:

```powershell
python fresh_study\independent_option_lab\gap_continuation\replay.py
python -m pytest fresh_study\independent_option_lab\gap_continuation\test_replay.py -q
```

Outputs are in `results\`: trade-level decisions and underlying proxies,
selected/rejected option candidates and trades, the primary option summary,
and `gap_option_confirmation_sensitivity.csv` for 5/15/30-minute outcomes.
The configuration is in [config.json](./config.json); the replay implementation
is in [replay.py](./replay.py).
