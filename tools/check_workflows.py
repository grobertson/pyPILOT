"""Validate the workflow YAML and check the things most likely to be wrong.

YAML that parses is not the same as a workflow that will work, and the failures
that matter here are the quiet ones: a tag trigger that never matches, a
permission the action needs but the job does not have, and a `permissions`
block that silently drops a default. So this checks structure *and* those
specific mistakes.

    uv run python tools/check_workflows.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def check_ci(data: dict) -> list[str]:
    problems: list[str] = []
    jobs = data.get("jobs", {})

    if "test" not in jobs:
        return ["ci.yml has no `test` job"]

    matrix = jobs["test"].get("strategy", {}).get("matrix", {})
    oses = set(matrix.get("os", []))
    if len(oses) < 3:
        problems.append(f"ci.yml matrix covers {sorted(oses)}, not 3 operating systems")

    names = {step.get("name") for step in jobs["test"].get("steps", [])}
    if not any(n == "Build" for n in names):
        problems.append("ci.yml has no Build step")
    if not any("clean environment" in str(n) for n in names):
        problems.append("ci.yml never installs the built wheel in a clean environment")

    for step in jobs["docs"].get("steps", []):
        command = str(step.get("run", ""))
        if "sphinx-build" in command and "-W" not in command:
            problems.append("ci.yml builds docs without -W, so a warning would pass")
    if "pypi-sync" not in jobs:
        problems.append("ci.yml has no `pypi-sync` job comparing the version with PyPI")
    return problems


def check_publish(data: dict) -> list[str]:
    problems: list[str] = []
    jobs = data.get("jobs", {})

    triggers = data.get("on") or data.get(True) or {}
    tags = triggers.get("push", {}).get("tags", [])
    if not tags:
        problems.append("publish.yml has no tag trigger, so it would never fire")
    elif not any(t.startswith("v") for t in tags):
        problems.append(f"publish.yml tag trigger {tags} will not match a v1.0.0 tag")

    permissions = data.get("permissions", {})
    if permissions.get("id-token") != "write":
        problems.append(
            "publish.yml lacks `id-token: write`, which trusted publishing "
            "requires - PyPI exchanges an OIDC token and the action cannot "
            "upload without it"
        )
    if permissions.get("contents") != "read":
        problems.append("publish.yml should keep `contents: read` (least privilege)")

    if "verify" not in jobs or "publish" not in jobs:
        return [*problems, "publish.yml needs a verify job and a publish job"]
    if jobs["publish"].get("needs") != "verify":
        problems.append("the publish job must depend on verify, or a red build can still release")

    if "environment" not in jobs["publish"]:
        problems.append("the publish job needs `environment: pypi` to match the trusted publisher")
    elif jobs["publish"]["environment"].get("name") != "pypi":
        problems.append("the publish environment must be named `pypi`")

    steps = jobs["publish"].get("steps", [])
    action = " ".join(str(s.get("uses", "")) for s in steps)
    if "gh-action-pypi-publish" not in action:
        problems.append("publish.yml does not use pypa/gh-action-pypi-publish")
    if "download-artifact" not in action:
        problems.append("publish.yml does not download the verified artifacts")

    verify_steps = jobs["verify"].get("steps", [])
    if not any("tag must match" in str(s.get("name", "")) for s in verify_steps):
        problems.append("publish.yml does not check that the tag matches the declared version")
    if not any(
        "check_pypi_sync.py --require-unpublished" in str(s.get("run", "")) for s in verify_steps
    ):
        problems.append("publish.yml does not check the version is unpublished on PyPI")
    return problems


def main() -> int:
    failures = 0
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        print(f"== {path.name} ==")
        try:
            data = load(path)
        except yaml.YAMLError as exc:
            print(f"  YAML ERROR: {exc}")
            failures += 1
            continue

        if path.name == "ci.yml":
            problems = check_ci(data)
        elif path.name == "publish.yml":
            problems = check_publish(data)
        else:
            problems = []

        if problems:
            failures += 1
            for problem in problems:
                print(f"  PROBLEM: {problem}")
        else:
            print("  ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
