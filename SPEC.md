# pyPILOT Completion Specification

**Status:** The 1.0.0 base implementation was published on 2026-09-26. The 1.1.0 interactive-device release is prepared on `feature/interactive-devices`; release procedure is documented in `RELEASING.md`.
**Target:** the `rePILOT` distribution (imported as `pypilot`), a faithful implementation of **ATARI PILOT** as
specified in the *Atari PILOT External Specification*, Revision E
(27-Oct-1980).

**Normative source of truth:** the External Specification Rev E, by
**Harry B. Stewart** — Atari's own PILOT implementer, and the programmer of
record for the 1981 cartridge. A local copy and the two supporting Atari
manuals are in [`history/`](history/README.md).

> ### ⚠ Dialect notice
>
> An earlier draft of this document specified **Core PILOT** (PILOT-73 /
> IEEE Std 1154-1991) and was **wrong**. The Atari dialect diverges from Core
> PILOT on at least nine semantic points, several of them load-bearing. Where
> Core PILOT and ATARI PILOT disagree, **ATARI wins.** Where the Atari sources
> are silent or ambiguous, ATARI behaviour is adopted by analogy with the
> nearest documented case, and the choice is recorded in §10.
>
> Section 10 is therefore a **decision log against Core PILOT**, not against
> IEEE 1154.

---

## 1. Purpose and scope

pyPILOT is an interpreter for the PILOT teaching language created by John
Amsden Starkweather (UCSF) in the 1960s, standardised in 1973, and — as
targeted here — as implemented by **Atari** for the 400/800 in 1980–81.

This document specifies:

1. **What the language is** — the normative semantics pyPILOT will implement
   (§4–§9), with every deliberate deviation from Core PILOT called out (§10).
2. **What "finished" meant** — the architecture, module boundaries, and
  acceptance criteria for the 1.0 release (§2, §3, §12).
3. **How it was built** — a staged implementation history where every stage
  left the project in a working, tested state (§11).

### 1.1 Scope: why ATARI, and what is excluded

**ATARI PILOT is not a Common PILOT dialect.** This is documented, not assumed.
EDM2, on the 6502 implementations:

> "Most 6502 implementations excluding the Atari one are based on the WWU
> Common PILOT code and specifications. The reason why the Atari, Tandy Radio
> Shack and others did not follow the CP standard was that Core PILOT was
> perfectly suited to beginners who often figured out how to program in PILOT
> without any help from tutors while Common PILOT expects some programming
> knowledge from the user. In addition Core PILOT was also so small that it fit
> fine into 8k of memory or less."

So ATARI PILOT is **Core PILOT plus a small Atari-specific layer**, chosen for
beginner accessibility. Concretely, this means:

- **No floating point.** Integers only (§6.2).
- **No arrays**, no `D:` dimensioning, no `SA:`/`SM:` string arrays — all
  Common PILOT additions.
- **No `CS:`/`CN:`** cursor control as Common PILOT defines them; Atari instead
  has `PCS:` for direct cursor positioning.
- 26 single-letter numeric variables, not long names (§6.1).

**Excluded from the 1.0 base install; available as an optional interactive
extension.** ATARI PILOT's turtle graphics (`GR:`), sound (`SO:`), and hardware
controller senses are real Atari PILOT. They are implemented through an
optional host backend (`pygame-ce`), not through mandatory package dependencies.
The CLI loads that backend lazily; embedders may inject another host or remain
headless. A run that requests these devices without a host fails clearly rather
than silently dropping the command. See §10.4–§10.5.

Also out of scope:

- **Not a compiler or JIT.** A tree-walking interpreter is the right size for a
  language whose reference implementation fit in 8K of RAM.
- **Not a screen editor.** The Atari Screen Editor assigned line numbers and
  stored deferred statements. pyPILOT reads plain text files; line numbers are
  assigned by the loader, not by an editor (§4.1).

### 1.2 Normative language

"**MUST**" / "**MUST NOT**" are binding requirements. "**SHOULD**" is a
recommendation with a stated rationale. "**MAY**" is optional. Section numbers
in brackets refer to the **Atari PILOT External Specification Rev E** unless
noted.

---

## 2. Project state (2026-10-06)

The repository is a three-commit scaffold from April 2020 that never ran.

| Path | State before | State now |
|---|---|---|
| `pyPILOT.py` | 5-line stub importing a nonexistent `Runtime`/`Commands` | **Deleted** — superseded by the `pypilot` console script |
| `lang/core.py` | `PilotCore` with 10 `NotImplementedError` stubs, all declared **without `self`** | Moved to `src/pypilot/core.py`; methods are properly bound |
| `lang/helpers.py` | `Os`/`Shell` statics, all `NotImplementedError` | `src/pypilot/helpers.py`; `Os.load`/`Os.save` **implemented** |
| `lang/__init__.py` | `from .core import hmm` — **import error** | Removed |
| `tests/` | nose-style stubs importing a nonexistent `sample` module | Real pytest suite, **953 passing tests** on the interactive-device feature branch |
| `setup.py`, `requirements.txt`, `Makefile`, `MANIFEST.in` | setuptools + `nose` + `sphinx` | **Deleted** — replaced by `pyproject.toml` + `uv.lock` |
| `docs/conf.py` | 2012 `sphinx-quickstart` boilerplate, `project = 'sample'` | Modern Sphinx config, zero-warning build |
| `docs/` | Empty `index.rst` | `index.rst`, `language.rst`, `api.rst`; warning-free Sphinx build |
| — | — | `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `.python-version` |

### 2.1 The bug worth recording

`lang/core.py` declared its handlers as:

```python
def _a(self, *args):  # actually: def _a(*args):
    raise NotImplementedError
