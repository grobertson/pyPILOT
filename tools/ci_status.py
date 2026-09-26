"""Report the conclusion of the newest CI run, compactly.

`gh run view --json` returns a large blob; this prints just the verdict and
the per-job conclusions, which is what actually gets read.
"""

from __future__ import annotations

import json
import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        ["gh", "run", "list", "--limit", "1", "--json", "status,conclusion,url,databaseId"],
        capture_output=True,
        text=True,
        check=True,
    )
    runs = json.loads(result.stdout)
    if not runs:
        print("no runs")
        return 1
    run = runs[0]
    print(f"run {run['databaseId']}: {run['status']} / {run['conclusion']}")
    print(run["url"])

    detail = subprocess.run(
        ["gh", "run", "view", str(run["databaseId"]), "--json", "conclusion,jobs"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(detail.stdout)
    for job in data.get("jobs", []):
        print(f"  {job['conclusion'] or job['status']:8} {job['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
