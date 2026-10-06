"""Command-line entry point for pyPILOT.

``pypilot prog.pilot`` **runs** a program, ``--check`` parses one and reports
its structure without running it, and ``pypilot`` with no arguments enters the
**interactive REPL** (spec 6.2).

Every supported run-mode statement is implemented. ``GR:``/``SO:`` use the
optional interactive host; the hardware and host-shell commands
(`CALL:`, `TAPE:`, `TSYNC:`, `DOS:`) remain refused.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pypilot import __version__
from pypilot.errors import PilotError
from pypilot.helpers import Os, Shell
from pypilot.interactive import InteractiveDevice
from pypilot.io import ConsoleInput, ConsoleOutput
from pypilot.pygame_backend import PygameInteractiveDevice
from pypilot.repl import Repl
from pypilot.runtime import Interpreter, TraceEvent
from pypilot.state import PilotState
from pypilot.syntax import CommandName, decode_source, parse

__all__ = ["build_parser", "check_program", "main", "repl", "run_program"]


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for the ``pypilot`` command."""
    parser = argparse.ArgumentParser(
        prog="pypilot",
        description="An implementation of the ATARI PILOT programming language.",
    )
    parser.add_argument(
        "program",
        nargs="?",
        help="PILOT program file (optional; omit to enter the REPL)",
    )
    parser.add_argument(
        "-c",
        "--check",
        action="store_true",
        help="parse the program and report its structure without running it",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="with --check, list the parsed statements with line numbers",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="enter the interactive REPL after running the program",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="print each statement as it executes",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def check_program(path: str, *, show_statements: bool = False) -> tuple[int, str]:
    """Parse the program at ``path`` and describe it.

    Returns ``(exit_code, output)``; the code is 0 when the program parsed.
    """
    source = decode_source(Os.load(path))
    try:
        program = parse(source)
    except PilotError as exc:
        return 1, f"{path}: {exc}\n"

    lines = [f"{path}: parsed {len(program)} statement(s), {len(program.labels)} label(s)"]
    if show_statements:
        for statement in program:
            note = ""
            if CommandName.is_refused(statement.command):
                note = "  (refused at run time)"
            elif CommandName.is_immediate_only(statement.command):
                note = "  (REPL only)"
            lines.append(f"  {statement.line_number:4}  {statement}{note}")
    return 0, "\n".join(lines) + "\n"


def run_program(
    path: str,
    *,
    trace: bool = False,
    interactive_device: InteractiveDevice | None = None,
) -> int:
    """Parse and run the program at ``path``, returning an exit code.

    Exit codes follow spec 12: 0 on success, 1 on a program or runtime error,
    and 130 when the user closes the interactive window. A completed program's
    window remains open until the user closes it. Trace output goes to stderr.
    """
    program = parse(decode_source(Os.load(path)))
    console = ConsoleOutput()
    device = interactive_device or PygameInteractiveDevice(
        fallback_output=console,
        fallback_input=ConsoleInput(),
        title=f"{Path(path).name} - rePILOT Interactive",
    )
    events: list[TraceEvent] = []

    interpreter = Interpreter(
        program,
        state=PilotState(),
        output=device,
        source=device,
        trace=events.append if trace else None,
        interactive=device,
        keep_interactive_open=isinstance(device, PygameInteractiveDevice),
    )
    interpreter.tracing = trace
    try:
        interpreter.run()
        if isinstance(device, PygameInteractiveDevice) and not interpreter.cancelled:
            device.wait_until_closed()
    except NotImplementedError as exc:
        # A statement belonging to a later stage: say which stage.
        raise PilotError(str(exc)) from exc
    finally:
        console.flush()
        if isinstance(device, PygameInteractiveDevice):
            device.close()
        if trace:
            _print_trace(events)

    if interpreter.cancelled:
        print(f"{path}: cancelled by closing the interactive window", file=sys.stderr)
        return 130
    return 0


def _print_trace(events: list[TraceEvent]) -> None:
    """Report traced statements to stderr, keeping program output clean (spec 12)."""
    print("--- trace ---", file=sys.stderr)
    for event in events:
        mark = " " if event.executed else "-"
        print(f"{mark} {event.line_number:4}  {event.source}", file=sys.stderr)


def repl(
    shell: Shell | None = None,
    *,
    load: str | None = None,
    trace: bool = False,
    device_root: str | None = None,
) -> int:
    """Run the interactive session (spec 6.2).

    Args:
        shell: an existing program area, or ``None`` for an empty one.
        load: a program file to load before the prompt appears, so
            ``pypilot prog.pilot -i`` can drop the user into a session with that
            program already in the area.
        trace: start with tracing on.
        device_root: where the emulated cassette and diskette live.

    Returns:
        Always 0. A REPL that exited non-zero on a bad line would be useless;
        errors are reported and the session continues.
    """
    if load is not None:
        text = decode_source(Os.load(load))
        area = shell if shell is not None else Shell()
        for entry in text.splitlines():
            if entry.strip():
                area.append(entry)
        shell = area

    console = ConsoleOutput()
    interactive_device = PygameInteractiveDevice(
        fallback_output=console,
        fallback_input=ConsoleInput(),
        title="rePILOT Immediate Mode",
    )
    session = Repl(
        shell,
        output=console,
        source=ConsoleInput(),
        interactive=interactive_device,
        trace=_trace_reporter if trace else None,
        device_root=device_root,
    )
    if trace:
        session.tracing = True
    session.run()
    return 0


def _trace_reporter(event: TraceEvent) -> None:
    """Report one traced statement to stderr, keeping program output clean.

    stderr rather than stdout so a trace can never be confused with what the
    program printed, and so it survives being redirected.
    """
    mark = " " if event.executed else "-"
    print(f"{mark} {event.line_number:4}  {event.source}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # No program and no --check: the interactive session. A file with -i runs
    # first and then drops into it, which is the useful order for experimenting.
    if args.program is None and not args.check:
        return repl(trace=args.trace)

    if args.program is None:
        print("--check needs a program file", file=sys.stderr)
        return 1

    try:
        if args.check:
            code, output = check_program(args.program, show_statements=args.list)
            print(output, end="", file=sys.stderr if code else sys.stdout)
            return code

        result = run_program(args.program, trace=args.trace)
        if args.interactive:
            repl(load=args.program, trace=args.trace)
        return result
    except PilotError as exc:
        print(f"{args.program}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
