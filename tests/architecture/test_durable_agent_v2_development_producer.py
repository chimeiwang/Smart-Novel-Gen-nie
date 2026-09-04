from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import runpy
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/durable-agent-v2-development-evidence.yml"
HELPER = ROOT / "scripts/durable_agent_v2_development_producer.py"
CONTROL_HELPER = ROOT / "scripts/durable_agent_v2_control_bundle.py"
EVIDENCE_TEST = ROOT / "tests/architecture/test_durable_agent_v2_development_evidence_v2.py"

TARGET = "1" * 40
REPOSITORY = "owner/repository"
RUN_ID = "12345"
RUN_ATTEMPT = "1"
WEB = "sha256:" + "2" * 64
CORE = "sha256:" + "3" * 64
AGENT = "sha256:" + "4" * 64
EXECUTION = "5" * 64

POLICY_NAMES = (
    "DURABLE_AGENT_V2_DEVELOPMENT_BUILD_DEFINITION_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_CANARY_SCENARIO_FINGERPRINT",
    "DURABLE_AGENT_V2_DEVELOPMENT_DEVELOPMENT_SCOPE_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_EXECUTION_MANIFEST_FINGERPRINT",
    "DURABLE_AGENT_V2_DEVELOPMENT_MIGRATION_QUALIFICATION_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_IDENTITY_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_POLICY_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_RESOURCE_HOST_IDENTITY_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_RESOURCE_POLICY_SHA256",
)
INTEGER_POLICY_VALUES = {
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_COMPLETION_TOKENS": "100",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_COST_MICROS": "2000",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_PROMPT_TOKENS": "200",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_REASONING_TOKENS": "40",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_TOTAL_TOKENS": "300",
}


