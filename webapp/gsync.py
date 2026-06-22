"""Google Sheets sync helper used by the server (status + sync-now + auto-sync).

Reads the locally stored token + config (written by bin/jobtrail-google), pulls
the configured tabs, and imports new rows into JobTrail's DB. One-way and
idempotent: re-running only adds rows not already present. No-ops cleanly when
the user hasn't connected a sheet, so it's always safe to call.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from webapp import gauth, gsheets, sheets_map
from webapp.db import Database

ROOT = Path(__file__).resolve().parent.parent
GDIR = ROOT / "data" / "google"
TOKEN = GDIR / "token.json"
CONFIG = GDIR / "config.json"


def _config():
    return json.loads(CONFIG.read_text()) if CONFIG.is_file() else {}


def status() -> dict:
    cfg = _config()
    return {
        "connected": gauth.is_connected(TOKEN),
        "spreadsheet_url": cfg.get("spreadsheet_url"),
        "tabs": cfg.get("tabs", []),
        "last_sync": cfg.get("last_sync"),
        "last_added": cfg.get("last_added"),
        "last_total": cfg.get("last_total"),
    }


def configured() -> bool:
    cfg = _config()
    return gauth.is_connected(TOKEN) and bool(cfg.get("spreadsheet_url")) and bool(cfg.get("tabs"))


def sync_now(db_path) -> dict:
    if not gauth.is_connected(TOKEN):
        return {"ok": False, "reason": "not connected"}
    cfg = _config()
    if not cfg.get("spreadsheet_url") or not cfg.get("tabs"):
        return {"ok": False, "reason": "no sheet configured"}

    token = gauth.access_token(TOKEN)
    sid = gsheets.spreadsheet_id(cfg["spreadsheet_url"])
    jobs = []
    for tab in cfg["tabs"]:
        values = gsheets.read_tab(sid, tab, token)
        jobs.extend(sheets_map.values_to_jobs(values, default_status=cfg.get("default_status"), tab=tab)["jobs"])

    db = Database(str(db_path))
    result = db.import_jobs(jobs)
    db.close()
    cfg.update({
        "last_sync": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "last_added": result["added"],
        "last_total": len(jobs),
    })
    GDIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))
    return {"ok": True, "added": result["added"], "skipped": result["skipped"], "total": len(jobs)}


class AutoSync:
    """Daemon thread: capture new sheet rows periodically while the app runs."""

    def __init__(self, db_path, interval: float = 900.0):
        self.db_path = db_path
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                if configured():
                    sync_now(self.db_path)
            except Exception:
                pass  # never let sheet sync crash the server
