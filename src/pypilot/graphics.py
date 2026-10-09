"""Interpreter for the ATARI PILOT ``GR:`` operand language."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pypilot.errors import PilotRuntimeError
from pypilot.interactive import GraphicsState

__all__ = ["MAX_GRAPHICS_OPERATIONS", "MAX_GRAPHICS_REPEAT_DEPTH", "GraphicsEngine", "GraphicsHost"]

MAX_GRAPHICS_OPERATIONS = 1_000_000
MAX_GRAPHICS_REPEAT_DEPTH = 16
_COMMANDS = (
    "DRAWTO",
    "FILLTO",
    "TURNTO",
    "CLEAR",
    "PEN",
    "GOTO",
    "TURN",
    "GO",
    "DRAW",
    "FILL",
    "QUIT",
)
_PEN_COLORS = frozenset({"RED", "YELLOW", "BLUE", "ERASE", "UP"})
_COUNT_RE = re.compile(r"(?:\d+|#[A-Za-z])")
_WORD_RE = re.compile(r"[A-Za-z]+")


class GraphicsHost(Protocol):
    """Drawing and event operations required by the language engine."""

    def start_graphics(self) -> None: ...

    def clear_graphics(self) -> None: ...

    def plot(self, x: float, y: float, color: str) -> None: ...

    def draw_line(
        self, start_x: float, start_y: float, end_x: float, end_y: float, color: str
    ) -> None: ...

    def fill_line(
        self, start_x: float, start_y: float, end_x: float, end_y: float, color: str
    ) -> None: ...

    def color_at(self, x: float, y: float) -> int: ...

    def quit_graphics(self) -> None: ...

    def pump_events(self) -> None: ...


@dataclass(frozen=True, slots=True)
class _Command:
    name: str
    operand: str


@dataclass(frozen=True, slots=True)
class _Repeat:
    count: str
    commands: tuple[_Command | _Repeat, ...]


_Operation = _Command | _Repeat


class _Parser:
    """Parse semicolon-separated graphics commands and repeat groups."""

    __slots__ = ("position", "repeat_depth", "text")

    def __init__(self, text: str) -> None:
        self.text = text
        self.position = 0
        self.repeat_depth = 0

    def parse(self) -> tuple[_Operation, ...]:
        operations = self._sequence(in_repeat=False)
        if self.position != len(self.text):
            raise PilotRuntimeError("GR: unexpected closing parenthesis")
        if not operations:
            raise PilotRuntimeError("GR: requires at least one graphics sub-command")
        return tuple(operations)

    def _sequence(self, *, in_repeat: bool) -> list[_Operation]:
        operations: list[_Operation] = []
        while True:
            self._skip_separators()
            if self.position >= len(self.text):
                if in_repeat:
                    raise PilotRuntimeError("GR: unterminated repeat group")
                return operations
            if self.text[self.position] == ")":
                if not in_repeat:
                    raise PilotRuntimeError("GR: unexpected closing parenthesis")
                return operations

            repeat = self._repeat()
            if repeat is not None:
                operations.append(repeat)
            else:
                operations.append(self._command(in_repeat=in_repeat))

    def _repeat(self) -> _Repeat | None:
        match = _COUNT_RE.match(self.text, self.position)
        if match is None:
            return None
        end = match.end()
        while end < len(self.text) and self.text[end].isspace():
            end += 1
        if end >= len(self.text) or self.text[end] not in "(xX":
            return None

        count = match.group(0)
        marker = self.text[end]
        if marker == "(":
            if self.repeat_depth >= MAX_GRAPHICS_REPEAT_DEPTH:
                raise PilotRuntimeError(
                    f"GR: repeat nesting exceeds {MAX_GRAPHICS_REPEAT_DEPTH} levels"
                )
            self.position = end + 1
            self.repeat_depth += 1
            try:
                commands = self._sequence(in_repeat=True)
            finally:
                self.repeat_depth -= 1
            if self.position >= len(self.text) or self.text[self.position] != ")":
                raise PilotRuntimeError("GR: unterminated repeat group")
            self.position += 1
            return _Repeat(count, tuple(commands))

        self.position = end + 1
        while self.position < len(self.text) and self.text[self.position].isspace():
            self.position += 1
        command = self._command(in_repeat=True)
        return _Repeat(count, (command,))

    def _command(self, *, in_repeat: bool) -> _Command:
        match = _WORD_RE.match(self.text, self.position)
        if match is None:
            raise PilotRuntimeError(
                f"GR: expected a sub-command near {self.text[self.position :]!r}"
            )
        name = match.group(0).upper()
        if name not in _COMMANDS:
            raise PilotRuntimeError(f"GR: unknown sub-command {name}")

        self.position = match.end()
        start = self.position
        depth = 0
        while self.position < len(self.text):
            char = self.text[self.position]
            if char == "(":
                depth += 1
            elif char == ")":
                if depth:
                    depth -= 1
                elif in_repeat:
                    break
                else:
                    raise PilotRuntimeError("GR: unexpected closing parenthesis")
            elif char == ";" and depth == 0:
                break
            self.position += 1

        if depth:
            raise PilotRuntimeError("GR: unbalanced numeric-expression parentheses")
        return _Command(name, self.text[start : self.position].strip())

    def _skip_separators(self) -> None:
        while self.position < len(self.text) and (
            self.text[self.position].isspace() or self.text[self.position] == ";"
        ):
            self.position += 1


class GraphicsEngine:
    """Execute graphics operands against shared PILOT state and a host renderer."""

    __slots__ = (
        "evaluate",
        "get_number",
        "host",
        "line",
        "max_operations",
        "operation_count",
        "source",
        "state",
    )

    def __init__(
        self,
        state: GraphicsState,
        host: GraphicsHost,
        *,
        evaluate: Callable[[str], int],
        get_number: Callable[[str], int],
        max_operations: int = MAX_GRAPHICS_OPERATIONS,
    ) -> None:
        self.state = state
        self.host = host
        self.evaluate = evaluate
        self.get_number = get_number
        self.max_operations = max_operations
        self.operation_count = 0
        self.line: int | None = None
        self.source: str | None = None
        self.state.color_reader = host.color_at

    def execute(self, operand: str, *, line: int | None = None, source: str | None = None) -> None:
        """Parse and execute a ``GR:`` operand, attaching PILOT source context."""
        self.line = line
        self.source = source
        self.operation_count = 0
        try:
            self._execute_operations(_Parser(operand).parse())
        except PilotRuntimeError as exc:
            if exc.line is not None:
                raise
            raise PilotRuntimeError(str(exc), line=line, source=source) from exc

    def _execute_operations(self, operations: tuple[_Operation, ...]) -> None:
        for operation in operations:
            if isinstance(operation, _Repeat):
                count = self._count(operation.count)
                if not 0 <= count <= 65535:
                    raise PilotRuntimeError(
                        f"GR: repeat count must be from 0 through 65535, not {count}"
                    )
                for _ in range(count):
                    self._execute_operations(operation.commands)
            else:
                self.operation_count += 1
                if self.operation_count > self.max_operations:
                    raise PilotRuntimeError(
                        f"GR: executed more than {self.max_operations} sub-commands"
                    )
                self._execute_command(operation)
                self.host.pump_events()

    def _count(self, count: str) -> int:
        if count.startswith("#"):
            try:
                return self.get_number(count[1:])
            except PilotRuntimeError as exc:
                raise PilotRuntimeError(f"GR: invalid repeat count {count}: {exc}") from exc
        return int(count)

    def _activate(self) -> None:
        if self.state.active:
            return
        self.host.start_graphics()
        self.state.active = True
        self.state.x = 0.0
        self.state.y = 0.0
        self.state.angle = 0
        self.state.pen = "YELLOW"
        self.host.clear_graphics()

    def _execute_command(self, command: _Command) -> None:
        self._activate()
        name = command.name
        operand = command.operand
        if name == "CLEAR":
            self._require_empty(name, operand)
            self.state.x = self.state.y = 0.0
            self.state.angle = 0
            self.state.pen = "YELLOW"
            self.host.clear_graphics()
        elif name == "QUIT":
            self._require_empty(name, operand)
            self.host.quit_graphics()
            self.state.active = False
        elif name == "PEN":
            color = operand.upper()
            if color not in _PEN_COLORS:
                raise PilotRuntimeError(
                    f"GR:PEN requires RED, YELLOW, BLUE, ERASE, or UP, not {operand!r}"
                )
            self.state.pen = color
        elif name in {"GOTO", "DRAWTO", "FILLTO"}:
            end_x, end_y = self._coordinates(operand, name)
            start_x, start_y = self.state.x, self.state.y
            if name == "GOTO":
                if self.state.pen != "UP":
                    self.host.plot(end_x, end_y, self.state.pen)
            elif self.state.pen != "UP":
                draw = self.host.fill_line if name == "FILLTO" else self.host.draw_line
                draw(start_x, start_y, end_x, end_y, self.state.pen)
            self.state.x, self.state.y = end_x, end_y
        elif name in {"TURNTO", "TURN"}:
            angle = self._number(operand, name)
            self.state.angle = (angle if name == "TURNTO" else self.state.angle + angle) % 360
        elif name in {"GO", "DRAW", "FILL"}:
            units = self._number(operand, name)
            radians = math.radians(self.state.angle)
            end_x = _limit(self.state.x + units * math.sin(radians))
            end_y = _limit(self.state.y + units * math.cos(radians))
            start_x, start_y = self.state.x, self.state.y
            if self.state.pen != "UP":
                if name == "GO":
                    self.host.plot(end_x, end_y, self.state.pen)
                else:
                    draw = self.host.fill_line if name == "FILL" else self.host.draw_line
                    draw(start_x, start_y, end_x, end_y, self.state.pen)
            self.state.x, self.state.y = end_x, end_y
        else:
            raise PilotRuntimeError(f"GR: unsupported sub-command {name}")

    def _number(self, operand: str, command: str) -> int:
        if not operand:
            raise PilotRuntimeError(f"GR:{command} numeric operand is empty")
        try:
            return self.evaluate(operand)
        except PilotRuntimeError as exc:
            raise PilotRuntimeError(
                f"GR:{command} invalid numeric operand {operand!r}: {exc}"
            ) from exc

    def _coordinates(self, operand: str, command: str) -> tuple[float, float]:
        if "," in operand:
            parts = operand.split(",")
            if len(parts) != 2:
                raise PilotRuntimeError(f"GR:{command} expected x,y coordinates, not {operand!r}")
            return (
                _limit(float(self._number(parts[0], command))),
                _limit(float(self._number(parts[1], command))),
            )

        last_error: PilotRuntimeError | None = None
        for match in re.finditer(r"\s+", operand):
            try:
                return (
                    _limit(float(self._number(operand[: match.start()], command))),
                    _limit(float(self._number(operand[match.end() :], command))),
                )
            except PilotRuntimeError as exc:
                last_error = exc
        if last_error is not None:
            raise PilotRuntimeError(
                f"GR:{command} expected x,y coordinates: {last_error}"
            ) from last_error
        raise PilotRuntimeError(f"GR:{command} expected x,y coordinates, not {operand!r}")

    @staticmethod
    def _require_empty(name: str, operand: str) -> None:
        if operand:
            raise PilotRuntimeError(f"GR:{name} does not take an operand")


def _limit(value: float) -> float:
    if abs(value) < 1e-10:
        return 0.0
    return min(32767.0, max(-32767.0, value))
