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
        self._rtl = gsheets.read_tab_with_links

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(gsync, k, v)
        gauth.access_token, gsheets.read_tab = self._oa, self._rt
        gsheets.read_tab_with_links = self._rtl

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
        gsheets.read_tab_with_links = lambda sid, tab, token: (
            [["Company", "Role"], ["Acme", "Engineer"]], [[None, None], [None, None]])
        # seed a stale error first
        gsync._save_config({**json.loads(gsync.CONFIG.read_text()), "last_error": "old failure"})
        res = gsync.sync_now(self.db_path)
        self.assertTrue(res["ok"])
        self.assertEqual(res["added"], 1)
        self.assertIsNone(gsync.status()["last_error"])
        self.assertIsNotNone(gsync.status()["last_sync"])


class TestCellLinks(unittest.TestCase):
    """Recover apply URLs hidden behind label text ('Apply Here')."""

    def test_cell_level_hyperlink(self):
        cell = {"formattedValue": "Apply Here", "hyperlink": "https://jobs.example.com/123"}
        self.assertEqual(gsheets._cell_link(cell), "https://jobs.example.com/123")

    def test_hyperlink_formula(self):
        cell = {"formattedValue": "Apply Here",
                "userEnteredValue": {"formulaValue": '=HYPERLINK("https://x.io/a","Apply Here")'}}
        self.assertEqual(gsheets._cell_link(cell), "https://x.io/a")

    def test_rich_text_run_link(self):
        cell = {"formattedValue": "Apply Here",
                "textFormatRuns": [{"format": {"link": {"uri": "https://x.io/rt"}}}]}
        self.assertEqual(gsheets._cell_link(cell), "https://x.io/rt")

    def test_no_link(self):
        self.assertIsNone(gsheets._cell_link({"formattedValue": "Apple Valley, CA"}))


class TestGroupedLinksThreaded(unittest.TestCase):
    """The date-grouped layout should pick up the hyperlink as the job url."""

    def test_apply_here_link_becomes_url(self):
        # >=2 date headers so the grouped layout is detected (looks_grouped).
        values = [
            ["June 21st, 2026 (1 Jobs)", "", "", ""],
            ["Decorware Inc", "Digital Marketing Manager", "Hybrid", "Apply Here"],
            ["June 22nd, 2026 (1 Jobs)", "", "", ""],
            ["Kingston Brass, Inc", "Digital Marketing Coordinator", "Chino, CA", "Apply Here"],
        ]
        links = [
            [None, None, None, None],
            [None, None, None, "https://decorware.example.com/apply"],
            [None, None, None, None],
            [None, None, None, "https://kingston.example.com/apply"],
        ]
        res = sheets_map.values_to_jobs(values, tab="Applications", links=links)
        jobs = {j["company"]: j for j in res["jobs"]}
        self.assertEqual(jobs["Kingston Brass, Inc"]["url"], "https://kingston.example.com/apply")
        self.assertEqual(jobs["Kingston Brass, Inc"]["date_applied"], "2026-06-22")
        self.assertEqual(jobs["Decorware Inc"]["date_applied"], "2026-06-21")

    def test_no_link_falls_back_to_placeholder(self):
        values = [["June 21st, 2026 (1 Jobs)", "", "", ""],
                  ["Decorware Inc", "Marketing Manager", "Hybrid", "Apply Here"],
                  ["June 22nd, 2026 (1 Jobs)", "", "", ""],
                  ["Acme", "Engineer", "Remote", "Apply Here"]]
        res = sheets_map.values_to_jobs(values, tab="T", links=None)
        self.assertTrue(all(j["url"].startswith("gsheet://") for j in res["jobs"]))


class TestResetReimport(unittest.TestCase):
    """delete_by_source enables a clean re-import with exact counts."""

    def test_reset_clears_stale_duplicates(self):
        from webapp.db import Database
        dbf = tempfile.mktemp(suffix=".db")
        db = Database(dbf)
        # Stale rows from an "older sync" with different job_keys, same days.
        stale = [{"source": "google-sheet", "company": "A", "title": "x",
                  "date_applied": "2026-06-22", "url": "gsheet://old1", "job_key": "old1"},
                 {"source": "google-sheet", "company": "B", "title": "y",
                  "date_applied": "2026-06-22", "url": "gsheet://old2", "job_key": "old2"}]
        db.import_jobs(stale)
        # A manually added (non-sheet) job must survive the reset.
        db.import_jobs([{"source": "indeed", "company": "Manual", "title": "z",
                         "url": "https://indeed.com/viewjob?jk=abc", "job_key": "abc"}])
        fresh = [{"source": "google-sheet", "company": "A", "title": "x",
                  "date_applied": "2026-06-22", "url": "https://a.io/apply", "job_key": "new1"}]
        removed = db.delete_by_source("google-sheet")
        db.import_jobs(fresh)
        rows = db.export_all()
        db.close(); os.remove(dbf)
        self.assertEqual(removed, 2)
        sheet_rows = [r for r in rows if r["source"] == "google-sheet"]
        self.assertEqual(len(sheet_rows), 1)
        self.assertEqual(sheet_rows[0]["url"], "https://a.io/apply")
        self.assertTrue(any(r["source"] == "indeed" for r in rows))  # manual job kept


