.. _language:

Language Reference
==================

This page describes **ATARI PILOT** as pyPILOT implements it.

The normative source is the *Atari PILOT External Specification*, Revision E
(27-Oct-1980), by Harry B. Stewart — Atari's own PILOT implementer. The full
specification, including the decision log for every ambiguity, is in
``SPEC.md``; this page is the readable summary.

.. warning::

   ATARI PILOT is **not** Core PILOT and **not** Common PILOT, despite the
   similarities. It is Core PILOT plus a small Atari layer. The two differ in
   several places that will surprise you if you have read about another PILOT
   dialect — most notably, an undefined string variable prints **its own name**,
   and division **truncates**. See ``SPEC.md`` §10.1 for the full list.

Program line structure
----------------------

A PILOT program is a sequence of lines. Each line is, in order:

1. an optional label,
2. a command name (one to five letters; names are matched case-insensitively),
3. an optional condition (``Y``, ``N``, a parenthesised expression, or both),
4. a colon,
5. the parameters, to the end of the line.

A label may also occupy a line on its own, and may share a line with a command.

.. code-block:: pilot

    R:Ask the learner their name and greet them
    *GREET
    T:WHAT IS YOUR NAME?
    A:$NAME
    T:HELLO, $NAME.

    *ASK_NUMERIC
    T:HOW OLD ARE YOU?
    A:#A
    T:YOU SAID YOU ARE #A.

Blanks are ignored to the left of the colon and **significant** to its right.
Commas and blanks are interchangeable as parameter separators.

Comments
--------

