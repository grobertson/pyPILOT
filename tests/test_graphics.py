from __future__ import annotations

import pytest

from pypilot.errors import PilotRuntimeError
from pypilot.graphics import GraphicsEngine
from pypilot.state import PilotState


class RecordingHost:
    def __init__(self) -> None:
        self.operations: list[tuple[object, ...]] = []

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
        return 3

    def quit_graphics(self) -> None:
        self.operations.append(("quit",))

    def pump_events(self) -> None:
        self.operations.append(("pump",))


def engine(state: PilotState, host: RecordingHost) -> GraphicsEngine:
    return GraphicsEngine(
        state.graphics,
        host,
        evaluate=lambda expression: state.evaluate(expression).value,
        get_number=lambda name: state.get_number(name).value,
    )


def test_graphics_repeat_draws_closed_square_and_updates_specials() -> None:
    state = PilotState()
    host = RecordingHost()

    engine(state, host).execute("GOTO 0,0;TURNTO 0;4(DRAW 10;TURN 90)", line=7, source="GR:...")

    assert state.evaluate("%X").value == 0
    assert state.evaluate("%Y").value == 0
    assert state.evaluate("%A").value == 0
    assert state.evaluate("%Z").value == 3
    assert sum(operation[0] == "line" for operation in host.operations) == 4


def test_graphics_pen_up_moves_without_drawing() -> None:
    state = PilotState()
    host = RecordingHost()

    engine(state, host).execute("PEN UP;DRAW 10;GOTO 3,4")

    assert state.graphics.x == 3
    assert state.graphics.y == 4
    assert not any(operation[0] in {"line", "plot", "fill"} for operation in host.operations)


def test_graphics_repeat_count_can_be_a_numeric_variable() -> None:
    state = PilotState()
    state.set_number("A", 3)
    host = RecordingHost()

    engine(state, host).execute("TURNTO 90;#A(DRAW 2)")

    assert state.graphics.x == 6
    assert state.graphics.y == 0
    assert sum(operation[0] == "line" for operation in host.operations) == 3


def test_graphics_fill_and_quit_are_forwarded_to_host() -> None:
    state = PilotState()
    host = RecordingHost()

    engine(state, host).execute("FILLTO 5,0;QUIT")

    assert any(operation[0] == "fill" for operation in host.operations)
    assert host.operations[-2][0] == "quit"
    assert not state.graphics.active


def test_graphics_errors_include_the_pilot_source_location() -> None:
    state = PilotState()
    host = RecordingHost()

    try:
        engine(state, host).execute("DRAWTO 2", line=12, source="GR:DRAWTO 2")
    except PilotRuntimeError as exc:
        assert exc.line == 12
        assert exc.source == "GR:DRAWTO 2"
        assert "coordinates" in str(exc)
    else:
        raise AssertionError("malformed coordinates should fail")


def test_graphics_repeat_nesting_is_bounded() -> None:
    from pypilot.graphics import MAX_GRAPHICS_REPEAT_DEPTH

    nested = (
        "1(" * (MAX_GRAPHICS_REPEAT_DEPTH + 1) + "CLEAR" + ")" * (MAX_GRAPHICS_REPEAT_DEPTH + 1)
    )
    with pytest.raises(PilotRuntimeError, match="repeat nesting exceeds"):
        engine(PilotState(), RecordingHost()).execute(nested)


def test_graphics_operation_count_is_bounded() -> None:
    with pytest.raises(PilotRuntimeError, match="more than 2 sub-commands"):
        GraphicsEngine(
            PilotState().graphics,
            RecordingHost(),
            evaluate=lambda expression: int(expression),
            get_number=lambda _name: 0,
            max_operations=2,
        ).execute("3(DRAW 1)")
