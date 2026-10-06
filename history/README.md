# Research Sources

Background material collected while writing `SPEC.md`. Kept so the
specification's claims can be re-checked against primary sources rather than
inherited from the author's memory.

Retrieved **2026-09-26**.

---

## Primary source — the one that matters

### Atari PILOT External Specification, Revision E (1980-10-27)

- **Files:** `manuals/Atari_PILOT_External_Specification_RevE.pdf` (6.2 MB)
  and `manuals/Atari_PILOT_External_Specification_RevE_djvu.txt` (OCR text)
- **Author:** Harry B. Stewart — Atari's own PILOT implementer, and the
  programmer of record for the 1981 cartridge (per Atarimania)
- **Source:** <https://archive.org/details/Atari_Pilot_External_Specification_Revision-E>
  (collection `atari8bitmanuals`)
- **Also collected:** `manuals/Atari_PILOT_External_Specification_StewartEdits_djvu.txt`
  — a second scan (2015 upload) carrying **Stewart's own hand-written
  corrections**. Where the two OCR texts disagree, the plain scan is the
  reference; the annotated one is a useful errata source.
- **Why it matters:** this is the *normative* document for ATARI PILOT, and it
  is the single most useful thing in this folder. Written by the implementer
  for Atari's own engineers, it is more precise than any secondary source
  about what ATARI PILOT actually did.
- **Licence / copyright:** Atari, 1980.

**Sections that drove specific decisions in `SPEC.md`:**

| Section | Content | Effect on spec |
|---|---|---|
| §4.0 | Statement grammar (label, command, condition, params, comment) | §4.2 |
| §4.1 | Line numbers `0`–`9999`, editor-assigned | new — see `SPEC.md` §4.7 |
| §4.2 | Labels: unlimited length, **no duplicate detection**, first (lowest line number) wins | **reversed** the spec's duplicate-label error |
| §4.3 | Command names spelled precisely; `TYPEN:` is not valid | new |
| §4.4 | Conditions: `Y`/`N` and arithmetic test are **conjunctive** | corrects Core PILOT reading |
| §4.5 | Field delimiting; commas and blanks interchangeable as operand separators | **reverses** the spec's strict comma rule |
| §4.6 | Comments delimited by `[` … EOL, **not** `//` | **replaces** the `//` intraline comment |
| §4.7 | Command continuation — allowed only after `T`, `Y`, `N`, `R` | **tightens** the spec's elision rules |
| §5.1 | 16-bit signed integers, −32768…32767, **wrapping is not an error** | new — see `SPEC.md` §6.2 |
| §5.1.2 | Exactly **26** numeric variables, `#A`–`#Z` | **reverses** the spec's 10-char name rule |
| §5.1.3 | `?` as a random number, usable wherever a numeric constant is | new |
| §5.1.4 | Controller sense: `%J` joystick, `%P` paddle, `%T` trigger, `%H`/`%V`/`%L` lightpen | new |
| §5.1.5 | Special variables: `%F` free memory, `%M` match result, `%X`/`%Y`/`%A` graphics state | **replaces** the Core `%MATCH`/`%LEFT`/`%RIGHT` set |
| §5.1.6 | Pointers: `*<addr>` (word), `@B<addr>` (byte) — BASIC `PEEK`/`POKE` | new |
| §5.2.2 | String variable names up to **254** characters | as above |
| §5.2.3 | **Undefined string variables substitute their own name**, not empty | **reverses** the spec's most load-bearing assumption |
| §5.2.3 | Trailing `_` yields a trailing blank; text buffer 254 chars, silent truncation | new |
| §5.2.4 | String indirection `$$ABC` | new |
| App. A | Full data-syntax summary: operators, pointers, controller sense | new |
| App. B | Full command summary: Core first, then Atari extensions | §9.1 |

### Cross-check from the Student Reference Guide

Its table of contents independently confirms the External Specification's
command set, and usefully distinguishes the three tiers:

- **Core PILOT** (single-letter commands) — `T A M J C E U R Y N`
- **Executive** — `AUTO RUN LIST REN NEW VNEW DUMP LOAD SAVE DOS`
- **Atari extensions** — `GR:` (15 turtle-graphics sub-commands), `SO:`, `PA:`,
  `JM:`, `MS:`, `PCS:`, `TRACE`, `READ`/`WRITE`/`CLOSE`, `TAPE`/`TSYNC`,
  `CALL`

It also confirms that **graphics and sound are Atari additions layered on Core
PILOT** — the guide introduces them as "Turtle Graphics, a concept… from
[LOGO] Technology" — which is exactly the boundary §1.1 draws.

---

## Official Atari manuals

Both were image-only scans. **Both have now been OCR'd** (2026-09-26) with
`tools/ocr_manual.py` (Tesseract 5.4 + PyMuPDF, 200 DPI). Per-page and combined
text files sit alongside the PDFs.

### Atari Student PILOT Reference Guide — OCR'd

- **Files:** `manuals/Atari_Student_PILOT_Reference_Guide.pdf` (27 MB, 115 pp.)
  and `manuals/Atari_Student_PILOT_Reference_Guide_ocr.txt` (95 KB text, plus
  `manuals/_ocr_ref/page-NNNN.txt`)
- **Source:** <https://www.atarimania.com/documents/Atari-Student-Pilot-Reference-Guide.pdf>
- **Value:** confirms and extends the External Specification, and its table of
  contents is a **complete, authoritative command listing** for Atari PILOT —
  the single most useful cross-check available. It confirms the dialect split
  beyond doubt, with chapters: *Core PILOT*, *Executive Commands*, *Graphics*,
  *Sound and Pause*, *Conditionals*.

