"""Tests for the distribution metadata and what a release must never contain.

Two kinds of thing live here, and the second is the important one.

**Metadata.** The version, the classifiers, the console script, and the promise
of *zero third-party runtime dependencies* — the interpreter has to run on a
classroom Raspberry Pi, and nothing in the test suite can catch an accidental
`dependencies = [...]` because the dev environment already has everything.

**What must never ship.** ``history/`` holds copies of copyrighted Atari
manuals, kept locally and gitignored. A distribution that redistributed them
would be the worst possible bug this project could have, and it is one
plausible edit away: adding a path to ``pyproject``'s sdist ``include`` list
would do it silently.

The sdist test builds a real one, because checking the metadata cannot tell you
what hatchling actually put in the archive.
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent

#: Never shipped. `history/` is copyrighted source material kept for reference
#: only; `.venv` and friends are build noise.
FORBIDDEN_IN_DIST = ("history/", ".venv", "dist/", ".git/", "__pycache__")


@pytest.fixture(scope="module")
def metadata() -> dict[str, Any]:
    """The parsed ``[project]`` table."""
    parsed: dict[str, Any] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project: dict[str, Any] = parsed["project"]
    return project


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_the_version_is_one_zero(metadata: dict[str, Any]) -> None:
    assert metadata["version"] == "1.0.0"


def test_the_version_is_not_hardcoded_in_the_package() -> None:
    """pyproject is the single source of truth.

    It drifted once: the package was bumped to 0.3.0, pyproject was forgotten,
    and `uv build` produced a 0.2.0 wheel. Reading `importlib.metadata` makes
    that impossible, so this asserts the two agree.
    """
    import importlib.metadata

    from pypilot import __version__

    declared = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert declared["project"]["version"] == __version__
    assert importlib.metadata.version("pypilot") == __version__


def test_there_are_no_runtime_dependencies(metadata: dict[str, Any]) -> None:
    """§12 - zero third-party runtime dependencies.

    The interpreter must run on a classroom Raspberry Pi with nothing but
    CPython, so this is a design constraint rather than a packaging preference.
    """
    assert metadata.get("dependencies", []) == []


def test_the_author_email_is_not_malformed(metadata: dict[str, Any]) -> None:
    """It carried a doubled `.com.com` for most of the project."""
    for author in metadata["authors"]:
        assert author["email"].count("@") == 1
        domain = author["email"].split("@")[1]
        assert domain.count(".") == 1, f"{author['email']} has a malformed domain"


def test_the_classifier_says_stable(metadata: dict[str, Any]) -> None:
    """A 1.0 release must not ship as an alpha."""
    assert "Development Status :: 5 - Production/Stable" in metadata["classifiers"]
    assert not any("Alpha" in c for c in metadata["classifiers"]), "still marked alpha"


def test_the_console_script_is_declared(metadata: dict[str, Any]) -> None:
    assert metadata["scripts"] == {"pypilot": "pypilot.cli:main"}


def test_the_readme_and_changelog_are_declared(metadata: dict[str, Any]) -> None:
    assert (ROOT / metadata["readme"]).exists()
    assert (ROOT / "CHANGELOG.md").exists(), "1.0 needs a changelog"
    assert metadata["urls"]["Changelog"].endswith("CHANGELOG.md")


# ---------------------------------------------------------------------------
# What a distribution must never contain
# ---------------------------------------------------------------------------


def test_history_is_excluded_from_the_build(metadata: dict[str, Any]) -> None:
    """The exclusion must be explicit, not merely the absence of an `include`.

    Relying on "we never mentioned it" is one edit away from shipping somebody
    else's copyrighted manuals.
    """
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    excludes = config["tool"]["hatch"]["build"].get("exclude", [])
    assert any("history" in pattern for pattern in excludes), (
        "pyproject must exclude history/ explicitly; the sdist include list alone is not enough"
    )


def test_the_collected_documents_are_gitignored() -> None:
    """The manuals stay local; only the bibliography is tracked.

    ``history/README.md`` is deliberately tracked - it is the provenance
    record, and it is ours. The *documents* under it are somebody's
    copyright and must never be committed, let alone packaged.
    """
    ignored = {
        line.strip().rstrip("/")
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    for directory in ("/history/web", "/history/manuals", "/history/references"):
        assert directory in ignored, f"{directory} must be gitignored"
    assert (ROOT / "history" / "README.md").is_file(), "the bibliography is tracked"


@pytest.mark.slow
def test_a_built_sdist_contains_nothing_forbidden(tmp_path: Path) -> None:
    """Build a real sdist and look inside it.

    Checking the metadata cannot tell you what hatchling actually packed, and
    this is the check that matters.
    """
    subprocess.run(
        ["uv", "build", "--sdist", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    archives = list(tmp_path.glob("*.tar.gz"))
    assert len(archives) == 1, f"expected one sdist, got {archives}"

    with tarfile.open(archives[0]) as tar:
        names = [f"/{name}" for name in tar.getnames()]

    for needle in FORBIDDEN_IN_DIST:
        offenders = [name for name in names if needle in name]
        assert not offenders, f"{archives[0].name} contains {needle}: {offenders[:5]}"

    # And it must still contain what a contributor needs.
    joined = "\n".join(names)
    for required in ("/src/pypilot/", "/tests/", "/examples/", "/SPEC.md"):
        assert required in joined, f"{required} missing from the sdist"


@pytest.mark.slow
def test_a_built_wheel_ships_only_the_package(tmp_path: Path) -> None:
    """A wheel is the installable artifact, so extra files are extra risk."""
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    archives = list(tmp_path.glob("*.whl"))
    assert len(archives) == 1, f"expected one wheel, got {archives}"

    with zipfile.ZipFile(archives[0]) as wheel:
        names = [f"/{name}" for name in wheel.namelist()]

    for needle in FORBIDDEN_IN_DIST:
        offenders = [name for name in names if needle in name]
        assert not offenders, f"{archives[0].name} contains {needle}: {offenders[:5]}"

    assert any(name.endswith("pypilot/py.typed") for name in names), "PEP 561 marker"
    assert any(name.endswith("pypilot/cli.py") for name in names), "the entry point module"
    assert any("dist-info/METADATA" in name for name in names), "core metadata"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
