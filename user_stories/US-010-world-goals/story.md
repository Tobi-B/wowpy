# US-010 — Tasks and goals in the virtual world

**As a** developer learning to program the robot,
**I want** the virtual world to set me a task and tell me whether I solved it,
**so that** the world is something to work against rather than only a place to
drive around in.

**Status: parked.** Written down now so the design of US-009 does not block it,
but deliberately not scheduled — the world has to exist first. Decided in the
refinement interview of 2026-11-27 ("Ziele sollen später hinzukommen").

## What this adds to US-009

US-009 ends at a world you can drive around in. This story adds the three
things that turn it into Swift Playgrounds:

| Piece | What it is |
|---|---|
| A task | a named starting situation: the world, the robot's start, and what counts as solved |
| A verdict | the world watches the run and says solved or not, and why not |
| A sequence | tasks in an order, so one builds on the last |

## What US-009 must not make impossible

Three things, all cheap to keep open while building the world and expensive to
retrofit:

1. **The world must be loadable from a file.** A task is a world plus a goal;
   if the world is hard-coded, every task needs code.
2. **A run must be observable from outside.** The verdict is decided by
   watching the run — where the robot went, what it touched, how long it took —
   not by instrumenting the user's program. If the world can already report its
   own history, this story needs no changes to the program runner.
3. **A run must be resettable.** Trying a task again has to put the world back
   exactly as it started, including the odometer.

US-009 happens to need all three anyway for its own tests.

## Open questions, to settle when this is picked up

- **What is a goal made of?** A reached area is the obvious first one. Others:
  touching nothing, finishing within a number of commands, visiting things in
  order. Starting with reached-area plus touched-nothing is probably enough.
- **Who writes the tasks?** Shipped with the package, or authored in the
  browser? Shipped files first, consistent with how `blocks/` works.
- **Does a verdict belong in the chart?** A run that failed is interesting
  alongside the sensor lanes from US-007.
- **How much is said when a task fails?** "Not solved" teaches nothing. "You
  stopped 30 cm short" teaches something. The world knows enough for the
  second.

## Out of scope even then

- Scoring, stars, progress tracking across sessions.
- Tasks that need capabilities the simulated robot does not have.
- Generating tasks automatically.

## Acceptance criteria

See `world-goals.feature` — a sketch, to be filled in when this is scheduled.
