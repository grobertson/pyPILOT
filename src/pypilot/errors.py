"""Exception hierarchy for pyPILOT.

Every error raised by the interpreter derives from :class:`PilotError` so that
embedding applications can catch a single base class.

Errors carry the 1-based source line number (and, where meaningful, the source
text) so a runtime failure can be reported to the learner in the same way a
1980s interpreter would have reported it on a CRT.
"""

from __future__ import annotations

__all__ = [
    "PilotError",
    "PilotRuntimeError",
    "PilotSyntaxError",
    "PilotUndefinedLabelError",
    "PilotUnsupportedError",
]


class PilotError(Exception):
    """Base class for every error raised by the pyPILOT interpreter."""

    def __init__(self, message: str, *, line: int | None = None, source: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.source = source

    def __str__(self) -> str:
        if self.line is None:
            return self.message
        location = f"line {self.line}"
        if self.source:
            return f"{location}: {self.message}\n  {self.source.rstrip()}"
        return f"{location}: {self.message}"


class PilotSyntaxError(PilotError):
    """Raised when a program cannot be tokenised or parsed."""


class PilotRuntimeError(PilotError):
    """Raised for errors detected while executing an already-parsed program."""


class PilotUndefinedLabelError(PilotRuntimeError):
    """Raised when a ``J:`` or ``U:`` statement names a label that does not exist."""


class PilotUnsupportedError(PilotRuntimeError):
    """Raised when a program uses a statement the interpreter deliberately does not implement."""
