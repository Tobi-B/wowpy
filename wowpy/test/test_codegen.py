import pytest

from wowpy import codegen
from wowpy.blocks import BLOCKS_BY_TYPE


def blk(type_, id_="b", fields=None, inputs=None, next_=None):
    b = {"type": type_, "id": id_}
    if fields:
        b["fields"] = fields
    if inputs:
        b["inputs"] = inputs
    if next_:
        b["next"] = {"block": next_}
    return b


def ws(*tops):
    return {"blocks": {"languageVersion": 0, "blocks": list(tops)}}


def start(body):
    return blk("mip_on_start", "start", inputs={"BODY": {"block": body}})


def body_of(code):
    """The lines of main() without the header."""
    lines = code.split("async def main(mip):\n", 1)[1].split("\n\n")[0]
    return [l[4:] for l in lines.rstrip().split("\n")]


def test_story_example():
    code = codegen.generate(ws(start(
        blk("mip_chest_led", "b", {"COLOUR": "#ff0000"},
            next_=blk("mip_wait", "c", {"SECS": 1},
                      next_=blk("mip_chest_led", "d", {"COLOUR": "#0000ff"}))))))
    assert body_of(code) == [
        "await _step('b')",
        "await mip.set_chest_led(255, 0, 0)",
        "await _step('c')",
        "await asyncio.sleep(1)",
        "await _step('d')",
        "await mip.set_chest_led(0, 0, 255)",
    ]


@pytest.mark.parametrize(
    "block, expected",
    [
        (blk("mip_drive_time", "x", {"DIR": "forward", "SPEED": 20, "TIME": 700}), "await mip.drive_forward(20, 700)"),
        (blk("mip_drive_time", "x", {"DIR": "backward", "SPEED": 10, "TIME": 100}), "await mip.drive_backward(10, 100)"),
        (blk("mip_turn", "x", {"DIR": "left", "DEG": 90, "SPEED": 12}), "await mip.turn_left(90, 12)"),
        (blk("mip_stop", "x"), "await mip.stop()"),
        (blk("mip_play_sound", "x", {"INDEX": 3}), "await mip.play_sound(3)"),
        (blk("mip_set_volume", "x", {"LEVEL": 7}), "await mip.set_volume(7)"),
        (blk("mip_head_leds", "x", {"L1": "0", "L2": "1", "L3": "2", "L4": "3"}), "await mip.set_head_leds(0, 1, 2, 3)"),
        (blk("mip_drive_for", "x", {"SECS": 0.5, "SPEED": 20, "TURN": 0}), "await mip.drive_for(0.5, 20, 0)"),
        (blk("mip_drive_distance", "x", {"DIST": 50, "TURN": 90}), "await mip.drive_distance(50, 90)"),
        (blk("mip_get_up", "x", {"DIR": "2"}), "await mip.execute('Get up', direction=2)"),
        (blk("mip_game_mode", "x", {"MODE": "1"}), "await mip.execute('Set game mode', mode=1)"),
        (blk("mip_reset_odometer", "x"), "await mip.execute('Reset odometer')"),
    ],
)
def test_statement_blocks(block, expected):
    assert body_of(codegen.generate(ws(start(block))))[-1] == expected


def test_wait_and_loops():
    inner = blk("mip_play_sound", "s", {"INDEX": 1})
    code = codegen.generate(ws(start(
        {"type": "controls_repeat_ext", "id": "r",
         "inputs": {"TIMES": {"block": blk("math_number", "n", {"NUM": 3})},
                    "DO": {"block": inner}}})))
    assert "for _ in range(int(3)):" in code
    assert "await mip.play_sound(1)" in code


def test_forever_yields_to_the_event_loop():
    code = codegen.generate(ws(start(
        blk("mip_forever", "f", inputs={"BODY": {"block": blk("mip_stop", "s")}}))))
    assert "while True:" in code
    assert code.rstrip().endswith("await asyncio.sleep(0)")


def test_if_else_with_sensor_condition():
    code = codegen.generate(ws(start(
        {"type": "controls_if", "id": "i",
         "inputs": {
             "IF0": {"block": {"type": "logic_compare", "id": "c", "fields": {"OP": "LT"},
                               "inputs": {"A": {"block": blk("mip_battery", "bat")},
                                          "B": {"block": blk("math_number", "n", {"NUM": 40})}}}},
             "DO0": {"block": blk("mip_chest_led", "r", {"COLOUR": "#ff0000"})},
             "ELSE": {"block": blk("mip_chest_led", "g", {"COLOUR": "#00ff00"})}}})))
    assert "if (await sensors.battery() < 40):" in code
    assert "await mip.set_chest_led(255, 0, 0)" in code
    assert "else:" in code
    assert "await mip.set_chest_led(0, 255, 0)" in code


def test_variables():
    code = codegen.generate(ws(start(
        {"type": "variables_set", "id": "v", "fields": {"VAR": {"name": "b"}},
         "inputs": {"VALUE": {"block": blk("mip_battery", "bat")}}})))
    assert "b = await sensors.battery()" in code


@pytest.mark.parametrize(
    "hat, fields, expected",
    [
        ("mip_on_clap", {"N": 2}, "program.on_clap(_on_clap_h, count=2)"),
        ("mip_on_gesture", {"G": "forward"}, "program.on_gesture(_on_gesture_h, gesture='forward' or None)"),
        ("mip_on_radar", {"R": "object < 10 cm"}, "program.on_radar(_on_radar_h, radar='object < 10 cm' or None)"),
        ("mip_on_position", {"POS": "face down"}, "program.on_position(_on_position_h, position='face down' or None)"),
        ("mip_every", {"SECS": 0.2}, "program.every(0.2, _every_h)"),
    ],
)
def test_event_hats(hat, fields, expected):
    code = codegen.generate(ws(
        {**blk(hat, "h", fields), "inputs": {"BODY": {"block": blk("mip_play_sound", "s", {"INDEX": 1})}}}))
    assert expected in code
    assert "await mip.play_sound(1)" in code


