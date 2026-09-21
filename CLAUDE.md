# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`wowpy` is a Python package for simple robot control over Bluetooth LE, starting with the WowWee MiP robot, with planned Blockly bindings. It is at a very early stage: the `wowpy` package is an empty skeleton and the only working code is a BLE prototype in `main.py`.

## Commands

Always work inside the project virtual environment (`.venv`); never install into the global Python.

```bash
# One-time setup
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .   # pulls in bleak, pytest, numpy from setup.py

# Run the BLE prototype (scans for the MiP, connects, sets the chest LED)
.venv\Scripts\python.exe main.py

# Run tests (none exist yet; tests belong under wowpy/test/)
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m pytest wowpy/test/test_foo.py::test_name   # single test
```

Running `main.py` requires a real MiP robot powered on and in range, plus a working BLE adapter. It is hardcoded to a specific device name (`Mip-52059`).

## Architecture notes

- **BLE layer:** all robot communication goes through `bleak` (`BleakScanner` to discover, `BleakClient` to connect/write). Everything is `asyncio`-based, so package code should expose `async` APIs and let callers drive the event loop.
- **MiP protocol:** commands are raw byte arrays written (write-without-response) to the send characteristic `0000ffe9-...` (service `ffe5`); notifications come back on `0000ffe4-...` (service `ffe0`). The first byte is the opcode (e.g. `0x84` = set chest LED, followed by R, G, B). `main.py` is the reference for scan → connect → write → disconnect; the real package code should be built by extracting this into `wowpy/`.
- **Gotchas learned on hardware:** do *not* call `client.pair()` — the MiP needs no pairing and pairing drops the connection. The default 5 s scan often misses the robot; use `find_device_by_name(..., timeout=15)` or similar.
- **Package layout:** `setup.py` declares `wowpy` and `wowpy.test` as packages. Put robot drivers and Blockly bindings under `wowpy/`, tests under `wowpy/test/`.
