"""Tests for the I/O device abstraction.

``io.py`` exists so a program's output can be captured in a test rather than
only reaching a terminal. These tests pin the devices themselves, since every
interpreter test depends on them being right.
"""

from __future__ import annotations

import io as _io

import pytest

from pypilot.errors import PilotRuntimeError
from pypilot.io import (
    BufferInput,
    BufferOutput,
    ConsoleOutput,
    InputDevice,
    NullInput,
    OutputDevice,
    StringInput,
)

# ---------------------------------------------------------------------------
# BufferOutput
# ---------------------------------------------------------------------------


def test_buffer_output_collects_writes() -> None:
    out = BufferOutput()
    out.write("HELLO")
    out.newline()
    assert out.text == "HELLO\n"
    assert out.lines == ["HELLO"]


def test_buffer_output_starts_from_an_initial_value() -> None:
    assert BufferOutput("seed").text == "seed"


def test_buffer_output_clear() -> None:
    out = BufferOutput("something")
    out.clear()
    assert out.text == ""


def test_buffer_output_flush_is_a_no_op() -> None:
    out = BufferOutput()
    out.flush()
    assert out.text == ""


def test_buffer_output_str_matches_text() -> None:
    out = BufferOutput()
    out.write("X")
    assert str(out) == out.text == "X"


def test_buffer_output_satisfies_the_protocol() -> None:
    assert isinstance(BufferOutput(), OutputDevice)


# ---------------------------------------------------------------------------
# ConsoleOutput
# ---------------------------------------------------------------------------


def test_console_output_writes_to_a_stream() -> None:
    stream = _io.StringIO()
    out = ConsoleOutput(stream)
    out.write("HELLO")
    out.newline()
    out.flush()
    assert stream.getvalue() == "HELLO\n"


def test_console_output_defaults_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    out = ConsoleOutput()
    out.write("TO STDOUT")
    out.newline()
    out.flush()
    assert "TO STDOUT" in capsys.readouterr().out


def test_console_output_flush_without_a_stream_is_safe() -> None:
    """``ConsoleOutput()`` has no stream to flush; it must not raise."""
    ConsoleOutput().flush()


def test_console_output_satisfies_the_protocol() -> None:
    assert isinstance(ConsoleOutput(_io.StringIO()), OutputDevice)


# ---------------------------------------------------------------------------
# StringInput
# ---------------------------------------------------------------------------


def test_string_input_serves_lines_in_order() -> None:
    feed = StringInput(["first", "second"])
    assert feed.read_line() == "first"
    assert feed.read_line() == "second"


def test_string_input_strips_terminators() -> None:
    assert StringInput(["line\n"]).read_line() == "line"


def test_string_input_reports_exhaustion() -> None:
    feed = StringInput(["only"])
    feed.read_line()
    assert feed.exhausted
    with pytest.raises(PilotRuntimeError, match="end of input"):
        feed.read_line()


def test_string_input_starts_exhausted_when_empty() -> None:
    feed = StringInput()
    assert feed.exhausted
    assert feed.remaining() == 0


def test_string_input_remaining_counts_down() -> None:
    feed = StringInput(["a", "b", "c"])
    assert feed.remaining() == 3
    feed.read_line()
    assert feed.remaining() == 2


def test_string_input_iterates_over_the_remainder() -> None:
    feed = StringInput(["a", "b", "c"])
    feed.read_line()
    assert list(feed) == ["b", "c"]


def test_string_input_satisfies_the_protocol() -> None:
    assert isinstance(StringInput([]), InputDevice)


# ---------------------------------------------------------------------------
# BufferInput and NullInput
# ---------------------------------------------------------------------------


def test_buffer_input_splits_a_string_into_lines() -> None:
    feed = BufferInput("one\ntwo\nthree")
    assert feed.read_line() == "one"
    assert feed.read_line() == "two"
    assert feed.read_line() == "three"


def test_buffer_input_reports_exhaustion() -> None:
    feed = BufferInput("only")
    feed.read_line()
    with pytest.raises(PilotRuntimeError, match="end of input"):
        feed.read_line()


def test_buffer_input_from_empty_text_is_exhausted() -> None:
    with pytest.raises(PilotRuntimeError, match="end of input"):
        BufferInput("").read_line()


def test_null_input_always_reports_end_of_file() -> None:
    """A program must not block on a terminal it was not given input for."""
    with pytest.raises(PilotRuntimeError, match="end of input"):
        NullInput().read_line()


def test_null_input_satisfies_the_protocol() -> None:
    assert isinstance(NullInput(), InputDevice)
