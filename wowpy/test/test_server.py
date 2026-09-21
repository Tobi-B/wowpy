"""Dashboard API tests against the mock robot (no hardware, no browser)."""

import pytest
from fastapi.testclient import TestClient

from wowpy.dashboard import server
from wowpy.mock import MOCK_ADDRESS


@pytest.fixture
def client():
    with TestClient(server.app) as c:
        yield c
        c.post("/api/disconnect")


@pytest.fixture
def connected(client):
    r = client.post("/api/connect", json={"address": MOCK_ADDRESS, "name": "Mock MiP"})
    assert r.status_code == 200 and r.json()["state"] == "connected"
    return client


def writes(opcode=None):
    w = server.hub.mock.writes
    return [x for x in w if opcode is None or x[0] == opcode]


def test_commands_metadata_lists_every_family(client):
    meta = client.get("/api/commands").json()
    assert meta["families"] == ["LEDs", "Driving", "Position & balance", "Sound", "Game modes", "Sensing", "IR", "System", "Raw"]
    families = {c["family"] for c in meta["commands"]}
    assert families == set(meta["families"]) - {"Raw"}
    forward = next(c for c in meta["commands"] if c["name"] == "Drive forward")
    assert forward["params"][1] == {"name": "time_ms", "min": 0, "max": 1785, "default": 700, "unit": "ms", "choices": None}


def test_scan_always_lists_the_mock(client):
    devices = client.post("/api/scan", params={"timeout": 0.1}).json()
    assert devices[0] == {"name": "Mock MiP", "address": MOCK_ADDRESS, "rssi": None}


def test_commands_are_refused_while_disconnected(client):
    r = client.post("/api/command", json={"name": "Stop"})
    assert r.status_code == 409 and r.json()["detail"] == "Connect to a MiP first"


def test_connect_queries_versions_and_status(connected):
    state = connected.get("/api/state").json()
    assert state["connection"]["state"] == "connected"
    assert state["status"]["battery"] == 100 and state["status"]["position"] == 2
    assert state["status"]["software_version"] == "2023-01-27 rev 1"
    assert state["status"]["hardware_version"] == "1 (voice chip 3)"
    assert state["status"]["odometer_cm"] == 200
    assert len(writes(0x14)) == 1 and len(writes(0x19)) == 1


def test_command_is_encoded_and_sent(connected):
    r = connected.post("/api/command", json={"name": "Set chest LED", "params": {"r": 255, "g": 0, "b": 128}})
    assert r.json() == {"sent": "84 FF 00 80"}
    assert writes(0x84)[-1] == bytes.fromhex("84FF0080")
    # a related getter is re-queried so the status panel follows the change
    assert writes(0x83)
    assert connected.get("/api/state").json()["status"]["chest_led"] == [255, 0, 128]


def test_out_of_range_parameter_is_rejected_before_sending(connected):
    before = len(writes())
    r = connected.post("/api/command", json={"name": "Drive forward", "params": {"speed": 31, "time_ms": 700}})
    assert r.status_code == 422 and r.json()["detail"] == "speed: 0–30"
    assert len(writes()) == before


def test_raw_bytes(connected):
    assert connected.post("/api/raw", json={"bytes": "F0 01 02"}).json() == {"sent": "F0 01 02"}
    assert writes(0xF0)[-1] == b"\xf0\x01\x02"
    r = connected.post("/api/raw", json={"bytes": "F0 0G"})
    assert r.status_code == 422 and r.json()["detail"] == "hex bytes only, e.g. 84 FF 00 00"


def test_websocket_streams_log_and_status(connected):
    with connected.websocket_connect("/ws") as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot" and snap["connection"]["state"] == "connected"
        connected.post("/api/command", json={"name": "Get status"})
        seen = [ws.receive_json() for _ in range(3)]
        kinds = [(m["type"], m.get("dir")) for m in seen]
        assert ("log", "sent") in kinds and ("log", "received") in kinds and ("status", None) in kinds
        recv = next(m for m in seen if m.get("dir") == "received")
        assert recv["name"] == "Get status" and recv["bytes"] == "79 7C 02" and recv["text"] == "battery 100%, upright"
        assert len(recv["ts"]) == 23  # ISO with milliseconds


def test_websocket_hold_to_drive_and_stop(connected):
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "drive", "speed": 20, "turn": 0})
        ws.send_json({"type": "drive", "speed": 10, "turn": -5})
        ws.send_json({"type": "stop"})
        # stop is logged; wait for it so the writes are in
        while ws.receive_json().get("name") != "Stop":
            pass
    assert [w for w in writes() if w[0] in (0x78, 0x77)] == [bytes.fromhex("781400"), bytes.fromhex("780A65"), bytes([0x77])]


def test_unsolicited_events_update_status_and_log(connected):
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        connected.post("/api/mock/emit", json={"hex": "1D02"})
        msgs = [ws.receive_json(), ws.receive_json()]   # log + status (claps field)
        log = next(m for m in msgs if m["type"] == "log")
        assert log["name"] == "Clap detected" and log["text"] == "2 claps"
        assert next(m for m in msgs if m["type"] == "status")["fields"]["claps"] == 2
        connected.post("/api/mock/position/1")
        msgs = [ws.receive_json(), ws.receive_json()]
        status = next(m for m in msgs if m["type"] == "status")
        assert status["fields"]["position"] == 1


def test_unknown_reply_is_logged(connected):
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        connected.post("/api/mock/emit", json={"hex": "F001"})
        m = ws.receive_json()
        assert m["name"] == "unknown (0xF0)" and m["bytes"] == "F0 01"


def test_query_timeout_keeps_last_values(connected):
    connected.post("/api/mock/override", json={"opcode": 0x79, "reply": None})
    before = connected.get("/api/state").json()["status"]["battery"]
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        connected.post("/api/command", json={"name": "Get status"})
        msgs = [ws.receive_json(), ws.receive_json()]
        assert any(m.get("dir") == "timeout" and m["name"] == "Get status" for m in msgs)
    assert connected.get("/api/state").json()["status"]["battery"] == before


def test_dropped_connection_is_reported(connected):
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        connected.post("/api/mock/drop")
        msgs = [ws.receive_json(), ws.receive_json()]
        assert any(m["type"] == "connection" and m["state"] == "disconnected" for m in msgs)
        assert any(m["type"] == "log" and m["name"] == "disconnected" for m in msgs)
    assert connected.post("/api/command", json={"name": "Stop"}).status_code == 409


def test_disconnect_then_reconnect(connected):
    assert connected.post("/api/disconnect").json()["state"] == "disconnected"
    r = connected.post("/api/connect", json={"address": MOCK_ADDRESS, "name": "Mock MiP"})
    assert r.json()["state"] == "connected"
