"""Tests for the ATARI PILOT value model.

Covers ``SPEC.md`` section 6.2 (16-bit numerics) and section 6.5 (text
expressions). Each test names the rule it pins, and the values come from the
Atari sources rather than from Python's own behaviour - division truncation and
16-bit wrap are the two places where "obviously correct" Python would be wrong.
"""

from __future__ import annotations

import pytest

from pypilot.errors import PilotRuntimeError
from pypilot.state import PilotState
from pypilot.values import (
    INT16_MAX,
    INT16_MIN,
    MAX_STRING_LENGTH,
    Kind,
    Numeric,
    expand_text,
    scan_text,
    wrap16,
)

D = "$"  # kept as a name so PowerShell never eats the sigil in a heredoc
H = "#"


# ---------------------------------------------------------------------------
# 6.2 Numeric semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 0),
        (1, 1),
        (-1, -1),
        (INT16_MAX, INT16_MAX),
        (INT16_MIN, INT16_MIN),
        (INT16_MAX + 1, INT16_MIN),  # wraps, and is NOT an error
        (INT16_MIN - 1, INT16_MAX),
        (65535, -1),
        (70000, 4464),
    ],
)
def test_wrap16_truncates_to_signed_16_bit(raw: int, expected: int) -> None:
    """Spec 6.2 - overflow wraps silently rather than raising."""
    assert wrap16(raw) == expected


def test_numeric_construction_wraps() -> None:
    assert Numeric(32768).value == INT16_MIN


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (32767, 1, -32768),  # the Primer's own example
        (32767, -32768, -1),
        (-32768, -1, 32767),
        (-1, 1, 0),
        (0, 32767, 32767),
    ],
)
def test_addition_wraps_at_16_bits(left: int, right: int, expected: int) -> None:
    """Spec 6.2 - "32767 + 1 will return -32768 instead of 32768"."""
    assert (Numeric(left) + Numeric(right)).value == expected


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        # The Primer's worked examples (p.85): longhand division, remainder
        # dropped, quotient kept.
        (7, 3, 2),
        (5, 4, 1),
        (10, 5, 2),
        (99, 12, 8),
        # Truncation toward zero - NOT Python floor division, and NOT
        # round-half-away-from-zero.
        (-7, 3, -2),
        (7, -3, -2),
        (-7, -3, 2),
        (1, 2, 0),
        (-1, 2, 0),
    ],
)
def test_division_truncates_toward_zero(left: int, right: int, expected: int) -> None:
    """Spec 6.2 - the quotient takes the sign of the dividend."""
    assert (Numeric(left) / Numeric(right)).value == expected


def test_division_is_not_python_floor_division() -> None:
    """The distinction that would silently break a lesson if got wrong."""
    assert (Numeric(-7) / Numeric(3)).value == -2
    assert -7 // 3 == -3, "Python floors; PILOT truncates"


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        # Modulo is the remainder of the longhand division above.
        (7, 3, 1),
        (5, 4, 1),
        (10, 5, 0),
        (99, 12, 3),
        # Spec 5.1.7: "\\ is the modulus operator (result is always positive)".
        # The absolute remainder, NOT the C convention where the result takes
        # the sign of the dividend.
        (-7, 3, 1),
        (7, -3, 1),
        (-7, -3, 1),
    ],
)
def test_modulo_result_is_always_positive(left: int, right: int, expected: int) -> None:
    """Spec 6.2 - the remainder is the absolute value, per spec 5.1.7."""
    assert (Numeric(left) % Numeric(right)).value == expected


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda a, b: a / b, id="truediv"),
        pytest.param(lambda a, b: a % b, id="modulo"),
    ],
)
def test_division_and_modulo_by_zero_raise(operation) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PilotRuntimeError, match="by zero"):
        operation(Numeric(5), Numeric(0))


def test_arithmetic_wraps_through_the_operators() -> None:
    assert (Numeric(32767) + Numeric(1)).value == -32768
    assert (Numeric(-32768) - Numeric(1)).value == 32767
    assert (Numeric(10000) * Numeric(4)).value == -25536


def test_numeric_comparisons() -> None:
    assert Numeric(5) < Numeric(10)
    assert Numeric(5) <= 5
    assert Numeric(-1) < Numeric(0)
    assert Numeric(3) == 3
    assert bool(Numeric(1))
    assert not bool(Numeric(0))


def test_comparison_against_a_bare_int_wraps_the_int() -> None:
    """A literal in a program is a PILOT number, so it wraps on entry (spec 5.1.1).

    ``32768`` and ``-32768`` are the *same* 16-bit value, so a comparison
    against a raw Python int must wrap the int first — otherwise 2**16
    arithmetic would leak into a language that has no 16-bit boundary.
    """
    assert Numeric(32768) == -32768
    assert Numeric(0) == 65536, "65536 wraps to 0, so they compare equal"
    assert Numeric(1) == 65537, "65537 wraps to 1"
    assert Numeric(5) != 6, "a genuinely different value is still unequal"


def test_numeric_converts_to_int() -> None:
    assert int(Numeric(42)) == 42
    assert [1, 2, 3][Numeric(1)] == 2


def test_numeric_repr_round_trips() -> None:
    assert repr(Numeric(-5)) == "Numeric(-5)"
    assert str(Numeric(-5)) == "-5"


