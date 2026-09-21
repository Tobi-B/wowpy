import asyncio

import pytest

from wowpy.mip import MiP, SEND_CHARACTERISTIC, RECEIVE_CHARACTERISTIC


class FakeClient:
    """Records writes; ``reply`` queues a notification for the next write."""

    def __init__(self):
        self.is_connected = False
        self.writes = []
        self.notify_cb = None
        self.reply = None

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def start_notify(self, uuid, cb):
        assert uuid == RECEIVE_CHARACTERISTIC
        self.notify_cb = cb

    async def write_gatt_char(self, uuid, data, response):
        assert uuid == SEND_CHARACTERISTIC
        assert response is False
        self.writes.append(bytes(data))
        if self.reply is not None:
            self.notify_cb(0, self.reply)
            self.reply = None


@pytest.fixture
def fake():
    return FakeClient()


@pytest.fixture
def mip(fake):
    return MiP(None, client=fake)


def run(coro):
    return asyncio.run(coro)


def test_context_manager_connects_and_disconnects(mip, fake):
    async def go():
        async with mip:
            assert fake.is_connected
            assert fake.notify_cb is not None
        assert not fake.is_connected

    run(go())


@pytest.mark.parametrize(
    "call, expected",
    [
        (lambda m: m.set_chest_led(255, 0, 128), bytes([0x84, 0xFF, 0x00, 0x80])),
        (lambda m: m.set_chest_led(300, -5, 0), bytes([0x84, 0xFF, 0x00, 0x00])),
        (lambda m: m.flash_chest_led(0, 255, 0, on_ms=500, off_ms=200), bytes([0x89, 0x00, 0xFF, 0x00, 25, 10])),
        (lambda m: m.set_head_leds(0, 1, 2, 3), bytes([0x8A, 0, 1, 2, 3])),
        (lambda m: m.drive_forward(20, 700), bytes([0x71, 20, 100])),
        (lambda m: m.drive_backward(40, 10000), bytes([0x72, 30, 255])),
        (lambda m: m.turn_left(90), bytes([0x73, 18, 12])),
        (lambda m: m.turn_right(45, speed=30), bytes([0x74, 9, 24])),
        (lambda m: m.stop(), bytes([0x77])),
        (lambda m: m.play_sound(10), bytes([0x06, 10])),
        (lambda m: m.set_volume(9), bytes([0x15, 7])),
        (lambda m: m.drive_distance(50, 90), bytes([0x70, 0x00, 50, 0x00, 0x00, 90])),
        (lambda m: m.drive_distance(-30, -300), bytes([0x70, 0x01, 30, 0x01, 0x01, 0x2C])),
    ],
)
def test_command_encoding(mip, fake, call, expected):
    run(call(mip))
    assert fake.writes == [expected]


@pytest.mark.parametrize(
    "speed, turn, expected",
    [
        (0, 0, bytes([0x78, 0x00, 0x00])),
        (10, 0, bytes([0x78, 0x0A, 0x00])),
        (-10, 0, bytes([0x78, 0x2A, 0x00])),
        (0, 5, bytes([0x78, 0x00, 0x45])),
        (0, -5, bytes([0x78, 0x00, 0x65])),
        (99, -99, bytes([0x78, 0x20, 0x80])),
    ],
)
def test_continuous_drive_encoding(mip, fake, speed, turn, expected):
    run(mip.drive(speed, turn))
    assert fake.writes == [expected]


def test_get_status_parses_ascii_hex_reply(mip, fake):
    async def go():
        async with mip:
            fake.reply = b"797C02"  # full battery, upright
            return await mip.get_status()

    assert run(go()) == (100, 2)
    assert fake.writes == [bytes([0x79])]


def test_get_status_battery_scaling(mip, fake):
    async def go():
        async with mip:
            fake.reply = b"794D00"  # empty battery, on back
            return await mip.get_status()

    assert run(go()) == (0, 0)


def test_get_status_tolerates_trailing_bytes(mip, fake):
    async def go():
        async with mip:
            fake.reply = b"7964021D02"  # status with a clap event appended
            return await mip.get_status()

    assert run(go()) == (49, 2)


def test_request_ignores_replies_for_other_opcodes(mip, fake):
    async def go():
        async with mip:
            fake.reply = b"8400"  # unrelated reply arrives first
            task = asyncio.ensure_future(mip.request(0x79, timeout=1.0))
            await asyncio.sleep(0)
            fake.notify_cb(0, b"796000")
            return await task

    assert run(go()) == bytes([0x60, 0x00])


def test_request_times_out_without_reply(mip, fake):
    async def go():
        async with mip:
            await mip.request(0x79, timeout=0.05)

    with pytest.raises(TimeoutError):
        run(go())


def test_request_raises_on_disconnect(mip, fake):
    async def go():
        async with mip:
            task = asyncio.ensure_future(mip.request(0x79, timeout=1.0))
            await asyncio.sleep(0)
            mip._on_disconnect(fake)
            return await task

    with pytest.raises(ConnectionError):
        run(go())
