"""Evaluation of ATARI PILOT numeric expressions (``nexp``).

Implements ``SPEC.md`` section 6.2 and Atari spec 5.1.7. Two properties of this
language are unusual and are the reason this is a hand-written evaluator rather
than a translation to Python:

**There is no operator precedence.** Spec 5.1.7 is explicit: *"Numeric
expressions are evaluated from left to right, with no operator precedence
rules; parentheses are allowed (encouraged?) to either clarify the formulae or
to alter the left to right evaluation scheme."* So ``1+2*3`` is ``9``, not
``7``. Anyone writing ``1+2*3`` and expecting ``7`` is importing a habit from
another language, and this evaluator will not accommodate it.

**The remainder is always positive.** Spec 5.1.7 calls ``\\`` "the modulus
operator (result is always positive)", so ``-7\\3`` is ``1``, not ``-1``.

Relational operators yield ``1`` for true and ``0`` for false, so they compose
with arithmetic to give logical *and* and *or* - which is how the Atari sources
themselves write them.

Results are :class:`~pypilot.values.Numeric`, so arithmetic wraps at 16 bits
per spec 6.2.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Final

from pypilot.errors import PilotRuntimeError
from pypilot.values import Numeric, wrap16

__all__ = [
    "ARITHMETIC",
    "MAX_NESTING",
    "RELATIONAL",
    "ExpressionError",
    "evaluate",
    "is_expression",
]

#: How many levels of *non-redundant* parentheses are allowed (spec 5.1.7).
#: Redundant parens such as ``(((7)))`` do not count against this.
MAX_NESTING: Final = 2

#: The six arithmetic operators (spec 5.1.7).
ARITHMETIC: Final = frozenset("+-*/\\")

#: The six relational operators, longest first so ``<=`` beats ``<`` (5.1.7).
RELATIONAL: Final[tuple[str, ...]] = ("<>", "<=", ">=", "=", "<", ">")


class ExpressionError(PilotRuntimeError):
    """Raised when a numeric expression cannot be parsed or evaluated."""


class TokenKind(Enum):
    """The token kinds of a numeric expression."""

    NUMBER = "number"
    VARIABLE = "variable"
    RANDOM = "random"
    SPECIAL = "special"
    CONTROLLER = "controller"
    POINTER = "pointer"
    OPERATOR = "operator"
    LEFT_PAREN = "("
    RIGHT_PAREN = ")"


# Controller-sense and special variables, per spec 5.1.4 and 5.1.5. They are
# supplied by the caller because only the runtime knows their values; the
# default reader reports 0, which is "no input" (spec 10.5).
CONTROLLER_PREFIXES: Final = ("J", "P", "T", "H", "V", "L")

SPECIAL_NAMES: Final = ("F", "M", "X", "Y", "A")

#: A pointer: ``*<addr>`` (word) or ``@B<addr>`` (byte), per spec 5.1.6.
_POINTER_RE: Final = re.compile(r"@?B?\d+")

_NAME_RE: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: A numeric constant, with an optional unary sign (spec 5.1.1).
_NUMBER_RE: Final = re.compile(r"\d+")


def is_expression(text: str) -> bool:
    """Does ``text`` look like a numeric expression rather than an operand name?"""
    stripped = text.strip()
    if not stripped:
        return False
    return any(operator in stripped for operator in ARITHMETIC | {"<", ">", "="})


def evaluate(
    text: str,
    *,
    get_number: Callable[[str], int] | None = None,
    get_special: Callable[[str], int] | None = None,
    get_controller: Callable[[str, str], int] | None = None,
    random_value: Callable[[], int] | None = None,
) -> Numeric:
    """Evaluate a numeric expression and return its :class:`~pypilot.values.Numeric` result.

    Args:
        text: the raw expression, as preserved by the parser.
        get_number: reads ``#A``-``#Z``. Defaults to reading 0.
        get_special: reads ``%F``/``%M``/``%X``/``%Y``/``%A``. Defaults to 0.
        get_controller: reads ``%J``/``%P``/``%T``/``%H``/``%V``/``%L`` given a
            prefix and an optional index. Defaults to 0 (spec 10.5).
        random_value: supplies ``?``. Defaults to 0 unless supplied.

    Raises:
        ExpressionError: on a malformed expression, a division or modulo by
            zero, an unbalanced or over-nested parenthesis, or a memory pointer
            (unsupported, spec 10.5).

    The result is already wrapped to 16 bits, because
    :class:`~pypilot.values.Numeric` wraps on construction (spec 6.2).
    """
    tokens = _tokenise(text)
    if not tokens:
        return Numeric(0)

    reader = _Reader(
        get_number or (lambda _name: 0),
        get_special or (lambda _name: 0),
        get_controller or (lambda _prefix, _index: 0),
        random_value or (lambda: 0),
    )
    value, position = _evaluate_sequence(tokens, 0, reader, nesting=0)
    if position != len(tokens):
        raise ExpressionError(f"unexpected {tokens[position].text!r} in expression {text!r}")
    return Numeric(value)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: TokenKind
    text: str
    index: int = 0
    byte_pointer: bool = False


def _expects_operand(tokens: list[_Token]) -> bool:
    """Is an operand expected at this point in the token stream?

    True at the start, and after any operator or an opening parenthesis. This
    is what disambiguates ``*``: at the start of an operand it is a word
    pointer, elsewhere it is multiplication (spec 5.1.6).
    """
    if not tokens:
        return True
    previous = tokens[-1].kind
    return previous in {TokenKind.OPERATOR, TokenKind.LEFT_PAREN}


def _tokenise(text: str) -> tuple[_Token, ...]:
    """Split ``text`` into tokens, rejecting anything malformed."""
    tokens: list[_Token] = []
    position = 0
    length = len(text)

    while position < length:
        char = text[position]

        if char.isspace():
            position += 1
            continue

        if char == "(":
            tokens.append(_Token(TokenKind.LEFT_PAREN, "(", position))
            position += 1
            continue

        if char == ")":
            tokens.append(_Token(TokenKind.RIGHT_PAREN, ")", position))
            position += 1
            continue

        # The two-character relational operators must be tried first, so `<=`
        # is not read as `<` followed by `=`.
        if text[position : position + 2] in RELATIONAL:
            tokens.append(_Token(TokenKind.OPERATOR, text[position : position + 2], position))
            position += 2
            continue

        if char in {"*", "@"}:
            # `*` is ambiguous: it is both multiplication and the word-pointer
            # sigil (spec 5.1.6). It is a pointer only where an operand is
            # expected, and a multiply otherwise, so `*4096` is a pointer while
            # `2*3` is a multiplication. `@` is never arithmetic, so it is
            # always a byte pointer.
            if char == "@" or _expects_operand(tokens):
                token, position = _read_pointer(text, position)
                tokens.append(token)
                continue
            tokens.append(_Token(TokenKind.OPERATOR, char, position))
            position += 1
            continue

        if char in ARITHMETIC or char in {"<", ">", "="}:
            tokens.append(_Token(TokenKind.OPERATOR, char, position))
            position += 1
            continue

        if char == "?":
            tokens.append(_Token(TokenKind.RANDOM, "?", position))
            position += 1
            continue

        if char in {"#", "$", "%"}:
            token, position = _read_sigil(text, position, char)
            tokens.append(token)
            continue

        match = _NUMBER_RE.match(text, position)
        if match:
            tokens.append(_Token(TokenKind.NUMBER, match.group(0), position))
            position = match.end()
            continue

        raise ExpressionError(f"unexpected {char!r} in numeric expression {text!r}")

    return tuple(tokens)


def _read_sigil(text: str, position: int, sigil: str) -> tuple[_Token, int]:
    """Read a ``#``, ``$`` or ``%`` reference (spec 5.1.2, 5.1.4, 5.1.5)."""
    start = position
    position += 1

    if sigil == "$":
        # A string has no numeric value; a $ where a number belongs is a
        # mistake worth reporting rather than silently reading as 0.
        text_name = _NAME_RE.match(text, position)
        found = text_name.group(0) if text_name is not None else ""
        raise ExpressionError(f"string variable ${found} cannot be used in a numeric expression")

    if sigil == "#":
        match = _NAME_RE.match(text, position)
        if match is None:
            raise ExpressionError(f"'#' must be followed by a variable name at position {start}")
        variable = match.group(0)
        if len(variable) != 1:
            # Only #A-#Z exist (spec 5.1.2).
            raise ExpressionError(
                f"{variable!r} is not a numeric variable; ATARI PILOT has only #A-#Z (spec 5.1.2)"
            )
        return _Token(TokenKind.VARIABLE, variable, start), match.end()

    # sigil == "%": a special or controller-sense variable, optionally
    # followed by a device index such as the 0-3 of %J0 (spec 5.1.4).
    match = _NAME_RE.match(text, position)
    if match is None:
        raise ExpressionError(f"'%' must be followed by a name at position {start}")
    special = match.group(0)
    position = match.end()

    prefix = special[:1]
    index = special[1:]
    if prefix in CONTROLLER_PREFIXES and (not index or index.isdigit()):
        if not index and text[position : position + 1] == "#":
            variable, end = _read_controller_variable(text, position)
            index = f"#{variable}"
            position = end
        return _Token(TokenKind.CONTROLLER, f"{prefix}:{index or '0'}", start), position
    # Every other %-name - %F, %M, %X, %Y, %A, and anything unrecognised -
    # reads through the special-variable path. An unknown name resolving to 0
    # keeps a lesson that probes something exotic running (spec 10.5).
    return _Token(TokenKind.SPECIAL, special, start), position


