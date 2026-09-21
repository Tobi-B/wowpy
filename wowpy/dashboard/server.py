"""FastAPI backend for the MiP dashboard.

One MiP connection at a time. REST for scan/connect/commands, a WebSocket
that pushes log entries, status updates and connection state to every open
page and accepts the hold-to-drive stream from the page.
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import protocol as p
from ..mip import MiP
from ..mock import MOCK_ADDRESS, MOCK_NAME, MockClient

STATIC = Path(__file__).parent / "static"

POLL_INTERVAL = 5.0
DRIVE_HOLDOFF = 0.3          # seconds after the last drive packet during which polling is paused
QUERY_TIMEOUT = 1.5

# Polled every cycle; queried once at connect; re-queried after a related set command.
POLL_OPCODES = (p.CMD_GET_STATUS, p.CMD_GET_VOLUME, p.CMD_GET_GAME_MODE, p.CMD_GET_ODOMETER)
ONCE_OPCODES = (p.CMD_GET_SOFTWARE_VERSION, p.CMD_GET_HARDWARE_VERSION, p.CMD_GET_CHEST_LED,
                p.CMD_GET_HEAD_LEDS, p.CMD_GET_GESTURE_RADAR_MODE, p.CMD_GET_CLAP_STATUS)
REFRESH_AFTER = {
    p.CMD_SET_CHEST_LED: (p.CMD_GET_CHEST_LED,),
    p.CMD_FLASH_CHEST_LED: (p.CMD_GET_CHEST_LED,),
    p.CMD_SET_HEAD_LEDS: (p.CMD_GET_HEAD_LEDS,),
    p.CMD_SET_VOLUME: (p.CMD_GET_VOLUME,),
    p.CMD_SET_GAME_MODE: (p.CMD_GET_GAME_MODE,),
    p.CMD_SET_GESTURE_RADAR_MODE: (p.CMD_GET_GESTURE_RADAR_MODE,),
    p.CMD_ENABLE_CLAP: (p.CMD_GET_CLAP_STATUS,),
    p.CMD_SET_CLAP_DELAY: (p.CMD_GET_CLAP_STATUS,),
    p.CMD_RESET_ODOMETER: (p.CMD_GET_ODOMETER,),
}
QUERY_NAMES = {c.opcode: c.name for c in p.COMMANDS if c.query}


def _hex(data):
    return bytes(data).hex(" ").upper()


class Hub:
    """Holds the single connection plus everything the pages need to know."""

    def __init__(self):
        self.mip = None
        self.mock = None
        self.device = {"name": None, "address": None, "rssi": None}
        self.connection = "disconnected"   # disconnected | connecting | connected
        self.status = {}
        self.last_update = None
        self.sockets = set()
        self.poll_task = None
        self.last_drive = 0.0
        self.lock = asyncio.Lock()
        self.scan_cache = []

    # -- broadcasting -------------------------------------------------------

    def _push(self, msg):
        for ws in list(self.sockets):
            asyncio.ensure_future(self._send(ws, msg))

    async def _send(self, ws, msg):
        try:
            await ws.send_json(msg)
        except Exception:
            self.sockets.discard(ws)

    def log(self, direction, name, data=b"", text=""):
        self._push({"type": "log", "ts": datetime.now().isoformat(timespec="milliseconds"),
                    "dir": direction, "name": name, "bytes": _hex(data), "text": text})

    def push_connection(self):
        self._push({"type": "connection", "state": self.connection, **self.device})

    def push_status(self):
        self._push({"type": "status", "fields": self.status, "last_update": self.last_update})

    def snapshot(self):
        return {"type": "snapshot", "connection": {"state": self.connection, **self.device},
                "status": self.status, "last_update": self.last_update, "devices": self.scan_cache}

    # -- notifications from the robot ----------------------------------------

    def _on_notification(self, data):
        name, fields = p.decode_reply(data)
        self.log("received", name, data, fields.get("text", ""))
        updates = {k: v for k, v in fields.items() if k != "text"}
        if updates:
            self.status.update(updates)
            self.last_update = datetime.now().isoformat(timespec="milliseconds")
            self.push_status()

    def _on_disconnect(self):
        self.connection = "disconnected"
        self.log("info", "disconnected")
        self.push_connection()
        if self.poll_task:
            self.poll_task.cancel()
            self.poll_task = None

    # -- connection ---------------------------------------------------------

    async def scan(self, timeout=10.0):
        devices = [{"name": MOCK_NAME, "address": MOCK_ADDRESS, "rssi": None}]
        try:
            for name, address, rssi in await MiP.scan(timeout):
                devices.append({"name": name, "address": address, "rssi": rssi})
        except Exception as e:  # no adapter, etc. - the mock must still be usable
            self.log("error", "scan failed", text=str(e))
        self.scan_cache = devices
        return devices

    async def connect(self, address, name=None, rssi=None):
        async with self.lock:
            if self.mip is not None:
                await self._disconnect()
            self.device = {"name": name or address, "address": address, "rssi": rssi}
            self.connection = "connecting"
            self.push_connection()
            self.status = {}
            self.last_update = None
            try:
                if address == MOCK_ADDRESS:
                    self.mock = MockClient()
                    mip = MiP(None, client=self.mock)
                else:
                    self.mock = None
                    mip = MiP(address)
                mip.on_notification = self._on_notification
                mip.on_disconnect = self._on_disconnect
                await mip.connect()
            except Exception as e:
                self.connection = "disconnected"
                self.push_connection()
                self.log("error", "connect failed", text=str(e))
                raise
            self.mip = mip
            self.connection = "connected"
            self.log("info", f"connected to {self.device['name']}")
            self.push_connection()
            self.poll_task = asyncio.create_task(self._poll_loop())

    async def _disconnect(self):
        if self.poll_task:
            self.poll_task.cancel()
            self.poll_task = None
        mip, self.mip = self.mip, None
        if mip is not None:
            mip.on_disconnect = None
            try:
                await mip.disconnect()
            except Exception as e:
                self.log("error", "disconnect failed", text=str(e))
        self.connection = "disconnected"
        self.log("info", "disconnected")
        self.push_connection()

    async def disconnect(self):
        async with self.lock:
            await self._disconnect()

    def require(self):
        if self.mip is None or self.connection != "connected":
            raise HTTPException(409, "Connect to a MiP first")
        return self.mip

    # -- commands -------------------------------------------------------------

    async def send_bytes(self, data, name):
        mip = self.require()
        await mip.send_bytes(data)
        self.log("sent", name, data)
        for op in REFRESH_AFTER.get(data[0], ()):
            await self.query(op)

    async def query(self, opcode, *params):
        mip = self.require()
        name = QUERY_NAMES.get(opcode, f"0x{opcode:02X}")
        self.log("sent", name, bytes([opcode, *params]))
        try:
            await mip.request(opcode, *params, timeout=QUERY_TIMEOUT)
        except TimeoutError:
            self.log("timeout", name, bytes([opcode, *params]), "no reply")
        except ConnectionError:
            pass

    async def run_command(self, name, params):
        cmd = p.COMMANDS_BY_NAME.get(name)
        if cmd is None:
            raise HTTPException(404, f"unknown command {name!r}")
        try:
            data = cmd.build(**params)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if cmd.query:
            await self.query(data[0], *data[1:])
        else:
            await self.send_bytes(data, name)
        return _hex(data)

    async def refresh(self, opcodes=POLL_OPCODES):
        for op in opcodes:
            if self.mip is None:
                return
            await self.query(op)

    async def _poll_loop(self):
        try:
            await self.refresh(ONCE_OPCODES + POLL_OPCODES)
            while True:
                await asyncio.sleep(POLL_INTERVAL)
                while time.monotonic() - self.last_drive < DRIVE_HOLDOFF:
                    await asyncio.sleep(0.1)
                await self.refresh()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log("error", "poll loop", text=str(e))

    async def drive(self, speed, turn):
        mip = self.require()
        now = time.monotonic()
        # One log line per hold, not one per 40 ms packet.
        if now - self.last_drive >= DRIVE_HOLDOFF:
            self.log("sent", "Drive (hold)", bytes([p.CMD_DRIVE_CONTINUOUS, *p.encode_continuous_drive(speed, turn)]),
                     f"speed {speed}, turn {turn}; repeating while held")
        self.last_drive = now
        await mip.drive(speed, turn)

    async def stop(self):
        mip = self.require()
        self.last_drive = 0.0
        await mip.stop()
        self.log("sent", "Stop", bytes([p.CMD_STOP]))


hub = Hub()
app = FastAPI(title="MiP dashboard")


# ------------------------------------------------------------------ REST

class ConnectBody(BaseModel):
    address: str
    name: str | None = None
    rssi: int | None = None


class CommandBody(BaseModel):
    name: str
    params: dict = {}


class RawBody(BaseModel):
    bytes: str


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/commands")
async def commands():
    return {
        "families": list(p.FAMILIES),
        "commands": [
            {
                "name": c.name, "opcode": c.opcode, "family": c.family, "query": c.query,
                "params": [
                    {"name": pr.name, "min": pr.min, "max": pr.max, "default": pr.default,
                     "unit": pr.unit, "choices": pr.choices or None}
                    for pr in c.params
                ],
            }
            for c in p.COMMANDS
        ],
        "positions": p.POSITIONS,
        "game_modes": p.GAME_MODES,
        "head_led_states": p.HEAD_LED_STATES,
        "gesture_radar_modes": p.GESTURE_RADAR_MODES,
    }


@app.post("/api/scan")
async def scan(timeout: float = 10.0):
    return await hub.scan(timeout)


@app.post("/api/connect")
async def connect(body: ConnectBody):
    try:
        await hub.connect(body.address, body.name, body.rssi)
    except Exception as e:
        raise HTTPException(502, f"connect failed: {e}")
    return {"state": hub.connection, **hub.device}


@app.post("/api/disconnect")
async def disconnect():
    await hub.disconnect()
    return {"state": hub.connection}


@app.post("/api/command")
async def command(body: CommandBody):
    return {"sent": await hub.run_command(body.name, body.params)}


@app.post("/api/raw")
async def raw(body: RawBody):
    try:
        data = p.parse_raw(body.bytes)
    except ValueError as e:
        raise HTTPException(422, str(e))
    await hub.send_bytes(data, "Raw")
    return {"sent": _hex(data)}


@app.post("/api/refresh")
async def refresh():
    hub.require()
    await hub.refresh()
    return {"ok": True}


@app.get("/api/state")
async def state():
    return hub.snapshot()


# Mock-only helpers so the acceptance scenarios can be driven without hardware.

def _mock():
    if hub.mock is None:
        raise HTTPException(409, "not connected to the mock robot")
    return hub.mock


class EmitBody(BaseModel):
    hex: str


class OverrideBody(BaseModel):
    opcode: int
    reply: str | None = None   # hex without opcode; None = stop answering


@app.post("/api/mock/emit")
async def mock_emit(body: EmitBody):
    _mock().emit(body.hex)
    return {"ok": True}


@app.post("/api/mock/position/{code}")
async def mock_position(code: int):
    _mock().set_position(code)
    return {"ok": True}


@app.post("/api/mock/battery/{raw}")
async def mock_battery(raw: int):
    _mock().set_battery_raw(raw)
    return {"ok": True}


@app.post("/api/mock/override")
async def mock_override(body: OverrideBody):
    m = _mock()
    if body.reply is None:
        m.silent.add(body.opcode)
        m.overrides.pop(body.opcode, None)
    else:
        m.silent.discard(body.opcode)
        m.overrides[body.opcode] = bytes.fromhex(body.reply)
    return {"ok": True}


@app.get("/api/mock/writes")
async def mock_writes(last: int = 50):
    """Most recent commands the mock received, oldest first, as hex strings."""
    return [_hex(w) for w in _mock().writes[-last:]]


@app.post("/api/mock/drop")
async def mock_drop():
    m = _mock()
    m.drop_connection(hub.mip)
    return {"ok": True}


# ------------------------------------------------------------- WebSocket

@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    hub.sockets.add(ws)
    await ws.send_json(hub.snapshot())
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            try:
                if kind == "drive":
                    await hub.drive(int(msg.get("speed", 0)), int(msg.get("turn", 0)))
                elif kind == "stop":
                    await hub.stop()
            except HTTPException:
                pass
            except Exception as e:
                hub.log("error", kind or "?", text=str(e))
    except WebSocketDisconnect:
        pass
    finally:
        hub.sockets.discard(ws)
        # A page going away mid-drive must not leave the robot rolling.
        if hub.mip is not None and time.monotonic() - hub.last_drive < DRIVE_HOLDOFF:
            try:
                await hub.stop()
            except Exception:
                pass
