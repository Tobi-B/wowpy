# US-009 — A virtual robot in a 3D world

**As a** developer who wants to program without working hardware,
**I want** a robot in a visible 3D world in the browser that my block programs
drive, that bumps into obstacles and whose sensors read the world,
**so that** I can build and try out programs when the robot is broken, out of
range, or simply not the device I am targeting.

The model is Swift Playgrounds: you write the program, you press run, and you
watch a robot carry it out in a world you can see.

## Decisions (from refinement interview, 2026-11-27)

| Topic | Decision |
|---|---|
| Dimensions | **3D**, rendered in the browser. Not a 2D top-down map. |
| What it is for | Running real block programs against a visible robot, with sensors that read the world. |
| Goals and levels | **Later** — US-010. This story builds the world, not the tasks. |
| Relation to US-008 | The simulated robot is a driver behind the robot interface. Programs do not know which one they drive. |
| Repository | Built here as its own package with its own install extra; split into its own repository once the driver interface has stopped changing. |

## Where the world lives — on the server

The tempting design is to put the world in the browser, where the rendering is.
It is the wrong one.

Programs execute **server-side** (`program.py`), and a program asks for sensor
readings inside its own control flow — `while distance() != "free": …`. If the
world lived in the browser, every such reading would be a round trip over the
WebSocket, and a program's behaviour would depend on browser frame rate, tab
focus and network timing. It would also be untestable: the 271 existing tests
run without a browser.

So the world is authoritative **on the server** and the browser is a viewer:

```
program.py  ──drives──>  SimDriver  ──>  World (server, headless)
                                           │
                                     state over WebSocket
                                           ↓
                              three.js scene in the browser
```

This also means the world runs perfectly well with no browser open at all,
which is what the test suite needs.

## The robot model

Kinematic differential drive — two wheels, a heading, a position. Good enough
to make driving, turning and bumping feel right, and simple enough to be
deterministic.

**Balancing is not simulated.** The MiP's defining trick is standing on two
wheels, and modelling that honestly means a physics engine and a controller to
tune — the very thing that is broken on the real robot. The simulated robot
stands; `orientation` reports `upright` unless it is tipped by a collision.
Pretending otherwise would teach the wrong thing about the real one.

## Sensors read the world, and only what the world knows

| Reading | How the world answers |
|---|---|
| `distance` | ray cast forward; mapped to the same three classes the MiP reports — free, 10–30 cm, under 10 cm |
| `orientation` | upright, or tipped after a hard collision |
| `odometer` | distance actually travelled, not distance commanded |
| `battery` | **absent.** A simulated robot has no battery, and a faked one would be indistinguishable from a real reading in the chart |

The distance classes are deliberately the MiP's three buckets rather than a
continuous number, so a program that works in the world works on the robot.
Keeping the simulated sensor *more* precise than the real one would let
programs be written that cannot work on hardware.

## Time

Two modes, because they serve different needs:

- **Real time** for watching: the world steps at wall-clock speed, the browser
  renders it, a `wait 2 s` takes two seconds.
- **Stepped** for tests: the world advances by a fixed tick that the test
  drives, so a scenario runs in milliseconds and gives the same answer every
  time.

A program must not be able to tell which mode it is in.

## What the browser shows

A three.js scene: a floor, the obstacles, the robot with its chest LED in the
colour the program set. The camera can be moved. The existing block editor gets
a "run in the world" target next to the real robot, and the block highlighting
from US-003 keeps working — you see the block light up and the robot move.

Loading three.js follows the pattern already used for Blockly: a pinned version
from a CDN, with the version written out in full.

## Package layout

```
wowsim/__init__.py     the world, headless and importable
wowsim/world.py        floor, obstacles, stepping, ray casts
wowsim/robot.py        the differential-drive body
wowsim/driver.py       SimDriver — implements the US-008 robot interface
wowsim/static/         the three.js viewer
```

Installed as an extra: `pip install -e ".[sim]"`, so the core package keeps its
small dependency set and someone who only drives a real robot does not pull in
the viewer.

**On splitting it out:** the dependency direction is clean (`wowsim` → `wowpy`,
never back), so a later move to its own repository is a `git filter-repo` plus a
dependency line. Doing it now, while the US-008 interface is still being
invented, would turn every interface change into a two-repository change. Split
when the interface stops moving.

## Out of scope

- **Goals, levels and success checking** — US-010. This story ends at a world
  you can drive around in.
- Balance physics, as argued above.
- More than one robot in the world.
- Editing the world in the browser. Worlds are files; a built-in world and the
  ability to load one are enough.
- Simulating the MiP's sounds, gestures, clap detection or game modes. The
  simulated robot declares only the capabilities it can honestly provide.
- Collision realism beyond "stop and report a bump".

## Acceptance criteria

See `virtual-world.feature`.
