# JobTrail — Frontend Redesign Plan

Applying the **gpt-taste** design-engineering skill to JobTrail, adapted to the
project's hard constraint: **zero runtime dependencies, vanilla HTML/CSS/JS,
served by a Python-stdlib server.** No React, no Tailwind, no build step.

The skill is written for React/Tailwind/GSAP marketing pages. We split its use:

- **The app UI is a *tool*, not a landing page.** It gets the skill's *taste
  fundamentals* — premium type, generous spacing, real micro-motion, perfect
  contrast, grid discipline, anti-default creativity — implemented in plain CSS
  + tiny vanilla JS (IntersectionObserver), so the app stays dependency-free.
- **The public marketing page is where the skill applies literally** — full
  AIDA, hero, bento, GSAP. It is a separate static page for the GitHub release
  and may load GSAP + fonts from a CDN because it is public and non-private.

---

## 0. Mandatory pre-flight `<design_plan>` (skill §8)

### 0.1 Python RNG execution (deterministic, seed = Σ ord(brief) mod 9973 = 7199)
```
Landing Hero   : Editorial Split
Display Font   : Cabinet Grotesk   (skill bans Inter)
Components (3) : Feedback Carousel, Inline-Typography Images, Sticky Split Scroll
Motion (2)     : Card Stacking, Scroll-Pinning Split
```
These drive the **landing page** (Phase 3). The **app** uses a coherent system
derived from the same font/era, not the marketing layouts.

### 0.2 AIDA check (landing page)
Navigation (floating pill) → Attention (Editorial Split hero) → Interest
(gapless bento of features) → Desire (sticky split scroll + card stacking) →
Action (high-contrast CTA + footer). Present. ✔

### 0.3 Hero math verification (landing page)
H1 container `max-width: 64rem` (`max-w-5xl`-equivalent), font
`clamp(2.75rem, 5vw, 5rem)`, hard-capped at **2–3 lines**. No stamp icons, no
pill-tags under the hero, no raw stats in the hero. ✔

### 0.4 Bento density verification (landing + app board)
Grid uses `grid-auto-flow: dense` with interlocking `span`s; mathematically
zero empty cells (see Phase 3 grid map). ✔

### 0.5 Label sweep & button check
No "SECTION 01 / QUESTION 05 / ABOUT US" meta-labels anywhere. Buttons: accent
background → white text; light background → ink text. No invisible text. ✔

---

## 1. Design system (foundation — applies to the app)

### Typography
- **Display:** Cabinet Grotesk (headings, job titles, brand) — via Fontshare
  CDN, `font-display: swap`, **system fallback** so the app still works offline.
- **Body:** Satoshi (UI text) — Fontshare, with `-apple-system` fallback.
- **Scale:** display `clamp(2rem,4vw,3rem)`, h1 22, h2 18, h3 15.5, body 15,
  small 13, micro 11.5. Two weights only where possible (400/500), 600 for
  display emphasis.
- **Rule:** never wrap a heading to 6 lines; titles get width, not stacking.

### Color (elevated warm editorial — keeps JobTrail's identity)
| Token | Value | Use |
| --- | --- | --- |
| `--paper` | `#FBF8F1` | page background |
| `--surface` | `#FFFFFF` | raised cards/panels |
| `--surface-2` | `#F4EFE5` | insets, chips |
| `--ink` | `#211C17` | primary text |
| `--muted` | `#6B635A` | secondary text |
| `--faint` | `#9A9189` | hints, meta |
| `--hairline` | `#EAE3D6` | borders |
| `--accent` | `#9E4636` | brick — primary actions |
| `--accent-hover` | `#85382B` | hover |
| `--accent-tint` | `#F7E6E1` | selection wash, focus ring |

Status hues stay readable on light fills (slate / blue / amber / green / brick /
gray) — text uses the dark stop of each family, never pure black.

### Space & shape
- Spacing rhythm: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64.
- Radius: cards 14, controls 10, pills 999.
- Depth: one tasteful layered shadow for raised cards on hover only
  (`0 1px 2px`, `0 12px 28px -12px`) — no flat drop shadows everywhere.

### Motion (vanilla, dependency-free)
- **Reveal-on-mount:** job cards fade+rise with a 40ms stagger via
  IntersectionObserver adding `.in`.
- **Hover physics:** cards lift `translateY(-2px)` + accent left-edge + image/
  title shift; 160–220ms `cubic-bezier(.2,.7,.2,1)`.
