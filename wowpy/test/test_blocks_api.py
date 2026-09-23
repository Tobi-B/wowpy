"""Block-programming API tests against the mock robot (US-003)."""

import time

import pytest
from fastapi.testclient import TestClient

from wowpy import protocol as p
from wowpy.blocks import BLOCKS_BY_TYPE
from wowpy.dashboard import server
from wowpy.mock import MOCK_ADDRESS
from wowpy.storage import Store


@pytest.fixture
def client(tmp_path):
    original = server.hub.store
    server.hub.store = Store(tmp_path)
    # keep the shipped blocks available
    for definition in original.list_blocks():
        server.hub.store.save_block(definition)
    with TestClient(server.app) as c:
        yield c
        c.post("/api/program/stop")
        c.post("/api/disconnect")
    server.hub.store = original


@pytest.fixture
def connected(client):
    assert client.post("/api/connect", json={"address": MOCK_ADDRESS, "name": "Mock MiP"}).status_code == 200
    return client


def writes(opcode=None):
    w = server.hub.mock.writes
    return [x for x in w if opcode is None or x[0] == opcode]


def ws(*tops):
    return {"blocks": {"languageVersion": 0, "blocks": list(tops)}}


def start(body):
    return {"type": "mip_on_start", "id": "s", "inputs": {"BODY": {"block": body}}}


def blk(type_, id_="b", fields=None, next_=None, inputs=None):
    b = {"type": type_, "id": id_}
    if fields:
        b["fields"] = fields
    if inputs:
        b["inputs"] = inputs
    if next_:
        b["next"] = {"block": next_}
    return b


