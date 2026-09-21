"""A fake MiP that answers queries with canned replies.

``MockClient`` has the subset of the ``BleakClient`` interface that
:class:`wowpy.mip.MiP` uses, so ``MiP(None, client=MockClient())`` behaves
like a connected robot: writes are recorded, query opcodes get a reply on the
notify callback, and tests or the dashboard can inject events with
:meth:`MockClient.emit`.
"""

import asyncio

from . import protocol as p

MOCK_ADDRESS = "00:00:00:00:00:00"
MOCK_NAME = "Mock MiP"


class MockClient:
    def __init__(self, *, battery_raw=0x7C, position=2):
        self.is_connected = False
        self.writes = []
        self.notify_cb = None
        self.state = {
            "battery_raw": battery_raw,
            "position": position,
            "volume": 4,
            "game_mode": 1,
            "odometer_cm": 200,
            "chest_led": (0, 255, 0, 0, 0),
            "head_leds": (1, 1, 1, 1),
            "gesture_radar_mode": 0,
            "detection": (0, 60),
            "clap_enabled": 1,
            "clap_delay_ms": 500,
            "user_data": {},
        }
        # opcode -> reply bytes (without opcode) or None to swallow the query
        self.overrides = {}
        self.silent = set()

    # -- BleakClient interface ----------------------------------------------

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def start_notify(self, _uuid, cb):
        self.notify_cb = cb

    async def write_gatt_char(self, _uuid, data, response=False):
        if not self.is_connected:
            raise ConnectionError("not connected")
        data = bytes(data)
        self.writes.append(data)
        reply = self._handle(data)
        if reply is not None:
            self.emit(reply)

    # -- test / dashboard helpers --------------------------------------------

    def emit(self, data):
        """Deliver ``data`` (bytes or hex string) to the MiP as a notification."""
        if isinstance(data, str):
            data = bytes.fromhex(data)
        if self.notify_cb:
            self.notify_cb(0, data.hex().upper().encode("ascii"))

    def set_position(self, position):
        self.state["position"] = position
        self.emit(bytes([p.CMD_GET_STATUS, self.state["battery_raw"], position]))

    def set_battery_raw(self, raw):
        self.state["battery_raw"] = raw

    def drop_connection(self, mip):
        """Simulate the robot going away."""
        self.is_connected = False
        mip._on_disconnect(self)

    # -- behaviour ---------------------------------------------------------

    def _handle(self, data):
        op, args = data[0], data[1:]
        s = self.state
        if op in self.silent:
            return None
        if op in self.overrides:
            return bytes([op, *self.overrides[op]])

        if op == p.CMD_SET_CHEST_LED:
            s["chest_led"] = (*args[:3], 0, 0)
        elif op == p.CMD_FLASH_CHEST_LED:
            s["chest_led"] = tuple(args[:5])
        elif op == p.CMD_SET_HEAD_LEDS:
            s["head_leds"] = tuple(args[:4])
        elif op == p.CMD_SET_VOLUME:
            s["volume"] = args[0]
        elif op == p.CMD_SET_GAME_MODE:
            s["game_mode"] = args[0]
        elif op == p.CMD_SET_GESTURE_RADAR_MODE:
            s["gesture_radar_mode"] = args[0]
        elif op == p.CMD_SET_MIP_DETECTION:
            s["detection"] = tuple(args[:2])
        elif op == p.CMD_ENABLE_CLAP:
            s["clap_enabled"] = args[0]
        elif op == p.CMD_SET_CLAP_DELAY:
            s["clap_delay_ms"] = int.from_bytes(args[:2], "big")
        elif op == p.CMD_SET_USER_DATA:
            s["user_data"][args[0]] = args[1]
        elif op == p.CMD_RESET_ODOMETER:
            s["odometer_cm"] = 0
        elif op == p.CMD_SET_POSITION:
            s["position"] = 0 if args[0] == 0 else 1
        elif op == p.CMD_GET_UP:
            s["position"] = 2
        elif op in (p.CMD_DRIVE_CONTINUOUS, p.CMD_DRIVE_FORWARD_TIME, p.CMD_DRIVE_BACKWARD_TIME):
            s["odometer_cm"] += 1
        elif op == p.CMD_DRIVE_DISTANCE:
            s["odometer_cm"] += args[1]

        # queries
        if op == p.CMD_GET_STATUS:
            return bytes([op, s["battery_raw"], s["position"]])
        if op == p.CMD_GET_VOLUME:
            return bytes([op, s["volume"]])
        if op == p.CMD_GET_GAME_MODE:
            return bytes([op, s["game_mode"]])
        if op == p.CMD_GET_ODOMETER:
            return bytes([op, *s["odometer_cm"].to_bytes(4, "big")])
        if op == p.CMD_GET_CHEST_LED:
            return bytes([op, *s["chest_led"]])
        if op == p.CMD_GET_HEAD_LEDS:
            return bytes([op, *s["head_leds"]])
        if op == p.CMD_GET_GESTURE_RADAR_MODE:
            return bytes([op, s["gesture_radar_mode"]])
        if op == p.CMD_GET_MIP_DETECTION:
            return bytes([op, *s["detection"]])
        if op == p.CMD_GET_CLAP_STATUS:
            return bytes([op, s["clap_enabled"], *s["clap_delay_ms"].to_bytes(2, "big")])
        if op == p.CMD_GET_USER_DATA:
            return bytes([op, args[0], s["user_data"].get(args[0], 0)])
        if op == p.CMD_GET_SOFTWARE_VERSION:
            return bytes([op, 0x17, 0x01, 0x1B, 0x01])
        if op == p.CMD_GET_HARDWARE_VERSION:
            return bytes([op, 0x01, 0x03])
        if op == p.CMD_GET_WEIGHT:
            return bytes([op, 0x00])
        return None
