# US-005 — Editable Python inside my own blocks

**As a** developer building complex control rules for the MiP,
**I want** my own blocks to hold plain Python that I can edit — either by
converting a stack of blocks or by writing one from scratch,
**so that** a block can do things the block language cannot express — maths,
state, retries, timing — while still being a block I can drop into a program.

Builds on US-003 (custom blocks, `blocks/*.json`, the generator and the runner).

## Decisions (from refinement interview, 2026-09-24)

| Topic | Decision |
|---|---|
| Direction | **One-way.** "In Python umwandeln" takes the block stack's generated body and makes it editable. From then on the code is the source of truth and the stack is gone from the block. No code → blocks round trip. |
| Editing | In the browser, in the block's dialog. Saving validates the code server-side; invalid code is refused with the message and line number. |
| Creating from scratch | **Offered.** "Neuer Python-Baustein" asks for a name, a colour and parameters and opens an empty body — for things that cannot be expressed in blocks at all. Such a block has no stored workspace, so it cannot be regenerated from blocks. |
| What the code may do | The same as generated code: `mip`, `sensors`, `program`, `asyncio`, `math`, `random`, plus its own imports. The server binds to localhost only. |

## Model

A definition in `blocks/<name>.json` gains a mode:

```json
{
  "name": "Warn and turn",
  "colour": 20,
  "params": [{"name": "angle", "default": 90}],
  "mode": "python",
  "code": "await mip.set_chest_led(255, 0, 0)\nawait mip.play_sound(3)\nawait mip.turn_left(angle, 12)",
  "workspace": { "...": "kept as provenance, no longer generated from" }
}
```

- `mode` is `"blocks"` (today's behaviour, the default when absent) or `"python"`.
- The original `workspace` is **kept read-only** so a conversion can be undone
  by regenerating from it — the one escape hatch, and it discards code edits
  after a confirmation. A block written from scratch has no workspace, so that
  option is simply not offered for it.
- Parameters stay what they are: names and defaults. In the code they are plain
  Python names (`angle`), in the workspace they are sockets on the block.

Generation for a Python block is the body indented into a function, nothing else:

```python
async def warn_and_turn(mip, angle):
    await mip.set_chest_led(255, 0, 0)
    await mip.play_sound(3)
    await mip.turn_left(angle, 12)
```

## Open question — which functions get generated

Today a custom block's function is emitted only when the generator *sees* a
block calling it. Hand-written code breaks that: a Python block whose body says

```python
await warn_and_turn(mip, 90)
```

creates a dependency the generator cannot see, so `warn_and_turn` is never
emitted and the program dies with a `NameError` at run time. Three ways out,
to be decided before building:

1. **Emit every defined custom block, always.** Predictable and trivial to
   implement; costs a few unused functions in the generated file.
   **← decided 2026-09-24.**
2. Scan each Python body for identifiers that match a custom block's function
   name and emit those. No bloat, but a heuristic — a name built at run time
   still fails.
3. Let the dialog declare dependencies explicitly. Precise, most work, and one
   more thing to keep in sync by hand.

Consequence of the decision: every generated program contains a function for
every block in `blocks/`, including the shipped ones it does not use.

## Known risk — worth deciding on before building

Generated block code yields to the event loop on every loop iteration
(`await asyncio.sleep(0)`), which is what makes **Stop** work. Hand-written code
carries no such guarantee: a body with

```python
while True:
    pass
```

never yields, so the whole server — Stop, the status poll, every other page —
freezes until the process is killed. This is a foot-gun that only appears in
Python blocks.

The story below takes the cheap route: say so in the dialog and in the
generated file. Two stronger options exist if that is not enough:

1. Reject a body whose loops contain no `await` (an AST check — catches the
   common case, not every case).
2. Run programs in a subprocess, so a wedged program can be killed without
   taking the server with it. Bigger change, also fixes it for good.

## Out of scope

- Code → blocks in any form.
- A syntax-highlighting code editor; a plain monospace text area with
  server-side validation is enough for the first iteration.
- Sandboxing the code.
- Editing the generated `programs/*.py` and having that flow back.

## Acceptance criteria

See `python-blocks.feature`.
