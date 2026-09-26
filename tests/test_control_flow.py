"""Tests for the control-flow statements: `J:`, `JM:`, `U:` and `E:` (Stage 6).

These four commands are what turn the language from a calculator into a
programmable one, and each has an ATARI-specific rule that is easy to get
wrong from Core PILOT intuition:

* `J:` takes a **single** label, not a list (spec 6.1.7).
* `JM:` is **positional** against the match ordinal, and *falls through*
  rather than erroring when the ordinal runs off the end (spec 6.1.8).
* `U:` nests to **8**, the Atari's own limit, not a host-sized number
  (spec 6.1.9).
* `E:` is **one statement with two outcomes** - return from a module, or end
  the program - chosen by whether the use stack is empty (spec 6.1.10).
"""

from __future__ import annotations

from typing import Any

import pytest

from pypilot.errors import PilotRuntimeError, PilotSyntaxError
from pypilot.match import split_jump_labels
from pypilot.state import MAX_MODULE_DEPTH

# ---------------------------------------------------------------------------
# 6.1.7 J: - Jump
# ---------------------------------------------------------------------------


def test_j_continues_at_the_label(run: Any) -> None:
    output, _, _ = run("T:A\nJ:*B\nT:SKIPPED\n*B\nT:B\nE:")
    assert output == "A\nB\n", "J: must skip the statement between them"


def test_j_may_be_conditional(run: Any) -> None:
    """Spec 6.1.7 - "This command, as all others, may be conditional"."""
    output, _, _ = run("C:#I=0\n*I\nC:#I=#I+1\nJ(#I<3):*I\nT:DONE AT #I\nE:")
    assert output == "DONE AT 3\n"


def test_a_false_condition_falls_through(run: Any) -> None:
    output, _, _ = run("C:#I=0\n*I\nJ(#I<0):*I\nT:PAST\nE:")
    assert output == "PAST\n"


def test_j_accepts_a_label_with_or_without_the_star(run: Any) -> None:
    """Spec 10.2 - the leading `*` is optional in the operand."""
    with_star, _, _ = run("J:*L\nT:NO\n*L\nT:HIT\nE:")
    without, _, _ = run("J:L\nT:NO\n*L\nT:HIT\nE:")
    assert with_star == without == "HIT\n"


def test_a_duplicate_label_jumps_to_the_lowest_line_number(run: Any) -> None:
    """Spec 6.1.7 - "the one with the lowest line number will be the target"."""
    output, _, _ = run("J:*D\n*D\nT:FIRST\nE:\n*D\nT:SECOND\nT:NEVER")
    assert output == "FIRST\n"


def test_an_undefined_label_names_the_line(run: Any) -> None:
    with pytest.raises(PilotRuntimeError) as excinfo:
        run("T:A\nJ:*NOWHERE\nE:")
    err = str(excinfo.value)
    assert "NOWHERE" in err
    assert excinfo.value.line == 2, "the error must say which line jumped"


def test_j_does_not_touch_the_use_stack(run: Any) -> None:
    """Jumping out of a module is legal; the stack is left alone."""
    output, _, _ = run("U:*S\nT:BACK\nE:\n*S\nJ:*OUT\nT:SKIPPED\n*OUT\nE:")
    assert output == "BACK\n", "E: after the jump returns to just past the U:"


# ---------------------------------------------------------------------------
# 6.1.8 JM: - Jump on Match
# ---------------------------------------------------------------------------


def test_jm_branches_on_the_ordinal(run: Any) -> None:
    source = "\n".join(
        [
            "A:=YES",
            "M:YES,NO,MAYBE",
            "JM:*ONE,*TWO,*THREE",
            "T:FELL THROUGH",
            "J:*END",
            "*ONE",
            "T:FIELD ONE",
            "J:*END",
            "*TWO",
            "T:FIELD TWO",
            "J:*END",
            "*THREE",
            "T:FIELD THREE",
            "*END",
            "E:",
        ]
    )
    assert "FIELD ONE" in run(source)[0]
    assert "FIELD THREE" in run(source.replace("A:=YES", "A:=MAYBE"))[0]


def test_jm_does_not_jump_when_the_match_failed(run: Any) -> None:
    """Spec 6.1.8 - "If the prior Match was unsuccessful ... no jump"."""
    output, _, _ = run("A:=NOPE\nM:YES\nJM:*ONE,*TWO\nT:FELL THROUGH\nE:\n*TWO\nT:HIT")
    assert output == "FELL THROUGH\n"