class TestWipeReimport(unittest.TestCase):
    """clear_jobs is the nuclear reset for stale rows that escape source scope."""

    def test_wipe_clears_everything_then_reimports(self):
        from webapp.db import Database
        dbf = tempfile.mktemp(suffix=".db")
        db = Database(dbf)
        # Stale rows WITHOUT a 'google-sheet' source (older sync) — delete_by_source
        # would miss these, but a wipe must not.
        db.import_jobs([{"source": None, "company": "Old", "title": "x",
                         "date_applied": "2026-06-22", "url": "gsheet://legacy", "job_key": "legacy"},
                        {"source": "indeed", "company": "Manual", "title": "z",
                         "url": "https://indeed.com/viewjob?jk=abc", "job_key": "abc"}])
        self.assertEqual(db.delete_by_source("google-sheet"), 0)  # source scope misses them
        cleared = db.clear_jobs()
        db.import_jobs([{"source": "google-sheet", "company": "A", "title": "x",
                         "date_applied": "2026-06-22", "url": "https://a.io/apply", "job_key": "new1"}])
        rows = db.export_all()
        db.close(); os.remove(dbf)
        self.assertEqual(cleared, 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["job_key"], "new1")


class TestPositionalSchema(unittest.TestCase):
    """Headerless A=company B=job C=location D=url E=time-submitted layout."""

    SCHEMA = [
        ["MGM Energy", "Human Resource Generalist", "Apple Valley, CA",
         "https://jobs.example.com/1", "2026-06-20 14:32:00"],
        ["Decorware Inc", "Digital Marketing Manager", "Rancho Cucamonga, CA",
         "https://jobs.example.com/2", "6/21/2026 9:05 AM"],
        ["Kingston Brass, Inc", "Digital Marketing Coordinator", "Chino, CA",
         "https://jobs.example.com/3", "06/22/2026"],
    ]

    def test_columns_map_by_position(self):
        res = sheets_map.values_to_jobs(self.SCHEMA, tab="Applications")
        self.assertEqual(res["mapping"]["layout"], "positional")
        jobs = res["jobs"]
        self.assertEqual(len(jobs), 3)
        j = jobs[0]
        self.assertEqual(j["company"], "MGM Energy")
        self.assertEqual(j["title"], "Human Resource Generalist")
        self.assertEqual(j["location"], "Apple Valley, CA")
        self.assertEqual(j["url"], "https://jobs.example.com/1")
        self.assertEqual(j["date_applied"], "2026-06-20")   # time stripped
        self.assertEqual(j["status"], "applied")            # has a submit date

    def test_timestamp_formats_reduce_to_date(self):
        res = sheets_map.values_to_jobs(self.SCHEMA, tab="A")
        days = sorted(j["date_applied"] for j in res["jobs"])
        self.assertEqual(days, ["2026-06-20", "2026-06-21", "2026-06-22"])

    def test_header_row_is_skipped_if_present(self):
        rows = [["Company", "Job", "Location", "URL", "Time Submitted"]] + self.SCHEMA
        res = sheets_map.values_to_jobs(rows, tab="A")
        # With recognizable headers this is the table layout, not positional;
        # either way the header must not become a job.
        self.assertEqual(len(res["jobs"]), 3)
        self.assertNotIn("Company", [j.get("company") for j in res["jobs"]])

    def test_per_day_counts_exact(self):
        rows = self.SCHEMA + [
            ["Pali Mountain", "Coordinator", "Running Springs, CA",
             "https://jobs.example.com/4", "2026-06-22 10:00:00"]]
        res = sheets_map.values_to_jobs(rows, tab="A")
        from collections import Counter
        by = Counter(j["date_applied"] for j in res["jobs"])
        self.assertEqual(by["2026-06-22"], 2)
        self.assertEqual(by["2026-06-20"], 1)


