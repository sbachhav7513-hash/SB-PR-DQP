# Index Trend-Strength Edge Study

History source: KiteHistoricalProvider one-minute NIFTY and BANKNIFTY spot history, 2015-01-09 through 2026-11-23. The regime gate is not applied.

## History coverage

| Underlying | First date | Last date | Sessions | Bars | Days with missing minutes |
| --- | --- | --- | ---: | ---: | --- |
| NIFTY | 2015-01-09 | 2026-11-23 | 2930 | 1097089 | 2015-01-19 (11), 2015-03-13 (20), 2015-03-16 (20), 2015-07-20 (5), 2015-08-24 (4), 2015-09-02 (8), 2015-09-07 (8), 2015-09-16 (1), 2015-09-18 (1), 2015-09-23 (2), 2015-12-22 (18), 2017-02-21 (39), 2019-04-18 (3), 2019-08-02 (1), 2019-09-18 (1), 2019-09-23 (14), 2020-02-13 (1), 2020-03-04 (1), 2020-08-27 (2), 2020-11-02 (1), 2021-02-24 (321), 2021-12-20 (1), 2022-03-07 (3), 2023-06-05 (1), 2023-06-14 (7), 2023-07-12 (1), 2023-07-24 (3), 2023-08-07 (1), 2024-03-02 (270), 2024-04-23 (6), 2024-05-18 (270), 2025-10-21 (315), 2026-11-08 (305) |
| BANKNIFTY | 2015-01-09 | 2026-11-23 | 2930 | 1097042 | 2015-01-19 (11), 2015-03-13 (20), 2015-03-16 (20), 2015-07-20 (5), 2015-08-24 (4), 2015-09-02 (6), 2015-09-07 (8), 2015-09-16 (2), 2015-09-18 (1), 2015-09-23 (2), 2015-12-22 (18), 2017-02-21 (39), 2019-04-18 (3), 2019-08-02 (1), 2019-09-18 (1), 2019-09-23 (14), 2020-02-13 (1), 2020-03-04 (1), 2020-08-27 (2), 2020-11-02 (1), 2021-02-24 (321), 2021-12-20 (1), 2022-03-07 (50), 2023-06-05 (1), 2023-06-14 (7), 2023-07-12 (1), 2023-07-24 (3), 2023-08-07 (1), 2024-03-02 (270), 2024-04-23 (6), 2024-05-18 (270), 2025-10-21 (315), 2025-12-15 (1), 2026-11-08 (305) |

Missing-minute counts compare observed timestamps with 375 regular-session minute slots (09:15-15:29). Shortened/special trading sessions are also listed as incomplete; calendar dates with no bars are not classified as holidays or missing sessions.

## Method

Thresholds are the training-period p50/p60/p70/p80/p90/p95 of absolute close-to-close 20-bar strength. Days are split chronologically 70% train / 30% OOS; thresholds are learned only from train days. Signals are produced by score_market using the active paper scoring configuration, with the regime hard gate disabled; threshold levels are then applied to the signal set. A 15-minute same-direction cooldown is applied. Forward returns use the exact +15/+30-minute close on the same session. Random controls shuffle signs within each day while preserving that day's BUY/SELL ratio. CIs resample trading days (2000 bootstrap replicates over active signal days); differences are signal mean minus random mean. Returns and CI bounds are percentages.

## Paper option round-trip costs

Spread cost is half the observed entry spread plus half the observed exit spread, multiplied by filled quantity; modeled journal fees are added and divided by entry premium times quantity. Only closed trades with fee and consistent entry/exit bid-ask snapshots are included.

The edge returns are underlying spot returns, while the cost percentage uses option premium; these are a friction-scale comparison, not direct option P&L or a break-even calculation.

| Underlying | Average cost (% entry premium) | Median | Trades used / closed | Modeled-fee coverage | Quoted round-trip coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| NIFTY | 0.890% | 0.890% | 2 / 14 | 2 / 14 | 2 / 14 |
| BANKNIFTY | 0.846% | 0.803% | 5 / 16 | 5 / 16 | 5 / 16 |

