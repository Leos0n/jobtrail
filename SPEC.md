# JobTrail — Design Specification (Designer Handoff)

> Source of truth for any agent redesigning JobTrail's frontend. Pair this spec
> with a reference image (provided separately) and the two companion skills.
> This document defines **what JobTrail is and what must not break**; the image
> defines the **visual target**.

---

## 0. How designer agents should use this

Two skills accompany this spec; they map to two different surfaces:

| Skill | Applies to | Mode |
| --- | --- | --- |
| `redesign-existing-projects` | **The app UI** (the live tracker) | Audit the existing vanilla code, upgrade in place, do **not** rewrite or break functionality. |
| `image-to-code` | **The public landing page** (new marketing surface) + generating target mockups | Image-first: generate/analyze section images, then implement faithfully. |

**Workflow:**
1. Read this spec fully. Internalize §3 (hard constraints) — violating them breaks the app.
2. Treat the user-provided reference image as the primary art-direction anchor. Per `image-to-code`, generate complementary **section-by-section** images to fully resolve the design before writing code; do not crop one board.
3. For the **app UI**, apply `redesign-existing-projects` as targeted upgrades over the current code — restyle, don't re-architect.
4. Keep everything inside the brand world (§4) unless the reference image clearly dictates a new direction; if it does, change design tokens **centrally** (CSS `:root`), not per-element.
5. Verify against §9 Definition of Done before finishing.

**Do not ask unnecessary questions if a strong interpretation exists** (both skills say this). Where the image is silent, fall back to this spec, then to the current implementation.

---

## 1. Product overview

**JobTrail** is a zero-dependency, local-first **job application tracker**. A user
pastes an Indeed or LinkedIn job URL; JobTrail fetches and parses the posting into
structured data, then lets them track the whole application — status, dates,
resume, cover letter, notes — entirely on their own machine.

- **Audience:** active job seekers managing many applications at once.
- **Core loop:** paste link → auto-parsed job card → work the application in a
  detail panel → move it through a status pipeline → never lose it.
- **Positioning:** private, fast, owns-your-data. The opposite of a cloud SaaS
  that mines your job search. It runs at `http://127.0.0.1:8765`.
- **Tone:** calm, editorial, confident, warm. A focused desk, not a dashboard
  control room. No hype, no enterprise jargon.

---

## 2. The two surfaces

### A. Application UI (primary — exists today)
The working tracker. A two-column workspace: a filterable **job list** on the
left, a **detail/application panel** on the right, with a status pipeline and a
data-safety toolbar. This is a **tool**, not a marketing page — apply taste
(type, space, motion, states) without turning it into a landing page. No hero,
no stock photography, no testimonials inside the app.

### B. Public landing page (optional — to be created)
A standalone marketing page for the open-source release (GitHub / Pages),
`webapp/static/landing.html`, independent from the private app. This is the
correct canvas for `image-to-code`'s full machinery: hero, sections, GSAP. It
**may** load fonts/animation libraries from a CDN because it is public and
static. It must never import the private app's data or live behind the server's
auth-free local API.

---

## 3. Hard constraints (MUST NOT break)

### 3.1 Stack
- **Zero runtime dependencies for the app.** Vanilla HTML/CSS/JS only. No React,
  Vue, Tailwind, build step, bundler, or npm. The server is Python **stdlib**
  (`http.server`); storage is `sqlite3`.
- App assets live in `webapp/static/` (`index.html`, `styles.css`, `app.js`) and
  are served verbatim from disk. No transpilation.
- **Offline-capable:** any CDN font/asset must have a **system fallback** so the
  app still works with no internet. (Current: Cabinet Grotesk + Satoshi via
  Fontshare, falling back to system sans.)
- Honor `prefers-reduced-motion: reduce` — disable transforms/reveals there.
- The landing page (surface B) may relax the CDN rule; the app (surface A) may not
  add hard runtime deps.

### 3.2 The JS hook contract — restyle freely, **never rename/remove**
`app.js` binds to these. Markup and CSS around them can change; these
identifiers cannot. Adding new elements/classes is fine.

**Element IDs (in `index.html`):**
`add-form`, `add-url`, `add-btn`, `toast`, `filters`, `job-list`, `empty-list`,
`detail`, `detail-empty`, `detail-template`, `trash-btn`, `trash-count`,
`export-btn`, `import-file`, `backup-btn`, `backup-status`.

