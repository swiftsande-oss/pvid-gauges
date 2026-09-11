#!/usr/bin/env python3
"""
fetch_ose_gauges.py
Scheduled fetcher for NM OSE/ISC real-time flow gauges (meas.ose.state.nm.us).

For each configured gauge it downloads the public site page and extracts every
(timestamp, discharge_cfs) reading currently shown. The site exposes roughly the
last 3-4 days at 15-minute cadence, so running on a schedule (at least every few
days; hourly or 6-hourly recommended) accumulates a continuous record over time
with no gaps. Values within the visible window are refreshed each run, which lets
OSE's provisional revisions settle in before they scroll out of view and freeze.

Outputs (under DATA_DIR, default ./data):
  data/by_gauge/<slug>.csv      tidy per-gauge log:  timestamp,discharge_cfs
  data/discharge_cfs_wide.csv   merged wide table:   timestamp + one col / gauge
  data/last_run.json            run summary / per-gauge status

Only dependency beyond the stdlib is `requests`.
"""

import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Site -------------------------------------------------------------------
BASE_URL = "https://meas.ose.state.nm.us/site.jsp"
COMMON = {"status": "Y", "type": "S", "dist": "6", "basin": "NPT"}

# --- Nambe dam release (USGS), the upstream reference gauge -----------------
# This one gauge comes from USGS, not OSE. It's the dam discharge upstream of
# all the acequias, shown as a reference curve (no Adjust arithmetic, no
# schedule). It lands as the FIRST column of the wide table (upstream on top).
USGS_DAM_NAME = "Nambe Dam Discharge"
USGS_DAM_SITE = "08294210"   # RIO NAMBE BELOW NAMBE FALLS DAM NEAR NAMBE, NM
# USGS "instantaneous values" service; discharge is parameter 00060, tab-delimited.
# MIGRATION NOTE: USGS plans to retire waterservices.usgs.gov in early 2027 and
# move to https://api.waterdata.usgs.gov/ . When that happens, update this one
# line (and parse_usgs_rdb() only if the response format changes).
USGS_IV_BASE = "https://waterservices.usgs.gov/nwis/iv/"

# --- The 21 NPT (Nambe-Pojoaque-Tesuque) acequia gauges ---------------------
# (id, display name). id is the OSE site id from the site.jsp URL.
# This is my best reading of the NPT acequia network from the OSE site map;
# CONFIRM / TRIM to your exact 21.
GAUGES = [
    (22, "High Line"),
    (43, "Upper Consolidated"),
    (28, "Lower Consolidated"),
    (31, "Nueva"),
    (27, "Llano"),
    (6,  "Comunidad"),
    (33, "Ortiz"),
    (21, "Gardunos"),
    (24, "Jose G. Ortiz"),
    (5,  "Cano"),
    (39, "Rincon"),
    (26, "Las Joyas"),
    (42, "Trujillos"),
    (3,  "Barranco Alto"),
    (25, "Larga"),
    (1,  "Ancon de Jacona"),
    (2,  "Barranco"),
    (45, "Otra Vanda"),
    (38, "Rancho"),
    (23, "Indios"),
    (41, "San Ildefonso"),
]

# --- Config -----------------------------------------------------------------
DATA_DIR = Path(os.environ.get("OSE_DATA_DIR", "data"))
BY_GAUGE_DIR = DATA_DIR / "by_gauge"
WIDE_CSV = DATA_DIR / "discharge_cfs_wide.csv"
STATUS_JSON = DATA_DIR / "last_run.json"

REQUEST_TIMEOUT = 30          # seconds
SLEEP_BETWEEN = 1.0           # polite gap between requests to a public server
USER_AGENT = "ose-gauge-logger/1.0 (research use)"

# Data table columns are: Date/Time | Discharge (cfs) | Gage Height (ft).
# After stripping HTML tags, a row reads e.g. "06/21/2026 15:15 2.01 0.33".
ROW_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})\s+"   # date + time
    r"(-?\d+(?:\.\d+)?)\s+"                       # discharge (cfs)  <- stored
    r"(-?\d+(?:\.\d+)?)"                          # gage height (ft) <- ignored
)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4, backoff_factor=1.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def strip_tags(html: str) -> str:
    html = re.sub(r"(?is)<script.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?</style>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ")
    return re.sub(r"[ \t]+", " ", text)


def parse_readings(html: str) -> dict:
    """Map ISO 'YYYY-MM-DD HH:MM' -> discharge_cfs (float) from a site page."""
    text = strip_tags(html)
    out = {}
    for date_s, time_s, disch_s, _gage_s in ROW_RE.findall(text):
        try:
            dt = datetime.strptime(f"{date_s} {time_s}", "%m/%d/%Y %H:%M")
        except ValueError:
            continue
        out[dt.strftime("%Y-%m-%d %H:%M")] = float(disch_s)  # dedupe by ts
    return out


def load_existing(path: Path) -> dict:
    rows = {}
    if path.exists():
        with path.open(newline="") as f:
            r = csv.reader(f)
            next(r, None)  # header
            for row in r:
                if len(row) >= 2 and row[0]:
                    rows[row[0]] = row[1]
    return rows


