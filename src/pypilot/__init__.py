"""pyPILOT - an implementation of the PILOT programming language.

PILOT (Programmed Inquiry, Learning, or Teaching) is an imperative teaching
language created by John Amsden Starkweather in the late 1960s and formalised
as a machine-independent specification in 1973 ("PILOT-73").

Two names, deliberately: the importable package is ``pypilot`` and the PyPI
distribution is ``rePILOT``, because ``pypilot`` is taken on PyPI by an
unrelated package. So it is installed as ``repilot`` and imported as
``pypilot``.

The complete 1.0 implementation is documented in ``SPEC.md``, including the
language specification and implementation history.
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
#
# The *distribution* is `rePILOT` even though the *package* is `pypilot`, so
# this must not guess. Asking for "pypilot" here worked until the distribution
# was renamed, and then failed with `PackageNotFoundError` on the very first
# import - a brutal way to discover a packaging change. `importlib.metadata`
# normalises the name, so the lower-case spelling is what a lookup needs.
_DISTRIBUTION = "repilot"

try:
    __version__ = _package_version(_DISTRIBUTION)
except Exception:
    # Not an error worth raising: the package is perfectly usable from a
    # checkout, it just has no installed metadata to read a version from.
    __version__ = "0.0.0.dev0"

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
