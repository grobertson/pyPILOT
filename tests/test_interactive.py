from pypilot.interactive import KeyboardController


def test_keyboard_controller_maps_joystick_directions_and_diagonals() -> None:
    controller = KeyboardController()
    controller.set_key("UP", True)
    controller.set_key("left", True)
    controller.set_key("w", True)
    controller.set_key("d", True)

    assert controller.read("J", "0") == 5
    assert controller.read("J", "1") == 9
    assert controller.read("J", "2") == 0

    controller.set_key("left", False)
    controller.set_key("w", False)
    assert controller.read("J", "0") == 1
    assert controller.read("J", "1") == 8


def test_keyboard_controller_paddles_move_clamp_and_retain_position() -> None:
    controller = KeyboardController()
    assert controller.read("P", "0") == 115
    assert controller.read("P", "1") == 115

    controller.set_key("e", True)
    controller.set_key("u", True)
    controller.update(1.0)
    assert controller.read("P", "0") == 227
    assert controller.read("P", "1") == 3

    controller.set_key("e", False)
    controller.set_key("u", False)
    controller.update(1.0)
    assert controller.read("P", "0") == 227
    assert controller.read("P", "1") == 3


def test_keyboard_controller_triggers_and_focus_loss() -> None:
    controller = KeyboardController()
    controller.set_key("space", True)
    controller.set_key("enter", True)

    assert controller.read("T", "8") == 1
    assert controller.read("T", "0") == 1
    assert controller.read("T", "2") == 0

    controller.release_all()
    assert controller.read("T", "8") == 0
    assert controller.read("T", "0") == 0
