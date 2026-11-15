# Changelog

All notable changes to multilitterrobot. The Kitties release landed 2026-11-14.

## [0.5.6] — 2026-11-14

### Added
- Delete a visit: a red ✕ at the end of each Recent visits row (with a confirm). Backend `DELETE /api/visits/{id}`.
- Box column now shows the box name and serial: `LR4.1 (LR4C297161)`.

### Changed
- Robot card: Clean button moved to the left, Light dropdown stays on the right.
- Removed a stray `t` that rendered after the last-cat dropdown.
- Footer debug readout (`chart WxH`) removed.
- `.gitignore` now covers all runtime data files (`pets.json`, `visits.json`, `last_cat.json`, `box_colors.json`).
- Added a committable `.env.example` documenting `LITTERBOT_USERNAME`, `LITTERBOT_PASSWORD`, `SERVER_ENDPOINT`.

### Fixed — graph toggle scaling
- Toggling a kitty card moved the dots but not the axis labels (and sometimes the dots didn't hide at all). Root cause: Svelte doesn't track the scale inside the `y()`/`x()` calls in the template, so the dots' list and the labels' list updated independently. Fix: the whole `<svg>` is keyed on the scale, size, range, visible dots and toggles, so it re-renders as one consistent unit whenever any of those change.

## [0.4.3] — 2026-11-14

### Added
- Custom hover tooltip on graph dots: who / box / weight / time (replaces the slow native tooltip).

### Changed
- Box colours are now a dark/muted palette (dark blue, red, dark green, brown, deep purple, slate) so they read as box outlines, distinct from the bright kitty colours.

### Fixed — graph height
- The chart was stuck at ~300px tall no matter what the flex chain did. Root cause: the footer `<p>` itself had `flex-grow: 1` and was eating half the card. Fix: inline `flex: 0 0 auto` on the footer. Chart now fills the card (744×612).

## [0.4.2] — 2026-11-14

### Changed
- Re-assigning a last-cat now corrects the latest manual visit for that box in place instead of adding a second (stale) dot.
- Graph dots 40% bigger; last X-axis time label no longer clipped.

## [0.4.1] — 2026-11-14

### Changed
- Layout: kitty cards stack in a left column and double as the graph legend (click to hide/show a cat); graph on the right; Recent visits below the graph, full width, with its own independent range controls.
- Shared `DateRangePicker` (presets 7d/30d/All, typed dates, dual sliders) drives both the graph and the visits table.

### Added
- Assigning a last-cat now logs a manual visit at that moment, so the graph shows it after refresh.
- "Last used by" shows clock time (HH:MM); the graph X-axis shows HH:MM ticks on a single-day range.

## [0.4.0] — 2026-11-14

### Added
- Last-cat tracking per box (`last_cat.json`): a confident match sets the box's last cat, and it breaks weight ties; reassigning a visit retrains it; clearing it sets Unknown.
- Box colours (`box_colors.json`): each box gets a colour (hash default), shown as the ring around each graph dot.
- CatGraphs: hand-rolled SVG chart (weight on Y, date on X), one dot per visit (fill = cat colour, ring = box colour), per-cat trend lines, Fill toggle.
- RobotLastCat (last-used-by + assign dropdown) and RobotBoxColor (gear + colour swatches) on each robot card.
- SvelteKit proxy routes for `/api/robot/[serial]/last-cat` and `/api/box-colors` (the dev server only serves `/api` through these).

## [0.3.0] — 2026-11-14

### Added
- Kitties: pet profiles (`pets.json`) and a visit log (`visits.json`).
- Visit detection: a cycle-count tick logs a visit, weighted by `catWeight` at that moment.
- Matching: nearest pet within ±0.75 lbs; if the closest isn't at least 0.5 lbs closer than the runner-up, the visit is ambiguous (shows both names) instead of a forced wrong guess; no match → Unknown.
- Per-pet cards (colour, usual weight, age from birthdate, last weight/visit/box, delete) and a Recent visits table with per-cat filter and a "Correct it" dropdown (reassign sticks).
- Known limits: back-to-back visits before one cycle log as a single visit; a manual Clean press also ticks the cycle count and logs a visit; history starts when the new backend starts (no backfill).

## [0.2.0] — 2026-11-13

### Added
- The base app: FastAPI + WebSockets backend wrapping pylitterbot, SvelteKit + TailwindCSS + DaisyUI frontend.
- Robot cards with live status, litter level, cat weight, scoops saved; Clean button; night-light ON/OFF/AUTO dropdown.
- nginx serves the production page from the static build; backend on port 4323.

### Fixed
- CPU: the uvicorn reloader was watching the whole project tree (including `node_modules`) and pinning the container at 16–18%. `reload=False` dropped it to ~0.01%.

