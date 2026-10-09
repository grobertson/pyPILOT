"""Host-independent input state for Atari controller senses."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final, Protocol

__all__ = [
    "ControllerKeyMap",
    "GraphicsState",
    "InteractiveCancelledError",
    "InteractiveDevice",
    "KeyboardController",
]

_DIRECTIONS: Final[dict[str, int]] = {"up": 1, "down": 2, "left": 4, "right": 8}
_JOYSTICK_KEYS: Final[dict[int, dict[str, str]]] = {
    0: {"up": "up", "down": "down", "left": "left", "right": "right"},
    1: {"up": "w", "down": "s", "left": "a", "right": "d"},
}
_TRIGGER_KEYS: Final[dict[int, str]] = {0: "enter", 1: "right ctrl", 8: "space", 9: "left ctrl"}
_PADDLE_KEYS: Final[dict[int, tuple[str, str]]] = {
    0: ("q", "e"),
    1: ("u", "o"),
}


@dataclass(frozen=True, slots=True)
class ControllerKeyMap:
    """Host key names assigned to Atari joystick, trigger, and paddle senses."""

    joysticks: Mapping[int, Mapping[str, str]] = field(
        default_factory=lambda: {number: dict(keys) for number, keys in _JOYSTICK_KEYS.items()}
    )
    triggers: Mapping[int, str] = field(default_factory=lambda: dict(_TRIGGER_KEYS))
    paddles: Mapping[int, tuple[str, str]] = field(default_factory=lambda: dict(_PADDLE_KEYS))


@dataclass(slots=True)
class GraphicsState:
    """Language-visible Atari graphics cursor and pen state."""

    active: bool = False
    x: float = 0.0
    y: float = 0.0
    angle: int = 0
    pen: str = "YELLOW"
    color_reader: Callable[[float, float], int] | None = field(default=None, repr=False)

    def special(self, name: str) -> int:
        """Read `%X`, `%Y`, `%A`, or `%Z`, returning neutral values when inactive."""
        if not self.active:
            return 0
        if name == "X":
            return round(self.x)
        if name == "Y":
            return round(self.y)
        if name == "A":
            return self.angle
        if name == "Z" and self.color_reader is not None:
            return self.color_reader(self.x, self.y)
        return 0


class InteractiveCancelledError(Exception):
    """Raised when the user closes the interactive window during a run."""


class InteractiveDevice(Protocol):
    """Host services used by the interpreter when interactive features are enabled."""

    @property
    def cancelled(self) -> bool: ...

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

    def read_controller(self, prefix: str, index: str) -> int: ...

    def set_audio_values(self, values: tuple[int, ...]) -> None: ...

    def pump_events(self) -> None: ...

    def read_line(self) -> str: ...

    def write(self, text: str) -> None: ...

    def newline(self) -> None: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


class KeyboardController:
    """Emulate two Atari joysticks, their triggers, and two paddles."""

    __slots__ = (
        "_joystick_keys",
        "_paddle_keys",
        "_paddle_rate",
        "_paddles",
        "_pressed",
        "_trigger_keys",
    )

    def __init__(
        self,
        *,
        paddle_rate: float = 120.0,
        keymap: ControllerKeyMap | None = None,
    ) -> None:
        mapping = keymap if keymap is not None else ControllerKeyMap()
        if any(
            direction not in _DIRECTIONS
            for directions in mapping.joysticks.values()
            for direction in directions
        ):
            raise ValueError("joystick key maps may only use up, down, left, and right")
        self._joystick_keys = {
            number: {direction: key.lower() for direction, key in directions.items()}
            for number, directions in mapping.joysticks.items()
        }
        self._trigger_keys = {number: key.lower() for number, key in mapping.triggers.items()}
        self._paddle_keys = {
            number: (decrease.lower(), increase.lower())
            for number, (decrease, increase) in mapping.paddles.items()
        }
        self._pressed: set[str] = set()
        self._paddles = [115.0] * 8
        self._paddle_rate = paddle_rate

    def set_key(self, key: str, pressed: bool) -> None:
        """Record a normalized key name from a host key event."""
        normalized = key.lower()
        if pressed:
            self._pressed.add(normalized)
        else:
            self._pressed.discard(normalized)

    def release_all(self) -> None:
        """Release held keys, as required when the window loses focus."""
        self._pressed.clear()

    def update(self, seconds: float) -> None:
        """Advance held paddle controls by elapsed wall-clock time."""
        if seconds <= 0:
            return
        for index, (decrease, increase) in self._paddle_keys.items():
            if not 0 <= index < len(self._paddles):
                continue
            direction = int(increase in self._pressed) - int(decrease in self._pressed)
            self._paddles[index] = min(
                227.0,
                max(3.0, self._paddles[index] + direction * self._paddle_rate * seconds),
            )

    def read(self, prefix: str, index: str = "") -> int:
        """Read one Atari controller sense, returning neutral for unmapped devices."""
        try:
            number = int(index) if index else 0
        except ValueError:
            return 0

        kind = prefix.upper()
        if kind == "J":
            keys = self._joystick_keys.get(number)
            if keys is None:
                return 0
            return sum(
                _DIRECTIONS[direction] for direction, key in keys.items() if key in self._pressed
            )
        if kind == "P" and 0 <= number < len(self._paddles):
            return int(self._paddles[number])
        if kind == "T":
            key = self._trigger_keys.get(number)
            return int(key in self._pressed) if key is not None else 0
        return 0
