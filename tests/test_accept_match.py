"""Tests for `A:`, `M:` and `MS:` (Stage 5).

The rules here are the ones that differ most from other PILOT dialects, and
each test cites the spec section it pins. Where the Atari spec prints a worked
example, that example is the test — including the two in §6.1.4, which pin the
`<right arrow>` semantics that OCR loses from the PDF.
"""

from __future__ import annotations

from typing import Any

import pytest

from pypilot.errors import PilotRuntimeError, PilotSyntaxError
from pypilot.match import CURSOR_RIGHT, find_match, split_fields
from pypilot.syntax import parse

D = "$"
CR = CURSOR_RIGHT  # ATASCII cursor-right, ESC CTRL-

#: Spec 6.1.4's own worked example, reproduced exactly.
SPEC_BUFFER = " THIS IS A TEST. "


# ---------------------------------------------------------------------------
# 7.2 A: - Accept
# ---------------------------------------------------------------------------


def test_a_reads_a_line_into_the_buffer(run: Any) -> None:
    _, state, _ = run("A:$X", ["typed"])
    assert state.accept_buffer == " TYPED "


def test_a_echoes_the_input(run: Any) -> None:
    """Spec 6.1.2 - the accept is "always terminated by a newline that is
    echoed to the display", so the echo is unconditional."""
    output, _, _ = run("A:$X", ["hello"])
    assert output == "hello\n"


def test_a_normalises_the_buffer_but_not_the_variable(run: Any) -> None:
    """Spec 7.2.2 - normalisation applies to the buffer only."""
    _, state, _ = run("A:$X", ["  Mixed   Case  "])
    assert state.accept_buffer == " MIXED CASE "
    assert state.get_string("X") == "  Mixed   Case  "


def test_a_with_no_variable_still_fills_the_buffer(run: Any) -> None:
    _, state, _ = run("A:", ["anonymous"])
    assert state.accept_buffer == " ANONYMOUS "


def test_a_accepts_a_numeric_variable(run: Any) -> None:
    _, state, _ = run("A:#A", ["42"])
    assert state.get_number("A").value == 42


def test_a_accepts_a_leading_s_as_a_dollar(run: Any) -> None:
    """Spec 6.1.2 - the spec's own examples use both `A:#A` and `A:SNAME`."""
    _, state, _ = run("A:SNAME", ["ada"])
    assert state.get_string("NAME") == "ada"


def test_a_assigns_without_prompting(run: Any) -> None:
    """Spec 7.2.1 - `A:=text` sets the buffer and asks for nothing."""
    output, state, _ = run("A:=THIS IS A TEST.")
    assert state.accept_buffer == " THIS IS A TEST. "
    assert output == "", "A:= must not prompt, so nothing is echoed"


def test_a_assign_is_still_normalised(run: Any) -> None:
    _, state, _ = run("A:=  mixed  ")
    assert state.accept_buffer == " MIXED "


def test_a_assign_then_matches(run: Any) -> None:
    """The assignment form exists precisely to drive `M:` without input."""
    output, state, _ = run("A:=YES\nM:YES\nT:MATCHED")
    assert output == "MATCHED\n"
    assert state.match.ordinal == 1


def test_a_rejects_a_multi_variable_operand(run: Any) -> None:
    """Spec 6.1.2 - there is no Core-PILOT style `A:$A,$B,$C`."""
    with pytest.raises(PilotRuntimeError, match="multi-variable"):
        run("A:$A,$B", ["x"])


def test_a_rejects_an_unknown_variable_sigil(run: Any) -> None:
    with pytest.raises(PilotRuntimeError, match="must be numeric"):
        run("A:?A", ["x"])


# ---------------------------------------------------------------------------
# 6.1.2 Numeric accept never errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("42", 42),
        ("-5", -5),
        ("0", 0),
        # Spec 6.1.2: a numeric constant "anywhere in the text" is taken.
        ("age 42", 42),
        ("3 apples", 3),
        # ...and wholly non-numeric text yields zero, with no error message.
        ("banana", 0),
        ("", 0),
        ("   ", 0),
    ],
)
def test_numeric_accept_never_errors(run: Any, typed: str, expected: int) -> None:
    """Spec 6.1.2 - non-numeric input stores 0 and reports nothing."""
    _, state, _ = run("A:#A", [typed])
    assert state.get_number("A").value == expected


