"""pyPILOT - an implementation of the PILOT programming language.

PILOT (Programmed Inquiry, Learning, or Teaching) is an imperative teaching
language created by John Amsden Starkweather in the late 1960s and formalised
as a machine-independent specification in 1973 ("PILOT-73").

The implementation is being built in stages; see ``SPEC.md`` for the language
specification and the implementation roadmap.
"""

from __future__ import annotations

from importlib.metadata import version as _package_version

from pypilot.errors import (
    PilotError,
    PilotRuntimeError,
    PilotSyntaxError,
    PilotUndefinedLabelError,
    PilotUnsupportedError,
)
from pypilot.state import MatchResult, PilotState
from pypilot.syntax import CommandName, Condition, Parser, Program, Statement, decode_source, parse
from pypilot.values import Kind, Numeric, expand_text

# Read from installed package metadata so this can never drift from
# pyproject.toml, which is the single source of truth for the version.
__version__ = _package_version("pypilot")

__all__ = [
    "CommandName",
    "Condition",
    "Kind",
    "MatchResult",
    "Numeric",
    "Parser",
    "PilotError",
    "PilotRuntimeError",
    "PilotState",
    "PilotSyntaxError",
    "PilotUndefinedLabelError",
    "PilotUnsupportedError",
    "Program",
    "Statement",
    "__version__",
    "decode_source",
    "expand_text",
    "parse",
]
