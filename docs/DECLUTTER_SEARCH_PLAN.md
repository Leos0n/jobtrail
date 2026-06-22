# Declutter + Search

Goal: keep the interface calm and scannable as the application count grows, and
make any single job findable without Ctrl+F. Branch: `declutter-and-search`.
All client-side (no backend changes); the app already loads every job.

## 1. Add Job page — dashboard, not a feed
- **Stats summary** strip above the list: Total · This week · Interviewing ·
  Offers. Gives an at-a-glance sense of the search.
- **Recently added** is **collapsible** (chevron toggle, state remembered in
  `localStorage`), shows a count, and is capped tight (6 rows). Collapsed by
  preference so the page is just "paste + stats".

## 2. Calendar page — structured, less scroll
- **Month summary** at the top of the Activity pane (applied / interviewing /
  offer counts for the viewed month).
- **Collapsible day groups**: each day is a header row `Weekday, Mon D · N`;
  the most recent day is expanded, the rest collapse to one line each and open
  on tap. A month with 100+ applications becomes a short, scannable list.
- Grid keeps the per-cell `+N more` cap already in place.

## 3. Search — find any job fast
- A **magnifier button** in the top bar, plus shortcuts **`/`** and **`⌘K`**.
- Opens a **command-palette overlay**: a single input with **live results**
  matching company, role/title, location, status, notes, and source.
- Results are keyboard-navigable (↑/↓, Enter) and clicking one opens the job's
  detail drawer. **Esc** closes.
- **Ctrl/Cmd+F is never intercepted** — the browser's native find still works,
  exactly as the user asked.

## Acceptance
- Adding many jobs never makes the Add or Calendar pages grow unboundedly.
- A specific job is reachable in ~2 keystrokes (`/` + type).
- No backend changes; all existing tests still pass; native find untouched.
