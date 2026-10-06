"""Reproduce the two things that broke the CI clean-wheel-install step.

The step was written for three platforms at once and failed on Windows for two
reasons, neither of which a YAML linter can see:

1. ``dist/*.whl`` reached ``uv pip install`` as a literal, because PowerShell
   does not glob-expand a path passed to a native command.
2. ``a || b`` is a *bash* construct. PowerShell rejects ``||`` outright, so the
   Windows runner died before it could fall back to ``Scripts/``.

Rather than require a bash on the maintainer's machine - which this one does
not have - this checks the two properties that make the fixed step correct, and
does it in plain Python so it runs everywhere.

    uv run python tools/check_wheel_install_step.py
"""

from __future__ import annotations

import glob
import re
import subprocess
import sys
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def main() -> int:
    failures: list[str] = []

    # 1. The step must opt into bash, or the fallback logic is bash-only.
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    step_start = ci.index("Check the wheel installs and runs")
    step = ci[step_start : ci.index("\n      - name:", step_start + 10)]
    if "shell: bash" not in step:
        failures.append("the step does not set `shell: bash`, so `||` is PowerShell")
    if re.search(r"\.venv-wheel/\S+\s*\|\|", step):
        failures.append("the step still uses `||`, which PowerShell rejects")

    # 2. Select the wheel for this checkout, not a stale artifact from a prior build.
    wheels = sorted(glob.glob(str(ROOT / "dist" / "*.whl")))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    expected_name = project["name"].casefold()
    expected_version = project["version"]
    matching_wheels: list[str] = []
    for wheel in wheels:
        try:
            with zipfile.ZipFile(wheel) as archive:
                metadata_path = next(
                    path for path in archive.namelist() if path.endswith(".dist-info/METADATA")
                )
                metadata = BytesParser().parsebytes(archive.read(metadata_path))
        except (OSError, StopIteration, zipfile.BadZipFile) as exc:
            failures.append(f"could not read wheel metadata from {Path(wheel).name}: {exc}")
            continue
        if (
            metadata.get("Name", "").casefold() == expected_name
            and metadata.get("Version") == expected_version
        ):
            matching_wheels.append(wheel)

    wheel_path: str | None = None
    if len(matching_wheels) != 1:
        failures.append(
            f"expected exactly one {project['name']} {expected_version} wheel in dist/, "
            f"found {len(matching_wheels)}"
        )
    else:
        wheel_path = matching_wheels[0]
        print(f"selected wheel: {Path(wheel_path).name}")

    # 3. The executable-name choice must cover both layouts without `||`.
    if "[ -x .venv-wheel/bin/pypilot ]" not in step:
        failures.append("the step does not choose between the posix and windows layouts")

    # 4. And the real thing: install the matching wheel here and run it.
    if wheel_path is not None:
        with TemporaryDirectory(prefix="pypilot-wheelcheck-") as temp:
            venv = Path(temp) / ".venv"
            try:
                subprocess.run(
                    ["uv", "venv", str(venv), "--python", "3.12"],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["uv", "pip", "install", "--python", str(venv), wheel_path],
                    cwd=ROOT,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                if sys.platform == "win32":
                    exe = venv / "Scripts" / "pypilot.exe"
                else:
                    exe = venv / "bin" / "pypilot"
                if not exe.exists():
                    failures.append(f"the console script is not where the step looks: {exe}")
                else:
                    version = subprocess.run(
                        [str(exe), "--version"], check=True, capture_output=True, text=True
                    )
                    print(f"installed wheel reports: {version.stdout.strip()}")

                    program = Path(temp) / "check.pilot"
                    program.write_text("T:HELLO FROM THE INSTALLED WHEEL\n", encoding="utf-8")
                    run_out = subprocess.run(
                        [str(exe), str(program)], check=True, capture_output=True, text=True
                    )
                    if "HELLO FROM THE INSTALLED WHEEL" not in run_out.stdout:
                        failures.append("the installed wheel ran but printed nothing")
                    else:
                        print("installed wheel ran a program successfully")
            except subprocess.CalledProcessError as exc:
                failures.append(f"a command failed: {exc.stderr or exc.stdout}")

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("\nall good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
