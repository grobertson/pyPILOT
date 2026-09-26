"""Tests for the Stage 7 commands: I/O devices and the utilities.

Covers spec 6.1.11 (`VNEW:`), 6.1.14 (`PA:`), 6.1.17 (`READ:`/`WRITE:`/`CLOSE:`),
6.1.18 (`PCS:`), 6.1.19 (`TRACE:`), 6.1.20 (`DUMP:`) and 6.1.21 (`LOAD:`).

Every test that touches a device passes ``device_root=tmp_path``. The default
root is under the user's home directory, and a test that writes there is a test
that litters - so this is not optional, it is the difference between a test
suite and a mess.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pypilot.devices import (
    DEVICE_LETTERS,
    MAX_OPEN_DEVICES,
    DeviceKind,
    DeviceTable,
    split_device_spec,
)
from pypilot.errors import PilotRuntimeError
from pypilot.io import BufferOutput, StringInput
from pypilot.runtime import Interpreter
from pypilot.state import PilotState
from pypilot.syntax import parse

# ---------------------------------------------------------------------------
# 6.1.17 Device specifications
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("C", ("C", "")),
        ("D:ELIZA", ("D", "ELIZA")),
        ("E", ("E", "")),
        ("e:", ("E", "")),
        ("K", ("K", "")),
        ("P", ("P", "")),
        ("S", ("S", "")),
        ("D:", ("D", "")),
        ("  C  ", ("C", "")),
    ],
)
def test_split_device_spec(spec: str, expected: tuple[str, str]) -> None:
    assert split_device_spec(spec) == expected


def test_the_device_letter_is_case_insensitive() -> None:
    """Spec 6.1.17 lists `E`, `E:` and `e:` as all naming the screen editor."""
    assert split_device_spec("e:")[0] == split_device_spec("E")[0] == "E"


def test_the_filename_keeps_its_case() -> None:
    """The letter is normalised; the filename is data the program chose."""
    assert split_device_spec("D:Eliza")[1] == "Eliza"


@pytest.mark.parametrize("spec", ["X", "1", "!", "QQ"])
def test_an_invalid_device_is_rejected(spec: str) -> None:
    with pytest.raises(PilotRuntimeError, match="not an ATARI PILOT device"):
        split_device_spec(spec)


def test_a_null_device_is_rejected() -> None:
    with pytest.raises(PilotRuntimeError, match="device specification is required"):
        split_device_spec("")


def test_the_device_letters_are_the_spec_set() -> None:
    assert set(DEVICE_LETTERS) == {"C", "D", "E", "P", "S", "K"}


# ---------------------------------------------------------------------------
# 6.1.17 Open, close, and the four-device limit
# ---------------------------------------------------------------------------


def _table(tmp_path: Path, state: PilotState | None = None) -> DeviceTable:
    """A device table rooted at ``tmp_path``.

    Callers should use it as a context manager (or call ``close_all``) so the
    host file handles are released - the suite runs with
    ``filterwarnings = ["error"]``, so a leaked handle fails the test that
    leaked it rather than passing quietly.
    """
    return DeviceTable(
        state if state is not None else PilotState(), BufferOutput(), StringInput([]), root=tmp_path
    )


def test_open_on_first_use(tmp_path: Path) -> None:
    """Spec 6.1.17 - there is no OPEN command; the first use opens the device."""
    with _table(tmp_path) as table:
        assert len(table) == 0
        table.open_device("C")
        assert table.is_open("C")
        assert len(table) == 1


def test_opening_twice_returns_the_same_device(tmp_path: Path) -> None:
    with _table(tmp_path) as table:
        first = table.open_device("D:NOTES")
        second = table.open_device("D:NOTES")
        assert first is second
        assert len(table) == 1


def test_synonyms_are_separate_devices(tmp_path: Path) -> None:
    """Spec 6.1.17 - "each synonym is treated as a separate device"."""
    with _table(tmp_path) as table:
        table.open_device("E")
        table.open_device("e:")
        assert len(table) == 2, "E and e: are different files, not two names for one"


def test_at_most_four_devices_may_be_open(tmp_path: Path) -> None:
    """Spec 6.1.17 - "The number of devices which may be accessed in parallel is 4"."""
    assert MAX_OPEN_DEVICES == 4
    with _table(tmp_path) as table:
        for spec in ("C", "D:A", "D:B", "D:C"):
            table.open_device(spec)
        assert len(table) == 4
        with pytest.raises(PilotRuntimeError, match="at most 4"):
            table.open_device("D:D")


def test_closing_frees_a_slot(tmp_path: Path) -> None:
    with _table(tmp_path) as table:
        for spec in ("C", "D:A", "D:B", "D:C"):
            table.open_device(spec)
        table.close("D:A")
        assert len(table) == 3
        table.open_device("D:D")
        assert len(table) == 4, "the freed slot is reusable"


def test_closing_something_not_open_is_not_an_error(tmp_path: Path) -> None:
    """A lesson that closes defensively is not making a mistake."""
    with _table(tmp_path) as table:
        table.close("C")
        assert len(table) == 0


def test_an_open_device_appears_in_the_string_table(tmp_path: Path) -> None:
    """Spec 6.1.17 - the Atari tracks open files *in the string table*.

    The name is the device spec appended to `@`, and the value is the IOCB slot
    character. Modelling it this way is what makes `VNEW:$` close every file.
    """
    state = PilotState()
    with _table(tmp_path, state) as table:
        table.open_device("C")
        assert state.get_string("@C") == "@", "an open cassette is $@C holding an IOCB slot"

    state = PilotState()
    with _table(tmp_path, state) as table:
        table.open_device("D:ELIZA")
        # A fresh table, so this is the first device and takes the first slot.
        assert state.get_string("@D:ELIZA") == "@"


def test_closing_removes_the_open_file_string(tmp_path: Path) -> None:
    state = PilotState()
    with _table(tmp_path, state) as table:
        table.open_device("C")
        table.close("C")
        assert state.get_string("@C") is None
        assert not state.is_defined("@C"), "closing makes it undefined, not null"


# ---------------------------------------------------------------------------
# 6.1.17 READ / WRITE / CLOSE through the interpreter
# ---------------------------------------------------------------------------


def test_write_then_read_a_cassette(tmp_path: Path, run: Any) -> None:
    out, _, _ = run(
        "WRITE:C,HELLO FROM PILOT\nCLOSE:C\nREAD:C,$LINE\nT:$LINE",
        device_root=tmp_path,
    )
    assert "HELLO FROM PILOT" in out


def test_a_comma_or_a_blank_separates_device_from_data(tmp_path: Path, run: Any) -> None:
    """Spec 4.5 - commas and blanks are interchangeable separators."""
    comma, _, _ = run("WRITE:D:N,SOMEMETHING\nCLOSE:D:N", device_root=tmp_path)
    blank, _, _ = run("WRITE:D:N SOMETHING\nCLOSE:D:N", device_root=tmp_path)
    assert comma == blank == ""


def test_read_populates_the_accept_buffer(tmp_path: Path, run: Any) -> None:
    """Spec 6.1.17 - READ applies the Accept transformation rules."""
    out, state, _ = run(
        "WRITE:C,JOE\nCLOSE:C\nREAD:C\nM: JOE \nTY:THE BUFFER NORMALISED",
        device_root=tmp_path,
    )
    assert "THE BUFFER NORMALISED" in out
    assert state.accept_buffer == " JOE ", "the buffer is normalised like any accept"


def test_read_into_a_numeric_variable(tmp_path: Path, run: Any) -> None:
    _, state, _ = run("WRITE:C,42\nCLOSE:C\nREAD:C,#A", device_root=tmp_path)
    assert state.get_number("A").value == 42


def test_read_into_a_string_variable_keeps_the_raw_text(tmp_path: Path, run: Any) -> None:
    """The buffer is normalised; the variable holds what was read (spec 6.1.2)."""
    _, state, _ = run("WRITE:C,  joe  \nCLOSE:C\nREAD:C,$N", device_root=tmp_path)
    assert state.get_string("N").strip() == "joe", "the leading blanks survive"


def test_end_of_file_yields_null_data_not_an_error(tmp_path: Path, run: Any) -> None:
    """Spec 6.1.17 - end-of-file "will result in null data being read"."""
    _, state, _ = run("READ:D:MISSING,$LINE", device_root=tmp_path)
    assert state.get_string("LINE") == "", "a read past the end gives the null string"
    assert state.is_defined("LINE"), "null, not undefined - they are different states"


def test_a_device_name_may_come_from_a_string_variable(tmp_path: Path, run: Any) -> None:
    """Spec 6.1.17 - a spec may be a text literal *or* a string variable."""
    _, state, _ = run(
        "C:$DEV=C:HELLO\nWRITE:$DEV,FROM A VARIABLE\nCLOSE:$DEV\nREAD:$DEV,$GOT",
        device_root=tmp_path,
    )
    assert state.get_string("GOT") == "FROM A VARIABLE"


def test_writing_to_the_screen_writes_to_the_output(tmp_path: Path, run: Any) -> None:
    """`S` is the display handler, so it goes to the output device."""
    out, _, _ = run("WRITE:S,VISIBLE", device_root=tmp_path)
    assert out == "VISIBLE\n"


def test_reading_the_screen_reads_the_input(tmp_path: Path, run: Any) -> None:
    _, state, _ = run("READ:E,$LINE", ["TYPED"], device_root=tmp_path)
    assert state.get_string("LINE") == "TYPED"


def test_reading_past_the_console_is_null_not_an_error(tmp_path: Path, run: Any) -> None:
    _, state, _ = run("READ:K,$LINE", [], device_root=tmp_path)
    assert state.get_string("LINE") == ""


def test_close_in_a_program_needs_no_open_first(tmp_path: Path, run: Any) -> None:
    """Closing something never opened is not an error."""
    out, _, _ = run("CLOSE:C\nT:SURVIVED", device_root=tmp_path)
    assert out == "SURVIVED\n"


# ---------------------------------------------------------------------------
# 6.1.11 VNEW:
# ---------------------------------------------------------------------------


def test_vnew_with_no_operand_clears_both(tmp_path: Path, run: Any) -> None:
    _, state, _ = run("C:#A=1\nC:$S=X\nVNEW:\nDUMP:", device_root=tmp_path)
    assert not state.is_defined("S")
    assert state.get_number("A").value == 0


def test_vnew_dollar_clears_only_strings(tmp_path: Path, run: Any) -> None:
    _, state, _ = run("C:#A=7\nC:$S=X\nVNEW:$", device_root=tmp_path)
    assert not state.is_defined("S")
    assert state.get_number("A").value == 7, "$ must leave the numerics alone"


def test_vnew_hash_clears_only_numerics(tmp_path: Path, run: Any) -> None:
    _, state, _ = run("C:#A=7\nC:$S=X\nVNEW:#", device_root=tmp_path)
    assert state.is_defined("S"), "# must leave the strings alone"
    assert state.get_number("A").value == 0


def test_vnew_dollar_closes_every_open_file(tmp_path: Path) -> None:
    """Spec 6.1.17 - clearing the strings "has the effect of closing all files"."""
    interpreter = Interpreter(
        parse("VNEW:$"), output=BufferOutput(), source=StringInput([]), device_root=tmp_path
    )
    interpreter.devices.open_device("C")
    assert len(interpreter.devices) == 1
    interpreter.core._vnew(interpreter.program.statements[0])
    assert len(interpreter.devices) == 0, "VNEW:$ must close the open cassette"


def test_vnew_rejects_an_unknown_operand(run: Any) -> None:
    with pytest.raises(PilotRuntimeError, match=r"VNEW: takes \$, #"):
        run("VNEW:X")


# ---------------------------------------------------------------------------
# 6.1.20 DUMP:
# ---------------------------------------------------------------------------


def test_dump_lists_the_string_variables(tmp_path: Path, run: Any) -> None:
    out, _, _ = run("C:$NAME=JOE\nDUMP:", device_root=tmp_path)
    assert "$NAME" in out and "JOE" in out


def test_dump_says_so_when_there_are_none(tmp_path: Path, run: Any) -> None:
    out, _, _ = run("DUMP:", device_root=tmp_path)
    assert "no string variables" in out


def test_dump_shows_open_devices(tmp_path: Path, run: Any) -> None:
    """They are strings, so the Atari's DUMP shows them too (spec 6.1.17)."""
    out, _, _ = run("WRITE:C,HELLO\nDUMP:", device_root=tmp_path)
    assert "@C" in out


