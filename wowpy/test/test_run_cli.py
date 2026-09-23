"""The CLI runner lets a saved program run without a browser (US-003)."""

import subprocess
import sys

from wowpy.storage import Store


def _save(tmp_path, name, workspace):
    store = Store(tmp_path)
    store.save_program(name, workspace)
    return store.programs / f"{name.replace(' ', '-')}.py"


def _run(path, *args):
    return subprocess.run([sys.executable, "-m", "wowpy.run", str(path), "--mock", *args],
                          capture_output=True, text=True, timeout=60)


def ws(block):
    return {"blocks": {"languageVersion": 0, "blocks": [block]}}


def start(body):
    return {"type": "mip_on_start", "id": "s", "inputs": {"BODY": {"block": body}}}


def test_saved_program_runs_without_the_browser(tmp_path):
    path = _save(tmp_path, "red light", ws(start(
        {"type": "mip_chest_led", "id": "b", "fields": {"COLOUR": "#ff0000"}})))
    result = _run(path)
    assert result.returncode == 0, result.stderr
    assert "sent Set chest LED [84 FF 00 00]" in result.stdout
    assert "program finished" in result.stdout


def test_cli_reports_a_runtime_error(tmp_path):
    path = tmp_path / "bad.py"
    path.write_text("import asyncio\n\nasync def main(mip):\n    1 / 0\n", encoding="utf-8")
    result = _run(path)
    assert result.returncode == 1
    assert "division by zero" in (result.stdout + result.stderr)


def test_cli_rejects_a_program_without_main(tmp_path):
    path = tmp_path / "empty.py"
    path.write_text("x = 1\n", encoding="utf-8")
    result = _run(path)
    assert result.returncode == 1
    assert "program error" in result.stderr
