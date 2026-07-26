# GitHub Actions workflow library

[![Validate library](https://github.com/sudo-kraken/github-actions-workflow-library/actions/workflows/validate-library.yml/badge.svg)](https://github.com/sudo-kraken/github-actions-workflow-library/actions/workflows/validate-library.yml)
[![MIT licence](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

A collection of GitHub Actions workflow files I use across my repositories.

The files are normal standalone workflows. I copy the ones I need into a
repository's `.github/workflows/` directory and edit the small configuration
section at the top. There are no reusable workflow calls, cross-repository
permissions or library commit references to maintain.

## Quick start

From a clone of this repository:

```bash
mkdir -p ../my-project/.github/workflows

cp workflow-templates/python-uv/python-ci.yml \
  ../my-project/.github/workflows/

cp workflow-templates/common/gitleaks.yml \
  ../my-project/.github/workflows/
```

The same files can be copied directly from GitHub after this repository is
published:

```bash
mkdir -p .github/workflows

curl -fsSL \
  https://raw.githubusercontent.com/sudo-kraken/github-actions-workflow-library/main/workflow-templates/python-uv/python-ci.yml \
  -o .github/workflows/python-ci.yml
```

The filenames are ready to use as-is. Review every copied file before committing
it; the comments at the top identify the values that normally need changing.

## Workflow catalogue

### Python with uv

| File | Purpose |
|---|---|
| `workflow-templates/python-uv/python-ci.yml` | Lockfile check, compile, Ruff, test matrix and coverage |
| `workflow-templates/python-uv/python-security.yml` | `pip-audit` and Bandit |
| `workflow-templates/python-uv/codeql-python.yml` | CodeQL analysis for Python |
| `workflow-templates/python-uv/python-package.yml` | Build wheel and source distributions on version tags |
| `workflow-templates/python-uv/uv-lock-check.yml` | Lightweight lockfile-only check |

The full CI workflow expects `pyproject.toml`, `uv.lock`, Ruff, pytest and
pytest-cov. Its default matrix is Python 3.12, 3.13 and 3.14 with a 75% coverage
gate. Edit those values for each repository.

An optional `.github/scripts/validate.sh` file is run by the Python CI workflow.
I use that for project-specific checks such as migrations, Compose validation
or generated-file consistency.

### Docker

| File | Purpose |
|---|---|
| `workflow-templates/docker/docker-ci.yml` | Pull-request build, configuration scan, image scan and optional smoke test |
| `workflow-templates/docker/docker-publish.yml` | Build by digest, scan, promote to GHCR, create an SBOM and attest the release |
| `workflow-templates/docker/devcontainer-smoke.yml` | Build and test a development container |

The Docker CI workflow defaults to pull requests, merge queues and manual runs.
The publish workflow handles pushes to `main`, version tags and manual runs, so
using both files does not duplicate the main-branch build.

The Docker publish workflow defaults to:

- GHCR;
- `linux/amd64` and `linux/arm64`;
- publication from `main`, `v*` tags and manual runs;
- `CRITICAL,HIGH` Trivy failures;
- a GitHub release with the generated SBOM for version tags.

Edit the configuration block at the top when a repository uses another
Dockerfile, build context, platform set or registry.

The Docker workflows look for `.github/scripts/container-smoke.sh`. It is
optional. Two starting points are included:

```text
scripts/container-smoke-http.sh
scripts/container-smoke-command.sh
```

Copy one into the target repository and adapt it:

```bash
mkdir -p ../my-project/.github/scripts
cp scripts/container-smoke-http.sh \
  ../my-project/.github/scripts/container-smoke.sh
```

### Common add-ons

| File | Purpose |
|---|---|
| `workflow-templates/common/dependency-review.yml` | Review dependency changes in pull requests |
| `workflow-templates/common/gitleaks.yml` | Scan the full Git history for secrets |
| `workflow-templates/common/codeql-actions.yml` | CodeQL analysis for GitHub Actions code |
| `workflow-templates/common/pr-title.yml` | Enforce conventional pull request titles |
| `workflow-templates/common/scorecard.yml` | OpenSSF Scorecard for public repositories |
| `workflow-templates/common/stale.yml` | Mark and close stale issues and pull requests |

## Suggested sets

For a Python package:

```text
python-uv/python-ci.yml
python-uv/python-security.yml
python-uv/codeql-python.yml
common/dependency-review.yml
common/gitleaks.yml
common/codeql-actions.yml
python-uv/python-package.yml
```

For a Python service that publishes a container, use the Python set plus:

```text
docker/docker-ci.yml
docker/docker-publish.yml
```

For a non-Python container repository:

```text
docker/docker-ci.yml
docker/docker-publish.yml
common/dependency-review.yml
common/gitleaks.yml
common/codeql-actions.yml
```

These are starting points rather than mandatory bundles. A repository should
only carry workflows that provide useful checks for that project.

Some GitHub security features depend on the target repository's settings and
plan. Leave out an unsupported optional workflow. For Docker publication,
remove the attestation steps and their permissions when attestations are not
available in the target repository.

## Renovate

`configs/renovate.json` is a starting configuration for repositories that use
these files. Copy it to the repository root as `renovate.json`. It updates full
GitHub Action commit pins, normal repository dependencies and the separately
pinned uv, Trivy, Gitleaks, Bandit and pip-audit versions.

Because each workflow is copied into the application repository, updates are
normal pull requests in that repository. There is no automatic coupling to
changes made here.

## Validation

Run the local checks with:

```bash
make check
```

The validator checks YAML parsing, standalone triggers, least-privilege job
permissions, timeouts, full action SHAs, checkout credential handling, embedded
Bash syntax, Docker promotion ordering and the Renovate configuration. The
repository validation workflow also runs actionlint against every template.
