#!/usr/bin/env python3

from fastapi import FastAPI, WebSocket, HTTPException, Query

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

from pylitterbot.enums import NightLightMode


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

MATCH_TOLERANCE = 0.75  # lbs — a visit must be within this of a pet's weight
AMBIGUITY_GAP = 0.5     # lbs — closest must beat runner-up by this to win
MAX_VISITS = 500        # keep the log bounded; oldest entries drop off

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


def serialize_robot(robot):
    """Safely turn a robot object into a JSON-friendly dict"""
    data = robot.__dict__.get("_data", {})

    return {
        "serial": robot.serial,
        "name": getattr(robot, "name", data.get("name", "Unknown")),
        "is_online": getattr(robot, "is_online", data.get("isOnline", False)),
        "status": data.get("robotStatus"),
        "litter_level": data.get("DFILevelPercent"),
        "is_full": data.get("isDFIFull"),
        "cat_weight": data.get("catWeight"),
        "weight_sensor": data.get("weightSensor"),
        "smart_weight_enabled": data.get("smartWeightEnabled"),
        "scoops_saved": data.get("scoopsSavedCount"),
        "cycles": data.get("DFINumberOfCycles"),
        "night_light": data.get("nightLightActive"),
        "night_light_mode": data.get("nightLightMode"),
        "raw": {k: (v if isinstance(v, (dict, list, str, int, float, bool, type(None))) else str(v))
                for k, v in robot.__dict__.items()},
    }


@app.on_event("startup")
async def startup_event():
    await connect_account()


@app.on_event("shutdown")
async def shutdown_event():
    await disconnect_account()


@app.get("/")
async def root():
    return {
        "msg": "litterbot multi-robot backend",
        "version": "0.4.4",
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
    return load_pets()


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
            visit["manual"] = True
            visit["matched_by"] = "manual"
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


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Last seen cycle count per robot, for visit detection. A cycle count
    # tick means a visit finished; the catWeight at that moment is the
    # visiting cat's weight. Known limit: two cats back-to-back before one
    # cycle log as a single visit — activity-history detection events are
    # the fix for that, and are the next step after this version.
    last_cycles = {}

    try:
        while True:
            if not account or not account.robots:
                await websocket.send_json({"robots": [], "error": "No robots available"})
            else:
                # Refresh all robots
                for robot in account.robots:
                    try:
                        await robot.refresh()
                    except Exception:
                        pass

                # Detect completed cycles -> visits
                pets = load_pets()
                visits = load_visits()
                new_visit = False
                for robot in account.robots:
                    data = robot.__dict__.get("_data", {})
                    cycles = data.get("DFINumberOfCycles")
                    prev = last_cycles.get(robot.serial)
                    if cycles is not None:
                        if prev is not None and cycles > prev:
                            weight = data.get("catWeight")
                            # The box's last cat breaks weight ties.
                            lc_name = last_cat_name_for(robot.serial, pets)
                            pet, ambiguous, matched_by = match_pet(weight, pets, lc_name)
                            visits.append({
                                "id": uuid.uuid4().hex[:8],
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "serial": robot.serial,
                                "robot": getattr(robot, "name", data.get("name", "Unknown")),
                                "weight": weight,
                                "pet": pet,
                                "ambiguous": ambiguous,
                                "manual": False,
                                "matched_by": matched_by,
                            })
                            # A confident match becomes the box's last cat.
                            if pet:
                                match = next((p for p in pets if p["name"] == pet), None)
                                if match:
                                    set_last_cat(robot.serial, match["id"])
                            new_visit = True
                        last_cycles[robot.serial] = cycles
                if new_visit:
                    save_visits(visits)

                payload = {
                    "robots": [serialize_robot(r) for r in account.robots],
                    "pets": pets,
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
