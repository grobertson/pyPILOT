"""Tests for the example programs referenced by ``SPEC.md`` section 13.

These do not execute the programs; they assert that every example named in the
spec exists, is non-empty, and sticks to the ATARI PILOT rules that are easiest
to get wrong from Core PILOT intuition. Behavioural coverage of the examples
lives in ``tests/test_accept_match.py`` and ``tests/test_runtime.py``.

Each rule enforced here links back to its section of the spec, so a future
implementer changing the corpus finds out why.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pypilot.match import CURSOR_RIGHT

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"

#: The examples ``SPEC.md`` section 13 commits to shipping.
EXPECTED = [
    "greeter.pilot",
    "numbers.pilot",
    "adventure.pilot",
    "msplit.pilot",
    "recurse.pilot",
    "graphics.pilot",
    "controls.pilot",
    "sound.pilot",
    "summary.pilot",
]

#: A Core PILOT numeric variable, e.g. ``#SUM``. ATARI allows only one letter.
CORE_STYLE_NUMERIC_VAR = re.compile(r"#[A-Za-z][A-Za-z0-9_]")

#: Core PILOT file commands, which do not exist in ATARI PILOT (spec 9.6, 10.6).
CORE_STYLE_FILE_COMMANDS = re.compile(r"^\s*(F[A-Z]|FO|FA|FB|FC|FD|FR|FW)\s*:", re.MULTILINE)

#: Core PILOT-only commands. ``L:`` is especially dangerous - in ATARI PILOT a
#: bare ``L`` is a *label* prefix, not a Link command (spec 10.6).
CORE_STYLE_COMMANDS = re.compile(r"^\s*(L|P|W)\s*:", re.MULTILINE)

#: Scripted answers and expected output fragments, per example.
#:
#: The examples are the acceptance corpus, so they must actually *run*. A
#: static check cannot see a program that parses perfectly and then falls off
#: the end of a module, which is exactly the bug this table caught in
#: ``summary.pilot``: its ``E:`` returned into the module it had just called.
RUNS: dict[str, tuple[list[str], list[str]]] = {
    "greeter.pilot": (["ada", "yes"], ["HELLO, ada.", "WELCOME TO THE COURSE."]),
    "numbers.pilot": (["5", "3"], ["SUM IS 8.", "HALF OF THE SUM IS 4."]),
    "adventure.pilot": (
        ["north", "north", "north", "south"],
        ["YOU WALK NORTH", "THE END"],
    ),
    "msplit.pilot": ([], ["LEFT IS  AT", "UNDEFINED MEANS UNSET", "NULL IS ."]),
    "recurse.pilot": ([], ["GOING DEEPER...", "BOTTOM REACHED.", "AT DEPTH 3."]),
    "summary.pilot": (
        ["yes"],
        ["YOU SAID YES - THAT WAS FIELD 1.", "COUNT 1", "COUNT 5"],
    ),
}


def run_example(name: str) -> str:
    """Run an example to completion and return its output.

    Raises:
        AssertionError: if the example does not run, which is the failure this
            exists to catch. A corpus program that parses and then does the
            wrong thing is worse than one that fails to parse, because it looks
            fine in a listing.
    """
    from pypilot.io import BufferOutput, StringInput
    from pypilot.runtime import Interpreter
    from pypilot.syntax import parse

    answers, _ = RUNS[name]
    out = BufferOutput()
    interpreter = Interpreter(
        parse(read(name)),
        output=out,
        source=StringInput(answers),
        device_root=str(EXAMPLES.parent / "dist" / "example-devices"),
    )
    interpreter.run()
    return out.text


def read(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


def executable_lines(name: str) -> list[str]:
    """Lines that are neither blank, nor ``R:`` remarks, nor label-only lines."""
    return [
        line
        for line in read(name).splitlines()
        if line.strip() and not line.strip().startswith(("R:", "*"))
    ]


@pytest.mark.parametrize("name", EXPECTED)
def test_example_exists_and_is_not_empty(name: str) -> None:
    assert (EXAMPLES / name).is_file(), f"missing example program: {name}"
    assert read(name).strip()


@pytest.mark.parametrize("name", EXPECTED)
def test_example_has_executable_statements(name: str) -> None:
    assert executable_lines(name), f"example has no executable statements: {name}"


@pytest.mark.parametrize("name", EXPECTED)
def test_example_uses_only_single_letter_numeric_variables(name: str) -> None:
    """ATARI PILOT has exactly 26 numeric variables, ``#A`` through ``#Z``.

    A multi-character name would not parse once the interpreter exists, because
    ``#XY`` is not a valid ATARI numeric variable (spec 6.1).
    """
    offenders = CORE_STYLE_NUMERIC_VAR.findall(read(name))
    assert not offenders, (
        f"{name} uses multi-character numeric variable(s) {offenders}; "
        "ATARI PILOT allows only #A-#Z (spec 6.1)"
    )


@pytest.mark.parametrize("name", EXPECTED)
def test_example_avoids_core_pilot_file_commands(name: str) -> None:
    """``FO:``/``FR:``/``FC:`` are Core PILOT; ATARI uses READ/WRITE/CLOSE."""
    assert not CORE_STYLE_FILE_COMMANDS.search(read(name)), (
        f"{name} uses a Core PILOT file command; ATARI PILOT is device-oriented "
        "with READ:/WRITE:/CLOSE: (spec 9.6, 10.6)"
    )


@pytest.mark.parametrize("name", EXPECTED)
def test_example_avoids_core_pilot_only_commands(name: str) -> None:
    """``L:``, ``P:`` and ``W:`` are not ATARI commands (spec 10.6)."""
    assert not CORE_STYLE_COMMANDS.search(read(name)), (
        f"{name} uses a Core PILOT-only command; see spec section 10.6"
    )


def test_numbers_example_uses_backslash_modulo() -> None:
    """Modulo is ``\\`` in ATARI PILOT; ``%`` is a variable sigil (spec 6.2)."""
    assert "C:#R=#S\\2" in read("numbers.pilot")


def test_numbers_example_exercises_truncating_division() -> None:
    """``#S/2`` must truncate - 7/2 is 3, not 4 (spec 6.2)."""
    assert "C:#Q=#S/2" in read("numbers.pilot")


