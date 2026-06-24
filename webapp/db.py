"""SQLite persistence for JobTrail — stdlib ``sqlite3`` only.

One table, ``jobs``, holds both the scraped posting and the user's application
tracking data. Uploaded resume / cover-letter files live on disk under
``data/files/<job_id>/`` and are referenced by path.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Editable application-tracking fields (everything a user can PATCH).
APPLICATION_FIELDS = {
    "status",
    "date_applied",
    "follow_up_date",
    "contact",
    "notes",
    "rating",
    "salary_expectation",
}

# Allowed values for the status pipeline.
STATUSES = ["saved", "applied", "interviewing", "offer", "rejected", "archived"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    url TEXT,
    job_key TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    remote TEXT,
    employment_type TEXT,
    salary TEXT,
    date_posted TEXT,
    industry TEXT,
    description_md TEXT,
    raw_json TEXT,
    -- application tracking --
    status TEXT NOT NULL DEFAULT 'saved',
    date_applied TEXT,
    follow_up_date TEXT,
    contact TEXT,
    notes TEXT,
    rating INTEGER NOT NULL DEFAULT 0,
    salary_expectation TEXT,
    resume_path TEXT,
    resume_name TEXT,
    cover_letter_path TEXT,
    cover_letter_name TEXT,
    created_at TEXT,
    updated_at TEXT,
    deleted_at TEXT
);
"""

