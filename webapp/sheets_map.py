"""Map Google Sheets rows (list-of-lists) into JobTrail job records.

Source-agnostic: the first row is treated as headers, which are fuzzily matched
to JobTrail fields. Free-text statuses and dates are normalized. A per-tab
``default_status`` lets a "tab = pipeline stage" layout assign status by tab.

Stdlib only. Shared by the Google Sheets connector (and reusable for CSV).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

STATUSES = ["saved", "applied", "interviewing", "offer", "rejected", "archived"]

HEADER_ALIASES = {
    "company": ["company", "employer", "organization", "org", "company name", "firm"],
    "title": ["title", "role", "position", "job title", "job", "job role", "job name"],
    "url": ["url", "link", "job link", "posting", "job url", "listing", "apply link", "job posting"],
    "location": ["location", "city", "place", "where", "office"],
    "salary": ["salary", "pay", "compensation", "comp", "salary range"],
    "status": ["status", "stage", "state", "progress", "application status", "result", "outcome"],
    "date_applied": ["date applied", "applied", "application date", "date", "applied on", "applied date", "submitted", "date submitted"],
    "follow_up_date": ["follow up", "follow up date", "followup", "next step", "next step date", "reminder", "follow-up"],
    "contact": ["contact", "recruiter", "referral", "point of contact", "poc", "hiring manager"],
    "notes": ["notes", "note", "comments", "comment", "details", "remarks"],
    "salary_expectation": ["salary expectation", "expected salary", "target salary", "ask", "desired salary"],
    "rating": ["rating", "interest", "priority", "fit", "excitement"],
}

STATUS_SYNONYMS = {
    "saved": ["saved", "wishlist", "to apply", "bookmarked", "interested", "backlog", "todo", "to do", "lead", "prospect"],
    "applied": ["applied", "submitted", "sent", "application sent", "app sent", "in review", "under review", "pending", "waiting"],
    "interviewing": ["interview", "interviewing", "interviews", "phone screen", "screen", "onsite", "on site", "final", "oa", "assessment", "in progress", "recruiter call", "tech screen"],
    "offer": ["offer", "offered", "accepted", "hired", "verbal offer"],
    "rejected": ["rejected", "declined", "no", "rejection", "ghosted", "closed", "withdrew", "withdrawn", "not selected", "turned down", "passed", "dinged"],
    "archived": ["archived", "archive", "old", "inactive", "stale"],
}

_RATING_WORDS = {"low": 2, "medium": 3, "med": 3, "high": 5, "top": 5, "maybe": 2, "dream": 5}
_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y",
                 "%b %d %Y", "%b %d, %Y", "%B %d %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"]


def _norm(s):
    return re.sub(r"[\s_]+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


def detect_mapping(headers):
    mapping, used = {}, set()
    for h in headers:
        n = _norm(h)
        for field, aliases in HEADER_ALIASES.items():
            if field in used:
                continue
            if n in aliases or any(n == _norm(a) for a in aliases):
                mapping[h] = field
                used.add(field)
                break
    for h in headers:
        if h in mapping:
            continue
        n = _norm(h)
        for field, aliases in HEADER_ALIASES.items():
            if field in used:
                continue
            if n and any(a in n or n in a for a in aliases):
                mapping[h] = field
                used.add(field)
                break
    return mapping


def normalize_status(value, default=None, has_date=False):
    n = _norm(value)
    if not n:
        return default or ("applied" if has_date else "saved")
    for status, syns in STATUS_SYNONYMS.items():
        if n in syns or any(n == _norm(s) for s in syns):
            return status
    for status, syns in STATUS_SYNONYMS.items():
        if any(s in n for s in syns):
            return status
    return default or "applied"


def normalize_date(value):
    v = (value or "").strip()
    if not v:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"\d{4}-\d{2}-\d{2}", v)
    return m.group(0) if m else v


def normalize_rating(value):
    v = _norm(value)
    if not v:
        return 0
    if v in _RATING_WORDS:
        return _RATING_WORDS[v]
    m = re.search(r"\d+", v)
    if m:
        return max(0, min(5, int(m.group(0))))
    return v.count("*") or v.count("★") or 0


def _job_key(url, company, title, tab):
    if url:
        m = re.search(r"[?&](?:jk|vjk)=([0-9a-fA-F]+)", url) or re.search(r"/jobs/view/(\d+)", url)
        if m:
            return m.group(1)
    basis = f"{_norm(tab)}|{_norm(company)}|{_norm(title)}"
    return "gsheet-" + hashlib.sha1(basis.encode()).hexdigest()[:12]


_MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
DATE_HEADER_RE = re.compile(rf"^\s*{_MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?\b", re.I)


def _cell(c):
    return "" if c is None else str(c)


def parse_header_date(text, default_year=None):
    m = re.search(rf"({_MONTHS})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?", text, re.I)
    if not m:
        return None
    year = m.group(3) or default_year or str(datetime.now().year)
    try:
        stamp = f"{m.group(1)[:3].title()} {int(m.group(2))} {year}"
        return datetime.strptime(stamp, "%b %d %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def match_status(value):
    """Return a canonical status only if the cell clearly *is* a status word."""
    n = _norm(value)
    if not n:
        return None
    for status, syns in STATUS_SYNONYMS.items():
        if n == status or n in [_norm(s) for s in syns]:
            return status
    return None


def looks_grouped(values):
    return sum(1 for r in values if r and DATE_HEADER_RE.match(_cell(r[0]).strip())) >= 2


def _values_to_jobs_grouped(values, tab, default_status):
    """Parse the date-grouped layout: a date header row, then one job per row
    (Company, Role, Location?, Link?, Status?), repeating per day."""
    jobs, cur_date, cur_year = [], None, None
    for row in values:
        cells = [_cell(c).strip() for c in row]
        if not any(cells):
            continue
        if DATE_HEADER_RE.match(cells[0]):
            ym = re.search(r"\b(\d{4})\b", cells[0])
            if ym:
                cur_year = ym.group(1)
            cur_date = parse_header_date(cells[0], default_year=cur_year)
            continue
        company = cells[0]
        if not company:
            continue
        title = cells[1] if len(cells) > 1 and cells[1] else None
        url = location = status = None
        for c in cells[2:]:
            if not c:
                continue
            if c.lower().startswith("http"):
                url = c
            elif match_status(c):
                status = match_status(c)
            elif location is None:
                location = c
        job = {
            "source": "google-sheet",
            "company": company,
            "title": title,
            "location": location,
            "status": status or default_status or "applied",
            "date_applied": cur_date,
            "url": url,
        }
        job["job_key"] = _job_key(url, company, title, f"{tab}|{cur_date}")
        if not job["url"]:
            job["url"] = f"gsheet://{job['job_key']}"
        jobs.append({k: v for k, v in job.items() if v is not None})
    return {"mapping": {"layout": "date-grouped"}, "jobs": jobs, "warnings": []}


def values_to_jobs(values, default_status=None, tab=None, mapping=None):
    """Convert a tab's values into job dicts. Handles both a standard table
    (row 0 = column headers) and a date-grouped layout (auto-detected)."""
    if not values:
        return {"mapping": {}, "jobs": [], "warnings": ["empty tab"]}
    if mapping is None and looks_grouped(values):
        return _values_to_jobs_grouped(values, tab, default_status)
    headers = [str(h).strip() for h in values[0]]
    mapping = mapping or detect_mapping(headers)
    warnings = []
    if "company" not in mapping.values() and "title" not in mapping.values():
        warnings.append(f"tab '{tab}': no company/title column detected")

    jobs = []
    for row in values[1:]:
        fields = {}
        for i, header in enumerate(headers):
            field = mapping.get(header)
            if not field:
                continue
            val = (str(row[i]).strip() if i < len(row) and row[i] is not None else "")
            if val:
                fields[field] = val
        if not any(fields.get(k) for k in ("company", "title", "url")):
            continue

        date_applied = normalize_date(fields.get("date_applied"))
        job = {
            "source": "google-sheet",
            "url": fields.get("url"),
            "company": fields.get("company"),
            "title": fields.get("title"),
            "location": fields.get("location"),
            "salary": fields.get("salary"),
            "status": normalize_status(fields.get("status"), default=default_status, has_date=bool(date_applied)),
            "date_applied": date_applied,
            "follow_up_date": normalize_date(fields.get("follow_up_date")),
            "contact": fields.get("contact"),
            "notes": fields.get("notes"),
            "salary_expectation": fields.get("salary_expectation"),
            "rating": normalize_rating(fields.get("rating")),
        }
        job["job_key"] = _job_key(job["url"], job["company"], job["title"], tab)
        if not job["url"]:
            job["url"] = f"gsheet://{job['job_key']}"
        jobs.append({k: v for k, v in job.items() if v is not None})

    return {"mapping": mapping, "jobs": jobs, "warnings": warnings}