def test_adventure_example_uses_jm_for_multi_way_branching() -> None:
    """``JM:`` is ATARI's multi-way branch; ``@M`` jumps do not exist (spec 9.4)."""
    source = read("adventure.pilot")
    assert "JM:*NORTH,*SOUTH" in source
    assert not re.search(r"@M\b", source)


def test_msplit_example_matches_the_spec_worked_example() -> None:
    """``msplit.pilot`` is the spec's own worked example, so it is load-bearing.

    It is the §6.1.4 example that is actually reproducible: ``A:=WHAT WILL
    HAPPEN?`` with three cursor-rights. The `?` matters - it is literal text in
    a text expression (spec 5.2.1), so the buffer really does end in a question
    mark and the printed `$LEFT` of ``'AT'`` holds.
    """
    source = read("msplit.pilot")
    assert "A:=WHAT WILL HAPPEN?" in source
    assert f"MS:{CURSOR_RIGHT * 3}_" in source
    for var in ("$LEFT", "$MATCH", "$RIGHT"):
        assert var in source


def test_msplit_example_covers_the_undefined_variable_rule() -> None:
    """An undefined string prints its own name (spec 6.1) - pin it in the corpus."""
    assert "UNDEFINED MEANS $UNSET" in read("msplit.pilot")


def test_graphics_example_exercises_the_graphics_language() -> None:
    """The graphics example contains a real repeated turtle drawing."""
    source = read("graphics.pilot")
    assert "GR:CLEAR" in source
    assert "4(DRAW 15;TURN 90)" in source
    assert source.index("GR:CLEAR") < source.index("E:")


@pytest.mark.parametrize("name", sorted(RUNS))
def test_every_runnable_example_actually_runs(name: str) -> None:
    """The corpus must *execute*, not merely parse.

    A program that parses and then does the wrong thing is worse than one that
    fails to parse, because a listing looks perfectly fine. This caught
    `summary.pilot` re-entering its own module every time it returned.
    """
    _, expected = RUNS[name]
    output = run_example(name)
    for fragment in expected:
        assert fragment in output, f"{name} did not produce {fragment!r}"


def test_graphics_example_runs_with_an_injected_host(interactive_host) -> None:  # type: ignore[no-untyped-def]
    """The graphics corpus runs without opening a real window in unit tests."""
    from pypilot.runtime import Interpreter
    from pypilot.syntax import parse

    interpreter = Interpreter(
        parse(read("graphics.pilot")),
        output=interactive_host,
        source=interactive_host,
        interactive=interactive_host,
    )
    interpreter.run()

    assert any(operation[0] == "line" for operation in interactive_host.operations)
    assert "SQUARE COMPLETE AT (0,0)" in interactive_host.text.text


def test_controller_example_reads_virtual_joystick_and_trigger(interactive_host) -> None:  # type: ignore[no-untyped-def]
    from pypilot.runtime import Interpreter
    from pypilot.syntax import parse

    interactive_host.controller_values[("T", "8")] = 1
    interpreter = Interpreter(
        parse((EXAMPLES / "controls.pilot").read_text(encoding="utf-8")),
        output=interactive_host,
        source=interactive_host,
        interactive=interactive_host,
    )
    interpreter.run()

    assert "SPACE TRIGGER PRESSED." in interactive_host.text.text


def test_sound_example_changes_and_stops_four_voices(interactive_host) -> None:  # type: ignore[no-untyped-def]
    from pypilot.runtime import Interpreter
    from pypilot.syntax import parse

    interpreter = Interpreter(
        parse((EXAMPLES / "sound.pilot").read_text(encoding="utf-8")),
        output=interactive_host,
        source=interactive_host,
        interactive=interactive_host,
    )
    interpreter.run()

    assert (13, 17, 20, 24) in interactive_host.audio_updates
    assert (14, 17, 20, 24) in interactive_host.audio_updates
    assert interactive_host.audio_updates[-1] == ()


@pytest.mark.parametrize("name", EXPECTED)
def test_spec_references_the_example(name: str) -> None:
    spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")
    assert name in spec, f"SPEC.md does not reference {name}"
