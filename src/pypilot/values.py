"""The ATARI PILOT value model and text-expression expansion.

Two things live here, both from ``SPEC.md`` section 6:

* :class:`Numeric` - a 16-bit signed integer that **wraps silently** on
  overflow, because that is what the Atari did (spec 6.2). Python's ``int`` is
  arbitrary precision, so it cannot be used directly for numeric variables.
* Text-expression scanning - the machinery behind ``expand_text`` (spec 6.5),
  including the two rules that surprise everyone: an **undefined string
  variable substitutes its own name** (spec 6.1), and expansion is
  **single-pass** (spec 6.5).

The scanner is a state machine over the *raw operand text* preserved by
:mod:`pypilot.syntax`. It deliberately does not know about the accept buffer
or the match flag - that is Stage 5's business, and it arrives through
:class:`pypilot.state.PilotState`.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Final

from pypilot.errors import PilotRuntimeError

__all__ = [
    "INT16_MAX",
    "INT16_MIN",
    "MAX_STRING_LENGTH",
    "MAX_STRING_NAME",
    "NUMERIC_NAME_LENGTH",
    "Kind",
    "Numeric",
    "Piece",
    "expand_text",
    "scan_text",
    "wrap16",
]

#: The 16-bit signed range PILOT arithmetic stays inside (spec 6.2).
INT16_MIN: Final = -32768
INT16_MAX: Final = 32767

#: String data and text expressions are buffered to 254 characters (spec 5.2.3).
MAX_STRING_LENGTH: Final = 254

#: A string variable name may be up to 254 characters (spec 5.2.2).
MAX_STRING_NAME: Final = 254

#: A numeric variable is exactly one letter, ``#A`` through ``#Z`` (spec 5.1.2).
NUMERIC_NAME_LENGTH: Final = 1

#: The prefix sigils. ``$`` string, ``#`` numeric, ``%`` special/controller
#: (spec 5.2.1). ``*`` and ``@`` introduce memory pointers (spec 5.1.6).
STRING_SIGIL: Final = "$"
NUMERIC_SIGIL: Final = "#"
SPECIAL_SIGIL: Final = "%"
POINTER_SIGILS: Final = ("*", "@")


def wrap16(value: int) -> int:
    """Truncate ``value`` to 16-bit signed, wrapping rather than raising.

    Spec 6.2: overflow is *not* an error in ATARI PILOT. ``wrap16(32767 + 1)``
    is ``-32768``, and ``wrap16(32768)`` is ``-32768`` too, because the value
    is first truncated to 16 bits and then reinterpreted as signed.
    """
    masked = value & 0xFFFF
    return masked - 0x10000 if masked > INT16_MAX else masked


@dataclass(frozen=True, slots=True)
class Numeric:
    """A PILOT numeric value: a 16-bit signed integer.

    Stored wrapped, so a :class:`Numeric` can never hold an out-of-range value.
    Construct it from a Python ``int`` and the wrapping happens immediately::

        >>> Numeric(32767) + Numeric(1)
        Numeric(value=-32768)
    """

    value: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", wrap16(self.value))

    # -- arithmetic ---------------------------------------------------------

    def __add__(self, other: object) -> Numeric:
        return Numeric(self.value + _int_of(other))

    def __sub__(self, other: object) -> Numeric:
        return Numeric(self.value - _int_of(other))

    def __mul__(self, other: object) -> Numeric:
        return Numeric(self.value * _int_of(other))

    def __truediv__(self, other: object) -> Numeric:
        """Integer division truncating toward zero, dropping the remainder.

        Spec 6.2: ``7/3`` is ``2`` and ``-7/3`` is ``-2``. This is neither
        Python's floor division nor round-half-away-from-zero, so the sign of
        the quotient is that of the dividend.
        """
        divisor = _int_of(other)
        if divisor == 0:
            raise PilotRuntimeError("division by zero")
        quotient = abs(self.value) // abs(divisor)
        if (self.value < 0) != (divisor < 0):
            quotient = -quotient
        return Numeric(quotient)

    def __mod__(self, other: object) -> Numeric:
        """Modulo, and the result is **always positive** (spec 6.2).

        Spec 5.1.7: "\\ is the modulus operator (result is always positive)". This
        is the *absolute* remainder, not the C convention where the result takes
        the sign of the dividend: ``-7\\3`` is ``1``, not ``-1``.

        Note this is spelled ``\\`` in PILOT, not ``%`` - ``%`` is a variable
        sigil (spec 5.1.7).
        """
        divisor = _int_of(other)
        if divisor == 0:
            raise PilotRuntimeError("modulo by zero")
        return Numeric(abs(self.value) % abs(divisor))

    def __neg__(self) -> Numeric:
        return Numeric(-self.value)

    def __pos__(self) -> Numeric:
        return self

    # -- comparison ---------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Numeric):
            return self.value == other.value
        if isinstance(other, int):
            return self.value == wrap16(other)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.value)

    def __lt__(self, other: object) -> bool:
        return self.value < _int_of(other)

    def __le__(self, other: object) -> bool:
        return self.value <= _int_of(other)

    def __gt__(self, other: object) -> bool:
        return self.value > _int_of(other)

    def __ge__(self, other: object) -> bool:
        return self.value >= _int_of(other)

    def __bool__(self) -> bool:
        return self.value != 0

    def __int__(self) -> int:
        return self.value

    def __index__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"Numeric({self.value})"


def _int_of(value: object) -> int:
    """Coerce ``value`` to a Python int for arithmetic."""
    if isinstance(value, Numeric):
        return value.value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise PilotRuntimeError(f"cannot use {type(value).__name__} in numeric arithmetic")


class Kind(Enum):
    """The element kinds a text expression is built from (spec 5.2.3)."""

    TEXT = "text"
    """Literal characters, needing no lookup."""

    STRING = "string"
    """A ``$`` string variable reference."""

    NUMERIC = "numeric"
    """A ``#`` numeric variable reference, or a memory pointer."""

    SPECIAL = "special"
    """A ``%`` special or controller-sense reference."""

    RANDOM = "random"
    """``?`` in a **numeric** expression only (spec 5.1.3).

    This kind is produced by :mod:`pypilot.expressions`, the ``nexp``
    tokeniser, and never by :func:`scan_text` - see the note there.
    """


