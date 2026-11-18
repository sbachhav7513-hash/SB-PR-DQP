# PAPER run-up veto and 5-minute entry replay

Sample: 51 closed PAPER option trades from 2026-10-30 through 2026-11-16. This replay is descriptive and is not an activation recommendation for a 5-minute entry rule.

## Run-up value verification

Offline recompute uses the last completed one-minute option close at or before `signal_time`, divided by the close exactly 60 minutes earlier. The runtime-aligned check requires all 61 minute bars; missing/gapped lookbacks are incomplete and fail open.

- Complete offline lookbacks: 26/51.
- Trades with a persisted runtime value: 23/51.
- Persisted runtime values comparable with offline: 10/51.
- Persisted runtime vs offline differences over 1 percentage point: 8.
- Reconstructed legacy row-count runtime values to compare: 26/51.
- Reconstructed legacy vs offline differences over 1 percentage point: 0.

Persisted runtime values were only available for the later telemetry cohort; earlier trades have no stored runtime value. The reconstructed legacy comparison applies the prior 61-valid-close runtime formula to the archived option bars and is labeled separately, not presented as a recorded runtime value.

| Trade | Runtime recorded % | Runtime reconstructed % | Offline % | Difference pp | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| NIFTY_PE-2026-10-30T10:07:21.189181+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| RELIANCE_CE-2026-11-03T09:58:37.552708+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| HDFCBANK_CE-2026-11-03T13:00:31.294452+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| INFY_CE-2026-11-03T13:26:35.553817+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| LT_PE-2026-11-04T10:19:50.401341+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| RELIANCE_CE-2026-11-04T12:27:49.645890+05:30-BUY | N/A | -0.6803 | -0.6803 | N/A | complete |
| SBIN_CE-2026-11-04T13:19:49.413291+05:30-BUY | N/A | 11.2583 | 11.2583 | N/A | complete |
| TCS_CE-2026-11-04T14:25:53.154906+05:30-BUY | N/A | 0.4908 | 0.4908 | N/A | complete |
| HDFCBANK_CE-2026-11-05T11:31:03.340974+05:30-BUY | N/A | 1.4706 | 1.4706 | N/A | complete |
| RELIANCE_CE-2026-11-05T13:43:03.335864+05:30-BUY | N/A | 8.7452 | 8.7452 | N/A | complete |
| LT_PE-2026-11-05T14:22:08.089786+05:30-BUY | N/A | 14.9109 | 14.9109 | N/A | complete |
| SBIN_CE-2026-11-06T10:05:04.001399+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| NIFTY_PE-2026-11-06T10:41:37.273817+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| HDFCBANK_PE-2026-11-06T10:41:37.464399+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| TCS_PE-2026-11-06T10:53:36.280612+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| INFY_PE-2026-11-06T10:55:37.279923+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| INFY_CE-2026-11-06T11:48:38.033746+05:30-BUY | N/A | -8.6287 | -8.6287 | N/A | complete |
| BANKNIFTY_CE-2026-11-06T12:11:37.532648+05:30-BUY | N/A | 2.1709 | 2.1709 | N/A | complete |
| LT_CE-2026-11-06T13:16:34.530139+05:30-BUY | N/A | 6.4477 | 6.4477 | N/A | complete |
| TCS_CE-2026-11-06T13:16:36.537440+05:30-BUY | N/A | -8.8154 | -8.8154 | N/A | complete |
| INFY_CE-2026-11-06T14:33:37.782767+05:30-BUY | N/A | 1.4519 | 1.4519 | N/A | complete |
| LT_CE-2026-11-09T10:04:22.638133+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| ICICIBANK_PE-2026-11-09T10:36:22.341814+05:30-BUY | N/A | N/A | N/A | N/A | lookback_incomplete |
| RELIANCE_CE-2026-11-09T11:28:22.855071+05:30-BUY | N/A | -4.3584 | -4.3584 | N/A | complete |
| TCS_PE-2026-11-09T12:16:22.846458+05:30-BUY | N/A | -7.1380 | -7.1380 | N/A | complete |
| INFY_CE-2026-11-09T12:51:24.338410+05:30-BUY | N/A | -11.7073 | -11.7073 | N/A | complete |
| BANKNIFTY_PE-2026-11-09T13:16:57.381000+05:30-BUY | N/A | 3.6147 | 3.6147 | N/A | complete |
| TCS_CE-2026-11-09T13:59:23.086457+05:30-BUY | N/A | 4.8864 | 4.8864 | N/A | complete |
| HDFCBANK_CE-2026-11-11T11:33:05.261555+05:30-BUY | 14.6789 | 13.1336 | 13.1336 | 1.5453 | complete |
| TCS_PE-2026-11-11T12:06:05.294871+05:30-BUY | 1.5625 | N/A | N/A | N/A | lookback_incomplete |
| LT_PE-2026-11-11T13:39:05.480164+05:30-BUY | -2.0122 | -2.0122 | -2.0122 | 0.0000 | complete |
| RELIANCE_PE-2026-11-11T13:41:05.981460+05:30-BUY | 0.3690 | -1.1111 | -1.1111 | 1.4801 | complete |
| INFY_CE-2026-11-11T14:01:05.495244+05:30-BUY | -2.1090 | -4.7452 | -4.7452 | 2.6362 | complete |
| BANKNIFTY_PE-2026-11-11T14:21:21.479640+05:30-BUY | 15.5367 | 14.8406 | 14.8406 | 0.6961 | complete |
| HDFCBANK_PE-2026-11-12T10:11:04.590286+05:30-BUY | -17.0868 | N/A | N/A | N/A | lookback_incomplete |
| BANKNIFTY_PE-2026-11-12T10:27:19.572005+05:30-BUY | -11.8240 | N/A | N/A | N/A | lookback_incomplete |
| HDFCBANK_CE-2026-11-12T10:48:04.318098+05:30-BUY | -1.8450 | N/A | N/A | N/A | lookback_incomplete |
| ICICIBANK_PE-2026-11-12T12:06:04.624825+05:30-BUY | 8.9474 | 10.5405 | 10.5405 | 1.5932 | complete |
| RELIANCE_CE-2026-11-12T12:49:04.584964+05:30-BUY | 11.6095 | 12.6344 | 12.6344 | 1.0249 | complete |
| LT_CE-2026-11-12T13:09:06.550071+05:30-BUY | -9.2863 | -10.3653 | -10.3653 | 1.0790 | complete |
| RELIANCE_CE-2026-11-13T10:07:14.146387+05:30-BUY | 3.6145 | N/A | N/A | N/A | lookback_incomplete |
| HDFCBANK_PE-2026-11-13T10:12:13.629137+05:30-BUY | 29.6928 | N/A | N/A | N/A | lookback_incomplete |
| INFY_CE-2026-11-13T10:35:15.396028+05:30-BUY | 5.5085 | N/A | N/A | N/A | lookback_incomplete |
| BANKNIFTY_CE-2026-11-13T10:50:29.411239+05:30-BUY | 12.5096 | N/A | N/A | N/A | lookback_incomplete |
| TCS_PE-2026-11-16T10:25:13.642973+05:30-BUY | -2.4540 | N/A | N/A | N/A | lookback_incomplete |
| NIFTY_PE-2026-11-16T10:31:49.833340+05:30-BUY | -6.8994 | N/A | N/A | N/A | lookback_incomplete |
| BANKNIFTY_PE-2026-11-16T10:31:50.201800+05:30-BUY | -16.6906 | N/A | N/A | N/A | lookback_incomplete |
| RELIANCE_PE-2026-11-16T10:35:14.102813+05:30-BUY | 24.6711 | N/A | N/A | N/A | lookback_incomplete |
| RELIANCE_PE-2026-11-16T11:21:13.795869+05:30-BUY | 23.8710 | N/A | N/A | N/A | lookback_incomplete |
| TCS_CE-2026-11-16T12:16:13.670355+05:30-BUY | 0.7194 | -2.1327 | -2.1327 | 2.8521 | complete |
| INFY_PE-2026-11-16T12:53:13.327157+05:30-BUY | 6.9444 | 5.0000 | 5.0000 | 1.9444 | complete |

