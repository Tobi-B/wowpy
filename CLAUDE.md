# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`wowpy` is a Python package for simple robot control over Bluetooth LE, starting with the WowWee MiP robot, with planned Blockly bindings. `wowpy/mip.py` holds the `MiP` class (discovery, connection, LED/drive/sound commands, status query); `main.py` is a small usage example.

## Commands

Always work inside the project virtual environment (`.venv`); never install into the global Python.

```bash
# One-time setup
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .   # pulls in bleak, pytest, numpy from setup.py

# Run the BLE prototype (scans for the MiP, connects, sets the chest LED)
.venv\Scripts\python.exe main.py

# Run tests (hardware-free; they inject a fake BLE client via MiP(client=...))
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m pytest wowpy/test/test_mip.py::test_command_encoding   # single test
```

Running `main.py` requires a real MiP robot powered on and in range, plus a working BLE adapter. It is hardcoded to a specific device name (`Mip-52059`).

## Architecture notes

- **BLE layer:** all robot communication goes through `bleak` (`BleakScanner` to discover, `BleakClient` to connect/write). Everything is `asyncio`-based, so package code should expose `async` APIs and let callers drive the event loop.
- **MiP protocol (`wowpy/mip.py`):** commands are raw byte arrays written (write-without-response) to the send characteristic `0000ffe9-...`; replies come back on `0000ffe4-...` as an ASCII hex string that `MiP._on_notify` decodes into bytes. The first byte is the opcode (e.g. `0x84` = set chest LED, R, G, B). `MiP.send()` is fire-and-forget; `MiP.request()` sends and waits for the reply whose first byte echoes the opcode. New commands should be thin wrappers over these two, clamping parameters to the ranges the MiP accepts.
- **User stories:** `user_stories/US-NNN-*/` holds one story per folder (`story.md` + Gherkin `*.feature`). Read the relevant story before implementing a feature; scenarios tagged `@hardware` need the real robot, everything else should run against the mock.
- **Testing:** `MiP(device, client=...)` accepts any object with the `BleakClient` write/notify interface, so tests use a fake client and assert on the encoded bytes — no robot needed.
- **Gotchas learned on hardware:** do *not* call `client.pair()` — the MiP needs no pairing and pairing drops the connection. The default 5 s scan often misses the robot; use `find_device_by_name(..., timeout=15)` or similar.
- **Package layout:** `setup.py` declares `wowpy` and `wowpy.test` as packages. Put robot drivers and Blockly bindings under `wowpy/`, tests under `wowpy/test/`.