def wait_for(predicate, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def wait_state(client, *states, timeout=3.0):
    got = []

    def done():
        got.append(client.get("/api/program/state").json())
        return got[-1]["state"] in states
    ok = wait_for(done, timeout)
    assert ok, f"state stayed {got[-1] if got else None}, wanted one of {states}"
    return got[-1]


# -- catalogue --------------------------------------------------------------

def test_catalogue_lists_toolbox_and_blocks(client):
    cat = client.get("/api/blocks/catalogue").json()
    labels = [t["label"] for t in cat["toolbox"]]
    assert labels == ["Robot: LEDs", "Robot: Move", "Robot: Sound", "Robot: Body",
                      "Robot: Sensing", "Sensors", "Events", "Control"]
    assert {b["type"] for b in cat["blocks"]} == set(BLOCKS_BY_TYPE)
    assert all("colour" in b for b in cat["blocks"])


def test_every_sendable_command_has_a_block(client):
    """Every non-query command is reachable from some block's generated code."""
    code = " ".join(b["code"] for b in client.get("/api/blocks/catalogue").json()["blocks"])
    skipped = {"Disconnect app", "Send IR", "Set user data", "Set MiP detection", "Drive"}
    method = {
        "Set chest LED": "set_chest_led", "Flash chest LED": "flash_chest_led",
        "Set head LEDs": "set_head_leds", "Drive forward": "drive_{DIR}", "Drive backward": "drive_{DIR}",
        "Turn left": "turn_{DIR}", "Turn right": "turn_{DIR}", "Drive distance": "drive_distance",
        "Stop": "stop()", "Play sound": "play_sound", "Set volume": "set_volume",
    }
    for cmd in p.COMMANDS:
        if cmd.query or cmd.name in skipped:
            continue
        needle = method.get(cmd.name) or f"'{cmd.name}'"
        assert needle in code, f"no block generates {cmd.name}"


def test_shipped_composite_blocks_are_offered(client):
    names = {b["name"] for b in client.get("/api/blocks/custom", ).json()}
    assert names >= {"Celebrate", "Patrol", "Look around", "Alarm", "Stand up and centre"}


def test_code_endpoint_matches_the_story_example(client):
    workspace = ws(start(blk("mip_chest_led", "b", {"COLOUR": "#ff0000"},
                             next_=blk("mip_wait", "c", {"SECS": 1},
                                       next_=blk("mip_chest_led", "d", {"COLOUR": "#0000ff"})))))
    code = client.post("/api/blocks/code", json={"workspace": workspace}).json()["code"]
    assert "async def main(mip):" in code
    assert "await mip.set_chest_led(255, 0, 0)" in code
    assert "await asyncio.sleep(1)" in code
    assert "await mip.set_chest_led(0, 0, 255)" in code


# -- running ----------------------------------------------------------------

def test_run_is_refused_without_a_connection(client):
    r = client.post("/api/program/run", json={"workspace": ws(start(blk("mip_stop")))})
    assert r.status_code == 409 and r.json()["detail"] == "Connect to a MiP first"


def test_running_sends_commands_in_order(connected):
    workspace = ws(start(blk("mip_chest_led", "b", {"COLOUR": "#ff0000"},
                             next_=blk("mip_wait", "w", {"SECS": 0.2},
                                       next_=blk("mip_play_sound", "p", {"INDEX": 3},
                                                 next_=blk("mip_stop", "s"))))))
    before = len(writes())
    connected.post("/api/program/run", json={"workspace": workspace})
    wait_state(connected, "finished")
    sent = [w.hex(" ").upper() for w in writes()[before:] if w[0] in (0x84, 0x06, 0x77)]
    assert sent == ["84 FF 00 00", "06 03", "77"]


def test_stop_halts_a_forever_program(connected):
    workspace = ws(start(blk("mip_forever", "f", inputs={
        "BODY": {"block": blk("mip_play_sound", "p", {"INDEX": 1},
                              next_=blk("mip_wait", "w", {"SECS": 0.05}))}})))
    connected.post("/api/program/run", json={"workspace": workspace})
    assert wait_for(lambda: len(writes(0x06)) >= 2)
    connected.post("/api/program/stop")
    state = wait_state(connected, "stopped")
    assert state["state"] == "stopped"
    count = len(writes(0x06))
    time.sleep(0.2)
    assert len(writes(0x06)) == count
    assert writes(0x77)


def test_drive_block_stops_the_robot_afterwards(connected):
    workspace = ws(start(blk("mip_drive_for", "d", {"SECS": 0.3, "SPEED": 20, "TURN": 0})))
    connected.post("/api/program/run", json={"workspace": workspace})
    wait_state(connected, "finished")
    drives = writes(0x78)
    assert len(drives) >= 5
    assert all(w == bytes.fromhex("781400") for w in drives)
    assert writes()[-1] == bytes([0x77])


def test_runtime_error_reports_the_block(connected):
    bad = blk("mip_play_sound", "boom", {"INDEX": 1})
    bad["inputs"] = {}
    workspace = ws(start(blk("mip_wait", "w", {"SECS": 0})))
    # force an error: division by zero through a math block
    workspace = ws(start({
        "type": "variables_set", "id": "v", "fields": {"VAR": {"name": "x"}},
        "inputs": {"VALUE": {"block": {"type": "math_arithmetic", "id": "m", "fields": {"OP": "DIVIDE"},
                                       "inputs": {"A": {"block": blk("math_number", "a", {"NUM": 10})},
                                                  "B": {"block": blk("math_number", "b", {"NUM": 0})}}}}}}))
    connected.post("/api/program/run", json={"workspace": workspace})
    state = wait_state(connected, "error")
    assert "division by zero" in (state["error"] or "")


def test_a_second_run_while_running_is_refused(connected):
    workspace = ws(start(blk("mip_forever", "f", inputs={
        "BODY": {"block": blk("mip_wait", "w", {"SECS": 0.05})}})))
    connected.post("/api/program/run", json={"workspace": workspace})
    wait_state(connected, "running")
    r = connected.post("/api/program/run", json={"workspace": workspace})
    assert r.status_code == 409
    connected.post("/api/program/stop")


def test_disconnect_stops_a_running_program(connected):
    workspace = ws(start(blk("mip_forever", "f", inputs={
        "BODY": {"block": blk("mip_wait", "w", {"SECS": 0.05})}})))
    connected.post("/api/program/run", json={"workspace": workspace})
    wait_state(connected, "running")
    connected.post("/api/mock/drop")
    state = wait_state(connected, "stopped (disconnected)")
    assert state["state"] == "stopped (disconnected)"


def test_program_state_is_pushed_over_the_websocket(connected):
    workspace = ws(start(blk("mip_play_sound", "p", {"INDEX": 2})))
    with connected.websocket_connect("/ws") as sock:
        assert sock.receive_json()["type"] == "snapshot"
        connected.post("/api/program/run", json={"workspace": workspace})
        seen = []
        for _ in range(12):
            m = sock.receive_json()
            seen.append(m)
            if m.get("type") == "program" and m.get("state") in ("finished", "error"):
                break
    programs = [m for m in seen if m["type"] == "program"]
    assert programs[0]["state"] == "running"
    assert programs[-1]["state"] == "finished"
    assert any(m["type"] == "log" and m.get("text") == "program" for m in seen)


# -- events -----------------------------------------------------------------

def test_clap_event_runs_its_stack(connected):
    workspace = ws(blk("mip_on_clap", "h", {"N": 2},
                       inputs={"BODY": {"block": blk("mip_chest_led", "c", {"COLOUR": "#ffff00"})}}))
    connected.post("/api/program/run", json={"workspace": workspace})
    wait_state(connected, "running")
    connected.post("/api/mock/emit", json={"hex": "1D02"})
    assert wait_for(lambda: bytes.fromhex("84FFFF00") in writes(0x84))
    connected.post("/api/program/stop")


def test_position_event_only_fires_for_the_chosen_position(connected):
    workspace = ws(blk("mip_on_position", "h", {"POS": "face down"},
                       inputs={"BODY": {"block": blk("mip_play_sound", "p", {"INDEX": 5})}}))
    connected.post("/api/program/run", json={"workspace": workspace})
    wait_state(connected, "running")
    connected.post("/api/mock/emit", json={"hex": "797901"})
    assert wait_for(lambda: bytes.fromhex("0605") in writes(0x06))
    count = len(writes(0x06))
    connected.post("/api/mock/emit", json={"hex": "797902"})
    time.sleep(0.2)
    assert len(writes(0x06)) == count
    connected.post("/api/program/stop")


def test_every_timer_repeats(connected):
    workspace = ws(blk("mip_every", "t", {"SECS": 0.05},
                       inputs={"BODY": {"block": blk("mip_play_sound", "p", {"INDEX": 1})}}))
    connected.post("/api/program/run", json={"workspace": workspace})
    assert wait_for(lambda: len(writes(0x06)) >= 4)
    connected.post("/api/program/stop")
    wait_state(connected, "stopped")
    count = len(writes(0x06))
    time.sleep(0.2)
    assert len(writes(0x06)) == count


def test_sensor_condition_uses_live_values(connected):
    connected.post("/api/mock/battery/85")      # 0x55 -> 17 %
    connected.post("/api/refresh")
    workspace = ws(start({
        "type": "controls_if", "id": "i",
        "inputs": {
            "IF0": {"block": {"type": "logic_compare", "id": "c", "fields": {"OP": "LT"},
                              "inputs": {"A": {"block": blk("mip_battery", "bat")},
                                         "B": {"block": blk("math_number", "n", {"NUM": 40})}}}},
            "DO0": {"block": blk("mip_chest_led", "r", {"COLOUR": "#ff0000"})},
            "ELSE": {"block": blk("mip_chest_led", "g", {"COLOUR": "#00ff00"})}}}))
    before = len(writes(0x84))
    connected.post("/api/program/run", json={"workspace": workspace})
    wait_state(connected, "finished")
    assert writes(0x84)[before:] == [bytes.fromhex("84FF0000")]


# -- persistence ------------------------------------------------------------

def test_save_and_load_a_program(client):
    workspace = ws(start(blk("mip_chest_led", "b", {"COLOUR": "#ff0000"})))
    r = client.post("/api/programs", json={"name": "red light", "workspace": workspace})
    assert r.status_code == 200
    assert "await mip.set_chest_led(255, 0, 0)" in r.json()["code"]
    assert client.get("/api/programs").json() == ["red light"]
    assert client.get("/api/programs/red light").json()["workspace"] == workspace


def test_unsafe_program_name_is_rejected(client):
    r = client.post("/api/programs", json={"name": "../etc/passwd", "workspace": ws()})
    assert r.status_code == 422
    assert r.json()["detail"] == "letters, digits, spaces and dashes only"
    assert client.get("/api/programs").json() == []


def test_loading_an_unknown_program(client):
    assert client.get("/api/programs/nope").status_code == 404


def test_custom_block_round_trip(client):
    definition = {"name": "Warn and turn", "colour": 20, "params": [{"name": "angle", "default": 90}],
                  "workspace": ws(blk("mip_chest_led", "w", {"COLOUR": "#ff0000"}))}
    assert client.post("/api/blocks/custom", json=definition).status_code == 200
    names = {b["name"] for b in client.get("/api/blocks/custom").json()}
    assert "Warn and turn" in names
    use = blk("Warn and turn", "u", inputs={"ANGLE": {"block": blk("math_number", "n", {"NUM": 45})}})
    code = client.post("/api/blocks/code", json={"workspace": ws(start(use))}).json()["code"]
    assert "async def warn_and_turn(mip, angle):" in code
    assert "await warn_and_turn(mip, 45)" in code


def test_deleting_a_custom_block_in_use_is_refused(client):
    definition = {"name": "Warn and turn", "colour": 20, "params": [],
                  "workspace": ws(blk("mip_chest_led", "w", {"COLOUR": "#ff0000"}))}
    client.post("/api/blocks/custom", json=definition)
    client.post("/api/programs", json={"name": "uses it", "workspace": ws(start(blk("Warn and turn", "u")))})
    r = client.delete("/api/blocks/custom/Warn and turn")
    assert r.status_code == 409
    assert r.json()["detail"] == "Warn and turn is still used 1 time in saved programs"
    assert any(b["name"] == "Warn and turn" for b in client.get("/api/blocks/custom").json())
    assert client.delete("/api/blocks/custom/Warn and turn?force=true").status_code == 200


def test_editing_a_custom_block_changes_every_use(client):
    definition = {"name": "Warn", "colour": 20, "params": [],
                  "workspace": ws(blk("mip_play_sound", "w", {"INDEX": 3}))}
    client.post("/api/blocks/custom", json=definition)
    use = blk("Warn", "u1", next_=blk("Warn", "u2"))
    code = client.post("/api/blocks/code", json={"workspace": ws(start(use))}).json()["code"]
    assert code.count("await mip.play_sound(3)") == 1
    definition["workspace"] = ws(blk("mip_play_sound", "w", {"INDEX": 7}))
    client.post("/api/blocks/custom", json=definition)
    code = client.post("/api/blocks/code", json={"workspace": ws(start(use))}).json()["code"]
    assert "await mip.play_sound(7)" in code
    assert "await mip.play_sound(3)" not in code
    assert code.count("await warn(mip)") == 2
