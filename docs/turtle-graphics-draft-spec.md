# ATARI PILOT Interactive Devices: Implementation Specification

**Status:** Implementation complete for 1.2.0 (2026-10-09). This document is the implementation contract and traceability record for the feature; it is retained as the detailed companion to `SPEC.md`. Follow-up checks are listed in §12.
**Target:** rePILOT / `pypilot`
**Original LOE estimate:** 16-26 engineer-days for one experienced Python developer, including implementation, tests, documentation, and cross-platform verification.

## 0. Implementation baseline

The core feature exists in the current repository. Sections 4-7 define the
behavior to preserve, §8 defines acceptance, and §11 identifies test evidence.
Section 9 is the original estimate, not a list of work to repeat. Before
changing behavior, verify the relevant tests and the follow-up checks in §12.
The following boundaries are part of the contract:

| Responsibility | Owning module | Contract |
| --- | --- | --- |
| `GR:` parsing, repeat groups, movement, limits, and source-aware errors | `src/pypilot/graphics.py` | Host-independent; uses injected numeric evaluators and a graphics host |
| Graphics cursor, pen, special variables, and controller state | `src/pypilot/interactive.py` | Shared language state; no duplicate copy in the interpreter |
| `SO:` source parsing and statement-boundary refresh | `src/pypilot/core.py`, `src/pypilot/runtime.py` | Up to four lazy numeric sources; empty `SO:` silences |
| Optional native display, keyboard, text pane, and audio | `src/pypilot/pygame_backend.py` | Pygame CE is imported only when a display or audio capability is requested |
| CLI lifecycle and exit status | `src/pypilot/cli.py` | Exit 0 on completion, 130 on interactive-window cancellation |

`Interpreter` remains headless when constructed without an interactive host.
The CLI constructs a lazy `PygameInteractiveDevice`; constructing that object
does not import Pygame. Embedders either inject an implementation of the
interactive-device protocol or receive `PilotUnsupportedError` when `GR:` or
`SO:` executes. This distinction is important: the language engine is
testable without SDL, while the CLI provides the native host when requested.

## 1. Summary

The opt-in interactive runtime implements ATARI PILOT's `GR:` graphics command, `SO:` sound command, and keyboard-backed controller sensing. `GR:` opens a native OS window with a black graphics area occupying approximately the upper two-thirds and an Atari-blue text area in the lower third. `T:` output is shown in that lower area while the turtle visualization is drawn above it. `SO:` can enable audio without opening a display window; joystick/paddle sensing opens the interactive window so it can receive keyboard events.

Use Pygame Community Edition (`pygame-ce`, imported as `pygame`) for the shared SDL display, event, and audio backend. Keep it in an optional `interactive` extra: the default installation and programs that do not use interactive features remain headless and have zero required runtime dependencies.

## 2. Goals

- Execute the complete, verified ATARI `GR:` subcommand language, including multiple subcommands and iteration within one `GR:` operand.
- Keep graphics state in the interpreter so `%X`, `%Y`, `%A`, and `%Z` report the live cursor position, heading, and color sense.
- Execute `SO:` with up to four simultaneous, variable-driven note sources.
- Provide keyboard emulation for Atari joystick directions, triggers, and paddles, with Atari-compatible numeric sense values.
- Display graphics and PILOT text in a responsive native window during execution.
- Preserve Atari's Cartesian and turtle/vector coordinate systems, pen states, colors, clipping, and graphics initialization behavior where documented.
- Make graphics, input, and sound logic testable without opening a real window or audio device.
- Keep non-graphics execution, embedding, and automated tests headless.

## 3. Out of scope

- Physical Atari hardware, joystick devices, Atari memory, or exact Atari chipset emulation.
- A general-purpose LOGO language, interactive turtle commands, mouse-driven drawing, or a full Atari screen editor.
- Pixel-perfect reproduction of Atari sound waveforms, television artifacts, or original hardware timing.
- Introducing a mandatory third-party runtime dependency.

## 4. User-visible behavior

### 4.1 Window lifecycle and layout