A comment runs from ``[`` to the end of the line, and may contain any character.
``R:`` is also a comment command and may carry a condition.

There is no ``//`` comment in ATARI PILOT — a ``//`` is ordinary text.

.. _immediate:

Immediate mode
--------------

Running ``pypilot`` with no program file opens the interactive session, the
*immediate mode* of the original system. It is the same language in a different
mood: a statement typed at the prompt executes at once, and the commands below
edit the program area that ``RUN`` later executes.

.. code-block:: text

   pilot> AUTO 100,10
   auto> 100 T:WHAT IS YOUR NAME?
   auto> 110 A:$NAME
   auto> 120 T:HELLO, $NAME.

   pilot> LIST
      1  100 T:WHAT IS YOUR NAME?
      2  110 A:$NAME
      3  120 T:HELLO, $NAME.
   pilot> RUN
   pilot> QUIT

The colon is **optional** on an immediate-mode line, and may sit on either side
of the blank — ``TRACE:ON``, ``TRACE: ON`` and ``TRACE ON`` are one command.

=========  ==========================================================
Command    What it does
=========  ==========================================================
``LIST``   Print the deferred program, optionally a line range
``RUN``    Run it, from a clean environment
``NEW``    Discard it and reset the variables
``AUTO``   Enter auto-numbered input mode
``REN``    Renumber the program
``LOAD``   Replace it from a device
``SAVE``   Write it to a device
``DUMP``   List the string variables
``VNEW``   Reset variables
``TRACE``  Toggle tracing
``QUIT``   Leave
=========  ==========================================================

``AUTO`` is the interesting one. It generates line numbers for you, and an
empty line leaves the mode. A statement with a syntax error is simply not
stored — the mode continues, so one mistyped line does not cost you the lesson.

``REN`` never reorders the program, only the numbers. That is deliberate: if a
generated number falls outside 0–9999, the process stops and the program is
left exactly as it was, so you can renumber again with different operands. A
program that had been *reorganised* could not be recovered that easily.

Continuation
------------

A statement with no command name and no condition repeats the previous
statement's command *and* condition:

.. code-block:: pilot

    T(#A>40):NOT ENOUGH.
    :TRY AGAIN.
    :ONE MORE TIME.

Continuation is allowed only after ``T:``, ``Y:``, ``N:`` and ``R:``; after any
other command it is a run-time error.

Labels
------

A label is an asterisk followed by alphanumerics, of any length. Labels are
case-sensitive. **Duplicate labels are allowed** — the one with the lowest line
number wins.

.. _commands:

Commands
--------

Core commands
~~~~~~~~~~~~~

``A`` - Accept
    ``A:`` reads a line into the *accept buffer*. ``A:$NAME`` also stores it in
    a string variable. ``A:#A`` stores a number. ``A:SRIGHT`` is a synonym for
    ``A:$RIGHT``.

``R`` - Remark
    A comment.

``C`` - Compute
    ``C:#A=(#B+#C)/2`` evaluates integer arithmetic. ``C:$S=HELLO, $NAME``
    performs string concatenation.

``T`` - Type
    Writes the expanded text plus a newline.

``Y`` / ``N`` - Type if match / no match
    Shorthand for ``TY:`` and ``TN:``.

``M`` - Match
    Compares the accept buffer against a list of fields.

``J`` - Jump
    ``J:*LABEL`` transfers control.

``U`` - Use
    Calls the module starting at a label. ATARI calls subroutines *modules*.

``E`` - End
    Returns from a module, or ends the program at the top level.

Atari extensions
~~~~~~~~~~~~~~~~

``MS``
    Match, additionally setting ``$LEFT``, ``$MATCH`` and ``$RIGHT``.

``JM``
    Jump on match — multi-way branching on the match ordinal.

``PA``
    Pause *n* units. The increment is **1/60 second**, not 1 second, so
    ``PA:60`` is about one second. The operand is a numeric expression, so
    ``PA:#D`` is a real delay. ``PA:0`` is **not** a no-op — it "delays to the
    next clock tick" and is handed to the host as a yield point, which is what
    keeps an embedding program responsive while a PILOT program runs.

``PCS``
    Position the cursor. Column 3–39, row 0–23; the upper-left of the text
    screen is 3,0 because columns 0–2 hold the prompt. Values outside that
    range are clamped rather than refused.

``VNEW``
    New variables. A null operand resets both stores, ``VNEW:$`` the strings,
    ``VNEW:#`` the numerics.

    Resetting the strings also **closes every open file**. The Atari records
    open devices in the string table, and the External Specification says
    clearing it "has the effect of closing all files". You can see this in
    ``DUMP:``, which lists the open devices among the strings.

``DUMP``
    Dump string variables and their values.

``TRACE``
    ``TRACE:ON`` / ``TRACE:OFF`` toggles execution tracing. Traced lines go to
    standard error, never to the program's output, so a trace can never be
    mistaken for a result or end up inside a redirected file.

``READ`` / ``WRITE`` / ``CLOSE``
    Device-oriented I/O. There are no numeric file handles — see
    :ref:`devices` below.

``LOAD`` / ``SAVE``
    Load or save a program to a device. A run-mode ``LOAD:`` clears the program
    area and the Use stack but **preserves** the accept buffer, the match flag
    and every variable, which is why ``VNEW:`` is how a program starts clean.

``GR:``
    Turtle graphics — 15 subcommands. **Specified but refused**; raises a
    clear error naming the subcommand because this host has no graphics device.

``SO:``
    Sound. **Specified but refused**, as with ``GR:``.

``CALL:``, ``TAPE:``, ``TSYNC:``, ``DOS:``
    Hardware, cassette, and host-shell commands. Parse, then are refused. See
    ``SPEC.md`` §10.7.

.. _devices:

Devices
-------

ATARI PILOT's I/O is **device-oriented**, which is the single biggest
difference from other PILOT dialects. Core PILOT has ``FA:#H,«file»`` and a
family of numeric file handles; ATARI PILOT has **none of that**. A program
names a device, and the first use of that name opens it:

.. code-block:: pilot

   C:$DEV=C:NOTES
   WRITE:$DEV,HELLO FROM PILOT
   CLOSE:$DEV
   READ:$DEV,$LINE
   T:YOU TYPED $LINE

There is no ``OPEN`` command. The External Specification is explicit that "the
first use of the name in a READ or WRITE command will attempt to OPEN the
device", so open-on-first-use is the language, not a convenience.

Device letters
~~~~~~~~~~~~~~

======  ======================  ================================================
Letter  Atari device            pyPILOT host mapping
======  ======================  ================================================
``C``   Cassette                a file in ``~/.pypilot/cassette/``
``D``   Diskette                a file in ``~/.pypilot/disk/``
``E``   Screen editor           the program's input
``K``   Keyboard                the program's input
``P``   Printer                 the program's output
``S``   Display handler         the program's output
======  ======================  ================================================

A device may be named by a bare letter (``C``), by a letter and a filename
(``D:ELIZA``), or by a string variable whose value is either of those. The
letter is case-insensitive; the filename is not, because it is a name the
program chose.

Four devices may be open at once. The fifth raises rather than silently
evicting one, because the Atari had four I/O control blocks and a program that
needed a fifth was a program the Atari could not run.

Four rules worth knowing
~~~~~~~~~~~~~~~~~~~~~~~~

**End-of-file is not an error.** A read past the end yields the *null string*,
so the variable is defined and empty. This is deliberately different from
undefined, which prints its own name — a program can tell the two apart. If you
want your own end-of-file marker, write one and match against it, which is what
the specification's own worked example does.

**Devices are bi-directional.** A cassette is a tape: write to the end, rewind,
read back. ``WRITE:`` followed by ``READ:`` on the same device returns what you
just wrote, and a second ``READ:`` returns the next line rather than the first.

**Synonyms are separate devices.** ``E`` and ``e:`` both name the screen editor,
but the specification says "each synonym is treated as a separate device", so
pyPILOT keys them separately and they do not share a slot.

**Open files appear as strings.** An open device is recorded in the string
table under ``@`` plus its spec, holding the character for its I/O control
block — an open cassette is ``$@C``. ``DUMP:`` shows them, and ``VNEW:$`` closes
them, because they are ordinary strings.

.. _conditions:

Conditions
----------

Any statement may be conditional:

.. code-block:: pilot

    TY:YOU SAID IT RIGHT.
    TN:TRY AGAIN.
    T(#A>10):EXCELLENT

``Y`` tests the match flag and ``N`` tests its negation. A parenthesised
expression is true when it is **greater than zero**.

``Y`` and a parenthesised expression may be combined, and are then
**conjunctive** — both must hold for the statement to run:

.. code-block:: pilot

    TY(#A>10):CORRECT AND LARGE

.. _numeric:

Numbers
-------

- **Integers only.** No floating point.
- Range is **16-bit signed**: ``-32768`` to ``32767``.
- Arithmetic **wraps silently** and is *not* an error. ``32767 + 1`` is
  ``-32768``.
- Division **truncates toward zero**, dropping the remainder: ``7/3`` is ``2``.
- Modulo is a **backslash**, not ``%`` — ``%`` is a variable sigil:
  ``7\3`` is ``1``.

.. code-block:: pilot

    C:#A=7/3     R:#A is 2, not 3
    C:#A=7\3     R:#A is 1

.. _variables:

Variables
---------

Variables have a one-character type prefix:

* ``#A`` … ``#Z`` — numeric. **Exactly 26 of them**, single letters.
* ``$NAME`` — string. Names run up to 254 characters.
* ``%F`` ``%M`` ``%X`` ``%Y`` ``%A`` — read-only specials.
* ``%J`` ``%P`` ``%T`` ``%H`` ``%V`` ``%L`` — controller sense.

.. _undefined-variables:

Undefined variables print their own name
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is the rule most likely to surprise you coming from another PILOT:

.. code-block:: pilot

    T:[$UNSET]     prints    [UNSET]

An **undefined** string variable is not empty — it renders as its own name. A
variable that has been assigned the empty string is a *null string*, which is a
different state and does print as empty.

.. _accept-buffer:

The accept buffer
-----------------

``A:`` does not store the input verbatim. The accept buffer is **normalised**
on the way in:

1. a space is added at the **beginning**,
2. a space is added at the **end**,
3. lower case is converted to **upper case**,
4. runs of spaces collapse to a single space,
5. the result is truncated to 254 characters.

So typing ``yes`` leaves `` YES `` in the buffer — padded, upper-cased, and
space-collapsed. This is why match fields in the manuals are written in upper
case, and why a field written with a trailing ``_`` matches a word *plus* its
trailing space.

.. _match:

Matching
--------

.. code-block:: pilot

    M:YES,YEAH,SURE     R:comma-separated fields
    M:|YES|YEAH|SURE    R:vertical-bar-separated fields
    M:$VERBLIST         R:fields from a string variable

- Each field is searched as a **substring within the normalised accept buffer**:
    ``M:YE`` matches ``YEAH``, and ``M:YES`` matches the padded input ``" YES "``.
- The separator is a comma, or — if the operand begins with ``|`` — a vertical
  bar. Never both.
- Fields are tried **in order**; the first match wins.
- The match flag holds the **ordinal** of the field that matched, or ``0`` for
  no match. It is available as ``%M`` and is what ``JM:`` uses.
- An **empty field** matches anything. A **null operand** is an error.
- Cursor-right characters at the start of the operand skip that many buffer
  characters before matching; one right-arrow skips the buffer's mandatory
  leading space, which is how you match the first *embedded* blank.

``MS:`` additionally splits the buffer on a successful match:

.. code-block:: pilot

    A:=THIS IS A TEST.
    MS:IS,WAS,WILL,BE
    T:[$LEFT]     prints    [ THIS ]
    T:[$MATCH]    prints    [IS]
    T:[$RIGHT]    prints    [ A TEST.]

On a **failed** match these three keep their previous values.
