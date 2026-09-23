"""Declarative description of the WowWee MiP BLE protocol.

``COMMANDS`` lists every documented opcode with its parameters and encoder;
``decode_reply`` turns a notification into a name and human-readable text.
Both the :class:`~wowpy.mip.MiP` methods and the dashboard build on this so
the byte layout lives in exactly one place.
"""

from dataclasses import dataclass, field

# --------------------------------------------------------------------- opcodes

CMD_MIP_DETECTED = 0x04           # event
CMD_PLAY_SOUND = 0x06
CMD_SET_POSITION = 0x08
CMD_GESTURE_DETECTED = 0x0A       # event
CMD_SET_GESTURE_RADAR_MODE = 0x0C
CMD_RADAR_RESPONSE = 0x0C         # event (same opcode as the set command)
CMD_GET_GESTURE_RADAR_MODE = 0x0D
CMD_SET_MIP_DETECTION = 0x0E
CMD_GET_MIP_DETECTION = 0x0F
CMD_IR_RECEIVED = 0x11            # event
CMD_SET_USER_DATA = 0x12
CMD_GET_USER_DATA = 0x13
CMD_GET_SOFTWARE_VERSION = 0x14
CMD_SET_VOLUME = 0x15
CMD_GET_VOLUME = 0x16
CMD_GET_HARDWARE_VERSION = 0x19
CMD_CLAP_DETECTED = 0x1D          # event
CMD_ENABLE_CLAP = 0x1E
CMD_GET_CLAP_STATUS = 0x1F
CMD_SET_CLAP_DELAY = 0x20
CMD_GET_UP = 0x23
CMD_DRIVE_DISTANCE = 0x70
CMD_DRIVE_FORWARD_TIME = 0x71
CMD_DRIVE_BACKWARD_TIME = 0x72
CMD_TURN_LEFT = 0x73
CMD_TURN_RIGHT = 0x74
CMD_SET_GAME_MODE = 0x76
CMD_STOP = 0x77
CMD_DRIVE_CONTINUOUS = 0x78
CMD_GET_STATUS = 0x79
CMD_GET_WEIGHT = 0x81
CMD_GET_GAME_MODE = 0x82
CMD_GET_CHEST_LED = 0x83
CMD_SET_CHEST_LED = 0x84
CMD_GET_ODOMETER = 0x85
CMD_RESET_ODOMETER = 0x86
CMD_FLASH_CHEST_LED = 0x89
CMD_SET_HEAD_LEDS = 0x8A
CMD_GET_HEAD_LEDS = 0x8B
CMD_SEND_IR = 0x8C
CMD_SLEEP = 0xFA
CMD_DISCONNECT_APP = 0xFE

# ------------------------------------------------------------------- lookups

POSITIONS = {
    0: "on back",
    1: "face down",
    2: "upright",
    3: "picked up",
    4: "hand stand",
    5: "face down on tray",
    6: "on back with kickstand",
}

GAME_MODES = {
    1: "app",
    2: "cage",
    3: "tracking",
    4: "dance",
    5: "default",
    6: "stack",
    7: "trick",
    8: "roam",
}

GESTURE_RADAR_MODES = {0: "off", 2: "gesture", 4: "radar"}

GESTURES = {
    0x0A: "left",
    0x0B: "right",
    0x0C: "center sweep left",
    0x0D: "center sweep right",
    0x0E: "center hold",
    0x0F: "forward",
    0x10: "backward",
}

RADAR = {1: "no object", 2: "object 10–30 cm", 3: "object < 10 cm"}

HEAD_LED_STATES = {0: "off", 1: "on", 2: "blink slow", 3: "blink fast"}

BATTERY_EMPTY = 0x4D
BATTERY_FULL = 0x7C


def battery_percent(raw):
    pct = round((raw - BATTERY_EMPTY) * 100 / (BATTERY_FULL - BATTERY_EMPTY))
    return max(0, min(100, pct))


def clamp(value, lo, hi):
    return max(lo, min(hi, int(value)))


# ------------------------------------------------------------------ commands

@dataclass(frozen=True)
class Param:
    """One user-facing parameter of a command.

    ``choices`` (value → label) makes it an enum; otherwise ``min``/``max``
    bound an integer. ``unit`` is shown next to the field.
    """
    name: str
    min: int = 0
    max: int = 255
    default: int = 0
    unit: str = ""
    choices: dict = field(default_factory=dict)

    def validate(self, value):
        value = int(value)
        if self.choices:
            if value not in self.choices:
                raise ValueError(f"{self.name}: must be one of {sorted(self.choices)}")
        elif not self.min <= value <= self.max:
            raise ValueError(f"{self.name}: {self.min}–{self.max}")
        return value


