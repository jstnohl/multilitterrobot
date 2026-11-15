# multilitterrobot

Manage multiple Litter-Robots from one page — a full replacement for the Whisker app, built to be better where it can be. Live robot status, Clean and night-light controls, and **Kitties**: per-cat profiles, automatic visit detection, and weight graphs.

(This screenshot will be updated once I get some graph data in my own version and I'll even scrub out my kitty names because the internet is weird)
![Kitty Crapper](kitty-crapper.png)

## What it does

- **Robot cards** — live status, litter level, last cat weight, scoops saved, and online state for every box on your account.
- **Clean** — start a cleaning cycle from any robot card.
- **Night light** — ON / OFF / AUTO dropdown per box.
- **Kitties** — pet profiles (name, usual weight, birthdate, colour). The backend watches the cycle count: when a box cycles, it logs a visit with the cat's weight at that moment, and matches it to a pet by weight.
- **Visit matching** — nearest pet within ±0.75 lbs wins. If two pets are in range and the closest isn't at least 0.5 lbs closer than the runner-up, the visit is **ambiguous** (shows both names) instead of a forced wrong guess. No match → **Unknown**. The box's **last cat** breaks ties: if one of the candidates is the box's last cat, that cat wins.
- **Recent visits** — full-width table with per-cat filter and its own date range. Correct a visit with the "Correct it" dropdown (reassigning retrains the box's last cat). Delete a wrong visit with the red ✕ (with a confirm).
- **Weight graphs** — hand-rolled SVG chart, one dot per visit. Dot fill = cat colour, dot ring = box colour, per-cat trend lines, Fill toggle. Kitty cards in the left column double as the legend: click one to hide/show that cat. A shared date-range picker (7d / 30d / All presets, typed dates, dual sliders) drives both the graph and the visits table.
- **Last used by** — each robot card shows which cat last used that box (and when). Set it by hand from the dropdown; assigning one logs a manual visit at that moment, and re-assigning corrects the latest manual visit in place instead of adding a second dot.
- **Box colours** — gear on each robot card picks a colour per box (dark/muted palette, so a ring never looks like a cat). The colour is the ring around each graph dot.

Nothing is hard-coded to one household. Pets, settings and data come from the owner through the page; the app starts with no cats and no history.

## Stack

- **Backend:** Python + FastAPI (WebSockets) wrapping [pylitterbot](https://github.com/natekspencer/pylitterbot), on port `4323`.
- **Frontend:** [SvelteKit](https://kit.svelte.dev), [TailwindCSS](https://tailwindcss.com), [DaisyUI](https://daisyui.com).
- Inspired by [engageintellect/litterbot](https://github.com/engageintellect/litterbot).

## Getting started

### 1. Clone

```bash
git clone https://github.com/jstnohl/multilitterrobot
cd multilitterrobot
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Fill in your own values. Never commit a real `.env` — it is gitignored.

| Variable | Where | What it is |
| --- | --- | --- |
| `LITTERBOT_USERNAME` | `server/.env` | Your Whisker / Litter-Robot account email |
| `LITTERBOT_PASSWORD` | `server/.env` | Your Whisker / Litter-Robot account password |
| `SERVER_ENDPOINT` | `client/.env` | Base URL of the backend API (dev), e.g. `http://localhost:4323` |

In production, nginx proxies `/api` to the backend directly, so the frontend doesn't need `SERVER_ENDPOINT` at runtime — it only matters for the dev server.

### 3. Backend

```bash
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

The backend connects to Whisker on startup (takes a few seconds) and serves on port `4323`. It runs with `reload=False` — the reloader used to watch the whole project tree (including `node_modules`) and pin the CPU at 16–18%.

For a permanent install, run it as a service (e.g. a systemd unit that runs `python main.py` from `server/`).

### 4. Frontend

```bash
cd client
pnpm i
pnpm run dev --host
```

Dev server on port `5173`. For production:

```bash
cd client
pnpm build
```

Then serve `client/build` with a static server (nginx below). The SvelteKit dev server only serves `/api` through the proxy routes in `client/src/routes/api/` — every backend endpoint needs a matching proxy route there. Production doesn't need them (nginx proxies `/api` straight to the backend).

### 5. Production (nginx)

Serve the static build and proxy the API:

```nginx
server {
    listen 80;
    server_name litterbox;  # or your host/IP

    root /path/to/multilitterrobot/client/build;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:4323;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Rebuilding the frontend needs no nginx restart (it serves files off disk). Backend changes need a backend restart.

## Using it

- **Add a kitty** — "Add kitty?" on the Kitties section. Name, usual weight (lbs), birthdate (optional — the page computes age from it), colour (auto-assigned from the palette if you pick none).
- **A visit appears** — when a box finishes a cycle, a row shows up in Recent visits and a dot on the graph, matched to a cat (or marked ambiguous / Unknown).
- **Wrong match?** — use the "Correct it" dropdown on that row. It sticks, and it retrains the box's last cat.
- **Duplicate or bogus visit?** — red ✕ at the end of the row (with a confirm). Deleting does not retrain last-cat.
- **Read the graph** — dot fill is the cat, ring is the box. Click a kitty card to hide/show that cat. Use the date-range picker (7d / 30d / All, or type dates / drag the sliders) to zoom. The visits table has its own independent range controls.
- **Box colour** — gear (⚙) on a robot card. The colour shows as the dot next to the gear and as the ring on the graph.
- **Last used by** — dropdown on a robot card. Setting it logs a manual visit now; re-assigning fixes the latest manual visit in place.

## Data files

All runtime data lives next to `server/main.py` and is **gitignored — never committed**:

| File | What it holds |
| --- | --- |
| `pets.json` | Pet profiles: `{id, name, weight, birthdate, color}` |
| `visits.json` | Visit log (newest 500): `{id, timestamp, serial, robot, weight, pet, ambiguous, manual, matched_by}` |
| `last_cat.json` | Which cat last used each box: `{serial: {pet_id, updated_at}}` |
| `box_colors.json` | Per-box colour: `{serial: "#rrggbb"}` |

## Known limits

- Back-to-back visits before a single cycle log as **one** visit.
- A manual **Clean** press also ticks the cycle count, so it logs a visit with the last cat's weight.
- History starts when the new backend starts — no backfill of older visits.
- `catWeight` is assumed to be the visiting cat's weight in lbs.

## API

Backend (port `4323`):

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/robots` | All robots (name, serial, status, litter level, weight, scoops) |
| GET | `/api/robot/{serial}` | One robot |
| POST | `/api/robot/{serial}/clean` | Start a cleaning cycle |
| POST | `/api/robot/{serial}/light?mode=on\|off\|auto` | Set night-light mode |
| GET/POST/DELETE | `/api/pets` | Pet profiles |
| GET | `/api/visits?limit=` | Visit log |
| POST | `/api/visits/reassign` | Correct a visit's pet |
| DELETE | `/api/visits/{visit_id}` | Delete one visit |
| GET/POST | `/api/robot/{serial}/last-cat` | The box's last cat |
| GET/POST | `/api/box-colors` | Per-box colours |

## Changelog

See [CHANGELOG.md](CHANGELOG.md). Current version: **0.5.6**.
