# US-001 — MiP command dashboard

**As a** developer building complex control rules for the MiP,
**I want** a browser dashboard with a button for every command the MiP understands,
**so that** I can exercise and observe each function on the real robot without writing code first.

## Decisions (from refinement interview, 2026-09-21)

| Topic | Decision |
|---|---|
| UI | Web dashboard: small local Python server (e.g. FastAPI) serving one HTML/JS page. |
| Command scope | Complete documented MiP BLE protocol, grouped by family (see below), plus a raw-bytes field for undocumented opcodes. |
| Parameters | Each command has input fields with the min/max the protocol allows; out-of-range values are rejected client-side before anything is sent. |
| Return channel | Live log of every notification on `ffe4`, decoded to bytes, with timestamp and opcode name where known. |
| Connection | Dashboard scans, lists all `Mip-*` devices with RSSI, user picks one and connects. Connection state is always visible; command buttons are disabled while disconnected. |
| Continuous drive (0x78) | Hold-to-drive buttons ▲▼◀▶: while pressed the dashboard resends every ≤50 ms, release sends stop. |
| Mock robot | A "Mock MiP" entry in the device list that logs commands and answers queries with canned replies, so the dashboard is testable without hardware. |
| Language | Story and scenarios in English. |

## Command families to cover

Every opcode in the WowWee MiP BLE protocol reference, grouped as:

1. **LEDs** — chest LED set/flash/get, head LEDs set/get
2. **Driving** — continuous, forward/backward by time, turn left/right, drive by distance, stop
3. **Position & balance** — set position (on back / face down), get up, get status, get weight
4. **Sound** — play sound, set/get volume
5. **Game modes** — set/get game mode
6. **Sensing** — gesture/radar mode set/get and their events, MiP-detection mode, clap enable/delay/status and clap events, odometer get/reset
7. **IR** — send IR command, receive IR event
8. **System** — software/hardware version, user data get/set, sleep, disconnect
9. **Raw** — free hex byte string sent as-is

The exact opcode table lives in `wowpy/mip.py` once implemented; the feature file only samples one or two commands per family.

## Out of scope

- Status panel (battery, position, versions …) — see US-002.
- Blockly bindings (separate story).
- Multiple robots connected at once.
- Persisting command history across restarts.
- Authentication — the server binds to localhost only.
