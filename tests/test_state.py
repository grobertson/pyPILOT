"""Tests for interpreter state.

Covers ``SPEC.md`` section 6.1 (variables, and the undefined/null
distinction), 6.3 (random), 6.5 (text expansion against state), 6.6 (the match
ordinal), 7.1 (the accept buffer) and 8.3 (module depth).

The undefined-variable rule is the one to watch: an undefined string prints as
**its own name**, which is the opposite of what every other PILOT dialect does.
A test written from Core PILOT intuition would get it backwards, so it is
pinned from several angles.
"""

from __future__ import annotations

import pytest

from pypilot.errors import PilotRuntimeError
from pypilot.state import MAX_MODULE_DEPTH, MatchResult, PilotState, normalise_accept
from pypilot.values import MAX_STRING_LENGTH, Numeric

D = "$"


@pytest.fixture
def state() -> PilotState:
    return PilotState()


# ---------------------------------------------------------------------------
# 6.1 Numeric variables
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["A", "B", "M", "Z"])
def test_every_single_letter_is_a_valid_numeric_name(state: PilotState, name: str) -> None:
    """Spec 5.1.2 - there are 26 numeric variables, #A through #Z."""
    assert state.is_numeric_name(name)
    state.set_number(name, 5)
    assert state.get_number(name).value == 5


@pytest.mark.parametrize("name", ["XY", "A1", "", "1", "#A", "AA"])
def test_multi_letter_numeric_names_are_invalid(state: PilotState, name: str) -> None:
    """Spec 5.1.2 - a longer name is a Core PILOT habit, not ATARI."""
    assert not state.is_numeric_name(name)
    with pytest.raises(PilotRuntimeError, match="only #A-#Z"):
        state.get_number(name)


def test_unset_numeric_reads_as_zero_not_an_error(state: PilotState) -> None:
    """Spec 5.1.2 - an unassigned numeric variable is 0."""
    assert state.get_number("Q").value == 0


def test_numeric_assignment_wraps(state: PilotState) -> None:
    state.set_number("A", 32768)
    assert state.get_number("A").value == -32768
    state.set_number("A", Numeric(40000))
    assert state.get_number("A").value == -25536


def test_numeric_names_are_case_insensitive(state: PilotState) -> None:
    """The name is a single letter, so case cannot distinguish two variables."""
    state.set_number("a", 3)
    assert state.get_number("A").value == 3


# ---------------------------------------------------------------------------
# 6.1 String variables, and undefined vs null
# ---------------------------------------------------------------------------


def test_undefined_and_null_are_different_states(state: PilotState) -> None:
    """Spec 6.1 - a null string is not the same as an undefined one."""
    assert not state.is_defined("A")
    assert state.get_string("A") is None

    state.set_string("A", "")
    assert state.is_defined("A")
    assert state.get_string("A") == ""


def test_undefined_expands_to_its_own_name(state: PilotState) -> None:
    """Spec 6.1 - the rule that is the opposite of every other dialect."""
    assert state.expand(f"[{D}UNSET]") == "[UNSET]"


def test_null_expands_to_nothing(state: PilotState) -> None:
    state.set_string("EMPTY", "")
    assert state.expand(f"[{D}EMPTY]") == "[]"


def test_defined_expands_to_its_value(state: PilotState) -> None:
    state.set_string("NAME", "ada")
    assert state.expand(f"HELLO {D}NAME") == "HELLO ada"


def test_string_names_are_case_sensitive(state: PilotState) -> None:
    """Spec 5.2.2 - ATARI does not fold case in variable names."""
    state.set_string("Name", "upper")
    state.set_string("name", "lower")
    assert state.get_string("Name") == "upper"
    assert state.get_string("name") == "lower"


def test_string_data_truncates_at_254(state: PilotState) -> None:
    """Spec 5.2.2 - string data is capped."""
    state.set_string("BIG", "X" * 400)
    assert len(state.get_string("BIG") or "") == MAX_STRING_LENGTH


def test_string_name_length_limit(state: PilotState) -> None:
    with pytest.raises(PilotRuntimeError, match="exceeds 254 characters"):
        state.set_string("N" * 300, "x")


def test_empty_string_name_is_rejected(state: PilotState) -> None:
    with pytest.raises(PilotRuntimeError, match="cannot be empty"):
        state.set_string("", "x")