# ---------------------------------------------------------------------------
# 6.1.14 PA: - pause, and the yield point
# ---------------------------------------------------------------------------


def test_pa_calls_the_host_hook_once_per_tick() -> None:
    ticks: list[int] = []
    Interpreter(
        parse("PA:3"), output=BufferOutput(), source=StringInput([]), tick=ticks.append
    ).run()
    assert ticks == [1, 1, 1]


def test_pa_zero_is_still_a_yield_point() -> None:
    """Spec 6.1.14 - `PA:0` "delays to the next clock tick", so it is not a no-op."""
    ticks: list[int] = []
    Interpreter(
        parse("PA:0"), output=BufferOutput(), source=StringInput([]), tick=ticks.append
    ).run()
    assert ticks == [1]


def test_pa_uses_a_numeric_expression_not_a_text_one() -> None:
    """Spec 6.1.14 - `<pause operand> ::= <nexp>`, so `PA:#D` is a real delay."""
    ticks: list[int] = []
    source = "C:#D=2\nPA:#D"
    Interpreter(
        parse(source), output=BufferOutput(), source=StringInput([]), tick=ticks.append
    ).run()
    assert len(ticks) == 2, "the operand must be evaluated, not treated as a name"


def test_a_negative_pause_clamps_to_zero() -> None:
    ticks: list[int] = []
    Interpreter(
        parse("PA:-5"), output=BufferOutput(), source=StringInput([]), tick=ticks.append
    ).run()
    assert ticks == [1], "negative is clamped, and still yields once"