def _read_controller_variable(text: str, position: int) -> tuple[str, int]:
    """Read a numeric-variable selector such as the ``#I`` in ``%J#I``."""
    match = _NAME_RE.match(text, position + 1)
    if match is None or len(match.group(0)) != 1 or not match.group(0).isalpha():
        raise ExpressionError("a controller selector after '#' must be #A-#Z")
    return match.group(0), match.end()


def _read_pointer(text: str, position: int) -> tuple[_Token, int]:
    """Read a memory pointer ``*<addr>`` or ``@B<addr>`` (spec 5.1.6).

    Parsed so the rest of the expression reads correctly, then refused at
    evaluation: there is no Atari memory model to expose, and faking one would
    be worse than declining (spec 10.5).
    """
    start = position
    byte = text[position] == "@"
    position += 1  # step over the `@` or the `*`
    if byte and text[position : position + 1] == "B":
        # `@B` is a byte pointer; a bare `@` points at a whole word (5.1.6).
        position += 1
    address = _NUMBER_RE.match(text, position)
    if address is None:
        raise ExpressionError("a memory pointer must be followed by an address (spec 5.1.6)")
    end = address.end()
    return _Token(TokenKind.POINTER, text[start:end], start, byte), end


@dataclass(slots=True)
class _Reader:
    """Resolves operand tokens to plain ints."""

    get_number: Callable[[str], int]
    get_special: Callable[[str], int]
    get_controller: Callable[[str, str], int]
    random_value: Callable[[], int]

    def read(self, token: _Token) -> int:
        """Resolve one operand token to an integer."""
        if token.kind is TokenKind.NUMBER:
            # Constants are truncated to 16 bits on entry (spec 5.1.1).
            return wrap16(int(token.text))
        if token.kind is TokenKind.VARIABLE:
            return wrap16(self.get_number(token.text))
        if token.kind is TokenKind.RANDOM:
            return wrap16(self.random_value())
        if token.kind is TokenKind.SPECIAL:
            return wrap16(self.get_special(token.text))
        if token.kind is TokenKind.CONTROLLER:
            prefix, _, index = token.text.partition(":")
            if index.startswith("#"):
                index = str(self.get_number(index[1:]))
            return wrap16(self.get_controller(prefix, index))
        raise ExpressionError(f"memory pointers are not supported: {token.text!r} (spec 10.5)")


