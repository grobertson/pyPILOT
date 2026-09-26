"""The interactive REPL: immediate mode (spec 6.2).

Immediate mode is the half of PILOT where a statement is typed and acted on at
once, and where the deferred program area is edited. The two modes share a
parser but not a set of commands - ``AUTO`` and ``REN`` are immediate-mode only
and are rejected inside a stored program.

The loop is deliberately thin. :class:`~pypilot.helpers.Shell` owns the program
area and the command shapes; this module owns the conversation - reading a
line, deciding what it is, and reporting what happened. That split means the
REPL can be driven from a test with a scripted input device and no terminal
anywhere, which is how every test in ``tests/test_repl.py`` works.

Commands
--------

=============  ==========================================================
Command        What it does
=============  ==========================================================
``LIST``       Print the deferred program, optionally a line range (§6.2.1)
``RUN``        Run it, from a clean environment (§6.2.2)
``NEW``        Discard it and reset the variables (§6.2.5)
``AUTO``       Enter auto-numbered input mode (§6.2.6)
``REN``        Renumber it (§6.2.7)
``LOAD``       Replace it from a device (§6.1.21)
``SAVE``       Write it to a device (§6.2.3)
``DUMP``       List the string variables (§6.1.20)
``VNEW``       Reset variables (§6.1.11)
``TRACE``      Toggle tracing (§6.1.19)
``T:``/``A:``  Any run-mode statement, executed at once
``QUIT``       Leave
=============  ==========================================================

The colon is optional on every immediate-mode command (spec 6.2): ``RUN`` and
``RUN:`` are the same statement.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import ClassVar, Final

from pypilot.devices import DeviceTable
from pypilot.errors import PilotError
from pypilot.helpers import Shell, parse_line_range
from pypilot.io import ConsoleOutput, InputDevice, NullInput, OutputDevice
from pypilot.runtime import Interpreter, TraceEvent
from pypilot.state import PilotState
from pypilot.syntax import MAX_LINE_NUMBER, CommandName, parse

__all__ = ["REPL_COMMANDS", "Repl"]

#: The prompt the REPL shows. The Atari's was a cursor, not a prompt string;
#: something visible is far more useful when input is scripted from a file.
PROMPT: Final = "pilot> "

#: The auto-number input mode prompt, distinct from the immediate one so the
#: mode is never invisible.
AUTO_PROMPT: Final = "auto> "

#: How the REPL says it is leaving.
FAREWELL: Final = "GOODBYE"

#: Immediate-mode commands the REPL handles itself. A line whose first word is
#: one of these is a REPL command; anything else is a PILOT statement executed
#: immediately, which is what immediate mode means (spec 6.2).
REPL_COMMANDS: Final = frozenset(
    {"LIST", "RUN", "NEW", "AUTO", "REN", "LOAD", "SAVE", "DUMP", "VNEW", "TRACE", "QUIT", "EXIT"}
)

#: The immediate-mode commands that are *invalid inside a stored program*
#: (spec 6.2.6, 6.2.7). A program containing one is refused when it is run, not
#: when it is typed - a learner typing `AUTO` at the prompt should not be told
#: it is wrong, because it is not; it is simply the wrong *place*.
IMMEDIATE_ONLY_HINT: Final = (
    "{} is an immediate-mode command and cannot appear in a stored program (spec 6.2)"
)


class Repl:
    """The interactive read-evaluate-print loop.

    A program run from the REPL gets its **own** input device, separate from the
    command stream. That separation is not tidiness - it is the difference
    between a usable REPL and a broken one. With a single shared stream, a
    program's first ``A:`` swallows the next REPL command, so a script that
    types a name has its ``QUIT`` eaten and the session runs away. The Atari
    had the same two-level structure: the program read from the keyboard, and
    the immediate-mode line was only re-read once the program returned.

    Args:
        shell: the program storage area. One is created if not supplied, so a
            test can start from a known-empty area.
        output: where the REPL and any executed statements write.
        source: where typed lines come from.
        program_source: where a running program's ``A:`` reads. Defaults to
            ``source``, which is right for an interactive session and wrong for
            a scripted one - see above.
        trace: receives trace events, so ``--trace`` and ``TRACE:ON`` agree.
    """

    def __init__(
        self,
        shell: Shell | None = None,
        *,
        output: OutputDevice | None = None,
        source: InputDevice | None = None,
        program_source: InputDevice | None = None,
        trace: Callable[[TraceEvent], None] | None = None,
        device_root: str | None = None,
    ) -> None:
        self.shell = shell if shell is not None else Shell()
        self.output = output if output is not None else ConsoleOutput()
        self.source = source if source is not None else NullInput()
        self.program_source = program_source
        self.state = PilotState()
        self.devices = DeviceTable(
            state=self.state, output=self.output, source=self.source, root=device_root
        )
        self.events: list[TraceEvent] = []
        self.tracing = False
        self._trace = trace
        self.running = True
        """False once ``QUIT`` is seen, or input is exhausted."""

    #: REPL command name -> method name. The name is the first word of the line
    #: with any trailing colon removed, upper-cased, so ``RUN``, ``run:`` and
    #: ``Run`` are all the same command (spec 6.2).
    _COMMANDS: ClassVar[dict[str, str]] = {
        "AUTO": "_do_auto",
        "DUMP": "_do_dump",
        "EXIT": "_do_quit",
        "LIST": "_do_list",
        "LOAD": "_do_load",
        "NEW": "_do_new",
        "QUIT": "_do_quit",
        "REN": "_do_renumber",
        "RUN": "_do_run",
        "SAVE": "_do_save",
        "TRACE": "_do_trace",
        "VNEW": "_do_vnew",
    }

    # -- the loop -----------------------------------------------------------

    def run(self) -> None:
        """Read, dispatch and report until the session ends.

        An exhausted input device ends the session cleanly, so a scripted
        session does not need a ``QUIT`` to terminate - which is what makes the
        REPL testable at all.
        """
        while self.running:
            self.output.write(self._prompt())
            self.output.flush()
            try:
                line = self.source.read_line()
            except PilotError:
                # End of input. Not an error - a scripted session just runs out.
                self.running = False
                self.output.newline()
                break
            self.handle_line(line)

    def _prompt(self) -> str:
        return PROMPT

    def handle_line(self, line: str) -> None:
        """Act on one typed line.

        Split out from :meth:`run` so a test can drive the REPL without an
        input device at all - which is how the command tests are written.
        """
        text = line.rstrip("\n")
        if not text.strip():
            return

        # The command word is the first token with any colon removed. Note
        # `partition`, not `rstrip(":")` - the colon in `TRACE:ON` is in the
        # *middle* of the token, and rstrip would leave it attached, so the
        # command would not be recognised.
        word = text.split()[0].partition(":")[0].upper()
        handler = self._COMMANDS.get(word)
        if handler is not None:
            getattr(self, handler)(text)
            return
        # Spec 6.2: the colon may be omitted in immediate mode, so `T HELLO` and
        # `T:HELLO` are the same statement. The parser knows that in immediate
        # mode, so let it do the work rather than rewriting the line here.
        self._execute(text, fresh_state=False, immediate=True)

    # -- the commands -------------------------------------------------------

    def _do_quit(self, line: str) -> None:
        """Leave the REPL. ``EXIT`` is accepted too; it is what people type."""
        self.running = False
        self.output.write(f"{FAREWELL}\n")

    def _do_list(self, line: str) -> None:
        """``LIST`` - print the deferred program (§6.2.1)."""
        try:
            first, last = parse_line_range(_operand(line))
        except PilotError as exc:
            self._report(str(exc))
            return
        self.output.write(self.shell.listing(first, last) + "\n")

    def _do_run(self, line: str) -> None:
        """``RUN`` - execute the program (§6.2.2).

        Spec 6.2.2 requires the Use stack cleared, the accept buffer cleared,
        all variables cleared, the screen cleared and the match flag false
        *before* the stored program starts. `PilotState.reset` does all of that
        except the screen, which on a host means the output buffer.

        Runs on a *fresh* interpreter each time, so a program that fails leaves
        the REPL usable rather than half-executed.
        """
        if self.shell.is_empty():
            self._report("(the program area is empty)")
            return
        self._execute(self.shell.source(), fresh_state=True)

    def _do_new(self, line: str) -> None:
        """``NEW`` - discard the program and reset the environment (§6.2.5).

        Note this **zeroes** the numeric variables rather than clearing the
        store, so a later read reports 0 rather than "undefined" - which is the
        spec's wording and a different end state from `VNEW:#`.
        """
        self.shell.clear()
        self.state.clear_variables()
        self.state.clear_call_stack()

    def _do_renumber(self, line: str) -> None:
        """``REN`` - renumber the program (§6.2.7)."""
        try:
            first, increment = Shell.parse_renumber_operands(_operand(line))
            self.shell.renumber(first, increment)
        except PilotError as exc:
            self._report(str(exc))

    def _do_auto(self, line: str) -> None:
        """``AUTO`` - enter auto-numbered input mode (§6.2.6)."""
        try:
            first, increment = Shell.parse_auto_operands(_operand(line))
            number = Shell.auto_start(first, increment)
        except PilotError as exc:
            self._report(str(exc))
            return
        self._auto_loop(number, increment)

    def _do_load(self, line: str) -> None:
        """``LOAD`` - replace the program from a device (§6.1.21)."""
        try:
            text = self._load_source(_operand(line))
        except PilotError as exc:
            self._report(str(exc))
            return
        try:
            parse(text)
        except PilotError as exc:
            self._report(f"LOAD: {exc}")
            return
        self.shell.clear()
        for entry in text.splitlines():
            self.shell.append(entry)

    def _do_save(self, line: str) -> None:
        """``SAVE`` - write the program to a device (§6.2.3)."""
        try:
            self._save_source(_operand(line), self.shell.source())
        except PilotError as exc:
            self._report(f"SAVE: {exc}")

    def _do_dump(self, line: str) -> None:
        """``DUMP`` - list the string variables (§6.1.20)."""
        self.output.write(self.state.dump_strings() + "\n")

    def _do_vnew(self, line: str) -> None:
        """``VNEW`` - reset variables (§6.1.11), and close every open file."""
        operand = _operand(line).strip().upper()
        if operand not in ("", "$", "#"):
            self._report(f"VNEW: takes $, # or nothing, not {operand!r}")
            return
        if operand in ("", "$"):
            # Spec 6.1.17: clearing the strings closes every open file.
            self.devices.close_all()
            self.state.clear_strings()
        if operand in ("", "#"):
            self.state.clear_numbers()

    def _do_trace(self, line: str) -> None:
        """``TRACE`` - toggle tracing (§6.1.19)."""
        operand = _operand(line).strip().upper()
        if operand == "ON":
            self.tracing = True
        elif operand == "OFF":
            self.tracing = False
        else:
            self._report(f"TRACE: takes ON or OFF, not {operand!r}")

    # -- helpers ------------------------------------------------------------

    def _auto_loop(self, number: int, increment: int) -> None:
        """Read statements until an empty line or a bad number (§6.2.6).

        The spec terminates the mode on an empty line *or* the generation of an
        invalid line number, and a statement with a syntax error is simply not
        stored - the mode continues, so one bad line does not lose the lesson.
        """
        self.output.write("AUTO-NUMBER INPUT MODE. AN EMPTY LINE EXITS.\n")
        while self.running:
            if number > MAX_LINE_NUMBER:
                self._report(
                    f"AUTO: line number {number} is outside the valid range 0-{MAX_LINE_NUMBER}"
                )
                return
            self.output.write(f"{AUTO_PROMPT}{number} ")
            self.output.flush()
            try:
                line = self.source.read_line()
            except PilotError:
                self.running = False
                return
            text = line.rstrip("\n")
            if not text.strip():
                return
            # In auto-number mode the colon is optional too (spec 6.2), so the
            # statement is validated in the form it was typed - and the parser
            # supplies the colon, which it does safely for a label too.
            try:
                parse(text, immediate_mode=True)
            except PilotError as exc:
                self._report(f"not stored: {exc}")
                number += increment
                continue
            self.shell.auto_append(text, number)
            number += increment

    def _run_immediate(self, text: str) -> None:
        """Execute one typed statement at once - immediate mode proper."""
        self._execute(text, fresh_state=False, immediate=True)

    def _execute(self, source: str, *, fresh_state: bool, immediate: bool = False) -> None:
        """Parse and run ``source``, reporting any error without dying."""
        try:
            program = parse(source, immediate_mode=immediate)
        except PilotError as exc:
            self._report(str(exc))
            return

        if fresh_state:
            self.state.reset()
            self.devices.close_all()

        for statement in program:
            if CommandName.is_immediate_only(statement.command):
                self._report(IMMEDIATE_ONLY_HINT.format(statement.command))
                return

        self.events.clear()
        interpreter = Interpreter(
            program,
            state=self.state,
            output=self.output,
            source=self.program_source if self.program_source is not None else self.source,
            trace=self._emit,
        )
        interpreter.tracing = self.tracing
        try:
            interpreter.run()
        except PilotError as exc:
            self._report(str(exc))

    def _emit(self, event: TraceEvent) -> None:
        self.events.append(event)
        if self._trace is not None:
            self._trace(event)

    def _device_table(self) -> DeviceTable:
        """The REPL's device table, shared so open files survive between lines."""
        return self.devices

    def _load_source(self, operand: str) -> str:
        return self.devices.read_source(operand)

    def _save_source(self, operand: str, source: str) -> None:
        self.devices.write_source(operand, source)

    def _report(self, message: str) -> None:
        """Report a problem, keeping the session alive.

        Immediate mode is a conversation. A REPL that exits on the first bad
        line is unusable for the thing it is for, which is experimenting.
        """
        print(message, file=sys.stderr)


def _operand(line: str) -> str:
    """The operand of a REPL command: everything after the command word.

    The colon is optional (spec 6.2) and may sit in either of the two places it
    can appear - ``TRACE:ON`` has it attached to the command word, ``TRACE: ON``
    has it as a separate token - so both are stripped, and ``TRACE ON`` with no
    colon at all works too. Note this splits on a **blank**, not on any
    whitespace, so an operand can never run past the end of the line.
    """
    word, _, rest = line.partition(" ")
    # `TRACE:ON` has no blank, so `rest` is empty and the operand is still
    # sitting in the word we already split on.
    tail = word.partition(":")[2]
    operand = (tail + " " + rest).strip()
    if operand.startswith(":"):
        operand = operand[1:]
    return operand.strip()
