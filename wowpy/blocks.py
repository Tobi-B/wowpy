"""Block catalogue for the Blockly editor (user story US-003).

Every block is described once here: its Blockly definition (fields, shape,
colour) and the Python it generates. The editor page fetches this as JSON and
registers the blocks; the server uses the same table to generate code for a
saved workspace, so both sides always agree.

A block's ``code`` is a template. ``{field}`` is replaced by a field value,
``{$input}`` by a generated value expression, ``{^body}`` by an indented
statement stack, and ``{id}`` by the block's id.
"""

from . import protocol as p

# Blockly colours per category
COLOURS = {
    "LEDs": 60, "Move": 200, "Sound": 20, "Body": 290, "Sensing": 150,
    "Sensors": 170, "Events": 40, "Control": 120, "My blocks": 330,
}


def _dropdown(mapping):
    return [[label, str(value)] for value, label in mapping.items()]


# Each entry: type, category, message, args, shape, code template.
# shape: "statement" (stackable), "value" (reporter), "hat" (event), "loop".
BLOCKS = [
    # -- LEDs ---------------------------------------------------------------
    {"type": "mip_chest_led", "category": "LEDs", "message": "chest LED %1",
     "args": [{"type": "field_colour", "name": "COLOUR", "colour": "#ff0000"}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.set_chest_led({COLOUR!rgb})"},
    {"type": "mip_flash_chest_led", "category": "LEDs", "message": "flash chest LED %1 on %2 ms off %3 ms",
     "args": [{"type": "field_colour", "name": "COLOUR", "colour": "#ff0000"},
              {"type": "field_number", "name": "ON", "value": 500, "min": 20, "max": 5100},
              {"type": "field_number", "name": "OFF", "value": 500, "min": 20, "max": 5100}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.flash_chest_led({COLOUR!rgb}, {ON}, {OFF})"},
    {"type": "mip_head_leds", "category": "LEDs", "message": "head LEDs %1 %2 %3 %4",
     "args": [{"type": "field_dropdown", "name": f"L{i}", "options": _dropdown(p.HEAD_LED_STATES)} for i in range(1, 5)],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.set_head_leds({L1}, {L2}, {L3}, {L4})"},

    # -- Move ---------------------------------------------------------------
    {"type": "mip_drive_time", "category": "Move", "message": "drive %1 at speed %2 for %3 ms",
     "args": [{"type": "field_dropdown", "name": "DIR", "options": [["forward", "forward"], ["backward", "backward"]]},
              {"type": "field_number", "name": "SPEED", "value": 20, "min": 0, "max": 30},
              {"type": "field_number", "name": "TIME", "value": 700, "min": 0, "max": 1785}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.drive_{DIR}({SPEED}, {TIME})"},
    {"type": "mip_turn", "category": "Move", "message": "turn %1 by %2 ° at speed %3",
     "args": [{"type": "field_dropdown", "name": "DIR", "options": [["left", "left"], ["right", "right"]]},
              {"type": "field_number", "name": "DEG", "value": 90, "min": 0, "max": 1275},
              {"type": "field_number", "name": "SPEED", "value": 12, "min": 0, "max": 24}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.turn_{DIR}({DEG}, {SPEED})"},
    {"type": "mip_drive_distance", "category": "Move", "message": "drive %1 cm then turn %2 °",
     "args": [{"type": "field_number", "name": "DIST", "value": 50, "min": -255, "max": 255},
              {"type": "field_number", "name": "TURN", "value": 0, "min": -360, "max": 360}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.drive_distance({DIST}, {TURN})"},
    {"type": "mip_drive_for", "category": "Move", "message": "drive continuously for %1 s speed %2 turn %3",
     "args": [{"type": "field_number", "name": "SECS", "value": 1, "min": 0, "max": 60, "precision": 0.1},
              {"type": "field_number", "name": "SPEED", "value": 20, "min": -32, "max": 32},
              {"type": "field_number", "name": "TURN", "value": 0, "min": -32, "max": 32}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.drive_for({SECS}, {SPEED}, {TURN})"},
    {"type": "mip_stop", "category": "Move", "message": "stop", "args": [], "shape": "statement",
     "code": "await _step({id})\nawait mip.stop()"},

    # -- Sound --------------------------------------------------------------
    {"type": "mip_play_sound", "category": "Sound", "message": "play sound %1",
     "args": [{"type": "field_number", "name": "INDEX", "value": 1, "min": 1, "max": 106}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.play_sound({INDEX})"},
    {"type": "mip_set_volume", "category": "Sound", "message": "set volume to %1",
     "args": [{"type": "field_number", "name": "LEVEL", "value": 4, "min": 0, "max": 7}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.set_volume({LEVEL})"},

    # -- Body ---------------------------------------------------------------
    {"type": "mip_get_up", "category": "Body", "message": "get up %1",
     "args": [{"type": "field_dropdown", "name": "DIR",
               "options": [["either way", "2"], ["from front", "0"], ["from back", "1"]]}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.execute('Get up', direction={DIR})"},
    {"type": "mip_set_position", "category": "Body", "message": "lie down %1",
     "args": [{"type": "field_dropdown", "name": "POS", "options": [["on back", "0"], ["face down", "1"]]}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.execute('Set position', position={POS})"},
    {"type": "mip_game_mode", "category": "Body", "message": "set game mode to %1",
     "args": [{"type": "field_dropdown", "name": "MODE", "options": _dropdown(p.GAME_MODES)}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.execute('Set game mode', mode={MODE})"},
    {"type": "mip_sleep", "category": "Body", "message": "send robot to sleep", "args": [], "shape": "statement",
     "code": "await _step({id})\nawait mip.execute('Sleep')"},

    # -- Sensing (configuration) -------------------------------------------
    {"type": "mip_enable_clap", "category": "Sensing", "message": "clap detection %1",
     "args": [{"type": "field_dropdown", "name": "ON", "options": [["on", "1"], ["off", "0"]]}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.execute('Enable clap', enabled={ON})"},
    {"type": "mip_clap_delay", "category": "Sensing", "message": "set clap delay to %1 ms",
     "args": [{"type": "field_number", "name": "MS", "value": 500, "min": 0, "max": 65535}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.execute('Set clap delay', delay_ms={MS})"},
    {"type": "mip_radar_mode", "category": "Sensing", "message": "gesture/radar mode %1",
     "args": [{"type": "field_dropdown", "name": "MODE", "options": _dropdown(p.GESTURE_RADAR_MODES)}],
     "shape": "statement",
     "code": "await _step({id})\nawait mip.execute('Set gesture/radar mode', mode={MODE})"},
    {"type": "mip_reset_odometer", "category": "Sensing", "message": "reset odometer", "args": [], "shape": "statement",
     "code": "await _step({id})\nawait mip.execute('Reset odometer')"},

    # -- Sensors (values) ---------------------------------------------------
    {"type": "mip_battery", "category": "Sensors", "message": "battery %", "args": [],
     "shape": "value", "output": "Number", "code": "await sensors.battery()"},
    {"type": "mip_position", "category": "Sensors", "message": "position", "args": [],
     "shape": "value", "output": "String", "code": "await sensors.position()"},
    {"type": "mip_odometer", "category": "Sensors", "message": "odometer cm", "args": [],
     "shape": "value", "output": "Number", "code": "await sensors.odometer()"},
    {"type": "mip_radar", "category": "Sensors", "message": "radar", "args": [],
     "shape": "value", "output": "String", "code": "await sensors.radar()"},
    {"type": "mip_last_gesture", "category": "Sensors", "message": "last gesture", "args": [],
     "shape": "value", "output": "String", "code": "await sensors.gesture()"},
    {"type": "mip_last_claps", "category": "Sensors", "message": "last clap count", "args": [],
     "shape": "value", "output": "Number", "code": "await sensors.claps()"},
    {"type": "mip_position_name", "category": "Sensors", "message": "%1",
     "args": [{"type": "field_dropdown", "name": "POS", "options": [[v, v] for v in p.POSITIONS.values()]}],
     "shape": "value", "output": "String", "code": "{POS!r}"},
    {"type": "mip_radar_name", "category": "Sensors", "message": "%1",
     "args": [{"type": "field_dropdown", "name": "R", "options": [[v, v] for v in p.RADAR.values()]}],
     "shape": "value", "output": "String", "code": "{R!r}"},
    {"type": "mip_gesture_name", "category": "Sensors", "message": "%1",
     "args": [{"type": "field_dropdown", "name": "G", "options": [[v, v] for v in p.GESTURES.values()]}],
     "shape": "value", "output": "String", "code": "{G!r}"},

    # -- Events (hats) ------------------------------------------------------
    {"type": "mip_on_start", "category": "Events", "message": "when program starts %1 %2",
     "args": [{"type": "input_dummy"}, {"type": "input_statement", "name": "BODY"}],
     "shape": "hat",
     "code": "async def main(mip):\n{^BODY}"},
    {"type": "mip_on_clap", "category": "Events", "message": "when clapped %1 times %2 %3",
     "args": [{"type": "field_number", "name": "N", "value": 2, "min": 1, "max": 10},
              {"type": "input_dummy"}, {"type": "input_statement", "name": "BODY"}],
     "shape": "hat",
     "code": "async def _on_clap_{id!name}(mip):\n{^BODY}\nprogram.on_clap(_on_clap_{id!name}, count={N})"},
    {"type": "mip_on_gesture", "category": "Events", "message": "when gesture %1 %2 %3",
     "args": [{"type": "field_dropdown", "name": "G", "options": [["any", ""]] + [[v, v] for v in p.GESTURES.values()]},
              {"type": "input_dummy"}, {"type": "input_statement", "name": "BODY"}],
     "shape": "hat",
     "code": "async def _on_gesture_{id!name}(mip):\n{^BODY}\nprogram.on_gesture(_on_gesture_{id!name}, gesture={G!r} or None)"},
    {"type": "mip_on_radar", "category": "Events", "message": "when radar %1 %2 %3",
     "args": [{"type": "field_dropdown", "name": "R", "options": [["any", ""]] + [[v, v] for v in p.RADAR.values()]},
              {"type": "input_dummy"}, {"type": "input_statement", "name": "BODY"}],
     "shape": "hat",
     "code": "async def _on_radar_{id!name}(mip):\n{^BODY}\nprogram.on_radar(_on_radar_{id!name}, radar={R!r} or None)"},
    {"type": "mip_on_position", "category": "Events", "message": "when position becomes %1 %2 %3",
     "args": [{"type": "field_dropdown", "name": "POS", "options": [["any", ""]] + [[v, v] for v in p.POSITIONS.values()]},
              {"type": "input_dummy"}, {"type": "input_statement", "name": "BODY"}],
     "shape": "hat",
     "code": "async def _on_position_{id!name}(mip):\n{^BODY}\nprogram.on_position(_on_position_{id!name}, position={POS!r} or None)"},
    {"type": "mip_every", "category": "Events", "message": "every %1 s %2 %3",
     "args": [{"type": "field_number", "name": "SECS", "value": 1, "min": 0.05, "max": 3600, "precision": 0.05},
              {"type": "input_dummy"}, {"type": "input_statement", "name": "BODY"}],
     "shape": "hat",
     "code": "async def _every_{id!name}(mip):\n{^BODY}\nprogram.every({SECS}, _every_{id!name})"},

    # -- Control ------------------------------------------------------------
    {"type": "mip_wait", "category": "Control", "message": "wait %1 s",
     "args": [{"type": "field_number", "name": "SECS", "value": 1, "min": 0, "max": 3600, "precision": 0.1}],
     "shape": "statement",
     "code": "await _step({id})\nawait asyncio.sleep({SECS})"},
    {"type": "mip_forever", "category": "Control", "message": "forever %1 %2",
     "args": [{"type": "input_dummy"}, {"type": "input_statement", "name": "BODY"}],
     "shape": "loop",
     "code": "while True:\n{^BODY}\n    await asyncio.sleep(0)"},
]

BLOCKS_BY_TYPE = {b["type"]: b for b in BLOCKS}

CATEGORIES = ["LEDs", "Move", "Sound", "Body", "Sensing", "Sensors", "Events", "Control"]

# Toolbox order shown in the editor; the standard Blockly categories and the
# dynamic "My blocks" category are inserted by the page.
TOOLBOX = [
    ("Robot: LEDs", "LEDs"), ("Robot: Move", "Move"), ("Robot: Sound", "Sound"),
    ("Robot: Body", "Body"), ("Robot: Sensing", "Sensing"), ("Sensors", "Sensors"),
    ("Events", "Events"), ("Control", "Control"),
]


def catalogue():
    """The block table as JSON-serialisable data for the editor page."""
    return {
        "blocks": [{**b, "colour": COLOURS[b["category"]]} for b in BLOCKS],
        "toolbox": [{"label": label, "category": cat} for label, cat in TOOLBOX],
        "colours": COLOURS,
    }
