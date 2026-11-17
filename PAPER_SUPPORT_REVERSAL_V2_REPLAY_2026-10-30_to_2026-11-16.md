# PAPER support-reversal v2 paired replay

Closed PAPER options replayed: **51** (2026-10-30 to 2026-11-16).
Exact support-reversal route cohort: **44**; other routes are unchanged/pass-through.
Baseline complete exits: **51/51**.
Best baseline trade removed from each period's no-best columns: 30-Oct to 11-Nov: `LT_CE-2026-11-09T10:04:22.638133+05:30-BUY`; 12-Nov to 16-Nov: `TCS_PE-2026-11-16T10:25:13.642973+05:30-BUY`.

The paired arms use the archived option candle and quote/bid paths. Both use the same fixed PAPER exit simulator: 10% premium stop backstop, 20% target, stop-first on same-candle stop/target touches, session-end bid exit, and configured PAPER fees on both orders. Dropped entries contribute zero net R and rupees; missing replay paths are excluded from both arms. Mean net R and net rupees are therefore paired portfolio results, while `kept` counts only complete trades in the eligible support-reversal cohort.

For `reversal_confirm_v2`, the signal's recorded pivot and direction are matched to completed decision-journal rows. A complete, contiguous, wall-clock 5-minute underlying candle must start after the signal, test the level within 0.10%, close in the directional 60% of its range, and complete within 15 minutes. Entry uses the first valid archived ask at or after that candle's completion.

For `level_stop_v2`, entry is skipped when the last completed underlying close before entry is more than `d` from the pivot. A completed 1-minute close beyond the pivot by `b` exits at the first valid archived option bid at or after that close; the premium stop remains active as backstop. Grid values are in percent.

