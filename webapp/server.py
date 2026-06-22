"""JobTrail local web server — Python stdlib ``http.server`` only.

Serves a single-page UI and a small JSON API over the SQLite store. Binds to
127.0.0.1 (loopback) so it is never exposed off the machine. File uploads are
sent as base64 JSON (no multipart), which keeps the whole thing dependency free
and works on Python 3.13+ where the ``cgi`` module was removed.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Make the sibling indeed_cli package importable when launched directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from indeed_cli.fetch import FetchError  # noqa: E402
from indeed_cli.render import render_markdown  # noqa: E402
from indeed_cli.sources import fetch_and_parse  # noqa: E402
from webapp import backup, gsync  # noqa: E402
from webapp.db import STATUSES, Database  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
DATA_DIR = ROOT / "data"
FILES_DIR = DATA_DIR / "files"
BACKUPS_DIR = DATA_DIR / "backups"

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(name: str) -> str:
    name = os.path.basename(name or "file")
    return _SAFE.sub("_", name).strip("_") or "file"


class Handler(BaseHTTPRequestHandler):
    server_version = "JobTrail/1.0"
    db: Database = None  # set on the server instance
    db_path: str = None
    backups_dir = None

    def _backup(self, reason: str):
        try:
            if self.db_path and self.backups_dir:
                backup.snapshot(self.db_path, self.backups_dir, reason=reason)
                self.db.dirty = False
        except Exception:
            pass  # backups must never block a user action

    # -- helpers ---------------------------------------------------------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message):
        self._send_json({"error": message}, status=status)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _serve_static(self, rel: str):
        rel = rel.lstrip("/") or "index.html"
        target = (STATIC_DIR / rel).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # -- routing ---------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "":
            return self._serve_static("index.html")
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        if path == "/api/meta":
            return self._send_json({"statuses": STATUSES})
        if path == "/api/jobs":
            return self._send_json(self.db.list_jobs())
        if path == "/api/trash":
            return self._send_json(self.db.list_trash())
        if path == "/api/backups":
            return self._send_json(backup.list_snapshots(self.backups_dir))
        if path == "/api/export":
            return self._export()
        if path == "/api/google/status":
            return self._send_json(gsync.status())

        m = re.fullmatch(r"/api/jobs/(\d+)", path)
        if m:
            job = self.db.get_job(int(m.group(1)))
            return self._send_json(job) if job else self._error(404, "no such job")

        m = re.fullmatch(r"/api/jobs/(\d+)/markdown", path)
        if m:
            job = self.db.get_job(int(m.group(1)))
            if not job:
                return self._error(404, "no such job")
            md = self._render_from_row(job)
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            body = md.encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)

        m = re.fullmatch(r"/api/jobs/(\d+)/file", path)
        if m:
            return self._download_file(int(m.group(1)), parse_qs(parsed.query))

        return self._error(404, "not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/jobs":
            return self._add_job()
        if path == "/api/import":
            return self._import()
        if path == "/api/google/sync":
            return self._send_json(gsync.sync_now(self.db_path))
        if path == "/api/backup":
            self._backup("manual")
            return self._send_json({"ok": True, "backups": backup.list_snapshots(self.backups_dir)})
        m = re.fullmatch(r"/api/jobs/(\d+)/file", path)
        if m:
            return self._upload_file(int(m.group(1)))
        m = re.fullmatch(r"/api/jobs/(\d+)/restore", path)
        if m:
            ok = self.db.restore(int(m.group(1)))
            return self._send_json(self.db.get_job(int(m.group(1)))) if ok else self._error(404, "no such job")
        return self._error(404, "not found")

    def do_PATCH(self):
        m = re.fullmatch(r"/api/jobs/(\d+)", urlparse(self.path).path)
        if not m:
            return self._error(404, "not found")
        job_id = int(m.group(1))
        if not self.db.get_job(job_id):
            return self._error(404, "no such job")
        try:
            self.db.update_application(job_id, self._read_json())
        except ValueError as e:
            return self._error(400, str(e))
        return self._send_json(self.db.get_job(job_id))

    def do_DELETE(self):
        parsed = urlparse(self.path)
        m = re.fullmatch(r"/api/jobs/(\d+)/file", parsed.path)
        if m:
            return self._delete_file(int(m.group(1)), parse_qs(parsed.query))
        m = re.fullmatch(r"/api/jobs/(\d+)", parsed.path)
        if m:
            job_id = int(m.group(1))
            purge = (parse_qs(parsed.query).get("purge") or ["0"])[0] in ("1", "true")
            if purge:
                self._backup("pre-purge")
                row = self.db.purge(job_id)
                if not row:
                    return self._error(404, "no such job")
                self._remove_files(row)
                return self._send_json({"purged": True})
            # Default: reversible soft delete (move to trash), with a safety backup.
            self._backup("pre-delete")
            ok = self.db.soft_delete(job_id)
            return self._send_json({"trashed": True}) if ok else self._error(404, "no such job")
        return self._error(404, "not found")

    def _remove_files(self, row: dict):
        for kind in ("resume", "cover_letter"):
            p = row.get(f"{kind}_path")
            if p and Path(p).is_file():
                try:
                    Path(p).unlink()
                except OSError:
                    pass
        # Drop the now-empty per-job directory if present.
        if row.get("id") is not None:
            d = FILES_DIR / str(row["id"])
            if d.is_dir():
                try:
                    d.rmdir()
                except OSError:
                    pass

    # -- handlers --------------------------------------------------------
    def _add_job(self):
        data = self._read_json()
        url = (data.get("url") or "").strip()
        if not url.startswith("http"):
            return self._error(400, "a valid http(s) job URL is required")
        try:
            job = fetch_and_parse(url)
        except FetchError as e:
            return self._error(502, str(e))
        except Exception as e:  # parsing safety net
            return self._error(500, f"could not parse job: {e}")
        job_id = self.db.add_job(job)
        return self._send_json(self.db.get_job(job_id), status=201)

    def _export(self):
        from datetime import datetime, timezone

        payload = {
            "jobtrail_export": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "jobs": self.db.export_all(),
        }
        body = json.dumps(payload, default=str, indent=2).encode("utf-8")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header(
            "Content-Disposition", f'attachment; filename="jobtrail-backup-{stamp}.json"'
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _import(self):
        data = self._read_json()
        jobs = data.get("jobs") if isinstance(data, dict) else data
        if not isinstance(jobs, list):
            return self._error(400, "expected a JobTrail export with a 'jobs' array")
        self._backup("pre-import")
        result = self.db.import_jobs(jobs)
        return self._send_json(result)

    def _upload_file(self, job_id: int):
        if not self.db.get_job(job_id):
            return self._error(404, "no such job")
        data = self._read_json()
        kind = data.get("kind")
        if kind not in ("resume", "cover_letter"):
            return self._error(400, "kind must be resume or cover_letter")
        filename = _safe_name(data.get("filename", "file"))
        try:
            content = base64.b64decode(data.get("content_b64", ""), validate=True)
        except Exception:
            return self._error(400, "content_b64 is not valid base64")
        if not content:
            return self._error(400, "empty file")
        dest_dir = FILES_DIR / str(job_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{kind}__{filename}"
        dest.write_bytes(content)
        self.db.set_file(job_id, kind, str(dest), filename)
        return self._send_json(self.db.get_job(job_id))

    def _delete_file(self, job_id: int, query: dict):
        kind = (query.get("kind") or [""])[0]
        if kind not in ("resume", "cover_letter"):
            return self._error(400, "kind must be resume or cover_letter")
        job = self.db.get_job(job_id)
        if not job:
            return self._error(404, "no such job")
        old = job.get(f"{kind}_path")
        if old and Path(old).is_file():
            try:
                Path(old).unlink()
            except OSError:
                pass
        self.db.set_file(job_id, kind, None, None)
        return self._send_json(self.db.get_job(job_id))

    def _download_file(self, job_id: int, query: dict):
        kind = (query.get("kind") or [""])[0]
        if kind not in ("resume", "cover_letter"):
            return self._error(400, "kind must be resume or cover_letter")
        job = self.db.get_job(job_id)
        if not job or not job.get(f"{kind}_path"):
            return self._error(404, "no file")
        path = Path(job[f"{kind}_path"])
        if not path.is_file():
            return self._error(404, "file missing on disk")
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{job.get(kind + "_name") or path.name}"',
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _render_from_row(self, row: dict) -> str:
        from indeed_cli.parse import Job

        job = Job(
            url=row.get("url", ""),
            job_key=row.get("job_key"),
            title=row.get("title"),
            company=row.get("company"),
            location=row.get("location"),
            remote=row.get("remote"),
            employment_type=row.get("employment_type"),
            salary=row.get("salary"),
            date_posted=row.get("date_posted"),
            industry=row.get("industry"),
            description_md=row.get("description_md"),
        )
        return render_markdown(job)

    def log_message(self, fmt, *args):  # quieter console
        sys.stderr.write("  %s\n" % (fmt % args))


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    db_path: str | None = None,
    backups_dir: str | None = None,
):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    resolved_db = str(db_path or (DATA_DIR / "jobs.db"))
    resolved_backups = Path(backups_dir) if backups_dir else BACKUPS_DIR
    resolved_backups.mkdir(parents=True, exist_ok=True)

    db = Database(resolved_db)
    Handler.db = db
    Handler.db_path = resolved_db
    Handler.backups_dir = resolved_backups

    # Safety net: snapshot on startup, then periodically while data changes.
    if Path(resolved_db).is_file():
        backup.snapshot(resolved_db, resolved_backups, reason="startup")
    periodic = backup.PeriodicBackup(db, resolved_db, resolved_backups)
    periodic.start()
    sheet_sync = gsync.AutoSync(resolved_db)
    sheet_sync.start()

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"\n  JobTrail running at {url}")
    print(f"  Backups: {resolved_backups}")
    print("  Open that URL in your browser. Press Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.")
    finally:
        periodic.stop()
        sheet_sync.stop()
        backup.snapshot(resolved_db, resolved_backups, reason="shutdown")
        httpd.server_close()
        db.close()


if __name__ == "__main__":
    serve()
