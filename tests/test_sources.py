"""Offline tests for source detection and LinkedIn parsing. No network."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indeed_cli import linkedin  # noqa: E402
from indeed_cli.sources import detect_source, parse_local  # noqa: E402

EX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


class TestDetect(unittest.TestCase):
    def test_indeed(self):
        self.assertEqual(detect_source("https://www.indeed.com/viewjob?jk=x"), "indeed")
        self.assertEqual(detect_source("https://uk.indeed.com/viewjob?jk=x"), "indeed")

    def test_linkedin(self):
        self.assertEqual(
            detect_source("https://www.linkedin.com/jobs/view/3812345678"), "linkedin"
        )

    def test_generic(self):
        self.assertEqual(detect_source("https://jobs.example.com/123"), "generic")


class TestLinkedInIds(unittest.TestCase):
    def test_view(self):
        self.assertEqual(
            linkedin.job_id_from_url("https://www.linkedin.com/jobs/view/3812345678"),
            "3812345678",
        )

    def test_current_job_id(self):
        self.assertEqual(
            linkedin.job_id_from_url(
                "https://www.linkedin.com/jobs/search/?currentJobId=3812345678&keywords=x"
            ),
            "3812345678",
        )

    def test_slug(self):
        self.assertEqual(
            linkedin.job_id_from_url(
                "https://www.linkedin.com/jobs/view/staff-designer-at-acme-3812345678"
            ),
            "3812345678",
        )


class TestLinkedInParse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(EX, "sample_linkedin.html"), encoding="utf-8") as fh:
            cls.job = parse_local(fh.read(), "https://www.linkedin.com/jobs/view/3812345678")

    def test_fields(self):
        j = self.job
        self.assertEqual(j.title, "Staff Product Designer")
        self.assertEqual(j.company, "Northwind Labs")
        self.assertEqual(j.job_key, "3812345678")
        self.assertEqual(j.extras.get("source"), "linkedin")
        self.assertIn("180,000", j.salary)
        self.assertIn("Seattle", j.location)

    def test_description(self):
        self.assertIn("Staff Product Designer", self.job.description_md)
        self.assertIn("- Own end-to-end design", self.job.description_md)

    def test_criteria(self):
        self.assertEqual(self.job.extras.get("seniority"), "Mid-Senior level")
        self.assertEqual(self.job.extras.get("job_function"), "Design")


if __name__ == "__main__":
    unittest.main()