def _evaluate_sequence(
    tokens: tuple[_Token, ...],
    position: int,
    reader: _Reader,
    *,
    nesting: int,
) -> tuple[int, int]:
    """Evaluate a run of ``operand (op operand)*`` and return ``(value, next)``.

    Evaluation is strictly left to right with no precedence (spec 5.1.7), so
    this is a plain fold rather than a precedence-climbing parse.
    """
    value, position = _evaluate_primary(tokens, position, reader, nesting=nesting)
    while position < len(tokens) and tokens[position].kind is TokenKind.OPERATOR:
        operator = tokens[position]
        right, position = _evaluate_primary(tokens, position + 1, reader, nesting=nesting)
        value = _apply(operator.text, value, right)
    return value, position


def _evaluate_primary(
    tokens: tuple[_Token, ...],
    position: int,
    reader: _Reader,
    *,
    nesting: int,
) -> tuple[int, int]:
    """Evaluate one operand, which may be parenthesised."""
    if position >= len(tokens):
        raise ExpressionError("expression ended unexpectedly")

    token = tokens[position]

    if token.kind is TokenKind.LEFT_PAREN:
        return _evaluate_group(tokens, position, reader, nesting=nesting)

    if token.kind is TokenKind.OPERATOR and token.text == "-":
        # Unary minus, permitted in most but not all contexts (spec 5.1.1).
        operand, position = _evaluate_primary(tokens, position + 1, reader, nesting=nesting)
        return wrap16(-operand), position

    if token.kind is TokenKind.RIGHT_PAREN:
        raise ExpressionError(f"unbalanced ')' at position {token.index}")

    return reader.read(token), position + 1


