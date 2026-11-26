# Changelog

All notable changes to multilitterrobot. The Kitties release landed 2026-11-14.

## [0.6.8] — 2026-11-16

### Added
- **Visits and the stuck-clean auto-reset now work with no page open.** Detection and the auto-reset used to live inside the page's live connection, so nothing was logged and nothing reset when no page was open — and two pages open at once could log the same visit twice. Both now run in a single background task that starts with the backend and runs forever. The page's connection only displays state. A box stuck in `ROBOT_CLEAN` for over 10 minutes still resets itself, and a missed visit is still recovered from the scale weight.

- **Weight change mid-detection now logs a new event.** A second cat stepping on while the first is still (or just) there used to be swallowed — one event per arrival, weight changes ignored. Now, if the scale moves more than 0.5 lb from the open event's weight while detection is still on, the new weight is matched and logged as its own visit.

## [0.6.7] — 2026-11-16

### Added
- **A box stuck in ROBOT_CLEAN now resets itself.** A normal clean cycle takes ~2-3 minutes; if a box sits in `ROBOT_CLEAN` longer than 10 minutes it is stuck, so the backend resets it automatically and it returns to READY. If no visit was logged for that cycle (the arrival detection was missed, e.g. no page was open when the cat used it), the visit is recovered from the scale weight first, so it still lands on the graph. A visit recorded within the last hour is the same cycle already logged at arrival and is never logged twice.

## [0.6.6] — 2026-11-16

### Changed
- **Kitty cards show a short date for the last visit** — "MM/DD @ h:mm AM" (e.g. "11/16 @ 11:30 AM") instead of the full "Mon, Nov 16, 11:30 AM" string, which was too long on a card. The Recent visits table keeps the full date.

## [0.6.5] — 2026-11-16

### Changed
- **Robot cards show the name and serial on one line** — name big and bold, serial small beside it, instead of stacked on two lines.
- **Section titles are vertical, on the left** — "Litter Robots" and "Kitties" are rotated 90° counter-clockwise and sit to the left of their sections, saving vertical space.
- **Waste drawer bar moved** — it now sits between the Cat Weight / Scoops Saved stats and the Clean / Reset / Light buttons.
- **Box colour picker moved to the bottom-right** of each robot card, cleanly separated from the "Last used by" field.
- **Graph timeline moved to the bottom** — the date-range controls sit below the graph, so the graph is what you see first on load.
- **Box names everywhere, serials only where they belong** — kitty cards ("Box used") and graph tooltips now show the box name, never the serial. The serial appears only on the robot card header and in the Recent visits table.
- **Dots are rounded squares** — graph dots and kitty-card dots are squares with rounded corners instead of circles, matching the other squares in the app.

## [0.6.4] — 2026-11-15

### Fixed
- **Repeat visits by the same cat now log.** The detector only logged a visit when the matched cat differed from the box's last cat, so Sally's 2:17 PM return to LR4.1 was skipped — the last cat was already Sally from 5:06 AM. Detection is now gated on the robot status: a visit logs when a cat arrives (status enters `ROBOT_CAT_DETECT` / `ROBOT_CAT_DETECT_DELAY`) and the weight confidently matches, even if it's the same cat as last time. A per-robot arrival flag prevents a sticky weight reading from re-logging while the cat is still there, and it clears when the status leaves the cat-present states.

## [0.6.3] — 2026-11-14

### Fixed
- **Visit matching tolerance tightened from ±0.75 lb to ±0.5 lb.** Sally (6.6 lb) and Reba (7.6 lb) are only 1.0 lb apart, so a 7.05 lb reading fell inside both cats' windows and was dropped as ambiguous — Sally's 9:17 PM visit never logged and her average never moved. At ±0.5 lb, 7.05 is in range for Sally only (0.45) and out of range for Reba (0.55), so it matches Sally confidently.

## [0.6.2] — 2026-11-14

### Fixed
- **Litter Level stat now shows the real globe litter state** (Optimal / Low / Refill / Empty / Overfill) instead of repeating the waste-drawer percentage. The drawer percentage lives on its own field now (`drawer_level`), so the top bar and the stat box no longer show the same number.
- **Top bar relabeled "Waste drawer"** (was "Drawer") so it's unambiguous.

## [0.6.1] — 2026-11-14

### Added
- **Drawer level bar at the top of each robot card.** A color-coded progress bar (green under 50%, yellow 50–80%, red over 80%) shows the waste drawer fullness at a glance, with the percentage next to it. Labeled "Drawer" to make clear it's the waste drawer, not the litter in the globe.
- **In-app Reset button on each robot card.** Sits between Clean and Light; sends the LR4's reset command (the in-app equivalent of the physical RESET button) to re-zero the sensors and reset the drawer gauge after emptying, so you don't have to get up and press the button on the unit.

## [0.6.0] — 2026-11-14

### Changed
- **Kitty cards now show "Average weight" instead of "Usual weight".** The average is the input weight plus every automatic scale-measured visit weight for that cat, divided by the count (rounded to 1 decimal). Manual visits are excluded (they just repeat the input weight). A cat with no automatic visits yet shows its input weight. Matching still uses the input weight to identify the cat; the average is display-only, so you can see drift at a glance (e.g. Cheetoh entered at 8.4 lb, measured 8.7 lb, average 8.6 lb).

## [0.5.9] — 2026-11-14

### Fixed
- **Last-used now updates when a cat uses a box.** Visit detection no longer waits on the cleaning cycle count (`DFINumberOfCycles` never ticks on the LR4, so no automatic visit had ever logged and "Last used by" stayed stale). It now matches the live scale weight against the known cats: when it confidently matches a cat different from the box's last cat, that's a new visit — timestamped, logged, and the last cat updates automatically. (Cheetoh's LR4.1 visit, ~20 min before the fix, was the trigger: weight read 8.7 lb but last-used still showed Reba from 5:49 PM.)

## [0.5.8] — 2026-11-14

### Changed
- Rebrand: the app is now **multilitterrobot** (was "Kitty Crapper") — cat icon in the header, kitty favicon, browser tab title.
- Header: logo top-left, theme selector just right of it, footer credits moved up into a clean two-line block at the top-right. The footer is gone from the bottom of the page.
- Removed the dead commented-out search and avatar blocks from the nav.

## [0.5.7] — 2026-11-14

### Added
- Colour gear on each kitty card: change a cat's colour any time (palette swatches), no more delete-and-re-add.
- Left accent bar on each robot card in the box's colour, matching the kitty cards — the card now reads as its graph ring.

### Changed
- Graph dots are bigger (r 9, ring 4.5) so the cat and the box read at a glance.

## [0.5.6] — 2026-11-14

### Added
- Delete a visit: a red ✕ at the end of each Recent visits row (with a confirm). Backend `DELETE /api/visits/{id}`.
- Box column now shows the box name and serial: `LR4.1 (LR4Cxxxxxx)`.

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

