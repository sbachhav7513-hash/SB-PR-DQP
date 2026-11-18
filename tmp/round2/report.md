# Round 2: Regime Gate, Pullback Entry, and Break-Even

Window: 14-Oct-2026 through 17-Nov-2026. Source data were not modified; generated outputs are in `tmp/round2/`.

## A. NIFTY regime gate at trade time

- Cohort: 130 archived trades over 21 dates, matching Test A daily counts.
- Timestamp: 56 use recorded `signal_time`; 9 fall back to `entry_time`; 65 use the trade timestamp as entry-time proxy where `entry_time` is blank. The per-trade source is recorded in `a_trade_metrics.csv`.
- Fees are recorded on 28/130 trades and recomputed on 102 via `market_bot/paper_costs.py`; daily gross, fees and net reconcile to Test A to the cent.
- Range-so-far uses completed 1-minute NIFTY bars from 09:15 up to (excluding) the signal minute, divided by the 09:15 open. First-hour/prior-day range percentages use the existing Test A daily regime table. Unknown prior-day range blocks R2; it is not forward-filled.

### Range-so-far buckets

| Bucket | Trades | Gross INR | Fees INR | Net INR | Mean net R (risk n) | Win rate |
| --- | --- | --- | --- | --- | --- | --- |
| <0.5% | 5 | 118.00 | 351.77 | -233.77 | NA (n=0) | 40.0% |
| 0.5-<0.7% | 26 | -9,147.25 | 2,022.75 | -11,170.00 | -0.413 (n=15) | 42.3% |
| 0.7-<1.0% | 47 | 6,733.50 | 3,747.60 | 2,985.90 | 0.033 (n=18) | 53.2% |
| >=1.0% | 52 | 2,820.00 | 3,783.61 | -963.61 | -0.840 (n=2) | 38.5% |
| unknown | 0 | 0.00 | 0.00 | 0.00 | NA (n=0) | NA% |

- Trades before the NIFTY range-so-far reached 0.7%: 31/130.


### Rule results

Baseline is all trades in each split. `Net ex-best` and `mean ex-best` remove the best single net-P&L trade in that set. Date-half split is the first 10 archive dates (14-Oct–29-Oct) versus the last 11 (30-Oct–17-Nov).

#### 14-Oct to 11-Nov
| Rule | Set | Trades | Net INR | Mean net INR/trade | Win rate | Mean net R (risk n) | Net ex-best INR | Mean ex-best INR/trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1: range-so-far >=0.7% | baseline | 108 | 4,347.62 | 40.26 | 45.4% | 0.007 (n=13) | 611.13 | 5.71 |
| R1: range-so-far >=0.7% | kept | 90 | 4,284.76 | 47.61 | 44.4% | 0.028 (n=11) | 548.27 | 6.16 |
| R1: range-so-far >=0.7% | blocked | 18 | 62.86 | 3.49 | 50.0% | -0.108 (n=2) | -1,066.48 | -62.73 |
| R2: prior-day NIFTY range >=1.1% | baseline | 108 | 4,347.62 | 40.26 | 45.4% | 0.007 (n=13) | 611.13 | 5.71 |
| R2: prior-day NIFTY range >=1.1% | kept | 55 | 2,670.58 | 48.56 | 41.8% | 0.076 (n=7) | -1,065.91 | -19.74 |
| R2: prior-day NIFTY range >=1.1% | blocked | 53 | 1,677.04 | 31.64 | 49.1% | -0.073 (n=6) | -2,056.79 | -39.55 |

#### 12-Nov to 17-Nov
| Rule | Set | Trades | Net INR | Mean net INR/trade | Win rate | Mean net R (risk n) | Net ex-best INR | Mean ex-best INR/trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1: range-so-far >=0.7% | baseline | 22 | -13,729.10 | -624.05 | 40.9% | -0.335 (n=22) | -15,070.76 | -717.66 |
| R1: range-so-far >=0.7% | kept | 9 | -2,262.47 | -251.39 | 55.6% | -0.155 (n=9) | -3,442.72 | -430.34 |
| R1: range-so-far >=0.7% | blocked | 13 | -11,466.63 | -882.05 | 30.8% | -0.460 (n=13) | -12,808.29 | -1,067.36 |
| R2: prior-day NIFTY range >=1.1% | baseline | 22 | -13,729.10 | -624.05 | 40.9% | -0.335 (n=22) | -15,070.76 | -717.66 |
| R2: prior-day NIFTY range >=1.1% | kept | 6 | -1,094.81 | -182.47 | 66.7% | -0.075 (n=6) | -2,150.77 | -430.15 |
| R2: prior-day NIFTY range >=1.1% | blocked | 16 | -12,634.29 | -789.64 | 31.2% | -0.433 (n=16) | -13,975.95 | -931.73 |