- The first `GR:` that executes a graphics subcommand creates and shows the window. A conditionally skipped `GR:`, or a `GR:` containing only zero-count repeats, does not create it.
- A controller sense (`%J`, `%P`, or `%T`) in a CLI run creates the same window on first use, if it is not already open, so keyboard events can be collected. In an embedding, controller-window creation is the responsibility of the injected host.
- `SO:` initializes only the audio subsystem when possible; a sound-only program does not need to open a window.
- Display and audio initialization are independent and lazy. Do not call global `pygame.init()` if doing so would initialize an unused subsystem.
- The window title includes the program filename when available, otherwise `rePILOT Interactive`.
- Initial window size is 960 by 720 pixels. The backing graphics surface is 960 by 480 pixels and the text area occupies the remaining 240 pixels; resizing keeps the split near 2:1 and scales the presentation rather than changing PILOT coordinates.
- The upper viewport is black. The lower one-third is solid Atari blue, initially `#0055AA`, with high-contrast monospaced PILOT text. Exact shade and typography are presentation choices, not language semantics.
- `T:` and echoed `A:` text go to the lower text area when the graphics window is active; ordinary runs continue to use their configured output device.
- `A:` reads from the configured console input before an interactive window exists; once the window is active, it accepts keyboard input there. Accepting input alone does not create a graphics window.
- The Pygame event queue is serviced during execution, at least after each PILOT statement and during `PA:` waits, so the window repaints and observes key-up/key-down and close events. Graphics commands do not introduce arbitrary delays.
- Audio sources are refreshed after each executed PILOT statement. A looping program that polls controller state must remain responsive without requiring `PA:`; event processing therefore occurs at statement boundaries, not only during pauses.
- Closing the OS window stops the running program cleanly with a user-cancelled result; it must not leave a stuck interpreter or a traceback. The CLI reports cancellation distinctly from a PILOT runtime error.
- After a successful CLI run, keep any opened window visible until the user closes it, so a short drawing program does not close before its result can be seen. A close during execution returns status 130.
- `GR:QUIT` leaves graphics mode and returns to a full-window blue text screen without discarding interpreter variables. Re-entering graphics mode clears and initializes the graphics viewport.

### 4.2 Graphics coordinate space

Use the documented Rev E interior coordinates as the language space:

- X runs from -79 at the left to +79 at the right; positive X is right.
- Y increases upward; the visible graphics area runs from +47 at the top to -31 at the top of the text window.
- The turtle starts at (0, 0), heading 0 degrees (straight up). Positive angle turns clockwise.
- Preserve cursor coordinates outside the visible area within the documented signed range; clip drawing to the visible graphics viewport and resume drawing when the cursor re-enters.
- Convert the coordinate space to display pixels in the graphics adapter only. Never leak scaling or window size into PILOT numeric state.

The Atari manual also describes graphics data between Y=-47 and Y=-31 as hidden behind the text window. The host preserves cursor coordinates there, clips rendering, and reports `%Z` as 0 outside the visible graphics area.

### 4.3 Colors and pen

The documented pen colors are `RED`, `YELLOW`, `BLUE`, `ERASE`, and `UP`. A fresh graphics mode selects `YELLOW`. `UP` moves the cursor without plotting; `ERASE` draws in the background color. The screen-color sense values are 0 for background/erase, 1 red, 2 yellow, and 3 blue. `%Z` returns the color at the cursor, or 0 when outside the visible graphics screen or outside graphics mode.

The user-requested black background and blue text lower-third are presentation defaults. The drawing palette remains the Atari four-value graphics palette; text-area blue is not a drawing color change.

### 4.4 Keyboard controller map

The default map provides two virtual joysticks and two virtual paddles while the interactive window has focus:

| Input | Atari sense |
| --- | --- |
| Arrow keys | `%J0`: up=1, down=2, left=4, right=8; diagonals combine the direction bits (5, 9, 6, 10); neutral=0 |
| W/A/S/D | `%J1`, with the same numeric values |
| Space / left Ctrl | `%T8` / `%T9`, the triggers associated with joysticks 0 / 1 |
| Q / E held | Decrease/increase `%P0` |
| U / O held | Decrease/increase `%P1` |
| Enter / right Ctrl | `%T0` / `%T1`, the triggers associated with paddles 0 / 1 |