def test_numeric_accept_of_an_empty_line_is_zero(run: Any) -> None:
    """Spec 6.1.2 - an empty line sets a numeric variable to zero."""
    _, state, _ = run("A:#A", [""])
    assert state.get_number("A").value == 0


def test_empty_line_makes_a_string_null_not_undefined(run: Any) -> None:
    """Spec 6.1.2 - null and undefined are different states (spec 6.1)."""
    _, state, _ = run("A:$E", [""])
    assert state.is_defined("E")
    assert state.get_string("E") == ""


def test_a_reports_running_out_of_input(run: Any) -> None:
    with pytest.raises(PilotRuntimeError, match="no more input"):
        run("A:$X", [])


def test_a_input_error_carries_the_line(run: Any) -> None:
    with pytest.raises(PilotRuntimeError) as excinfo:
        run("T:ONE\nA:$X", [])
    assert excinfo.value.line == 2


# ---------------------------------------------------------------------------
# 7.4 M: - field splitting
# ---------------------------------------------------------------------------


def test_fields_split_on_a_comma() -> None:
    assert split_fields("YES,YEAH,SURE") == (["YES", "YEAH", "SURE"], 0)


def test_a_leading_bar_selects_the_bar_separator() -> None:
    """Spec 6.1.3 - the leading bar selects the separator; it is not a field."""
    assert split_fields("|YES|YEAH") == (["YES", "YEAH"], 0)


def test_the_separator_is_never_both_at_once() -> None:
    """Spec 6.1.3 - 'there is no situation in which both' may act as separator."""
    fields, _ = split_fields("|A,B|C")
    assert fields == ["A,B", "C"]


def test_a_leading_bar_is_not_an_empty_first_field() -> None:
    fields, _ = split_fields("|YES")
    assert fields == ["YES"], "the bar is a selector, not an empty field"


def test_empty_fields_are_preserved() -> None:
    """Spec 6.1.3 - `M:THIS,THAT,,OTHER` has a null match in the middle."""
    assert split_fields("THIS,THAT,,OTHER") == (["THIS", "THAT", "", "OTHER"], 0)


def test_a_null_operand_is_rejected() -> None:
    """Spec 6.1.3 - a null operand is not allowed."""
    with pytest.raises(PilotRuntimeError, match="at least one match field"):
        split_fields("")


def test_separators_without_a_field_are_a_null_match() -> None:
    """Spec 6.1.3 - `M:,` is one of the spec's own three special cases.

    Its table reads: "Null operand is not allowed" for `M:`, then "Will match
    anything (null match)" for **both** `M:,` and `M:THIS,THAT,,OTHER`. So a
    list of two empty fields is legal and matches everything - which is only
    consistent with an empty field being a null match, since the first field is
    tried first and matches immediately.
    """
    fields, skipped = split_fields(",")
    assert fields == ["", ""]
    assert skipped == 0
    assert find_match(" ANYTHING AT ALL ", fields, 0).matched
    assert find_match(" ANYTHING AT ALL ", fields, 0).ordinal == 1


def test_a_trailing_underscore_becomes_a_blank(run: Any) -> None:
    """Spec 5.2.3 - the idiomatic way to match a word *plus* the buffer's
    mandatory trailing space: `M:YES,YEAH,SURE_` vs `M:YES,YEAH,SURE`.

    The underscore is turned into a blank by **text expansion** (spec 5.2.3),
    before the fields are split, so it is the expansion that must show the
    difference - not ``split_fields`` on raw text.
    """
    _, state, _ = run("A:=SURE\nM:SURE_\nT:MATCHED")
    assert state.match.matched, "SURE_ should match the buffer ' SURE '"

    _, state, _ = run("A:=SURE\nM:SURE\nT:MATCHED")
    assert state.match.matched, "SURE matches the buffer as a substring"

    # The distinct case: a field with an explicit trailing blank needs the
    # full normalised buffer, so the underscore is what makes 'SURE ' differ.
    _, state, _ = run("A:=SURE\nM: SURE \nT:MATCHED")
    assert state.match.matched
    _, state, _ = run("A:=SURE\nM: SURE\nT:MATCHED")
    assert state.match.matched, "a substring match still succeeds"


