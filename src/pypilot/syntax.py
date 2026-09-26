"""Lexing and parsing for ATARI PILOT.

This module turns PILOT source text into a
:class:`~pypilot.syntax.Program` of :class:`~pypilot.syntax.Statement` objects. It implements ``SPEC.md`` sections 4.1-4.5:

* optional leading line numbers, range 0-9999 (4.1)
* labels of any length, which may share a line with a command (4.2)
* command names of one or two letters, matched exactly (4.2)
* conditions: ``Y``, ``N``, ``(expression)``, or a combination (4.2)
* ``[`` ... EOL comments (4.2)
* comma/blank field delimiting (4.3)
* command continuation after ``T``, ``Y``, ``N``, ``R`` only (4.4)

Deliberately **not** implemented here, because the spec defers them to later
stages: text-expression expansion, arithmetic evaluation, and the
accept-buffer rules. Those all need the operand text, which this module
preserves verbatim.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Final

from pypilot.errors import PilotSyntaxError

__all__ = [
    "CONTINUABLE",
    "DEFAULT_CONTINUATION",
    "MAX_LINE_NUMBER",
    "REJECTED",
    "CommandName",
    "Condition",
    "Parser",
    "Program",
    "Statement",
    "decode_source",
    "parse",
]

#: The highest line number the Atari Screen Editor could assign (spec 4.1).
MAX_LINE_NUMBER: Final = 9999

#: Commands a bare ``:`` statement may continue (spec 4.4).
#: Commands a bare ``:`` statement may continue (spec 4.4). ``Y`` and ``N`` are
#: absent because spec 6.1.1 makes them abbreviations for ``TY``/``TN``, so they
#: resolve to ``T`` - which is here - before continuation is considered.
CONTINUABLE: Final[frozenset[str]] = frozenset({"T", "R"})

#: The default continuation command, restored at startup and after any error.
DEFAULT_CONTINUATION: Final = "T"


class CommandName:
    """The ATARI PILOT command vocabulary, grouped by role.

    This is the single place that knows which command names exist. It drives
    both dispatch (spec 9.1) and the rejection of Core PILOT commands that do
    not exist in ATARI PILOT (spec 10.6) - those are listed in ``REJECTED`` so
    they produce a good error message rather than being silently accepted.
    """

    # Core commands, one-letter names, all to be implemented in 1.0.
    CORE: Final[frozenset[str]] = frozenset({"A", "C", "E", "J", "M", "N", "R", "T", "U", "Y"})

    # Atari extensions relevant to the language, implemented in 1.0.
    ATARI_LANGUAGE: Final[frozenset[str]] = frozenset(
        {"MS", "JM", "PA", "PCS", "VNEW", "DUMP", "READ", "WRITE", "CLOSE", "LOAD", "SAVE", "TRACE"}
    )

    # Device-dependent commands: real ATARI PILOT, parsed but refused (spec 10.4).
    ATARI_DEVICE: Final[frozenset[str]] = frozenset({"GR", "SO"})

    # Commands that parse but are refused (spec 10.7).
    REFUSED: Final[frozenset[str]] = frozenset({"CALL", "TAPE", "TSYNC", "DOS"})

    # The `GR:` sub-commands of spec 6.1.12, used only to *name* one in a
    # refusal message.
    #
    # A refusal that says merely "GR: is not implemented" leaves a learner
    # wondering whether they mistyped it or asked for something impossible. The
    # Atari manual lists fifteen sub-commands, so naming the one that was
    # actually requested turns a dead end into a diagnosis. This is a message
    # table, not a parser: the operand is never interpreted, because nothing
    # about it can be honoured.
    GR_SUBCOMMANDS: Final[tuple[str, ...]] = (
        "CLEAR",
        "PEN",
        "GOTO",
        "DRAWTO",
        "FILLTO",
        "TURNTO",
        "DRAW",
        "FILL",
        "TURN",
        "CHAR",
        "COLOR",
        "MODE",
        "SETCLR",
        "CLR",
        "TEXT",
    )

    # The `SO:` operands of spec 6.1.13, for the same reason as `GR_SUBCOMMANDS`.
    SO_SUBCOMMANDS: Final[tuple[str, ...]] = ("ON", "OFF", "PLAY", "STOP")

    # Immediate-mode-only commands; invalid in a run-mode program (spec 10.8).
    IMMEDIATE_ONLY: Final[frozenset[str]] = frozenset({"AUTO", "REN"})

    # Two-letter spellings of the one-letter Type commands. Spec 6.1.1:
    # `Y` is an abbreviation for `TY` and `N` for `TN`, so all of these
    # resolve to `T` with a match condition rather than to a command of
    # their own.
    CORE_ALIASES: Final[dict[str, str]] = {
        "TY": "Y",
        "TN": "N",
        "YY": "Y",
        "YN": "Y",
        "NN": "N",
        "NY": "N",
    }

    @classmethod
    def all(cls) -> frozenset[str]:
        """Every command name a program may use, including the two-letter forms."""
        return (
            cls.CORE
            | cls.ATARI_LANGUAGE
            | cls.ATARI_DEVICE
            | cls.REFUSED
            | cls.IMMEDIATE_ONLY
            | frozenset(cls.CORE_ALIASES)
        )

    @classmethod
    def canonical(cls, name: str) -> str:
        """Resolve a two-letter core alias to its one-letter command.

        ``TY``/``TN`` are the general forms of ``Y:``/``N:`` (spec 7.3), so
        ``TY:`` and ``Y:`` mean the same thing. Everything else is returned
        unchanged.
        """
        return cls.CORE_ALIASES.get(name.upper(), name.upper())

    @classmethod
    def is_command(cls, name: str) -> bool:
        """Is ``name`` a known command?"""
        return name.upper() in cls.all()

    @classmethod
    def subcommand(cls, command: str, operand: str) -> str | None:
        """Name the ``GR:``/``SO:`` sub-command in ``operand``, if there is one.

        Used only to make a refusal diagnostic. A sub-command is the first
        alphabetic run of the operand, so ``DRAWTO 30,2`` names ``DRAWTO`` and
        not ``DRAW`` - the longest match is what the reader meant, and the
        Atari manuals write the full word.

        Returns ``None`` when the operand does not name a known sub-command, in
        which case the caller should say so rather than guess.
        """
        upper = operand.strip().upper()
        if not upper:
            return None
        known = cls.GR_SUBCOMMANDS if command == "GR" else cls.SO_SUBCOMMANDS
        word = "".join(char for char in upper if char.isalpha())
        for size in range(min(len(word), 12), 0, -1):
            candidate = word[:size]
            if candidate in known:
                return candidate
        return None

    @classmethod
    def is_refused(cls, name: str) -> bool:
        """Is ``name`` one that parses but raises ``PilotUnsupportedError``?"""
        upper = name.upper()
        return upper in cls.ATARI_DEVICE or upper in cls.REFUSED

    @classmethod
    def is_immediate_only(cls, name: str) -> bool:
        """Is ``name`` valid only at the REPL, not in a run-mode program?"""
        return name.upper() in cls.IMMEDIATE_ONLY


#: Core PILOT commands that do not exist in ATARI PILOT. Using one is an error,
#: not something to ignore - a Core PILOT program that appeared to run while
#: doing the wrong thing would be the worst possible failure (spec 10.6).
REJECTED: Final[dict[str, str]] = {
    "FA": "ATARI PILOT has no file handles; use READ:/WRITE: (spec 9.6)",
    "FB": "ATARI PILOT has no file handles; use READ:/WRITE: (spec 9.6)",
    "FC": "ATARI PILOT has no file handles; use CLOSE: (spec 9.6)",
    "FD": "ATARI PILOT has no file handles; use DOS: at the REPL (spec 9.6)",
    "FO": "ATARI PILOT has no file handles; use READ: (spec 9.6)",
    "FR": "ATARI PILOT has no file handles; use READ: (spec 9.6)",
    "FW": "ATARI PILOT has no file handles; use WRITE: (spec 9.6)",
    "F": "ATARI PILOT has no F command; use READ:/WRITE:/CLOSE: (spec 9.6)",
    "P": "P: (Problem/Parameters) is not an ATARI command (spec 10.6)",
    "W": "W: (Wait) is not an ATARI command; use PA: (spec 9.5)",
    "CS": "CS: is not an ATARI command; the accept buffer is always upper case (spec 7.2.2)",
    "CN": "CN: is not an ATARI command; use PCS: (spec 9.5)",
    "LS": "LIST is immediate-mode only, spelled LIST (spec 10.8)",
    "RU": "RUN is immediate-mode only, spelled RUN (spec 10.8)",
}


@dataclass(frozen=True, slots=True)
class Condition:
    """A statement's condition: a match test, an arithmetic test, or both.

    The two are **conjunctive** - when both are present the statement runs only
    if both hold (spec 4.4).
    """

    match: str | None = None
    """``"Y"`` (last match succeeded), ``"N"`` (it did not), or ``None``."""

    expression: str | None = None
    """Raw ``(expression)`` text without the parentheses, or ``None``."""

    def __bool__(self) -> bool:
        return self.match is not None or self.expression is not None

    def __str__(self) -> str:
        parts = [p for p in (self.match, f"({self.expression})" if self.expression else None) if p]
        return "".join(parts)


@dataclass(frozen=True, slots=True)
class Statement:
    """A single parsed PILOT statement.

    Frozen so statements can be shared, cached, and indexed by label; all
    mutable interpreter state lives in ``state.PilotState`` (spec 5.1).
    """

    command: str
    """Upper-case command name, e.g. ``"T"``, ``"TY"``, ``"GR"``."""

    params: str = ""
    """Text right of the colon, verbatim. Blanks are significant (spec 4.3)."""

    label: str | None = None
    """Label with the ``*`` stripped. Case is preserved (spec 4.2)."""

    condition: Condition | None = None
    """Condition, or ``None`` when the statement is unconditional."""

    comment: str | None = None
    """Text inside ``[`` ... ``]``, or ``None``."""

    source: str = ""
    """The original source line, for error messages."""

    line_number: int = 0
    """1-based line number assigned by the loader (spec 4.1)."""

    continued: bool = False
    """True when this statement inherited its command from the line above."""

    @property
    def is_continuation(self) -> bool:
        """True for a statement that opened with ``:`` and inherited its command.

        Distinct from ``command == ""``, which also covers a label-only line and
        a comment-only line - neither of which is a continuation.
        """
        return self.continued

    @property
    def is_label_only(self) -> bool:
        """True for a bare ``*LABEL`` line carrying no command."""
        return self.command == "" and self.label is not None and not self.continued

    def __str__(self) -> str:
        if self.command == "" and not self.continued:
            # Label-only, comment-only and blank lines have no fields to
            # re-render, and re-rendering would be lossy - a comment has no
            # closing delimiter, so `str()` cannot know whether the original
            # line ended with a `]` or not. The source line round-trips exactly.
            return self.source.rstrip()
        out = f"*{self.label} " if self.label else ""
        out += self.command
        if self.condition:
            out += str(self.condition)
        out += f":{self.params}"
        if self.comment is not None:
            out += f"[{self.comment}]"
        return out


@dataclass(frozen=True, slots=True)
class Program:
    """A parsed program: an ordered list of statements plus a label index.

    The label index is built here so that ``J:`` and ``U:`` are a dict lookup
    rather than a linear scan - the hottest path in any PILOT program
    (spec 8.1). First writer wins, matching the Atari rule that the lowest line
    number wins when labels are duplicated (spec 4.2).
    """

    statements: tuple[Statement, ...] = field(default=())

    labels: dict[str, int] = field(default_factory=dict, compare=False)

    def __len__(self) -> int:
        return len(self.statements)

    def __iter__(self) -> Iterator[Statement]:
        return iter(self.statements)

    def resolve(self, label: str) -> int | None:
        """Index of the statement carrying ``label``, or ``None``.

        The leading ``*`` is optional in a ``J:``/``U:`` operand, matching most
        implementations (spec 10.2).
        """
        return self.labels.get(label.lstrip("*"))

    @property
    def source(self) -> str:
        """The program as text, one statement per line."""
        return "\n".join(str(s) for s in self.statements)


def decode_source(data: bytes | str) -> str:
    """Decode PILOT source text, falling back through a legacy chain (spec 4.1).

    A 1980s lesson may be ATASCII, CP437, or Latin-1. UTF-8 is tried first, then
    the platform encoding, then Latin-1 with replacement - which always
    succeeds, so this never raises.
    """
    if isinstance(data, str):
        return data
    for encoding in ("utf-8", "cp437", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


#: A leading line number: digits, range-checked by the parser.
_LINE_NUMBER_RE: Final = re.compile(r"\s*(\d+)")

#: A label: ``*`` then alphanumerics to end of token.
_LABEL_RE: Final = re.compile(r"\*([A-Za-z0-9]+)")

#: The letters that make up a match condition (spec 4.2).
#:
#: Any command may carry one, so this is what separates a real command from a
#: command-plus-condition spelling. ``EY:`` is `E` with a `Y` condition (spec
#: 6.1.10), while ``CN:`` is the rejected Core PILOT cursor command - the same
#: two-letter shape, entirely different meaning, and the second letter is what
#: tells them apart.
_CONDITION_LETTERS: Final = frozenset({"Y", "N"})

#: A command name: a run of letters. Atari command names range from one letter
#: (`T`) to five (`TSYNC`), and the scanner must find the *longest* known one,
#: so `CN:` is rejected as the Core PILOT cursor command rather than mistaken
#: for `C` followed by junk. Spec 4.3 forbids short and long forms alike, so
#: `TYPEN:` is `TY` plus junk rather than a forgiving `TY`.
_COMMAND_RE: Final = re.compile(r"[A-Za-z]+")

#: The longest command name in the Atari vocabulary, used to bound the scan.
_MAX_COMMAND_NAME: Final = 5


class Parser:
    """Parses PILOT source text into a :class:`~pypilot.syntax.Program`.

    The parser is a sequence of small field scanners rather than a fixed split,
    mirroring the Atari rule that *every field is delimited by the first
    character not valid for that field* (spec 4.3).
    """

    def __init__(self, *, immediate_mode: bool = False) -> None:
        """Create a parser.

        Args:
            immediate_mode: when true, a bare ``:`` statement may continue any
                command, not just ``T``, ``Y``, ``N`` and ``R`` (spec 4.4).
        """
        self._immediate_mode = immediate_mode

    # -- public API ---------------------------------------------------------

    def parse(self, text: str) -> Program:
        """Parse ``text`` into a :class:`~pypilot.syntax.Program`.

        Raises:
            PilotSyntaxError: on any malformed line, with the line number and
                source line attached.
        """
        statements: list[Statement] = []
        labels: dict[str, int] = {}
        # Command and condition inherited by a continuation line.
        last_command: str = DEFAULT_CONTINUATION
        last_condition: Condition | None = None
        line_number = 0

        for raw in self._iter_lines(text):
            line_number += 1
            if not raw.strip():
                continue

            raw = self._supply_colon(raw, line_number)
            statement = self._parse_line(raw, line_number)

            if statement.is_continuation:
                # A line opening with ':' carries no command of its own; it
                # inherits command *and* condition from the statement above
                # (spec 4.4).
                self._check_continuable(last_command, raw, line_number)
                statement = self._as_continuation(statement, last_command, last_condition)
            elif statement.is_label_only:
                # A label line does not change the continuation command.
                pass
            else:
                last_command = statement.command
                last_condition = statement.condition

            if statement.label is not None:
                # First writer wins; ATARI does not diagnose duplicates (spec 4.2).
                labels.setdefault(statement.label, len(statements))

            statements.append(statement)

        return Program(tuple(statements), labels)

    # -- line splitting -----------------------------------------------------

    def _supply_colon(self, raw: str, line_number: int) -> str:
        """Insert the optional colon immediate mode allows (spec 6.2).

        "For the immediate mode only commands, the condition field delimiter
        (`:`) may be omitted if desired. Thus, for example, either `RUN` or
        `RUN:` will be accepted as a legal form of the Run command."

        Two things must *not* be touched:

        * a **label-only** line, because `*LABEL` becoming `*LABEL:` would read
          as a continuation of the line above (spec 4.4);
        * a line that already has a colon, or one that is already a
          continuation.

        A bare `*` prefix or a leading `:` marks those cases, and anything that
        does not start with a known command word is left alone so a genuinely
        malformed line still produces a proper syntax error rather than being
        silently rewritten.
        """
        if not self._immediate_mode or ":" in raw:
            return raw
        stripped = raw.lstrip()
        if stripped.startswith(("*", ":")):
            return raw

        match = _COMMAND_RE.match(stripped)
        if match is None:
            return raw
        letters = match.group(0)
        if not CommandName.is_command(letters.upper()):
            return raw

        # Insert the colon after the command word, keeping whatever followed it.
        offset = len(raw) - len(stripped) + match.end()
        return f"{raw[:offset]}:{raw[offset:]}"

    @staticmethod
    def _iter_lines(text: str) -> list[str]:
        """Split ``text`` into lines, honouring LF, CRLF and lone CR (spec 4.1)."""
        normalised = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalised.split("\n")

    # -- one line -----------------------------------------------------------

    def _parse_line(self, raw: str, line_number: int) -> Statement:
        """Parse a single non-blank line into a :class:`~pypilot.syntax.Statement`."""
        rest = self._strip_line_number(raw, line_number)
        rest, comment = self._strip_comment(rest)
        # Only leading blanks are insignificant. Trailing blanks to the right of
        # the colon are operand data (spec 4.3) - `M:YES,SURE_` relies on the
        # underscore form precisely because trailing blanks are preserved, so
        # stripping here would make that idiom meaningless.
        rest = rest.lstrip()

        if not rest:
            # A line holding only a comment, or only line numbers. It keeps its
            # place in the numbering but carries no command.
            return Statement(command="", comment=comment, source=raw, line_number=line_number)

        label: str | None = None
        if rest.startswith("*"):
            match = _LABEL_RE.match(rest)
            if match is None:
                raise self._error("a label must be '*' followed by alphanumerics", raw, line_number)
            label = match.group(1)
            rest = rest[match.end() :].lstrip()

        if not rest:
            return Statement(
                command="", label=label, comment=comment, source=raw, line_number=line_number
            )

        if not rest.startswith(":"):
            command, rest = self._take_command(rest, raw, line_number)
            condition, rest = self._take_condition(rest, raw, line_number)
        else:
            # A line opening with ':' is a continuation; the command and
            # condition are filled in by the caller (spec 4.4).
            command, condition = "", None
            rest = rest[1:]
            params = rest
            self._validate_params(command, params, raw, line_number)
            return Statement(
                command="",
                params=params,
                label=label,
                comment=comment,
                source=raw,
                line_number=line_number,
                continued=True,
            )

        # Blanks before the colon are formatting, not operand data (spec 4.3):
        # `T   :hello` and `T:hello` are the same statement, and the operand
        # starts after the colon either way.
        rest = rest.lstrip()
        if not rest.startswith(":"):
            raise self._error(f"expected ':' after {command or 'the command'}", raw, line_number)

        params = rest[1:]
        self._validate_params(command, params, raw, line_number)
        return Statement(
            command=command,
            params=params,
            label=label,
            condition=condition,
            comment=comment,
            source=raw,
            line_number=line_number,
        )

    # -- fields -------------------------------------------------------------

    def _strip_line_number(self, raw: str, line_number: int) -> str:
        """Remove an optional leading line number (spec 4.1).

        A `LIST:`ed Atari program carries these; they are accepted and ignored.
        """
        match = _LINE_NUMBER_RE.match(raw)
        if match is None:
            return raw
        number = int(match.group(1))
        if number > MAX_LINE_NUMBER:
            raise self._error(
                f"line number {number} exceeds the maximum of {MAX_LINE_NUMBER}", raw, line_number
            )
        return raw[match.end() :]

    @staticmethod
    def _strip_comment(text: str) -> tuple[str, str | None]:
        """Split a trailing ``[`` ... EOL comment off ``text`` (spec 4.2).

        The comment runs to end of line and may contain any character, including
        ``:`` and further ``[``.

        Nothing is stripped from the part before the ``[``. Blanks right of the
        colon are significant (spec 4.3), and a trailing blank is data: in
        ``M:YES,YEAH,SURE_`` the underscore is how a trailing blank is written
        precisely because trailing blanks would otherwise be at risk. So
        ``T:HELLO  [note]`` has the operand ``HELLO  ``, blanks and all.
        """
        index = text.find("[")
        if index == -1:
            return text, None
        return text[:index], text[index + 1 :]

    @staticmethod
    def _take_command(text: str, raw: str, line_number: int) -> tuple[str, str]:
        """Take the command name from the front of ``text`` (spec 4.2).

        Command names run from one letter (``T``) to five (``TSYNC``), so the
        scanner takes the longest run of letters that names a known command.
        An unknown name is rejected rather than truncated: ``TYPEN:`` is ``TY``
        plus junk, not a forgiving ``TY`` (spec 4.3).
        """
        match = _COMMAND_RE.match(text)
        if match is None:
            raise Parser._error("expected a command name", raw, line_number)
        letters = match.group(0)
        # Longest known match wins. A one-letter name is only accepted when the
        # letter run is *exactly* that long, or when the run is a
        # command-plus-condition spelling. Otherwise `CN:` would resolve to `C`
        # plus junk and the Core PILOT command would slip through unrecognised.
        #
        # `ambiguous` is the set of `T`-specific spellings, where the *second*
        # letter is the condition and the command is really `T` (spec 6.1.1).
        # Every other command takes its condition the same way but keeps its own
        # name - `EY:` is `E` with a `Y` condition, not `T` (spec 6.1.10).
        ambiguous = frozenset({"TY", "TN", "YY", "YN", "NN", "NY"})
        for size in range(min(len(letters), _MAX_COMMAND_NAME), 0, -1):
            candidate = letters[:size].upper()
            if not CommandName.is_command(candidate):
                continue

            if size == 1 and len(letters) > 1:
                # A one-letter name is only a prefix of a longer letter run when
                # that run is a command+condition spelling. `CN:` must NOT
                # resolve to `C` plus junk, or the Core PILOT rejection for `CN`
                # would never fire.
                #
                # The REJECTED table is consulted *first* and unconditionally:
                # `CN` and `CS` are two-letter Core PILOT commands that happen to
                # end in a condition letter, and rejecting them is the whole
                # point. Only an unlisted run may be read as a spelling.
                if letters.upper() in REJECTED:
                    break
                if candidate in ambiguous:
                    return "T", text[size - 1 :]
                if letters[1].upper() in _CONDITION_LETTERS:
                    # Any command may carry a Y/N condition (spec 4.2); 6.1.10
                    # relies on it directly with `EY:`/`EN:` as its examples.
                    #
                    # `text[size:]` skips the *command* letter and leaves the
                    # condition letter for `_take_condition` to consume, so
                    # `EY:` becomes `E` plus a `Y` condition. (The `ambiguous`
                    # branch above uses `size - 1` because there the run is two
                    # letters long and both belong to the spelling.)
                    return candidate, text[size:]
                # Not a condition spelling, so the whole run is the name. Fall
                # through to the REJECTED lookup below rather than `continue`ing,
                # so a two-letter Core command still gets its explanation rather
                # than a bare "expected ':'".
                break

            if candidate in ambiguous:
                # Spec 6.1.1: `Y` is an abbreviation for `TY` and `N` for `TN`,
                # so every one of these forms is really `T` with a match
                # condition. The spec calls `YY` redundant and `YN` a statement
                # that never executes - both are accepted, because rejecting
                # them would fail a program a real Atari accepts.
                #
                # The condition letter goes *back* to the condition scanner,
                # which is about to run, so `TY(#A>0)` becomes a conjunctive
                # `Y` plus expression (spec 4.4).
                return "T", text[size - 1 :]
            if candidate in _CONDITION_LETTERS:
                # Bare `Y:`/`N:` are the same abbreviations, so they resolve to
                # `T` with a match condition. This matters for `Y(#A>0):`,
                # which must combine the two conjunctively (spec 4.4) rather
                # than treating `Y` as a command with its own condition slot.
                return "T", text[size - 1 :]
            return CommandName.canonical(candidate), text[size:]
        name = letters.upper()
        reason = REJECTED.get(name)
        if reason:
            raise Parser._error(
                f"{name!r} is not an ATARI PILOT command: {reason}", raw, line_number
            )
        raise Parser._error(f"unknown command {name!r}", raw, line_number)

    @staticmethod
    def _take_condition(text: str, raw: str, line_number: int) -> tuple[Condition | None, str]:
        """Take an optional condition from the front of ``text`` (spec 4.2).

        A condition is ``Y``/``N``, a parenthesised expression, or both. They
        are conjunctive when combined (spec 4.4).
        """
        match_flag: str | None = None
        expression: str | None = None
        rest = text

        if rest[:1] in {"Y", "y", "N", "n"}:
            match_flag = rest[0].upper()
            rest = rest[1:]

        if rest.startswith("("):
            depth = 0
            for index, char in enumerate(rest):
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        expression = rest[1:index]
                        rest = rest[index + 1 :]
                        break
            else:
                raise Parser._error("unbalanced '(' in condition", raw, line_number)

        if match_flag is None and expression is None:
            return None, text
        return Condition(match=match_flag, expression=expression), rest

    def _validate_params(self, command: str, params: str, raw: str, line_number: int) -> None:
        """Check operand rules that the spec states outright.

        Skipped for continuation lines, which carry an empty command until the
        caller resolves them; the resolved statement is checked on its own.
        """
        if not command:
            return
        upper = command.upper()
        # `E:` takes no operand (spec 6.1.10, App. B).
        #
        # Note this is about the operand *after* the colon, not about conditions:
        # spec 6.1.10 also says "This command, as all others, may be
        # conditional" and gives `EY:` and `EN:` as its examples, so
        # `E(#A>0):` is legal and must not be caught by this check. The
        # condition lives before the colon, and the parser has already consumed
        # it by the time we get here.
        if upper == "E" and params.strip():
            raise self._error("E: takes no operand", raw, line_number)
        # A null operand is not allowed (spec 7.4).
        if upper in {"M", "MS"} and not params:
            raise self._error(f"{upper}: requires at least one match field", raw, line_number)
        # No @-jumps in ATARI PILOT; JM: is the replacement (spec 10.6).
        if params.startswith("@"):
            raise self._error(
                f"{upper}:@ shorthand jumps are not an ATARI construct; use JM: (spec 9.4)",
                raw,
                line_number,
            )

    # -- continuation -------------------------------------------------------

    def _check_continuable(self, command: str, raw: str, line_number: int) -> None:
        """Continuation is legal only after T, Y, N, R in run mode (spec 4.4)."""
        if self._immediate_mode:
            return
        if command not in CONTINUABLE:
            raise self._error(
                f"continuation is not allowed after {command or 'no command'}; "
                "only T, Y, N and R may be continued (spec 4.4)",
                raw,
                line_number,
            )

    @staticmethod
    def _as_continuation(
        statement: Statement, command: str, condition: Condition | None
    ) -> Statement:
        """Fill in the inherited command and condition for a continuation line."""
        return Statement(
            command=command,
            params=statement.params,
            label=statement.label,
            condition=condition,
            comment=statement.comment,
            source=statement.source,
            line_number=statement.line_number,
            continued=True,
        )

    # -- errors -------------------------------------------------------------

    @staticmethod
    def _error(message: str, source: str, line: int) -> PilotSyntaxError:
        return PilotSyntaxError(message, line=line, source=source)


def parse(text: str, *, immediate_mode: bool = False) -> Program:
    """Parse PILOT source text into a :class:`~pypilot.syntax.Program`.

    Args:
        text: PILOT source.
        immediate_mode: allow continuation after any command (spec 4.4).

    Raises:
        PilotSyntaxError: on a malformed line.
    """
    return Parser(immediate_mode=immediate_mode).parse(text)