#### First 10 dates (2026-10-14 to 2026-10-29)
| Rule | Set | Trades | Net INR | Mean net INR/trade | Win rate | Mean net R (risk n) | Net ex-best INR | Mean ex-best INR/trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1: range-so-far >=0.7% | baseline | 74 | -1,087.50 | -14.70 | 41.9% | NA (n=0) | -4,821.33 | -66.05 |
| R1: range-so-far >=0.7% | kept | 61 | -368.51 | -6.04 | 41.0% | NA (n=0) | -4,102.34 | -68.37 |
| R1: range-so-far >=0.7% | blocked | 13 | -718.99 | -55.31 | 46.2% | NA (n=0) | -1,848.33 | -154.03 |
| R2: prior-day NIFTY range >=1.1% | baseline | 74 | -1,087.50 | -14.70 | 41.9% | NA (n=0) | -4,821.33 | -66.05 |
| R2: prior-day NIFTY range >=1.1% | kept | 30 | -2,195.74 | -73.19 | 36.7% | NA (n=0) | -3,825.48 | -131.91 |
| R2: prior-day NIFTY range >=1.1% | blocked | 44 | 1,108.24 | 25.19 | 45.5% | NA (n=0) | -2,625.59 | -61.06 |

#### Second 11 dates (2026-10-30 to 2026-11-17)
| Rule | Set | Trades | Net INR | Mean net INR/trade | Win rate | Mean net R (risk n) | Net ex-best INR | Mean ex-best INR/trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1: range-so-far >=0.7% | baseline | 56 | -8,293.98 | -148.11 | 48.2% | -0.208 (n=35) | -12,030.47 | -218.74 |
| R1: range-so-far >=0.7% | kept | 38 | 2,390.80 | 62.92 | 52.6% | -0.054 (n=20) | -1,345.69 | -36.37 |
| R1: range-so-far >=0.7% | blocked | 18 | -10,684.78 | -593.60 | 38.9% | -0.413 (n=15) | -12,026.44 | -707.44 |
| R2: prior-day NIFTY range >=1.1% | baseline | 56 | -8,293.98 | -148.11 | 48.2% | -0.208 (n=35) | -12,030.47 | -218.74 |
| R2: prior-day NIFTY range >=1.1% | kept | 31 | 3,771.51 | 121.66 | 51.6% | 0.006 (n=13) | 35.02 | 1.17 |
| R2: prior-day NIFTY range >=1.1% | blocked | 25 | -12,065.49 | -482.62 | 44.0% | -0.335 (n=22) | -13,423.51 | -559.31 |

#### All dates
| Rule | Set | Trades | Net INR | Mean net INR/trade | Win rate | Mean net R (risk n) | Net ex-best INR | Mean ex-best INR/trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1: range-so-far >=0.7% | baseline | 130 | -9,381.48 | -72.17 | 44.6% | -0.208 (n=35) | -13,117.97 | -101.69 |
| R1: range-so-far >=0.7% | kept | 99 | 2,022.29 | 20.43 | 45.5% | -0.054 (n=20) | -1,714.20 | -17.49 |
| R1: range-so-far >=0.7% | blocked | 31 | -11,403.77 | -367.86 | 41.9% | -0.413 (n=15) | -12,745.43 | -424.85 |
| R2: prior-day NIFTY range >=1.1% | baseline | 130 | -9,381.48 | -72.17 | 44.6% | -0.208 (n=35) | -13,117.97 | -101.69 |
| R2: prior-day NIFTY range >=1.1% | kept | 61 | 1,575.77 | 25.83 | 44.3% | 0.006 (n=13) | -2,160.72 | -36.01 |
| R2: prior-day NIFTY range >=1.1% | blocked | 69 | -10,957.25 | -158.80 | 44.9% | -0.335 (n=22) | -14,691.08 | -216.05 |

