from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/durable_agent_v2_development_evidence_v2.py"
DEVELOPMENT_WORKFLOW = ROOT / ".github/workflows/durable-agent-v2-development-evidence.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/durable-agent-v2-release.yml"

NOW = "2026-09-01T12:00:00Z"
QUALIFICATION_ISSUED = "2026-09-01T11:00:00Z"
QUALIFICATION_EXPIRES = "2026-09-20T11:00:00Z"
CANDIDATE_ISSUED = "2026-09-01T11:30:00Z"
CANDIDATE_EXPIRES = "2026-09-02T11:30:00Z"
MIGRATION_COMMIT = "1" * 40
TARGET_COMMIT = "2" * 40
FORWARD_SHA = "3" * 64
ROLLBACK_SHA = "4" * 64
PRE_CONTRACT = "5" * 64
POST_CONTRACT = "6" * 64
DEVELOPMENT_SCOPE = "7" * 64
CANARY_SCENARIO = "8" * 64
EXECUTION_FINGERPRINT = "9" * 64
RESOURCE_POLICY_SHA = "3" * 64
PROVIDER_POLICY_SHA = "4" * 64
RESOURCE_HOST_IDENTITY = "1" * 64
PROVIDER_IDENTITY = "0" * 64
WEB_DIGEST = "sha256:" + "a" * 64
CORE_DIGEST = "sha256:" + "b" * 64
AGENT_DIGEST = "sha256:" + "c" * 64
REPOSITORY = "owner/repository"

QUALIFICATION_FILES = {
    "migration-backup": "migration-backup-report.json",
    "live-contract": "live-contract-report.json",
    "idempotent-forward": "idempotent-forward-report.json",
    "rollback-rehearsal": "rollback-rehearsal-report.json",
}
CANDIDATE_FILES = {
    "fault-injection": "fault-injection-report.json",
    "resource-constrained": "resource-constrained-report.json",
    "provider-canary": "provider-canary-report.json",
}


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