### Differences above 1 percentage point

- HDFCBANK_CE-2026-11-11T11:33:05.261555+05:30-BUY: recorded runtime 14.6789%, offline 13.1336%, difference 1.5453 pp.
- RELIANCE_PE-2026-11-11T13:41:05.981460+05:30-BUY: recorded runtime 0.3690%, offline -1.1111%, difference 1.4801 pp.
- INFY_CE-2026-11-11T14:01:05.495244+05:30-BUY: recorded runtime -2.1090%, offline -4.7452%, difference 2.6362 pp.
- ICICIBANK_PE-2026-11-12T12:06:04.624825+05:30-BUY: recorded runtime 8.9474%, offline 10.5405%, difference 1.5932 pp.
- RELIANCE_CE-2026-11-12T12:49:04.584964+05:30-BUY: recorded runtime 11.6095%, offline 12.6344%, difference 1.0249 pp.
- LT_CE-2026-11-12T13:09:06.550071+05:30-BUY: recorded runtime -9.2863%, offline -10.3653%, difference 1.0790 pp.
- TCS_CE-2026-11-16T12:16:13.670355+05:30-BUY: recorded runtime 0.7194%, offline -2.1327%, difference 2.8521 pp.
- INFY_PE-2026-11-16T12:53:13.327157+05:30-BUY: recorded runtime 6.9444%, offline 5.0000%, difference 1.9444 pp.