**`#detail-template` inner classes (cloned per job):**
`d-title`, `d-company`, `d-source`, `d-md`, `d-delete`, `d-meta`, `d-status`,
`d-applied`, `d-followup`, `d-salexp`, `d-contact`, `d-stars`, `d-notes`,
`desc-body`, and `.file-slot[data-kind="resume"|"cover_letter"]` each containing
a `.file-row`.

**Classes generated by JS (must keep these selectors working):**
`job-card`, `selected`, `reveal`/`in`, `company`, `card-foot`, `loc`,
`source-tag`, `pill` + one status modifier, `trashed`, `trash-actions`,
`file-name`, `link-btn`, `upload-label`, `star`/`on`, `chip`, `toast`/
`toast-action`/`err`, `btn-ghost`, `btn-danger`, `count`.

> If a redesign genuinely needs to restructure interaction (e.g. a board view),
> update `app.js` deliberately and keep all 30 tests green — do not silently break
> bindings.

### 3.3 Data model (design states with real shapes)
Each job object the UI receives has:
`id, source, url, job_key, title, company, location, remote, employment_type,
salary, date_posted, industry, description_md, status, date_applied,
follow_up_date, contact, notes, rating (0–5), salary_expectation, resume_name,
cover_letter_name, created_at, updated_at, deleted_at`.

**Status pipeline (exact values):** `saved → applied → interviewing → offer →
rejected → archived`. Every status needs a distinct, readable pill style.

**API (read-only summary, for context):** `GET /api/jobs`, `/api/trash`,
`/api/meta`, `/api/backups`, `/api/export`; `POST /api/jobs` (add by URL),
`/api/import`, `/api/backup`, `/api/jobs/{id}/file`, `/api/jobs/{id}/restore`;
`PATCH /api/jobs/{id}`; `DELETE /api/jobs/{id}[?purge=1]`. Designers don't change
these — but they explain every state the UI must render.

---

## 4. Brand & design system (current baseline)

Designers may evolve this toward the reference image, but keep it **coherent and
warm-editorial** unless the image dictates otherwise. Change tokens centrally.

- **Type:** Display = `Cabinet Grotesk` (headings, job titles, brand). Body =
  `Satoshi`. Never Inter. System-font fallback required. Consider
  `font-variant-numeric: tabular-nums` for dates/salary.
- **Color tokens (warm editorial):** paper `#FBF8F1`, surface `#FFFFFF`,
  surface-2 `#F4EFE5`, ink `#211C17`, muted `#6B635A`, faint `#9A9189`, hairline
  `#EAE3D6`, accent (brick) `#9E4636`, accent-hover `#85382B`, accent-tint
  `#F7E6E1`. **One** accent only. Tint shadows warm, never pure black.
- **Shape:** cards 14px, controls 10px, pills 999px. Vary radius by nesting.
- **Depth:** one tasteful layered shadow on hover/raised only — not flat shadows
  on everything.
- **Motion:** reveal-on-mount stagger (≤320ms), hover lift `translateY(-2px)` +
  accent edge, spring-ish `cubic-bezier(.2,.7,.2,1)`, 160–220ms. GPU props only
  (`transform`/`opacity`).

See [docs/FRONTEND_REDESIGN_PLAN.md](docs/FRONTEND_REDESIGN_PLAN.md) for the
rationale and the Phase plan already underway.

---

## 5. App UI — view-by-view spec (surface A)

For each view: **purpose**, key **content**, and **all states** to design.

### 5.1 Top bar — brand + add-by-URL
- **Purpose:** identity + the single primary action (paste a job link).
- **Content:** wordmark + mark; one-line value prop; URL input with an
  Indeed·LinkedIn affordance; primary **Add** button.
- **States:** idle; input focus; **loading** (fetching/parsing — show progress,
  not a bare spinner); error (invalid URL / fetch blocked → inline, not
  `alert()`); success.

### 5.2 Sub-bar — status pipeline + data-safety toolbar
- **Purpose:** filter by status; reach Trash, Export, Import, Back-up; show last-
  backup status.
- **Content:** segmented status filters with live counts (All + 6 statuses);
  right-aligned ghost actions; "Last backup …" line.
- **States:** active filter; hover; Trash active; backup-status empty vs present.

### 5.3 Job list — cards
- **Purpose:** scan and select applications.
- **Content per card:** title (display font), company, location, status pill,
  source tag, interest. Click → selects, drives detail panel.
- **States:** default; hover (lift + accent edge); **selected** (accent rail +
  tinted surface); reveal-on-mount; empty (first run) and empty-filter.

