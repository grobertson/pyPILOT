"""Audit SPEC.md section 12's checklist against what the code actually does.

Reports each item as OK / STALE / MISSING so the discrepancies are visible
rather than assumed. Run with `uv run python tools/audit_checklist.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "SPEC.md").read_text(encoding="utf-8")


def section(number: str) -> str:
    """The text of a `## N.` section of SPEC.md."""
    start = SPEC.index(f"## {number}.")
    rest = SPEC[start + 1 :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def items(number: str) -> list[tuple[str, str]]:
    """Every `- [ ]` item of a section as ``(text, section-heading)``."""
    body = section(number)
    heading = ""
    found: list[tuple[str, str]] = []
    for line in body.splitlines():
        if line.startswith("### "):
            heading = line[4:].strip()
        match = re.match(r"^- \[([ x])\] (.+)$", line.strip())
        if match:
            found.append((match.group(2), heading))
    return found


def main() -> int:
    total = 0
    for number in ("12", "11"):
        try:
            found = items(number)
        except ValueError:
            print(f"section {number}: not found")
            continue
        total += len(found)
        done = sum(1 for text, _ in found if "DONE" in text)
        print(f"section {number}: {len(found)} checklist items, {done} marked done")
        current = None
        for text, heading in found:
            if heading != current:
                current = heading
                print(f"  -- {_safe(current)}")
            print(f"     {_safe(text[:96])}")
    print(f"\ntotal: {total}")
    return 0


def _safe(text: str) -> str:
    """Strip anything the Windows console cannot encode.

    SPEC.md is full of arrows, section marks and maths, and `cp1252` will
    raise rather than substitute. An audit tool that crashes on the character
    it is auditing is no use.
    """
    return text.encode("ascii", errors="replace").decode("ascii")


if __name__ == "__main__":
    sys.exit(main())