def test_jm_falls_through_when_there_are_more_fields_than_labels(run: Any) -> None:
    """Spec 6.1.8 - "or if there is no nth operand label, no jump".

    Erroring here would punish a program the Atari accepts, so this is a
    fall-through and must be pinned.
    """
    source = "A:=MAYBE\nM:YES,NO,MAYBE\nJM:*ONE,*TWO\nT:FELL THROUGH\nE:\n*TWO\nT:HIT"
    output, _, _ = run(source)
    assert output == "FELL THROUGH\n"


def test_jm_uses_only_the_nth_label(run: Any) -> None:
    """A two-way match with a three-label list must take label 2, not 3."""
    source = "A:=NO\nM:YES,NO\nJM:*ONE,*TWO,*THREE\nT:FELL THROUGH\nE:\n*TWO\nT:HIT"
    output, _, _ = run(source)
    assert output == "HIT\n"


def test_jm_with_a_null_operand_is_a_no_op(run: Any) -> None:
    output, _, _ = run("A:=YES\nM:YES\nJM:\nT:FELL THROUGH\nE:")
    assert output == "FELL THROUGH\n"


def test_jm_accepts_blanks_as_separators(run: Any) -> None:
    """Spec 4.5 - a run of commas/blanks is ONE separator, outside `M:`.

    This is the opposite of the `M:` rule, where blanks are significant data.
    Both spellings in the spec's own examples must give the same branch.
    """
    spaced = "A:=NO\nM:YES,NO\nJM:*ONE *TWO *THREE\nT:FELL\nE:\n*TWO\nT:HIT"
    commas = "A:=NO\nM:YES,NO\nJM : *ONE , *TWO , *THREE\nT:FELL\nE:\n*TWO\nT:HIT"
    run_of_mixed = "A:=NO\nM:YES,NO\nJM:*ONE ,,  *TWO ,,*THREE\nT:FELL\nE:\n*TWO\nT:HIT"
    assert run(spaced)[0] == run(commas)[0] == run(run_of_mixed)[0] == "HIT\n"


def test_jm_with_an_undefined_label_names_the_line(run: Any) -> None:
    with pytest.raises(PilotRuntimeError) as excinfo:
        run("A:=YES\nM:YES\nJM:*GONE\nE:")
    assert "GONE" in str(excinfo.value)
    assert excinfo.value.line == 3


# ---------------------------------------------------------------------------
# 6.1.8 operand grammar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("operand", "expected"),
    [
        ("*L1 *L2 *L3", ["*L1", "*L2", "*L3"]),
        ("*HERE , *THERE , *EVERYWHERE", ["*HERE", "*THERE", "*EVERYWHERE"]),
        ("*A,*B", ["*A", "*B"]),
        ("  *A  ,,  *B  ", ["*A", "*B"]),
        ("*ONLY", ["*ONLY"]),
        ("", []),
        ("   ", []),
        (",,,", []),
    ],
)
def test_split_jump_labels(operand: str, expected: list[str]) -> None:
    assert split_jump_labels(operand) == expected


def test_split_jump_labels_keeps_the_star_for_resolution() -> None:
    """The `*` is stripped per-label at resolve time, so it is kept here."""
    assert split_jump_labels("*LOOP") == ["*LOOP"]


# ---------------------------------------------------------------------------
# 6.1.9 / 6.1.10 U: and E: - modules
# ---------------------------------------------------------------------------


def test_u_calls_a_module_and_e_returns(run: Any) -> None:
    output, _, _ = run("T:BEFORE\nU:*S\nT:AFTER\nE:\n*S\nT:INSIDE\nE:\nT:NEVER")
    assert output == "BEFORE\nINSIDE\nAFTER\n"


def test_a_module_may_call_another_module(run: Any) -> None:
    output, _, _ = run("U:*OUTER\nT:END\nE:\n*OUTER\nT:OUTER\nU:*INNER\nE:\n*INNER\nT:INNER\nE:")
    assert output == "OUTER\nINNER\nEND\n"


def test_u_takes_no_arguments(run: Any) -> None:
    """Spec 6.1.9 - the operand is a bare label; modules share variables only."""
    output, _, _ = run("C:#A=7\nU:*S\nE:\n*S\nT:#A\nE:")
    assert output == "7\n"


def test_recursion_terminates_and_counts(run: Any) -> None:
    output, state, _ = run("C:#N=0\nU:*R\nE:\n*R\nC:#N=#N+1\nJ(#N<3):*R\nE:")
    assert state.get_number("N").value == 3
    assert output == ""


def test_module_depth_is_capped_at_the_atari_limit() -> None:
    """Spec 6.1.9 - "Up to eight (8) Uses may be nested"."""
    assert MAX_MODULE_DEPTH == 8, "this is the Atari's limit, not a host-sized number"


