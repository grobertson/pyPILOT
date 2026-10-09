"""Optional Pygame CE host for the interpreter's interactive devices.

Pygame is imported only when a window or audio device is first requested.
"""

from __future__ import annotations

import importlib
import math
import sys
import time
from array import array
from collections import deque
from typing import Any, cast

from pypilot.errors import PilotUnsupportedError
from pypilot.interactive import ControllerKeyMap, InteractiveCancelledError, KeyboardController
from pypilot.io import ConsoleInput, ConsoleOutput, InputDevice, OutputDevice

__all__ = ["PygameInteractiveDevice"]

_WINDOW_SIZE = (960, 720)
_GRAPHICS_SIZE = (960, 480)
_TEXT_HEIGHT = _WINDOW_SIZE[1] - _GRAPHICS_SIZE[1]
_BACKGROUND = (0, 0, 0)
_TEXT_BACKGROUND = (0, 85, 170)
_COLORS = {
    "RED": (255, 0, 0),
    "YELLOW": (255, 255, 0),
    "BLUE": (0, 0, 255),
    "ERASE": _BACKGROUND,
}
_COLOR_VALUES = {
    color: value
    for value, color in enumerate((_BACKGROUND, _COLORS["RED"], _COLORS["YELLOW"], _COLORS["BLUE"]))
}
_SAMPLE_RATE = 44100


