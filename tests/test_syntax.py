"""Table-driven tests for the ATARI PILOT parser.

One case per grammar production in ``SPEC.md`` section 4, plus the rejections
required by section 10.6. Each test names the spec rule it pins, so a failure
says which rule broke rather than just that "parsing changed".
"""

from __future__ import annotations

import pytest

from pypilot.errors import PilotSyntaxError
from pypilot.syntax import (
    CONTINUABLE,
    MAX_LINE_NUMBER,
    REJECTED,
    CommandName,
    Condition,
    decode_source,
    parse,
)


def statements(source: str) -> list[str]:
    """Parse ``source`` and render each statement via its ``__str__``."""
    return [str(s) for s in parse(source).statements]


def first(source: str):  # type: ignore[no-untyped-def]
    """Parse ``source`` and return its single statement."""
    program = parse(source)
    assert len(program.statements) == 1, f"expected one statement, got {len(program.statements)}"
    return program.statements[0]


# ---------------------------------------------------------------------------
# 4.1 Source encoding and line numbers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_all_three_line_endings_terminate_a_line(newline: str) -> None:
    assert statements(f"T:A{newline}T:B") == ["T:A", "T:B"]


def test_line_numbers_are_sequential_from_one() -> None:
    program = parse("T:A\n\nT:B")
    assert [s.line_number for s in program.statements] == [1, 3]


def test_leading_line_number_is_accepted_and_ignored() -> None:
    """A `LIST:`ed Atari program carries line numbers; they must load."""
    assert statements("100 T:HELLO") == ["T:HELLO"]


def test_line_number_above_maximum_is_an_error() -> None:
    with pytest.raises(PilotSyntaxError, match=f"exceeds the maximum of {MAX_LINE_NUMBER}"):
        parse("10000 T:HELLO")


def test_decode_source_handles_utf8() -> None:
    assert decode_source("T:café".encode()) == "T:café"


def test_decode_source_falls_back_for_legacy_bytes() -> None:
    """ATASCII/CP437 text must still load rather than raising."""
    assert decode_source(b"T:\x9d")  # a high byte that is not valid UTF-8


def test_decode_source_passes_str_through() -> None:
    assert decode_source("T:X") == "T:X"


# ---------------------------------------------------------------------------
# 4.2 Line structure
# ---------------------------------------------------------------------------


def test_label_may_share_a_line_with_a_command() -> None:
    """Spec 4.2 - Core PILOT readings often disallow this; ATARI permits it."""
    statement = first("*HERE T:we are here")
    assert statement.label == "HERE"
    assert statement.command == "T"
    assert statement.params == "we are here"


def test_label_only_line_is_a_no_op() -> None:
    statement = first("*START")
    assert statement.is_label_only
    assert statement.label == "START"
    assert statement.command == ""


def test_label_of_any_length_is_accepted() -> None:
    """Spec 4.2 - labels are not limited to ten characters."""
    long_label = "A" * 200
    assert first(f"*{long_label}").label == long_label


def test_label_case_is_preserved() -> None:
    """Spec 4.2 - ATARI does not fold label case."""
    assert first("*MixedCase").label == "MixedCase"


def test_label_with_no_name_is_an_error() -> None:
    with pytest.raises(PilotSyntaxError, match="a label must be"):
        parse("*:NOPE")


def test_command_names_are_upper_cased() -> None:
    assert first("t:hello").command == "T"


def test_ty_and_tn_carry_a_match_condition() -> None:
    """Spec 4.4/7.3 - `TY:` is the general form of `Y:`, not a separate command."""
    assert first("TY:GOOD").command == "T"
    assert first("TN:BAD").command == "T"


def test_ty_is_continuable_because_it_folds_to_t_with_a_y_condition() -> None:
    """``TY:`` resolves to ``T``, and ``T`` is continuable (spec 4.4)."""
    assert "T" in CONTINUABLE


