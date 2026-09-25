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


# -- Python blocks (US-005) -------------------------------------------------

PY_BLOCK = {"name": "Suchlauf", "colour": 200, "mode": "python",
            "params": [{"name": "sekunden", "default": 5}],
            "code": "await mip.drive(12, 8)\nawait mip.stop()"}


def test_check_accepts_valid_code(client):
    r = client.post("/api/blocks/check", json={"code": "await mip.stop()", "params": []})
    assert r.status_code == 200 and r.json()["ok"] is True


@pytest.mark.parametrize("code, message", [
    ("while True:\n    pass", "kein await"),
    ("await mip.stop(", "Zeile 1"),
    ("", "mindestens eine Zeile"),
])
def test_check_refuses_bad_code(client, code, message):
    r = client.post("/api/blocks/check", json={"code": code, "params": []})
    assert r.status_code == 422
    assert message in r.json()["detail"]


def test_creating_a_python_block(client):
    r = client.post("/api/blocks/custom", json={**PY_BLOCK, "create": True})
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "python" and "workspace" not in data
    names = {b["name"] for b in client.get("/api/blocks/custom").json()}
    assert "Suchlauf" in names


def test_creating_refuses_an_existing_name(client):
    client.post("/api/blocks/custom", json={**PY_BLOCK, "create": True})
    r = client.post("/api/blocks/custom", json={**PY_BLOCK, "create": True})
    assert r.status_code == 409
    assert "schon einen Baustein" in r.json()["detail"]


def test_saving_invalid_code_is_refused_and_writes_nothing(client):
    client.post("/api/blocks/custom", json={**PY_BLOCK, "create": True})
    r = client.post("/api/blocks/custom", json={**PY_BLOCK, "code": "while True:\n    pass"})
    assert r.status_code == 422 and "kein await" in r.json()["detail"]
    stored = next(b for b in client.get("/api/blocks/custom").json() if b["name"] == "Suchlauf")
    assert stored["code"] == PY_BLOCK["code"]


def test_body_endpoint_seeds_a_conversion(client):
    """The body a block generates today, without the highlighting hooks."""
    r = client.get("/api/blocks/custom/Celebrate/body")
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "blocks" and data["has_workspace"] is True
    assert "_step" not in data["code"]
    assert "await mip.play_sound(8)" in data["code"]


def test_body_endpoint_of_a_python_block_returns_its_code(client):
    client.post("/api/blocks/custom", json={**PY_BLOCK, "create": True})
    data = client.get("/api/blocks/custom/Suchlauf/body").json()
    assert data["mode"] == "python" and data["code"] == PY_BLOCK["code"]
    assert data["has_workspace"] is False


def test_body_endpoint_for_an_unknown_block(client):
    assert client.get("/api/blocks/custom/Nope/body").status_code == 404


def test_converting_then_regenerating(client):
    before = client.get("/api/blocks/custom/Celebrate/body").json()["code"]
    definition = next(b for b in client.get("/api/blocks/custom").json() if b["name"] == "Celebrate")
    client.post("/api/blocks/custom", json={**definition, "mode": "python",
                                            "code": "await mip.play_sound(20)"})
    converted = next(b for b in client.get("/api/blocks/custom").json() if b["name"] == "Celebrate")
    assert converted["mode"] == "python" and converted["workspace"]        # provenance kept

    r = client.post("/api/blocks/custom/Celebrate/regenerate")
    assert r.status_code == 200
    back = next(b for b in client.get("/api/blocks/custom").json() if b["name"] == "Celebrate")
    assert back.get("mode", "blocks") == "blocks" and "code" not in back
    assert client.get("/api/blocks/custom/Celebrate/body").json()["code"] == before


def test_regenerating_a_block_without_a_workspace_is_refused(client):
    client.post("/api/blocks/custom", json={**PY_BLOCK, "create": True})
    r = client.post("/api/blocks/custom/Suchlauf/regenerate")
    assert r.status_code == 409 and "no blocks to regenerate" in r.json()["detail"]


def test_python_block_generates_and_runs(connected):
    connected.post("/api/blocks/custom", json={**PY_BLOCK, "create": True,
                                               "code": "await mip.play_sound(4)"})
    workspace = ws(start(blk("Suchlauf", "u", inputs={
        "SEKUNDEN": {"block": blk("math_number", "n", {"NUM": 1})}})))
    code = connected.post("/api/blocks/code", json={"workspace": workspace}).json()["code"]
    assert "async def suchlauf(mip, sekunden):" in code
    assert "await suchlauf(mip, 1)" in code

    before = len(writes(0x06))
    connected.post("/api/program/run", json={"workspace": workspace})
    wait_state(connected, "finished")
    assert writes(0x06)[before:] == [bytes.fromhex("0604")]


def test_a_python_block_may_call_another_blocks_function(connected):
    """Every defined block is emitted, so the invisible dependency resolves."""
    connected.post("/api/blocks/custom", json={
        "name": "Ruft Celebrate", "colour": 330, "mode": "python", "params": [],
        "code": "await celebrate(mip)", "create": True})
    workspace = ws(start(blk("Ruft Celebrate", "u")))
    code = connected.post("/api/blocks/code", json={"workspace": workspace}).json()["code"]
    assert "async def celebrate(mip):" in code          # never called from a block
    assert "await celebrate(mip)" in code

    before = len(writes(0x06))
    connected.post("/api/program/run", json={"workspace": workspace})
    state = wait_state(connected, "finished", "error")
    assert state["state"] == "finished", state
    assert writes(0x06)[before:] == [bytes.fromhex("0608")]   # Celebrate's sound


def test_saving_a_program_writes_the_hand_written_body(client):
    client.post("/api/blocks/custom", json={**PY_BLOCK, "create": True,
                                            "code": "await mip.play_sound(4)"})
    workspace = ws(start(blk("Suchlauf", "u", inputs={
        "SEKUNDEN": {"block": blk("math_number", "n", {"NUM": 1})}})))
    client.post("/api/programs", json={"name": "test", "workspace": workspace})
    text = (server.hub.store.programs / "test.py").read_text(encoding="utf-8")
    assert "async def suchlauf(mip, sekunden):\n    await mip.play_sound(4)" in text
