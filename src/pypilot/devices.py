"""The Atari device model, for `READ:`/`WRITE:`/`CLOSE:`/`LOAD:`/`SAVE:`.

ATARI PILOT's I/O is **device-oriented**, not handle-oriented. Core PILOT has
`FA:#H,«file»` and a family of numeric file handles; ATARI PILOT has none of
that. A program names a *device* — a single letter, optionally followed by a
filename — and the first use of that name opens it (spec 6.1.17):

    READ:C,«var»        ← read a line from the cassette into a variable
    WRITE:C,«texp»     ← write a text expression to the cassette
    CLOSE:C             ← free the device

**There is no `OPEN` command.** Spec 6.1.17 is explicit: *"There is no explicit
OPEN type of command provided; the first use of the name in a READ or WRITE
command will attempt to OPEN the device."* So open-on-first-use is not a
convenience here, it is the language.

Two further rules from the same section shape this module:

**Open files live in the string table.** Each open device gets a string whose
name is the device spec appended to `@`, holding the IOCB slot character — and
*"clearing the string variables using the VNEW command has the effect of closing
all files"*. ``pypilot.state`` owns the string table, so this module only has
to record those strings and clear them on close.

**End-of-file is not an error.** It *"will result in null data being read"*, so
a `READ:` past the end yields the null string rather than raising. A program
that wants its own end-of-file marker writes one and matches against it, which
is what the spec's own worked example does.

The device letters are not arbitrary and are not a pyPILOT invention; see
``DEVICE_LETTERS`` below and SPEC.md §9.6 for the full table.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Final, Protocol

from pypilot.errors import PilotRuntimeError
from pypilot.io import InputDevice, OutputDevice
from pypilot.state import PilotState

__all__ = [
    "DEVICE_LETTERS",
    "MAX_OPEN_DEVICES",
    "OPEN_FILE_PREFIX",
    "DeviceKind",
    "DeviceTable",
    "FileHandle",
    "OpenDevice",
    "device_root",
    "split_device_spec",
]

#: The prefix the Atari appends to a device spec to name its open-file string
#: (spec 6.1.17). An open cassette appears as ``$@C``, a disk file as
#: ``$@D:ELIZA``.
#:
#: ``@`` is safe precisely because it is *not* a sigil inside a text operand
#: (spec 6.4 - memory pointers belong to ``nexp``), so ``$@C`` scans as one
#: literal name and is never mistaken for a pointer.
OPEN_FILE_PREFIX: Final = "@"

#: The device letters of §6.1.17, with what each one is on the Atari.
#:
#: ``E`` and ``K`` both read the keyboard path; ``S`` and ``P`` both write the
#: display. The spec treats the two spellings of the screen as *separate*
#: devices, and so does this table — see :class:`DeviceTable`.
DEVICE_LETTERS: Final = "CDEPSK"

#: How many devices may be open at once.
#:
#: Spec 6.1.17: *"The number of devices which may be accessed in parallel is 4"*.
#: The Atari had four I/O control blocks, so this is a hardware limit rather
#: than a policy choice.
MAX_OPEN_DEVICES: Final = 4

#: The four IOCB slot characters the Atari uses, from the worked example in
#: The four IOCB slot characters the Atari uses, from the worked example in
#: spec 6.1.17: *"'@' is IOCB 4, 'P' is IOCB 5, ... is IOCB 6 & 'p' is IOCB 7"*.
#:
#: The OCR drops the character for IOCB 6 - the line renders as *"is IOCB 6"*
#: with nothing before it - so that slot is spelled here with the Atari's own
#: descending case convention. What is **not** in doubt is the count: the spec
#: names IOCB 4 through 7, which is four, and separately states that four
#: devices may be open in parallel. A three-slot list would make the fourth
#: device impossible to open, which is the one thing the spec rules out.
_IOCB_SLOTS: Final = "@PpG"

#: Directories the file-backed devices resolve against, under the user's home.
#:
#: A modern host has no cassette or diskette, so ``C`` and ``D`` become
#: directories the program can read and write. They are created on demand and
#: are ordinary files inside — which is what makes a lesson's data survive
#: between runs, exactly as a real cassette would.
_CASSETTE_DIRNAME: Final = "cassette"
_DISK_DIRNAME: Final = "disk"


class DeviceKind(Enum):
    """What a device letter means, and therefore how it is opened.

    This is a pyPILOT mapping, not an Atari one: the 6502 had an IOCB and a
    device handler table, and reproducing that faithfully on a modern host would
    mean emulating a peripheral bus for no benefit. What matters is that each
    device keeps the *character* the Atari gave it, so a program written against
    a cassette behaves like one.
    """

    FILE = "file"
    """Backed by a host file. ``C`` and ``D``."""

    INPUT = "input"
    """The host's input stream. ``E`` and ``K``."""

    OUTPUT = "output"
    """The host's output stream. ``S`` and ``P``."""


