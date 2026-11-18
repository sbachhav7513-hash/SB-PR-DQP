# Data gaps

## Missing dates
- 2026-10-20
- 2026-10-27
- 2026-11-02
- 2026-11-10

## 10-Nov
- 10-Nov-2026 has no trade archive directory and no decision archive in the requested data.

## VIX
- No usable VIX candle or index field was found in the archive set.

## Pivot fields
- Pivot-named columns in decision archives: none.
Some trade/decision rows contain pivot metadata in nested JSON, but there is no complete consistent pivot field.

## Gap table

| gap | date | symbol | detail |
| --- | --- | --- | --- |
| missing KITE underlying bar | 2026-10-20 | NIFTY | No underlyings CSV in kite_daily |
| missing KITE underlying bar | 2026-10-20 | BANKNIFTY | No underlyings CSV in kite_daily |
| missing KITE underlying bar | 2026-11-10 | NIFTY | No underlyings CSV in kite_daily |
| missing KITE underlying bar | 2026-11-10 | BANKNIFTY | No underlyings CSV in kite_daily |
| 10-Nov archive | 2026-11-10 | ALL | No trade or decision archive directory found |
| VIX | ALL | VIX | No VIX archive file found |
| pivot fields | ALL | ALL | Archived pivot columns: none |