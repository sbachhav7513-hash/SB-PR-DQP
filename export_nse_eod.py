"""Export filtered daily NSE F&O bhavcopies; this is EOD data, not intraday history."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import pathlib
import urllib.error
import urllib.request
import zipfile

DEFAULT_UNDERLYINGS = (
    "NIFTY,BANKNIFTY,RELIANCE,HDFCBANK,ICICIBANK,SBIN,INFY,TCS,LT,TATAMOTORS"
)
REQUIRED_COLUMNS = {
    "TradDt",
    "TckrSymb",
    "XpryDt",
    "FininstrmActlXpryDt",
    "FinInstrmNm",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "LastPric",
    "TtlTradgVol",
    "OpnIntrst",
}


def export_day(day: dt.date, underlyings: set[str], output_dir: pathlib.Path) -> dict:
    date_text = day.strftime("%Y%m%d")
    url = (
        "https://nsearchives.nseindia.com/content/fo/"
        f"BhavCopy_NSE_FO_0_0_0_{date_text}_F_0000.csv.zip"
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.nseindia.com/all-reports-derivatives",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            archive_bytes = response.read()
        source_hash = hashlib.sha256(archive_bytes).hexdigest()
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                return {
                    "date": day.isoformat(),
                    "status": "unexpected_archive_members",
                    "url": url,
                    "members": csv_names,
                }
            with archive.open(csv_names[0]) as binary:
                text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
                reader = csv.DictReader(text)
                fields = reader.fieldnames
                if not fields or not REQUIRED_COLUMNS.issubset(fields):
                    return {
                        "date": day.isoformat(),
                        "status": "unexpected_schema",
                        "url": url,
                        "fields": fields or [],
                    }
                selected = []
                counts: dict[str, int] = {}
                for row in reader:
                    symbol = row.get("TckrSymb", "")
                    if symbol in underlyings:
                        selected.append(row)
                        counts[symbol] = counts.get(symbol, 0) + 1

        if not selected:
            return {
                "date": day.isoformat(),
                "status": "no_matching_rows",
                "url": url,
                "archive_bytes": len(archive_bytes),
                "source_zip_sha256": source_hash,
            }

        destination = output_dir / "daily_contract_rows" / f"nse_fo_eod_{date_text}.csv.gz"
        with gzip.open(destination, "wt", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(selected)

        return {
            "date": day.isoformat(),
            "status": "downloaded",
            "url": url,
            "file": destination.as_posix(),
            "archive_bytes": len(archive_bytes),
            "filtered_rows": len(selected),
            "underlying_counts": counts,
            "source_zip_sha256": source_hash,
        }
    except urllib.error.HTTPError as error:
        return {"date": day.isoformat(), "status": f"http_{error.code}", "url": url}
    except Exception as error:
        return {
            "date": day.isoformat(),
            "status": f"error_{type(error).__name__}",
            "url": url,
            "detail": str(error)[:250],
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download filtered daily NSE F&O bhavcopies (not intraday data)."
    )
    parser.add_argument("--start", default="2026-03-29", help="First date, inclusive (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-09-28", help="Last date, inclusive (YYYY-MM-DD)")
    parser.add_argument("--out-dir", default="data_uploads/nse_eod")
    parser.add_argument("--underlyings", default=DEFAULT_UNDERLYINGS)
    args = parser.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    if start > end:
        parser.error("--start must be on or before --end")
    underlyings = {symbol.strip().upper() for symbol in args.underlyings.split(",") if symbol.strip()}
    if not underlyings:
        parser.error("at least one underlying is required")

    output_dir = pathlib.Path(args.out_dir)
    (output_dir / "daily_contract_rows").mkdir(parents=True, exist_ok=True)
    weekdays = [
        start + dt.timedelta(days=offset)
        for offset in range((end - start).days + 1)
        if (start + dt.timedelta(days=offset)).weekday() < 5
    ]

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(export_day, day, underlyings, output_dir) for day in weekdays]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            if result["status"] == "downloaded":
                print(f"{result['date']} rows={result['filtered_rows']} downloaded", flush=True)
            else:
                print(f"{result['date']} {result['status']}", flush=True)

    results.sort(key=lambda row: row["date"])
    manifest_columns = [
        "date",
        "status",
        "file",
        "url",
        "archive_bytes",
        "filtered_rows",
        "underlying_counts",
        "source_zip_sha256",
        "detail",
    ]
    with (output_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=manifest_columns, extrasaction="ignore")
        writer.writeheader()
        for result in results:
            row = dict(result)
            if "underlying_counts" in row:
                row["underlying_counts"] = json.dumps(row["underlying_counts"], sort_keys=True)
            writer.writerow(row)

    metadata = {
        "source": "NSE official F&O daily bhavcopy archive",
        "start_date_inclusive": start.isoformat(),
        "end_date_inclusive": end.isoformat(),
        "underlyings": sorted(underlyings),
        "weekday_dates_checked": len(weekdays),
        "successful_days": sum(row["status"] == "downloaded" for row in results),
        "total_filtered_rows": sum(row.get("filtered_rows", 0) for row in results),
        "data_granularity": "daily EOD only",
        "fields_present": [
            "contract symbol",
            "underlying",
            "expiry",
            "OHLC",
            "last price",
            "volume",
            "open interest",
        ],
        "fields_absent": ["minute bars", "historical bid", "historical ask"],
        "warning": "Not suitable as input to the requested 1-minute production replay.",
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print("SUMMARY", json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