Paddle values range from 3 (full counterclockwise) to 227 (full clockwise), with 115 as the neutral starting value. Holding a paddle key moves its value at a fixed rate and clamps at the endpoints. The initial implementation supports keyboard mappings for these devices only; unmapped controller indices return 0. Embedders can inject a `ControllerKeyMap` into `KeyboardController` or `PygameInteractiveDevice` to customize host keys without changing Atari sense values.

Keyboard input is sampled from key state, not key-repeat events. On focus loss, all held keys are released and virtual joystick directions and triggers return to neutral; paddle values remain at their last position.

## 5. Language and state requirements

### 5.1 `GR:` operand language

`GR:` is not a single ordinary operand. Its operand is a small graphics program
with semicolon-separated subcommands, numeric expressions evaluated against
current PILOT state, and repeat groups. The accepted repeat forms are:

```text
repeat-count "(" graphics-sequence ")"
repeat-count ["x" | "X"] subcommand
repeat-count ::= decimal-integer | "#" numeric-variable
```

Whitespace is allowed between the count and its marker. A repeat count is a
non-negative integer from 0 through 65535; zero executes no contained
subcommands and does not activate the graphics host. A numeric-variable count
is evaluated once when that repeat group is reached, not once per iteration.

The parser/evaluator must:

- Evaluate each numeric expression at the point its subcommand runs, so earlier subcommands can affect later state.
- Support nested/combined iteration with a host safety limit of 16 nested groups and 1,000,000 executed leaf subcommands per `GR:` statement. Exceeding either limit raises a source-aware `PilotRuntimeError`.
- Reject malformed subcommands, missing coordinates, invalid colors, and malformed iteration with a `PilotRuntimeError` that names `GR:`, the source line, and the offending subcommand.
- Avoid evaluating expressions in skipped outer PILOT statements.
- Apply the interpreter's existing 16-bit integer expression semantics and source-aware error reporting.

### 5.2 Documented Rev E subcommands

Implement the eleven commands described in detail in the local Rev E OCR and current `SPEC.md` table:

| Subcommand | Required behavior |
| --- | --- |
| `CLEAR` | Clear graphics and text areas; restore documented graphics initialization state. |
| `PEN color` | Select `RED`, `YELLOW`, `BLUE`, `ERASE`, or `UP`. |
| `GOTO x,y` | Move to a Cartesian position and plot there unless pen is `UP`. |
| `DRAWTO x,y` | Move to a Cartesian position, drawing a segment unless pen is `UP`; leave heading unchanged. |
| `FILLTO x,y` | Move to a Cartesian position while drawing and filling the documented region, unless pen is `UP`. |
| `TURNTO angle` | Set heading modulo 360; 0 is up and positive is clockwise. |
| `GO units` | Move along heading without a line; plot the endpoint unless pen is `UP`. Negative values move backward. |
| `DRAW units` | Move along heading while drawing; negative values move backward. |
| `FILL units` | Move along heading while drawing and applying the documented fill behavior; negative values move backward. |
| `TURN angle` | Add angle modulo 360 to the heading. |
| `QUIT` | Leave graphics mode and return to text mode. |

`FILL`/`FILLTO` draw the segment, then flood-fill the connected background on the turtle's right side. The implementation uses the Pygame backing surface, clips at the visible bounds, and tests both the enclosed area and untouched exterior. This is the chosen reproducible host rule where the Atari description does not specify a pixel algorithm.

### 5.3 Subcommand source discrepancy: resolved

The earlier draft and runtime diagnostic table were not internally aligned:

- The former `CommandName.GR_SUBCOMMANDS` contained 15 names, including undocumented `CHAR`, `COLOR`, `MODE`, `SETCLR`, `CLR`, and `TEXT`, but omitted `GO` and `QUIT`.
- Rev E's detailed descriptions and the `SPEC.md` table specify the 11 names in §5.2.
- Earlier project prose called the Atari set "15 subcommands," although the Rev E OCR does not describe all 15 names from that old table.

