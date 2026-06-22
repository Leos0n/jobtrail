"""Offline tests for the Google Sheets connector. No network, no real OAuth."""

import base64
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp import gauth, gsheets, gsync, sheets_map  # noqa: E402


class TestSpreadsheetId(unittest.TestCase):
    def test_from_url(self):
        self.assertEqual(
            gsheets.spreadsheet_id("https://docs.google.com/spreadsheets/d/1AbC_dEF-123/edit#gid=0"),
            "1AbC_dEF-123",
        )

    def test_bare_id(self):
        self.assertEqual(gsheets.spreadsheet_id("1AbCdEFghIJklMnOpQrStUvWx"), "1AbCdEFghIJklMnOpQrStUvWx")

    def test_bad(self):
        with self.assertRaises(ValueError):
            gsheets.spreadsheet_id("not a sheet")


class TestPKCE(unittest.TestCase):
    def test_pair_valid_s256(self):
        verifier, challenge = gauth.pkce_pair()
        self.assertTrue(43 <= len(verifier) <= 128)
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        self.assertEqual(challenge, expected)
        self.assertNotIn("=", challenge)

    def test_auth_url(self):
        url = gauth.build_auth_url("cid.apps.googleusercontent.com", "http://127.0.0.1:5000/", "chal", "st")
        q = parse_qs(urlparse(url).query)
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["access_type"], ["offline"])
        self.assertEqual(q["scope"], ["https://www.googleapis.com/auth/spreadsheets.readonly"])
        self.assertEqual(q["redirect_uri"], ["http://127.0.0.1:5000/"])


class TestMapping(unittest.TestCase):
    def test_two_job_tabs_layout(self):
        tab_a = [
            ["Company", "Role", "Date Applied", "Status", "Link"],
            ["Stripe", "Backend Engineer", "5/20/2026", "Phone Screen", "https://www.indeed.com/viewjob?jk=aaa111"],
            ["Figma", "Product Designer", "5/28/2026", "", ""],
        ]
        res = sheets_map.values_to_jobs(tab_a, default_status="applied", tab="Applications")
        self.assertEqual(len(res["jobs"]), 2)
        stripe = next(j for j in res["jobs"] if j["company"] == "Stripe")
        self.assertEqual(stripe["status"], "interviewing")
        self.assertEqual(stripe["date_applied"], "2026-05-20")
        self.assertEqual(stripe["job_key"], "aaa111")
        figma = next(j for j in res["jobs"] if j["company"] == "Figma")
        self.assertEqual(figma["status"], "applied")          # blank -> default
        self.assertTrue(figma["job_key"].startswith("gsheet-"))

    def test_idempotent_keys(self):
        rows = [["Company", "Role"], ["Linear", "Frontend Eng"]]
        k1 = sheets_map.values_to_jobs(rows, tab="T")["jobs"][0]["job_key"]
        k2 = sheets_map.values_to_jobs(rows, tab="T")["jobs"][0]["job_key"]
        self.assertEqual(k1, k2)

    def test_skips_blank_and_chart_like_rows(self):
        chart_tab = [["Month", "Count"], ["May", "12"], ["June", "9"]]
        res = sheets_map.values_to_jobs(chart_tab, tab="Charts")
        self.assertEqual(res["jobs"], [])  # no company/title/url -> nothing imported
        self.assertTrue(res["warnings"])

    def test_empty(self):
        self.assertEqual(sheets_map.values_to_jobs([], tab="x")["jobs"], [])


class TestDateGroupedYearCarry(unittest.TestCase):
    def test_yearless_headers_inherit_year(self):
        rows = [
            ["May 20th, 2026 (2 Jobs)"],
            ["Home Depot", "Cashier"],
            ["Target", "Stocker"],
            ["June 3rd (1 Jobs)"],   # no year
            ["Costco", "Member Rep"],
            ["June 5 (1 Jobs)"],     # no ordinal, no year
            ["Lowe's", "Associate"],
        ]
        res = sheets_map.values_to_jobs(rows, default_status="applied", tab="Applied")
        by = {j["company"]: j["date_applied"] for j in res["jobs"]}
        self.assertEqual(by["Home Depot"], "2026-05-20")
        self.assertEqual(by["Costco"], "2026-06-03")   # year carried from May header
        self.assertEqual(by["Lowe's"], "2026-06-05")


