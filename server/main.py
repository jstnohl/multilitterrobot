#!/usr/bin/env python3

from fastapi import FastAPI, WebSocket, HTTPException, Query, File, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from fastapi.middleware.cors import CORSMiddleware

import uvicorn

import asyncio
import json
import uuid

from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from pylitterbot import Account

import os

from typing import Optional

load_dotenv()

from pylitterbot.enums import BrightnessLevel, NightLightMode

try:
    from pylitterbot.robot import VALID_WAIT_TIMES
except ImportError:  # older pylitterbot without the constant
    VALID_WAIT_TIMES = (3, 7, 15, 30)


app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


username = os.getenv("LITTERBOT_USERNAME")
password = os.getenv("LITTERBOT_PASSWORD")

account: Optional[Account] = None

# ---------------------------------------------------------------------------
# Pets + visits (Kitties feature, v0.3.0) + per-robot last cat (v0.4.0)
#
# The app is open source, so NOTHING here is hard-coded to one household:
# pets.json starts empty and the owner adds their own cats through the page.
#
# pets.json  : [{id, name, weight, birthdate, color}]
#   weight    — usual weight in lbs, used for visit matching.
#   birthdate — "YYYY-MM-DD" or null; the page computes age from it, so the
#               age ticks up on its own as the cat gets older (Whisker does
#               the same). Null means "unknown" and age shows as a dash.
#   color     — hex colour for the cat's card accent and the graphs.
#               Auto-assigned from PALETTE when the owner picks none.
# visits.json: [{id, timestamp, serial, robot, weight, pet, ambiguous,
#                manual, matched_by}]
# events.json: [{id, timestamp, serial, robot, type, weight, pet,
#                ambiguous, note, visit_id}]
#   Everything the detector sees that is NOT a confident cat visit:
#   unmatched_arrival, ambiguous_arrival, unmatched_weight_change,
#   interruption, refill, back_to_back, auto_reset. The anomaly tab
#   (v071) reads this file; the main graph reads visits.json only.
#   pet is a name, or None when no pet matched. ambiguous is a list of names
#   when the weight fits more than one pet. manual is True when the owner
#   corrected the match by hand. matched_by is "weight", "last_cat",
#   "ambiguous" or "none" — how the visit was attributed.
# last_cat.json: {serial: {pet_id, updated_at}}
#   Which cat last used each box. Set automatically when a visit is matched
#   confidently, set by hand from the robot card ("Last used by"), and
#   updated whenever the owner corrects a visit. It is the tie-breaker:
#   when a visit's weight fits two cats and one of them is the box's last
#   cat, that cat wins instead of the visit going ambiguous.
#
# Matching rule: nearest pet within MATCH_TOLERANCE lbs. If two pets are
# within tolerance and the closest is not at least AMBIGUITY_GAP lbs closer
# than the runner-up, the visit is ambiguous — UNLESS one of the candidates
# is the box's last cat, in which case the last cat wins. A forced wrong
# guess is still never made; when the last cat is not among the candidates
# the visit stays ambiguous and the owner corrects it.
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
PETS_FILE = BASE_DIR / "pets.json"
VISITS_FILE = BASE_DIR / "visits.json"
LAST_CAT_FILE = BASE_DIR / "last_cat.json"
BOX_COLORS_FILE = BASE_DIR / "box_colors.json"
EVENTS_FILE = BASE_DIR / "events.json"
CLEAN_SINCE_FILE = BASE_DIR / "clean_since.json"
SETTINGS_FILE = BASE_DIR / "settings.json"
PET_PHOTOS_FILE = BASE_DIR / "pet_photos.json"
PET_PHOTOS_DIR = BASE_DIR / "pet_photos"
REFILLS_FILE = BASE_DIR / "refills.json"
DRAWER_HISTORY_FILE = BASE_DIR / "drawer_history.json"


def load_clean_since():
    """Load clean_since.json ({serial: ISO timestamp}); {} when missing
    or unreadable. Entries for boxes no longer in ROBOT_CLEAN are
    dropped by the loop on its next poll."""
    try:
        with open(CLEAN_SINCE_FILE) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        out = {}
        for serial, ts in data.items():
            try:
                dt = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            out[serial] = dt
        return out
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_clean_since():
    """Save clean_since.json ({serial: ISO timestamp})."""
    with open(CLEAN_SINCE_FILE, "w") as f:
        json.dump({s: dt.isoformat() for s, dt in clean_since.items()}, f)

MATCH_TOLERANCE = 0.5  # lbs — a visit must be within this of a pet's weight
AMBIGUITY_GAP = 0.5     # lbs — closest must beat runner-up by this to win
MAX_VISITS = 500        # keep the log bounded; oldest entries drop off
CLEAN_TIMEOUT_SECONDS = 600    # a clean cycle takes ~2-3 min; ROBOT_CLEAN past this is stuck
CLEAN_RECENT_VISIT_SECONDS = 3600  # don't re-log a visit recorded within the last hour
WEIGHT_CHANGE_THRESHOLD = 0.5  # lb; a bigger swing mid-detection = a different cat stepped on
SETTLE_TOLERANCE = 0.2  # lb; a weight must hold within this across polls to count as settled
SETTLE_POLLS = 2        # consecutive polls at a settled weight before an arrival logs
MAX_EVENTS = 500        # keep the events log bounded; oldest entries drop off

# Distinct default colours, used in order when a pet is added without one.
PALETTE = ["#f97316", "#38bdf8", "#a78bfa", "#34d399", "#f472b6", "#facc15"]


def load_pets():
    try:
        with open(PETS_FILE) as f:
            pets = json.load(f)
        if isinstance(pets, list):
            return pets
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    # Open-source default: no cats hard-coded. The owner adds their own
    # through the "Add kitty?" form on the page.
    save_pets([])
    return []


def save_pets(pets):
    with open(PETS_FILE, "w") as f:
        json.dump(pets, f, indent=2)


def load_visits():
    try:
        with open(VISITS_FILE) as f:
            visits = json.load(f)
        if isinstance(visits, list):
            return visits
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def enrich_pets_with_average(pets, visits):
    """Add average_weight to each pet: input weight + all AUTOMATIC
    scale-measured visit weights, / (1 + number of auto visits), rounded
    to 1 decimal. Manual visits are excluded (they just repeat the input
    weight). A cat with no auto visits keeps average_weight == input weight.
    Matching still uses the input weight; the average is display-only."""
    by_name = {}
    for v in visits or []:
        if v.get("manual"):
            continue
        name = v.get("pet")
        w = v.get("weight")
        if name and isinstance(w, (int, float)):
            by_name.setdefault(name, []).append(float(w))
    out = []
    for pet in pets:
        p = dict(pet)
        vals = []
        base = pet.get("weight")
        if isinstance(base, (int, float)):
            vals.append(float(base))
        vals.extend(by_name.get(pet.get("name"), []))
        p["average_weight"] = round(sum(vals) / len(vals), 1) if vals else None
        out.append(p)
    return out


def save_visits(visits):
    with open(VISITS_FILE, "w") as f:
        json.dump(visits[-MAX_VISITS:], f, indent=2)