#### Revised PASS checks (the two requested periods)

| Rule | Period | Kept mean INR | Blocked mean INR | Kept net INR | Baseline net INR | Result |
| --- | --- | --- | --- | --- | --- | --- |
| R1: range-so-far >=0.7% | 14-Oct to 11-Nov | 47.61 | 3.49 | 4,284.76 | 4,347.62 | FAIL |
| R1: range-so-far >=0.7% | 12-Nov to 17-Nov | -251.39 | -882.05 | -2,262.47 | -13,729.10 | PASS |
| R2: prior-day NIFTY range >=1.1% | 14-Oct to 11-Nov | 48.56 | 31.64 | 2,670.58 | 4,347.62 | FAIL |
| R2: prior-day NIFTY range >=1.1% | 12-Nov to 17-Nov | -182.47 | -789.64 | -1,094.81 | -13,729.10 | PASS |

- Rule-level A result: R1: range-so-far >=0.7%: FAIL; R2: prior-day NIFTY range >=1.1%: FAIL. A passes overall only if at least one rule passes both periods.
- R2 blocks 23 trades because their prior-day NIFTY range is unavailable.

### Fixed-simulator 51-trade window (30-Oct–16-Nov)

- Cohort size: 51. Mean net R uses only trades with recorded planned risk: 30/51; no risk is inferred.

| Rule | Set | Trades | Net INR | Mean net INR/trade | Mean net R (risk n) |
| --- | --- | --- | --- | --- | --- |
| R1: range-so-far >=0.7% | kept | 35 | 3,558.46 | 101.67 | -0.008 (n=17) |
| R1: range-so-far >=0.7% | blocked | 16 | -8,829.11 | -551.82 | -0.389 (n=13) |
| R2: prior-day NIFTY range >=1.1% | kept | 31 | 3,771.51 | 121.66 | 0.006 (n=13) |
| R2: prior-day NIFTY range >=1.1% | blocked | 20 | -9,042.16 | -452.11 | -0.310 (n=17) |

### Daily fee reconciliation

| Date | Trades | Gross INR | Fees INR | Net INR | Fee source |
| --- | --- | --- | --- | --- | --- |
| 2026-10-14 | 7 | -1,264.00 | 582.05 | -1,846.05 | 0 recorded / 7 recomputed |
| 2026-10-15 | 10 | 7,079.50 | 811.69 | 6,267.81 | 0 recorded / 10 recomputed |
| 2026-10-16 | 14 | -2,690.75 | 1,044.92 | -3,735.67 | 0 recorded / 14 recomputed |
| 2026-10-19 | 7 | -455.00 | 486.14 | -941.14 | 0 recorded / 7 recomputed |
| 2026-10-21 | 10 | -2,193.75 | 627.78 | -2,821.53 | 0 recorded / 10 recomputed |
| 2026-10-22 | 7 | 1,164.00 | 457.10 | 706.90 | 0 recorded / 7 recomputed |
| 2026-10-23 | 8 | 898.00 | 479.84 | 418.16 | 0 recorded / 8 recomputed |
| 2026-10-26 | 7 | 1,324.75 | 416.92 | 907.83 | 0 recorded / 7 recomputed |
| 2026-10-28 | 2 | 168.00 | 137.01 | 30.99 | 0 recorded / 2 recomputed |
| 2026-10-29 | 2 | 45.50 | 120.30 | -74.80 | 0 recorded / 2 recomputed |
| 2026-10-30 | 1 | 893.75 | 70.73 | 823.02 | 0 recorded / 1 recomputed |
| 2026-11-03 | 3 | 2,025.00 | 257.18 | 1,767.82 | 0 recorded / 3 recomputed |
| 2026-11-04 | 4 | 1,992.50 | 333.92 | 1,658.58 | 0 recorded / 4 recomputed |
| 2026-11-05 | 3 | -2,842.50 | 248.53 | -3,091.03 | 0 recorded / 3 recomputed |
| 2026-11-06 | 10 | 5,344.50 | 822.67 | 4,521.83 | 0 recorded / 10 recomputed |
| 2026-11-09 | 7 | 1,531.50 | 577.58 | 953.92 | 0 recorded / 7 recomputed |
| 2026-11-11 | 6 | -687.50 | 511.52 | -1,199.02 | 6 recorded / 0 recomputed |
| 2026-11-12 | 6 | -528.50 | 566.31 | -1,094.81 | 6 recorded / 0 recomputed |
| 2026-11-13 | 4 | -3,332.50 | 298.02 | -3,630.52 | 4 recorded / 0 recomputed |
| 2026-11-16 | 7 | -5,352.75 | 627.69 | -5,980.44 | 7 recorded / 0 recomputed |
| 2026-11-17 | 5 | -2,595.50 | 427.83 | -3,023.33 | 5 recorded / 0 recomputed |