# ---------------------------------------------------------------------------
# 6.5 Text expressions - scanning
# ---------------------------------------------------------------------------


def test_plain_text_is_one_piece() -> None:
    pieces = scan_text("HELLO WORLD")
    assert len(pieces) == 1
    assert pieces[0].kind is Kind.TEXT
    assert not pieces[0].is_reference


def test_variable_references_are_pieces() -> None:
    pieces = scan_text("A#B$C")
    assert [p.kind for p in pieces] == [Kind.TEXT, Kind.NUMERIC, Kind.STRING]
    assert [p.text for p in pieces] == ["A", "B", "C"]


def test_empty_text_scans_to_nothing() -> None:
    assert scan_text("") == ()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Spec 5.2.1's own examples: the sigil is literal because the next
        # character does not start a valid variable specification, so `30#.`
        # keeps its `#`, and `$#V.` is a literal `$` then numeric `#V`.
        ("YOUR WEIGHT IS 30#.", "YOUR WEIGHT IS 30#."),
        (f"THE COST IS {D}{H}V.", f"THE COST IS {D}V."),
        # A lone sigil, and a sigil followed by another sigil: the first sigil
        # is literal because the second does not begin a name.
        (D, D),
        (H, H),
        (f"{D}{D}A", "A"),
        (f"{H}{D}A", f"{H}A"),
        # A trailing % is not a special variable.
        ("100%", "100%"),
    ],
)
def test_a_sigil_not_followed_by_a_valid_reference_is_literal(text: str, expected: str) -> None:
    """Spec 5.2.1 - there is no escape mechanism in ATARI PILOT.

    A sigil is literal when the character after it does not begin a valid
    variable specification, which is why a space always works as a separator.
    The default lookup substitutes an undefined name for its own name
    (spec 6.1), so a surviving ``#V`` here prints as ``V`` with no state.
    """
    assert expand_text(text) == expected


def test_a_literal_sigil_before_a_real_reference_prints_both() -> None:
    """``$#V.`` with ``#V`` defined is a literal ``$`` then the number."""
    state = PilotState()
    state.set_number("V", 5)
    assert state.expand(f"THE COST IS {D}{H}V.") == "THE COST IS $5."


def test_two_letter_numeric_reference_is_not_a_reference() -> None:
    """Spec 5.1.2 - only #A-#Z exist, so `#AB` is a literal sigil plus text."""
    pieces = scan_text("VAL #AB")
    assert all(not p.is_reference or p.kind is not Kind.NUMERIC for p in pieces)
    assert expand_text("VAL #AB") == "VAL #AB"


def test_trailing_underscore_yields_a_blank() -> None:
    """Spec 5.2.3 - the underscore is how a trailing blank is written."""
    assert expand_text("SURE_") == "SURE "


def test_underscore_elsewhere_is_literal() -> None:
    assert expand_text("A_B") == "A_B"


def test_question_mark_is_literal_in_a_text_expression() -> None:
    """Spec 5.2.1 - `?` is **not** in the list of characters that cannot be a
    literal, so it is ordinary text here.

    Spec 5.1.3 allows `?` "anywhere a numeric expression is allowed", and a text
    expression is not one. The spec's own example `T:#X%, ARE YOU SURE?` needs
    the `?` to print literally, and so does its 6.1.4 worked example
    `A:=WHAT WILL HAPPEN?`. `?` is handled in `nexp`, not in a text operand.
    """
    assert expand_text("N=?") == "N=?"
    assert all(p.kind is not Kind.RANDOM for p in scan_text("N=?"))


def test_a_question_mark_does_not_corrupt_a_text_operand() -> None:
    """Regression: `?` used to expand as a random number here, which silently
    corrupted the accept buffer in the spec's §6.1.4 worked example."""
    assert expand_text("WHAT WILL HAPPEN?") == "WHAT WILL HAPPEN?"


def test_indirection_depth_is_recorded() -> None:
    pieces = scan_text("$$ABC")
    reference = next(p for p in pieces if p.is_reference)
    assert reference.indirection == 2
    assert reference.text == "ABC"


# ---------------------------------------------------------------------------
# 6.5 Text expressions - expansion
# ---------------------------------------------------------------------------


def test_default_lookup_substitutes_the_own_name() -> None:
    """Spec 6.1 - the rule that is the opposite of most PILOT dialects."""
    assert expand_text("[$UNSET]") == "[UNSET]"


def test_expansion_truncates_at_254_silently() -> None:
    """Spec 6.5 - a longer expression is truncated with no error or warning."""
    result = expand_text("X" * 500)
    assert len(result) == MAX_STRING_LENGTH
    assert result == "X" * MAX_STRING_LENGTH


def test_expansion_truncates_after_substitution() -> None:
    long_value = "Y" * 300
    result = expand_text(f"start{D}BIG", lookup=lambda piece: long_value)
    assert len(result) == MAX_STRING_LENGTH
    assert result.startswith("start")


def test_expansion_is_single_pass() -> None:
    """Spec 6.5 - expanded text is never rescanned for further references."""

    def lookup(piece):  # type: ignore[no-untyped-def]
        return f"{D}OTHER"

    assert expand_text(f"{D}SELF", lookup=lookup) == f"{D}OTHER"


def test_expansion_accepts_a_custom_limit() -> None:
    assert len(expand_text("X" * 100, limit=10)) == 10
