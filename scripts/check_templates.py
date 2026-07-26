#!/usr/bin/env python3
"""Validate the copyable workflow templates in this repository."""

from __future__ import annotations

import json
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "workflow-templates"
FULL_ACTION_SHA = re.compile(r"^[^\s@]+@[0-9a-f]{40}$")
UNSAFE_SHELL_CONTEXT = re.compile(
    r"\$\{\{\s*(?:github|matrix|needs|steps|secrets|inputs)\."
)
INVALID_ENV_SELF_REFERENCE = re.compile(r"\$\{\{\s*env\.")
IGNORED_PATH_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}
EXPECTED_TEMPLATES = {
    "common/codeql-actions.yml",
    "common/dependency-review.yml",
    "common/gitleaks.yml",
    "common/pr-title.yml",
    "common/scorecard.yml",
    "common/stale.yml",
    "docker/docker-ci.yml",
    "docker/devcontainer-smoke.yml",
    "docker/docker-publish.yml",
    "python-uv/python-ci.yml",
    "python-uv/codeql-python.yml",
    "python-uv/python-package.yml",
    "python-uv/python-security.yml",
    "python-uv/uv-lock-check.yml",
}


class WorkflowLoader(yaml.SafeLoader):
    """Load workflow YAML without treating ``on`` as a boolean."""


for first_char, resolvers in list(WorkflowLoader.yaml_implicit_resolvers.items()):
    WorkflowLoader.yaml_implicit_resolvers[first_char] = [
        resolver
        for resolver in resolvers
        if resolver[0] != "tag:yaml.org,2002:bool"
    ]

WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.load(handle, Loader=WorkflowLoader)
    if not isinstance(data, dict):
        raise AssertionError(f"{path}: top-level YAML value must be a mapping")
    return data


