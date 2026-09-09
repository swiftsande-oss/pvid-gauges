#!/usr/bin/env python3
"""
schedule_from_pdf.py -- convert a PVID irrigation-cycle PDF into the CSV the
PVID Gauge Explorer uses for its schedule underlays.

WHAT IT DOES
  Reads a "Water Diversion Schedule" PDF for one cycle, pulls each acequia's
  scheduled diversion (flow in cfs, start datetime, end datetime), and writes:

    data/<year>cycle<n>.csv    columns:  acequia,cfs,start,end   (ISO datetimes)
    data/schedules.json        a small manifest the explorer reads to build its
                               SCHEDULES buttons (name, year, date range).

  The PDF's acequia labels are mapped to the explorer's gauge names. Any row it
  can't confidently map -- notably the Highline / Consolidated special cases --
  is written with its RAW label and loudly flagged, so you fix the name by hand.
  Nothing is silently guessed.

USAGE
  pip install pdfplumber
  python schedule_from_pdf.py PVID_..._cycle1_....pdf
        -> auto-detects year + cycle number, writes data/2026cycle1.csv
  python schedule_from_pdf.py file.pdf --out data/2026cycle2.csv --cycle 2 --year 2026

ALWAYS open the CSV and check it before trusting it 
         -- a wrong row is worse than a missing one.
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("This tool needs pdfplumber.  Install it with:  pip install pdfplumber")

DATA_DIR = Path("data")

# The explorer's gauge names (the CSV's acequia field must match one of these
# for a schedule row to render).
GAUGES = ["High Line", "Upper Consolidated", "Lower Consolidated", "Nueva", "Llano",
          "Comunidad", "Ortiz", "Gardunos", "Jose G. Ortiz", "Cano", "Rincon",
          "Las Joyas", "Trujillos", "Barranco Alto", "Larga", "Ancon de Jacona",
          "Barranco", "Otra Vanda", "Rancho", "Indios", "San Ildefonso"]

# PDF-label keyword -> gauge. Matching is done on a NORMALIZED form of the label:
# lowercased, with all punctuation and spaces stripped. So "High Line",
# "Highline", "High line", and "HIGH-LINE" all match; "Jose G Ortiz" matches even
# if someone drops the period. Keys below are written normally and normalized at
# load time -- just add a new spelling to the list if one shows up.
#
# Ordered most-specific first, so "jose g. ortiz" wins over "ortiz" and
# "barranco alto" wins over "barranco".
NAME_KEYS_RAW = [
    ("high line", "High Line"), ("highline", "High Line"),
    ("upper consolidated", "Upper Consolidated"),
    ("lower consolidated", "Lower Consolidated"),
    ("jose g. ortiz", "Jose G. Ortiz"), ("jose g ortiz", "Jose G. Ortiz"),
    ("barranco alto", "Barranco Alto"),
    ("ancon de jacona", "Ancon de Jacona"),
    ("otra vanda", "Otra Vanda"), ("otra banda", "Otra Vanda"),   # both spellings seen
    ("san ildefonso", "San Ildefonso"),
    ("joyas", "Las Joyas"),
    ("comunidad", "Comunidad"),
    ("gardunos", "Gardunos"),
    ("trujillos", "Trujillos"),
    ("rincon", "Rincon"),
    ("larga", "Larga"),
    ("nueva", "Nueva"),
    ("llano", "Llano"),
    ("cano", "Cano"),
    ("indios", "Indios"),
    ("rancho", "Rancho"),
    ("ortiz", "Ortiz"),
    ("barranco", "Barranco"),
]


def normalize(s):
    """Lowercase and strip everything that isn't a letter or digit, so spelling,
    spacing, capitalization, and punctuation stop mattering:
    'High Line', 'Highline', 'HIGH-LINE' -> 'highline'."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


# keys pre-normalized once, longest first so specific names beat general ones
NAME_KEYS = sorted(((normalize(k), g) for k, g in NAME_KEYS_RAW),
                   key=lambda kv: -len(kv[0]))

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}

# Weekday, Month D, YYYY  H:MM AM/PM  (locale-independent: we read the month name
# ourselves rather than relying on strptime's locale)
DT_RE = re.compile(
    r"[A-Za-z]+,\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})\s+(\d{1,2}):(\d{2})\s+([AP]M)")


def parse_dt(m):
    mon, day, year = m.group(1), int(m.group(2)), int(m.group(3))
    hh, mm, ap = int(m.group(4)), int(m.group(5)), m.group(6)
    mon_n = MONTHS.get(mon.lower())
    if not mon_n:
        return None
    if ap == "PM" and hh != 12:
        hh += 12
    if ap == "AM" and hh == 12:
        hh = 0
    return f"{year:04d}-{mon_n:02d}-{day:02d} {hh:02d}:{mm:02d}"