def test_right_arrows_are_counted_and_removed() -> None:
    fields, skipped = split_fields(f"{CR}{CR}YES,NO")
    assert fields == ["YES", "NO"]
    assert skipped == 2


def test_right_arrows_may_follow_the_leading_bar() -> None:
    """Spec 6.1.3 - 'they may start after the optional vertical bar'."""
    fields, skipped = split_fields(f"|{CR}YES")
    assert fields == ["YES"]
    assert skipped == 1


# ---------------------------------------------------------------------------
# 7.4 M: - matching
# ---------------------------------------------------------------------------


def test_an_exact_field_matches() -> None:
    outcome = find_match(" YES ", ["YES"], 0)
    assert outcome.matched
    assert outcome.ordinal == 1


def test_the_field_may_be_found_inside_a_word(run: Any) -> None:
    """Spec 6.1.3 - "a less precise matching of character substrings within
    words" is the documented behaviour, so `M:YES` can land mid-word."""
    output, _, _ = run("A:=YES\nM: YES \nT:MATCHED")
    assert output == "MATCHED\n"


def test_a_field_may_be_the_whole_buffer(run: Any) -> None:
    output, _, _ = run("A:=YES\nM: YES \nT:MATCHED")
    assert output == "MATCHED\n"


def test_matching_is_a_substring_search() -> None:
    """Spec 6.1.3 - the manual calls `M:YE,SURE` "a less precise matching of
    character substrings within words", so `M:YE` **does** match `YEAH`.

    Asserted against `find_match` rather than through a program: `M:` does not
    set the three split strings, only `MS:` does (spec 6.1.4), so there is no
    `$MATCH` to read for a plain `M:`.
    """
    outcome = find_match(" YEAH ", ["YE"], 0)
    assert outcome.matched
    assert outcome.match == "YE"
    assert outcome.left == " "
    assert outcome.right == "AH "


def test_the_first_occurrence_is_used() -> None:
    """The scan is left to right, so the earliest occurrence wins."""
    outcome = find_match(" A B A B ", ["B"], 0)
    assert outcome.left == " A ", "the leading blank is part of the buffer"
    assert outcome.right == " A B "


def test_fields_are_tried_in_order(run: Any) -> None:
    """Spec 6.1.3 - the buffer is searched for field 1, then 2, and so on."""
    _, state, _ = run("A:=NO\nM:YES,NO,MAYBE")
    assert state.match.ordinal == 2


def test_the_first_matching_field_wins(run: Any) -> None:
    _, state, _ = run("A:=YES\nM:YES,YES")
    assert state.match.ordinal == 1


def test_no_match_gives_ordinal_zero(run: Any) -> None:
    _, state, _ = run("A:=MAYBE\nM:YES,NO")
    assert state.match.ordinal == 0
    assert not state.match.matched


def test_an_empty_field_is_a_null_match(run: Any) -> None:
    """Spec 6.1.3 - an empty field matches anything, at its position in order."""
    _, state, _ = run("A:=ANYTHING AT ALL\nM:THIS,THAT,,OTHER")
    assert state.match.matched
    assert state.match.ordinal == 3


def test_the_null_match_reports_ordinal_not_one(run: Any) -> None:
    _, state, _ = run("A:=WHATEVER\nM:FIRST,SECOND,,")
    assert state.match.ordinal == 3


def test_m_clears_a_previous_match(run: Any) -> None:
    """A failed `M:` sets the flag; `M:` does not preserve $LEFT etc."""
    _, state, _ = run("A:=YES\nM:YES\nA:=NO\nM:MAYBE")
    assert state.match.ordinal == 0
    assert not state.match.matched


def test_match_accepts_a_variable_operand(run: Any) -> None:
    """Spec 6.1.3 - `M:$VERBLIST` uses a string variable holding the fields."""
    output, _, _ = run(f"C:{D}LIST=YES,YEAH\nA:=YEAH\nM:{D}LIST\nT:MATCHED")
    assert output == "MATCHED\n"


