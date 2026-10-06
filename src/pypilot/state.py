"""Interpreter state for ATARI PILOT.

:class:`PilotState` holds everything that changes while a program runs: the
variable stores, the accept buffer, the match flag, and the module call stack.
Statements are frozen (spec 5.1), so all mutable interpreter state lives here.

This module implements ``SPEC.md`` sections 6.1, 6.5, 6.6 and 7.1:

* the 26 single-letter numeric variables, ``#A``-``#Z`` (spec 6.1)
* the string table, where **undefined and null are different states** (spec 6.1)
* text expansion, including the undefined-name substitution rule (spec 6.1)
* the accept buffer and its normalisation (spec 7.1, 7.2.2)
* the match ordinal (spec 6.6)

Expression evaluation is delegated to :mod:`pypilot.expressions`; statement
execution and file devices are owned by the runtime and device modules.
"""

from __future__ import annotations

import gc
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from pypilot.errors import PilotRuntimeError
from pypilot.expressions import evaluate as evaluate_expression
from pypilot.values import (
    INT16_MAX,
    INT16_MIN,
    MAX_STRING_LENGTH,
    MAX_STRING_NAME,
    Kind,
    Numeric,
    Piece,
    expand_text,
)

__all__ = [
    "MATCH_STRING_NAMES",
    "MAX_MODULE_DEPTH",
    "MatchResult",
    "PilotState",
    "normalise_accept",
]

#: How deep ``U:`` may nest before the interpreter refuses (spec 8.3).
#:
#: **8**, not a host-sized number. Spec 6.1.9: *"Up to eight (8) Uses may be
#: nested before the system responds with an error message."* That is a real
#: constraint of the 6502 target, which had 256 bytes of variable space, and a
#: lesson nesting deeper than 8 was using more stack than a real Atari allowed.
#: Keeping the target's limit is the whole point of targeting ATARI PILOT.
MAX_MODULE_DEPTH = 8

#: The 26 numeric variable names, ``A``-``#Z`` (spec 5.1.2).
NUMERIC_NAMES: tuple[str, ...] = tuple(chr(ord("A") + i) for i in range(26))

#: The three strings ``MS:`` produces, readable as ``$LEFT``/``$MATCH``/``$RIGHT``
#: (spec 6.1.4). They are **not** entries in the string table - they live in
#: :attr:`MatchResult` and are resolved here, so ``T:$LEFT`` works without ``MS:``
#: having written anything the program can clobber with ``C:$LEFT=...``.
MATCH_STRING_NAMES: Final = ("LEFT", "MATCH", "RIGHT")


def host_kilobytes() -> int:
    """A rough figure for the process's live heap, used only by ``%F``.

    This is emphatically **not** a 6502 free-byte count - see spec 10.5. It
    exists so ``%F`` reads as a plausible number rather than 0, which is what a
    program probing memory would expect to see.

    Reported in kilobytes because PILOT numbers are 16-bit, so a byte count
    would always wrap. Uses the GC's tracked-object count, which is cheap and
    monotonic enough for a diagnostic.
    """
    try:
        objects = gc.get_count()[0]  # [0] is the number of tracked objects
    except Exception:  # pragma: no cover - defensive only
        return 0
    return int(objects) % (INT16_MAX + 1)


@dataclass(frozen=True, slots=True)
class MatchResult:
    """The outcome of the last ``M:`` or ``MS:`` (spec 6.1.3, 6.6).

    ``ordinal`` is the **1-based index of the field that matched**, or 0 when
    nothing matched. It is not a boolean: ``JM:`` branches on it, so a three-way
    ``M:`` list is a three-way branch.
    """

    ordinal: int = 0
    matched: bool = False
    left: str = ""
    """``$LEFT`` from the last ``MS:`` - unset strings are retained (spec 7.5)."""

    match: str = ""
    """``$MATCH`` from the last ``MS:``."""

    right: str = ""
    """``$RIGHT`` from the last ``MS:``."""


#: Maps each ``MS:``-produced name to the :class:`MatchResult` field it reads.
#:
#: Written out explicitly rather than resolved with ``getattr`` so that a
#: rename of a :class:`MatchResult` field is a type error rather than a runtime
#: one, and so the three names appear together in one place.
_MATCH_STRING_READERS: Final[dict[str, Callable[[MatchResult], str]]] = {
    "LEFT": lambda result: result.left,
    "MATCH": lambda result: result.match,
    "RIGHT": lambda result: result.right,
}