## Paired simulator

- Baseline entry: recorded PAPER ask fill and original quantity.
- Variant entry: the clock-aligned five-minute candle uses the completed one-minute bars whose timestamps are in `[HH:MM:00, HH:MM+5:00)`, accepting seconds offsets. All five minute buckets must be present, including the last completed minute. The candle close must strictly continue beyond the recorded one-minute confirmation close; entry uses the first valid archived option ask after the last minute has closed.
- Both arms use a 10% premium stop and a 20% target recalculated from that arm's ask entry, with identical quantity. If stop and target touch in one candle, stop wins. Stops use archived bid quotes when available; the session-end exit uses the last available bid. A target requires an observed bid at/above target.
- Fees are deducted on both executed orders using the configured PAPER charge model. Net R divides net rupees by 10% of entry ask times quantity. A valid no-continuation is zero R; missing data is excluded and shown in coverage.
- The best-trade exclusion removes the single highest baseline net-R trade from both arms to preserve the paired sample.

| Period | Reached | Passed | Failed | Expired | Data missing | Baseline n | Baseline mean net R | Baseline mean net ₹ | Variant n | Variant mean net R | Variant mean net ₹ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30-Oct to 11-Nov | 34 | 19 | 15 | 0 | 0 | 34 | 0.1660 | 261.6707 | 34 | -0.0823 | -84.7654 |
| 12-Nov to 16-Nov | 17 | 6 | 11 | 0 | 0 | 17 | -0.4653 | -820.3553 | 17 | -0.1753 | -274.0812 |
| All 51 | 51 | 25 | 26 | 0 | 0 | 51 | -0.0444 | -99.0046 | 51 | -0.1133 | -147.8707 |

### Without the best trade

| Period / sample | Excluded trade | Baseline n | Baseline mean net R | Baseline mean net ₹ | Variant n | Variant mean net R | Variant mean net ₹ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30-Oct to 11-Nov | LT_CE-2026-11-09T10:04:22.638133+05:30-BUY | 33 | 0.1006 | 162.8232 | 33 | -0.0848 | -87.3341 |
| 12-Nov to 16-Nov | LT_CE-2026-11-09T10:04:22.638133+05:30-BUY | 17 | -0.4653 | -820.3553 | 17 | -0.1753 | -274.0812 |
| All 51 | LT_CE-2026-11-09T10:04:22.638133+05:30-BUY | 50 | -0.0918 | -171.4575 | 50 | -0.1155 | -150.8281 |

Reconciliation: the earlier paired baseline without-best result (-0.0723 R, n=49) excluded SBIN_CE-2026-11-06T10:05:04.001399+05:30-BUY because its legacy replay window was incomplete. The corrected clock-window has all five minute buckets; its directional outcome is failed, so its baseline -1.0485 R is now included. The fixed-rule without-best paired baseline is therefore -0.0918 R (n=50), matching the baseline-only cohort.
- Baseline-only without-best: n=50, mean net R=-0.0918, mean net ₹=-171.4575.

## Recommendation

Do not recommend the 5-minute continuation rule: it does not win in both periods and/or without the best trade.

## Trade-level arm results

