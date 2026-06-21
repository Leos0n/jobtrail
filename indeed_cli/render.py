"""Render a :class:`~indeed_cli.parse.Job` as a Markdown document."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .parse import Job


def _fmt_date(value: str | None) -> str | None:
    """Show ISO dates as ``YYYY-MM-DD``; pass anything else through."""
    if not value:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    return m.group(1) if m else value


def slugify(text: str, maxlen: int = 60) -> str:
    text = (text or "job").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:maxlen].rstrip("-")) or "job"


def filename_for(job: Job) -> str:
    parts = [p for p in (job.company, job.title) if p]
    base = slugify("-".join(parts)) if parts else "indeed-job"
    if job.job_key:
        base = f"{base}-{job.job_key}"
    return f"{base}.md"


def render_markdown(job: Job) -> str:
    lines: list[str] = []
    lines.append(f"# {job.title or 'Untitled role'}")
    lines.append("")

    # Metadata block as a definition-style list.
    meta: list[tuple[str, str | None]] = [
        ("Company", job.company),
        ("Location", job.location),
        ("Remote", job.remote),
        ("Employment type", job.employment_type),
        ("Salary", job.salary),
        ("Industry", job.industry),
        ("Posted", _fmt_date(job.date_posted)),
        ("Apply by", _fmt_date(job.valid_through)),
        ("Job key", job.job_key),
        ("Source", job.url),
    ]
    for label, value in meta:
        if value:
            lines.append(f"- **{label}:** {value}")
    lines.append("")

    # Structured schema.org sections, when Indeed provides them.
    structured: list[tuple[str, str | None]] = [
        ("Responsibilities", job.responsibilities),
        ("Qualifications", job.qualifications),
        ("Skills", job.skills),
        ("Education", job.education),
        ("Experience", job.experience),
        ("Benefits", job.benefits),
    ]
    for heading, value in structured:
        if value:
            lines.append(f"## {heading}")
            lines.append("")
            lines.append(value)
            lines.append("")

    lines.append("## Description")
    lines.append("")
    lines.append(job.description_md or "_No description was found on the page._")
    lines.append("")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("---")
    lines.append(f"_Extracted from Indeed with Indeed-CLI on {stamp}._")
    lines.append("")
    return "\n".join(lines)
