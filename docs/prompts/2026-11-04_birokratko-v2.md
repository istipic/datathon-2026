# TASK: Birokratko v2 – Neo-Brutalist redesign, threshold e-mail alerts, better matching, new features

You are working in the monorepo `C:\ajmobree\projekt1\datathon-2026` (Datathon Portala otvorenih podataka 2026,
deadline 9 Nov 2026). The app to change is **Birokratko** (formerly NabavaRadar): for a company (OIB) it ranks open
public tenders (TED notices for Croatia) by fit to the company's registered activities (NKD), and for a public buyer
it estimates the supplier market before a procurement.

Read these first and follow them strictly:

- `/CLAUDE.md` and `docs/FOUNDATION.md` (working rules, conventions, report format)
- `apps/nabavaradar/docs/README.md`, `apps/nabavaradar/docs/validation.md`, `docs/adr/0006-nabavaradar-data-decisions.md`
- the code: `apps/nabavaradar/api/src/nabavaradar_api/` (`fit.py`, `match.py`, `subscriptions.py`, `api.py`, `cli.py`,
  `db.py`, `evaluation.py`) and `apps/nabavaradar/web/src/` (`App.tsx`, `index.css`, `pages/`, `components/`)

Technical identifiers stay **`nabavaradar`** (folder, package `nabavaradar_api`, CLI, database, env vars
`NABAVARADAR_*`). Only the visible brand is "Birokratko". UI text is Croatian; code, comments and commits are English.

---

## 0. Ground rules (non-negotiable)

1. **Never invent data.** No fake brand logos, customers, testimonials, revenue charts, star ratings or usage numbers.
   Wherever the design reference below asks for marketing filler, replace it with real data from the API or with neutral,
   factual copy (see section 1.3). Every number on screen must come from the API.
