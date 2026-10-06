"""Per-statement handlers for ATARI PILOT.

Each statement is a single method: ``A`` for Accept, ``C`` for Compute, and so
on. :class:`PilotCore` holds them; the
:class:`~pypilot.runtime.Interpreter` dispatches into it as it walks a program.

Every runnable Core statement - ``A`` ``C`` ``E``
``J`` ``M`` ``R`` ``T`` ``U`` - plus the Atari language extensions ``MS`` and
``JM``, the utility commands ``PA`` ``PCS`` ``VNEW`` ``DUMP`` ``TRACE``, and the
I/O commands ``READ`` ``WRITE`` ``CLOSE`` ``LOAD`` ``SAVE``.

The device-dependent Atari commands ``GR:``/``SO:`` are parsed and refused by
:mod:`pypilot.syntax` with a clear
:class:`~pypilot.errors.PilotUnsupportedError` (spec 10.4). Immediate-mode
commands are handled by :mod:`pypilot.repl`.

``Y`` and ``N`` have no handlers because they are not commands: spec 6.1.1
calls them abbreviations for ``TY`` and ``TN``, so the parser resolves them to
``T`` plus a match condition before dispatch.

Note on the original 2020 design: the scaffolding declared these as unbound
methods taking ``*args`` with no ``self``, so ``self._a(...)`` raised
:class:`TypeError` instead of reaching the method body. They are properly
bound here, and ``tests/test_advanced.py`` asserts it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

from pypilot.errors import PilotRuntimeError
from pypilot.match import find_match, split_fields, split_jump_labels
from pypilot.syntax import Statement

#: A numeric accept never errors: any numeric constant in the text is taken, and
#: wholly non-numeric text yields 0, with no message (spec 6.1.2).
_NUMERIC_RE = re.compile(r"-?\d+")


def _numeric_from(text: str) -> int:
    """Extract a number from accepted input, yielding 0 if there is none.

    Spec 6.1.2: *"if the accepted data contains a numeric constant anywhere in
    the text, the value is stored in the variable or if the accepted data is
    totally non-numeric then the value will be zero (no error message will be
    generated)."* So this looks for the first integer **anywhere** in the line,
    not for a wholly numeric line.
    """
    match = _NUMERIC_RE.search(text)
    return int(match.group(0)) if match else 0


if TYPE_CHECKING:
    from pypilot.runtime import Interpreter

__all__ = ["PilotCore"]

#: ``C:`` splits its operand on the first ``=``, which must be present.
_ASSIGN_REQUIRES_EQ = "C: requires an assignment, as in C:#A=1+1"


class PilotCore:
    """Base implementation of the ATARI PILOT statement set.

    Subclasses override the statement methods they support. Each method takes
    the statement to execute; the interpreter that owns this object supplies the
    state and the devices.
    """

    __slots__ = ("_interpreter",)

    def __init__(self, interpreter: Interpreter) -> None:
        self._interpreter = interpreter

    # ------------------------------------------------------------------
    # Stage 4: implemented
    # ------------------------------------------------------------------

    def _t(self, statement: Statement) -> None:
        """``T`` - Type text to the output device (spec 7.3).

        The operand is a text expression: variables are expanded, and an
        **undefined** string variable prints its own name (spec 6.1). An empty
        operand emits a bare newline, which is how a program writes a blank
        line.

        ``Y:`` and ``N:`` need no handler of their own: spec 6.1.1 makes them
        abbreviations for ``TY:`` and ``TN:``, so the parser resolves every one
        of those spellings to ``T`` plus a match condition before it gets here.
        """
        text = self._interpreter.state.expand(statement.params)
        self._interpreter.emit_line(text)

    def _r(self, statement: Statement) -> None:
        """``R`` - Remark. The operand is discarded (spec 9.2).

        A remark is a no-op at run time; it exists so a lesson can carry its
        own commentary in the program text.
        """

    def _c(self, statement: Statement) -> None:
        """``C`` - Compute and assign (spec 9.3).

        ``C:#VAR=«nexp»`` assigns a number; ``C:$VAR=«texp»`` assigns text. The
        target is read from the *start* of the operand and the value from the
        rest, so the variable may also appear on the right-hand side:
        ``C:#A=#A+1`` is well defined because the new value is computed before
        it is stored.
        """
        operand = statement.params
        target, separator, remainder = operand.partition("=")
        if not separator:
            raise self._error(_ASSIGN_REQUIRES_EQ, statement)

        kind = target.strip()[:1]
        name = target.strip()[1:]

        if kind == "#":
            self._assign_number(name, remainder, statement)
        elif kind == "$":
            self._interpreter.state.set_string(name, self._interpreter.state.expand(remainder))
        else:
            raise self._error(
                "C: must assign to a numeric (#A-Z) or string ($NAME) variable, "
                f"not {target.strip()!r}",
                statement,
            )

    def _assign_number(self, name: str, expression: str, statement: Statement) -> None:
        """Evaluate ``expression`` and store it in numeric variable ``name``."""
        state = self._interpreter.state
        try:
            value = state.evaluate(expression.strip())
        except PilotRuntimeError as exc:
            # Attach the source line, as a learner would expect.
            raise type(exc)(str(exc), line=statement.line_number, source=statement.source) from exc
        try:
            state.set_number(name, value)
        except PilotRuntimeError as exc:
            raise self._error(str(exc), statement) from exc

    def _a(self, statement: Statement) -> None:
        """``A`` - Accept into the accept buffer and/or a variable (spec 7.2).

        One or two operands only. The first names the variable to receive the
        input; a leading ``S`` is a synonym for ``$`` (spec 6.1.2). The second,
        when present, is ``=«texp»`` and *assigns* to the buffer instead of
        prompting (spec 7.2.1).

        Numeric accept never errors: non-numeric input stores 0, silently
        (spec 6.1.2). An empty line sets a numeric variable to 0 and a string
        variable to the null string - which is a different state from undefined
        (spec 6.1).
        """
        target, assignment, expression = self._split_accept(statement.params)

        if assignment:
            data = self._interpreter.state.expand(expression)
        else:
            data = self._interpreter.read_input(statement)

        # The *buffer* is normalised; the *variable* receives the raw text
        # (spec 6.1.2), so a variable holds what was typed, not a padded form.
        self._interpreter.state.set_accept(data)

        if target is None:
            return

        kind, name = target
        if kind == "#":
            self._interpreter.state.set_number(name, _numeric_from(data))
        else:
            self._interpreter.state.set_string(name, data)

    @staticmethod
    def _split_accept(params: str) -> tuple[tuple[str, str] | None, bool, str]:
        """Split an accept operand into ``(target, is_assignment, expression)``.

        Spec 6.1.2 gives the grammar as ``[«variable»] [=«texp»]``, so the ``=``
        is looked for first: ``A:=text`` carries an assignment and *no* variable,
        with no comma in sight.

        Raises:
            PilotRuntimeError: if more than two operands are given, which
                spec 6.1.2 does not allow - unlike Core PILOT, there is no
                multi-variable form.
        """
        first, separator, second = params.partition(",")
        if separator and second.strip():
            raise PilotRuntimeError(
                "A: takes at most one variable and one '=text' assignment "
                "(spec 6.1.2); ATARI PILOT has no multi-variable accept"
            )

        # The assignment form is `=text` on the *first* operand, with no comma.
        if not separator and first.startswith("="):
            return None, True, first[1:]

        if separator:
            assignment = second.strip()
            if not assignment.startswith("="):
                raise PilotRuntimeError(
                    f"A: second operand must be '=text', not {assignment!r} (spec 7.2.1)"
                )
            return None, True, assignment[1:]

        name = first.strip()
        if not name:
            return None, False, ""

        # Spec 6.1.2's own examples use both `A:#A` and `A:SNAME`, so a leading
        # `S` is a synonym for `$`.
        kind = "#" if name.startswith("#") else "$"
        if kind == "$" and not name.startswith(("$", "S")):
            raise PilotRuntimeError(
                f"A: variable must be numeric (#A) or string ($NAME), not {name!r} (spec 6.1.2)"
            )
        return (kind, name[1:]), False, ""

    def _m(self, statement: Statement) -> None:
        """``M`` - Match the accept buffer against a list of fields (spec 7.4).

        A **substring search** over the buffer, field by field, and the result
        is the field's **ordinal** rather than a boolean - which is what lets
        `JM:` branch three ways on a three-way list. ``M:`` does not set
        ``$LEFT``/``$MATCH``/``$RIGHT``; ``MS:`` does.
        """
        self._run_match(statement, produce_strings=False)

    def _ms(self, statement: Statement) -> None:
        """``MS`` - Match, also setting ``$LEFT``/``$MATCH``/``$RIGHT`` (spec 7.5).

        Identical to ``M:`` plus the split. On a *failed* match the three keep
        their previous values (spec 6.1.4) - they are not cleared - which is a
        real difference from `M:` and worth a test of its own.
        """
        self._run_match(statement, produce_strings=True)

    def _run_match(self, statement: Statement, *, produce_strings: bool) -> None:
        """Shared body of ``M:`` and ``MS:``."""
        state = self._interpreter.state
        try:
            fields, skipped = split_fields(self._interpreter.state.expand(statement.params))
        except PilotRuntimeError as exc:
            raise self._error(str(exc), statement) from exc

        outcome = find_match(state.accept_buffer, fields, skipped)

        if outcome.matched:
            state.record_match(outcome.ordinal)
            if produce_strings:
                state.set_match_parts(outcome.left, outcome.match, outcome.right)
        else:
            # MS: retains $LEFT/$MATCH/$RIGHT on failure (spec 6.1.4);
            # record_no_match carries them over.
            state.record_no_match()

    # ------------------------------------------------------------------
    # 8 Control flow: J, JM, U, E
    # ------------------------------------------------------------------

    def _resolve_label(self, operand: str, statement: Statement) -> int:
        """Look up one jump/use target, turning a miss into a clear error.

        The leading ``*`` is optional in the operand (spec 10.2), so both
        ``J:*LOOP`` and ``J:LOOP`` work. The label table is a dict built by the
        parser, so this is a lookup and not a scan - ``J:`` inside a loop is the
        hottest path in any PILOT program (spec 8.1).
        """
        target = self._interpreter.program.resolve(operand.strip())
        if target is None:
            raise self._error(
                f"undefined label {operand.strip()!r}; no statement carries that label (spec 8.1)",
                statement,
            )
        return target

    def _j(self, statement: Statement) -> None:
        """``J`` - Jump: continue at the statement with this label (spec 6.1.7).

        Only the program counter moves. The use stack is untouched, so jumping
        *into* a module that a ``U:`` has already entered is legal, and leaving
        one by jumping out is legal too - the module's ``E:`` simply returns to
        whatever the current top of the stack says.
        """
        self._interpreter.program_counter = self._resolve_label(statement.params, statement)

    def _jm(self, statement: Statement) -> None:
        """``JM`` - Jump on Match (spec 6.1.8), the `M:` ordinal made useful.

        Operand *n* is taken when the last match succeeded on field *n*. Two
        cases deliberately do **not** jump, per the spec's own wording: a failed
        match (``%M`` is 0, and there is no 0th operand) and a match whose
        ordinal runs past the end of the label list. Both fall through, which
        makes it safe to place ``JM:`` unconditionally after an ``M:`` that may
        fail or that has more fields than labels.
        """
        ordinal = self._interpreter.state.match.ordinal
        if ordinal == 0:
            return

        labels = split_jump_labels(self._interpreter.state.expand(statement.params))
        if ordinal > len(labels):
            return

        self._interpreter.program_counter = self._resolve_label(labels[ordinal - 1], statement)

    def _u(self, statement: Statement) -> None:
        """``U`` - Use: call a module (spec 6.1.9), the Atari ``GOSUB``.

        Saves the address of the statement *after* this ``U:`` and jumps to the
        label. The module returns via ``E:``. No arguments and no return value -
        modules talk through variables only, which is authentic even though a
        nicer design would not be PILOT.

        Nesting is capped at ``MAX_MODULE_DEPTH`` (8), the Atari's own limit, so
        deep recursion raises a clear
        :class:`~pypilot.errors.PilotRuntimeError` rather than a Python
        ``RecursionError``.
        """
        # The program counter already points past this statement, because
        # run() increments it before dispatch.
        self._interpreter.state.push_module(self._interpreter.program_counter)
        self._interpreter.program_counter = self._resolve_label(statement.params, statement)

    def _e(self, statement: Statement) -> bool:
        """``E`` - End (spec 6.1.10). Returns ``False`` to stop the run.

        The spec states this as one rule with two outcomes: return to the
        statement following the most recently executed ``U:``, **or** stop the
        program if there is no use return stacked. So this is both the module's
        return and the program's end - there is no separate command for either.

        The ``False`` return is what ``Interpreter.run`` tests to break its
        loop, so returning ``True`` here would carry on into whatever follows.
        """
        if self._interpreter.state.in_module():
            self._interpreter.program_counter = self._interpreter.state.pop_module()
            return True
        return False

    # ------------------------------------------------------------------
    # 9.5 Utility commands
    # ------------------------------------------------------------------

    def _vnew(self, statement: Statement) -> None:
        """``VNEW`` - new variables (spec 6.1.11).

        A null operand clears both stores; ``$`` clears the strings and ``#``
        the numerics. Clearing the strings also **closes every open file**,
        because the Atari records open devices in the string table and spec
        6.1.17 says clearing the strings *"has the effect of closing all
        files"*. That is why the device table is flushed first here rather than
        after.
        """
        operand = statement.params.strip().upper()
        state = self._interpreter.state
        if operand not in ("", "$", "#"):
            raise self._error(
                f"VNEW: takes $, # or nothing, not {statement.params!r} (spec 6.1.11)",
                statement,
            )

        clears_strings = operand in ("", "$")
        if clears_strings:
            self._interpreter.devices.close_all()
            state.clear_strings()
        if operand in ("", "#"):
            state.clear_numbers()

    def _dump(self, statement: Statement) -> None:
        """``DUMP`` - list the string variables (spec 6.1.20).

        Diagnostic, and it writes to the output device like any other typed
        output. Open devices appear here too, because they live in the string
        table (spec 6.1.17) - which is exactly what the Atari's own DUMP
        example shows.
        """
        self._interpreter.emit_line(self._interpreter.state.dump_strings())

    def _pa(self, statement: Statement) -> None:
        """``PA`` - pause, in units of 1/60 second (spec 6.1.14).

        The operand is a ``nexp``, not a text expression, so ``PA:#D`` is a real
        delay rather than a variable named ``1D``. Negative values clamp to
        zero, and ``PA:0`` is **not** a no-op - the spec calls it "delays to
        the next clock tick" - so it is still handed to the host as a yield
        point, which is what lets an embedding program regain control.
        """
        state = self._interpreter.state
        try:
            units = state.evaluate(statement.params.strip()).value
        except PilotRuntimeError as exc:
            raise self._error(str(exc), statement) from exc

        ticks = max(0, units)
        for _ in range(ticks):
            self._interpreter.tick()
        # A zero pause still yields: `PA:0` is a clock tick on real hardware.
        if ticks == 0:
            self._interpreter.tick()

    def _pcs(self, statement: Statement) -> None:
        """``PCS`` - position the cursor (spec 6.1.18).

        Column 3-39, row 0-23, with the upper-left of the text screen at 3,0 -
        the Atari screen is not the full 40 columns, because column 0-2 hold
        the prompt. Values outside that are clamped rather than refused: a
        lesson that positions slightly off should still run.
        """
        first, separator, second = statement.params.partition(",")
        if not separator:
            raise self._error("PCS: takes a column and a row, e.g. PCS:5,2", statement)
        state = self._interpreter.state
        try:
            column = state.evaluate(first.strip()).value
            row = state.evaluate(second.strip()).value
        except PilotRuntimeError as exc:
            raise self._error(str(exc), statement) from exc

        self._interpreter.position_cursor(min(max(column, 3), 39), min(max(row, 0), 23))

    def _trace(self, statement: Statement) -> None:
        """``TRACE:ON|OFF`` - toggle statement tracing (spec 6.1.19).

        Traced lines go to the **error** stream, never the output stream, so a
        trace can never be mistaken for program output or end up inside a
        redirected ``WRITE:`` target.
        """
        operand = statement.params.strip().upper()
        if operand == "ON":
            self._interpreter.tracing = True
        elif operand == "OFF":
            self._interpreter.tracing = False
        else:
            raise self._error(f"TRACE: takes ON or OFF, not {statement.params!r}", statement)

    # ------------------------------------------------------------------
    # 9.6 I/O commands
    # ------------------------------------------------------------------

    def _read(self, statement: Statement) -> None:
        """``READ`` - read a line from a device (spec 6.1.17).

        The data is normalised into the accept buffer exactly as ``A:`` would
        be, because the spec says the *"data transformation rules"* of Accept
        apply. An optional second operand names a variable to receive the raw
        text, as with ``A:``.

        At end-of-file the spec requires **null data**, not an error, so the
        buffer becomes a padded blank and a string variable becomes null.
        """
        device, _, variable = self._split_io_operand(statement)
        data = self._interpreter.devices.read_line(self._interpreter.state.expand(device))
        state = self._interpreter.state
        state.set_accept(data)
        if variable:
            kind, name = self._io_variable(variable, statement)
            if kind == "#":
                state.set_number(name, _numeric_from(data))
            else:
                state.set_string(name, data)

    def _write(self, statement: Statement) -> None:
        """``WRITE`` - write a text expression to a device (spec 6.1.17).

        The device and the data are separated by a comma, or equivalently by
        blanks (spec 4.5), so ``WRITE:C,HELLO`` and ``WRITE:C HELLO`` agree.
        """
        device, _, expression = self._split_io_operand(statement)
        text = self._interpreter.state.expand(expression)
        self._interpreter.devices.write_line(self._interpreter.state.expand(device), text)

    def _close(self, statement: Statement) -> None:
        """``CLOSE`` - free a device's I/O control block (spec 6.1.17).

        Closing something that is not open is deliberately **not** an error; a
        lesson that closes defensively is not making a mistake, and failing
        there would be an addition of ours rather than the Atari's behaviour.
        """
        device = statement.params.partition(",")[0]
        self._interpreter.devices.close(self._interpreter.state.expand(device))

    def _load(self, statement: Statement) -> bool:
        """``LOAD`` - replace the running program (spec 6.1.21, §8.5).

        Run mode clears the program area and the Use stack first, then executes
        the newly loaded program **without** initialising the environment
        otherwise. That is the part worth getting right: the accept buffer, the
        match flag and the variables all survive, which is precisely why
        ``VNEW:`` exists.

        Returns ``False`` so the run loop stops: everything after ``LOAD:`` in
        the old program is unreachable.
        """
        text = self._interpreter.devices.read_source(
            self._interpreter.state.expand(statement.params.strip())
        )
        self._interpreter.replace_program(text)
        self._interpreter.state.clear_call_stack()
        self._interpreter.program_counter = 0
        return False

    def _save(self, statement: Statement) -> None:
        """``SAVE`` - write the program to a device (spec 6.2.3)."""
        self._interpreter.devices.write_source(
            self._interpreter.state.expand(statement.params.strip()),
            self._interpreter.program.source,
        )

    # -- I/O operand helpers ------------------------------------------------

    @staticmethod
    def _split_io_operand(statement: Statement) -> tuple[str, str, str]:
        """Split an I/O operand into ``(device, separator, rest)``.

        Spec 4.5 makes commas and blanks interchangeable separators to the right
        of the colon, and any run of them is one separator - except within the
        Match commands. ``WRITE:C,HELLO`` and ``WRITE:C HELLO`` are therefore
        the same statement, and a device with a filename (``D:ELIZA,JOE``) must
        not be split at its own colon.

        The character class is a **blank**, not ``\\s``. A PILOT operand is the
        text up to the end of the *line*, and an operator reading on a
        continuation line would otherwise swallow the newline and treat the next
        statement as more of this one's data.
        """
        text = statement.params
        match = re.search(r"[,\x20]+", text)
        if match is None:
            return text.strip(), "", ""
        return text[: match.start()].strip(), match.group(0), text[match.end() :]

    @staticmethod
    def _io_variable(operand: str, statement: Statement) -> tuple[str, str]:
        """Validate the variable half of a ``READ:`` operand.

        Spec 6.1.17's ``<input variable>`` is a numeric or string variable, and
        ATARI PILOT has no multi-variable accept, so exactly one is allowed.
        """
        name = operand.strip()
        kind = "#" if name.startswith("#") else "$"
        if kind == "$" and not name.startswith(("$", "S")):
            raise PilotRuntimeError(
                f"READ: variable must be numeric (#A) or string ($NAME), not {name!r}"
            )
        return kind, name[1:]

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    #: Maps a command name to its handler method name.
    #:
    #: ``Y`` and ``N`` are deliberately absent: spec 6.1.1 makes them
    #: abbreviations for ``TY``/``TN``, so the parser folds them into ``T`` with
    #: a match condition and they never reach dispatch.
    #:
    #: Everything else that parses is here, including the Atari extensions.
    #: The device-dependent ``GR:`` and ``SO:`` are **not**: those are refused
    #: with a :class:`~pypilot.errors.PilotUnsupportedError` before dispatch
    #: (spec 10.4), because they are real Atari PILOT that this host cannot
    #: honour rather than something this host supports.
    DISPATCH: ClassVar[dict[str, str]] = {
        "A": "_a",
        "C": "_c",
        "CLOSE": "_close",
        "DUMP": "_dump",
        "E": "_e",
        "J": "_j",
        "JM": "_jm",
        "LOAD": "_load",
        "M": "_m",
        "MS": "_ms",
        "PA": "_pa",
        "PCS": "_pcs",
        "R": "_r",
        "READ": "_read",
        "SAVE": "_save",
        "T": "_t",
        "TRACE": "_trace",
        "U": "_u",
        "VNEW": "_vnew",
        "WRITE": "_write",
    }

    @staticmethod
    def _error(message: str, statement: Statement) -> PilotRuntimeError:
        """Build a runtime error carrying the statement's line and source."""
        return PilotRuntimeError(message, line=statement.line_number, source=statement.source)
