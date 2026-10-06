"""Tests for tools/check_pypi_sync.py, the PyPI version comparison."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_pypi_sync", ROOT / "tools/check_pypi_sync.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = _load()


def test_an_unpublished_project_is_fine() -> None:
    ok, _ = sync.check("1.0.0", [], require_unpublished=True)
    assert ok


def test_a_new_version_ahead_of_pypi_is_fine() -> None:
    ok, _ = sync.check("1.1.0", ["1.0.0"], require_unpublished=True)
    assert ok


def test_a_published_version_passes_ci_but_blocks_a_release() -> None:
    assert sync.check("1.0.0", ["1.0.0"], require_unpublished=False)[0]
    assert not sync.check("1.0.0", ["1.0.0"], require_unpublished=True)[0]


def test_a_version_behind_pypi_always_fails() -> None:
    assert not sync.check("1.0.0", ["1.0.0", "1.2.0"], require_unpublished=False)[0]


def test_versions_compare_numerically_not_as_text() -> None:
    ok, _ = sync.check("1.10.0", ["1.9.0"], require_unpublished=True)
    assert ok


def test_pre_release_versions_are_rejected_loudly() -> None:
    with pytest.raises(ValueError, match=r"final X\.Y\.Z"):
        sync.version_key("1.0.0rc1")


def test_the_declared_version_is_a_final_release() -> None:
    name, version = sync.declared()
    assert name == "rePILOT"
    assert sync.version_key(version)
