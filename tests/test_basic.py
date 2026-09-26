"""Tests for the package surface: version, error hierarchy, and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from pypilot import __version__
from pypilot.errors import (
    PilotError,
    PilotRuntimeError,
    PilotSyntaxError,
    PilotUndefinedLabelError,
    PilotUnsupportedError,
)
from pypilot.helpers import Os, Shell

ALL_ERRORS = [
    PilotSyntaxError,
    PilotRuntimeError,
    PilotUndefinedLabelError,
    PilotUnsupportedError,
]


def test_version_is_a_string() -> None:
    assert isinstance(__version__, str)
    assert __version__.count(".") == 2


@pytest.mark.parametrize("error_type", ALL_ERRORS)
def test_every_error_derives_from_pilot_error(error_type: type[Exception]) -> None:
    assert issubclass(error_type, PilotError)


def test_pilot_error_without_line_reports_plain_message() -> None:
    assert str(PilotError("boom")) == "boom"


def test_pilot_error_with_line_reports_location() -> None:
    err = PilotError("boom", line=7)
    assert str(err) == "line 7: boom"


def test_pilot_error_with_line_and_source_echoes_source() -> None:
    err = PilotError("boom", line=3, source="T:Hello\n")
    rendered = str(err)
    assert "line 3: boom" in rendered
    assert "T:Hello" in rendered


class TestOs:
    """The host filesystem helpers must round-trip program source."""

    def test_save_then_load(self, tmp_path: Path) -> None:
        path = tmp_path / "prog.pilot"
        Os.save(path, "T:Hello\nA:$NAME\n")
        assert Os.load(path) == "T:Hello\nA:$NAME\n"

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "deeper" / "prog.pilot"
        Os.save(path, "T:Hello\n")
        assert path.is_file()

    def test_save_uses_lf_line_endings(self, tmp_path: Path) -> None:
        path = tmp_path / "prog.pilot"
        Os.save(path, "T:Hello\n")
        assert path.read_bytes() == b"T:Hello\n"

    def test_load_missing_file_raises_pilot_error(self, tmp_path: Path) -> None:
        with pytest.raises(PilotError, match="cannot read program file"):
            Os.load(tmp_path / "nope.pilot")

    def test_save_into_non_directory_raises_pilot_error(self, tmp_path: Path) -> None:
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        with pytest.raises(PilotError, match="cannot write program file"):
            Os.save(blocker / "child.pilot", "T:Hello\n")


class TestShell:
    """The program storage area and the immediate-mode commands.

    The behaviour lives in ``tests/test_repl.py``, which drives a real session
    with a scripted input device. What is worth checking *here*, next to
    `Os`, is that the storage area is a real container and that a program
    written into it round-trips.
    """

    def test_a_new_shell_is_empty(self) -> None:
        shell = Shell()
        assert shell.is_empty()
        assert len(shell) == 0
        assert not shell

    def test_appending_makes_it_non_empty(self) -> None:
        shell = Shell()
        shell.append("T:HELLO")
        assert not shell.is_empty()
        assert len(shell) == 1
        assert bool(shell)

    def test_the_stored_program_round_trips_through_the_parser(self) -> None:
        shell = Shell()
        for line in ("T:HELLO", "C:#A=1", "E:"):
            shell.append(line)
        program = shell.program()
        assert [s.command for s in program] == ["T", "C", "E"]

    def test_clearing_empties_it(self) -> None:
        shell = Shell()
        shell.append("T:HELLO")
        shell.clear()
        assert shell.is_empty()