## B. 30% pullback entry on Test B episodes

- Burst is the signed move over the prior 15 completed 1-minute bars. Non-positive directional bursts are not eligible. The first 30%-retrace touch within 20 minutes triggers; entry is the next 1-minute bar open.
- Minute bars cannot resolve sub-minute sequencing: scan starts at the first full bar after the signal minute (or the signal minute if the signal is exactly on its boundary). Forward moves are signed from entry open to the close 15/30/60 elapsed minutes later. ATR is the preceding 14 completed true ranges.
- 95% percentile bootstrap intervals use 10,000 resamples of triggered episodes. The original Test B random-baseline point means are reused from `test_b_summary.csv`; random draw-level observations were not retained, so this report does not claim a new baseline CI.
- Episodes: 587; retracement-triggered: 367; entered on next bar: 366; status counts: no_30pct_retrace_within_20m=154, no_positive_15m_burst=66, trigger_no_next_minute_bar=1, triggered=366.

### Outcomes by period and tier

| Period / tier | Episodes | Triggered | Entered | Horizon | n | Mean % | 95% CI % | Mean ATR | 95% CI ATR | Hit rate | 95% CI hit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 14-Oct to 11-Nov / stock | 223 | 139 | 139 | 15 | 137 | 0.0354 | [-0.0129, 0.0853] | 0.213 | [-0.331, 0.766] | 53.3% | [45.3, 62.0] |
| 14-Oct to 11-Nov / stock | 223 | 139 | 139 | 30 | 133 | 0.0557 | [-0.0053, 0.1185] | 0.537 | [-0.217, 1.302] | 53.4% | [45.1, 61.7] |
| 14-Oct to 11-Nov / stock | 223 | 139 | 139 | 60 | 119 | 0.0590 | [-0.0344, 0.1561] | 0.442 | [-0.671, 1.566] | 52.1% | [43.7, 61.3] |
| 14-Oct to 11-Nov / NIFTY | 58 | 38 | 38 | 15 | 38 | 0.0327 | [-0.0014, 0.0661] | 0.872 | [-0.007, 1.783] | 63.2% | [47.4, 78.9] |
| 14-Oct to 11-Nov / NIFTY | 58 | 38 | 38 | 30 | 36 | 0.0197 | [-0.0357, 0.0757] | 0.726 | [-0.708, 2.189] | 50.0% | [33.3, 66.7] |
| 14-Oct to 11-Nov / NIFTY | 58 | 38 | 38 | 60 | 31 | 0.0083 | [-0.0947, 0.1078] | 0.858 | [-1.602, 3.327] | 58.1% | [41.9, 74.2] |
| 14-Oct to 11-Nov / BANKNIFTY | 48 | 24 | 24 | 15 | 24 | -0.0672 | [-0.1323, 0.0009] | -0.991 | [-2.211, 0.342] | 29.2% | [12.5, 45.8] |
| 14-Oct to 11-Nov / BANKNIFTY | 48 | 24 | 24 | 30 | 24 | -0.0368 | [-0.1565, 0.0857] | -0.625 | [-2.796, 1.645] | 45.8% | [25.0, 66.7] |
| 14-Oct to 11-Nov / BANKNIFTY | 48 | 24 | 24 | 60 | 24 | -0.0320 | [-0.1857, 0.1229] | -0.414 | [-3.325, 2.351] | 41.7% | [20.8, 62.5] |
| 12-Nov to 17-Nov / stock | 192 | 120 | 119 | 15 | 117 | -0.0080 | [-0.0385, 0.0218] | -0.007 | [-0.449, 0.454] | 48.7% | [40.2, 58.1] |
| 12-Nov to 17-Nov / stock | 192 | 120 | 119 | 30 | 113 | -0.0244 | [-0.0659, 0.0178] | -0.256 | [-0.885, 0.386] | 44.2% | [35.4, 53.1] |
| 12-Nov to 17-Nov / stock | 192 | 120 | 119 | 60 | 101 | -0.0404 | [-0.1015, 0.0229] | -0.482 | [-1.388, 0.433] | 44.6% | [34.7, 54.5] |
| 12-Nov to 17-Nov / NIFTY | 38 | 28 | 28 | 15 | 28 | 0.0294 | [0.0012, 0.0584] | 0.858 | [-0.024, 1.744] | 64.3% | [46.4, 82.1] |
| 12-Nov to 17-Nov / NIFTY | 38 | 28 | 28 | 30 | 27 | 0.0338 | [-0.0138, 0.0841] | 1.069 | [-0.378, 2.573] | 59.3% | [40.7, 77.8] |
| 12-Nov to 17-Nov / NIFTY | 38 | 28 | 28 | 60 | 24 | 0.0488 | [-0.0328, 0.1272] | 1.242 | [-1.291, 3.611] | 62.5% | [41.7, 83.3] |
| 12-Nov to 17-Nov / BANKNIFTY | 28 | 18 | 18 | 15 | 18 | 0.0302 | [-0.0259, 0.0894] | 0.660 | [-0.589, 1.925] | 61.1% | [38.9, 83.3] |
| 12-Nov to 17-Nov / BANKNIFTY | 28 | 18 | 18 | 30 | 17 | 0.0138 | [-0.0590, 0.0968] | 0.356 | [-1.364, 2.206] | 35.3% | [11.8, 58.8] |
| 12-Nov to 17-Nov / BANKNIFTY | 28 | 18 | 18 | 60 | 14 | -0.0463 | [-0.1340, 0.0468] | -1.240 | [-3.290, 0.895] | 28.6% | [7.1, 50.0] |

