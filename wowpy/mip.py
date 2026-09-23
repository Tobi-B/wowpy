"""Control for the WowWee MiP robot over Bluetooth LE.

Commands are raw byte sequences written to the MiP's "send" characteristic:
the first byte is an opcode, followed by parameters (see :mod:`wowpy.protocol`
for the full table). Responses arrive on the "receive" characteristic as an
ASCII hex string (e.g. b"794D00" for a status reply) which is decoded back
into bytes here.
"""

import asyncio

from bleak import BleakClient, BleakScanner

from . import protocol
from .protocol import (  # noqa: F401  (re-exported for convenience)
    CMD_DRIVE_BACKWARD_TIME, CMD_DRIVE_CONTINUOUS, CMD_DRIVE_DISTANCE, CMD_DRIVE_FORWARD_TIME,
    CMD_FLASH_CHEST_LED, CMD_GET_STATUS, CMD_PLAY_SOUND, CMD_SET_CHEST_LED, CMD_SET_HEAD_LEDS,
    CMD_SET_VOLUME, CMD_STOP, CMD_TURN_LEFT, CMD_TURN_RIGHT, COMMANDS_BY_NAME, battery_percent,
)

NAME_PREFIX = "Mip-"

SEND_CHARACTERISTIC = "0000ffe9-0000-1000-8000-00805f9b34fb"
RECEIVE_CHARACTERISTIC = "0000ffe4-0000-1000-8000-00805f9b34fb"

# Head LED states for set_head_leds()
HEAD_LED_OFF = 0
HEAD_LED_ON = 1
HEAD_LED_BLINK_SLOW = 2
HEAD_LED_BLINK_FAST = 3


