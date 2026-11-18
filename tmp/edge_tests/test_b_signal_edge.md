# Test B - Signal edge on the underlying

Directional rows: 3989. Clustered episodes: 587.
Clustering: same date, symbol, and side, first signal of each 15-minute contiguous episode.
Move uses the next completed minute bar and is signed for BUY/SELL direction. ATR is a 14-bar mean true range ending at the signal timestamp.
Baseline: 1,000 random timestamp draws per symbol/day/direction/time bucket.
Bootstrap intervals are 95% percentile intervals for episode means.

## Plain verdict
- 5 minutes: accepted does not beat baseline.
- 15 minutes: accepted beats baseline.
- 30 minutes: accepted does not beat baseline.
- 60 minutes: accepted does not beat baseline.

Rejected-gate verdict: at least one rejected gate beats baseline.

## Summary

| dimension | group | horizon_min | episodes | mean_pct | hit_rate_pct | pct_ci_low | pct_ci_high | mean_atr | atr_ci_low | atr_ci_high | baseline_mean_pct | baseline_mean_atr | beats_pct_baseline | beats_atr_baseline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| accepted_vs_rejected | False | 5 | 405 | 0.0096 | 51.24 | -0.0008 | 0.0209 | 0.1677 | 0.0156 | 0.3259 | 0.0051 | 0.0962 | True | True |
| accepted_vs_rejected | False | 15 | 405 | 0.0248 | 56.17 | 0.0042 | 0.0453 | 0.4606 | 0.1381 | 0.7525 | 0.0148 | 0.2573 | True | True |
| accepted_vs_rejected | False | 30 | 405 | 0.0135 | 50.39 | -0.0157 | 0.0426 | 0.3978 | -0.0497 | 0.8451 | 0.0264 | 0.4521 | False | False |
| accepted_vs_rejected | False | 60 | 405 | 0.0099 | 50.43 | -0.0307 | 0.0483 | 0.2786 | -0.3899 | 0.9212 | 0.0453 | 0.7517 | False | False |
| accepted_vs_rejected | True | 5 | 182 | 0.009 | 46.41 | -0.0113 | 0.029 | 0.1171 | -0.128 | 0.3594 | 0.0099 | 0.1111 | False | True |
| accepted_vs_rejected | True | 15 | 182 | 0.0313 | 53.59 | -0.0022 | 0.0654 | 0.3113 | -0.0733 | 0.7011 | 0.0292 | 0.3314 | True | False |
| accepted_vs_rejected | True | 30 | 182 | 0.0246 | 50.57 | -0.0217 | 0.0735 | 0.1531 | -0.4346 | 0.7504 | 0.0548 | 0.6441 | False | False |
| accepted_vs_rejected | True | 60 | 182 | -0.0017 | 45.68 | -0.068 | 0.0677 | -0.249 | -1.0484 | 0.5583 | 0.0968 | 1.0543 | False | False |
| first_failed_gate | accepted | 5 | 182 | 0.009 | 46.41 | -0.0113 | 0.029 | 0.1171 | -0.128 | 0.3594 | 0.0099 | 0.1111 | False | True |
| first_failed_gate | accepted | 15 | 182 | 0.0313 | 53.59 | -0.0022 | 0.0654 | 0.3113 | -0.0733 | 0.7011 | 0.0292 | 0.3314 | True | False |
| first_failed_gate | accepted | 30 | 182 | 0.0246 | 50.57 | -0.0217 | 0.0735 | 0.1531 | -0.4346 | 0.7504 | 0.0548 | 0.6441 | False | False |
| first_failed_gate | accepted | 60 | 182 | -0.0017 | 45.68 | -0.068 | 0.0677 | -0.249 | -1.0484 | 0.5583 | 0.0968 | 1.0543 | False | False |
| first_failed_gate | confirmation | 5 | 25 | -0.0201 | 37.5 | -0.0552 | 0.0116 | -0.2563 | -0.6963 | 0.137 | 0.0015 | 0.0318 | False | False |
| first_failed_gate | confirmation | 15 | 25 | -0.0313 | 41.67 | -0.1077 | 0.0435 | -0.2825 | -1.2866 | 0.7539 | -0.0035 | -0.0023 | False | False |
| first_failed_gate | confirmation | 30 | 25 | -0.0442 | 21.74 | -0.1383 | 0.0573 | -0.4927 | -1.6913 | 0.9373 | -0.0057 | 0.0016 | False | False |
| first_failed_gate | confirmation | 60 | 25 | 0.0282 | 42.86 | -0.0842 | 0.1524 | 0.667 | -1.0191 | 2.4971 | -0.0123 | -0.0934 | True | True |
| first_failed_gate | option quote stale: 118.7s | 5 | 1 | 0.0259 | 100.0 | 0.0259 | 0.0259 | 0.3933 | 0.3933 | 0.3933 | 0.0101 | 0.295 | True | True |
| first_failed_gate | option quote stale: 118.7s | 15 | 1 | -0.0983 | 0.0 | -0.0983 | -0.0983 | -1.4944 | -1.4944 | -1.4944 | 0.0069 | 0.3588 | False | False |
| first_failed_gate | option quote stale: 118.7s | 30 | 1 | -0.2743 | 0.0 | -0.2743 | -0.2743 | -4.1685 | -4.1685 | -4.1685 | -0.0072 | 0.0214 | False | False |
| first_failed_gate | option quote stale: 118.7s | 60 | 1 | -0.0466 | 0.0 | -0.0466 | -0.0466 | -0.7079 | -0.7079 | -0.7079 | -0.0107 | -0.1447 | False | False |
| first_failed_gate | option quote stale: 142.4s | 5 | 1 | -0.0433 | 0.0 | -0.0433 | -0.0433 | -0.8235 | -0.8235 | -0.8235 | 0.0029 | -0.0143 | False | False |
| first_failed_gate | option quote stale: 142.4s | 15 | 1 | -0.0102 | 0.0 | -0.0102 | -0.0102 | -0.1938 | -0.1938 | -0.1938 | 0.0163 | 0.0199 | False | False |
| first_failed_gate | option quote stale: 142.4s | 30 | 1 | -0.1096 | 0.0 | -0.1096 | -0.1096 | -2.083 | -2.083 | -2.083 | 0.0195 | 0.2729 | False | False |
| first_failed_gate | option quote stale: 142.4s | 60 | 1 | 0.0025 | 100.0 | 0.0025 | 0.0025 | 0.0484 | 0.0484 | 0.0484 | 0.0341 | 0.716 | False | False |
| first_failed_gate | option quote stale: 161.0s | 5 | 1 | 0.1383 | 100.0 | 0.1383 | 0.1383 | 1.7256 | 1.7256 | 1.7256 | 0.0345 | 0.5257 | True | True |
| first_failed_gate | option quote stale: 161.0s | 15 | 1 | 0.3418 | 100.0 | 0.3418 | 0.3418 | 4.2651 | 4.2651 | 4.2651 | 0.0917 | 1.3061 | True | True |
| first_failed_gate | option quote stale: 161.0s | 30 | 1 | 0.5115 | 100.0 | 0.5115 | 0.5115 | 6.3814 | 6.3814 | 6.3814 | 0.1626 | 2.2191 | True | True |
| first_failed_gate | option quote stale: 161.0s | 60 | 1 | 0.6707 | 100.0 | 0.6707 | 0.6707 | 8.3674 | 8.3674 | 8.3674 | 0.1476 | 1.8105 | True | True |
| first_failed_gate | option quote stale: 212.4s | 5 | 1 | -0.0465 | 0.0 | -0.0465 | -0.0465 | -0.7368 | -0.7368 | -0.7368 | 0.007 | 0.0798 | False | False |
| first_failed_gate | option quote stale: 212.4s | 15 | 1 | -0.0078 | 0.0 | -0.0078 | -0.0078 | -0.1228 | -0.1228 | -0.1228 | 0.026 | 0.324 | False | False |
| first_failed_gate | option quote stale: 212.4s | 30 | 1 | 0.0698 | 100.0 | 0.0698 | 0.0698 | 1.1053 | 1.1053 | 1.1053 | 0.0449 | 0.5556 | True | True |
| first_failed_gate | option quote stale: 212.4s | 60 | 1 | -0.5195 | 0.0 | -0.5195 | -0.5195 | -8.2281 | -8.2281 | -8.2281 | -0.1905 | -2.7011 | False | False |
| first_failed_gate | option quote stale: 222.7s | 5 | 1 | -0.1319 | 0.0 | -0.1319 | -0.1319 | -1.3431 | -1.3431 | -1.3431 | 0.0068 | 0.1101 | False | False |
| first_failed_gate | option quote stale: 222.7s | 15 | 1 | -0.1003 | 0.0 | -0.1003 | -0.1003 | -1.0213 | -1.0213 | -1.0213 | 0.02 | 0.3043 | False | False |
| first_failed_gate | option quote stale: 222.7s | 30 | 1 | 0.0582 | 100.0 | 0.0582 | 0.0582 | 0.5932 | 0.5932 | 0.5932 | 0.0925 | 1.334 | False | False |
| first_failed_gate | option quote stale: 222.7s | 60 | 1 | 0.3633 | 100.0 | 0.3633 | 0.3633 | 3.701 | 3.701 | 3.701 | 0.2334 | 3.8204 | True | False |
| first_failed_gate | option quote stale: 301.8s | 5 | 1 | 0.0726 | 100.0 | 0.0726 | 0.0726 | 0.8187 | 0.8187 | 0.8187 | 0.058 | 0.7034 | True | True |
| first_failed_gate | option quote stale: 301.8s | 15 | 1 | 0.1887 | 100.0 | 0.1887 | 0.1887 | 2.1287 | 2.1287 | 2.1287 | 0.1539 | 1.9289 | True | True |
| first_failed_gate | option quote stale: 301.8s | 30 | 1 | 0.7837 | 100.0 | 0.7837 | 0.7837 | 8.8421 | 8.8421 | 8.8421 | 0.2683 | 3.3455 | True | True |
| first_failed_gate | option quote stale: 301.8s | 60 | 1 | 0.5588 | 100.0 | 0.5588 | 0.5588 | 6.3041 | 6.3041 | 6.3041 | 0.2813 | 3.0496 | True | True |
| first_failed_gate | option quote stale: 430.8s | 5 | 1 | 0.2089 | 100.0 | 0.2089 | 0.2089 | 2.1818 | 2.1818 | 2.1818 | -0.0561 | -0.4699 | True | True |
| first_failed_gate | option quote stale: 430.8s | 15 | 1 | -0.2263 | 0.0 | -0.2263 | -0.2263 | -2.3636 | -2.3636 | -2.3636 | -0.1627 | -1.3466 | False | False |
| first_failed_gate | option quote stale: 430.8s | 30 | 1 | -0.5309 | 0.0 | -0.5309 | -0.5309 | -5.5455 | -5.5455 | -5.5455 | -0.2323 | -2.2571 | False | False |
| first_failed_gate | option quote stale: 430.8s | 60 | 1 | 0.1132 | 100.0 | 0.1132 | 0.1132 | 1.1818 | 1.1818 | 1.1818 | -0.4237 | -3.4826 | True | True |
| first_failed_gate | option quote stale: 473.5s | 5 | 1 | -0.0159 | 0.0 | -0.0159 | -0.0159 | -0.2993 | -0.2993 | -0.2993 | -0.0038 | -0.0554 | False | False |
| first_failed_gate | option quote stale: 473.5s | 15 | 1 | 0.0381 | 100.0 | 0.0381 | 0.0381 | 0.7167 | 0.7167 | 0.7167 | -0.0124 | -0.2307 | True | True |
| first_failed_gate | option quote stale: 473.5s | 30 | 1 | -0.1292 | 0.0 | -0.1292 | -0.1292 | -2.4288 | -2.4288 | -2.4288 | -0.0219 | -0.2201 | False | False |
| first_failed_gate | option quote stale: 473.5s | 60 | 1 | -0.2416 | 0.0 | -0.2416 | -0.2416 | -4.5412 | -4.5412 | -4.5412 | -0.0738 | -1.5192 | False | False |
| first_failed_gate | option quote stale: 65.8s | 5 | 1 | -0.0421 | 0.0 | -0.0421 | -0.0421 | -0.8565 | -0.8565 | -0.8565 | -0.0059 | -0.2019 | False | False |
| first_failed_gate | option quote stale: 65.8s | 15 | 1 | -0.0372 | 0.0 | -0.0372 | -0.0372 | -0.7582 | -0.7582 | -0.7582 | -0.0367 | -1.0975 | False | True |
| first_failed_gate | option quote stale: 65.8s | 30 | 1 | -0.1313 | 0.0 | -0.1313 | -0.1313 | -2.6732 | -2.6732 | -2.6732 | -0.081 | -2.3397 | False | False |
| first_failed_gate | option quote stale: 65.8s | 60 | 1 | -0.5079 | 0.0 | -0.5079 | -0.5079 | -10.3443 | -10.3443 | -10.3443 | -0.1512 | -3.8125 | False | False |
| first_failed_gate | option quote stale: 850.0s | 5 | 1 | -0.0895 | 0.0 | -0.0895 | -0.0895 | -2.4491 | -2.4491 | -2.4491 | -0.0038 | -0.0554 | False | False |
| first_failed_gate | option quote stale: 850.0s | 15 | 1 | -0.1551 | 0.0 | -0.1551 | -0.1551 | -4.2436 | -4.2436 | -4.2436 | -0.0124 | -0.2307 | False | False |
| first_failed_gate | option quote stale: 850.0s | 30 | 1 | -0.2429 | 0.0 | -0.2429 | -0.2429 | -6.6453 | -6.6453 | -6.6453 | -0.0219 | -0.2201 | False | False |
| first_failed_gate | option quote stale: 850.0s | 60 | 1 | -0.3965 | 0.0 | -0.3965 | -0.3965 | -10.8491 | -10.8491 | -10.8491 | -0.0738 | -1.5192 | False | False |
| first_failed_gate | premium too high: 1008.45 > 1000.0 | 5 | 1 | 0.0683 | 100.0 | 0.0683 | 0.0683 | 1.4309 | 1.4309 | 1.4309 | 0.0032 | 0.0451 | True | True |
| first_failed_gate | premium too high: 1008.45 > 1000.0 | 15 | 1 | 0.1909 | 100.0 | 0.1909 | 0.1909 | 4.0007 | 4.0007 | 4.0007 | 0.0164 | 0.1533 | True | True |
| first_failed_gate | premium too high: 1008.45 > 1000.0 | 30 | 1 | 0.1405 | 100.0 | 0.1405 | 0.1405 | 2.9455 | 2.9455 | 2.9455 | 0.0463 | 0.7729 | True | True |
| first_failed_gate | premium too high: 1008.45 > 1000.0 | 60 | 1 | 0.0166 | 100.0 | 0.0166 | 0.0166 | 0.3483 | 0.3483 | 0.3483 | 0.0507 | 1.0558 | False | False |
| first_failed_gate | premium too high: 1043.35 > 1000.0 | 5 | 1 | -0.093 | 0.0 | -0.093 | -0.093 | -2.704 | -2.704 | -2.704 | -0.0026 | -0.1472 | False | False |
| first_failed_gate | premium too high: 1043.35 > 1000.0 | 15 | 1 | -0.2037 | 0.0 | -0.2037 | -0.2037 | -5.9239 | -5.9239 | -5.9239 | -0.0051 | -0.2164 | False | False |
| first_failed_gate | premium too high: 1043.35 > 1000.0 | 30 | 1 | -0.2273 | 0.0 | -0.2273 | -0.2273 | -6.6095 | -6.6095 | -6.6095 | 0.0001 | -0.0721 | False | False |
| first_failed_gate | premium too high: 1043.35 > 1000.0 | 60 | 1 | -0.2454 | 0.0 | -0.2454 | -0.2454 | -7.1373 | -7.1373 | -7.1373 | -0.0242 | -0.5554 | False | False |
| first_failed_gate | premium too high: 1077.55 > 1000.0 | 5 | 1 | 0.2058 | 100.0 | 0.2058 | 0.2058 | 4.4434 | 4.4434 | 4.4434 | 0.0073 | 0.1757 | True | True |
| first_failed_gate | premium too high: 1077.55 > 1000.0 | 15 | 1 | 0.0492 | 100.0 | 0.0492 | 0.0492 | 1.063 | 1.063 | 1.063 | 0.0169 | 0.527 | True | True |
| first_failed_gate | premium too high: 1077.55 > 1000.0 | 30 | 1 | -0.1331 | 0.0 | -0.1331 | -0.1331 | -2.8737 | -2.8737 | -2.8737 | 0.0148 | 0.5733 | False | False |
| first_failed_gate | premium too high: 1077.55 > 1000.0 | 60 | 1 | -0.1072 | 0.0 | -0.1072 | -0.1072 | -2.3138 | -2.3138 | -2.3138 | 0.0361 | 0.7789 | False | False |
| first_failed_gate | premium too high: 1412.25 > 1000.0 | 5 | 1 | 0.1295 | 100.0 | 0.1295 | 0.1295 | 1.9272 | 1.9272 | 1.9272 | 0.0136 | 0.396 | True | True |
| first_failed_gate | premium too high: 1412.25 > 1000.0 | 15 | 1 | 0.006 | 100.0 | 0.006 | 0.006 | 0.0888 | 0.0888 | 0.0888 | 0.0528 | 0.9257 | False | False |
| first_failed_gate | premium too high: 1412.25 > 1000.0 | 30 | 1 | 0.1126 | 100.0 | 0.1126 | 0.1126 | 1.6763 | 1.6763 | 1.6763 | 0.1299 | 1.6035 | False | True |
| first_failed_gate | premium too high: 1412.25 > 1000.0 | 60 | 1 | 0.1321 | 100.0 | 0.1321 | 0.1321 | 1.9664 | 1.9664 | 1.9664 | 0.2585 | 3.936 | False | False |
| first_failed_gate | premium too high: 1589.35 > 1000.0 | 5 | 1 | -0.1437 | 0.0 | -0.1437 | -0.1437 | -1.8744 | -1.8744 | -1.8744 | -0.0245 | -0.5306 | False | False |
| first_failed_gate | premium too high: 1589.35 > 1000.0 | 15 | 1 | -0.3069 | 0.0 | -0.3069 | -0.3069 | -4.0026 | -4.0026 | -4.0026 | -0.0261 | -0.3319 | False | False |
| first_failed_gate | premium too high: 1589.35 > 1000.0 | 30 | 1 | -0.1218 | 0.0 | -0.1218 | -0.1218 | -1.5886 | -1.5886 | -1.5886 | -0.0802 | -1.5504 | False | False |
| first_failed_gate | premium too high: 1589.35 > 1000.0 | 60 | 1 | -0.6424 | 0.0 | -0.6424 | -0.6424 | -8.3777 | -8.3777 | -8.3777 | -0.1793 | -2.8541 | False | False |
| first_failed_gate | premium too high: 1680.0 > 1000.0 | 5 | 1 | 0.0266 | 100.0 | 0.0266 | 0.0266 | 0.3755 | 0.3755 | 0.3755 | -0.0105 | -0.1725 | True | True |
| first_failed_gate | premium too high: 1680.0 > 1000.0 | 15 | 1 | -0.1606 | 0.0 | -0.1606 | -0.1606 | -2.2702 | -2.2702 | -2.2702 | -0.0406 | -0.6257 | False | False |
| first_failed_gate | premium too high: 1680.0 > 1000.0 | 30 | 1 | -0.1471 | 0.0 | -0.1471 | -0.1471 | -2.079 | -2.079 | -2.079 | -0.1014 | -1.8224 | False | False |
| first_failed_gate | premium too high: 1680.0 > 1000.0 | 60 | 1 | -0.5486 | 0.0 | -0.5486 | -0.5486 | -7.7538 | -7.7538 | -7.7538 | -0.3416 | -6.0498 | False | False |
| first_failed_gate | premium too high: 859.95 > 800.0 | 5 | 1 | 0.0872 | 100.0 | 0.0872 | 0.0872 | 1.3307 | 1.3307 | 1.3307 | 0.024 | 0.4613 | True | True |
| first_failed_gate | premium too high: 859.95 > 800.0 | 15 | 1 | 0.0143 | 100.0 | 0.0143 | 0.0143 | 0.2176 | 0.2176 | 0.2176 | 0.0732 | 1.4395 | False | False |
| first_failed_gate | premium too high: 859.95 > 800.0 | 30 | 1 | 0.0692 | 100.0 | 0.0692 | 0.0692 | 1.0559 | 1.0559 | 1.0559 | 0.148 | 3.0298 | False | False |
| first_failed_gate | premium too high: 859.95 > 800.0 | 60 | 1 | -0.0114 | 0.0 | -0.0114 | -0.0114 | -0.1744 | -0.1744 | -0.1744 | 0.1848 | 3.7632 | False | False |
| first_failed_gate | premium too high: 884.9 > 800.0 | 5 | 1 | -0.2476 | 0.0 | -0.2476 | -0.2476 | -3.8058 | -3.8058 | -3.8058 | -0.0061 | -0.0589 | False | False |
| first_failed_gate | premium too high: 884.9 > 800.0 | 15 | 1 | -0.3367 | 0.0 | -0.3367 | -0.3367 | -5.1763 | -5.1763 | -5.1763 | 0.0039 | 0.0652 | False | False |
| first_failed_gate | premium too high: 884.9 > 800.0 | 30 | 1 | -0.3416 | 0.0 | -0.3416 | -0.3416 | -5.2519 | -5.2519 | -5.2519 | 0.0141 | 0.6443 | False | False |
| first_failed_gate | premium too high: 884.9 > 800.0 | 60 | 1 | -0.3367 | 0.0 | -0.3367 | -0.3367 | -5.1763 | -5.1763 | -5.1763 | 0.1113 | 3.4833 | False | False |
| first_failed_gate | premium too high: 970.85 > 800.0 | 5 | 1 | -0.1705 | 0.0 | -0.1705 | -0.1705 | -2.9105 | -2.9105 | -2.9105 | 0.0183 | 0.4419 | False | False |
| first_failed_gate | premium too high: 970.85 > 800.0 | 15 | 1 | -0.1313 | 0.0 | -0.1313 | -0.1313 | -2.2415 | -2.2415 | -2.2415 | 0.0464 | 1.1767 | False | False |
| first_failed_gate | premium too high: 970.85 > 800.0 | 30 | 1 | -0.176 | 0.0 | -0.176 | -0.176 | -3.0052 | -3.0052 | -3.0052 | 0.0629 | 1.4678 | False | False |
| first_failed_gate | premium too high: 970.85 > 800.0 | 60 | 1 | -0.1295 | 0.0 | -0.1295 | -0.1295 | -2.212 | -2.212 | -2.212 | -0.0093 | -0.444 | False | False |
| first_failed_gate | premium too low: 10.0 < 12.0 | 5 | 1 | -0.0138 | 0.0 | -0.0138 | -0.0138 | -0.1834 | -0.1834 | -0.1834 | -0.0019 | -0.0792 | False | False |
| first_failed_gate | premium too low: 10.0 < 12.0 | 15 | 1 | -0.1789 | 0.0 | -0.1789 | -0.1789 | -2.3843 | -2.3843 | -2.3843 | -0.0138 | -0.232 | False | False |
| first_failed_gate | premium too low: 10.0 < 12.0 | 30 | 1 | -0.2615 | 0.0 | -0.2615 | -0.2615 | -3.4847 | -3.4847 | -3.4847 | -0.0323 | -0.4094 | False | False |
| first_failed_gate | premium too low: 10.0 < 12.0 | 60 | 1 | -0.2065 | 0.0 | -0.2065 | -0.2065 | -2.7511 | -2.7511 | -2.7511 | -0.0146 | -0.2117 | False | False |
| first_failed_gate | premium too low: 10.65 < 12.0 | 5 | 1 | -0.1405 | 0.0 | -0.1405 | -0.1405 | -1.7658 | -1.7658 | -1.7658 | -0.0283 | -0.3345 | False | False |
| first_failed_gate | premium too low: 10.65 < 12.0 | 15 | 1 | -0.4014 | 0.0 | -0.4014 | -0.4014 | -5.045 | -5.045 | -5.045 | -0.0803 | -0.8962 | False | False |
| first_failed_gate | premium too low: 10.65 < 12.0 | 30 | 1 | -0.5971 | 0.0 | -0.5971 | -0.5971 | -7.5045 | -7.5045 | -7.5045 | -0.1858 | -2.0296 | False | False |
| first_failed_gate | premium too low: 10.65 < 12.0 | 60 | 1 | -1.0789 | 0.0 | -1.0789 | -1.0789 | -13.5586 | -13.5586 | -13.5586 | -0.4358 | -4.9335 | False | False |
| first_failed_gate | premium too low: 11.5 < 12.0 | 5 | 1 | 0.1857 | 100.0 | 0.1857 | 0.1857 | 1.9178 | 1.9178 | 1.9178 | 0.0286 | 0.4297 | True | True |
| first_failed_gate | premium too low: 11.5 < 12.0 | 15 | 1 | 0.6995 | 100.0 | 0.6995 | 0.6995 | 7.2237 | 7.2237 | 7.2237 | 0.0625 | 0.6754 | True | True |
| first_failed_gate | premium too low: 11.65 < 12.0 | 5 | 1 | 0.0551 | 100.0 | 0.0551 | 0.0551 | 0.7326 | 0.7326 | 0.7326 | 0.0174 | 0.259 | True | True |
| first_failed_gate | premium too low: 11.65 < 12.0 | 15 | 1 | 0.1653 | 100.0 | 0.1653 | 0.1653 | 2.1977 | 2.1977 | 2.1977 | -0.0058 | -0.0325 | True | True |
| first_failed_gate | premium too low: 11.65 < 12.0 | 30 | 1 | 0.3736 | 100.0 | 0.3736 | 0.3736 | 4.9651 | 4.9651 | 4.9651 | -0.064 | -0.6295 | True | True |
| first_failed_gate | premium too low: 11.9 < 15.0 | 5 | 1 | -0.0433 | 0.0 | -0.0433 | -0.0433 | -0.329 | -0.329 | -0.329 | -0.0106 | -0.2242 | False | False |
| first_failed_gate | premium too low: 11.9 < 15.0 | 15 | 1 | 0.5913 | 100.0 | 0.5913 | 0.5913 | 4.4961 | 4.4961 | 4.4961 | -0.0113 | -0.4976 | True | True |
| first_failed_gate | premium too low: 11.9 < 15.0 | 30 | 1 | 0.4423 | 100.0 | 0.4423 | 0.4423 | 3.3629 | 3.3629 | 3.3629 | 0.0576 | 0.1232 | True | True |
| first_failed_gate | premium too low: 11.9 < 15.0 | 60 | 1 | 0.2596 | 100.0 | 0.2596 | 0.2596 | 1.9739 | 1.9739 | 1.9739 | 0.2919 | 2.6548 | False | False |
| first_failed_gate | premium too low: 5.1 < 12.0 | 5 | 1 | 0.0585 | 100.0 | 0.0585 | 0.0585 | 0.6437 | 0.6437 | 0.6437 | -0.0948 | -1.1446 | True | True |
| first_failed_gate | premium too low: 5.1 < 12.0 | 15 | 1 | -0.2997 | 0.0 | -0.2997 | -0.2997 | -3.2989 | -3.2989 | -3.2989 | -0.3019 | -3.636 | True | True |
| first_failed_gate | premium too low: 5.1 < 12.0 | 30 | 1 | -0.0731 | 0.0 | -0.0731 | -0.0731 | -0.8046 | -0.8046 | -0.8046 | -0.5553 | -7.3314 | True | True |
| first_failed_gate | premium too low: 5.3 < 12.0 | 5 | 1 | -0.009 | 0.0 | -0.009 | -0.009 | -0.1628 | -0.1628 | -0.1628 | -0.004 | -0.0412 | False | False |
| first_failed_gate | premium too low: 5.3 < 12.0 | 15 | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | -0.0264 | -0.309 | True | True |
| first_failed_gate | premium too low: 5.3 < 12.0 | 30 | 1 | -0.009 | 0.0 | -0.009 | -0.009 | -0.1628 | -0.1628 | -0.1628 | -0.0759 | -0.9357 | True | True |
| first_failed_gate | premium too low: 5.4 < 12.0 | 5 | 1 | -0.0271 | 0.0 | -0.0271 | -0.0271 | -0.4158 | -0.4158 | -0.4158 | 0.0093 | 0.1824 | False | False |
| first_failed_gate | premium too low: 5.4 < 12.0 | 15 | 1 | 0.2799 | 100.0 | 0.2799 | 0.2799 | 4.297 | 4.297 | 4.297 | 0.0299 | 0.5524 | True | True |
| first_failed_gate | premium too low: 5.4 < 12.0 | 30 | 1 | 0.2573 | 100.0 | 0.2573 | 0.2573 | 3.9505 | 3.9505 | 3.9505 | 0.085 | 1.7137 | True | True |
| first_failed_gate | premium too low: 5.4 < 12.0 | 60 | 1 | -0.149 | 0.0 | -0.149 | -0.149 | -2.2871 | -2.2871 | -2.2871 | 0.1409 | 3.1804 | False | False |
| first_failed_gate | premium too low: 5.55 < 12.0 | 5 | 1 | -0.1579 | 0.0 | -0.1579 | -0.1579 | -1.5605 | -1.5605 | -1.5605 | -0.0485 | -0.5368 | False | False |
| first_failed_gate | premium too low: 5.55 < 12.0 | 15 | 1 | -0.1128 | 0.0 | -0.1128 | -0.1128 | -1.1146 | -1.1146 | -1.1146 | -0.1421 | -1.0414 | True | False |
| first_failed_gate | premium too low: 5.55 < 12.0 | 30 | 1 | -0.0316 | 0.0 | -0.0316 | -0.0316 | -0.3121 | -0.3121 | -0.3121 | -0.282 | -1.5951 | True | True |
| first_failed_gate | premium too low: 5.55 < 12.0 | 60 | 1 | -0.0812 | 0.0 | -0.0812 | -0.0812 | -0.8025 | -0.8025 | -0.8025 | -0.3051 | -1.0359 | True | True |
| first_failed_gate | premium too low: 6.25 < 12.0 | 5 | 1 | -0.0184 | 0.0 | -0.0184 | -0.0184 | -0.3529 | -0.3529 | -0.3529 | 0.0242 | 0.8744 | False | False |
| first_failed_gate | premium too low: 6.25 < 12.0 | 15 | 1 | -0.0307 | 0.0 | -0.0307 | -0.0307 | -0.5882 | -0.5882 | -0.5882 | 0.0957 | 2.6367 | False | False |
| first_failed_gate | premium too low: 6.25 < 12.0 | 30 | 1 | 0.7622 | 100.0 | 0.7622 | 0.7622 | 14.5882 | 14.5882 | 14.5882 | 0.1929 | 4.0485 | True | True |
| first_failed_gate | premium too low: 6.25 < 12.0 | 60 | 1 | 0.4856 | 100.0 | 0.4856 | 0.4856 | 9.2941 | 9.2941 | 9.2941 | 0.3068 | 4.4561 | True | True |
| first_failed_gate | premium too low: 6.6 < 12.0 | 5 | 1 | 0.0919 | 100.0 | 0.0919 | 0.0919 | 1.4789 | 1.4789 | 1.4789 | -0.0152 | -0.2032 | True | True |
| first_failed_gate | premium too low: 6.6 < 12.0 | 15 | 1 | 0.141 | 100.0 | 0.141 | 0.141 | 2.2676 | 2.2676 | 2.2676 | 0.0047 | 0.0751 | True | True |
| first_failed_gate | premium too low: 6.6 < 12.0 | 30 | 1 | 0.2574 | 100.0 | 0.2574 | 0.2574 | 4.1408 | 4.1408 | 4.1408 | 0.0594 | 0.6309 | True | True |
| first_failed_gate | premium too low: 6.6 < 12.0 | 60 | 1 | 0.0919 | 100.0 | 0.0919 | 0.0919 | 1.4789 | 1.4789 | 1.4789 | -0.0267 | -0.8217 | True | True |
| first_failed_gate | premium too low: 6.7 < 12.0 | 5 | 1 | 0.3068 | 100.0 | 0.3068 | 0.3068 | 6.0345 | 6.0345 | 6.0345 | 0.0242 | 0.8744 | True | True |
| first_failed_gate | premium too low: 6.7 < 12.0 | 15 | 1 | 0.4356 | 100.0 | 0.4356 | 0.4356 | 8.569 | 8.569 | 8.569 | 0.0957 | 2.6367 | True | True |
| first_failed_gate | premium too low: 6.7 < 12.0 | 30 | 1 | 0.2209 | 100.0 | 0.2209 | 0.2209 | 4.3448 | 4.3448 | 4.3448 | 0.1929 | 4.0485 | True | True |
| first_failed_gate | premium too low: 6.7 < 12.0 | 60 | 1 | 0.4295 | 100.0 | 0.4295 | 0.4295 | 8.4483 | 8.4483 | 8.4483 | 0.3068 | 4.4561 | True | True |
| first_failed_gate | premium too low: 7.35 < 12.0 | 5 | 2 | -0.0133 | 0.0 | -0.0205 | -0.0061 | -0.1933 | -0.2658 | -0.1207 | -0.0276 | -0.2899 | True | True |
| first_failed_gate | premium too low: 7.35 < 12.0 | 15 | 2 | -0.0765 | 0.0 | -0.0917 | -0.0614 | -1.3039 | -1.8103 | -0.7975 | -0.0544 | -0.5197 | False | False |
| first_failed_gate | premium too low: 7.35 < 12.0 | 30 | 2 | -0.1839 | 0.0 | -0.2456 | -0.1223 | -2.8018 | -3.1899 | -2.4138 | -0.0956 | -0.817 | False | False |
| first_failed_gate | premium too low: 7.35 < 12.0 | 60 | 2 | -0.3857 | 0.0 | -0.423 | -0.3484 | -6.1865 | -6.8793 | -5.4937 | -0.2282 | -2.5961 | False | False |
| first_failed_gate | premium too low: 9.15 < 12.0 | 5 | 1 | 0.0137 | 100.0 | 0.0137 | 0.0137 | 0.1772 | 0.1772 | 0.1772 | 0.0183 | 0.2917 | False | False |
| first_failed_gate | premium too low: 9.15 < 12.0 | 15 | 1 | 0.1646 | 100.0 | 0.1646 | 0.1646 | 2.1266 | 2.1266 | 2.1266 | 0.0841 | 0.935 | True | True |
| first_failed_gate | premium too low: 9.15 < 12.0 | 30 | 1 | 0.3978 | 100.0 | 0.3978 | 0.3978 | 5.1392 | 5.1392 | 5.1392 | 0.1434 | 1.8506 | True | True |
| first_failed_gate | premium too low: 9.15 < 12.0 | 60 | 1 | 0.2332 | 100.0 | 0.2332 | 0.2332 | 3.0127 | 3.0127 | 3.0127 | 0.2506 | 2.3981 | False | True |
| first_failed_gate | premium too low: 9.85 < 12.0 | 5 | 1 | 0.222 | 100.0 | 0.222 | 0.222 | 4.3299 | 4.3299 | 4.3299 | -0.0948 | -1.1446 | True | True |
| first_failed_gate | premium too low: 9.85 < 12.0 | 15 | 1 | -0.0296 | 0.0 | -0.0296 | -0.0296 | -0.5773 | -0.5773 | -0.5773 | -0.3019 | -3.636 | True | True |
| first_failed_gate | premium too low: 9.85 < 12.0 | 30 | 1 | -0.6511 | 0.0 | -0.6511 | -0.6511 | -12.701 | -12.701 | -12.701 | -0.5553 | -7.3314 | False | False |
| first_failed_gate | premium too low: 9.85 < 12.0 | 60 | 1 | -1.0803 | 0.0 | -1.0803 | -1.0803 | -21.0722 | -21.0722 | -21.0722 | -0.7959 | -10.8112 | False | False |
| first_failed_gate | score<70 | 5 | 12 | -0.0072 | 33.33 | -0.0436 | 0.036 | -0.0648 | -0.4308 | 0.3827 | 0.0277 | 0.3475 | False | False |
| first_failed_gate | score<70 | 15 | 12 | 0.0583 | 63.64 | -0.0822 | 0.2111 | 0.6627 | -0.6533 | 2.147 | 0.0822 | 0.9979 | False | False |
| first_failed_gate | score<70 | 30 | 12 | 0.0795 | 50.0 | -0.0774 | 0.2458 | 0.6185 | -0.7135 | 1.9913 | 0.1664 | 1.9045 | False | False |
| first_failed_gate | score<70 | 60 | 12 | -0.1266 | 33.33 | -0.4178 | 0.153 | -1.4565 | -4.2818 | 1.082 | 0.2952 | 3.4 | False | False |
| first_failed_gate | trading_hours | 5 | 2 | 0.1749 | 100.0 | 0.1749 | 0.1749 | 2.4372 | 2.4372 | 2.4372 | 0.007 | 0.2985 | True | True |
| first_failed_gate | volatility | 5 | 57 | 0.0192 | 64.91 | 0.0023 | 0.0362 | 0.5051 | 0.0821 | 0.9294 | 0.0064 | 0.1505 | True | True |
| first_failed_gate | volatility | 15 | 57 | 0.0516 | 64.91 | 0.0188 | 0.0862 | 1.3474 | 0.5567 | 2.1585 | 0.02 | 0.4734 | True | True |
| first_failed_gate | volatility | 30 | 57 | 0.0515 | 55.56 | 0.005 | 0.1023 | 1.3631 | 0.1889 | 2.6121 | 0.0346 | 0.8718 | True | True |
| first_failed_gate | volatility | 60 | 57 | 0.1179 | 62.5 | 0.036 | 0.2113 | 2.9726 | 0.9408 | 5.1199 | 0.0748 | 1.7648 | True | True |
| first_failed_gate | weak candle momentum | 5 | 274 | 0.01 | 50.92 | -0.0049 | 0.0246 | 0.1324 | -0.0618 | 0.3238 | 0.0054 | 0.09 | True | True |
| first_failed_gate | weak candle momentum | 15 | 274 | 0.0248 | 57.41 | -0.0005 | 0.0497 | 0.3975 | 0.0187 | 0.7754 | 0.0158 | 0.2324 | True | True |
| first_failed_gate | weak candle momentum | 30 | 274 | 0.0104 | 53.03 | -0.0281 | 0.0465 | 0.3679 | -0.219 | 0.9267 | 0.0273 | 0.4 | False | False |
| first_failed_gate | weak candle momentum | 60 | 274 | 0.0086 | 50.85 | -0.0397 | 0.0558 | 0.1146 | -0.6585 | 0.8546 | 0.0449 | 0.6576 | False | False |
| tier | BANKNIFTY | 5 | 76 | 0.0021 | 55.26 | -0.0179 | 0.0208 | 0.077 | -0.2891 | 0.4299 | 0.0026 | 0.0557 | False | True |
| tier | BANKNIFTY | 15 | 76 | 0.0076 | 56.58 | -0.0285 | 0.0459 | 0.2726 | -0.4388 | 1.0202 | 0.0075 | 0.1284 | True | True |
| tier | BANKNIFTY | 30 | 76 | 0.0043 | 48.65 | -0.049 | 0.0525 | 0.1364 | -0.8788 | 1.0969 | 0.0154 | 0.2416 | False | False |
| tier | BANKNIFTY | 60 | 76 | 0.0065 | 50.75 | -0.0698 | 0.0834 | 0.162 | -1.3352 | 1.5833 | 0.0284 | 0.4105 | False | False |
| tier | NIFTY | 5 | 96 | 0.0087 | 56.25 | -0.0027 | 0.0197 | 0.2454 | -0.0195 | 0.5117 | 0.0038 | 0.1246 | True | True |
| tier | NIFTY | 15 | 96 | 0.0208 | 60.42 | -0.0009 | 0.0408 | 0.6136 | 0.0501 | 1.1166 | 0.0112 | 0.3613 | True | True |
| tier | NIFTY | 30 | 96 | 0.0181 | 55.91 | -0.0187 | 0.0553 | 0.6883 | -0.2469 | 1.6539 | 0.0228 | 0.7151 | False | False |
| tier | NIFTY | 60 | 96 | -0.0004 | 56.63 | -0.053 | 0.0523 | 0.3651 | -0.9309 | 1.6562 | 0.0434 | 1.2336 | False | False |
| tier | stock | 5 | 415 | 0.0109 | 47.2 | -0.0019 | 0.0244 | 0.1441 | -0.0102 | 0.3108 | 0.008 | 0.1036 | True | True |
| tier | stock | 15 | 415 | 0.0319 | 53.94 | 0.0079 | 0.0557 | 0.3931 | 0.0945 | 0.6904 | 0.0233 | 0.2893 | True | True |
| tier | stock | 30 | 415 | 0.0191 | 49.49 | -0.0107 | 0.0525 | 0.269 | -0.143 | 0.6881 | 0.0417 | 0.514 | False | False |
| tier | stock | 60 | 415 | 0.0076 | 46.78 | -0.0372 | 0.0549 | 0.0409 | -0.5705 | 0.6419 | 0.0714 | 0.8354 | False | False |
| period | 12-Nov to 17-Nov | 5 | 258 | 0.0126 | 51.36 | 0.0002 | 0.0254 | 0.2871 | 0.1031 | 0.4789 | 0.0036 | 0.0681 | True | True |
| period | 12-Nov to 17-Nov | 15 | 258 | 0.0236 | 57.25 | 0.0029 | 0.0446 | 0.5089 | 0.172 | 0.8467 | 0.0101 | 0.1856 | True | True |
| period | 12-Nov to 17-Nov | 30 | 258 | -0.005 | 45.97 | -0.0328 | 0.0239 | 0.0916 | -0.3632 | 0.5495 | 0.0158 | 0.2848 | False | False |
| period | 12-Nov to 17-Nov | 60 | 258 | -0.013 | 47.25 | -0.052 | 0.0276 | -0.1763 | -0.8353 | 0.5082 | 0.0248 | 0.4151 | False | False |
| period | 14-Oct to 11-Nov | 5 | 329 | 0.0069 | 48.47 | -0.0073 | 0.022 | 0.0455 | -0.1263 | 0.223 | 0.0089 | 0.1265 | False | False |
| period | 14-Oct to 11-Nov | 15 | 329 | 0.0294 | 53.87 | 0.0049 | 0.0556 | 0.3389 | -0.003 | 0.6981 | 0.0265 | 0.3545 | True | False |
| period | 14-Oct to 11-Nov | 30 | 329 | 0.0344 | 53.99 | -0.0045 | 0.0726 | 0.5028 | -0.0148 | 1.0376 | 0.0504 | 0.6895 | False | False |
| period | 14-Oct to 11-Nov | 60 | 329 | 0.0206 | 50.17 | -0.0305 | 0.0752 | 0.3259 | -0.3956 | 1.1036 | 0.0899 | 1.183 | False | False |