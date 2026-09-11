#!/usr/bin/env python3
"""
archiveYear.py -- freeze a finished year as a browsable "prior year" file.

It reads the accumulated per-gauge logs in data/by_gauge/ and writes
data/discharge_cfs_wide_<year>.csv (dam column first, then the 21 acequias),
in the same format as the live wide file.

SAFE AND ADDITIVE: it only READS by_gauge and WRITES one new prior-year file.
It never touches the live discharge_cfs_wide.csv or the by_gauge logs, so it
cannot disturb the running site or make you a second author of the Action's data.

WHEN TO RUN: once, early in the new year (any time -- the data waits safely in
by_gauge). The live wide file rolls itself over to the new year automatically;
this just captures the year that ended so the explorer can show it under
"Prior years".

Usage:
  python archiveYear.py            # archive last year (this year - 1)
  python archiveYear.py --year 2026
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from fetch_ose_gauges import (
    GAUGES, slugify, load_existing, BY_GAUGE_DIR, DATA_DIR, USGS_DAM_NAME,
)


def main():
    ap = argparse.ArgumentParser(description="Archive a finished year from by_gauge logs.")
    ap.add_argument("--year", type=int, metavar="YYYY",
                    help="year to archive (default: last year)")
    args = ap.parse_args()
    year = args.year or (datetime.now().year - 1)
    ys = str(year)

    names = [USGS_DAM_NAME] + [name for _, name in GAUGES]   # dam first (upstream on top)
    cols, all_ts = {}, set()
    for nm in names:
        path = BY_GAUGE_DIR / f"{slugify(nm)}.csv"
        d = {ts: v for ts, v in load_existing(path).items() if ts[:4] == ys}
        cols[nm] = d
        all_ts.update(d)

    if not all_ts:
        sys.exit(f"No {year} data found in {BY_GAUGE_DIR}. Nothing to archive.")

    out = DATA_DIR / f"discharge_cfs_wide_{year}.csv"
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp"] + names)
        for ts in sorted(all_ts):
            w.writerow([ts] + [cols[nm].get(ts, "") for nm in names])

    print(f"Wrote {out}  ({len(all_ts)} timestamps, {len(names)} gauges).")
    print("Additive only -- the live data and by_gauge logs were not touched.")
    print(f"Commit {out.name}, then finish the new-year chores (season dates, "
          f"irrigable acres, and adjustments file).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
