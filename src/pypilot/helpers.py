"""Host-environment services that sit outside the PILOT language proper.

Three groups of helpers live here:

* :class:`Os` - program source file load/save, and the ``L:`` (Link) file search
  path used by the ``F`` command family.
* :class:`Shell` - the deferred **program storage area** and the immediate-mode
  commands that edit it (spec 6.2).
* the small operand parsers those commands share.

``Shell`` and ``Os`` are the two surfaces an embedder is most likely to
substitute, so both are kept deliberately thin: ``Shell`` holds text and knows
the immediate-mode command shapes, and leaves running to ``pypilot.runtime``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from pypilot.errors import PilotError
from pypilot.syntax import MAX_LINE_NUMBER, Program, parse

__all__ = ["MAX_LINE_NUMBER", "Os", "Shell", "parse_line_range"]


class Os:
    """Host filesystem access for PILOT programs."""

    @staticmethod
    def load(filename: str | Path) -> str:
        """Read a PILOT program source file and return its text.

        The source is returned as-is; normalisation of line endings and encoding
        happens in the lexer, so this is a thin wrapper that exists mainly so
        tests and embedders can substitute it.

        Raises:
            PilotError: if the file cannot be read.
        """
        path = Path(filename)
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PilotError(f"cannot read program file {str(path)!r}: {exc}") from exc

    @staticmethod
    def save(filename: str | Path, sourcecode: str) -> None:
        """Write PILOT program source text to ``filename``, creating parents.

        Raises:
            PilotError: if the file cannot be written.
        """
        path = Path(filename)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(sourcecode, encoding="utf-8", newline="\n")
        except OSError as exc:
            raise PilotError(f"cannot write program file {str(path)!r}: {exc}") from exc


#: A run of commas and/or blanks, which spec 4.5 makes a single separator.
#:
#: A literal blank rather than ``\s``, so an operand cannot run past the end of
#: the line it is on.
_SEPARATOR: Final = re.compile(r"[,\x20]+")

#: A run of digits, for the numeric operands of the immediate-mode commands.
_NUMBER: Final = re.compile(r"\d+")

#: A leading line number on a stored program line (spec 4.1). ``AUTO:`` and
#: ``REN`` both write one, so anything rewriting a line has to replace it
#: rather than prepend a second.
#:
#: Anchored to the start of the line on purpose. A loose ``\d+`` would happily
#: match the ``6`` in ``C:#A=6`` and silently destroy the statement - which is
#: exactly what it did before the ``^`` went in.
_LEADING_LINE_NUMBER: Final = re.compile(r"^\s*\d+\s+")


def _strip_line_number(line: str) -> str:
    """Remove a leading line number from ``line``, if it has one."""
    return _LEADING_LINE_NUMBER.sub("", line, count=1)


def _parse_start_increment(operand: str, *, command: str, default: int) -> tuple[int, int]:
    """Parse ``[<n> [<sep><n>]]``, the shape shared by ``AUTO`` and ``REN``.

    Both commands take the same operands and both default to 10, and either may
    be omitted alone - ``AUTO 100`` means start at 100, step 10 (spec 6.2.6).

    Raises:
        PilotError: if an operand is present but is not a number.
    """
    parts = [part for part in _SEPARATOR.split(operand.strip()) if part]
    values: list[int] = []
    for part in parts:
        match = _NUMBER.fullmatch(part)
        if match is None:
            raise PilotError(f"{command}: {part!r} is not a line number")
        values.append(int(match.group(0)))

    first = values[0] if len(values) > 0 else default
    increment = values[1] if len(values) > 1 else default
    return first, increment


def parse_line_range(operand: str) -> tuple[int | None, int | None]:
    """Parse a ``LIST`` operand into an optional ``(first, last)`` range.

    Spec 6.2.1 shows ``LIST 100 200`` and ``LIST 500``, with **blanks** as the
    separator - though commas work too, since spec 4.5 makes them
    interchangeable. A null operand means the whole program.

    Raises:
        PilotError: if an operand is present but is not a number.
    """
    parts = [part for part in _SEPARATOR.split(operand.strip()) if part]
    if not parts:
        return None, None
    if len(parts) > 2:
        raise PilotError(f"LIST: takes at most two line numbers, not {operand.strip()!r}")

    values: list[int] = []
    for part in parts:
        match = _NUMBER.fullmatch(part)
        if match is None:
            raise PilotError(f"LIST: {part!r} is not a line number")
        values.append(int(match.group(0)))

    if len(values) == 1:
        return values[0], values[0]
    first, last = values
    if first > last:
        raise PilotError(f"LIST: {first} is after {last}")
    return first, last


class Shell:
    """The deferred program area and the immediate-mode commands over it.

    This is the Atari's *program storage area* - the list of statements waiting
    to be run by ``RUN`` - together with the editing commands that act on it.
    It is a store, not a loop: :mod:`pypilot.cli` drives the REPL and calls in
    here.

    The commands are the immediate-mode half of PILOT (spec 6.2). Note that
    ``AUTO`` and ``REN`` are the only two that are *immediate-mode only* and so
    are rejected inside a stored program (spec 6.2.6, 6.2.7); everything else
    here is legal in both modes.

    ``list``/``run``/``clear`` take their optional operands as **blanks**, not
    commas - ``LIST 100 200`` lists lines 100 through 200, and
    ``LIST 100 , 200`` is the same statement (spec 4.5).
    """

    def __init__(self) -> None:
        """Create an empty program storage area."""
        self.lines: list[str] = []
        """The deferred program, one source line per entry.

        Stored as **text** rather than parsed statements, because ``REN`` and
        ``AUTO`` both renumber and append, and re-parsing text is what a real
        editor does. Holding statements would make renumbering a
        re-serialisation with all the lossiness that implies.
        """

    # -- the program area ---------------------------------------------------

    def __len__(self) -> int:
        return len(self.lines)

    def __bool__(self) -> bool:
        return bool(self.lines)

    def is_empty(self) -> bool:
        """Is the program area empty? ``RUN`` on an empty program is a no-op."""
        return not self.lines

    def append(self, line: str) -> None:
        """Add one statement to the end of the program."""
        self.lines.append(line)

    def source(self) -> str:
        """The program as source text, ready for :func:`pypilot.syntax.parse`."""
        return "\n".join(self.lines)

    def program(self) -> Program:
        """Parse the stored program.

        Raises:
            PilotError: if the stored program does not parse. A statement with a
                syntax error is never stored in the first place (§6.2.6), so
                this means something outside this class wrote a bad line.
        """
        return parse(self.source())

    def clear(self) -> None:
        """Discard the program (the REPL's ``NEW`` on the program area alone).

        This does **not** touch variables - that is :meth:`pypilot.state.PilotState.reset`,
        and ``NEW`` does both. They are separate so a caller can discard the
        program while keeping a lesson's data.
        """
        self.lines.clear()

    # -- 6.2.1 LIST ---------------------------------------------------------

    def listing(self, first: int | None = None, last: int | None = None) -> str:
        """Render the program for ``LIST``, optionally a line range.

        Spec 6.2.1: the whole area, or the portion between two line numbers.
        The numbers used are the statements' *own* line numbers, which for a
        program built by ``AUTO`` are the generated ones.

        Args:
            first: the first line number to show, or ``None`` for the start.
            last: the last line number to show, or ``None`` for the end.
        """
        if not self.lines:
            return "(the program area is empty)"

        shown: list[str] = []
        for number, line in enumerate(self.lines, start=1):
            if first is not None and number < first:
                continue
            if last is not None and number > last:
                continue
            shown.append(f"{number:4}  {line}")
        return "\n".join(shown) if shown else "(no lines in that range)"

    # -- 6.2.7 REN ----------------------------------------------------------

    def renumber(self, first: int = 10, increment: int = 10) -> None:
        """Renumber the program (spec 6.2.7).

        Both operands default to 10. The program is **never reorganised** - only
        the numbers change - so a line-number overflow part-way through leaves
        the program in a correctable state. The spec is explicit that this
        matters: a partially renumbered program that is saved and reloaded
        *would* be reorganised, and then recovery would be impossible.

        Raises:
            PilotError: if a generated line number falls outside 0-9999, having
                first restored the original numbering.
        """
        if increment <= 0:
            raise PilotError("REN: the increment must be positive")

        original = list(self.lines)
        renumbered: list[str] = []
        number = first
        for line in original:
            if not 0 <= number <= MAX_LINE_NUMBER:
                # Put the original numbering back before raising, so the program
                # is left exactly as it was found.
                self.lines = original
                raise PilotError(
                    f"REN: line number {number} is outside the valid range "
                    f"0-{MAX_LINE_NUMBER} (spec 6.2.7); the program is unchanged"
                )
            # Replace any existing leading number rather than prepending to it.
            # A program typed with `AUTO:` already has numbers, and prefixing a
            # second one would produce `10 100 T:HELLO`, which does not parse.
            renumbered.append(f"{number} {_strip_line_number(line)}")
            number += increment
        self.lines = renumbered

    # -- 6.2.6 AUTO ---------------------------------------------------------

    @staticmethod
    def auto_start(first: int = 10, increment: int = 10) -> int:
        """Validate ``AUTO``'s operands and return the first line number.

        Both default to 10. An out-of-range first number is an error, because
        the spec terminates the mode on "the generation of an invalid line
        number" and entering it is no more valid than reaching it.
        """
        if increment <= 0:
            raise PilotError("AUTO: the increment must be positive")
        if not 0 <= first <= MAX_LINE_NUMBER:
            raise PilotError(
                f"AUTO: line number {first} is outside the valid range 0-{MAX_LINE_NUMBER}"
            )
        return first

    def auto_append(self, line: str, number: int) -> None:
        """Append one statement with its generated line number (spec 6.2.6).

        Any line number already on ``line`` is replaced, so a statement pasted
        in from a ``LIST``-ed program does not end up numbered twice.
        """
        self.lines.append(f"{number} {_strip_line_number(line)}")

    @staticmethod
    def parse_auto_operands(operand: str) -> tuple[int, int]:
        """Parse ``AUTO``'s ``[<line#> [<sep><increment>]]`` operands.

        Both default to 10, and either may be omitted alone - ``AUTO 100`` means
        start at 100, step 10.
        """
        return _parse_start_increment(operand, command="AUTO", default=10)

    @staticmethod
    def parse_renumber_operands(operand: str) -> tuple[int, int]:
        """Parse ``REN``'s ``[<line#> [<sep><increment>]]`` operands (spec 6.2.7)."""
        return _parse_start_increment(operand, command="REN", default=10)