Rev E's detailed descriptions, cross-checked against the Student Reference Guide and Primer, are normative: the supported list is the eleven commands in §5.2. The former 15-name runtime diagnostic table was incorrect. `src/pypilot/syntax.py`, `src/pypilot/graphics.py`, the tests, and `SPEC.md` now use the verified list.

### 5.4 Graphics special variables

- `%X` and `%Y` return the current cursor coordinates rounded to integers.
- `%A` returns the current heading.
- `%Z` returns the current screen color using the mapping above.
- Before graphics mode is initialized, preserve the current compatibility value of zero. During graphics mode, read values from the same graphics-state object used by `GR:`; do not maintain a second, drifting copy in `PilotState`.

### 5.5 Controller senses

The controller expression forms remain the existing `%J<n>`, `%P<n>`, and `%T<n>`; they are sampled from the interactive input service when an expression is evaluated.

- `%J0` and `%J1` report the keyboard-backed joysticks in §4.4. Values use Atari's direction codes: center 0, cardinal directions 1/2/4/8, and diagonals 5/9/6/10.
- `%P0` and `%P1` report paddle positions from 3 through 227. Values are independent of the direction codes and retain their position when no key is held.
- `%T0`, `%T1`, `%T8`, and `%T9` report the mapped paddle and joystick trigger keys as 0/1. Other trigger indices report 0 until mapped.
- Unsupported joystick, paddle, trigger, and lightpen indices continue to report 0, preserving the existing neutral-value behavior.
- Key state is sampled on demand and updated by the Pygame event pump. A PILOT program can branch or assign a sense value without any new language syntax.

### 5.6 `SO:` sound operands

`SO:` selects up to four sound sources; it is not an `ON`/`OFF`/`PLAY`/`STOP` subcommand language. Each source is a numeric constant, a numeric variable, or an Atari pointer as specified in Rev E. An empty operand disables all voices. More than four sources, malformed operands, or invalid variable references produce a source-aware `PilotRuntimeError`.

- `0` is silence. Values 1 through 31 select chromatic notes: 1 is C below middle C, 13 is middle C, 25 is C one octave above, and 31 is F-sharp above that C. Values wrap modulo 32; negative values use positive modulo, so `-1` selects note 31.
- Each source occupies one independent voice. Numeric variables are read after every PILOT statement, so assignments and control-flow changes update the sound without reissuing `SO:`. Numeric constants remain constant until another `SO:` replaces the source list.
- An empty `SO:` immediately silences and releases all voices. Replacing the operand set stops voices no longer selected.
- The host synthesizes a continuous tone for each active voice. Pitch and polyphony are language requirements; Atari-specific waveform, envelope, and analog output are not.
- Pointer sources are legal in the Atari grammar, but the current interpreter deliberately has no Atari memory model. Until that model exists, a pointer source must fail clearly with `PilotUnsupportedError`; it must not read arbitrary host memory. This is an explicit limitation, not silent acceptance.

## 6. Implementation boundaries

- Add `pygame-ce>=2.5.5` as the `repilot[interactive]` optional project extra. Import it only in the interactive backend. Pygame CE's distribution name is `pygame-ce`, its import name is `pygame`, and it must not be installed alongside the original `pygame` distribution.
- Use Pygame CE/SDL as the single host for the native window, drawing, keyboard events, and audio mixer. This avoids coordinating separate GUI and sound event systems. Initialize display and mixer subsystems independently and only when first required.
- Keep language behavior outside Pygame: a graphics-state/`GR:` evaluator, virtual-controller state and keymap, and `SO:` source/voice model should be independently unit-testable.
- Define an injectable interactive-device protocol for drawing operations, text output, event pumping, controller reads, audio updates, and shutdown. Provide a fake backend for unit tests; do not make tests depend on a physical audio device, display, or keyboard.
- Keep `Interpreter` headless by default. The CLI supplies a lazy Pygame backend factory; embedders may inject their own backend or omit it. `GR:` opens the window, controller reads open it when keyboard capture is needed, and `SO:` alone may initialize audio without opening a display.
- Route `T:` output and `A:` echo to the lower blue text pane only while the Pygame display is active. Preserve `BufferOutput`, console behavior, and all existing noninteractive embedding paths.
- Use a software backing surface if required for `ERASE`, fill operations, clipping, and `%Z` color sensing; scale that surface for window resizing without changing language coordinates.
- Refresh live voice values and poll keyboard state at interpreter statement boundaries; pump SDL events inside graphics iteration and during `PA:` waits so long graphics operations and waits remain responsive. Audio playback itself must not block the interpreter. The statement-boundary hook runs after both executed and conditionally skipped statements.

