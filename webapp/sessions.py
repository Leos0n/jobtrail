"""Apply-session analytics.

A "session" is one focused apply block the user bracketed with (START)/(END)
in their sheet. Each job in a block carries a ``session`` label and an ISO
``date_applied`` that includes the submission time, so we can measure
consistency (how steadily applications went out) and distraction (the longest
gap between two submissions).

Stdlib only.
"""

from __future__ import annotations

import re
from datetime import datetime

_DT_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})")


def _dt(value):
    m = _DT_RE.match(value or "")
    return datetime(*(int(g) for g in m.groups())) if m else None


def summarize(jobs):
    """Group jobs by session label into per-block summaries (sorted by time).

    Each summary: label, day, count, start, end, span_min, avg_gap_min,
    longest_gap_min. Jobs without a session label or a timed date are ignored.
    """
    groups = {}
    for j in jobs:
        label = j.get("session")
        ts = _dt(j.get("date_applied"))
        if label and ts:
            groups.setdefault(label, []).append(ts)

    summaries = []
    for label, times in groups.items():
        times.sort()
        gaps = [int((b - a).total_seconds() // 60) for a, b in zip(times, times[1:])]
        summaries.append({
            "label": label,
            "day": times[0].strftime("%Y-%m-%d"),
            "count": len(times),
            "start": times[0].strftime("%H:%M"),
            "end": times[-1].strftime("%H:%M"),
            "span_min": int((times[-1] - times[0]).total_seconds() // 60),
            "avg_gap_min": round(sum(gaps) / len(gaps), 1) if gaps else 0,
            "longest_gap_min": max(gaps) if gaps else 0,
        })
    summaries.sort(key=lambda s: (s["day"], s["start"]))
    return summaries


def format_text(summaries):
    """Render summaries as compact aligned lines for the terminal."""
    if not summaries:
        return "No bracketed (START)/(END) sessions found."
    lines = ["Apply sessions (consistency / distraction):"]
    for s in summaries:
        pace = f"{s['avg_gap_min']}m avg" if s["count"] > 1 else "—"
        lines.append(
            f"  {s['label']:<16} {s['count']:>3} apps  {s['start']}–{s['end']} "
            f"({s['span_min']}m)  pace {pace}  longest gap {s['longest_gap_min']}m"
        )
    return "\n".join(lines)
