from __future__ import annotations

from pypilot.interactive import InteractiveDevice
from pypilot.io import BufferOutput
from pypilot.runtime import Interpreter
from pypilot.state import PilotState
from pypilot.syntax import parse


class FakeInteractive:
    def __init__(self) -> None:
        self.cancelled = False
        self.operations: list[tuple[object, ...]] = []
        self.audio_updates: list[tuple[int, ...]] = []
        self.controller_values = {("J", "0"): 1}
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
        return 2

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


def test_runtime_executes_graphics_through_injected_host() -> None:
    host: InteractiveDevice = FakeInteractive()
    state = PilotState()
    interpreter = Interpreter(parse("GR:GOTO 0,0;TURNTO 90;DRAW 10"), state=state, interactive=host)

    interpreter.run()

    assert state.graphics.x == 10
    assert state.graphics.y == 0
    assert state.evaluate("%A").value == 90
    assert any(operation[0] == "line" for operation in host.operations)  # type: ignore[attr-defined]


def test_runtime_reads_keyboard_controller_senses_in_conditions() -> None:
    host: InteractiveDevice = FakeInteractive()
    output = BufferOutput()
    interpreter = Interpreter(
        parse("T(%J0=1):PRESSED"),
        state=PilotState(),
        output=output,
        interactive=host,
    )

    interpreter.run()

    assert output.text == "PRESSED\n"


def test_runtime_refreshes_sound_sources_after_each_statement() -> None:
    host = FakeInteractive()
    state = PilotState()
    interpreter = Interpreter(
        parse("C:#A=1\nSO:#A\nC:#A=13\nSO:"),
        state=state,
        interactive=host,
    )

    interpreter.run()

    assert (1,) in host.audio_updates
    assert (13,) in host.audio_updates
    assert host.audio_updates[-1] == ()


def test_runtime_gr_and_so_without_interactive_host_fail_clearly() -> None:
    for source in ("GR:CLEAR", "SO:1"):
        interpreter = Interpreter(parse(source))
        try:
            interpreter.run()
        except Exception as exc:
            assert "interactive host" in str(exc)
        else:
            raise AssertionError(f"{source} requires an interactive host")
