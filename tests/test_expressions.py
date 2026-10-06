"""Tests for the ATARI PILOT numeric-expression evaluator.

Covers ``SPEC.md`` section 6.2 and Atari spec 5.1.7. Two of this language's
properties are the opposite of what most languages do, and both are pinned
here from several angles:

* **There is no operator precedence.** Evaluation is strictly left to right, so
  ``1+2*3`` is ``9``. A test written with conventional-precedence expectations
  would be wrong, and a program that relies on precedence would compute the
  wrong answer silently.
* **The remainder is always positive.** ``-7\\3`` is ``1``, not ``-1``.
"""

from __future__ import annotations

import pytest

from pypilot.expressions import MAX_NESTING, ExpressionError, evaluate, is_expression

D = "$"
H = "#"


def value(text: str, /, **numbers: int) -> int:
    """Evaluate ``text`` with the given ``#A``-``#Z`` bindings.

    Names are given as lowercase keywords (``value("#A", a=2)``) and matched
    case-insensitively, which is how a single-letter variable is written in a
    program anyway.
    """
    table = {name.upper(): int(number) for name, number in numbers.items()}
    return evaluate(text, get_number=lambda n: table.get(n.upper(), 0)).value


# ---------------------------------------------------------------------------
# The spec's own worked examples (5.1.7)
# ---------------------------------------------------------------------------


def test_spec_example_variable_plus_constant() -> None:
    assert value(f"{H}A + 4", a=2) == 6


def test_spec_example_redundant_parens() -> None:
    """Spec 5.1.7 - "Any number of redundant parens are allowed"."""
    assert evaluate("((((7))))").value == 7


def test_spec_example_nested_arithmetic() -> None:
    assert value(f"1+(2/({H}J/6))", j=6) == 3


def test_spec_example_sum() -> None:
    assert evaluate("1+2+3+4+5+6+7+8+9").value == 45


def test_spec_example_sum_in_parens() -> None:
    assert evaluate("(1+2+3+4+5+6+7+8+9)").value == 45


def test_spec_example_unary_minus() -> None:
    assert value(f"{H}J/-3", j=6) == -2


def test_spec_example_relational() -> None:
    assert value(f"{H}V<3", v=5) == 0


def test_spec_example_logical_and() -> None:
    """``(#A<3) * (#B=#C)`` is a logical and, written with arithmetic."""
    assert value(f"({H}A<3) * ({H}B={H}C)", a=2, b=3, c=3) == 1
    assert value(f"({H}A<3) * ({H}B={H}C)", a=9, b=3, c=3) == 0


def test_spec_example_logical_or() -> None:
    assert value(f"({H}D<>5) + ({H}C/3=1)", d=5, c=3) == 1


# ---------------------------------------------------------------------------
# No operator precedence - the correction that matters most
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Each expectation is the strict left-to-right result. Where
        # conventional precedence would differ, the comment says so.
        ("1+2*3", 9),  # conventional precedence would give 7
        ("2*3+4*5", 50),  # 6, +4=10, *5=50
        ("10-2-3", 5),  # 8-3; conventional would also be 5
        ("100/10/2", 5),  # 10, then 5
        ("2+3*4-6/2", 7),  # 5, *4=20, -6=14, /2=7
    ],
)
def test_evaluation_is_left_to_right_with_no_precedence(text: str, expected: int) -> None:
    """Spec 5.1.7 - "no operator precedence rules".

    Each expectation is the strict left-to-right result. If this test ever
    fails, someone has reintroduced conventional precedence.
    """
    assert evaluate(text).value == expected