# ---------------------------------------------------------------------------
# 6.1.18 PCS: - position cursor
# ---------------------------------------------------------------------------


def test_pcs_records_the_cursor_position() -> None:
    interpreter = Interpreter(parse("PCS:5,2"), output=BufferOutput(), source=StringInput([]))
    interpreter.run()
    assert interpreter.cursor == (5, 2)


def test_pcs_clamps_to_the_text_screen() -> None:
    """Spec 6.1.18 - column 3-39, row 0-23, upper-left at 3,0."""
    interpreter = Interpreter(parse("PCS:0,99"), output=BufferOutput(), source=StringInput([]))
    interpreter.run()
    assert interpreter.cursor == (3, 23), "column 0 is off-screen; 0-2 hold the prompt"


def test_pcs_needs_both_a_column_and_a_row() -> None:
    with pytest.raises(PilotRuntimeError, match="column and a row"):
        Interpreter(parse("PCS:5"), output=BufferOutput(), source=StringInput([])).run()


def test_pcs_calls_the_host_hook() -> None:
    seen: list[tuple[int, int]] = []
    Interpreter(
        parse("PCS:7,3"),
        output=BufferOutput(),
        source=StringInput([]),
        position=lambda c, r: seen.append((c, r)),
    ).run()
    assert seen == [(7, 3)]


