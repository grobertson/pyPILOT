"""Tests for `PilotState.evaluate` — expressions evaluated against real state.

The evaluator itself is covered by ``tests/test_expressions.py``. What matters
here is that it reads *this* state's variables, specials and random source, and
that the two surprising rules from spec 5.1.7 survive the wiring:

* there is **no operator precedence** — everything is left to right;
* the remainder of ``\\`` is **always positive**.
"""

from __future__ import annotations

import pytest

from pypilot.errors import PilotRuntimeError
from pypilot.expressions import ExpressionError
from pypilot.state import PilotState
from pypilot.values import Numeric

D = "$"


@pytest.fixture
def state() -> PilotState:
    """A state with ``#A`` = 10 and ``#B`` = 3."""
    s = PilotState()
    s.set_number("A", 10)
    s.set_number("B", 3)
    return s


# ---------------------------------------------------------------------------
# Reading variables out of state
# ---------------------------------------------------------------------------


def test_evaluate_reads_a_single_variable(state: PilotState) -> None:
    assert state.evaluate("#A").value == 10


def test_evaluate_reads_an_unset_variable_as_zero(state: PilotState) -> None:
    """Spec 5.1.2 - an unassigned numeric variable is 0, not an error."""
    assert state.evaluate("#Z").value == 0


def test_evaluate_combines_variables(state: PilotState) -> None:
    assert state.evaluate("#A+#B").value == 13


def test_evaluate_divides_variables(state: PilotState) -> None:
    assert state.evaluate("#A/#B").value == 3, "10/3 truncates to 3"


def test_evaluate_modulus_of_variables_is_positive(state: PilotState) -> None:
    """Spec 5.1.7 - the remainder is always positive, even when #A is smaller."""
    assert state.evaluate("#B\\#A").value == 3


def test_evaluate_assignment_is_not_performed(state: PilotState) -> None:
    """``C:`` assigns; ``evaluate`` only reads. Nothing may mutate here."""
    state.evaluate("#A+#B")
    assert state.get_number("A").value == 10
    assert state.get_number("B").value == 3


# ---------------------------------------------------------------------------
# The two rules from spec 5.1.7, verified through state
# ---------------------------------------------------------------------------


def test_no_operator_precedence_through_state(state: PilotState) -> None:
    """``1+2*3`` is 9 in ATARI PILOT, not 7.

    Spec 5.1.7: expressions are evaluated left to right with no precedence
    rules. This is the single most likely thing to get wrong, because every
    other language the reader knows would give 7.
    """
    assert state.evaluate("1+2*3").value == 9
    assert state.evaluate("1+(2*3)").value == 7, "parentheses are the fix"


def test_subtraction_also_has_no_precedence(state: PilotState) -> None:
    assert state.evaluate("10-2-3").value == 5
    assert state.evaluate("10-(2-3)").value == 11


def test_modulus_is_always_positive_through_state(state: PilotState) -> None:
    """Spec 5.1.7 - "the modulus operator (result is always positive)"."""
    state.set_number("A", -7)
    assert state.evaluate("#A\\#B").value == 1
    state.set_number("B", -3)
    assert state.evaluate("#A\\#B").value == 1


# ---------------------------------------------------------------------------
# 16-bit wrap through evaluation
# ---------------------------------------------------------------------------


def test_evaluate_wraps_at_16_bits(state: PilotState) -> None:
    """Spec 6.2 - overflow is silent, not an error."""
    state.set_number("A", 32767)
    assert state.evaluate("#A+1").value == -32768


def test_evaluate_returns_a_numeric(state: PilotState) -> None:
    assert isinstance(state.evaluate("#A+#B"), Numeric)


# ---------------------------------------------------------------------------
# Relational operators and the logical idiom
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("#A>#B", 1),
        ("#B>#A", 0),
        ("#A>=#A", 1),
        ("#A<#B", 0),
        ("#A<=#A", 1),
        ("#A=#A", 1),
        ("#A<>#B", 1),
    ],
)
def test_relational_operators_yield_one_or_zero(
    state: PilotState, expression: str, expected: int
) -> None:
    """Spec 5.1.7 - relationals return 1/0 so they compose with arithmetic.

    This is how the Atari sources spell logical AND and OR: ``(1<2)+(3<2)``.
    """
    assert state.evaluate(expression).value == expected


def test_relationals_compose_as_boolean_and_or(state: PilotState) -> None:
    state.set_number("A", 1)
    state.set_number("B", 2)
    # AND: 1 + 0 = 1 (true). OR: 1 + 1 = 2 (truthy).
    assert state.evaluate("(#A<#B)+(#A<#B)").value == 2
    state.set_number("A", 5)
    assert state.evaluate("(#A<#B)+(#A>#B)").value == 1


# ---------------------------------------------------------------------------
# Specials, controllers and random
# ---------------------------------------------------------------------------