# ---------------------------------------------------------------------------
# 6.4 / 5.2.4 String indirection
# ---------------------------------------------------------------------------


@pytest.fixture
def ladder(state: PilotState) -> PilotState:
    """The Atari spec's own indirection example (spec 5.2.4).

    ``$LADDER`` holds ``JANE``, ``$JANE`` holds ``ATARI``, ``$ATARI`` holds
    ``LUNCH``, so one ``$`` gives ``JANE``, two give ``ATARI``, three give
    ``LUNCH``.
    """
    state.set_string("LADDER", "JANE")
    state.set_string("JANE", "ATARI")
    state.set_string("ATARI", "LUNCH")
    return state


@pytest.mark.parametrize(
    ("dollars", "expected"),
    [(1, "JANE"), (2, "ATARI"), (3, "LUNCH")],
)
def test_indirection_follows_the_specs_worked_example(
    ladder: PilotState, dollars: int, expected: str
) -> None:
    assert ladder.expand(f"{D * dollars}LADDER") == expected


def test_indirection_that_cannot_be_carried_yields_the_name(ladder: PilotState) -> None:
    """Spec 5.2.4 - a failed indirection behaves like an undefined name."""
    assert ladder.expand(f"{D * 6}LADDER") == "LADDER"


def test_single_dollar_is_not_indirection(state: PilotState) -> None:
    """One ``$`` is a plain reference - the spec's ``T:$LADDER`` case."""
    state.set_string("A", "B")
    state.set_string("B", "C")
    assert state.expand(f"{D}A") == "B"


# ---------------------------------------------------------------------------
# 6.5 Expansion against state
# ---------------------------------------------------------------------------


def test_expansion_is_single_pass_against_state(state: PilotState) -> None:
    """Spec 6.5 - a variable holding a sigil is not re-scanned."""
    state.set_string("SELF", f"{D}OTHER")
    state.set_string("OTHER", "NOPE")
    assert state.expand(f"{D}SELF") == f"{D}OTHER"


def test_expansion_mixes_literals_and_references(state: PilotState) -> None:
    state.set_string("NAME", "ada")
    state.set_number("A", 7)
    assert state.expand(f"HELLO {D}NAME YOU ARE #A") == "HELLO ada YOU ARE 7"


def test_expansion_of_an_empty_expression(state: PilotState) -> None:
    assert state.expand("") == ""


def test_expansion_respects_a_limit(state: PilotState) -> None:
    assert len(state.expand("X" * 400, limit=10)) == 10


# ---------------------------------------------------------------------------
# 6.3 Random numbers
# ---------------------------------------------------------------------------


def test_seeded_random_is_reproducible() -> None:
    """Spec 6.3 - ``?`` must be seedable for testability."""
    assert PilotState(random_seed=7).next_random() == PilotState(random_seed=7).next_random()


def test_seed_random_restarts_the_sequence(state: PilotState) -> None:
    state.seed_random(3)
    first = state.next_random()
    state.seed_random(3)
    assert state.next_random() == first


def test_random_is_in_16_bit_range(state: PilotState) -> None:
    for _ in range(50):
        assert -32768 <= state.next_random() <= 32767


def test_question_mark_in_text_is_literal() -> None:
    """Spec 5.2.1 - `?` is not in the literal-exclusion list, so it is text.

    This is a regression guard. `?` used to draw a random number here, which
    silently corrupted the accept buffer for the spec's §6.1.4 worked example
    `A:=WHAT WILL HAPPEN?`. `?` remains available in `nexp` (spec 5.1.3).
    """
    state = PilotState(random_seed=11)
    assert state.expand("N=?") == "N=?"


def test_text_expansion_does_not_disturb_the_random_sequence() -> None:
    """A text operand containing `?` must not consume a random draw."""
    a = PilotState(random_seed=5)
    a.expand("WHAT WILL HAPPEN?")
    b = PilotState(random_seed=5)
    assert a.next_random() == b.next_random()


# ---------------------------------------------------------------------------
# 7.1 / 7.2.2 The accept buffer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("yes", " YES "),
        ("  yes  ", " YES "),  # collapsed, then padded
        ("a   b", " A B "),  # a run of spaces collapses to one
        ("MiXeD", " MIXED "),  # lower case is converted
        ("", "  "),  # an empty line is two spaces
    ],
)
def test_accept_buffer_normalisation(raw: str, expected: str) -> None:
    """Spec 7.2.2 - the five-step transformation, in order."""
    assert normalise_accept(raw) == expected


