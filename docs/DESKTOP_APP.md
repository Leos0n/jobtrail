# Run JobTrail as a desktop app

JobTrail is a local web app, but you can give it a real app icon so you launch
it like any other program — no terminal required. Clicking the icon starts the
local server and opens JobTrail in your browser.

## Install

From the repo folder:

```bash
python3 install-desktop.py
```

That detects your OS and creates a native launcher:

| OS      | What it creates                                            |
|---------|------------------------------------------------------------|
| Linux   | a `.desktop` entry in your app menu **and** on your Desktop |
| macOS   | `~/Applications/JobTrail.app` (+ a Desktop alias)          |
| Windows | a `JobTrail` shortcut on your Desktop                      |

Then just double-click **JobTrail**.

- **Linux:** the first time you double-click the Desktop icon, your file
  manager may ask you to "Allow Launching" / trust it — that's normal for
  `.desktop` files. (The installer already marks it trusted via `gio` when
  available.)
- **macOS:** if Gatekeeper blocks the first launch, right-click the app →
  **Open** → **Open**.

To remove it:

```bash
python3 install-desktop.py --uninstall
```

## How it works

- `bin/jobtrail-app` is the entry point. It starts the server if it isn't
  already running, then opens `http://127.0.0.1:8765`. If JobTrail is already
  running it just opens a new browser tab instead of starting a second copy.
- The launcher points at **this checkout**, so it always uses the same code and
  the same data you already have.
- Icons are generated locally from `assets/icon.svg` by `assets/icongen.py`
  (pure standard library — no Pillow, no ImageMagick). They're written to
  `assets/` and are git-ignored, so nothing binary is committed.

## Your data stays private

This matters when open-sourcing the code:

- All of your data lives in the git-ignored `data/` directory — the SQLite
  database (`data/jobs.db`), uploaded resumes/cover letters
  (`data/files/...`), and your Google credentials/token
  (`data/google/...`). The desktop launcher reads and writes exactly that
  directory, so launching from the icon uses **all of your existing data**.
- `data/` (and `private/`, `*.db`, and the generated icons) are listed in
  `.gitignore`, so `git` never tracks them. Publishing or pushing the repo
  leaks none of your jobs, files, or API keys.
- The project itself ships **zero secrets**: the Google Sheets integration uses
  a bring-your-own-credentials model (see `docs/GOOGLE_SHEETS.md`). Your OAuth
  client and token are yours alone and only ever exist under `data/google/`.

If you ever want to double-check before publishing:

```bash
git status --ignored        # data/ and assets/icon*.png should show as ignored
git ls-files | grep -Ei 'data/|\.db|credential|token|secret'   # should print nothing
```