class TestTokenRefresh(unittest.TestCase):
    """A dead/expired refresh token must raise a clear AuthError, not KeyError."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.token = Path(self.dir) / "token.json"
        self.token.write_text(json.dumps({
            "access_token": "old", "refresh_token": "r", "expires_in": 3600,
            "_obtained": 0, "_client_id": "cid", "_client_secret": "sec",
        }))
        self._orig_post = gauth._post

    def tearDown(self):
        gauth._post = self._orig_post

    def test_invalid_grant_raises_autherror(self):
        def boom(url, data):
            raise urllib.error.HTTPError(
                url, 400, "Bad Request", {},
                io.BytesIO(b'{"error": "invalid_grant"}'),
            )
        gauth._post = boom
        with self.assertRaises(gauth.AuthError) as ctx:
            gauth.access_token(self.token)
        self.assertIn("invalid_grant", str(ctx.exception))
        self.assertIn("bin/jobtrail-google", str(ctx.exception))

    def test_missing_access_token_raises_autherror(self):
        gauth._post = lambda url, data: {"error": "unauthorized_client"}
        with self.assertRaises(gauth.AuthError):
            gauth.access_token(self.token)

    def test_successful_refresh_returns_token(self):
        gauth._post = lambda url, data: {"access_token": "fresh", "expires_in": 3600}
        self.assertEqual(gauth.access_token(self.token), "fresh")


class TestSyncErrorSurfacing(unittest.TestCase):
    """sync_now must record failures (not swallow them) and clear on success."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self._orig = {k: getattr(gsync, k) for k in ("GDIR", "TOKEN", "CONFIG")}
        gsync.GDIR = self.dir
        gsync.TOKEN = self.dir / "token.json"
        gsync.CONFIG = self.dir / "config.json"
        gsync.TOKEN.write_text("{}")  # is_connected only checks the file exists
        gsync.CONFIG.write_text(json.dumps(
            {"spreadsheet_url": "1AbCdEFghIJklMnOpQrStUvWxYz0123456789", "tabs": ["T"]}))
        self.db_path = str(self.dir / "jobs.db")
        self._oa, self._rt = gauth.access_token, gsheets.read_tab

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(gsync, k, v)
        gauth.access_token, gsheets.read_tab = self._oa, self._rt

    def test_auth_failure_is_recorded_not_swallowed(self):
        def boom(_):
            raise gauth.AuthError("Google rejected the refresh token (invalid_grant).")
        gauth.access_token = boom
        res = gsync.sync_now(self.db_path)
        self.assertFalse(res["ok"])
        self.assertIn("invalid_grant", res["reason"])
        st = gsync.status()
        self.assertIn("invalid_grant", st["last_error"])
        self.assertIsNotNone(st["last_attempt"])

    def test_success_clears_last_error(self):
        gauth.access_token = lambda _: "tok"
        gsheets.read_tab = lambda sid, tab, token: [["Company", "Role"], ["Acme", "Engineer"]]
        # seed a stale error first
        gsync._save_config({**json.loads(gsync.CONFIG.read_text()), "last_error": "old failure"})
        res = gsync.sync_now(self.db_path)
        self.assertTrue(res["ok"])
        self.assertEqual(res["added"], 1)
        self.assertIsNone(gsync.status()["last_error"])
        self.assertIsNotNone(gsync.status()["last_sync"])


class TestAutoSyncStartup(unittest.TestCase):
    """AutoSync should sync shortly after startup, not after a full interval."""

    def test_initial_tick_runs_before_full_interval(self):
        calls = []
        orig_configured, orig_sync = gsync.configured, gsync.sync_now
        gsync.configured = lambda: True
        gsync.sync_now = lambda db: calls.append(time.time())
        try:
            auto = gsync.AutoSync("ignored.db", interval=999, startup_delay=0.05)
            auto.start()
            time.sleep(0.3)
            auto.stop()
        finally:
            gsync.configured, gsync.sync_now = orig_configured, orig_sync
        self.assertEqual(len(calls), 1, "expected exactly one startup sync, not an interval wait")


if __name__ == "__main__":
    unittest.main()