## 7. Error and portability behavior

- Headless and interactive tests must not hang waiting for a window, key, or audio device.
- Missing `pygame-ce`, display initialization failure, or unavailable audio produces an actionable `PilotUnsupportedError` with the relevant command and line/source context; the interpreter must not silently ignore `GR:` or `SO:`.
- A program that uses no graphics, sound, or controller senses must run without importing Pygame CE. A sound-only program initializes audio without requiring a display.
- The window close action is distinct from `GR:QUIT` and from a PILOT error.
- Verify native window creation, keyboard events, and audio on Windows, macOS, and Linux with suitable devices/sessions. CI without a display or audio device runs fake-backend tests; optional-dependency smoke tests run where multimedia initialization is available.
- Keep audio generation off the interpreter's blocking path. Prefer Pygame CE's mixer rather than adding a custom SDL/audio thread. If statement-boundary updates prove insufficient, document the measured failure before introducing additional concurrency.

## 8. Acceptance criteria

1. The verified Atari `GR:` command list and grammar are reconciled against primary sources and documented; the implementation and tests use that definitive list.
2. `GR:` opens a native Pygame CE window with a black graphics viewport and blue lower third. An example such as `GR:GOTO 0,0;TURNTO 0;4(DRAW 10;TURN 90)` draws a closed square, and `%X/%Y/%A` report the final state.
3. `PEN UP`, `ERASE`, clipping/re-entry, `CLEAR`, `QUIT`, and `%Z` have focused tests. `FILL` and `FILLTO` have deterministic acceptance tests against documented behavior.
4. The default keymap yields Atari-compatible `%J0`/`%J1` directions, `%P0`/`%P1` ranges, and mapped `%T` trigger values, including diagonals and simultaneous key presses.
5. `SO:` accepts the verified source grammar, supports four concurrent voices, refreshes variable-backed notes after statements, silences on an empty operand, and handles invalid or unavailable audio clearly. Pointer operands never access host memory.
6. A normal program with no interactive commands remains headless, does not import Pygame CE, and has unchanged output behavior. A sound-only program does not open a window.
7. Event servicing, focus loss, window close, unavailable display/audio, text output, and Pygame initialization are covered by fake-backend tests and available platform smoke tests.
8. Existing tests, strict lint/type checks, packaging checks, and documentation build pass; the built wheel still has zero mandatory runtime dependencies and the `interactive` extra installs Pygame CE.
9. Add runnable graphics, controller, and sound examples; update `SPEC.md`, language docs, CLI docs/help, and release notes.

## 9. Historical work breakdown and LOE

The following estimate records the original planning basis. It is not a list of
remaining work; rerun the relevant gates when changing the implementation.

| Work | Estimate |
| --- | ---: |
| Verify authoritative `GR:` and `SO:` rules, fill/audio ambiguities, and update normative decisions | 1-2 days |
| Graphics state, command grammar, expression evaluation, iteration, and errors | 2-3 days |
| Drawing surface, Cartesian/vector movement, palette, clipping, fill, and `%Z` | 2-4 days |
| Pygame CE window, blue text pane, live output, resize/event/close lifecycle | 2-3 days |
| Keyboard joystick/paddle mappings, triggers, focus behavior, and sense tests | 1-2 days |
| `SO:` source parsing, four-voice synthesis, updates, and graceful audio failure | 3-5 days |
| Runtime/CLI integration, lazy subsystem activation, `PA:`/statement event servicing | 2-3 days |
| Unit/integration/platform tests, docs, examples, optional-extra packaging, release updates | 3-4 days |
| **Total** | **16-26 engineer-days** |

