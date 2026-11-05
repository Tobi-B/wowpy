# US-006 — Edit a custom block's blocks after the fact

**As a** developer who builds his own blocks from a stack of blocks,
**I want** to reopen such a block later and change it — add blocks, adjust
values, add a parameter —
**so that** a block can grow with what I need instead of having to be rebuilt
from scratch every time.

Builds on US-003 (custom blocks) and US-005 (the `mode` field and the code
dialog). Today a block made of blocks can only be converted to Python or
deleted; its stack is stored but unreachable.

## Decisions (from refinement interview, 2026-09-25)

| Topic | Decision |
|---|---|
| Where | A dialog with its own small Blockly canvas and the same toolbox. The program on the main canvas is untouched. |
| Parameters | Editable: add, rename, remove. A new parameter appears on every existing use with its default; a removed one disappears. |
| Shipped blocks | Editable like any other. They are ordinary files in `blocks/`, so a change shows up in the Git diff and can be reverted. |
| Python blocks | Not covered. A `mode: python` block offers "Python bearbeiten" (US-005); to get its blocks back it must be regenerated first. |

## The thing to get right — parameters are identified by name

A parameter is referenced in three places, all of them by its **name**:

| Where | Looks like |
|---|---|
| Inside the block's own workspace | a `custom_param` block with `fields.NAME = "angle"` |
| On a block instance in a program | an input socket named `ANGLE` (the name, upper-cased) |
| In the generated function | the argument `angle` |

So renaming `angle` → `winkel` today would:

- leave every `custom_param` inside the block pointing at a name that no longer
  exists — the generated body would use an undefined `angle`, a `NameError` at
  run time;
- rename the socket on every use from `ANGLE` to `WINKEL`, so the value the user
  had plugged in (`45`) no longer matches any input and is **silently dropped**,
  replaced by the parameter's default on the next save.

Neither failure is visible when it happens. Two ways out:

1. **Give each parameter a stable `id`** (`{"name": "angle", "id": "p1", "default": 90}`)
   and key sockets and `custom_param` references off the id, exactly as Blockly
   does for its own procedures. Renaming then touches only the label.
   Costs a migration for existing `blocks/*.json` (params without an id get one
   on first save) and a change to how input names are built. **Recommended.**
2. Keep names as the key and, on rename, rewrite the block's own
   `custom_param` blocks *and* every saved program in `programs/`. Works, but it
   edits files the user did not open, and a program open in another tab would
   still hold the old socket name.

The scenarios below assume option 1.

**Removing** a parameter that the block's blocks still reference is the same
class of problem and needs an explicit answer: the dialog refuses the removal
and says which blocks still use it.

## Also worth deciding

- **A block must not contain itself.** The generator's cycle guard stops it from
  hanging while generating, but the generated function would recurse forever at
  run time. The editing canvas should not offer the block being edited in its
  own "My blocks" category, and saving should refuse a stack that reaches
  itself through another block.
- **Live preview.** The dialog can show the Python the stack currently
  generates, which is the same view the conversion in US-005 starts from. Cheap,
  and it makes the parameter wiring visible.

## Out of scope

- Editing a `mode: python` block as blocks (one-way, decided in US-005).
- Editing the blocks of a block from within a program's canvas.
- Undo across a save: closing the dialog with "Abbrechen" discards, saving
  commits, and there is no history beyond Git.

## Acceptance criteria

See `edit-blocks.feature`.
