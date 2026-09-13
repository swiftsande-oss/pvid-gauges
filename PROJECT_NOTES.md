# PVID Gauge Explorer — Project Notes & Design Decisions

*A companion to the code: the "why" behind the choices, the things to remember,
and how to do the recurring tasks. Written for future-you and the next
maintainer.*

Current version: **Version 1.1.1** · MIT-licensed · publicly linked from PVID's site.

---

## 1. What this is

An interactive web tool for monitoring irrigation in the the Pojoaque Valley 
Irrigation District (PVID) acequia network. It shows, per gauge:

- **Flow (CFS)** — instantaneous discharge at each acequia headgate.
- **Total (AF)** — cumulative acre-feet delivered since the window start.
- **TotalAF/acre** — cumulative acre-feet per irrigable acre (a fairer
  cross-acequia comparison), available in Adjust mode over a Season or All window.

Its most important capability is **plan-versus-actual**: overlaying each cycle's
*scheduled* diversions (pastel bands) against the *measured* gauge readings, so
anyone can see whether acequias are following the schedule.

---

## 2. The architecture in one picture

Two halves that never run at the same time or place, communicating only through
CSV files in the repo:

- **The builder** — Python (`fetch_ose_gauges.py`) run on a schedule by a
  GitHub Action, *on GitHub's servers*. Its only job is to fetch data and write
  CSV files back into the repository. This is build-time, not visit-time.
- **The website** — `index.html` (the explorer): HTML/CSS/JavaScript that runs
  *in the visitor's browser*. It fetches CSV files and does all computation
  locally.

GitHub Pages is a **static file host** — it serves files exactly as they sit in
the repo; it does **not** run Python when a visitor loads the page. This
"static site + separate scheduled job that regenerates the files" pattern is
common (sometimes called Jamstack).

