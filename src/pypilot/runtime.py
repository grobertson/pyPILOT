"""The interpreter: walks a program and dispatches statements.

``SPEC.md`` section 5 puts the dispatch loop in ``runtime.py`` and the
per-statement handlers in ``core.py``. This module owns:

* the program counter and the dispatch loop
* condition evaluation, including the **conjunctive** ``Y``/``N`` + expression
  rule (spec 4.4)
* the trace hook, which is also what ``--trace`` and ``TRACE:ON`` drive
  (spec 9.5, 12)
* the device table, and the host hooks ``PA:`` and ``PCS:`` call (spec 9.5, 9.6)

Every Core statement is implemented as of Stage 7, along with ``MS``/``JM``,
the utility commands and the I/O commands. The only commands that still raise
are the device-dependent ``GR:``/``SO:``, which are refused with a message
naming SPEC.md §10.4 rather than silently ignored.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from pypilot.core import PilotCore
from pypilot.devices import DeviceTable
from pypilot.errors import PilotRuntimeError, PilotUnsupportedError
from pypilot.io import BufferOutput, ConsoleOutput, InputDevice, NullInput, OutputDevice
from pypilot.state import PilotState
from pypilot.syntax import CommandName, Condition, Program, Statement, parse

__all__ = [
    "MAX_STEPS",
    "PENDING_STAGES",
    "Interpreter",
    "TraceEvent",
]

#: Which stage will implement each command that parses but has not landed.
#:
#: A pending statement must say *which* stage is coming. Silently doing nothing
#: would be the worst outcome for a teaching language: the learner would watch
#: their program produce no output and blame PILOT.
#:
#: **Empty as of Stage 7.** Every run-mode command is implemented. It stays as a
#: mapping rather than being deleted so that a Stage 8 addition has an obvious
#: home, and so ``_dispatch`` can keep naming a stage for anything that lands
#: in the table without a handler.
PENDING_STAGES: Final[dict[str, str]] = {}

#: How many statements a run may execute before the interpreter gives up.
#:
#: **Not** an Atari limit - the 6502 had no such concept and a real PILOT would
#: loop forever happily. This exists because ``J:`` makes an accidental infinite
#: loop a one-character slip (``J:`` with no condition, or a condition that is
#: never false), and a teaching language that *hangs* gives the learner nothing
#: to work with. A clear error naming the limit is more useful than a spinner.
#:
#: Generous enough that no realistic lesson reaches it - the longest example in
#: the corpus runs a few dozen statements.
MAX_STEPS = 1_000_000


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """One traced statement, for ``--trace`` and ``TRACE:ON`` (spec 9.5)."""

    line_number: int
    command: str
    source: str
    executed: bool = True
    skipped: bool = False
    """True when a condition evaluated false, so the statement was not run."""


def _refusal_message(command: str, statement: Statement) -> str:
    """Explain why a real-but-unimplemented command cannot be honoured.

    The distinction that matters is **refused**, not *pending*. ``GR:`` is real
    ATARI PILOT with fifteen documented sub-commands; this host has no turtle
    graphics, and a program using it would need a screen this interpreter does
    not have. Saying "not implemented yet" would promise something that will
    never arrive.

    For ``GR:`` and ``SO:`` the message **names the sub-command that was
    actually requested**. A bare "GR: is refused" leaves a learner wondering
    whether they mistyped it; naming ``DRAWTO`` tells them the program was
    understood and the hardware is what is missing.
    """
    section = "10.4" if command in CommandName.ATARI_DEVICE else "10.7"
    detail = ""
    if command in CommandName.ATARI_DEVICE:
        found = CommandName.subcommand(command, statement.params)
        if found is not None:
            kind = "sub-command" if command == "GR" else "operand"
            detail = f", specifically its {kind} {found}"
    return (
        f"{command}: is real ATARI PILOT{detail}, but this host cannot honour it "
        f"(see SPEC.md section {section}); it is refused rather than ignored, "
        "so a program relying on it fails loudly here"
    )


class Interpreter:
    """Runs a parsed :class:`~pypilot.syntax.Program`."""

    def __init__(
        self,
        program: Program,
        *,
        state: PilotState | None = None,
        output: OutputDevice | None = None,
        source: InputDevice | None = None,
        trace: Callable[[TraceEvent], None] | None = None,
        max_steps: int = MAX_STEPS,
        tick: Callable[[int], None] | None = None,
        position: Callable[[int, int], None] | None = None,
        device_root: str | Path | None = None,
    ) -> None:
        self.program = program
        self.state = state if state is not None else PilotState()
        self.output = output if output is not None else ConsoleOutput()
        self.input = source if source is not None else NullInput()
        self.core = PilotCore(self)
        self.devices = DeviceTable(
            state=self.state, output=self.output, source=self.input, root=device_root
        )
        self._trace = trace
        self.tracing = False
        self.program_counter = 0
        self.steps = 0
        self.max_steps = max_steps
        self._tick = tick
        self._position = position
        self.cursor: tuple[int, int] | None = None
        """Last position set by ``PCS:``, or ``None`` if it has not been used."""

    # -- execution ----------------------------------------------------------

    def run(self) -> None:
        """Execute the program from the current program counter.

        Stops at the end of the program, when a statement returns ``False``
        from its handler (which is how ``E:`` ends a run), or when the
        ``max_steps`` limit is reached.

        Open devices are closed on the way out, however the run ends. Leaving a
        host file handle open past the run would leak it, and a language that
        leaks handles across a hundred lessons exhausts its own file table - so
        this closes them even when an exception is unwinding, which is exactly
        when it is easiest to forget.
        """
        try:
            self._run_loop()
        finally:
            self.close_devices()

    def _run_loop(self) -> None:
        while 0 <= self.program_counter < len(self.program):
            self.steps += 1
            if self.steps > self.max_steps:
                raise PilotRuntimeError(
                    f"executed {self.steps} statements without finishing "
                    f"(limit {self.max_steps}); a J: loop is probably never "
                    "meeting its exit condition"
                )

            statement = self.program.statements[self.program_counter]
            self.program_counter += 1

            if statement.command == "":
                # A label-only or comment-only line; nothing to do.
                continue

            if not self._condition_holds(statement):
                self._emit(statement, executed=False)
                continue

            if not self._dispatch(statement):
                return

    def _dispatch(self, statement: Statement) -> bool:
        """Run one statement. Returns ``False`` when the program should stop."""
        name = CommandName.canonical(statement.command)

        if CommandName.is_refused(name):
            raise PilotUnsupportedError(
                _refusal_message(name, statement),
                line=statement.line_number,
                source=statement.source,
            )

        handler_name = PilotCore.DISPATCH.get(name)
        handler = getattr(self.core, handler_name, None) if handler_name else None
        if handler is None:
            stage = PENDING_STAGES.get(name, "a later")
            raise PilotUnsupportedError(
                f"{statement.command}: is real ATARI PILOT but is not implemented yet "
                f"(see SPEC.md section 11); {name}: arrives in Stage {stage}",
                line=statement.line_number,
                source=statement.source,
            )

        self._emit(statement, executed=True)
        result = handler(statement)
        return result is not False

    # -- conditions ---------------------------------------------------------

    def _condition_holds(self, statement: Statement) -> bool:
        """Evaluate a statement's condition (spec 4.4).

        ``Y`` and a parenthesised expression are **conjunctive**: when both are
        present the statement runs only if both hold. The expression is true
        when it is **greater than zero** (spec 4.4).
        """
        condition = statement.condition
        if condition is None:
            return True
        if not self._match_flag_holds(condition):
            return False
        return self._expression_holds(condition, statement)

    def _match_flag_holds(self, condition: Condition) -> bool:
        """``Y`` needs a successful last match, ``N`` needs an unsuccessful one."""
        if condition.match is None:
            return True
        if condition.match == "Y":
            return self.state.match.matched
        if condition.match == "N":
            return not self.state.match.matched
        raise PilotRuntimeError(f"unknown condition flag {condition.match!r}")

    def _expression_holds(self, condition: Condition, statement: Statement) -> bool:
        """The parenthesised test: true when the value exceeds zero (spec 4.4)."""
        if condition.expression is None:
            return True
        try:
            value = self.state.evaluate(condition.expression)
        except PilotRuntimeError as exc:
            # Re-raise with the source line attached, as a learner would expect.
            raise type(exc)(str(exc), line=statement.line_number, source=statement.source) from exc
        return value.value > 0

    # -- output -------------------------------------------------------------

    def emit(self, text: str) -> None:
        """Write ``text`` to the output device."""
        self.output.write(text)

    def emit_line(self, text: str = "") -> None:
        """Write ``text`` followed by a newline."""
        self.output.write(text)
        self.output.newline()

    def flush(self) -> None:
        """Flush the output device and every open file.

        Both matter: a program that writes to a cassette and is then read back
        by the host must see its own data, and a test that captures output must
        see it before the run returns.
        """
        self.output.flush()
        self.devices.flush()

    def close_devices(self) -> None:
        """Close every open device, flushing what is still buffered."""
        self.devices.flush()
        self.devices.close_all()

    # -- host hooks ---------------------------------------------------------

    def tick(self, units: int = 1) -> None:
        """Advance the host by *units* 1/60-second ticks (spec 6.1.14).

        Called once per tick by ``PA:``, and once even for ``PA:0`` - on the
        Atari a zero pause "delays to the next clock tick", so it is a real
        yield point rather than a no-op. That is what lets an embedding program
        stay responsive to input while a PILOT program is running.

        With no host hook installed this is a genuine ``time.sleep``, so
        ``PA:60`` really does pause for about a second.
        """
        if self._tick is not None:
            self._tick(units)
            return
        if units > 0:
            time.sleep(units / 60.0)

    def position_cursor(self, column: int, row: int) -> None:
        """Move the cursor to ``column``/``row`` (spec 6.1.18).

        The Atari text screen starts at column 3, not 0, because columns 0-2
        hold the prompt; ``_pcs`` clamps to that range before calling.
        """
        self.cursor = (column, row)
        if self._position is not None:
            self._position(column, row)

    def replace_program(self, text: str) -> Program:
        """Swap in a newly loaded program, keeping the environment (spec 6.1.21).

        Run-mode ``LOAD:`` clears the program area and the Use stack but
        **not** the accept buffer, the match flag, or the variables. That is why
        ``VNEW:`` exists, and it is the opposite of what Core PILOT's ``LOAD``
        does.
        """
        program = parse(text)
        self.program = program
        self.steps = 0
        return program

    # -- input --------------------------------------------------------------

    def read_input(self, statement: Statement) -> str:
        """Read one line of input for an ``A:`` statement.

        Spec 6.1.2 notes that the Atari accept "*always terminated by a newline
        that is echoed to the display*", so the echo is unconditional and
        ``AH:`` is a no-op rather than a modifier.

        Raises:
            PilotRuntimeError: when input is exhausted, carrying the source
                line so a program that reads past the end says where.
        """
        try:
            line = self.input.read_line()
        except PilotRuntimeError as exc:
            raise type(exc)(
                f"no more input for A: ({exc})",
                line=statement.line_number,
                source=statement.source,
            ) from exc
        # The Atari accept echoes what was typed (spec 6.1.2).
        self.emit_line(line)
        return line

    # -- tracing ------------------------------------------------------------

    def _emit(self, statement: Statement, *, executed: bool) -> None:
        if not self.tracing or self._trace is None:
            return
        self._trace(
            TraceEvent(
                line_number=statement.line_number,
                command=statement.command,
                source=statement.source,
                executed=executed,
            )
        )

    def trace_lines(self) -> Iterator[str]:
        """Yield a human-readable trace line for each executed statement."""
        for statement in self.program:
            yield f"{statement.line_number:4}  {statement}"


@dataclass(slots=True)
class RunResult:
    """The outcome of a run, for the CLI to report (spec 12)."""

    state: PilotState
    output: BufferOutput
    trace: list[TraceEvent] = field(default_factory=list)
    statements_run: int = 0