### Marginal outcomes by period and by tier

| Scope | Group | Episodes | Triggered | Entered | Horizon | n | Mean % | 95% CI % | Mean ATR | 95% CI ATR | Hit rate | 95% CI hit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| period | 14-Oct to 11-Nov | 329 | 201 | 201 | 15 | 199 | 0.0225 | [-0.0119, 0.0578] | 0.193 | [-0.251, 0.659] | 52.3% | [45.2, 59.3] |
| period | 14-Oct to 11-Nov | 329 | 201 | 201 | 30 | 193 | 0.0375 | [-0.0087, 0.0839] | 0.428 | [-0.223, 1.093] | 51.8% | [44.6, 59.1] |
| period | 14-Oct to 11-Nov | 329 | 201 | 201 | 60 | 174 | 0.0374 | [-0.0325, 0.1084] | 0.398 | [-0.568, 1.331] | 51.7% | [44.3, 59.2] |
| period | 12-Nov to 17-Nov | 258 | 166 | 165 | 15 | 163 | 0.0026 | [-0.0201, 0.0253] | 0.216 | [-0.169, 0.603] | 52.8% | [45.4, 60.1] |
| period | 12-Nov to 17-Nov | 258 | 166 | 165 | 30 | 157 | -0.0103 | [-0.0420, 0.0218] | 0.038 | [-0.526, 0.606] | 45.9% | [38.2, 53.5] |
| period | 12-Nov to 17-Nov | 258 | 166 | 165 | 60 | 139 | -0.0256 | [-0.0738, 0.0223] | -0.261 | [-1.095, 0.574] | 46.0% | [38.1, 54.7] |
| tier | stock | 415 | 259 | 258 | 15 | 254 | 0.0154 | [-0.0139, 0.0451] | 0.112 | [-0.254, 0.469] | 51.2% | [44.9, 57.5] |
| tier | stock | 415 | 259 | 258 | 30 | 246 | 0.0189 | [-0.0200, 0.0570] | 0.173 | [-0.333, 0.688] | 49.2% | [42.7, 55.3] |
| tier | stock | 415 | 259 | 258 | 60 | 220 | 0.0134 | [-0.0460, 0.0717] | 0.018 | [-0.715, 0.773] | 48.6% | [42.3, 55.5] |
| tier | NIFTY | 96 | 66 | 66 | 15 | 66 | 0.0313 | [0.0082, 0.0541] | 0.866 | [0.239, 1.525] | 63.6% | [51.5, 74.2] |
| tier | NIFTY | 96 | 66 | 66 | 30 | 63 | 0.0257 | [-0.0130, 0.0648] | 0.873 | [-0.138, 1.906] | 54.0% | [41.3, 65.1] |
| tier | NIFTY | 96 | 66 | 66 | 60 | 55 | 0.0260 | [-0.0441, 0.0934] | 1.026 | [-0.786, 2.773] | 60.0% | [47.3, 72.7] |
| tier | BANKNIFTY | 76 | 42 | 42 | 15 | 42 | -0.0255 | [-0.0735, 0.0242] | -0.284 | [-1.195, 0.681] | 42.9% | [28.6, 57.1] |
| tier | BANKNIFTY | 76 | 42 | 42 | 30 | 41 | -0.0158 | [-0.0932, 0.0645] | -0.218 | [-1.685, 1.312] | 41.5% | [26.8, 56.1] |
| tier | BANKNIFTY | 76 | 42 | 42 | 60 | 38 | -0.0372 | [-0.1417, 0.0636] | -0.718 | [-2.694, 1.240] | 36.8% | [21.1, 52.6] |