@pytest.mark.parametrize(
    ("spelling", "flag"),
    [
        ("Y", "Y"),
        ("TY", "Y"),
        ("YY", "Y"),
        ("NY", "Y"),
        ("N", "N"),
        ("TN", "N"),
        ("YN", "N"),
        ("NN", "N"),
    ],
)
def test_y_and_n_spellings_all_fold_to_t_with_a_match_condition(spelling: str, flag: str) -> None:
    """Spec 6.1.1 - `Y` abbreviates `TY` and `N` abbreviates `TN`.

    The spec calls `YY` redundant and `YN` a statement that never executes,
    but both are *syntactically proper*, so a real Atari accepts them and so
    must pyPILOT. The **second** letter is the condition, which is what makes
    `YN` never execute: type-if-yes *and* if-no-match cannot both hold.
    """
    statement = first(f"{spelling}:TEXT")
    assert statement.command == "T"
    assert statement.condition == Condition(match=flag)


@pytest.mark.parametrize("spelling", ["Y", "TY", "N", "TN"])
def test_a_y_or_n_condition_combines_with_an_expression(spelling: str) -> None:
    """Spec 4.4 - the match flag and the expression are conjunctive.

    For the two-letter spellings the condition is the **second** letter.
    """
    flag = "N" if spelling in {"N", "TN"} else "Y"
    statement = first(f"{spelling}(#A>3):TEXT")
    assert statement.command == "T"
    assert statement.condition == Condition(match=flag, expression="#A>3")


@pytest.mark.parametrize(
    "name", sorted(CommandName.all() - set(CommandName.CORE_ALIASES) - {"Y", "N"})
)
def test_every_known_command_parses(name: str) -> None:
    # E: takes no operand (spec 8.4), so it is exercised with an empty payload.
    # Y/N and their two-letter spellings are excluded because spec 6.1.1 makes
    # them abbreviations for TY/TN, which parse as T with a match condition -
    # covered by test_y_and_n_spellings_all_fold_to_t_with_a_match_condition.
    payload = "" if name == "E" else "payload"
    assert first(f"{name}:{payload}").command == name


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(PilotSyntaxError, match="unknown command"):
        parse("Q:NOPE")


def test_command_name_is_exact_not_truncated() -> None:
    """Spec 4.2 - `TYPEN:` is `TY` plus junk, not a forgiving `TY`.

    The longest-match scan takes `TY`, leaving `PEN:` which is not a colon, so
    this must be an error rather than silently typing something.
    """
    with pytest.raises(PilotSyntaxError):
        parse("TYPEN:JUNK")


def test_missing_colon_is_an_error() -> None:
    with pytest.raises(PilotSyntaxError, match="expected ':'"):
        parse("T NO COLON HERE")


def test_comment_runs_from_bracket_to_end_of_line() -> None:
    """Spec 4.2/4.6 - the delimiter is `[`, not `//`.

    There is no closing delimiter: the comment runs to end of line, so a `]`
    inside it is ordinary comment text.
    """
    statement = first("T:HELLO [this: is ignored entirely")
    assert statement.params == "HELLO "
    assert statement.comment == "this: is ignored entirely"


def test_comment_may_contain_colon_and_brackets() -> None:
    statement = first("T:X [a [nested] bracket: colon]")
    assert statement.params == "X "
    assert statement.comment == "a [nested] bracket: colon]"


def test_slash_slash_is_literal_text_not_a_comment() -> None:
    """Spec 4.2 - ATARI has no `//` comment."""
    statement = first("T:see //this")
    assert statement.params == "see //this"
    assert statement.comment is None


def test_comment_only_line_produces_no_command() -> None:
    assert parse("[just a comment]").statements[0].command == ""


def test_label_with_a_command_on_the_same_line_is_indexed() -> None:
    program = parse("*DUP T:FIRST\n*DUP T:SECOND")
    assert program.resolve("DUP") == 0
    assert program.statements[0].params == "FIRST"


# ---------------------------------------------------------------------------
# Conditions (4.2, 4.4)
# ---------------------------------------------------------------------------


def test_ty_normalises_to_t_with_a_y_condition() -> None:
    """`TY:` is the general form of `Y:` - a `T` with a `Y` condition (spec 4.4).

    Both readings mean the same thing; the general form wins because it carries
    strictly more information.
    """
    statement = first("TY:GOOD")
    assert statement.command == "T"
    assert statement.condition == Condition(match="Y")


