"""Route a job URL to the right fetch + parse strategy.

Supported sources:
  - indeed    (indeed.com and country subdomains)
  - linkedin  (linkedin.com job views, via the no-auth guest fragment)
  - generic   (any page carrying schema.org JobPosting JSON-LD)
"""

from __future__ import annotations

from urllib.parse import urlparse

from . import linkedin
from .fetch import fetch
from .parse import Job, parse_job


def detect_source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "linkedin." in host:
        return "linkedin"
    if "indeed." in host:
        return "indeed"
    return "generic"


def fetch_and_parse(url: str, *, timeout: float = 30.0, retries: int = 3) -> Job:
    """Fetch ``url`` and return a normalized :class:`Job`, source-aware."""
    source = detect_source(url)

    if source == "linkedin":
        job_id = linkedin.job_id_from_url(url)
        fetch_url = linkedin.guest_api_url(job_id) if job_id else url
        html = fetch(fetch_url, timeout=timeout, retries=retries)
        job = linkedin.parse_fragment(html, url, job_id=job_id)
    else:
        html = fetch(url, timeout=timeout, retries=retries)
        job = parse_job(html, url)

    job.extras.setdefault("source", source)
    return job


def parse_local(html: str, url: str) -> Job:
    """Parse already-fetched HTML (e.g. a saved page), source-aware."""
    source = detect_source(url)
    if source == "linkedin":
        job = linkedin.parse_fragment(html, url)
    else:
        job = parse_job(html, url)
    job.extras.setdefault("source", source)
    return job
