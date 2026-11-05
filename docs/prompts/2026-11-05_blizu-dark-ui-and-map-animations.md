# TASK: Blizu v2 — "Night Atlas": a dark, cinematic, data-honest redesign with live map choreography

**Repo:** `C:\ajmobree\projekt1\datathon-2026` · **App:** `apps/blizu` (API `blizu_api`, web `blizu-web`) ·
**Deadline:** 9 Nov 2026 (you have about 1.5 working days) · **UI language:** Croatian · **Code/commits:** English

Blizu answers "Što ti je blizu?": for any address in Grad Zagreb it shows the walking minutes to 9 public services
for 4 personas (opće 1,33 m/s, starija 0,90, roditelj 1,10, kolica 0,90 on the wheelchair graph), and a planner
shows where unmet need is largest and where 1–5 new facilities help most. All of that already works and is tested.
Your job is to make it look and move like a flagship product **without breaking a single working feature and without
showing one invented number.**

---

## 0. How to work (read this twice)

1. **Read before you touch:** `/CLAUDE.md`, `docs/FOUNDATION.md`, `apps/blizu/docs/README.md`,
   `docs/adr/0005-*.md`, then `apps/blizu/web/src/` (all of `pages/`, `components/`, `lib/`, `index.css`, `App.tsx`),
   `packages/ui/src/components/MapView.tsx` (shared by all three apps: changes must be backward compatible) and
   `apps/blizu/api/src/blizu_api/` (`api.py`, `service.py`, `planner.py`, `store.py`, `ingest/graph.py`,
   `ingest/access.py`, `config/scoring.yaml`). Write a 10-line plan of the files you will change before Phase 1.
