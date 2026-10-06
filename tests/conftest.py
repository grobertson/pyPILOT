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


class FakeInteractive:
    """Recording host for graphics, controller, and audio integration tests."""

    def __init__(self) -> None:
        self.cancelled = False
        self.operations: list[tuple[object, ...]] = []
        self.audio_updates: list[tuple[int, ...]] = []
        self.controller_values: dict[tuple[str, str], int] = {}
        self.text = BufferOutput()

    def start_graphics(self) -> None:
        self.operations.append(("start",))

    def clear_graphics(self) -> None:
        self.operations.append(("clear",))

    def plot(self, x: float, y: float, color: str) -> None:
        self.operations.append(("plot", x, y, color))

    def draw_line(
        self, start_x: float, start_y: float, end_x: float, end_y: float, color: str
    ) -> None:
        self.operations.append(("line", start_x, start_y, end_x, end_y, color))

    def fill_line(
        self, start_x: float, start_y: float, end_x: float, end_y: float, color: str
    ) -> None:
        self.operations.append(("fill", start_x, start_y, end_x, end_y, color))

    def color_at(self, _x: float, _y: float) -> int:
        return 0

    def quit_graphics(self) -> None:
        self.operations.append(("quit",))

    def read_controller(self, prefix: str, index: str) -> int:
        return self.controller_values.get((prefix, index), 0)

    def set_audio_values(self, values: tuple[int, ...]) -> None:
        self.audio_updates.append(values)

    def pump_events(self) -> None:
        pass

    def read_line(self) -> str:
        return ""

    def write(self, text: str) -> None:
        self.text.write(text)

    def newline(self) -> None:
        self.text.newline()

    def flush(self) -> None:
        self.text.flush()

    def close(self) -> None:
        self.operations.append(("close",))


@pytest.fixture
def interactive_host() -> FakeInteractive:
    return FakeInteractive()


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
