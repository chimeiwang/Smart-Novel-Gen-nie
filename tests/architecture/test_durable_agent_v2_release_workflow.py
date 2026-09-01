from __future__ import annotations

import hashlib
import json
import os
import runpy
import shutil
import stat
import subprocess
import textwrap
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/durable-agent-v2-release.yml"
DEVELOPMENT_WORKFLOW = (
    ROOT / ".github/workflows/durable-agent-v2-development-evidence.yml"
)
BUILD_WORKFLOW = ROOT / ".github/workflows/build.yml"
TOKEN_WORKFLOW = ROOT / ".github/workflows/token-usage-details-migration.yml"
DRIVER = ROOT / "scripts/durable-agent-v2-release.sh"
DEPLOY = ROOT / "scripts/deploy-production.sh"
MANIFEST_HELPER = ROOT / "scripts/durable_agent_v2_release_manifest.py"
CONTROL_BUNDLE_HELPER = ROOT / "scripts/durable_agent_v2_control_bundle.py"
RECEIPT_HELPER = ROOT / "scripts/durable_agent_v2_release_receipt.py"
GUARD_HELPER = ROOT / "scripts/durable_agent_release_guard.py"
BOUNDARY_HELPER = ROOT / "scripts/durable_agent_release_boundary.py"
DEVELOPMENT_HELPER = ROOT / "scripts/durable_agent_v2_development_evidence.py"
ENVIRONMENT_HELPER = ROOT / "scripts/verify_github_environment_policy.py"
PROVENANCE_HELPER = ROOT / "scripts/verify_github_workflow_run_provenance.py"
JOINT_DRAIN_HELPER = ROOT / "scripts/durable_agent_joint_drain.py"
UPLOAD_MANIFEST = ROOT / "scripts/upload-durable-agent-v2-release-manifest.sh"
UPLOAD_SOURCE = ROOT / "scripts/upload-deploy-source.sh"
UPLOAD_CONTROL = ROOT / "scripts/upload-durable-agent-v2-control-bundle.sh"
FORWARD = ROOT / "scripts/migrations/20260831_durable_agent_execution.sql"
ROLLBACK = ROOT / "scripts/migrations/20260831_durable_agent_execution.rollback.sql"
EXPECTED_FORWARD_SHA = "f8342b40c63aba24075fba04a877a5601faa982ef7c40c99d8d164a80b502600"
EXPECTED_ROLLBACK_SHA = "9855a0487d7c5f71723a2fdeda5ae81c3e10dcf0fbc0fa44cd9fceef30000db1"

WORKFLOW_COMMIT = "a" * 40
ROLLBACK_SOURCE_COMMIT = "c" * 40
LOCK_ID = "d" * 64
TARGET_WEB = "sha256:" + "1" * 64
TARGET_CORE = "sha256:" + "2" * 64
TARGET_AGENT = "sha256:" + "3" * 64
ROLLBACK_WEB = "sha256:" + "4" * 64
ROLLBACK_CORE = "sha256:" + "5" * 64
ROLLBACK_AGENT = "sha256:" + "6" * 64
DEVELOPMENT_SHA = "7" * 64
CONTROL_BUNDLE_SHA = "8" * 64
ROLLBACK_SOURCE_RECEIPT_SHA = "9" * 64
CANARY_USER = "user-1"
CANARY_NOVEL = "novel-1"
POSIX_SHELL = shutil.which("sh") or "/bin/sh"


def _run(
    arguments: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        arguments,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


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


def _write_live_boundary_report(path: Path) -> None:
    document = {
        "capturedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "coreRuntime": {
            "containerId": "1" * 64,
            "imageId": "sha256:" + "4" * 64,
            "routeMode": "off",
            "schemaReady": False,
            "v1FreshStartsEnabled": False,
        },
        "database": "novelwriter",
        "executionRedisIdentity": {
            "containerId": "3" * 64,
            "imageId": "sha256:" + "6" * 64,
            "redisRunId": "b" * 40,
        },
        "format": "inkforge-durable-agent-v2-live-drain/1",
        "mode": "pre-contract",
        "postgresIdentity": {
            "databaseOid": 16_384,
            "serverAddress": "127.0.0.1",
            "serverPort": 5432,
            "serverVersionNum": 140019,
        },
        "redisIdentity": {
            "containerId": "2" * 64,
            "imageId": "sha256:" + "5" * 64,
            "redisRunId": "a" * 40,
        },
        "runtimeTopologySha256": "7" * 64,
        "schemaState": "unmigrated",
        "sourceReportSha256": "8" * 64,
        "zeroDrain": True,
    }
    path.write_bytes(_canonical(document))


def _boundary_owner_arguments(boundary: str) -> list[str]:
    return [
        "--boundary",
        boundary,
        "--lock-id",
        LOCK_ID,
        "--control-bundle-sha256",
        CONTROL_BUNDLE_SHA,
        "--manifest-sha256",
        "e" * 64,
        "--run-id",
        "123",
        "--run-attempt",
        "1",
        "--boundary-helper-sha256",
        hashlib.sha256(BOUNDARY_HELPER.read_bytes()).hexdigest(),
        "--workflow-trusted-commit",
        WORKFLOW_COMMIT,
        "--target-release-commit",
        WORKFLOW_COMMIT,
    ]


def _write_valid_release_ssh_policy(tmp_path: Path) -> tuple[Path, Path]:
    secrets_path = tmp_path / "secrets.json"
    variables_path = tmp_path / "variables.json"
    secrets_path.write_text(
        json.dumps(
            {
                "total_count": 1,
                "secrets": [{"name": "DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY"}],
            }
        ),
        encoding="utf-8",
    )
    names = (
        "DURABLE_AGENT_V2_RELEASE_OLD_KEY_REVOCATION_EVIDENCE_SHA256",
        "DURABLE_AGENT_V2_RELEASE_FORCED_COMMAND_EVIDENCE_SHA256",
        "DURABLE_AGENT_V2_RELEASE_MINIMUM_PERMISSION_EVIDENCE_SHA256",
    )
    variables_path.write_text(
        json.dumps(
            {
                "total_count": 3,
                "variables": [
                    {"name": name, "value": str(index) * 64}
                    for index, name in enumerate(names, 1)
                ],
            }
        ),
        encoding="utf-8",
    )
    return secrets_path, variables_path