> **OCR caveat — read before quoting.** The command listings are set in a
> decorative stencil face that Tesseract mangles. In the contents, `T:` is
> rendered `7:`, `C:` as `OF:`, `E:` as `Es`. Prose is reliable; **command
> letters in the OCR text are not.** Always confirm a command against the PDF
> page image or the External Specification before relying on it.

### The PILOT Programming Language Instruction Manual ("Pilot Primer") — OCR'd

- **Files:** `manuals/Atari_PILOT_Primer_Instruction_Manual.pdf` (65 MB,
  209 pp.) and `manuals/Atari_PILOT_Primer_Instruction_Manual_ocr.txt`
  (247 KB text, plus `manuals/_ocr_primer/page-NNNN.txt`)
- **Source:** <https://www.atarimania.com/documents/Atari_Pilot_Primer.pdf>
- **Note:** per Atarimania, this shipped only with the **Educators Package**, not
  the Home Package. This is the book the project README remembers as "a step by
  step course disguised as a cute book of cartoons."
- **Value:** a **ten-section course**, each with concepts, worked programs, a
  section summary, and a quiz — and therefore the best available source of
  *period-correct example programs* to use as acceptance tests for `SPEC.md` §13.
  Sections: getting started · writing a program · decision-making · branching ·
  variables · using numbers · modules · sound · graphics.

  It also **settles two semantics** the External Specification states but the
  textbook states far more loudly (Primer p.85, *Using Numbers*):

  - Division is **longhand integer division that drops the remainder** —
    `7/3 = 2`, `5/4 = 1`, `99/12 = 8`. Not round-half-away-from-zero.
  - Max number size is `32767`, min `-32768`, and arithmetic **wraps
    silently** — the book literally shows `32767 + 1` returning `-32768` and
    calls the behaviour "strange".
- **Status:** OCR complete. Same stencil-font caveat applies.

### Re-OCRing

```console
uv run --with pymupdf python tools/ocr_manual.py <pdf> <outdir> [first] [last]
```

Raise `DPI` in the tool to 300 for a slower, slightly cleaner pass.

---

## Secondary sources

### psPILOT — `web/psPILOT.md`

- **Source:** <https://github.com/FreeTrav/psPILOT>
- **Author:** FreeTrav. MIT/PS licensed PowerShell implementation of much of
  Core PILOT per IEEE 1154-1991.
- **Use:** the best available *prose* description of Core PILOT semantics, and
  a ready-made list of where implementations disagree (its "Differences"
  appendices).
- **Caution:** it documents **Core PILOT / IEEE 1154**, *not* ATARI PILOT. Where
  the two conflict, the Atari External Specification wins.

### Wikipedia, *PILOT* — `web/wikipedia_PILOT.wiki`

- **Source:** <https://en.wikipedia.org/wiki/PILOT> (raw wikitext, CC BY-SA)
- **Use:** history, and the widely-reproduced command list. That command list
  is the *Core PILOT* subset and is silent on most of what ATARI added.

### EDM2, *PILOT* — `web/edm2_PILOT.wiki`

- **Source:** <https://www.edm2.com/index.php/PILOT> (raw wikitext)
- **Use:** **the key sentence justifying the project scope.** It states that
  most 6502 implementations descend from Western Washington's Common PILOT
  *except* the Atari one, and gives the reason:

  > "The reason why the Atari, Tandy Radio Shack and others did not follow the
  > CP standard was that Core PILOT was perfectly suited to beginners who often
  > figured out how to program in PILOT without any help from tutors while
  > Common PILOT expects some programming knowledge from the user. In addition
  > Core PILOT was also so small that it fit fine into 8k of memory or less,
  > thus being distributable with memory constrained 16k versions of the
  > computers sold by those companies, while Common PILOT needed or more."

  This independently confirms the project owner's recollection that ATARI PILOT
  is not Common PILOT, and explains *why*.

### EDM2, *RPilot* — `web/edm2_RPilot.wiki`

- **Source:** <https://www.edm2.com/index.php/RPilot>
- **Use:** pointer to Rob Linwood's C implementation, cited in `SPEC.md` §15.

---

## Sources consulted but *not* collected

| Item | Why not |
|---|---|
| IEEE Std 1154-1991 | Withdrawn **and** paywalled. Underpins Core PILOT; the reason `history/` leans on the Atari spec and psPILOT instead. |
| Starkweather, *PILOT-73 Guide* (1974) | Not online. The original Core PILOT definition. |
| Starkweather, *A User's Guide to PILOT* (1985) | Not online. |
| Kheriaty & Gerhold, *COMMON PILOT Language Reference Manual* (1980) | Not online. **Deliberately de-prioritised** — see `SPEC.md` §1.1: ATARI PILOT does not descend from it. |
| *Atari PILOT for Beginners* (Conlan & Deliman, 1983) | archive.org item exists; superseded by the External Specification, which is normative and machine-readable. |

---

## A note on source authority

The research for this project went through three revisions, and the earlier
ones were wrong in ways that mattered:

1. Wikipedia's command list suggested a small, Core-PILOT-ish language.
2. psPILOT filled in the Core PILOT details — good prose, but the *wrong
   dialect* for this project.
3. The Atari External Specification then showed the real dialect, and
   contradicted several of my assumptions outright: undefined variables
   substitute their own name, numeric variables are 26 single letters rather
   than 10-character names, division is not "round half away from zero" but
   16-bit integer division, and conditions are conjunctive rather than
   exclusive.

Lesson recorded in `SPEC.md` §10: **cite a primary source, and prefer the
implementer's own specification over a description of it.**