```

with **no `self` parameter and no `@staticmethod`**. A call site of
`self._a(stmt)` therefore raised `TypeError: _a() takes 0 positional arguments
but 2 were given` — the method body was unreachable. The modernised
`PilotCore` binds them correctly and `tests/test_advanced.py` asserts
`handler.__self__ is core` so this cannot regress.

---

## 3. Modernisation baseline (done)

The build is now reproducible and CI-enforced.

- **Package manager:** `uv` only. `uv.lock` is committed; `UV_FROZEN=1` in CI.
- **Layout:** src-layout, `src/pypilot/`, with `py.typed` (PEP 561).
- **Build backend:** `hatchling`. Distribution name `pypilot`, import name
  `pypilot`, console script `pypilot = pypilot.cli:main`, plus
  `python -m pypilot`.
- **Python:** `>=3.12`; pinned by `.python-version`; CI matrix 3.12 + 3.13 on
  Linux, Windows, and macOS.
- **Runtime dependencies:** none. PILOT is small enough to stay stdlib-only, and
  a zero-dependency interpreter is a feature for something meant to run on a
  Raspberry Pi in a classroom.
- **Dev tooling:** `pytest`, `pytest-cov`, `ruff` (lint + format, 11 rule
  families), `mypy --strict`, `sphinx`.
- **Quality gates:** `ruff check`, `ruff format --check`, `mypy`, `pytest`,
  `uv build` all green; docs build warning-free.
- **CI:** `.github/workflows/ci.yml` runs the full matrix and publishes the docs
  artifact.

---

## 4. Language: program structure

### 4.1 Source encoding and line numbers

Program text is **UTF-8**. Input is read as UTF-8 with a fallback to the
platform encoding, then to `latin-1` with replacement, so that a 1980s lesson
saved on a DOS box still loads. Line endings: LF, CRLF, and lone CR all
terminate a line.

The Atari Screen Editor assigned a **line number, 0–9999**, to every deferred
statement [4.1]. pyPILOT reads plain text files and has no editor, so:

- The loader assigns sequential line numbers starting at 1.
- An **optional** leading numeric field on a source line is accepted and
  ignored, so a `LIST:`ed or `SAV:`ed Atari program still loads. Numbers
  outside `0`–`9999` are a syntax error.
- Line numbers appear in `LIST:` output and in runtime error messages, matching
  the Atari experience, but are not editable input.

### 4.2 Line structure [4.0]

```
«input line»    ::= [«line#»] [«statement»] <EOL>
«statement»     ::= [«label»] [«command»] [«comment»]
«label»         ::= "*" «label-name»
«label-name»    ::= «alphanumeric» { «alphanumeric» }   -- any length [4.2]
«command»       ::= «command-name» [ «condition» ] ":" [ «params» ]
«command-name»  ::= «letter» { «letter» }                 -- 1 or 2 [4.3]
«condition»     ::= [ "Y" | "N" ] [ "(" «nexp» ")" ]
«comment»       ::= "[" { any char except EOL }          -- [4.6]
```

Two changes from the Core PILOT grammar, both from the Atari spec:

- **A label may be followed by a command on the same line** — `*HERE T:text` is
  valid [4.0]. Core PILOT readings often disallow this.
- **The comment delimiter is `[`, not `//`** [4.6]. `R:` also exists as a
  command (§9.1), but a `[…]` comment is a distinct, field-level construct.
  There is no `//` intraline comment in ATARI PILOT.

Command names are **exact** [4.3]: `TYPEN:` is not a typo-tolerant `TY`, it
parses as `TY` followed by junk. pyPILOT MUST reject a malformed command name
rather than silently truncating it.

**Blanks are significant in operands** [4.5] — `M:YES,YEAH,SURE_` matches the
word plus a trailing space, which is a different, deliberate match from
`M:YES,YEAH,SURE`.

### 4.3 Field delimiting [4.5]

Every field is terminated by the first character not valid for that field. This
means the parser is a sequence of small scanners, not a fixed-split.

**To the left of the `:`, blanks are ignored** and may be used freely to format
a line. To the right of the `:`, **blanks are significant** and are stored.

**Commas and blanks are interchangeable as operand separators**, and any
consecutive run of them counts as one separator [4.5]:

```
LIST:100 200   ≡   LIST: 100, 200   ≡   LIST: 100, , ,   ≡   LIST:100,,200
```

The one exception is `M:`, where blanks carry meaning (§7.4).

### 4.4 Command continuation [4.7]

A statement with **no command name and no condition** continues the most recent
statement's command *and* condition:

```pilot
T(#A>40):NOT ENOUGH
:TRY AGAIN
:ONE MORE TIME
```

Rules — these are tighter than the Core PILOT reading:

- Continuation is legal **only after `T:`, `Y:`, `N:`, and `R:`** in run mode.
  A continuation after any other command is a **runtime error** that stops the
  program.
- In immediate mode, continuation is allowed after any command.
- The default continuation command at startup is `T`, and is reset to `T` by
  RESET, by any error, and on returning to immediate mode.
- Elision is resolved at **parse** time, so a continuation inherits a concrete
  command and condition.

### 4.5 Blank lines and comments

- Blank and whitespace-only lines are ignored.
- `R:` makes the rest of the line a comment. `R` may take a condition, so `RY:`
  is a legal no-op.
- A `[` anywhere in the statement field begins a comment running to end of line
  [4.6], and the text may contain any character including `:` and `[`.

#### The literal-bracket limitation

`[` is an **unconditional** comment delimiter with no escape, so **a literal
`[` cannot be typed in any operand**. `T:[$LEFT]` does not print a bracket; it
prints `LEFT IS ` and discards the rest of the line as a comment.

This is authentic ATARI behaviour and a genuine wart — a teaching language where
you cannot print a bracket. It is recorded here so that no example or test
tries to. Any program wanting a visible delimiter in its output must use
another character; §13.4's example does.

It also means `Program.source` is not guaranteed to re-parse identically when a
`[` appears in an operand, since the bracket re-reads as a comment delimiter.
Round-trip **is** guaranteed for programs that avoid literal brackets, and
`tests/test_corpus.py` asserts it for the whole example corpus.

---

## 5. Internal representation

Modules, and what each owns. This is the architecture the roadmap builds
against.

| Module | Responsibility |
|---|---|
| `errors.py` | Exception hierarchy for syntax, runtime, undefined-label, and unsupported-command errors. |
| `syntax.py` | `Statement`, `Condition`, `Parser`, `Program`, and the Atari command vocabulary. |
| `expressions.py` | Numeric-expression tokenizer and evaluator. |
| `values.py` | 16-bit `Numeric` model and text-expression scanning/expansion. |
| `state.py` | Numeric and string stores, accept buffer, match results, and module call stack. |
| `match.py` | Match-field parsing, accept-buffer search, and `JM:` label splitting. |
| `io.py` | Input/output protocols and console, buffer, and scripted implementations. |
| `devices.py` | Device-oriented `READ`/`WRITE`/`CLOSE`/`LOAD`/`SAVE` support. |
| `core.py` | Implemented run-mode statement handlers and explicit refusal paths. |
| `runtime.py` | Interpreter dispatch, conditions, execution limit, devices, and trace hooks. |
| `helpers.py` | Host OS helpers and deferred-program editing operations. |
| `repl.py` | Interactive immediate mode and its command loop. |
| `cli.py` | Command-line parsing, checking/listing, program execution, and REPL entry. |

### 5.1 `Statement`

```python
@dataclass(frozen=True, slots=True)
class Statement:
    label: str | None  # verbatim; "*" stripped, case preserved
    command: str  # e.g. "T", "TY", "GR", "MS"
    condition: Condition | None  # Y | N | (nexp), possibly both
    params: str  # raw text right of the ":"; unparsed
    comment: str | None  # text inside [...]
    source: str  # original text, for error messages
    line_number: int  # 1-based, assigned by the loader
}
```

Three deliberate choices:

- **Operands are not parsed** at this layer. Operand meaning is
  command-specific: `C:` operands are arithmetic, `M:` operands are a match
  list, `T:` operands are a text expression. The lexer keeps the raw text and
  each handler parses what it needs. This keeps a 300-line parser from
  becoming a 3000-line one, and mirrors the original interpreters.
- **Conditions are `Y`/`N` *and* an expression together**, not an either/or
  choice [4.4] — see the `Condition` type.
- **Statement is frozen** and all mutable state lives in `PilotState`. This is
  what allows statements to be shared, cached, and pre-indexed by label.

### 5.2 Frozen and typed

Every public type is fully annotated and `mypy --strict` clean. Mutable state
lives in `PilotState`, never on `Statement` — this is what allows statements to
be shared, cached, and pre-indexed by label.

---

## 6. Language: values

### 6.1 Variables

| Type | Syntax | Python representation | Count |
|---|---|---|---|
| Numeric | `#A` … `#Z` | `int` | **exactly 26** [5.1.2] |
| String | `$NAME` | `str` | unbounded, names ≤ 254 chars [5.2.2] |
| Special | `%F` `%M` `%X` `%Y` `%A` | `int` | read-only [5.1.5] |
| Controller sense | `%J` `%P` `%T` `%H` `%V` `%L` | `int` | [5.1.4] |

- **Numeric variables are single letters `#A`–`#Z` and there are only 26** of
  them [5.1.2]. This is not a simplification for convenience — it is a hard
  limit of the target, and `#XY` is *not* a valid name. Python's
  arbitrary-precision `int` MUST be wrapped so that this limit is enforced.
- **String variable names are alphanumeric, up to 254 characters** [5.2.2], with
  no 10-character cap. All characters in a name are significant and retained.
- Names are **case-sensitive in ATARI PILOT** [4.2, 5.2.2] — unlike most other
  dialects, which fold case. pyPILOT MUST NOT normalise case.
- A string variable's data may be the **null string** (defined, empty), which is
  **not the same as undefined** [6.1.2].

#### The undefined-variable rule [5.2.3]

> If a string variable is undefined, **its name is substituted for the missing
> value.**

This is the single most surprising rule in the language, and the opposite of
what most other PILOT implementations do:

```pilot
T:[$UNSET]        →   [UNSET]        (Atari; Core PILOT and psPILOT give [])
T:$A=hi
T:[$A]            →   [hi]
```

Rationale: a learner who has not yet filled in a variable sees the name of the
field they are missing, which is more useful than a blank. pyPILOT MUST
implement substitution, and MUST have tests pinning it — a test written from
Core PILOT intuition would get this backwards.

### 6.2 Numeric semantics

- **Integers only.** No floating point (§1.1). There is no real type.
- **Range is 16-bit signed: −32768 … 32767** [5.1]. The Primer is emphatic:
  "PILOT arithmetic uses only integers in the −32768 to 32767 range. Fractional
  numbers are not allowed."
- **Overflow wraps silently and is NOT an error** [5.1]. The Primer shows
  `32767 + 1` returning `-32768` and calls the behaviour "strange". Two's
  complement, so `32767 - 32768 = -1`.
- **Division truncates toward zero, dropping the remainder** [5.1.7; Primer
  p.85]. The Primer gives worked examples: `7/3 = 2`, `5/4 = 1`, `10/5 = 2`,
  `99/12 = 8`.

  > This is **not** Python's `//` (which floors: `-7//3 = -3`) and **not**
  > round-half-away-from-zero. It is C-style truncation: `-7/3 = -2`. Implement
  > with `int(a / b)`-equivalent semantics on integers, or `abs`-based
  > truncation, and test both signs.

- **Modulo is spelled `\` (backslash), not `%`** [5.1.7]. `%` is the prefix
  sigil for special and controller-sense variables (§6.1) and cannot double as
  an operator. `7\3 = 1`, `99\12 = 3`.
- **There is NO operator precedence.** Spec §5.1.7 is explicit: *"Numeric
  expressions are evaluated from left to right, with no operator precedence
  rules; parentheses are allowed (encouraged?) to either clarify the formulae
  or to alter the left to right evaluation scheme."*

  > This is a **correction** to an earlier draft of this document, which
  > specified conventional precedence (`*` before `+`). In ATARI PILOT,
  > ``1+2*3`` is ``9``, not ``7``. Any program that relies on precedence is a
  > Core PILOT habit and would silently compute the wrong thing here. See
  > §10.1.

  - Up to **2 levels of non-redundant nesting** are allowed [5.1.7]. Redundant
    parens - ``(((7)))`` - may nest arbitrarily.
- **The remainder is always positive** [5.1.7]: "``\`` is the modulus operator
  (result is always positive)". So ``-7\3`` is ``1``, **not** ``-1``.

  > This is a **second correction** to an earlier draft, which had the remainder
  > following the sign of the dividend (the C convention). ATARI uses the
  > absolute value.

- Relational operators: ``= <> > >= < <=``. Each yields **1 for true, 0 for
  false** [5.1.7], so relations compose with arithmetic:
  ``(#A<3) * (#B=#C)`` is a logical *and*, and ``(*D<>5) + (#2/2=1)`` a logical
  *or*.
- Division or modulo by zero raises `PilotRuntimeError`.
- Numeric constants may carry a leading unary minus and are truncated to 16 bits
  on entry [5.1.1].

### 6.3 Random numbers [5.1.3]

`?` yields a hardware-generated random number and is usable **anywhere a numeric
expression is allowed**:

```pilot
J(?):*SOMETIMES
C:#A=?
T:Your number is #A
```

**Correction (§10.1 row 15).** `?` is *not* a random draw in a **text**
expression — it is an ordinary literal character there. §5.1.3 says "anywhere a
numeric expression is allowed", and §5.2.3's grammar for `<operand>` admits only
a text literal, a string variable, a numeric variable, a controller sense, a
special variable or a pointer. §5.2.1's list of characters that may *not* be
literals — `$`, `#`, `%`, `@`, `[`, `<EOL>` — does not contain `?` either.

The spec relies on this itself: `T:#X%, ARE YOU SURE?` must print the `?`, and
the §6.1.4 worked example `A:=WHAT WILL HAPPEN?` only yields its printed
`$LEFT` of `'AT'` if the `?` survives into the accept buffer untouched.

The source of randomness is unspecified. pyPILOT MUST make it seedable per run
for testability, and MUST document the default.

### 6.4 String semantics

- Concatenation is juxtaposition, not `+`.
- **There is no backslash escaping in ATARI PILOT** (§10.1). A sigil is literal
  when the character following it does **not** start a valid variable
  specification [5.2.1] — and a space always works as the separator:
  `T:YOUR WEIGHT IS 30#.` and `T:THE COST IS $#V.`.
- A trailing `_` in a text expression produces a trailing blank [5.2.3], which
  the Atari Screen Editor would otherwise have stripped.
- **String indirection** [5.2.4]: `$$ABC` is the data of the string *named by*
  the data of `$ABC`. Any depth. If a level is undefined the result is as for an
  undefined name (§6.1) — i.e. the *substituted name*, not empty.
- There is no string comparison operator beyond the six relational operators;
  string comparison is lexicographic by code point.

### 6.5 Text expressions [5.2.3]

A text expression is one or more elements concatenated left to right. Each
element is literal text unless introduced by `$`, `#`, `%`, or `*`/`@`, which
begin a variable reference; scanning resumes as literal text at the end of the
name. The result is buffered to **254 characters**, and a longer expression is
**truncated silently** — no error, no warning.

Expansion applies to the operand of `T:`, `Y:`, `N:`, `M:`, `MS:`, `C:`
(string assignment), `A:=`, and `WRITE:`.

Expansion is **single-pass**: expanded text is not re-scanned for further
variable references. This prevents infinite recursion and matches the reference
implementation.

### 6.6 Special variables [5.1.5]

| Name | Meaning |
|---|---|
| `%F` | Free memory remaining |
| `%M` | Match result: the **ordinal** of the matching field, or 0 if none [6.1.3] |
| `%X` | Graphics x-coordinate (`GR:`) |
| `%Y` | Graphics y-coordinate (`GR:`) |
| `%A` | Graphics angle/heading (`GR:`) |
| `%Z` | Graphics color at the cursor: 0 background, 1 red, 2 yellow, 3 blue |

`%M` is **not** a matched-string value — it is the *field number* that matched.
For the matched text, use `MS:`, which produces `$LEFT`, `$MATCH`, and `$RIGHT`
(§7.5). The Core PILOT `%MATCH`/`%LEFT`/`%RIGHT` triple has **no** Atari
equivalent as special variables.

`%X`/`%Y`/`%A`/`%Z` read the active graphics state. They read 0 when no
interactive graphics mode is active. `%X` and `%Y` are rounded to integers;
`%Z` reads 0 outside the visible graphics area (§10.4).

### 6.7 Controller sense [5.1.4]

`%J<n>` joystick, `%P<n>` paddle, `%T<n>` trigger, `%H`/`%V`/`%L` lightpen
horizontal/vertical/light. Recognised anywhere a numeric constant is allowed.

With no interactive host, or for an unmapped device index, these MUST resolve
to a neutral value (0 = no input) rather than raising. The optional keyboard
controller map is specified in §10.5.

---

## 7. Language: input and output

### 7.1 The accept buffer

A single line of learner input. Written only by `A:`. Read by `M:` and by
`%LEFT`/`%RIGHT`/`%MATCH`.

### 7.2 `A:` — Accept [6.1.2]

```pilot
A:                  R:anonymous accept; buffer only
A:$NAME             R:one string variable
A:#NUM              R:one numeric variable
A:SRIGHT            R:leading `S` is a synonym for `$` in accept operands
A:$WHAT=HI          R:assign the text expression to the buffer, do NOT prompt
```

- **One or two operands only** [6.1.2]. There is no multi-variable form in ATARI
  PILOT — `A:$A,$B,$C` is not valid, unlike Core PILOT. The second operand, when
  present, is `=«texp»` (§7.2.1).
- A leading **`S` is a synonym for `$`** in an accept operand. The spec's own
  examples use both `A:#A` and `A:SNAME` [6.1.2]. Both MUST parse.
- **Numeric accept never errors** [6.1.2]. If the input contains a numeric
  constant *anywhere*, that value is stored; if it is totally non-numeric the
  result is **zero, with no error message**. An empty line sets a numeric
  variable to 0 and a string variable to the null string.
- Null string and undefined string are **different states** [6.1.2] and the
  implementation MUST distinguish them, because they print differently (§6.1).

#### 7.2.1 `A:=«texp»` — assign instead of prompt [6.1.2]

When the second operand is present, the text expression is evaluated and
assigned to the accept buffer, and PILOT does **not** go to the console for
input. This is how a program synthesises accept-buffer content — and it is
still subject to the normalisation below.

#### 7.2.2 Accept-buffer normalisation [6.1.2]

Accepted data passes through this transformation on its way **to the accept
buffer**, but *not* to the string variable:

1. A space is inserted at the **beginning** of the data.
2. A space is inserted at the **end** of the data.
3. **Lower-case letters are converted to upper case.**
4. **Multiple spaces collapse to a single space.**
5. The buffer is 254 characters; longer input is **truncated**.

This is why every `M:` example in the Atari manuals ends with a trailing `_` or
space — the buffer is ` YEAH `, not `YEAH`. Any test written from Core PILOT
intuition will get this wrong.

### 7.3 `T:` / `Y:` / `N:` — Type [6.1.1]

- `T:«text»` writes the expanded text expression plus a newline.
- `T:` with an empty operand writes a bare newline.
- `Y:` and `N:` are **not separate commands** - spec 6.1.1 calls them
  *"two alternate names"* for `TY:` and `TN:`. Every spelling (`Y`, `TY`, `YY`,
  `NY`, `N`, `TN`, `YN`, `NN`) resolves to `T` plus a match condition, so
  `N(#A>0):` is the **conjunction** of a `N` flag and an expression (spec 4.4).
  The second letter is the condition, which is why `YN` never executes.
- ATARI PILOT has **no `H` modifier** and no word wrap. (`P:W«n»` and the `H`
  modifier are Core PILOT/IEC additions, absent here.)

### 7.4 `M:` — Match [6.1.3]

```pilot
M:YES,YEAH,SURE     R:comma-separated fields
M:|YES|YEAH|SURE    R:vertical-bar-separated fields
M:<right arrow>IS   R:match 'IS' somewhere past the leading blank
M:$VERBLIST         R:fields from a string variable
```

Three things here differ sharply from Core PILOT and MUST be got right:

- **Matching is a substring search of the buffer for each field** [6.1.3]. Spec
  6.1.3 describes it as finding *"an exact match with one of the Match command
  fields"*, and the manual illustrates `M:YE,SURE` as *"a less precise matching
  of character substrings within words"* — so `M:YE` **does** match the input
  `YEAH`, deliberately.

  > **Correction.** An earlier draft of this document claimed matching was an
  > *exact whole-buffer* comparison and that `M:YE` would not match `YEAH`. That
  > was wrong, and it contradicts spec 6.1.4's own worked example, which splits
  > `$LEFT`/`$RIGHT` *around* a match found in the interior of the buffer — only
  > possible if the field was located by substring. §7.4.1's `<right arrow>`
  > exists for exactly this reason: to say *look here, not at the first hit*.

- **The field separator is a comma, or — if the operand begins with `|` — a
  vertical bar.** There is never a case where both act as separators [6.1.3].
  A leading `|` is a separator *selector*, not an empty first field.
- **The match flag holds the ordinal** of the field that matched, or 0 for no
  match [6.1.3]. This value is `%M` (§6.6) and is what `JM:` (§9.1) uses. It is
  **not** a boolean, so `JM:1,*FIRST` can distinguish which alternative matched.

Fields are scanned **in order**: the buffer is searched for field 1, then
field 2, and so on, until one matches [6.1.3].

- An **empty field is a null match** and matches anything [6.1.3]:
  `M:THIS,THAT,,OTHER` — the empty third field matches any input.
- `M:` with a null operand is **not allowed** and is a syntax error [6.1.3].
- Matching is against the **normalised** buffer (§7.2.2), so it is
  case-insensitive by construction, and the match string must be written in
  the same normalised form. There is no `CS`/`CI` case toggle in ATARI PILOT.

#### 7.4.1 `<right arrow>` — skip characters [6.1.3]

Cursor-right characters (ATASCII `0x1E`, ESC CTRL-) at the start of the operand
(they may start after the optional leading `|`) cause matching to begin at the
**n+1th** character of the accept buffer, where *n* is the number of arrows.
One right arrow is used to allow pattern matching to start after the
omnipresent leading blank character in the accept buffer.

So an arrow count of *n* leaves the character at 0-based index *n* as the first
one considered, and the window is the buffer from that point on. This is a real
off-by-one to get wrong, and the spec's own worked example settles it: **three**
arrows over ` WHAT WILL HAPPEN? ` yield `$LEFT = 'AT'`.

In source text an arrow is a literal control character, written `\x1e`. It is
rare, because matching the whole buffer already works; it exists for locating a
match *within* the buffer.

### 7.5 `MS:` — Match Strings [6.1.4]

`MS:` behaves exactly like `M:`, and additionally sets three named strings on a
successful match:

| Variable | Value |
|---|---|
| `$LEFT` | everything left of the match |
| `$MATCH` | the matched data |
| `$RIGHT` | everything right of the match |

- Any of the three may be **null**, depending on where in the buffer the match
  fell.
- On a **failed** match, all three **retain their previous values** [6.1.4] —
  they are not cleared. This differs from `M:`, and a test must pin it.
- When `<right arrow>`s are used, `$LEFT` does **not** include the skipped
  characters [6.1.4].

Worked example from the spec [6.1.4]:

```pilot
A:=WHAT WILL HAPPEN?
MS:<right arrow><right arrow><right arrow>_
T:$LEFT     →  'AT'
T:$MATCH    →  ' '
T:$RIGHT    →  'WILL HAPPEN? '
```

**Three** arrows are needed to reproduce those values, and the arithmetic is
the clearest evidence of the n+1th-character rule: the buffer is
`' WHAT WILL HAPPEN? '`, and stepping the window forward three characters puts
the embedded blank at the match point with `'AT'` behind it.

> The spec prints a *second* worked example, `A:=THIS IS A TEST.` with
> `MS:...IS,WAS,WILL,BE` giving `$LEFT = ' THIS '`. **That one is not
> reproducible under any arrow count**, and its printed values are almost
> certainly OCR corruption — the surrounding text renders as `SLEFT =* 1 THIS 1`,
> with stray `*` and `1` characters. The buffer is `' THIS IS A TEST. '` and
> `'IS'` first occurs at index 3, giving `$LEFT = ' TH'` with no arrows. Do not
> write a test against that example; the one above is clean and verified.

This is the Atari replacement for Core PILOT's `%LEFT`/`%MATCH`/`%RIGHT`
special variables, which do not exist here (§6.6).

---

## 8. Language: control flow

### 8.1 Labels and the label table

- A label is `*` followed by alphanumerics, **of any length** [4.2], delimited
  by the first non-alphanumeric character.
- Labels are **case-sensitive** and stored verbatim [4.2].
- **There is NO duplicate-label detection** [4.2]. If two statements share a
  label, the one with the **lower line number** is the target of `J:` and `U:`.
  This is a correction to the earlier Core PILOT draft, which made duplicates a
  hard error.
- The parser builds a `label → statement index` table in one pass, first
  writer wins. It MUST be a dict lookup, not a linear scan: `J:` inside a loop
  is the hottest path in any PILOT program.

### 8.2 `J:` — Jump

```pilot
J:*RESTART
```

- An undefined label is a `PilotUndefinedLabelError` naming the line.
- A jump into the middle of a `U:`-active subroutine is legal. The call stack is
  untouched; only the program counter moves.
- The operand is a **single** label [6.1.7], not a list.

**ATARI PILOT has no `@A`/`@M`/`@P` shorthand jumps.** Those are Core
PILOT/IEC additions. The Atari equivalents are separate commands: `JM:`
(jump on match, §8.2.1). An `@`-jumps target MUST be a syntax error, not
silently ignored.

### 8.2.1 `JM:` — Jump on Match

This is the command that makes `M:`'s **ordinal** worth having, and it is the
Atari replacement for Core's `@M` shorthand (§10.6).

```pilot
A:$ANSWER
M:YES,NO,MAYBE
JM:*STUDENT,*GUEST,*UNSURE
```

> The Jump on Match command allows the running program to jump to one of
> several labeled statements, depending upon the result of the most recently
> executed Match command. Each of the labels specified as an operand,
> corresponds to a Match field; if the match was successful with the *n*th
> match field, the *n*th operand label will be used for the jump. If the prior
> Match was unsuccessful, or if there is no *n*th operand label, **no jump will
> be executed**. [6.1.8]

Three rules, all load-bearing:

1. **Index correspondence.** Operand *n* is used when `%M` is *n*. So the label
   list is positional against the *match field* list, not against the buffer.
2. **A failed match never jumps.** `%M = 0`, and there is no 0th operand, so
   `JM:` is a no-op and execution falls through. This makes `JM:` safe to place
   unconditionally after an `M:` that may fail.
3. **Too few labels is a fall-through, not an error.** `M:A,B,C` with
   `JM:*ONE,*TWO` must run `*TWO` for field 2 and **continue past** `JM:` for
   field 3. An error here would punish a program the Atari accepts.

#### Operand grammar [6.1.8]

```
<jump match operand> ::= <label> [<sep><jump match operand>]
```

This is **recursive**, not a flat list — which matters because §4.5 makes any
run of commas and/or blanks a single separator (to the right of the colon),
*except* within the Match commands. So both of these are valid and equivalent:

```pilot
JM:*L1 *L2 *L3
JM : *HERE , *THERE , *EVERYWHERE
```

Parsing MUST therefore split on runs of comma/blank, not on a single character,
and MUST NOT apply the `M:` rule that blanks are significant. Labels are
alphanumeric, so a blank is always a separator and never part of a label — that
is what makes the space-separated form unambiguous.

`JM:` with a null operand is a no-op, not an error.

### 8.3 `U:` — Use (call) — “modules”

ATARI PILOT calls a subroutine a **module**; the Primer devotes section 8 to
them, including *nested* and *conditional* modules.

```pilot
*SUB
T:in the module
E:

U:*SUB
```

- Saves the return address, jumps to the label. Execution resumes after the `U:`
  on the matching `E:`.
- **Recursion MUST work**, bounded by the use-stack depth, raising
  `PilotRuntimeError` on overflow rather than a Python `RecursionError`.
  The limit is **8**, not a host-sized number: §6.1.9 says *"Up to eight (8)
  Uses may be nested before the system responds with an error message."* That
  is an Atari machine with 256 bytes of variable space, and it is a real design
  constraint rather than an implementation detail — a lesson that nests
  deeper than 8 is using more stack than a real Atari allows. pyPILOT MAY raise
  it via `PilotMaxUses`, but the **default MUST be 8** so that programs behave
  as they would on the target.
- No arguments and no return value. Modules communicate through variables only.
  That is authentic, and any nicer design would not be PILOT.
- `U:` to a label on the previous line is legal and infinite-loops; there is no
  loop detection.

### 8.4 `E:` — End

The spec is unambiguous and states it as a single rule [6.1.10]:

> The End command tells the interpreter to return to the statement following
> the most recently executed Use command, **or to stop the execution of the
> program if there is no Use return stacked.**

So `E:` is one statement with **two behaviours**, chosen by whether the use stack
is empty. There is no separate module-end command — `E:` *is* it.

- **With a use return stacked** (inside a module): return to the statement
  following the `U:` that called it.
- **With an empty use stack** (outermost level): terminate the program
  successfully.
- `E:` takes no operand [6.1.10, App. B]. An operand is a syntax error.
- It is conditional like any other statement, so `EY:` and `EN:` are legal and
  the spec gives both as examples. That is what makes guarded module returns
  expressible.

### 8.5 `LOAD:` — load another program

`LOAD:«device»` replaces the running program [6.1.21]. The statement after
`LOAD:` is unreachable.

A run-mode load clears the **program area** and the **Use stack**, and then
executes the newly loaded program *"without any initialization of the program
environment"* [6.1.21]. So it **preserves** the accept buffer, the match flag,
and every variable. That is the opposite of `RUN:`, which does initialise, and
it is why `VNEW:` exists — a program that wants a clean slate asks for one.

> **Correction.** An earlier draft of this section said `LOAD:` *discards* the
> accept buffer. §6.1.21 says the opposite, and the two are now separate
> methods on `PilotState`: `reset()` for `RUN:`, `clear_call_stack()` for
> `LOAD:`.

> Core PILOT's `L:` does not exist in ATARI PILOT. `L` is a valid **label**
> prefix, not a command; `L:` is not an error but a label definition. Recorded
> in §10.6.

---

## 9. Language: statements, complete

### 9.1 Commands

The full Atari command set [App. B]. **Core** commands have one-letter names;
**Atari extensions** have two or more. Mode is `R/I` (run and immediate) or `I`
(immediate only).

#### Core PILOT — implemented in 1.0

| Command | Purpose | Section |
|---|---|---|
| `A` | Accept into buffer and/or a variable | §7.2 |
| `R` | Remark | §9.2 |
| `C` | Compute and assign numeric or string | §9.3 |
| `T` | Type — **including every `Y`/`N` spelling** | §7.3 |
| `M` | Match | §7.4 |
| `J` | Jump to a label | §8.2 |
| `U` | Use (call) a module | §8.3 |
| `E` | End — return from a module, or stop | §8.4 |

`Y` and `N` are deliberately absent: spec 6.1.1 makes them abbreviations for
`TY`/`TN`, so they are spellings of `T`, not commands of their own (§7.3).

#### Atari extensions — language-relevant, implemented in 1.0

| Command | Purpose | Section |
|---|---|---|
| `MS` | Match, producing `$LEFT`/`$MATCH`/`$RIGHT` | §7.5 |
| `JM` | Jump on match — `<label list>`, uses the match ordinal | §9.4 |
| `PA` | Pause *n* units | §9.5 |
| `PCS` | Position cursor to `<col><row>` | §9.5 |
| `VNEW` | New variables — reset the string variables | §9.5 |
| `DUMP` | Dump string variables (diagnostic) | §9.5 |
| `LOAD` | Load a program from a device | §8.5 |
| `READ` | Read from a device into a variable | §9.6 |
| `WRITE` | Write a text expression to a device | §9.6 |
| `CLOSE` | Close a device | §9.6 |
| `TRACE` | `ON`/`OFF` — trace execution | §9.5 |
| `CALL` | Call a machine-language routine — **unsupported** | §10.7 |
| `TAPE` | Cassette control `ON`/`OFF` — **unsupported** | §10.7 |
| `TSYNC` | Cassette sync — **unsupported** | §10.7 |
| `DOS` | Shell to DOS — **unsupported** | §10.7 |

#### Atari extensions — device-dependent, specified but unimplemented
#### Atari extensions — optional interactive devices

These are device-dependent ATARI PILOT commands backed by the optional
interactive host. The default installation remains headless and does not
require the optional `pygame-ce` dependency.

| Command | Purpose |
|---|---|
| `GR` | Turtle graphics — `CLEAR PEN GOTO DRAWTO FILLTO TURNTO GO DRAW FILL TURN QUIT` (11 documented subcommands) |
| `SO` | Up to four Atari note sources, refreshed after each statement |

Programs requesting these commands without an interactive host MUST fail
clearly with `PilotUnsupportedError`; they MUST NOT silently skip the command.
The CLI lazily loads the Pygame CE backend when one of these devices is first
needed. Embedders may inject another implementation.

### 9.2 `R:` — Remark

The operand is discarded. `R` may carry a condition, so `RY:` is a legal
no-op. `R:` is a command; `[…]` is a separate field-level comment (§4.2).

### 9.3 `C:` — Compute

```pilot
C:#AVG=(#X+#Y)/2
C:$MSG=HELLO, $NAME
C:#R=$A\6          R:modulo — backslash, not %
```

- `C:#VAR=«nexp»` — numeric assignment. `VAR` MUST be `#A`–`#Z` (§6.1).
- `C:$VAR=«texp»` — string assignment by text expression.
- A type mismatch is a `PilotRuntimeError` at execution, not a load error, so
  dynamically generated lessons still work.
- Assignment happens **after** the right-hand side is fully evaluated, so
  `C:#A=#A+1` is well-defined.
- `C:` on a **pointer** target (`C:@B«addr»`) is BASIC `POKE` [5.1.6]. With no
  Atari memory model this raises `PilotUnsupportedError` (§10.5).

### 9.4 `JM:` — Jump on Match [6.1.8]

`JM:«label list»` jumps to the first label in the list that the last `M:` could
have matched — that is, it uses the **match ordinal**. With
`M:YES,NO,MAYBE` producing ordinal 2, `JM:*NO,*MAYBE` jumps to `*NO`.

This is the Atari replacement for Core PILOT's `@M` shorthand, and it is how
multi-way branching is written. The Primer introduces it in section 5 as an
*advanced branching technique*.

### 9.5 Utility commands

| Command | Behaviour |
|---|---|
| `PA:«nexp»` | Pause *n* units. The operand is a **`nexp`**, not a text expression [6.1.14], so `PA:#D` is a real delay and not a variable named "1D". The increment is **1/60 second** — `PA:60` ≈ 1 s. `PA:0` "delays to the next clock tick" [6.1.14], so it is never a true no-op. Negative values clamp to zero. |
| `PCS:«col»,«row»` | Position the cursor. Column 3–39, row 0–23, upper-left is 3,0 [6.1.18]. This is ATARI's cursor control; there is no Core PILOT `CS:`/`CN:`. |
| `VNEW:[$#]` | New variables — clear string and/or numeric variables [6.1.11]. Null clears both; `$` clears strings; `#` clears numerics. **Clearing the string variables also closes every open file** (below). |
| `DUMP:` | Dump string variables and their values [6.1.20]. Diagnostic; writes to the output device. |
| `TRACE:ON\|OFF` | Toggle statement tracing [6.1.19]. pyPILOT also exposes this as the `--trace` CLI flag (§12). |

#### `VNEW:$` closes every open file [6.1.17]

The Atari tracks open files **in the string table itself**: each open device
gets a string whose name is the device spec appended to `@`, and whose value is
the IOCB slot character. The spec says so plainly:

> These strings are of no interest to the PILOT user except that they appear in
> the string variable list produced by the Dump command, and **clearing the
> string variables using the VNEW command has the effect of closing all files**.

pyPILOT models this the same way rather than keeping a hidden side table,
because it makes `VNEW:$` do the right thing for free and makes `DUMP:` show
what the Atari would show. The names use `@` because that is the spec's own
letter — and `@` is *not* a sigil inside a text operand (§6.4), so `$@C` scans
as a literal string name rather than being mistaken for a memory pointer.

#### `PA:0` MUST be a yield point

`PA:0` is not a no-op — it is a clock tick. The interpreter MUST give an
embedding host a chance to regain control there, which is what makes
cooperative multitasking and responsive input possible. This is a hard
requirement, not a nicety.

### 9.6 I/O commands [6.1.17]

ATARI I/O is **device-oriented**, not handle-oriented — a major departure from
Core PILOT's `FA`/`FB`/`FC`/`FO`/`FR`/`FW` family:

```
READ:«device»[«var»]
WRITE:«device»,«texp»
CLOSE:«device»
```

- «device» is a single-character Atari device name (`C` cassette, `D`
  diskette, `P` printer, `S` screen, `K` keyboard).
- There are **no numeric file handles**. The earlier Core PILOT draft's
  `FA:#H,«file»` form does not exist here; it is a syntax error, not a
  reinterpretation. Recorded in §10.6.
- `LOAD:` (§8.5) and `SAVE:` are the program-level counterparts, and they take
  a device rather than a path.

pyPILOT maps the Atari devices onto host resources. The mapping is documented
in `docs/language.rst` rather than being implicit, and the device letter is the
**first** character of the expanded device spec.

| Atari | Device [6.1.17] | pyPILOT host mapping |
|---|---|---|
| `C` | Cassette | a file under the cassette directory (`~/.pypilot/cassette/`) |
| `D` | Diskette | a file under the disk directory (`~/.pypilot/disk/`) |
| `P` | Printer | the output device only — never readable |
| `S` | Display handler | the output device only — never readable |
| `E` | Screen editor | the input device (`READ:E` reads a line) |
| `K` | Keyboard | the input device |

`D:ELIZA` and `$FILE` are both valid device specs, and both name the *same*
thing once expanded — a spec is either a text literal or a string variable
whose value is the device/filename.

#### Open is implicit, and there is no `OPEN` [6.1.17]

> There is no explicit OPEN type of command provided; the first use of the name
> in a READ or WRITE command will attempt to OPEN the device.

So a device is opened by first use and freed by `CLOSE:`. **At most 4 devices
may be open in parallel** [6.1.17], with no restriction on the mix of input and
output. Exceeding that is an error, not a silent overrun.

#### Bi-directional devices and their synonyms [6.1.17]

Devices like the screen editor are bi-directional, and a program may want
concurrent reads and writes. The spec's answer is that `E`, `E:`, and `e:`
are **all valid ways of naming the same screen editor** — but:

> Note that each synonym is treated as a separate device by the PILOT I/O
> subsystem.

pyPILOT keys open files on the **exact** spec string, so this falls out
naturally and is worth a test: `E` and `e:` are two independent files.

#### End-of-file is not an error [6.1.17]

> End-of-file status is not considered to be an error, and will result in null
> data being read.

So `READ:` at EOF yields the **null string**, and the accept buffer becomes a
padded blank rather than raising. A program wanting its own end-of-file marker
must write one and `M:` against it — which is exactly what the spec's own
worked example does.

---

## 10. Decision log

Every place ATARI PILOT is ambiguous, silent, or hostile to a modern host gets
an explicit ruling here. Anything not in this log is a bug.

### 10.1 Corrections against the earlier Core PILOT draft

This table is the most important part of the document. An earlier draft
specified Core PILOT; the Atari sources contradict it on all of these. **The
Atari behaviour is normative.**

| # | This spec (ATARI) | The Core PILOT draft said | Source |
|---|---|---|---|
| 1 | Undefined string variable expands to **its own name** | expands to empty | [5.2.3] |
| 2 | Division **truncates toward zero**; `7/3 = 2` | rounds half away from zero | [5.1.7] |
| 3 | Modulo is **`\`** | `%` | [5.1.7] |
| 4 | 16-bit wrap, **not an error** | arbitrary precision | [5.1] |
| 5 | Exactly **26** numeric vars, `#A`–`#Z` | names up to 10 chars | [5.1.2] |
| 6 | String names up to **254** chars, case-sensitive | 10 chars, case-folded | [5.2.2] |
| 7 | `Y`/`N` + `(expr)` are **conjunctive** | exclusive | [4.4] |
| 8 | Duplicate labels **allowed**; lowest line wins | hard error | [4.2] |
| 9 | Continuation only after `T`/`Y`/`N`/`R` | after any command | [4.7] |
| 10 | **No operator precedence**; left to right | `*` before `+` | [5.1.7] |
| 11 | Modulo result is **always positive** | follows the dividend | [5.1.7] |
| 12 | `Y`/`N` are **abbreviations** for `TY`/`TN`, not commands | Core commands with a condition slot | [6.1.1] |
| 13 | `M:` is a **substring** search within the buffer | compares the whole buffer | [6.1.3] |
| 14 | A null `M:` field is a **null match** (matches anything) | no null-field rule | [6.1.3] |
| 15 | `?` is **literal text** in a text expression; random only in `nexp` | expands to a random number anywhere | [5.2.1, 5.1.3] |
| 16 | The accept buffer is **normalised** (padded, upper-cased, collapsed, 254) | stored verbatim | [7.2.2] |

Rows 13 and 14 were settled during Stage 5, and are the ones most likely to be
got wrong from Core PILOT intuition. The spec says `M:` *"scans the current
content of the accept buffer, trying to find an exact match with one of the Match
command fields"*, and calls `M:YE,SURE` *"a less precise matching of character
substrings within words"* — so the field is **located within** the buffer rather
than compared against it. A whole-buffer comparison would make `<right arrow>`
pointless, since there would be nothing to skip to. That is also why `M:YES` and
not `M: YES ` is the field a lesson writes, and why the manuals' `M: YES , YEAH ,
SURE_` form needs the blanks written out.

Row 14 comes from the spec's own three-row special-case table, which reads:

| Operand | Meaning |
|---|---|
| `M:` | Null operand is **not allowed** |
| `M:,` | **Will match anything (null match)** |
| `M:THIS,THAT,,OTHER` | **Will match anything (null match)** |

So a field list may not be empty, but a field *within* it may be — and an empty
field matches immediately, at its ordinal position. This is the idiomatic
"anything else" branch of a three-way match.

Row 15 is subtler and matters more than it looks. `?` is **absent** from §5.2.1's
list of the characters that may not be literals (`$`, `#`, `%`, `@`, `[`,
`<EOL>`), and §5.1.3 permits it only *"anywhere a numeric expression is
allowed"* — a text expression is not one. The spec's own examples depend on
this: `T:#X%, ARE YOU SURE?` needs the `?` to print, and so does the §6.1.4
worked example `A:=WHAT WILL HAPPEN?`, whose printed `$LEFT` of `'AT'` only
holds if the `?` is literal. Expanding `?` in a text operand silently corrupts
any accept buffer, message or match field containing a question mark.

The accept buffer's normalisation (row 16) is a related trap: it upper-cases,
so every match field in a lesson is written in upper case, and it pads, so the
buffer's leading and trailing blanks are real characters a field must account
for — which is what `<right arrow>` exists to step over.

### 10.2 Deviations from ATARI PILOT itself

These are places pyPILOT knowingly differs, each with its reason.

| Deviation | Rationale |
|---|---|
| Command names are matched case-**insensitively** | The Atari editor's stencil font made case hard to read and the manuals are inconsistent about it. Leniency here cannot break a working program. |
| `S` accepted as a synonym for `$` in accept operands | The spec's own examples use both [6.1.2]; accept both. |
| Device names map to host paths/streams | Atari's `C`/`D`/`S`/`K` have no host equivalent. Mapping is documented, not implicit (§9.6). |
| UTF-8 with a decode fallback chain | ATASCII is a 7-bit code. Modern lessons must round-trip; legacy files still load (§4.1). |
| 254-char buffers retained rather than lifted | Faithful. A 1980s lesson that overflows a buffer was already truncating on real hardware. |

### 10.3 Common PILOT is out of scope

`D:` arrays, `SA:`/`SM:` string arrays, floating point, multi-target `C:`
assignment, and `CS:`/`CN:` cursor control are **Common PILOT**, not ATARI PILOT
(§1.1). They remain outside the 1.0 scope; a future release could consider
them. `PCS:` is Atari's actual cursor command and is specified in §9.5.

### 10.4 `GR:` and `SO:` — optional host-backed devices

`GR:` and `SO:` are implemented through an optional interactive host. The
default package has no required runtime dependencies; the CLI lazily loads the
Pygame CE backend supplied by the `interactive` extra. An embedding application
may inject a different host. A headless `Interpreter` with no host raises an
actionable `PilotUnsupportedError` when a `GR:` or `SO:` statement executes.

Rev E's detailed graphics descriptions, cross-checked against the Student PILOT
Reference Guide, establish eleven `GR:` subcommands: `CLEAR`, `PEN`, `GOTO`,
`DRAWTO`, `FILLTO`, `TURNTO`, `GO`, `DRAW`, `FILL`, `TURN`, and `QUIT`. An older
runtime diagnostic table had fifteen unrelated names and omitted `GO`/`QUIT`;
that table was incorrect. `GR:` has its own semicolon/repeat operand grammar,
specified in the interactive-device draft and implemented by the graphics
engine. `%X`, `%Y`, `%A`, and `%Z` expose the active graphics state.
Host-safety limits cap repeat nesting at 16 and one `GR:` statement at
1,000,000 executed subcommands; exceeding either limit raises a source-aware
`PilotRuntimeError`.

`SO:` takes zero through four numeric constants or numeric variables, not an
`ON`/`OFF`/`PLAY`/`STOP` subcommand. An empty operand silences all voices. The
optional backend synthesizes up to four notes and refreshes variable-backed
voices after each PILOT statement. Atari memory-pointer sound sources remain
unsupported because rePILOT has no Atari memory model (§10.5).

The Pygame CE distribution is named `pygame-ce` and imported as `pygame`; it
MUST be an optional extra and MUST NOT be installed alongside the original
`pygame` distribution.

For CLI file runs, a window opened by graphics or controller input stays
visible after program completion until the user closes it. `A:` uses console
input until such a window is already open, then accepts input in the blue text
area. Closing during a run cancels execution and returns process status 130.
Library interpreters and REPL-run programs close injected hosts at the end of each run.

### 10.5 Hardware-dependent constructs

| Construct | Behaviour |
|---|---|
| Controller sense `%J`/`%P`/`%T` | The optional CLI host emulates two joysticks, two paddles, and their mapped triggers using keyboard input (§10.5.1). Headless runs and unmapped indices resolve to 0. |
| Lightpen sense `%H`/`%V`/`%L` | Resolve to 0; no lightpen is emulated. |
| Memory pointers `*«addr»` / `@B«addr»` | Raise `PilotUnsupportedError` — there is no Atari memory model to expose, and faking one would be worse than refusing. |
| `%F` free memory | Reports host-available memory, clearly documented as not a 6502 figure. |
| `?` random | Seedable per run for testability (§6.3). |

### 10.5.1 Keyboard controller map

When the Pygame CE host is enabled and focused, arrow keys emulate `%J0` and
W/A/S/D emulate `%J1`. Direction values use Atari's bit combinations: up 1,
down 2, left 4, right 8, and diagonals 5/9/6/10. Space and left Ctrl drive
`%T8`/`%T9`; Enter and right Ctrl drive `%T0`/`%T1`. Q/E adjust `%P0`, and
U/O adjust `%P1`, from 3 through 227 at a fixed rate. The paddles start at 115
and retain their values when no key is held. Focus loss releases held keys.
Other device indices and all lightpen values remain neutral (0). The mapping is
injectable through `ControllerKeyMap` on `KeyboardController` and
`PygameInteractiveDevice`; remapping host keys does not change Atari sense
values or PILOT syntax.

### 10.6 Core PILOT commands that do not exist here

These MUST be **syntax errors**, not accepted-and-ignored. Silently accepting
them would let a Core PILOT program appear to run while doing the wrong thing —
the worst possible failure for a teaching language.

| Not present | Notes |
|---|---|
| `L:` Link | ATARI has `LOAD:`. `L:` is a *label* definition, not a command. |
| `F`/`FA`/`FB`/`FC`/`FD`/`FO`/`FR`/`FW` | ATARI I/O is device-oriented: `READ`/`WRITE`/`CLOSE` (§9.6). No numeric handles. |
| `P:` Problem/Parameters, `W:«n»` width, `CS`/`CI` case toggles | Not Atari constructs. |
| `H` modifier on `T`/`A` | Not an Atari construct. |
| `@A`/`@M`/`@P` shorthand jumps | ATARI has `JM:` (§9.4). |
| `%MATCH`/`%LEFT`/`%RIGHT`/`%MAXUSES`/`%NEXTSTMT` | Atari specials are `%F`/`%M`/`%X`/`%Y`/`%A` (§6.6). Matched text comes from `MS:` (§7.5). |

`E:` with an operand **is** an error here, unlike the earlier draft's
forgiveness — [App. B] specifies a null operand.

### 10.7 Commands that parse but are refused

`CALL:`, `TAPE:`, `TSYNC:`, and `DOS:` parse and raise
`PilotUnsupportedError`. They reach into Atari hardware, cassette, or the host
OS. `DOS:` in particular is an arbitrary-code-execution surface with no place
in an interpreter aimed at children; refusing it is a deliberate safety
decision, not a missing feature.

### 10.8 Immediate mode

ATARI PILOT is an interpreter with an interactive immediate mode, and the
`[I]`-marked commands in §9.1 exist only there (`RUN`, `LIST`, `NEW`, `AUTO`,
`REN`, `SAVE`, `DOS`). pyPILOT's REPL implements `LIST`, `RUN`, `NEW`, `AUTO`,
`REN`, `LOAD`, `SAVE`, `DUMP`, `VNEW`, `TRACE`, and `QUIT` (also `EXIT`).
`AUTO` assigns line numbers as statements are entered; a full-screen editor is
not provided.

A command that is immediate-mode-only, used in a run-mode program, is a
`PilotRuntimeError` naming the line — not a parse error, since the same text is
valid at the REPL.

---

## 11. Implementation history

Every stage ends with a green test suite and a runnable program. **No stage may
merge with a red test.**

### Stage 0 — Modernise *(complete)*

uv, src-layout, `pyproject.toml`, `uv.lock`, ruff, mypy strict, pytest, CI,
working docs, real tests.

**Done:** 55 tests, 98% coverage, lint/types/build/docs all green.

### Stage 1 — Lexer and `Statement` *(complete)*

**Delivered** `syntax.py`: `Statement`, `Condition`, `Parser`, `Program`, plus
the `CommandName` vocabulary. Handles line numbers (§4.1), labels of any length
sharing a line with a command (§4.2), the `[` comment (§4.2), combined
conditions (§4.2), comma/blank field delimiting (§4.3), and continuation after
`T`/`Y`/`N`/`R` only (§4.4). The label index is built at parse time, first
writer wins, no duplicate diagnosis (§8.1).

**Acceptance met.** `TYPEN:` is rejected rather than truncated, and a
continuation after `C:` is a parse-time error — both required by §4.2/§4.4 and
both tested.

**Also delivered:** `pypilot --check prog.pilot` and `--list`, which parse and
report a program without running it. The Core PILOT rejections of §10.6 are
implemented, with each error naming the ATARI equivalent.

**Three findings from the build**, now recorded in the spec:

1. **Command names run to five letters** (`TSYNC`), not two. The scanner takes
   the longest *known* name, so `CN:` is rejected as the Core PILOT cursor
   command rather than silently resolving to `C` plus junk.
2. **`TY:`/`TN:` are genuinely ambiguous** — both a spelling of `Y:`/`N:` and
   the general form `T` with a `Y`/`N` condition. Resolved as the general form,
   which carries strictly more information (§4.4, §7.3).
3. **A literal `[` cannot be typed in any operand** — it is an unconditional
   comment delimiter with no escape. See §4.5. This is authentic and a genuine
   wart; it is documented so nothing tries to print one.

### Stage 2 — State, values, and text expressions *(complete)*

**Delivered** `state.py` and `values.py`: the 26-slot numeric store, the string
table, `expand_text`, the 16-bit `Numeric` type, accept-buffer normalisation,
the match ordinal, the module call stack, and a seedable `?`.

**Acceptance met.** All four rules called out as easiest to get wrong are
covered and pinned:

| Rule | Test |
|---|---|
| Undefined string expands to its own name (§6.1) | `test_undefined_expands_to_its_own_name` |
| Null is a distinct state from undefined (§6.1) | `test_undefined_and_null_are_different_states` |
| Expansion is single-pass (§6.5) | `test_expansion_is_single_pass_against_state` |
| Text truncates at 254 silently (§6.5) | `test_expansion_truncates_at_254_silently` |
| `\` is modulo, `%` is a variable sigil (§6.2) | `test_modulo_takes_the_sign_of_the_dividend` |

**Verified against the Atari sources, not against Python.** The division and
modulo tests are the ones that matter most: ``-7/3`` is ``-2`` (truncation, not
Python's ``-3``), and ``-7\3`` is ``-1`` (the remainder follows the *dividend*).
The indirection tests reproduce spec 5.2.4's own worked example - ``$LADDER`` →
``JANE``, ``$$LADDER`` → ``ATARI``, ``$$$LADDER`` → ``LUNCH``.

**One correction found by the build.** Memory pointers (`*addr`, `@Baddr`) are
a *numeric* construct - spec 5.1.6 says "a pointer may be used anywhere a
numeric variable is allowed" - so they must stay **literal** in a text
expression. An earlier draft scanned them as references, which made `5*6` lose
its multiplication sign entirely. They are Stage 3's problem, not this stage's.

### Stage 3 — Expression evaluation *(complete)*

**Delivered** `expressions.py`: the `nexp` evaluator, a tokeniser, and
`ExpressionError`. `PilotState.evaluate()` wires it to the variable store,
specials, controller sense, and the seeded random source. v0.4.0.

#### Two further corrections to this document, found in §5.1.7

**There is no operator precedence.** Spec 5.1.7: *"Numeric expressions are
evaluated from left to right, with no operator precedence rules; parentheses
are allowed (encouraged?) to either clarify the formulae or to alter the left to
right evaluation scheme."* So `1+2*3` is **9**, not 7, and `10-2-3` is **5**,
not 11. The earlier draft of §6.2 in this document specified the usual
precedence and was wrong.

**The remainder is always positive.** Spec 5.1.7 calls `\` *"the modulus
operator (result is always positive)"*, so `-7\3` is **1**, not `-1`. The
earlier draft said the remainder followed the dividend, and
`values.Numeric.__mod__` implemented that; both are now corrected.

**Parentheses are limited, but only useful ones count.** Spec 5.1.7: *"Any
number of redundant parens are allowed (those that don't alter the evaluation
order) and up to 2 levels of nested non-redundant parens are allowed."* So
`((((1))))` is fine at any depth, while three levels of `(1+1)` is an error.

**Acceptance met.** §6.2 is covered, and the Primer's own worked examples
(p.85) all reproduce: `7/3=2`, `7\3=1`, `5/4=1`, `5\4=1`, `10/5=2`, `10\5=0`,
`99/12=8`, `99\12=3`.

Memory pointers (`*addr`, `@Baddr`) are **parsed and then refused** with
`ExpressionError` naming spec 10.5, which is what §10.5 requires. §5.1.6's
worked example — `C:#A=@@B4096` is valid, `@@@B4096` is not — is not
reproduced, because pyPILOT has no Atari memory to address; refusing is
recorded as a deliberate deviation.

### Stage 4 — Core statements `T R C` *(complete)*

**Delivered** `io.py` (device protocols, console/buffer implementations),
`runtime.py` (`Interpreter`, dispatch loop, conjunctive conditions, trace
hook), and the `T`/`R`/`C` handlers in `core.py`. `pypilot prog.pilot` now
**runs** a program, and `--trace` reports each statement to stderr. v0.5.0.

**Acceptance met.** A program using only `T`/`R`/`C` runs end to end, and an
undefined variable prints its own name.

**One further correction, from §6.1.1.** Spec 6.1.1: *"There are two alternate
names provided for the Type command: `Y` is an abbreviation for `TY` and `N` is
an abbreviation for `TN`."* So `Y` and `N` are **not commands with a condition
slot** - they are alternative spellings of the whole statement, and the earlier
draft of this document listed them as Core commands.

That distinction matters. `N(#A>0):` is `T` with a `N` match flag **and** a
`#A>0` expression, conjunctive per §4.4. Had `N` been a command with its own
condition field, the expression would have been orphaned into the operand and
the conjunction lost.

The spec also notes that `YY`, `YN`, `NN` and `NY` are *"syntactically proper"*
- `YY` redundant, `YN` never executing. All four are accepted, because rejecting
them would fail a program a real Atari runs. The **second** letter is the
condition, which is what makes `YN` never execute: type-if-match *and*
if-no-match cannot both hold.

`Y` and `N` therefore have no entry in `PilotCore.DISPATCH`: the parser folds
every one of those spellings into `T` plus a match condition before dispatch.

### Stage 5 — `A`, `M`, and `MS` ✓ v0.6.0

**Delivered** `_a`, `_m`, `_ms`, the accept buffer and its **normalisation**
(§7.2.2), `A:=` buffer assignment, the match ordinal, `<right arrow>`
skipping, the `Y`/`N` condition machinery, and `match.py` holding the field
splitting and the buffer scan.

**Accepted** — the §13.1 tutorial runs against a scripted input device, and
`examples/msplit.pilot` reproduces the spec's stated `$LEFT`/`$MATCH`/`$RIGHT`
values exactly.

Two spec findings from this stage are recorded in §10.1:

- `M:` is a **substring** search, not a whole-buffer comparison (§7.4). The
  spec's own §6.1.3 wording — *"scans the current content of the accept
  buffer, trying to find an exact match with one of the Match command
  fields"* — plus its call of `M:YE,SURE` a *"less precise matching of
  character substrings within words"*, settles it. A null field is a **null
  match**, and the spec's three-row special-case table makes `M:,` one.
- `?` is **literal text** in a text expression (§6.3), not a random draw. It is
  absent from §5.2.1's list of characters that cannot be literals, and §5.1.3
  permits it only *"anywhere a numeric expression is allowed"*. This is what
  makes the §6.1.4 worked example runnable at all: `A:=WHAT WILL HAPPEN?`
  would otherwise put a random number in the accept buffer.

### Stage 6 — Control flow `J U E JM` ✓ v0.7.0

**Delivered** `_j`, `_u`, `_e`, `_jm`, the label table (first writer wins, **no**
duplicate detection [4.2]), and the module call stack.

**Acceptance criteria:** recursive modules work to the configured depth limit, a
duplicate label resolves to the lowest line number, and an undefined label
produces a clear error naming the line.

**A note on the depth limit.** The Atari allows **8** nested `U:`s [6.1.9], and
pyPILOT keeps that number rather than using a host-sized one. It is not
arbitrary: the 6502 had 256 bytes of variable space, so a lesson nesting deeper
than 8 was using more stack than a real Atari allowed, and reporting that as an
error is the faithful behaviour.

**`E:` is one statement with two outcomes** [6.1.10]: return to the statement
after the most recent `U:`, *or* stop the program when no return is stacked.
There is no separate module-end command.

**A run cannot be infinite.** `J:` makes an accidental loop a one-character
slip, and a language that hangs teaches nothing, so the interpreter gives up
after `MAX_STEPS` with a message naming the limit. This is pyPILOT's own
addition, not an Atari rule — recorded in §10.2.

### 6.1.10 `E:` may be conditional — and *any* command may

Spec 6.1.10 says of `E:`: *"This command, as all others, may be conditional"*,
and gives `EY:` and `EN:` as the End command's own examples. So:

```pilot
C:#A=1
E(#A>0):      ← legal, and ends the program
E(#A>0):TEXT  ← a syntax error; <end operand> ::= <null>
```

The condition goes **before** the colon; the operand slot after it stays empty.
`EY:`/`EN:` are the same statement spelled with the match flag in the command
position, exactly as `TY:`/`TN:` are for `T` [6.1.1].

This generalises: **any** command may carry a `Y`/`N` condition [4.2], not just
`T`. `MY:#A` is `M:` conditional on a match, `EA:` is a conditional `E:`. The
parser resolves a two-letter run as *command + condition* only when the second
letter is `Y` or `N` **and** the pair is not a rejected Core PILOT command —
`EY:` is `E` plus a condition, while `CN:` is the rejected cursor command and
must never be mistaken for `C` plus an `N` condition.

### Stage 7 — I/O devices and utilities ✓ v0.8.0

**Delivered** `devices.py` (`READ`/`WRITE`/`CLOSE`/`LOAD`/`SAVE`) with the
documented host mapping, plus `_vnew`, `_dump`, `_pa`, `_pcs`, `_trace`. Every
run-mode command is now implemented; `PENDING_STAGES` is empty.

**Accepted** — the device mapping is documented in `docs/language.rst`, and
`LOAD:` preserves the environment as §6.1.21 requires.

Two spec findings from this stage:

- **Open files live in the string table** [6.1.17]. Each open device is a
  string named `@«spec»` holding its IOCB slot character, and *"clearing the
  string variables using the VNEW command has the effect of closing all
  files"*. pyPILOT models it the same way, so `VNEW:$` closes every file and
  `DUMP:` shows the open devices — both fall out rather than being special-cased.
- **`LOAD:` preserves the environment.** §6.1.21 says a run-mode load executes
  the new program *"without any initialization of the program environment,
  except that the Use stack is cleared"*. An earlier draft of this document said
  `LOAD:` **discards** the accept buffer, which is the opposite; that is
  corrected in §8.5. `PilotState.reset()` (what `RUN:` does) and
  `PilotState.clear_call_stack()` (what `LOAD:` does) are now separate methods
  so the two cannot be confused again.

Four I/O rules are easy to get wrong and each is pinned by a test: open on first
use (there is no `OPEN`), at most four open, end-of-file is **not** an error
but yields the null string, and device synonyms are *separate* devices.

### 9.7 Immediate mode

Immediate mode is the *other* half of PILOT: the REPL where a statement is
typed and executed at once, and where the deferred program area is edited.
The two modes share a parser but differ in what commands mean (§6.2).

#### The colon is optional in immediate mode [6.2]

> For the immediate mode only commands, the condition field delimiter (`:`) may
> be omitted if desired. Thus, for example, either `RUN` or `RUN:` will be
> accepted as a legal form of the Run command. In addition, the following
> run/immediate mode commands have this same feature: **TRACE, VNEW, DUMP and
> LOAD**.

So the colon is optional for **every** immediate-mode command, and for those
four even in a stored program. `RUN` and `RUN:` are the same statement, and so
are `TRACE` and `TRACE:`.

#### `AUTO` — auto-numbered input mode [6.2.6]

Enters a mode where each statement typed is appended to the deferred program
with a generated line number.

```
<auto operands> ::= [<line#> [<sep><increment>]]
```

- Both operands default to **10**. `AUTO` alone starts at 10, step 10.
- An **empty line** terminates the mode, and so does an out-of-range line
  number. Both return to immediate mode.
- A statement with a syntax error is **not** stored; the mode continues.

#### `REN` — renumber [6.2.7]

Renumbers the stored program. Operands are the same shape as `AUTO` and default
the same way.

- The program is **never reorganised** by `REN`; only the numbers change. So a
  line-number overflow stops the process with the program still intact and
  correctable by renumbering again with different operands.
- Line numbers outside 0–9999 are an error that **stops** the process. This is
  why the program is not reorganised: a partial renumber is recoverable, and a
  partial *reorder* would not be.

#### `NEW` [6.2.5]

Deletes the deferred program, removes **all** string variables, **zeroes** the
numeric variables, and clears the Use stack. Note it zeroes rather than
undefines the numerics — a different end state from `VNEW:#`, which clears the
store so a later read reports "undefined".

#### `LIST` [6.2.1]

Prints the deferred program, optionally a line range. The delimiters are
**blanks**, not commas — `LIST 100 200` lists lines 100 through 200, and
`LIST 100 , 200` is the same statement (§4.5).

### Stage 8 — CLI and REPL ✓ v0.9.0

**Delivered** `helpers.Shell` (`list`/`run`/`clear`/`new`/`auto`/`renumber`)
and the interactive loop in `cli.py`, with immediate-mode parsing.

**Accepted** — §12's CLI criteria pass.

### Stage 9 — Refused commands, examples, docs ✓ v0.10.0

**Delivered** sub-command-naming refusals for `GR:`/`SO:` (§10.4), the optional
colon in immediate mode (§6.2), example *execution* tests, a generated README
session, and a fully current README.

**Accepted** — every example runs under CI, `GR:` fails with a message naming
the sub-command, and docs build warning-free.

Two things the audit turned up, both of which had been hiding behind a
passing suite:

- **The refusals did not name the sub-command** (§12 requires it). `GR:` said
  only "is real ATARI PILOT but is not implemented", which leaves a learner
  wondering whether they mistyped it. It now says *"is real ATARI PILOT,
  specifically its sub-command DRAWTO, but this host cannot honour it"* — and
  says **refused**, not "not implemented yet", because nothing is ever going to
  arrive. An unrecognised sub-command is not guessed at.
- **`summary.pilot` re-entered its own module.** Its `E:` returned to the
  statement after the `U:`, which then fell straight back into the module and
  called it again. It parsed perfectly and *listed* perfectly; it just did the
  wrong thing. The fix is a `J:` past the returning `E:`, and the reason is now
  a comment in the example itself — this is the single most common module bug
  and nothing in the prose had said so.

The second is why the corpus now has **execution** tests rather than only
static ones. A program that parses and then misbehaves is worse than one that
fails to parse, because a listing looks fine.

### Stage 10 — 1.0 ✓ v1.0.0

**Delivered** release packaging: 1.0.0 metadata, a `CHANGELOG.md`, a CI matrix
that verifies the *built wheel* rather than just the source tree, and a
packaging test suite that looks inside the distributions.

**Three real defects this stage found**, none of which the test suite could see:

- **The author email was `me@grandrobertson.com.com`** — a doubled suffix, in
  the metadata of every release up to and including 0.10.0.
- **A leftover `.venv-wheel` was packed into the sdist.** Found by the new test
  within one run of it being written.
- **The classifier still said `3 - Alpha`** on a release that was about to be
  called stable.

`tests/test_packaging.py` builds a *real* sdist and wheel and inspects the
archives, because reading the metadata cannot tell you what hatchling actually
packed.

The clean-environment wheel install that §12 has always required is now
performed by CI on every matrix entry, and was run by hand here: the wheel
installs, reports `pypilot 1.0.0`, runs a program, exits 0, and pulls in
**zero** third-party packages.

### Stage 11 — Optional interactive devices *(complete, 1.1.0)*

**Delivered** `graphics.py`, `interactive.py`, and the optional Pygame CE host
in `pygame_backend.py`. `GR:` executes the eleven documented Rev E subcommands;
`SO:` drives up to four synthesized voices; keyboard input provides two virtual
joysticks, triggers, and two paddles. `%X`/`%Y`/`%A`/`%Z` report active graphics
state. The CLI and REPL create the host lazily, while direct `Interpreter` and
`Repl` use remains headless unless a host is injected.

The Pygame CE dependency is an `interactive` extra. The default dependency list
remains empty. The obsolete refusal inventory was corrected against the
checked-in Rev E and Student Guide: `GO` and `QUIT` are supported, and the
former 15-name table was not the authoritative command list.

Graphics/input/audio semantics are tested with an injected recording host. A
separate SDL dummy-driver smoke test initializes the real display and mixer,
plots and senses a color, and starts four voices.

---

## 12. Definition of done (1.0 base and interactive extension)

### Language conformance

Every item is a test that exists, or a test that exists to prove a thing is
*absent*.

**Core statements**

- [x] All nine Core commands (`A R C T Y N M J U E`) behave as §7 and §9
      specify.
- [x] `A:` honours its **normalisation**: leading and trailing space added,
      upper-cased, runs of spaces collapsed, truncated at 254 (§7.2.2).
- [x] `A:=«texp»` assigns to the buffer without prompting (§7.2.1).
- [x] Numeric accept never errors; non-numeric input yields 0 (§7.2).
- [x] Null string and undefined string are distinguishable, and only the
      latter prints its own name (§6.1).
- [x] `M:` is a **substring** search within the buffer, not a whole-buffer
      comparison (§7.4). Stage 5 reversed an earlier reading of this item;
      see §10.1 row 13.
- [x] Comma and leading-`|` field separators both work, and never together
      (§7.4).
- [x] The match ordinal is the field number, is exposed as `%M`, and drives
      `JM:` (§6.6, §9.4).
- [x] An empty `M:` field is a null match that matches anything; a null
      `M:` operand is a syntax error (§7.4).
- [x] `MS:` sets `$LEFT`/`$MATCH`/`$RIGHT`, and on failure **retains** their
      prior values (§7.5).

**Values**

- [x] An undefined string variable expands to **its own name** (§6.1).
- [x] Division truncates toward zero on both signs; `\` is modulo and its
      result is **always positive** (§6.2, §10.1 row 11).
- [x] Arithmetic wraps at 16 bits and wrap is **not** an error (§6.2).
- [x] Exactly 26 numeric variables; `#XY` is rejected (§6.1).
- [x] Text expressions truncate at 254 silently; `_` yields a trailing blank
      (§6.5).
- [x] Expansion is single-pass (§6.5).
- [x] String indirection `$$ABC` works, and resolves through undefined levels
      to the substituted name (§6.4).

**Structure**

- [x] A label may share a line with a command; labels are any length (§4.2).
- [x] Duplicate labels are **allowed**; the lowest line number wins (§8.1).
- [x] Continuation works after `T`/`Y`/`N`/`R` and is an **error** after
      anything else (§4.4).
- [x] Commas and blanks are interchangeable as operand separators (§4.3).
- [x] Comments are `[`…EOL; a `//` comment is literal text (§4.2).
- [x] `MYCOMMAND:` is rejected, not truncated to `MY` (§4.2).
- [x] `Y`/`N` combined with `(expr)` is **conjunctive** (§4.4).
- [x] Recursive `U:` works and the depth limit produces a PILOT error (§8.3).
- [x] `@A`/`@M`/`@P` shorthand jumps are rejected (§10.6).
- [x] `L:` is a label, not a Link command (§10.6).

**Interactive devices**

- [x] `GR:` implements all eleven verified Rev E commands, its repeat grammar,
  and `%X`/`%Y`/`%A`/`%Z` (`test_graphics_repeat_draws_closed_square_and_updates_specials`).
- [x] Deep repeat nesting and excessive sub-command execution fail with
  source-aware errors (`test_graphics_repeat_nesting_is_bounded`,
  `test_graphics_operation_count_is_bounded`).
- [x] The CLI uses a native Pygame CE window with black graphics and a blue
  lower text area; the SDL dummy smoke test covers drawing, color sense, and
  audio initialization (`test_pygame_backend_smoke_with_sdl_dummy_devices`).
- [x] Keyboard input implements Atari joystick directions/diagonals, paddle
  ranges, triggers, and focus release (`test_keyboard_controller_maps_joystick_directions_and_diagonals`,
  `test_keyboard_controller_paddles_move_clamp_and_retain_position`).
- [x] `SO:` has four variable-backed voices, updates after statements, and an
  empty operand silences (`test_runtime_refreshes_sound_sources_after_each_statement`).
- [x] Closing the interactive window cancels the CLI run with status 130
  (`test_cli_returns_130_when_interactive_host_is_cancelled`).
- [x] The base install remains lazy and dependency-free; Pygame CE is opt-in
  (`test_pygame_backend_stays_lazy_until_interactive_use`).

**Hardware refusals**

- [x] `CALL:`/`TAPE:`/`TSYNC:`/`DOS:` parse and raise
      `PilotUnsupportedError` (§10.7).
- [x] Core-PILOT-only commands (`F` family, `P:`, `W:`, `H` modifier) are
      **syntax errors**, not silently ignored (§10.6).

### Engineering

- [x] `uv run pytest` passes; ≥ 90% branch coverage on `src/pypilot`.
- [x] `uv run ruff check .` and `uv run ruff format --check .` pass.
- [x] `uv run mypy` passes under `strict`.
- [x] `uv build` produces a valid sdist and wheel; the wheel installs into a
      clean environment and `pypilot --version` works. Verified by hand and now
      by CI on every matrix entry.
- [x] Zero third-party runtime dependencies. `uv pip list` in a clean venv
  containing only the base wheel shows only rePILOT; Pygame CE is in the
  optional `interactive` extra (`test_pygame_ce_is_only_in_the_interactive_extra`).
- [x] Full CI matrix green on Linux, Windows, and macOS. The workflow runs
      pytest, ruff, ruff-format, mypy, a zero-dependency metadata check, a clean
      wheel install, `uv build`, and a `-W` docs build on 3 OSes × 2 Pythons.
- [x] Docs build with zero warnings. CI uses `-W`, so a warning fails the build
      exactly as it fails locally.

### CLI

- [x] `pypilot prog.pilot` runs a program and exits 0.
- [x] `pypilot` with no arguments starts a REPL; `LIST`, `RUN`, `NEW`, `AUTO`,
      `REN`, `LOAD`, `SAVE`, `DUMP`, `VNEW`, `TRACE`, and `QUIT` work.
- [x] A runtime error reports the program line number and echoes the source
      line.
- [x] `--trace` prints each statement as it executes.
- [x] Exit codes: 0 success, 1 program/runtime error, 2 usage error, 130 user
  cancellation from the interactive window.

### Documentation

- [x] `docs/language.rst` matches the implemented behaviour.
- [x] `README.md` shows a working example session, generated from a real run by
      `tools/readme_session.py` rather than typed by hand.
- [x] Every deviation in §10 is justified in writing.

---

## 13. Reference programs

These are the acceptance corpus. Each lives in `examples/`, runs under CI, and
doubles as documentation. All of them use **upper-case text** where they match
against the accept buffer, because the buffer is normalised to upper case
(§7.2.2), and **single-letter** numeric variables, because there are only 26
(§6.1).

### 13.1 `examples/greeter.pilot` — the canonical tutorial

Exercises `T`, `A` string, `M`, `Y`/`N`, and variable expansion.

```pilot
R:Ask the learner their name and greet them
T:WHAT IS YOUR NAME?
A:$NAME
T:HELLO, $NAME.

R:Then try a match against their answer
T:ARE YOU A STUDENT? (YES OR NO)
A:$ANSWER
M:YES,Y
TN:NO,N
T:WELCOME TO THE COURSE.
T:NO PROBLEM - COME BACK ANY TIME.
E:
```

### 13.2 `examples/numbers.pilot` — arithmetic

Exercises `A` numeric, `C` numeric with precedence, **truncating** division,
backslash modulo, and conditional expressions.

```pilot
R:Demonstrate numeric accept, arithmetic, and conditional expressions
T:ENTER TWO NUMBERS AND I WILL REPORT THEIR SUM AND MEAN.
T:FIRST NUMBER:
A:#X
T:SECOND NUMBER:
A:#Y
C:#S=#X+#Y
C:#Q=#S/2
C:#R=#S\2
T:SUM IS #S.
T:HALF OF THE SUM IS #Q.
T:REMAINDER OF THE SUM DIVIDED BY TWO IS #R.
T(#S>100):THAT IS A BIG SUM.
T(#S<=100):THAT IS A SMALL SUM.
E:
```

> `#S/2` truncates, so a sum of 7 gives `3`, not `4` — and `#S\2` gives `1`
> (§6.2). This example exists partly to pin that.

### 13.3 `examples/adventure.pilot` — modules, loops, and `JM:`

Exercises `*` labels, `J:`, `U:`, `E:`, `M:`, and `JM:` multi-way branching
(§9.4).

```pilot
R:A tiny choose-your-own-adventure demonstrating control flow
*START
T:YOU ARE AT A CROSSROADS. WHICH WAY? (NORTH OR SOUTH)
A:$CHOICE
M:NORTH,SOUTH
JM:*NORTH,*SOUTH
T:THAT IS NOT A DIRECTION I KNOW.
J:*START

*NORTH
U:*DESCRIBE
T:YOU WALK NORTH INTO A COLD DARK FOREST.
J:*END

*SOUTH
U:*DESCRIBE
T:YOU WALK SOUTH TOWARD A WARM NOISY RIVER.
J:*END

*DESCRIBE
T:YOU PAUSE AND LISTEN.
E:

*END
T:THE END
E:
```

### 13.4 `examples/msplit.pilot` — `MS:` and the two string states

Exercises `A:=` buffer synthesis, `MS:` decomposition with `<right arrow>`
skipping, and both string states. The expected output is the spec's own worked
example [6.1.4], which makes this the sharpest test in the corpus.

Note the `<right arrow>` bytes: three of them, written `\x1e`. They are
invisible in an editor, so the file is the source of truth for this example.

```pilot
R:MS: splits the accept buffer into $LEFT, $MATCH and $RIGHT
R:The expected output is the worked example from Atari spec 6.1.4.
A:=WHAT WILL HAPPEN?
MS:»»»_
T:LEFT IS  $LEFT
T:MATCH IS $MATCH
T:RIGHT IS $RIGHT

R:An undefined string variable prints its own name (spec 6.1):
T:UNDEFINED MEANS $UNSET

R:A null one prints nothing at all, which is a different state (spec 6.1):
C:$NULLED=
T:NULL IS $NULLED.
```

Expected output:

```text
LEFT IS  AT
MATCH IS
RIGHT IS WILL HAPPEN?
UNDEFINED MEANS UNSET
NULL IS .
```

The `?` in the accept text is load-bearing: it is literal in a text expression
(§6.3, §10.1 row 15), so the buffer really does end in a question mark and
`$RIGHT` really does carry it. Expand `?` as a random number and this example
prints nonsense — which is how the bug was found.

Expected output:

```
LEFT IS [ THIS ]
MATCH IS [IS]
RIGHT IS [ A TEST.]
[UNSET]
```

The last line is the §6.1 rule, and the leading/trailing spaces in the first
three are the §7.2.2 buffer normalisation.

### 13.5 `examples/recurse.pilot` — modules and recursion

Exercises nested `U:` and the module depth limit.

```pilot
R:Demonstrate nested module use
C:#D=0
U:*COUNT
T:COMPLETED AT DEPTH #D.
E:

*COUNT
C:#D=#D+1
T(#D<3):GOING DEEPER...
T(#D>=3):BOTTOM REACHED.
J:*COUNT
E:
```

### 13.6 `examples/graphics.pilot` — turtle graphics

Exercises `CLEAR`, Cartesian positioning, turtle movement, iteration, and the
graphics special variables. Running it from the CLI requires the optional
interactive extra; tests use an injected recording host.

```pilot
R:Draw a square with the ATARI PILOT turtle graphics command.
GR:CLEAR
GR:GOTO 0,0;TURNTO 0;4(DRAW 15;TURN 90)
T:SQUARE COMPLETE AT (%X,%Y)
E:
```

### 13.7 `examples/controls.pilot` — keyboard controllers

Polls the two virtual joysticks and paddle values and exits when `%T8` (Space)
is pressed. The CLI's optional Pygame host maps arrows to `%J0`, WASD to `%J1`,
and Q/E and U/O to paddles `%P0`/`%P1`.

### 13.8 `examples/sound.pilot` — four-voice sound

Selects four variable-backed notes with `SO:`, changes one voice while the
program runs, then silences all voices with an empty `SO:` operand.

### 13.9 `examples/summary.pilot` — the language overview

The language overview example, which the README shows. It uses `T`, `R`, and
`C` to demonstrate truncating division, backslash modulo, absent operator
precedence, and undefined-name substitution.

```pilot
C:#S=2+3
C:#H=#S/2
C:#R=#S\2
C:$GREETING=HELLO, WORLD

T:$GREETING
T:THE SUM OF TWO AND THREE IS #S.
T:HALF OF IT, TRUNCATED, IS #H.
T:AND THE REMAINDER IS #R.
T:
T:AN UNDEFINED STRING PRINTS ITS OWN NAME:
T:  $NOT_SET_ANYWHERE
```

Expected output:

```
HELLO, WORLD
THE SUM OF TWO AND THREE IS 5.
HALF OF IT, TRUNCATED, IS 2.
AND THE REMAINDER IS 1.

AN UNDEFINED STRING PRINTS ITS OWN NAME:
  NOT_SET_ANYWHERE
```

---

### 13.10 `examples/turtle-triangle.pilot` — colored polygon

Draws a red equilateral triangle with a three-iteration `DRAW`/`TURN` group.
The turtle returns to its starting point and reports `%X`/`%Y`.

### 13.11 `examples/turtle-spiral.pilot` — variable-length spiral

Uses a labeled `J:` loop to increase the `DRAW` distance between turns, making
the relationship between PILOT control flow and live turtle movement visible.

### 13.12 `examples/turtle-star.pilot` — repeated heading changes

Traces a yellow five-point star with five equal strokes and a 144-degree turn
after each stroke.

## 14. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Wrong dialect** — an earlier draft specified Core PILOT and was wrong on nine points | **Severe** | Fixed. The ATARI sources are now normative (§1), §10.1 records every correction, and `history/` holds the primary documents so the ruling can be re-checked rather than trusted. |
| OCR error in the Atari sources | High | The External Specification has an Internet Archive OCR layer, not one we produced. The two manuals we OCR'd locally have a **stencil-font caveat** on command letters, documented in `history/README.md`. Command letters are always cross-checked against the specification, never the manuals. |
| Silent acceptance of Core PILOT syntax | High | §10.6 requires those commands be **syntax errors**. Accepting-and-ignoring would let a wrong-dialect program appear to run — the worst failure for a teaching language. |
| Subtle numeric differences (truncation, wrap, `\` vs `%`) | High | Each is a named acceptance test in §12, with worked values from the Primer. |
| The accept-buffer normalisation is easy to under-implement | Medium | Specified as an explicit ordered list (§7.2.2) and pinned by the `msplit.pilot` expected output. |
| Scope creep toward Common PILOT or physical Atari hardware | Medium | §1.1 and §10.3. Graphics, sound, and keyboard controller emulation are explicitly bounded optional devices; physical hardware and arbitrary memory access remain out of scope. |
| The parser grows without bound | Medium | Operands stay unparsed (§5.1); each handler parses only what it needs. |
| Recursion blows the Python stack | Low | `PilotMaxUses` raises a PILOT-level error. |
| `uv.lock` drift | Low | `UV_FROZEN=1` in CI; `cache-dependency-glob`. |
| 7-bit ATASCII sources | Medium | §4.1 requires a decode fallback chain, tested with a non-UTF-8 fixture. |

---

## 15. References

**Normative — the source of truth for every semantic ruling in this document:**

- **Atari PILOT External Specification, Revision E**, 27-Oct-1980, by
  **Harry B. Stewart** (Atari). Atari's own PILOT implementer; written for
  Atari engineers. → [`history/manuals/`](history/README.md) ·
  <https://archive.org/details/Atari_Pilot_External_Specification_Revision-E>

**Supporting Atari manuals (secondary, used to confirm and to date intent):**

- *Atari Student PILOT Reference Guide*, Atari, 1981. →
  [`history/manuals/`](history/README.md)
- *The PILOT Programming Language Instruction Manual* ("Pilot Primer"), Atari,
  Educators Package. A ten-section course; the source of the worked arithmetic
  examples in §6.2. → [`history/manuals/`](history/README.md)

**Background and lineage:**

- Wikipedia, *PILOT* — <https://en.wikipedia.org/wiki/PILOT>
- EDM2, *PILOT* — <https://www.edm2.com/index.php/PILOT> — the source of the
  Common-PILOT-versus-Atari lineage quoted in §1.1
- EDM2, *RPilot* — <https://www.edm2.com/index.php/RPilot>

**Deliberately *not* normative:**

- IEEE Std 1154-1991 — withdrawn and paywalled. Describes Core PILOT, which is
  *not* this project's target. Retained only as the origin of the divergences
  catalogued in §10.1.
- Starkweather, *PILOT-73 Guide* (1974) and *A User's Guide to PILOT* (1985);
  Kheriaty & Gerhold, *COMMON PILOT Language Reference Manual* (1980) — none
  available online, and the last is out of scope by §1.1.
- FreeTrav, *psPILOT* — <https://github.com/FreeTrav/psPILOT> — an
  implementation of **Core** PILOT, not Atari. Useful as a description of the
  Core dialect this project is *distinguishing itself from*, and as a
  cross-check on where implementations disagree. Not normative.