def _days(iso):
    """Days-since-epoch for an 'YYYY-MM-DD HH:MM' string (for duration checks)."""
    from datetime import datetime as _dt
    return _dt.strptime(iso, "%Y-%m-%d %H:%M").timestamp() / 86400.0


def map_name(label):
    low = normalize(label)
    for key, gauge in NAME_KEYS:
        if key in low:
            return gauge
    return None


def parse_pdf(path):
    """Return (rows, unmatched, cycle_num). rows = [(name, cfs, start, end, matched)]."""
    with pdfplumber.open(path) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)

    cyc = re.search(r"Cycle\s*No\.?\s*(\d+)", text, re.I)
    cycle_num = int(cyc.group(1)) if cyc else None

    rows, unmatched = [], []
    for line in text.splitlines():
        dts = list(DT_RE.finditer(line))
        if len(dts) != 2:
            continue                                   # a data row needs a start AND an end datetime
        start, end = parse_dt(dts[0]), parse_dt(dts[1])
        if not start or not end:
            continue
        prefix = line[:dts[0].start()].strip()
        prefix = re.sub(r"^SD-\d+\s*", "", prefix)      # drop the OSE SD code if present
        m = re.match(r"^(.*)\s+([\d.]+)\s+([\d.]+)$", prefix)   # <label>  <Days>  <CFS>
        if not m:
            continue
        label, cfs = m.group(1).strip(), float(m.group(3))
        gauge = map_name(label)
        if gauge is None:
            unmatched.append(label)
            rows.append((label, cfs, start, end, False))
        else:
            rows.append((gauge, cfs, start, end, True))
    return rows, unmatched, cycle_num


def update_manifest(entry):
    path = DATA_DIR / "schedules.json"
    data = {"cycles": []}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except Exception:
            pass
    cycles = [c for c in data.get("cycles", []) if c.get("file") != entry["file"]]
    cycles.append(entry)
    cycles.sort(key=lambda c: (c.get("year", 0), c.get("num", 0)))
    path.write_text(json.dumps({"cycles": cycles}, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Convert a PVID cycle PDF to the explorer's schedule CSV.")
    ap.add_argument("pdf", help="the cycle PDF from the PVID manager")
    ap.add_argument("--out", help="output CSV path (default: data/<year>cycle<n>.csv)")
    ap.add_argument("--cycle", type=int, help="override the cycle number")
    ap.add_argument("--year", type=int, help="override the year")
    args = ap.parse_args()

    if not Path(args.pdf).exists():
        sys.exit(f"Can't find {args.pdf}")

    rows, unmatched, cycle_num = parse_pdf(args.pdf)
    if not rows:
        sys.exit("No schedule rows found. Is this a PVID diversion-schedule PDF?")

    cycle_num = args.cycle or cycle_num
    year = args.year or int(rows[0][2][:4])
    if cycle_num is None:
        sys.exit("Couldn't read the cycle number from the PDF; pass --cycle N.")

    # Sanity-check the dates the same way the explorer does, so a mis-parsed row
    # is caught here rather than drawn as a confident wrong rectangle on the site.
    date_warnings = []
    for name, cfs, start, end, matched in rows:
        sy, ey = int(start[:4]), int(end[:4])
        if sy != year or ey != year:
            date_warnings.append(f"{name}: date not in {year} ({start} .. {end})")
        elif end <= start:
            date_warnings.append(f"{name}: end not after start ({start} .. {end})")
        elif (_days(end) - _days(start)) > 60:
            date_warnings.append(f"{name}: spans over 60 days ({start} .. {end})")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else DATA_DIR / f"{year}cycle{cycle_num}.csv"

    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["acequia", "cfs", "start", "end"])
        for name, cfs, start, end, matched in rows:
            w.writerow([name, f"{cfs:g}", start, end])

    starts = [r[2] for r in rows]
    ends = [r[3] for r in rows]
    update_manifest({"name": f"Cycle {cycle_num}", "year": year, "num": cycle_num,
                     "file": out.name, "start": min(starts), "end": max(ends)})

    matched = sum(1 for r in rows if r[4])
    print(f"Wrote {out}  ({len(rows)} rows, {matched} mapped to gauges).")
    print(f"Cycle {cycle_num}, {year}:  {min(starts)}  ..  {max(ends)}")
    print(f"Updated {DATA_DIR / 'schedules.json'}.")
    if date_warnings:
        print("\n*** DATE PROBLEMS -- check these rows against the PDF (likely a "
              "mis-read date) ***")
        for d in date_warnings:
            print(f"    {d}")
    if unmatched:
        print("\n*** COULD NOT MAP these labels to a gauge -- edit the 'acequia' "
              "field in the CSV by hand ***")
        for u in unmatched:
            print(f"    {u!r}")
    print("\nReview the CSV before committing it. Copy it (and schedules.json) into "
          "your repo's data/ folder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
