"""End-to-end webapp tests over loopback. No external network.

Seeds the SQLite store directly (no live scrape), starts the stdlib server on an
ephemeral port, and exercises the JSON API with http.client.
"""

import base64
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indeed_cli.parse import Job  # noqa: E402
from webapp import server as srv  # noqa: E402
from webapp.db import Database  # noqa: E402


class TestWebApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = cls.tmp.name
        # Redirect file storage into the temp dir.
        srv.DATA_DIR = __import__("pathlib").Path(base)
        srv.FILES_DIR = srv.DATA_DIR / "files"
        srv.FILES_DIR.mkdir(parents=True, exist_ok=True)

        cls.db = Database(os.path.join(base, "jobs.db"))
        job = Job(
            url="https://www.indeed.com/viewjob?jk=seed123",
            job_key="seed123",
            title="Test Engineer",
            company="Seed Co",
            location="Remote",
            salary="$100,000 per year",
            description_md="# Role\n\n- Do things",
            extras={"source": "indeed"},
        )
        cls.job_id = cls.db.add_job(job)
        srv.Handler.db = cls.db
        srv.Handler.db_path = os.path.join(base, "jobs.db")
        srv.Handler.backups_dir = srv.DATA_DIR / "backups"

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.db.close()
        cls.tmp.cleanup()

    def req(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data

    def test_01_list_and_meta(self):
        status, data = self.req("GET", "/api/jobs")
        self.assertEqual(status, 200)
        jobs = json.loads(data)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Test Engineer")

        status, data = self.req("GET", "/api/meta")
        self.assertIn("applied", json.loads(data)["statuses"])

    def test_02_patch(self):
        status, data = self.req(
            "PATCH", f"/api/jobs/{self.job_id}",
            {"status": "applied", "date_applied": "2026-06-20", "rating": 4,
             "notes": "Referred by a friend"},
        )
        self.assertEqual(status, 200)
        job = json.loads(data)
        self.assertEqual(job["status"], "applied")
        self.assertEqual(job["rating"], 4)
        self.assertEqual(job["notes"], "Referred by a friend")

    def test_03_bad_status_rejected(self):
        status, _ = self.req("PATCH", f"/api/jobs/{self.job_id}", {"status": "nope"})
        self.assertEqual(status, 400)

    def test_04_file_roundtrip(self):
        payload = b"%PDF-1.4 fake resume bytes"
        status, data = self.req(
            "POST", f"/api/jobs/{self.job_id}/file",
            {"kind": "resume", "filename": "my resume.pdf",
             "content_b64": base64.b64encode(payload).decode()},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["resume_name"], "my_resume.pdf")

        status, data = self.req("GET", f"/api/jobs/{self.job_id}/file?kind=resume")
        self.assertEqual(status, 200)
        self.assertEqual(data, payload)

    def test_05_markdown(self):
        status, data = self.req("GET", f"/api/jobs/{self.job_id}/markdown")
        self.assertEqual(status, 200)
        self.assertIn("# Test Engineer", data.decode())

    def test_06_soft_delete_to_trash(self):
        status, data = self.req("DELETE", f"/api/jobs/{self.job_id}")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["trashed"])
        # Gone from the active list...
        _, data = self.req("GET", "/api/jobs")
        self.assertEqual(len(json.loads(data)), 0)
        # ...but recoverable from trash.
        _, data = self.req("GET", "/api/trash")
        trash = json.loads(data)
        self.assertEqual(len(trash), 1)
        self.assertEqual(trash[0]["id"], self.job_id)

    def test_07_restore(self):
        status, _ = self.req("POST", f"/api/jobs/{self.job_id}/restore")
        self.assertEqual(status, 200)
        _, data = self.req("GET", "/api/jobs")
        self.assertEqual(len(json.loads(data)), 1)
        _, data = self.req("GET", "/api/trash")
        self.assertEqual(len(json.loads(data)), 0)

    def test_08_export_import_roundtrip(self):
        status, data = self.req("GET", "/api/export")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        self.assertEqual(payload["jobtrail_export"], 1)
        self.assertEqual(len(payload["jobs"]), 1)
        # Re-importing the same data is a no-op (already present).
        status, data = self.req("POST", "/api/import", payload)
        self.assertEqual(status, 200)
        res = json.loads(data)
        self.assertEqual(res["added"], 0)
        self.assertEqual(res["skipped"], 1)

    def test_09_import_new_job(self):
        new = {"jobs": [{"url": "https://www.indeed.com/viewjob?jk=imported9",
                          "job_key": "imported9", "title": "Imported Role",
                          "company": "Elsewhere", "status": "applied"}]}
        status, data = self.req("POST", "/api/import", new)
        self.assertEqual(json.loads(data)["added"], 1)
        _, data = self.req("GET", "/api/jobs")
        titles = {j["title"] for j in json.loads(data)}
        self.assertIn("Imported Role", titles)

    def test_10_backup_now(self):
        status, data = self.req("POST", "/api/backup", {})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["ok"])
        status, data = self.req("GET", "/api/backups")
        self.assertGreaterEqual(len(json.loads(data)), 1)

    def test_11_purge_forever(self):
        # Move the seeded job to trash, then permanently delete it.
        self.req("DELETE", f"/api/jobs/{self.job_id}")
        status, data = self.req("DELETE", f"/api/jobs/{self.job_id}?purge=1")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["purged"])
        _, data = self.req("GET", "/api/trash")
        ids = {j["id"] for j in json.loads(data)}
        self.assertNotIn(self.job_id, ids)


if __name__ == "__main__":
    unittest.main()