### 5.4 Detail panel — the application workspace
- **Purpose:** view + edit everything about one application; autosaves.
- **Content:** header (title, company, "Open original", "Markdown", "Delete");
  meta chips (location, remote, type, salary, posted, source); **Application**
  section (status select, date applied, follow-up, salary expectation, contact,
  1–5 interest stars); **Documents** (resume + cover letter: upload / download /
  remove); notes textarea; collapsible rendered-markdown description.
- **States:** empty (nothing selected); populated; field focus; star hover-
  preview; file empty vs attached; saving feedback.

### 5.5 Trash view
- **Purpose:** recover or permanently remove deleted jobs.
- **Content:** muted cards, "Trashed {when}", **Restore** and **Delete forever**.
- **States:** populated; empty ("Nothing in Trash"); confirm-before-purge.

### 5.6 Global: toasts
- Success/info + error variants; the delete flow shows an **Undo** action.
- No exclamation marks; no "Oops!"; active voice, direct copy.

---

## 6. Landing page — section spec (surface B, for `image-to-code`)

Build only if requested. Generate one large image **per section** (don't compress
into one board), analyze, then implement faithfully.

**Default section pack (4):** Hero → Features (the four pillars) → How-it-works /
proof → CTA + footer.

- **Hero (1–3 lines max):** product name + a short, plain promise. No pills, no
  fake stats, no stock-photo clutter. Wide H1 container so it never wraps to
  6 lines. Two CTAs max ("Get it on GitHub", "How it works"), perfect contrast.
- **The four pillars** (use as feature content): zero-dependency / local & private,
  Indeed + LinkedIn parsing, never-lose-your-data (trash + backups), markdown &
  export. Avoid a generic 3-equal-card row — use an asymmetric or bento rhythm.
- **Motion:** staggered float-up + one signature scroll moment. GSAP via CDN is
  acceptable here.
- **Assets:** if real screenshots aren't available, use framed product shots of
  the actual app UI; placeholder imagery only as a last resort, treated (not raw
  stock). Keep one coherent visual world with surface A.

---

## 7. Content & copy rules (both skills)

- **Banned AI clichés:** "Elevate, Seamless, Unleash, Next-Gen, Game-changer,
  Delve, Tapestry, Revolutionize, In the world of…". Write plain and specific.
- **Banned fake brands/data:** Acme, Nexus, NovaCore, "John Doe", round fake
  numbers. If sample data is needed, make it realistic and varied.
- Sentence case for headings (not Title Case). No exclamation marks in success.
- Error copy is direct and active: "Connection failed. Please try again."
- No meta-labels ("SECTION 01", "ABOUT US", pseudo-system tags).

---

## 8. Accessibility & quality bars

- Visible keyboard focus rings on every interactive element (not optional).
- Color contrast AA for text on fills; pill text uses the dark stop of its hue.
- Semantic HTML (`<nav> <main> <section> <ul>`), real `alt`/`aria-label`s.
- Inline form validation + error states; never `window.alert()`.
- Animate only `transform`/`opacity`; respect reduced-motion.
- Custom favicon + proper `<title>`/meta for the landing page.

---

## 9. Definition of Done (deliverables)

A redesign is complete when:
1. **(image-to-code)** Section reference image(s) were generated/analyzed and the
   implementation is visually faithful to them (no drift to a generic layout).
2. **(redesign)** The audit was applied as targeted upgrades over existing code;
   the stack was not migrated.
3. The **JS hook contract (§3.2) is intact** and `python3 -m unittest discover -s
   tests` still passes all 30 tests.
4. All view **states** in §5 are designed (empty / loading / error / hover /
   active / selected / focus), not just the happy path.
5. The app still runs offline (system-font fallback) and honors reduced-motion.
6. Changes are reviewable diffs on a branch; `main`/`v1.0-stable` stays the
   revert point.

---

## 10. The reference image

When provided, place it at `docs/reference/` (e.g. `docs/reference/target-01.png`)
and treat it as the visual anchor described in §0. Per `image-to-code`, generate
additional section/detail images as needed for faithful extraction; do not crop a
single board.

---

## 11. Pointers

- Run the app: `./bin/job-tracker` → `http://127.0.0.1:8765` (seed example jobs to
  see populated states).
- Current state: Phase 1 app redesign is live on branch `frontend-redesign`;
  `main` = `v1.0-stable` (immutable revert point).
- Rationale & phases: [docs/FRONTEND_REDESIGN_PLAN.md](docs/FRONTEND_REDESIGN_PLAN.md).
- Public repo: https://github.com/Leos0n/jobtrail
- **Revert anytime:** `git checkout v1.0-stable`.
