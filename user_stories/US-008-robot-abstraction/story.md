# US-008 — One robot interface, the MiP as one driver among several

**As a** developer who wants to keep this system when the robot changes,
**I want** programs, blocks and the dashboard to talk to *a robot* rather than
to the MiP,
**so that** an Arduino, a Raspberry Pi, a make:bot or a simulated robot can take
its place without rewriting the editor, the generator or the saved programs.

The trigger: the real MiP is probably faulty (see the diagnosis notes below) and
the whole system currently stops when it does.

## Decisions (from refinement interview, 2026-11-27)

| Topic | Decision |
|---|---|
| Depth | **Capability model.** A robot declares what it can do (drive, LEDs, distance, tilt, …); blocks and dashboard build themselves from the capabilities, not from opcodes. The MiP becomes one driver. |
| First second target | **None — the simulator** (US-009). The abstraction proves itself against MiP + virtual world, so no hardware purchase and no dependency on the broken robot. |
| Repository | The abstraction **stays in `wowpy`** — it touches nearly every module here. Only the virtual world leaves scope (US-009). |
| Scope of this story | The interface, the MiP driver behind it, and everything that has to follow (blocks, codegen, dashboard). No new hardware driver. |

## Why this is not a new repository

Everything the abstraction touches already lives here:

| Module | Lines | What couples it to the MiP |
|---|---|---|
| `protocol.py` | 427 | the opcode table itself — device-specific by nature |
| `mip.py` | 256 | BLE transport *and* MiP semantics in one class |
| `blocks.py` | 199 | 59 mentions; every block template emits `mip.<method>(…)` |
| `codegen.py` | 363 | emits `async def main(mip)` |
| `program.py` | 241 | holds a `MiP`, passes it to the program |
| `dashboard/server.py` | 711 | `Hub` owns a `MiP`, panels come from the MiP table |
| `mock.py` | 150 | mocks the **BLE client**, not the robot |
| `storage.py` | 176 | already device-independent |

Moving this to a new repository would mean forking all of it, tests included.
The driver interface is the seam; the simulator sits on the far side of it.

## The shape

```
wowpy/robot.py        Robot  — the interface every driver implements
                      Capability descriptors (what this robot can do)
wowpy/drivers/mip/    MiPDriver — bleak transport + the opcode table
wowpy/drivers/sim/    SimDriver — US-009, talks to the virtual world
```

A driver answers two different questions, and keeping them apart is the point:

1. **What can you do?** — the portable capability set. Blocks and programs use
   only this, so a program written for one robot runs on another.
2. **What else can you do?** — the device's own full command table. The MiP has
   around sixty opcodes (play sound 1–106, game modes, clap detection) that no
   other robot will have. The command dashboard from US-001 must keep all of
   them.

So the capability layer is *not* a lowest common denominator that throws the
MiP's richness away. It is a portable subset **next to** the device table, and
`/api/commands` keeps serving whatever the connected driver declares.

## The thing to get right — `mip` is baked into code the user wrote

`codegen` emits `async def main(mip)` and every block template calls
`mip.something(…)`. Generated code can be regenerated, so that part is free.
**Hand-written code cannot.**

A `mode: python` block (US-005) stores a body the user typed, and
`blockcode.validate()` compiles it as the body of `async def <block>(mip, …)`.
`blocks/blinkfolge.json` is exactly such a block. Renaming the parameter to
`robot` would:

- break every hand-written block body that calls `mip.…` — a `NameError` at run
  time, not at save time, because validation only checks that it *compiles*;
- break any body a user has in a browser tab but has not saved yet.

Three ways out:

1. **Keep `mip` as the parameter name.** Zero migration, but the name is a lie
   on an Arduino and the abstraction never looks finished. Rejected.
2. **Rename to `robot` and pass `mip` as an alias** to the same object, for as
   long as any `mode: python` block still mentions it. Old bodies keep working,
   new ones are written with `robot`. A warning on save when `mip` is used.
   **Recommended** — nothing breaks silently, and the alias can be dropped once
   no block uses it.
3. Rename and rewrite every stored body with a regex. Edits files the user
   wrote, and `mip` can legitimately appear inside a string or a comment.

The scenarios below assume option 2.

## The second thing — capabilities must be checkable before a program runs

If a program drives but the connected robot has no drive capability, the failure
should be visible **before** anything moves, not as an `AttributeError` halfway
through. A program carries the capabilities it uses; `program.py` checks them
against the connected driver and refuses with a readable message naming the
missing capability and the robot.

This also gives the editor something useful: a block whose capability the
connected robot lacks can be greyed out rather than silently failing.

## Capabilities to start with

Derived from what the MiP actually offers and what a simulated robot can
honestly provide:

| Capability | Methods | MiP | Sim (US-009) |
|---|---|---|---|
| `drive` | `drive(speed, turn)`, `drive_for(…)`, `stop()` | yes | yes |
| `turn` | `turn(degrees, speed)` | yes | yes |
| `chest_led` | `set_chest_led(r, g, b)` | yes | yes |
| `head_leds` | `set_head_leds(…)` | yes | optional |
| `sound` | `play_sound(index)` | yes (106 sounds) | no |
| `distance` | reading: free / near / very near | radar, 3 classes | ray cast, same 3 classes |
| `orientation` | reading: upright, on back, face down, … | yes | yes |
| `odometer` | reading: cm | yes | yes |
| `battery` | reading: percent | yes | simulated or absent |

A reading a robot does not have must be **absent**, not zero. A simulated robot
reporting a fake battery would be a lie the chart cannot tell from a real one.

## Out of scope

- Any new hardware driver (Arduino, Raspberry Pi, make:bot). The interface is
  designed so they fit; building one is a later story.
- The virtual world itself — US-009.
- Renaming the `wowpy` package or the repository. The name stops fitting once
  the MiP is one device among several, but that is a separate decision with its
  own fallout (imports, `setup.py`, the GitHub URL).
- Changing the saved format of `programs/*.json` and `blocks/*.json` beyond what
  the `mip`/`robot` alias needs.

## Acceptance criteria

See `robot-abstraction.feature`.
