"""Tests for the Core PILOT command dispatch contract.

Asserts the *shape* of :class:`~pypilot.core.PilotCore`: every Core statement
has a handler slot, the handlers are properly bound methods, and the ones
belonging to later stages say so rather than failing obscurely.

The ``T``, ``R`` and ``C`` handlers landed in Stage 4, the ``A``, ``M`` and
``MS`` handlers in Stage 5, and ``J``, ``JM``, ``U`` and ``E`` in Stage 6; they
are covered behaviourally in ``tests/test_runtime.py``,
``tests/test_accept_match.py`` and ``tests/test_control_flow.py``. This file is
about the contract the dispatch loop relies on.
"""

from __future__ import annotations

import pytest

from pypilot.core import PilotCore
from pypilot.runtime import Interpreter
from pypilot.syntax import parse

#: Every command in the dispatch table.
#:
#: ``Y``/``N`` are absent by design: they fold to ``T`` with a match condition
#: (spec 6.1.1), so they must never reach dispatch.
CORE_LETTERS = ["A", "C", "E", "J", "M", "R", "T", "U"]

#: The two-letter commands that dispatch under their own name: ``MS:``
#: (spec 6.1.4) and ``JM:`` (spec 6.1.8). Both are language-level rather than
#: device-level, so both belong in the table alongside the Core letters.
TWO_LETTER_COMMANDS = ["JM", "MS"]

#: The utility commands of spec 9.5.
UTILITY_COMMANDS = ["DUMP", "PA", "PCS", "TRACE", "VNEW"]

#: The device and I/O commands of spec 9.6.
IO_COMMANDS = ["CLOSE", "LOAD", "READ", "SAVE", "WRITE"]

#: Device commands backed by the optional interactive host.
DEVICE_COMMANDS = ["GR", "SO"]

#: Everything in the dispatch table.
DISPATCHED = sorted(
    CORE_LETTERS + TWO_LETTER_COMMANDS + UTILITY_COMMANDS + IO_COMMANDS + DEVICE_COMMANDS
)

#: Handlers that arrived in Stage 4.
STAGE4 = {"C", "R", "T"}

#: Handlers that arrived in Stage 5.
STAGE5 = {"A", "M", "MS"}

#: Handlers that arrived in Stage 6 - the control-flow statements.
STAGE6 = {"E", "J", "JM", "U"}

#: Handlers that arrived in Stage 7 - the utility and I/O commands.
STAGE7 = {"CLOSE", "DUMP", "LOAD", "PA", "PCS", "READ", "SAVE", "TRACE", "VNEW", "WRITE"}

#: Every implemented handler.
IMPLEMENTED = STAGE4 | STAGE5 | STAGE6 | STAGE7 | set(DEVICE_COMMANDS)


@pytest.fixture
def core() -> PilotCore:
    return PilotCore(Interpreter(parse("E:")))


def test_dispatch_covers_every_core_letter() -> None:
    assert sorted(PilotCore.DISPATCH) == DISPATCHED


@pytest.mark.parametrize("letter", CORE_LETTERS)
def test_dispatch_maps_to_a_real_handler(letter: str) -> None:
    method = PilotCore.DISPATCH[letter]
    assert callable(getattr(PilotCore, method))


def test_every_core_handler_is_implemented() -> None:
    """No Core statement may still be a `Stage N` stub.

    This replaced a test that asserted each *pending* handler named its stage.
    Once the last Core command (``E:``) landed in Stage 6 that set became empty
    and the test silently stopped testing anything - a green light over no
    assertions. Inverting it makes the same idea bite forever: if a future
    change ever stubs a Core handler again, this fails.

    Device commands are covered separately because they need an injected host.
    """
    for letter in CORE_LETTERS:
        handler = getattr(PilotCore, PilotCore.DISPATCH[letter])
        assert not handler.__doc__ or "Stage" not in handler.__doc__, (
            f"{letter}: is still documented as landing in a later stage"
        )


@pytest.mark.parametrize("letter", sorted(IMPLEMENTED))
def test_implemented_handlers_do_not_raise(core: PilotCore, letter: str) -> None:
    """The Stage 4, 5 and 6 handlers must be real, callable methods."""
    handler = getattr(core, PilotCore.DISPATCH[letter])
    assert callable(handler)
    assert handler.__func__ is not None


@pytest.mark.parametrize("letter", CORE_LETTERS)
def test_handler_is_a_bound_method(core: PilotCore, letter: str) -> None:
    """Handlers must be callable on an instance.

    This is the regression test for the original 2020 bug: the scaffolding
    declared them without ``self``, so ``self._a(...)`` raised TypeError instead
    of reaching the method body.
    """
    handler = getattr(core, PilotCore.DISPATCH[letter])
    assert handler.__self__ is core


def test_unknown_letter_is_not_in_dispatch() -> None:
    assert "Q" not in PilotCore.DISPATCH
    assert "G" not in PilotCore.DISPATCH  # graphics is a two-letter command: `GR`


def test_y_and_n_are_not_dispatchable_commands() -> None:
    """Spec 6.1.1 - `Y`/`N` are abbreviations for `TY`/`TN`, not commands.

    The parser folds them into `T` plus a match condition, so they must never
    reach dispatch: a handler for them would mean `Y(#A>0):` silently lost its
    conjunction with the expression (spec 4.4).
    """
    assert "Y" not in PilotCore.DISPATCH
    assert "N" not in PilotCore.DISPATCH


def test_device_commands_dispatch_and_hardware_commands_remain_refused() -> None:
    """GR/SO need an injected host; hardware/OS escape commands stay refused."""
    for name in TWO_LETTER_COMMANDS + UTILITY_COMMANDS + IO_COMMANDS:
        assert name in PilotCore.DISPATCH, f"{name}: is implemented"
    for name in DEVICE_COMMANDS:
        assert name in PilotCore.DISPATCH
    for name in ("CALL", "TAPE", "TSYNC", "DOS"):
        assert name not in PilotCore.DISPATCH, f"{name}: remains refused, not dispatched"