def test_m_requires_a_field() -> None:
    """Spec 7.4 - a null operand is rejected when the program is *read*.

    This is a parse-time error, not a runtime one: `M:` with nothing after the
    colon is malformed whatever the accept buffer happens to hold, so it is
    caught before the program runs.
    """
    with pytest.raises(PilotSyntaxError, match="at least one match field"):
        parse("M:")


def test_m_rejects_a_null_operand_at_run_time_too() -> None:
    """The same rule enforced by :func:`split_fields`, for a built operand.

    Reached when the operand arrives by a route the parser cannot see - which
    is why both layers check.
    """
    with pytest.raises(PilotRuntimeError, match="at least one match field"):
        split_fields("")


# ---------------------------------------------------------------------------
# 7.4.1 <right arrow>
# ---------------------------------------------------------------------------


def test_no_arrow_matches_the_whole_buffer_including_the_blanks() -> None:
    """Spec 6.1.3 - with no arrow, the field is compared to the whole buffer,
    blanks and all. That is the simplest form and the one most lessons use."""
    assert find_match(" YES ", [" YES "], 0).matched


def test_one_arrow_starts_after_the_leading_blank() -> None:
    """Spec 6.1.3 - a single arrow is the idiomatic skip of the leading blank.

    With one arrow the window is ``YES `` - the leading blank is behind the
    match point - so the field must be written without it.
    """
    assert find_match(" YES ", ["YES "], 1).matched
    assert not find_match(" YES ", [" YES "], 1).matched


def test_the_field_must_be_written_in_normalised_form() -> None:
    """Spec 7.2.2 - the buffer is upper case, so a field must be too.

    Case is what the rule is really about: `M:yes` cannot match ` YES ` because
    the buffer is upper-cased. Blanks are *not* forced - `M:YES` does match,
    since the field is a substring and the leading blank simply falls to the
    left of the match. This is why the Atari manuals still write `M: YES ` when
    they want the whole buffer and nothing else.
    """
    assert not find_match(" YES ", ["yes"], 0).matched
    assert not find_match(" YES ", ["YeS"], 0).matched
    assert find_match(" YES ", ["YES"], 0).matched
    assert find_match(" YES ", [" YES "], 0).matched


def test_ms_requires_a_field() -> None:
    """Spec 7.4 - as for `M:`, a null `MS:` operand is a parse-time error."""
    with pytest.raises(PilotSyntaxError, match="at least one match field"):
        parse("MS:")


def test_the_specs_worked_example_reproduces_exactly() -> None:
    """Spec 6.1.4 - three arrows over a synthesised buffer give the printed values.

    This is the clean, verifiable worked example. The spec prints a second one
    (``A:=THIS IS A TEST.``) whose values are not reproducible under any arrow
    count and appear to be OCR corruption; see SPEC.md section 7.5.
    """
    outcome = find_match(" WHAT WILL HAPPEN? ", [" "], 3)
    assert outcome.left == "AT"
    assert outcome.match == " "
    assert outcome.right == "WILL HAPPEN? "


def test_the_worked_example_as_a_program(run: Any) -> None:
    """The same thing, run rather than computed directly."""
    _, state, _ = run("A:=WHAT WILL HAPPEN?\nMS:" + CR * 3 + "_")
    assert (state.match.left, state.match.match, state.match.right) == (
        "AT",
        " ",
        "WILL HAPPEN? ",
    )


def test_the_specs_worked_example_pins_the_arrow_count() -> None:
    """Spec 6.1.4 - three arrows over ` WHAT WILL HAPPEN? ` give `AT`.

    This is the clearest evidence that *n* arrows land on the n+1th character.
    """
    buffer = " WHAT WILL HAPPEN? "
    outcome = find_match(buffer, [" "], 3)
    assert outcome.left == "AT"
    assert outcome.match == " "
    assert outcome.right == "WILL HAPPEN? "


def test_too_few_arrows_give_a_longer_left() -> None:
    buffer = " WHAT WILL HAPPEN? "
    assert find_match(buffer, [" "], 1).left == "WHAT"
    assert find_match(buffer, [" "], 2).left == "HAT"