#: Which kind each device letter is. See SPEC.md §9.6 for the rationale.
DEVICE_KINDS: Final[dict[str, DeviceKind]] = {
    "C": DeviceKind.FILE,
    "D": DeviceKind.FILE,
    "E": DeviceKind.INPUT,
    "K": DeviceKind.INPUT,
    "S": DeviceKind.OUTPUT,
    "P": DeviceKind.OUTPUT,
}

#: Where each file-backed device's files live, under :func:`device_root`.
_DEVICE_DIRNAMES: Final[dict[str, str]] = {
    "C": _CASSETTE_DIRNAME,
    "D": _DISK_DIRNAME,
}


def device_root() -> Path:
    """The directory holding pyPILOT's emulated cassette and diskette.

    Deliberately under the user's home and not the working directory: a lesson's
    data should not appear in whichever directory the program happened to be
    started from, and should survive a change of working directory. Tests
    override this by passing ``root=`` to :class:`DeviceTable`.
    """
    return Path.home() / ".pypilot"


def split_device_spec(operand: str) -> tuple[str, str]:
    """Split a device spec into its ``(letter, filename)`` parts.

    The spec allows a device to be named by a single letter (``C``), by a
    letter and a filename (``D:ELIZA``), or by a string variable holding either
    (spec 6.1.17). Callers expand the operand first, so this only has to split
    the result.

    The letter is case-**insensitive** — the Atari's own device table is upper
    case, and the spec's bi-directional synonym discussion lists ``E``, ``E:``
    and ``e:`` as all naming the screen editor. The filename keeps its case,
    because it is a name a program chose.

    Raises:
        PilotRuntimeError: if the first character is not a device letter, which
            the spec requires to evaluate to a valid device.
    """
    text = operand.strip()
    if not text:
        raise PilotRuntimeError("a device specification is required, e.g. READ:C (spec 6.1.17)")

    letter = text[0].upper()
    if letter not in DEVICE_LETTERS:
        raise PilotRuntimeError(
            f"{text[0]!r} is not an ATARI PILOT device; valid devices are "
            f"{', '.join(sorted(DEVICE_LETTERS))} (spec 6.1.17)"
        )

    # A colon is the conventional separator, but the filename may be given
    # straight after the letter too. Drop a leading colon if present; keep the
    # rest verbatim, since a filename is data the program chose.
    remainder = text[1:]
    if remainder.startswith(":"):
        remainder = remainder[1:]
    return letter, remainder


def _open_file_name(spec: str) -> str:
    """The string-table name the Atari uses for an open device (spec 6.1.17)."""
    return f"{OPEN_FILE_PREFIX}{spec.strip()}"


class FileHandle(Protocol):
    """The part of a host file object this module uses.

    A real :class:`io.TextIOWrapper` satisfies all of it, and declaring it means
    the calls below are type-checked rather than ``Any``.
    """

    def readline(self) -> str: ...

    def write(self, data: str) -> object: ...

    def seek(self, offset: int) -> object: ...

    def close(self) -> object: ...


@dataclass(slots=True)
class OpenDevice:
    """One open device: its spec, its handle, and the IOCB slot it took."""

    spec: str
    """The device spec exactly as written, which is its identity.

    Spec 6.1.17 insists that synonyms are *separate* devices - ``E`` and ``e:``
    are two files, not one - so the spec string is the key rather than the
    device letter.
    """

    letter: str
    """The device letter, upper case."""

    kind: DeviceKind
    """Whether this is a file, the input stream, or the output stream."""

    handle: FileHandle | None
    """The open file, or ``None`` for the console devices which are never closed."""

    slot: str
    """The IOCB character recorded in the open-file string (spec 6.1.17)."""

    reading: bool = False
    """True while a ``READ:`` sequence is in progress.

    A file device is one handle used for both directions, so a read and a write
    interleave on the same file position unless something tracks it. The Atari
    avoids the question with a cassette, which is a tape: you write to the end,
    then *rewind*, then read. This flag is that rewind, and it is what makes
    ``WRITE:`` followed by ``READ:`` return the data just written rather than
    restarting at the beginning on every line.
    """

    exhausted: bool = False
    """True once a read has hit end-of-file, so later reads stay at null."""