- **Selection / status:** pill and panel cross-fade; star rating springs.
- **Toast:** slide-down + fade; Undo affordance.
- Respect `prefers-reduced-motion`: disable transforms/reveals.

---

## 2. The app, view by view (what each does + redesign)

### 2.1 Top bar — brand + add-by-URL  *(primary action)*
- **Does:** the command surface. Paste an Indeed/LinkedIn URL → fetch + parse +
  save. Shows brand wordmark and a one-line value prop.
- **Redesign:** Cabinet-Grotesk wordmark with a small brick mark; a wide,
  focused "Paste a job link…" field with a source affordance (Indeed · LinkedIn)
  and a confident accent **Add** button (white text). Loading state animates.

### 2.2 Sub-bar — status pipeline + data-safety toolbar
- **Does:** filter by status (All / Saved / Applied / Interviewing / Offer /
  Rejected / Archived) with live counts; data actions: Trash, Export backup,
  Import, Back up now, and "Last backup …" status.
- **Redesign:** pipeline as quiet segmented pills (active = brick); toolbar
  right-aligned with ghost buttons and a subtle backup-status line. No cheap
  uppercase labels.

### 2.3 Job list — cards  *(scan + select)*
- **Does:** one card per job: title, company, location, salary, status pill,
  source tag, interest rating. Click selects → detail panel.
- **Redesign:** title in Cabinet Grotesk; clear company/location hierarchy;
  status pill + source as restrained metadata; **hover lift + accent edge**;
  **reveal-on-mount stagger**; strong selected state (accent rail + surface-2).

### 2.4 Detail panel — the application workspace  *(track + edit)*
- **Does:** everything about one application. Header (title, company, "Open
  original", "Markdown", "Delete"); meta chips; tracker form (status, date
  applied, follow-up, salary expectation, contact, 1–5 interest stars); file
  attachments (resume + cover letter: upload / download / remove); notes;
  collapsible rendered-markdown description.
- **Redesign:** generous sectioning with hairline dividers; inputs unified to
  the new control style with accent focus rings; star rating with hover preview;
  attachment rows as tactile chips; description typeset for reading.

### 2.5 Trash view  *(recover / purge)*
- **Does:** lists soft-deleted jobs; Restore or Delete-forever (backup taken
  first). Reached via the Trash toolbar button.
- **Redesign:** muted cards, "Trashed {when}", two clear actions; calm empty
  state ("Nothing in Trash").

### 2.6 Empty states
- First run (no jobs): a warm prompt to paste the first link.
- Empty filter: "No jobs in {status} yet."
- Empty trash.

### 2.7 Toasts  *(feedback + undo)*
- Success/info/error variants; the delete flow surfaces **Undo** (restore).

---

## 3. Optional phases (documented; gated on the core landing first)

### Phase 2 — Board (Kanban) view *(in-app, dependency-free)*
A toggle between **List** and **Board**. Board = columns per status, cards move
via a status menu (no drag dependency). Uses `grid-auto-flow: dense` so columns
never show dead cells. This is the app's "bento" moment.

### Phase 3 — Public landing page *(skill applied literally)*
A standalone `webapp/static/landing.html` for the GitHub release / Pages:
- **Editorial Split hero** (RNG): headline left in Cabinet Grotesk, product
  shot right, massive negative space; two CTAs ("Get it on GitHub", "How it
  works"); `max-w` capped to 2–3 lines.
- **Gapless bento** of the four pillars: zero-dependency, Indeed+LinkedIn,
  never-lose-data, local & private.
- **Sticky Split Scroll** + **Card Stacking** for the "how it works" steps.
- **Feedback Carousel** + **Inline-Typography Images** for texture.
- GSAP (+ ScrollTrigger) and fonts via CDN — acceptable here because the page is
  public and static, never the private app.

---

## 4. Build order & safety

1. **Stable tagged** `v1.0-stable`, pushed to `origin/main` (public) — revert
   point. Personal data in the private repo only.
2. Redesign on branch **`frontend-redesign`**; `main` stays stable.
3. Implement **Phase 1 (app UI)** — the explicit ask — preserving every JS hook
   (ids/classes) so functionality is untouched; only structure/CSS/motion change.
4. Verify: server serves new assets, 30 tests still green, `prefers-reduced-
   motion` honored.
5. Phases 2–3 are follow-ups, each its own branch/commit.

**Revert at any time:** `git checkout v1.0-stable` (or `git checkout main`).
