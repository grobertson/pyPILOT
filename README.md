# pyPILOT

An implementation of the PILOT (Programmed Inquiry, Learning, or Teaching)
programming language.

# My Deepest Condolences

I just learned (10/5/26) that the author of Atari PILOT Harry Stewart -- whose documents and notes were invaluable to the accuracy of this recreation -- passed away in 2025 at the age of 89. Harry was a devoted husband, father, and grandfather according to all reports, and a hobby musician to boot. Rest in peace, Harry -- You helped me understand the basic concepts of programming (input, output, matching, conditionals, modified execution flow) very very early (Six!)  I only wish he might have seen this resurrection and gotten a chuckle out of it. I certainly hope other "ATARI Kids" of the 80s like me have a chuckle as well.

## What is PILOT?

PILOT is a very simple interpreted language created by John Amsden Starkweather
in the late 1960s and formalized as a machine-independent specification in 1973
("PILOT-73"). A predecessor to Logo, it was designed for computer-aided
instruction: single-letter commands, text typed straight into the program, and
a learner answering questions into an accept buffer.

- <https://en.wikipedia.org/wiki/PILOT>
- <https://www.edm2.com/index.php/PILOT>

**This project targets ATARI PILOT** — the 1980/81 dialect shipped in an Atari
cartridge for the 400/800, authored by Harry B. Stewart. It is *not* Core PILOT
and *not* Common PILOT, despite superficial similarity. See
[`SPEC.md`](SPEC.md) §1.1 and the research notes in [`history/`](history/README.md).

## Status

> **1.0.0.** Every run-mode command in the Atari vocabulary is implemented, and
> `pypilot` with no arguments opens the interactive REPL of the original system.
> The two device-dependent commands — `GR:` and `SO:`, real ATARI PILOT with no
> host equivalent — parse and then raise a clear error naming the sub-command
> you asked for, rather than being silently ignored.

Zero third-party runtime dependencies, so it runs on a classroom Raspberry Pi
with nothing but CPython. 903 tests, 95% branch coverage, mypy strict, and a
3-OS × 2-Python CI matrix that installs the built wheel and runs a program from
it.

## Install

```console
$ pip install repilot
$ pypilot examples/summary.pilot
```

The **distribution** is `repilot`; the **importable package** is `pypilot`:

```python
from pypilot import parse, PilotState
```

That is deliberate rather than an oversight. `pypilot` is taken on PyPI by an
unrelated long-standing package, so the distribution needed a different name,
and renaming the import path as well would have broken every import in the
docs and tests for no benefit. PyPI normalises names, so `rePILOT` in the web
UI is installed as `repilot`.

The language specification and implementation history live in
[`SPEC.md`](SPEC.md); the release notes in [`CHANGELOG.md`](CHANGELOG.md). The
language reference is in [`docs/language.rst`](docs/language.rst), and the API in
[`docs/api.rst`](docs/api.rst).

## Why use it?

Don't. This is purely a bucket-list project. I've never *exactly* implemented a
language, and this likely won't be a repo of my finest code.

## Then, why write it?

Primarily? Safer-at-Home, Covid-19, boredom, and avoiding the dishes.

On a deeper level? Because it's crossed my mind repeatedly for years and
*doing* it will stop me from saying, "You know, I've always wanted to write my
own PILOT runtime, wouldn't that be fun this rainy weekend?" before I binge
more Netflix.

PILOT was magical to me at 6 or 7 years old. It's simple to understand and has
minimal command names which make it easier on learners who type at rates
approaching 10 words per hour. Added to which, ATARI's implementation came with
a step by step course disguised as a cute book of cartoons.

## Development