def bash_errors(label: str, script: str) -> list[str]:
    result = subprocess.run(
        ["bash", "-n"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return []
    detail = result.stderr.strip() or "bash reported a syntax error"
    return [f"{label}: {detail}"]


def iter_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    raw_steps = job.get("steps", [])
    if not isinstance(raw_steps, list):
        return []
    return [step for step in raw_steps if isinstance(step, dict)]


def validate_workflow(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = load_yaml(path)
    except (OSError, yaml.YAMLError, AssertionError) as exc:
        return [f"{path}: {exc}"]

    triggers = data.get("on")
    if not isinstance(triggers, dict) or not triggers:
        errors.append(f"{path}: on must be a non-empty mapping")
    else:
        if "workflow_call" in triggers:
            errors.append(f"{path}: reusable workflow_call is not allowed")
        if "pull_request_target" in triggers:
            errors.append(f"{path}: pull_request_target is not allowed")

    if data.get("permissions") != {}:
        errors.append(f"{path}: top-level permissions must be an empty mapping")

    workflow_env = data.get("env", {})
    if workflow_env is not None and not isinstance(workflow_env, dict):
        errors.append(f"{path}: top-level env must be a mapping")
    elif isinstance(workflow_env, dict):
        for name, value in workflow_env.items():
            if isinstance(value, str) and INVALID_ENV_SELF_REFERENCE.search(value):
                errors.append(
                    f"{path}: top-level env {name} cannot reference the env context"
                )

    jobs = data.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        errors.append(f"{path}: jobs must be a non-empty mapping")
        return errors

    for job_id, raw_job in jobs.items():
        if not isinstance(raw_job, dict):
            errors.append(f"{path}: job {job_id} must be a mapping")
            continue
        if "uses" in raw_job:
            errors.append(f"{path}: job {job_id} calls another workflow")
        if "runs-on" not in raw_job:
            errors.append(f"{path}: job {job_id} has no runs-on")
        timeout = raw_job.get("timeout-minutes")
        if timeout is None:
            errors.append(f"{path}: job {job_id} has no timeout-minutes")
        elif not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            errors.append(
                f"{path}: job {job_id} timeout-minutes must be a positive integer"
            )
        if not isinstance(raw_job.get("permissions"), dict):
            errors.append(f"{path}: job {job_id} must declare permissions")

        job_env = raw_job.get("env", {})
        if job_env is not None and not isinstance(job_env, dict):
            errors.append(f"{path}: job {job_id} env must be a mapping")
        elif isinstance(job_env, dict):
            for name, value in job_env.items():
                if isinstance(value, str) and INVALID_ENV_SELF_REFERENCE.search(value):
                    errors.append(
                        f"{path}: job {job_id} env {name} cannot reference "
                        "the env context"
                    )

        raw_steps = raw_job.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            errors.append(f"{path}: job {job_id} has no steps")
            continue

        for index, step in enumerate(iter_steps(raw_job), start=1):
            uses = step.get("uses")
            if isinstance(uses, str) and not uses.startswith("./"):
                if not FULL_ACTION_SHA.fullmatch(uses):
                    errors.append(
                        f"{path}: job {job_id} step {index} is not pinned "
                        f"to a full commit SHA: {uses}"
                    )

            if isinstance(uses, str) and uses.startswith("actions/checkout@"):
                with_values = step.get("with", {})
                credentials_disabled = (
                    isinstance(with_values, dict)
                    and str(with_values.get("persist-credentials", "")).lower()
                    == "false"
                )
                if not credentials_disabled:
                    errors.append(
                        f"{path}: job {job_id} checkout must set "
                        "persist-credentials: false"
                    )

            script = step.get("run")
            if isinstance(script, str):
                if step.get("shell") != "bash":
                    errors.append(
                        f"{path}: job {job_id} step {index} must explicitly use bash"
                    )
                if UNSAFE_SHELL_CONTEXT.search(script):
                    errors.append(
                        f"{path}: job {job_id} step {index} inserts a workflow "
                        "value directly into shell source"
                    )
                errors.extend(
                    bash_errors(f"{path}: job {job_id} step {index}", script)
                )

    return errors


def validate_content() -> list[str]:
    errors: list[str] = []
    template_paths = sorted(TEMPLATE_ROOT.rglob("*.yml"))
    actual_templates = {
        path.relative_to(TEMPLATE_ROOT).as_posix() for path in template_paths
    }
    missing = EXPECTED_TEMPLATES - actual_templates
    extra = actual_templates - EXPECTED_TEMPLATES
    if missing:
        errors.append(f"Missing workflow templates: {sorted(missing)}")
    if extra:
        errors.append(f"Unexpected workflow templates: {sorted(extra)}")

    names: dict[str, list[Path]] = {}
    for path in template_paths:
        names.setdefault(path.name, []).append(path)
        errors.extend(validate_workflow(path))

        copy_instruction = (
            f"Copy this file to .github/workflows/{path.name}"
        )
        header = "\n".join(path.read_text(encoding="utf-8").splitlines()[:5])
        if copy_instruction not in header:
            errors.append(
                f"{path}: header must include '{copy_instruction}'"
            )

    duplicate_names = {
        name: paths for name, paths in names.items() if len(paths) > 1
    }
    if duplicate_names:
        formatted = {
            name: [path.relative_to(ROOT).as_posix() for path in paths]
            for name, paths in duplicate_names.items()
        }
        errors.append(f"Template filenames must be unique: {formatted}")

    workflow_directory = ROOT / ".github" / "workflows"
    active_workflows = sorted(workflow_directory.glob("*.yml"))
    expected_active = [workflow_directory / "validate-library.yml"]
    if active_workflows != expected_active:
        errors.append(
            ".github/workflows must contain only validate-library.yml"
        )
    errors.extend(validate_workflow(expected_active[0]))

    for issue_form in sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")):
        try:
            load_yaml(issue_form)
        except (OSError, yaml.YAMLError, AssertionError) as exc:
            errors.append(f"{issue_form}: {exc}")

    python_ci = (TEMPLATE_ROOT / "python-uv" / "python-ci.yml").read_text(
        encoding="utf-8"
    )
    for required in (
        "uv lock --check",
        "uv sync --locked",
        "uv run --locked ruff format --check",
        "uv run --locked ruff check",
        "--cov-fail-under=75",
    ):
        if required not in python_ci:
            errors.append(f"python-uv/python-ci.yml is missing: {required}")

    python_security = (TEMPLATE_ROOT / "python-uv" / "python-security.yml").read_text(
        encoding="utf-8"
    )
    for required in ("pip-audit==", "bandit==", "uv export --locked"):
        if required not in python_security:
            errors.append(f"python-uv/python-security.yml is missing: {required}")

    docker_publish = (TEMPLATE_ROOT / "docker" / "docker-publish.yml").read_text(
        encoding="utf-8"
    )
    for required in (
        "Scan the exact candidate digest",
        "Record the approved digest",
        "Create the manifest from approved digests",
        "Generate build provenance",
        "Generate the SBOM attestation",
    ):
        if required not in docker_publish:
            errors.append(f"docker/docker-publish.yml is missing: {required}")

    scan_position = docker_publish.find("Scan the exact candidate digest")
    record_position = docker_publish.find("Record the approved digest")
    manifest_position = docker_publish.find("Create the manifest from approved digests")
    if not (0 <= scan_position < record_position < manifest_position):
        errors.append(
            "docker/docker-publish.yml must scan candidates before recording and promoting digests"
        )

    for script in sorted((ROOT / "scripts").glob("*.sh")):
        errors.extend(bash_errors(str(script), script.read_text(encoding="utf-8")))
        if not script.stat().st_mode & stat.S_IXUSR:
            errors.append(f"{script}: smoke-test script must be executable")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    referenced_paths = set(
        re.findall(
            r"(?:workflow-templates/[A-Za-z0-9_./-]+\.yml|"
            r"(?<!/)scripts/[A-Za-z0-9_.-]+\.sh|configs/renovate\.json)",
            readme,
        )
    )
    for reference in sorted(referenced_paths):
        if not (ROOT / reference).is_file():
            errors.append(f"README.md references missing file: {reference}")

    try:
        with (ROOT / "renovate.json").open(encoding="utf-8") as handle:
            json.load(handle)
        with (ROOT / "configs" / "renovate.json").open(encoding="utf-8") as handle:
            json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Renovate configuration is invalid: {exc}")

    for path in ROOT.rglob("*"):
        if not path.is_file() or any(
            part in IGNORED_PATH_PARTS for part in path.parts
        ):
            continue
        data = path.read_bytes()
        if b"\r\n" in data:
            errors.append(f"{path}: contains CRLF line endings")
        if data and not data.endswith(b"\n"):
            errors.append(f"{path}: missing final newline")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.rstrip() != line:
                errors.append(f"{path}:{line_number}: trailing whitespace")
        if any(character in text for character in "\u202a\u202b\u202d\u202e\u2066\u2067\u2068\u2069"):
            errors.append(f"{path}: contains bidirectional control characters")

    return errors


def main() -> int:
    errors = validate_content()
    if errors:
        print("Workflow template validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    count = len(list(TEMPLATE_ROOT.rglob("*.yml")))
    print(f"Validated {count} copyable workflow templates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