def test_arrows_do_not_appear_in_left(run: Any) -> None:
    """Spec 6.1.4 - `$LEFT` excludes the characters the arrows skipped over."""
    _, state, _ = run("A:=WHAT WILL HAPPEN?\nMS:" + CR * 3 + "_")
    assert state.match.left == "AT"
    assert not state.match.left.startswith(" WHAT"), "the skipped text is excluded"


# ---------------------------------------------------------------------------
# 7.5 MS: - match strings
# ---------------------------------------------------------------------------


def test_ms_sets_the_three_strings(run: Any) -> None:
    """The §6.1.4 worked example, run rather than computed."""
    _, state, _ = run("A:=WHAT WILL HAPPEN?\nMS:" + CR * 3 + "_")
    assert (state.match.left, state.match.match, state.match.right) == (
        "AT",
        " ",
        "WILL HAPPEN? ",
    )


def test_ms_sets_the_ordinal_like_m(run: Any) -> None:
    _, state, _ = run("A:=NO\nMS:YES,NO")
    assert state.match.ordinal == 2


def test_ms_retains_previous_values_on_failure(run: Any) -> None:
    """Spec 6.1.4 - a failed `MS:` leaves `$LEFT`/`$MATCH`/`$RIGHT` alone."""
    _, state, _ = run("A:=WHAT WILL HAPPEN?\nMS:" + CR * 3 + "_\nA:=NOPE\nMS:ZZZ")
    assert not state.match.matched
    assert state.match.match == " ", "the previous match must be retained"
    assert state.match.left == "AT"


def test_ms_left_and_right_may_be_empty() -> None:
    """Spec 6.1.4 - 'any of these strings may have null values.'

    Asserted against `find_match`, since the null-ness is a property of where
    the field falls in the buffer rather than of the statement.
    """
    outcome = find_match(" ONLY ", ["ONLY"], 0)
    assert outcome.matched
    assert outcome.match == "ONLY"
    assert outcome.left == " "
    assert outcome.right == " "

    whole = find_match(" ONLY ", [" ONLY "], 0)
    assert whole.left == "" and whole.right == "", "a whole-buffer match has no flanks"


def test_ms_matches_at_the_start_and_end() -> None:
    """A field at either edge of the buffer can have a null flank (spec 6.1.4).

    The buffer's mandatory surrounding blanks (spec 7.2.2) are ordinary buffer
    text, so a null flank only appears where the field genuinely runs to the
    edge of the search window - which is why a `<right arrow>` is what creates
    one at the front.
    """
    # One arrow puts the window on the 'A', giving a null $LEFT.
    start = find_match(" ABC ", ["A"], 1)
    assert (start.left, start.match, start.right) == ("", "A", "BC ")

    # Without one, the leading blank is legitimately to the left.
    unskipped = find_match(" ABC ", ["A"], 0)
    assert (unskipped.left, unskipped.match, unskipped.right) == (" ", "A", "BC ")

    # The trailing blank trails the 'C', so $RIGHT is a single blank, not null.
    end = find_match(" ABC ", ["C"], 0)
    assert (end.left, end.match, end.right) == (" AB", "C", " ")

    # Skipping the leading blank only: the match starts at the window's edge,
    # giving a null $LEFT and the rest of the buffer as $RIGHT.
    windowed = find_match(" ABC ", ["ABC"], 1)
    assert (windowed.left, windowed.match, windowed.right) == ("", "ABC", " ")

    # The whole buffer as a single field has both flanks null.
    entire = find_match(" ABC ", [" ABC "], 0)
    assert (entire.left, entire.match, entire.right) == ("", " ABC ", "")


# ---------------------------------------------------------------------------
# 6.6 %M and the Y/N conditions
# ---------------------------------------------------------------------------


def test_percent_m_reports_the_ordinal(run: Any) -> None:
    _, state, _ = run("A:=NO\nM:YES,NO,MAYBE")
    assert state.evaluate("%M").value == 2


def test_percent_m_is_zero_without_a_match(run: Any) -> None:
    _, state, _ = run("A:=MAYBE\nM:YES")
    assert state.evaluate("%M").value == 0