class TestTimestampNormalize(unittest.TestCase):
    def test_various(self):
        cases = {
            "2026-06-22": "2026-06-22",
            "2026-06-22 14:30:00": "2026-06-22",
            "2026-06-22T14:30": "2026-06-22",
            "6/22/2026": "2026-06-22",
            "6/22/2026 9:05 AM": "2026-06-22",
            "06/22/2026 14:30:00": "2026-06-22",
        }
        for raw, want in cases.items():
            self.assertEqual(sheets_map.normalize_date(raw), want, raw)


class TestClockParsing(unittest.TestCase):
    def test_formats(self):
        from webapp import sheets_map as sm
        self.assertEqual(sm.parse_clock("1218pm"), ("12:18", None))
        self.assertEqual(sm.parse_clock("102pm"), ("13:02", None))
        self.assertEqual(sm.parse_clock("115pm (END)"), ("13:15", "end"))
        self.assertEqual(sm.parse_clock("1218pm (START)"), ("12:18", "start"))
        self.assertEqual(sm.parse_clock("905am"), ("09:05", None))
        self.assertEqual(sm.parse_clock("1200am"), ("00:00", None))
        self.assertIsNone(sm.parse_clock("Apple Valley, CA"))
        self.assertIsNone(sm.parse_clock(""))


class TestGroupedTimeSessions(unittest.TestCase):
    """Date from the header, time from column E, (START)/(END) -> sessions."""

    def _day(self):
        times = ["1218pm (START)", "1220pm", "1225pm", "1230pm", "1233pm",
                 "1240pm", "1245pm", "1250pm", "1253pm", "102pm", "105pm",
                 "110pm", "115pm (END)", "145pm (START)", "155pm", "200pm",
                 "205pm", "217pm", "227pm", "231pm", "235pm", "255pm (END)"]
        rows = [["June 22nd, 2026 (22 Jobs)", "", "", "", ""],
                ["June 23rd, 2026 (0 Jobs)", "", "", "", ""]]  # 2nd header -> grouped
        # put the 22 real rows under the first header
        body = [[f"Co{i}", f"Role {i}", "Ontario, CA", f"https://x.io/{i}", t]
                for i, t in enumerate(times)]
        return rows[:1] + body + rows[1:]

    def test_time_in_date_and_sessions(self):
        res = sheets_map.values_to_jobs(self._day(), tab="A")
        jobs = res["jobs"]
        self.assertEqual(len(jobs), 22)
        # first job: 12:18 on the header date, session #1
        self.assertEqual(jobs[0]["date_applied"], "2026-06-22T12:18:00")
        self.assertEqual(jobs[0]["session"], "2026-06-22 #1")
        # the 14th app starts the second block at 1:45pm
        self.assertEqual(jobs[13]["date_applied"], "2026-06-22T13:45:00")
        self.assertEqual(jobs[13]["session"], "2026-06-22 #2")
        # all on the same calendar day (counts stay by-day)
        days = {j["date_applied"][:10] for j in jobs}
        self.assertEqual(days, {"2026-06-22"})

    def test_session_summary(self):
        from webapp import sessions
        jobs = sheets_map.values_to_jobs(self._day(), tab="A")["jobs"]
        summ = sessions.summarize(jobs)
        self.assertEqual(len(summ), 2)
        s1, s2 = summ
        self.assertEqual((s1["count"], s1["start"], s1["end"]), (13, "12:18", "13:15"))
        self.assertEqual((s2["count"], s2["start"], s2["end"]), (9, "13:45", "14:55"))
        self.assertGreater(s2["longest_gap_min"], 0)

    def test_repeat_application_stays_distinct(self):
        """Each logged application is its own record. The same posting (or a
        non-posting careers URL) submitted twice in a day must NOT collapse, so
        DB counts match the sheet — while a re-sync of the same sheet is still
        idempotent (no duplicates)."""
        from webapp.db import Database
        rows = [["June 22nd, 2026 (3 Jobs)", "", "", "", ""],
                ["Acme", "Eng", "CA", "https://indeed.com/viewjob?jk=aaa", "1218pm"],
                ["Acme", "Eng", "CA", "https://indeed.com/viewjob?jk=aaa", "1242pm"],
                ["Crux", "Dev", "CA", "https://co.com/careers/x", "105pm"],
                ["June 21st, 2026 (0 Jobs)", "", "", "", ""]]
        jobs = sheets_map.values_to_jobs(rows, tab="A")["jobs"]
        self.assertEqual(len(jobs), 3)
        self.assertEqual(len({j["job_key"] for j in jobs}), 3)  # all distinct

        db = Database(":memory:")
        db.import_jobs(jobs)
        self.assertEqual(len(db.list_jobs()), 3)                # match the sheet
        db.import_jobs(sheets_map.values_to_jobs(rows, tab="A")["jobs"])
        self.assertEqual(len(db.list_jobs()), 3)                # re-sync idempotent
        db.close()


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