class MiP:
    """A connection to a single MiP robot.

    Use as an async context manager::

        async with await MiP.discover() as mip:
            await mip.set_chest_led(255, 0, 0)

    or call :meth:`connect` / :meth:`disconnect` explicitly. A ``BleakClient``
    (or anything with the same ``write_gatt_char``/``start_notify`` interface)
    can be injected via ``client`` for testing or for the mock robot.

    ``on_notification(data: bytes)`` is called for every decoded notification,
    ``on_send(data: bytes)`` for every command written, ``on_disconnect()``
    when the link drops.
    """

    def __init__(self, device, *, timeout=20.0, client=None):
        self._client = client or BleakClient(device, timeout=timeout, disconnected_callback=self._on_disconnect)
        self._responses = asyncio.Queue()
        self.on_notification = None
        self.on_send = None
        self.on_disconnect = None

    @classmethod
    async def discover(cls, name=None, *, timeout=15.0, **kwargs):
        """Scan for a MiP and return an unconnected :class:`MiP`.

        With ``name`` set, only that exact device name matches; otherwise the
        first device whose name starts with ``Mip-`` is used. The default 5 s
        scan often misses the robot, hence the longer timeout.
        """
        if name is not None:
            device = await BleakScanner.find_device_by_name(name, timeout=timeout)
        else:
            device = await BleakScanner.find_device_by_filter(
                lambda d, _adv: bool(d.name and d.name.startswith(NAME_PREFIX)), timeout=timeout
            )
        if device is None:
            raise RuntimeError(f"no MiP found within {timeout:.0f}s")
        return cls(device, **kwargs)

    @staticmethod
    async def scan(timeout=10.0):
        """Return ``[(name, address, rssi), ...]`` for every MiP seen within ``timeout``."""
        found = await BleakScanner.discover(timeout=timeout, return_adv=True)
        result = []
        for device, adv in found.values():
            name = device.name or adv.local_name
            if name and name.startswith(NAME_PREFIX):
                result.append((name, device.address, adv.rssi))
        return sorted(result, key=lambda r: -r[2])

    # -- connection --------------------------------------------------------

    @property
    def is_connected(self):
        return self._client.is_connected

    async def connect(self):
        # No pair(): the MiP needs no pairing and calling it drops the connection.
        await self._client.connect()
        await self._client.start_notify(RECEIVE_CHARACTERISTIC, self._on_notify)
        return self

    async def disconnect(self):
        if self._client.is_connected:
            await self._client.disconnect()

    async def __aenter__(self):
        return await self.connect()

    async def __aexit__(self, *exc):
        await self.disconnect()

    def _on_disconnect(self, _client):
        # Unblock anyone waiting on a response that will never come.
        self._responses.put_nowait(None)
        if self.on_disconnect:
            self.on_disconnect()

    def _on_notify(self, _handle, data):
        try:
            decoded = bytes.fromhex(data.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            decoded = bytes(data)
        self._responses.put_nowait(decoded)
        if self.on_notification:
            self.on_notification(decoded)

    # -- low level ---------------------------------------------------------

    async def send_bytes(self, data):
        """Write a raw, pre-encoded command without waiting for a reply."""
        data = bytes(data)
        if self.on_send:
            self.on_send(data)
        await self._client.write_gatt_char(SEND_CHARACTERISTIC, data, response=False)

    async def send(self, opcode, *params):
        """Write a raw command without waiting for a reply."""
        await self.send_bytes(bytes([opcode, *params]))

    async def request(self, opcode, *params, timeout=2.0):
        """Send a command and return the first reply that echoes its opcode."""
        # Drop stale replies so we don't match one from an earlier request.
        while not self._responses.empty():
            self._responses.get_nowait()
        await self.send(opcode, *params)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"no reply to 0x{opcode:02X} within {timeout}s")
            reply = await asyncio.wait_for(self._responses.get(), remaining)
            if reply is None:
                raise ConnectionError("MiP disconnected")
            if reply and reply[0] == opcode:
                return reply[1:]

    async def execute(self, command_name, timeout=2.0, **params):
        """Run a command from :data:`wowpy.protocol.COMMANDS` by name.

        Returns the decoded reply fields for query commands, else ``None``.
        """
        cmd = COMMANDS_BY_NAME[command_name]
        data = cmd.build(**params)
        if cmd.query:
            reply = await self.request(data[0], *data[1:], timeout=timeout)
            _name, fields = protocol.decode_reply(bytes([cmd.opcode, *reply]))
            return fields
        await self.send_bytes(data)
        return None

    async def _run(self, name, **params):
        await self.send_bytes(COMMANDS_BY_NAME[name].build(**params))

    # -- LEDs --------------------------------------------------------------

    async def set_chest_led(self, r, g, b):
        await self._run("Set chest LED", r=_c(r), g=_c(g), b=_c(b))

    async def flash_chest_led(self, r, g, b, on_ms=500, off_ms=500):
        """Blink the chest LED; on/off times are in 20 ms steps (max ~5 s)."""
        await self._run("Flash chest LED", r=_c(r), g=_c(g), b=_c(b),
                        on_ms=protocol.clamp(on_ms, 20, 5100), off_ms=protocol.clamp(off_ms, 20, 5100))

    async def set_head_leds(self, led1, led2, led3, led4):
        """Set the four head LEDs, each to one of the ``HEAD_LED_*`` states."""
        await self._run("Set head LEDs", **{f"led{i}": protocol.clamp(v, 0, 3)
                                            for i, v in enumerate((led1, led2, led3, led4), 1)})

    # -- driving -----------------------------------------------------------

    async def drive(self, speed, turn=0):
        """Continuous drive; resend at least every ~50 ms to keep moving.

        ``speed`` is -32..32 (negative = backward), ``turn`` is -32..32
        (negative = left). Both encode into the MiP's 0x01-0x80 ranges.
        """
        await self._run("Drive", speed=protocol.clamp(speed, -32, 32), turn=protocol.clamp(turn, -32, 32))

    async def drive_for(self, seconds, speed, turn=0, interval=0.04):
        """Continuous drive for ``seconds``: resends every ``interval`` s, then stops.

        Always ends with :meth:`stop`, even when cancelled, so a program can
        never leave the robot rolling.
        """
        loop = asyncio.get_running_loop()
        end = loop.time() + max(0.0, float(seconds))
        try:
            while True:
                await self.drive(speed, turn)
                remaining = end - loop.time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(interval, remaining))
        finally:
            await self.stop()

    async def drive_forward(self, speed, time_ms):
        """Drive forward at ``speed`` 0..30 for ``time_ms`` (7 ms steps, max ~1.8 s)."""
        await self._run("Drive forward", speed=protocol.clamp(speed, 0, 30), time_ms=protocol.clamp(time_ms, 0, 1785))

    async def drive_backward(self, speed, time_ms):
        await self._run("Drive backward", speed=protocol.clamp(speed, 0, 30), time_ms=protocol.clamp(time_ms, 0, 1785))

    async def turn_left(self, degrees, speed=12):
        """Turn left by ``degrees`` (5° steps, max 1275°) at ``speed`` 0..24."""
        await self._run("Turn left", degrees=protocol.clamp(degrees, 0, 1275), speed=protocol.clamp(speed, 0, 24))

    async def turn_right(self, degrees, speed=12):
        await self._run("Turn right", degrees=protocol.clamp(degrees, 0, 1275), speed=protocol.clamp(speed, 0, 24))

    async def drive_distance(self, distance_cm, turn_degrees=0):
        """Drive ``distance_cm`` (negative = backward), then turn ``turn_degrees`` (negative = left)."""
        await self._run("Drive distance", distance_cm=protocol.clamp(distance_cm, -255, 255),
                        turn_degrees=protocol.clamp(turn_degrees, -360, 360))

    async def stop(self):
        await self._run("Stop")

    # -- sound -------------------------------------------------------------

    async def play_sound(self, index):
        """Play built-in sound ``index`` (1..106)."""
        await self._run("Play sound", index=protocol.clamp(index, 1, 106))

    async def set_volume(self, level):
        """Set speaker volume 0..7."""
        await self._run("Set volume", level=protocol.clamp(level, 0, 7))

    # -- status ------------------------------------------------------------

    async def get_status(self):
        """Return ``(battery_percent, position)``; see ``protocol.POSITIONS`` for codes."""
        # Under heavy activity the MiP sometimes appends extra bytes; only the first two matter.
        battery_raw, position = (await self.request(CMD_GET_STATUS))[:2]
        return battery_percent(battery_raw), position


def _c(v):
    return protocol.clamp(v, 0, 255)
