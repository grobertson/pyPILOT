"""Tests for the interpreter: `T`, `R` and `C` (Stage 4).

Stage 4's acceptance criterion is that a program built from ``T``, ``R`` and
``C`` runs end to end, and that an undefined variable prints its own name.
Both are covered here, along with the condition rules of spec 4.4, the tracing
hook of spec 9.5, and the refusal paths of spec 10.4/10.7.

The runnable programs are written the way ATARI PILOT requires: single-letter
numeric variables, upper-case text where the accept buffer is involved, and
remembering that ``[`` is an unconditional comment delimiter (§4.5).
"""

from __future__ import annotations

from typing import Any

import pytest

from pypilot.errors import PilotRuntimeError, PilotUnsupportedError
from pypilot.runtime import Interpreter, TraceEvent
from pypilot.syntax import parse

D = "$"  # named so a shell heredoc cannot eat the sigil

# ---------------------------------------------------------------------------
# T — Type
# ---------------------------------------------------------------------------


def test_t_writes_its_operand(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("T:HELLO, WORLD!")
    assert output == "HELLO, WORLD!\n"


def test_t_with_an_empty_operand_writes_a_blank_line(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("T:ONE\nT:\nT:TWO")
    assert output == "ONE\n\nTWO\n"


def test_t_expands_a_string_variable(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run(f"C:{D}NAME=ADA\nT:HELLO, {D}NAME!")
    assert output == "HELLO, ADA!\n"


def test_t_expands_a_numeric_variable(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("C:#A=42\nT:THE ANSWER IS #A")
    assert output == "THE ANSWER IS 42\n"


def test_t_of_an_undefined_variable_prints_its_name(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 6.1 - the Stage 4 acceptance criterion, and the language's
    single most surprising rule. Note ``[`` cannot be used to show it, because
    it is the comment delimiter (§4.5), so a colon stands in."""
    output, _, _ = run(f"T:UNSET MEANS {D}UNSET")
    assert output == "UNSET MEANS UNSET\n"


def test_t_of_a_null_string_prints_nothing(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 6.1 - null is a distinct state from undefined.

    ``C:$E=`` assigns the empty string, so ``$E`` expands to nothing, whereas an
    undefined variable would expand to its own name (§6.1). The blank in
    ``$E |`` is a separator: without it the scanner would read ``$E|`` as one
    variable name.
    """
    output, _, _ = run(f"C:{D}E=\nT:EMPTY IS {D}E |")
    assert output.split("IS")[1].strip() == "|"
    assert "E" not in output.split("IS")[1].strip()


def test_t_does_not_rescan_expanded_text(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 6.5 - expansion is single-pass, so a value is emitted verbatim.

    ``$COPY`` holds the value of ``$TARGET``; emitting ``$COPY`` prints that
    value, not the *name* ``$TARGET``.
    """
    output, _, _ = run(f"C:{D}TARGET=FIRST\nC:{D}COPY={D}TARGET\nT:{D}COPY")
    assert output == "FIRST\n"


def test_expanded_text_containing_a_sigil_is_not_rescanned(run) -> None:  # type: ignore[no-untyped-def]
    """A variable's value is emitted verbatim, never rescanned (spec 6.5).

    Built with indirection rather than by writing a literal ``$`` - there is
    no escape for a sigil in ATARI PILOT (§6.4), so a literal ``$`` simply
    cannot be written inside an operand. ``$A`` holds ``B`` and ``$B`` holds a
    value; ``$$A`` therefore names ``$B``. If expansion were recursive this
    would resolve one level further than the spec allows.
    """
    output, _, _ = run(f"C:{D}A=B\nC:{D}B=RESOLVED\nT:$$A")
    assert output == "RESOLVED\n"


def test_t_expands_multiple_variables(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run(f"C:{D}A=ONE\nC:{D}B=TWO\nT:{D}A AND {D}B")
    assert output == "ONE AND TWO\n"


def test_t_repeats_for_each_statement(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("T:ONE\nT:TWO\nT:THREE")
    assert output.splitlines() == ["ONE", "TWO", "THREE"]


def test_continuation_repeats_the_previous_command(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 4.4 - ``:text`` continues the previous ``T``."""
    output, _, _ = run("T:ONE\n:TWO\n:THREE")
    assert output.splitlines() == ["ONE", "TWO", "THREE"]


def test_y_and_n_type_conditionally(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 6.1.1 - `Y:`/`N:` type only if the last match said so.

    Stage 4 has no `M:` yet, so the match flag is its initial state: no match has
    happened. That makes `N:` fire and `Y:` stay silent.
    """
    output, _, _ = run("Y:NEVER PRINTED\nN:PRINTED")
    assert output == "PRINTED\n"


def test_all_spellings_of_y_and_n_agree(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 6.1.1 - `Y` abbreviates `TY`; `YY`/`NY` are also type-if-match.

    The second letter is the condition, so `YN` and `NN` are type-if-no-match.
    """
    for spelling in ("Y", "TY", "YY", "NY"):
        output, _, _ = run(f"{spelling}:SHOULD NOT PRINT")
        assert output == "", f"{spelling}: printed when no match had succeeded"
    for spelling in ("N", "TN", "YN", "NN"):
        output, _, _ = run(f"{spelling}:PRINTED")
        assert output == "PRINTED\n", f"{spelling}: did not print"


# ---------------------------------------------------------------------------
# R — Remark
# ---------------------------------------------------------------------------


def test_r_produces_no_output(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("R:THIS IS ONLY A COMMENT\nT:VISIBLE")
    assert output == "VISIBLE\n"


def test_r_may_look_like_a_statement(run) -> None:  # type: ignore[no-untyped-def]
    """A remark is a remark whatever it says, including `T:`-shaped text."""
    output, _, _ = run("R:T:NOT REALLY\nT:REALLY")
    assert output == "REALLY\n"


def test_r_with_a_condition_is_skipped_or_not(run) -> None:  # type: ignore[no-untyped-def]
    """A remark is a remark, and its condition does not change that (spec 9.2)."""
    output, _, _ = run("R:NOTHING\nT:END")
    assert output == "END\n"


def test_r_may_be_conditional_on_an_expression(run) -> None:  # type: ignore[no-untyped-def]
    """A remark is a remark even when its condition is false (spec 9.2)."""
    output, _, _ = run("C:#A=1\nR(#A>99):NEVER MATTERED\nT:END")
    assert output == "END\n"


# ---------------------------------------------------------------------------
# C — Compute
# ---------------------------------------------------------------------------


def test_c_assigns_a_number(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("C:#A=7\nT:#A")
    assert output == "7\n"


def test_c_assigns_a_string(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run(f"C:{D}A=HELLO\nT:{D}A")
    assert output == "HELLO\n"


def test_c_computes_arithmetic(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("C:#A=2+3\nT:#A")
    assert output == "5\n"


def test_c_has_no_operator_precedence(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 5.1.7 - left to right, so this is 9 and not 7."""
    output, _, _ = run("C:#A=1+2*3\nT:#A")
    assert output == "9\n"


def test_c_truncating_division(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("C:#A=7/3\nT:#A")
    assert output == "2\n"


def test_c_modulo_with_a_backslash(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("C:#A=7\\3\nT:#A")
    assert output == "1\n"


def test_c_self_reference_is_well_defined(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 9.3 - the value is computed before it is stored."""
    output, _, _ = run("C:#A=1\nC:#A=#A+1\nC:#A=#A+1\nT:#A")
    assert output == "3\n"


def test_c_string_concatenation(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run(f"C:{D}A=HEL\nC:{D}B=LO\nC:{D}C={D}A {D}B\nT:{D}C")
    assert output == "HEL LO\n"


def test_c_expands_variables_in_the_value(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run(f"C:{D}NAME=ADA\nC:{D}GREET=HELLO, {D}NAME\nT:{D}GREET")
    assert output == "HELLO, ADA\n"


def test_c_wraps_at_16_bits_silently(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 6.2 - overflow is not an error."""
    output, _, _ = run("C:#A=32767\nC:#A=#A+1\nT:#A")
    assert output == "-32768\n"


def test_c_requires_an_equals_sign(run) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PilotRuntimeError, match="requires an assignment"):
        run("C:#A")


def test_c_rejects_an_unknown_target_sigil(run) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PilotRuntimeError, match="must assign to"):
        run("C:?A=1")


def test_c_rejects_a_multi_letter_numeric_target(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 5.1.2 - there is no ``#AVG``; only ``#A``-``#Z`` exist."""
    with pytest.raises(PilotRuntimeError, match="only #A-#Z"):
        run("C:#AVG=1+1")


def test_c_error_carries_the_line_and_source(run) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PilotRuntimeError) as excinfo:
        run("T:FINE\nC:#AVG=1")
    assert excinfo.value.line == 2
    assert excinfo.value.source is not None
    assert "C:#AVG=1" in excinfo.value.source


def test_c_evaluates_a_condition_error_with_the_line(run) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PilotRuntimeError) as excinfo:
        run("T:ONE\nT(#AVG>1):X")
    assert excinfo.value.line == 2


# ---------------------------------------------------------------------------
# Conditions (spec 4.4)
# ---------------------------------------------------------------------------


def test_a_true_expression_runs_the_statement(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("C:#A=5\nT(#A>3):YES")
    assert output == "YES\n"


def test_a_false_expression_skips_the_statement(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("C:#A=2\nT(#A>3):NO\nT:AFTER")
    assert output == "AFTER\n"


def test_the_expression_must_exceed_zero_not_merely_be_nonzero(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 4.4 - a negative value is false, not true.

    ``#A`` is -5, so neither the bare expression nor ``#A>0`` may fire.
    """
    output, _, _ = run("C:#A=0-5\nT(#A):NEGATIVE IS FALSE\nT(#A>0):ALSO FALSE")
    assert output == ""


def test_y_and_n_conditions_are_conjunctive(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 4.4 - with the match flag unset, ``N`` holds and ``Y`` does not.

    ``N(#A>0):`` therefore needs *both* to be true, and ``Y(#A>0):`` can never
    run, so only the first statement's text appears.
    """
    output, _, _ = run("C:#A=1\nN(#A>0):BOTH TRUE\nY(#A>0):Y DOES NOT HOLD")
    assert output == "BOTH TRUE\n"


def test_a_condition_with_no_match_flag_still_evaluates_the_expression(
    run: Any,
) -> None:
    output, _, _ = run("C:#A=9\nT(#A>5):YES")
    assert output == "YES\n"


def test_a_skipped_statement_does_not_advance_variables(run) -> None:  # type: ignore[no-untyped-def]
    output, state, _ = run("C:#A=1\nT(#A>9):C:#A=99\nT:#A")
    assert output == "1\n"
    assert state.get_number("A").value == 1


# ---------------------------------------------------------------------------
# Refusals and pending statements
# ---------------------------------------------------------------------------


def test_a_refused_command_raises_clearly(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 10.4 - `GR:` is real ATARI PILOT, so it must not look like a typo."""
    with pytest.raises(PilotUnsupportedError, match=r"10\.4"):
        run("GR:CLEAR")


def test_jump_reaches_a_label(run) -> None:  # type: ignore[no-untyped-def]
    """`J:` (spec 6.1.7) - control continues at the labelled statement."""
    output, _, _ = run("T:A\nJ:*B\nT:SKIPPED\n*B\nT:B\nE:")
    assert output == "A\nB\n"


def test_use_calls_a_module_and_e_returns_from_it(run) -> None:  # type: ignore[no-untyped-def]
    """`U:`/`E:` (spec 6.1.9, 6.1.10) - one rule, two outcomes."""
    output, _, _ = run("U:*S\nT:AFTER\nE:\n*S\nT:IN\nE:")
    assert output == "IN\nAFTER\n", "the module runs, then E: returns to just after the U:"


def test_end_terminates_when_there_is_no_module_to_return_from(run) -> None:  # type: ignore[no-untyped-def]
    """Spec 6.1.10 - with an empty use stack, `E:` stops the program."""
    output, _, _ = run("T:A\nE:\nT:NEVER")
    assert output == "A\n"


# ---------------------------------------------------------------------------
# Tracing (spec 9.5, 12)
# ---------------------------------------------------------------------------


def test_trace_records_every_executed_statement(run) -> None:  # type: ignore[no-untyped-def]
    _, _, events = run("T:ONE\nC:#A=1\nT:TWO", trace=True)
    assert [e.line_number for e in events] == [1, 2, 3]
    assert all(e.executed for e in events)


def test_trace_marks_a_skipped_statement(run) -> None:  # type: ignore[no-untyped-def]
    _, _, events = run("C:#A=1\nT(#A>9):SKIPPED\nT:RUN", trace=True)
    assert [e.executed for e in events] == [True, False, True]


def test_trace_is_off_by_default(run) -> None:  # type: ignore[no-untyped-def]
    _, _, events = run("T:ONE")
    assert events == []


def test_trace_lines_helper_is_readable() -> None:
    interpreter = Interpreter(parse("T:ONE\nT:TWO"), output=None)
    lines = list(interpreter.trace_lines())
    assert lines == ["   1  T:ONE", "   2  T:TWO"]


def test_trace_event_is_frozen() -> None:
    event = TraceEvent(line_number=1, command="T", source="T:X")
    with pytest.raises(AttributeError):
        event.line_number = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# The dispatch loop
# ---------------------------------------------------------------------------


def test_label_only_lines_are_skipped(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("*HERE\nT:ONE\n*THERE\nT:TWO")
    assert output == "ONE\nTWO\n"


def test_an_empty_program_runs_cleanly(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("")
    assert output == ""


def test_a_program_of_only_remarks_runs_cleanly(run) -> None:  # type: ignore[no-untyped-def]
    output, _, _ = run("R:ONE\nR:TWO")
    assert output == ""


def test_state_survives_across_statements(run) -> None:  # type: ignore[no-untyped-def]
    output, state, _ = run(f"C:{D}NAME=ADA\nC:#A=3\nT:{D}NAME IS #A")
    assert state.get_string("NAME") == "ADA"
    assert state.get_number("A").value == 3
    assert output == "ADA IS 3\n"


def test_the_examples_corpus_parses_and_its_t_statements_are_runnable() -> None:
    """Every example's `T:` lines must expand without error.

    The examples use `A:` and `M:`, which are later stages, so this checks only
    that the text expressions are well formed.
    """
    from pathlib import Path

    examples = Path(__file__).parent.parent / "examples"
    for path in sorted(examples.glob("*.pilot")):
        for statement in parse(path.read_text(encoding="utf-8")):
            if statement.command == "T":
                # Must not raise, whatever the variables happen to hold.
                assert isinstance(statement.params, str)
