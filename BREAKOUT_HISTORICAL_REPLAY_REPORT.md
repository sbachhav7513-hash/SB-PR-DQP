# Paper Option Breakout: Historical Replay

## Result

The **baseline replay** covered the three sessions for which this workspace contains both option minute candles and underlying candles. Results are gross modeled P/L, not broker-settled returns.

| Session | Option series replayed | Trades | Wins / losses | Gross modeled P/L |
|---|---:|---:|---:|---:|
| 2026-10-07 | 16 (8 underlyings × CE/PE) | 10 | 1 / 9 | -₹9,225.25 |
| 2026-10-08 | 14 (7 underlyings × CE/PE) | 13 | 7 / 6 | +₹10,994.25 |
| 2026-10-14 | 14 (7 underlyings × CE/PE) | 14 | 4 / 10 | -₹332.25 |
| **Total** | — | **37** | **12 / 25 (32.4% wins)** | **+₹1,436.75** |

Two of the three days were negative; the small three-day gross profit is driven by the strong October 8 session. It is not persuasive evidence of a stable edge. Brokerage, taxes, bid/ask spread, slippage, latency, and partial fills are excluded, so the net result could be materially lower or negative.

## End-to-end breakout-volume filter comparison

I replayed a second variant across all three available sessions. The only difference from the baseline is that an option breakout is admitted only when the breakout candle's volume is at least the average volume of the preceding 15 option candles. It is evaluated on every bar in chronological order; rejected entries do not consume the symbol's one-trade allowance, and later signals, shared risk, and the daily loss circuit are recalculated. This historical comparison was run offline before the corresponding gate was added to the paper-only strategy path; the change has not altered the existing live-order-disabled setting.

| Session | Baseline trades | Baseline gross P/L | Volume-filter trades | Volume-filter gross P/L | Change |
|---|---:|---:|---:|---:|---:|
| 2026-10-07 | 10 (1W / 9L) | -₹9,225.25 | 13 (2W / 11L) | -₹8,499.00 | +₹726.25 |
| 2026-10-08 | 13 (7W / 6L) | +₹10,994.25 | 13 (8W / 5L) | +₹13,494.25 | +₹2,500.00 |
| 2026-10-14 | 14 (4W / 10L) | -₹332.25 | 14 (6W / 8L) | +₹2,877.75 | +₹3,210.00 |
| **Total** | **37 (12W / 25L)** | **+₹1,436.75** | **40 (16W / 24L)** | **+₹7,873.00** | **+₹6,436.25** |

The volume-filter replay is better on each of these three dates, but it still loses **₹8,499.00 on October 7**. It changes which later signals get taken: for example, it rejects the original 09:39 ICICIBANK PE trade but admits a later ICICIBANK PE re-breakout. This is why simply subtracting rejected trade P/L would not be a valid comparison.

The filter is now implemented in the paper-only breakout path. Treat these results as a promising hypothesis, **not evidence that the filter is ready for live trading**. The filter was chosen after inspecting these same sessions, so these results are in-sample and susceptible to overfitting. There are only three sessions, all P/L is gross, and real fills, spreads, latency, and costs remain unknown. Validate it on additional unseen sessions before adoption beyond paper trading.

In the **baseline** October 14 replay, the ICICIBANK 1360 PE signal was modeled at ₹26.20, with a ₹24.10 stop and ₹30.40 2R target. The candle data later reached the target at 13:03, giving a modeled gross result of ₹2,940 for 700 units. This is a candle-touch counterfactual, not proof the live paper process or a broker could fill at those prices.

## Why the losing sessions lost

The clearest common failure mode in the replay is **option-premium breakouts that did not continue**. The entry rule confirms that an option's close has crossed its own recent high, but it does not require the underlying to confirm the direction. A brief volatility/premium spike can therefore qualify without evidence that the move will persist. The October 7 follow-up below shows that underlying-direction alignment alone would not have filtered most of that day's losing signals.

- **October 7:** 9 of 10 entries hit their modeled stops, losing ₹10,675.25 gross; the single 2R target made ₹1,450, leaving **-₹9,225.25**. Five PE entries fired in a narrow 09:38–09:39 cluster across NIFTY, HDFCBANK, ICICIBANK, SBIN, and LT. During those trades, each corresponding underlying rose about 0.17%–0.47%, adverse to a long PE position. Later CE breakouts also stopped while RELIANCE and TCS underlying prices fell; the 10:01 TCS PE stopped as TCS rebounded. This looks like a broad early-session false-breakout/underlying-reversal cluster rather than one isolated bad contract.
- **October 14:** 9 stop exits lost ₹8,531.75 and one 15:15-exit proxy lost ₹225. Three 2R targets gained ₹7,640, while the two market-close proxies together gained ₹559.50, leaving **-₹332.25** gross. Several stopouts clustered from 10:07–10:30. The stopped PE trades (BANKNIFTY, RELIANCE, TCS) coincided with underlying rises; stopped CE trades (INFY, TCS, ICICIBANK) coincided with underlying falls. The same adverse relationship appeared in the later NIFTY/INFY PE stopouts. A few successful breakouts nearly offset the many failed ones, but that is before costs.

