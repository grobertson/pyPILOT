# Changelog

All notable changes to pyPILOT are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project uses [semantic versioning](https://semver.org/spec/v2.0.0.html)
with a twist that matters here: **the language is pinned to ATARI PILOT**, so a
"patch" that changes a semantic rule is not a patch. Anything touching
`SPEC.md` §6–§9 is a minor bump at minimum.

## 1.0.0 — 2026-09-26

First stable release. Every run-mode command in the Atari vocabulary is
implemented; the two device-dependent ones are specified and refused.

### The language

A complete ATARI PILOT interpreter, per the *Atari PILOT External
Specification, Revision E* (27-Oct-1980, Harry B. Stewart).

- **Core statements** — `A` `C` `E` `J` `M` `R` `T` `U`, with `Y`/`N` and every
  `TY`/`TN`/`YY`/`YN`/`NN`/`NY` spelling folded into `T` plus a conjunctive
  match condition (spec 6.1.1, 4.4).
- **Atari language extensions** — `MS:` (match producing `$LEFT`/`$MATCH`/
  `$RIGHT`) and `JM:` (jump on the match ordinal).
- **Control flow** — recursive modules with the Atari's own depth limit of **8**
  (spec 6.1.9), conditional jumps, and `E:` as a single statement with two
  outcomes (spec 6.1.10).
- **I/O** — device-oriented, with no numeric file handles. `READ:` `WRITE:`
  `CLOSE:` `LOAD:` `SAVE:` over `C` `D` `E` `K` `P` `S` (spec 6.1.17).
- **Utilities** — `PA:` `PCS:` `VNEW:` `DUMP:` `TRACE:`.
- **Immediate mode** — a full REPL: `LIST` `RUN` `NEW` `AUTO` `REN` `LOAD` `SAVE`
  `DUMP` `VNEW` `TRACE` `QUIT`, with the colon optional (spec 6.2).

### Sixteen documented corrections to Core PILOT

The Atari sources contradict the Core PILOT reading in sixteen places. They are
listed with their evidence in [`SPEC.md`](SPEC.md) §10.1, and the four most
likely to bite:

- An **undefined string variable substitutes its own name** (spec 5.2.3) — the
  opposite of every other PILOT dialect.
- **`?` is literal text** in a text expression, not a random draw (spec 5.2.1).
  Expanding it silently corrupts any operand containing a question mark.
- **Division truncates toward zero** and the modulus result is **always
  positive** — `7/3 = 2`, `-7/3 = -2`, `-7\3 = 1` (spec 5.1.7).
- **`M:` is a substring search**, not a whole-buffer comparison (spec 6.1.3), so
  match fields are written padded with the buffer's own blanks.

### Specified but refused

`GR:` and `SO:` are real ATARI PILOT with no host equivalent. They parse and
then raise an error **naming the sub-command** that was requested — a refusal
that says only "not implemented" leaves a learner wondering whether they
mistyped. `CALL:` `TAPE:` `TSYNC:` `DOS:` are refused the same way, and the
Core-PILOT-only `F` family, `P:`, `W:` and `L:`-as-Link are syntax errors
rather than being silently ignored.

### Engineering

- Python ≥ 3.12, **zero third-party runtime dependencies** — it has to run on a
  classroom Raspberry Pi.
- 884 tests, 95% branch coverage, `mypy` strict, `ruff` lint and format, Sphinx
  docs that build with zero warnings, and a 3-OS × 2-Python CI matrix.
- Typed (`py.typed`, PEP 561).
- The corpus in `examples/` is **executed** by the test suite, not merely
  parsed — a program that parses and then misbehaves is worse than one that
  fails to parse, because a listing looks fine.

### Documentation

- [`SPEC.md`](SPEC.md) — the normative specification, with a decision log for
  every ambiguity (§10).
- [`docs/language.rst`](docs/language.rst) — the readable language reference.
- [`docs/api.rst`](docs/api.rst) — the API.
- A README session generated from a real run rather than typed by hand.

## Earlier stages

Development ran as ten staged releases. The intermediate versions
(0.1.0 – 0.10.0) are visible in the commit history; each stage is described in
`SPEC.md` §11 with what it delivered and what it revealed about the Atari
sources.
