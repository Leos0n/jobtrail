"""Extract a normalized job record from an Indeed job page.

Strategy, most reliable first:

1. ``<script type="application/ld+json">`` containing a schema.org JobPosting.
   This is clean, stable, and already structured. It is the primary source.
2. ``window._initialData`` / Mosaic JSON blobs, used only to fill gaps the
   JSON-LD leaves empty (occasionally the salary or remote flag).
3. Plain-text fallbacks (``<title>``) so we always return *something* useful.
"""

from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass, field

from .htmlmd import html_to_markdown


@dataclass
class Job:
    """A normalized Indeed job posting."""

    url: str
    job_key: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    remote: str | None = None
    employment_type: str | None = None
    salary: str | None = None
    date_posted: str | None = None
    valid_through: str | None = None
    industry: str | None = None
    description_html: str | None = None
    description_md: str | None = None
    # schema.org JobPosting extras when present.
    responsibilities: str | None = None
    qualifications: str | None = None
    skills: str | None = None
    education: str | None = None
    experience: str | None = None
    benefits: str | None = None
    extras: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# URL helpers
# --------------------------------------------------------------------------
def job_key_from_url(url: str) -> str | None:
    """Pull the Indeed job key (``jk`` / ``vjk``) out of a URL if present."""
    m = re.search(r"[?&](?:jk|vjk)=([0-9a-fA-F]+)", url)
    return m.group(1) if m else None


# --------------------------------------------------------------------------
# JSON-LD extraction
# --------------------------------------------------------------------------
_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _iter_jsonld(html: str):
    for block in _LD_RE.findall(html):
        block = block.strip()
        if not block:
            continue
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        # A block may be a single object, a list, or wrapped in @graph.
        if isinstance(data, list):
            yield from data
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                yield from data["@graph"]
            else:
                yield data