def _copy_repository_facts(root: Path) -> None:
    for relative in (
        "contracts/agent-execution/manifest.json",
        "scripts/migrations/20260831_durable_agent_execution.sql",
        "scripts/migrations/20260831_durable_agent_execution.rollback.sql",
        "apps/core-api-java/src/main/resources/db/pre-durable-agent-v2/schema-contract.json",
        "apps/core-api-java/src/main/resources/db/post-durable-agent-v2/schema-contract.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def _source_fingerprint(root: Path = ROOT) -> str:
    result = _run(
        [
            "python3",
            str(MANIFEST_HELPER),
            "source-fingerprint",
            "--repository-root",
            str(root),
        ]
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _scope_fingerprint() -> str:
    result = _run(
        [
            "python3",
            str(DEVELOPMENT_HELPER),
            "scope-fingerprint",
            "--user-id",
            CANARY_USER,
            "--novel-id",
            CANARY_NOVEL,
        ]
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _create_control_bundle(
    tmp_path: Path,
    *,
    target_commit: str = WORKFLOW_COMMIT,
    repository_root: Path = ROOT,
) -> tuple[Path, str]:
    directory = tmp_path / "control-bundle"
    result = _run(
        [
            "python3",
            str(CONTROL_BUNDLE_HELPER),
            "create",
            "--repository-root",
            str(repository_root),
            "--output-dir",
            str(directory),
            "--workflow-trusted-commit",
            WORKFLOW_COMMIT,
            "--target-release-commit",
            target_commit,
            "--producer-run-id",
            "123",
            "--producer-run-attempt",
            "1",
        ]
    )
    assert result.returncode == 0, result.stderr
    return directory, result.stdout.strip().removeprefix("control-bundle-created:")


def _create_manifest(
    root: Path,
    output: Path,
    *,
    route_mode: str = "off",
    rollback_fingerprint: str | None = None,
    target_fingerprint: str | None = None,
    control_bundle_sha: str = CONTROL_BUNDLE_SHA,
) -> subprocess.CompletedProcess[str]:
    source = _source_fingerprint(root)
    return _run(
        [
            "python3",
            str(MANIFEST_HELPER),
            "create",
            "--repository-root",
            str(root),
            "--output-dir",
            str(output),
            "--workflow-trusted-commit",
            WORKFLOW_COMMIT,
            "--target-release-commit",
            WORKFLOW_COMMIT,
            "--rollback-source-release-commit",
            ROLLBACK_SOURCE_COMMIT,
            "--cli-commit",
            WORKFLOW_COMMIT,
            "--development-evidence-sha256",
            DEVELOPMENT_SHA,
            "--control-bundle-sha256",
            control_bundle_sha,
            "--rollback-source-receipt-sha256",
            ROLLBACK_SOURCE_RECEIPT_SHA,
            "--producer-run-id",
            "12345",
            "--producer-run-attempt",
            "2",
            "--producer-repository",
            "owner/repo",
            "--canary-scope-sha256",
            _scope_fingerprint(),
            "--route-mode",
            route_mode,
            "--target-web-digest",
            TARGET_WEB,
            "--target-core-digest",
            TARGET_CORE,
            "--target-agent-digest",
            TARGET_AGENT,
            "--rollback-web-digest",
            ROLLBACK_WEB,
            "--rollback-core-digest",
            ROLLBACK_CORE,
            "--rollback-agent-digest",
            ROLLBACK_AGENT,
            "--target-manifest-fingerprint",
            target_fingerprint or source,
            "--rollback-manifest-fingerprint",
            rollback_fingerprint or source,
        ]
    )


def _write_development_evidence(
    directory: Path,
    *,
    provider_status: str,
    reports_directory: Path | None = None,
) -> str:
    directory.mkdir(mode=0o700)
    pending = provider_status == "pending"
    report_names = (
        "fault-injection-report.json",
        "idempotent-forward-report.json",
        "live-contract-evidence.json",
        "migration-backup-evidence.json",
        "provider-canary-report.json",
        "resource-constrained-report.json",
        "rollback-rehearsal-report.json",
    )
    report_hashes: dict[str, str] = {}
    if reports_directory is not None:
        reports_directory.mkdir(mode=0o700)
        checksum_lines: list[str] = []
        for name in report_names:
            path = reports_directory / name
            payload = _canonical({"format": "test-report/1", "name": name})
            path.write_bytes(payload)
            path.chmod(0o600)
            report_hashes[name] = hashlib.sha256(payload).hexdigest()
            checksum_lines.append(f"{report_hashes[name]}  {name}\n")
        checksums = reports_directory / "SHA256SUMS"
        checksums.write_text("".join(checksum_lines), encoding="ascii")
        checksums.chmod(0o600)

    def report_hash(name: str, fallback: str) -> str:
        return report_hashes.get(name, fallback * 64)

    document = {
        "canaryScopeSha256": _scope_fingerprint(),
        "composeValidation": {
            "faultInjectionReportSha256": report_hash(
                "fault-injection-report.json", "8"
            ),
            "resourceConstrainedReportSha256": report_hash(
                "resource-constrained-report.json", "9"
            ),
        },
        "developmentMigration": {
            "backupEvidenceSha256": report_hash(
                "migration-backup-evidence.json", "a"
            ),
            "database": "novelwriterdev",
            "idempotentForwardReportSha256": report_hash(
                "idempotent-forward-report.json", "b"
            ),
            "liveContractEvidenceSha256": report_hash(
                "live-contract-evidence.json", "c"
            ),
            "rollbackRehearsalReportSha256": report_hash(
                "rollback-rehearsal-report.json", "d"
            ),
        },
        "executionManifestFingerprint": _source_fingerprint(),
        "format": "inkforge-durable-agent-v2-development-evidence/1",
        "images": {
            "agent": TARGET_AGENT,
            "core": TARGET_CORE,
            "web": TARGET_WEB,
        },
        "producerRunId": "12345",
        "providerCanary": {
            "mode": "unavailable" if pending else "real",
            "reportSha256": (
                None if pending else report_hash("provider-canary-report.json", "e")
            ),
            "status": provider_status,
        },
        "targetReleaseCommit": WORKFLOW_COMMIT,
    }
    payload = _canonical(document)
    evidence = directory / "development-evidence.json"
    evidence.write_bytes(payload)
    evidence.chmod(0o600)
    digest = hashlib.sha256(payload).hexdigest()
    checksums = directory / "SHA256SUMS"
    checksums.write_text(
        f"{digest}  development-evidence.json\n",
        encoding="ascii",
    )
    checksums.chmod(0o600)
    return digest


def test_build_keeps_ci_but_has_no_main_auto_deploy_and_all_production_groups_match() -> None:
    build = yaml.safe_load(BUILD_WORKFLOW.read_text(encoding="utf-8"))
    assert set(build["jobs"]) == {"ci"}
    assert "deploy-production.sh" not in BUILD_WORKFLOW.read_text(encoding="utf-8")

    for path in (WORKFLOW, TOKEN_WORKFLOW):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in workflow["jobs"].values():
            environment = job.get("environment")
            environment_name = (
                environment.get("name") if isinstance(environment, dict) else environment
            )
            if environment_name == "production":
                assert job["concurrency"] == {
                    "group": "production",
                    "cancel-in-progress": False,
                }


def test_trusted_context_guard_is_before_checkout_and_rejects_malicious_ref(
    tmp_path: Path,
) -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["source"]["steps"]
    first = steps[0]
    assert "uses" not in first
    assert "scripts/" not in first["run"]
    assert steps[1]["with"]["ref"] == "${{ github.sha }}"

    output = tmp_path / "output"
    environment = os.environ.copy()
    environment.update(
        {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/attacker",
            "GITHUB_SHA": WORKFLOW_COMMIT,
            "GITHUB_OUTPUT": str(output),
            "INPUT_WORKFLOW_COMMIT": WORKFLOW_COMMIT,
            "RELEASE_ACTION": "route_off_release",
            "DEVELOPMENT_EVIDENCE_RUN_ID": "123",
            "DEVELOPMENT_EVIDENCE_SHA256": DEVELOPMENT_SHA,
            "RELEASE_MANIFEST_RUN_ID": "",
            "RELEASE_MANIFEST_SHA256": "",
            "CANARY_USER_ID": CANARY_USER,
            "CANARY_NOVEL_ID": CANARY_NOVEL,
            "FAILED_LOCK_ID": "",
            "FAILED_LOCK_CLEANUP_CONFIRM": "",
        }
    )
    result = _run(["bash", "-c", first["run"]], env=environment)
    assert result.returncode != 0
    assert not output.exists()


def test_workflow_separates_development_evidence_from_production_and_fails_before_ssh(
    tmp_path: Path,
) -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    development = workflow["jobs"]["development_evidence"]
    production = workflow["jobs"]["production"]

    assert development["environment"] == {"name": "development"}
    assert "development_evidence" in production["needs"]
    assert "needs.development_evidence.result == 'success'" in production["if"]
    assert production["environment"] == {"name": "production"}
    production_source = source.split("  production:", maxsplit=1)[1]
    assert production_source.index("verify-production") < production_source.index(
        "准备严格 SSH（所有证据复验之后）"
    )
    assert "开发库 route-off 迁移" not in production_source
    assert "release-database novelwriterdev" not in production_source
    assert "GH_ENVIRONMENT_POLICY_AUDIT_TOKEN" in source
    assert "GH_TOKEN:" in source
    assert "Authorization: Bearer" not in source
    assert "verify_github_workflow_run_provenance.py" in source
    assert "durable-agent-v2-development-reports" in source
    assert '--reports-dir "$reports_dir"' in source

    producer = yaml.safe_load(DEVELOPMENT_WORKFLOW.read_text(encoding="utf-8"))
    producer_source = DEVELOPMENT_WORKFLOW.read_text(encoding="utf-8")
    assert "actions/upload-artifact" not in producer_source
    assert "real-provider-identity-not-automated" in producer_source

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    ssh_counter = tmp_path / "ssh-counter"
    fake_ssh = fake_bin / "ssh"
    fake_ssh.write_text(
        "#!/bin/sh\nprintf x >> \"$SSH_COUNTER\"\n",
        encoding="utf-8",
    )
    fake_ssh.chmod(0o755)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "SSH_COUNTER": str(ssh_counter),
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": WORKFLOW_COMMIT,
            "TARGET_RELEASE_COMMIT": WORKFLOW_COMMIT,
        }
    )
    result: subprocess.CompletedProcess[str] | None = None
    for step in producer["jobs"]["development_evidence"]["steps"]:
        if "run" not in step:
            continue
        result = _run(["bash", "-c", step["run"]], env=environment)
        if result.returncode != 0:
            break
    assert result is not None and result.returncode != 0
    assert not ssh_counter.exists()


def test_development_run_provenance_rejects_wrong_workflow_or_commit(
    tmp_path: Path,
) -> None:
    run_path = tmp_path / "run.json"
    document = {
        "id": 12345,
        "path": ".github/workflows/durable-agent-v2-development-evidence.yml",
        "head_sha": WORKFLOW_COMMIT,
        "head_branch": "main",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "owner/repo"},
    }
    run_path.write_text(json.dumps(document), encoding="utf-8")
    arguments = [
        "python3",
        str(PROVENANCE_HELPER),
        "--run-json",
        str(run_path),
        "--expected-run-id",
        "12345",
        "--expected-head-sha",
        WORKFLOW_COMMIT,
        "--expected-repository",
        "owner/repo",
        "--expected-workflow-path",
        ".github/workflows/durable-agent-v2-development-evidence.yml",
    ]
    valid = _run(arguments)
    assert valid.returncode == 0, valid.stderr

    document["head_sha"] = "f" * 40
    run_path.write_text(json.dumps(document), encoding="utf-8")
    drifted = _run(arguments)
    assert drifted.returncode != 0
    assert "head SHA" in drifted.stderr


@pytest.mark.parametrize(
    ("mutator", "expected_error"),
    [
        (
            lambda environment, _policies: environment["protection_rules"].clear(),
            "required reviewers",
        ),
        (
            lambda environment, _policies: environment["protection_rules"][0].update(
                {"prevent_self_review": False}
            ),
            "禁止发起人自审",
        ),
        (
            lambda _environment, policies: policies["branch_policies"].append(
                {"name": "feature/*"}
            ),
            "分页或计数不完整",
        ),
    ],
)
def test_external_environment_policy_fails_closed(
    tmp_path: Path,
    mutator: Any,
    expected_error: str,
) -> None:
    environment = {
        "name": "production",
        "deployment_branch_policy": {
            "protected_branches": False,
            "custom_branch_policies": True,
        },
        "protection_rules": [
            {
                "type": "required_reviewers",
                "prevent_self_review": True,
                "reviewers": [{"type": "Team", "reviewer": {"id": 1}}],
            }
        ],
    }
    policies = {"total_count": 1, "branch_policies": [{"name": "main"}]}
    mutator(environment, policies)
    environment_path = tmp_path / "environment.json"
    policies_path = tmp_path / "policies.json"
    environment_path.write_text(json.dumps(environment), encoding="utf-8")
    policies_path.write_text(json.dumps(policies), encoding="utf-8")
    secrets_path, variables_path = _write_valid_release_ssh_policy(tmp_path)

    result = _run(
        [
            "python3",
            str(ENVIRONMENT_HELPER),
            "--environment-json",
            str(environment_path),
            "--branch-policies-json",
            str(policies_path),
            "--secrets-json",
            str(secrets_path),
            "--variables-json",
            str(variables_path),
        ]
    )
    assert result.returncode != 0
    assert expected_error in result.stderr