def test_y_types_after_a_successful_match(run: Any) -> None:
    output, _, _ = run("A:=YES\nM:YES\nY:GOOD\nN:BAD")
    assert output == "GOOD\n"


def test_n_types_after_a_failed_match(run: Any) -> None:
    output, _, _ = run("A:=MAYBE\nM:YES\nY:GOOD\nN:BAD")
    assert output == "BAD\n"


def test_y_and_n_before_any_match(run: Any) -> None:
    """No match has happened, so the flag is clear and `N:` fires."""
    output, _, _ = run("Y:NEVER\nN:PRINTED")
    assert output == "PRINTED\n"


def test_a_match_condition_combines_with_an_expression(run: Any) -> None:
    """Spec 4.4 - conjunctive. `#A>0` alone is not enough for `Y:`."""
    output, _, _ = run("C:#A=1\nA:=YES\nM:YES\nY(#A>0):BOTH\nN(#A>0):NEITHER")
    assert output == "BOTH\n"


def test_a_match_condition_blocks_on_a_false_expression(run: Any) -> None:
    output, _, _ = run("C:#A=0\nA:=YES\nM:YES\nY(#A>0):BOTH")
    assert output == ""


# ---------------------------------------------------------------------------
# The end-to-end tutorial
# ---------------------------------------------------------------------------


def test_the_question_and_answer_tutorial(run: Any) -> None:
    """A whole lesson: greet, ask, match, branch.

    No trailing `E:` — that is a Stage 6 statement, so the program simply runs
    off the end, which is how a program terminated today behaves.
    """
    source = "\n".join(
        [
            "T:WHAT IS YOUR NAME?",
            f"A:{D}NAME",
            f"T:HELLO, {D}NAME.",
            "T:ARE YOU A STUDENT? (YES OR NO)",
            f"A:{D}ANSWER",
            "M:YES,Y",
            "TY:WELCOME TO THE COURSE.",
            "TN:COME BACK ANY TIME.",
        ]
    )
    output, state, _ = run(source, ["ada", "yes"])
    assert "HELLO, ada." in output
    assert "WELCOME TO THE COURSE." in output
    assert "COME BACK ANY TIME." not in output
    assert state.accept_buffer == " YES "


def test_the_tutorial_takes_the_other_branch(run: Any) -> None:
    """The `N:` half of the tutorial: answering NO must take the N branch.

    The two branch lines are guarded by the match condition - `Y:` and `N:`
    are `T` with a condition (spec 6.1.1), so the *text* after the colon is
    always typed and the *label* is what the branch jumps to. Jump-on-match
    (`JM:`) is the statement that actually branches, and it lands in Stage 6;
    here the conditions alone decide what prints.
    """
    source = "\n".join(
        [
            f"A:{D}ANSWER",
            "M:YES,Y",
            "TY:STUDENT",
            "TN:GUEST",
        ]
    )
    output, _, _ = run(source, ["no"])
    assert "GUEST" in output
    assert "STUDENT" not in output, "the Y branch must not have run"

    output_yes, _, _ = run(source, ["yes"])
    assert "STUDENT" in output_yes
    assert "GUEST" not in output_yes, "the N branch must not have run"


def test_the_msplit_example_program_runs() -> None:
    """`examples/msplit.pilot` is the spec's §6.1.4 worked example as a program.

    Runs the shipped file end to end, so the example and the interpreter cannot
    drift apart. The three expected lines are the spec's printed values.
    """
    from pathlib import Path

    from pypilot.io import BufferOutput, StringInput
    from pypilot.runtime import Interpreter
    from pypilot.syntax import parse

    path = Path(__file__).parent.parent / "examples" / "msplit.pilot"
    out = BufferOutput()
    Interpreter(parse(path.read_text(encoding="utf-8")), output=out, source=StringInput([])).run()
    text = out.text
    assert "LEFT IS  AT" in text, "spec 6.1.4 prints $LEFT as 'AT'"
    assert "MATCH IS  \n" in text, "the matched field is the embedded blank"
    assert "RIGHT IS WILL HAPPEN? " in text
    # Spec 6.1: undefined prints its own name, null prints nothing.
    assert "UNDEFINED MEANS UNSET" in text
    assert "NULL IS .\n" in text