def normalise_accept(data: str) -> str:
    """Normalise accepted input into the accept buffer (spec 7.2.2).

    In order: a space is added at the start, a space at the end, lower case is
    converted to upper case, runs of spaces collapse to one, and the result is
    truncated to 254 characters.

    This is why every Atari manual writes match fields in upper case, and why a
    field with a trailing ``_`` matches a word *plus* its trailing space.
    """
    collapsed = " ".join(data.split())
    return f" {collapsed.upper()} "[:MAX_STRING_LENGTH]


@dataclass(slots=True)
class PilotState:
    """All mutable interpreter state for one run of a program."""

    # -- variables ----------------------------------------------------------

    numbers: dict[str, Numeric] = field(default_factory=dict)
    """Numeric variables ``#A``-``#Z``, absent until assigned (spec 6.1)."""

    strings: dict[str, str] = field(default_factory=dict)
    """String variables. Absent means *undefined*, which prints as the name."""

    # -- accept buffer and matching ----------------------------------------

    accept_buffer: str = ""
    """The normalised accept buffer, 254 characters max (spec 7.2.2)."""

    match: MatchResult = field(default_factory=MatchResult)
    """Outcome of the last match; ``ordinal`` drives ``Y``/``N`` and ``JM:``."""

    # -- module calls -------------------------------------------------------

    call_stack: list[int] = field(default_factory=list)
    """Return addresses for ``U:``; depth is capped at MAX_MODULE_DEPTH."""

    max_module_depth: int = 0
    """High-water mark, reported by ``DUMP:`` in place of Core's ``%MAXUSES``."""

    # -- determinism --------------------------------------------------------

    random_seed: int | None = None
    """When set, every ``?`` draw is reproducible (spec 6.3)."""

    _random: random.Random = field(default_factory=random.Random, repr=False)

    def __post_init__(self) -> None:
        if self.random_seed is not None:
            self._random = random.Random(self.random_seed)

    # -- numeric variables --------------------------------------------------

    @staticmethod
    def is_numeric_name(name: str) -> bool:
        """Is ``name`` a valid numeric variable name? Only ``A``-``#Z`` (spec 6.1)."""
        return len(name) == 1 and name.isalpha() and name.upper() in NUMERIC_NAMES

    def get_number(self, name: str) -> Numeric:
        """Read a numeric variable. Unset reads as 0, not an error (spec 5.1.2)."""
        key = name.upper()
        if not self.is_numeric_name(key):
            raise PilotRuntimeError(
                f"{name!r} is not a numeric variable; ATARI PILOT has only #A-#Z"
            )
        return self.numbers.get(key, Numeric(0))

    def set_number(self, name: str, value: int | Numeric) -> None:
        """Assign a numeric variable, wrapping to 16 bits (spec 6.2)."""
        key = name.upper()
        if not self.is_numeric_name(key):
            raise PilotRuntimeError(
                f"{name!r} is not a numeric variable; ATARI PILOT has only #A-#Z"
            )
        self.numbers[key] = value if isinstance(value, Numeric) else Numeric(value)

    def clear_numbers(self) -> None:
        """``VNEW:#`` - reset the numeric variables (spec 9.5)."""
        self.numbers.clear()

    # -- string variables ---------------------------------------------------

    def is_defined(self, name: str) -> bool:
        """Has ``name`` been assigned? Undefined is not the same as null."""
        return name in self.strings

    def get_string(self, name: str) -> str | None:
        """Read a string variable, or ``None`` when undefined (spec 6.1)."""
        return self.strings.get(name)

    def set_string(self, name: str, value: str) -> None:
        """Assign a string variable, truncating to 254 characters (spec 5.2.2).

        Assigning the empty string makes the variable *null*, which is a
        different state from undefined and prints differently.
        """
        if not name:
            raise PilotRuntimeError("a string variable name cannot be empty")
        if len(name) > MAX_STRING_NAME:
            raise PilotRuntimeError(
                f"string variable name {name!r} exceeds {MAX_STRING_NAME} characters"
            )
        self.strings[name] = value[:MAX_STRING_LENGTH]

    def forget_string(self, name: str) -> bool:
        """Make a string variable **undefined** again, the counterpart of assignment.

        Distinct from assigning the empty string, which makes it *null*: a null
        string prints as nothing but is still defined, while an undefined one
        substitutes its own name (spec 6.1). A program can tell the two apart
        with :meth:`is_defined`, so this must not be faked with ``set_string(n, "")``.

        Used by ``CLOSE:``, which removes the open-file string the Atari keeps in
        the string table (spec 6.1.17).

        Returns:
            True if the variable existed.
        """
        return self.strings.pop(name, None) is not None

    def clear_strings(self) -> None:
        """``VNEW:$`` - reset the string variables (spec 6.1.11).

        This also **closes every open file**. The Atari records open devices as
        strings named ``@«spec»`` in the string table, and spec 6.1.17 says
        clearing the string variables *"has the effect of closing all files"* -
        so the caller closes the devices before calling this.
        """
        self.strings.clear()

    def clear_variables(self, *, strings: bool = True, numbers: bool = True) -> None:
        """``VNEW:`` with no operand clears both (spec 9.5)."""
        if strings:
            self.clear_strings()
        if numbers:
            self.clear_numbers()

    # -- indirection --------------------------------------------------------

    def resolve_indirection(self, name: str, levels: int) -> str | None:
        """Follow ``$`` indirection ``levels`` deep (spec 5.2.4).

        ``$$ABC`` with ``$ABC`` holding ``XYZ`` returns the data of ``$XYZ``.
        Returns ``None`` if any level is undefined.
        """
        current = name
        for _ in range(levels):
            value = self.strings.get(current)
            if value is None:
                return None
            current = value
        return self.strings.get(current)

    # -- text expansion -----------------------------------------------------

    def lookup(self, piece: Piece) -> str:
        """Resolve one scanned reference for :func:`~pypilot.values.expand_text`.

        This is where the undefined-variable rule lives (spec 6.1): an
        **undefined string variable substitutes its own name**. A variable that
        was assigned the empty string is null, and prints as nothing.

        ``$$ABC`` indirection is handled here (spec 5.2.4): the name is resolved
        through ``$ABC``'s data, and if that cannot be carried the result is the
        same as a simple undefined name, which is the name itself.

        ``$LEFT``/``$MATCH``/``$RIGHT`` (spec 6.1.4) are answered from the
        match result, not the string table, so that ``C:$LEFT=...`` cannot
        shadow them and ``MS:``-retention is automatic. They resolve to the
        **null string** rather than to their own name, because an unset match
        string is null by definition - unlike an undefined string variable.
        """
        name = piece.name_for_lookup()
        if piece.kind is Kind.STRING:
            if piece.indirection > 1:
                resolved = self.resolve_indirection(name, piece.indirection - 1)
                return name if resolved is None else resolved
            if name in MATCH_STRING_NAMES:
                # Spelling the three out rather than using getattr keeps this
                # type-safe, and keeps the names in one visible place.
                return _MATCH_STRING_READERS[name](self.match)
            value = self.strings.get(name)
            return name if value is None else value
        if piece.kind is Kind.NUMERIC:
            # Only #A-#Z exist, so a single letter is a numeric variable.
            return str(self.get_number(name).value)
        # Controller sense has no host input; unsupported hardware values read as 0.
        return "0"

    def expand(self, text: str, *, limit: int = MAX_STRING_LENGTH) -> str:
        """Expand a text expression against this state (spec 6.5).

        Expansion is **single-pass**: text produced by a variable is never
        rescanned, so a variable holding ``$OTHER`` does not expand ``$OTHER``.
        """
        return expand_text(text, lookup=self.lookup, random_value=self.next_random, limit=limit)

    # -- numeric expressions ------------------------------------------------

    def get_special(self, name: str) -> int:
        """Read a special variable ``%F``/``%M``/``%X``/``%Y``/``%A`` (spec 6.6).

        ``%M`` is real: it is the match ordinal, which is why ``J(%M=2):``
        can branch on *which* alternative matched. The graphics variables read 0
        while ``GR:`` is unimplemented (spec 10.4), and ``%F`` reports a host
        figure rather than a 6502 one (spec 10.5).
        """
        if name == "M":
            return self.match.ordinal
        if name in {"X", "Y", "A"}:
            # Graphics cursor state; zero while GR: is unimplemented.
            return 0
        if name == "F":
            return host_kilobytes()
        return 0

    def get_controller(self, prefix: str, index: str) -> int:
        """Read a controller sense value (spec 5.1.4).

        There is no Atari hardware behind this, so every sense reports 0, which
        reads as "no input" and keeps a controller-probing lesson running
        (spec 10.5). The prefix and index are accepted so the shape of the
        construct is preserved for when a host device is wired up.
        """
        return 0

    def evaluate(self, text: str) -> Numeric:
        """Evaluate a numeric expression against this state (spec 6.2).

        Left to right with **no operator precedence**, and the remainder is
        always positive - both per spec 5.1.7. See
        :mod:`pypilot.expressions`.
        """
        return evaluate_expression(
            text,
            get_number=lambda name: self.get_number(name).value,
            get_special=self.get_special,
            get_controller=self.get_controller,
            random_value=self.next_random,
        )

    # -- random -------------------------------------------------------------

    def next_random(self) -> int:
        """A random number in the 16-bit signed range (spec 5.1.3)."""
        return self._random.randint(INT16_MIN, INT16_MAX)

    def seed_random(self, seed: int | None) -> None:
        """Make ``?`` reproducible. ``None`` restores non-determinism."""
        self.random_seed = seed
        self._random = random.Random(seed)

    # -- accept buffer ------------------------------------------------------

    def set_accept(self, data: str) -> str:
        """Normalise and store ``data`` as the accept buffer (spec 7.2.2)."""
        self.accept_buffer = normalise_accept(data)
        return self.accept_buffer

    def clear_accept(self) -> None:
        self.accept_buffer = ""

    def accept_text(self) -> str:
        """The accept buffer as a *value* - null string, never undefined.

        An unset buffer is a null string, so it expands to nothing rather than
        to a name (spec 7.1, 7.2.2).
        """
        return self.accept_buffer

    # -- matching -----------------------------------------------------------

    def record_match(self, ordinal: int) -> None:
        """Record a successful match, setting the ordinal (spec 6.1.3)."""
        self.match = MatchResult(ordinal=ordinal, matched=True)

    def record_no_match(self) -> None:
        """Record a failed match. ``$LEFT``/``$MATCH``/``$RIGHT`` are retained
        by ``MS:`` (spec 6.1.4), so they are carried over untouched."""
        previous = self.match
        self.match = MatchResult(
            ordinal=0,
            matched=False,
            left=previous.left,
            match=previous.match,
            right=previous.right,
        )

    def set_match_parts(self, left: str, match: str, right: str) -> None:
        """``MS:`` sets the three split strings (spec 6.1.4)."""
        current = self.match
        self.match = MatchResult(
            ordinal=current.ordinal,
            matched=current.matched,
            left=left,
            match=match,
            right=right,
        )

    def reset(self) -> None:
        """Clear the whole environment: variables, buffer, match flag, stack.

        This is what ``RUN:`` does before starting a stored program (spec 6.2.2)
        and what a fresh interpreter starts from.

        Note it is **not** what ``LOAD:`` does. Spec 6.1.21 says a run-mode load
        clears the program area and the Use stack and *"will be executed without
        any initialization of the program environment"* - so the accept buffer,
        the match flag and every variable survive a ``LOAD:``. Use
        :meth:`clear_call_stack` for that.
        """
        self.clear_variables()
        self.clear_accept()
        self.match = MatchResult()
        self.call_stack.clear()

    def clear_call_stack(self) -> None:
        """Empty the Use stack, leaving everything else alone (spec 6.1.21).

        ``LOAD:`` in run mode does exactly this: the program area is replaced
        and the Use stack cleared, but the environment is otherwise carried
        over into the newly loaded program.
        """
        self.call_stack.clear()

    # -- modules ------------------------------------------------------------

    def push_module(self, return_address: int) -> None:
        """Enter a module (spec 8.3). Raises rather than blowing the Python stack."""
        if len(self.call_stack) >= self.max_module_depth_limit():
            raise PilotRuntimeError(f"U: nesting exceeded {self.max_module_depth_limit()} levels")
        self.call_stack.append(return_address)
        self.max_module_depth = max(self.max_module_depth, len(self.call_stack))

    def pop_module(self) -> int:
        """Leave a module, returning to the saved address (spec 8.3)."""
        if not self.call_stack:
            raise PilotRuntimeError("E: with no module to return from")
        return self.call_stack.pop()

    def max_module_depth_limit(self) -> int:
        return MAX_MODULE_DEPTH

    def in_module(self) -> bool:
        return bool(self.call_stack)

    # -- diagnostics --------------------------------------------------------

    def dump_strings(self) -> str:
        """Render the string variables, for ``DUMP:`` (spec 9.5)."""
        if not self.strings:
            return "(no string variables defined)"
        width = max(len(name) for name in self.strings)
        return "\n".join(
            f"${name.ljust(width)} = {self.strings[name]!r}" for name in sorted(self.strings)
        )

    def dump_numbers(self) -> str:
        """Render the numeric variables, for ``DUMP:`` (spec 9.5)."""
        if not self.numbers:
            return "(no numeric variables defined)"
        return " ".join(f"#{name}={self.numbers[name].value}" for name in sorted(self.numbers))

    def binder(self) -> Callable[[Piece], str]:
        """The lookup callable to pass to :func:`~pypilot.values.expand_text`."""
        return self.lookup
