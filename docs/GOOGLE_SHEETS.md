# Connect a Google Sheet to JobTrail

JobTrail can read a Google Sheet of job applications and import every row —
**all past entries and any you add later** — into your local JobTrail.

## Why this is safe to open-source

There is **no shared server and no shared secret**. Every user runs JobTrail on
their own machine with their own database and their own Google credentials, so
**two people's data can never overlap — it's isolated by construction.** The
repo ships zero Google secrets. The integration is read-only (`spreadsheets.
readonly` scope) and one-way (Sheets → JobTrail). It uses only the Python
standard library — no `pip install`, no Google client libraries.

## One-time setup (~5 minutes)

You bring your own free Google OAuth client. This is the standard pattern used
by tools like rclone and gspread.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and
   create a new project (free).
2. **APIs & Services → Library →** search "Google Sheets API" → **Enable**.
3. **APIs & Services → OAuth consent screen:** choose **External**, fill in an
   app name and your email, and **add your own Google account as a Test user**.
   (In "Testing" mode no Google review is needed — it just works for you.)
4. **APIs & Services → Credentials → Create credentials → OAuth client ID →**
   Application type **Desktop app** → Create → **Download JSON**.
5. Save that file as `data/google/credentials.json` in your JobTrail folder.
   (`data/google/` is git-ignored everywhere — it never gets committed.)

## Connect and sync

From the JobTrail directory:

```bash
# 1. Authorize (opens your browser; consent once)
./bin/jobtrail-google connect

# 2. See your sheet's tab names
./bin/jobtrail-google tabs --sheet "https://docs.google.com/spreadsheets/d/<ID>/edit"

# 3. Import the tabs that hold applications (skip chart/summary tabs).
#    Preview first — writes nothing:
./bin/jobtrail-google sync --sheet "<url>" --tabs "Applications,Older applications" --status applied --dry-run

#    Then for real:
./bin/jobtrail-google sync --sheet "<url>" --tabs "Applications,Older applications" --status applied

# Later — capture new rows (uses your saved sheet + tabs):
./bin/jobtrail-google sync

# Check connection + last sync:
./bin/jobtrail-google status
```

- **Pick only the job tabs.** If your spreadsheet has data/chart tabs, leave
  them out of `--tabs`; only tabs with job rows (company/role/date columns) are
  imported. (Even if you include a chart tab, rows with no company/title/url are
  skipped automatically.)
- **Columns are auto-mapped** (Company, Role/Title, Link, Status, Date Applied,
  Salary, Location, Notes, …) and free-text statuses are normalized into
  JobTrail's pipeline. `--status applied` sets the status for rows whose status
  cell is blank.
- **Layouts handled automatically:** a header-row table, a date-grouped layout
  (a "June 22nd, 2026" header then one job per row), or a **headerless** table
  read by column position — `A` company, `B` job/title, `C` location, `D` url,
  `E` date / time submitted. "Time submitted" timestamps (e.g. `6/22/2026 9:05
  AM`) are accepted and reduced to the application date.
- **Idempotent:** re-running only adds new rows; it never duplicates or
  overwrites edits you've made inside JobTrail.

## Automatic capture

While JobTrail is running, it **auto-syncs the configured sheet every 15
minutes** in the background (only once you've connected — otherwise it does
nothing). You can also trigger a sync on demand:

```bash
curl -X POST http://127.0.0.1:8765/api/google/sync     # or the in-app action
```

For capture even when the app isn't running, schedule the CLI, e.g. hourly:

```cron
0 * * * * cd /path/to/Indeed-CLI && ./bin/jobtrail-google sync
```

## Troubleshooting wrong counts or missing links

- **Counts look doubled / off (over- or under-counting per day).** Older sync
  versions could leave rows that newer syncs don't recognize as the same job, so
  they pile up (sync only ever *adds*). Do a one-time clean re-import — it backs
  up your database first, removes previously sheet-imported rows, and re-imports
  fresh:

  ```bash
  ./bin/jobtrail-google sync --reset
  ```

  Only `google-sheet` rows are cleared; jobs you added by pasting an Indeed /
  LinkedIn link are untouched.

  If counts are *still* wrong after `--reset` (some stale rows predate source
  tagging and escape the source-scoped delete), do a full reset — clears **all**
  jobs, then re-imports from the sheet:

  ```bash
  ./bin/jobtrail-google sync --wipe
  ```

  Both back up your database to `data/backups` first, so a wipe is recoverable.

- **"Apply Here" links weren't imported.** Cells that show label text but link
  out (a hyperlink, an `=HYPERLINK()` formula, or an inserted rich-text link) are
  now read as the job's URL. Re-run `sync --reset` to backfill links on rows that
  imported before this was supported.

- **See exactly what the sync reads** (read-only; writes nothing):

  ```bash
  ./bin/jobtrail-sheet-debug
  ```

  It prints per-tab parsed jobs, recovered links, and flags any day where the
  database count disagrees with the sheet (the signal that `--reset` is needed).

## What's stored where

| File | Contents | Committed? |
| --- | --- | --- |
| `data/google/credentials.json` | your OAuth client | **never** (git-ignored) |
| `data/google/token.json` | your refresh token (user-only perms) | **never** |
| `data/google/config.json` | sheet id, tab names, last sync | **never** |

Revoke access anytime at <https://myaccount.google.com/permissions>.

## One-way, by design

JobTrail treats the sheet as a **source**: it reads new rows in, but never
writes back. Once imported, JobTrail is the source of truth and your edits there
always win. (Two-way sync — writing JobTrail changes back to the sheet — is a
larger feature and intentionally out of scope for now.)
