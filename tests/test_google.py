"""Offline tests for the Google Sheets connector. No network, no real OAuth."""

import base64
import hashlib
import os
import sys
import unittest
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp import gauth, gsheets, sheets_map  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