| Period | Variant | Paired n | Support kept | Wins lost | Mean net R (base / variant) | Net ₹ (base / variant) | Without best mean net R (base / variant) | Without best net ₹ (base / variant) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30-Oct to 11-Nov | reversal_confirm_v2 | 34 | 3/29 | 13 | 0.1660 / -0.0299 | 8896.81 / -265.65 | 0.1006 / -0.0308 | 5373.17 / -265.65 |
| 30-Oct to 11-Nov | level_stop_v2 b=0.05% d=0.20% | 34 | 2/29 | 13 | 0.1660 / 0.0052 | 8896.81 / 1131.73 | 0.1006 / 0.0054 | 5373.17 / 1131.73 |
| 30-Oct to 11-Nov | level_stop_v2 b=0.05% d=0.30% | 34 | 11/29 | 11 | 0.1660 / -0.1402 | 8896.81 / -3645.78 | 0.1006 / -0.1445 | 5373.17 / -3645.78 |
| 30-Oct to 11-Nov | level_stop_v2 b=0.05% d=0.40% | 34 | 23/29 | 4 | 0.1660 / 0.0749 | 8896.81 / 3773.65 | 0.1006 / 0.0772 | 5373.17 / 3773.65 |
| 30-Oct to 11-Nov | level_stop_v2 b=0.10% d=0.20% | 34 | 2/29 | 13 | 0.1660 / 0.0052 | 8896.81 / 1131.73 | 0.1006 / 0.0054 | 5373.17 / 1131.73 |
| 30-Oct to 11-Nov | level_stop_v2 b=0.10% d=0.30% | 34 | 11/29 | 11 | 0.1660 / -0.1402 | 8896.81 / -3645.78 | 0.1006 / -0.1445 | 5373.17 / -3645.78 |
| 30-Oct to 11-Nov | level_stop_v2 b=0.10% d=0.40% | 34 | 23/29 | 4 | 0.1660 / 0.0749 | 8896.81 / 3773.65 | 0.1006 / 0.0772 | 5373.17 / 3773.65 |
| 30-Oct to 11-Nov | level_stop_v2 b=0.15% d=0.20% | 34 | 2/29 | 13 | 0.1660 / 0.0052 | 8896.81 / 1131.73 | 0.1006 / 0.0054 | 5373.17 / 1131.73 |
| 30-Oct to 11-Nov | level_stop_v2 b=0.15% d=0.30% | 34 | 11/29 | 11 | 0.1660 / -0.1402 | 8896.81 / -3645.78 | 0.1006 / -0.1445 | 5373.17 / -3645.78 |
| 30-Oct to 11-Nov | level_stop_v2 b=0.15% d=0.40% | 34 | 23/29 | 4 | 0.1660 / 0.0749 | 8896.81 / 3773.65 | 0.1006 / 0.0772 | 5373.17 / 3773.65 |
| 12-Nov to 16-Nov | reversal_confirm_v2 | 17 | 2/15 | 3 | -0.4653 / -0.1508 | -13946.04 / -4020.68 | -0.6285 / -0.1602 | -17031.16 / -4020.68 |
| 12-Nov to 16-Nov | level_stop_v2 b=0.05% d=0.20% | 17 | 2/15 | 3 | -0.4653 / -0.1441 | -13946.04 / -3793.08 | -0.6285 / -0.1532 | -17031.16 / -3793.08 |
| 12-Nov to 16-Nov | level_stop_v2 b=0.05% d=0.30% | 17 | 5/15 | 3 | -0.4653 / -0.3304 | -13946.04 / -9866.72 | -0.6285 / -0.3510 | -17031.16 / -9866.72 |
| 12-Nov to 16-Nov | level_stop_v2 b=0.05% d=0.40% | 17 | 10/15 | 2 | -0.4653 / -0.5227 | -13946.04 / -14480.76 | -0.6285 / -0.5554 | -17031.16 / -14480.76 |
| 12-Nov to 16-Nov | level_stop_v2 b=0.10% d=0.20% | 17 | 2/15 | 3 | -0.4653 / -0.1441 | -13946.04 / -3793.08 | -0.6285 / -0.1532 | -17031.16 / -3793.08 |
| 12-Nov to 16-Nov | level_stop_v2 b=0.10% d=0.30% | 17 | 5/15 | 3 | -0.4653 / -0.3304 | -13946.04 / -9866.72 | -0.6285 / -0.3510 | -17031.16 / -9866.72 |
| 12-Nov to 16-Nov | level_stop_v2 b=0.10% d=0.40% | 17 | 10/15 | 2 | -0.4653 / -0.5227 | -13946.04 / -14480.76 | -0.6285 / -0.5554 | -17031.16 / -14480.76 |
| 12-Nov to 16-Nov | level_stop_v2 b=0.15% d=0.20% | 17 | 2/15 | 3 | -0.4653 / -0.1441 | -13946.04 / -3793.08 | -0.6285 / -0.1532 | -17031.16 / -3793.08 |
| 12-Nov to 16-Nov | level_stop_v2 b=0.15% d=0.30% | 17 | 5/15 | 3 | -0.4653 / -0.3304 | -13946.04 / -9866.72 | -0.6285 / -0.3510 | -17031.16 / -9866.72 |
| 12-Nov to 16-Nov | level_stop_v2 b=0.15% d=0.40% | 17 | 10/15 | 2 | -0.4653 / -0.5227 | -13946.04 / -14480.76 | -0.6285 / -0.5554 | -17031.16 / -14480.76 |

## Decision

Both flags remain **OFF**. No candidate beat baseline in both periods for both mean net R and net rupees, including each period's no-best result.
`reversal_confirm_v2` dropped 39 eligible signals for no qualifying confirmation.
Level-stop entry skips by grid: level_stop_v2 b=0.05% d=0.20%: 40, level_stop_v2 b=0.05% d=0.30%: 28, level_stop_v2 b=0.05% d=0.40%: 11, level_stop_v2 b=0.10% d=0.20%: 40, level_stop_v2 b=0.10% d=0.30%: 28, level_stop_v2 b=0.10% d=0.40%: 11, level_stop_v2 b=0.15% d=0.20%: 40, level_stop_v2 b=0.15% d=0.30%: 28, level_stop_v2 b=0.15% d=0.40%: 11.

## Coverage

- Support-route rows with archived pivot metadata: 44/44.
- Missing baseline exit paths: 0.
- Confirmation alternatives with missing ask/exit path: 0.
- Other variants with missing decision/underlying/option paths are excluded from their paired metric denominators, not imputed.
