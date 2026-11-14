#!/usr/bin/env python3
from fastapi import FastAPI, WebSocket, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
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
        "version": "0.2.0",
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


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
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

                payload = {
                    "robots": [serialize_robot(r) for r in account.robots]
                }
                await websocket.send_json(payload)

            await asyncio.sleep(5)
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        print("WebSocket closed")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=4323, reload=True)