# ---------------------------------------------------------------------------
# 6.1.19 TRACE:
# ---------------------------------------------------------------------------


def test_trace_on_emits_events_and_off_stops() -> None:
    events: list[Any] = []
    interpreter = Interpreter(
        parse("TRACE:ON\nT:ONE\nTRACE:OFF\nT:TWO"),
        output=BufferOutput(),
        source=StringInput([]),
        trace=events.append,
    )
    interpreter.run()
    traced = [e.source for e in events]
    assert "T:ONE" in traced
    assert "T:TWO" not in traced, "TRACE:OFF must stop the tracing"


def test_trace_rejects_anything_else() -> None:
    with pytest.raises(PilotRuntimeError, match="TRACE: takes ON or OFF"):
        Interpreter(parse("TRACE:MAYBE"), output=BufferOutput(), source=StringInput([])).run()


# ---------------------------------------------------------------------------
# 6.1.21 LOAD: - program loading
# ---------------------------------------------------------------------------


def test_load_replaces_the_program_and_keeps_the_environment(tmp_path: Path) -> None:
    """Spec 6.1.21 - a run-mode load executes "without any initialization of the
    program environment, except that the Use stack is cleared"."""
    from pypilot.helpers import Os

    program_path = tmp_path / "square.pilot"
    Os.save(program_path, "T:LOADED WITH $NAME STILL SET\n")

    # Stage it where the LOAD: device table will look.
    disk = tmp_path / "disk"
    disk.mkdir(parents=True, exist_ok=True)
    (disk / "SQUARE").write_text("T:LOADED WITH $NAME STILL SET\n", encoding="utf-8", newline="\n")

    interpreter = Interpreter(
        parse("C:$NAME=KEPT\nLOAD:D:SQUARE"),
        output=BufferOutput(),
        source=StringInput([]),
        device_root=tmp_path,
    )
    interpreter.run()
    assert interpreter.output is not None
    assert interpreter.state.get_string("NAME") == "KEPT", "LOAD: must not clear variables"
    assert interpreter.state.accept_buffer == "", "a fresh state has a null buffer"


