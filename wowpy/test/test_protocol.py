import pytest

from wowpy import protocol as p


def build(name, **params):
    return p.COMMANDS_BY_NAME[name].build(**params).hex(" ").upper()


# One sample per family, mirroring the Scenario Outline in US-001.
@pytest.mark.parametrize(
    "name, params, expected",
    [
        ("Set chest LED", dict(r=255, g=0, b=128), "84 FF 00 80"),
        ("Flash chest LED", dict(r=0, g=255, b=0, on_ms=500, off_ms=200), "89 00 FF 00 19 0A"),
        ("Set head LEDs", dict(led1=0, led2=1, led3=2, led4=3), "8A 00 01 02 03"),
        ("Drive forward", dict(speed=20, time_ms=700), "71 14 64"),
        ("Turn left", dict(degrees=90, speed=12), "73 12 0C"),
        ("Stop", {}, "77"),
        ("Get status", {}, "79"),
        ("Play sound", dict(index=10), "06 0A"),
        ("Set volume", dict(level=7), "15 07"),
        ("Set game mode", dict(mode=1), "76 01"),
        ("Get odometer", {}, "85"),
        ("Get software version", {}, "14"),
        ("Drive", dict(speed=10, turn=-5), "78 0A 65"),
        ("Drive distance", dict(distance_cm=-30, turn_degrees=-300), "70 01 1E 01 01 2C"),
        ("Set clap delay", dict(delay_ms=500), "20 01 F4"),
        ("Send IR", dict(byte1=1, byte2=2, byte3=3, byte4=4, power=60), "8C 01 02 03 04 3C"),
        ("Get user data", dict(address=5), "13 05"),
    ],
)
def test_command_encoding(name, params, expected):
    assert build(name, **params) == expected


def test_defaults_are_used_for_missing_params():
    assert build("Set chest LED") == "84 FF 00 00"


@pytest.mark.parametrize(
    "name, params, message",
    [
        ("Drive forward", dict(speed=31, time_ms=700), "speed: 0–30"),
        ("Turn left", dict(degrees=1280), "degrees: 0–1275"),
        ("Set game mode", dict(mode=9), "mode: must be one of"),
        ("Set volume", dict(level=7, bogus=1), "unknown parameter"),
    ],
)
def test_out_of_range_is_rejected(name, params, message):
    with pytest.raises(ValueError, match=message):
        p.COMMANDS_BY_NAME[name].build(**params)


def test_every_command_has_a_family_and_unique_name():
    names = [c.name for c in p.COMMANDS]
    assert len(names) == len(set(names))
    assert all(c.family in p.FAMILIES for c in p.COMMANDS)
    assert set(c.family for c in p.COMMANDS) == set(p.FAMILIES) - {"Raw"}


def test_parse_raw():
    assert p.parse_raw("F0 01 02") == b"\xf0\x01\x02"
    assert p.parse_raw("f00102") == b"\xf0\x01\x02"
    for bad in ("", "F0 0G", "F0 1"):
        with pytest.raises(ValueError, match="hex bytes only, e.g. 84 FF 00 00"):
            p.parse_raw(bad)


@pytest.mark.parametrize(
    "data, name, text",
    [
        ("797C02", "Get status", "battery 100%, upright"),
        ("794D00", "Get status", "battery 0%, on back"),
        ("1D02", "Clap detected", "2 claps"),
        ("1D01", "Clap detected", "1 clap"),
        ("F001", "unknown (0xF0)", "01"),
        ("1417011B01", "Get software version", "2023-01-27 rev 1"),
        ("190103", "Get hardware version", "1 (voice chip 3)"),
        ("85000000C8", "Get odometer", "200 cm"),
        ("1604", "Get volume", "volume 4"),
        ("8201", "Get game mode", "app"),
        ("0A0F", "Gesture detected", "forward"),
        ("0C03", "Radar", "object < 10 cm"),
        ("81D3", "Get weight", "tilt -45°"),
        ("1F0101F4", "Get clap status", "enabled, delay 500 ms"),
        ("8300FF000000", "Get chest LED", "rgb(0, 255, 0)"),
        ("8B00010203", "Get head LEDs", "off, on, blink slow, blink fast"),
    ],
)
def test_decode_reply(data, name, text):
    got_name, fields = p.decode_reply(bytes.fromhex(data))
    assert got_name == name
    assert fields["text"] == text


def test_decode_reply_exposes_structured_fields():
    _, fields = p.decode_reply(bytes.fromhex("796402"))
    assert fields["battery"] == 49 and fields["position"] == 2 and fields["battery_raw"] == 0x64
    _, fields = p.decode_reply(bytes.fromhex("85000000C8"))
    assert fields["odometer_cm"] == 200


@pytest.mark.parametrize("raw, pct", [(0x4D, 0), (0x65, 51), (0x7C, 100), (0x5F, 38), (0x60, 40)])
def test_battery_percent(raw, pct):
    assert p.battery_percent(raw) == pct
