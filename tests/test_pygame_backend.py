from __future__ import annotations

import importlib.util

import pytest

from pypilot import pygame_backend
from pypilot.interactive import ControllerKeyMap
from pypilot.io import BufferOutput, StringInput
from pypilot.pygame_backend import PygameInteractiveDevice


def test_pygame_backend_stays_lazy_until_interactive_use() -> None:
    output = BufferOutput()
    device = PygameInteractiveDevice(fallback_output=output)

    device.write("headless")
    device.newline()

    assert output.text == "headless\n"
    assert device._pygame is None


def test_accept_input_uses_console_until_the_graphics_window_is_open() -> None:
    device = PygameInteractiveDevice(fallback_input=StringInput(["answer"]))

    assert device.read_line() == "answer"
    assert device._pygame is None


def test_pygame_backend_passes_injected_controller_keymap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keymap = ControllerKeyMap(joysticks={3: {"right": "l"}})
    received: list[ControllerKeyMap | None] = []

    class ControllerCapture:
        def __init__(self, *, keymap: ControllerKeyMap | None = None) -> None:
            received.append(keymap)

    monkeypatch.setattr(pygame_backend, "KeyboardController", ControllerCapture)
    PygameInteractiveDevice(controller_keymap=keymap)

    assert received == [keymap]


def test_pygame_backend_smoke_with_sdl_dummy_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    if importlib.util.find_spec("pygame") is None:
        pytest.skip("install the interactive extra to run the Pygame smoke test")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    device = PygameInteractiveDevice()

    try:
        device.start_graphics()
        device.plot(0, 0, "RED")
        assert device.color_at(0, 0) == 1
        device.clear_graphics()
        device.draw_line(0, 0, 0, 10, "YELLOW")
        device.draw_line(0, 10, 10, 10, "YELLOW")
        device.draw_line(10, 10, 10, 0, "YELLOW")
        device.fill_line(10, 0, 0, 0, "YELLOW")
        assert device.color_at(5, 5) == 2
        assert device.color_at(20, 5) == 0
        device.set_audio_values((13, 17, 0, 31))
        device.pump_events()
        assert device.window_open
        pygame = device._load()
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        device.wait_until_closed()
        assert device.cancelled
    finally:
        device.close()
