#!/usr/bin/env python3
"""
launchFromMyPC.py -- serve the PVID Gauge Explorer locally, for previewing.

Run it (double-click, or `python launchFromMyPC.py` in the project folder). It:
  1. serves this folder at http://localhost:8000, and
  2. opens the explorer in your browser.

It does NOT fetch data, on purpose. The live data on GitHub is authored by the
scheduled GitHub Action. To preview with fresh, gap-free data, `git pull` first,
then run this. (Running a local fetcher would make your PC a second author of
the live CSVs and cause the sync conflicts we want to avoid -- so this launcher
only ever serves what is already on disk.)

Leave the window open while you use the explorer. Press Ctrl+C to stop.
"""

import os
import threading
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PORT = int(os.environ.get("PORT", "8000"))
HERE = Path(__file__).resolve().parent
EXPLORER = "index.html"   # the deployed explorer filename


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the console quiet


def main():
    os.chdir(HERE)
    target = EXPLORER if (HERE / EXPLORER).exists() else ""
    if not target:
        print(f"(Note: {EXPLORER} not found here; opening the folder listing instead.)")
    url = f"http://localhost:{PORT}/{target}"
    ThreadingHTTPServer.allow_reuse_address = True
    with ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as httpd:
        print("Serving this folder. No data fetch -- pull from GitHub for fresh data.")
        print(f"Explorer:  {url}")
        print("Leave this window open while you use the explorer.  Ctrl+C to stop.")
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