2. **Phases with exit gates.** Do the phases in order. A phase ends only when its gate is green, then commit
   (Conventional Commits, trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`). If you are behind,
   cut from the **cut list** (section 9) — never skip a gate.
3. **Data honesty:** every minute, count, route, area and column height comes from the API or the real walking graph.
   Decorative motion carries no data and is commented `// decorative`. If a number would need a guess, label it
   "procjena" in the UI or leave it out.
4. **Fixtures are real.** Record API responses with `curl` (byte-exact, never PowerShell `Invoke-WebRequest`).
   Run prettier only from the repo root (it ignores `**/__fixtures__/**` and `**/fixtures/**`).
5. **Dependencies:** MapLibre GL is the only map engine. No deck.gl, three.js, framer-motion, GSAP, lottie. The only
   allowed new package is a self-hosted font (`@fontsource-variable/inter`, OFL) with an ADR. Everything else is CSS,
   MapLibre and ~300 lines of our own animation code.
6. **Machine:** Windows; at most 2–3 heavy processes at once (this PC crashed once with five). Node 20 portable at
   `C:\Users\ivann\.dt-tools\node\node-v20.20.2-win-x64` (prepend to PATH), `uv`, Docker Desktop
   (`docker compose up -d --wait`), always `127.0.0.1`, never `localhost`. Old source files have CRLF line endings:
   edit with exact-match tools; in Git Bash write new files with the Write tool (heredocs with quotes break).
7. **Run:** API `apps/blizu/data/run_dev_api.ps1` (port 8010, DB `blizu`); web
   `BLIZU_API_URL=http://127.0.0.1:8010 pnpm dev --host 127.0.0.1 --port 5173` in `apps/blizu/web`.

---

## 1. The experience in one paragraph (your north star)

You open Blizu at night-mode calm: a deep, quiet canvas, one confident headline, a glass search card. You type an
address, pick "Stariji", press **Provjeri dostupnost**. The map flies in, and from your door the streets of Zagreb
**light up like water spreading** — cyan near you, cooling to violet at 15 minutes — while pharmacies, schools and stops
**blink awake** the moment the front reaches them, and a counter ticks "U dosegu 10 min: 2 ljekarne, 1 škola". You tap
"Ljekarna": the camera glides, the route **draws itself**, and a bright dot walks it at an elderly person's pace.
In the planner, unmet need rises as **glowing columns** over the city; you press "Predloži 3 lokacije", three sites drop
in with a shockwave and the columns around them **sink** to their new values while the headline counts the people who
just got in reach. Everything is real, everything is clickable, and with reduced motion it is the same information,
instantly, without movement.

Three "wow" moments carry the product: **(1) the walking-time flood, (2) the route that draws itself, (3) the planner
columns that sink.** Polish those to perfection before anything else in Part B.

---

## 2. Phase 1 — Design system "Night Atlas" (tokens first, then components)

Override `@dt/ui` tokens only inside `apps/blizu/web/src/index.css` (Otporko and Birokratko keep theirs).

**Colour tokens** (verify contrast with a small script `apps/blizu/web/scripts/contrast.mjs` that fails on < 4.5:1 for
text and < 3:1 for UI borders/large text; run it in CI via a vitest test):

| Token          | Value                                                                    | Use                                        |
| -------------- | ------------------------------------------------------------------------ | ------------------------------------------ |
| `--bg`         | `#07090D`                                                                | page canvas                                |
| `--surface-1`  | `#0D1117`                                                                | sidebar, panels                            |
| `--surface-2`  | `#141A23`                                                                | tiles, inputs                              |
| `--glass`      | `rgb(255 255 255 / 0.04)` + `backdrop-filter: blur(16px) saturate(140%)` | hero card, floating controls               |
| `--line`       | `rgb(255 255 255 / 0.09)`                                                | 1 px borders (hairlines)                   |
| `--text`       | `#F3F5F8`                                                                | primary text                               |
| `--text-muted` | `#9AA4B2`                                                                | secondary text (≥ 7:1 on `--bg`)           |
| `--accent`     | `#22D3EE`                                                                | focus ring, links, map "near"              |
| `--accent-2`   | `#A78BFA`                                                                | map "far" end of the time ramp             |
| grade A–E      | `#34D399` `#A3E635` `#FACC15` `#FB923C` `#F87171`                        | always with the letter, never colour alone |

Backdrop-filter fallback: where unsupported, use solid `--surface-1` (no unreadable transparency).

**Type:** Inter Variable, self-hosted (`@fontsource-variable/inter`, latin + latin-ext; check č ć š ž đ render), with
`font-feature-settings: "tnum" 1, "cv11" 1` for numbers. Scale (rem): 0.75 / 0.875 / 1 / 1.25 / 1.5 / 2 / 3 / 4.5;
display headings weight 700, letter-spacing −0.03em; overline labels 0.75 rem, weight 600, letter-spacing 0.12em,
uppercase, `--text-muted`.

**Shape & depth:** radii 10 / 16 / 24 / 9999; elevation via border + inner highlight
(`inset 0 1px 0 rgb(255 255 255 / 0.06)`) and a soft ambient shadow (`0 24px 48px -24px rgb(0 0 0 / 0.6)`), no heavy
drop shadows. Background texture: a 24 px dot grid at 6 % plus a radial vignette; nothing that reduces text contrast.

**Motion tokens:** `--dur-1 120ms` (press), `--dur-2 220ms` (hover, chips), `--dur-3 420ms` (panels),
`--ease-out cubic-bezier(.2,.8,.2,1)`, `--ease-spring cubic-bezier(.34,1.56,.64,1)` (small pops only). Under
`prefers-reduced-motion: reduce` every duration becomes 0 and transforms are disabled.

**Components (dark, all states: default, hover, focus-visible, active, disabled, loading, error):** glass card; white
pill primary button with trailing arrow; ghost button; persona segmented control (`role="radiogroup"`, arrow keys,
selected = solid white tile, dark text, icon + uppercase label); category tile (icon, label, big tabular "N min",
grade chip with letter; hover lift 2 px; press scale .98); score card ("DOSTUPNOST USLUGA", grade letter in a ring,
index /100, confidence chip); chips; skeleton shimmer (static under reduced motion); empty and error states with retry;
floating map control stack (layers, zoom ±, locate, 3D) as 40 px glass buttons with tooltips and `aria-label`s.

**Gate 1:** contrast test green; all existing vitest tests green (update selectors, not behaviour); screenshot of a
component sheet page (dev-only route `/__ui`) at 1360 px — look at it and fix anything that looks cheap.

---

## 3. Phase 2 — Screens (keep every feature, change the stage)

- **Header:** white rounded-square logo mark + "Blizu**.zg**" (".zg" in `--text-muted`); centre links "Kako radi?"
  (→ methodology), "Otvoreni podaci" (→ sources); right: pill "Planerski način" (→ `/planiranje`) and a search icon
  that focuses the address field. Sticky, glass, 64 px.
- **Home:** hero "Što ti je **blizu?**" (last word in a cyan→violet text gradient; the real text stays selectable),
  one-line subtitle, the glass card with the address combobox, persona control, and the primary button
  "Provjeri dostupnost →". Below the fold: three honest explainer tiles (what we measure, data sources with dates from
  `/api/v1/sources`, planner teaser). No fake stats.
- **Results (`/kartica`):** desktop = 360 px left panel + full-bleed map; panel: "← Nova pretraga", address, persona
  chip (changeable), score card, the 9 category tiles in a 3-column grid, data-age notes, compare and print actions.
  Map: dark style, address pin with label card, floating controls, bottom-right cyan pill "Vidi analizu potreba kvarta"
  (→ planner centred on this address). **Mobile (390 px):** the panel becomes a bottom sheet with two states
  (peek: score + 3 tiles; expanded: everything) toggled by a handle button (`aria-expanded`); dragging is a bonus, the
  button is the requirement.
- **Compare, planner, methodology, sources, not found:** same system. **Print** stays a light A4 card (dedicated print
  stylesheet: white background, black text, no map, no glass).
- Keep all routes, query parameters and share links working exactly as today.

**Gate 2:** all vitest + Playwright tests green (adapt selectors only); Lighthouse a11y ≥ 95 on `/` and `/kartica`;
screenshots 1360 px and 390 px of home and results look like a flagship product (fix spacing, alignment, hierarchy
until they do).

---

## 4. Phase 3 — API for honest animation (backend first, then the map)

Add to `apps/blizu/api/src/blizu_api/` with tests on the real Trg bana Jelačića subgraph fixture. Reuse the
snapping and validation of `/access` (422 outside Zagreb or > 300 m from the network; problem+json). Cache with an LRU
keyed by (lat, lon rounded to 5 decimals, persona). Caddy already compresses responses (`encode zstd gzip`).

### 4.1 `GET /api/v1/isochrone?lat&lon&persona&max_min=15` (max_min 5–20)

One Dijkstra (`scipy.sparse.csgraph.dijkstra`, `indices=start`, `limit=max_min·60·speed`, persona's graph variant).
**Return the streets grouped by time bucket, not edge by edge** — this is what keeps the animation at 60 fps:

```json
{
  "origin": {"lon": 15.977, "lat": 45.813, "snapped_m": 12.4},
  "persona": "starija", "speed_mps": 0.9, "max_min": 15, "bucket_min": 0.25,
  "buckets": {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"t": 0.25}, "geometry": {"type": "MultiLineString", "coordinates": [...]}}
  ]},
  "facilities": [{"id": "...", "category": "ljekarna", "name": "...", "t": 6.8, "lon": 0, "lat": 0}],
  "counts": {"5": {"ljekarna": 1}, "10": {"ljekarna": 2, "skola": 1}, "15": {}}
}
```

An edge (u, v) belongs to bucket `ceil(min(d_u, d_v)/speed/60 / bucket_min)·bucket_min`, drawn as the straight segment
between its nodes (the graph stores one edge per node pair). Coordinates rounded to 5 decimals; drop edges whose far
end exceeds the limit. Facilities and counts come from the same Dijkstra distances to the facilities' snapped nodes,
so they match `/access` (test: ±0,1 min). Budget: ≤ 80 buckets, ≤ 1 MB raw, warm < 100 ms.

### 4.2 `GET /api/v1/route?lat&lon&persona&category` (or `&facility_id=`)

Nearest facility of that category (or the given one) and the shortest path via Dijkstra predecessors:
`{minutes, distance_m, facility{...}, coordinates:[[lon,lat],...]}`. Test: minutes equal `/access` for the same
category (±0,1 min); kolica ≥ opće; path is connected and starts/ends at the snapped nodes.

### 4.3 `/plan/optimise` → add per-cell before/after

Today it returns `sites`, `share_before/after`, `total_newly_covered`, but no per-cell values. Add
`cells: [{cell_id, unmet_before, unmet_after}]` computed with the **same node coverage the optimiser uses**
(node demand minus newly covered demand, summed per cell). Test: Σ(before − after) equals `total_newly_covered`
(±1 person) and every after ≤ before.

**Gate 3:** `uv run pytest apps/blizu/api` green with the new tests; README API table and OpenAPI updated; record the
three responses for one real address as web fixtures (`curl`).

---

## 5. Phase 4 — The map engine (`apps/blizu/web/src/lib/anim/`)

Small, pure, tested modules; React components only wire them to MapLibre.

- `clock.ts` — one shared `requestAnimationFrame` loop, time-based (`dt` from timestamps, identical at 60 and 144 Hz),
  subscribers register/unregister, auto-pauses on `document.hidden` and when no map is on screen
  (IntersectionObserver), never runs under reduced motion. Dev-only `window.__blizuAnim = { frames, running }` for tests.
- `easing.ts`, `timeline.ts` — easing functions; timelines of keyframes `{at, duration, ease, apply(p)}`.
- `camera.ts` — presets (`overview`, `street`, `orbit`), `flyTo` with `curve: 1.42`, `essential: false` (MapLibre then
  respects reduced motion by itself), `easeTo` for small moves, `jumpTo` when reduced.
- `route.ts` — cumulative lengths, `positionAt(p)`, bearing at p (for the walking dot).
- `scene.ts` — scene state machine `idle → doseg ↔ put ↔ 3d`, URL sync `?scena=doseg|put|3d`.

**MapLibre techniques (and the gotchas that matter):**

- **Dark base style:** `https://tiles.openfreemap.org/styles/dark` (verified 2026-11-05: HTTP 200, 47 layers, no 3D
  buildings). Probe again and save it as dated evidence. Insert our layers **below the first symbol layer** so labels
  stay on top. Pass it through `MapView`'s existing `styleUrl` prop; extend `MapView` only with optional props
  (e.g. `onLoad` already exists; add `interactive`/`attributionPosition` only if needed).
- **Flood (scene "doseg"):** one GeoJSON source with the buckets; three line layers: a wide blurred glow
  (`line-blur`, low opacity), the crisp line (colour ramp `interpolate` on `t`: `--accent` → `--accent-2`), and a
  "front" layer showing only buckets within the last 0.75 min of the clock at higher width/brightness. Animate by
  updating the **filters** (`['<=', ['get','t'], clock]`) at ≤ 30 Hz — cheap because there are ≤ 80 features.
  Facilities are DOM markers that get a CSS "pop" class when `clock ≥ t`.
- **Route draw (scene "put"):** GeoJSON source with `lineMetrics: true` (required for `line-progress`); animate
  `line-gradient` stops each frame (`['interpolate', ['linear'], ['line-progress'], 0, accent, p, accent, p+0.0001,
'transparent']`); a trail layer with a softer gradient; the walking dot is a small GeoJSON point updated with
  `setData` (or a DOM marker) at the persona's real speed scaled by a constant time-lapse factor shown in the UI
  ("ubrzano ×30").
- **3D (scene "3d"):** add a `fill-extrusion` layer on the style's `openmaptiles` source, source-layer `building`,
  height from `render_height`/`render_min_height`. **First verify in real tiles over Zagreb at z15–16 that these
  attributes exist** (decode one tile or query rendered features) and save evidence; if missing, ship 3D as pitch +
  orbit only and say so. Fade buildings with the native paint transition on the constant `fill-extrusion-opacity`
  (data-driven properties do **not** transition in MapLibre — animate those by expression + clock instead).
  Orbit = bearing += 4°/s, stops on any user input.
- **Planner columns (scene D):** `fill-extrusion` on the cell polygons, height = `unmet · scale`, colour ramp from the
  API's real quantile thresholds. Before→after: height expression
  `['+', ['*', ['get','unmet_before'], 1-p], ['*', ['get','unmet_after'], p]]` with p driven by the clock for 900 ms
  (≈ 600 cells, fine at 30 Hz). Sites drop in (DOM marker with a CSS shockwave ring), headline number counts to the
  real `total_newly_covered`.
- Never put per-frame values in React state (refs + MapLibre setters only). No layout reads in the loop.

**Gate 4:** vitest for clock (pauses, time-based), easing, timeline, route `positionAt`, bucket filter builder, scene
URL sync, reduced-motion decisions — all green.

---

## 6. Phase 5 — Scenes and controls

Scene switcher = a segmented control over the map ("Doseg pješice", "Put do…", "3D") with `aria-pressed`, keyboard
operable, state in the URL.

- **A · Doseg pješice** (default after search): auto-plays once (2.5 s for 15 min of walking), then rests; controls:
  play/replay, a time slider 0–15 min (`input type=range`, `aria-valuetext="10 minuta"`), chips 5/10/15; live counter
  "U dosegu 10 min: 2 ljekarne, 1 škola" (`aria-live="polite"`, from `counts`/`facilities`, not computed on the client).
- **B · Put do…**: tapping a category tile (or a facility marker) loads `/route`, glides the camera to frame the route,
  draws it, walks the dot; the tile shows the minutes; tapping another tile morphs (old route fades as the new one draws).
- **C · 3D**: pitch 60°, slow orbit, buildings fade in, the flood stays as ground light; any drag stops the orbit.
- **D · Planner**: `/planiranje` gets the columns and "Predloži lokacije" (k 1–5); changing k replays from the current
  state; hover/focus tooltip with real numbers; the same numbers in a table below the map.

**Reduced motion (all scenes):** no flights (`jumpTo`), no orbit, no flood growth, no walking dot, no shockwave — the
final state appears immediately and every control still works (the slider sets the filter directly).
**Failure modes:** no WebGL → current graceful message + lists; tile or API error → error state with retry over the
map; dark style failure → `MapView`'s raster fallback with 3D disabled and a notice. **Nothing is only on the map:**
the panel lists the same facilities, minutes and counts.

**Gate 5:** Playwright (real stack) —

1. search → `/kartica` → flood runs (`__blizuAnim.frames` increases), slider to 5 changes the counter text;
2. tap "Ljekarna" → route layer has data, minutes in the tile equal the API's;
3. "3D" → `map.getPitch() ≥ 55` (dev-only `window.__blizuMap`);
4. planner → "Predloži 3" → final headline equals the API `total_newly_covered`; table present;
5. `emulateMedia({ reducedMotion: 'reduce' })` → `__blizuAnim.running === false`, final states visible;
6. all existing e2e tests still pass.

---

## 7. Phase 6 — Polish pass (only after Gate 5)

Spend real time here; this is what separates "nice" from "elite":

- Screenshots at 1360 and 390 px of home, results (A, B, C), planner before/after. **Look at every one.** Fix: optical
  alignment, consistent 8 px rhythm, label truncation, empty corners, z-index fights between map controls and panels,
  focus rings clipped by `overflow:hidden`.
- Measure: Chrome performance trace of the flood on `/kartica` — target ≥ 50 fps; if lower, enlarge the bucket size or
  reduce glow width, never drop data.
- Lighthouse: accessibility ≥ 95 on `/`, `/kartica`, `/planiranje`; mobile performance ≥ 80 on `/` and `/kartica`
  (today 85–88: if it drops, lazy-load the map chunk and fonts properly). Save JSON in `apps/blizu/data/evidence/`.

---

## 8. Definition of done

Phases 1–6 gates green; `uv run pytest apps/blizu/api`, `pnpm --filter blizu-web test`, `pnpm exec tsc --noEmit`,
`pnpm exec eslint . --max-warnings 0`, Playwright, root `uv run ruff check .`, `uv run ruff format --check .`,
`pnpm exec prettier --check .`, `gitleaks detect --no-git --source apps/blizu` all green; ADR (font, dark style and 3D
source, isochrone/route/planner contracts); README updated (new endpoints, scenes, reduced motion); one commit per phase
at least. Final REPORT in the CLAUDE.md format — Implemented / Verified (exact commands + results) / Not done /
Fallbacks / Known issues — with the fps you measured and the screenshots you checked.

## 9. Cut list (in this order, only if you run out of time)

1. Mobile drag gesture of the bottom sheet (keep the toggle button).
2. Orbit in 3D (keep the pitch toggle).
3. 3D buildings (if the tile attributes are missing or time runs out).
4. Home-page decorative background motion (keep the static dot grid).

Never cut: data honesty, reduced-motion behaviour, keyboard access, the three "wow" moments, the tests.
**Out of scope:** video export, AI-generated map styles, a guided "tour" mode, light theme for the app (print only).