def _is_jobposting(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    t = obj.get("@type")
    if isinstance(t, list):
        return any("JobPosting" in str(x) for x in t)
    return "JobPosting" in str(t or "")


def find_jobposting(html: str) -> dict | None:
    for obj in _iter_jsonld(html):
        if _is_jobposting(obj):
            return obj
    return None


# --------------------------------------------------------------------------
# window._initialData / Mosaic extraction (brace-balanced)
# --------------------------------------------------------------------------
def _extract_js_object(text: str, key_pattern: str) -> dict | None:
    """Find ``<key> = { ... };`` and return the parsed object.

    Uses brace balancing so nested objects are captured correctly.
    """
    m = re.search(key_pattern, text)
    if not m:
        return None
    start = text.find("{", m.end() - 1)
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    quote = ""
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == quote:
                in_str = False
        else:
            if c in "\"'":
                in_str = True
                quote = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        return None
    return None


def _deep_find(obj, keys: set[str]):
    """Yield values whose dict key is in ``keys``, searching recursively."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                yield v
            yield from _deep_find(v, keys)
    elif isinstance(obj, list):
        for item in obj:
            yield from _deep_find(item, keys)


# --------------------------------------------------------------------------
# Field normalization
# --------------------------------------------------------------------------
def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = _html.unescape(value).strip()
        return s or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("value"))
    if isinstance(value, list):
        parts = [p for p in (_text(v) for v in value) if p]
        return ", ".join(parts) or None
    return None


def _format_location(jp: dict) -> str | None:
    loc = jp.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, dict):
        addr = loc.get("address", loc)
        if isinstance(addr, dict):
            parts = [
                addr.get("streetAddress"),
                addr.get("addressLocality"),
                addr.get("addressRegion"),
                addr.get("postalCode"),
                _text(addr.get("addressCountry")),
            ]
            joined = ", ".join(str(p).strip() for p in parts if p and str(p).strip())
            return joined or None
    return _text(loc)


def _format_salary(jp: dict) -> str | None:
    bs = jp.get("baseSalary")
    if not isinstance(bs, dict):
        return _text(bs)
    currency = bs.get("currency") or ""
    val = bs.get("value")
    sym = {"USD": "$", "GBP": "£", "EUR": "€", "CAD": "C$", "AUD": "A$"}.get(currency, "")
    if isinstance(val, dict):
        lo = val.get("minValue")
        hi = val.get("maxValue")
        single = val.get("value")
        unit = (val.get("unitText") or "").lower()
        unit_str = f" per {unit}" if unit else ""

        def fmt(n):
            try:
                f = float(n)
                return f"{sym}{f:,.0f}" if f == int(f) else f"{sym}{f:,.2f}"
            except (TypeError, ValueError):
                return f"{sym}{n}"

        if lo and hi and lo != hi:
            return f"{fmt(lo)} – {fmt(hi)}{unit_str}".strip()
        if single or lo:
            return f"{fmt(single or lo)}{unit_str}".strip()
    return _text(val) or (f"{currency}".strip() or None)


def _humanize_employment(value) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    pretty = {
        "FULL_TIME": "Full-time",
        "PART_TIME": "Part-time",
        "CONTRACTOR": "Contract",
        "TEMPORARY": "Temporary",
        "INTERN": "Internship",
        "VOLUNTEER": "Volunteer",
        "PER_DIEM": "Per diem",
        "OTHER": "Other",
    }
    parts = [pretty.get(p.strip().upper(), p.strip().title()) for p in raw.split(",")]
    return ", ".join(p for p in parts if p)


def _remote_flag(jp: dict) -> str | None:
    jlt = jp.get("jobLocationType")
    if jlt and "TELECOMMUTE" in str(jlt).upper():
        return "Remote"
    app = jp.get("applicantLocationRequirements")
    if app:
        return f"Remote ({_text(app)})" if _text(app) else "Remote"
    return None


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def parse_job(html: str, url: str) -> Job:
    job = Job(url=url, job_key=job_key_from_url(url))
    jp = find_jobposting(html)

    if jp:
        job.title = _text(jp.get("title"))
        job.company = _text(jp.get("hiringOrganization"))
        job.location = _format_location(jp)
        job.remote = _remote_flag(jp)
        job.employment_type = _humanize_employment(jp.get("employmentType"))
        job.salary = _format_salary(jp)
        job.date_posted = _text(jp.get("datePosted"))
        job.valid_through = _text(jp.get("validThrough"))
        job.industry = _text(jp.get("industry"))
        job.description_html = jp.get("description")
        job.responsibilities = _text(jp.get("responsibilities"))
        job.qualifications = _text(jp.get("qualifications"))
        job.skills = _text(jp.get("skills"))
        job.education = _text(jp.get("educationRequirements"))
        job.experience = _text(jp.get("experienceRequirements"))
        job.benefits = _text(jp.get("jobBenefits"))
        ident = jp.get("identifier")
        if isinstance(ident, dict) and not job.job_key:
            job.job_key = _text(ident.get("value"))

    # Fallback: mine the _initialData blob for a description if JSON-LD lacked one.
    if not job.description_html or not job.title:
        blob = _extract_js_object(html, r"_initialData\s*=") or _extract_js_object(
            html, r"window\.mosaic\.providerData\s*\[[^\]]+\]\s*="
        )
        if blob:
            if not job.title:
                for v in _deep_find(blob, {"jobTitle", "title"}):
                    if isinstance(v, str) and v.strip():
                        job.title = _html.unescape(v.strip())
                        break
            if not job.description_html:
                for v in _deep_find(blob, {"sanitizedJobDescription", "description"}):
                    if isinstance(v, str) and "<" in v:
                        job.description_html = v
                        break

    # Last-ditch title from <title>.
    if not job.title:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if m:
            job.title = _html.unescape(re.sub(r"\s+", " ", m.group(1)).strip()) or None

    if job.description_html:
        job.description_md = html_to_markdown(job.description_html)

    return job
