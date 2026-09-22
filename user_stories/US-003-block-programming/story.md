# US-003 — Block programming (Blockly)

**As a** developer writing complex control rules for the MiP,
**I want** to program the robot graphically with Blockly-style blocks — ready-made blocks that bundle several Bluetooth commands, plus the ability to compose my own blocks from the individual commands —
**so that** I can build and try out behaviours quickly without writing Python by hand, while still getting a readable wowpy script out of every program.

Builds on US-001/US-002: same server, same connection, same status panel and log.

## Decisions (from refinement interview, 2026-09-21)

| Topic | Decision |
|---|---|
| Editor | Google Blockly loaded from a CDN, on its own page `/blocks` of the dashboard server. No build pipeline. |
| Execution | Blockly's Python generator turns the workspace into a wowpy script (`async def main(mip): ...`). The server runs it as an asyncio task against the current connection (real MiP or Mock MiP). A "Python" tab shows the generated code live. |
| Control flow | Full language from the start: sequence, wait, repeat n / forever / while, if / else, comparisons, logic, math, variables, text — the standard Blockly blocks — plus **event hat blocks** ("when clapped", "when gesture …", "when radar …", "when position becomes …", "when program starts") and **sensor value blocks** (battery %, position, radar, odometer, last gesture, clap count). |
| Predefined composite blocks | Ship a starter set of blocks that bundle several commands (e.g. *Celebrate*: flash LED + sound + spin; *Patrol*: drive, turn, repeat; *Look around*: turn left/right with head LEDs; *Alarm*: red flash + loud sound; *Stand up and centre*: get up, wait, LED green). Each is itself defined as a stored custom block, so users can open and adapt it. |
| Custom blocks | A user selects a stack of blocks in the workspace and chooses "Make a block from selection", gives it a name, colour and optional parameters (inner numeric fields promoted to inputs). The block appears in a "My blocks" toolbox category and generates a Python function. Editing a custom block updates every use. |
| Storage | Files in the project: `programs/<name>.json` (Blockly workspace) + `programs/<name>.py` (generated), `blocks/<name>.json` (custom block definition + body). Saved through the server so they are versionable with Git and runnable without a browser (`python -m wowpy.run programs/<name>.py`). |
| Run controls | Run / Stop buttons. While running, the current block is highlighted and the log shows each command as in the dashboard. Stop cancels the task and sends `Stop` to the robot; a disconnect also stops the program. |
| Safety | Continuous drive (0x78) inside a program is a "drive for x seconds" block that resends every 40 ms and stops afterwards; a program cannot leave the robot rolling. Generated code runs in-process with the same rights as the server (localhost only; see US-001 out-of-scope). |

## Block catalogue (iteration 1)

| Category | Blocks |
|---|---|
| Robot: LEDs | chest LED colour (colour picker), flash chest LED, head LEDs (4 dropdowns) |
| Robot: Move | drive forward/backward for t ms at speed, turn left/right by degrees, drive distance cm, drive continuously for t s (speed, turn), stop |
| Robot: Sound | play sound #n, set volume |
| Robot: Body | get up, set position, set game mode, sleep |
| Robot: Sensing | enable clap, gesture/radar mode, reset odometer |
| Sensors (values) | battery %, position (dropdown compare), radar, odometer cm, last gesture, last clap count |
| Events (hats) | when program starts, when clapped (n times), when gesture …, when radar …, when position becomes …, every t seconds |
| Control | wait t s, repeat n, forever, while, if/else, break |
| Blockly standard | Logic, Math, Text, Variables, Functions |
| My blocks | user-defined and shipped composite blocks |

## Out of scope

- Multiple robots in one program.
- Collaborative editing, cloud storage.
- A Skulpt/BlockPy in-browser runtime — the program always runs on the server.
- Blockly's own "define function" being the *only* custom-block mechanism: it still works, but "Make a block from selection" is the supported way to create reusable, toolbox-visible blocks.
