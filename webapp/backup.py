"""Backup engine for JobTrail — stdlib ``sqlite3`` online backups.

Three layers of safety so a user never loses progress by accident:

1. A timestamped snapshot is taken on startup, before every destructive
   operation, and periodically while data is changing.
2. Snapshots use SQLite's online backup API, which is consistent even while the
   live database is open and being written to.
3. Old snapshots are pruned to a rolling window, and a plain-JSON export is
   always available for off-machine safekeeping.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

KEEP = 60  # how many timestamped snapshots to retain


def snapshot(db_path: str | Path, backups_dir: str | Path, reason: str = "") -> Path:
    """Write a consistent copy of ``db_path`` into ``backups_dir``."""
    backups_dir = Path(backups_dir)
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    tag = "".join(c for c in reason if c.isalnum() or c in "-_")[:24]
    dest = backups_dir / (f"jobs-{stamp}{('-' + tag) if tag else ''}.db")

    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()

    _prune(backups_dir)
    return dest


def _prune(backups_dir: Path, keep: int = KEEP) -> None:
    snaps = sorted(backups_dir.glob("jobs-*.db"), key=lambda p: p.stat().st_mtime)
    for old in snaps[:-keep] if len(snaps) > keep else []:
        try:
            old.unlink()
        except OSError:
            pass


def list_snapshots(backups_dir: str | Path) -> list[dict]:
    backups_dir = Path(backups_dir)
    if not backups_dir.is_dir():
        return []
    out = []
    for p in sorted(backups_dir.glob("jobs-*.db"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        out.append(
            {
                "name": p.name,
                "size": st.st_size,
                "created": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return out


class PeriodicBackup:
    """Daemon thread that snapshots the DB when it has changed since last run."""

    def __init__(self, db, db_path, backups_dir, interval: float = 300.0):
        self.db = db
        self.db_path = db_path
        self.backups_dir = backups_dir
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
                if getattr(self.db, "dirty", False):
                    snapshot(self.db_path, self.backups_dir, reason="auto")
                    self.db.dirty = False
            except Exception:
                pass  # never let backup crash the server