def write_gauge_csv(path: Path, rows: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "discharge_cfs"])
        for ts in sorted(rows):
            w.writerow([ts, rows[ts]])


def fetch_gauge(session: requests.Session, gid: int) -> dict:
    resp = session.get(
        BASE_URL, params={"id": str(gid), **COMMON}, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    return parse_readings(resp.text)


def parse_usgs_rdb(text: str) -> dict:
    """Map 'YYYY-MM-DD HH:MM' -> discharge_cfs (float) from a USGS iv rdb reply.
    The datetime is already local wall-clock time, matching the OSE gauges."""
    out, header, dt_col, val_col = {}, None, None, None
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if header is None:
            if cols and cols[0] == "agency_cd":            # the column-names row
                header = cols
                dt_col = header.index("datetime") if "datetime" in header else 2
                for i, c in enumerate(header):
                    if c.endswith("_00060"):               # discharge value column
                        val_col = i
                        break
            continue
        if not cols or cols[0] != "USGS":                  # skips the '5s 15s 20d' spec row
            continue
        if val_col is None or len(cols) <= max(dt_col, val_col):
            continue
        ts, v = cols[dt_col].strip(), cols[val_col].strip()
        if not ts or not v:
            continue
        try:
            out[ts] = float(v)
        except ValueError:
            continue
    return out


def fetch_usgs_discharge(session: requests.Session, period=None,
                         start=None, end=None) -> dict:
    """Discharge (cfs) for the Nambe dam site. Pass period ('P4D') for recent
    data, or start/end ('YYYY-MM-DD') for a historical range."""
    params = {"sites": USGS_DAM_SITE, "parameterCd": "00060", "format": "rdb"}
    if period:
        params["period"] = period
    if start:
        params["startDT"] = start
    if end:
        params["endDT"] = end
    resp = session.get(USGS_IV_BASE, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return parse_usgs_rdb(resp.text)


def build_wide(gauge_files: list) -> None:
    cols, all_ts = {}, set()
    for name, path in gauge_files:
        d = load_existing(path)
        cols[name] = d
        all_ts.update(d)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    names = [n for n, _ in gauge_files]
    # The live wide holds only the CURRENT year, taken as the year of the most
    # recent reading (local, DST-proof, no timezone math). At the New Year this
    # rolls over on its own; by_gauge keeps all history for archiveYear.py.
    cur = max(all_ts)[:4] if all_ts else ""
    with WIDE_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp"] + names)
        for ts in sorted(all_ts):
            if cur and ts[:4] != cur:
                continue
            w.writerow([ts] + [cols[n].get(ts, "") for n in names])


def main() -> int:
    session = make_session()
    summary = {
        "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gauges": {},
    }
    gauge_files = []

    # Nambe dam (USGS) — upstream reference, kept as the first wide column.
    dam_path = BY_GAUGE_DIR / f"{slugify(USGS_DAM_NAME)}.csv"
    gauge_files.append((USGS_DAM_NAME, dam_path))
    try:
        dam = fetch_usgs_discharge(session, period="P4D")
        existing = load_existing(dam_path)
        before = len(existing)
        for ts, cfs in dam.items():
            existing[ts] = f"{cfs:g}"       # USGS revises; take latest
        write_gauge_csv(dam_path, existing)
        latest = max(existing) if existing else None
        summary["gauges"][USGS_DAM_NAME] = {
            "site": USGS_DAM_SITE, "added": len(existing) - before,
            "latest": latest, "ok": True,
        }
        print(f"[ok]  {USGS_DAM_NAME:<20} +{len(existing) - before:<4} latest={latest}")
    except Exception as e:  # dam trouble shouldn't sink the acequia run
        summary["gauges"][USGS_DAM_NAME] = {"site": USGS_DAM_SITE, "ok": False, "error": str(e)}
        print(f"[err] {USGS_DAM_NAME:<20} {e}", file=sys.stderr)

    for gid, name in GAUGES:
        path = BY_GAUGE_DIR / f"{slugify(name)}.csv"
        gauge_files.append((name, path))
        try:
            fetched = fetch_gauge(session, gid)
            existing = load_existing(path)
            before = len(existing)
            for ts, cfs in fetched.items():
                existing[ts] = f"{cfs:g}"   # overwrite to absorb revisions
            write_gauge_csv(path, existing)
            latest = max(existing) if existing else None
            summary["gauges"][name] = {
                "id": gid, "added": len(existing) - before,
                "latest": latest, "ok": True,
            }
            print(f"[ok]  {name:<20} +{len(existing) - before:<4} latest={latest}")
        except Exception as e:  # one bad gauge shouldn't sink the run
            summary["gauges"][name] = {"id": gid, "ok": False, "error": str(e)}
            print(f"[err] {name:<20} {e}", file=sys.stderr)
        time.sleep(SLEEP_BETWEEN)

    build_wide(gauge_files)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_JSON.write_text(json.dumps(summary, indent=2))

    ok = sum(1 for g in summary["gauges"].values() if g.get("ok"))
    print(f"\nDone: {ok}/{len(GAUGES)} gauges ok. Wide table -> {WIDE_CSV}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
