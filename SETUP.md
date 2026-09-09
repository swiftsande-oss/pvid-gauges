# Setting up the NM gauge fetcher

This is Claude Opus's original instructions to Greg, to get things going.

This walks through getting `fetch_ose_gauges.py` running on a schedule so it
collects flow data from the 21 OSE acequia gauges and the USGS dam discharge gauge 
by itself, every 30 minutes, without your computer needing to be on.

**The one key idea:** there are two places this can run.

- **Your computer** can run it *once* so you can watch it work. Optional.
- **GitHub** runs it *for you, in the cloud, on a schedule.* This is the part
  that matters — your laptop can be closed and it keeps collecting data.

Part A (your computer) is just a confidence-builder. Part B (GitHub) is the
real setup. Part C publishes the explorer web page from the same repo. Python
3.9 is fine; nothing here needs anything newer.

---

## Part A — see it work on your computer (optional, ~5 min)

1. Make a new empty folder somewhere, e.g. `nm-gauges`. Put
   `fetch_ose_gauges.py` inside it.
2. In VSCode: **File → Open Folder** and pick that folder. The file should
   appear in the left sidebar.
3. Open a terminal inside VSCode: **Terminal → New Terminal**. A command
   prompt appears at the bottom.
4. Install the one library it needs:
   ```
   python -m pip install requests
   ```
   If `python` errors, try `python3` (Mac/Linux) or `py` (Windows).
5. Run it:
   ```
   python fetch_ose_gauges.py
   ```
   A line scrolls by for each gauge (`[ok]  High Line  +384  latest=...`), and
   a new `data` folder appears with the CSVs inside. That's the whole fetcher
   working.

If any gauge shows `[err]` instead of `[ok]`, that's the live-page-layout check
— copy the message and send it over so the parser can be adjusted.

Skipping Part A loses nothing: GitHub installs `requests` and runs the script
itself.

---

## Note added later by Greg:  

