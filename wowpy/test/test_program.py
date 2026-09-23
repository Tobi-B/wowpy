import asyncio
import time

import pytest

from wowpy.mip import MiP
from wowpy.mock import MockClient
from wowpy.program import Program, ProgramError

HEADER = "import asyncio\n\n"


def run(coro):
    return asyncio.run(coro)


async def _connected():
    mock = MockClient()
    mip = MiP(None, client=mock)
    await mip.connect()
    return mip, mock


def sent(mock, opcode=None):
    return [w for w in mock.writes if opcode is None or w[0] == opcode]


def test_simple_program_sends_commands_in_order():
    async def go():
        mip, mock = await _connected()
        prog = Program(mip)
        code = HEADER + (
            "async def main(mip):\n"
            "    await _step('a')\n"
            "    await mip.set_chest_led(255, 0, 0)\n"
            "    await asyncio.sleep(0.2)\n"
            "    await _step('b')\n"
            "    await mip.play_sound(3)\n"
            "    await mip.stop()\n")
        t0 = time.monotonic()
        state = await prog.run(code)
        return state, [w.hex(" ").upper() for w in mock.writes], time.monotonic() - t0

    state, writes, elapsed = run(go())
    assert state == "finished"
    assert writes == ["84 FF 00 00", "06 03", "77"]
    assert elapsed >= 0.2


def test_step_reports_the_current_block():
    seen = []

    async def go():
        mip, _ = await _connected()
        prog = Program(mip, on_state=lambda s, b, e: seen.append((s, b)))
        await prog.run(HEADER + "async def main(mip):\n    await _step('one')\n    await _step('two')\n")

    run(go())
    assert ("running", "one") in seen and ("running", "two") in seen
    assert seen[-1][0] == "finished" and seen[-1][1] is None


def test_stop_cancels_a_forever_loop():
    async def go():
        mip, mock = await _connected()
        prog = Program(mip)
        code = HEADER + "async def main(mip):\n    while True:\n        await mip.play_sound(1)\n        await asyncio.sleep(0.02)\n"
        task = asyncio.ensure_future(prog.run(code))
        await asyncio.sleep(0.15)
        await prog.stop_and_halt()
        state = await task
        count = len(sent(mock, 0x06))
        await asyncio.sleep(0.1)
        return state, count, len(sent(mock, 0x06)), sent(mock, 0x77)

    state, count, after, stops = run(go())
    assert state == "stopped"
    assert count >= 2
    assert after == count          # nothing more was sent
    assert stops                   # the robot was halted


def test_drive_for_always_ends_with_stop():
    async def go():
        mip, mock = await _connected()
        prog = Program(mip)
        await prog.run(HEADER + "async def main(mip):\n    await mip.drive_for(0.3, 20, 0)\n")
        return sent(mock, 0x78), mock.writes[-1]

    drives, last = run(go())
    assert len(drives) >= 6
    assert all(w == bytes.fromhex("781400") for w in drives)
    assert last == bytes([0x77])


def test_cancelled_drive_still_stops_the_robot():
    async def go():
        mip, mock = await _connected()
        prog = Program(mip)
        task = asyncio.ensure_future(prog.run(HEADER + "async def main(mip):\n    await mip.drive_for(5, 20, 0)\n"))
        await asyncio.sleep(0.15)
        prog.stop()
        await task
        return mock.writes[-1]

    assert run(go()) == bytes([0x77])


def test_runtime_error_reports_state_and_block():
    states = []

    async def go():
        mip, _ = await _connected()
        prog = Program(mip, on_state=lambda s, b, e: states.append((s, b, e)))
        return await prog.run(HEADER + "async def main(mip):\n    await _step('boom')\n    1 / 0\n")

    assert run(go()) == "error"
    final = states[-1]
    assert final[0] == "error" and final[1] == "boom" and "division by zero" in final[2]


def test_syntax_error_is_reported_as_program_error():
    async def go():
        mip, _ = await _connected()
        with pytest.raises(ProgramError, match="syntax error"):
            await Program(mip).run("async def main(mip)\n    pass\n")

    run(go())


def test_program_without_main_or_events_is_rejected():
    async def go():
        mip, _ = await _connected()
        with pytest.raises(ProgramError, match="no 'when program starts'"):
            await Program(mip).run("x = 1\n")

    run(go())


# -- events ----------------------------------------------------------------