This project uses [uv](https://docs.astral.sh/uv/).

```console
uv sync --all-extras --dev     # create .venv and install everything
uv run pytest                  # run the test suite
uv run ruff check .            # lint
uv run ruff format .           # format
uv run mypy                    # type check
uv build                       # build sdist + wheel
uv run --group docs sphinx-build -W -b html docs docs/_build/html
```

Every one of those is a release gate, and CI runs all of them on Linux, Windows
and macOS — plus a clean-environment install of the *built wheel*, because
building a distribution and being able to install it are different claims.

The packaging tests build real archives and inspect their contents.
`tools/scan_secrets.py` greps everything Git would stage for API tokens and the
like; run it before any bulk `git add -A`.

## Releasing

See [`RELEASING.md`](RELEASING.md). Publishing is gated on a tag and uses
**trusted publishing**, so there is no PyPI token in the repository.

Run a program. `examples/summary.pilot` demonstrates the whole language:

```console
$ uv run pypilot examples/summary.pilot
HELLO, WORLD
THE SUM OF TWO AND THREE IS 5.
HALF OF IT, TRUNCATED, IS 2.
AND THE REMAINDER IS 1.

EXPRESSIONS HAVE NO OPERATOR PRECEDENCE, SO 1+2*3 IS:
  9   (not 7)

AN UNDEFINED STRING PRINTS ITS OWN NAME:
  NOT_SET_ANYWHERE

AND NUMBERS WRAP AT 16 BITS WITHOUT COMPLAINING:
  -32768

JM: BRANCHES ON WHICH MATCH FIELD WON, BECAUSE M: SETS AN
ORDINAL RATHER THAN A BOOLEAN. TRY IT WITH YES, NO OR MAYBE:
yes
  YOU SAID YES - THAT WAS FIELD 1.

U: CALLS A MODULE, AND E: COMES BACK FROM ONE. IT IS ALSO HOW
A PROGRAM ENDS WHEN THERE IS NO MODULE TO RETURN FROM.
NOTE THE J: AFTER THE RETURNING E: - WITHOUT IT EXECUTION WOULD
FALL BACK INTO THE MODULE AND CALL IT AGAIN.
THE MODULE HAS BEEN ENTERED 1 TIMES.

AND A J: LOOPS, AS LONG AS ITS CONDITION HOLDS:
  COUNT 1
  COUNT 2
  COUNT 3
  COUNT 4
  COUNT 5
```

### The interactive REPL

Run `pypilot` with no program file and you get the *immediate mode* of the
original system: type a statement and it runs, or build a program with `AUTO`
and `RUN` it. Here is a real session — type the lines shown, answer `ada` and
`yes` at the two prompts:

```console
$ uv run pypilot
pilot> AUTO 100,10
AUTO-NUMBER INPUT MODE. AN EMPTY LINE EXITS.
auto> 100 T:WHAT IS YOUR NAME?
auto> 110 A:$NAME
auto> 120 T:HELLO, $NAME.
auto> 130 T:ARE YOU A STUDENT? (YES OR NO)
auto> 140 A:$ANSWER
auto> 150 M: YES , NO
auto> 160 JM:*YES,*NO
auto> 170 T:UNRECOGNISED ANSWER.
auto> 180 J:*END
auto> 190 *YES
auto> 200 T:WELCOME TO THE COURSE.
auto> 210 J:*END
auto> 220 *NO
auto> 230 T:COME BACK ANY TIME.
auto> 240 *END
auto> 250 E:

pilot> LIST
   1  100 T:WHAT IS YOUR NAME?
   2  110 A:$NAME
   3  120 T:HELLO, $NAME.
   4  130 T:ARE YOU A STUDENT? (YES OR NO)
   5  140 A:$ANSWER
   6  150 M: YES , NO
   7  160 JM:*YES,*NO
   8  170 T:UNRECOGNISED ANSWER.
   9  180 J:*END
  10  190 *YES
  11  200 T:WELCOME TO THE COURSE.
  12  210 J:*END
  13  220 *NO
  14  230 T:COME BACK ANY TIME.
  15  240 *END
  16  250 E:
pilot> RUN
WHAT IS YOUR NAME?
ada
HELLO, ada.
ARE YOU A STUDENT? (YES OR NO)
yes
WELCOME TO THE COURSE.
pilot> QUIT
GOODBYE
```

Note the colon is optional at the prompt, so `T HELLO` and `T:HELLO` are the
same statement (spec 6.2). The transcript above is generated by
`tools/readme_session.py`, which runs the real REPL — documentation that is
produced rather than typed does not drift.

The whole `examples/` corpus runs now, apart from `graphics.pilot`, which
deliberately fails:

Add `--trace` to watch each statement; trace goes to stderr, so it never mixes
with the program's own output:

```console
$ uv run pypilot --trace examples/summary.pilot
```

Parse a program without running it:

```console
uv run pypilot --check examples/greeter.pilot
uv run pypilot --check --list examples/adventure.pilot
```

```console
$ uv run pypilot --check --list examples/graphics.pilot
examples/graphics.pilot: parsed 6 statement(s), 0 label(s)
     1  R:Turtle graphics is real ATARI PILOT, but unimplemented in pyPILOT (SPEC 10.4)
     2  R:This program MUST parse cleanly and fail at RUN time with a message
     3  R:naming the subcommand - not at parse time.
     4  GR:CLEAR  (refused at run time)
     5  T:THIS LINE IS NEVER REACHED.
     6  E:
```

A syntax error is reported the way a 1980s interpreter would have reported it —
line number, message, and the offending line echoed back:

```console
$ printf 'T:HELLO\nFO:1,DATA\n' > bad.pilot
$ uv run pypilot --check bad.pilot
bad.pilot: line 2: 'FO' is not an ATARI PILOT command: ATARI PILOT has no file
handles; use READ: (spec 9.6)
  FO:1,DATA
$ echo $?
1
```

Or from Python:

```python
from pypilot import PilotState, parse

program = parse("*GREET T:HELLO, $NAME\nA:$NAME\n*AGAIN J:*GREET\nE:")
print(len(program), "statements,", len(program.labels), "labels")
print(program.resolve("*GREET"))  # -> 0

# An undefined string variable prints *its own name* — the ATARI rule,
# and the opposite of every other PILOT dialect.
state = PilotState()
print(state.expand("HELLO $NAME"))  # HELLO NAME
state.set_string("NAME", "ada")
print(state.expand("HELLO $NAME"))  # HELLO ada
```

Three rules worth knowing before you write tests, because Python's defaults are
the opposite of every one of them:

```python
from pypilot import Numeric, PilotState

print(Numeric(7) / Numeric(3))  # 2  — truncates toward zero
print(Numeric(-7) / Numeric(3))  # -2 — not Python's -3
print(Numeric(32767) + Numeric(1))  # -32768 — wraps, silently

state = PilotState()
print(state.evaluate("1+2*3"))  # 9 — no operator precedence!
print(state.evaluate("1+(2*3)"))  # 7 — parens are the only fix
print(state.evaluate("-7\\3"))  # 1 — the remainder is always positive
```

## License

MIT. See [LICENSE](LICENSE).
