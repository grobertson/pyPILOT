"""Tests for distribution metadata and built archive contents.

The suite pins the distinct PyPI distribution and import package names,
release metadata, zero runtime dependencies, and the contents of real build
artifacts.
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

#: Generated environments and build output do not belong in distributions.
BUILD_ARTIFACTS = (".venv", "dist/", ".git/", "__pycache__")

#: The PyPI distribution name. **Not** `pypilot`: that name is taken on PyPI by
#: somebody else. `importlib.metadata` normalises names, so lookups must use
#: the lower-case form.
DIST_NAME = "rePILOT"


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
    # The *distribution* is `rePILOT`; `importlib.metadata` normalises the
    # name, so it must be asked for the normalised spelling.
    assert importlib.metadata.version(DIST_NAME.lower()) == __version__


def test_the_distribution_is_named_repilot(metadata: dict[str, Any]) -> None:
    """The distribution is ``rePILOT``, because ``pypilot`` is taken on PyPI.

    The importable package is *still* ``pypilot`` - renaming it would break
    every import in the docs and tests for no benefit - so this asserts the two
    names are deliberately different, which is the thing a future tidy-up
    would otherwise "fix" by accident.
    """
    assert metadata["name"] == DIST_NAME
    assert (ROOT / "src" / "pypilot" / "__init__.py").exists(), (
        "the importable package keeps its own name; only the distribution changed"
    )


def test_the_package_reads_its_version_from_the_distribution(metadata: dict[str, Any]) -> None:
    """`pypilot.__version__` must look up the *distribution* name.

    This is a regression guard for a genuinely nasty one. Renaming the
    distribution to `rePILOT` left `__init__.py` asking for `"pypilot"`, and
    the very first `import pypilot` in the entire test suite died with
    `PackageNotFoundError` - every test in the project failed at collection
    because of a one-word packaging change.

    The two names are now asserted equal here so a future rename breaks one
    obvious test instead of all of them.
    """
    import importlib

    package = importlib.import_module("pypilot")
    assert metadata["name"].lower() == package._DISTRIBUTION, (
        "__init__ asks importlib.metadata for the wrong distribution name; "
        "a rename will break every import in the suite at once"
    )


def test_the_repository_urls_point_at_the_current_repo(metadata: dict[str, Any]) -> None:
    """Every `project.urls` entry must name the repository that actually exists.

    A stale URL is the kind of thing nobody notices for a year.
    """
    for name, url in metadata["urls"].items():
        assert "grobertson" in url, f"{name} points somewhere unexpected: {url}"
        assert url.startswith("https://github.com/grobertson/"), f"{name}: {url}"


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
# Archive contents
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_a_built_sdist_contains_no_build_artifacts(tmp_path: Path) -> None:
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

    for needle in BUILD_ARTIFACTS:
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

    for needle in BUILD_ARTIFACTS:
        offenders = [name for name in names if needle in name]
        assert not offenders, f"{archives[0].name} contains {needle}: {offenders[:5]}"

    assert any(name.endswith("pypilot/py.typed") for name in names), "PEP 561 marker"
    assert any(name.endswith("pypilot/cli.py") for name in names), "the entry point module"
    assert any("dist-info/METADATA" in name for name in names), "core metadata"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