| Trade | Period | Run-up offline % | 5m result | Baseline net R | Variant net R |
| --- | --- | ---: | --- | ---: | ---: |
| NIFTY_PE-2026-10-30T10:07:21.189181+05:30-BUY | 30-Oct to 11-Nov | N/A | passed | -1.0731 | -1.0811 |
| RELIANCE_CE-2026-11-03T09:58:37.552708+05:30-BUY | 30-Oct to 11-Nov | N/A | passed | -1.1218 | -1.5225 |
| HDFCBANK_CE-2026-11-03T13:00:31.294452+05:30-BUY | 30-Oct to 11-Nov | N/A | failed | 0.5019 | 0.0000 |
| INFY_CE-2026-11-03T13:26:35.553817+05:30-BUY | 30-Oct to 11-Nov | N/A | passed | 0.0486 | -0.0916 |
| LT_PE-2026-11-04T10:19:50.401341+05:30-BUY | 30-Oct to 11-Nov | N/A | passed | 2.0411 | 1.9592 |
| RELIANCE_CE-2026-11-04T12:27:49.645890+05:30-BUY | 30-Oct to 11-Nov | -0.6803 | failed | 1.9486 | 0.0000 |
| SBIN_CE-2026-11-04T13:19:49.413291+05:30-BUY | 30-Oct to 11-Nov | 11.2583 | failed | 0.1654 | 0.0000 |
| TCS_CE-2026-11-04T14:25:53.154906+05:30-BUY | 30-Oct to 11-Nov | 0.4908 | passed | -0.0369 | -0.1668 |
| HDFCBANK_CE-2026-11-05T11:31:03.340974+05:30-BUY | 30-Oct to 11-Nov | 1.4706 | failed | 2.0499 | 0.0000 |
| RELIANCE_CE-2026-11-05T13:43:03.335864+05:30-BUY | 30-Oct to 11-Nov | 8.7452 | passed | -1.0541 | -1.0539 |
| LT_PE-2026-11-05T14:22:08.089786+05:30-BUY | 30-Oct to 11-Nov | 14.9109 | failed | -1.0804 | 0.0000 |
| SBIN_CE-2026-11-06T10:05:04.001399+05:30-BUY | 30-Oct to 11-Nov | N/A | failed | -1.0485 | 0.0000 |
| NIFTY_PE-2026-11-06T10:41:37.273817+05:30-BUY | 30-Oct to 11-Nov | N/A | passed | -1.1935 | -1.0582 |
| HDFCBANK_PE-2026-11-06T10:41:37.464399+05:30-BUY | 30-Oct to 11-Nov | N/A | failed | -1.1679 | 0.0000 |
| TCS_PE-2026-11-06T10:53:36.280612+05:30-BUY | 30-Oct to 11-Nov | N/A | passed | 0.6784 | -1.0484 |
| INFY_PE-2026-11-06T10:55:37.279923+05:30-BUY | 30-Oct to 11-Nov | N/A | passed | -1.2263 | -1.1677 |
| INFY_CE-2026-11-06T11:48:38.033746+05:30-BUY | 30-Oct to 11-Nov | -8.6287 | failed | -1.1553 | 0.0000 |
| BANKNIFTY_CE-2026-11-06T12:11:37.532648+05:30-BUY | 30-Oct to 11-Nov | 2.1709 | passed | 2.0181 | 2.1919 |
| LT_CE-2026-11-06T13:16:34.530139+05:30-BUY | 30-Oct to 11-Nov | 6.4477 | passed | 1.9814 | 2.1046 |
| TCS_CE-2026-11-06T13:16:36.537440+05:30-BUY | 30-Oct to 11-Nov | -8.8154 | failed | -0.3299 | 0.0000 |
| INFY_CE-2026-11-06T14:33:37.782767+05:30-BUY | 30-Oct to 11-Nov | 1.4519 | passed | 0.9663 | 0.7960 |
| LT_CE-2026-11-09T10:04:22.638133+05:30-BUY | 30-Oct to 11-Nov | N/A | failed | 2.3224 | 0.0000 |
| ICICIBANK_PE-2026-11-09T10:36:22.341814+05:30-BUY | 30-Oct to 11-Nov | N/A | passed | -1.1587 | -1.0520 |
| RELIANCE_CE-2026-11-09T11:28:22.855071+05:30-BUY | 30-Oct to 11-Nov | -4.3584 | passed | 2.1089 | 1.9894 |
| TCS_PE-2026-11-09T12:16:22.846458+05:30-BUY | 30-Oct to 11-Nov | -7.1380 | passed | -0.2982 | -0.9135 |
| INFY_CE-2026-11-09T12:51:24.338410+05:30-BUY | 30-Oct to 11-Nov | -11.7073 | passed | 0.7806 | 0.5245 |
| BANKNIFTY_PE-2026-11-09T13:16:57.381000+05:30-BUY | 30-Oct to 11-Nov | 3.6147 | failed | -1.1161 | 0.0000 |
| TCS_CE-2026-11-09T13:59:23.086457+05:30-BUY | 30-Oct to 11-Nov | 4.8864 | failed | 0.6013 | 0.0000 |
| HDFCBANK_CE-2026-11-11T11:33:05.261555+05:30-BUY | 30-Oct to 11-Nov | 13.1336 | passed | -1.0508 | -1.0894 |
| TCS_PE-2026-11-11T12:06:05.294871+05:30-BUY | 30-Oct to 11-Nov | N/A | failed | 1.9690 | 0.0000 |
| LT_PE-2026-11-11T13:39:05.480164+05:30-BUY | 30-Oct to 11-Nov | -2.0122 | failed | 1.9663 | 0.0000 |
| RELIANCE_PE-2026-11-11T13:41:05.981460+05:30-BUY | 30-Oct to 11-Nov | -1.1111 | passed | -1.0565 | -1.0553 |
| INFY_CE-2026-11-11T14:01:05.495244+05:30-BUY | 30-Oct to 11-Nov | -4.7452 | passed | -0.2501 | -1.0636 |
| BANKNIFTY_PE-2026-11-11T14:21:21.479640+05:30-BUY | 30-Oct to 11-Nov | 14.8406 | failed | -1.0870 | 0.0000 |
| HDFCBANK_PE-2026-11-12T10:11:04.590286+05:30-BUY | 12-Nov to 16-Nov | N/A | failed | -1.0461 | 0.0000 |
| BANKNIFTY_PE-2026-11-12T10:27:19.572005+05:30-BUY | 12-Nov to 16-Nov | N/A | failed | -1.0733 | 0.0000 |
| HDFCBANK_CE-2026-11-12T10:48:04.318098+05:30-BUY | 12-Nov to 16-Nov | N/A | failed | 0.2492 | 0.0000 |
| ICICIBANK_PE-2026-11-12T12:06:04.624825+05:30-BUY | 12-Nov to 16-Nov | 10.5405 | passed | -1.0539 | -1.0862 |
| RELIANCE_CE-2026-11-12T12:49:04.584964+05:30-BUY | 12-Nov to 16-Nov | 12.6344 | failed | -1.0804 | 0.0000 |
| LT_CE-2026-11-12T13:09:06.550071+05:30-BUY | 12-Nov to 16-Nov | -10.3653 | failed | -0.5728 | 0.0000 |
| RELIANCE_CE-2026-11-13T10:07:14.146387+05:30-BUY | 12-Nov to 16-Nov | N/A | passed | 2.0025 | -1.1925 |
| HDFCBANK_PE-2026-11-13T10:12:13.629137+05:30-BUY | 12-Nov to 16-Nov | N/A | passed | -1.8217 | 1.9388 |
| INFY_CE-2026-11-13T10:35:15.396028+05:30-BUY | 12-Nov to 16-Nov | N/A | failed | -1.0732 | 0.0000 |
| BANKNIFTY_CE-2026-11-13T10:50:29.411239+05:30-BUY | 12-Nov to 16-Nov | N/A | failed | -1.0528 | 0.0000 |
| TCS_PE-2026-11-16T10:25:13.642973+05:30-BUY | 12-Nov to 16-Nov | N/A | passed | 2.1458 | -0.3891 |
| NIFTY_PE-2026-11-16T10:31:49.833340+05:30-BUY | 12-Nov to 16-Nov | N/A | passed | -1.2732 | -1.0898 |
| BANKNIFTY_PE-2026-11-16T10:31:50.201800+05:30-BUY | 12-Nov to 16-Nov | N/A | passed | 1.9321 | -1.1605 |
| RELIANCE_PE-2026-11-16T10:35:14.102813+05:30-BUY | 12-Nov to 16-Nov | N/A | failed | -1.0466 | 0.0000 |
| RELIANCE_PE-2026-11-16T11:21:13.795869+05:30-BUY | 12-Nov to 16-Nov | N/A | failed | -1.0464 | 0.0000 |
| TCS_CE-2026-11-16T12:16:13.670355+05:30-BUY | 12-Nov to 16-Nov | -2.1327 | failed | -1.0468 | 0.0000 |
| INFY_PE-2026-11-16T12:53:13.327157+05:30-BUY | 12-Nov to 16-Nov | 5.0000 | failed | -1.0524 | 0.0000 |

## 17-Nov follow-up

- Reached: 5; passed: 3; failed: 2; expired: 0; data_missing: 0.

| Sample | Excluded trade | Baseline n | Baseline mean net R | Baseline mean net ₹ | Variant n | Variant mean net R | Variant mean net ₹ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All 5 | — | 5 | -1.0673 | -1766.1820 | 5 | -0.6671 | -1040.8070 |
| Without best | INFY_CE-2026-11-17T13:44:24.405269+05:30-BUY | 4 | -1.1142 | -1826.3400 | 4 | -0.8339 | -1301.0087 |