def test_left_to_right_differs_from_conventional_precedence() -> None:
    """The clearest single demonstration of the rule."""
    # Conventional precedence would make this 7.
    assert evaluate("1+2*3").value == 9
    # Parentheses are the only way to change the grouping.
    assert evaluate("(1+2)*3").value == 9
    assert evaluate("1+(2*3)").value == 7


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("7+3", 10),
        ("7-3", 4),
        ("7*3", 21),
        ("7/3", 2),  # truncates
        ("7\\3", 1),
        ("-7/3", -2),  # toward zero, not floor
        ("-7\\3", 1),  # always positive
        ("7/-3", -2),
        ("-7/-3", 2),
        ("5\\4", 1),
        ("99\\12", 3),
        ("10\\5", 0),
    ],
)
def test_arithmetic(text: str, expected: int) -> None:
    assert evaluate(text).value == expected


def test_wrap_at_16_bits() -> None:
    """Spec 6.2 - overflow is silent."""
    assert evaluate("32767+1").value == -32768
    assert evaluate("-32768-1").value == 32767
    assert evaluate("10000*4").value == -25536


def test_constants_truncate_on_entry() -> None:
    """Spec 5.1.1 - a constant is truncated to 16 bits."""
    assert evaluate("40000").value == -25536
    assert evaluate("65536").value == 0


@pytest.mark.parametrize("text", ["1/0", "5/0", "1\\0"])
def test_division_and_modulo_by_zero_raise(text: str) -> None:
    with pytest.raises(ExpressionError, match="zero"):
        evaluate(text)


# ---------------------------------------------------------------------------
# Relational operators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5=5", 1),
        ("5=4", 0),
        ("5<>5", 0),
        ("5<>4", 1),
        ("5>4", 1),
        ("5>5", 0),
        ("4>5", 0),
        ("5>=5", 1),
        ("4>=5", 0),
        ("4<5", 1),
        ("5<5", 0),
        ("5<4", 0),
        ("4<=4", 1),
        ("5<=4", 0),
    ],
)
def test_relational_operators_yield_one_or_zero(text: str, expected: int) -> None:
    """Spec 5.1.7 - a relation is 1 for true, 0 for false."""
    assert evaluate(text).value == expected


def test_two_character_operators_are_not_split() -> None:
    """`<=` must be one operator, not `<` then `=`."""
    assert evaluate("4<=4").value == 1
    assert evaluate("4>=4").value == 1
    assert evaluate("4<>5").value == 1


# ---------------------------------------------------------------------------
# Parentheses and nesting (5.1.7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["1", "(1)", "((1))", "((((1))))", "(((((1)))))"],
)
def test_redundant_parens_nest_arbitrarily(text: str) -> None:
    """Spec 5.1.7 - "any number of redundant parens are allowed"."""
    assert evaluate(text).value == 1


def test_nesting_limit_is_enforced_for_non_redundant_parens() -> None:
    """Spec 5.1.7 - at most two levels of *non-redundant* nesting."""
    assert evaluate("1+2").value == 3
    assert evaluate("(1+2)").value == 3
    assert evaluate("((1+2))").value == 3
    with pytest.raises(ExpressionError, match="nested parentheses"):
        value(f"((({H}A+2)))", a=1)


def test_sibling_parens_are_not_nested() -> None:
    """`((1+2)+(3+4))` is two groups side by side, not nested three deep."""
    assert evaluate("((1+2)+(3+4))").value == 10


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_redundant_parens_do_not_count_toward_the_limit(depth: int) -> None:
    """Wrapping a variable in any number of redundant parens stays legal.

    Spec 5.1.7 allows "any number of redundant parens"; only parens that change
    the evaluation order count against the two-level limit.
    """
    text = "(" * depth + f"{H}A" + ")" * depth + "+1"
    assert value(text, a=2) == 3


# ---------------------------------------------------------------------------
# Operands
# ---------------------------------------------------------------------------


def test_numeric_variable_defaults_to_zero() -> None:
    """An unset numeric variable is 0 (spec 5.1.2)."""
    assert value(f"{H}A") == 0


