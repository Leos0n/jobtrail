"""Offline regression tests — no network required.

Run from the Indeed-CLI directory:

    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indeed_cli.htmlmd import html_to_markdown  # noqa: E402
from indeed_cli.parse import job_key_from_url, parse_job  # noqa: E402
from indeed_cli.render import filename_for, render_markdown, slugify  # noqa: E402

FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "examples",
    "sample_job.html",
)


class TestUrlParsing(unittest.TestCase):
    def test_jk(self):
        self.assertEqual(
            job_key_from_url("https://www.indeed.com/viewjob?jk=abc123"), "abc123"
        )

    def test_vjk(self):
        self.assertEqual(
            job_key_from_url("https://www.indeed.com/q-x-jobs.html?vjk=def456"), "def456"
        )

    def test_none(self):
        self.assertIsNone(job_key_from_url("https://www.indeed.com/companies"))


class TestHtmlToMarkdown(unittest.TestCase):
    def test_lists_and_emphasis(self):
        md = html_to_markdown("<p>Hi <strong>there</strong></p><ul><li>a</li><li>b</li></ul>")
        self.assertIn("**there**", md)
        self.assertIn("- a", md)
        self.assertIn("- b", md)

    def test_links(self):
        md = html_to_markdown('<a href="https://x.com">x</a>')
        self.assertEqual(md, "[x](https://x.com)")

    def test_plain_text(self):
        self.assertEqual(html_to_markdown("just words"), "just words")


class TestParseFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as fh:
            cls.job = parse_job(fh.read(), "https://www.indeed.com/viewjob?jk=abc123def456")

    def test_core_fields(self):
        j = self.job
        self.assertEqual(j.title, "Senior Backend Engineer")
        self.assertEqual(j.company, "Acme Robotics")
        self.assertEqual(j.employment_type, "Full-time")
        self.assertEqual(j.job_key, "abc123def456")
        self.assertIn("San Francisco", j.location)
        self.assertIn("165,000", j.salary)
        self.assertIn("205,000", j.salary)
        self.assertTrue(j.date_posted.startswith("2026-06-15"))

    def test_description_markdown(self):
        self.assertIn("### Requirements", self.job.description_md)
        self.assertIn("- 5+ years", self.job.description_md)

    def test_render_and_filename(self):
        md = render_markdown(self.job)
        self.assertIn("# Senior Backend Engineer", md)
        self.assertIn("**Salary:**", md)
        self.assertEqual(
            filename_for(self.job),
            "acme-robotics-senior-backend-engineer-abc123def456.md",
        )


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")


if __name__ == "__main__":
    unittest.main()
