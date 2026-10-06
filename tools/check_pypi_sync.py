"""Compare the version in pyproject.toml with what PyPI has published.

    uv run python tools/check_pypi_sync.py                      # report; fail if PyPI is ahead
    uv run python tools/check_pypi_sync.py --require-unpublished  # release gate; fail if already on PyPI

A project that is not on PyPI yet (HTTP 404) counts as "nothing published".
Without `--require-unpublished` a network failure is a warning, so an outage
at PyPI cannot turn every pull request red; with it, it is an error, because a
release must not guess.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPI_JSON = "https://pypi.org/pypi/{name}/json"
TIMEOUT_SECONDS = 15

_FINAL_VERSION = re.compile(r"\d+(\.\d+)*")


def declared() -> tuple[str, str]:
    """The distribution name and version declared in pyproject.toml."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return project["name"], project["version"]


def version_key(version: str) -> tuple[int, ...]:
    """Order final releases; pre-releases are not supported by this project."""
    if not _FINAL_VERSION.fullmatch(version):
        raise ValueError(f"unsupported version {version!r}: only final X.Y.Z releases")
    return tuple(int(part) for part in version.split("."))


def published_versions(name: str) -> list[str]:
    """Versions PyPI has for ``name``; empty if the project does not exist yet."""
    url = PYPI_JSON.format(name=name.lower())
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        raise
    return [v for v, files in data["releases"].items() if files and _FINAL_VERSION.fullmatch(v)]


def check(local: str, published: list[str], *, require_unpublished: bool) -> tuple[bool, str]:
    """Decide whether the local version is acceptable; returns (ok, message)."""
    if not published:
        return True, f"{local} is local; nothing is published on PyPI yet"
    latest = max(published, key=version_key)
    if version_key(local) < version_key(latest):
        return False, f"local {local} is behind PyPI {latest}; PyPI versions cannot be reused"
    if local in published:
        if require_unpublished:
            return False, f"{local} is already on PyPI; bump the version before releasing"
        return True, f"{local} is published and in sync (latest on PyPI: {latest})"
    return True, f"{local} is unreleased (latest on PyPI: {latest})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--require-unpublished", action="store_true")
    args = parser.parse_args()

    name, local = declared()
    try:
        published = published_versions(name)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if args.require_unpublished:
            print(f"::error::could not reach PyPI to verify {name} {local}: {exc}")
            return 1
        print(f"::warning::could not reach PyPI, skipping the sync check: {exc}")
        return 0

    ok, message = check(local, published, require_unpublished=args.require_unpublished)
    print(f"{'::notice::' if ok else '::error::'}{name}: {message}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
