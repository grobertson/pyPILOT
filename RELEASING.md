# Releasing

The `rePILOT` distribution is published to PyPI as `repilot`. The importable
Python package remains `pypilot`, so users install with `pip install repilot`
and import with `from pypilot import ...`.

The first stable release, `1.0.0`, was published on 2026-09-26. PyPI releases
are immutable, so every release needs a new version declared in `pyproject.toml`.

## Publishing setup

Publishing uses **PyPI trusted publishing**. GitHub Actions gets a short-lived
OIDC token; no PyPI API token should be stored in this repository or its GitHub
secrets.

The canonical repository is `grobertson/pyPILOT` (the configured `origin`). On
the PyPI project's Publishing page, configure this GitHub Actions publisher:

| Field | Value |
|---|---|
| PyPI project | `repilot` |
| GitHub owner | `grobertson` |
| GitHub repository | `pyPILOT` |
| Workflow filename | `publish.yml` |
| GitHub environment | `pypi` |

Remove the obsolete `groberts/pypilot` publisher if present. All publisher
fields must match exactly; a mismatch makes trusted publishing fail. Create the
GitHub `pypi` environment under **Settings → Environments**. Configure required
reviewers there if publishing should require approval.

## Release procedure

Release manually means preparing and pushing a version tag. The tag starts the
GitHub Actions workflow, which verifies and publishes the distributions. Do not
upload from a developer machine with Twine; this project uses trusted
publishing.

1. Confirm the PyPI trusted publisher and GitHub `pypi` environment match the
   setup above. Start from an up-to-date `master` and require CI to pass before
   tagging.
2. Choose a new version. Update `project.version` in `pyproject.toml`, add a
   dated entry to `CHANGELOG.md`, then run `uv lock` to refresh the local
   package entry in `uv.lock`. `pyproject.toml` is the version source of truth;
   `pypilot.__version__` reads the installed distribution metadata.
3. Run the local release checks:

```console
uv lock --check
uv sync --all-extras --dev
uv run python tools/check_pypi_sync.py --require-unpublished
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python tools/check_workflows.py
uv run python tools/check_embedded_python.py
uv run --group docs sphinx-build -W -b html docs docs/_build/html
uv build
uv run python tools/check_wheel_install_step.py
```

`check_wheel_install_step.py` selects the wheel whose metadata matches
`pyproject.toml`, installs it into a temporary environment, and runs the CLI.
It distinguishes the current wheel from stale files left in `dist/`. The full CI
matrix repeats the clean-wheel smoke test on Linux, Windows, and macOS with
Python 3.12 and 3.13; require CI to pass before tagging.

Check the freshly built artifacts with Twine. On PowerShell, pass the two
versioned artifact paths explicitly because native commands do not reliably
expand `dist/*`:

```powershell
uv tool run twine check --strict dist/repilot-X.Y.Z.tar.gz dist/repilot-X.Y.Z-py3-none-any.whl
```

Replace `X.Y.Z` with the selected version. CI additionally inspects the
archives for accidentally packaged build artifacts.

4. Review the exact files to include. Stage only those files, inspect the
   staged diff, and run the secret scan:

```console
git status --short
git add pyproject.toml uv.lock CHANGELOG.md
# Add any other intentional release, workflow, test, or documentation changes explicitly.
git diff --cached --check
git diff --cached
uv run python tools/scan_secrets.py
```

5. Commit and push the commit to the default branch, then create and push a tag
   whose version exactly matches `pyproject.toml`:

```console
git commit -m "Release X.Y.Z"
git push origin master
git tag -a vX.Y.Z -m "X.Y.Z"
git push origin vX.Y.Z
```

Replace every `X.Y.Z` with the chosen version. The tagged commit must be
reachable from `master` or `main`. Pushing the tag starts `publish.yml`; monitor
the run in GitHub Actions and approve the `pypi` environment if it requires
review. The workflow checks repository identity, default-branch ancestry,
tag/version match, and that the version is not already on PyPI; it then runs
Ruff, mypy, pytest, builds the distributions, checks them with Twine, verifies
the archives contain no build artifacts, and publishes with PEP 740
attestations.

`workflow_dispatch` is **not a dry run**: it can reach the real publish job if
the checks pass. Use a disposable test project for workflow experiments rather
than dispatching this workflow as a release rehearsal.

### Version synchronization

The `pypi-sync` CI job runs `tools/check_pypi_sync.py` on pushes and pull
requests. It fails when PyPI is ahead of `pyproject.toml`; an unpublished local
version is allowed. The release workflow uses `--require-unpublished` so it
refuses a duplicate release.

## Failures and verification

- **Version already exists on PyPI:** published files cannot be replaced. Bump
  the version and create a new release.
- **Tag/version mismatch:** correct `pyproject.toml`, commit the correction,
  then recreate the tag only if publication did not succeed. Never move a tag
  for a version already published.
- **Trusted-publisher 403:** verify the PyPI publisher's owner, repository,
  workflow filename, and environment against the actual GitHub repository and
  `.github/workflows/publish.yml`, then rerun the failed workflow if its
  verified artifact is still retained.

After a successful run, verify the version at
https://pypi.org/project/repilot/ and check its attestations at
https://pypi.org/project/repilot/#attestations. A quick installed CLI check is:

```console
uv tool run --from repilot==X.Y.Z pypilot --version
```