def test_clap_event_starts_its_stack():
    async def go():
        mip, mock = await _connected()
        prog = Program(mip)
        code = HEADER + (
            "async def _on_clap(mip):\n"
            "    await mip.set_chest_led(255, 255, 0)\n"
            "program.on_clap(_on_clap, count=2)\n")
        task = asyncio.ensure_future(prog.run(code))
        await asyncio.sleep(0.05)
        mock.emit("1D02")
        await asyncio.sleep(0.1)
        prog.stop()
        await task
        return sent(mock, 0x84)

    assert run(go()) == [bytes.fromhex("84FFFF00")]


def test_clap_event_ignores_a_different_count():
    async def go():
        mip, mock = await _connected()
        prog = Program(mip)
        code = HEADER + "async def _h(mip):\n    await mip.play_sound(1)\nprogram.on_clap(_h, count=2)\n"
        task = asyncio.ensure_future(prog.run(code))
        await asyncio.sleep(0.05)
        mock.emit("1D03")
        await asyncio.sleep(0.1)
        prog.stop()
        await task
        return sent(mock, 0x06)

    assert run(go()) == []


def test_position_event_fires_only_on_change():
    async def go():
        mip, mock = await _connected()
        prog = Program(mip)
        code = HEADER + ("async def _h(mip):\n    await mip.play_sound(5)\n"
                         "program.on_position(_h, position='face down')\n")
        task = asyncio.ensure_future(prog.run(code))
        await asyncio.sleep(0.05)
        mock.emit("797901")          # face down
        await asyncio.sleep(0.08)
        first = len(sent(mock, 0x06))
        mock.emit("797902")          # upright: handler must not fire
        await asyncio.sleep(0.08)
        prog.stop()
        await task
        return first, len(sent(mock, 0x06))

    first, total = run(go())
    assert first == 1 and total == 1


def test_every_timer_repeats_until_stopped():
    async def go():
        mip, mock = await _connected()
        prog = Program(mip)
        code = HEADER + "async def _t(mip):\n    await mip.play_sound(1)\nprogram.every(0.05, _t)\n"
        task = asyncio.ensure_future(prog.run(code))
        await asyncio.sleep(0.32)
        during = len(sent(mock, 0x06))
        prog.stop()
        await task
        await asyncio.sleep(0.1)
        return during, len(sent(mock, 0x06))

    during, after = run(go())
    assert during >= 4
    assert after == during


def test_event_program_keeps_running_after_main_finishes():
    async def go():
        mip, mock = await _connected()
        prog = Program(mip)
        code = HEADER + ("async def main(mip):\n    await mip.set_volume(7)\n"
                         "async def _h(mip):\n    await mip.play_sound(2)\n"
                         "program.on_clap(_h)\n")
        task = asyncio.ensure_future(prog.run(code))
        await asyncio.sleep(0.1)
        state_during = prog.state
        mock.emit("1D01")
        await asyncio.sleep(0.1)
        prog.stop()
        return state_during, await task, sent(mock, 0x06)

    during, final, sounds = run(go())
    assert during == "running" and final == "stopped"
    assert sounds == [bytes.fromhex("0602")]


# -- sensors ----------------------------------------------------------------

def test_sensor_values_come_from_the_status_cache():
    async def go():
        mip, mock = await _connected()
        prog = Program(mip)
        prog.status.update({"battery": 17, "position": 1})
        code = HEADER + (
            "async def main(mip):\n"
            "    if (await sensors.battery() < 40):\n"
            "        await mip.set_chest_led(255, 0, 0)\n"
            "    else:\n"
            "        await mip.set_chest_led(0, 255, 0)\n")
        await prog.run(code)
        return sent(mock, 0x84)

    assert run(go()) == [bytes.fromhex("84FF0000")]


def test_sensor_queries_the_robot_when_the_value_is_unknown():
    async def go():
        mip, mock = await _connected()
        prog = Program(mip)
        code = HEADER + "async def main(mip):\n    global v\n    v = await sensors.battery()\n"
        ns_before = len(sent(mock, 0x79))
        await prog.run(code)
        return ns_before, len(sent(mock, 0x79)), prog.status.get("battery")

    before, after, battery = run(go())
    assert after > before
    assert battery == 100


def test_position_sensor_returns_a_name():
    async def go():
        mip, _ = await _connected()
        prog = Program(mip)
        prog.status["position"] = 2
        out = {}
        code = HEADER + "async def main(mip):\n    result['p'] = await sensors.position()\n"
        ns = prog.namespace()
        ns["result"] = out
        exec(compile(code, "<t>", "exec"), ns)
        await ns["main"](mip)
        return out["p"]

    assert run(go()) == "upright"