def load_last_cat():
    """{serial: {pet_id, updated_at}} — which cat last used each box."""
    try:
        with open(LAST_CAT_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def save_last_cat(data):
    with open(LAST_CAT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def pet_by_id(pets, pet_id):
    for pet in pets:
        if pet.get("id") == pet_id:
            return pet
    return None


def last_cat_name_for(serial, pets):
    """The last cat's name for a box, or None if unset / pet deleted."""
    entry = load_last_cat().get(serial)
    if not entry:
        return None
    pet = pet_by_id(pets, entry.get("pet_id"))
    return pet["name"] if pet else None


def set_last_cat(serial, pet_id):
    """Record which cat last used a box. pet_id None clears it."""
    data = load_last_cat()
    if pet_id is None:
        data.pop(serial, None)
    else:
        data[serial] = {
            "pet_id": pet_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    save_last_cat(data)


# ---------------------------------------------------------------------------
# Box colours — the ring around each dot on the graph says which box the
# visit was on (the dot's fill is the cat, the ring is the box; the trend
# line stays the cat's colour). box_colors.json is {serial: "#rrggbb"},
# set by the owner from the gear on each robot card. Defaults come from
# the serial, so they are stable no matter what order the boxes show up
# in. The palette is dark and muted on purpose — nothing like the bright
# kitty colours — so a ring never looks like a cat.
# ---------------------------------------------------------------------------

DEFAULT_BOX_COLORS = ["#1e40af", "#dc2626", "#065f46", "#92400e", "#4c1d95", "#334155"]


def load_box_colors():
    try:
        with open(BOX_COLORS_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def save_box_colors(data):
    with open(BOX_COLORS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Per-robot local settings (v074, 0.6.13): things the Whisker API does not
# expose, kept in settings.json keyed by serial.
#   filter_replaced: "YYYY-MM-DD" the carbon filter was last replaced
#   litter_type: free text, e.g. "clay", "crystal"
#   floor_surface: free text, e.g. "hardwood", "carpet"
# ---------------------------------------------------------------------------
def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_pet_photos():
    try:
        with open(PET_PHOTOS_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def save_pet_photos(data):
    with open(PET_PHOTOS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def default_box_color(serial):
    h = 0
    for ch in str(serial):
        h = (h * 31 + ord(ch)) % (2 ** 31)
    return DEFAULT_BOX_COLORS[h % len(DEFAULT_BOX_COLORS)]


def effective_box_colors():
    """{serial: color} for every box the backend knows about."""
    colors = load_box_colors()
    out = {}
    if account and account.robots:
        for robot in account.robots:
            out[robot.serial] = colors.get(robot.serial) or default_box_color(robot.serial)
    for serial, color in colors.items():
        out.setdefault(serial, color)
    return out


def match_pet(weight, pets, last_cat_name=None):
    """Match a visit weight to a pet.

    Returns (pet_name_or_None, ambiguous_names_list, matched_by).
    weight may be None (no scale reading) -> (None, [], "none").
    matched_by is "weight" (clear winner), "last_cat" (tie broken by the
    box's last cat), "ambiguous" (weight fits two or more), or "none".
    """
    if weight is None:
        return None, [], "none"
    scored = []
    for pet in pets:
        try:
            dist = abs(float(weight) - float(pet["weight"]))
        except (TypeError, ValueError, KeyError):
            continue
        if dist <= MATCH_TOLERANCE:
            scored.append((dist, pet["name"]))
    if not scored:
        return None, [], "none"
    scored.sort()
    if len(scored) == 1:
        return scored[0][1], [], "weight"
    # Two or more in range: closest wins only if clearly closer.
    if scored[0][0] + AMBIGUITY_GAP < scored[1][0]:
        return scored[0][1], [], "weight"
    # Tie — the box's last cat breaks it, if it is one of the candidates.
    names = [name for _, name in scored]
    if last_cat_name and last_cat_name in names:
        return last_cat_name, [], "last_cat"
    return None, names, "ambiguous"


def pair_sum_match(weight, pets):
    """Match a weight to TWO pets on the box at once.

    Returns (pet1_dict, pet2_dict) whose combined input weights match
    `weight` within MATCH_TOLERANCE, or None. The closest pair wins;
    sums here are 14.2 / 15.0 / 16.0, so a reading can sit within
    tolerance of two pairs at the boundary (e.g. 14.6) -- then the
    first-closest in pet order wins, and the anomaly tab lets Justin
    correct it. weight may be None -> None.
    """
    if weight is None:
        return None
    best = None
    best_d = None
    for i, p1 in enumerate(pets):
        for p2 in pets[i + 1:]:
            try:
                s = float(p1["weight"]) + float(p2["weight"])
                d = abs(float(weight) - s)
            except (TypeError, ValueError, KeyError):
                continue
            if d <= MATCH_TOLERANCE and (best_d is None or d < best_d):
                best_d = d
                best = (p1, p2)
    return best


async def connect_account():
    global account

    account = Account()

    await account.connect(username=username, password=password, load_robots=True)


async def disconnect_account():
    global account

    if account:
        await account.disconnect()

        account = None


def get_robot(serial: str = None):
    if not account or not account.robots:
        return None

    if serial:
        for robot in account.robots:
            if robot.serial == serial:
                return robot
        return None

    return account.robots[0]


_drawer_est_cache = {}  # serial -> (computed_at_epoch, days_or_None)


def drawer_full_in_days(serial, current_level):
    """Estimate days until the waste drawer is full, from the recorded
    drawer-level history. Returns an int, or None when there is not enough
    history yet (needs >=24h and a rising level). Cached 15 minutes per
    box so /api/robots + the WebSocket don't re-read the file."""
    if current_level is None:
        return None
    now_epoch = datetime.now(timezone.utc).timestamp()
    cached = _drawer_est_cache.get(serial)
    if cached and (now_epoch - cached[0]) < 900:
        return cached[1]
    result = None
    hist = load_drawer_history()
    samples = hist.get(serial, [])
    # Only use samples after the last big drop (the drawer was emptied).
    start = 0
    for idx in range(1, len(samples)):
        if samples[idx].get("level", 0) < samples[idx - 1].get("level", 0) - 10:
            start = idx
    samples = samples[start:]
    if len(samples) >= 2:
        try:
            t0 = datetime.fromisoformat(samples[0]["t"])
            t1 = datetime.fromisoformat(samples[-1]["t"])
            days = (t1 - t0).total_seconds() / 86400
            rise = samples[-1].get("level", 0) - samples[0].get("level", 0)
            if days >= 1 and rise > 0:
                rate = rise / days
                remaining = 100 - current_level
                result = 0 if remaining <= 0 else max(1, round(remaining / rate))
        except (KeyError, ValueError):
            result = None
    _drawer_est_cache[serial] = (now_epoch, result)
    return result



def serialize_robot(robot):
    """Safely turn a robot object into a JSON-friendly dict"""
    data = robot.__dict__.get("_data", {})

    return {
        "serial": robot.serial,
        "name": getattr(robot, "name", data.get("name", "Unknown")),
        "is_online": getattr(robot, "is_online", data.get("isOnline", False)),
        "status": data.get("robotStatus"),
        "drawer_level": data.get("DFILevelPercent"),
        "drawer_full_in_days": drawer_full_in_days(robot.serial, data.get("DFILevelPercent")),
        "litter_level_state": data.get("litterLevelState"),
        "is_full": data.get("isDFIFull"),
        "cat_weight": data.get("catWeight"),
        "weight_sensor": data.get("weightSensor"),
        "smart_weight_enabled": data.get("smartWeightEnabled"),
        "scoops_saved": data.get("scoopsSavedCount"),
        "cycles": data.get("DFINumberOfCycles"),
        "night_light": data.get("nightLightActive"),
        "night_light_mode": data.get("nightLightMode"),
        "wifi_rssi": data.get("wifiRssi"),
        "raw": {k: (v if isinstance(v, (dict, list, str, int, float, bool, type(None))) else str(v))
                for k, v in robot.__dict__.items()},
    }


@app.on_event("startup")
async def startup_event():
    await connect_account()
    global detection_task
    detection_task = asyncio.create_task(detection_loop())


@app.on_event("shutdown")
async def shutdown_event():
    global detection_task
    if detection_task:
        detection_task.cancel()
        try:
            await detection_task
        except asyncio.CancelledError:
            pass
        detection_task = None
    await disconnect_account()


@app.get("/")
async def root():
    return {
        "msg": "litterbot multi-robot backend",
        "version": "0.6.30",
        "robots_connected": len(account.robots) if account else 0
    }


@app.get("/api/robots")
async def get_robots():
    if not account or not account.robots:
        return []

    return [serialize_robot(r) for r in account.robots]


@app.get("/api/robot/{serial}")
async def get_robot_detail(serial: str):
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    return serialize_robot(robot)


@app.post("/api/robot/{serial}/reset")
async def reset_robot(serial: str):
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    await robot.reset()
    return {"ok": True}


@app.post("/api/robot/{serial}/clean")
async def start_clean(serial: str):
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    await robot.start_cleaning()

    return {"msg": "Cleaning started", "serial": serial}


@app.post("/api/robot/{serial}/light")
async def set_light_mode(serial: str, mode: str = Query(...)):
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    modes = {"on": NightLightMode.ON, "off": NightLightMode.OFF, "auto": NightLightMode.AUTO}

    if mode.lower() not in modes:
        raise HTTPException(status_code=400, detail="mode must be on, off, or auto")

    await robot.set_night_light_mode(modes[mode.lower()])

    return {"msg": f"Night light mode set to {mode}", "serial": serial}


@app.post("/api/robot/{serial}/wait-time")
async def set_wait_time(serial: str, body: dict):
    """Set the clean-cycle wait time (cycle delay), in minutes."""
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    try:
        minutes = int(body.get("minutes"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="minutes must be a number")

    if minutes not in VALID_WAIT_TIMES:
        raise HTTPException(status_code=400,
                            detail=f"minutes must be one of {list(VALID_WAIT_TIMES)}")

    await robot.set_wait_time(minutes)

    return {"msg": f"Cycle delay set to {minutes} minutes", "serial": serial}


@app.post("/api/robot/{serial}/panel-lock")
async def set_panel_lock(serial: str, body: dict):
    """Lock or unlock the robot's front-panel buttons."""
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="enabled must be true or false")

    await robot.set_panel_lockout(enabled)

    return {"msg": f"Panel lock {'enabled' if enabled else 'disabled'}", "serial": serial}


@app.post("/api/robot/{serial}/sleep-mode")
async def set_sleep_mode(serial: str, body: dict):
    """Turn sleep mode on or off (toggles the per-weekday schedule
    already set in the Whisker app; the schedule itself is edited there)."""
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="enabled must be true or false")

    await robot.set_sleep_mode(enabled)

    return {"msg": f"Sleep mode {'enabled' if enabled else 'disabled'}", "serial": serial}


@app.get("/api/robot/{serial}/settings")
async def get_robot_settings(serial: str):
    """Current settings for one robot: live robot state plus the local
    settings.json fields."""
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    local = load_settings().get(serial, {})
    return {
        "serial": serial,
        "wait_time_minutes": getattr(robot, "clean_cycle_wait_time_minutes", None),
        "valid_wait_times": list(VALID_WAIT_TIMES),
        "panel_lock_enabled": getattr(robot, "panel_lock_enabled", None),
        "sleep_mode_enabled": getattr(robot, "sleep_mode_enabled", None),
        "night_light_mode": getattr(robot, "night_light_mode", None),
        "night_light_brightness": getattr(robot, "night_light_brightness", None),
        "night_light_level": getattr(getattr(robot, "night_light_level", None), "name", None),
        "panel_brightness": getattr(getattr(robot, "panel_brightness", None), "name", None),
        "filter_replaced": local.get("filter_replaced"),
        "litter_type": local.get("litter_type"),
        "floor_surface": local.get("floor_surface"),
    }


@app.post("/api/robot/{serial}/settings")
async def post_robot_settings(serial: str, body: dict):
    """Save the local (app-side) settings for one robot. Only the three
    known fields are stored; anything else is ignored."""
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    settings = load_settings()
    record = settings.get(serial, {})
    for key in ("filter_replaced", "litter_type", "floor_surface"):
        if key in body:
            record[key] = body[key]
    settings[serial] = record
    save_settings(settings)

    return {"msg": "Settings saved", "serial": serial, "settings": record}


@app.post("/api/robot/{serial}/night-light-brightness")
async def set_night_light_brightness(serial: str, body: dict):
    """Set the globe (night) light brightness: 25 Low, 50 Medium,
    100 High. LR4 accepts only these three values (BrightnessLevel).
    The cloud queues the command, so the value may take a moment to show."""
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    try:
        brightness = int(body.get("brightness"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="brightness must be 25, 50, or 100 (Low, Medium, High)")
    if brightness not in (25, 50, 100):
        raise HTTPException(status_code=400, detail="brightness must be 25, 50, or 100 (Low, Medium, High)")

    await robot.set_night_light_brightness(brightness)
    return {"msg": "Night light brightness set", "serial": serial, "brightness": brightness}


@app.post("/api/robot/{serial}/panel-brightness")
async def set_panel_brightness(serial: str, body: dict):
    """Set the control-panel light brightness: LOW, MEDIUM, or HIGH.
    The cloud queues the command, so the value may take a moment to show."""
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    level = body.get("level")
    if level not in ("LOW", "MEDIUM", "HIGH"):
        raise HTTPException(status_code=400, detail="level must be LOW, MEDIUM, or HIGH")

    await robot.set_panel_brightness(BrightnessLevel[level])
    return {"msg": "Panel brightness set", "serial": serial, "level": level}


@app.get("/api/pet-photos")
async def get_pet_photos():
    """{pet_id: filename} for every cat with a profile photo."""
    return load_pet_photos()


@app.post("/api/pets/{pet_id}/photo")
async def upload_pet_photo(pet_id: str, file: UploadFile = File(...)):
    """Upload a profile photo for one cat (image, up to 5 MB). Stored
    under pet_photos/ with the mapping in pet_photos.json -- never on
    the pet record itself, so a colour change cannot clobber it."""
    pets = load_pets()
    if pet_by_id(pets, pet_id) is None:
        raise HTTPException(status_code=404, detail="Pet not found")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="file must be an image")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="photo must be under 5 MB")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"
    PET_PHOTOS_DIR.mkdir(exist_ok=True)
    filename = f"{pet_id}{ext}"
    for old in PET_PHOTOS_DIR.glob(f"{pet_id}.*"):
        if old.name != filename:
            old.unlink(missing_ok=True)
    (PET_PHOTOS_DIR / filename).write_bytes(data)
    photos = load_pet_photos()
    photos[pet_id] = filename
    save_pet_photos(photos)
    return {"pet_id": pet_id, "photo": filename}


@app.get("/api/pets/{pet_id}/photo")
async def get_pet_photo(pet_id: str):
    """Serve one cat's profile photo."""
    photos = load_pet_photos()
    filename = photos.get(pet_id)
    if not filename:
        raise HTTPException(status_code=404, detail="No photo for this pet")
    path = PET_PHOTOS_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="No photo for this pet")
    return FileResponse(path)


@app.delete("/api/pets/{pet_id}/photo")
async def delete_pet_photo(pet_id: str):
    """Remove one cat's profile photo (file + mapping)."""
    photos = load_pet_photos()
    filename = photos.pop(pet_id, None)
    if filename:
        (PET_PHOTOS_DIR / Path(filename).name).unlink(missing_ok=True)
        save_pet_photos(photos)
    return {"msg": "Photo removed", "pet_id": pet_id}


@app.get("/api/robot/{serial}/firmware")
async def get_firmware(serial: str):
    """Current firmware state for one robot: installed version, latest
    available version, whether an update is pending, and whether one is
    already in progress."""
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    if not hasattr(robot, "has_firmware_update"):
        return {"serial": serial,
                "installed": getattr(robot, "firmware", None),
                "latest": None, "has_update": None,
                "update_triggered": getattr(robot, "firmware_update_triggered", False),
                "note": "this pylitterbot version does not expose firmware checks"}

    has_update = await robot.has_firmware_update()
    if has_update:
        latest = await robot.get_latest_firmware()
    else:
        latest = getattr(robot, "firmware", None)
    if latest != getattr(robot, "firmware", None) and not getattr(robot, "firmware_update_triggered", False):
        latest = await robot.get_latest_firmware(True)
        if not await robot.has_firmware_update():
            latest = getattr(robot, "firmware", None)
    return {
        "serial": serial,
        "installed": getattr(robot, "firmware", None),
        "latest": latest,
        "has_update": has_update,
        "update_triggered": getattr(robot, "firmware_update_triggered", False),
    }


@app.post("/api/robot/{serial}/firmware/update")
async def update_firmware(serial: str):
    """Trigger a firmware update (Litter-Robot 4 only). Takes up to 15
    minutes; the box may go offline briefly and its WiFi may need a
    press of the Connect button afterwards."""
    robot = get_robot(serial)

    if not robot:
        raise HTTPException(status_code=404, detail="Robot not found")

    if not hasattr(robot, "has_firmware_update"):
        raise HTTPException(status_code=501, detail="this pylitterbot version does not expose firmware updates")

    if not await robot.has_firmware_update():
        raise HTTPException(status_code=409, detail="no firmware update available")

    if not await robot.update_firmware():
        raise HTTPException(status_code=502, detail="could not start the firmware update")

    return {"msg": "Firmware update started", "serial": serial}


# ---------------------------------------------------------------------------
# Per-robot last cat — which cat last used each box. The owner sets it from
# the robot card; the backend also sets it on every confidently matched
# visit and on every manual correction, so it keeps dialling itself in.
# ---------------------------------------------------------------------------

@app.get("/api/robot/{serial}/last-cat")
async def get_last_cat(serial: str):
    pets = load_pets()
    entry = load_last_cat().get(serial)
    if not entry:
        return {"serial": serial, "pet_id": None, "pet_name": None, "updated_at": None}
    pet = pet_by_id(pets, entry.get("pet_id"))
    return {
        "serial": serial,
        "pet_id": entry.get("pet_id"),
        "pet_name": pet["name"] if pet else None,
        "updated_at": entry.get("updated_at"),
    }


def log_manual_visit(serial, pet):
    """Log a manual attribution as a visit, so it shows on the graph.

    Weight is the pet's usual weight (an estimate, flagged manual) — the
    point is the time: when the owner says a cat used a box, that moment
    is a data point.

    If the latest visit for this box is itself a manual attribution,
    correct it in place instead of adding a second dot — the dropdown
    says who used the box last, so changing it fixes that record.
    Real cycle visits are never rewritten.
    """
    visits = load_visits()
    now = datetime.now(timezone.utc).isoformat()
    for v in reversed(visits):
        if v.get("serial") != serial:
            continue
        if v.get("matched_by") == "manual":
            v["timestamp"] = now
            v["weight"] = pet.get("weight")
            v["pet"] = pet.get("name")
            v["ambiguous"] = []
            v["manual"] = True
            save_visits(visits)
            return
        break
    robot_name = serial
    for v in reversed(visits):
        if v.get("serial") == serial and v.get("robot"):
            robot_name = v["robot"]
            break
    visits.append({
        "id": uuid.uuid4().hex[:8],
        "timestamp": now,
        "serial": serial,
        "robot": robot_name,
        "weight": pet.get("weight"),
        "pet": pet.get("name"),
        "ambiguous": [],
        "manual": True,
        "matched_by": "manual",
        "type": None,
    })
    save_visits(visits)


@app.post("/api/robot/{serial}/last-cat")
async def post_last_cat(serial: str, body: dict):
    """Set the box's last cat. {"pet_id": "<id>"} or {"pet_id": null} to clear.

    Setting a cat also logs a manual visit at this moment (usual weight,
    flagged manual), so the attribution shows on the graph and in the
    visits table. Clearing logs nothing.
    """
    pet_id = body.get("pet_id") or None
    pets = load_pets()
    if pet_id is not None and pet_by_id(pets, pet_id) is None:
        raise HTTPException(status_code=404, detail="Pet not found")
    set_last_cat(serial, pet_id)
    if pet_id is not None:
        pet = pet_by_id(pets, pet_id)
        if pet:
            log_manual_visit(serial, pet)
    return await get_last_cat(serial)


# ---------------------------------------------------------------------------
# Box colours API — the ring colour for each box on the graph.
# ---------------------------------------------------------------------------

@app.get("/api/box-colors")
async def get_box_colors():
    return effective_box_colors()


@app.post("/api/box-colors")
async def post_box_color(body: dict):
    """Set one box's colour. {"serial": "...", "color": "#rrggbb"}.
    {"color": null} clears the override back to the default."""
    import re

    serial = str(body.get("serial") or "").strip()
    color = body.get("color")
    if not serial:
        raise HTTPException(status_code=400, detail="serial is required")
    colors = load_box_colors()
    if color is None:
        colors.pop(serial, None)
    else:
        color = str(color).strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise HTTPException(status_code=400, detail="color must be #rrggbb")
        colors[serial] = color
    save_box_colors(colors)
    return {"serial": serial, "color": effective_box_colors().get(serial)}


# ---------------------------------------------------------------------------
# Pets API
# ---------------------------------------------------------------------------

@app.get("/api/pets")
async def get_pets():
    return enrich_pets_with_average(load_pets(), load_visits())


@app.post("/api/pets")
async def add_pet(pet: dict):
    name = str(pet.get("name", "")).strip()
    try:
        weight = float(pet.get("weight"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="weight must be a number")

    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    # Birthdate is optional; when given it must be a real YYYY-MM-DD date.
    # Age is computed from it on the page, so it stays current on its own.
    birthdate = pet.get("birthdate") or None
    if birthdate:
        try:
            datetime.strptime(str(birthdate), "%Y-%m-%d")
            birthdate = str(birthdate)
        except ValueError:
            raise HTTPException(status_code=400, detail="birthdate must be YYYY-MM-DD")

    # Colour is optional; a bad value (or none) gets the next palette colour.
    import re

    color = str(pet.get("color") or "").strip()
    pets = load_pets()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = PALETTE[len(pets) % len(PALETTE)]

    # Update path: if an id matches an existing pet, update it in place
    # (the colour gear on a kitty card posts the pet back with its id).
    # Otherwise fall through and create a new pet.
    pet_id = pet.get("id")
    if pet_id:
        for existing in pets:
            if existing.get("id") == pet_id:
                existing["name"] = name
                existing["weight"] = weight
                existing["birthdate"] = birthdate
                existing["color"] = color
                save_pets(pets)
                return existing

    new_pet = {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "weight": weight,
        "birthdate": birthdate,
        "color": color,
    }
    pets.append(new_pet)
    save_pets(pets)
    return new_pet


@app.delete("/api/pets")
async def delete_pet(id: str = Query(...)):
    pets = load_pets()
    kept = [p for p in pets if p.get("id") != id]
    if len(kept) == len(pets):
        raise HTTPException(status_code=404, detail="Pet not found")
    save_pets(kept)
    return {"msg": "Pet deleted", "id": id}


# ---------------------------------------------------------------------------
# Visits API
# ---------------------------------------------------------------------------

@app.get("/api/visits")
async def get_visits(limit: int = Query(100, ge=1, le=500)):
    visits = load_visits()
    return list(reversed(visits))[:limit]


@app.post("/api/visits/reassign")
async def reassign_visit(body: dict):
    """Correct a visit's pet by hand. pet may be a name or None (Unknown).

    The correction also retrains that box's last cat, so the next ambiguous
    visit on the same box leans toward the corrected cat.
    """
    visit_id = body.get("id")
    pet = body.get("pet")  # name string, or None
    visits = load_visits()
    for visit in visits:
        if visit.get("id") == visit_id:
            visit["pet"] = pet
            visit["ambiguous"] = []
            save_visits(visits)
            # Retrain the box: the corrected cat is now its last cat.
            pets = load_pets()
            if pet:
                match = next((p for p in pets if p["name"] == pet), None)
                set_last_cat(visit.get("serial"), match["id"] if match else None)
            else:
                set_last_cat(visit.get("serial"), None)
            return visit
    raise HTTPException(status_code=404, detail="Visit not found")


@app.delete("/api/visits/{visit_id}")
async def delete_visit(visit_id: str):
    """Delete one visit (e.g. an erroneous manual/logged visit)."""
    visits = load_visits()
    kept = [v for v in visits if v.get("id") != visit_id]
    if len(kept) == len(visits):
        raise HTTPException(status_code=404, detail="Visit not found")
    save_visits(kept)
    return {"deleted": visit_id}


@app.post("/api/visits/{visit_id}/type")
async def set_visit_type(visit_id: str, body: dict):
    """Mark a visit pee/poop (or clear it). {"type": "pee"|"poop"|null}.

    Manual marking until the LR5 WasteID auto-detect lands; the LR4
    has no waste-type sensor, so its visits start untyped (None)."""
    visit_type = (body or {}).get("type")
    if visit_type not in ("pee", "poop", None):
        raise HTTPException(status_code=400, detail='type must be "pee", "poop" or null')
    visits = load_visits()
    visit = next((v for v in visits if v.get("id") == visit_id), None)
    if visit is None:
        raise HTTPException(status_code=404, detail="Visit not found")
    visit["type"] = visit_type
    save_visits(visits)
    return {"msg": "Visit type set", "id": visit_id, "type": visit_type}


_METRICS_START_TS = datetime.now(timezone.utc).timestamp()


@app.get("/api/metrics")
async def prometheus_metrics():
    """Prometheus exposition format, hand-rolled (no extra dependency).

    Visits, weight, anomalies, waste levels and robot health, all
    labelled by pet / robot so Grafana can filter per box or per cat.
    Scrape target: http://<host>/api/metrics (proxied by nginx)."""
    visits = load_visits()
    events = load_events()
    pets = load_pets()

    def esc(s):
        return str(s).replace("\\", "\\\\").replace('"', '\\"')

    now_ts = datetime.now(timezone.utc).timestamp()

    counts = {}
    last = {}
    type_counts = {}
    for v in visits:
        pet = v.get("pet") or "Unknown"
        robot = v.get("robot") or v.get("serial") or "unknown"
        key = (pet, robot)
        counts[key] = counts.get(key, 0) + 1
        t = v.get("type") or "unmarked"
        type_counts[t] = type_counts.get(t, 0) + 1
        ts = None
        try:
            ts = datetime.fromisoformat(str(v.get("timestamp")).replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = None
        if ts is not None and (key not in last or ts > last[key][0]):
            last[key] = (ts, v.get("weight"))

    event_counts = {}
    for ev in events:
        t = ev.get("type") or "unknown"
        res = ev.get("resolution") or "unresolved"
        key = (t, res)
        event_counts[key] = event_counts.get(key, 0) + 1

    # Live robot state, best-effort: if the account is not up yet the
    # visit/event metrics below still serve.
    live = []
    try:
        live = [serialize_robot(r) for r in account.robots]
    except Exception:
        live = []

    lines = []
    lines.append("# HELP litterbot_visits_total Total logged visits by pet and robot")
    lines.append("# TYPE litterbot_visits_total counter")
    for (pet, robot), n in sorted(counts.items()):
        lines.append(f'litterbot_visits_total{{pet="{esc(pet)}",robot="{esc(robot)}"}} {n}')
    lines.append("# HELP litterbot_visits_by_type_total Logged visits by type (pee/poop/unmarked)")
    lines.append("# TYPE litterbot_visits_by_type_total counter")
    for t, n in sorted(type_counts.items()):
        lines.append(f'litterbot_visits_by_type_total{{type="{esc(t)}"}} {n}')
    lines.append("# HELP litterbot_last_visit_weight_lbs Weight of the most recent visit by pet and robot")
    lines.append("# TYPE litterbot_last_visit_weight_lbs gauge")
    for (pet, robot), (ts, w) in sorted(last.items()):
        if w is not None:
            lines.append(f'litterbot_last_visit_weight_lbs{{pet="{esc(pet)}",robot="{esc(robot)}"}} {w}')
    lines.append("# HELP litterbot_last_visit_timestamp Unix time of the most recent visit by pet and robot")
    lines.append("# TYPE litterbot_last_visit_timestamp gauge")
    for (pet, robot), (ts, w) in sorted(last.items()):
        lines.append(f'litterbot_last_visit_timestamp{{pet="{esc(pet)}",robot="{esc(robot)}"}} {ts}')
    lines.append("# HELP litterbot_seconds_since_last_visit Seconds since the last logged visit by pet and robot")
    lines.append("# TYPE litterbot_seconds_since_last_visit gauge")
    for (pet, robot), (ts, w) in sorted(last.items()):
        lines.append(f'litterbot_seconds_since_last_visit{{pet="{esc(pet)}",robot="{esc(robot)}"}} {now_ts - ts}')
    lines.append("# HELP litterbot_pet_input_weight_lbs Configured input weight per pet (reference line for the weight graph)")
    lines.append("# TYPE litterbot_pet_input_weight_lbs gauge")
    for p in pets:
        if p.get("weight") is not None:
            lines.append(f'litterbot_pet_input_weight_lbs{{pet="{esc(p.get("name"))}"}} {p.get("weight")}')
    lines.append("# HELP litterbot_pet_average_weight_lbs Running average weight per pet (input weight + automatic visit weights, manual visits excluded; same number the kitty cards show)")
    lines.append("# TYPE litterbot_pet_average_weight_lbs gauge")
    for p in enrich_pets_with_average(pets, visits):
        if p.get("average_weight") is not None:
            lines.append(f'litterbot_pet_average_weight_lbs{{pet="{esc(p.get("name"))}"}} {p.get("average_weight")}')
    lines.append("# HELP litterbot_events_total Logged detection events by type and resolution")
    lines.append("# TYPE litterbot_events_total counter")
    for (t, res), n in sorted(event_counts.items()):
        lines.append(f'litterbot_events_total{{type="{esc(t)}",resolution="{esc(res)}"}} {n}')
    lines.append("# HELP litterbot_uptime_seconds Backend uptime in seconds")
    lines.append("# TYPE litterbot_uptime_seconds gauge")
    lines.append(f"litterbot_uptime_seconds {now_ts - _METRICS_START_TS}")
    lines.append("# HELP litterbot_drawer_level_percent Waste drawer level (0-100)")
    lines.append("# TYPE litterbot_drawer_level_percent gauge")
    lines.append("# HELP litterbot_drawer_full Waste drawer full flag (1 = full)")
    lines.append("# TYPE litterbot_drawer_full gauge")
    lines.append("# HELP litterbot_litter_low Litter level low flag (1 = low)")
    lines.append("# TYPE litterbot_litter_low gauge")
    lines.append("# HELP litterbot_robot_online Robot online flag (1 = online)")
    lines.append("# TYPE litterbot_robot_online gauge")
    lines.append("# HELP litterbot_robot_status Robot status (1 = current status, labelled)")
    lines.append("# TYPE litterbot_robot_status gauge")
    lines.append("# HELP litterbot_scoops_saved_total Scoops saved, cumulative")
    lines.append("# TYPE litterbot_scoops_saved_total counter")
    lines.append("# HELP litterbot_cycles_total Clean cycles, cumulative")
    lines.append("# TYPE litterbot_cycles_total counter")
    lines.append("# HELP litterbot_wifi_rssi_dbm WiFi signal strength in dBm")
    lines.append("# TYPE litterbot_wifi_rssi_dbm gauge")
    for r in live:
        name = r.get("name") or r.get("serial") or "unknown"
        dl = r.get("drawer_level")
        if dl is not None:
            lines.append(f'litterbot_drawer_level_percent{{robot="{esc(name)}"}} {dl}')
        lines.append(f'litterbot_drawer_full{{robot="{esc(name)}"}} {1 if r.get("is_full") else 0}')
        lines.append(f'litterbot_litter_low{{robot="{esc(name)}"}} {1 if str(r.get("litter_level_state")) == "LOW" else 0}')
        lines.append(f'litterbot_robot_online{{robot="{esc(name)}"}} {1 if r.get("is_online") else 0}')
        st = r.get("status") or "unknown"
        lines.append(f'litterbot_robot_status{{robot="{esc(name)}",status="{esc(st)}"}} 1')
        sc = r.get("scoops_saved")
        if sc is not None:
            lines.append(f'litterbot_scoops_saved_total{{robot="{esc(name)}"}} {sc}')
        cy = r.get("cycles")
        if cy is not None:
            lines.append(f'litterbot_cycles_total{{robot="{esc(name)}"}} {cy}')
        rssi = r.get("wifi_rssi")
        if rssi is None:
            rssi = r.get("wifi_rssi")
        if rssi is None:
            rssi = r.get("wifiRssi")
        if rssi is not None:
            lines.append(f'litterbot_wifi_rssi_dbm{{robot="{esc(name)}"}} {rssi}')
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


# Background visit detection + stuck-clean auto-reset. This is the only
# detection loop in the app: it runs whether or not any page is open, and
# there is exactly one of it, so a visit can never be logged twice by two
# pages open at once. The WebSocket endpoint only broadcasts state.
cat_present = {}
current_weight = {}  # scale weight of the currently-open event, per robot
clean_since = load_clean_since()  # restored from clean_since.json (v073)
pending_weight = {}  # scale weight being settled, per robot (v070)
pending_polls = {}  # consecutive polls the pending weight has held (v070)
needs_clean = {}  # True once an arrival logged and no clean seen since (v070)
last_litter_state = {}  # last litterLevelState seen, per robot (v070)
window_open = {}  # a visit's cycle-delay window is open, per robot (v070)
window_weights = {}  # weights sampled in the open window, per robot (v070)
window_visit_id = {}  # visit the open window belongs to, per robot (v070)


# ---------------------------------------------------------------------------
# Events (v070, 0.6.9): everything the detector sees that is NOT a
# confident cat visit. events.json mirrors visits.json; the anomaly tab
# (v071) reads this file and the main graph reads visits.json only.
#   type: unmatched_arrival | ambiguous_arrival | unmatched_weight_change
#         | interruption | refill | back_to_back | auto_reset
# ---------------------------------------------------------------------------
def load_events():
    """Load events.json; [] when missing or unreadable."""
    try:
        with open(EVENTS_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_events(events):
    """Save events.json, keeping the newest MAX_EVENTS."""
    with open(EVENTS_FILE, "w") as f:
        json.dump(events[-MAX_EVENTS:], f)


def load_refills():
    """Load refills.json; [] when missing or unreadable."""
    try:
        with open(REFILLS_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_refills(refills):
    """Save refills.json."""
    with open(REFILLS_FILE, "w") as f:
        json.dump(refills, f)


def load_drawer_history():
    """Load drawer_history.json; {} when missing or unreadable."""
    try:
        with open(DRAWER_HISTORY_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_drawer_history(hist):
    """Save drawer_history.json."""
    with open(DRAWER_HISTORY_FILE, "w") as f:
        json.dump(hist, f)



def log_event(events, serial, robot_name, event_type, weight=None, pet=None,
              ambiguous=None, note=None, visit_id=None):
    """Append one event record to the in-memory events list."""
    events.append({
        "id": uuid.uuid4().hex[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "serial": serial,
        "robot": robot_name,
        "type": event_type,
        "weight": weight,
        "pet": pet,
        "ambiguous": ambiguous or [],
        "note": note,
        "visit_id": visit_id,
    })


def _open_window(serial, visit_id):
    """Open the cycle-delay window for a visit: weights sampled from now
    until the clean starts attach to this visit."""
    window_open[serial] = True
    window_visit_id[serial] = visit_id
    window_weights[serial] = []


def _close_window(serial, visits):
    """Close the cycle-delay window, attaching sampled weights to its
    visit. Returns True when a visit was updated."""
    if not window_open.get(serial):
        return False
    window_open[serial] = False
    visit_id = window_visit_id.pop(serial, None)
    samples = window_weights.pop(serial, [])
    if not visit_id:
        return False
    for v in reversed(visits):
        if v.get("id") == visit_id:
            v["window_weights"] = samples
            return True
    return False


@app.get("/api/events")
async def get_events(limit: int = Query(100, ge=1, le=500)):
    """List logged events, newest first. The anomaly tab (v071) reads this."""
    events = load_events()
    return list(reversed(events[-limit:]))


@app.post("/api/events/{event_id}/resolve")
async def resolve_event(event_id: str, body: dict):
    """Attribute an anomaly-tab event (v071): dismiss it, log it as a cat
    visit, or record it as a refill / maintenance. A cat visit also appends
    a real visit (matched_by "weight", counted as an automatic visit) and sets the box's last cat."""
    resolution = (body or {}).get("resolution")
    if resolution not in ("dismiss", "cat_visit", "refill", "maintenance"):
        raise HTTPException(status_code=400, detail="resolution must be dismiss, cat_visit, refill or maintenance")
    events = load_events()
    event = next((e for e in events if e.get("id") == event_id), None)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    if event.get("resolution"):
        raise HTTPException(status_code=409, detail=f"event already resolved as {event['resolution']}")
    if resolution == "cat_visit":
        pet_id = (body or {}).get("pet_id")
        pets = load_pets()
        pet = pet_by_id(pets, pet_id) if pet_id else None
        if pet is None:
            raise HTTPException(status_code=400, detail="cat_visit needs a valid pet_id")
        if event.get("weight") is None:
            raise HTTPException(status_code=400, detail="event has no weight to log as a visit")
        visits = load_visits()
        visit = {
            "id": uuid.uuid4().hex[:8],
            "timestamp": event["timestamp"],
            "serial": event["serial"],
            "robot": event.get("robot"),
            "weight": event["weight"],
            "pet": pet["name"],
            "ambiguous": False,
            "manual": False,
            "matched_by": "weight",
            "type": None,
        }
        visits.append(visit)
        save_visits(visits)
        set_last_cat(event["serial"], pet["id"])
        event["resolution"] = "cat_visit"
        event["resolved_pet"] = pet["name"]
        event["visit_id"] = visit["id"]
    elif resolution == "refill":
        # v084: record the refill (the event's weight is the litter added).
        refills = load_refills()
        refills.append({
            "id": uuid.uuid4().hex[:8],
            "timestamp": event["timestamp"],
            "serial": event["serial"],
            "robot": event.get("robot"),
            "weight_lbs": event.get("weight"),
            "source": "anomaly",
            "event_id": event["id"],
        })
        save_refills(refills)
        event["resolution"] = "refill"
    else:
        event["resolution"] = resolution
    save_events(events)
    return event
@app.get("/api/refills")
async def get_refills(serial: str = Query(None), limit: int = Query(100, ge=1, le=500)):
    """List litter refills, newest first. Filter by robot serial."""
    refills = load_refills()
    if serial:
        refills = [r for r in refills if r.get("serial") == serial]
    return list(reversed(refills[-limit:]))


@app.post("/api/refills")
async def post_refill(body: dict):
    """Log a litter refill (from the settings menu). Body: {serial, weight_lbs}."""
    serial = (body or {}).get("serial")
    weight = (body or {}).get("weight_lbs")
    if not serial:
        raise HTTPException(status_code=400, detail="serial is required")
    robot = get_robot(serial)
    if robot is None:
        raise HTTPException(status_code=404, detail="Robot not found")
    refills = load_refills()
    refill = {
        "id": uuid.uuid4().hex[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "serial": serial,
        "robot": getattr(robot, "name", None),
        "weight_lbs": weight if isinstance(weight, (int, float)) else None,
        "source": "manual",
        "event_id": None,
    }
    refills.append(refill)
    save_refills(refills)
    return refill



detection_task = None


async def detection_loop():
    """Refresh the robots, log visits on cat arrival, and auto-reset a box
    stuck in ROBOT_CLEAN. Runs forever (until cancelled).

    v070 (0.6.9): an arrival (or a mid-detection weight change) is only
    logged once the scale weight holds steady across SETTLE_POLLS
    consecutive polls (within SETTLE_TOLERANCE). The first, unsettled
    reading of a visit never logs -- that was the Nov 17 phantom 6.13 lb
    visit: the scale's first reading while a cat steps on, before it
    settles on the real weight. A weight change only counts as a second
    cat when the open event's weight was already stable, which the
    arrival gate guarantees (cat_present is only set on a stable log).
    Everything else the detector sees is logged to events.json instead
    of being silently dropped, so the owner can attribute it in the
    anomaly tab (v071): unmatched/ambiguous arrivals, unmatched weight
    changes, interruptions, refills, back-to-back arrivals, auto-resets.
    Weights sampled during the cycle-delay window (cat left, clean not
    yet started) attach to the visit as window_weights.
    """
    while True:
        try:
            if account and account.robots:
                # Refresh all robots
                for robot in account.robots:
                    try:
                        await robot.refresh()
                    except Exception:
                        pass

                # Detect visits by weight + status. A visit is logged when a
                # cat ARRIVES (status enters CAT_DETECT / CAT_DETECT_DELAY)
                # and the scale weight confidently matches a pet — even if
                # it's the same cat as last time. The old "only log on a
                # change of cat" rule missed back-to-back visits by the same
                # cat (Sally 2:17 PM Nov 15 never logged because the last
                # cat was already Sally from 5:06 AM). The per-robot
                # cat_present flag tracks whether we've already logged the
                # current arrival, so a sticky weight reading can't re-log.
                # (DFINumberOfCycles does not tick on the LR4, so the old
                # cycle-count detection never fired -- auto visits stayed 0.)
                pets = load_pets()
                visits = load_visits()
                events = load_events()
                drawer_hist = load_drawer_history()
                drawer_hist_dirty = False
                visits_dirty = False
                events_dirty = False
                now = datetime.now(timezone.utc)
                for robot in account.robots:
                    data = robot.__dict__.get("_data", {})
                    status = data.get("robotStatus")
                    weight = data.get("catWeight")
                    serial = robot.serial
                    robot_name = getattr(robot, "name", data.get("name", "Unknown"))
                    # v084: sample the drawer level (<=1/hour per box) for the fill-rate estimate.
                    _lvl = data.get("DFILevelPercent")
                    if _lvl is not None:
                        _s = drawer_hist.setdefault(serial, [])
                        _lt = None
                        if _s:
                            try:
                                _lt = datetime.fromisoformat(_s[-1]["t"])
                            except (KeyError, ValueError):
                                _lt = None
                        if (_lt is None or (now - _lt).total_seconds() >= 3600) and (not _s or _s[-1].get("level") != _lvl):
                            _s.append({"t": now.isoformat(), "level": _lvl})
                            drawer_hist[serial] = _s[-500:]
                            drawer_hist_dirty = True

                    # Litter refill: litterLevelState moving LOW -> OPTIMAL
                    # means someone topped the litter up (the level is
                    # measured during each clean cycle). First sighting
                    # just records the state; no event.
                    litter_state = data.get("litterLevelState")
                    if litter_state is not None:
                        prev_litter = last_litter_state.get(serial)
                        if prev_litter == "LOW" and litter_state == "OPTIMAL":
                            log_event(events, serial, robot_name, "refill", weight,
                                      note="litter level went LOW -> OPTIMAL")
                            events_dirty = True
                        last_litter_state[serial] = litter_state

                    # No cat on the box: clear the arrival flag.
                    if status not in ("ROBOT_CAT_DETECT", "ROBOT_CAT_DETECT_DELAY"):
                        # The cat stepped on and off before the scale ever
                        # settled: an interrupted arrival, not a visit.
                        if not cat_present.get(serial) and serial in pending_weight:
                            log_event(events, serial, robot_name, "interruption",
                                      pending_weight.get(serial),
                                      note="cat left before the scale settled")
                            events_dirty = True
                        cat_present[serial] = False
                        current_weight.pop(serial, None)
                        pending_weight.pop(serial, None)
                        pending_polls.pop(serial, None)
                        if status == "ROBOT_CLEAN":
                            # A clean cycle happened: the next arrival is
                            # not back-to-back, and the cycle-delay window
                            # for the last visit closes here.
                            needs_clean[serial] = False
                            if _close_window(serial, visits):
                                visits_dirty = True
                        elif window_open.get(serial) and weight is not None:
                            # Cycle-delay window: record the weight while
                            # waiting for the clean to start.
                            samples = window_weights.setdefault(serial, [])
                            if len(samples) < 60:
                                samples.append({"t": now.isoformat(), "w": weight})
                        continue

                    # Cat present but we already logged this arrival.
                    if cat_present.get(serial):
                        # Weight changed mid-detection? A different cat
                        # stepped on while the first was still (or just)
                        # there — log it as a new event instead of
                        # swallowing it. The new weight must settle first,
                        # same as an arrival: a mid-transition reading
                        # must not log.
                        prev = current_weight.get(serial)
                        if weight is None or prev is None:
                            continue
                        if abs(weight - prev) <= WEIGHT_CHANGE_THRESHOLD:
                            # No real change; a pending change fizzled
                            # (the weight moved back).
                            pending_weight.pop(serial, None)
                            pending_polls.pop(serial, None)
                            continue
                        pend = pending_weight.get(serial)
                        if pend is None:
                            pending_weight[serial] = weight
                            pending_polls[serial] = 1
                            continue
                        if abs(weight - pend) > SETTLE_TOLERANCE:
                            pending_weight[serial] = weight
                            pending_polls[serial] = 1
                            continue
                        pending_polls[serial] = pending_polls[serial] + 1
                        if pending_polls[serial] < SETTLE_POLLS:
                            continue
                        # Stable new weight: match it.
                        pending_weight.pop(serial, None)
                        pending_polls.pop(serial, None)
                        # match with NO last-cat tie-break: the
                        # last cat is the one that just left (the
                        # weight moved away from them), so letting
                        # it win a tie would hand the new event
                        # back to them.
                        pet, ambiguous, matched_by = match_pet(weight, pets, None)
                        if not pet and ambiguous:
                            # Ambiguous weight change: take the
                            # closest candidate (the weight moved
                            # away from the cat that just left, so
                            # closeness — not the last cat — decides).
                            best = None
                            best_d = None
                            for _p in pets:
                                if _p["name"] not in ambiguous:
                                    continue
                                try:
                                    _d = abs(float(weight) - float(_p["weight"]))
                                except (TypeError, ValueError, KeyError):
                                    continue
                                if best_d is None or _d < best_d:
                                    best_d = _d
                                    best = _p["name"]
                            if best:
                                pet, ambiguous, matched_by = best, [], "weight"
                        if pet:
                            visit_id = uuid.uuid4().hex[:8]
                            visits.append({
                                "id": visit_id,
                                "timestamp": now.isoformat(),
                                "serial": serial,
                                "robot": robot_name,
                                "weight": weight,
                                "pet": pet,
                                "ambiguous": ambiguous,
                                "manual": False,
                                "matched_by": matched_by,
                                "type": None,
                            })
                            match = next((p for p in pets if p["name"] == pet), None)
                            if match:
                                set_last_cat(serial, match["id"])
                            current_weight[serial] = weight
                            visits_dirty = True
                            _open_window(serial, visit_id)
                        else:
                            # Two cats on the box at once (v072, option B):
                            # same pair-sum check as the arrival branch.
                            pair = pair_sum_match(weight, pets)
                            if pair:
                                p1, p2 = pair
                                for cand, other in ((p1, p2), (p2, p1)):
                                    log_event(events, serial, robot_name,
                                        "two_cat_sum", float(cand["weight"]),
                                        pet=cand["name"],
                                        ambiguous=[p1["name"], p2["name"]],
                                        note=f"likely {cand['name']} — {weight} lbs total with {other['name']}")
                                events_dirty = True
                                current_weight[serial] = weight
                                continue
                            # The weight swung but matched no pet:
                            # record it instead of dropping it.
                            log_event(events, serial, robot_name,
                                      "unmatched_weight_change", weight,
                                      ambiguous=ambiguous,
                                      note="weight swung mid-detection but matched no pet")
                            events_dirty = True
                            current_weight[serial] = weight
                        continue

                    # No open event yet: settle the arrival weight first.
                    # The scale's first reading while a cat steps on is
                    # unreliable (Nov 17: 6.13 lb phantom while the real
                    # weight settled a poll later) -- log nothing until the
                    # weight holds within SETTLE_TOLERANCE for SETTLE_POLLS
                    # consecutive polls.
                    if weight is None:
                        continue
                    pend = pending_weight.get(serial)
                    if pend is None:
                        pending_weight[serial] = weight
                        pending_polls[serial] = 1
                        continue
                    if abs(weight - pend) > SETTLE_TOLERANCE:
                        pending_weight[serial] = weight
                        pending_polls[serial] = 1
                        continue
                    pending_polls[serial] = pending_polls[serial] + 1
                    if pending_polls[serial] < SETTLE_POLLS:
                        continue
                    # Stable arrival weight: match it.
                    pending_weight.pop(serial, None)
                    pending_polls.pop(serial, None)
                    # The box's last cat breaks weight ties.
                    lc_name = last_cat_name_for(serial, pets)
                    pet, ambiguous, matched_by = match_pet(weight, pets, lc_name)
                    if not pet:
                        # Two cats on the box at once (v072, option B):
                        # the weight matches two pets' combined input
                        # weights. Log one event per cat, each carrying
                        # that cat's own weight so resolving it logs a
                        # correct visit; the note ties the pair to the
                        # one total reading.
                        pair = pair_sum_match(weight, pets)
                        if pair:
                            p1, p2 = pair
                            for cand, other in ((p1, p2), (p2, p1)):
                                log_event(events, serial, robot_name,
                                    "two_cat_sum", float(cand["weight"]),
                                    pet=cand["name"],
                                    ambiguous=[p1["name"], p2["name"]],
                                    note=f"likely {cand['name']} — {weight} lbs total with {other['name']}")
                            events_dirty = True
                            cat_present[serial] = True
                            current_weight[serial] = weight
                            continue
                        # No confident match: record the encounter as an
                        # event instead of silently dropping it, and mark
                        # the arrival handled so it is not re-logged.
                        ev_type = "ambiguous_arrival" if ambiguous else "unmatched_arrival"
                        log_event(events, serial, robot_name, ev_type, weight,
                                  ambiguous=ambiguous,
                                  note="arrival weight fit more than one pet" if ambiguous else "arrival weight matched no pet")
                        events_dirty = True
                        cat_present[serial] = True
                        current_weight[serial] = weight
                        continue
                    # Confident match on a fresh arrival: log it.
                    visit_id = uuid.uuid4().hex[:8]
                    if needs_clean.get(serial):
                        # Second arrival before any clean cycle since the
                        # last one: a back-to-back anomaly (the visit
                        # itself still logs normally).
                        log_event(events, serial, robot_name, "back_to_back", weight,
                                  pet=pet, visit_id=visit_id,
                                  note="second arrival before a clean cycle")
                        events_dirty = True
                    if _close_window(serial, visits):
                        # A previous visit's cycle-delay window was still
                        # open: attach its weights before starting a new one.
                        visits_dirty = True
                    cat_present[serial] = True
                    current_weight[serial] = weight
                    needs_clean[serial] = True
                    visits.append({
                        "id": visit_id,
                        "timestamp": now.isoformat(),
                        "serial": serial,
                        "robot": robot_name,
                        "weight": weight,
                        "pet": pet,
                        "ambiguous": ambiguous,
                        "manual": False,
                        "matched_by": matched_by,
                        "type": None,
                    })
                    match = next((p for p in pets if p["name"] == pet), None)
                    if match:
                        set_last_cat(serial, match["id"])
                    visits_dirty = True
                    _open_window(serial, visit_id)

                # Auto-reset a box stuck in ROBOT_CLEAN. A normal clean
                # cycle takes ~2-3 min; a box sitting in ROBOT_CLEAN past
                # CLEAN_TIMEOUT_SECONDS is stuck (the box that sat there
                # until someone reset it by hand). Reset it so it returns
                # to READY. If no visit was logged for this cycle — the
                # arrival detection was missed, e.g. no page was open when
                # the cat used it — log the visit from the sticky scale
                # weight first, so it still lands on the graph. A visit
                # recorded within CLEAN_RECENT_VISIT_SECONDS is the same
                # cycle already logged at arrival, so it is not logged twice.
                for robot in account.robots:
                    data = robot.__dict__.get("_data", {})
                    status = data.get("robotStatus")
                    if status != "ROBOT_CLEAN":
                        clean_since.pop(robot.serial, None)
                        save_clean_since()
                        continue
                    first_seen = clean_since.get(robot.serial)
                    if first_seen is None:
                        clean_since[robot.serial] = now
                        save_clean_since()
                        continue
                    if (now - first_seen).total_seconds() < CLEAN_TIMEOUT_SECONDS:
                        continue
                    # Stuck in ROBOT_CLEAN too long: reset it.
                    weight = data.get("catWeight")
                    recent = False
                    for v in visits:
                        if v.get("serial") != robot.serial:
                            continue
                        try:
                            ts = datetime.fromisoformat(v["timestamp"])
                        except (ValueError, TypeError, KeyError):
                            continue
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        if (now - ts).total_seconds() < CLEAN_RECENT_VISIT_SECONDS:
                            recent = True
                            break
                    if not recent and weight is not None:
                        lc_name = last_cat_name_for(robot.serial, pets)
                        pet, ambiguous, matched_by = match_pet(weight, pets, lc_name)
                        if pet:
                            visits.append({
                                "id": uuid.uuid4().hex[:8],
                                "timestamp": now.isoformat(),
                                "serial": robot.serial,
                                "robot": getattr(robot, "name", data.get("name", "Unknown")),
                                "weight": weight,
                                "pet": pet,
                                "ambiguous": ambiguous,
                                "manual": False,
                                "matched_by": matched_by,
                                "type": None,
                            })
                            match = next((p for p in pets if p["name"] == pet), None)
                            if match:
                                set_last_cat(robot.serial, match["id"])
                            visits_dirty = True
                    try:
                        await robot.reset()
                        log_event(events, robot.serial,
                                  getattr(robot, "name", data.get("name", "Unknown")),
                                  "auto_reset", weight,
                                  note="box stuck in ROBOT_CLEAN past timeout; reset by detection loop")
                        events_dirty = True
                    except Exception as e:
                        print(f"Auto-reset failed for {robot.serial}: {e}")
                    clean_since.pop(robot.serial, None)
                    save_clean_since()
                if visits_dirty:
                    save_visits(visits)
                if events_dirty:
                    save_events(events)
                if drawer_hist_dirty:
                    save_drawer_history(drawer_hist)
        except Exception as e:
            print(f"Detection loop error: {e}")
        await asyncio.sleep(5)


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            if not account or not account.robots:
                await websocket.send_json({"robots": [], "error": "No robots available"})
            else:
                payload = {
                    "robots": [serialize_robot(r) for r in account.robots],
                    "pets": load_pets(),
                    "visits": list(reversed(load_visits()))[:50],
                }

                await websocket.send_json(payload)

            await asyncio.sleep(5)

    except Exception as e:
        print(f"WebSocket error: {e}")

    finally:
        print("WebSocket closed")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=4323, reload=False)