@dataclass(frozen=True, slots=True)
class Piece:
    """One element of a scanned text expression, still unresolved."""

    kind: Kind
    text: str = ""
    """Literal text, or the variable *name* (without its sigil)."""

    is_reference: bool = False
    """True for a variable or random reference, False for plain text."""

    indirection: int = 0
    """How many ``$`` prefixes to follow before reading the name (spec 5.2.4)."""

    def name_for_lookup(self) -> str:
        """The name to hand to a lookup callable.

        Indirection needs state to resolve - ``$$ABC`` names a variable whose
        name is stored in ``$ABC`` - so with no state available the name is
        used as-is, which is also how an undefined reference resolves
        (spec 5.2.4).
        """
        return self.text


def scan_text(text: str) -> tuple[Piece, ...]:
    """Scan ``text`` into its constituent :class:`Piece` elements (spec 6.5).

    A ``$``, ``#`` or ``%`` begins a variable reference; scanning resumes as
    literal text at the end of the name. There is **no escape** in ATARI PILOT:
    a sigil is literal when the next character does not start a valid variable
    specification (spec 5.2.1), so ``30#`` prints a literal ``#``.

    A trailing ``_`` yields a trailing blank (spec 5.2.3), which is how a
    match string or typed text keeps a significant trailing space.
    """
    pieces: list[Piece] = []
    buffer: list[str] = []
    index = 0
    length = len(text)

    def flush() -> None:
        if buffer:
            pieces.append(Piece(Kind.TEXT, "".join(buffer)))
            buffer.clear()

    while index < length:
        char = text[index]

        if char == "_" and index == length - 1:
            # A trailing underscore stands for one blank (spec 5.2.3).
            buffer.append(" ")
            index += 1
            continue

        if char in (STRING_SIGIL, NUMERIC_SIGIL, SPECIAL_SIGIL):
            consumed, piece = _scan_reference(text, index)
            if piece is None:
                # A sigil not followed by a valid name is literal text.
                buffer.append(char)
                index += 1
                continue
            flush()
            pieces.append(piece)
            index = consumed
            continue

        if char in POINTER_SIGILS:
            # Memory pointers are a *numeric* construct: spec 5.1.6 places them
            # in `nexp` ("a pointer may be used anywhere a numeric variable is
            # allowed"). They are never a text element, so they stay literal
            # here and are handled by the expression evaluator in Stage 3.
            # Without this, `5*6` would scan as the number 5 and a reference to
            # 6, and silently lose the multiplication sign.
            buffer.append(char)
            index += 1
            continue

        # NOTE: `?` is deliberately NOT special in a text expression. Spec 5.2.1
        # lists the characters that cannot be literals - `$`, `#`, `%`, `@`, `[`,
        # `<EOL>` - and `?` is not among them. Spec 5.1.3 allows `?` "anywhere a
        # numeric expression is allowed", and a text expression is not one; the
        # spec's own example `T:#X%, ARE YOU SURE?` relies on the `?` printing
        # literally. Treating it as random here corrupts any operand containing a
        # question mark, including the spec's own 6.1.4 worked example
        # `A:=WHAT WILL HAPPEN?`, whose printed $LEFT of 'AT' only holds if the
        # `?` is a literal. `?` is handled in `nexp` (pypilot.expressions), where
        # the spec actually permits it, so it simply falls through to the
        # literal-text branch below.

        buffer.append(char)
        index += 1

    flush()
    return tuple(pieces)


