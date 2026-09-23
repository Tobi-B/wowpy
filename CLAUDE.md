# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`wowpy` is a Python package for simple robot control over Bluetooth LE, starting with the WowWee MiP robot. `wowpy/mip.py` holds the `MiP` class (discovery, connection, commands, status query), `wowpy/protocol.py` the full opcode table, `wowpy/dashboard/` a browser dashboard (command panels at `/`, Blockly editor at `/blocks`); `main.py` is a small usage example.

## Commands

Always work inside the project virtual environment (`.venv`); never install into the global Python.

```bash
# One-time setup
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"   # bleak, fastapi, uvicorn + pytest, httpx

# Run the BLE prototype (scans for the MiP, connects, sets the chest LED)
.venv\Scripts\python.exe main.py

# Run tests (hardware-free; they use the mock robot / a fake BLE client)
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m pytest wowpy/test/test_mip.py::test_command_encoding   # single test

# Run the dashboard (http://127.0.0.1:8000; pick "Mock MiP" to try it without hardware)
.venv\Scripts\python.exe -m wowpy.dashboard

# Run a saved block program without the browser
.venv\Scripts\python.exe -m wowpy.run programs/<name>.py --mock
```

The server does not hot-reload; restart it after editing `wowpy/dashboard/server.py`. `.claude/launch.json` has a `dashboard` entry for the in-app browser preview.

Running `main.py` requires a real MiP robot powered on and in range, plus a working BLE adapter. It is hardcoded to a specific device name (`Mip-52059`).

## Architecture notes

- **BLE layer:** all robot communication goes through `bleak` (`BleakScanner` to discover, `BleakClient` to connect/write). Everything is `asyncio`-based, so package code should expose `async` APIs and let callers drive the event loop.
- **MiP protocol (`wowpy/protocol.py`):** the single source of truth for opcodes. `COMMANDS` is a declarative table (name, opcode, family, `Param`s with min/max/choices, optional custom encoder); `Command.build(**params)` validates and returns the bytes. `REPLIES`/`decode_reply()` turn a notification into `(name, fields)` with a human-readable `text`. Add a new opcode there, not in `mip.py` or the dashboard — both render/encode from the table.
- **BLE transport (`wowpy/mip.py`):** commands are written (write-without-response) to `0000ffe9-...`; replies come back on `0000ffe4-...` as an ASCII hex string that `MiP._on_notify` decodes. `MiP.send()` is fire-and-forget; `MiP.request()` waits for the reply whose first byte echoes the opcode; `MiP.execute(name, **params)` runs a table command. `on_notification`/`on_disconnect` hooks feed the dashboard.
- **Mock robot (`wowpy/mock.py`):** `MockClient` implements the `BleakClient` subset `MiP` uses and answers every query with canned/stateful replies; `emit()`, `set_position()`, `overrides`, `silent` let tests inject events and failures.
- **Dashboard (`wowpy/dashboard/`):** FastAPI `server.py` owns one connection in `Hub` (REST for scan/connect/commands, WebSocket pushing `log`/`status`/`connection` messages and receiving the hold-to-drive stream; polls status every 5 s, paused while driving). `static/index.html` is one vanilla-JS page that builds the panels from `/api/commands`. `/api/mock/*` endpoints exist only to drive acceptance scenarios against the mock.
- **Block programming (`wowpy/blocks.py`, `codegen.py`, `program.py`, `storage.py`):** `blocks.py` describes every editor block once — its Blockly definition *and* the Python it generates (`{FIELD}`, `{FIELD!r}`, `{FIELD!rgb}`, `{$input}`, `{^body}`, `{id}`, `{id!name}`). `codegen.py` turns a saved workspace into a module with `async def main(mip)` plus event handlers; `program.py` executes it (event hats, `sensors`, block highlighting via `_step`, stop/cancel that always halts the robot); `storage.py` reads and writes `programs/*.json` + `.py` and `blocks/*.json`. Add a block in `blocks.py`, not in the page.
- **Blockly notes:** Blockly 11 removed the colour field from core (loaded as a plugin, registered via `registerFieldColour()`, with a dropdown fallback) and removed `setHighlighted` (the editor applies its own `.mip-running` class). `block.select()` does nothing when called programmatically — selection needs a real click.
- **User stories:** `user_stories/US-NNN-*/` holds one story per folder (`story.md` + Gherkin `*.feature`). Read the relevant story before implementing a feature; scenarios tagged `@hardware` need the real robot, everything else should run against the mock.
- **Testing:** `MiP(device, client=...)` accepts any object with the `BleakClient` write/notify interface, so tests use a fake client and assert on the encoded bytes — no robot needed.
- **Gotchas learned on hardware:** do *not* call `client.pair()` — the MiP needs no pairing and pairing drops the connection. The default 5 s scan often misses the robot; use `find_device_by_name(..., timeout=15)` or similar.
- **Package layout:** `setup.py` declares `wowpy`, `wowpy.dashboard` and `wowpy.test`; `static/*` ships via `package_data`. Put robot drivers and Blockly bindings under `wowpy/`, tests under `wowpy/test/`.