## NIFTY

Training: 2015-01-09 to 2023-05-08 (2051 sessions).

| Train pctl | Threshold | Signals/day | n(+15/+30) | Signal mean +15 | Signal hit +15 | Random mean +15 | Random hit +15 | Delta +15 95% CI | Signal mean +30 | Signal hit +30 | Random mean +30 | Random hit +30 | Delta +30 95% CI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p50 | 0.077% | 13.04 | 25207/23868 | 0.001% | 47.685% | 0.002% | 50.601% | [-0.004%, 0.001%] | 0.003% | 48.441% | 0.012% | 52.707% | [-0.013%, -0.006%] |
| p60 | 0.099% | 11.31 | 21864/20600 | 0.001% | 47.722% | 0.005% | 50.997% | [-0.007%, -0.001%] | 0.003% | 48.374% | 0.011% | 52.393% | [-0.012%, -0.003%] |
| p70 | 0.128% | 9.25 | 17837/16728 | 0.002% | 47.671% | 0.007% | 51.920% | [-0.009%, -0.002%] | 0.004% | 48.697% | 0.017% | 52.917% | [-0.018%, -0.008%] |
| p80 | 0.169% | 6.67 | 12839/11908 | 0.003% | 47.675% | 0.007% | 51.507% | [-0.009%, 0.001%] | 0.006% | 48.715% | 0.019% | 52.712% | [-0.019%, -0.006%] |
| p90 | 0.245% | 3.52 | 6808/6214 | 0.006% | 49.148% | 0.009% | 51.439% | [-0.011%, 0.004%] | 0.009% | 49.421% | 0.022% | 52.462% | [-0.024%, -0.002%] |
| p95 | 0.330% | 1.77 | 3429/3104 | 0.008% | 48.936% | 0.012% | 50.335% | [-0.017%, 0.008%] | 0.015% | 49.581% | 0.029% | 53.447% | [-0.032%, 0.004%] |

Out of sample: 2023-05-09 to 2026-11-23 (879 sessions).

| Train pctl | Threshold | Signals/day | n(+15/+30) | Signal mean +15 | Signal hit +15 | Random mean +15 | Random hit +15 | Delta +15 95% CI | Signal mean +30 | Signal hit +30 | Random mean +30 | Random hit +30 | Delta +30 95% CI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p50 | 0.077% | 11.61 | 9793/9258 | 0.001% | 48.004% | 0.004% | 51.537% | [-0.006%, 0.000%] | 0.003% | 48.704% | 0.010% | 53.402% | [-0.011%, -0.002%] |
| p60 | 0.099% | 9.57 | 8089/7623 | 0.001% | 48.350% | 0.006% | 51.675% | [-0.008%, -0.001%] | 0.003% | 48.721% | 0.009% | 52.709% | [-0.011%, -0.000%] |
| p70 | 0.128% | 7.17 | 6064/5693 | 0.003% | 48.829% | 0.004% | 51.435% | [-0.005%, 0.003%] | 0.005% | 49.376% | 0.013% | 53.083% | [-0.014%, -0.001%] |
| p80 | 0.169% | 4.57 | 3878/3628 | 0.006% | 49.381% | 0.005% | 50.284% | [-0.005%, 0.007%] | 0.007% | 49.614% | 0.016% | 53.418% | [-0.017%, -0.001%] |
| p90 | 0.245% | 2.04 | 1741/1618 | 0.009% | 49.627% | 0.009% | 50.890% | [-0.010%, 0.010%] | 0.013% | 50.247% | 0.024% | 53.523% | [-0.022%, -0.000%] |
| p95 | 0.330% | 0.88 | 755/709 | 0.003% | 48.609% | -0.008% | 47.550% | [-0.008%, 0.034%] | 0.012% | 47.673% | 0.020% | 53.032% | [-0.038%, 0.028%] |

