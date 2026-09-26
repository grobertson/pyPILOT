"""The `M:` and `MS:` match commands (spec 6.1.3, 6.1.4), and the `JM:` operand
grammar (spec 6.1.8) that consumes the ordinal they produce.

Matching in ATARI PILOT is unlike every other PILOT dialect, and the
differences are the whole point of this module:

**Matching is a substring search within the buffer.** ``M:YE`` *does* match the
input ``YEAH``; spec 6.1.3 calls this "less precise matching of character
substrings within words" and the looseness is deliberate. This is what makes
``<right arrow>`` meaningful: because the field is located *within* the buffer,
an arrow is how a program says *start looking here rather than at the first
occurrence*.

**The field separator is a comma, or a vertical bar if the operand starts with
one.** There is never a case where both act as separators.

**The result is an ordinal, not a boolean.** The field that matched determines
the value, so ``JM:`` can branch three ways on a three-way ``M:``.

**The buffer is normalised** (spec 7.2.2), so it always carries a leading and
trailing blank and is always upper case. A match field written in lower case
will not match, and this is deliberate: the Atari manuals write their fields in
upper case for exactly this reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pypilot.errors import PilotRuntimeError

__all__ = [
    "CURSOR_RIGHT",
    "FIELD_SEPARATORS",
    "MatchOutcome",
    "split_fields",
    "split_jump_labels",
]

#: ATASCII cursor-right (ESC CTRL-), the character that skips forward in the
#: accept buffer (spec 6.1.3). Written literally in a program as ``\x1e``.
CURSOR_RIGHT: Final = "\x1e"

#: The two legal field separators. A leading ``|`` selects the second (spec
#: 6.1.3); otherwise the separator is a comma.
FIELD_SEPARATORS: Final = (",", "|")

#: A run of commas and/or blanks, which spec 4.5 makes a **single** separator.
#:
#: This is the separator rule for every operand *except* ``M:``/``MS:``, where
#: blanks are significant data. ``JM:`` follows the general rule, which is what
#: lets the manuals write ``JM:*HERE , *THERE`` and ``JM:*L1 *L2 *L3`` and mean
#: the same thing.
#:
#: The class is a literal blank, not ``\s``, on purpose: a PILOT operand ends at
#: the end of the line, and ``\s`` would let a continuation line be swallowed
#: into the one before it.
_GENERIC_SEPARATOR: Final = re.compile(r"[,\x20]+")


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    """The result of one ``M:`` or ``MS:``.

    ``ordinal`` is the **1-based index of the field that matched**, or 0 when
    nothing matched. It is the value ``%M`` reports and the one ``JM:``
    branches on (spec 6.1.3).
    """

    ordinal: int = 0
    matched: bool = False
    left: str = ""
    """Buffer text left of the match; empty when the match starts at 0."""

    match: str = ""
    """The matched field, as written - not as it appears in the buffer."""

    right: str = ""
    """Buffer text right of the match."""

    skipped: int = 0
    """Characters skipped by ``<right arrow>`` before matching began.

    ``$LEFT`` deliberately does **not** include these (spec 6.1.4), so they
    are recorded separately rather than folded into ``left``.
    """


def split_fields(operand: str) -> tuple[list[str], int]:
    """Split a match operand into fields, returning them and the skip count.

    Args:
        operand: the text right of the ``:`` in an ``M:`` or ``MS:``.

    Returns:
        ``(fields, skipped)``. A leading ``|`` selects the vertical-bar
        separator rather than introducing an empty first field (spec 6.1.3), and
        leading cursor-right characters are consumed as a skip count.

    Raises:
        PilotRuntimeError: if the operand is null, which spec 6.1.3 forbids.
    """
    if not operand:
        raise PilotRuntimeError("M: requires at least one match field (spec 6.1.3)")

    text = operand
    separator = FIELD_SEPARATORS[0]

    if text.startswith(FIELD_SEPARATORS[1]):
        # A leading bar selects the separator; it is not itself a field.
        separator = FIELD_SEPARATORS[1]
        text = text[1:]

    skipped = 0
    while text.startswith(CURSOR_RIGHT):
        skipped += 1
        text = text[1:]

    # A trailing underscore is a trailing blank (spec 5.2.3), which is the
    # idiomatic way to match a word *plus* the buffer's mandatory trailing
    # space: `M:YES,YEAH,SURE_`.
    #
    # Note that `text` is deliberately not re-checked for emptiness here. Spec
    # 6.1.3's own special-case table lists `M:,` as "will match anything (null
    # match)" - the same as `M:THIS,THAT,,OTHER` - so an operand of nothing but
    # separators is legal. Only a wholly **null operand** (`M:`, rejected by the
    # parser) is forbidden.
    return text.split(separator), skipped


def split_jump_labels(operand: str) -> list[str]:
    """Split a ``JM:`` operand into its positional target labels (spec 6.1.8).

    The grammar is recursive rather than a flat list::

        <jump match operand> ::= <label> [<sep><jump match operand>]

    which matters because spec 4.5 makes **any run** of commas and/or blanks a
    single separator, to the right of the colon. So all of these are the same
    three-way branch::

        JM:*L1 *L2 *L3
        JM:*HERE , *THERE , *EVERYWHERE
        JM: *L1,,*L2 ,, *L3

    Note this is the *opposite* of the ``M:`` rule, where blanks are significant
    data and only a comma separates (spec 4.5's exception). Labels are
    alphanumeric (spec 4.2), so a blank is always a separator here and can never
    be part of a label - that is what makes the space-separated form
    unambiguous.

    The leading ``*`` is kept: it is stripped per-label at resolution time, so
    a program may write ``*LOOP`` or plain ``LOOP`` interchangeably (spec 10.2).

    A null operand yields an empty list, which ``JM:`` treats as a no-op rather
    than an error.
    """
    if not operand.strip():
        return []
    return [label for label in _GENERIC_SEPARATOR.split(operand.strip()) if label]


def find_match(buffer: str, fields: list[str], skipped: int = 0) -> MatchOutcome:
    """Match ``buffer`` against ``fields``, in order (spec 6.1.3).

    The buffer is scanned for field 1, then field 2, and so on, until one is
    found. The scan is a **substring search**: spec 6.1.3 describes it as
    finding *"an exact match with one of the Match command fields"*, and the
    manual calls ``M:YE,SURE`` *"a less precise matching of character
    substrings within words"* — that looseness is deliberate, not an accident.

    That is also why ``<right arrow>`` exists. Because the field is located
    *within* the buffer, ``$LEFT`` and ``$RIGHT`` are the text either side of
    wherever it landed, and a right arrow is how a program says *look here
    rather than at the first occurrence*.

    ``skipped`` is the number of those arrows. Spec 6.1.3 says they cause
    matching to *"start at the n+1th character of the accept buffer"*, so
    ``n`` arrows leave the character at index *n* as the first considered.

    An **empty field is a null match** and matches anything — that is spec
    6.1.3's own example, ``M:THIS,THAT,,OTHER``, where the empty third field
    catches every input the first two missed.
    """
    if skipped:
        # "start at the n+1th character" is 1-based, so n arrows leave the
        # character at index n as the first one considered.
        buffer = buffer[skipped:]

    for index, field in enumerate(fields, start=1):
        if field == "":
            # A null field matches anything, at the start of what is left.
            return MatchOutcome(
                ordinal=index,
                matched=True,
                left="",
                match=field,
                right=buffer,
                skipped=skipped,
            )
        position = buffer.find(field)
        if position != -1:
            return MatchOutcome(
                ordinal=index,
                matched=True,
                left=buffer[:position],
                match=field,
                right=buffer[position + len(field) :],
                skipped=skipped,
            )

    return MatchOutcome(ordinal=0, matched=False, skipped=skipped)