def test_special_m_is_the_match_ordinal(state: PilotState) -> None:
    """Spec 6.6 - %M is the field number that matched, not a boolean."""
    state.record_match(3)
    assert state.evaluate("%M").value == 3
    assert state.evaluate("%M=3").value == 1


def test_specials_read_as_zero_when_unset(state: PilotState) -> None:
    """Graphics specials are 0 with no graphics device (spec 10.4)."""
    assert state.evaluate("%X").value == 0
    assert state.evaluate("%Y").value == 0
    assert state.evaluate("%A").value == 0


def test_special_f_is_reported(state: PilotState) -> None:
    """%F is free memory, a host figure rather than a 6502 one (spec 6.6)."""
    assert state.evaluate("%F").value > 0


def test_controller_sense_reads_as_no_input(state: PilotState) -> None:
    """Spec 10.5 - no Atari hardware, so every sense is 0."""
    assert state.evaluate("%J0").value == 0
    assert state.evaluate("%P0").value == 0
    assert state.evaluate("%T0").value == 0


def test_random_comes_from_the_states_generator() -> None:
    """``?`` draws from this state's generator, so seeding is reproducible."""
    a = PilotState(random_seed=5)
    b = PilotState(random_seed=5)
    a.set_number("A", 0)
    b.set_number("A", 0)
    first = a.evaluate("?")
    assert first.value == b.evaluate("?").value


def test_random_is_in_the_16_bit_range(state: PilotState) -> None:
    """A draw is in -32768..32767 (spec 5.1.3), so it is below 32768.

    Checked against the value the state actually drew rather than against a
    seed, so the assertion does not depend on the draw's order.
    """
    state.seed_random(5)
    value = state.next_random()
    assert -32768 <= value <= 32767
    assert state.evaluate("?") >= -32768


def test_random_never_reaches_32768(state: PilotState) -> None:
    """The upper bound is 32767, so this must never be true."""
    state.seed_random(5)
    assert state.evaluate("?=32768").value == 0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("1+", "ended unexpectedly"),
        ("(1+2", "unbalanced"),
        ("#XY+1", "only #A-#Z"),
        ("#A##B", "must be followed by a variable name"),
        ("*", "must be followed by an address"),
        ("@B", "must be followed by an address"),
    ],
)
def test_bad_expressions_raise(state: PilotState, expression: str, message: str) -> None:
    with pytest.raises(ExpressionError, match=message):
        state.evaluate(expression)


def test_expression_errors_are_runtime_errors(state: PilotState) -> None:
    """They must be catchable as PilotRuntimeError, not just ExpressionError."""
    with pytest.raises(PilotRuntimeError):
        state.evaluate("(1+2")


def test_division_by_zero_raises(state: PilotState) -> None:
    state.set_number("A", 0)
    with pytest.raises(PilotRuntimeError, match="by zero"):
        state.evaluate("#A+1/#A")


def test_nesting_limit_is_enforced(state: PilotState) -> None:
    """Spec 5.1.7 - "up to 2 levels of nested non-redundant parens" are allowed.

    A group only counts as nesting when it actually changes the evaluation
    order, so the test expression must contain an operator inside the parens.
    """
    from pypilot.expressions import MAX_NESTING

    for depth in range(1, MAX_NESTING + 1):
        state.evaluate("(" * depth + "1+1" + ")" * depth)
    with pytest.raises(ExpressionError, match="nested parentheses"):
        state.evaluate("(" * (MAX_NESTING + 1) + "1+1" + ")" * (MAX_NESTING + 1))


def test_redundant_parens_do_not_count_towards_the_limit(state: PilotState) -> None:
    """Spec 5.1.7 - "any number of redundant parens are allowed"."""
    from pypilot.expressions import MAX_NESTING

    deep = MAX_NESTING + 6
    state.evaluate("(" * deep + "1" + ")" * deep)


def test_memory_pointers_are_refused(state: PilotState) -> None:
    """Spec 10.5 - there is no Atari memory model to expose.

    The reference is still *parsed* correctly, so a real Atari program gets a
    clear diagnostic rather than a syntax error.
    """
    with pytest.raises(ExpressionError, match="pointer"):
        state.evaluate("*4096")
    with pytest.raises(ExpressionError, match="pointer"):
        state.evaluate("@B4096")


# ---------------------------------------------------------------------------
# Text and expressions together
# ---------------------------------------------------------------------------


def test_expansion_and_evaluation_agree_on_a_variable(state: PilotState) -> None:
    """The same variable read as text and as a number must be consistent."""
    state.set_number("A", 7)
    assert state.expand("#A") == "7"
    assert state.evaluate("#A").value == 7


def test_string_variable_in_an_expression_is_not_a_number(state: PilotState) -> None:
    """A `$` name is not a numeric entity; the error should say so clearly."""
    state.set_string("NAME", "ada")
    with pytest.raises(ExpressionError):
        state.evaluate(f"{D}NAME")