**How a visitor's data loads:** the browser downloads `index.html` first, then
fetches data *on demand*. The current-year wide CSV, `schedules.json`, the
season file, and the current year's acres and adjustments files load on arrival.
A prior year's file is **not** downloaded until the user selects that year — that
click causes a fresh fetch from GitHub. (This is why prior-year switching needs
the page *served*, and why it can't work from a double-clicked `file://` page.)
All data is public — anyone with the URL can read any CSV, which is appropriate
for public water-measurement data.

---

## 3. The files

**Builder / data-prep (Python, run by you or the Action — never by visitors):**

- `fetch_ose_gauges.py` — scrapes the 21 OSE gauges and fetches the USGS dam
  gauge; writes per-gauge logs in `data/by_gauge/` and the combined wide table.
  Its `build_wide` keeps only the current year in the live wide (see §4, Year
  rollover).
- `backfill_from_csv.py` — imports hand-downloaded OSE history. No `--year`
  merges into the current-year data; `--year YYYY` builds a standalone prior-year
  file. Both also pull the dam from USGS.
- `archiveYear.py` — freezes a finished year: reads the accumulated `by_gauge`
  logs and writes `data/discharge_cfs_wide_YYYY.csv`. Purely additive; never
  touches the live wide or `by_gauge`. Run once in the new year (see §6).
- `schedule_from_pdf.py` — converts a PVID cycle PDF into a schedule CSV and
  updates the schedules manifest.
- `launchFromMyPC.py` — local launcher: serves the folder so the page can fetch
  its data (unlike double-clicking). **Serve-only — it never runs the fetcher**,
  so it can't make your PC a second author of the live CSVs.
- `fetch-gauges.yml` — the GitHub Action (schedule lives in its `cron:` line).

**The website:**

- `index.html` — the whole explorer, one self-contained file. (Delivered under a
  working name like `pvid-flow-explorer.html`; saved/committed as `index.html`.)

**Data (in `data/`), the only thing the two halves share:**

- `discharge_cfs_wide.csv` — live current-year readings, one column per gauge.
- `discharge_cfs_wide_YYYY.csv` — completed prior years.
- `by_gauge/*.csv` — per-gauge logs (all history; used to rebuild the wide table
  and to archive a finished year).
- `last_run.json` — the Action's own bookkeeping (when it last ran). GitHub-owned.
- `schedules.json` — manifest of available cycles (drives the SCHEDULES buttons).
- `YYYYcycleN.csv` — one irrigation cycle's schedule (`acequia,cfs,start,end`).
- `season_start_and_end_dates.csv` — one file, one line per year (season start/end).
- `YYYYirrigableAcres.csv` — per-year irrigable-acre denominators for TotalAF/acre.
- `YYYYadjustments.csv` — per-year definitions of the Adjust arithmetic (see §4).

**Auxiliary (documentation / links):** `README.md`, `SETUP.md`, this file,
`LICENSE` (MIT), and `info/` (the linked PDFs and the MoreInfo / License pages).

---

## 4. Key design decisions (and why)

**Static site + scheduled builder.** Keeps hosting free and simple, and cleanly
separates "prepare the data" from "show the data." The explorer needs no server
of its own.

**The explorer is data-driven from the CSV header.** It builds its gauge list
from whatever columns exist in the wide file. Consequence: adding a gauge (like
the dam) required almost no explorer change — the new column just appears. Gauge
order in the file controls legend order ("upstream on top").

**Wide CSV format.** One `timestamp` column plus one column per gauge, on a
union time-grid (empty cells where a gauge has no reading at that timestamp).
Timestamps are local Mountain wall-clock time, `YYYY-MM-DD HH:MM`, matching how
all sources report — so everything lines up on one axis.

**"Human verifies at the boundary."** Wherever a machine could confidently
produce a *wrong* answer, the design surfaces it for human review instead of
guessing: the schedule converter flags names it can't map and dates that look
wrong; the explorer validates cycle files and shows a red warning; live-fetch
values are confirmed by you on your own machine before committing. In an
enforcement tool, a confidently-wrong number is the dangerous failure mode.

**Adjust mode — derived series, computed in the browser; the CSV is never
modified.** The arithmetic is **not hardcoded**; it is defined per year in
`data/YYYYadjustments.csv`, which is the *sole* source (no built-in fallback —
if no file applies, the Adjust button simply disappears with an explanatory
note). This lets a future gauge recalibration change the formula *going forward*
without corrupting prior years' graphs, which keep their own year's arithmetic.
The 2026 definitions are:
- `NambePuebloNet = HighLine + UpperConsol − Nueva − Llano − Comunidad`
- `ConsolNet = UpperConsol − Nueva − Llano − Comunidad` *(revised from an
  earlier Upper − Lower definition as understanding of the interconnections
  improved)*
- `IndiosAdj = 1.0724 × (Indios − 0.135)`, floored at 0 (a gauge zero-offset
  correction)
- Negative net values are **legitimate** — ungauged channels interconnect some
  upstream acequias, and it takes about an hour for water to flow from Upper to
  Lower Consolidated, so a net can genuinely go negative. This is why schedule
  editing needs human judgment and why the y-axis-min control exists (to clip
  the confusing-but-real negatives when showing others).

The file format is `name, type, definition, hide`: `net` rows are a `+`/`-`
combination of gauges; a `calib` row is `scale * (gauge - offset)` floored at 0;
`hide` (`;`-separated) lists which raw gauges fold out of the display. The
explorer's schedule-band arithmetic and color inheritance are derived from these
definitions, so they follow the file automatically. **Any change to this math
must pass the regression check (reproduce the prior graphs) before going live.**

**Schedules as an underlay.** Each cycle's scheduled diversions are drawn as
pastel bands *behind* the actual readings. In CFS the band is a step function;
in AF it's the cumulative ramp. In Adjust mode the bands do the **same net
arithmetic** as the curves (signed constituents), so ConsolNet's band is Upper's
schedule minus the three ditches'. Emphasis (clicking gauge names) filters the
bands to reduce clutter. Cycle files are validated on load (bad dates, overlaps).

**TotalAF/acre view.** The denominators live in per-year `YYYYirrigableAcres.csv`
files. The measure is cumulative AF ÷ irrigable acres. The button's hover popup
shows the file's provenance comment lines *and* the acres used, so a wrong
denominator is visible, not buried.

**Window presets and the Season button.** Launch shows the last **24 h**. The
**Season** button clips the axis to the irrigation season for the loaded year
(from `season_start_and_end_dates.csv`, currently Apr 1–Oct 31; for the current
year it ends at "now"). **All** reveals the entire record — useful because the
USGS dam runs year-round, so the raw record starts January 1 while the OSE
gauges wake up around March. The season start is expected to move earlier as the
climate warms; it's a one-line edit per year. A completed season also exposes a
**Season totals** link (a printable AF-per-acequia table, computed on the
adjusted data).

**The USGS dam gauge.** Added as an upstream reference curve (no Adjust
arithmetic, no schedule, no acres). It comes from a *different* source than the
OSE gauges — the USGS instantaneous-values web service, clean JSON/RDB — and
slots in as the first wide-table column.

**Year rollover (automatic + one human step).** `build_wide` writes only the
*current* year to the live wide, defining "current year" as the year of the most
recent reading (DST-proof, no timezone math, and exercised every run so it can't
rot). At the New Year the live file rolls over on its own. `by_gauge` keeps all
history, so the finished year is captured later with `archiveYear.py` — a safe,
additive human step (see §6).

**Discovery mechanisms.**
- Prior-year *data* files: found by *probing* (`2011`..last year).
- Cycles: a manifest, `schedules.json`.
- Season dates: one file with a line per year.
- Acres and adjustments: per-year files, loaded by exact year. Adjustments
  additionally *cascade* — a missing year falls back to the most recent year that
  has a file; if none exists at all, Adjust is hidden.

---

## 5. Things to remember / known caveats

- **GitHub's scheduler is best-effort and often late** — real intervals stretch
  to hours, and it can skip or drop runs under load (worse near the top of the
  hour, which is why the cron uses off-hour minutes). Reducing the request
  frequency does **not** help reliability (the load is GitHub's, not yours); it
  only lowers freshness. Data stays gap-free regardless, because each fetch pulls
  several days of history. Fine for historical/analysis use; **not** fine for
  real-time management. The real fix is moving the *same* fetcher to an always-on
  host (a small VPS, or cPanel cron if the host supports Python) — a
  *where-it-runs* change only; script, CSVs, and explorer are unchanged.
- **The real cadence ceiling is OSE's servers.**
  Confirm an acceptable request frequency with OSE before increasing it — a
  cadence they've blessed won't get throttled or blocked. (OSE is currently OK
  with ~20-minute polling.)
- **USGS is retiring `waterservices.usgs.gov` in early 2027**, moving to
  `api.waterdata.usgs.gov`. The switch is a one-line change at the `USGS_IV_BASE`
  constant in `fetch_ose_gauges.py` (and the parser only if the format changes).
- **The irrigable-acre numbers are provisional** pending firmer figures from
  Rob H / OSE. The tool faithfully divides by whatever's in the file.
- **`Consolidated - PVID`** and the Highline/Consolidated split are handled by
  human judgment, not code — the converter flags them for you to resolve.
- **Adjust arithmetic is data, not code.** To change it, edit the year's
  `YYYYadjustments.csv` and run the regression check before committing — never
  edit formulas in the explorer.
- **`file://` limitations:** opened by double-clicking, the page can't fetch its
  data (auto-load, prior years, schedules, seasons, acres, adjustments all need
  the page *served*, via `launchFromMyPC.py` locally or GitHub Pages / a host).

---

## 6. Recurring tasks (quick reference)

- **Add a cycle schedule:** `pip install pdfplumber`, then
  `python schedule_from_pdf.py <cycle>.pdf`. Review the CSV (fix any flagged
  names/dates), copy it and `schedules.json` into `data/`, commit.
- **Add a prior year (historical backfill):** download that year's 21 OSE gauge
  CSVs into a folder, `python backfill_from_csv.py --year YYYY --dir <folder>`
  (the dam comes from USGS automatically), check the output, copy the year file
  into `data/`, commit.
- **Refresh the current year's data by hand:** `python backfill_from_csv.py`
  (no `--year`).
- **Update irrigable acres:** edit `data/YYYYirrigableAcres.csv` (canonical
  names; comment lines at the top show up in the popup). No code change.
- **Change a season's dates:** edit one line in
  `data/season_start_and_end_dates.csv`. No code change.
- **Change the Adjust math (e.g. after a gauge recalibration):** edit the year's
  `data/YYYYadjustments.csv`, run the regression check (confirm prior years'
  graphs are unchanged), then commit. No code change.
- **New-year chores (any time after Jan 1 — the old year waits safely in
  `by_gauge`; the live wide has already rolled itself over):**
  1. `git pull`
  2. `python archiveYear.py` — glance at the row count; confirm the new
     `discharge_cfs_wide_YYYY.csv` looks right.
  3. Add the new year's line to `season_start_and_end_dates.csv` (in March, when
     OSE gauges wake up; the start may be earlier than before).
  4. Add the new year's `YYYYirrigableAcres.csv` (copy last year's; update figures).
  5. Add the new year's `YYYYadjustments.csv` (copy last year's; edit only if a
     gauge was recalibrated).
  6. `git add` the new files → commit → pull → push.
- **Speed up live updates later:** run the same `fetch_ose_gauges.py` on an
  always-on host via cron at the OSE-approved interval; point it at the same
  `data/` folder. Nothing else changes.

---

## 7. Working style that served this project

- The CSVs are the source of truth; the explorer never modifies them — every
  transformation (nets, per-acre, schedule arithmetic) happens in the browser at
  render time, so raw data is always recoverable.
- **One author per file.** The GitHub Action authors the live data
  (`discharge_cfs_wide.csv`, `by_gauge/*`, `last_run.json`); the human authors
  everything else. Never commit human changes to the Action's files — the human routine is
  pull → edit the human files → commit → pull → push, and `git restore <file>` undoes
  an accidental edit to an Action-owned file before it becomes a commit.
- Small, reversible changes, each verified before moving on; keep a stable
  known-good version while a new revision is in progress.
- Honesty about limits: when a value couldn't be confirmed (e.g. a live fetch a
  sandbox couldn't reach), it was flagged for human check rather than asserted.
- A regression-testing process lives in the repo.  Run it before trusting any
  change to the derived-data math.