2. Inspect before changing; small steps; Conventional Commits ending with
   `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
3. Test fixtures are **real recorded API responses** (record them from the running API, byte-exact with `curl`, never
   with PowerShell `Invoke-WebRequest`, which breaks UTF-8). Fixtures live in `__fixtures__/` and must not be
   reformatted (prettier ignores `**/__fixtures__/**` only when run from the repo root).
4. New dependencies (including font files) need an ADR in `docs/adr/` (next free number).
5. Secrets only in the gitignored root `.env`. The `.env` holds Sudreg **test-portal** credentials; the company data is
   a test snapshot (2024-06-16) and the UI must keep saying so.
6. Accessibility: WCAG 2.1 AA, visible focus, keyboard reachable, `prefers-reduced-motion` respected, Lighthouse
   accessibility ≥ 95 on `/`, `/tvrtka/:oib`, `/narucitelj` and the new alert pages.
7. Privacy: store only what a feature needs (e-mail, OIB or free-text query, alert preferences). No tracking of people.

---

## 1. Redesign: Neo-Brutalist look

Replace the current "službeni dosje" look (ink strip, burgundy stamp) with the Neo-Brutalist system below. It must stay
clearly different from the two sibling apps: **Blizu** (teal, rounded, top bar, IBM Plex) and **Otporko** (warm paper,
navy left rail, serif headings).

### 1.1 Design tokens

| Token             | Value     | Use                                                |
| ----------------- | --------- | -------------------------------------------------- |
| Primary           | `#ffe17c` | hero, feature band, final CTA, highlights          |
| Charcoal          | `#171e19` | dark sections, footer, primary buttons             |
| Sage              | `#b7c6c2` | accents, icon boxes, secondary panels              |
| Dark gray         | `#272727` | connector lines, dark cards, social squares        |
| UI                | `#ffffff` | cards, inputs                                      |
| Text              | `#000000` | body text on light backgrounds                     |
| Star/alert yellow | `#ffbc2e` | only for small status marks (not ratings, see 1.3) |

- Override the `@dt/ui` tokens in `apps/nabavaradar/web/src/index.css` (`--brand-600/700`, `--accent-600`, neutrals,
  radii, shadows). Check contrast for every pair you use: black on `#ffe17c` and on `#b7c6c2` is fine; white on
  `#171e19` is fine; **never** put white text on yellow or sage.
- Borders: **2px solid #000** on every card, button, input and section divider. No exceptions for interactive elements.
- Shadows: hard, zero blur: `4px 4px 0 0 #000` (standard), `8px 8px 0 0 #000` (large containers), `12px 12px 0 0 #000`
  (hero mockup). **No gradients, no soft shadows.**
- Radius: buttons ≤ 12px (`0.75rem`); cards may use `1.5rem`; keep it geometric.
- Dot pattern on primary yellow backgrounds: 32×32px radial dots at 10% opacity (CSS `radial-gradient`, no image).
- Typography: headings **Cabinet Grotesk** (700–800, `letter-spacing: -0.03em`), body **Satoshi** (500).
  Both are Fontshare fonts. The production CSP in the root `Caddyfile` is `default-src 'self'`, so **self-host** the
  WOFF2 files (latin + latin-ext, check that č ć š ž đ render) under `apps/nabavaradar/web/public/fonts/` with
  `font-display: swap`. Verify and record the licence (ITF Free Font License) in the ADR, and keep a system fallback
  stack. Do not load fonts from a CDN.
- Numbers stay tabular (`font-variant-numeric: tabular-nums`).

### 1.2 Components

- **Push button:** black background, white text, 2px black border, radius 0.75rem, padding `1rem 2rem`, shadow
  `8px 8px 0 0 #000`, `transition: all .2s cubic-bezier(0.175, 0.885, 0.32, 1.275)`. On hover/active:
  `transform: translate(4px, 4px)` and shadow `4px 4px 0 0 #000` (it "fills" its shadow). Secondary: white background,
  black text, 4px shadow. Disabled: no movement, gray, `cursor: not-allowed`. Under `prefers-reduced-motion` no
  transform, only a colour change.
- **Card:** white, 2px border, 4px shadow, radius 1.5rem. Tender card keeps its information (fit %, title, buyer,
  value, deadline, competition chip, "Zašto?" explanation), restyled. The fit bar becomes a thick black-bordered bar
  with a yellow fill and the percentage in Cabinet Grotesk.
- **Pill badge:** white, 2px border, fully rounded, small bold Satoshi.
- **Browser mockup:** white, 2px border, radius 1rem, 12px hard shadow; black header bar with three dots
  (`#ff5f57`, `#febc2e`, `#28c840`). Its content shows a **real tender card preview** (see 1.3), not a fake dashboard.
- **Icon box:** 64×64 sage square with a 2px border that turns `#ffe17c` on hover.
- Forms: 2px black border inputs, 4px shadow on focus plus a visible focus ring (`outline: 3px solid #000;
outline-offset: 2px`). Keep the OIB inline validation (check digit) and its status message.

### 1.3 Page structure (home `/`)

Adapt the reference landing layout to the product. Sections, top to bottom:

1. **Navigation** (sticky, h-20, `#ffe17c`, bottom border 2px). Left: logo = 40×40 black square with a yellow "B"
   (or a stamp glyph) + "Birokratko". Centre: links (bold Satoshi): Za tvrtke, Za naručitelje, Upozorenja, Izvori
   podataka. Right: primary button **"Pošalji mi relevantne natječaje"** (opens the alert flow, section 2). Mobile:
   collapsible menu, all links reachable by keyboard.
2. **Hero** (two columns on yellow with dot pattern). Left: pill badge with a real fact from `/api/v1/status` (for
   example the number of open notices and the data date), heading in Cabinet Grotesk 6xl–8xl
   "Natječaji koji odgovaraju tvojoj djelatnosti" with **one** keyword drawn as outline text
   (`-webkit-text-stroke: 2px #000; color: transparent`, keep it readable and keep the real text in the DOM), the OIB
   form as the primary action, and a secondary white button "Javni naručitelj? Provjerite tržište". Right: browser
   mockup showing one real tender card rendered from the recorded fixture, labelled "Primjer stvarnog natječaja".
3. **Live data marquee** (charcoal bar). Instead of fake brand names, scroll **real** items: names of buyers with open
   notices, or CPV areas with counts, from an API endpoint (add a small one if needed, e.g. `GET /api/v1/highlights`).
   Sage text at 50% opacity, slow linear infinite animation; **paused under `prefers-reduced-motion`** and on hover;
   duplicated content `aria-hidden`, with one accessible static list for screen readers.
4. **Problem vs rješenje** (white). Card A (problem, `#f4f4f5`, dashed gray border, 70% opacity): factual pains
   (hundreds of notices, CPV codes do not match NKD, deadlines missed). Card B (solution, yellow, 8px shadow): what
   Birokratko does. Custom check/x icons.
5. **Feature grid** (yellow band, 3 columns of white cards with icon boxes): ranked tenders with explanation,
   competition history, alerts by threshold, deadline calendar export, supplier market for buyers, saved tenders.
   Only list features that exist after this task.
6. **Kako radi** (charcoal, 3 steps with 96px circles and 4px sage/yellow/white rings connected by a `#272727` line):
   1 Upiši OIB, 2 Pogledaj rangirane natječaje i zašto, 3 Uključi upozorenja.
7. **Za koga** (bento, 3 cards: sage, yellow with 8px shadow, `#272727` with white text), each with a white pill:
   Tvrtke, Javni naručitelji, Savjetnici za nabavu. Short factual copy, **no invented quotes or personas with names**.
8. **Česta pitanja** (sage background) instead of testimonials: 3 white cards with the asymmetric corners from the
   reference (top-right and bottom-left 1.5rem, other corners 2px). Answer real questions: where the data comes from
   (TED, Sudski registar test snapshot), how the fit score works in one paragraph, how to unsubscribe. No star ratings.
9. **Final CTA** (yellow, centred big heading) with the alert button, then **footer** (charcoal, 4 columns: proizvod,
   podaci i izvori, pravno/privatnost, kontakt; licence EUPL-1.2). Square icon links (40×40 `#272727`, light border,
   yellow/black on hover) only for links that really exist.

Restyle the other pages (`/tvrtka/:oib`, `/natjecaj/:pubNo`, `/narucitelj`, `/izvori`, subscription confirm/unsubscribe,
not found) with the same system. The company page keeps its filters, list, empty state and "snimka od" data note.

### 1.4 Remove "Metodologija"

Remove the page, its route and nav item, and the link on the home page. `/metodologija` redirects to `/` (or `/izvori`
if you keep the validation numbers there). Keep transparency elsewhere: the "Zašto?" panel on every tender card, a
one-paragraph "Kako računamo prilagodbu" in the FAQ, and the validation numbers (from `GET /api/v1/validation`) moved
to `/izvori` under a heading "Provjera kvalitete". Update the vitest and Playwright tests that referred to the page.

---

## 2. Feature: "Pošalji mi relevantne natječaje" (threshold e-mail alerts)

Today there is a weekly digest (`subscriptions.py`, table `subscription`, double opt-in, cron Monday 07:00, top 10 new
matches). Extend it into threshold alerts.

**User flow**

1. Button "Pošalji mi relevantne natječaje" (nav, hero, company page, final CTA) opens a dialog (accessible modal:
   focus trap, Esc closes, labelled) or a page `/upozorenja`.
2. Fields: e-mail; OIB (prefilled on the company page) **or** a free-text description of what the company does;
   **threshold** "Javi mi kad prilagodba bude barem X %" (slider + number, 50–95, default 75); optional filters: counties
   (multi-select), minimum estimated value (EUR), CPV areas; frequency: "odmah (jednom dnevno)" or "tjedni pregled".
   Show a live preview: "S ovim postavkama danas bi dobili N natječaja" (call the match endpoint with the same filters).
3. Explicit consent checkbox with the exact consent text stored with the subscription. Double opt-in e-mail (existing
   mechanism). Nothing is sent before confirmation.
4. Every e-mail has a one-click unsubscribe link and a "Promijeni postavke" link to `/pretplata/postavke?token=…`
   (HMAC token like the existing unsubscribe token) where the threshold and filters can be changed or alerts paused.

**Backend**

- Alembic migration (new revision, do not edit applied ones): add to `subscription` `min_fit` (float, 0.5–0.95),
  `min_value_eur` (nullable), `counties` (array/JSON), `cpv_divisions` (array/JSON), `frequency`
  (`daily`|`weekly`), `paused` (bool). New table `alert_sent (subscription_id, pub_no, fit, sent_at)` with a unique
  constraint on `(subscription_id, pub_no)`: **a notice is sent to a subscriber at most once**.
- "Crosses the threshold": a notice qualifies when its fit for the subscriber's profile is `>= min_fit`, it passes the
  filters, its deadline has not passed, and it was not sent before. Because the fit has a time component, re-check
  daily; a notice whose fit rises above the threshold later (for example after a corrected CPV in an updated notice)
  is sent then.
- CLI `nabavaradar alerts send [--dry-run]`: one e-mail per subscriber per run that lists all qualifying notices
  (cap 20, sorted by fit), with fit %, deadline, buyer, value and the "Zašto?" reasons. Plain-text and HTML templates in
  `templates/`. Add the cron line to `apps/nabavaradar/deploy/crontab` at 07:00 daily (after `derive` at 06:30). The
  weekly digest keeps working for `frequency = weekly`.
- API: extend `POST /api/v1/subscriptions` with the new fields (validated with Pydantic: threshold range, counties
  from `config/counties.yaml`, value ≥ 0), add `GET/PUT /api/v1/subscriptions/settings?token=` and keep
  `DELETE` for unsubscribe. Rate-limit subscription creation per IP and per e-mail.
- Tests (pytest, DB tests via `TEST_DATABASE_URL=…/postgres`): threshold boundary (exactly at `min_fit` is sent),
  filters, dedupe across two runs, unconfirmed and paused subscriptions get nothing, unsubscribe stops alerts, token
  tampering is rejected, dry-run sends nothing. Playwright: the alert flow end to end with Mailpit
  (`http://127.0.0.1:8025`): subscribe → confirmation mail → confirm → run `alerts send` → alert mail arrives with the
  expected notice.

---

## 3. Improve the tender selection logic

Current fit (`fit.py`): `Fit = 0.55·S + 0.25·C + 0.10·G + 0.10·T` (S = rescaled best cosine between a company
activity and the notice, C = CPV division in the company's top-3/top-10 crosswalk divisions, G = geography, T = time
to deadline). Known weaknesses visible in the UI: several lots of the same procedure fill the top
(for example three "OPERATIVNI LEASING VOZILA…" or three "Autobus" cards), and the main activity counts the same as
side activities.

Improve it **measurably**:

1. **Baseline first:** run the existing evaluation (`nabavaradar eval`, see `evaluation.py` and
   `apps/nabavaradar/docs/validation.md`) and record the current metrics.
2. **Group lots / near-duplicates:** collapse notices that share the procedure (same buyer + same base title or the
   same TED procedure identifier if the data has it) into one card with "+N grupa" that expands. Rank by the best lot.
3. **Main activity weighting:** S uses the main NKD activity at full weight and secondary activities with a discount
   (for example 0.85), configurable.
4. **Finer CPV match:** besides the division (2 digits), reward a match at group/class level (3–4 digits) where the
   crosswalk supports it.
5. **Hard filters before scoring:** expired notices (already), notice types that are not open for bids, and the user's
   own filters.
6. **"Ne zanima me" feedback:** a per-card action that hides the notice and down-ranks notices of the same CPV class
   for this browser (localStorage), and for alert subscribers stores the exclusion server-side.
7. Move all weights and discounts to a config file (`config/`), not code. Keep the four components visible in the
   "Zašto?" panel and add the new signals there in plain Croatian.
8. **Accept a change only if the evaluation does not get worse**; put before/after numbers in `validation.md` and in the
   final report. If a change hurts the metric, revert it and say so.

---

## 4. More features (professional, real data only)

Implement in this order and stop adding features once the time budget is used; finished and tested beats many:

1. **Sort and search** on the company page: by fit, deadline, value; text search within results.
2. **Saved tenders ("Prati")**: star a notice, list on `/spremljeno` (localStorage; no account).
3. **Deadline to calendar**: download an `.ics` file per notice (rok za ponude, link to the TED notice).
4. **Deadline badges**: "Rok za 3 dana" in `#ffbc2e` with text, never colour alone.
5. **Export**: CSV of the current result list (columns as shown, UTF-8 with BOM so Excel shows č ć š ž đ).
6. **Share link**: the company page URL keeps filters and sort in the query string.

---

## 5. The floating euro banknote (small, playful, professional)

A small stylised **banknote** (Croatia uses the euro, so show a "€" bill; use a "$" only if the product owner asks)
floats slowly across the screen.

- Size about 72×36px, drawn in SVG with the design tokens (yellow bill, 2px black border, hard 4px shadow).
- Motion: slow drifting path across the viewport (CSS keyframes or `requestAnimationFrame`), never over the nav or
  primary buttons for long, `pointer-events` only on the bill itself, z-index below dialogs.
- Click/Enter/Space: short animation (flip + "+1 €" pop that rises and fades, about 600 ms), then the bill leaves and
  a new one appears after 20–40 s.
- Counter: a small pill in the footer or the nav corner, "Ulovljeno: 3 €", stored in `localStorage` (wrap every access
  in try/catch). Not sent to the server.
- It is a `<button>` with `aria-label="Uhvati novčanicu"`; the counter is announced politely (`aria-live="polite"`).
- **`prefers-reduced-motion: reduce`**: no drifting; the bill sits still in a corner and the click shows only the
  counter change. A visible toggle "Sakrij novčanicu" hides it (remembered in localStorage).
- Not shown on the subscription confirm/unsubscribe pages, in print, or while a dialog is open.
- Tests: vitest for the counter logic and the reduced-motion branch; Playwright clicks the bill and sees the counter
  increase.

---

## 6. How to run and verify

- Toolchain: Node 20 portable in `C:\Users\ivann\.dt-tools\node\node-v20.20.2-win-x64` (prepend to PATH), `uv` for
  Python, Docker Desktop for PostgreSQL and Mailpit (`docker compose up -d --wait`). Use `127.0.0.1`, never `localhost`.
- Dev API: `apps/nabavaradar/deploy/run_dev_api.ps1` (port 8030, database `nabavaradar`). Dev web:
  `pnpm dev --host 127.0.0.1 --port 5174` in `apps/nabavaradar/web` with `NABAVARADAR_API_URL=http://127.0.0.1:8030`.
- Tests: `TEST_DATABASE_URL=<root .env DATABASE_URL with /postgres> uv run pytest apps/nabavaradar/api`;
  `pnpm exec vitest run`, `pnpm exec tsc --noEmit`, `pnpm exec eslint . --max-warnings 0` in the web folder;
  `NABAVARADAR_API_URL=http://127.0.0.1:8030 pnpm exec playwright test`; from the repo root `uv run ruff check .`,
  `uv run ruff format --check .`, `pnpm exec prettier --check .`; `gitleaks detect --no-git --source apps/nabavaradar`.
- Lighthouse: `pnpm dlx lighthouse@12.8.2 <url> --only-categories=accessibility` with
  `CHROME_PATH="C:/Program Files/Google/Chrome/Application/chrome.exe"`; save the JSON under
  `apps/nabavaradar/data/evidence/` with the date.
- Take before/after screenshots (Playwright, 1360 px and 390 px wide) of `/`, `/tvrtka/45050126417`, `/narucitelj`
  and the alert flow, and look at them before you call the design done. OIB 45050126417 (KONČAR) is the documented
  test company.

## 7. Definition of done

- The new look is applied to every page; no gradients, no soft shadows, 2px borders everywhere, fonts self-hosted.
- Metodologija is gone; transparency kept in "Zašto?", FAQ and `/izvori`.
- Threshold alerts work end to end with double opt-in, dedupe, settings and unsubscribe, tested with Mailpit.
- Matching changes are measured; before/after numbers documented; no regression.
- Features from section 4 that you built are tested; the banknote works with keyboard, reduced motion and the toggle.
- All test suites, linters and Lighthouse (≥ 95) pass; docs (`apps/nabavaradar/docs/README.md`, `validation.md`),
  ADR(s) and `.env.example` updated; small Conventional Commits.
- Final REPORT in the format from CLAUDE.md: Implemented / Verified (exact commands and results) / Not done /
  Fallbacks / Known issues.