def test_tn_normalises_to_t_with_a_n_condition() -> None:
    statement = first("TN:BAD")
    assert statement.command == "T"
    assert statement.condition == Condition(match="N")


def test_y_condition() -> None:
    assert first("T:HELLO").command == "T"
    assert first("TY:HELLO").condition == Condition(match="Y")


def test_n_condition() -> None:
    assert first("TN:HELLO").condition == Condition(match="N")


def test_parenthesised_expression_condition() -> None:
    assert first("T(#A>10):X").condition == Condition(expression="#A>10")


def test_match_and_expression_conditions_are_conjunctive() -> None:
    """Spec 4.4 - when both are present, both must hold."""
    condition = first("TY(#A>10):X").condition
    assert condition is not None
    assert condition.match == "Y"
    assert condition.expression == "#A>10"
    assert bool(condition)


def test_nested_parentheses_in_condition() -> None:
    condition = first("T((#A+#B)>10):X").condition
    assert condition is not None
    assert condition.expression == "(#A+#B)>10"


def test_unbalanced_paren_is_an_error() -> None:
    with pytest.raises(PilotSyntaxError, match="unbalanced"):
        parse("T(#A>10:X")


def test_unconditional_statement_has_no_condition() -> None:
    assert first("T:X").condition is None


def test_empty_condition_is_falsey() -> None:
    assert not Condition()


# ---------------------------------------------------------------------------
# 4.3 Field delimiting
# ---------------------------------------------------------------------------


def test_blanks_to_the_left_of_colon_are_ignored() -> None:
    """Spec 4.3 - a line may be freely formatted before the `:`.

    Spec 4.2: a label is delimited by the first non-alphanumeric character, so
    the blanks after `LAB` are what end the label and let `T` be the command.
    """
    statement = first("   *LAB    T   :   value")
    assert statement.label == "LAB"
    assert statement.command == "T"
    assert statement.params == "   value"


def test_label_runs_to_the_first_non_alphanumeric_character() -> None:
    """Spec 4.2 - a label needs a delimiter, or it swallows what follows."""
    # With no delimiter, `T` is part of the label.
    assert first("*LABT:value").label == "LABT"
    # A blank is a delimiter, so `T` becomes the command.
    assert first("*LAB T:value").label == "LAB"
    assert first("*LAB T:value").command == "T"


def test_blanks_right_of_colon_are_significant() -> None:
    """Spec 4.3 - and preserved exactly, leading and trailing."""
    assert first("T:  padded  ").params == "  padded  "


def test_blanks_before_a_comment_are_part_of_the_operand() -> None:
    """Trailing blanks are data, which is why `M:` uses `_` for them (spec 5.2.3)."""
    assert first("T:HELLO  [note]").params == "HELLO  "


def test_comment_only_line_renders_without_a_command() -> None:
    statement = first("[just a comment]")
    assert statement.command == ""
    assert statement.comment == "just a comment]"
    assert str(statement) == "[just a comment]"


# ---------------------------------------------------------------------------
# 4.4 Command continuation
# ---------------------------------------------------------------------------


def test_continuation_inherits_the_previous_command() -> None:
    assert statements("T:one\n:two\n:three") == ["T:one", "T:two", "T:three"]


def test_continuation_inherits_the_condition_too() -> None:
    """Spec 4.4 - the condition is inherited, not just the command."""
    program = parse("T(#A>40):NOT ENOUGH\n:TRY AGAIN")
    assert program.statements[1].condition == Condition(expression="#A>40")
    assert program.statements[1].continued


@pytest.mark.parametrize("command", sorted(CONTINUABLE))
def test_continuation_is_allowed_after_the_permitted_commands(command: str) -> None:
    assert statements(f"{command}:one\n:two") == [f"{command}:one", f"{command}:two"]