def _evaluate_group(
    tokens: tuple[_Token, ...],
    position: int,
    reader: _Reader,
    *,
    nesting: int,
) -> tuple[int, int]:
    """Evaluate ``( nexp )``, enforcing the nesting limit (spec 5.1.7)."""
    depth = nesting + 1
    if depth > MAX_NESTING and not _is_redundant(tokens, position):
        raise ExpressionError(
            f"at most {MAX_NESTING} levels of nested parentheses are allowed (spec 5.1.7)"
        )

    value, position = _evaluate_sequence(tokens, position + 1, reader, nesting=depth)
    if position >= len(tokens) or tokens[position].kind is not TokenKind.RIGHT_PAREN:
        raise ExpressionError("unbalanced '(' in numeric expression")
    return value, position + 1


def _is_redundant(tokens: tuple[_Token, ...], position: int) -> bool:
    """Is the group at ``position`` just a parenthesised single value?

    Spec 5.1.7 allows any number of redundant parens - ``(((7)))`` - and only
    limits parens that actually change the evaluation order.
    """
    depth = 0
    for index in range(position, len(tokens)):
        token = tokens[index]
        if token.kind is TokenKind.LEFT_PAREN:
            depth += 1
        elif token.kind is TokenKind.RIGHT_PAREN:
            depth -= 1
            if depth == 0:
                inner = tokens[position + 1 : index]
                return not any(piece.kind is TokenKind.OPERATOR for piece in inner)
    return False


def _apply(operator: str, left: int, right: int) -> int:
    """Apply one operator, wrapping the result to 16 bits (spec 6.2)."""
    if operator == "+":
        return wrap16(left + right)
    if operator == "-":
        return wrap16(left - right)
    if operator == "*":
        return wrap16(left * right)
    if operator == "/":
        if right == 0:
            raise ExpressionError("division by zero")
        quotient = abs(left) // abs(right)
        return wrap16(-quotient if (left < 0) != (right < 0) else quotient)
    if operator == "\\":
        if right == 0:
            raise ExpressionError("modulo by zero")
        # Always positive (spec 5.1.7).
        return wrap16(abs(left) % abs(right))
    if operator == "=":
        return 1 if left == right else 0
    if operator == "<>":
        return 1 if left != right else 0
    if operator == "<":
        return 1 if left < right else 0
    if operator == "<=":
        return 1 if left <= right else 0
    if operator == ">":
        return 1 if left > right else 0
    if operator == ">=":
        return 1 if left >= right else 0
    raise ExpressionError(f"unknown operator {operator!r}")
