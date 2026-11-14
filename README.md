# multilitterrobot

Got multiple Litter-Robots like me? Make your life easier with this setup!

A web app to monitor and control multiple Litter-Robots from one page. A Python/FastAPI backend wraps [pylitterbot](https://github.com/natekspencer/pylitterbot) (live status over WebSockets), and a SvelteKit + TailwindCSS + DaisyUI frontend shows every robot on one dashboard with Clean and night-light controls.

Derived from [engageintellect/litterbot](https://github.com/engageintellect/litterbot).

## Features

- **Multi-robot dashboard** — status, litter level, cat weight, scoops saved, and online state for every robot, live-updated over WebSocket (~5s refresh).
- **Clean button** — starts a cleaning cycle on that robot.
- **Night-light dropdown** — set the light mode to **On**, **Off**, or **Auto** per robot. The dropdown always shows the robot's current mode.
- **Works on your LAN** — run the frontend with `--host` and open it from any device on your network.

## Supported robots

| Model | Clean | Night light |
| --- | --- | --- |
| Litter-Robot 4 | ✅ | ✅ On / Off / Auto |
| Litter-Robot 5 | ✅ | ✅ On / Off / Auto |
| Litter-Robot 3 | ✅ | ⚠️ On / Off only — see below |

**Litter-Robot 3 note:** the LR3 has no Auto mode — its night light is a simple on/off command, and its own light sensor decides when the light actually comes on. If you pick **Auto** for an LR3, the app treats it as **On**. The dropdown may also show Auto as the current mode on an LR3, because the LR3 doesn't report a light mode at all; the commands themselves still work.

## Your robots — no serial numbers needed

This setup was built and tested with **two Litter-Robot 4s** (named LR4.1 and LR4.2 in the app). **You don't need to change any serial numbers to deploy it** — the app discovers your robots from your Whisker account automatically, and no serial numbers are hardcoded anywhere in the code. The `[serial]` in the route paths is a placeholder SvelteKit fills in from the URL, not a real serial.

If you're adapting an older copy of this project that still has one folder per robot serial number (e.g. `client/src/routes/api/robots/LR4C.../`), delete those folders — they're obsolete. Don't paste your robots' serial numbers into the code, your config, or this README; they're not needed to run the app, and they don't belong in a public repo.

## Requirements

- Python 3.11+ (backend)
- Node.js 18+ and [pnpm](https://pnpm.io/) (frontend)
- A Whisker account with your robots already set up in the Whisker app
- Your robots and this server on the same network (or otherwise reachable)

## Quick start

```bash
git clone https://github.com/jstnohl/multilitterrobot
cd multilitterrobot
```

### 1. Backend

```bash
cd server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `server/.env` with your Whisker credentials:

```env
LITTERBOT_USERNAME=your@email.com
LITTERBOT_PASSWORD=yourpassword
```

Then run it:

```bash
python main.py
```

The backend listens on `http://0.0.0.0:4323`. You can check it's up at `http://localhost:4323/` — it reports how many robots are connected.

> ⚠️ Never commit your `.env` — it holds your Whisker login.

### 2. Frontend

```bash
cd client
pnpm i
```

Create `client/.env`:

```env
# Where the browser connects for live updates
PUBLIC_WEB_SOCKET_URL=ws://localhost:4323/api/ws
# Where the frontend proxies API calls to (server-side only)
SERVER_ENDPOINT=http://localhost:4323
```

Then run it:

```bash
pnpm run dev --host
```

Open `http://localhost:5173` (or `http://<your-server-ip>:5173` from another device on your network).

## Configuration

| Variable | Where | What it does |
| --- | --- | --- |
| `LITTERBOT_USERNAME` | `server/.env` | Your Whisker account email |
| `LITTERBOT_PASSWORD` | `server/.env` | Your Whisker account password |
| `PUBLIC_WEB_SOCKET_URL` | `client/.env` | WebSocket URL the browser uses for live robot updates |
| `SERVER_ENDPOINT` | `client/.env` | Backend base URL the frontend proxies API calls to |

## How it works

```
Browser ──► SvelteKit frontend (:5173) ──► FastAPI backend (:4323) ──► pylitterbot ──► Whisker cloud ──► your robots
                     ▲                              │
                     └──── WebSocket live updates ──┘
```

- The page loads robot data from `GET /api/robots` and then stays live over the `/api/ws` WebSocket.
- Clean and light actions go through SvelteKit proxy routes, not directly to the backend:
  - `POST /api/robot/<serial>/clean`
  - `POST /api/robot/<serial>/light?mode=on|off|auto`
- Those proxy routes live under `client/src/routes/api/robot/[serial]/` — `[serial]` is a literal folder name (SvelteKit fills it in from the URL). Don't create one folder per serial number; one `[serial]` folder covers every robot.

## Night-light modes

The LR4/LR5 night light is a **mode**, not a simple on/off switch — that's why the UI is a dropdown instead of a toggle:

- **On** — light stays on.
- **Off** — light stays off.
- **Auto** — the robot decides based on its light sensor.

(An earlier version used a toggle button. It didn't work reliably: on the LR4, the library call for "on" actually maps to the Auto command, so the button kept putting the light back to Auto. The dropdown sends the exact mode you pick.)

## Troubleshooting

- **Clean / light controls do nothing (404s in the dev-server log):** the proxy routes are missing. They must be at `client/src/routes/api/robot/[serial]/clean/+server.ts` and `.../light/+server.ts` — note singular `robot`, not `robots` (that's only the list endpoint), and the literal `[serial]` folder name. Restart the dev server after adding them.
- **You edited `server/main.py` and nothing changed:** restart the backend (`Ctrl+C`, then `python main.py`). The frontend hot-reloads on its own; the backend does not.
- **The dev server "just sits there":** that's normal. `pnpm run dev` is a server — it waits for browser requests. Open a second terminal tab for other commands.
- **`[404] GET /favicon.ico` in the dev log:** harmless — there's no favicon file. Drop one into `client/static/` to silence it.
- **The light dropdown doesn't match the Whisker app right away:** the page refreshes robot state over the WebSocket every ~5 seconds, so give it a moment.
- **Buttons are greyed out:** the robot is offline. The controls only enable for robots reporting online.

## Credits

- [natekspencer/pylitterbot](https://github.com/natekspencer/pylitterbot) — the Python library that talks to the Whisker API.
- [engageintellect/litterbot](https://github.com/engageintellect/litterbot) — the original FastAPI + SvelteKit app this is derived from.
