#!/usr/bin/env python3
"""
backfill_from_csv.py  --  one-time historical backfill from manually-downloaded
OSE (and one USGS) CSV exports.

WHY THIS IS A MANUAL-DOWNLOAD STEP
The scheduled fetcher (fetch_ose_gauges.py) scrapes the last few days off each
OSE gauge's page. To load the whole irrigation season at once, each OSE site has a
CSV export button -- but that export is a server-side form submission whose
internal field names the page doesn't expose, and direct requests to the export
servlet return errors. So the reliable path is: you download the 21 OSE CSVs by hand
(check Discharge, set the start date, click CSV), put them in one folder, and
this script parses and merges them into the SAME data files the fetcher uses.

The USGS gauge for the dam discharge is an exception.  This script can access a full
year's worth of data directly.

HOW TO USE
  1. Next to this script, make a folder named:  backfill_csv
  2. For each of the 21 OSE gauges, on its OSE page:
        - check the Discharge box
        - set Start Date = 03/01 of this year
        - click the CSV button
        - save the file into the backfill_csv folder
     Tip: if you can, save each file with the gauge in its name (e.g.
     high_line.csv). The script also tries to auto-detect the gauge from the
     station name inside the file, but a good filename is a sure thing.
  3. Run:   python backfill_from_csv.py
     It harvests the USGS dam discharge data from USGS, finds the fruits of your human 
     downloads, merges all 22 into data/by_gauge/<slug>.csv, and rebuilds
     data/discharge_cfs_wide.csv. Existing readings are kept; history is added
     around them. Safe to re-run.

Only the standard library is used (plus whatever fetch_ose_gauges imports).

PRIOR YEARS
  To add a completed past year (e.g. 2024) as its own file the explorer can
  show, download that year's 21 OSE CSVs (set the OSE start/end dates to span the
  whole year), put them in a folder, and run, e.g.,

      python backfill_from_csv.py --year 2024 --dir backfill_2024

  That fetches the USGS dam data and combines it with your human downloaded data for
  the OSE gauges.  It writes a standalone data/discharge_cfs_wide_2024.csv and does NOT touch
  your live data or by_gauge files. If you omit --dir it looks for a folder
  named backfill_2024, then falls back to backfill_csv. Copy the resulting
  file into your repo's data/ folder; the explorer discovers it automatically.
"""

import argparse
import csv
import glob
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Reuse the fetcher's gauge list, slug rule, file format, and wide-table builder
# so the backfill produces byte-for-byte compatible output.
from fetch_ose_gauges import (
    GAUGES, slugify, load_existing, write_gauge_csv, build_wide, BY_GAUGE_DIR, DATA_DIR,
    USGS_DAM_NAME, fetch_usgs_discharge, make_session,
)

INPUT_DIR = Path(os.environ.get("OSE_BACKFILL_DIR", "backfill_csv"))