def test_external_environment_policy_accepts_exact_main_and_reviewer(
    tmp_path: Path,
) -> None:
    environment_path = tmp_path / "environment.json"
    policies_path = tmp_path / "policies.json"
    environment_path.write_text(
        json.dumps(
            {
                "name": "production",
                "deployment_branch_policy": {
                    "protected_branches": False,
                    "custom_branch_policies": True,
                },
                "protection_rules": [
                    {
                        "type": "required_reviewers",
                        "prevent_self_review": True,
                        "reviewers": [
                            {"type": "User", "reviewer": {"id": 42}}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    policies_path.write_text(
        json.dumps({"total_count": 1, "branch_policies": [{"name": "main"}]}),
        encoding="utf-8",
    )
    secrets_path, variables_path = _write_valid_release_ssh_policy(tmp_path)
    result = _run(
        [
            "python3",
            str(ENVIRONMENT_HELPER),
            "--environment-json",
            str(environment_path),
            "--branch-policies-json",
            str(policies_path),
            "--secrets-json",
            str(secrets_path),
            "--variables-json",
            str(variables_path),
        ]
    )
    assert result.returncode == 0, result.stderr


def test_external_policy_requires_new_ssh_identity_and_three_offline_attestations(
    tmp_path: Path,
) -> None:
    environment_path = tmp_path / "environment.json"
    policies_path = tmp_path / "policies.json"
    secrets_path = tmp_path / "secrets.json"
    variables_path = tmp_path / "variables.json"
    environment_path.write_text(
        json.dumps(
            {
                "name": "production",
                "deployment_branch_policy": {
                    "protected_branches": False,
                    "custom_branch_policies": True,
                },
                "protection_rules": [
                    {
                        "type": "required_reviewers",
                        "prevent_self_review": True,
                        "reviewers": [{"type": "Team", "reviewer": {"id": 1}}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    policies_path.write_text(
        json.dumps({"total_count": 1, "branch_policies": [{"name": "main"}]}),
        encoding="utf-8",
    )
    secrets_path.write_text(
        json.dumps(
            {
                "total_count": 1,
                "secrets": [{"name": "DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY"}],
            }
        ),
        encoding="utf-8",
    )
    variable_names = (
        "DURABLE_AGENT_V2_RELEASE_OLD_KEY_REVOCATION_EVIDENCE_SHA256",
        "DURABLE_AGENT_V2_RELEASE_FORCED_COMMAND_EVIDENCE_SHA256",
        "DURABLE_AGENT_V2_RELEASE_MINIMUM_PERMISSION_EVIDENCE_SHA256",
    )
    variables_path.write_text(
        json.dumps(
            {
                "total_count": 3,
                "variables": [
                    {"name": name, "value": f"{index}" * 64}
                    for index, name in enumerate(variable_names, 1)
                ],
            }
        ),
        encoding="utf-8",
    )
    arguments = [
        "python3",
        str(ENVIRONMENT_HELPER),
        "--environment-json",
        str(environment_path),
        "--branch-policies-json",
        str(policies_path),
        "--secrets-json",
        str(secrets_path),
        "--variables-json",
        str(variables_path),
    ]
    valid = _run(arguments)
    assert valid.returncode == 0, valid.stderr

    secrets_path.write_text(
        json.dumps(
            {
                "total_count": 2,
                "secrets": [
                    {"name": "DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY"},
                    {"name": "SERVER_SSH_KEY"},
                ],
            }
        ),
        encoding="utf-8",
    )
    old_key = _run(arguments)
    assert old_key.returncode != 0
    assert "旧 SERVER_SSH_KEY 尚未删除" in old_key.stderr

    secrets_path.write_text(
        json.dumps({"total_count": 0, "secrets": []}), encoding="utf-8"
    )
    missing_new_key = _run(arguments)
    assert missing_new_key.returncode != 0
    assert "专用 SSH secret" in missing_new_key.stderr

    secrets_path.write_text(
        json.dumps(
            {
                "total_count": 1,
                "secrets": [{"name": "DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY"}],
            }
        ),
        encoding="utf-8",
    )
    variables_path.write_text(
        json.dumps(
            {
                "total_count": 3,
                "variables": [
                    {"name": name, "value": "0" * 64}
                    for name in variable_names
                ],
            }
        ),
        encoding="utf-8",
    )
    placeholder_evidence = _run(arguments)
    assert placeholder_evidence.returncode != 0
    assert "SSH 外部证据 hash" in placeholder_evidence.stderr


def test_external_policy_and_provenance_are_before_any_ssh_and_old_key_is_unreachable() -> None:
    release_source = WORKFLOW.read_text(encoding="utf-8")
    all_workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / ".github" / "workflows").glob("*.yml")
    )
    source_job = release_source.split("  source:", 1)[1].split(
        "  candidate_validation:", 1
    )[0]
    production_job = release_source.split("  production:", 1)[1]
    assert "environments/production/secrets?per_page=100" in source_job
    assert "--variables-json" in source_job
    assert "ssh " not in source_job and "scp " not in source_job
    assert production_job.index("准备严格 SSH") < production_job.index(
        "事务前上传并复验不可变 trusted control bundle"
    )
    assert "secrets.SERVER_SSH_KEY" not in all_workflows
    assert "SERVER_SSH_KEY:" not in all_workflows
    assert "secrets.DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY" in release_source


def test_pending_provider_evidence_is_recordable_but_never_production_grade(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "pending"
    digest = _write_development_evidence(directory, provider_status="pending")
    common = [
        "--evidence-dir",
        str(directory),
        "--expected-sha256",
        digest,
        "--expected-run-id",
        "12345",
        "--expected-target-commit",
        WORKFLOW_COMMIT,
    ]
    ordinary = _run(["python3", str(DEVELOPMENT_HELPER), "verify", *common])
    production = _run(
        ["python3", str(DEVELOPMENT_HELPER), "verify-production", *common]
    )
    assert ordinary.returncode == 0, ordinary.stderr
    assert production.returncode != 0
    assert "pending provider" in production.stderr


def test_passed_real_provider_evidence_binds_commit_scope_and_images(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "passed"
    reports = tmp_path / "reports"
    digest = _write_development_evidence(
        directory,
        provider_status="passed",
        reports_directory=reports,
    )
    result = _run(
        [
            "python3",
            str(DEVELOPMENT_HELPER),
            "verify-production",
            "--evidence-dir",
            str(directory),
            "--expected-sha256",
            digest,
            "--expected-run-id",
            "12345",
            "--expected-target-commit",
            WORKFLOW_COMMIT,
            "--expected-canary-scope-sha256",
            _scope_fingerprint(),
            "--expected-execution-fingerprint",
            _source_fingerprint(),
            "--expected-web-digest",
            TARGET_WEB,
            "--expected-core-digest",
            TARGET_CORE,
            "--expected-agent-digest",
            TARGET_AGENT,
            "--reports-dir",
            str(reports),
        ]
    )
    assert result.returncode == 0, result.stderr

    drifted = _run(
        [
            "python3",
            str(DEVELOPMENT_HELPER),
            "verify-production",
            "--evidence-dir",
            str(directory),
            "--expected-sha256",
            digest,
            "--expected-target-commit",
            "f" * 40,
            "--reports-dir",
            str(reports),
        ]
    )
    assert drifted.returncode != 0
    assert "target commit" in drifted.stderr


def test_manifest_v3_is_canonical_and_old_artifact_uses_its_own_commit(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "manifest"
    created = _create_manifest(ROOT, directory)
    assert created.returncode == 0, created.stderr
    manifest = directory / "release-manifest.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()

    assert document["format"] == "inkforge-durable-agent-v2-release/3"
    assert document["workflowTrustedCommit"] == WORKFLOW_COMMIT
    assert document["targetReleaseCommit"] == WORKFLOW_COMMIT
    assert document["rollbackSourceReleaseCommit"] == ROLLBACK_SOURCE_COMMIT
    assert document["developmentEvidenceSha256"] == DEVELOPMENT_SHA
    assert document["controlBundleSha256"] == CONTROL_BUNDLE_SHA
    assert document["rollbackSourceReceiptSha256"] == ROLLBACK_SOURCE_RECEIPT_SHA
    assert document["producer"] == {
        "repository": "owner/repo",
        "runAttempt": "2",
        "runId": "12345",
        "workflowPath": ".github/workflows/durable-agent-v2-release.yml",
    }
    assert document["canaryScopeSha256"] == _scope_fingerprint()
    assert manifest.read_bytes() == _canonical(document)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o600

    root_independent = _run(
        [
            "python3",
            str(MANIFEST_HELPER),
            "verify",
            "--manifest-dir",
            str(directory),
            "--expected-artifact-sha256",
            digest,
        ]
    )
    old_target_facts = _run(
        [
            "python3",
            str(MANIFEST_HELPER),
            "verify",
            "--repository-root",
            str(ROOT),
            "--manifest-dir",
            str(directory),
            "--expected-target-commit",
            WORKFLOW_COMMIT,
            "--expected-artifact-sha256",
            digest,
        ]
    )
    wrong_current_main = _run(
        [
            "python3",
            str(MANIFEST_HELPER),
            "verify",
            "--manifest-dir",
            str(directory),
            "--expected-target-commit",
            "f" * 40,
            "--expected-artifact-sha256",
            digest,
        ]
    )
    assert root_independent.returncode == 0, root_independent.stderr
    assert old_target_facts.returncode == 0, old_target_facts.stderr
    assert wrong_current_main.returncode != 0


def test_manifest_still_rejects_fingerprint_mismatch_and_allowlist_rollback(
    tmp_path: Path,
) -> None:
    target_mismatch = _create_manifest(
        ROOT,
        tmp_path / "target-mismatch",
        target_fingerprint="f" * 64,
    )
    allowlist_mismatch = _create_manifest(
        ROOT,
        tmp_path / "allowlist-mismatch",
        route_mode="allowlist",
        rollback_fingerprint="e" * 64,
    )
    assert target_mismatch.returncode != 0
    assert "source/target" in target_mismatch.stderr
    assert allowlist_mismatch.returncode != 0
    assert "allowlist rollback" in allowlist_mismatch.stderr


def test_control_bundle_binds_both_commits_and_rejects_helper_tampering(
    tmp_path: Path,
) -> None:
    target_commit = "b" * 40
    directory, digest = _create_control_bundle(tmp_path, target_commit=target_commit)
    metadata = json.loads(
        (directory / "control-bundle.json").read_text(encoding="utf-8")
    )
    assert metadata["workflowTrustedCommit"] == WORKFLOW_COMMIT
    assert metadata["targetReleaseCommit"] == target_commit
    assert metadata["producerRunId"] == "123"
    assert metadata["producerRunAttempt"] == "1"
    verified = _run(
        [
            "python3",
            str(CONTROL_BUNDLE_HELPER),
            "verify",
            "--bundle-dir",
            str(directory),
            "--expected-sha256",
            digest,
        ]
    )
    assert verified.returncode == 0, verified.stderr

    published_directory = tmp_path / "published-control-bundle"
    published = _run(
        [
            "python3",
            str(CONTROL_BUNDLE_HELPER),
            "publish",
            "--bundle-dir",
            str(directory),
            "--target-dir",
            str(published_directory),
            "--expected-sha256",
            digest,
        ]
    )
    assert published.returncode == 0, published.stderr
    assert not directory.exists()
    directory = published_directory

    driver = directory / "scripts" / "durable-agent-v2-release.sh"
    driver.write_text(driver.read_text(encoding="utf-8") + "\n# attacker\n", encoding="utf-8")
    driver.chmod(0o600)
    tampered = _run(
        [
            "python3",
            str(CONTROL_BUNDLE_HELPER),
            "verify",
            "--bundle-dir",
            str(directory),
            "--expected-sha256",
            digest,
        ]
    )
    assert tampered.returncode != 0
    assert "SHA256SUMS" in tampered.stderr


def test_rollback_producer_provenance_accepts_old_success_after_main_progresses(
    tmp_path: Path,
) -> None:
    old_commit = "a" * 40
    current_main = "f" * 40
    assert current_main != old_commit
    run_path = tmp_path / "run.json"
    document = {
        "id": 12345,
        "run_attempt": 2,
        "path": ".github/workflows/durable-agent-v2-release.yml",
        "head_sha": old_commit,
        "head_branch": "main",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "owner/repo"},
    }
    run_path.write_text(json.dumps(document), encoding="utf-8")
    arguments = [
        "python3",
        str(PROVENANCE_HELPER),
        "--run-json",
        str(run_path),
        "--expected-run-id",
        "12345",
        "--expected-run-attempt",
        "2",
        "--expected-head-sha",
        old_commit,
        "--expected-repository",
        "owner/repo",
        "--expected-workflow-path",
        ".github/workflows/durable-agent-v2-release.yml",
    ]
    valid = _run(arguments)
    assert valid.returncode == 0, valid.stderr
    document["conclusion"] = "failure"
    run_path.write_text(json.dumps(document), encoding="utf-8")
    failed = _run(arguments)
    assert failed.returncode != 0
    assert "conclusion" in failed.stderr


def test_server_control_never_uses_mutable_app_helpers_after_checkout() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    driver = DRIVER.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")
    production = workflow.split("  production:", 1)[1]
    assert production.index("事务前上传并复验不可变 trusted control bundle") < production.index(
        "route-off/allowlist 建锁并冻结回滚起点"
    )
    assert "sh -s" not in production
    assert "< scripts/durable-agent-v2-release.sh" not in production
    assert "< scripts/deploy-production.sh" not in production
    assert 'migration_helper="$control_dir/scripts/durable-agent-execution-migration.sh"' in driver
    assert 'joint_drain_helper="$control_dir/scripts/durable_agent_joint_drain.py"' in driver
    assert (
        'durable_migration_helper="$control_dir/scripts/'
        'durable-agent-execution-migration.sh"'
    ) in deploy
    assert 'safe_git reset --hard "$DEPLOY_SHA"' in deploy
    assert deploy.index('sh "$durable_image_verifier" core') < deploy.index(
        'consume-live-boundary'
    ) < deploy.index('safe_git reset --hard "$DEPLOY_SHA"')
    assert '--project-directory "$control_dir/infra"' in deploy
    assert 'SERVICE_KEYS_DIR="$APP_DIR/infra/secrets"' in deploy
    assert '"infra/redis/execution-redis.conf"' in CONTROL_BUNDLE_HELPER.read_text(
        encoding="utf-8"
    )


def test_workflow_owns_route_state_transitions_and_rollback_never_reopens_allowlist() -> None:
    source = WORKFLOW.read_text(encoding="utf-8").split("  production:", 1)[1]
    off_transition = source.index("transition-runtime-config off")
    deploy = source.index("按 manifest 与服务器锁部署冻结 digest")
    allowlist_transition = source.index("finalize-allowlist-transaction")
    postflight = source.index("统一 runtime postflight")
    assert off_transition < deploy < allowlist_transition < postflight
    assert "DEPLOY_RUNTIME_ROUTE_MODE: off" in source
    allowlist_step = source.split(
        "单服务器进程完成 allowlist、receipt commit point 与 finalize", 1
    )[1].split("rollback 后 V2-aware route-off 门禁", 1)[0]
    assert "if: inputs.action == 'allowlist_release'" in allowlist_step
    rollback_step = source.split("rollback 后 V2-aware route-off 门禁", 1)[1].split(
        "统一 runtime postflight", 1
    )[0]
    assert "transition-runtime-config allowlist" not in rollback_step
    driver = DRIVER.read_text(encoding="utf-8")
    assert "allowlist_failure_trap" in driver
    assert "force_allowlist_route_off" in driver
    assert 'os.replace(temporary, path)' in driver
    assert 'restore_env_snapshot "$transition_before"' in driver


def test_release_shell_traps_preserve_status_and_orchestration_is_subshell_isolated() -> None:
    release = DRIVER.read_text(encoding="utf-8")
    migration = (
        ROOT / "scripts" / "durable-agent-execution-migration.sh"
    ).read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert ":?" not in release
    assert ":?" not in migration
    for function in (
        "current_service_digest",
        "manifest_read",
        "runtime_preflight",
        "current_core_config_snapshot",
        "consume_live_boundary",
        "mark_live_boundary_applied",
        "write_release_guard",
        "transition_runtime_config",
        "prepare_release_receipt",
        "receipt_commit_status",
        "commit_prepared_receipt",
        "finalize_committed_transaction",
        "reconcile_transaction_internal",
    ):
        assert f"{function}() (" in release
    assert "trap 'allowlist_failure_trap 129' HUP" in release
    assert "trap 'allowlist_failure_trap 130' INT" in release
    assert "trap 'allowlist_failure_trap 143' TERM" in release
    assert "cleanup_status=$?; trap - EXIT; cleanup" in migration
    assert "cleanup_deploy_bundle_on_exit" in deploy
    assert 'rollback "$?"' in deploy


def test_fresh_v2_main_wiring_has_final_guard_after_all_locks_before_insert() -> None:
    java = ROOT / "apps" / "core-api-java" / "src" / "main" / "java"
    starter = (
        java
        / "cn/inkforge/core/writing/application/LongSerialDurableRunStarter.java"
    ).read_text(encoding="utf-8")
    durable = (
        java
        / "cn/inkforge/core/writing/infrastructure/JooqLongSerialDurableRunStarter.java"
    ).read_text(encoding="utf-8")
    repository = (
        java
        / "cn/inkforge/core/workflows/infrastructure/JooqWorkflowStartRepository.java"
    ).read_text(encoding="utf-8")
    all_main = "\n".join(path.read_text(encoding="utf-8") for path in java.rglob("*.java"))

    assert all_main.count("durable.startFresh(") == 1
    assert all_main.count("workflows.startFresh(") == 1
    assert "WritingRunV2Response startFresh(" in starter
    assert "WritingRunV2Response replayExisting(" in starter
    assert (
        "workflows.startFresh(\n                    plan, finalFreshStartAuthorization)"
        in durable
    )
    lock_index = repository.index("lockOwnedResources(transaction, plan);")
    derived_index = repository.index("String stepRequestHash =")
    guard_index = repository.index("finalFreshStartAuthorization.run();")
    insert_index = repository.index("insertRun(transaction, plan, runId, now);")
    assert lock_index < derived_index < guard_index < insert_index
    assert repository[guard_index:insert_index].strip() == (
        "finalFreshStartAuthorization.run();"
    )


def _lock_environment(
    root: Path,
    control_dir: Path,
    control_sha: str,
    **overrides: str,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "APP_DIR": str(root),
            "WORKFLOW_TRUSTED_COMMIT": WORKFLOW_COMMIT,
            "TARGET_RELEASE_COMMIT": WORKFLOW_COMMIT,
            "RELEASE_ACTION": "route_off_release",
            "RELEASE_ROUTE_MODE": "off",
            "CANARY_SCOPE_SHA256": _scope_fingerprint(),
            "DURABLE_AGENT_RELEASE_LOCK_ID": LOCK_ID,
            "DURABLE_AGENT_CONTROL_BUNDLE_DIR": str(control_dir),
            "DURABLE_AGENT_CONTROL_BUNDLE_SHA256": control_sha,
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": WORKFLOW_COMMIT,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "INKFORGE_RELEASE_APPROVED_ENVIRONMENT": "production",
        }
    )
    environment.update(overrides)
    return environment


def test_release_receipt_is_canonical_and_binds_runtime_digests_and_control(
    tmp_path: Path,
) -> None:
    output = tmp_path / "receipt"
    arguments = [
        "python3",
        str(RECEIPT_HELPER),
        "create",
        "--output-dir",
        str(output),
        "--active-release-commit",
        WORKFLOW_COMMIT,
        "--agent-digest",
        TARGET_AGENT,
        "--canary-scope-sha256",
        _scope_fingerprint(),
        "--control-bundle-sha256",
        CONTROL_BUNDLE_SHA,
        "--core-container-id",
        "c" * 64,
        "--core-digest",
        TARGET_CORE,
        "--boundary-ledger-sha256",
        "d" * 64,
        "--execution-manifest-fingerprint",
        _source_fingerprint(),
        "--lock-id",
        LOCK_ID,
        "--manifest-sha256",
        "e" * 64,
        "--previous-receipt-sha256",
        ROLLBACK_SOURCE_RECEIPT_SHA,
        "--release-action",
        "allowlist_release",
        "--route-mode",
        "allowlist",
        "--run-attempt",
        "1",
        "--run-id",
        "123",
        "--schema-ready",
        "true",
        "--target-release-commit",
        WORKFLOW_COMMIT,
        "--v1-fresh-starts-enabled",
        "true",
        "--web-digest",
        TARGET_WEB,
        "--workflow-trusted-commit",
        WORKFLOW_COMMIT,
    ]
    created = _run(arguments)
    assert created.returncode == 0, created.stderr
    digest = created.stdout.strip().removeprefix("release-receipt-created:")
    document = json.loads((output / "release-receipt.json").read_text(encoding="utf-8"))
    assert document["activeReleaseCommit"] == WORKFLOW_COMMIT
    assert document["images"] == {
        "agent": TARGET_AGENT,
        "core": TARGET_CORE,
        "web": TARGET_WEB,
    }
    assert document["controlBundleSha256"] == CONTROL_BUNDLE_SHA
    verified = _run(
        [
            "python3",
            str(RECEIPT_HELPER),
            "verify",
            "--receipt-dir",
            str(output),
            "--expected-sha256",
            digest,
        ]
    )
    assert verified.returncode == 0, verified.stderr
    final = tmp_path / "published-receipt"
    published = _run(
        [
            "python3",
            str(RECEIPT_HELPER),
            "publish",
            "--receipt-dir",
            str(output),
            "--target-dir",
            str(final),
            "--expected-sha256",
            digest,
        ]
    )
    assert published.returncode == 0, published.stderr
    assert not output.exists()
    assert (final / "release-receipt.json").read_bytes() == _canonical(document)
    source = DRIVER.read_text(encoding="utf-8")
    begin = source.split("  begin-snapshot)", 1)[1].split("  begin-rollback)", 1)[0]
    assert "verify_current_receipt_runtime" in begin
    assert "git -C" not in begin
    rollback = source.split("  begin-rollback)", 1)[1].split("  create-manifest)", 1)[0]
    assert "previous-receipt-sha256" in rollback
    assert "rollback-receipt-chain" in rollback


def test_release_guard_pending_lease_is_nonrenewable_and_commit_is_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "guard" / "guard.json"
    off = _run(
        ["python3", str(GUARD_HELPER), "write", "--path", str(path), "--state", "off"]
    )
    assert off.returncode == 0, off.stderr
    common = [
        "--path",
        str(path),
        "--canary-scope-sha256",
        _scope_fingerprint(),
        "--control-bundle-sha256",
        CONTROL_BUNDLE_SHA,
        "--execution-manifest-fingerprint",
        _source_fingerprint(),
        "--lease-id",
        "1" * 64,
        "--lock-id",
        LOCK_ID,
        "--manifest-sha256",
        "e" * 64,
        "--run-attempt",
        "1",
        "--run-id",
        "123",
    ]
    pending = _run(
        ["python3", str(GUARD_HELPER), "write", *common, "--state", "pending"]
    )
    assert pending.returncode == 0, pending.stderr
    original = path.read_bytes()
    repeated = _run(
        ["python3", str(GUARD_HELPER), "write", *common, "--state", "pending"]
    )
    assert repeated.returncode != 0
    assert "不可续租" in repeated.stderr
    assert path.read_bytes() == original
    replaced_lease = ["2" * 64 if value == "1" * 64 else value for value in common]
    replaced = _run(
        ["python3", str(GUARD_HELPER), "write", *replaced_lease, "--state", "pending"]
    )
    assert replaced.returncode != 0
    assert path.read_bytes() == original

    receipt_sha = "9" * 64
    commit_arguments = [
        "python3",
        str(GUARD_HELPER),
        "write",
        *common,
        "--state",
        "committed",
        "--committed-receipt-sha256",
        receipt_sha,
    ]
    committed = _run(commit_arguments)
    assert committed.returncode == 0, committed.stderr
    committed_payload = path.read_bytes()
    replay = _run(commit_arguments)
    assert replay.returncode == 0, replay.stderr
    assert path.read_bytes() == committed_payload


def test_boundary_claim_is_single_use_and_unknown_outcome_blocks_commit(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "boundaries"
    evidence_dir.mkdir(mode=0o700)
    evidence_dir.chmod(0o700)
    live = tmp_path / "live.json"
    _write_live_boundary_report(live)
    owner = _boundary_owner_arguments("ddl-forward-1")

    issued = _run(
        [
            "python3",
            str(BOUNDARY_HELPER),
            "issue",
            "--live-report",
            str(live),
            "--evidence-dir",
            str(evidence_dir),
            *owner,
        ]
    )
    assert issued.returncode == 0, issued.stderr
    _prefix, _sequence, evidence_sha, ready_raw = issued.stdout.strip().split(":", 3)
    ready = Path(ready_raw)
    claimed = ready.with_name(ready.name.replace(".ready.json", ".claimed.json"))
    consumed = _run(
        [
            "python3",
            str(BOUNDARY_HELPER),
            "consume",
            "--evidence-dir",
            str(evidence_dir),
            "--ready-file",
            str(ready),
            "--expected-sha256",
            evidence_sha,
            *owner,
        ]
    )
    assert consumed.returncode == 0, consumed.stderr
    assert claimed.is_file()
    assert not ready.exists()

    unknown = _run(
        [
            "python3",
            str(BOUNDARY_HELPER),
            "ledger",
            "--evidence-dir",
            str(evidence_dir),
            "--lock-id",
            LOCK_ID,
        ]
    )
    assert unknown.returncode != 0
    assert "outcome-unknown" in unknown.stderr
    repeated_issue = _run(
        [
            "python3",
            str(BOUNDARY_HELPER),
            "issue",
            "--live-report",
            str(live),
            "--evidence-dir",
            str(evidence_dir),
            *owner,
        ]
    )
    assert repeated_issue.returncode != 0
    assert "禁止重试" in repeated_issue.stderr

    applied = _run(
        [
            "python3",
            str(BOUNDARY_HELPER),
            "mark-applied",
            "--evidence-dir",
            str(evidence_dir),
            "--claimed-file",
            str(claimed),
            "--expected-sha256",
            evidence_sha,
            "--outcome",
            "succeeded",
            *owner,
        ]
    )
    assert applied.returncode == 0, applied.stderr
    ledger = _run(
        [
            "python3",
            str(BOUNDARY_HELPER),
            "ledger",
            "--evidence-dir",
            str(evidence_dir),
            "--lock-id",
            LOCK_ID,
        ]
    )
    assert ledger.returncode == 0, ledger.stderr
    assert json.loads(ledger.stdout)["entries"] == [
        {
            "boundary": "ddl-forward-1",
            "evidenceSha256": evidence_sha,
            "outcome": "succeeded",
            "sequence": 1,
        }
    ]


def test_server_lock_is_non_stealable_failure_retained_and_cleanup_is_exact(
    tmp_path: Path,
) -> None:
    root = tmp_path / "server"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(DRIVER, scripts / DRIVER.name)
    driver = scripts / DRIVER.name
    driver.chmod(0o755)
    control_dir, control_sha = _create_control_bundle(tmp_path)
    environment = _lock_environment(root, control_dir, control_sha)

    first = _run(["sh", str(driver), "begin-snapshot"], cwd=root, env=environment)
    lock_dir = root / ".durable-agent-v2-release-transactions" / LOCK_ID
    fixed_lock = root / ".durable-agent-v2-release-transaction.lock"
    owner = lock_dir / "owner"
    assert first.returncode != 0
    assert owner.is_file()
    assert fixed_lock.samefile(owner)
    assert (lock_dir / "state").read_text(encoding="ascii") == "active\n"
    env_partial = lock_dir / ".env.transition.partial"
    env_partial.write_text("DURABLE_AGENT_EXECUTION_ROUTE_MODE=off\n", encoding="utf-8")
    env_partial.chmod(0o600)
    receipt_partial = lock_dir / ".release-receipt-candidate.partial"
    receipt_partial.mkdir(mode=0o700)
    (receipt_partial / "release-receipt.json").write_text("{}\n", encoding="utf-8")
    (receipt_partial / "release-receipt.json").chmod(0o600)
    token_partial = lock_dir / "token-usage-control"
    token_partial.mkdir(mode=0o700)
    (token_partial / ".env").write_text("DATABASE_URL=redacted\n", encoding="utf-8")
    (token_partial / ".env").chmod(0o600)

    second = _run(["sh", str(driver), "begin-snapshot"], cwd=root, env=environment)
    assert second.returncode != 0
    assert "release-transaction-locked" in second.stderr
    assert owner.is_file()

    cleanup_base = {
        "RELEASE_LOCK_OWNER_RUN_ID": "123",
        "RELEASE_LOCK_OWNER_RUN_ATTEMPT": "1",
        "RELEASE_LOCK_OWNER_ACTION": "route_off_release",
        "RELEASE_LOCK_OWNER_WORKFLOW_COMMIT": WORKFLOW_COMMIT,
        "RELEASE_LOCK_OWNER_TARGET_COMMIT": WORKFLOW_COMMIT,
        "RELEASE_LOCK_OWNER_CONTROL_BUNDLE_SHA256": control_sha,
    }
    wrong = _run(
        ["sh", str(driver), "cleanup-failed-transaction"],
        cwd=root,
        env={**environment, **cleanup_base, "INKFORGE_RELEASE_CLEANUP_CONFIRM": "wrong"},
    )
    assert wrong.returncode != 0
    assert owner.is_file()

    cleaned = _run(
        ["sh", str(driver), "cleanup-failed-transaction"],
        cwd=root,
        env={
            **environment,
            **cleanup_base,
            "INKFORGE_RELEASE_CLEANUP_CONFIRM": f"cleanup-failed-release:{LOCK_ID}",
        },
    )
    assert cleaned.returncode == 0, cleaned.stderr
    assert not lock_dir.exists()
    assert not fixed_lock.exists()


@pytest.mark.parametrize("acquired_fixed", (False, True))
def test_cleanup_handles_partial_owner_and_hardlink_acquired_interruption(
    tmp_path: Path,
    acquired_fixed: bool,
) -> None:
    root = tmp_path / "server"
    root.mkdir()
    control_dir, control_sha = _create_control_bundle(tmp_path)
    environment = _lock_environment(root, control_dir, control_sha)
    partial = root / f".durable-agent-v2-release-owner.{LOCK_ID}.partial"
    partial.write_text(
        "\n".join(
            (
                "format=2",
                f"lockId={LOCK_ID}",
                "runId=123",
                "runAttempt=1",
                "operation=route_off_release",
                f"workflowTrustedCommit={WORKFLOW_COMMIT}",
                f"targetReleaseCommit={WORKFLOW_COMMIT}",
                f"controlBundleSha256={control_sha}",
                "",
            )
        ),
        encoding="ascii",
    )
    partial.chmod(0o600)
    fixed = root / ".durable-agent-v2-release-transaction.lock"
    if acquired_fixed:
        os.link(partial, fixed)
    cleanup = _run(
        ["sh", str(control_dir / "scripts" / DRIVER.name), "cleanup-failed-transaction"],
        cwd=root,
        env={
            **environment,
            "RELEASE_LOCK_OWNER_RUN_ID": "123",
            "RELEASE_LOCK_OWNER_RUN_ATTEMPT": "1",
            "RELEASE_LOCK_OWNER_ACTION": "route_off_release",
            "RELEASE_LOCK_OWNER_WORKFLOW_COMMIT": WORKFLOW_COMMIT,
            "RELEASE_LOCK_OWNER_TARGET_COMMIT": WORKFLOW_COMMIT,
            "RELEASE_LOCK_OWNER_CONTROL_BUNDLE_SHA256": control_sha,
            "INKFORGE_RELEASE_CLEANUP_CONFIRM": f"cleanup-failed-release:{LOCK_ID}",
        },
    )
    assert cleanup.returncode == 0, cleanup.stderr
    assert not fixed.exists()
    assert not partial.exists()
    assert not (root / ".durable-agent-v2-release-transactions" / LOCK_ID).exists()


def _write_fake_runtime(root: Path, fake_bin: Path, log: Path) -> None:
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DRIVER, scripts / DRIVER.name)
    shutil.copy2(MANIFEST_HELPER, scripts / MANIFEST_HELPER.name)
    _copy_repository_facts(root)
    verifier = scripts / "verify-durable-agent-v2-image.sh"
    verifier.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            printf 'verifier:%s\n' "$*" >> "$FAKE_LOG"
            if [ "$1" = core ]; then echo v2-aware-image-ok:core; exit 0; fi
            if [ "$2" = "$FAKE_ROLLBACK_AGENT" ]; then
              actual="$FAKE_ROLLBACK_FINGERPRINT"
            else
              actual="$FAKE_TARGET_FINGERPRINT"
            fi
            [ -z "${3:-}" ] || [ "$3" = "$actual" ] || exit 1
            printf 'v2-aware-image-ok:agent:%s\n' "$actual"
            """
        ),
        encoding="utf-8",
    )
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            printf 'docker:%s\n' "$*" >> "$FAKE_LOG"
            if [ "$1" = image ] && [ "$2" = inspect ]; then
              ref="$5"
              case "$ref" in
                inkforge-web:*) echo "$FAKE_TARGET_WEB" ;;
                inkforge-core-api:*) echo "$FAKE_TARGET_CORE" ;;
                inkforge-agent-service:*) echo "$FAKE_TARGET_AGENT" ;;
                sha256:*) echo "$ref" ;;
                *) exit 1 ;;
              esac
              exit 0
            fi
            if [ "$1" = image ] && [ "$2" = tag ]; then exit 0; fi
            if [ "$1" = compose ]; then
              if [ -n "${FAKE_COMPOSE_BLOCK_MARKER:-}" ] \
                && [ ! -e "$FAKE_COMPOSE_BLOCK_MARKER.done" ]; then
                : > "$FAKE_COMPOSE_BLOCK_MARKER"
                while [ ! -e "$FAKE_COMPOSE_BLOCK_RELEASE" ]; do sleep 0.02; done
                : > "$FAKE_COMPOSE_BLOCK_MARKER.done"
              fi
              exit 0
            fi
            if [ "$1" = ps ]; then
              case "$*" in
                *service=web*) echo container-web ;;
                *service=core-api*) echo container-core ;;
                *service=agent-service*) echo container-agent ;;
              esac
              exit 0
            fi
            if [ "$1" = inspect ]; then
              if [ "$3" = '{{.Config.Image}}' ]; then
                case "$4" in
                  container-web) echo inkforge-web:running ;;
                  container-core) echo inkforge-core-api:running ;;
                  container-agent) echo inkforge-agent-service:running ;;
                esac
              else
                case "$4" in
                  container-web) echo "$FAKE_ROLLBACK_WEB" ;;
                  container-core) echo "$FAKE_ROLLBACK_CORE" ;;
                  container-agent) echo "$FAKE_ROLLBACK_AGENT" ;;
                esac
              fi
              exit 0
            fi
            if [ "$1" = exec ]; then
              sed 's/^/runtime-env:/' "$FAKE_ENV_FILE" >> "$FAKE_LOG"
              read_value() {
                key="$1"
                fallback="$2"
                value="$(sed -n "s/^${key}=//p" "$FAKE_ENV_FILE")"
                [ -n "$value" ] || value="$fallback"
                printf '%s\n' "$value"
              }
              read_value DURABLE_AGENT_EXECUTION_ROUTE_MODE "$FAKE_ROUTE"
              read_value DURABLE_AGENT_EXECUTION_SCHEMA_READY "$FAKE_SCHEMA_READY"
              read_value DURABLE_AGENT_EXECUTION_USER_ALLOWLIST "$FAKE_USER_ID"
              read_value DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST "$FAKE_NOVEL_ID"
              read_value V1_FRESH_AGENT_STARTS_ENABLED "$FAKE_V1_FRESH"
              exit 0
            fi
            exit 1
            """
        ),
        encoding="utf-8",
    )
    git = fake_bin / "git"
    git.write_text(
        "#!/bin/sh\nprintf 'git:%s\\n' \"$*\" >> \"$FAKE_LOG\"\necho \"$FAKE_GIT_COMMIT\"\n",
        encoding="utf-8",
    )
    for path in (scripts / DRIVER.name, verifier, docker, git):
        path.chmod(0o755)
    log.touch()


def _runtime_environment(
    root: Path,
    fake_bin: Path,
    log: Path,
    control_dir: Path,
    control_sha: str,
    **overrides: str,
) -> dict[str, str]:
    environment = _lock_environment(root, control_dir, control_sha)
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "FAKE_LOG": str(log),
            "FAKE_TARGET_WEB": TARGET_WEB,
            "FAKE_TARGET_CORE": TARGET_CORE,
            "FAKE_TARGET_AGENT": TARGET_AGENT,
            "FAKE_ROLLBACK_WEB": ROLLBACK_WEB,
            "FAKE_ROLLBACK_CORE": ROLLBACK_CORE,
            "FAKE_ROLLBACK_AGENT": ROLLBACK_AGENT,
            "FAKE_TARGET_FINGERPRINT": _source_fingerprint(root),
            "FAKE_ROLLBACK_FINGERPRINT": "e" * 64,
            "FAKE_ROUTE": "off",
            "FAKE_SCHEMA_READY": "false",
            "FAKE_V1_FRESH": "false",
            "FAKE_USER_ID": CANARY_USER,
            "FAKE_NOVEL_ID": CANARY_NOVEL,
            "FAKE_ENV_FILE": str(root / ".env"),
            "FAKE_GIT_COMMIT": ROLLBACK_SOURCE_COMMIT,
        }
    )
    environment.update(overrides)
    return environment


def _seed_current_release_receipt(
    root: Path,
    control_sha: str,
    execution_fingerprint: str,
) -> str:
    staging = root.parent / "base-release-receipt"
    created = _run(
        [
            "python3",
            str(RECEIPT_HELPER),
            "create",
            "--output-dir",
            str(staging),
            "--active-release-commit",
            ROLLBACK_SOURCE_COMMIT,
            "--agent-digest",
            ROLLBACK_AGENT,
            "--canary-scope-sha256",
            _scope_fingerprint(),
            "--control-bundle-sha256",
            control_sha,
            "--core-container-id",
            "container-core",
            "--core-digest",
            ROLLBACK_CORE,
            "--boundary-ledger-sha256",
            "0" * 64,
            "--execution-manifest-fingerprint",
            execution_fingerprint,
            "--lock-id",
            "0" * 64,
            "--manifest-sha256",
            "0" * 64,
            "--previous-receipt-sha256",
            "f" * 64,
            "--release-action",
            "route_off_release",
            "--route-mode",
            "off",
            "--run-attempt",
            "1",
            "--run-id",
            "1",
            "--schema-ready",
            "true",
            "--target-release-commit",
            ROLLBACK_SOURCE_COMMIT,
            "--v1-fresh-starts-enabled",
            "false",
            "--web-digest",
            ROLLBACK_WEB,
            "--workflow-trusted-commit",
            ROLLBACK_SOURCE_COMMIT,
        ]
    )
    assert created.returncode == 0, created.stderr
    receipt_sha = created.stdout.strip().removeprefix("release-receipt-created:")
    receipt_root = root / ".durable-agent-v2-release-receipts"
    receipt_root.mkdir(mode=0o700)
    receipt_root.chmod(0o700)
    published = _run(
        [
            "python3",
            str(RECEIPT_HELPER),
            "publish",
            "--receipt-dir",
            str(staging),
            "--target-dir",
            str(receipt_root / receipt_sha),
            "--expected-sha256",
            receipt_sha,
        ]
    )
    assert published.returncode == 0, published.stderr
    current = receipt_root / "current"
    current.write_text(receipt_sha + "\n", encoding="ascii")
    current.chmod(0o600)
    return receipt_sha


def _copy_control_repository_with_fake_runtime(root: Path) -> None:
    namespace = runpy.run_path(str(CONTROL_BUNDLE_HELPER))
    for raw_relative in namespace["PAYLOAD_FILES"]:
        relative = str(raw_relative)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    (root / "scripts/durable-agent-execution-migration.sh").write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            set -eu
            [ "$1" = boundary-drain ] && [ "$2" = novelwriter ]
            python3 - "$FAKE_DRAIN_REPORT" <<'PY'
            import json
            import sys
            from datetime import UTC, datetime
            from pathlib import Path

            document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
            document["capturedAt"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            print(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            PY
            """
        ),
        encoding="utf-8",
    )
    (root / "scripts/verify-durable-agent-v2-image.sh").write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            set -eu
            case "$1" in
              core) echo v2-aware-image-ok:core ;;
              agent) printf 'v2-aware-image-ok:agent:%s\n' "$3" ;;
              *) exit 2 ;;
            esac
            """
        ),
        encoding="utf-8",
    )
    (root / "scripts/durable-agent-v2-rollout-gate.sh").write_text(
        "#!/bin/sh\nset -eu\nexit 0\n",
        encoding="utf-8",
    )


def _write_zero_drain_report(path: Path) -> None:
    report = {
        "capturedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "coreRuntime": {
            "containerId": "c" * 64,
            "imageId": TARGET_CORE,
            "routeMode": "off",
            "schemaReady": True,
            "v1FreshStartsEnabled": False,
        },
        "database": "novelwriter",
        "executionRedisIdentity": {
            "containerId": "e" * 64,
            "imageId": "sha256:" + "4" * 64,
            "redisRunId": "5" * 40,
        },
        "format": "inkforge-durable-agent-v2-live-drain/1",
        "mode": "migrated",
        "postgresIdentity": {
            "databaseOid": "1",
            "serverAddress": "127.0.0.1",
            "serverPort": "5432",
            "serverVersionNum": "170000",
        },
        "redisIdentity": {
            "containerId": "d" * 64,
            "imageId": "sha256:" + "3" * 64,
            "redisRunId": "6" * 40,
        },
        "runtimeTopologySha256": "a" * 64,
        "schemaState": "migrated-empty-v2",
        "sourceReportSha256": "b" * 64,
        "zeroDrain": True,
    }
    path.write_bytes(_canonical(report))


def _prepare_allowlist_transaction(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, str], str]:
    root = tmp_path / "server"
    fake_bin = tmp_path / "bin"
    log = tmp_path / "docker.log"
    _write_fake_runtime(root, fake_bin, log)
    fake_repository = tmp_path / "trusted-control-source"
    _copy_control_repository_with_fake_runtime(fake_repository)
    control_dir, control_sha = _create_control_bundle(
        tmp_path,
        repository_root=fake_repository,
    )
    report = tmp_path / "drain-report.json"
    _write_zero_drain_report(report)
    manifest_dir = tmp_path / "manifest"
    execution_fingerprint = _source_fingerprint(root)
    created = _create_manifest(
        ROOT,
        manifest_dir,
        route_mode="allowlist",
        rollback_fingerprint=execution_fingerprint,
        target_fingerprint=execution_fingerprint,
        control_bundle_sha=control_sha,
    )
    assert created.returncode == 0, created.stderr
    manifest_sha = hashlib.sha256(
        (manifest_dir / "release-manifest.json").read_bytes()
    ).hexdigest()
    env_file = root / ".env"
    env_file.write_text(
        "DURABLE_AGENT_EXECUTION_SCHEMA_READY=true\n"
        "DURABLE_AGENT_EXECUTION_ROUTE_MODE=off\n"
        f"DURABLE_AGENT_EXECUTION_USER_ALLOWLIST={CANARY_USER}\n"
        f"DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST={CANARY_NOVEL}\n"
        "V1_FRESH_AGENT_STARTS_ENABLED=false\n",
        encoding="utf-8",
    )
    base_receipt = _seed_current_release_receipt(
        root,
        control_sha,
        execution_fingerprint,
    )
    environment = _runtime_environment(
        root,
        fake_bin,
        log,
        control_dir,
        control_sha,
        RELEASE_ACTION="allowlist_release",
        RELEASE_ROUTE_MODE="allowlist",
        RELEASE_MANIFEST_DIR=str(manifest_dir),
        RELEASE_MANIFEST_SHA256=manifest_sha,
        CANARY_USER_ID=CANARY_USER,
        CANARY_NOVEL_ID=CANARY_NOVEL,
        FAKE_DRAIN_REPORT=str(report),
        FAKE_ROLLBACK_FINGERPRINT=execution_fingerprint,
        INKFORGE_LOCAL_RELEASE_TEST_MODE="true",
    )
    driver = control_dir / "scripts" / DRIVER.name
    acquired = _run(["sh", str(driver), "begin-snapshot"], cwd=root, env=environment)
    assert acquired.returncode == 0, acquired.stderr
    claimed = _run(
        ["sh", str(driver), "consume-live-boundary", "compose-release"],
        cwd=root,
        env=environment,
    )
    assert claimed.returncode == 0, claimed.stderr
    applied = _run(
        ["sh", str(driver), "mark-live-boundary-applied", "compose-release"],
        cwd=root,
        env=environment,
    )
    assert applied.returncode == 0, applied.stderr
    # fake migration helper 只回放该文件；在真正的下一 boundary 前模拟重新采样。
    _write_zero_drain_report(report)
    target_environment = {
        **environment,
        "FAKE_ROLLBACK_WEB": TARGET_WEB,
        "FAKE_ROLLBACK_CORE": TARGET_CORE,
        "FAKE_ROLLBACK_AGENT": TARGET_AGENT,
    }
    return root, driver, target_environment, base_receipt


def test_locked_route_off_to_allowlist_transition_succeeds_with_frozen_scope(
    tmp_path: Path,
) -> None:
    root = tmp_path / "server"
    fake_bin = tmp_path / "bin"
    log = tmp_path / "docker.log"
    _write_fake_runtime(root, fake_bin, log)
    fake_repository = tmp_path / "trusted-control-source"
    _copy_control_repository_with_fake_runtime(fake_repository)
    control_dir, control_sha = _create_control_bundle(
        tmp_path,
        repository_root=fake_repository,
    )
    report = tmp_path / "drain-report.json"
    _write_zero_drain_report(report)
    source_fingerprint = _source_fingerprint(ROOT)
    manifest_dir = tmp_path / "manifest"
    created = _create_manifest(
        ROOT,
        manifest_dir,
        route_mode="allowlist",
        rollback_fingerprint=source_fingerprint,
        control_bundle_sha=control_sha,
    )
    assert created.returncode == 0, created.stderr
    manifest_sha = hashlib.sha256(
        (manifest_dir / "release-manifest.json").read_bytes()
    ).hexdigest()
    env_file = root / ".env"
    env_file.write_text(
        "DURABLE_AGENT_EXECUTION_SCHEMA_READY=true\n"
        "DURABLE_AGENT_EXECUTION_ROUTE_MODE=allowlist\n"
        f"DURABLE_AGENT_EXECUTION_USER_ALLOWLIST={CANARY_USER}\n"
        f"DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST={CANARY_NOVEL}\n"
        "V1_FRESH_AGENT_STARTS_ENABLED=true\n",
        encoding="utf-8",
    )
    environment = _runtime_environment(
        root,
        fake_bin,
        log,
        control_dir,
        control_sha,
        RELEASE_ACTION="allowlist_release",
        RELEASE_ROUTE_MODE="allowlist",
        RELEASE_MANIFEST_DIR=str(manifest_dir),
        RELEASE_MANIFEST_SHA256=manifest_sha,
        CANARY_USER_ID=CANARY_USER,
        CANARY_NOVEL_ID=CANARY_NOVEL,
        FAKE_DRAIN_REPORT=str(report),
    )
    acquired = _run(
        ["sh", str(control_dir / "scripts" / DRIVER.name), "begin-snapshot"],
        cwd=root,
        env=environment,
    )
    assert acquired.returncode != 0
    assert "current-release-receipt-missing" in acquired.stderr

    route_off = _run(
        ["sh", str(control_dir / "scripts" / DRIVER.name), "transition-runtime-config", "off"],
        cwd=root,
        env=environment,
    )
    assert route_off.returncode == 0, route_off.stderr
    assert "DURABLE_AGENT_EXECUTION_ROUTE_MODE=off" in env_file.read_text(
        encoding="utf-8"
    )
    prepared = _run(
        ["sh", str(control_dir / "scripts" / DRIVER.name), "prepare-release"],
        cwd=root,
        env=environment,
    )
    assert prepared.returncode == 0, prepared.stderr
    drain_sha = prepared.stdout.strip().removeprefix(
        "prepare-release-ok:verifiedDrain:"
    )
    assert len(drain_sha) == 64
    allowlist_environment = {
        **environment,
        "VERIFIED_DRAIN_SHA256": drain_sha,
        # fixture 在此模拟前一步已把运行三镜像切到 manifest target。
        "FAKE_ROLLBACK_WEB": TARGET_WEB,
        "FAKE_ROLLBACK_CORE": TARGET_CORE,
        "FAKE_ROLLBACK_AGENT": TARGET_AGENT,
        "FAKE_V1_FRESH": "true",
    }
    allowlist = _run(
        [
            "sh",
            str(control_dir / "scripts" / DRIVER.name),
            "transition-runtime-config",
            "allowlist",
        ],
        cwd=root,
        env=allowlist_environment,
    )
    assert allowlist.returncode == 0, allowlist.stderr
    final_env = env_file.read_text(encoding="utf-8")
    assert "DURABLE_AGENT_EXECUTION_ROUTE_MODE=allowlist" in final_env
    assert "DURABLE_AGENT_EXECUTION_SCHEMA_READY=true" in final_env
    assert "V1_FRESH_AGENT_STARTS_ENABLED=true" in final_env
    assert log.read_text(encoding="utf-8").count("docker:compose ") >= 2


@pytest.mark.parametrize(
    "fault_point",
    (
        "receipt-create",
        "receipt-before-publish",
        "current-temp-written",
        "before-current-replace",
    ),
)
def test_allowlist_precommit_fault_restores_off_and_preserves_nonzero_status(
    tmp_path: Path,
    fault_point: str,
) -> None:
    root, driver, environment, base_receipt = _prepare_allowlist_transaction(tmp_path)
    failed = _run(
        ["sh", str(driver), "finalize-allowlist-transaction"],
        cwd=root,
        env={**environment, "DURABLE_AGENT_RELEASE_FAULT_POINT": fault_point},
    )

    assert failed.returncode == 90, failed.stderr
    receipt_root = root / ".durable-agent-v2-release-receipts"
    assert (receipt_root / "current").read_text(encoding="ascii").strip() == base_receipt
    lock_dir = root / ".durable-agent-v2-release-transactions" / LOCK_ID
    assert (lock_dir / "state").read_text(encoding="ascii") == "failed\n"
    env_text = (root / ".env").read_text(encoding="utf-8")
    assert "DURABLE_AGENT_EXECUTION_ROUTE_MODE=off" in env_text
    assert "V1_FRESH_AGENT_STARTS_ENABLED=false" in env_text
    guard = json.loads(
        (root / ".durable-agent-v2-release-guard" / "guard.json").read_text(
            encoding="utf-8"
        )
    )
    assert guard["state"] == "off"
    assert (root / ".durable-agent-v2-release-transaction.lock").is_file()


@pytest.mark.parametrize(
    "fault_point",
    ("after-current-replace", "after-current-root-fsync", "before-lock-cleanup"),
)
def test_allowlist_current_advanced_fault_never_rolls_back_or_marks_failed(
    tmp_path: Path,
    fault_point: str,
) -> None:
    root, driver, environment, base_receipt = _prepare_allowlist_transaction(tmp_path)
    interrupted = _run(
        ["sh", str(driver), "finalize-allowlist-transaction"],
        cwd=root,
        env={**environment, "DURABLE_AGENT_RELEASE_FAULT_POINT": fault_point},
    )
    assert interrupted.returncode in {0, 90}, interrupted.stderr
    receipt_root = root / ".durable-agent-v2-release-receipts"
    committed_receipt = (receipt_root / "current").read_text(
        encoding="ascii"
    ).strip()
    assert committed_receipt != base_receipt
    env_text = (root / ".env").read_text(encoding="utf-8")
    assert "DURABLE_AGENT_EXECUTION_ROUTE_MODE=allowlist" in env_text
    assert "V1_FRESH_AGENT_STARTS_ENABLED=true" in env_text
    guard_path = root / ".durable-agent-v2-release-guard" / "guard.json"
    assert json.loads(guard_path.read_text(encoding="utf-8"))["state"] != "off"
    lock_dir = root / ".durable-agent-v2-release-transactions" / LOCK_ID
    if lock_dir.exists():
        assert (lock_dir / "state").read_text(encoding="ascii") != "failed\n"

    recovery_environment = dict(environment)
    recovery_environment.pop("DURABLE_AGENT_RELEASE_FAULT_POINT", None)
    recovered = _run(
        ["sh", str(driver), "mark-transaction-failed"],
        cwd=root,
        env=recovery_environment,
    )
    assert recovered.returncode == 0, recovered.stderr
    assert "already-committed" in recovered.stdout
    assert not lock_dir.exists()
    assert not (root / ".durable-agent-v2-release-transaction.lock").exists()
    assert (receipt_root / "current").read_text(
        encoding="ascii"
    ).strip() == committed_receipt
    guard = json.loads(guard_path.read_text(encoding="utf-8"))
    assert guard["state"] == "committed"
    assert guard["committedReceiptSha256"] == committed_receipt
    assert "DURABLE_AGENT_EXECUTION_ROUTE_MODE=allowlist" in (
        root / ".env"
    ).read_text(encoding="utf-8")


def test_mark_failed_is_read_only_idempotent_only_for_exact_failed_lock_owner(
    tmp_path: Path,
) -> None:
    root, driver, environment, _ = _prepare_allowlist_transaction(tmp_path)
    first = _run(
        ["sh", str(driver), "mark-transaction-failed"],
        cwd=root,
        env=environment,
    )
    assert first.returncode == 0, first.stderr
    assert "release-transaction-failed" in first.stdout
    lock_dir = root / ".durable-agent-v2-release-transactions" / LOCK_ID
    assert (lock_dir / "state").read_text(encoding="ascii") == "failed\n"
    log_path = Path(environment["FAKE_LOG"])
    log_before_retry = log_path.read_text(encoding="utf-8")

    repeated = _run(
        ["sh", str(driver), "mark-transaction-failed"],
        cwd=root,
        env=environment,
    )
    assert repeated.returncode == 0, repeated.stderr
    assert "release-transaction-failed" in repeated.stdout
    assert log_path.read_text(encoding="utf-8") == log_before_retry

    wrong_owner = _run(
        ["sh", str(driver), "mark-transaction-failed"],
        cwd=root,
        env={**environment, "GITHUB_RUN_ATTEMPT": "2"},
    )
    assert wrong_owner.returncode != 0
    assert "control-bundle-provenance" in wrong_owner.stderr
    assert (lock_dir / "state").read_text(encoding="ascii") == "failed\n"
    assert log_path.read_text(encoding="utf-8") == log_before_retry


def test_allowlist_runner_term_preserves_143_and_falls_back_before_commit(
    tmp_path: Path,
) -> None:
    root, driver, environment, base_receipt = _prepare_allowlist_transaction(tmp_path)
    marker = tmp_path / "compose-blocked"
    release = tmp_path / "compose-release"
    process = subprocess.Popen(  # noqa: S603 - 固定 driver 与隔离 fake runtime
        [POSIX_SHELL, str(driver), "finalize-allowlist-transaction"],
        cwd=root,
        env={
            **environment,
            "FAKE_COMPOSE_BLOCK_MARKER": str(marker),
            "FAKE_COMPOSE_BLOCK_RELEASE": str(release),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 10
    while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert marker.exists(), process.communicate(timeout=1)
    process.terminate()
    release.touch()
    stdout, stderr = process.communicate(timeout=20)

    assert process.returncode == 143, (stdout, stderr)
    receipt_root = root / ".durable-agent-v2-release-receipts"
    assert (receipt_root / "current").read_text(encoding="ascii").strip() == base_receipt
    assert "DURABLE_AGENT_EXECUTION_ROUTE_MODE=off" in (root / ".env").read_text(
        encoding="utf-8"
    )
    guard = json.loads(
        (root / ".durable-agent-v2-release-guard" / "guard.json").read_text(
            encoding="utf-8"
        )
    )
    assert guard["state"] == "off"
    lock_dir = root / ".durable-agent-v2-release-transactions" / LOCK_ID
    assert (lock_dir / "state").read_text(encoding="ascii") == "failed\n"


def test_scope_drift_fails_inside_locked_snapshot_without_compose_or_ddl(
    tmp_path: Path,
) -> None:
    root = tmp_path / "server"
    root.mkdir()
    control_dir, control_sha = _create_control_bundle(tmp_path)
    environment = _lock_environment(root, control_dir, control_sha)
    acquired = _run(
        ["sh", str(control_dir / "scripts" / DRIVER.name), "begin-snapshot"],
        cwd=root,
        env=environment,
    )
    assert acquired.returncode != 0
    assert "current-release-receipt-missing" in acquired.stderr
    manifest_dir = tmp_path / "manifest"
    created = _create_manifest(
        ROOT,
        manifest_dir,
        control_bundle_sha=control_sha,
    )
    assert created.returncode == 0, created.stderr
    manifest_sha = hashlib.sha256(
        (manifest_dir / "release-manifest.json").read_bytes()
    ).hexdigest()
    (root / ".env").write_text(
        "DURABLE_AGENT_EXECUTION_SCHEMA_READY=true\n"
        "DURABLE_AGENT_EXECUTION_ROUTE_MODE=off\n"
        f"DURABLE_AGENT_EXECUTION_USER_ALLOWLIST={CANARY_USER}\n"
        f"DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST={CANARY_NOVEL}\n"
        "V1_FRESH_AGENT_STARTS_ENABLED=false\n",
        encoding="utf-8",
    )
    result = _run(
        ["sh", str(control_dir / "scripts" / DRIVER.name), "transition-runtime-config", "off"],
        cwd=root,
        env={
            **environment,
            "RELEASE_MANIFEST_DIR": str(manifest_dir),
            "RELEASE_MANIFEST_SHA256": manifest_sha,
            "CANARY_USER_ID": "attacker-user",
            "CANARY_NOVEL_ID": CANARY_NOVEL,
        },
    )
    assert result.returncode != 0
    assert "transition-canary-scope" in result.stderr
    assert (root / ".durable-agent-v2-release-transaction.lock").is_file()
    assert "docker compose" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("missing", "expected_error"),
    (
        ("confirm", "production-confirm-file"),
        ("evidence", "production-evidence-dir"),
        ("manifest", "release-manifest-dir"),
    ),
)
def test_release_database_missing_required_input_is_nonzero_before_external_action(
    tmp_path: Path,
    missing: str,
    expected_error: str,
) -> None:
    root = tmp_path / "server"
    root.mkdir()
    control_dir, control_sha = _create_control_bundle(tmp_path)
    environment = _lock_environment(root, control_dir, control_sha)
    acquired = _run(
        ["sh", str(control_dir / "scripts" / DRIVER.name), "begin-snapshot"],
        cwd=root,
        env=environment,
    )
    assert acquired.returncode != 0
    manifest_dir = tmp_path / "manifest"
    created = _create_manifest(
        ROOT,
        manifest_dir,
        control_bundle_sha=control_sha,
    )
    assert created.returncode == 0, created.stderr
    manifest_sha = hashlib.sha256(
        (manifest_dir / "release-manifest.json").read_bytes()
    ).hexdigest()
    command_log = tmp_path / "external.log"
    fake_bin = tmp_path / "external-bin"
    fake_bin.mkdir()
    for name in ("docker", "psql"):
        path = fake_bin / name
        path.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$0 $*\" >> \"$EXTERNAL_LOG\"\nexit 99\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
    action_environment = {
        **environment,
        "PATH": f"{fake_bin}:{environment['PATH']}",
        "EXTERNAL_LOG": str(command_log),
        "RELEASE_MANIFEST_DIR": str(manifest_dir),
        "RELEASE_MANIFEST_SHA256": manifest_sha,
        "DURABLE_AGENT_PRODUCTION_CONFIRM_FILE": str(tmp_path / "confirm"),
        "DURABLE_AGENT_PRODUCTION_EVIDENCE_DIR": str(tmp_path / "evidence"),
    }
    if missing == "confirm":
        action_environment.pop("DURABLE_AGENT_PRODUCTION_CONFIRM_FILE")
    elif missing == "evidence":
        action_environment.pop("DURABLE_AGENT_PRODUCTION_EVIDENCE_DIR")
    else:
        action_environment.pop("RELEASE_MANIFEST_DIR")
        action_environment.pop("RELEASE_MANIFEST_SHA256")

    result = _run(
        ["sh", str(control_dir / "scripts" / DRIVER.name), "release-database", "novelwriter"],
        cwd=root,
        env=action_environment,
    )

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert not command_log.exists()


def test_missing_verified_drain_fails_before_compose_or_ddl(tmp_path: Path) -> None:
    root = tmp_path / "server"
    root.mkdir()
    control_dir, control_sha = _create_control_bundle(tmp_path)
    environment = _lock_environment(root, control_dir, control_sha)
    acquired = _run(
        ["sh", str(control_dir / "scripts" / DRIVER.name), "begin-snapshot"],
        cwd=root,
        env=environment,
    )
    assert acquired.returncode != 0
    manifest_dir = tmp_path / "manifest"
    created = _create_manifest(
        ROOT,
        manifest_dir,
        control_bundle_sha=control_sha,
    )
    assert created.returncode == 0, created.stderr
    manifest_sha = hashlib.sha256(
        (manifest_dir / "release-manifest.json").read_bytes()
    ).hexdigest()
    missing = _run(
        ["sh", str(control_dir / "scripts" / DRIVER.name), "verify-drain-binding"],
        cwd=root,
        env={
            **environment,
            "RELEASE_MANIFEST_DIR": str(manifest_dir),
            "RELEASE_MANIFEST_SHA256": manifest_sha,
        },
    )
    assert missing.returncode != 0
    assert "verified-drain-sha256" in missing.stderr
    assert "docker compose" not in missing.stdout + missing.stderr


def test_deploy_forces_manifest_lock_scope_and_drain_before_compose_or_ddl() -> None:
    source = DEPLOY.read_text(encoding="utf-8")
    assert "DURABLE_AGENT_RELEASE_MANIFEST_DIR:?" in source
    assert "DURABLE_AGENT_RELEASE_LOCK_ID:?" in source
    assert "DEPLOY_BUNDLE_PATH:?" in source
    assert "无 bundle 只保留" not in source
    lock_index = source.index("# GitHub concurrency 只能减少并发")
    git_mutation_index = source.index('safe_git init -b "$BRANCH"')
    drain_index = source.index("verify_verified_drain_evidence || exit 1")
    compose_index = source.index("docker compose version >/dev/null")
    assert lock_index < drain_index < git_mutation_index < compose_index
    assert 'sh "$migration_helper" up' not in source
    assert source.count("verify_running_core_rollout_config") >= 3


def test_release_scripts_parse_and_migration_sql_hashes_remain_frozen() -> None:
    for script in (DRIVER, DEPLOY, UPLOAD_MANIFEST, UPLOAD_SOURCE):
        result = _run(["sh", "-n", str(script)])
        assert result.returncode == 0, result.stderr
    assert hashlib.sha256(FORWARD.read_bytes()).hexdigest() == EXPECTED_FORWARD_SHA
    assert hashlib.sha256(ROLLBACK.read_bytes()).hexdigest() == EXPECTED_ROLLBACK_SHA