The calendar estimate was **about 4-6 weeks** for one developer allowing for review and multimedia verification across operating systems. It covers graphics, keyboard input, and sound together.

## 10. Main risks and decisions

- **Command-list conflicts:** resolved against Rev E and the Student Guide; `GR:` has eleven documented commands and `SO:` has note-source operands, not `ON`/`OFF`/`PLAY`/`STOP`.
- **Fill fidelity:** Atari's prose does not specify a pixel algorithm. The implementation's right-side connected-region fill is pinned by a dummy-SDL surface test and documented as the host rule.
- **Pygame availability:** the optional wheel, SDL display, and audio backend may be unavailable on some Python/OS combinations or on headless hosts. The interactive extra, capability error, and no-GUI mode must remain first-class.
- **Audio fidelity:** Atari specifies note selection and four voices, but not a modern host waveform contract. Document oscillator, volume, and mixing behavior; do not promise cycle-accurate reproduction.
- **Synchronous execution:** long `GR:` iteration or a tight `J:` loop can starve SDL events. Pump events at statement and graphics-subcommand boundaries without adding arbitrary PILOT delays.
- **Window/text lifecycle:** `CLEAR`, `QUIT`, `A:`, and existing output-device injection need a written, tested rule so GUI support does not break console or embedding use.
- **Controller configuration:** the default key map supports two joysticks and two paddles. Supporting arbitrary mappings or physical joystick hardware is separate work.

## 11. Implementation traceability

The detailed acceptance evidence lives in the repository rather than in this
document. The focused test surfaces are:

| Requirement | Evidence |
| --- | --- |
| Graphics grammar, state, repeats, clipping contract, fill delegation, and errors | `tests/test_graphics.py` |
| Shared runtime dispatch, statement-boundary audio refresh, cancellation, and headless refusal | `tests/test_interactive_runtime.py`, `tests/test_runtime.py`, `tests/test_cli.py` |
| Keyboard directions, diagonals, paddles, triggers, and focus release | `tests/test_interactive.py` |
| Lazy Pygame loading, dummy SDL display/audio smoke test, text input, and window lifecycle | `tests/test_pygame_backend.py` |
| Runnable graphics, controller, and sound examples | `tests/test_examples.py` |
| Optional-extra metadata and zero mandatory runtime dependencies | `tests/test_packaging.py` |

The implementation gate is the repository's normal quality gate: the focused
tests above, the complete pytest suite, strict Ruff and mypy checks, a wheel
build, and a warning-free Sphinx build. Native display/audio verification is
platform-dependent; CI uses fake hosts and dummy SDL devices where no physical
devices are available.

## 12. Follow-up checks and handoff

The feature is already implemented; do not build a second graphics or device
runtime. The two previously identified differences from this contract are now
resolved:

1. **Configurable controller mapping (§4.4):** `ControllerKeyMap` is injectable
   through `KeyboardController` and `PygameInteractiveDevice`; tests verify a
   non-default map without changing Atari sense values.
2. **Graphics error detail (§5.1):** malformed `DRAW`, `TURN`, and `DRAWTO`
   numeric operands name their subcommand and retain source location details.

For future changes to either boundary, run the focused suite first, then the full
repository gates before release:

```console
uv run pytest tests/test_graphics.py tests/test_interactive_runtime.py tests/test_interactive.py tests/test_pygame_backend.py tests/test_examples.py tests/test_packaging.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
uv run --group docs sphinx-build -W -b html docs docs/_build/html
```

On each supported OS with real display/audio access, manually verify window
creation, resize, keyboard focus/release, closing during a run (exit 130),
post-run window visibility, four audible voices, and sound-only execution
without a window. Dummy SDL tests are not evidence of native-device behavior.
