.. _api:

API Reference
=============

.. module:: pypilot

The package exports its error hierarchy, the parser, the value model, and
interpreter state. The *interpreter* is not yet written; see ``SPEC.md`` section
11 for the implementation roadmap.

Quick start
-----------

.. code-block:: python

   from pypilot import PilotState, parse

   program = parse("T:HELLO, $NAME\nA:$NAME\nT:HI $NAME.\nE:")
   for statement in program:
       print(statement.line_number, statement.command, repr(statement.params))

   # An undefined string variable prints *its own name* - the ATARI rule.
   state = PilotState()
   assert state.expand("HELLO $NAME") == "HELLO NAME"
   state.set_string("NAME", "ada")
   assert state.expand("HELLO $NAME") == "HELLO ada"

   # Expressions are left-to-right, with no operator precedence.
   assert state.evaluate("1+2*3").value == 9, "not 7"

   # Running a program, with output captured for a test.
   from pypilot import Interpreter
   from pypilot.io import BufferOutput

   out = BufferOutput()
   Interpreter(parse("T:HELLO\nC:#A=2+3\nT:#A"), output=out).run()
   assert out.text == "HELLO\n5\n"

Errors
------

.. autoexception:: pypilot.errors.PilotError
.. autoexception:: pypilot.errors.PilotSyntaxError
.. autoexception:: pypilot.errors.PilotRuntimeError
.. autoexception:: pypilot.errors.PilotUndefinedLabelError
.. autoexception:: pypilot.errors.PilotUnsupportedError

Parser
------

.. autofunction:: pypilot.syntax.parse
.. autofunction:: pypilot.syntax.decode_source

.. autoclass:: pypilot.syntax.Parser
   :members:

.. autoclass:: pypilot.syntax.Program
   :members:

.. autoclass:: pypilot.syntax.Statement
   :members:

.. autoclass:: pypilot.syntax.Condition
   :members:

.. autoclass:: pypilot.syntax.CommandName
   :members:

Values
------

.. autoclass:: pypilot.values.Numeric
   :members:

.. autofunction:: pypilot.values.wrap16
.. autofunction:: pypilot.values.expand_text
.. autofunction:: pypilot.values.scan_text

.. autoclass:: pypilot.values.Piece
   :members:

.. autoclass:: pypilot.values.Kind
   :members:

State
-----

.. autoclass:: pypilot.state.PilotState
   :members:

.. autoclass:: pypilot.state.MatchResult
   :members:

.. autofunction:: pypilot.state.normalise_accept

Expressions
-----------

.. automodule:: pypilot.expressions
   :no-members:

.. autofunction:: pypilot.expressions.evaluate
.. autofunction:: pypilot.expressions.is_expression

.. autoexception:: pypilot.expressions.ExpressionError

.. warning::

   ATARI PILOT has **no operator precedence**. Expressions are evaluated left
   to right, so ``1+2*3`` is ``9``, not ``7``. Parentheses are the only way to
   change that, and only two levels of *useful* nesting are allowed.

Matching
--------

.. automodule:: pypilot.match
   :no-members:

.. autoclass:: pypilot.match.MatchOutcome
   :members:

.. autofunction:: pypilot.match.split_fields
.. autofunction:: pypilot.match.find_match
.. autofunction:: pypilot.match.split_jump_labels

.. note::

   ``M:`` and ``MS:`` search for a field **anywhere within** the accept
   buffer; they do not compare it against the whole thing. ``M:YE`` matches
   the input ``YEAH``. A ``<right arrow>`` operand (``\x1e``) moves where the
   search starts: *n* arrows start it at the (n+1)th character.

   An **empty field is a null match** and matches anything, which is the
   idiomatic "anything else" branch: ``M:YES,NO,`` catches every input the
   first two missed. Only a wholly null operand (``M:``) is an error.

Interpreter
-----------

.. autoclass:: pypilot.runtime.Interpreter
   :members:

.. autoclass:: pypilot.runtime.TraceEvent
   :members:

.. note::

   ``J:`` and ``U:`` move the program counter; ``E:`` has **two** behaviours and
   picks between them from the use stack. Spec 6.1.10 states it as one rule:
   return to the statement after the most recent ``U:``, *or* stop the program
   if no return is stacked. There is no separate module-end command.

   ``JM:`` is positional against the match ordinal, and deliberately falls
   through rather than erroring when the ordinal runs past the end of the label
   list — or when the match failed, since ``%M`` is then 0 and there is no 0th
   operand. That makes it safe to place unconditionally after an ``M:``.

   Its operand follows the general separator rule of spec 4.5 (a run of commas
   and/or blanks is one separator) rather than the ``M:`` exception, so both
   ``JM:*L1 *L2 *L3`` and ``JM: *HERE , *THERE , *EVERYWHERE`` are valid.

   ``U:`` nests to **8**, the Atari's own limit (spec 6.1.9), not a host-sized
   number. A ninth level raises rather than exhausting the Python stack.

Devices
-------

.. automodule:: pypilot.devices
   :no-members:

.. autoclass:: pypilot.devices.DeviceTable
   :members:

.. autoclass:: pypilot.devices.OpenDevice
   :members:

.. autoclass:: pypilot.devices.DeviceKind
   :members:

.. autofunction:: pypilot.devices.split_device_spec
.. autofunction:: pypilot.devices.device_root
.. autoclass:: pypilot.devices.FileHandle
   :members:
.. autodata:: pypilot.devices.DEVICE_LETTERS
.. autodata:: pypilot.devices.MAX_OPEN_DEVICES
.. autodata:: pypilot.devices.OPEN_FILE_PREFIX

.. note::

   ATARI PILOT's I/O is **device-oriented**: a program names a device and the
   first use of that name opens it. There is no ``OPEN`` command and there are
   no numeric file handles — see ``SPEC.md`` §9.6 and the device table in
   ``docs/language.rst``.

   Four rules from spec 6.1.17 that are easy to get wrong:

   - **Open on first use.** That is the language, not a convenience.
   - **At most four open.** The Atari had four I/O control blocks; a fifth
     device raises rather than silently evicting one.
   - **End-of-file is not an error.** It yields the *null string*, which is
     distinct from an undefined string — which prints its own name.
   - **Open files live in the string table**, named ``@«spec»``. That is what
     makes ``VNEW:$`` close every file, and what ``DUMP:`` shows.

.. autoclass:: pypilot.io.OutputDevice
   :members:

.. autoclass:: pypilot.io.InputDevice
   :members:

.. autoclass:: pypilot.io.BufferOutput
   :members:

.. autoclass:: pypilot.io.StringInput
   :members:

.. autoclass:: pypilot.io.ConsoleOutput
   :members:

Host helpers
------------

.. automodule:: pypilot.helpers
   :no-members:

.. autoclass:: pypilot.helpers.Os
   :members:

Core command surface
--------------------

.. autoclass:: pypilot.core.PilotCore
   :members:
   :private-members: _a, _r, _c, _t, _m, _ms, _j, _jm, _u, _e

Immediate mode
---------------

.. automodule:: pypilot.repl
   :no-members:

.. autoclass:: pypilot.repl.Repl
   :members:

.. autoclass:: pypilot.helpers.Shell
   :members:

.. autofunction:: pypilot.helpers.parse_line_range

.. note::

   A program run from the REPL gets its **own** input device, separate from the
   command stream. That is not tidiness: with one shared stream the program's
   first ``A:`` swallows the next REPL command, so a ``QUIT`` typed after
   ``RUN`` is eaten and the session runs away. The Atari had the same two-level
   structure - the program read from the keyboard, and the immediate-mode line
   was only re-read once the program returned.

   The colon is **optional** on every immediate-mode command (spec 6.2), and may
   sit on either side of the blank: ``TRACE:ON``, ``TRACE: ON`` and ``TRACE ON``
   are one command.

Command line
------------

.. automodule:: pypilot.cli
   :members: main, build_parser, check_program, run_program, repl