def test_empty_workspace_still_generates_a_module():
    code = codegen.generate(ws())
    assert "async def main(mip):" in code
    compile(code, "<test>", "exec")


def test_generated_code_always_compiles():
    """Every statement block on its own must produce valid Python."""
    for spec in BLOCKS_BY_TYPE.values():
        if spec["shape"] not in ("statement", "loop"):
            continue
        fields = {}
        for arg in spec["args"]:
            if arg["type"] == "field_number":
                fields[arg["name"]] = arg.get("value", 0)
            elif arg["type"] == "field_dropdown":
                fields[arg["name"]] = arg["options"][0][1]
            elif arg["type"] == "field_colour":
                fields[arg["name"]] = arg.get("colour", "#000000")
        code = codegen.generate(ws(start(blk(spec["type"], "t", fields))))
        compile(code, f"<{spec['type']}>", "exec")


# -- custom blocks ---------------------------------------------------------

WARN = {
    "name": "Warn and turn",
    "colour": 20,
    "params": [{"name": "angle", "default": 90}],
    "workspace": {"blocks": {"blocks": [
        blk("mip_chest_led", "w1", {"COLOUR": "#ff0000"},
            next_=blk("mip_play_sound", "w2", {"INDEX": 3},
                      next_={"type": "mip_turn", "id": "w3", "fields": {"DIR": "left", "SPEED": 12},
                             "inputs": {"DEG": {"block": {"type": "custom_param", "id": "p", "fields": {"NAME": "angle"}}}}}))]}},
}


def test_custom_block_generates_a_function():
    code = codegen.generate(
        ws(start({"type": "Warn and turn", "id": "u",
                  "inputs": {"ANGLE": {"block": blk("math_number", "n", {"NUM": 90})}}})),
        [WARN])
    assert "async def warn_and_turn(mip, angle):" in code
    assert "await mip.set_chest_led(255, 0, 0)" in code
    assert "await mip.play_sound(3)" in code
    assert "await mip.turn_left(angle, 12)" in code
    assert "await warn_and_turn(mip, 90)" in code
    compile(code, "<custom>", "exec")


def test_custom_block_used_twice_emits_one_function():
    inner = {"type": "Warn and turn", "id": "u2",
             "inputs": {"ANGLE": {"block": blk("math_number", "n2", {"NUM": 180})}}}
    first = {"type": "Warn and turn", "id": "u1",
             "inputs": {"ANGLE": {"block": blk("math_number", "n1", {"NUM": 45})}},
             "next": {"block": inner}}
    code = codegen.generate(ws(start(first)), [WARN])
    assert code.count("async def warn_and_turn(") == 1
    assert "await warn_and_turn(mip, 45)" in code
    assert "await warn_and_turn(mip, 180)" in code


def test_nested_custom_blocks():
    double = {
        "name": "Double warn", "colour": 330, "params": [],
        "workspace": {"blocks": {"blocks": [
            {"type": "Warn and turn", "id": "d1",
             "inputs": {"ANGLE": {"block": blk("math_number", "dn1", {"NUM": 90})}},
             "next": {"block": {"type": "Warn and turn", "id": "d2",
                                "inputs": {"ANGLE": {"block": blk("math_number", "dn2", {"NUM": 90})}}}}}]}},
    }
    code = codegen.generate(ws(start(blk("Double warn", "u"))), [WARN, double])
    assert "async def double_warn(mip):" in code
    assert code.count("await warn_and_turn(mip, 90)") == 2
    compile(code, "<nested>", "exec")


def test_shipped_blocks_generate_valid_python():
    from wowpy.storage import Store
    shipped = Store().list_blocks()
    assert {b["name"] for b in shipped} >= {"Celebrate", "Patrol", "Look around", "Alarm", "Stand up and centre"}
    for definition in shipped:
        params = {p["name"].upper(): {"block": blk("math_number", "n", {"NUM": p.get("default", 1)})}
                  for p in definition.get("params", [])}
        code = codegen.generate(ws(start({"type": definition["name"], "id": "u", "inputs": params})), shipped)
        compile(code, f"<{definition['name']}>", "exec")


@pytest.mark.parametrize("name, expected", [
    ("red light", "red-light"), ("Warn and turn", "warn-and-turn"),
    ("../etc/passwd", "etc-passwd"), ("a  b", "a-b"),
])
def test_slug(name, expected):
    assert codegen.slug(name) == expected


def test_hat_ids_that_differ_only_in_punctuation_get_distinct_functions():
    """Blockly ids contain punctuation; stripping it must not merge two hats."""
    code = codegen.generate(ws(
        {**blk("mip_on_clap", "a!b", {"N": 1}),
         "inputs": {"BODY": {"block": blk("mip_play_sound", "s1", {"INDEX": 1})}}},
        {**blk("mip_on_clap", "a?b", {"N": 2}),
         "inputs": {"BODY": {"block": blk("mip_play_sound", "s2", {"INDEX": 2})}}}))
    assert code.count("async def _on_clap_a_b(") == 1
    assert code.count("async def _on_clap_a_b_2(") == 1
    assert "program.on_clap(_on_clap_a_b, count=1)" in code
    assert "program.on_clap(_on_clap_a_b_2, count=2)" in code
    compile(code, "<ids>", "exec")


def test_punctuated_block_ids_are_safe_in_step_calls():
    code = codegen.generate(ws(start(blk("mip_stop", "|![gg4[t@/O@.K)oz??R"))))
    compile(code, "<step>", "exec")