@pytest.mark.parametrize("spelling", ["Y", "TY", "YY", "N", "TN", "NN"])
def test_continuation_is_allowed_after_a_y_or_n_spelling(spelling: str) -> None:
    """They all resolve to `T`, which is continuable (spec 4.4).

    Compared by parsed command rather than by rendered text, because
    ``TY:one`` re-renders as ``TY:one`` - the spelling is preserved, which is
    what a learner who typed ``TY:`` expects to see.
    """
    program = parse(f"{spelling}:one\n:two")
    assert [s.command for s in program.statements] == ["T", "T"]
    assert program.statements[1].continued


def test_continuation_after_c_is_a_parse_error() -> None:
    """Spec 4.4 - continuation is limited to T, Y, N and R in run mode."""
    with pytest.raises(PilotSyntaxError, match="continuation is not allowed after C"):
        parse("C:#A=1\n:more")


def test_continuation_after_j_is_a_parse_error() -> None:
    with pytest.raises(PilotSyntaxError, match="continuation is not allowed after J"):
        parse("J:*A\n:more")


def test_continuation_after_a_label_only_line_is_allowed() -> None:
    """A label line does not change the continuation command (spec 4.4)."""
    assert statements("T:one\n*HERE\n:two") == ["T:one", "*HERE", "T:two"]


def test_immediate_mode_allows_continuation_after_any_command() -> None:
    """Spec 4.4 - in immediate mode the restriction lifts."""
    program = parse("C:#A=1\n:more", immediate_mode=True)
    assert [str(s) for s in program.statements] == ["C:#A=1", "C:more"]


def test_first_line_continuation_defaults_to_type() -> None:
    """Spec 4.4 - the default continuation command at power-up is T."""
    assert statements(":orphan") == ["T:orphan"]


# ---------------------------------------------------------------------------
# Labels and the label index (8.1)
# ---------------------------------------------------------------------------


def test_labels_are_indexed() -> None:
    program = parse("*START\nT:A\n*LOOP\nJ:*LOOP")
    assert program.labels == {"START": 0, "LOOP": 2}


def test_resolve_accepts_an_optional_leading_asterisk() -> None:
    """Spec 10.2 - most implementations accept `J:FOO` and `J:*FOO` alike."""
    program = parse("*FOO\nE:")
    assert program.resolve("FOO") == 0
    assert program.resolve("*FOO") == 0


def test_resolve_returns_none_for_an_unknown_label() -> None:
    assert parse("T:A").resolve("NOPE") is None


def test_duplicate_labels_are_allowed_and_lowest_line_wins() -> None:
    """Spec 4.2 - ATARI makes no duplicate check; the lower line number wins."""
    program = parse("*DUP T:FIRST\nT:MIDDLE\n*DUP T:SECOND")
    assert program.resolve("DUP") == 0
    assert program.statements[0].params == "FIRST"
    assert program.statements[2].params == "SECOND"


# ---------------------------------------------------------------------------
# Command-specific operand rules
# ---------------------------------------------------------------------------


def test_e_takes_no_operand() -> None:
    """Spec 8.4 / App. B - the operand is null."""
    assert first("E:").params == ""
    with pytest.raises(PilotSyntaxError, match="E: takes no operand"):
        parse("E:SOMETHING")


def test_m_requires_at_least_one_field() -> None:
    """Spec 7.4 - a null M: operand is not allowed."""
    with pytest.raises(PilotSyntaxError, match="at least one match field"):
        parse("M:")


def test_ms_requires_at_least_one_field() -> None:
    with pytest.raises(PilotSyntaxError, match="at least one match field"):
        parse("MS:")


@pytest.mark.parametrize("command", ["J", "U", "JM"])
def test_at_shorthand_jumps_are_rejected(command: str) -> None:
    """Spec 10.6 - `@A`/`@M`/`@P` are Core PILOT; ATARI has `JM:`."""
    with pytest.raises(PilotSyntaxError, match="shorthand jumps are not an ATARI construct"):
        parse(f"{command}:@A")


def test_empty_field_in_m_is_preserved() -> None:
    """Spec 7.4 - an empty field is a null match that matches anything."""
    assert first("M:THIS,THAT,,OTHER").params == "THIS,THAT,,OTHER"