@dataclass(slots=True)
class DeviceTable:
    """The set of open devices, and the rules for opening and closing them.

    Owns the four behaviours from spec 6.1.17 that a caller cannot infer:

    * **open on first use** - there is no ``OPEN`` command;
    * **at most four open** - a fifth is an error, not a silent overrun;
    * **end-of-file is not an error** - a read past the end gives the null string;
    * **closing frees the IOCB slot** - and the open-file string goes with it.

    Usable as a context manager, which is the reliable way to release host file
    handles::

        with DeviceTable(state, out, src, root=tmp) as devices:
            devices.write_line("C", "HELLO")
    """

    state: PilotState
    """Used only to record and clear the open-file strings."""

    output: OutputDevice
    """Where the ``S`` and ``P`` devices write."""

    source: InputDevice
    """Where the ``E`` and ``K`` devices read."""

    root: str | Path | None = None
    """Overrides :func:`device_root`. Tests set this to a temporary directory."""

    _open: dict[str, OpenDevice] = field(default_factory=dict)
    _used_slots: list[str] = field(default_factory=list)

    def __enter__(self) -> DeviceTable:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.flush()
        self.close_all()

    # -- opening ------------------------------------------------------------

    def is_open(self, spec: str) -> bool:
        return spec.strip() in self._open

    def open_device(self, operand: str) -> OpenDevice:
        """Open (or return) the device named by ``operand``.

        Args:
            operand: the *expanded* device specification — a bare letter, or a
                letter and filename. A string variable is expanded by the
                caller first, per spec 6.1.17.

        Returns:
            The :class:`OpenDevice`, newly opened or already open.

        Raises:
            PilotRuntimeError: if the spec is invalid, or if opening it would
                exceed the four-device limit.
        """
        letter, filename = split_device_spec(operand)
        spec = operand.strip()

        existing = self._open.get(spec)
        if existing is not None:
            return existing

        if len(self._open) >= MAX_OPEN_DEVICES:
            raise PilotRuntimeError(
                f"cannot open {spec!r}: already {len(self._open)} devices are open "
                f"and ATARI PILOT allows at most {MAX_OPEN_DEVICES} in parallel "
                "(spec 6.1.17)"
            )

        device = OpenDevice(
            spec=spec,
            letter=letter,
            kind=DEVICE_KINDS[letter],
            handle=None,
            slot=self._take_slot(spec),
        )
        if device.kind is DeviceKind.FILE:
            path = self._path_for(letter, filename)
            device.handle = self._open_file(path)

        self._open[spec] = device
        # Spec 6.1.17: the Atari records the open device in the *string table*,
        # and VNEW:$ closing every file is a consequence of that. Modelling it
        # the same way makes DUMP: show what the Atari would show.
        self.state.set_string(_open_file_name(spec), device.slot)
        return device

    def _take_slot(self, spec: str) -> str:
        """Assign the lowest free IOCB character (spec 6.1.17)."""
        for slot in _IOCB_SLOTS:
            if slot not in self._used_slots:
                self._used_slots.append(slot)
                return slot
        # Unreachable while MAX_OPEN_DEVICES == len(_IOCB_SLOTS), which the
        # open-time check enforces. Kept as a guard rather than an assert so a
        # future change to either constant fails loudly instead of silently.
        raise PilotRuntimeError(  # pragma: no cover
            f"no free I/O control block for {spec!r}: all {len(_IOCB_SLOTS)} are in use"
        )

    def _path_for(self, letter: str, filename: str) -> Path:
        """Resolve a file-backed device spec to a host path.

        A bare letter gets a default name, so ``WRITE:C,HELLO`` and
        ``WRITE:C:,HELLO`` both work and neither silently writes to a file called
        the empty string.
        """
        base = self.root if self.root is not None else device_root()
        directory = Path(base) / _DEVICE_DIRNAMES[letter]
        name = filename.strip() or "default"
        return directory / name

    def _open_file(self, path: Path) -> FileHandle:
        """Open a file-backed device, creating the file if it is not there.

        Opened for **both** reading and appending, because spec 6.1.17 says the
        direction is not fixed at open time:

        > Atari PILOT I/O is inherently bidirectional - there is no OPEN command
        > and the direction is determined by the initiating I/O command (READ or
        > WRITE).

        A cassette is bi-directional in exactly this sense: a program writes a
        few lines, rewinds, and reads them back, which is the whole point of the
        spec's own worked example. So a file device is opened read+append, and
        each command decides what to do with it. Opening read-only would make
        ``WRITE:`` fail, and write-only would make ``READ:`` see nothing.
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            return path.open("a+", encoding="utf-8", newline="\n")
        except OSError as exc:
            raise PilotRuntimeError(f"cannot open {str(path)!r}: {exc}") from exc

    # -- using --------------------------------------------------------------

    def read_line(self, operand: str) -> str:
        """Read one line from the device named by ``operand``.

        Returns the **null string** at end-of-file, because spec 6.1.17 says
        end-of-file *"will result in null data being read"* rather than being
        an error. The caller applies the usual accept-buffer normalisation.
        """
        device = self.open_device(operand)

        if device.kind is DeviceKind.INPUT:
            try:
                return self.source.read_line()
            except PilotRuntimeError:
                # Same rule: running out of console input is an end-of-file.
                return ""

        handle = device.handle
        if handle is None:  # pragma: no cover - only file devices have handles
            raise PilotRuntimeError(f"{device.spec!r} is not readable")

        # A write ends the read, exactly as rewinding a tape would: the next
        # READ: starts again from the beginning rather than from wherever the
        # last write left the file position.
        if not device.reading:
            device.reading = True
            device.exhausted = False
            try:
                handle.seek(0)
            except OSError as exc:  # pragma: no cover - defensive
                raise PilotRuntimeError(f"cannot rewind {device.spec!r}: {exc}") from exc

        if device.exhausted:
            return ""

        try:
            line = handle.readline()
        except OSError as exc:
            raise PilotRuntimeError(f"cannot read from {device.spec!r}: {exc}") from exc
        if line == "":
            # Spec 6.1.17: end-of-file "will result in null data being read",
            # and staying at null is what a real read would do.
            device.exhausted = True
            return ""
        # A final line with no newline still counts; readline returns it.
        return line.rstrip("\n")

    def write_line(self, operand: str, text: str) -> None:
        """Write ``text`` to the device named by ``operand``."""
        device = self.open_device(operand)

        if device.kind is DeviceKind.OUTPUT:
            self.output.write(text)
            self.output.newline()
            return

        handle = device.handle
        if handle is None:  # pragma: no cover - only file devices have handles
            raise PilotRuntimeError(f"{device.spec!r} is not writable")
        # A write rewinds first, so the data lands after everything already on
        # the device rather than at whatever position a read left behind.
        device.reading = False
        device.exhausted = False
        try:
            handle.write(text + "\n")
        except OSError as exc:
            raise PilotRuntimeError(f"cannot write to {device.spec!r}: {exc}") from exc

    def close(self, operand: str) -> None:
        """Close the device named by ``operand``, freeing its slot.

        Closing a device that is not open is **not** an error. Spec 6.1.17 says
        ``CLOSE`` frees the IOCS *"associated with the named file"*, and a
        lesson that closes defensively is not making a mistake; failing there
        would be a hostile addition of our own.

        The spec string is validated even for a device that is not open, so a
        typo in a ``CLOSE:`` is still reported.
        """
        split_device_spec(operand)  # validates; the letter is not needed to close
        spec = operand.strip()
        device = self._open.pop(spec, None)
        if device is None:
            return
        if device.slot in self._used_slots:
            self._used_slots.remove(device.slot)
        if device.handle is not None:
            # A close that fails must not mask the program's real state.
            with contextlib.suppress(OSError):
                device.handle.close()
        self.state.forget_string(_open_file_name(spec))

    def close_all(self) -> None:
        """Close every open device. Called when ``VNEW:$`` clears the strings."""
        for spec in list(self._open):
            self.close(spec)

    # -- program source -----------------------------------------------------

    def read_source(self, operand: str) -> str:
        """Read a whole PILOT **program** from the device named by ``operand``.

        This is the ``LOAD:`` counterpart to :meth:`read_line`, and it is a
        different operation: ``READ:`` takes one line and applies the accept
        transformations, while ``LOAD:`` takes an entire program source and does
        not. Spec 6.1.21 gives the operand as a bare device/filename literal.

        A missing file is an error here, not an end-of-file: loading nothing
        would leave the interpreter running whatever it had, which is the kind
        of silent surprise a teaching language should not spring.
        """
        path = self._path_for(*split_device_spec(operand))
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise PilotRuntimeError(
                f"LOAD: cannot read {str(path)!r}: no such file (spec 6.1.21)"
            ) from exc
        except OSError as exc:
            raise PilotRuntimeError(f"LOAD: cannot read {str(path)!r}: {exc}") from exc

    def write_source(self, operand: str, source: str) -> None:
        """Write a whole PILOT program to the device named by ``operand``.

        The ``SAVE:`` counterpart to :meth:`read_source` (spec 6.2.3).
        """
        path = self._path_for(*split_device_spec(operand))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8", newline="\n")
        except OSError as exc:
            raise PilotRuntimeError(f"SAVE: cannot write {str(path)!r}: {exc}") from exc

    def flush(self) -> None:
        """Flush every writable file, so data is visible to a later read."""
        for device in self._open.values():
            handle = device.handle
            flush = getattr(handle, "flush", None)
            if flush is None:
                continue
            with contextlib.suppress(OSError):  # best effort
                flush()

    # -- introspection ------------------------------------------------------

    def open_specs(self) -> Iterator[str]:
        """The specs of the open devices, in the order they were opened."""
        return iter(tuple(self._open))

    def __len__(self) -> int:
        return len(self._open)
