"""LinkedIn job source.

LinkedIn job pages embed schema.org JobPosting JSON-LD just like Indeed, so the
generic :func:`indeed_cli.parse.parse_job` already covers most fields. On top of
that, LinkedIn exposes a public, no-auth "guest" fragment endpoint:

    https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<jobId>

which returns a small HTML fragment with the JSON-LD and a clean description
block. We prefer that endpoint because the full job page is heavier and more
likely to challenge an automated request.
"""

from __future__ import annotations

import html as _html
import re

from .htmlmd import html_to_markdown
from .parse import Job, parse_job

GUEST_API = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


def job_id_from_url(url: str) -> str | None:
    """Extract the numeric LinkedIn job id from any common URL shape."""
    for pat in (
        r"/jobs/view/(\d+)",          # /jobs/view/3812345678
        r"[?&]currentJobId=(\d+)",    # /jobs/search/?currentJobId=3812345678
        r"jobPosting/(\d+)",          # guest api url
        r"-(\d{6,})(?:[/?]|$)",       # slug ending -3812345678
    ):
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def guest_api_url(job_id: str) -> str:
    return GUEST_API.format(job_id=job_id)


def _first(patterns: list[str], html: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m:
            text = re.sub(r"<[^>]+>", " ", m.group(1))
            text = _html.unescape(re.sub(r"\s+", " ", text)).strip()
            if text:
                return text
    return None


def parse_fragment(html: str, url: str, job_id: str | None = None) -> Job:
    """Parse a LinkedIn guest fragment (or full page) into a :class:`Job`."""
    # JSON-LD is source-agnostic — reuse the generic parser first.
    job = parse_job(html, url)
    job.job_key = job.job_key or job_id or job_id_from_url(url)

    # Fill gaps from LinkedIn's known markup when JSON-LD was thin.
    if not job.title:
        job.title = _first(
            [
                r'<h2[^>]*class="[^"]*top-card-layout__title[^"]*"[^>]*>(.*?)</h2>',
                r'<h1[^>]*class="[^"]*topcard__title[^"]*"[^>]*>(.*?)</h1>',
            ],
            html,
        )
    if not job.company:
        job.company = _first(
            [
                r'<a[^>]*class="[^"]*topcard__org-name-link[^"]*"[^>]*>(.*?)</a>',
                r'<span[^>]*class="[^"]*topcard__flavor[^"]*"[^>]*>(.*?)</span>',
            ],
            html,
        )
    if not job.location:
        job.location = _first(
            [
                r'<span[^>]*class="[^"]*topcard__flavor--bullet[^"]*"[^>]*>(.*?)</span>',
            ],
            html,
        )

    # Description: LinkedIn puts the rich HTML in show-more-less-html__markup.
    if not job.description_md:
        m = re.search(
            r'<div[^>]*class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>\s*</div>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            job.description_html = m.group(1)
            job.description_md = html_to_markdown(m.group(1))

    # The "job criteria" list carries seniority / employment type / function.
    criteria = re.findall(
        r'<h3[^>]*criteria[^>]*subheader[^>]*>(.*?)</h3>\s*'
        r'<span[^>]*criteria[^>]*>(.*?)</span>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    for label_raw, value_raw in criteria:
        label = _html.unescape(re.sub(r"<[^>]+>", "", label_raw)).strip().lower()
        value = _html.unescape(re.sub(r"<[^>]+>", "", value_raw)).strip()
        if not value:
            continue
        if "employment type" in label and not job.employment_type:
            job.employment_type = value
        elif "seniority" in label:
            job.extras["seniority"] = value
        elif "job function" in label:
            job.extras["job_function"] = value
        elif "industries" in label and not job.industry:
            job.industry = value

    return job