# Columns added after the first release — applied as idempotent migrations.
_MIGRATIONS = {
    "deleted_at": "ALTER TABLE jobs ADD COLUMN deleted_at TEXT",
    "session": "ALTER TABLE jobs ADD COLUMN session TEXT",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()
        # Set True by any write; the periodic backup watches this flag.
        self.dirty = False

    def _migrate(self):
        have = {r[1] for r in self.conn.execute("PRAGMA table_info(jobs)")}
        for col, ddl in _MIGRATIONS.items():
            if col not in have:
                self.conn.execute(ddl)

    # -- writes ----------------------------------------------------------
    def add_job(self, job, raw: dict | None = None) -> int:
        """Insert a scraped Job. If the same url/job_key exists, refresh it."""
        existing = self.find_by_key(job.url, job.job_key)
        now = _now()
        scraped = {
            "source": (job.extras or {}).get("source"),
            "url": job.url,
            "job_key": job.job_key,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "remote": job.remote,
            "employment_type": job.employment_type,
            "salary": job.salary,
            "date_posted": job.date_posted,
            "industry": job.industry,
            "description_md": job.description_md,
            "raw_json": json.dumps(raw if raw is not None else asdict(job), default=str),
        }
        if existing:
            cols = ", ".join(f"{k} = ?" for k in scraped)
            self.conn.execute(
                f"UPDATE jobs SET {cols}, updated_at = ? WHERE id = ?",
                [*scraped.values(), now, existing["id"]],
            )
            self.conn.commit()
            self.dirty = True
            return existing["id"]

        scraped["created_at"] = now
        scraped["updated_at"] = now
        cols = ", ".join(scraped)
        ph = ", ".join("?" for _ in scraped)
        cur = self.conn.execute(
            f"INSERT INTO jobs ({cols}) VALUES ({ph})", list(scraped.values())
        )
        self.conn.commit()
        self.dirty = True
        return cur.lastrowid

    def update_application(self, job_id: int, fields: dict) -> bool:
        clean = {k: v for k, v in fields.items() if k in APPLICATION_FIELDS}
        if "status" in clean and clean["status"] not in STATUSES:
            raise ValueError(f"invalid status: {clean['status']}")
        if not clean:
            return False
        cols = ", ".join(f"{k} = ?" for k in clean)
        self.conn.execute(
            f"UPDATE jobs SET {cols}, updated_at = ? WHERE id = ?",
            [*clean.values(), _now(), job_id],
        )
        self.conn.commit()
        self.dirty = True
        return True

    def set_file(self, job_id: int, kind: str, path: str | None, name: str | None):
        if kind not in ("resume", "cover_letter"):
            raise ValueError(f"invalid file kind: {kind}")
        self.conn.execute(
            f"UPDATE jobs SET {kind}_path = ?, {kind}_name = ?, updated_at = ? "
            f"WHERE id = ?",
            [path, name, _now(), job_id],
        )
        self.conn.commit()
        self.dirty = True

    def soft_delete(self, job_id: int) -> bool:
        """Move a job to the trash. Recoverable; files are kept."""
        cur = self.conn.execute(
            "UPDATE jobs SET deleted_at = ?, updated_at = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            [_now(), _now(), job_id],
        )
        self.conn.commit()
        self.dirty = True
        return cur.rowcount > 0

    def restore(self, job_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE jobs SET deleted_at = NULL, updated_at = ? WHERE id = ?",
            [_now(), job_id],
        )
        self.conn.commit()
        self.dirty = True
        return cur.rowcount > 0

    def purge(self, job_id: int) -> dict | None:
        """Permanently delete a job. Returns the row so callers can remove files."""
        row = self.get_job(job_id)
        if not row:
            return None
        self.conn.execute("DELETE FROM jobs WHERE id = ?", [job_id])
        self.conn.commit()
        self.dirty = True
        return row

    # -- reads -----------------------------------------------------------
    def find_by_key(self, url: str, job_key: str | None):
        if job_key:
            row = self.conn.execute(
                "SELECT * FROM jobs WHERE job_key = ?", [job_key]
            ).fetchone()
            if row:
                return row
        return self.conn.execute("SELECT * FROM jobs WHERE url = ?", [url]).fetchone()

    def get_job(self, job_id: int):
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", [job_id]).fetchone()
        return dict(row) if row else None

    def list_jobs(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE deleted_at IS NULL ORDER BY "
            "CASE status WHEN 'archived' THEN 1 ELSE 0 END, "
            "datetime(updated_at) DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def list_trash(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM jobs WHERE deleted_at IS NOT NULL "
            "ORDER BY datetime(deleted_at) DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def export_all(self) -> list[dict]:
        """Every job, including trashed — the full structured backup."""
        rows = self.conn.execute(
            "SELECT * FROM jobs ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def import_jobs(self, jobs: list[dict]) -> dict:
        """Merge exported jobs in. Inserts missing ones; never overwrites or
        deletes existing data.

        Identity is the job_key when present (so two distinct roles that share
        an apply link — e.g. one company careers page for several openings —
        stay separate); only keyless rows fall back to url matching."""
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(jobs)")]
        importable = [c for c in cols if c != "id"]
        added = skipped = 0
        for job in jobs:
            key = job.get("job_key")
            if key:
                existing = self.conn.execute(
                    "SELECT 1 FROM jobs WHERE job_key = ?", [key]
                ).fetchone()
            else:
                existing = self.find_by_key(job.get("url", ""), None)
            if existing:
                skipped += 1
                continue
            vals = {c: job.get(c) for c in importable if c in job}
            vals.setdefault("created_at", _now())
            vals.setdefault("updated_at", _now())
            names = ", ".join(vals)
            ph = ", ".join("?" for _ in vals)
            self.conn.execute(
                f"INSERT INTO jobs ({names}) VALUES ({ph})", list(vals.values())
            )
            added += 1
        self.conn.commit()
        self.dirty = True
        return {"added": added, "skipped": skipped}

    def delete_by_source(self, source: str) -> int:
        """Hard-delete every job with the given source (e.g. 'google-sheet').

        Used for a clean re-import: because import is insert-only, rows left by
        older syncs accumulate; clearing them first makes counts exact again.
        Only touches that source, so manually added jobs are untouched."""
        cur = self.conn.execute("DELETE FROM jobs WHERE source = ?", [source])
        self.conn.commit()
        self.dirty = True
        return cur.rowcount

    def clear_jobs(self) -> int:
        """Hard-delete EVERY job — a full reset. Use when source-scoped cleanup
        isn't enough (e.g. stale rows from very old syncs that predate source
        tagging). Caller should snapshot a backup first."""
        cur = self.conn.execute("DELETE FROM jobs")
        self.conn.commit()
        self.dirty = True
        return cur.rowcount

    def close(self):
        self.conn.close()