def test_load_of_a_missing_file_is_an_error(tmp_path: Path) -> None:
    """Loading nothing would leave the old program running - too surprising."""
    with pytest.raises(PilotRuntimeError, match="no such file"):
        Interpreter(
            parse("LOAD:D:NOSUCH"),
            output=BufferOutput(),
            source=StringInput([]),
            device_root=tmp_path,
        ).run()


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    """`SAVE:` writes the *running* program, so the saved text is the source.

    That is the point - a `SAVE:` in one run and a `LOAD:` in another is how a
    program persists, and it is why the round-trip is worth pinning.
    """
    source = "C:$F=D:KEPT\nSAVE:$F\nE:\n"
    Interpreter(
        parse(source),
        output=BufferOutput(),
        source=StringInput([]),
        device_root=tmp_path,
    ).run()
    saved = (tmp_path / "disk" / "KEPT").read_text(encoding="utf-8")
    assert "SAVE:$F" in saved, "SAVE: writes the program that contains it"
    assert parse(saved).source == parse(source).source, "and it must re-parse identically"


# ---------------------------------------------------------------------------
# The device table in isolation
# ---------------------------------------------------------------------------


def test_the_device_table_reports_its_open_specs(tmp_path: Path) -> None:
    with _table(tmp_path) as table:
        table.open_device("C")
        table.open_device("D:A")
        assert list(table.open_specs()) == ["C", "D:A"], "in the order they were opened"


def test_flush_makes_written_data_visible(tmp_path: Path) -> None:
    with _table(tmp_path) as table:
        table.write_line("D:LOG", "WRITTEN")
        table.flush()
        assert "WRITTEN" in (tmp_path / "disk" / "LOG").read_text(encoding="utf-8")


def test_device_kinds_cover_the_spec_table(tmp_path: Path) -> None:
    with _table(tmp_path) as table:
        assert table.open_device("C").kind is DeviceKind.FILE
        assert table.open_device("D").kind is DeviceKind.FILE
        assert table.open_device("E").kind is DeviceKind.INPUT
        assert table.open_device("K").kind is DeviceKind.INPUT
    with _table(tmp_path) as table:
        assert table.open_device("S").kind is DeviceKind.OUTPUT
        assert table.open_device("P").kind is DeviceKind.OUTPUT


def test_a_write_then_read_sequence_rewinds(tmp_path: Path) -> None:
    """A cassette is a tape: write, rewind, read back.

    Reading and writing share one host handle, so without an explicit rewind a
    read would sit wherever the last write left the file position - and the
    second READ would return nothing at all.
    """
    with _table(tmp_path) as table:
        table.write_line("C", "ONE")
        table.write_line("C", "TWO")
        assert table.read_line("C") == "ONE"
        assert table.read_line("C") == "TWO"
        assert table.read_line("C") == "", "past the end is null, not an error"
