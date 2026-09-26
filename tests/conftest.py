"""Shared pytest fixtures for the pyPILOT test suite."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from pypilot import __version__
from pypilot.io import BufferOutput, StringInput
from pypilot.runtime import Interpreter, TraceEvent
from pypilot.state import PilotState
from pypilot.syntax import Program, parse


@pytest.fixture
def version() -> str:
    """The package version string."""
    return __version__


@pytest.fixture
def state() -> PilotState:
    """A fresh interpreter state."""
    return PilotState()


@pytest.fixture
def out() -> BufferOutput:
    """An output device that collects text for assertions."""
    return BufferOutput()


@pytest.fixture
def feed() -> StringInput:
    """A scripted input device, for Stage 5's `A:` handler."""
    return StringInput([])


def run_program(
    source: str,
    lines: Sequence[str] | None = None,
    *,
    state: PilotState | None = None,
    feed: StringInput | None = None,
    trace: bool = False,
    device_root: Path | None = None,
) -> tuple[str, PilotState, list[TraceEvent]]:
    """Parse and run ``source``, returning its output, state and trace.

    The workhorse for the interpreter tests: it wires a program to a buffer
    rather than a terminal so the output can be asserted on.

    Args:
        source: PILOT program text.
        lines: input lines to script for `A:` statements, in order. May also be
            passed as a `StringInput` via ``feed`` when a test needs to inspect
            how much input was consumed.
        state: an existing state to continue from.
        feed: a pre-built input device, taking precedence over ``lines``.
        trace: collect :class:`~pypilot.runtime.TraceEvent` records.
        device_root: where the emulated cassette and diskette live. **Always
            pass this in a device test** - the default is under the user's home
            directory, and a test that writes there is a test that litters.
    """
    program: Program = parse(source)
    out = BufferOutput()
    events: list[TraceEvent] = []
    if feed is None:
        feed = StringInput(list(lines) if lines else [])
    interpreter = Interpreter(
        program,
        state=state if state is not None else PilotState(),
        output=out,
        source=feed,
        trace=events.append if trace else None,
        device_root=device_root,
    )
    interpreter.tracing = trace
    interpreter.run()
    return out.text, interpreter.state, events


@pytest.fixture
def run():  # type: ignore[no-untyped-def]
    """Fixture form of :func:`run_program`, for terser test bodies."""
    return run_program


@pytest.fixture
def write_program(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Return a factory that writes a temporary PILOT source file."""

    def _write(name: str, source: str) -> Path:
        path = tmp_path / name
        path.write_text(source, encoding="utf-8", newline="\n")
        return path

    return _write
