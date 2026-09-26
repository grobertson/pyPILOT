"""Tests for the less-travelled corners of the value model.

These paths are not exercised by ordinary programs, but each one is a place
where a wrong answer would be silent rather than loud, so they are pinned
explicitly. Covers pointer scanning, the coercion helper, and the remaining
operators.
"""

from __future__ import annotations

import pytest

from pypilot.errors import PilotRuntimeError
from pypilot.values import Kind, Numeric, expand_text, scan_text

# ---------------------------------------------------------------------------
# Operators not covered by the arithmetic tests
# ---------------------------------------------------------------------------


def test_unary_operators() -> None:
    assert (-Numeric(5)).value == -5
    assert (+Numeric(5)).value == 5


def test_numeric_coerces_from_a_numeric_string() -> None:
    assert (Numeric(10) + "5").value == 15


def test_arithmetic_with_a_non_number_raises() -> None:
    with pytest.raises(PilotRuntimeError, match="cannot use"):
        _ = Numeric(1) + object()


def test_numeric_equality_with_an_unrelated_type_is_not_implemented() -> None:
    assert Numeric(1).__eq__(object()) is NotImplemented
    assert Numeric(1) != "1"


def test_numeric_is_hashable_by_value() -> None:
    assert len({Numeric(5), Numeric(5), Numeric(6)}) == 2


def test_all_four_ordering_operators() -> None:
    lower, higher = Numeric(3), Numeric(5)
    assert lower < higher
    assert lower <= higher
    assert higher > lower
    assert higher >= lower
    assert higher >= Numeric(5)
    assert not (lower > higher)


# ---------------------------------------------------------------------------
# Memory pointers (5.1.6) - a numeric construct, so literal in text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["5*6", "a@b", "*4096", "@B4096"])
def test_pointer_sigil_is_literal_in_a_text_expression(text: str) -> None:
    """Spec 5.1.6 - "a pointer may be used anywhere a *numeric variable* is
    allowed".

    Pointers are a construct of ``nexp``, not of a text expression, so the text
    scanner must leave ``*`` and ``@`` alone. Reading them as references would
    make ``5*6`` lose its sign entirely.
    """
    assert expand_text(text) == text


# ---------------------------------------------------------------------------
# Scanning edge cases
# ---------------------------------------------------------------------------


def test_a_sigil_at_the_very_end_is_literal() -> None:
    assert expand_text("cost 5#") == "cost 5#"


def test_a_sigil_before_a_space_is_literal() -> None:
    """Spec 5.2.1 - a space always works as a separator.

    ``$ #V`` is a literal ``$``, a blank, then a real numeric reference. With
    no state the undefined ``#V`` prints as its own name, ``V``.
    """
    assert expand_text("cost $ #V") == "cost $ V"


def test_variable_name_may_contain_underscores() -> None:
    pieces = scan_text(f"{'$'}MY_VAR")
    reference = pieces[0]
    assert reference.is_reference
    assert reference.text == "MY_VAR"


def test_piece_exposes_its_name() -> None:
    piece = scan_text(f"{'$'}NAME")[0]
    assert piece.name_for_lookup() == "NAME"


def test_empty_text_piece_reports_no_reference() -> None:
    piece = scan_text("plain")[0]
    assert piece.kind is Kind.TEXT
    assert not piece.is_reference