@dataclass(frozen=True)
class Command:
    name: str
    opcode: int
    family: str
    params: tuple = ()
    query: bool = False   # True if the MiP answers with a reply echoing the opcode
    encode: object = None  # optional custom encoder (validated params dict) -> tuple of bytes

    def build(self, **kwargs):
        """Validate ``kwargs`` against ``params`` and return the full byte string."""
        values = {}
        for p in self.params:
            values[p.name] = p.validate(kwargs.get(p.name, p.default))
        unknown = set(kwargs) - set(values)
        if unknown:
            raise ValueError(f"unknown parameter(s) {sorted(unknown)} for {self.name}")
        body = self.encode(values) if self.encode else tuple(values[p.name] for p in self.params)
        return bytes([self.opcode, *body])


_RGB = (Param("r", 0, 255, 255), Param("g", 0, 255, 0), Param("b", 0, 255, 0))


def _enc_flash(v):
    return (v["r"], v["g"], v["b"], clamp(v["on_ms"] // 20, 1, 255), clamp(v["off_ms"] // 20, 1, 255))


def _enc_time_drive(v):
    return (v["speed"], clamp(v["time_ms"] // 7, 0, 255))


def _enc_turn(v):
    return (clamp(v["degrees"] // 5, 0, 255), v["speed"])


def _enc_distance(v):
    angle = abs(v["turn_degrees"])
    return (
        0x00 if v["distance_cm"] >= 0 else 0x01, abs(v["distance_cm"]),
        0x00 if v["turn_degrees"] >= 0 else 0x01, angle >> 8, angle & 0xFF,
    )


def encode_continuous_drive(speed, turn):
    """Map signed speed/turn (-32..32) onto the MiP's 0x01–0x80 ranges."""
    speed = clamp(speed, -32, 32)
    turn = clamp(turn, -32, 32)
    speed_byte = 0x00 if speed == 0 else (speed if speed > 0 else 0x20 - speed)
    turn_byte = 0x00 if turn == 0 else (0x40 + turn if turn > 0 else 0x60 - turn)
    return (speed_byte, turn_byte)


def _enc_continuous(v):
    return encode_continuous_drive(v["speed"], v["turn"])


def _enc_clap_delay(v):
    return (v["delay_ms"] >> 8, v["delay_ms"] & 0xFF)


def _enc_ir(v):
    return (v["byte1"], v["byte2"], v["byte3"], v["byte4"], v["power"])


COMMANDS = (
    # LEDs
    Command("Set chest LED", CMD_SET_CHEST_LED, "LEDs", _RGB),
    Command("Flash chest LED", CMD_FLASH_CHEST_LED, "LEDs",
            (*_RGB, Param("on_ms", 20, 5100, 500, "ms"), Param("off_ms", 20, 5100, 500, "ms")), encode=_enc_flash),
    Command("Get chest LED", CMD_GET_CHEST_LED, "LEDs", query=True),
    Command("Set head LEDs", CMD_SET_HEAD_LEDS, "LEDs",
            tuple(Param(f"led{i}", 0, 3, 1, choices=HEAD_LED_STATES) for i in range(1, 5))),
    Command("Get head LEDs", CMD_GET_HEAD_LEDS, "LEDs", query=True),
    # Driving
    Command("Drive", CMD_DRIVE_CONTINUOUS, "Driving",
            (Param("speed", -32, 32, 20), Param("turn", -32, 32, 0)), encode=_enc_continuous),
    Command("Drive forward", CMD_DRIVE_FORWARD_TIME, "Driving",
            (Param("speed", 0, 30, 20), Param("time_ms", 0, 1785, 700, "ms")), encode=_enc_time_drive),
    Command("Drive backward", CMD_DRIVE_BACKWARD_TIME, "Driving",
            (Param("speed", 0, 30, 20), Param("time_ms", 0, 1785, 700, "ms")), encode=_enc_time_drive),
    Command("Turn left", CMD_TURN_LEFT, "Driving",
            (Param("degrees", 0, 1275, 90, "°"), Param("speed", 0, 24, 12)), encode=_enc_turn),
    Command("Turn right", CMD_TURN_RIGHT, "Driving",
            (Param("degrees", 0, 1275, 90, "°"), Param("speed", 0, 24, 12)), encode=_enc_turn),
    Command("Drive distance", CMD_DRIVE_DISTANCE, "Driving",
            (Param("distance_cm", -255, 255, 50, "cm"), Param("turn_degrees", -360, 360, 0, "°")), encode=_enc_distance),
    Command("Stop", CMD_STOP, "Driving"),
    # Position & balance
    Command("Get status", CMD_GET_STATUS, "Position & balance", query=True),
    Command("Get up", CMD_GET_UP, "Position & balance",
            (Param("direction", 0, 2, 2, choices={0: "from front", 1: "from back", 2: "either"}),)),
    Command("Set position", CMD_SET_POSITION, "Position & balance",
            (Param("position", 0, 1, 0, choices={0: "on back", 1: "face down"}),)),
    Command("Get weight", CMD_GET_WEIGHT, "Position & balance", query=True),
    # Sound
    Command("Play sound", CMD_PLAY_SOUND, "Sound", (Param("index", 1, 106, 1),)),
    Command("Set volume", CMD_SET_VOLUME, "Sound", (Param("level", 0, 7, 4),)),
    Command("Get volume", CMD_GET_VOLUME, "Sound", query=True),
    # Game modes
    Command("Set game mode", CMD_SET_GAME_MODE, "Game modes", (Param("mode", 1, 8, 1, choices=GAME_MODES),)),
    Command("Get game mode", CMD_GET_GAME_MODE, "Game modes", query=True),
    # Sensing
    Command("Set gesture/radar mode", CMD_SET_GESTURE_RADAR_MODE, "Sensing",
            (Param("mode", 0, 4, 0, choices=GESTURE_RADAR_MODES),)),
    Command("Get gesture/radar mode", CMD_GET_GESTURE_RADAR_MODE, "Sensing", query=True),
    Command("Set MiP detection", CMD_SET_MIP_DETECTION, "Sensing",
            (Param("id", 0, 255, 0), Param("power", 0, 120, 60))),
    Command("Get MiP detection", CMD_GET_MIP_DETECTION, "Sensing", query=True),
    Command("Enable clap", CMD_ENABLE_CLAP, "Sensing", (Param("enabled", 0, 1, 1, choices={0: "off", 1: "on"}),)),
    Command("Get clap status", CMD_GET_CLAP_STATUS, "Sensing", query=True),
    Command("Set clap delay", CMD_SET_CLAP_DELAY, "Sensing", (Param("delay_ms", 0, 65535, 500, "ms"),), encode=_enc_clap_delay),
    Command("Get odometer", CMD_GET_ODOMETER, "Sensing", query=True),
    Command("Reset odometer", CMD_RESET_ODOMETER, "Sensing"),
    # IR
    Command("Send IR", CMD_SEND_IR, "IR",
            (Param("byte1"), Param("byte2"), Param("byte3"), Param("byte4"), Param("power", 0, 120, 60)), encode=_enc_ir),
    # System
    Command("Get software version", CMD_GET_SOFTWARE_VERSION, "System", query=True),
    Command("Get hardware version", CMD_GET_HARDWARE_VERSION, "System", query=True),
    Command("Set user data", CMD_SET_USER_DATA, "System", (Param("address", 0, 255, 0), Param("value", 0, 255, 0))),
    Command("Get user data", CMD_GET_USER_DATA, "System", (Param("address", 0, 255, 0),), query=True),
    Command("Sleep", CMD_SLEEP, "System"),
    Command("Disconnect app", CMD_DISCONNECT_APP, "System"),
)

FAMILIES = ("LEDs", "Driving", "Position & balance", "Sound", "Game modes", "Sensing", "IR", "System", "Raw")

COMMANDS_BY_NAME = {c.name: c for c in COMMANDS}
NAMES_BY_OPCODE = {c.opcode: c.name for c in COMMANDS}


def parse_raw(text):
    """Turn "84 FF 00 00" (spaces optional) into bytes; raises ValueError on bad input."""
    cleaned = "".join(text.split())
    if not cleaned or len(cleaned) % 2:
        raise ValueError("hex bytes only, e.g. 84 FF 00 00")
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        raise ValueError("hex bytes only, e.g. 84 FF 00 00") from None


# ------------------------------------------------------------------- replies

def _dec_status(b):
    return {"battery_raw": b[0], "battery": battery_percent(b[0]), "position": b[1],
            "text": f"battery {battery_percent(b[0])}%, {POSITIONS.get(b[1], f'position {b[1]}')}"}


def _dec_version(b):
    text = f"20{b[0]:02d}-{b[1]:02d}-{b[2]:02d}" + (f" rev {b[3]}" if len(b) > 3 else "")
    return {"software_version": text, "text": text}


def _dec_hw(b):
    text = f"{b[0]} (voice chip {b[1]})" if len(b) > 1 else str(b[0])
    return {"hardware_version": text, "text": text}


def _dec_odometer(b):
    cm = int.from_bytes(b[:4], "big")
    return {"odometer_cm": cm, "text": f"{cm} cm"}


def _dec_chest(b):
    return {"chest_led": (b[0], b[1], b[2]), "text": f"rgb({b[0]}, {b[1]}, {b[2]})"
            + (f", on {b[3] * 20} ms / off {b[4] * 20} ms" if len(b) > 4 and (b[3] or b[4]) else "")}


def _dec_head(b):
    states = tuple(b[:4])
    return {"head_leds": states, "text": ", ".join(HEAD_LED_STATES.get(s, str(s)) for s in states)}


def _dec_weight(b):
    angle = b[0] - 256 if b[0] > 127 else b[0]
    return {"weight_angle": angle, "text": f"tilt {angle}°"}


def _dec_enum(key, table, label=None):
    def dec(b):
        return {key: b[0], "text": f"{label + ' ' if label else ''}{table.get(b[0], str(b[0]))}"}
    return dec


def _dec_clap_status(b):
    delay = int.from_bytes(b[1:3], "big") if len(b) >= 3 else None
    text = "enabled" if b[0] else "disabled"
    if delay is not None:
        text += f", delay {delay} ms"
    return {"clap_enabled": bool(b[0]), "clap_delay_ms": delay, "text": text}


def _dec_claps(b):
    return {"claps": b[0], "text": f"{b[0]} claps" if b[0] != 1 else "1 clap"}


def _dec_detection(b):
    return {"detection_id": b[0], "detection_power": b[1] if len(b) > 1 else None,
            "text": f"id {b[0]}" + (f", power {b[1]}" if len(b) > 1 else "")}


def _dec_user_data(b):
    return {"user_data": (b[0], b[1]), "text": f"address {b[0]} = {b[1]}"}


def _dec_hex(label):
    return lambda b: {"text": f"{label} {b.hex(' ').upper()}"}


REPLIES = {
    CMD_GET_STATUS: ("Get status", _dec_status),
    CMD_GET_SOFTWARE_VERSION: ("Get software version", _dec_version),
    CMD_GET_HARDWARE_VERSION: ("Get hardware version", _dec_hw),
    CMD_GET_VOLUME: ("Get volume", _dec_enum("volume", {i: str(i) for i in range(8)}, "volume")),
    CMD_GET_GAME_MODE: ("Get game mode", _dec_enum("game_mode", GAME_MODES)),
    CMD_GET_ODOMETER: ("Get odometer", _dec_odometer),
    CMD_GET_CHEST_LED: ("Get chest LED", _dec_chest),
    CMD_GET_HEAD_LEDS: ("Get head LEDs", _dec_head),
    CMD_GET_WEIGHT: ("Get weight", _dec_weight),
    CMD_GET_GESTURE_RADAR_MODE: ("Get gesture/radar mode", _dec_enum("gesture_radar_mode", GESTURE_RADAR_MODES)),
    CMD_GET_MIP_DETECTION: ("Get MiP detection", _dec_detection),
    CMD_GET_CLAP_STATUS: ("Get clap status", _dec_clap_status),
    CMD_GET_USER_DATA: ("Get user data", _dec_user_data),
    CMD_CLAP_DETECTED: ("Clap detected", _dec_claps),
    CMD_GESTURE_DETECTED: ("Gesture detected", _dec_enum("gesture", GESTURES)),
    CMD_RADAR_RESPONSE: ("Radar", _dec_enum("radar", RADAR)),
    CMD_MIP_DETECTED: ("MiP detected", _dec_detection),
    CMD_IR_RECEIVED: ("IR received", _dec_hex("data")),
}


def decode_reply(data):
    """Return ``(name, fields)`` for a notification; ``fields`` always has ``text``."""
    if not data:
        return "empty", {"text": ""}
    opcode = data[0]
    entry = REPLIES.get(opcode)
    if entry is None:
        return f"unknown (0x{opcode:02X})", {"text": data[1:].hex(" ").upper()}
    name, decoder = entry
    try:
        return name, decoder(data[1:])
    except (IndexError, ValueError):
        return name, {"text": data[1:].hex(" ").upper()}
