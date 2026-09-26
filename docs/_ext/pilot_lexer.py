"""A minimal Pygments lexer for PILOT program source.

PILOT has no built-in highlighting. This lexer gives the documentation reasonable
colours for single-letter command statements, labels, remarks, and variables.
"""

from __future__ import annotations

from typing import ClassVar

from pygments.lexer import RegexLexer, bygroups
from pygments.token import Comment, Keyword, Name, Number, Punctuation, String, Text

__all__ = ["PilotLexer"]


class PilotLexer(RegexLexer):
    """Syntax highlighting for PILOT source."""

    name = "PILOT"
    aliases = ["pilot"]
    filenames = ["*.pilot"]
    mimetypes = ["text/x-pilot"]

    tokens: ClassVar[dict[str, list[tuple[str, str]]]] = {
        "root": [
            # A remark / comment occupies the whole line.
            (r"^R:.*$", Comment.Single),
            # A label, alone or in front of a statement.
            (r"^\*[\w]+", Name.Label),
            # Command letter, optional H modifier, optional condition, then colon.
            (
                r"^([A-Z])(H)?(\([^)]*\))?(:)",
                bygroups(Keyword, Keyword, Keyword.Constant, Punctuation),
            ),
            # A statement whose command letter was omitted (repeats the previous).
            (r"^(\([^)]*\))?(:)", bygroups(Keyword.Constant, Punctuation)),
            # Variables: string, numeric, system.
            (r"[$#%][A-Za-z_]\w*", Name.Variable),
            (r"-?\d+(?:\.\d+)?", Number),
            (r'"[^"]*"', String),
            (r"[*,()]", Punctuation),
            (r"\\\\.", Text),
            (r"\s+", Text),
            (r"[^\s]+", Text),
        ],
    }
