"""Tests for the ``pypilot`` command-line entry point."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from pypilot import __version__
from pypilot.cli import build_parser, check_program, main

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_parser_accepts_a_program_path() -> None:
    assert build_parser().parse_args(["lesson.pilot"]).program == "lesson.pilot"


def test_parser_program_is_optional() -> None:
    args = build_parser().parse_args([])
    assert args.program is None
    assert args.check is False
    assert args.list is False
    assert args.interactive is False
    assert args.trace is False


@pytest.mark.parametrize(
    "flag", ["-c", "--check", "-l", "--list", "-i", "--interactive", "--trace"]
)
def test_parser_flags(flag: str) -> None:
    assert build_parser().parse_args([flag]) is not None


def test_version_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------


def test_no_program_starts_the_repl(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No file means the interactive session (spec 6.2).

    Feeding it a scripted `QUIT` is the only way to test this without a
    terminal, and it also pins that the REPL exits cleanly on its own.
    """
    monkeypatch.setattr("sys.stdin", io.StringIO("T:HELLO FROM THE REPL\nQUIT\n"))
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "HELLO FROM THE REPL" in out
    assert "GOODBYE" in out


def test_check_without_a_file_is_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    """`--check` inspects a file; with no file there is nothing to inspect."""
    assert main(["--check"]) == 1
    assert "needs a program file" in capsys.readouterr().err


@pytest.mark.parametrize(
    "name",
    [
        "greeter.pilot",
        "numbers.pilot",
        "adventure.pilot",
        "msplit.pilot",
        "recurse.pilot",
        "graphics.pilot",
    ],
)
def test_check_succeeds_for_every_example(name: str) -> None:
    code, output = check_program(str(EXAMPLES / name))
    assert code == 0, output
    assert "parsed" in output


def test_check_list_names_every_statement(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check", "--list", str(EXAMPLES / "adventure.pilot")]) == 0
    out = capsys.readouterr().out
    assert "*START" in out
    assert "JM:*NORTH,*SOUTH" in out


def test_check_marks_refused_commands(capsys: pytest.CaptureFixture[str]) -> None:
    """Spec 10.4 - `GR:` is real ATARI PILOT, refused only at run time."""
    assert main(["--check", "--list", str(EXAMPLES / "graphics.pilot")]) == 0
    out = capsys.readouterr().out
    assert "GR:CLEAR" in out
    assert "refused at run time" in out


def test_check_reports_a_syntax_error_with_line_and_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Spec 12 - a runtime error must name the line and echo the source."""
    bad = tmp_path / "bad.pilot"
    bad.write_text("T:HELLO\nFO:1,DATA\n", encoding="utf-8")
    assert main(["--check", str(bad)]) == 1
    err = capsys.readouterr().err
    assert "line 2" in err
    assert "FO:1,DATA" in err
    assert "READ:" in err, "the error should suggest the ATARI equivalent"


def test_check_reports_a_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check", "does-not-exist.pilot"]) == 1
    assert "cannot read program file" in capsys.readouterr().err


def test_check_returns_nonzero_for_a_syntax_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pilot"
    bad.write_text("T:ok\nW:5\n", encoding="utf-8")
    code, output = check_program(str(bad))
    assert code == 1
    assert "PA:" in output


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def test_running_a_trivial_program_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Spec 12 - exit 0 on success, and the program's output reaches stdout."""
    program = tmp_path / "hello.pilot"
    program.write_text("T:HELLO FROM pyPILOT\n", encoding="utf-8")
    assert main([str(program)]) == 0
    assert "HELLO FROM pyPILOT" in capsys.readouterr().out


def test_running_a_whole_program(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A program using only T, R and C runs end to end (Stage 4 acceptance)."""
    program = tmp_path / "demo.pilot"
    program.write_text("R:sum two numbers\nT:THE ANSWER IS\nC:#A=2+3\nT:#A\n", encoding="utf-8")
    assert main([str(program)]) == 0
    out = capsys.readouterr().out
    assert "THE ANSWER IS" in out
    assert "5" in out


def test_running_a_program_with_a_runtime_error_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    program = tmp_path / "bad.pilot"
    program.write_text("T:FINE\nC:#XY=1\n", encoding="utf-8")
    assert main([str(program)]) == 1
    err = capsys.readouterr().err
    assert "line 2" in err
    assert "C:#XY=1" in err


def test_running_a_refused_command_says_why_it_cannot_be_honoured(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Spec 10.4 - `GR:` is real ATARI PILOT, refused with a clear message.

    This replaced a test that asserted an *unimplemented* statement named its
    stage. Every run-mode command is implemented as of Stage 7, so there is no
    longer a pending handler to point at - and the one that had been used, `J:`,
    was a poor choice anyway, since an unconditioned `J:` to itself loops
    forever. The refusal path is the behaviour worth pinning now.
    """
    program = tmp_path / "draw.pilot"
    program.write_text("T:BEFORE\nGR:CLEAR\n", encoding="utf-8")
    assert main([str(program)]) == 1
    err = capsys.readouterr().err
    assert "GR:" in err
    assert "10.4" in err, "the message must point at the spec section"


def test_a_runaway_jump_loop_is_reported_rather_than_hanging(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`J:` makes an accidental infinite loop a one-character slip.

    A teaching language that hangs teaches nothing, so the run gives up with a
    message naming the limit instead of spinning forever.
    """
    program = tmp_path / "jumpy.pilot"
    program.write_text("*LOOP\nJ:*LOOP\n", encoding="utf-8")
    assert main([str(program)]) == 1
    err = capsys.readouterr().err
    assert "without finishing" in err
    assert "J:" in err


def test_running_a_program_with_a_refused_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Spec 10.4 - `GR:` is real ATARI PILOT, refused with a clear message.

    The message must **name the sub-command**. "GR: is not implemented" leaves
    a learner wondering whether they mistyped it; naming `CLEAR` says the
    program was understood and the hardware is what is missing.
    """
    program = tmp_path / "draw.pilot"
    program.write_text("GR:CLEAR\n", encoding="utf-8")
    assert main([str(program)]) == 1
    err = capsys.readouterr().err
    assert "CLEAR" in err, "the refusal must name the sub-command that was asked for"
    assert "10.4" in err
    assert "refused" in err, "refused, not pending - nothing is ever going to arrive"


def test_a_refusal_says_refused_rather_than_not_implemented_yet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`GR:` will never be implemented here, so promising otherwise is a lie."""
    program = tmp_path / "draw.pilot"
    program.write_text("GR:DRAW\n", encoding="utf-8")
    assert main([str(program)]) == 1
    err = capsys.readouterr().err
    assert "DRAW" in err
    assert "not implemented yet" not in err


def test_trace_goes_to_stderr_not_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Spec 12 - trace output must not mix with the program's own output."""
    program = tmp_path / "demo.pilot"
    program.write_text("T:ONE\nT:TWO\n", encoding="utf-8")
    assert main(["--trace", str(program)]) == 0
    captured = capsys.readouterr()
    assert "ONE" in captured.out
    assert "trace" in captured.err
    assert "trace" not in captured.out


def test_running_a_broken_program_reports_the_syntax_error_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The more useful message wins: a real error, not "not implemented"."""
    bad = tmp_path / "bad.pilot"
    bad.write_text("NOPE:X\n", encoding="utf-8")
    assert main([str(bad)]) == 1
    err = capsys.readouterr().err
    assert "unknown command" in err