### Existing Test B random baseline

Baseline references are shown separately by period and by tier, as persisted in the Test B summary.

| Dimension | Group | Horizon | Episodes | Signal mean % | Random mean % | Signal ATR | Random ATR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| period | 12-Nov to 17-Nov | 15 | 258 | 0.0236 | 0.0101 | 0.509 | 0.186 |
| period | 12-Nov to 17-Nov | 30 | 258 | -0.0050 | 0.0158 | 0.092 | 0.285 |
| period | 12-Nov to 17-Nov | 60 | 258 | -0.0130 | 0.0248 | -0.176 | 0.415 |
| period | 14-Oct to 11-Nov | 15 | 329 | 0.0294 | 0.0265 | 0.339 | 0.354 |
| period | 14-Oct to 11-Nov | 30 | 329 | 0.0344 | 0.0504 | 0.503 | 0.690 |
| period | 14-Oct to 11-Nov | 60 | 329 | 0.0206 | 0.0899 | 0.326 | 1.183 |
| tier | BANKNIFTY | 15 | 76 | 0.0076 | 0.0075 | 0.273 | 0.128 |
| tier | BANKNIFTY | 30 | 76 | 0.0043 | 0.0154 | 0.136 | 0.242 |
| tier | BANKNIFTY | 60 | 76 | 0.0065 | 0.0284 | 0.162 | 0.410 |
| tier | NIFTY | 15 | 96 | 0.0208 | 0.0112 | 0.614 | 0.361 |
| tier | NIFTY | 30 | 96 | 0.0181 | 0.0228 | 0.688 | 0.715 |
| tier | NIFTY | 60 | 96 | -0.0004 | 0.0434 | 0.365 | 1.234 |
| tier | stock | 15 | 415 | 0.0319 | 0.0233 | 0.393 | 0.289 |
| tier | stock | 30 | 415 | 0.0191 | 0.0417 | 0.269 | 0.514 |
| tier | stock | 60 | 415 | 0.0076 | 0.0714 | 0.041 | 0.835 |

### B PASS check by period

The 60-minute break-even comparator is weighted by the triggered 60-minute outcomes' tier mix.