To get all the data since March 1 this year, a human must download a csv discharge file manually from every one of the 21 acequias, renaming each such file to be acequia_name.csv, and put all of them in the backfill_csv folder.  (Claude explained why this step can't be automated.  All the automation can get is the current html display for each gauge, which is 4 days worth.)  After making the 21 year-to-date csv files, run backfill_from_csv.py once, to merge all of that into the data\discharge_cfs_wide.csv file.  Then the other software can keep it up to date throughout the year.

Similarly, A human must laboriously download all the prior-year data from OSE, one year at a time, one acequia at a time, in csv format.  I have made folders \backfill_*YEAR* in my main folder, into which I download the 21 files from OSE, Discharge from 03/01 to 10/31.  Then backfill_from_csv.py will combine those 21 into a single csv file, name it appropriately, and put it in my local \data folder.  (See top of backfill_from_csv.py for run syntax in the terminal.)  Then I upload each of those from my local \data folder to the github repo.  

The USGS data is easier.  Claude got the fetch script to do that automatically.

---

## Part B — put it on GitHub so it runs by itself

A *repository* ("repo") is just a folder that lives on GitHub. We create one,
add the two files, flip one permission, and press a button to test it.

1. Go to **github.com** and sign in (reset the password if it's been a while).
2. Top-right **+ → New repository**. Name it something like `nm-gauges`. Leave
   it **Public** (simplest, and this data is already public) or choose Private
   — both work. Do **not** check any "add a file" boxes. Click
   **Create repository**.
3. **Add the script.** On the new repo page: **Add file → Upload files**, drag
   in `fetch_ose_gauges.py`, then **Commit changes** at the bottom.
4. **Add the workflow.** This one needs a specific folder path, so type it
   rather than upload. **Add file → Create new file**, and in the filename box
   type exactly:
   ```
   .github/workflows/fetch-gauges.yml
   ```
   (Typing the `/` slashes auto-creates the folders.) Open `fetch-gauges.yml`,
   copy its full contents into the editor box, and **Commit changes**.
5. **Flip the write permission — don't skip this.** Without it the auto-commit
   silently fails and no data ever appears. Go to **Settings → Actions →
   General**, scroll to **Workflow permissions**, choose **Read and write
   permissions**, and **Save**.
6. **Test it now** instead of waiting 30 minutes. Click the **Actions** tab. If it
   offers to enable workflows, say yes. Click **Fetch OSE gauges** on the left,
   then **Run workflow → Run workflow** on the right. It churns for a minute;
   refresh and look for a green check.
7. **Confirm it worked.** Back on the **Code** tab you should now see a `data`
   folder and a recent commit by "gauge-bot". Open
   `data/discharge_cfs_wide.csv` to see all 21 gauges side by side.

From here it updates itself every 6 hours on Github.

---

## Part C — publish the explorer web page (GitHub Pages)

This puts the explorer online at its own web address, reading the live data the
robot keeps refreshing. The explorer file lives **in the same repo** as the
data, you open it from a GitHub URL, and your PC isn't involved — anyone you
send the link to sees it the same way.

**Why they must live together:** a web page is only allowed to auto-load data
files that come from the *same website* it was opened from (a browser safety
rule). Put the explorer HTML and `discharge_cfs_wide.csv` on the same GitHub
Pages site and they count as one website, so the data loads with no clicks.
(That same rule is why double-clicking the file on your PC can't reach GitHub —
your PC and GitHub are different places.)

Do this once, after Part B is working:

1. **Add the explorer to the same repo, named `index.html`.** Add file → Upload
   files → drag in `npt-flow-explorer.html`, and rename it to `index.html`
   before committing. (Naming it `index.html` makes it the page that opens by
   default, so the link is just the site address with nothing tacked on.)
2. **Turn on Pages.** Repo **Settings → Pages**. Under "Build and deployment":
   Source = **Deploy from a branch**, Branch = **main**, folder = **/ (root)**,
   then **Save**.
3. **Open your site.** Wait ~1 minute, refresh the Settings → Pages screen, and
   it shows your URL, like `https://yourname.github.io/nm-gauges/`. Click it.

That URL is the explorer, already pointed at your live data — no "Choose CSV"
step. Each time the Action commits new readings, Pages rebuilds within a minute,
so the page stays current on its own; a visitor can refresh or hit **Reload**
for the very latest.

**The same HTML works in all three places, with no edits:**

- Double-click on your PC → opens with the file-picker (good for trying a new
  data file by hand).
- `python -m http.server` locally → auto-loads from your local `data` folder
  (good while developing).
- GitHub Pages → the public, shareable copy for your reviewers.

**Heads-up:** a public repo makes a publicly reachable site, so anyone with the
link can view it. Fine here, since the gauge data is already public — just worth
knowing before you share it around.

## Part D -- Things added after the original setup

Cycle schedules.

Soon, Greg hopes, moving "normalizations" out of the html and into to year-specific files.

---

## Things that won't surprise you now

- **Scheduled times are approximate.** GitHub may run a few minutes late, and
  occasionally skips a run under heavy load. Harmless here — each gauge page
  carries 3–4 days of history, so a missed run leaves no gap.
- **60-day pause.** If the repo sits with no commits *from you* for 60 days,
  GitHub pauses the schedule and emails a one-click re-enable. (The bot's own
  commits don't reset this clock, so if you go quiet for two months you'll get
  the nudge.)
- **Revisions.** OSE marks recent data "provisional." The fetcher refreshes
  values still inside the visible 3–4 day window, so revisions get absorbed
  before a reading scrolls out of view and freezes.

## If something looks off

- A gauge stuck on `[err]`: send the error line from the run log (Actions tab →
  the run → the `python fetch_ose_gauges.py` step) — likely a page-layout tweak.
- No `data` folder after a green run: almost always the **write permission**
  in step 5. Set it, then re-run from the Actions tab.
- Want a different cadence: edit the `cron:` line in `fetch-gauges.yml`. The
  five fields are `minute hour day month weekday`; `17 */6 * * *` means "minute
  17 of every 6th hour."

## What's next

Two refinements are deliberately left for when
the data supports them: a **water-year overlay** (stack years on one
axis), which needs more than a year of record, and **per-drainage-area
normalization** (cfs/mi²), which needs each gauge's basin area.
