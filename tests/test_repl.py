"""Tests for the interactive REPL and the immediate-mode commands (Stage 8).

Every test drives a real :class:`~pypilot.repl.Repl` with a scripted input
device and a buffer output, so what is asserted is what a user would actually
see. No terminal is involved anywhere.

The spec sections pinned here are 6.2 (immediate mode), 6.2.1 ``LIST``,
6.2.2 ``RUN``, 6.2.5 ``NEW``, 6.2.6 ``AUTO`` and 6.2.7 ``REN``, plus 10.4 and
10.7 for the refused commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pypilot.errors import PilotError
from pypilot.helpers import Shell, parse_line_range
from pypilot.io import BufferOutput, StringInput
from pypilot.repl import Repl
from pypilot.syntax import parse

# ---------------------------------------------------------------------------
# Driving a session
# ---------------------------------------------------------------------------


def session(
    lines: list[str], tmp_path: Path | None = None, program_lines: list[str] | None = None
) -> tuple[Repl, str]:
    """Run a whole REPL session over ``lines`` and return it with its output.

    Args:
        lines: the REPL command stream.
        tmp_path: where the emulated devices live.
        program_lines: what a running program's ``A:`` reads. Separate by
            default, because a shared stream would let the program's first
            accept swallow the next REPL command.
    """
    out = BufferOutput()
    repl = Repl(
        output=out,
        source=StringInput(lines),
        program_source=StringInput(program_lines) if program_lines is not None else None,
        device_root=str(tmp_path) if tmp_path else None,
    )
    repl.run()
    return repl, out.text


def feed(repl: Repl, lines: list[str]) -> str:
    """Push ``lines`` into a live session and return just the new output."""
    out = BufferOutput()
    repl.output = out
    for line in lines:
        repl.handle_line(line)
    return out.text


# ---------------------------------------------------------------------------
# 6.2 Immediate mode
# ---------------------------------------------------------------------------


def test_a_statement_is_executed_at_once(tmp_path: Path) -> None:
    """Immediate mode: a typed statement runs, with no program area needed."""
    _, text = session(["T:HELLO", "QUIT"], tmp_path)
    assert "HELLO" in text
    assert "GOODBYE" in text


def test_exhausted_input_ends_the_session_cleanly(tmp_path: Path) -> None:
    """A scripted session must not need a QUIT to terminate.

    This is what makes the REPL testable at all: an exhausted input device is
    an end of session, not an error.
    """
    repl, _ = session(["T:ONE"], tmp_path)
    assert repl.running is False


def test_the_colon_is_optional(tmp_path: Path) -> None:
    """Spec 6.2 - the condition-field delimiter may be omitted in immediate mode."""
    _, with_colon = session(["T:HELLO", "QUIT"], tmp_path)
    _, without = session(["T HELLO", "QUIT"], tmp_path)
    assert "HELLO" in with_colon
    assert "HELLO" in without


def test_a_blank_line_is_ignored(tmp_path: Path) -> None:
    repl, text = session(["", "   ", "T:AFTER BLANKS", "QUIT"], tmp_path)
    assert "AFTER BLANKS" in text
    assert repl.running is False


def test_a_bad_statement_reports_and_keeps_going(tmp_path: Path, capsys: Any) -> None:
    """A REPL that exits on the first bad line is useless for experimenting."""
    _, text = session(["NOTACOMMAND", "T:STILL HERE", "QUIT"], tmp_path)
    assert "STILL HERE" in text
    assert "NOTACOMMAND" in capsys.readouterr().err


def test_quit_and_exit_both_leave(tmp_path: Path) -> None:
    for word in ("QUIT", "EXIT", "quit", "Quit:"):
        repl, _ = session([word], tmp_path)
        assert repl.running is False, f"{word} should end the session"


# ---------------------------------------------------------------------------
# 6.2.1 LIST
# ---------------------------------------------------------------------------


def test_list_prints_the_numbered_program(tmp_path: Path) -> None:
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    repl.shell.append("T:HELLO")
    repl.shell.append("E:")
    text = feed(repl, ["LIST"])
    assert "1  T:HELLO" in text
    assert "2  E:" in text


def test_list_of_an_empty_area_says_so(tmp_path: Path) -> None:
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    assert "empty" in feed(repl, ["LIST"])


def test_list_takes_a_line_range(tmp_path: Path) -> None:
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    for i in range(5):
        repl.shell.append(f"T:LINE{i}")
    text = feed(repl, ["LIST 2 3"])
    assert "LINE1" in text
    assert "LINE2" in text
    assert "LINE0" not in text
    assert "LINE3" not in text


def test_list_of_a_single_line_number_selects_that_line(tmp_path: Path) -> None:
    """Spec 6.2.1 - `LIST 500` is one line, not a range starting at 500."""
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    for i in range(3):
        repl.shell.append(f"T:LINE{i}")
    text = feed(repl, ["LIST 2"])
    assert "LINE1" in text
    assert "LINE0" not in text


@pytest.mark.parametrize(
    ("operand", "expected"),
    [
        ("", (None, None)),
        ("100", (100, 100)),
        ("100 200", (100, 200)),
        ("100, 200", (100, 200)),
        ("100  200", (100, 200)),
    ],
)
def test_parse_line_range(operand: str, expected: tuple[int | None, int | None]) -> None:
    assert parse_line_range(operand) == expected


def test_parse_line_range_rejects_nonsense() -> None:
    with pytest.raises(PilotError, match="not a line number"):
        parse_line_range("abc")
    with pytest.raises(PilotError, match="after"):
        parse_line_range("200 100")
    with pytest.raises(PilotError, match="at most two"):
        parse_line_range("1 2 3")


# ---------------------------------------------------------------------------
# 6.2.2 RUN
# ---------------------------------------------------------------------------


def test_run_executes_the_stored_program(tmp_path: Path) -> None:
    _, text = session(
        ["AUTO", "T:STORED", "", "RUN", "QUIT"],
        tmp_path,
    )
    assert "STORED" in text


def test_run_of_an_empty_area_says_so(tmp_path: Path, capsys: Any) -> None:
    session(["RUN", "QUIT"], tmp_path)
    assert "empty" in capsys.readouterr().err


def test_run_starts_from_a_clean_environment(tmp_path: Path) -> None:
    """Spec 6.2.2 - RUN clears the stack, buffer, variables and match flag."""
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    repl.shell.append("T:VALUE IS #A")
    repl.state.set_number("A", 99)
    text = feed(repl, ["RUN"])
    assert "VALUE IS 0" in text, "RUN must clear the variables first"


def test_an_immediate_only_command_is_refused_inside_a_program(tmp_path: Path, capsys: Any) -> None:
    """AUTO/REN are immediate-mode only (spec 6.2.6, 6.2.7).

    Refused when the *program* is run, not when the line is typed - typing
    `AUTO` at the prompt is exactly right, so telling the learner it is wrong
    there would be wrong.
    """
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    repl.shell.append("AUTO:100")
    feed(repl, ["RUN"])
    assert "immediate-mode" in capsys.readouterr().err


def test_a_failing_program_leaves_the_repl_usable(tmp_path: Path, capsys: Any) -> None:
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    repl.shell.append("J:*NOWHERE")
    feed(repl, ["RUN"])
    assert "NOWHERE" in capsys.readouterr().err
    # Still alive and still able to run.
    text = feed(repl, ["T:STILL ALIVE"])
    assert "STILL ALIVE" in text
    assert repl.running is True


# ---------------------------------------------------------------------------
# 6.2.5 NEW
# ---------------------------------------------------------------------------


def test_new_discards_the_program_and_the_variables(tmp_path: Path) -> None:
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    repl.shell.append("T:GONE")
    repl.state.set_number("A", 5)
    repl.state.set_string("S", "x")
    feed(repl, ["NEW"])
    assert repl.shell.is_empty()
    assert not repl.state.is_defined("S")


# ---------------------------------------------------------------------------
# 6.2.6 AUTO
# ---------------------------------------------------------------------------


def test_auto_numbers_from_ten_by_default(tmp_path: Path) -> None:
    repl, _ = session(["AUTO", "T:ONE", "T:TWO", "", "LIST", "QUIT"], tmp_path)
    assert len(repl.shell) == 2
    assert repl.shell.lines[0].startswith("10 ")
    assert repl.shell.lines[1].startswith("20 ")


def test_auto_takes_a_start_and_an_increment(tmp_path: Path) -> None:
    repl, _ = session(["AUTO 100,5", "T:ONE", "T:TWO", "", "LIST", "QUIT"], tmp_path)
    assert repl.shell.lines[0].startswith("100 ")
    assert repl.shell.lines[1].startswith("105 ")


def test_auto_start_alone_keeps_the_default_increment(tmp_path: Path) -> None:
    repl, _ = session(["AUTO 100", "T:ONE", "T:TWO", "", "LIST", "QUIT"], tmp_path)
    assert repl.shell.lines[0].startswith("100 ")
    assert repl.shell.lines[1].startswith("110 ")


def test_an_empty_line_leaves_auto_mode(tmp_path: Path) -> None:
    """Spec 6.2.6 - the entry of an empty line terminates the mode."""
    repl, _ = session(["AUTO", "T:STORED", "", "T:AFTER AUTO", "QUIT"], tmp_path)
    assert "AFTER AUTO" in repl.output.text if hasattr(repl.output, "text") else True
    assert len(repl.shell) == 1, "only the statement before the blank was stored"


def test_a_bad_statement_is_not_stored_and_auto_continues(tmp_path: Path, capsys: Any) -> None:
    """Spec 6.2.6 - only error-free statements are stored; the mode continues."""
    repl, _ = session(["AUTO", "NOTACOMMAND", "T:GOOD", "", "LIST", "QUIT"], tmp_path)
    assert len(repl.shell) == 1
    assert "GOOD" in repl.shell.lines[0]
    assert "not stored" in capsys.readouterr().err


def test_auto_rejects_a_bad_increment(tmp_path: Path, capsys: Any) -> None:
    session(["AUTO 10,0", "QUIT"], tmp_path)
    assert "increment must be positive" in capsys.readouterr().err


def test_auto_rejects_an_out_of_range_start(tmp_path: Path, capsys: Any) -> None:
    session(["AUTO 99999", "QUIT"], tmp_path)
    assert "outside the valid range" in capsys.readouterr().err


def test_auto_stops_when_a_line_number_would_overflow(tmp_path: Path, capsys: Any) -> None:
    """Spec 6.2.6 - an invalid line number terminates the mode."""
    _, _ = session(["AUTO 9990,10", "T:ONE", "T:TWO", "T:THREE", "QUIT"], tmp_path)
    err = capsys.readouterr().err
    assert "outside the valid range" in err


# ---------------------------------------------------------------------------
# 6.2.7 REN
# ---------------------------------------------------------------------------


def test_renumber_defaults_to_ten(tmp_path: Path) -> None:
    repl, _ = session(["AUTO", "T:ONE", "T:TWO", "", "REN", "LIST", "QUIT"], tmp_path)
    assert repl.shell.lines[0].startswith("10 ")
    assert repl.shell.lines[1].startswith("20 ")


def test_renumber_takes_a_start_and_an_increment(tmp_path: Path) -> None:
    repl, _ = session(["AUTO", "T:ONE", "T:TWO", "", "REN 100,25", "LIST", "QUIT"], tmp_path)
    assert repl.shell.lines[0].startswith("100 ")
    assert repl.shell.lines[1].startswith("125 ")


def test_renumbering_replaces_rather_than_stacks_numbers(tmp_path: Path) -> None:
    """`AUTO` already numbered these lines; `REN` must not prefix a second.

    A regression guard with teeth: prepending produced `10 100 T:HELLO`, which
    does not parse, so `RUN` failed outright. The `C:#A=6` line is the sharper
    half - a loose number-stripping regex ate the trailing `6` and turned the
    statement into `C:#A=`.
    """
    repl, text = session(
        ["AUTO 100,10", "T:HELLO", "C:#A=6", "", "REN 10,20", "RUN", "QUIT"], tmp_path
    )
    for line in repl.shell.lines:
        parts = line.split(maxsplit=1)
        assert len(parts) == 2, f"{line!r} has more than a number and a statement"
        assert parts[0].isdigit(), f"{line!r} does not start with a line number"
    assert "C:#A=6" in repl.shell.lines[1], "the statement's own digits must survive"
    assert "HELLO" in text, "the program must run after renumbering"
    assert "HELLO" in repl.output.text if hasattr(repl.output, "text") else True


def test_renumber_never_reorders_and_leaves_the_program_intact_on_overflow(
    tmp_path: Path, capsys: Any
) -> None:
    """Spec 6.2.7 - the program is never reorganised, so a partial renumber is
    recoverable. An overflowing REN must leave it exactly as it was."""
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    repl.shell.append("T:ONE")
    repl.shell.append("T:TWO")
    before = list(repl.shell.lines)
    feed(repl, ["REN 9990,10"])
    assert repl.shell.lines == before, "a failed renumber must change nothing"
    assert "unchanged" in capsys.readouterr().err


def test_renumber_rejects_a_zero_increment(tmp_path: Path) -> None:
    shell = Shell()
    shell.append("T:X")
    with pytest.raises(PilotError, match="increment must be positive"):
        shell.renumber(10, 0)


# ---------------------------------------------------------------------------
# DUMP / VNEW / TRACE in the REPL
# ---------------------------------------------------------------------------


def test_dump_lists_the_strings(tmp_path: Path) -> None:
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    repl.state.set_string("NAME", "JOE")
    assert "JOE" in feed(repl, ["DUMP"])


def test_vnew_clears_the_variables(tmp_path: Path) -> None:
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    repl.state.set_string("S", "x")
    repl.state.set_number("A", 5)
    feed(repl, ["VNEW"])
    assert not repl.state.is_defined("S")
    assert repl.state.get_number("A").value == 0


def test_vnew_dollar_leaves_the_numbers_alone(tmp_path: Path) -> None:
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    repl.state.set_string("S", "x")
    repl.state.set_number("A", 5)
    feed(repl, ["VNEW:$"])
    assert not repl.state.is_defined("S")
    assert repl.state.get_number("A").value == 5


def test_vnew_hash_leaves_the_strings_alone(tmp_path: Path) -> None:
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    repl.state.set_string("S", "x")
    repl.state.set_number("A", 5)
    feed(repl, ["VNEW:#"])
    assert repl.state.is_defined("S")
    assert repl.state.get_number("A").value == 0


def test_vnew_rejects_an_unknown_operand(tmp_path: Path, capsys: Any) -> None:
    session(["VNEW:X", "QUIT"], tmp_path)
    assert "takes $, # or nothing" in capsys.readouterr().err


def test_trace_toggles_and_collects_events(tmp_path: Path) -> None:
    repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
    feed(repl, ["TRACE:ON"])
    assert repl.tracing is True
    feed(repl, ["T:TRACED"])
    assert any("TRACED" in event.source for event in repl.events)
    feed(repl, ["TRACE:OFF"])
    assert repl.tracing is False


def test_trace_accepts_the_colon_in_either_place(tmp_path: Path) -> None:
    """Spec 6.2 - the colon is optional, and may sit either side of the blank."""
    for form in ("TRACE:ON", "TRACE: ON", "TRACE ON", "trace:on"):
        repl = Repl(output=BufferOutput(), source=StringInput([]), device_root=str(tmp_path))
        feed(repl, [form])
        assert repl.tracing is True, f"{form!r} should turn tracing on"


def test_trace_rejects_an_unknown_operand(tmp_path: Path, capsys: Any) -> None:
    session(["TRACE:MAYBE", "QUIT"], tmp_path)
    assert "takes ON or OFF" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# LOAD / SAVE
# ---------------------------------------------------------------------------


def test_save_then_list_round_trips_through_a_device(tmp_path: Path) -> None:
    _, text = session(
        ["AUTO", "T:ON DISK", "", "SAVE D:KEPT", "NEW", "LIST", "LOAD D:KEPT", "LIST", "QUIT"],
        tmp_path,
    )
    assert "ON DISK" in text
    assert (tmp_path / "disk" / "KEPT").exists()


def test_load_of_a_missing_file_reports_and_keeps_going(tmp_path: Path, capsys: Any) -> None:
    repl, text = session(["AUTO", "T:KEPT", "", "LOAD D:NOSUCH", "T:STILL HERE", "QUIT"], tmp_path)
    assert "STILL HERE" in text
    assert len(repl.shell) == 1, "the failed load must not have cleared the program"


# ---------------------------------------------------------------------------
# The whole point: a REPL-sized lesson
# ---------------------------------------------------------------------------


def test_a_whole_lesson_in_the_repl(tmp_path: Path) -> None:
    """A single session using AUTO, RUN and the match machinery.

    This is the end-to-end proof that the immediate mode and the run mode are
    the same language - which is the whole design of spec 6.2. The program asks
    for a name and then an answer, and the match branches on which one.
    """
    lines = [
        "AUTO 10,10",
        "T:WHAT IS YOUR NAME?",  # 10
        "A:$NAME",  # 20
        "T:HELLO, $NAME.",  # 30
        "T:ARE YOU A STUDENT? (YES OR NO)",  # 40
        "A:$ANSWER",  # 50
        # The fields carry the buffer's own surrounding blanks, so ` NO ` and
        # ` YES ` are matched as a whole. That is not decoration: `M:` is a
        # *substring* search (spec 6.1.3), so bare `NO` would also match the
        # "NO" inside anything containing those letters, and a bare `Y` field
        # would match the "y" of "yes" before `NO` was ever tried. Writing the
        # blanks is what the Atari manuals do, and it is why.
        "M: YES , NO ",  # 60
        "JM:*YES,*NO",  # 70
        "T:UNRECOGNISED ANSWER.",  # 80
        "J:*END",  # 90
        "*YES",  # 100
        "T:YOU SAID YES.",  # 110
        "J:*END",  # 120
        "*NO",  # 130
        "T:YOU SAID NO.",  # 140
        "*END",  # 150
        "E:",  # 160
        "",
        "RUN",
        "QUIT",
    ]
    _, text = session(lines, tmp_path, program_lines=["ada", "yes"])
    assert "WHAT IS YOUR NAME?" in text
    assert "HELLO, ada." in text
    assert "YOU SAID YES." in text
    assert "YOU SAID NO." not in text

    _, other = session(lines, tmp_path, program_lines=["bob", "no"])
    assert "YOU SAID NO." in other

    _, unmatched = session(lines, tmp_path, program_lines=["eve", "maybe"])
    assert "UNRECOGNISED ANSWER." in unmatched, "field 3 has no label, so it falls through"


def test_a_program_reads_from_its_own_input_stream(tmp_path: Path) -> None:
    """The program must not eat the REPL's next command.

    With one shared stream, the program's first ``A:`` reads the next REPL
    line, so a `QUIT` typed after `RUN` is consumed as the answer and the
    session runs away. This is the regression guard for that.
    """
    lines = ["AUTO", "T:NAME?", "A:$N", "T:HI $N", "", "RUN", "T:AFTER THE PROGRAM", "QUIT"]
    _, text = session(lines, tmp_path, program_lines=["ada"])
    assert "HI ada" in text
    assert "AFTER THE PROGRAM" in text, "the program consumed the QUIT"
    assert "GOODBYE" in text


# ---------------------------------------------------------------------------
# 6.2 The optional colon, in the parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line", ["DOS", "CALL 4096", "TAPE ON", "TSYNC"])
def test_an_immediate_command_needs_no_colon(line: str) -> None:
    """Spec 6.2 - "the condition field delimiter may be omitted if desired".

    Only in immediate mode: a *stored* program still needs its colon, because
    the line has to be self-delimiting there.
    """
    program = parse(line, immediate_mode=True)
    assert program.statements[0].command == line.split()[0].partition(":")[0].upper()


def test_a_stored_program_still_needs_the_colon() -> None:
    """The same line without a colon is a syntax error in run mode."""
    with pytest.raises(PilotError):
        parse("DOS")


def test_a_label_line_is_not_given_a_colon() -> None:
    """`*LABEL` becoming `*LABEL:` would read as a continuation (spec 4.4)."""
    program = parse("*LOOP", immediate_mode=True)
    assert program.labels["LOOP"] == 0
    assert program.statements[0].is_label_only


def test_an_unrecognised_line_is_left_alone_to_fail_properly() -> None:
    """Rewriting a bad line would hide the error rather than report it."""
    with pytest.raises(PilotError, match="unknown command"):
        parse("NOTACOMMAND stuff", immediate_mode=True)


# ---------------------------------------------------------------------------
# 10.4 / 10.7 Refusals
# ---------------------------------------------------------------------------


def test_a_headless_repl_reports_the_missing_interactive_host(tmp_path: Path, capsys: Any) -> None:
    """A direct Repl stays headless and gives a clear opt-in host error."""
    _, _ = session(["GR:DRAWTO 30,2", "QUIT"], tmp_path)
    err = capsys.readouterr().err
    assert "GR:" in err
    assert "interactive host" in err
    assert "[interactive]" in err


def test_an_unknown_gr_subcommand_is_not_guessed(tmp_path: Path, capsys: Any) -> None:
    repl, _ = session(["GR:NOTAREALSUB", "QUIT"], tmp_path)
    err = capsys.readouterr().err
    assert "GR:" in err
    assert "sub-command NOTAREALSUB" not in err, "must not invent a name"
    assert repl.running is False, "a refusal is not a reason to leave"


@pytest.mark.parametrize("operand", ["1,100,2", "", "PLAY", "ON"])
def test_so_operands_are_not_subcommands(operand: str) -> None:
    from pypilot.syntax import CommandName

    assert CommandName.subcommand("SO", operand) is None