class PygameInteractiveDevice:
    """Pygame CE display, keyboard, output, input, and four-voice audio device."""

    __slots__ = (
        "_audio_notes",
        "_audio_ready",
        "_cancelled",
        "_clock",
        "_controller",
        "_fallback_input",
        "_fallback_output",
        "_font",
        "_graphics_active",
        "_graphics_surface",
        "_input_buffer",
        "_input_result",
        "_last_update",
        "_pygame",
        "_text_lines",
        "_text_only",
        "_title",
        "_tone_cache",
        "_window",
    )

    def __init__(
        self,
        fallback_output: OutputDevice | None = None,
        fallback_input: InputDevice | None = None,
        *,
        title: str = "rePILOT Interactive",
        controller_keymap: ControllerKeyMap | None = None,
    ) -> None:
        self._fallback_output = fallback_output if fallback_output is not None else ConsoleOutput()
        self._fallback_input = fallback_input if fallback_input is not None else ConsoleInput()
        self._title = title
        self._pygame: Any = None
        self._window: Any = None
        self._graphics_surface: Any = None
        self._font: Any = None
        self._clock: Any = None
        self._graphics_active = False
        self._text_only = False
        self._cancelled = False
        self._controller = KeyboardController(keymap=controller_keymap)
        self._last_update = time.monotonic()
        self._text_lines: deque[str] = deque([""], maxlen=10)
        self._input_buffer: str | None = None
        self._input_result: str | None = None
        self._audio_ready = False
        self._audio_notes = [0, 0, 0, 0]
        self._tone_cache: dict[int, Any] = {}

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def window_open(self) -> bool:
        return self._window is not None

    def _load(self) -> Any:
        if self._pygame is None:
            try:
                self._pygame = importlib.import_module("pygame")
            except ImportError as exc:
                raise PilotUnsupportedError(
                    "interactive graphics, input, or sound requires pygame-ce; "
                    "install rePILOT with the [interactive] extra"
                ) from exc
        return self._pygame

    def _ensure_display(self) -> None:
        if self._window is not None:
            return
        pygame = self._load()
        try:
            if not pygame.display.get_init():
                pygame.display.init()
            if not pygame.font.get_init():
                pygame.font.init()
            self._window = pygame.display.set_mode(_WINDOW_SIZE, pygame.RESIZABLE)
            pygame.display.set_caption(self._title)
            self._graphics_surface = pygame.Surface(_GRAPHICS_SIZE)
            self._graphics_surface.fill(_BACKGROUND)
            self._font = pygame.font.Font(None, 20)
            self._clock = pygame.time.Clock()
            self._draw_window()
        except Exception as exc:
            self._window = None
            raise PilotUnsupportedError(
                f"could not open the rePILOT graphics window: {exc}"
            ) from exc

    def _ensure_audio(self) -> None:
        if self._audio_ready:
            return
        pygame = self._load()
        try:
            pygame.mixer.init(frequency=_SAMPLE_RATE, size=-16, channels=1, buffer=512)
            pygame.mixer.set_num_channels(4)
            self._audio_ready = True
        except Exception as exc:
            raise PilotUnsupportedError(f"could not initialize interactive audio: {exc}") from exc

    def start_graphics(self) -> None:
        self._ensure_display()
        self._graphics_active = True
        self._text_only = False
        self._draw_window()

    def clear_graphics(self) -> None:
        self._ensure_display()
        self._graphics_surface.fill(_BACKGROUND)
        self._text_lines.clear()
        self._text_lines.append("")
        self._draw_window()

    def quit_graphics(self) -> None:
        self._graphics_active = False
        self._text_only = True
        self._draw_window()

    def plot(self, x: float, y: float, color: str) -> None:
        self._ensure_display()
        self._load().draw.circle(self._graphics_surface, _COLORS[color], self._to_pixel(x, y), 2)
        self._draw_window()

    def draw_line(
        self, start_x: float, start_y: float, end_x: float, end_y: float, color: str
    ) -> None:
        self._ensure_display()
        self._load().draw.line(
            self._graphics_surface,
            _COLORS[color],
            self._to_pixel(start_x, start_y),
            self._to_pixel(end_x, end_y),
            2,
        )
        self._draw_window()

    def fill_line(
        self, start_x: float, start_y: float, end_x: float, end_y: float, color: str
    ) -> None:
        """Draw a segment and flood the connected background on its right side."""
        self.draw_line(start_x, start_y, end_x, end_y, color)
        first = self._to_pixel(start_x, start_y)
        second = self._to_pixel(end_x, end_y)
        delta_x = second[0] - first[0]
        delta_y = second[1] - first[1]
        length = math.hypot(delta_x, delta_y)
        if length == 0:
            return
        seed_x = round((first[0] + second[0]) / 2 - delta_y / length * 3)
        seed_y = round((first[1] + second[1]) / 2 + delta_x / length * 3)
        self._flood_fill(seed_x, seed_y, _COLORS[color])
        self._draw_window()

    def _flood_fill(self, seed_x: int, seed_y: int, color: tuple[int, int, int]) -> None:
        width, height = _GRAPHICS_SIZE
        if not (0 <= seed_x < width and 0 <= seed_y < height):
            return
        pygame = self._load()
        pixels = pygame.PixelArray(self._graphics_surface)
        target = pixels[seed_x, seed_y]
        background = self._graphics_surface.map_rgb(_BACKGROUND)
        replacement = self._graphics_surface.map_rgb(color)
        if target != background or target == replacement:
            del pixels
            return
        pending = [(seed_x, seed_y)]
        while pending:
            pixel_x, pixel_y = pending.pop()
            if not (0 <= pixel_x < width and 0 <= pixel_y < height):
                continue
            if pixels[pixel_x, pixel_y] != background:
                continue
            pixels[pixel_x, pixel_y] = replacement
            pending.extend(
                (
                    (pixel_x + 1, pixel_y),
                    (pixel_x - 1, pixel_y),
                    (pixel_x, pixel_y + 1),
                    (pixel_x, pixel_y - 1),
                )
            )
        del pixels

    def color_at(self, x: float, y: float) -> int:
        if not (-79 <= x <= 79 and -31 <= y <= 47) or self._graphics_surface is None:
            return 0
        pixel_x, pixel_y = self._to_pixel(x, y)
        color = tuple(self._graphics_surface.get_at((pixel_x, pixel_y))[:3])
        return _COLOR_VALUES.get(color, 0)

    def read_controller(self, prefix: str, index: str) -> int:
        if prefix.upper() in {"H", "V", "L"}:
            return 0
        self._ensure_display()
        self.pump_events()
        return self._controller.read(prefix, index)

    def set_audio_values(self, values: tuple[int, ...]) -> None:
        if not values and not self._audio_ready:
            return
        if values:
            self._ensure_audio()
        if not self._audio_ready:
            return
        pygame = self._load()
        notes = [value % 32 for value in values[:4]]
        notes.extend([0] * (4 - len(notes)))
        for index, note in enumerate(notes):
            if note == self._audio_notes[index]:
                continue
            channel = pygame.mixer.Channel(index)
            if note == 0:
                channel.fadeout(12)
            else:
                channel.play(self._tone(note), loops=-1, fade_ms=12)
                channel.set_volume(0.25)
        self._audio_notes = notes

    def _tone(self, note: int) -> Any:
        sound = self._tone_cache.get(note)
        if sound is not None:
            return sound
        pygame = self._load()
        frequency = 261.625565 * 2 ** ((note - 13) / 12)
        samples = array(
            "h",
            (
                round(7000 * math.sin(2 * math.pi * frequency * sample / _SAMPLE_RATE))
                for sample in range(_SAMPLE_RATE // 2)
            ),
        )
        if sys.byteorder != "little":
            samples.byteswap()
        sound = pygame.mixer.Sound(buffer=samples.tobytes())
        self._tone_cache[note] = sound
        return sound

    def pump_events(self) -> None:
        now = time.monotonic()
        self._controller.update(now - self._last_update)
        self._last_update = now
        if self._window is None:
            return
        pygame = self._load()
        focus_lost = getattr(pygame, "WINDOWFOCUSLOST", -1)
        redraw_events = {
            getattr(pygame, "WINDOWEXPOSED", -2),
            getattr(pygame, "WINDOWRESIZED", -3),
            getattr(pygame, "VIDEORESIZE", -4),
        }
        redraw = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._cancelled = True
            elif event.type in redraw_events:
                redraw = True
            elif event.type == focus_lost:
                self._controller.release_all()
            elif event.type == pygame.KEYDOWN:
                key = pygame.key.name(event.key).lower()
                self._controller.set_key(key, True)
                if self._input_buffer is not None:
                    if event.key == pygame.K_RETURN:
                        self._input_result = self._input_buffer
                        redraw = True
                    elif event.key == pygame.K_BACKSPACE:
                        self._input_buffer = self._input_buffer[:-1]
                        redraw = True
                    elif event.key == pygame.K_ESCAPE:
                        self._input_result = ""
                        redraw = True
            elif event.type == pygame.KEYUP:
                self._controller.set_key(pygame.key.name(event.key).lower(), False)
            elif event.type == pygame.TEXTINPUT and self._input_buffer is not None:
                self._input_buffer += event.text
                redraw = True
        if redraw:
            self._draw_window()

    def wait_until_closed(self) -> None:
        """Keep a completed CLI drawing visible until the user closes its window."""
        while self._window is not None and not self._cancelled:
            self.pump_events()
            if not self._cancelled:
                self._clock.tick(60)

    def read_line(self) -> str:
        if self._window is None:
            return self._fallback_input.read_line()
        self._ensure_display()
        self._input_buffer = ""
        self._input_result = None
        pygame = self._load()
        pygame.key.start_text_input()
        self._draw_window()
        try:
            while self._input_pending():
                self.pump_events()
                self._clock.tick(60)
        finally:
            pygame.key.stop_text_input()
        if self._cancelled:
            raise InteractiveCancelledError("the interactive window was closed")
        result = cast(str, self._input_result)
        self._input_buffer = None
        self._input_result = None
        return result

    def _input_pending(self) -> bool:
        return self._input_result is None and not self._cancelled

    def write(self, text: str) -> None:
        if self._window is None:
            self._fallback_output.write(text)
            return
        for part_index, part in enumerate(text.split("\n")):
            if part_index:
                self._text_lines.append("")
            if part:
                self._text_lines[-1] += part
        self._draw_window()

    def newline(self) -> None:
        if self._window is None:
            self._fallback_output.newline()
            return
        self._text_lines.append("")
        self._draw_window()

    def flush(self) -> None:
        self._fallback_output.flush()

    def close(self) -> None:
        if self._audio_ready:
            pygame = self._load()
            pygame.mixer.stop()
            pygame.mixer.quit()
            self._audio_ready = False
        if self._window is not None:
            pygame = self._load()
            pygame.display.quit()
            self._window = None
        self._graphics_surface = None
        self._controller.release_all()
        self._graphics_active = False
        self._text_only = False
        self._cancelled = False

    def _to_pixel(self, x: float, y: float) -> tuple[int, int]:
        pixel_x = round((x + 79) * (_GRAPHICS_SIZE[0] - 1) / 158)
        pixel_y = round((47 - y) * (_GRAPHICS_SIZE[1] - 1) / 78)
        return pixel_x, pixel_y

    def _draw_window(self) -> None:
        if self._window is None:
            return
        pygame = self._load()
        size = self._window.get_size()
        if self._text_only:
            text_top = 0
            text_height = size[1]
            self._window.fill(_TEXT_BACKGROUND)
        else:
            scaled_height = round(size[1] * 2 / 3)
            scaled = pygame.transform.smoothscale(self._graphics_surface, (size[0], scaled_height))
            self._window.fill(_BACKGROUND)
            self._window.blit(scaled, (0, 0))
            text_top = scaled_height
            text_height = max(1, size[1] - text_top)
        pygame.draw.rect(self._window, _TEXT_BACKGROUND, (0, text_top, size[0], text_height))
        line_height = self._font.get_linesize()
        for row, text in enumerate(self._text_lines):
            y = text_top + 6 + row * line_height
            if y + line_height > size[1]:
                break
            rendered = self._font.render(text, True, (255, 255, 255))
            self._window.blit(rendered, (8, y))
        if self._input_buffer is not None:
            prompt = self._font.render("? " + self._input_buffer, True, (255, 255, 255))
            self._window.blit(prompt, (8, size[1] - line_height - 4))
        pygame.display.flip()