def test_two_letter_numeric_name_is_rejected() -> None:
    """Spec 5.1.2 - only #A-#Z exist."""
    with pytest.raises(ExpressionError, match="only #A-#Z"):
        evaluate(f"{H}AB")


def test_string_variable_in_a_numeric_expression_is_rejected() -> None:
    with pytest.raises(ExpressionError, match="string variable"):
        evaluate(f"{D}NAME")


def test_random_is_usable_anywhere_a_constant_is() -> None:
    """Spec 5.1.3 - `?` is a random number."""
    assert evaluate("?+1", random_value=lambda: 41).value == 42
    assert evaluate("?*2", random_value=lambda: 21).value == 42


def test_special_variable() -> None:
    assert evaluate(f"{'%'}M", get_special=lambda name: 3).value == 3


def test_controller_sense_reads_as_zero() -> None:
    """Spec 10.5 - no hardware, so every sense reports "no input"."""
    assert evaluate(f"{'%'}J0").value == 0
    assert evaluate(f"{'%'}P3").value == 0


def test_controller_sense_passes_prefix_and_constant_index() -> None:
    seen: list[tuple[str, str]] = []

    def read_controller(prefix: str, index: str) -> int:
        seen.append((prefix, index))
        return 9

    value = evaluate(
        "%J1",
        get_controller=read_controller,
    )

    assert value.value == 9
    assert seen == [("J", "1")]


def test_controller_sense_evaluates_numeric_variable_index() -> None:
    seen: list[tuple[str, str]] = []

    def read_controller(prefix: str, index: str) -> int:
        seen.append((prefix, index))
        return 227

    value = evaluate(
        "%P#A",
        get_number=lambda name: 3 if name == "A" else 0,
        get_controller=read_controller,
    )

    assert value.value == 227
    assert seen == [("P", "3")]


def test_unknown_percent_name_reads_as_zero() -> None:
    assert evaluate(f"{'%'}Q").value == 0


def test_unary_minus_at_the_start() -> None:
    assert evaluate("-5").value == -5
    assert evaluate("--5").value == 5


# ---------------------------------------------------------------------------
# Pointers (5.1.6) - parsed, then refused (10.5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["*4096", "@B4096", "1+*4096", "(*4096)"])
def test_memory_pointers_are_refused(text: str) -> None:
    """Spec 10.5 - no Atari memory model, so decline rather than fake one."""
    with pytest.raises(ExpressionError):
        evaluate(text)


def test_asterisk_is_multiplication_when_not_a_pointer() -> None:
    """`*` is only a pointer where an operand is expected (spec 5.1.6)."""
    assert evaluate("2*3").value == 6
    assert evaluate("2*3*4").value == 24


def test_pointer_without_an_address_is_an_error() -> None:
    with pytest.raises(ExpressionError, match="address"):
        evaluate("*")


# ---------------------------------------------------------------------------
# Malformed expressions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["((1+2)", "1+2)", "()", "1+", "*", "1 $ 2", "abc"],
)
def test_malformed_expressions_raise(text: str) -> None:
    with pytest.raises(ExpressionError):
        evaluate(text)


def test_empty_expression_is_zero() -> None:
    assert evaluate("").value == 0
    assert evaluate("   ").value == 0


def test_expression_error_is_a_pilot_runtime_error() -> None:
    """So a host can catch it with the rest of the interpreter's errors."""
    from pypilot.errors import PilotRuntimeError

    assert issubclass(ExpressionError, PilotRuntimeError)


# ---------------------------------------------------------------------------
# is_expression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["1+2", "1+2*3", "3-1", "#A>2"])
def test_is_expression_detects_expressions(text: str) -> None:
    assert is_expression(text)


@pytest.mark.parametrize("text", ["#A", "$NAME", "", "5"])
def test_is_expression_rejects_plain_operands(text: str) -> None:
    assert not is_expression(text)


def test_max_nesting_is_two() -> None:
    assert MAX_NESTING == 2