def _run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- 参数完全由本测试构造
        [sys.executable, str(SCRIPT), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _evidence_module() -> Any:
    scripts_path = str(ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    return importlib.import_module("durable_agent_v2_development_evidence_v2")


def _producer(*, head: str, run_id: str, run_attempt: str) -> dict[str, str]:
    return {
        "headSha": head,
        "repository": REPOSITORY,
        "runAttempt": run_attempt,
        "runId": run_id,
        "workflowPath": ".github/workflows/durable-agent-v2-development-evidence.yml",
    }


def _migration_bundle_fingerprint() -> str:
    return _sha(
        _canonical(
            {
                "forwardSqlSha256": FORWARD_SHA,
                "migrationSourceCommit": MIGRATION_COMMIT,
                "postContractFingerprint": POST_CONTRACT,
                "preContractFingerprint": PRE_CONTRACT,
                "rollbackSqlSha256": ROLLBACK_SHA,
            }
        )[:-1]
    )


def _report_source(
    directory: Path,
    documents: dict[str, dict[str, Any]],
    files: dict[str, str],
) -> None:
    directory.mkdir(mode=0o700)
    payloads: dict[str, bytes] = {}
    for report_type, name in files.items():
        payload = _canonical(documents[report_type])
        path = directory / name
        path.write_bytes(payload)
        path.chmod(0o600)
        payloads[name] = payload
    checksum = directory / "SHA256SUMS"
    checksum.write_text(
        "".join(f"{_sha(payloads[name])}  {name}\n" for name in sorted(payloads)),
        encoding="ascii",
    )
    checksum.chmod(0o600)


def _refresh_checksums(directory: Path) -> None:
    payloads = {
        path.name: path.read_bytes() for path in directory.iterdir() if path.name != "SHA256SUMS"
    }
    checksum = directory / "SHA256SUMS"
    checksum.write_text(
        "".join(f"{_sha(payloads[name])}  {name}\n" for name in sorted(payloads)),
        encoding="ascii",
    )
    checksum.chmod(0o600)


def _qualification_reports() -> dict[str, dict[str, Any]]:
    producer = _producer(head=MIGRATION_COMMIT, run_id="100", run_attempt="1")
    common = {
        "database": "novelwriterdev",
        "developmentScopeSha256": DEVELOPMENT_SCOPE,
        "expiresAt": QUALIFICATION_EXPIRES,
        "issuedAt": QUALIFICATION_ISSUED,
        "migrationBundleFingerprint": _migration_bundle_fingerprint(),
        "producer": producer,
        "sensitiveContentAbsent": True,
    }

    def report(
        report_type: str,
        observations: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            **common,
            "format": f"inkforge-durable-agent-v2-{report_type}-report/2",
            "observations": observations,
            "reportType": report_type,
        }

    backup = report(
        "migration-backup",
        {
            "executionAofStatus": "ok",
            "executionRedisRdbReadable": True,
            "executionRedisRdbSha256": "d" * 64,
            "postgresCustomDumpReadable": True,
            "postgresCustomDumpSha256": "e" * 64,
            "postgresRestoreRequiresExecutionQuarantine": True,
            "status": "passed",
        },
    )
    backup_sha = _sha(_canonical(backup))
    return {
        "migration-backup": backup,
        "live-contract": report(
            "live-contract",
            {
                "contractEvidenceSha256": "f" * 64,
                "contractFingerprint": POST_CONTRACT,
                "guardFingerprint": POST_CONTRACT,
                "schemaState": "migrated-empty-v2",
                "status": "passed",
                "structureDiffCount": 0,
            },
        ),
        "idempotent-forward": report(
            "idempotent-forward",
            {
                "backupReportSha256": backup_sha,
                "firstForwardExitCode": 0,
                "firstPostContractFingerprint": POST_CONTRACT,
                "partialStateObserved": False,
                "secondForwardExitCode": 0,
                "secondPostContractFingerprint": POST_CONTRACT,
                "status": "passed",
                "v2FactCount": 0,
            },
        ),
        "rollback-rehearsal": report(
            "rollback-rehearsal",
            {
                "finalContractFingerprint": POST_CONTRACT,
                "postRollbackContractFingerprint": PRE_CONTRACT,
                "preRollbackState": "migrated-empty-v2",
                "reforwardExitCode": 0,
                "residueCount": 0,
                "rollbackExitCode": 0,
                "status": "passed",
                "v2FactCountBeforeRollback": 0,
            },
        ),
    }


def _candidate_reports(
    *,
    run_id: str = "200",
    run_attempt: str = "2",
) -> dict[str, dict[str, Any]]:
    producer = _producer(
        head=TARGET_COMMIT,
        run_id=run_id,
        run_attempt=run_attempt,
    )
    common = {
        "canaryScenarioFingerprint": CANARY_SCENARIO,
        "developmentScopeSha256": DEVELOPMENT_SCOPE,
        "executionManifestFingerprint": EXECUTION_FINGERPRINT,
        "expiresAt": CANDIDATE_EXPIRES,
        "images": {
            "agent": AGENT_DIGEST,
            "core": CORE_DIGEST,
            "web": WEB_DIGEST,
        },
        "issuedAt": CANDIDATE_ISSUED,
        "producer": producer,
        "sensitiveContentAbsent": True,
        "targetReleaseCommit": TARGET_COMMIT,
    }

    def report(
        report_type: str,
        observations: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            **common,
            "format": f"inkforge-durable-agent-v2-{report_type}-report/2",
            "observations": observations,
            "reportType": report_type,
        }

    return {
        "fault-injection": report(
            "fault-injection",
            {
                "agentRestartJournalReplayPassed": True,
                "allResourcesRemoved": True,
                "aofAgentFreshHealthcheckPassed": True,
                "callbackReceiptLossPassed": True,
                "callbackReceiptIdentityMatched": True,
                "callbackReceiptIdentitySha256": "d" * 64,
                "cancelBeforeAgentSubmitPassed": True,
                "cancelProviderCalls": 0,
                "cleanupPassed": True,
                "coreRestartCallbackReplayPassed": True,
                "duplicateAnswerMessages": 0,
                "duplicateBillingReservations": 0,
                "duplicateTerminalEvents": 0,
                "duplicateTokenUsage": 0,
                "executionRedisAofRestartPassed": True,
                "happyIdempotencyPassed": True,
                "sseCursorReconnectPassed": True,
                "status": "passed",
            },
        ),
        "resource-constrained": report(
            "resource-constrained",
            {
                "cgroupMode": "v2",
                "cpuCount": 2,
                "cpuThrottledMicros": 250_000,
                "hostIdentitySha256": RESOURCE_HOST_IDENTITY,
                "latencySloPassed": True,
                "maxProviderConcurrency": 3,
                "measuredLatencySummarySha256": "2" * 64,
                "memoryMiB": 2048,
                "nonTerminalRuns": 0,
                "observationSeconds": 1800,
                "oomKills": 0,
                "peakRssMiB": 1536,
                "pendingExecutions": 0,
                "performancePolicySha256": RESOURCE_POLICY_SHA,
                "performancePolicyVersion": "durable-agent-v2-resource-slo/1",
                "quarantineEvents": 0,
                "redisEvictions": 0,
                "sampleCount": 30,
                "sloHardFailures": 0,
                "status": "passed",
                "swapMiB": 0,
                "unexpectedRestarts": 0,
            },
        ),
        "provider-canary": report(
            "provider-canary",
            {
                "answerMessages": 1,
                "completedResultMessageBinding": True,
                "completedRuns": 1,
                "completionTokens": 80,
                "costMicros": 1234,
                "credentialsStored": False,
                "duplicateBillingReservations": 0,
                "duplicateTokenUsage": 0,
                "idempotentReplayPhysicalCallsUnchanged": True,
                "maxCompletionTokens": 100,
                "maxCostMicros": 2000,
                "maxPromptTokens": 200,
                "maxReasoningTokens": 40,
                "maxTotalTokens": 300,
                "mode": "real",
                "operation": "long_serial.answer_question",
                "promptTokens": 100,
                "providerAttempts": 1,
                "providerCalls": 1,
                "providerIdentitySha256": PROVIDER_IDENTITY,
                "reasoningTokens": 20,
                "reconciliationRequiredCount": 0,
                "requestPayloadStored": False,
                "reservationChargedMicros": 1234,
                "reservationCount": 1,
                "reservationRemainingMicros": 0,
                "reservationStatus": "settled",
                "reservationUsageBinding": True,
                "responsePayloadStored": False,
                "status": "passed",
                "terminalState": "completed",
                "tokenUsageBindingUnique": True,
                "tokenUsageCount": 1,
                "totalTokens": 180,
                "usageComplete": True,
                "usageCostPolicySha256": PROVIDER_POLICY_SHA,
                "usageCostPolicyVersion": ("durable-agent-v2-provider-canary-budget/1"),
                "usageCostSummarySha256": "5" * 64,
            },
        ),
    }


def _qualification_create_args(
    reports: Path,
    output: Path,
) -> list[str]:
    return [
        "create-qualification",
        "--reports-dir",
        str(reports),
        "--output-dir",
        str(output),
        "--development-scope-sha256",
        DEVELOPMENT_SCOPE,
        "--migration-source-commit",
        MIGRATION_COMMIT,
        "--forward-sql-sha256",
        FORWARD_SHA,
        "--rollback-sql-sha256",
        ROLLBACK_SHA,
        "--pre-contract-fingerprint",
        PRE_CONTRACT,
        "--post-contract-fingerprint",
        POST_CONTRACT,
        "--producer-repository",
        REPOSITORY,
        "--producer-run-id",
        "100",
        "--producer-run-attempt",
        "1",
        "--producer-head-sha",
        MIGRATION_COMMIT,
        "--issued-at",
        QUALIFICATION_ISSUED,
        "--expires-at",
        QUALIFICATION_EXPIRES,
        "--trusted-now",
        NOW,
    ]


def _qualification_verify_args(
    directory: Path,
    digest: str,
) -> list[str]:
    return [
        "verify-qualification",
        "--qualification-dir",
        str(directory),
        "--expected-sha256",
        digest,
        "--expected-development-scope-sha256",
        DEVELOPMENT_SCOPE,
        "--expected-migration-source-commit",
        MIGRATION_COMMIT,
        "--expected-forward-sql-sha256",
        FORWARD_SHA,
        "--expected-rollback-sql-sha256",
        ROLLBACK_SHA,
        "--expected-pre-contract-fingerprint",
        PRE_CONTRACT,
        "--expected-post-contract-fingerprint",
        POST_CONTRACT,
        "--expected-repository",
        REPOSITORY,
        "--expected-run-id",
        "100",
        "--expected-run-attempt",
        "1",
        "--trusted-now",
        NOW,
    ]


def _candidate_create_args(
    reports: Path,
    output: Path,
    qualification: Path,
    qualification_sha: str,
    *,
    run_id: str = "200",
    run_attempt: str = "2",
) -> list[str]:
    return [
        "create-candidate",
        "--reports-dir",
        str(reports),
        "--output-dir",
        str(output),
        "--qualification-dir",
        str(qualification),
        "--migration-qualification-sha256",
        qualification_sha,
        "--target-release-commit",
        TARGET_COMMIT,
        "--development-scope-sha256",
        DEVELOPMENT_SCOPE,
        "--canary-scenario-fingerprint",
        CANARY_SCENARIO,
        "--execution-manifest-fingerprint",
        EXECUTION_FINGERPRINT,
        "--resource-performance-policy-sha256",
        RESOURCE_POLICY_SHA,
        "--provider-usage-cost-policy-sha256",
        PROVIDER_POLICY_SHA,
        "--provider-max-prompt-tokens",
        "200",
        "--provider-max-completion-tokens",
        "100",
        "--provider-max-reasoning-tokens",
        "40",
        "--provider-max-total-tokens",
        "300",
        "--provider-max-cost-micros",
        "2000",
        "--resource-host-identity-sha256",
        RESOURCE_HOST_IDENTITY,
        "--provider-identity-sha256",
        PROVIDER_IDENTITY,
        "--web-digest",
        WEB_DIGEST,
        "--core-digest",
        CORE_DIGEST,
        "--agent-digest",
        AGENT_DIGEST,
        "--producer-repository",
        REPOSITORY,
        "--producer-run-id",
        run_id,
        "--producer-run-attempt",
        run_attempt,
        "--producer-head-sha",
        TARGET_COMMIT,
        "--issued-at",
        CANDIDATE_ISSUED,
        "--expires-at",
        CANDIDATE_EXPIRES,
        "--trusted-now",
        NOW,
    ]


def _candidate_verify_args(
    directory: Path,
    digest: str,
    qualification: Path,
    qualification_sha: str,
    *,
    run_id: str = "200",
    run_attempt: str = "2",
) -> list[str]:
    return [
        "verify-candidate",
        "--candidate-dir",
        str(directory),
        "--qualification-dir",
        str(qualification),
        "--expected-sha256",
        digest,
        "--expected-migration-qualification-sha256",
        qualification_sha,
        "--expected-target-release-commit",
        TARGET_COMMIT,
        "--expected-development-scope-sha256",
        DEVELOPMENT_SCOPE,
        "--expected-canary-scenario-fingerprint",
        CANARY_SCENARIO,
        "--expected-execution-manifest-fingerprint",
        EXECUTION_FINGERPRINT,
        "--expected-web-digest",
        WEB_DIGEST,
        "--expected-core-digest",
        CORE_DIGEST,
        "--expected-agent-digest",
        AGENT_DIGEST,
        "--expected-resource-performance-policy-sha256",
        RESOURCE_POLICY_SHA,
        "--expected-provider-usage-cost-policy-sha256",
        PROVIDER_POLICY_SHA,
        "--expected-provider-max-prompt-tokens",
        "200",
        "--expected-provider-max-completion-tokens",
        "100",
        "--expected-provider-max-reasoning-tokens",
        "40",
        "--expected-provider-max-total-tokens",
        "300",
        "--expected-provider-max-cost-micros",
        "2000",
        "--expected-resource-host-identity-sha256",
        RESOURCE_HOST_IDENTITY,
        "--expected-provider-identity-sha256",
        PROVIDER_IDENTITY,
        "--expected-repository",
        REPOSITORY,
        "--expected-run-id",
        run_id,
        "--expected-run-attempt",
        run_attempt,
        "--trusted-now",
        NOW,
    ]


def _created_digest(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().rsplit(":", 1)[1]


def _create_valid_qualification(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "qualification-reports"
    output = tmp_path / "qualification"
    _report_source(source, _qualification_reports(), QUALIFICATION_FILES)
    digest = _created_digest(_run(_qualification_create_args(source, output)))
    return output, digest


def _create_valid_candidate(
    tmp_path: Path,
) -> tuple[Path, str, Path, str]:
    qualification, qualification_sha = _create_valid_qualification(tmp_path)
    source = tmp_path / "candidate-reports"
    output = tmp_path / "candidate"
    _report_source(source, _candidate_reports(), CANDIDATE_FILES)
    digest = _created_digest(
        _run(
            _candidate_create_args(
                source,
                output,
                qualification,
                qualification_sha,
            )
        )
    )
    return output, digest, qualification, qualification_sha


def test_fingerprints_separate_development_topology_from_canary_scenario() -> None:
    scope = _run(
        [
            "development-scope-fingerprint",
            "--database-identity-sha256",
            "1" * 64,
            "--ordinary-redis-identity-sha256",
            "2" * 64,
            "--execution-redis-identity-sha256",
            "3" * 64,
            "--topology-sha256",
            "4" * 64,
        ]
    )
    scenario = _run(
        [
            "canary-scenario-fingerprint",
            "--actor-scope-sha256",
            "1" * 64,
            "--assertions-sha256",
            "2" * 64,
            "--fixture-sha256",
            "3" * 64,
            "--operation",
            "long_serial.answer_question",
            "--scenario-version",
            "durable-agent-v2-real-provider-canary/1",
        ]
    )
    assert scope.returncode == 0, scope.stderr
    assert scenario.returncode == 0, scenario.stderr
    assert scope.stdout.strip() != scenario.stdout.strip()
    assert len(scope.stdout.strip()) == len(scenario.stdout.strip()) == 64


def test_v2_foundation_does_not_unlock_existing_workflows() -> None:
    development = DEVELOPMENT_WORKFLOW.read_text(encoding="utf-8")
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "real-provider-identity-not-automated" in development
    assert "actions/upload-artifact" not in development
    assert "durable_agent_v2_development_evidence_v2.py" not in development
    assert "durable_agent_v2_development_evidence_v2.py" not in release


def test_builds_and_verifies_two_immutable_semantic_bundles(tmp_path: Path) -> None:
    candidate, candidate_sha, qualification, qualification_sha = _create_valid_candidate(tmp_path)
    qualification_result = _run(_qualification_verify_args(qualification, qualification_sha))
    candidate_result = _run(
        _candidate_verify_args(
            candidate,
            candidate_sha,
            qualification,
            qualification_sha,
        )
    )
    assert qualification_result.returncode == 0, qualification_result.stderr
    assert candidate_result.returncode == 0, candidate_result.stderr
    for directory in (qualification, candidate):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in directory.iterdir())
    assert not list(tmp_path.glob(".*.partial-*"))

    recreate = _run(
        _candidate_create_args(
            tmp_path / "candidate-reports",
            candidate,
            qualification,
            qualification_sha,
        )
    )
    assert recreate.returncode != 0
    assert "拒绝覆盖" in recreate.stderr


def test_one_qualification_can_bind_a_later_distinct_candidate_run(
    tmp_path: Path,
) -> None:
    qualification, qualification_sha = _create_valid_qualification(tmp_path)
    source = tmp_path / "candidate-reports-later"
    output = tmp_path / "candidate-later"
    _report_source(
        source,
        _candidate_reports(run_id="201", run_attempt="3"),
        CANDIDATE_FILES,
    )
    candidate_sha = _created_digest(
        _run(
            _candidate_create_args(
                source,
                output,
                qualification,
                qualification_sha,
                run_id="201",
                run_attempt="3",
            )
        )
    )
    verified = _run(
        _candidate_verify_args(
            output,
            candidate_sha,
            qualification,
            qualification_sha,
            run_id="201",
            run_attempt="3",
        )
    )
    assert verified.returncode == 0, verified.stderr


@pytest.mark.parametrize(
    ("mutate", "error_fragment"),
    [
        (
            lambda reports: reports["migration-backup"].__setitem__("format", "test-report/1"),
            "format 无效",
        ),
        (
            lambda reports: reports["live-contract"].__setitem__("extra", True),
            "字段集合无效",
        ),
        (
            lambda reports: reports["idempotent-forward"]["observations"].__setitem__(
                "v2FactCount", 1
            ),
            "forward V2 fact count",
        ),
        (
            lambda reports: reports["rollback-rehearsal"]["observations"].__setitem__(
                "postRollbackContractFingerprint", POST_CONTRACT
            ),
            "post rollback contract",
        ),
    ],
)
def test_qualification_rejects_arbitrary_or_semantically_false_reports(
    tmp_path: Path,
    mutate: Any,
    error_fragment: str,
) -> None:
    reports = _qualification_reports()
    mutate(reports)
    source = tmp_path / "reports"
    output = tmp_path / "qualification"
    _report_source(source, reports, QUALIFICATION_FILES)
    result = _run(_qualification_create_args(source, output))
    assert result.returncode != 0
    assert error_fragment in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    ("mutate", "error_fragment"),
    [
        (
            lambda reports: reports["fault-injection"].__setitem__("targetReleaseCommit", "f" * 40),
            "targetReleaseCommit 绑定漂移",
        ),
        (
            lambda reports: reports["resource-constrained"]["images"].__setitem__(
                "core", "sha256:" + "f" * 64
            ),
            "images 绑定漂移",
        ),
        (
            lambda reports: reports["provider-canary"]["producer"].__setitem__("runId", "999"),
            "producer 绑定漂移",
        ),
        (
            lambda reports: reports["resource-constrained"]["observations"].__setitem__(
                "observationSeconds", 10
            ),
            "resource observation seconds",
        ),
        (
            lambda reports: reports["provider-canary"]["observations"].__setitem__(
                "providerCalls", 2
            ),
            "providerCalls",
        ),
    ],
)
def test_candidate_rejects_wrong_source_image_run_or_semantics(
    tmp_path: Path,
    mutate: Any,
    error_fragment: str,
) -> None:
    qualification, qualification_sha = _create_valid_qualification(tmp_path)
    reports = _candidate_reports()
    mutate(reports)
    source = tmp_path / "candidate-reports"
    output = tmp_path / "candidate"
    _report_source(source, reports, CANDIDATE_FILES)
    result = _run(
        _candidate_create_args(
            source,
            output,
            qualification,
            qualification_sha,
        )
    )
    assert result.returncode != 0
    assert error_fragment in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    ("report_type", "field", "value", "error_fragment"),
    [
        ("fault-injection", "cleanupPassed", False, "cleanupPassed"),
        ("fault-injection", "allResourcesRemoved", False, "allResourcesRemoved"),
        (
            "fault-injection",
            "callbackReceiptIdentityMatched",
            False,
            "callbackReceiptIdentityMatched",
        ),
        (
            "fault-injection",
            "callbackReceiptIdentitySha256",
            "invalid",
            "callback receipt identity SHA",
        ),
        (
            "fault-injection",
            "aofAgentFreshHealthcheckPassed",
            False,
            "aofAgentFreshHealthcheckPassed",
        ),
        (
            "resource-constrained",
            "hostIdentitySha256",
            "invalid",
            "resource host identity SHA",
        ),
        ("resource-constrained", "cgroupMode", "unknown", "cgroup mode"),
        ("resource-constrained", "swapMiB", 1, "host swap MiB"),
        ("resource-constrained", "sampleCount", 29, "resource sample count"),
        ("resource-constrained", "sampleCount", "30", "resource sample count"),
        (
            "resource-constrained",
            "cpuThrottledMicros",
            -1,
            "CPU throttled micros",
        ),
        ("resource-constrained", "peakRssMiB", 2049, "peak RSS MiB"),
        ("resource-constrained", "redisEvictions", 1, "redisEvictions"),
        ("resource-constrained", "quarantineEvents", 1, "quarantineEvents"),
        ("resource-constrained", "pendingExecutions", 1, "pendingExecutions"),
        ("resource-constrained", "nonTerminalRuns", 1, "nonTerminalRuns"),
        (
            "resource-constrained",
            "performancePolicyVersion",
            "unversioned",
            "performance policy version",
        ),
        (
            "resource-constrained",
            "performancePolicySha256",
            "invalid",
            "performance policy SHA",
        ),
        (
            "resource-constrained",
            "measuredLatencySummarySha256",
            "invalid",
            "latency summary SHA",
        ),
        ("resource-constrained", "latencySloPassed", False, "latency SLO"),
        ("provider-canary", "providerAttempts", 2, "providerAttempts"),
        ("provider-canary", "providerAttempts", True, "providerAttempts"),
        ("provider-canary", "promptTokens", 201, "promptTokens 超过"),
        ("provider-canary", "completionTokens", 101, "completionTokens 超过"),
        ("provider-canary", "reasoningTokens", 41, "reasoningTokens 超过"),
        ("provider-canary", "totalTokens", 301, "totalTokens 超过"),
        ("provider-canary", "costMicros", 2001, "costMicros 超过"),
        (
            "provider-canary",
            "reservationStatus",
            "reserved",
            "reservation status",
        ),
        (
            "provider-canary",
            "reservationRemainingMicros",
            1,
            "reservationRemainingMicros",
        ),
        (
            "provider-canary",
            "reservationChargedMicros",
            1233,
            "charged micros",
        ),
        ("provider-canary", "reservationCount", 2, "reservationCount"),
        (
            "provider-canary",
            "reservationUsageBinding",
            False,
            "reservationUsageBinding",
        ),
        ("provider-canary", "tokenUsageCount", 2, "tokenUsageCount"),
        (
            "provider-canary",
            "tokenUsageBindingUnique",
            False,
            "tokenUsageBindingUnique",
        ),
        (
            "provider-canary",
            "reconciliationRequiredCount",
            1,
            "reconciliationRequiredCount",
        ),
        (
            "provider-canary",
            "completedResultMessageBinding",
            False,
            "completedResultMessageBinding",
        ),
        (
            "provider-canary",
            "idempotentReplayPhysicalCallsUnchanged",
            False,
            "idempotentReplayPhysicalCallsUnchanged",
        ),
        (
            "provider-canary",
            "usageCostPolicyVersion",
            "unversioned",
            "usage/cost policy version",
        ),
        (
            "provider-canary",
            "usageCostPolicySha256",
            "invalid",
            "usage/cost policy SHA",
        ),
        (
            "provider-canary",
            "usageCostSummarySha256",
            "invalid",
            "usage/cost summary SHA",
        ),
    ],
)
def test_candidate_v2_semantic_fields_are_exact_and_bounded(
    tmp_path: Path,
    report_type: str,
    field: str,
    value: Any,
    error_fragment: str,
) -> None:
    qualification, qualification_sha = _create_valid_qualification(tmp_path)
    reports = _candidate_reports()
    reports[report_type]["observations"][field] = value
    source = tmp_path / "candidate-reports"
    output = tmp_path / "candidate"
    _report_source(source, reports, CANDIDATE_FILES)
    result = _run(
        _candidate_create_args(
            source,
            output,
            qualification,
            qualification_sha,
        )
    )
    assert result.returncode != 0
    assert error_fragment in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_candidate_v2_observation_field_set_is_exact(
    tmp_path: Path,
    mutation: str,
) -> None:
    qualification, qualification_sha = _create_valid_qualification(tmp_path)
    reports = _candidate_reports()
    observations = reports["resource-constrained"]["observations"]
    if mutation == "missing":
        observations.pop("hostIdentitySha256")
    else:
        observations["untrustedSummary"] = "0" * 64
    source = tmp_path / "candidate-reports"
    output = tmp_path / "candidate"
    _report_source(source, reports, CANDIDATE_FILES)
    result = _run(
        _candidate_create_args(
            source,
            output,
            qualification,
            qualification_sha,
        )
    )
    assert result.returncode != 0
    assert "字段集合无效" in result.stderr


def test_candidate_rejects_expired_window_and_scope_scenario_alias(
    tmp_path: Path,
) -> None:
    qualification, qualification_sha = _create_valid_qualification(tmp_path)
    reports = _candidate_reports()
    for document in reports.values():
        document["expiresAt"] = "2026-09-01T11:59:59Z"
    source = tmp_path / "expired-reports"
    output = tmp_path / "expired"
    _report_source(source, reports, CANDIDATE_FILES)
    arguments = _candidate_create_args(
        source,
        output,
        qualification,
        qualification_sha,
    )
    arguments[arguments.index("--expires-at") + 1] = "2026-09-01T11:59:59Z"
    expired = _run(arguments)
    assert expired.returncode != 0
    assert "已过期" in expired.stderr

    reports = _candidate_reports()
    for document in reports.values():
        document["canaryScenarioFingerprint"] = DEVELOPMENT_SCOPE
    alias_source = tmp_path / "alias-reports"
    alias_output = tmp_path / "alias"
    _report_source(alias_source, reports, CANDIDATE_FILES)
    alias_arguments = _candidate_create_args(
        alias_source,
        alias_output,
        qualification,
        qualification_sha,
    )
    alias_arguments[alias_arguments.index("--canary-scenario-fingerprint") + 1] = DEVELOPMENT_SCOPE
    alias = _run(alias_arguments)
    assert alias.returncode != 0
    assert "不得混用" in alias.stderr


def test_verifier_rejects_wrong_trusted_commit_image_run_and_qualification(
    tmp_path: Path,
) -> None:
    candidate, candidate_sha, qualification, qualification_sha = _create_valid_candidate(tmp_path)
    base = _candidate_verify_args(
        candidate,
        candidate_sha,
        qualification,
        qualification_sha,
    )
    mutations = (
        ("--expected-target-release-commit", "f" * 40, "producer"),
        ("--expected-core-digest", "sha256:" + "f" * 64, "目标镜像"),
        ("--expected-run-id", "999", "producer"),
        ("--expected-run-attempt", "9", "producer"),
        (
            "--expected-migration-qualification-sha256",
            "f" * 64,
            "qualification",
        ),
        (
            "--expected-resource-performance-policy-sha256",
            "f" * 64,
            "policy",
        ),
        (
            "--expected-provider-usage-cost-policy-sha256",
            "f" * 64,
            "policy",
        ),
        (
            "--expected-resource-host-identity-sha256",
            "f" * 64,
            "subject",
        ),
        (
            "--expected-provider-identity-sha256",
            "f" * 64,
            "subject",
        ),
    )
    for option, value, error_fragment in mutations:
        arguments = list(base)
        arguments[arguments.index(option) + 1] = value
        result = _run(arguments)
        assert result.returncode != 0
        assert error_fragment in result.stderr


@pytest.mark.parametrize(
    ("binding", "report_type", "report_field", "create_option", "error_fragment"),
    [
        (
            "f" * 64,
            "resource-constrained",
            "performancePolicySha256",
            "--resource-performance-policy-sha256",
            "policy",
        ),
        (
            "e" * 64,
            "provider-canary",
            "usageCostPolicySha256",
            "--provider-usage-cost-policy-sha256",
            "policy",
        ),
        (
            "d" * 64,
            "resource-constrained",
            "hostIdentitySha256",
            "--resource-host-identity-sha256",
            "subject",
        ),
        (
            "c" * 64,
            "provider-canary",
            "providerIdentitySha256",
            "--provider-identity-sha256",
            "subject",
        ),
    ],
)
def test_recomputed_report_and_summary_cannot_replace_trusted_policy_or_subject(
    tmp_path: Path,
    binding: str,
    report_type: str,
    report_field: str,
    create_option: str,
    error_fragment: str,
) -> None:
    qualification, qualification_sha = _create_valid_qualification(tmp_path)
    reports = _candidate_reports()
    reports[report_type]["observations"][report_field] = binding
    source = tmp_path / "candidate-reports"
    candidate = tmp_path / "candidate"
    _report_source(source, reports, CANDIDATE_FILES)
    create_arguments = _candidate_create_args(
        source,
        candidate,
        qualification,
        qualification_sha,
    )
    create_arguments[create_arguments.index(create_option) + 1] = binding
    candidate_sha = _created_digest(_run(create_arguments))

    verified = _run(
        _candidate_verify_args(
            candidate,
            candidate_sha,
            qualification,
            qualification_sha,
        )
    )
    assert verified.returncode != 0
    assert error_fragment in verified.stderr


@pytest.mark.parametrize(
    ("report_field", "create_option", "replacement"),
    [
        ("maxTotalTokens", "--provider-max-total-tokens", 999),
        ("maxCostMicros", "--provider-max-cost-micros", 9999),
    ],
)
def test_recomputed_provider_caps_cannot_exceed_trusted_candidate_policy(
    tmp_path: Path,
    report_field: str,
    create_option: str,
    replacement: int,
) -> None:
    qualification, qualification_sha = _create_valid_qualification(tmp_path)
    reports = _candidate_reports()
    reports["provider-canary"]["observations"][report_field] = replacement
    source = tmp_path / "candidate-reports"
    candidate = tmp_path / "candidate"
    _report_source(source, reports, CANDIDATE_FILES)
    create_arguments = _candidate_create_args(
        source,
        candidate,
        qualification,
        qualification_sha,
    )
    create_arguments[create_arguments.index(create_option) + 1] = str(replacement)
    candidate_sha = _created_digest(_run(create_arguments))

    verified = _run(
        _candidate_verify_args(
            candidate,
            candidate_sha,
            qualification,
            qualification_sha,
        )
    )
    assert verified.returncode != 0
    assert "policy" in verified.stderr


def test_report_source_rejects_symlink_and_sensitive_value(tmp_path: Path) -> None:
    reports = _qualification_reports()
    source = tmp_path / "reports"
    output = tmp_path / "qualification"
    _report_source(source, reports, QUALIFICATION_FILES)
    backup = source / QUALIFICATION_FILES["migration-backup"]
    target = tmp_path / "backup-target.json"
    target.write_bytes(backup.read_bytes())
    target.chmod(0o600)
    backup.unlink()
    backup.symlink_to(target)
    symlink = _run(_qualification_create_args(source, output))
    assert symlink.returncode != 0
    assert "无法安全打开" in symlink.stderr

    reports = _qualification_reports()
    reports["migration-backup"]["format"] = "Bearer abcdefghijklmnop"
    sensitive_source = tmp_path / "sensitive-reports"
    sensitive_output = tmp_path / "sensitive"
    _report_source(sensitive_source, reports, QUALIFICATION_FILES)
    sensitive = _run(_qualification_create_args(sensitive_source, sensitive_output))
    assert sensitive.returncode != 0
    assert "疑似凭据" in sensitive.stderr


@pytest.mark.parametrize("attack", ["noncanonical", "duplicate-key"])
def test_report_source_rejects_noncanonical_or_duplicate_json(
    tmp_path: Path,
    attack: str,
) -> None:
    source = tmp_path / "reports"
    output = tmp_path / "qualification"
    reports = _qualification_reports()
    _report_source(source, reports, QUALIFICATION_FILES)
    backup = source / QUALIFICATION_FILES["migration-backup"]
    if attack == "noncanonical":
        backup.write_text(
            json.dumps(reports["migration-backup"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        backup.write_text('{"format":"one","format":"two"}\n', encoding="utf-8")
    backup.chmod(0o600)
    _refresh_checksums(source)
    result = _run(_qualification_create_args(source, output))
    assert result.returncode != 0
    if attack == "noncanonical":
        assert "不是 canonical JSON" in result.stderr
    else:
        assert "JSON key 重复" in result.stderr


@pytest.mark.parametrize("attack", ["permission", "checksum", "extra", "symlink"])
def test_bundle_verifier_rejects_permission_hash_whitelist_and_symlink_drift(
    tmp_path: Path,
    attack: str,
) -> None:
    candidate, candidate_sha, qualification, qualification_sha = _create_valid_candidate(tmp_path)
    if attack == "permission":
        (candidate / "candidate-evidence.json").chmod(0o644)
    elif attack == "checksum":
        report = candidate / "fault-injection-report.json"
        report.write_bytes(report.read_bytes() + b" ")
    elif attack == "extra":
        extra = candidate / "unexpected.json"
        extra.write_text("{}\n", encoding="utf-8")
        extra.chmod(0o600)
    else:
        report = candidate / "provider-canary-report.json"
        payload = report.read_bytes()
        report.unlink()
        target = tmp_path / "provider-target.json"
        target.write_bytes(payload)
        target.chmod(0o600)
        report.symlink_to(target)
    result = _run(
        _candidate_verify_args(
            candidate,
            candidate_sha,
            qualification,
            qualification_sha,
        )
    )
    assert result.returncode != 0


def test_qualification_verifier_rejects_wrong_migration_source_and_attempt(
    tmp_path: Path,
) -> None:
    qualification, qualification_sha = _create_valid_qualification(tmp_path)
    arguments = _qualification_verify_args(qualification, qualification_sha)
    wrong_source = list(arguments)
    wrong_source[wrong_source.index("--expected-migration-source-commit") + 1] = "f" * 40
    source_result = _run(wrong_source)
    assert source_result.returncode != 0
    assert "producer" in source_result.stderr or "migration" in source_result.stderr

    wrong_attempt = list(arguments)
    wrong_attempt[wrong_attempt.index("--expected-run-attempt") + 1] = "2"
    attempt_result = _run(wrong_attempt)
    assert attempt_result.returncode != 0
    assert "producer" in attempt_result.stderr


def test_candidate_report_checksum_covers_semantic_bytes(tmp_path: Path) -> None:
    candidate, candidate_sha, qualification, qualification_sha = _create_valid_candidate(tmp_path)
    report_path = candidate / "provider-canary-report.json"
    document = json.loads(report_path.read_text(encoding="utf-8"))
    document["observations"]["providerCalls"] = 2
    report_path.write_bytes(_canonical(document))
    report_path.chmod(0o600)

    _refresh_checksums(candidate)
    summary_path = candidate / "candidate-evidence.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["reports"]["providerCanarySha256"] = _sha(report_path.read_bytes())
    summary_path.write_bytes(_canonical(summary))
    summary_path.chmod(0o600)
    _refresh_checksums(candidate)
    drifted_sha = _sha(summary_path.read_bytes())

    result = _run(
        _candidate_verify_args(
            candidate,
            drifted_sha,
            qualification,
            qualification_sha,
        )
    )
    assert result.returncode != 0
    assert "providerCalls" in result.stderr


def test_test_fixture_does_not_mutate_shared_documents() -> None:
    reports = _candidate_reports()
    copy = deepcopy(reports)
    reports["fault-injection"]["observations"]["cancelProviderCalls"] = 1
    assert copy["fault-injection"]["observations"]["cancelProviderCalls"] == 0


def test_script_never_reads_credentials_from_environment(tmp_path: Path) -> None:
    source = tmp_path / "reports"
    output = tmp_path / "qualification"
    _report_source(source, _qualification_reports(), QUALIFICATION_FILES)
    environment = os.environ.copy()
    environment["OPENAI_API_KEY"] = "must-not-be-consumed"
    result = subprocess.run(  # noqa: S603 -- 参数完全由本测试构造
        [sys.executable, str(SCRIPT), *_qualification_create_args(source, output)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "must-not-be-consumed" not in result.stdout + result.stderr


def test_secure_read_rejects_existing_hardlink(tmp_path: Path) -> None:
    module = _evidence_module()
    source = tmp_path / "source.json"
    linked = tmp_path / "linked.json"
    source.write_text("{}\n", encoding="utf-8")
    source.chmod(0o600)
    os.link(source, linked)
    with pytest.raises(module.EvidenceV2Invalid, match="硬链接计数必须是 1"):
        module._secure_read(source, "test evidence")


def test_secure_read_rejects_oversized_file_before_loading(tmp_path: Path) -> None:
    module = _evidence_module()
    source = tmp_path / "oversized.json"
    with source.open("wb") as output:
        output.truncate(module.MAX_EVIDENCE_FILE_BYTES + 1)
    source.chmod(0o600)

    with pytest.raises(module.EvidenceV2Invalid, match="超过单文件大小上限"):
        module._secure_read(source, "test evidence")


@pytest.mark.parametrize("drift_field", ["st_mtime_ns", "st_ctime_ns", "st_nlink"])
def test_secure_read_detects_metadata_drift_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_field: str,
) -> None:
    module = _evidence_module()
    source = tmp_path / "source.json"
    source.write_text("{}\n", encoding="utf-8")
    source.chmod(0o600)
    real_fstat = module.os.fstat
    calls = 0

    def drifting_fstat(descriptor: int) -> Any:
        nonlocal calls
        metadata = real_fstat(descriptor)
        calls += 1
        if calls == 1:
            return metadata
        values = {
            "st_mode": metadata.st_mode,
            "st_dev": metadata.st_dev,
            "st_ino": metadata.st_ino,
            "st_size": metadata.st_size,
            "st_mtime_ns": metadata.st_mtime_ns,
            "st_ctime_ns": metadata.st_ctime_ns,
            "st_nlink": metadata.st_nlink,
        }
        values[drift_field] += 1
        return SimpleNamespace(**values)

    monkeypatch.setattr(module.os, "fstat", drifting_fstat)
    with pytest.raises(module.EvidenceV2Invalid, match="读取期间发生漂移"):
        module._secure_read(source, "test evidence")
