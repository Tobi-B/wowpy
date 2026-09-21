"""Control for the WowWee MiP robot over Bluetooth LE.

Commands are raw byte sequences written to the MiP's "send" characteristic:
the first byte is an opcode, followed by parameters. Responses arrive on the
"receive" characteristic as an ASCII hex string (e.g. b"794D00" for a status
reply) which is decoded back into bytes here.
"""

import asyncio

from bleak import BleakClient, BleakScanner

NAME_PREFIX = "Mip-"

SEND_CHARACTERISTIC = "0000ffe9-0000-1000-8000-00805f9b34fb"
RECEIVE_CHARACTERISTIC = "0000ffe4-0000-1000-8000-00805f9b34fb"

# Opcodes
CMD_PLAY_SOUND = 0x06
CMD_SET_VOLUME = 0x15
CMD_DRIVE_DISTANCE = 0x70
CMD_DRIVE_FORWARD_TIME = 0x71
CMD_DRIVE_BACKWARD_TIME = 0x72
CMD_TURN_LEFT = 0x73
CMD_TURN_RIGHT = 0x74
CMD_STOP = 0x77
CMD_DRIVE_CONTINUOUS = 0x78
CMD_GET_STATUS = 0x79
CMD_SET_CHEST_LED = 0x84
CMD_FLASH_CHEST_LED = 0x89
CMD_SET_HEAD_LEDS = 0x8A

# Head LED states for set_head_leds()
HEAD_LED_OFF = 0
HEAD_LED_ON = 1
HEAD_LED_BLINK_SLOW = 2
HEAD_LED_BLINK_FAST = 3


def _clamp(value, lo, hi):
    return max(lo, min(hi, int(value)))


class MiP:
    """A connection to a single MiP robot.

    Use as an async context manager::

        async with await MiP.discover() as mip:
            await mip.set_chest_led(255, 0, 0)

    or call :meth:`connect` / :meth:`disconnect` explicitly. A ``BleakClient``
    (or anything with the same ``write_gatt_char`` interface) can be injected
    via ``client`` for testing.
    """

    def __init__(self, device, *, timeout=20.0, client=None):
        self._client = client or BleakClient(device, timeout=timeout, disconnected_callback=self._on_disconnect)
        self._responses = asyncio.Queue()

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

    def _on_notify(self, _handle, data):
        try:
            self._responses.put_nowait(bytes.fromhex(data.decode("ascii")))
        except (UnicodeDecodeError, ValueError):
            self._responses.put_nowait(bytes(data))

    # -- low level ---------------------------------------------------------

    async def send(self, opcode, *params):
        """Write a raw command without waiting for a reply."""
        await self._client.write_gatt_char(SEND_CHARACTERISTIC, bytes([opcode, *params]), response=False)

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

    # -- LEDs --------------------------------------------------------------

    async def set_chest_led(self, r, g, b):
        await self.send(CMD_SET_CHEST_LED, _clamp(r, 0, 255), _clamp(g, 0, 255), _clamp(b, 0, 255))

    async def flash_chest_led(self, r, g, b, on_ms=500, off_ms=500):
        """Blink the chest LED; on/off times are in 20 ms steps (max ~5 s)."""
        await self.send(
            CMD_FLASH_CHEST_LED,
            _clamp(r, 0, 255), _clamp(g, 0, 255), _clamp(b, 0, 255),
            _clamp(on_ms // 20, 1, 255), _clamp(off_ms // 20, 1, 255),
        )

    async def set_head_leds(self, led1, led2, led3, led4):
        """Set the four head LEDs, each to one of the ``HEAD_LED_*`` states."""
        await self.send(CMD_SET_HEAD_LEDS, *(_clamp(v, 0, 3) for v in (led1, led2, led3, led4)))

    # -- driving -----------------------------------------------------------

    async def drive(self, speed, turn=0):
        """Continuous drive; resend at least every ~50 ms to keep moving.

        ``speed`` is -32..32 (negative = backward), ``turn`` is -32..32
        (negative = left). Both encode into the MiP's 0x01-0x80 ranges.
        """
        speed = _clamp(speed, -32, 32)
        turn = _clamp(turn, -32, 32)
        speed_byte = 0x00 if speed == 0 else (speed if speed > 0 else 0x20 - speed)
        turn_byte = 0x00 if turn == 0 else (0x40 + turn if turn > 0 else 0x60 - turn)
        await self.send(CMD_DRIVE_CONTINUOUS, speed_byte, turn_byte)

    async def drive_forward(self, speed, time_ms):
        """Drive forward at ``speed`` 0..30 for ``time_ms`` (7 ms steps, max ~1.8 s)."""
        await self.send(CMD_DRIVE_FORWARD_TIME, _clamp(speed, 0, 30), _clamp(time_ms // 7, 0, 255))

    async def drive_backward(self, speed, time_ms):
        await self.send(CMD_DRIVE_BACKWARD_TIME, _clamp(speed, 0, 30), _clamp(time_ms // 7, 0, 255))

    async def turn_left(self, degrees, speed=12):
        """Turn left by ``degrees`` (5° steps, max 1275°) at ``speed`` 0..24."""
        await self.send(CMD_TURN_LEFT, _clamp(degrees // 5, 0, 255), _clamp(speed, 0, 24))

    async def turn_right(self, degrees, speed=12):
        await self.send(CMD_TURN_RIGHT, _clamp(degrees // 5, 0, 255), _clamp(speed, 0, 24))

    async def drive_distance(self, distance_cm, turn_degrees=0):
        """Drive ``distance_cm`` (negative = backward), then turn ``turn_degrees`` (negative = left)."""
        direction = 0x00 if distance_cm >= 0 else 0x01
        turn_dir = 0x00 if turn_degrees >= 0 else 0x01
        angle = _clamp(abs(turn_degrees), 0, 360)
        await self.send(
            CMD_DRIVE_DISTANCE,
            direction, _clamp(abs(distance_cm), 0, 255),
            turn_dir, angle >> 8, angle & 0xFF,
        )

    async def stop(self):
        await self.send(CMD_STOP)

    # -- sound -------------------------------------------------------------

    async def play_sound(self, index):
        """Play built-in sound ``index`` (1..106)."""
        await self.send(CMD_PLAY_SOUND, _clamp(index, 1, 106))

    async def set_volume(self, level):
        """Set speaker volume 0..7."""
        await self.send(CMD_SET_VOLUME, _clamp(level, 0, 7))

    # -- status ------------------------------------------------------------

    async def get_status(self):
        """Return ``(battery_percent, position)``.

        ``position`` is the MiP's own code: 0 on back, 1 face down, 2 upright,
        3 picked up, 4 hand stand, 5 face down on tray, 6 on back with kickstand.
        """
        # Under heavy activity the MiP sometimes appends extra bytes; only the first two matter.
        battery_raw, position = (await self.request(CMD_GET_STATUS))[:2]
        # Raw battery is 0x4D (empty) .. 0x7C (full).
        percent = round((battery_raw - 0x4D) * 100 / (0x7C - 0x4D))
        return _clamp(percent, 0, 100), position