def _run(
    arguments: list[str],
    *,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- 参数完全由本测试构造
        [sys.executable, str(HELPER), *arguments],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_control(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- 参数完全由本测试构造
        [sys.executable, str(CONTROL_HELPER), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _producer_module() -> Any:
    scripts_path = str(ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    return importlib.import_module("durable_agent_v2_development_producer")


def _git_source_tree_manifest(path: Path, *, target: str = TARGET) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        output.write(f"target {target}\0".encode("ascii"))
        output.flush()
        result = subprocess.run(  # noqa: S603 -- 只读取当前 Git tree
            ["/usr/bin/git", "ls-tree", "-rz", "--full-tree", "HEAD"],
            cwd=ROOT,
            stdout=output,
            check=False,
        )
    assert result.returncode == 0
    path.chmod(0o600)
    return path


def _checkout_hashes(source_tree_manifest: Path, *, target: str = TARGET) -> tuple[str, str]:
    producer = _producer_module()
    source_sha = hashlib.sha256(source_tree_manifest.read_bytes()).hexdigest()
    build_document = {
        "filesSha256": {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in producer.BUILD_DEFINITION_FILES
        },
        "format": producer.BUILD_DEFINITION_FORMAT,
    }
    build_sha = hashlib.sha256(_canonical(build_document)).hexdigest()
    assert producer.source_tree_sha256(source_tree_manifest, target_commit=target) == source_sha
    assert producer.build_definition_sha256(ROOT) == build_sha
    return source_sha, build_sha


def _canonical(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_bytes(_canonical(document))
    path.chmod(0o600)


def _environment_documents(tmp_path: Path) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = {
        name: tmp_path / f"{name}.json"
        for name in ("environment", "branches", "secrets", "variables")
    }
    _write_json(
        paths["environment"],
        {
            "deployment_branch_policy": {
                "custom_branch_policies": True,
                "protected_branches": False,
            },
            "name": "development",
            "protection_rules": [
                {
                    "prevent_self_review": True,
                    "reviewers": [
                        {"reviewer": {"id": 42}, "type": "User"},
                    ],
                    "type": "required_reviewers",
                }
            ],
        },
    )
    _write_json(
        paths["branches"],
        {"branch_policies": [{"name": "main"}], "total_count": 1},
    )
    _write_json(
        paths["secrets"],
        {
            "secrets": [{"name": "GH_ENVIRONMENT_POLICY_AUDIT_TOKEN"}],
            "total_count": 1,
        },
    )
    variables = []
    for name in POLICY_NAMES:
        value = hashlib.sha256(name.encode()).hexdigest()
        if name == "DURABLE_AGENT_V2_DEVELOPMENT_BUILD_DEFINITION_SHA256":
            value = _producer_module().build_definition_sha256(ROOT)
        elif name == "DURABLE_AGENT_V2_DEVELOPMENT_EXECUTION_MANIFEST_FINGERPRINT":
            value = EXECUTION
        variables.append({"name": name, "value": value})
    variables.extend(
        {"name": name, "value": value} for name, value in INTEGER_POLICY_VALUES.items()
    )
    variables.append(
        {
            "name": "DURABLE_AGENT_V2_DEVELOPMENT_PRODUCER_POLICY_VERSION",
            "value": "inkforge-durable-agent-v2-development-producer-policy/1",
        }
    )
    _write_json(
        paths["variables"],
        {"total_count": len(variables), "variables": variables},
    )
    return paths


def _environment_args(paths: dict[str, Path]) -> list[str]:
    return [
        "verify-environment-policy",
        "--environment-json",
        str(paths["environment"]),
        "--branch-policies-json",
        str(paths["branches"]),
        "--secrets-json",
        str(paths["secrets"]),
        "--variables-json",
        str(paths["variables"]),
    ]


def _checkout_args(
    variables: Path,
    source_tree_manifest: Path,
    *,
    expected_source_tree_sha256: str | None = None,
) -> list[str]:
    arguments = [
        "verify-checkout-bindings",
        "--repository-root",
        str(ROOT),
        "--source-tree-manifest",
        str(source_tree_manifest),
        "--target-release-commit",
        TARGET,
        "--variables-json",
        str(variables),
    ]
    if expected_source_tree_sha256 is not None:
        arguments.extend(["--expected-source-tree-sha256", expected_source_tree_sha256])
    return arguments


def _image_create_args(
    output: Path,
    source_tree_manifest: Path,
    *,
    run_attempt: str = RUN_ATTEMPT,
    target: str = TARGET,
) -> list[str]:
    source_tree_sha, build_definition_sha = _checkout_hashes(
        source_tree_manifest,
        target=target,
    )
    return [
        "create-images",
        "--repository",
        REPOSITORY,
        "--target-release-commit",
        target,
        "--run-id",
        RUN_ID,
        "--run-attempt",
        run_attempt,
        "--output-dir",
        str(output),
        "--web-digest",
        WEB,
        "--core-digest",
        CORE,
        "--agent-digest",
        AGENT,
        "--execution-manifest-fingerprint",
        EXECUTION,
        "--repository-root",
        str(ROOT),
        "--source-tree-manifest",
        str(source_tree_manifest),
        "--expected-source-tree-sha256",
        source_tree_sha,
        "--expected-build-definition-sha256",
        build_definition_sha,
    ]


def _image_verify_args(
    directory: Path,
    digest: str,
    source_tree_manifest: Path,
) -> list[str]:
    source_tree_sha, build_definition_sha = _checkout_hashes(source_tree_manifest)
    return [
        "verify-images",
        "--repository",
        REPOSITORY,
        "--target-release-commit",
        TARGET,
        "--run-id",
        RUN_ID,
        "--run-attempt",
        RUN_ATTEMPT,
        "--images-dir",
        str(directory),
        "--expected-sha256",
        digest,
        "--repository-root",
        str(ROOT),
        "--source-tree-manifest",
        str(source_tree_manifest),
        "--expected-source-tree-sha256",
        source_tree_sha,
        "--expected-build-definition-sha256",
        build_definition_sha,
    ]


def _plan_create_args(output: Path) -> list[str]:
    return [
        "create-blocked-plan",
        "--repository",
        REPOSITORY,
        "--target-release-commit",
        TARGET,
        "--run-id",
        RUN_ID,
        "--run-attempt",
        RUN_ATTEMPT,
        "--output-dir",
        str(output),
    ]


def _plan_verify_args(directory: Path, digest: str, action: str) -> list[str]:
    return [
        action,
        "--repository",
        REPOSITORY,
        "--target-release-commit",
        TARGET,
        "--run-id",
        RUN_ID,
        "--run-attempt",
        RUN_ATTEMPT,
        "--plan-dir",
        str(directory),
        "--expected-sha256",
        digest,
    ]


def _digest_from(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().rsplit(":", 1)[1]


def _refresh_bundle(directory: Path, summary_name: str) -> str:
    payload = (directory / summary_name).read_bytes()
    digest = _sha(payload)
    checksums = directory / "SHA256SUMS"
    checksums.write_text(f"{digest}  {summary_name}\n", encoding="ascii")
    checksums.chmod(0o600)
    return digest


def test_workflow_has_pre_checkout_trusted_context_and_global_concurrency() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert workflow["concurrency"] == {
        "group": "durable-agent-v2-development",
        "cancel-in-progress": False,
    }
    assert list(workflow["jobs"]) == [
        "trusted_context",
        "offline_validation",
        "development_evidence",
    ]
    assert all(job["runs-on"] == "ubuntu-24.04" for job in workflow["jobs"].values())
    assert "ubuntu-latest" not in WORKFLOW.read_text(encoding="utf-8")
    source = workflow["jobs"]["trusted_context"]
    assert "environment" not in source
    first = source["steps"][0]
    assert "uses" not in first
    assert "scripts/" not in first["run"]
    assert "secrets." not in json.dumps(first)
    checkout = source["steps"][1]
    assert checkout["with"]["ref"] == "${{ github.sha }}"


@pytest.mark.parametrize(
    ("overrides", "valid"),
    [
        ({}, True),
        ({"TRUSTED_EVENT_NAME": "push"}, False),
        ({"TRUSTED_REF": "refs/heads/feature"}, False),
        ({"TRUSTED_RUN_ATTEMPT": "2"}, False),
        ({"INPUT_TARGET_RELEASE_COMMIT": "2" * 40}, False),
        ({"TRUSTED_SHA": "g" * 40}, False),
    ],
)
def test_trusted_context_rejects_attack_before_checkout(
    tmp_path: Path,
    overrides: dict[str, str],
    valid: bool,
) -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = workflow["jobs"]["trusted_context"]["steps"][0]
    environment = os.environ.copy()
    environment.update(
        {
            "GITHUB_OUTPUT": str(tmp_path / "output"),
            "INPUT_TARGET_RELEASE_COMMIT": TARGET,
            "TRUSTED_EVENT_NAME": "workflow_dispatch",
            "TRUSTED_REF": "refs/heads/main",
            "TRUSTED_RUN_ATTEMPT": "1",
            "TRUSTED_RUN_ID": RUN_ID,
            "TRUSTED_SHA": TARGET,
        }
    )
    environment.update(overrides)
    result = subprocess.run(  # noqa: S603 -- 固定 workflow shell
        ["/bin/bash", "-c", step["run"]],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert (result.returncode == 0) is valid


def test_workflow_pins_every_action_and_keeps_remote_and_artifact_actions_absent() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    source = WORKFLOW.read_text(encoding="utf-8")
    uses = [
        step["uses"] for job in workflow["jobs"].values() for step in job["steps"] if "uses" in step
    ]
    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", value) for value in uses)
    assert set(uses) == {
        "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
        "actions/setup-java@c5195efecf7bdfc987ee8bae7a71cb8b11521c00",
        "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020",
        "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
        "astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78",
    }
    checkout_steps = [
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    ]
    assert checkout_steps
    assert all(step["with"]["persist-credentials"] is False for step in checkout_steps)
    assert "actions/upload-artifact" not in source
    assert "actions/download-artifact" not in source
    assert "durable-agent-v2-development-evidence" not in source
    assert re.search(r"\b(?:ssh|scp)\b", source) is None
    assert "DURABLE_AGENT_V2_DEVELOPMENT_SSH_PRIVATE_KEY" not in source
    assert "OPENAI_API_KEY" not in source


def test_offline_job_is_full_and_local_fault_is_only_a_prerequisite() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    offline = workflow["jobs"]["offline_validation"]
    assert "environment" not in offline
    source = "\n".join(step.get("run", "") for step in offline["steps"])
    for command in (
        "uv run ruff check .",
        "uv run mypy",
        "uv run pytest -q",
        "./mvnw verify",
        "npm run typecheck",
        "npm run lint",
        "npm run test:web",
        "npm run api:check",
        "npm run build",
        "--evidence-class local-fake-prerequisite-only",
        "create-blocked-plan",
        "verify-blocked-plan",
    ):
        assert command in source


def test_protected_job_orders_policy_provenance_and_fixed_block() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    protected = workflow["jobs"]["development_evidence"]
    assert protected["environment"] == {"name": "development"}
    names = [step["name"] for step in protected["steps"]]
    assert (
        names.index("采集 development environment 外部策略（仅 GitHub API）")
        < names.index("无令牌语义验证 development environment 外部策略")
        < names.index("确定性复验 checkout source 与 build definition")
    )
    assert names[-1] == ("固定阻断真实远程 driver、2C2G、provider 与 cleanup（零远程动作）")
    secret_steps = [step for step in protected["steps"] if "${{ secrets." in json.dumps(step)]
    assert [step["name"] for step in secret_steps] == [
        "采集 development environment 外部策略（仅 GitHub API）"
    ]
    token_step = secret_steps[0]
    assert set(token_step["env"]) == {"GH_TOKEN"}
    token_source = token_step["run"]
    assert "gh api" in token_source
    assert "python" not in token_source
    assert "scripts/" not in token_source
    helper_steps = [
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "scripts/durable_agent_v2_development_producer.py" in step.get("run", "")
    ]
    assert helper_steps
    assert all("GH_TOKEN" not in json.dumps(step) for step in helper_steps)
    assert all("${{ secrets." not in json.dumps(step) for step in helper_steps)
    protected_source = "\n".join(step.get("run", "") for step in protected["steps"])
    assert "git ls-tree -rz --full-tree" in protected_source
    assert "sha256sum" in protected_source
    assert "--expected-source-tree-sha256" in protected_source
    assert "verify-checkout-bindings" in protected_source
    assert "verify-prerequisites" not in protected_source
    assert "durable-agent-v2-candidate-evidence" not in protected_source
    for impossible_static_expected in (
        "DURABLE_AGENT_V2_DEVELOPMENT_IMAGE_PROVENANCE_SHA256",
        "DURABLE_AGENT_V2_DEVELOPMENT_CONTROL_BUNDLE_SHA256",
        "DURABLE_AGENT_V2_DEVELOPMENT_CANDIDATE_EVIDENCE_SHA256",
    ):
        assert impossible_static_expected not in protected_source


def test_environment_policy_is_semantic_and_forbids_remote_credentials(
    tmp_path: Path,
) -> None:
    paths = _environment_documents(tmp_path)
    valid = _run(_environment_args(paths))
    assert valid.returncode == 0, valid.stderr

    secrets = {"secrets": [{"name": "OPENAI_API_KEY"}], "total_count": 1}
    _write_json(paths["secrets"], secrets)
    forbidden = _run(_environment_args(paths))
    assert forbidden.returncode != 0
    assert "不得配置远程" in forbidden.stderr


@pytest.mark.parametrize(
    "attack",
    ["reviewer", "branch", "variable", "placeholder", "dynamic"],
)
def test_environment_policy_rejects_missing_or_untrusted_policy(
    tmp_path: Path,
    attack: str,
) -> None:
    paths = _environment_documents(tmp_path)
    if attack == "reviewer":
        document = json.loads(paths["environment"].read_text(encoding="utf-8"))
        document["protection_rules"] = []
        _write_json(paths["environment"], document)
    elif attack == "branch":
        _write_json(
            paths["branches"],
            {"branch_policies": [{"name": "feature"}], "total_count": 1},
        )
    else:
        document = json.loads(paths["variables"].read_text(encoding="utf-8"))
        if attack == "variable":
            document["variables"].pop()
            document["total_count"] -= 1
        elif attack == "dynamic":
            document["variables"].append(
                {
                    "name": "DURABLE_AGENT_V2_DEVELOPMENT_CANDIDATE_EVIDENCE_SHA256",
                    "value": "f" * 64,
                }
            )
            document["total_count"] += 1
        else:
            document["variables"][0]["value"] = "0" * 64
        _write_json(paths["variables"], document)
    result = _run(_environment_args(paths))
    assert result.returncode != 0


def test_checkout_bindings_recompute_tree_and_build_definition(
    tmp_path: Path,
) -> None:
    paths = _environment_documents(tmp_path / "policy")
    manifest = _git_source_tree_manifest(tmp_path / "source-tree.manifest")
    source_sha, _ = _checkout_hashes(manifest)
    valid = _run(
        _checkout_args(
            paths["variables"],
            manifest,
            expected_source_tree_sha256=source_sha,
        )
    )
    assert valid.returncode == 0, valid.stderr
    assert f":{source_sha}:" in valid.stdout

    wrong_source = _run(
        _checkout_args(
            paths["variables"],
            manifest,
            expected_source_tree_sha256="f" * 64,
        )
    )
    assert wrong_source.returncode != 0
    assert "source tree" in wrong_source.stderr

    wrong_target_arguments = _checkout_args(
        paths["variables"],
        manifest,
        expected_source_tree_sha256=source_sha,
    )
    target_option = wrong_target_arguments.index("--target-release-commit") + 1
    wrong_target_arguments[target_option] = "f" * 40
    wrong_target = _run(wrong_target_arguments)
    assert wrong_target.returncode != 0
    assert "manifest target" in wrong_target.stderr

    _replace_variables(
        paths["variables"],
        {"DURABLE_AGENT_V2_DEVELOPMENT_BUILD_DEFINITION_SHA256": "0" * 64},
    )
    zero_build = _run(_checkout_args(paths["variables"], manifest))
    assert zero_build.returncode != 0


def test_image_create_rejects_self_reported_or_zero_source_build_bindings(
    tmp_path: Path,
) -> None:
    manifest = _git_source_tree_manifest(tmp_path / "source-tree.manifest")
    arguments = _image_create_args(tmp_path / "images", manifest)
    assert "--source-tree-sha256" not in arguments
    assert "--build-definition-sha256" not in arguments

    source_option = arguments.index("--expected-source-tree-sha256") + 1
    arguments[source_option] = "0" * 64
    zero_source = _run(arguments)
    assert zero_source.returncode != 0
    assert "source tree" in zero_source.stderr

    build_arguments = _image_create_args(tmp_path / "build-images", manifest)
    build_option = build_arguments.index("--expected-build-definition-sha256") + 1
    build_arguments[build_option] = "0" * 64
    zero_build = _run(build_arguments)
    assert zero_build.returncode != 0
    assert "build definition" in zero_build.stderr


def test_image_provenance_is_canonical_immutable_and_run_attempt_one(
    tmp_path: Path,
) -> None:
    source_tree_manifest = _git_source_tree_manifest(tmp_path / "source-tree.manifest")
    images = tmp_path / "images"
    digest = _digest_from(_run(_image_create_args(images, source_tree_manifest)))
    verified = _run(_image_verify_args(images, digest, source_tree_manifest))
    assert verified.returncode == 0, verified.stderr
    assert stat.S_IMODE(images.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in images.iterdir())

    rerun = _run(
        _image_create_args(
            tmp_path / "rerun",
            source_tree_manifest,
            run_attempt="2",
        )
    )
    assert rerun.returncode != 0
    assert "runAttempt=1" in rerun.stderr


@pytest.mark.parametrize(
    "attack",
    ["commit", "digest", "source", "build", "extra", "checksum"],
)
def test_image_provenance_rejects_drift(tmp_path: Path, attack: str) -> None:
    source_tree_manifest = _git_source_tree_manifest(tmp_path / "source-tree.manifest")
    images = tmp_path / "images"
    digest = _digest_from(_run(_image_create_args(images, source_tree_manifest)))
    document_path = images / "development-images.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    if attack == "commit":
        document["targetReleaseCommit"] = "f" * 40
        document["producer"]["headSha"] = "f" * 40
    elif attack == "digest":
        document["images"]["core"] = document["images"]["web"]
    elif attack == "source":
        document["sourceTreeSha256"] = "f" * 64
    elif attack == "build":
        document["buildDefinitionSha256"] = "e" * 64
    elif attack == "extra":
        document["untrusted"] = True
    else:
        document_path.write_bytes(document_path.read_bytes() + b" ")
        result = _run(_image_verify_args(images, digest, source_tree_manifest))
        assert result.returncode != 0
        return
    _write_json(document_path, document)
    drifted = _refresh_bundle(images, "development-images.json")
    result = _run(_image_verify_args(images, drifted, source_tree_manifest))
    assert result.returncode != 0


def test_blocked_plan_is_canonical_and_assertion_always_fails(tmp_path: Path) -> None:
    plan = tmp_path / "plan"
    digest = _digest_from(_run(_plan_create_args(plan)))
    verified = _run(_plan_verify_args(plan, digest, "verify-blocked-plan"))
    blocked = _run(_plan_verify_args(plan, digest, "assert-remote-blocked"))
    assert verified.returncode == 0, verified.stderr
    assert blocked.returncode != 0
    assert "未实现" in blocked.stderr


def test_remote_capabilities_unavailable_helper_always_fails() -> None:
    unavailable = _run(
        [
            "assert-remote-capabilities-unavailable",
            "--repository",
            REPOSITORY,
            "--target-release-commit",
            TARGET,
            "--run-id",
            RUN_ID,
            "--run-attempt",
            RUN_ATTEMPT,
        ]
    )
    assert unavailable.returncode != 0
    assert "未实现" in unavailable.stderr


@pytest.mark.parametrize("attack", ["fake", "ready", "cleanup", "extra"])
def test_local_fake_or_missing_cleanup_cannot_turn_blocked_plan_ready(
    tmp_path: Path,
    attack: str,
) -> None:
    plan = tmp_path / "plan"
    _digest_from(_run(_plan_create_args(plan)))
    document_path = plan / "development-remote-plan.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    if attack == "fake":
        document["providerMode"] = "fake"
    elif attack == "ready":
        document["decision"] = "ready"
    elif attack == "cleanup":
        document["reasonCodes"].remove("route-off-cleanup-unavailable")
    else:
        document["summarySha256"] = "f" * 64
    _write_json(document_path, document)
    digest = _refresh_bundle(plan, "development-remote-plan.json")
    result = _run(_plan_verify_args(plan, digest, "verify-blocked-plan"))
    assert result.returncode != 0


def _replace_variables(variables_path: Path, replacements: dict[str, str]) -> None:
    document = json.loads(variables_path.read_text(encoding="utf-8"))
    for item in document["variables"]:
        if item["name"] in replacements:
            item["value"] = replacements[item["name"]]
    _write_json(variables_path, document)


def _prerequisite_args(
    variables: Path,
    images: Path,
    control: Path,
    qualification: Path,
    run_json: Path,
    source_tree_manifest: Path,
    expected_source_tree_sha256: str,
    candidate: Path | None = None,
    candidate_run_json: Path | None = None,
    repository: str = REPOSITORY,
    target: str = TARGET,
    run_id: str = RUN_ID,
    run_attempt: str = RUN_ATTEMPT,
) -> list[str]:
    candidate = candidate or qualification.parent / "missing-candidate"
    candidate_run_json = candidate_run_json or qualification.parent / "missing-candidate-run.json"
    return [
        "verify-prerequisites",
        "--repository",
        repository,
        "--target-release-commit",
        target,
        "--run-id",
        run_id,
        "--run-attempt",
        run_attempt,
        "--variables-json",
        str(variables),
        "--images-dir",
        str(images),
        "--control-bundle-dir",
        str(control),
        "--qualification-dir",
        str(qualification),
        "--qualification-run-json",
        str(run_json),
        "--candidate-dir",
        str(candidate),
        "--candidate-run-json",
        str(candidate_run_json),
        "--repository-root",
        str(ROOT),
        "--source-tree-manifest",
        str(source_tree_manifest),
        "--expected-source-tree-sha256",
        expected_source_tree_sha256,
    ]


def test_missing_images_control_or_qualification_fail_before_external_actions(
    tmp_path: Path,
) -> None:
    paths = _environment_documents(tmp_path)
    source_tree_manifest = _git_source_tree_manifest(tmp_path / "source-tree.manifest")
    source_tree_sha, _ = _checkout_hashes(source_tree_manifest)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    counter = tmp_path / "external-counter"
    for name in ("ssh", "scp", "artifact-upload"):
        executable = fake_bin / name
        executable.write_text(
            '#!/bin/sh\nprintf x >> "$EXTERNAL_COUNTER"\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)
    environment = os.environ.copy()
    environment.update(
        {
            "EXTERNAL_COUNTER": str(counter),
            "PATH": f"{fake_bin}:{environment['PATH']}",
        }
    )

    missing_images = _run(
        _prerequisite_args(
            paths["variables"],
            tmp_path / "missing-images",
            tmp_path / "missing-control",
            tmp_path / "missing-qualification",
            tmp_path / "missing-run.json",
            source_tree_manifest,
            source_tree_sha,
        ),
        environment=environment,
    )
    assert missing_images.returncode != 0
    assert not counter.exists()

    images = tmp_path / "images"
    _digest_from(_run(_image_create_args(images, source_tree_manifest)))
    missing_control = _run(
        _prerequisite_args(
            paths["variables"],
            images,
            tmp_path / "missing-control",
            tmp_path / "missing-qualification",
            tmp_path / "missing-run.json",
            source_tree_manifest,
            source_tree_sha,
        ),
        environment=environment,
    )
    assert missing_control.returncode != 0
    assert "control bundle" in missing_control.stderr
    assert not counter.exists()

    control = tmp_path / "control"
    control_result = _run_control(
        [
            "create",
            "--repository-root",
            str(ROOT),
            "--output-dir",
            str(control),
            "--workflow-trusted-commit",
            TARGET,
            "--target-release-commit",
            TARGET,
            "--producer-run-id",
            RUN_ID,
            "--producer-run-attempt",
            RUN_ATTEMPT,
        ]
    )
    _digest_from(control_result)
    missing_qualification = _run(
        _prerequisite_args(
            paths["variables"],
            images,
            control,
            tmp_path / "missing-qualification",
            tmp_path / "missing-run.json",
            source_tree_manifest,
            source_tree_sha,
        ),
        environment=environment,
    )
    assert missing_qualification.returncode != 0
    assert "evidence bundle" in missing_qualification.stderr or "不存在" in (
        missing_qualification.stderr
    )
    assert not counter.exists()


def test_cross_repository_qualification_and_matching_run_json_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixtures = runpy.run_path(str(EVIDENCE_TEST))
    current = datetime.now(UTC).replace(microsecond=0)
    fixture_globals = fixtures["_qualification_reports"].__globals__
    fixture_globals["NOW"] = current.strftime("%Y-%m-%dT%H:%M:%SZ")
    fixture_globals["QUALIFICATION_ISSUED"] = (current - timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    fixture_globals["QUALIFICATION_EXPIRES"] = (current + timedelta(days=10)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    attacker_repository = "attacker/forged-repository"
    fixture_globals["REPOSITORY"] = attacker_repository

    qualification_reports = tmp_path / "qualification-reports"
    qualification = tmp_path / "qualification"
    fixtures["_report_source"](
        qualification_reports,
        fixtures["_qualification_reports"](),
        fixtures["QUALIFICATION_FILES"],
    )
    qualification_sha = fixtures["_created_digest"](
        fixtures["_run"](
            fixtures["_qualification_create_args"](
                qualification_reports,
                qualification,
            )
        )
    )
    qualification_document = json.loads(
        (qualification / "migration-qualification.json").read_text(encoding="utf-8")
    )
    assert qualification_document["producer"]["repository"] == attacker_repository

    forged_run = tmp_path / "qualification-run.json"
    _write_json(
        forged_run,
        {
            "conclusion": "success",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": qualification_document["producer"]["headSha"],
            "id": int(qualification_document["producer"]["runId"]),
            "path": ".github/workflows/durable-agent-v2-development-evidence.yml",
            "repository": {"full_name": attacker_repository},
            "run_attempt": 1,
            "status": "completed",
        },
    )

    policy_paths = _environment_documents(tmp_path / "policy")
    _replace_variables(
        policy_paths["variables"],
        {
            "DURABLE_AGENT_V2_DEVELOPMENT_MIGRATION_QUALIFICATION_SHA256": (qualification_sha),
            "DURABLE_AGENT_V2_DEVELOPMENT_DEVELOPMENT_SCOPE_SHA256": fixtures["DEVELOPMENT_SCOPE"],
        },
    )
    variables_document = json.loads(policy_paths["variables"].read_text(encoding="utf-8"))
    variables = {item["name"]: item["value"] for item in variables_document["variables"]}

    scripts_path = str(ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    producer = importlib.import_module("durable_agent_v2_development_producer")
    monkeypatch.setattr(
        producer,
        "verify_images",
        lambda *_args, **_kwargs: (
            {
                "executionManifestFingerprint": variables[
                    "DURABLE_AGENT_V2_DEVELOPMENT_EXECUTION_MANIFEST_FINGERPRINT"
                ],
                "images": {"agent": AGENT, "core": CORE, "web": WEB},
            },
            "a" * 64,
        ),
    )
    monkeypatch.setattr(
        producer,
        "verify_control_bundle",
        lambda *_args, **_kwargs: (
            {
                "producerRunAttempt": RUN_ATTEMPT,
                "producerRunId": RUN_ID,
                "targetReleaseCommit": TARGET,
                "workflowTrustedCommit": TARGET,
            },
            "b" * 64,
        ),
    )
    arguments = argparse.Namespace(
        candidate_dir=tmp_path / "unreached-candidate",
        candidate_run_json=tmp_path / "unreached-candidate-run.json",
        control_bundle_dir=tmp_path / "stub-control",
        images_dir=tmp_path / "stub-images",
        qualification_dir=qualification,
        qualification_run_json=forged_run,
        repository=REPOSITORY,
        run_attempt=RUN_ATTEMPT,
        run_id=RUN_ID,
        repository_root=ROOT,
        source_tree_manifest=tmp_path / "unreached-source-tree.manifest",
        expected_source_tree_sha256="c" * 64,
        target_release_commit=TARGET,
        variables_json=policy_paths["variables"],
    )
    with pytest.raises(
        producer.ProducerInvalid,
        match="migration qualification producer repository 与可信仓库不一致",
    ):
        producer.verify_prerequisites(arguments)


def test_complete_legal_current_run_rejects_completed_stage_and_hits_workflow_gate(
    tmp_path: Path,
) -> None:
    fixtures = runpy.run_path(str(EVIDENCE_TEST))
    current = datetime.now(UTC).replace(microsecond=0)
    fixture_globals = fixtures["_qualification_reports"].__globals__
    fixture_globals["NOW"] = current.strftime("%Y-%m-%dT%H:%M:%SZ")
    fixture_globals["QUALIFICATION_ISSUED"] = (current - timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    fixture_globals["QUALIFICATION_EXPIRES"] = (current + timedelta(days=10)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    fixture_globals["CANDIDATE_ISSUED"] = (current - timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    fixture_globals["CANDIDATE_EXPIRES"] = (current + timedelta(hours=12)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    qualification_reports = tmp_path / "qualification-reports"
    qualification = tmp_path / "qualification"
    fixtures["_report_source"](
        qualification_reports,
        fixtures["_qualification_reports"](),
        fixtures["QUALIFICATION_FILES"],
    )
    qualification_result = fixtures["_run"](
        fixtures["_qualification_create_args"](
            qualification_reports,
            qualification,
        )
    )
    qualification_sha = fixtures["_created_digest"](qualification_result)

    candidate_run_id = "200"
    candidate_reports = tmp_path / "candidate-reports"
    candidate = tmp_path / "candidate"
    fixtures["_report_source"](
        candidate_reports,
        fixtures["_candidate_reports"](
            run_id=candidate_run_id,
            run_attempt="1",
        ),
        fixtures["CANDIDATE_FILES"],
    )
    candidate_result = fixtures["_run"](
        fixtures["_candidate_create_args"](
            candidate_reports,
            candidate,
            qualification,
            qualification_sha,
            run_id=candidate_run_id,
            run_attempt="1",
        )
    )
    candidate_sha = fixtures["_created_digest"](candidate_result)
    candidate_target = fixtures["TARGET_COMMIT"]

    source_tree_manifest = _git_source_tree_manifest(
        tmp_path / "source-tree.manifest",
        target=candidate_target,
    )
    source_tree_sha, _ = _checkout_hashes(
        source_tree_manifest,
        target=candidate_target,
    )
    images = tmp_path / "images"
    image_arguments = _image_create_args(
        images,
        source_tree_manifest,
        target=candidate_target,
    )
    replacements = {
        "--run-id": candidate_run_id,
        "--web-digest": fixtures["WEB_DIGEST"],
        "--core-digest": fixtures["CORE_DIGEST"],
        "--agent-digest": fixtures["AGENT_DIGEST"],
        "--execution-manifest-fingerprint": fixtures["EXECUTION_FINGERPRINT"],
    }
    for option, value in replacements.items():
        image_arguments[image_arguments.index(option) + 1] = value
    images_sha = _digest_from(_run(image_arguments))

    control = tmp_path / "control"
    control_sha = _digest_from(
        _run_control(
            [
                "create",
                "--repository-root",
                str(ROOT),
                "--output-dir",
                str(control),
                "--workflow-trusted-commit",
                candidate_target,
                "--target-release-commit",
                candidate_target,
                "--producer-run-id",
                candidate_run_id,
                "--producer-run-attempt",
                "1",
            ]
        )
    )

    policy_paths = _environment_documents(tmp_path / "policy")
    qualification_document = json.loads(
        (qualification / "migration-qualification.json").read_text(encoding="utf-8")
    )
    candidate_document = json.loads(
        (candidate / "candidate-evidence.json").read_text(encoding="utf-8")
    )
    variable_replacements = {
        "DURABLE_AGENT_V2_DEVELOPMENT_MIGRATION_QUALIFICATION_SHA256": (qualification_sha),
        "DURABLE_AGENT_V2_DEVELOPMENT_DEVELOPMENT_SCOPE_SHA256": fixtures["DEVELOPMENT_SCOPE"],
        "DURABLE_AGENT_V2_DEVELOPMENT_CANARY_SCENARIO_FINGERPRINT": fixtures["CANARY_SCENARIO"],
        "DURABLE_AGENT_V2_DEVELOPMENT_EXECUTION_MANIFEST_FINGERPRINT": fixtures[
            "EXECUTION_FINGERPRINT"
        ],
        "DURABLE_AGENT_V2_DEVELOPMENT_RESOURCE_POLICY_SHA256": fixtures["RESOURCE_POLICY_SHA"],
        "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_POLICY_SHA256": fixtures["PROVIDER_POLICY_SHA"],
        "DURABLE_AGENT_V2_DEVELOPMENT_RESOURCE_HOST_IDENTITY_SHA256": fixtures[
            "RESOURCE_HOST_IDENTITY"
        ],
        "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_IDENTITY_SHA256": fixtures["PROVIDER_IDENTITY"],
    }
    _replace_variables(policy_paths["variables"], variable_replacements)
    policy_document = json.loads(policy_paths["variables"].read_text(encoding="utf-8"))
    policy_names = {item["name"] for item in policy_document["variables"]}
    assert policy_names.isdisjoint(
        {
            "DURABLE_AGENT_V2_DEVELOPMENT_IMAGE_PROVENANCE_SHA256",
            "DURABLE_AGENT_V2_DEVELOPMENT_CONTROL_BUNDLE_SHA256",
            "DURABLE_AGENT_V2_DEVELOPMENT_CANDIDATE_EVIDENCE_SHA256",
            "DURABLE_AGENT_V2_DEVELOPMENT_WEB_DIGEST_SHA256",
            "DURABLE_AGENT_V2_DEVELOPMENT_CORE_DIGEST_SHA256",
            "DURABLE_AGENT_V2_DEVELOPMENT_AGENT_DIGEST_SHA256",
        }
    )

    qualification_run = tmp_path / "qualification-run.json"
    _write_json(
        qualification_run,
        {
            "conclusion": "success",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": qualification_document["producer"]["headSha"],
            "id": int(qualification_document["producer"]["runId"]),
            "path": ".github/workflows/durable-agent-v2-development-evidence.yml",
            "repository": {"full_name": REPOSITORY},
            "run_attempt": 1,
            "status": "completed",
        },
    )
    candidate_run = tmp_path / "candidate-run.json"
    _write_json(
        candidate_run,
        {
            "conclusion": None,
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": candidate_document["producer"]["headSha"],
            "id": int(candidate_document["producer"]["runId"]),
            "path": ".github/workflows/durable-agent-v2-development-evidence.yml",
            "repository": {"full_name": REPOSITORY},
            "run_attempt": 1,
            "status": "in_progress",
        },
    )
    prerequisites = _run(
        _prerequisite_args(
            policy_paths["variables"],
            images,
            control,
            qualification,
            qualification_run,
            source_tree_manifest,
            source_tree_sha,
            candidate,
            candidate_run,
            target=candidate_target,
            run_id=candidate_run_id,
        )
    )
    assert prerequisites.returncode == 0, prerequisites.stderr
    computed = json.loads(prerequisites.stdout.strip().split(":", 1)[1])
    assert computed == {
        "buildDefinitionSha256": _checkout_hashes(
            source_tree_manifest,
            target=candidate_target,
        )[1],
        "candidateEvidenceSha256": candidate_sha,
        "controlBundleSha256": control_sha,
        "imageProvenanceSha256": images_sha,
        "images": {
            "agent": fixtures["AGENT_DIGEST"],
            "core": fixtures["CORE_DIGEST"],
            "web": fixtures["WEB_DIGEST"],
        },
        "sourceTreeSha256": source_tree_sha,
    }

    completed_current_run = json.loads(candidate_run.read_text(encoding="utf-8"))
    completed_current_run["status"] = "completed"
    completed_current_run["conclusion"] = "success"
    _write_json(candidate_run, completed_current_run)
    mixed_stage = _run(
        _prerequisite_args(
            policy_paths["variables"],
            images,
            control,
            qualification,
            qualification_run,
            source_tree_manifest,
            source_tree_sha,
            candidate,
            candidate_run,
            target=candidate_target,
            run_id=candidate_run_id,
        )
    )
    assert mixed_stage.returncode != 0
    assert "candidate producer current-run status 不一致" in mixed_stage.stderr
    completed_current_run["status"] = "in_progress"
    completed_current_run["conclusion"] = None
    _write_json(candidate_run, completed_current_run)

    fake_bin = tmp_path / "external-bin"
    fake_bin.mkdir()
    counter = tmp_path / "external-counter"
    for name in ("ssh", "scp", "artifact-upload"):
        executable = fake_bin / name
        executable.write_text(
            '#!/bin/sh\nprintf x >> "$EXTERNAL_COUNTER"\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)
    environment = os.environ.copy()
    environment.update(
        {
            "EXTERNAL_COUNTER": str(counter),
            "GITHUB_REPOSITORY": REPOSITORY,
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_RUN_ID": candidate_run_id,
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "TARGET_RELEASE_COMMIT": candidate_target,
        }
    )
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    workflow_stop = workflow["jobs"]["development_evidence"]["steps"][-1]
    assert workflow_stop["name"] == (
        "固定阻断真实远程 driver、2C2G、provider 与 cleanup（零远程动作）"
    )
    unavailable = subprocess.run(  # noqa: S603 -- 执行固定 Workflow shell
        ["/bin/bash", "-c", workflow_stop["run"]],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert unavailable.returncode != 0
    assert "未实现" in unavailable.stderr
    assert not counter.exists()


def test_helper_contains_no_network_or_external_process_client() -> None:
    source = HELPER.read_text(encoding="utf-8")
    for forbidden in (
        "import socket",
        "import subprocess",
        "import requests",
        "import urllib",
        "paramiko",
        "docker ",
        "ssh ",
        "scp ",
    ):
        assert forbidden not in source
