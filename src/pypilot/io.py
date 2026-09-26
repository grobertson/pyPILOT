"""Input and output devices for the pyPILOT interpreter.

``SPEC.md`` section 11 Stage 4 requires an I/O abstraction so that output is
capturable in tests: a program that types text must be able to run with its
output going to a string buffer, not only to a terminal.

Two protocols and four implementations:

* :class:`OutputDevice` - :class:`ConsoleOutput` and :class:`BufferOutput`
* :class:`InputDevice` - :class:`StringInput` and :class:`NullInput`

The Atari device model proper - ``READ``/``WRITE``/``CLOSE`` over ``C``/``D``/
``S``/``K`` - is Stage 7's job, in ``devices.py``. What lives here is the
primitive the rest of the interpreter is written against.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Iterator
from typing import Protocol, TextIO, runtime_checkable

from pypilot.errors import PilotRuntimeError

__all__ = [
    "BufferInput",
    "BufferOutput",
    "ConsoleInput",
    "ConsoleOutput",
    "InputDevice",
    "NullInput",
    "OutputDevice",
    "StringInput",
]


@runtime_checkable
class OutputDevice(Protocol):
    """Where typed text goes."""

    def write(self, text: str) -> None:
        """Write ``text`` verbatim, with no trailing newline added."""

    def newline(self) -> None:
        """End the current line."""

    def flush(self) -> None:
        """Push any buffered text onward."""


@runtime_checkable
class InputDevice(Protocol):
    """Where accepted input comes from."""

    def read_line(self) -> str:
        """Return one line of input, without its terminator.

        Raises:
            PilotRuntimeError: when input is exhausted, so the interpreter can
                turn it into the end-of-file condition a PILOT program expects.
        """


class ConsoleOutput:
    """Writes to a Python text stream, ``sys.stdout`` by default.

    Used for the terminal, and the model the test implementations mirror.
    """

    __slots__ = ("_stream",)

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream

    def write(self, text: str) -> None:
        stream = self._stream
        if stream is None:
            stream = sys.stdout
        stream.write(text)

    def newline(self) -> None:
        self.write("\n")

    def flush(self) -> None:
        if self._stream is not None:
            self._stream.flush()


class BufferOutput:
    """Collects output in a string, so tests can assert on it.

    >>> out = BufferOutput()
    >>> out.write("HI")
    >>> out.newline()
    >>> out.text
    'HI\\n'
    """

    __slots__ = ("_parts",)

    def __init__(self, initial: str = "") -> None:
        self._parts: list[str] = [initial] if initial else []

    def write(self, text: str) -> None:
        self._parts.append(text)

    def newline(self) -> None:
        self._parts.append("\n")

    def flush(self) -> None:
        """No-op; a buffer has nowhere to flush to."""

    @property
    def text(self) -> str:
        """Everything written so far."""
        return "".join(self._parts)

    @property
    def lines(self) -> list[str]:
        """The output split into lines, with no trailing empty element."""
        return self.text.splitlines()

    def clear(self) -> None:
        self._parts.clear()

    def __str__(self) -> str:
        return self.text


class StringInput:
    """Serves input from a list of lines, then reports end of file.

    This is how a test scripts a program's input::

        feed = StringInput(["yes", "no"])
        assert feed.read_line() == "yes"
    """

    __slots__ = ("_index", "_lines")

    def __init__(self, lines: Iterable[str] | None = None) -> None:
        self._lines = [line.rstrip("\n") for line in (lines or [])]
        self._index = 0

    def read_line(self) -> str:
        if self._index >= len(self._lines):
            raise PilotRuntimeError("end of input")
        line = self._lines[self._index]
        self._index += 1
        return line

    @property
    def exhausted(self) -> bool:
        """Has every line been consumed?"""
        return self._index >= len(self._lines)

    def remaining(self) -> int:
        return len(self._lines) - self._index

    def __iter__(self) -> Iterator[str]:
        return iter(self._lines[self._index :])


class BufferInput:
    """Serves input from a single string, splitting it into lines."""

    __slots__ = ("_iterator",)

    def __init__(self, text: str = "") -> None:
        self._iterator = iter(text.splitlines())

    def read_line(self) -> str:
        try:
            return next(self._iterator)
        except StopIteration:
            raise PilotRuntimeError("end of input") from None


class ConsoleInput:
    """Reads a line from a Python text stream, ``sys.stdin`` by default.

    This is the REPL's input device. End-of-file is reported as a
    :class:`~pypilot.errors.PilotRuntimeError` like every other input device, so
    the REPL loop can treat "the user pressed Ctrl-D" and "the script ran out"
    identically.
    """

    __slots__ = ("_stream",)

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream

    def read_line(self) -> str:
        stream = self._stream
        if stream is None:
            stream = sys.stdin
        line = stream.readline()
        if line == "":
            raise PilotRuntimeError("end of input")
        return line.rstrip("\n")


class NullInput:
    """Always reports end of file.

    The default for a program that has not asked for input, so running a
    non-interactive program does not block on a terminal.
    """

    __slots__ = ()

    def read_line(self) -> str:
        raise PilotRuntimeError("end of input")
