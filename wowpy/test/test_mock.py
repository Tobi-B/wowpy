import asyncio

from wowpy.mip import MiP
from wowpy.mock import MockClient


def run(coro):
    return asyncio.run(coro)


def test_mock_answers_status_query():
    async def go():
        mock = MockClient(battery_raw=0x64, position=0)
        async with MiP(None, client=mock) as mip:
            return await mip.get_status()

    assert run(go()) == (49, 0)


def test_mock_reflects_set_commands_in_getters():
    async def go():
        mock = MockClient()
        async with MiP(None, client=mock) as mip:
            await mip.set_chest_led(1, 2, 3)
            chest = await mip.execute("Get chest LED")
            await mip.set_volume(2)
            vol = await mip.execute("Get volume")
            await mip.execute("Reset odometer")
            odo = await mip.execute("Get odometer")
            return chest["chest_led"], vol["volume"], odo["odometer_cm"]

    assert run(go()) == ((1, 2, 3), 2, 0)


def test_mock_override_and_silence():
    async def go():
        mock = MockClient()
        async with MiP(None, client=mock) as mip:
            mock.overrides[0x79] = bytes.fromhex("5502")
            first = await mip.get_status()
            mock.silent.add(0x79)
            try:
                await mip.request(0x79, timeout=0.05)
            except TimeoutError:
                timed_out = True
            else:
                timed_out = False
            return first, timed_out

    assert run(go()) == ((17, 2), True)


def test_mock_emits_events_to_notification_hook():
    async def go():
        mock = MockClient()
        seen = []
        mip = MiP(None, client=mock)
        mip.on_notification = seen.append
        async with mip:
            mock.emit("1D02")
            mock.set_position(1)
        return seen

    assert run(go()) == [bytes.fromhex("1D02"), bytes.fromhex("797C01")]


def test_mock_drop_connection_fires_disconnect_hook():
    async def go():
        mock = MockClient()
        fired = []
        mip = MiP(None, client=mock)
        mip.on_disconnect = lambda: fired.append(True)
        await mip.connect()
        mock.drop_connection(mip)
        return fired, mip.is_connected

    assert run(go()) == ([True], False)
