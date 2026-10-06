# Releasing

rePILOT is published to PyPI with **trusted publishing** — no API token lives
in this repository, in its secrets, or in any build log. GitHub mints a
short-lived OIDC token for the job and PyPI exchanges it for an upload token.

> **Two names, on purpose.** The PyPI *distribution* is `rePILOT`; the
> importable *package* is still `pypilot`. The distribution had to be renamed
> because `pypilot` is taken on PyPI by an unrelated long-standing package, and
> renaming the import path too would have broken every import in the docs and
> tests for no benefit. So: `pip install repilot`, then
> `from pypilot import ...`.

## One-time setup

On the project's **Publishing** page — **https://pypi.org/manage/project/repilot/settings/publishing/**
— add a GitHub Actions publisher:

| Field | Value |
|---|---|
| PyPI project name | `rePILOT` (shown as `repilot` in the URL) |
| Owner | `groberts` |
| Repository name | `pypilot` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

Three of those are matched **exactly**, and a mismatch fails at upload time
rather than at setup time:

- the **workflow filename** must be exactly `publish.yml` (this file);
- the **owner** and **repository name** must match GitHub exactly:
  `groberts/pypilot`;
- the **environment name** must match the `environment:` block in the workflow,
  or is left blank on both sides.

The publisher only becomes active once the project has an owner and at least
one release; add the publisher *after* the project exists.

Then create a matching GitHub environment called `pypi` under
**Settings → Environments**. Leave **Required reviewers** enabled if you want
publishing to be a deliberate act rather than a side effect of tagging.

## Cutting a release

The first release is `1.0.0`; `repilot` does not exist on PyPI until it is
published. For later releases, use the version declared in `pyproject.toml`,
and release from an up-to-date `master`.

### How the PyPI version stays in sync

- **Every push and pull request:** the `pypi-sync` job in `ci.yml` runs
  `tools/check_pypi_sync.py`. It fails only if PyPI is *ahead* of
  `pyproject.toml`; an unreleased or already-published version passes.
- **Every tag:** `publish.yml` refuses to upload unless the repository is
  `groberts/pypilot`, the tag is on `master`/`main`, the tag equals the
  `pyproject.toml` version, and that version is **not** already on PyPI.

```console
# 1. Set the version. pyproject.toml is the single source of truth;
#    pypilot.__version__ reads it, so never edit the version by hand.
#    (SPEC.md §11 records the version for each stage.)

# 2. Run the full gate. All of it, because `publish.yml` runs all of it again.
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run --group docs sphinx-build -W -b html docs docs/_build/html
uv build
uv tool run twine check --strict dist/*

# 3. Commit, then tag. The tag MUST match the declared version, or the
#    workflow refuses to publish.
git add -A
git commit -m "Release X.Y.Z"
git tag -a vX.Y.Z -m "X.Y.Z"
git push origin master
git push origin vX.Y.Z
```

The tag push is what triggers the publish. The workflow then:

1. checks the tag matches `pyproject.toml`
2. runs ruff, mypy and pytest
3. builds and runs `twine check --strict`
4. uploads, with PEP 740 attestations

The tag check prevents publishing a version that does not match its tag.

## If a publish fails

- **The version is already on PyPI.** PyPI is immutable; you cannot replace a
  file. Bump the version and cut a new tag.
- **A tag fired but the version mismatched.** Fix `pyproject.toml`, commit, and
  move the tag: `git tag -f vX.Y.Z && git push -f origin vX.Y.Z`. Force-pushing
  a tag is acceptable here *only* because the release did not happen.
- **The publisher was not configured yet.** The job fails at the upload step
  with a 403 from PyPI. Add the publisher, then re-run the failed job from the
  Actions tab — the artifact is still within its 7-day retention.

## Verifying a release

```console
uv pip install --python .venv-check repilot==X.Y.Z
.venv-check/bin/pypilot --version
```

Or check the attestations, which tie the artifact to this repository and commit:
https://pypi.org/project/repilot/#attestations

## Before any bulk `git add -A`

```console
uv run python tools/scan_secrets.py
```

It greps everything Git would stage for PyPI tokens, GitHub PATs, AWS keys,
private key blocks and similar, and fails the operation.