def test_a_assign_operands_are_preserved_verbatim() -> None:
    """Spec 7.2.1 - `A:=<text>` assigns without prompting."""
    assert first("A:=THIS IS A TEST.").params == "=THIS IS A TEST."


# ---------------------------------------------------------------------------
# 10.6 Core PILOT commands that must be rejected, not ignored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("FO:1,F", "READ:"),
        ("FA:#A,F", "READ:"),
        ("FR:#A,$B", "READ:"),
        ("P:WIDTH", "not an ATARI command"),
        ("W:5", "PA:"),
        ("CN:3,4", "PCS:"),
        ("CS:0", "upper case"),
        ("RU:PROG", "immediate-mode only"),
    ],
)
def test_core_pilot_only_commands_are_rejected_not_ignored(source: str, expected: str) -> None:
    """Spec 10.6 - silently accepting these would run the wrong program.

    Spelled out rather than driven off :data:`REJECTED`, because several names
    are prefix-ambiguous: the scanner finds a shorter valid name first, so the
    rejection has to survive longest-match resolution.
    """
    with pytest.raises(PilotSyntaxError) as excinfo:
        parse(source)
    assert expected in str(excinfo.value), source


def test_rejected_table_has_a_reason_for_every_entry() -> None:
    assert all(reason.strip() for reason in REJECTED.values())


def test_l_is_a_label_not_a_link_command() -> None:
    """Spec 10.6 - `L` is a label prefix in ATARI, not Core PILOT's Link."""
    statement = first("*LOOK")
    assert statement.label == "LOOK"


# ---------------------------------------------------------------------------
# Refused and immediate-only commands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["GR", "SO", "CALL", "TAPE", "TSYNC", "DOS"])
def test_refused_commands_still_parse(name: str) -> None:
    """Spec 10.4/10.7 - they parse here and are refused at run time.

    Stage 9 implements the refusal; Stage 1 only requires that a real ATARI
    program loads rather than failing at the parser.
    """
    assert first(f"{name}:CLEAR").command == name


@pytest.mark.parametrize("name", ["AUTO", "REN"])
def test_immediate_only_commands_parse(name: str) -> None:
    """Spec 10.8 - rejected at run time, not parse time."""
    assert first(f"{name}:1").command == name


def test_command_name_predicates() -> None:
    assert CommandName.is_command("gr")
    assert not CommandName.is_command("ZZ")
    assert not CommandName.is_refused("GR")
    assert not CommandName.is_refused("SO")
    assert CommandName.is_refused("DOS")
    assert not CommandName.is_refused("T")
    assert CommandName.is_immediate_only("AUTO")
    assert not CommandName.is_immediate_only("RUN")


# ---------------------------------------------------------------------------
# Program container
# ---------------------------------------------------------------------------


def test_program_source_round_trips() -> None:
    original = "*HERE T:hello\nA:$NAME\n*LOOP\nJ:*LOOP\nE:"
    program = parse(original)
    reparsed = parse(program.source)
    assert [str(s) for s in reparsed.statements] == [str(s) for s in program.statements]
    assert reparsed.labels == program.labels


def test_program_length_and_iteration() -> None:
    program = parse("T:A\nT:B\nT:C")
    assert len(program) == 3
    assert [s.params for s in program] == ["A", "B", "C"]


def test_empty_program_is_valid() -> None:
    program = parse("")
    assert len(program) == 0
    assert program.labels == {}


def test_blank_lines_are_ignored() -> None:
    assert statements("\n\n   \nT:A\n\n") == ["T:A"]


def test_crlf_source_preserves_params_without_carriage_returns() -> None:
    program = parse("T:A\r\nT:B\r\n")
    assert all("\r" not in s.params for s in program.statements)


def test_syntax_error_carries_line_and_source() -> None:
    with pytest.raises(PilotSyntaxError) as excinfo:
        parse("T:A\nT:B\nQ:BAD")
    assert excinfo.value.line == 3
    assert excinfo.value.source == "Q:BAD"
    assert "line 3" in str(excinfo.value)
