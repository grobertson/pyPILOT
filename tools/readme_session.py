"""Produce the README's example session from a real run, not by hand.

Writing a transcript by hand is how documentation drifts. This runs the actual
REPL and prints what came out, so the README can be updated from the truth.

    uv run python tools/readme_session.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pypilot.helpers import Shell  # noqa: E402
from pypilot.io import BufferOutput, StringInput  # noqa: E402
from pypilot.repl import Repl  # noqa: E402

#: What a learner would type, and what the program would be told.
TYPED = [
    "AUTO 100,10",
    "T:WHAT IS YOUR NAME?",
    "A:$NAME",
    "T:HELLO, $NAME.",
    "T:ARE YOU A STUDENT? (YES OR NO)",
    "A:$ANSWER",
    "M: YES , NO",
    "JM:*YES,*NO",
    "T:UNRECOGNISED ANSWER.",
    "J:*END",
    "*YES",
    "T:WELCOME TO THE COURSE.",
    "J:*END",
    "*NO",
    "T:COME BACK ANY TIME.",
    "*END",
    "E:",
    "",
    "LIST",
    "RUN",
    "QUIT",
]

ANSWERS = ["ada", "yes"]


def main() -> int:
    out = BufferOutput()
    repl = Repl(
        Shell(),
        output=out,
        source=StringInput(TYPED),
        program_source=StringInput(ANSWERS),
        device_root=str(ROOT / "dist" / "readme-devices"),
    )
    repl.run()

    # The raw transcript has the prompt, then the generated number, glued to the
    # start of every echoed line. Strip both: what a terminal shows is the
    # statement, not the prompt the user already typed past. A trailing run of
    # bare prompts (the `AUTO` mode announcing numbers nobody typed at) is an
    # artefact of piping and would be noise in a README.
    cleaned: list[str] = []
    for line in out.text.splitlines():
        # The piped transcript runs every `auto> NNN ` prompt together on one
        # line. Split them back out first, so each gets its own line.
        parts = re.split(r"auto> \d+ ", line)
        for part in parts:
            stripped = part
            for _ in range(4):
                if not (stripped.startswith("pilot> ") or stripped.startswith("auto> ")):
                    break
                for prefix in ("pilot> ", "auto> "):
                    if stripped.startswith(prefix):
                        stripped = stripped[len(prefix) :]
                        head, sep, tail = stripped.partition(" ")
                        if head.isdigit() and sep:
                            stripped = tail
                        break
            cleaned.append(stripped)

    # A bare prompt with nothing after it is the REPL waiting; piping leaves a
    # trail of them that a terminal would not show.
    for line in cleaned:
        if line.strip():
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
