"""Validation for hand-written block bodies (user story US-005).

A custom block may hold Python instead of a stack of blocks. That code runs in
the server's event loop, so before it is ever saved it has to

1. compile as the body of ``async def <block>(mip, ...)``, and
2. yield to the event loop inside every loop.

Rule 2 is the important one: generated block code awaits on every iteration,
which is what lets Stop interrupt a running program. A hand-written
``while True: pass`` never yields, and would freeze the whole server - Stop,
the status poll and every open page - until the process is killed.
"""

import ast

from .codegen import func_name, normalise_code

EMPTY = "der Baustein braucht mindestens eine Zeile"
LOOP_NEEDS_AWAIT = (
    "Schleife in Zeile {line} enthält kein await. "
    "Ohne await blockiert sie den Server und Stopp wirkt nicht mehr - "
    "nimm z. B. 'await asyncio.sleep(0)' in die Schleife auf."
)


class CodeError(ValueError):
    """Block code that must not be saved."""


def _contains_await(node):
    """True if ``node``'s own body awaits, ignoring nested function definitions.

    A loop that only awaits inside a nested ``def`` still never yields itself,
    so those bodies do not count.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef, ast.Lambda)):
            continue
        if isinstance(child, (ast.Await, ast.AsyncFor, ast.AsyncWith)):
            return True
        if _contains_await(child):
            return True
    return False


def _check_loops(tree, line_offset):
    for node in ast.walk(tree):
        if not isinstance(node, (ast.While, ast.For)):
            continue
        # An await anywhere in the loop body (including a nested loop that
        # awaits) is enough - the iteration cannot run away without yielding.
        if _contains_await(node):
            continue
        # A loop that always breaks out cannot spin forever.
        if any(isinstance(n, (ast.Break, ast.Return)) for n in ast.walk(node)):
            continue
        raise CodeError(LOOP_NEEDS_AWAIT.format(line=node.lineno - line_offset))


def validate(code, params=()):
    """Raise :class:`CodeError` if ``code`` cannot be a block body.

    Returns the normalised body on success.
    """
    body = normalise_code(code)
    if body == "pass" and not str(code or "").strip():
        raise CodeError(EMPTY)

    names = ["mip"] + [func_name(p["name"] if isinstance(p, dict) else p) for p in params]
    header = f"async def _block({', '.join(names)}):\n"
    candidate = header + "\n".join("    " + line if line.strip() else line
                                   for line in body.split("\n"))
    try:
        tree = ast.parse(candidate)
    except SyntaxError as e:
        line = max(1, (e.lineno or 2) - 1)      # the header occupies line 1
        raise CodeError(f"Zeile {line}: {e.msg}") from None
    _check_loops(tree, line_offset=1)
    return body