## BANKNIFTY

Training: 2015-01-09 to 2023-05-08 (2051 sessions).

| Train pctl | Threshold | Signals/day | n(+15/+30) | Signal mean +15 | Signal hit +15 | Random mean +15 | Random hit +15 | Delta +15 95% CI | Signal mean +30 | Signal hit +30 | Random mean +30 | Random hit +30 | Delta +30 95% CI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p50 | 0.105% | 13.12 | 25288/24006 | -0.000% | 46.042% | 0.009% | 51.613% | [-0.013%, -0.006%] | 0.004% | 46.926% | 0.023% | 53.337% | [-0.023%, -0.013%] |
| p60 | 0.136% | 11.40 | 21950/20766 | -0.000% | 46.064% | 0.007% | 51.121% | [-0.011%, -0.003%] | 0.006% | 47.274% | 0.017% | 52.875% | [-0.017%, -0.005%] |
| p70 | 0.176% | 9.23 | 17716/16729 | 0.002% | 46.523% | 0.007% | 51.197% | [-0.009%, 0.001%] | 0.010% | 47.959% | 0.024% | 52.585% | [-0.020%, -0.007%] |
| p80 | 0.237% | 6.59 | 12631/11863 | 0.004% | 46.964% | 0.011% | 51.777% | [-0.013%, -0.000%] | 0.014% | 48.099% | 0.023% | 52.381% | [-0.018%, -0.001%] |
| p90 | 0.351% | 3.46 | 6657/6173 | 0.011% | 48.025% | 0.020% | 52.366% | [-0.020%, 0.002%] | 0.024% | 49.425% | 0.027% | 52.892% | [-0.017%, 0.011%] |
| p95 | 0.481% | 1.71 | 3311/3060 | 0.023% | 49.079% | 0.033% | 52.643% | [-0.029%, 0.013%] | 0.045% | 51.046% | 0.047% | 53.203% | [-0.025%, 0.021%] |

Out of sample: 2023-05-09 to 2026-11-23 (879 sessions).

| Train pctl | Threshold | Signals/day | n(+15/+30) | Signal mean +15 | Signal hit +15 | Random mean +15 | Random hit +15 | Delta +15 95% CI | Signal mean +30 | Signal hit +30 | Random mean +30 | Random hit +30 | Delta +30 95% CI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| p50 | 0.105% | 10.96 | 9260/8792 | 0.001% | 46.771% | 0.006% | 52.095% | [-0.010%, -0.001%] | -0.000% | 47.054% | 0.012% | 51.899% | [-0.018%, -0.006%] |
| p60 | 0.136% | 8.72 | 7353/6974 | 0.002% | 47.028% | 0.006% | 51.163% | [-0.009%, 0.002%] | 0.001% | 47.276% | 0.014% | 52.151% | [-0.019%, -0.006%] |
| p70 | 0.176% | 6.19 | 5193/4898 | 0.004% | 48.103% | 0.007% | 50.799% | [-0.009%, 0.003%] | 0.005% | 48.224% | 0.015% | 53.287% | [-0.019%, -0.002%] |
| p80 | 0.237% | 3.70 | 3104/2922 | 0.006% | 49.130% | 0.010% | 51.514% | [-0.014%, 0.004%] | 0.004% | 48.426% | 0.020% | 52.806% | [-0.027%, -0.005%] |
| p90 | 0.351% | 1.40 | 1188/1117 | 0.002% | 48.822% | 0.008% | 51.347% | [-0.018%, 0.008%] | -0.002% | 49.150% | 0.014% | 51.835% | [-0.035%, 0.005%] |
| p95 | 0.481% | 0.52 | 436/414 | -0.001% | 48.853% | 0.001% | 47.936% | [-0.031%, 0.027%] | -0.015% | 48.068% | 0.023% | 50.966% | [-0.073%, -0.000%] |
