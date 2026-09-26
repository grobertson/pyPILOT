"""Fail if a secret is about to be committed.

Deliberately blunt: it greps the *staged* content for the shapes that have
actually leaked in this project, and reports the file and line. A pre-commit
hook is the wrong place for this because the token once sat in a `tools/` script
that a `--dry-run` would not have flagged as sensitive.

Run: `uv run python tools/scan_secrets.py`
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Patterns that must never appear in tracked content.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PyPI API token", re.compile(r"\bpypi-[A-Za-z0-9_-]{20,}")),
    ("GitHub PAT", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
]

#: Paths never worth scanning: the manuals are somebody else's copyright and the
#: local venvs are build noise.
SKIP_DIRS = {".git", ".venv", "dist", "__pycache__", "docs", "history", "tools"}


def tracked_files() -> list[Path]:
    """Every file git would stage, as paths."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    findings: list[str] = []
    scanned = 0
    for path in tracked_files():
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        for name, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line = text[: match.start()].count("\n") + 1
                # Show enough to identify it, never enough to use it.
                excerpt = match.group(0)[:8]
                findings.append(f"{path.relative_to(ROOT)}:{line}: {name} ({excerpt}...)")

    print(f"scanned {scanned} file(s)")
    if findings:
        print("\nSECRETS FOUND - do not commit:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print("no secrets found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
