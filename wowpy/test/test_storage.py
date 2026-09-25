import json

import pytest

from wowpy.storage import NAME_HINT, NameError_, Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def ws(block=None):
    return {"blocks": {"languageVersion": 0, "blocks": [block] if block else []}}


LED = {"type": "mip_chest_led", "id": "b", "fields": {"COLOUR": "#ff0000"}}
START = {"type": "mip_on_start", "id": "s", "inputs": {"BODY": {"block": LED}}}


def test_saving_writes_json_and_python(store):
    code = store.save_program("red light", ws(START))
    assert (store.programs / "red-light.json").exists()
    assert (store.programs / "red-light.py").exists()
    assert "await mip.set_chest_led(255, 0, 0)" in code
    assert "await mip.set_chest_led(255, 0, 0)" in (store.programs / "red-light.py").read_text(encoding="utf-8")


def test_saved_json_keeps_the_display_name(store):
    store.save_program("red light", ws(START))
    data = json.loads((store.programs / "red-light.json").read_text(encoding="utf-8"))
    assert data["name"] == "red light"
    assert data["workspace"]["blocks"]["blocks"][0]["type"] == "mip_on_start"


def test_load_round_trip(store):
    store.save_program("red light", ws(START))
    assert store.load_program("red light")["workspace"] == ws(START)
    assert store.list_programs() == ["red light"]


def test_loading_a_missing_program(store):
    with pytest.raises(FileNotFoundError):
        store.load_program("nope")


@pytest.mark.parametrize("name", ["../etc/passwd", "a/b", "", "   ", "x\\y", "a:b", "..", "a.py"])
def test_unsafe_names_are_rejected(store, name):
    with pytest.raises(NameError_, match=NAME_HINT):
        store.save_program(name, ws(START))
    assert not list(store.programs.glob("*")) if store.programs.exists() else True


def test_no_file_escapes_the_programs_folder(store, tmp_path):
    with pytest.raises(NameError_):
        store.save_program("../evil", ws(START))
    assert not (tmp_path / "evil.json").exists()


# -- custom blocks ---------------------------------------------------------

WARN = {"name": "Warn and turn", "colour": 20, "params": [{"name": "angle", "default": 90}],
        "workspace": ws(LED)}


def test_save_and_list_custom_blocks(store):
    store.save_block(WARN)
    assert (store.blocks / "warn-and-turn.json").exists()
    assert [b["name"] for b in store.list_blocks()] == ["Warn and turn"]
    assert store.load_block("Warn and turn")["params"] == [{"name": "angle", "default": 90}]


def test_custom_block_usage_counts_saved_programs(store):
    store.save_block(WARN)
    use = {"type": "Warn and turn", "id": "u"}
    store.save_program("uses it", ws({"type": "mip_on_start", "id": "s", "inputs": {"BODY": {"block": use}}}))
    assert store.block_usage("Warn and turn") == 1
    assert store.block_usage("Celebrate") == 0


def test_delete_custom_block(store):
    store.save_block(WARN)
    store.delete_block("Warn and turn")
    assert store.list_blocks() == []


def test_saving_a_program_uses_custom_blocks(store):
    store.save_block(WARN)
    use = {"type": "Warn and turn", "id": "u",
           "inputs": {"ANGLE": {"block": {"type": "math_number", "id": "n", "fields": {"NUM": 45}}}}}
    code = store.save_program("warner", ws({"type": "mip_on_start", "id": "s", "inputs": {"BODY": {"block": use}}}))
    assert "async def warn_and_turn(mip, angle):" in code
    assert "await warn_and_turn(mip, 45)" in code


def test_shipped_blocks_are_present_in_the_project():
    names = {b["name"] for b in Store().list_blocks()}
    assert names >= {"Celebrate", "Patrol", "Look around", "Alarm", "Stand up and centre"}


# -- Python blocks (US-005) ------------------------------------------------

PY = {"name": "Suchlauf", "colour": 200, "mode": "python",
      "params": [{"name": "sekunden", "default": 5}],
      "code": "await mip.drive(12, 8)\nawait mip.stop()"}


def test_save_python_block(store):
    data = store.save_block(PY)
    assert data["mode"] == "python"
    assert "workspace" not in data          # written from scratch
    assert store.load_block("Suchlauf")["code"] == PY["code"]


def test_python_block_code_is_validated_before_writing(store):
    from wowpy.blockcode import CodeError
    with pytest.raises(CodeError, match="kein await"):
        store.save_block({**PY, "code": "while True:\n    pass"})
    assert not (store.blocks / "suchlauf.json").exists()

    with pytest.raises(CodeError, match="Zeile 1"):
        store.save_block({**PY, "code": "await mip.stop("})
    assert not (store.blocks / "suchlauf.json").exists()


def test_converting_keeps_the_workspace_as_provenance(store):
    store.save_block(WARN)                                   # block mode
    store.save_block({**WARN, "mode": "python", "code": "await mip.stop()"})
    data = store.load_block("Warn and turn")
    assert data["mode"] == "python"
    assert data["workspace"] == WARN["workspace"]


def test_create_refuses_an_existing_name(store):
    from wowpy.storage import NameTaken
    store.save_block(PY)
    with pytest.raises(NameTaken):
        store.save_block({**PY, "code": "await mip.stop()"}, create=True)
    store.save_block({**PY, "code": "await mip.stop()"})      # editing is fine
    assert store.load_block("Suchlauf")["code"] == "await mip.stop()"


def test_unmanaged_fields_survive_a_round_trip(store):
    store.save_block({**WARN, "shipped": True})
    store.save_block({**store.load_block("Warn and turn"), "mode": "python", "code": "await mip.stop()"})
    back = store.load_block("Warn and turn")
    back.pop("mode"), back.pop("code")
    store.save_block(back)
    assert store.load_block("Warn and turn")["shipped"] is True


def test_block_body_seeds_a_conversion_without_step_calls(store):
    store.save_block(WARN)
    body = store.block_body("Warn and turn")
    assert "_step" not in body
    assert body == "await mip.set_chest_led(255, 0, 0)"


def test_block_body_of_a_python_block_is_its_code(store):
    store.save_block(PY)
    assert store.block_body("Suchlauf") == PY["code"]