Thus the replay points to **weak continuation/whipsaw after option-premium breakouts** as the main observed pattern. Missing underlying-direction confirmation is a design weakness, but it is not, by itself, a demonstrated fix for October 7 because the spot was directionally aligned on most losing entries at the signal. One-minute candles cannot establish tick order, actual fills, spread, IV changes, or whether a real-time quote gate would have admitted each entry. October 7 also reached close to the configured ₹10,000 daily risk ceiling in the simulation, so simultaneous correlated positions made the opening false-breakout cluster costly even with the modeled risk controls.

### October 7 follow-up: candidate filters

The opening signals were not simply all weak or directionless. At entry, most had a strong-looking option candle body, several had above-average minute volume, and the underlying was already breaking its preceding 15-minute extreme in the trade direction for most of the initial cluster. Those checks alone would not have reliably predicted the reversal.

- Two losing entries (RELIANCE CE at 09:42 and TCS PE at 10:01) had zero reported volume on the breakout minute. The live quote gate uses cumulative day volume, not breakout-minute volume, so it can admit a breakout candle with no minute volume in the historical export.
- A retrospective screen requiring breakout-minute volume to be at least the preceding 15-minute average would have excluded four of the ten recorded entries: all four were losers, worth ₹4,760.00 in modeled losses. The six remaining recorded entries still sum to **-₹4,465.25**. This is only a screen of the original trades, not a full replay: removing entries changes shared risk usage and may permit other later signals.
- A separate replay requiring a second consecutive close above the original range high produced six entries, all stopped, for **-₹6,747.50**. It reduced modeled loss versus the baseline but removed the only winning trade; it is not a sufficient fix.
- The configured `paper_option_min_candle_body_ratio` is not currently checked in the range-breakout entry path. However, merely wiring in a 0.60 body threshold is not justified by these data: most losing breakout candles already had strong bodies, and the sole winner was borderline at that threshold.

The evidence therefore does **not** support claiming that one simple confirmation filter solves October 7. A sensible next controlled paper test is a breakout-minute volume confirmation, replayed end-to-end with shared risk recalculated and alternative newly eligible signals included. Keep live trading disabled. Independently, consider a smaller daily loss budget: that caps damage but does not improve the entry signal.

## Replay method

- Applied the configured 15-closed-minute option-premium range breakout: current close above the previous 15-bar high, with the preceding close at or below that high.
- Approximated the entry at the breakout candle close. Stop was one ₹0.05 tick below the previous 15-bar low; target was 2R from entry.
- Reconstructed cumulative day volume by summing the CSV minute volumes through the signal candle, because the live quote-quality gate consumes streaming cumulative volume. Used the candle's close and OI as historical proxies for the quote.
- Modeled current option premium/volume/OI limits, configured lot sizing (one to three lots, with the premium-based 10% risk-per-lot cap), shared ₹10,000 daily risk budget, one entry per exact option symbol per session, and the three-consecutive-loss circuit breaker.
- Managed positions only from candles after the entry candle. If a later candle touched both stop and target, the stop would be counted first. None of the recorded trades had both levels touched in the same candle.
- Used the final available candle close as a proxy for the 15:15 market-wide exit when a position remained open.
- Approximate contract selection as the nearest exported strike to the underlying's first 09:15 candle price, using both CE and PE. The live contract subscription chooses the nearest strike from its available instrument master based on the underlying price at startup, which may differ from this historical approximation.

## Coverage and limitations

Exact option-candle exports are available only for October 7, October 8, and October 14. The replay used 8, 7, and 7 configured underlyings respectively; it did not cover all ten configured underlyings on every day. In particular, TATAMOTORS had no option export in these sets, and several other configured underlyings were absent on individual dates.

One-minute OHLC candles cannot establish tick ordering, executable breakout/stop/target prices, quote freshness, or bid/ask spread. IV was not available in the candle exports. Simultaneous signals were processed in deterministic symbol order, while actual tick arrival order can affect the shared risk budget. Stop fills were modeled at the stop price even if a gap could have produced a worse fill. The results therefore describe a limited, approximate paper replay—not a full execution backtest or a forecast.

## Decision for the next session

The replay does **not** establish that the strategy will be profitable tomorrow. Keep it paper-only with live orders disabled, inspect actual signal/quote/entry/exit logs, and collect more sessions with execution costs and fill evidence before considering any live use. Three sessions—one substantially positive, one substantially negative, and one slightly negative—are too few to establish reliability.
