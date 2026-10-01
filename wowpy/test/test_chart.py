"""The dashboard's sensor chart and its sampling (US-007)."""

import time

import pytest
from fastapi.testclient import TestClient

from wowpy import protocol as p
from wowpy.dashboard import server
from wowpy.mock import MOCK_ADDRESS


@pytest.fixture
def client():
    with TestClient(server.app) as c:
        yield c
        c.post("/api/disconnect")


@pytest.fixture
def connected(client):
    assert client.post("/api/connect", json={"address": MOCK_ADDRESS, "name": "Mock MiP"}).status_code == 200
    return client


def writes(opcode=None):
    w = server.hub.mock.writes
    return [x for x in w if opcode is None or x[0] == opcode]


def count_since(mark, opcode):
    return len([w for w in server.hub.mock.writes[mark:] if w[0] == opcode])


def mark():
    return len(server.hub.mock.writes)


# -- the sensor table -------------------------------------------------------

def test_sensors_endpoint_describes_every_lane(client):
    data = client.get("/api/sensors").json()
    keys = [s["key"] for s in data["sensors"]]
    assert keys == ["battery", "position", "odometer", "weight", "volume",
                    "game_mode", "radar", "gesture", "claps", "chest_led", "head_leds"]
    assert data["interval"] == server.CHART_INTERVAL
    assert data["window_minutes"] == 60


def test_each_sensor_says_how_to_draw_it(client):
    for sensor in client.get("/api/sensors").json()["sensors"]:
        assert sensor["kind"] in ("line", "band", "marker", "colour", "leds")
        assert sensor["label"] and sensor["field"]
        assert "poll" not in sensor          # an internal detail


def test_battery_carries_its_warning_threshold(client):
    battery = next(s for s in client.get("/api/sensors").json()["sensors"] if s["key"] == "battery")
    assert battery["warn_below"] == 40
    assert (battery["min"], battery["max"]) == (0, 100)


def test_event_only_sensors_have_no_poll_opcode():
    for key in ("radar", "gesture", "claps"):
        assert p.CHART_SENSORS_BY_KEY[key]["poll"] is None
    assert p.chart_poll_opcodes(["radar", "gesture", "claps"]) == ()


def test_poll_opcodes_are_deduplicated():
    # battery and position both come from Get status
    assert p.chart_poll_opcodes(["battery", "position"]) == (p.CMD_GET_STATUS,)
    assert p.chart_poll_opcodes(["battery", "weight"]) == (p.CMD_GET_STATUS, p.CMD_GET_WEIGHT)


def test_unknown_sensor_keys_are_ignored():
    assert p.chart_poll_opcodes(["battery", "nonsense"]) == (p.CMD_GET_STATUS,)


# -- the subscription -------------------------------------------------------

def test_a_page_registers_what_it_charts(connected):
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chart", "sensors": ["battery", "weight"]})
        time.sleep(0.2)
        assert server.hub.chart_keys() == {"battery", "weight"}
        assert server.hub.chart_opcodes() == (p.CMD_GET_STATUS, p.CMD_GET_WEIGHT)


def test_two_pages_are_unioned(connected):
    with connected.websocket_connect("/ws") as a, connected.websocket_connect("/ws") as b:
        a.receive_json(), b.receive_json()
        a.send_json({"type": "chart", "sensors": ["battery"]})
        b.send_json({"type": "chart", "sensors": ["volume"]})
        time.sleep(0.2)
        assert server.hub.chart_keys() == {"battery", "volume"}


def test_closing_a_page_drops_its_sensors(connected):
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chart", "sensors": ["weight"]})
        time.sleep(0.2)
        assert server.hub.chart_keys() == {"weight"}
    time.sleep(0.3)
    assert server.hub.chart_keys() == set()


def test_an_empty_selection_unsubscribes(connected):
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chart", "sensors": ["battery"]})
        time.sleep(0.2)
        ws.send_json({"type": "chart", "sensors": []})
        time.sleep(0.2)
        assert server.hub.chart_keys() == set()
        assert server.hub.chart_opcodes() == ()


# -- the sampling ------------------------------------------------------------

def test_weight_is_never_polled_unless_charted(connected):
    """0x81 is deliberately absent from the ordinary status poll."""
    start = mark()
    time.sleep(2.5)
    assert count_since(start, p.CMD_GET_WEIGHT) == 0


def test_a_charted_sensor_is_sampled_about_once_a_second(connected):
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chart", "sensors": ["weight"]})
        time.sleep(0.3)
        start = mark()
        time.sleep(3.2)
        samples = count_since(start, p.CMD_GET_WEIGHT)
    assert 2 <= samples <= 5, samples


def test_only_the_charted_sensors_get_the_fast_poll(connected):
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chart", "sensors": ["battery"]})
        time.sleep(0.3)
        start = mark()
        time.sleep(3.2)
        status = count_since(start, p.CMD_GET_STATUS)
        weight = count_since(start, p.CMD_GET_WEIGHT)
    assert status >= 2
    assert weight == 0


def test_the_slow_poll_does_not_repeat_what_the_chart_samples(connected):
    """Battery is charted, so the 5 s poll should leave Get status alone."""
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chart", "sensors": ["battery"]})
        time.sleep(0.3)
        start = mark()
        time.sleep(3.2)
        status = count_since(start, p.CMD_GET_STATUS)
    # ~1/s from the chart; a duplicating slow poll would push this higher
    assert status <= 5, status


def test_sampling_pauses_while_driving(connected):
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chart", "sensors": ["battery", "weight"]})
        time.sleep(0.3)
        # hold the drive the way the page does, then measure strictly inside
        deadline = time.monotonic() + 2.0
        ws.send_json({"type": "drive", "speed": 20, "turn": 0})
        time.sleep(0.4)
        start = mark()
        while time.monotonic() < deadline:
            ws.send_json({"type": "drive", "speed": 20, "turn": 0})
            time.sleep(0.04)
        during_status = count_since(start, p.CMD_GET_STATUS)
        during_weight = count_since(start, p.CMD_GET_WEIGHT)
        ws.send_json({"type": "stop"})
        time.sleep(1.5)
        after = count_since(start, p.CMD_GET_WEIGHT)
    assert during_status == 0, during_status
    assert during_weight == 0, during_weight
    assert after > 0           # resumes once the robot is idle again


def test_reconnecting_starts_the_subscription_empty(connected):
    with connected.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chart", "sensors": ["weight"]})
        time.sleep(0.2)
    connected.post("/api/disconnect")
    connected.post("/api/connect", json={"address": MOCK_ADDRESS, "name": "Mock MiP"})
    assert server.hub.chart_keys() == set()


def test_charting_without_a_connection_does_not_crash(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "chart", "sensors": ["battery"]})
        time.sleep(0.3)
        assert server.hub.chart_keys() == {"battery"}