def test_accept_buffer_truncates_at_254() -> None:
    assert len(normalise_accept("X" * 400)) == MAX_STRING_LENGTH


def test_set_accept_stores_the_normalised_form(state: PilotState) -> None:
    assert state.set_accept("yes") == " YES "
    assert state.accept_buffer == " YES "


def test_clear_accept(state: PilotState) -> None:
    state.set_accept("yes")
    state.clear_accept()
    assert state.accept_buffer == ""


# ---------------------------------------------------------------------------
# 6.6 The match ordinal
# ---------------------------------------------------------------------------


def test_match_ordinal_is_the_field_number(state: PilotState) -> None:
    """Spec 6.1.3 - the flag is a 1-based ordinal, not a boolean."""
    state.record_match(3)
    assert state.match.ordinal == 3
    assert state.match.matched


def test_no_match_is_ordinal_zero(state: PilotState) -> None:
    state.record_no_match()
    assert state.match.ordinal == 0
    assert not state.match.matched


def test_failed_ms_retains_the_split_strings(state: PilotState) -> None:
    """Spec 6.1.4 - a failed `MS:` leaves $LEFT/$MATCH/$RIGHT untouched."""
    state.record_match(1)
    state.set_match_parts("LEFT", "MID", "RIGHT")
    state.record_no_match()
    assert (state.match.left, state.match.match, state.match.right) == ("LEFT", "MID", "RIGHT")
    assert state.match.ordinal == 0


def test_default_match_result_is_ordinal_zero() -> None:
    assert MatchResult() == MatchResult(ordinal=0, matched=False)


# ---------------------------------------------------------------------------
# 8.3 Module depth
# ---------------------------------------------------------------------------


def test_module_push_and_pop(state: PilotState) -> None:
    state.push_module(10)
    state.push_module(20)
    assert len(state.call_stack) == 2
    assert state.pop_module() == 20
    assert state.pop_module() == 10
    assert not state.in_module()


def test_module_depth_limit_raises(state: PilotState) -> None:
    """Spec 8.3 - a PILOT error, not a Python RecursionError."""
    for address in range(MAX_MODULE_DEPTH):
        state.push_module(address)
    assert state.max_module_depth == MAX_MODULE_DEPTH
    with pytest.raises(PilotRuntimeError, match="nesting exceeded"):
        state.push_module(0)


def test_pop_with_no_module_raises(state: PilotState) -> None:
    with pytest.raises(PilotRuntimeError, match="no module to return from"):
        state.pop_module()


# ---------------------------------------------------------------------------
# VNEW and reset (9.5, 8.5)
# ---------------------------------------------------------------------------


def test_vnew_clears_both_stores(state: PilotState) -> None:
    state.set_string("A", "x")
    state.set_number("A", 1)
    state.clear_variables()
    assert state.strings == {}
    assert state.numbers == {}


def test_vnew_can_clear_one_store(state: PilotState) -> None:
    state.set_string("A", "x")
    state.set_number("A", 1)
    state.clear_variables(strings=True, numbers=False)
    assert state.strings == {}
    assert state.numbers != {}


def test_reset_clears_everything(state: PilotState) -> None:
    """Spec 8.5 - a `LOAD:` discards state but keeps variables; a reset does not."""
    state.set_string("A", "x")
    state.set_accept("yes")
    state.record_match(2)
    state.push_module(5)
    state.reset()
    assert state.strings == {}
    assert state.accept_buffer == ""
    assert state.match.ordinal == 0
    assert state.call_stack == []


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_dump_strings_lists_sorted_names(state: PilotState) -> None:
    state.set_string("B", "two")
    state.set_string("A", "one")
    dumped = state.dump_strings()
    assert dumped.index("$A") < dumped.index("$B")
    assert "one" in dumped


def test_dump_with_nothing_defined(state: PilotState) -> None:
    assert "no string variables" in state.dump_strings()
    assert "no numeric variables" in state.dump_numbers()


def test_dump_numbers(state: PilotState) -> None:
    state.set_number("B", 2)
    state.set_number("A", 1)
    assert state.dump_numbers() == "#A=1 #B=2"
