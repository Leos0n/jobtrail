"""Google Sheets sync helper used by the server (status + sync-now + auto-sync).

Reads the locally stored token + config (written by bin/jobtrail-google), pulls
the configured tabs, and imports new rows into JobTrail's DB. One-way and
idempotent: re-running only adds rows not already present. No-ops cleanly when
the user hasn't connected a sheet, so it's always safe to call.
"""

from __future__ import annotations

import json
import sys
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


def _save_config(cfg):
    GDIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))


def _stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def status() -> dict:
    cfg = _config()
    return {
        "connected": gauth.is_connected(TOKEN),
        "spreadsheet_url": cfg.get("spreadsheet_url"),
        "tabs": cfg.get("tabs", []),
        "last_sync": cfg.get("last_sync"),
        "last_added": cfg.get("last_added"),
        "last_total": cfg.get("last_total"),
        "last_attempt": cfg.get("last_attempt"),
        "last_error": cfg.get("last_error"),
    }


def configured() -> bool:
    cfg = _config()
    return gauth.is_connected(TOKEN) and bool(cfg.get("spreadsheet_url")) and bool(cfg.get("tabs"))


def sync_now(db_path, reset=False) -> dict:
    if not gauth.is_connected(TOKEN):
        return {"ok": False, "reason": "not connected"}
    cfg = _config()
    if not cfg.get("spreadsheet_url") or not cfg.get("tabs"):
        return {"ok": False, "reason": "no sheet configured"}

    cfg["last_attempt"] = _stamp()
    try:
        token = gauth.access_token(TOKEN)
        sid = gsheets.spreadsheet_id(cfg["spreadsheet_url"])
        jobs = []
        for tab in cfg["tabs"]:
            values, links = gsheets.read_tab_with_links(sid, tab, token)
            jobs.extend(sheets_map.values_to_jobs(
                values, default_status=cfg.get("default_status"), tab=tab, links=links)["jobs"])
        db = Database(str(db_path))
        removed = db.delete_by_source("google-sheet") if reset else 0
        result = db.import_jobs(jobs)
        db.close()
    except Exception as exc:
        # Don't crash, but never fail *silently*: record the reason so it
        # surfaces in /api/google/status, and log it for the server console.
        reason = f"{type(exc).__name__}: {exc}"
        cfg["last_error"] = reason
        _save_config(cfg)
        print(f"[gsync] sync failed: {reason}", file=sys.stderr)
        return {"ok": False, "reason": reason}

    cfg.update({
        "last_sync": _stamp(),
        "last_added": result["added"],
        "last_total": len(jobs),
        "last_error": None,
    })
    _save_config(cfg)
    return {"ok": True, "added": result["added"], "skipped": result["skipped"],
            "removed": removed, "total": len(jobs)}


class AutoSync:
    """Daemon thread: capture new sheet rows periodically while the app runs.

    Runs one sync shortly after startup (so freshly added rows don't wait a
    full interval to appear), then every ``interval`` seconds.
    """

    def __init__(self, db_path, interval: float = 900.0, startup_delay: float = 5.0):
        self.db_path = db_path
        self.interval = interval
        self.startup_delay = startup_delay
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        if not self._stop.wait(self.startup_delay):
            self._tick()
        while not self._stop.wait(self.interval):
            self._tick()

    def _tick(self):
        try:
            if configured():
                sync_now(self.db_path)
        except Exception as exc:  # defensive: the daemon must never die
            print(f"[gsync] auto-sync tick error: {exc}", file=sys.stderr)