| Period | Triggered | Entered | n30 | Mean30% | CI low30 | Base30% | CI>base | n60 | Mean60% | CI low60 | Base60% | CI>base | Weighted BE% | Mean60>BE | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 14-Oct to 11-Nov | 201 | 201 | 193 | 0.0375 | -0.0087 | 0.0504 | no | 174 | 0.0374 | -0.0325 | 0.0899 | no | 0.0368 | yes | FAIL |
| 12-Nov to 17-Nov | 166 | 165 | 157 | -0.0103 | -0.0420 | 0.0158 | no | 139 | -0.0256 | -0.0738 | 0.0248 | no | 0.0382 | no | FAIL |

- B overall: FAIL (both period conditions must pass).

## C. Break-even from modeled fees and observed spreads

- Spread cost is midpoint-based round-trip crossing cost: half the entry spread plus half the exit spread, times option quantity. Modeled round-trip fees are added. Underlying points = total cost / (0.5 delta × option units), using recorded lot size and lot count; percentage uses the last completed underlying close before entry as spot proxy.
- Complete entry/exit spread and spot samples: 45 trades. Quote coverage is limited; per-trade inputs and counts are in `c_break_even_trade_inputs.csv` and `c_break_even_by_tier.csv`.

| Tier | Trades | Mean lot | Entry spread pts | Exit spread pts | Fees/lot INR | Spread/lot INR | Total/lot INR | BE points | BE % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| stock | 36 | 412.5 | 0.238 | 0.228 | 65.01 | 74.58 | 139.59 | 0.864 | 0.0477 |
| NIFTY | 3 | 65.0 | 0.333 | 0.300 | 66.54 | 20.58 | 87.12 | 2.681 | 0.0107 |
| BANKNIFTY | 6 | 30.0 | 1.775 | 2.250 | 89.26 | 60.38 | 149.63 | 9.975 | 0.0166 |

### Forward moves versus break-even

All moves are signed underlying returns, not option P&L. ORB means use index signals through 17-Nov; 18-Nov is excluded.

| Tier | Min | BE % | Test B mean % | Test B baseline % | Test B ATR | ORB mean % | ORB ATR | Pullback all % | Pullback 14Oct-11Nov % | Pullback 12Nov-17Nov % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| stock | 15 | 0.0477 | 0.0319 | 0.0233 | 0.393 | NA | NA | 0.0154 | 0.0354 | -0.0080 |
| stock | 30 | 0.0477 | 0.0191 | 0.0417 | 0.269 | NA | NA | 0.0189 | 0.0557 | -0.0244 |
| stock | 60 | 0.0477 | 0.0076 | 0.0714 | 0.041 | NA | NA | 0.0134 | 0.0590 | -0.0404 |
| NIFTY | 15 | 0.0107 | 0.0208 | 0.0112 | 0.614 | 0.0307 | 0.123 | 0.0313 | 0.0327 | 0.0294 |
| NIFTY | 30 | 0.0107 | 0.0181 | 0.0228 | 0.688 | -0.0061 | -0.524 | 0.0257 | 0.0197 | 0.0338 |
| NIFTY | 60 | 0.0107 | -0.0004 | 0.0434 | 0.365 | 0.0143 | -0.341 | 0.0260 | 0.0083 | 0.0488 |
| BANKNIFTY | 15 | 0.0166 | 0.0076 | 0.0075 | 0.273 | -0.0210 | -0.461 | -0.0255 | -0.0672 | 0.0302 |
| BANKNIFTY | 30 | 0.0166 | 0.0043 | 0.0154 | 0.136 | 0.0209 | 0.083 | -0.0158 | -0.0368 | 0.0138 |
| BANKNIFTY | 60 | 0.0166 | 0.0065 | 0.0284 | 0.162 | -0.0670 | -0.991 | -0.0372 | -0.0320 | -0.0463 |

## E. Optional India VIX

Not run; the requested VPS/Kite credential environment is outside this local archived-data replay.

## Verdict and stop rule

- A regime gate: FAIL (at least one of R1/R2 must pass both required periods).
- B pullback: FAIL.

**No tested price-based entry signal beats costs** under these tests.
Still untested: India VIX gating; other retracement fractions and wait windows; alternative confirmation/exit rules; broader out-of-sample dates and market regimes; and live fill/market-impact costs beyond modeled fees and observed spreads.

Late-period caution: 12-Nov–17-Nov has 22 trades across 4 dates.