def test_nesting_past_the_limit_raises_rather_than_crashing(run: Any) -> None:
    with pytest.raises(PilotRuntimeError, match="nesting exceeded 8"):
        run("U:*S\nE:\n*S\nU:*S\nE:")


def test_nesting_just_within_the_limit_is_allowed(run: Any) -> None:
    """8 deep must work - the cap is 8, not 7, and off-by-one here is silent."""
    body = "E:"
    for _ in range(MAX_MODULE_DEPTH):
        body = f"U:*S\n{body}\n*S\nE:"
    output, _, _ = run(body)
    assert output == ""


def test_e_ends_the_program_when_the_use_stack_is_empty(run: Any) -> None:
    output, _, _ = run("T:A\nE:\nT:NEVER")
    assert output == "A\n"


def test_e_returns_to_the_most_recent_use(run: Any) -> None:
    output, _, _ = run("U:*A\nT:BOTTOM\nE:\n*A\nU:*B\nE:\n*B\nT:MIDDLE\nE:")
    assert output == "MIDDLE\nBOTTOM\n", "each E: returns to just past its own U:"


def test_e_is_conditional(run: Any) -> None:
    """Spec 6.1.10 - "This command, as all others, may be conditional".

    `E:` takes a condition but never an operand, so whatever text the caller
    wants printed has to be a separate statement - and that statement runs
    whether or not the `E:` fired. What the condition changes is whether the
    *program ends* there.
    """
    output, _, _ = run("C:#A=1\nE(#A>0):\nT:NEVER REACHED\nE:\nT:TOP")
    assert output == "", "a true E: ends the program outright - nothing after it runs"

    output, _, _ = run("C:#A=0\nE(#A>0):\nT:FELL THROUGH\nE:\nT:TOP")
    assert output == "FELL THROUGH\n", "a false E: falls through; the bare E: then ends it"


def test_e_ey_and_en_are_legal_spellings(run: Any) -> None:
    """Spec 6.1.10 gives `EY:` and `EN:` as its own examples.

    `EY:` ends the program when the last match succeeded, `EN:` when it did
    not. `A:=NOPE` sets the buffer to ` NOPE `, which does **not** contain
    `YES`, so the match fails and `EN:` is the one that fires.
    """
    output, _, _ = run("A:=YES\nM:YES\nEY:\nT:NEVER\nT:NEVER EITHER")
    assert output == "", "EY: ends the program after a successful match"

    output, _, _ = run("A:=NOPE\nM:YES\nEN:\nT:NEVER\nT:NEVER EITHER")
    assert output == "", "EN: ends the program after a failed match"


def test_e_skipped_by_its_condition_keeps_running(run: Any) -> None:
    """The other side of the pair: a skipped `E:` does not end anything.

    Note the trailing `T:TOP` never appears, because the bare `E:` after it
    finds an empty use stack and ends the program - which is the spec's rule,
    not a bug. The point of the test is that `T:KEPT GOING` *did* run, i.e.
    the skipped `EN:` did not consume it.
    """
    output, _, _ = run("A:=YES\nM:YES\nEN:\nT:KEPT GOING\nE:\nT:TOP")
    assert output == "KEPT GOING\n", "EN: was skipped, so the statement after it ran"


def test_e_still_rejects_an_operand(run: Any) -> None:
    """`<end operand> :: = <null>` (spec 6.1.10) - a condition is not an operand."""
    with pytest.raises(PilotSyntaxError, match="takes no operand"):
        run("E(#A>0):TEXT")


def test_the_module_returns_when_e_is_conditional_and_false(run: Any) -> None:
    """A false `E:` inside a module does not return - the module runs on."""
    output, _, _ = run("C:#A=0\nU:*S\nE:\n*S\nE(#A>0):\nT:STILL INSIDE\nE:")
    assert output == "STILL INSIDE\n"


# ---------------------------------------------------------------------------
# Runaway programs
# ---------------------------------------------------------------------------


def test_a_runaway_jump_loop_is_reported_not_hung(run: Any) -> None:
    """`J:` makes an infinite loop a one-character slip; a hang teaches nothing."""
    with pytest.raises(PilotRuntimeError, match="without finishing"):
        run("*LOOP\nJ:*LOOP")


def test_the_step_limit_is_configurable() -> None:
    from pypilot.io import BufferOutput, StringInput
    from pypilot.runtime import Interpreter
    from pypilot.syntax import parse

    interpreter = Interpreter(
        parse("*LOOP\nJ:*LOOP\n"), output=BufferOutput(), source=StringInput([]), max_steps=10
    )
    with pytest.raises(PilotRuntimeError, match="limit 10"):
        interpreter.run()
    # The counter is incremented before the check, so it reads 11 on the
    # statement that trips the limit - the reported total is the limit plus one.
    assert interpreter.steps == 11
