# Opening-Range Breakout Underlying Replay

## Method

- Universe: NIFTY and BANKNIFTY archived 1-minute underlying candles from 14-Oct-2026 through 18-Nov-2026.
- Opening range: 09:15:00 through 09:29:59 inclusive for each date. The range high/low are candle extremes.
- 5-minute close: resampled completed 5-minute closes after 09:30. The first close beyond the range defines the one signal for that index/date.
- Forward move: signed close-to-close move from the signal close at 15, 30, 60, and 120 minutes. Positive means movement in the breakout direction. Percent move and ATR units use a 14-bar mean true range ending at the signal timestamp.
- Excursions: favorable uses the favorable extreme of the high/low path within 120 minutes; adverse uses the adverse extreme. Both are signed favorable/adverse magnitudes in percent and ATR units.
- Baseline: 1,000 random minute timestamps on the same index/date and in the same breakout direction, subject to sufficient forward and 120-minute data. The baseline uses the same horizons and ATR method.
- Intervals: 95% percentile bootstrap intervals for signal and baseline means; 5,000 draws. Bootstrap intervals for hit-rate use 5,000 draws.
- Archive absence: missing weekdays are 20-Oct-2026, 10-Nov-2026, and 18-Nov-2026.

## Coverage

| Index | Archived weekdays | Signals | Days with no breakout signal |
|---|---:|---:|---:|
| NIFTY | 23 | 23 | 0 |
| BANKNIFTY | 23 | 22 | 1 (19-Oct-2026) |

The NIFTY signal on 04-Nov-2026 is a late 15:30 close and has no 15/30/60/120-minute forward observations. The BANKNIFTY signal on 26-Oct-2026 is likewise late at 15:30 and has no forward observations.

## Headline verdict

The breakout is **not a demonstrated robust edge** against the random-timestamp baseline. NIFTY beats random in percent terms at 15 minutes and 60 minutes across all data, and in both percent and ATR terms at 15 minutes overall and in the first period. BANKNIFTY does not beat random at 15/30/60/120 minutes overall. In the second period, BANKNIFTY does beat random at 30 minutes in percent and ATR terms, but the 4-signal sample is too small for a stable conclusion.

## Summary: all data

| Index | Horizon | Hit rate | Hit 95% CI | Mean move % | Mean % 95% CI | Random mean % | Mean move ATR | Mean ATR 95% CI | Random mean ATR | Beats random % | Beats random ATR |
|---|---:|---:|---|---:|---|---:|---:|---|---:|---|---|
| NIFTY | 15m | 59.09% | 36.36%-77.27% | 0.0307% | -0.0432%-0.1116% | 0.005945% | 0.1228 | -0.9119-1.1267 | 0.06775 | Yes | Yes |
| NIFTY | 30m | 54.55% | 36.36%-77.27% | -0.00614% | -0.1224%-0.1041% | 0.007088% | -0.5244 | -2.1330-0.9952 | 0.10477 | No | No |
| NIFTY | 60m | 63.64% | 45.45%-81.82% | 0.01425% | -0.1493%-0.1804% | 0.006721% | -0.3410 | -2.6406-1.8602 | 0.14869 | Yes | No |
| NIFTY | 120m | 54.55% | 31.82%-77.27% | -0.02255% | -0.2260%-0.1905% | 0.019488% | -0.5074 | -3.5604-2.2343 | 0.42278 | No | No |
| BANKNIFTY | 15m | 33.33% | 14.29%-52.38% | -0.02103% | -0.08761%-0.05338% | 0.015216% | -0.4612 | -1.3975-0.5418 | 0.23439 | No | No |
| BANKNIFTY | 30m | 52.38% | 28.57%-71.43% | 0.02089% | -0.10635%-0.15558% | 0.023120% | 0.08312 | -1.6959-1.9451 | 0.40702 | No | No |
| BANKNIFTY | 60m | 38.10% | 19.05%-57.14% | -0.06700% | -0.24053%-0.10323% | 0.030132% | -0.9912 | -3.2836-1.3876 | 0.63474 | No | No |
| BANKNIFTY | 120m | 38.10% | 19.05%-57.14% | -0.06271% | -0.29137%-0.16288% | 0.055824% | -0.9431 | -3.8928-1.9892 | 1.06212 | No | No |

## Excursions within 120 minutes

| Index | Period | MFE mean % | MFE 95% CI | MFE mean ATR | MFE ATR 95% CI | MAE mean % | MAE 95% CI | MAE mean ATR | MAE ATR 95% CI |
|---|---|---:|---|---:|---|---:|---|---:|---|
| NIFTY | All | 0.3402% | 0.2335%-0.4653% | 4.7983 | 3.4922-6.2197 | 0.3451% | 0.2310%-0.4704% | 5.2259 | 3.5426-7.1967 |
| NIFTY | 14-Oct to 11-Nov | 0.3774% | 0.2588%-0.5165% | 5.1090 | 3.6718-6.6541 | 0.3547% | 0.2276%-0.5010% | 5.0443 | 3.2310-7.2746 |
| NIFTY | 12-Nov to 18-Nov | 0.1727% | 0.0548%-0.3280% | 3.4003 | 1.1017-6.3676 | 0.3017% | 0.1193%-0.4892% | 6.0432 | 2.3720-9.7717 |
| BANKNIFTY | All | 0.3208% | 0.2045%-0.4479% | 4.2428 | 2.8215-5.8204 | 0.4256% | 0.2973%-0.5760% | 5.8510 | 3.9744-7.9766 |
| BANKNIFTY | 14-Oct to 11-Nov | 0.3247% | 0.1975%-0.4691% | 4.1490 | 2.5794-5.7207 | 0.4573% | 0.3012%-0.6314% | 6.1031 | 3.9204-8.6031 |
| BANKNIFTY | 12-Nov to 18-Nov | 0.1829% | -0.2432%-0.6168% | 2.1760 | -5.1303-9.2458 | 0.1691% | -0.0260%-0.3928% | 2.3142 | -0.9149-6.1489 |

## Period split

### 14-Oct to 11-Nov

| Index | Signals | 15m hit | 15m mean % | 15m mean ATR | 30m mean % | 30m mean ATR | 60m mean % | 60m mean ATR | 120m mean % | 120m mean ATR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | 19 | 61.11% | 0.04214% | 0.2446 | 0.002486% | -0.4380 | 0.03811% | -0.0020 | 0.007857% | 0.1067 |
| BANKNIFTY | 18 | 29.41% | -0.02814% | -0.5580 | -0.004686% | -0.2749 | -0.06576% | -0.8923 | -0.09189% | -1.3662 |

NIFTY beats random at 15 minutes in percent and ATR in this period. BANKNIFTY beats no random forward horizon in this period.

### 12-Nov to 18-Nov

| Index | Signals | 15m hit | 15m mean % | 15m mean ATR | 30m mean % | 30m mean ATR | 60m mean % | 60m mean ATR | 120m mean % | 120m mean ATR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIFTY | 4 | 50.00% | -0.02095% | -0.4251 | -0.04493% | -0.9134 | -0.09312% | -1.8667 | -0.15936% | -3.2711 |
| BANKNIFTY | 4 | 50.00% | 0.009219% | -0.04993 | 0.12958% | 1.6049 | -0.07231% | -1.4113 | 0.06128% | 0.8549 |

BANKNIFTY beats random at 30 minutes in percent and ATR in this period. NIFTY beats random at no forward horizon here.

## Archives missing

No archive directory existed for:

- 20-Oct-2026
- 10-Nov-2026
- 18-Nov-2026

There is a BANKNIFTY archive but no breakout on 19-Oct-2026.
