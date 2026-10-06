"""Parse every example program and check the parse is faithful.

This is the ``SPEC.md`` section 13 acceptance corpus. The parser is not the
interpreter, so these tests cannot check *behaviour* - they check that each
example is well-formed ATARI PILOT, that the structure the spec says the
example demonstrates is actually present, and that the parse round-trips
through :attr:`Program.source` without drift.

That last property matters more than it looks: a program that cannot be
re-serialised and re-parsed identically is a program whose errors a learner
cannot be shown clearly later.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pypilot.syntax import parse

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"

EXAMPLE_NAMES = [
    "greeter.pilot",
    "numbers.pilot",
    "adventure.pilot",
    "msplit.pilot",
    "recurse.pilot",
    "graphics.pilot",
    "controls.pilot",
    "sound.pilot",
]


def load(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


def commands_in(name: str) -> list[str]:
    """Every command name used by ``name``, in order."""
    return [s.command for s in parse(load(name)).statements if s.command]


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_example_parses(name: str) -> None:
    program = parse(load(name))
    assert len(program) > 0, f"{name} produced no statements"


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_example_round_trips_exactly(name: str) -> None:
    """Serialising a parsed program and re-parsing it must be a no-op."""
    program = parse(load(name))
    reparsed = parse(program.source)
    assert [str(s) for s in reparsed.statements] == [str(s) for s in program.statements]
    assert reparsed.labels == program.labels


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_round_trip_is_stable_over_two_passes(name: str) -> None:
    """Idempotence: rendering twice must converge, not drift each time."""
    once = parse(load(name)).source
    twice = parse(once).source
    assert once == twice


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_every_label_resolves_to_a_real_statement(name: str) -> None:
    program = parse(load(name))
    for label, index in program.labels.items():
        assert 0 <= index < len(program)
        assert program.statements[index].label == label


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_every_jump_and_use_target_is_defined(name: str) -> None:
    """`J:` and `U:` must name a label that exists - the spec requires it."""
    program = parse(load(name))
    for statement in program.statements:
        if statement.command not in {"J", "U", "JM"}:
            continue
        targets = re.split(r"[,\s]+", statement.params.strip())
        for target in filter(None, targets):
            assert program.resolve(target) is not None, (
                f"{name} line {statement.line_number}: "
                f"{statement.command}: names undefined label {target!r}"
            )


# ---------------------------------------------------------------------------
# Per-example structural expectations - the behaviour each was written to show
# ---------------------------------------------------------------------------


def test_greeter_uses_string_accept_and_match() -> None:
    commands = commands_in("greeter.pilot")
    assert "A" in commands
    assert "M" in commands
    assert "T" in commands
    # The `Y`/`N` branch is expressed as a condition, not a command.
    assert any(
        s.condition is not None and s.condition.match in {"Y", "N"}
        for s in parse(load("greeter.pilot")).statements
    )


def test_numbers_uses_only_single_letter_numeric_variables() -> None:
    """Spec 6.1 - there are exactly 26 numeric variables, `#A`..`#Z`."""
    found = set(re.findall(r"#([A-Za-z0-9_]+)", load("numbers.pilot")))
    for name in found:
        assert len(name) == 1, f"multi-character numeric variable {name!r}"
    assert {"X", "Y", "S", "Q", "R"} <= found


def test_numbers_uses_backslash_modulo_not_percent() -> None:
    """Spec 6.2 - modulo is `\\`; `%` is a variable sigil, not an operator."""
    assert re.search(r"#R=#S\\2", load("numbers.pilot"))
    operators = re.findall(r"[a-zA-Z0-9#]\s*([+\-*/%])\s*", load("numbers.pilot"))
    assert "%" not in operators


def test_numbers_uses_conditional_expressions() -> None:
    program = parse(load("numbers.pilot"))
    assert any(s.condition and s.condition.expression for s in program.statements)


def test_adventure_labels_and_modules_line_up() -> None:
    program = parse(load("adventure.pilot"))
    assert set(program.labels) == {"START", "NORTH", "SOUTH", "DESCRIBE", "END"}
    assert "U" in commands_in("adventure.pilot")


def test_adventure_branches_with_jm() -> None:
    """Spec 9.4 - `JM:` is ATARI's multi-way branch."""
    program = parse(load("adventure.pilot"))
    jm = [s for s in program.statements if s.command == "JM"]
    assert jm, "adventure.pilot should branch with JM:"
    assert jm[0].params.count(",") == 1, "expected a two-way JM: list"


def test_msplit_uses_a_assign_and_ms() -> None:
    commands = commands_in("msplit.pilot")
    assert "A" in commands
    assert "MS" in commands
    for variable in ("$LEFT", "$MATCH", "$RIGHT"):
        assert variable in load("msplit.pilot")


def test_recurse_uses_numeric_variables_and_a_module() -> None:
    program = parse(load("recurse.pilot"))
    assert program.resolve("COUNT") is not None
    assert "U" in commands_in("recurse.pilot")
    assert any(s.condition and s.condition.expression for s in program.statements)


def test_graphics_exercises_a_supported_device_command() -> None:
    """`GR:` parses as a supported device command with its graphics operand intact."""
    program = parse(load("graphics.pilot"))
    gr = [s for s in program.statements if s.command == "GR"]
    assert gr, "graphics.pilot should contain a GR: statement"
    assert gr[0].params.strip() == "CLEAR"


#: Commands the examples are allowed to use. Anything else would be spec drift.
ALLOWED_COMMANDS = frozenset(
    {"T", "A", "M", "C", "R", "E", "J", "U", "N", "MS", "JM", "PA", "GR", "SO"}
)


def test_no_example_uses_a_core_pilot_only_command() -> None:
    """Spec 10.6 - a Core-only command in the corpus would be a spec drift."""
    for name in EXAMPLE_NAMES:
        program = parse(load(name))
        for statement in program.statements:
            # Label-only and comment-only lines carry no command at all.
            if statement.command == "":
                continue
            assert statement.command in ALLOWED_COMMANDS, (
                f"{name} line {statement.line_number}: unexpected command {statement.command!r}"
            )


def test_examples_avoid_the_literal_bracket_trap() -> None:
    """A `[` in an operand always starts a comment, so it cannot be printed.

    Spec 4.2 makes `[` an unconditional comment delimiter with no escape, so
    ``T:[$LEFT]`` types `LEFT IS ` and discards the rest of the line. The
    examples must therefore avoid brackets in output text.
    """
    for name in EXAMPLE_NAMES:
        for statement in parse(load(name)).statements:
            if statement.command != "T":
                continue
            assert "[" not in statement.params, (
                f"{name} line {statement.line_number}: a literal '[' in a T: operand "
                "is parsed as a comment delimiter, not printed"
            )