DT_FORMATS = ["%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
              "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]


def parse_dt(s):
    s = s.strip().strip('"')
    for f in DT_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def find_gauge(filename, text):
    """Identify which gauge a file belongs to, by filename then by content."""
    fslug = slugify(filename)
    # 1) filename contains a gauge slug (longest slug first to disambiguate
    #    e.g. 'barranco_alto' before 'barranco')
    for gid, name in sorted(GAUGES, key=lambda g: -len(slugify(g[1]))):
        if slugify(name) and slugify(name) in fslug:
            return gid, name
    # 2) an explicit id in the filename or the file body (e.g. id=22)
    m = re.search(r"id[=_-]?(\d+)", filename) or re.search(r"[?&]id=(\d+)", text)
    if m:
        gid = int(m.group(1))
        for g, name in GAUGES:
            if g == gid:
                return g, name
    # 3) the station's display name appears in the file (longest match wins)
    low = text.lower()
    best = None
    for gid, name in GAUGES:
        if name.lower() in low and (best is None or len(name) > len(best[1])):
            best = (gid, name)
    return best


def parse_csv_discharge(text):
    """Return {iso_timestamp: discharge_cfs} from an OSE CSV export."""
    rows = list(csv.reader(text.splitlines()))
    hdr_idx = disch_col = dt_col = None
    for i, r in enumerate(rows):
        low = [c.strip().lower() for c in r]
        dcol = next((j for j, c in enumerate(low) if "disch" in c), None)
        if dcol is not None:
            hdr_idx, disch_col = i, dcol
            dt_col = next((j for j, c in enumerate(low) if "date" in c or "time" in c), 0)
            break
    if hdr_idx is None:           # no recognizable header: assume col0=time, col1=cfs
        dt_col, disch_col, start = 0, 1, 0
    else:
        start = hdr_idx + 1

    out = {}
    for r in rows[start:]:
        if len(r) <= max(dt_col, disch_col):
            continue
        dt = parse_dt(r[dt_col])
        if dt is None:
            continue
        v = r[disch_col].strip().strip('"').replace(",", "")
        if v == "":
            continue
        try:
            val = float(v)
        except ValueError:
            continue
        out[dt.strftime("%Y-%m-%d %H:%M")] = val
    return out


def write_wide_from_cols(cols, out_path):
    """Write a standalone wide CSV (union-timestamp grid) from in-memory
    per-gauge readings, in the same format as the live discharge_cfs_wide.csv."""
    names = [USGS_DAM_NAME] + [name for _, name in GAUGES]   # dam first (upstream on top)
    all_ts = set()
    for n in names:
        all_ts.update(cols.get(n, {}))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp"] + names)
        for ts in sorted(all_ts):
            w.writerow([ts] + [cols.get(n, {}).get(ts, "") for n in names])
    return len(all_ts)


def run_year(year, input_dir):
    """Build a standalone data/discharge_cfs_wide_<year>.csv from a folder of
    that year's downloaded CSVs. Does NOT touch the live data or by_gauge files."""
    input_dir = Path(input_dir)
    if not input_dir.exists():
        print(f"Folder '{input_dir}' not found. Put {year}'s 21 downloaded CSVs in it.")
        return 1
    if year >= datetime.now().year:
        print(f"Note: {year} is the current year — the live discharge_cfs_wide.csv "
              f"already covers it. Building a year file anyway.")
    files = sorted(set(glob.glob(str(input_dir / "*.csv")) +
                       glob.glob(str(input_dir / "*.CSV"))))
    if not files:
        print(f"No .csv files found in '{input_dir}'.")
        return 1

    cols, matched = {}, set()
    for fp in files:
        base = os.path.basename(fp)
        text = Path(fp).read_text(encoding="latin-1")   # OSE pages are ISO-8859-1
        g = find_gauge(base, text)
        if not g:
            print(f"[skip] {base:<28} couldn't identify the gauge — rename it to "
                  f"include the gauge name (e.g. high_line.csv).")
            continue
        gid, name = g
        readings = parse_csv_discharge(text)
        # keep only this calendar year, guarding against stray adjacent-year rows
        readings = {ts: v for ts, v in readings.items() if ts[:4] == str(year)}
        if not readings:
            print(f"[warn] {base:<28} -> {name}: no {year} discharge rows parsed.")
            continue
        d = cols.setdefault(name, {})
        for ts, v in readings.items():
            d[ts] = f"{v:g}"
        matched.add(name)
        lo, hi = min(readings), max(readings)
        print(f"[ok]   {name:<20} <- {base:<26} {len(readings):>6} rows  {lo} .. {hi}")

    # Nambe dam (USGS) for this year — fetched directly, added as the first column.
    try:
        dam = fetch_usgs_discharge(make_session(),
                                   start=f"{year}-01-01", end=f"{year}-12-31")
        dam = {ts: v for ts, v in dam.items() if ts[:4] == str(year)}
        if dam:
            cols[USGS_DAM_NAME] = {ts: f"{v:g}" for ts, v in dam.items()}
            print(f"[ok]   {USGS_DAM_NAME:<20} <- USGS {len(dam):>6} rows")
        else:
            print(f"[warn] {USGS_DAM_NAME}: USGS returned no {year} data.")
    except Exception as e:
        print(f"[warn] {USGS_DAM_NAME}: USGS fetch failed ({e}); the year file will "
              f"have an empty dam column.")

    out = DATA_DIR / f"discharge_cfs_wide_{year}.csv"
    n_ts = write_wide_from_cols(cols, out)
    print(f"\nWrote {out}  ({len(matched)}/{len(GAUGES)} gauges, {n_ts} timestamps).")
    print("Standalone file — your live data and by_gauge files were NOT touched.")
    if len(matched) < len(GAUGES):
        missing = [n for _, n in GAUGES if n not in matched]
        print("No file matched for: " + ", ".join(missing))
    print(f"Copy {out.name} into your repo's data/ folder; the explorer finds it automatically.")
    return 0


def main():
    if not INPUT_DIR.exists():
        print(f"Make a folder named '{INPUT_DIR}' next to this script and put the "
              f"21 downloaded CSV files in it, then run this again.")
        return 1
    files = sorted(set(glob.glob(str(INPUT_DIR / "*.csv")) +
                       glob.glob(str(INPUT_DIR / "*.CSV"))))
    if not files:
        print(f"No .csv files found in '{INPUT_DIR}'.")
        return 1

    gauge_files = ([(USGS_DAM_NAME, BY_GAUGE_DIR / f"{slugify(USGS_DAM_NAME)}.csv")] +
                   [(name, BY_GAUGE_DIR / f"{slugify(name)}.csv") for _, name in GAUGES])
    matched = set()
    for fp in files:
        base = os.path.basename(fp)
        text = Path(fp).read_text(encoding="latin-1")   # OSE pages are ISO-8859-1
        g = find_gauge(base, text)
        if not g:
            print(f"[skip] {base:<28} couldn't identify the gauge — rename it to "
                  f"include the gauge name (e.g. high_line.csv).")
            continue
        gid, name = g
        readings = parse_csv_discharge(text)
        if not readings:
            print(f"[warn] {base:<28} -> {name}: no discharge rows parsed.")
            continue
        path = BY_GAUGE_DIR / f"{slugify(name)}.csv"
        existing = load_existing(path)
        before = len(existing)
        for ts, v in readings.items():
            existing.setdefault(ts, f"{v:g}")   # keep live-fetcher values; backfill the rest
        write_gauge_csv(path, existing)
        lo, hi = min(readings), max(readings)
        print(f"[ok]   {name:<20} <- {base:<26} {len(readings):>6} rows  "
              f"{lo} .. {hi}  (+{len(existing)-before} new)")
        matched.add(name)

    # Nambe dam (USGS): merge this year's history into its by_gauge log, keeping
    # whatever the live fetcher already collected. Mirrors the --year behavior so
    # both modes fill in the dam column the same way.
    year = datetime.now().year
    dam_path = BY_GAUGE_DIR / f"{slugify(USGS_DAM_NAME)}.csv"
    try:
        dam = fetch_usgs_discharge(make_session(),
                                   start=f"{year}-01-01", end=f"{year}-12-31")
        dam = {ts: v for ts, v in dam.items() if ts[:4] == str(year)}
        existing = load_existing(dam_path)
        before = len(existing)
        for ts, v in dam.items():
            existing.setdefault(ts, f"{v:g}")   # keep live-fetcher values; backfill the rest
        write_gauge_csv(dam_path, existing)
        print(f"[ok]   {USGS_DAM_NAME:<20} <- USGS {len(dam):>6} rows  "
              f"(+{len(existing)-before} new)")
    except Exception as e:
        print(f"[warn] {USGS_DAM_NAME}: USGS fetch failed ({e}); kept existing by_gauge data.")

    build_wide(gauge_files)
    print(f"\nMerged {len(matched)}/{len(GAUGES)} gauges; rebuilt the wide table.")
    if len(matched) < len(GAUGES):
        missing = [n for _, n in GAUGES if n not in matched]
        print("No file matched for: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Backfill OSE discharge data from manually-downloaded CSVs.")
    ap.add_argument("--year", type=int, metavar="YYYY",
                    help="Build a standalone data/discharge_cfs_wide_YYYY.csv for a "
                         "prior year (does not touch the live data or by_gauge files).")
    ap.add_argument("--dir", metavar="FOLDER",
                    help="Folder holding that year's downloaded CSVs "
                         "(default: backfill_<year>, else backfill_csv).")
    args = ap.parse_args()
    if args.year:
        folder = args.dir or (f"backfill_{args.year}"
                              if Path(f"backfill_{args.year}").exists() else str(INPUT_DIR))
        raise SystemExit(run_year(args.year, folder))
    raise SystemExit(main())
