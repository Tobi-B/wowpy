"""Validation of hand-written block bodies (US-005)."""

import pytest

from wowpy.blockcode import EMPTY, CodeError, validate

PARAMS = [{"name": "angle"}, {"name": "wie oft"}]


@pytest.mark.parametrize("code", [
    "await mip.stop()",
    "await mip.turn_left(angle, 12)",
    "import random\nawait mip.turn_left(random.randint(1, angle), 12)",
    "while True:\n    await asyncio.sleep(0.05)",
    "for i in range(wie_oft):\n    await mip.play_sound(i)",
    "async for x in thing:\n    pass",
    "for i in range(3):\n    if i:\n        break",
    "for i in range(3):\n    return i",
    "while True:\n    for _ in range(2):\n        await mip.stop()",
    "x = 1\nif x:\n    await mip.stop()\nelse:\n    await mip.play_sound(1)",
])
def test_accepted(code):
    assert validate(code, PARAMS)


def test_returns_the_normalised_body():
    assert validate("    await mip.stop()\n", PARAMS) == "await mip.stop()"


def test_leading_and_trailing_blank_lines_are_trimmed():
    assert validate("\n\nawait mip.stop()\n\n", PARAMS) == "await mip.stop()"


@pytest.mark.parametrize("code, message", [
    ("", EMPTY),
    ("   \n  \n", EMPTY),
    ("await mip.stop(", "Zeile 1"),
    ("await mip.stop()\n  await mip.stop()", "Zeile 2"),
    ("def :", "Zeile 1"),
])
def test_rejected(code, message):
    with pytest.raises(CodeError, match=message):
        validate(code, PARAMS)


# -- the rule the user asked for: every loop must yield ---------------------

@pytest.mark.parametrize("code", [
    "while True:\n    pass",
    "while True:\n    x = 1",
    "for i in range(10):\n    x = i",
    "await mip.stop()\nwhile True:\n    x = 1",
    # awaiting only inside a nested function does not make the loop yield
    "while True:\n    async def inner():\n        await mip.stop()",
])
def test_loop_without_await_is_refused(code):
    with pytest.raises(CodeError, match="kein await"):
        validate(code, PARAMS)


def test_the_loop_error_names_the_line():
    with pytest.raises(CodeError, match="Zeile 3"):
        validate("await mip.stop()\nx = 1\nwhile True:\n    x = 2", PARAMS)


def test_a_loop_that_can_break_out_is_allowed():
    """It cannot spin forever, so it will not wedge the event loop."""
    assert validate("for i in range(1000):\n    if i > 5:\n        break", PARAMS)


def test_nested_loop_without_await_is_caught():
    with pytest.raises(CodeError, match="kein await"):
        validate("while True:\n    await asyncio.sleep(0)\n    for i in range(10):\n        x = i", PARAMS)


def test_parameter_names_are_available_to_the_code():
    # "wie oft" becomes wie_oft, matching the generated signature
    assert validate("await mip.play_sound(wie_oft)", PARAMS)
    with pytest.raises(CodeError):
        validate("await mip.play_sound(wie oft)", PARAMS)