def _scan_reference(text: str, start: int) -> tuple[int, Piece | None]:
    """Scan a variable reference beginning at ``text[start]``.

    Returns ``(next_index, piece)``, or ``(start + 1, None)`` when the sigil is
    not followed by a valid name and is therefore literal (spec 5.2.1).
    """
    sigil = text[start]
    index = start

    # String indirection: $$ABC, $$$ABC ... (spec 5.2.4).
    indirection = 0
    if sigil == STRING_SIGIL:
        while index < len(text) and text[index] == STRING_SIGIL:
            indirection += 1
            index += 1
    else:
        index += 1

    name_start = index
    while index < len(text) and (text[index].isalnum() or text[index] == "_"):
        index += 1

    name = text[name_start:index]
    if not name:
        return start + 1, None

    if sigil == STRING_SIGIL:
        kind = Kind.STRING
    elif sigil == NUMERIC_SIGIL:
        kind = Kind.NUMERIC
    else:
        kind = Kind.SPECIAL

    if kind is Kind.NUMERIC and len(name) > NUMERIC_NAME_LENGTH:
        # Only #A-#Z exist (spec 5.1.2). A longer run is a Core PILOT habit
        # and is not a valid ATARI reference, so treat the sigil as literal.
        return start + 1, None

    return index, Piece(kind, name, is_reference=True, indirection=indirection)


def expand_text(
    text: str,
    *,
    lookup: Callable[[Piece], str] | None = None,
    random_value: Callable[[], int] | None = None,
    limit: int = MAX_STRING_LENGTH,
) -> str:
    """Expand a text expression into its output string (spec 6.5).

    Args:
        text: the raw operand, as preserved by the parser.
        lookup: called once per variable reference with the whole
            :class:`Piece`, so a resolver can see the indirection depth.
            Defaults to substituting the variable's own name, which is what
            ATARI does for an undefined variable (spec 6.1).
        random_value: supplies a value for ``?``. Defaults to an unseeded
            :mod:`random` draw; a seed is injected for testability. Retained
            for callers that build :class:`Piece` objects by hand - the text
            scanner itself never produces a :attr:`Kind.RANDOM` piece, because
            ``?`` is literal text in a text expression (spec 5.2.1). Retained
            for callers that construct :class:`Piece` objects by hand - the
            text scanner itself never produces a :attr:`Kind.RANDOM` piece,
            because ``?`` is literal text in a text expression (spec 5.2.1).
        limit: truncate the result to this many characters.

    Expansion is **single-pass**: the text produced by ``lookup`` is never
    rescanned for further variable references (spec 6.5).
    """
    resolve: Callable[[Piece], str] = lookup if lookup is not None else _default_lookup

    def draw() -> int:
        if random_value is not None:
            return random_value()
        return random.randrange(INT16_MIN, INT16_MAX + 1)

    out: list[str] = []
    length = 0
    for piece in scan_text(text):
        if not piece.is_reference:
            part = piece.text
        elif piece.kind is Kind.RANDOM:
            part = str(draw())
        else:
            part = resolve(piece)
        out.append(part)
        length += len(part)
        if length >= limit:
            # Truncation is silent (spec 6.5), so stop gathering once the
            # buffer is certainly full rather than truncating each piece.
            break
    return "".join(out)[:limit]


def _default_lookup(piece: Piece) -> str:
    """Fallback used when no state is supplied: substitute the name itself.

    This is the ATARI behaviour for an undefined variable (spec 6.1), so it is
    the right default for a text expression evaluated with no state.
    """
    return piece.text
