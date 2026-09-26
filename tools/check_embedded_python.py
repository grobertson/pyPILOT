"""Verify the Python embedded in publish.yml actually parses.

A heredoc inside a YAML block scalar is invisible to every other check: the
YAML parses, the workflow is valid, and then the job fails on the runner because
of a typo three lines into a `<<'PY'` block. Cheap to check here, expensive to
find out on a release.

    uv run python tools/check_embedded_python.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

#: A heredoc of the form `<<'PY'` ... `PY`.
HEREDOC = re.compile(r"<<'(?P<tag>[A-Z_]+)'\n(?P<body>.*?)\n\s*(?P=tag)\b", re.DOTALL)


def main() -> int:
    failures = 0
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        blocks = list(HEREDOC.finditer(text))
        if not blocks:
            print(f"{path.name}: no embedded heredoc")
            continue
        for index, block in enumerate(blocks, start=1):
            body = block.group("body")
            # The block is indented to sit inside a YAML block scalar; dedent
            # before parsing or Python sees a leading IndentationError.
            lines = body.splitlines()
            pad = min((len(line) - len(line.lstrip()) for line in lines if line.strip()), default=0)
            source = "\n".join(line[pad:] for line in lines)
            try:
                ast.parse(source)
            except SyntaxError as exc:
                failures += 1
                print(f"{path.name} block {index} ({block.group('tag')}): {exc}")
                print(f"  first line: {source.splitlines()[0] if source.splitlines() else ''}")
            else:
                first = source.splitlines()[0] if source.splitlines() else ""
                print(f"{path.name} block {index} ({block.group('tag')}): ok - {first[:60]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
