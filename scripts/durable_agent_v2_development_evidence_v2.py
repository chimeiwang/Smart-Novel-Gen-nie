#!/usr/bin/env python3
"""构建并复验 Durable Agent V2 可信开发证据 v2。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

from durable_agent_v2_development_evidence import (
    EvidenceInvalid as LegacyEvidenceInvalid,
)
from durable_agent_v2_development_evidence import _canonical_bytes as canonical_bytes
from durable_agent_v2_development_evidence import _unique_object as unique_object
from durable_agent_v2_release_receipt import ReceiptInvalid, fsync_path, publish_no_replace

QUALIFICATION_FORMAT = "inkforge-durable-agent-v2-migration-qualification/2"
CANDIDATE_FORMAT = "inkforge-durable-agent-v2-candidate-evidence/2"
PRODUCER_WORKFLOW = ".github/workflows/durable-agent-v2-development-evidence.yml"
QUALIFICATION_TTL = timedelta(days=30)
CANDIDATE_TTL = timedelta(hours=24)
FUTURE_SKEW = timedelta(minutes=5)
MAX_EVIDENCE_FILE_BYTES = 1_048_576

HEX_DIGITS = frozenset("0123456789abcdef")
REPOSITORY = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})\Z"
)
OPERATION = re.compile(r"[a-z][a-z0-9_]{0,63}\.[a-z][a-z0-9_]{0,63}\Z")

QUALIFICATION_REPORT_FILES = {
    "migration-backup": "migration-backup-report.json",
    "live-contract": "live-contract-report.json",
    "idempotent-forward": "idempotent-forward-report.json",
    "rollback-rehearsal": "rollback-rehearsal-report.json",
}
CANDIDATE_REPORT_FILES = {
    "fault-injection": "fault-injection-report.json",
    "resource-constrained": "resource-constrained-report.json",
    "provider-canary": "provider-canary-report.json",
}
REPORT_FORMATS = {
    report_type: f"inkforge-durable-agent-v2-{report_type}-report/2"
    for report_type in (*QUALIFICATION_REPORT_FILES, *CANDIDATE_REPORT_FILES)
}

PRODUCER_KEYS = {"headSha", "repository", "runAttempt", "runId", "workflowPath"}
IMAGE_KEYS = {"agent", "core", "web"}
QUALIFICATION_KEYS = {
    "database",
    "developmentScopeSha256",
    "expiresAt",
    "format",
    "issuedAt",
    "migration",
    "producer",
    "reports",
}
MIGRATION_KEYS = {
    "bundleFingerprint",
    "forwardSqlSha256",
    "migrationSourceCommit",
    "postContractFingerprint",
    "preContractFingerprint",
    "rollbackSqlSha256",
}
QUALIFICATION_REPORT_HASH_KEYS = {
    "backupSha256",
    "idempotentForwardSha256",
    "liveContractSha256",
    "rollbackRehearsalSha256",
}
CANDIDATE_KEYS = {
    "canaryScenarioFingerprint",
    "developmentScopeSha256",
    "executionManifestFingerprint",
    "expiresAt",
    "format",
    "images",
    "issuedAt",
    "migrationQualificationSha256",
    "policies",
    "producer",
    "reports",
    "subjects",
    "targetReleaseCommit",
}
POLICY_KEYS = {
    "providerMaxCompletionTokens",
    "providerMaxCostMicros",
    "providerMaxPromptTokens",
    "providerMaxReasoningTokens",
    "providerMaxTotalTokens",
    "providerUsageCostPolicySha256",
    "providerUsageCostPolicyVersion",
    "resourcePerformancePolicySha256",
    "resourcePerformancePolicyVersion",
}
SUBJECT_KEYS = {
    "providerIdentitySha256",
    "resourceHostIdentitySha256",
}
CANDIDATE_REPORT_HASH_KEYS = {
    "faultInjectionSha256",
    "providerCanarySha256",
    "resourceConstrainedSha256",
}
MIGRATION_REPORT_KEYS = {
    "database",
    "developmentScopeSha256",
    "expiresAt",
    "format",
    "issuedAt",
    "migrationBundleFingerprint",
    "observations",
    "producer",
    "reportType",
    "sensitiveContentAbsent",
}
CANDIDATE_REPORT_KEYS = {
    "canaryScenarioFingerprint",
    "developmentScopeSha256",
    "executionManifestFingerprint",
    "expiresAt",
    "format",
    "images",
    "issuedAt",
    "observations",
    "producer",
    "reportType",
    "sensitiveContentAbsent",
    "targetReleaseCommit",
}

BACKUP_OBSERVATION_KEYS = {
    "executionAofStatus",
    "executionRedisRdbReadable",
    "executionRedisRdbSha256",
    "postgresCustomDumpReadable",
    "postgresCustomDumpSha256",
    "postgresRestoreRequiresExecutionQuarantine",
    "status",
}
LIVE_CONTRACT_OBSERVATION_KEYS = {
    "contractEvidenceSha256",
    "contractFingerprint",
    "guardFingerprint",
    "schemaState",
    "status",
    "structureDiffCount",
}
IDEMPOTENT_FORWARD_OBSERVATION_KEYS = {
    "backupReportSha256",
    "firstForwardExitCode",
    "firstPostContractFingerprint",
    "partialStateObserved",
    "secondForwardExitCode",
    "secondPostContractFingerprint",
    "status",
    "v2FactCount",
}
ROLLBACK_OBSERVATION_KEYS = {
    "finalContractFingerprint",
    "postRollbackContractFingerprint",
    "preRollbackState",
    "reforwardExitCode",
    "residueCount",
    "rollbackExitCode",
    "status",
    "v2FactCountBeforeRollback",
}
FAULT_OBSERVATION_KEYS = {
    "agentRestartJournalReplayPassed",
    "allResourcesRemoved",
    "aofAgentFreshHealthcheckPassed",
    "callbackReceiptLossPassed",
    "callbackReceiptIdentityMatched",
    "callbackReceiptIdentitySha256",
    "cancelBeforeAgentSubmitPassed",
    "cancelProviderCalls",
    "cleanupPassed",
    "coreRestartCallbackReplayPassed",
    "duplicateAnswerMessages",
    "duplicateBillingReservations",
    "duplicateTerminalEvents",
    "duplicateTokenUsage",
    "executionRedisAofRestartPassed",
    "happyIdempotencyPassed",
    "sseCursorReconnectPassed",
    "status",
}
RESOURCE_OBSERVATION_KEYS = {
    "cgroupMode",
    "cpuCount",
    "cpuThrottledMicros",
    "hostIdentitySha256",
    "latencySloPassed",
    "maxProviderConcurrency",
    "measuredLatencySummarySha256",
    "memoryMiB",
    "nonTerminalRuns",
    "observationSeconds",
    "oomKills",
    "peakRssMiB",
    "pendingExecutions",
    "performancePolicySha256",
    "performancePolicyVersion",
    "quarantineEvents",
    "redisEvictions",
    "sampleCount",
    "sloHardFailures",
    "status",
    "swapMiB",
    "unexpectedRestarts",
}
PROVIDER_OBSERVATION_KEYS = {
    "answerMessages",
    "completedResultMessageBinding",
    "completedRuns",
    "completionTokens",
    "costMicros",
    "credentialsStored",
    "duplicateBillingReservations",
    "duplicateTokenUsage",
    "idempotentReplayPhysicalCallsUnchanged",
    "maxCompletionTokens",
    "maxCostMicros",
    "maxPromptTokens",
    "maxReasoningTokens",
    "maxTotalTokens",
    "mode",
    "operation",
    "promptTokens",
    "providerAttempts",
    "providerCalls",
    "providerIdentitySha256",
    "reasoningTokens",
    "reconciliationRequiredCount",
    "requestPayloadStored",
    "reservationChargedMicros",
    "reservationCount",
    "reservationRemainingMicros",
    "reservationStatus",
    "reservationUsageBinding",
    "responsePayloadStored",
    "status",
    "terminalState",
    "tokenUsageBindingUnique",
    "tokenUsageCount",
    "totalTokens",
    "usageComplete",
    "usageCostPolicySha256",
    "usageCostPolicyVersion",
    "usageCostSummarySha256",
}

SENSITIVE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)-----"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?key|secret|token|cookie)\s*[:=]"),
    re.compile(r"(?i)\bpostgres(?:ql)?://[^\s/:@]+:[^\s@]+@"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)


class EvidenceV2Invalid(ValueError):
    """开发证据 v2 不满足严格协议。"""


def _fail(message: str) -> NoReturn:
    raise EvidenceV2Invalid(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(f"{label} 字段集合无效")
    return value


def _hex(value: Any, length: int, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in HEX_DIGITS for character in value)
    ):
        _fail(f"{label} 格式无效")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        _fail(f"{label} 必须是不可变 sha256 digest")
    _hex(value.removeprefix("sha256:"), 64, label)
    return value


def _positive_decimal(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or not value.isdecimal()
        or value.startswith("0")
    ):
        _fail(f"{label} 必须是无前导零的正十进制")
    return value


def _integer(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(f"{label} 数值无效")
    return value


def _require_value(value: Any, expected: Any, label: str) -> None:
    if value != expected or type(value) is not type(expected):
        _fail(f"{label} 必须为 {expected!r}")


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, str):
        if any(pattern.search(value) for pattern in SENSITIVE_PATTERNS):
            _fail("证据包含疑似凭据或敏感正文")
        return
    if isinstance(value, list):
        for item in value:
            _reject_sensitive(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_sensitive(key)
            _reject_sensitive(item)


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        _fail(f"{label} 必须是 UTC 时间")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise EvidenceV2Invalid(f"{label} 格式无效") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail(f"{label} 不是 canonical UTC 时间")
    return parsed


def _validate_window(
    issued_value: Any,
    expires_value: Any,
    *,
    now: datetime,
    maximum_ttl: timedelta,
    label: str,
) -> tuple[datetime, datetime]:
    issued = _parse_time(issued_value, f"{label} issuedAt")
    expires = _parse_time(expires_value, f"{label} expiresAt")
    if issued >= expires:
        _fail(f"{label} 时间窗口无效")
    if expires - issued > maximum_ttl:
        _fail(f"{label} TTL 超过上限")
    if issued > now + FUTURE_SKEW:
        _fail(f"{label} 签发时间位于未来")
    if now >= expires:
        _fail(f"{label} 已过期")
    return issued, expires


def _parse_trusted_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC).replace(microsecond=0)
    return _parse_time(value, "可信当前时间")


def _validate_producer(
    value: Any,
    *,
    expected: dict[str, str] | None = None,
) -> dict[str, Any]:
    producer = _exact(value, PRODUCER_KEYS, "producer")
    repository = producer["repository"]
    if not isinstance(repository, str) or REPOSITORY.fullmatch(repository) is None:
        _fail("producer repository 格式无效")
    if producer["workflowPath"] != PRODUCER_WORKFLOW:
        _fail("producer workflow path 无效")
    _hex(producer["headSha"], 40, "producer head SHA")
    _positive_decimal(producer["runId"], "producer run ID")
    _positive_decimal(producer["runAttempt"], "producer run attempt")
    if expected is not None and producer != expected:
        _fail("producer 与可信 run 来源不一致")
    return producer


def _validate_images(value: Any, expected: dict[str, str] | None = None) -> dict[str, str]:
    images = _exact(value, IMAGE_KEYS, "images")
    normalized = {
        component: _digest(images[component], f"{component} image")
        for component in sorted(IMAGE_KEYS)
    }
    if len(set(normalized.values())) != 3:
        _fail("三张目标镜像 digest 必须互不相同")
    if expected is not None and normalized != expected:
        _fail("目标镜像 digest 与可信来源不一致")
    return normalized


def _validate_policies(
    value: Any,
    expected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policies = _exact(value, POLICY_KEYS, "candidate policies")
    _require_value(
        policies["resourcePerformancePolicyVersion"],
        "durable-agent-v2-resource-slo/1",
        "resource performance policy version",
    )
    _require_value(
        policies["providerUsageCostPolicyVersion"],
        "durable-agent-v2-provider-canary-budget/1",
        "provider usage/cost policy version",
    )
    _hex(
        policies["resourcePerformancePolicySha256"],
        64,
        "resource performance policy SHA",
    )
    _hex(
        policies["providerUsageCostPolicySha256"],
        64,
        "provider usage/cost policy SHA",
    )
    for key, minimum, maximum in (
        ("providerMaxPromptTokens", 1, 10**9),
        ("providerMaxCompletionTokens", 1, 10**9),
        ("providerMaxReasoningTokens", 0, 10**9),
        ("providerMaxTotalTokens", 1, 2 * 10**9),
        ("providerMaxCostMicros", 0, 10**15),
    ):
        _integer(policies[key], key, minimum=minimum, maximum=maximum)
    if expected is not None and policies != expected:
        _fail("candidate policy 与可信输入不一致")
    return policies


def _validate_subjects(
    value: Any,
    expected: dict[str, str] | None = None,
) -> dict[str, str]:
    subjects = _exact(value, SUBJECT_KEYS, "candidate subjects")
    _hex(subjects["resourceHostIdentitySha256"], 64, "resource host identity SHA")
    _hex(subjects["providerIdentitySha256"], 64, "provider identity SHA")
    if expected is not None and subjects != expected:
        _fail("candidate subject 与可信输入不一致")
    return subjects


def _migration_fingerprint(migration: dict[str, Any]) -> str:
    payload = {
        key: migration[key]
        for key in (
            "forwardSqlSha256",
            "migrationSourceCommit",
            "postContractFingerprint",
            "preContractFingerprint",
            "rollbackSqlSha256",
        )
    }
    return _sha256(canonical_bytes(payload)[:-1])


def development_scope_fingerprint(
    *,
    database_identity_sha256: str,
    ordinary_redis_identity_sha256: str,
    execution_redis_identity_sha256: str,
    topology_sha256: str,
) -> str:
    document = {
        "databaseIdentitySha256": _hex(database_identity_sha256, 64, "database identity SHA"),
        "environment": "development",
        "executionRedisIdentitySha256": _hex(
            execution_redis_identity_sha256, 64, "execution Redis identity SHA"
        ),
        "ordinaryRedisIdentitySha256": _hex(
            ordinary_redis_identity_sha256, 64, "ordinary Redis identity SHA"
        ),
        "topologySha256": _hex(topology_sha256, 64, "topology SHA"),
    }
    return _sha256(canonical_bytes(document)[:-1])


def canary_scenario_fingerprint(
    *,
    actor_scope_sha256: str,
    assertions_sha256: str,
    fixture_sha256: str,
    operation: str,
    scenario_version: str,
) -> str:
    if OPERATION.fullmatch(operation) is None:
        _fail("canary operation 格式无效")
    if scenario_version != "durable-agent-v2-real-provider-canary/1":
        _fail("canary scenario version 无效")
    document = {
        "actorScopeSha256": _hex(actor_scope_sha256, 64, "actor scope SHA"),
        "assertionsSha256": _hex(assertions_sha256, 64, "assertions SHA"),
        "fixtureSha256": _hex(fixture_sha256, 64, "fixture SHA"),
        "operation": operation,
        "scenarioVersion": scenario_version,
    }
    return _sha256(canonical_bytes(document)[:-1])


def _secure_read(path: Path, label: str) -> bytes:
    flags = os.O_RDONLY
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        _fail("当前平台缺少 O_NOFOLLOW，拒绝读取证据")
    flags |= no_follow
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise EvidenceV2Invalid(f"{label} 无法安全打开") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            _fail(f"{label} 必须是普通文件")
        if stat.S_IMODE(before.st_mode) != 0o600:
            _fail(f"{label} 权限必须是 0600")
        if before.st_nlink != 1:
            _fail(f"{label} 硬链接计数必须是 1")
        if before.st_size > MAX_EVIDENCE_FILE_BYTES:
            _fail(f"{label} 超过单文件大小上限")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mode,
            before.st_mtime_ns,
            before.st_ctime_ns,
            before.st_nlink,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mode,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        ):
            _fail(f"{label} 读取期间发生漂移")
        payload = b"".join(chunks)
        if len(payload) != after.st_size:
            _fail(f"{label} 读取长度漂移")
        return payload
    finally:
        os.close(descriptor)


def _validate_directory(directory: Path, expected_names: set[str], label: str) -> None:
    if not directory.is_absolute():
        _fail(f"{label} 必须是绝对路径")
    try:
        metadata = directory.lstat()
    except OSError as error:
        raise EvidenceV2Invalid(f"{label} 不存在") from error
    if not stat.S_ISDIR(metadata.st_mode) or directory.is_symlink():
        _fail(f"{label} 必须是普通目录")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        _fail(f"{label} 权限必须是 0700")
    try:
        names = {entry.name for entry in directory.iterdir()}
    except OSError as error:
        raise EvidenceV2Invalid(f"{label} 无法读取") from error
    if names != expected_names:
        _fail(f"{label} 文件白名单不匹配")


def _load_json_payload(payload: bytes, label: str) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_float=lambda _: _fail(f"{label} 禁止浮点数"),
            parse_constant=lambda _: _fail(f"{label} 禁止非有限数字"),
        )
    except EvidenceV2Invalid:
        raise
    except LegacyEvidenceInvalid as error:
        raise EvidenceV2Invalid(f"{label} JSON key 重复") from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceV2Invalid(f"{label} 不是有效 UTF-8 JSON") from error
    if not isinstance(value, dict):
        _fail(f"{label} 顶层必须是对象")
    _reject_sensitive(value)
    try:
        canonical = canonical_bytes(value)
    except LegacyEvidenceInvalid as error:
        raise EvidenceV2Invalid(f"{label} 不能 canonicalize") from error
    if payload != canonical:
        _fail(f"{label} 不是 canonical JSON")
    return value


def _checksum_text(payloads: dict[str, bytes]) -> bytes:
    return "".join(f"{_sha256(payloads[name])}  {name}\n" for name in sorted(payloads)).encode(
        "ascii"
    )


def _load_report_source(
    directory: Path,
    report_files: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], dict[str, bytes], dict[str, str]]:
    names = set(report_files.values())
    _validate_directory(directory, names | {"SHA256SUMS"}, "report source")
    payloads = {name: _secure_read(directory / name, f"report {name}") for name in names}
    checksums = _secure_read(directory / "SHA256SUMS", "report SHA256SUMS")
    if checksums != _checksum_text(payloads):
        _fail("report source SHA256SUMS 不一致")
    documents = {
        report_type: _load_json_payload(
            payloads[name],
            f"{report_type} report",
        )
        for report_type, name in report_files.items()
    }
    digests = {name: _sha256(payload) for name, payload in payloads.items()}
    return documents, payloads, digests


def _load_bundle(
    directory: Path,
    summary_name: str,
    report_files: dict[str, str],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, bytes], str]:
    json_names = {summary_name, *report_files.values()}
    _validate_directory(directory, json_names | {"SHA256SUMS"}, "evidence bundle")
    payloads = {name: _secure_read(directory / name, f"bundle file {name}") for name in json_names}
    checksum = _secure_read(directory / "SHA256SUMS", "bundle SHA256SUMS")
    if checksum != _checksum_text(payloads):
        _fail("evidence bundle SHA256SUMS 不一致")
    summary = _load_json_payload(payloads[summary_name], summary_name)
    reports = {
        report_type: _load_json_payload(payloads[name], name)
        for report_type, name in report_files.items()
    }
    return summary, reports, payloads, _sha256(payloads[summary_name])


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                _fail("证据文件写入未前进")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _create_bundle(
    output: Path,
    *,
    summary_name: str,
    summary: dict[str, Any],
    report_payloads: dict[str, bytes],
    report_files: dict[str, str],
) -> str:
    if not output.is_absolute() or output.name in {"", ".", ".."}:
        _fail("输出目录必须是尚不存在的绝对路径")
    if os.path.lexists(output):
        _fail("输出目录已经存在，拒绝覆盖")
    try:
        if output.parent.is_symlink():
            _fail("输出目录父目录不得是符号链接")
        parent = output.parent.resolve(strict=True)
        parent_metadata = parent.lstat()
    except OSError as error:
        raise EvidenceV2Invalid("输出目录父目录无效") from error
    if not stat.S_ISDIR(parent_metadata.st_mode) or parent.is_symlink():
        _fail("输出目录父目录必须是普通目录")
    output = parent / output.name
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.partial-", dir=parent))
    os.chmod(temporary, 0o700)
    try:
        summary_payload = canonical_bytes(summary)
        payloads = {summary_name: summary_payload, **report_payloads}
        for name, payload in payloads.items():
            _write_exclusive(temporary / name, payload)
        _write_exclusive(temporary / "SHA256SUMS", _checksum_text(payloads))
        fsync_path(temporary)
        try:
            publish_no_replace(temporary, output)
        except ReceiptInvalid as error:
            raise EvidenceV2Invalid("证据目录原子 no-replace 发布失败") from error
        fsync_path(parent)
        published_summary, _, published_payloads, digest = _load_bundle(
            output,
            summary_name,
            report_files,
        )
        if published_summary != summary or any(
            published_payloads[name] != payload for name, payload in report_payloads.items()
        ):
            _fail("证据目录发布后内容漂移")
        return digest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _validate_migration_observations(
    report_type: str,
    observations_value: Any,
    *,
    pre_contract: str,
    post_contract: str,
    backup_report_sha: str | None,
) -> None:
    if report_type == "migration-backup":
        observations = _exact(
            observations_value,
            BACKUP_OBSERVATION_KEYS,
            "migration-backup observations",
        )
        _require_value(observations["status"], "passed", "backup status")
        _require_value(
            observations["postgresCustomDumpReadable"],
            True,
            "PostgreSQL custom dump readable",
        )
        _require_value(
            observations["executionRedisRdbReadable"],
            True,
            "execution Redis RDB readable",
        )
        _require_value(observations["executionAofStatus"], "ok", "execution AOF")
        _require_value(
            observations["postgresRestoreRequiresExecutionQuarantine"],
            True,
            "PostgreSQL restore quarantine",
        )
        _hex(observations["postgresCustomDumpSha256"], 64, "PostgreSQL dump SHA")
        _hex(observations["executionRedisRdbSha256"], 64, "execution RDB SHA")
        return
    if report_type == "live-contract":
        observations = _exact(
            observations_value,
            LIVE_CONTRACT_OBSERVATION_KEYS,
            "live-contract observations",
        )
        _require_value(observations["status"], "passed", "live contract status")
        _require_value(
            observations["schemaState"],
            "migrated-empty-v2",
            "live contract schema state",
        )
        _require_value(
            observations["contractFingerprint"],
            post_contract,
            "live contract fingerprint",
        )
        _require_value(
            observations["guardFingerprint"],
            post_contract,
            "live guard fingerprint",
        )
        _integer(
            observations["structureDiffCount"],
            "live contract diff count",
            minimum=0,
            maximum=0,
        )
        _hex(observations["contractEvidenceSha256"], 64, "contract evidence SHA")
        return
    if report_type == "idempotent-forward":
        observations = _exact(
            observations_value,
            IDEMPOTENT_FORWARD_OBSERVATION_KEYS,
            "idempotent-forward observations",
        )
        _require_value(observations["status"], "passed", "forward status")
        _integer(
            observations["firstForwardExitCode"],
            "first forward exit code",
            minimum=0,
            maximum=0,
        )
        _integer(
            observations["secondForwardExitCode"],
            "second forward exit code",
            minimum=0,
            maximum=0,
        )
        _require_value(
            observations["firstPostContractFingerprint"],
            post_contract,
            "first forward contract",
        )
        _require_value(
            observations["secondPostContractFingerprint"],
            post_contract,
            "second forward contract",
        )
        _require_value(
            observations["partialStateObserved"],
            False,
            "partial migration state",
        )
        _integer(
            observations["v2FactCount"],
            "forward V2 fact count",
            minimum=0,
            maximum=0,
        )
        if backup_report_sha is None:
            _fail("idempotent-forward 缺 backup report 绑定")
        _require_value(
            observations["backupReportSha256"],
            backup_report_sha,
            "forward backup report SHA",
        )
        return
    if report_type == "rollback-rehearsal":
        observations = _exact(
            observations_value,
            ROLLBACK_OBSERVATION_KEYS,
            "rollback-rehearsal observations",
        )
        _require_value(observations["status"], "passed", "rollback status")
        _require_value(
            observations["preRollbackState"],
            "migrated-empty-v2",
            "pre rollback state",
        )
        for key, label in (
            ("rollbackExitCode", "rollback exit code"),
            ("reforwardExitCode", "reforward exit code"),
            ("v2FactCountBeforeRollback", "rollback V2 fact count"),
            ("residueCount", "rollback residue count"),
        ):
            _integer(observations[key], label, minimum=0, maximum=0)
        _require_value(
            observations["postRollbackContractFingerprint"],
            pre_contract,
            "post rollback contract",
        )
        _require_value(
            observations["finalContractFingerprint"],
            post_contract,
            "final reforward contract",
        )
        return
    _fail("未知 migration report type")


def _validate_candidate_observations(report_type: str, value: Any) -> None:
    if report_type == "fault-injection":
        observations = _exact(value, FAULT_OBSERVATION_KEYS, "fault observations")
        _require_value(observations["status"], "passed", "fault status")
        for key in (
            "agentRestartJournalReplayPassed",
            "allResourcesRemoved",
            "aofAgentFreshHealthcheckPassed",
            "callbackReceiptLossPassed",
            "callbackReceiptIdentityMatched",
            "cancelBeforeAgentSubmitPassed",
            "cleanupPassed",
            "coreRestartCallbackReplayPassed",
            "executionRedisAofRestartPassed",
            "happyIdempotencyPassed",
            "sseCursorReconnectPassed",
        ):
            _require_value(observations[key], True, key)
        _hex(
            observations["callbackReceiptIdentitySha256"],
            64,
            "callback receipt identity SHA",
        )
        for key in (
            "cancelProviderCalls",
            "duplicateAnswerMessages",
            "duplicateBillingReservations",
            "duplicateTerminalEvents",
            "duplicateTokenUsage",
        ):
            _integer(observations[key], key, minimum=0, maximum=0)
        return
    if report_type == "resource-constrained":
        observations = _exact(
            value,
            RESOURCE_OBSERVATION_KEYS,
            "resource-constrained observations",
        )
        _require_value(observations["status"], "passed", "resource status")
        _hex(observations["hostIdentitySha256"], 64, "resource host identity SHA")
        if observations["cgroupMode"] not in {"v1", "v2"}:
            _fail("resource cgroup mode 无效")
        _integer(observations["cpuCount"], "host CPU count", minimum=2, maximum=2)
        _integer(
            observations["memoryMiB"],
            "host memory MiB",
            minimum=2048,
            maximum=2048,
        )
        _integer(
            observations["observationSeconds"],
            "resource observation seconds",
            minimum=1800,
            maximum=604800,
        )
        _integer(
            observations["sampleCount"],
            "resource sample count",
            minimum=30,
            maximum=1_000_000,
        )
        _integer(
            observations["swapMiB"],
            "host swap MiB",
            minimum=0,
            maximum=0,
        )
        _integer(
            observations["cpuThrottledMicros"],
            "CPU throttled micros",
            minimum=0,
            maximum=10**15,
        )
        _integer(
            observations["peakRssMiB"],
            "peak RSS MiB",
            minimum=1,
            maximum=2048,
        )
        _integer(
            observations["maxProviderConcurrency"],
            "max provider concurrency",
            minimum=1,
            maximum=3,
        )
        for key in (
            "nonTerminalRuns",
            "oomKills",
            "pendingExecutions",
            "quarantineEvents",
            "redisEvictions",
            "unexpectedRestarts",
            "sloHardFailures",
        ):
            _integer(observations[key], key, minimum=0, maximum=0)
        _require_value(
            observations["performancePolicyVersion"],
            "durable-agent-v2-resource-slo/1",
            "resource performance policy version",
        )
        _hex(
            observations["performancePolicySha256"],
            64,
            "resource performance policy SHA",
        )
        _hex(
            observations["measuredLatencySummarySha256"],
            64,
            "measured latency summary SHA",
        )
        _require_value(
            observations["latencySloPassed"],
            True,
            "resource latency SLO",
        )
        return
    if report_type == "provider-canary":
        observations = _exact(
            value,
            PROVIDER_OBSERVATION_KEYS,
            "provider-canary observations",
        )
        _require_value(observations["status"], "passed", "provider status")
        _require_value(observations["mode"], "real", "provider mode")
        _require_value(
            observations["operation"],
            "long_serial.answer_question",
            "provider operation",
        )
        _require_value(observations["terminalState"], "completed", "provider terminal state")
        for key in (
            "providerAttempts",
            "providerCalls",
            "completedRuns",
            "answerMessages",
            "reservationCount",
            "tokenUsageCount",
        ):
            _integer(observations[key], key, minimum=1, maximum=1)
        for key in (
            "duplicateTokenUsage",
            "duplicateBillingReservations",
            "reconciliationRequiredCount",
            "reservationRemainingMicros",
        ):
            _integer(observations[key], key, minimum=0, maximum=0)
        _require_value(observations["usageComplete"], True, "provider usage complete")
        for key in (
            "completedResultMessageBinding",
            "idempotentReplayPhysicalCallsUnchanged",
            "reservationUsageBinding",
            "tokenUsageBindingUnique",
        ):
            _require_value(observations[key], True, key)
        _require_value(
            observations["reservationStatus"],
            "settled",
            "reservation status",
        )
        measured_limits = (
            ("promptTokens", "maxPromptTokens", 1, 10**9),
            ("completionTokens", "maxCompletionTokens", 1, 10**9),
            ("reasoningTokens", "maxReasoningTokens", 0, 10**9),
            ("totalTokens", "maxTotalTokens", 1, 2 * 10**9),
            ("costMicros", "maxCostMicros", 0, 10**15),
        )
        for measured_key, limit_key, minimum, maximum in measured_limits:
            measured = _integer(
                observations[measured_key],
                measured_key,
                minimum=minimum,
                maximum=maximum,
            )
            limit = _integer(
                observations[limit_key],
                limit_key,
                minimum=minimum,
                maximum=maximum,
            )
            if measured > limit:
                _fail(f"{measured_key} 超过版本化 usage/cost 上限")
        charged = _integer(
            observations["reservationChargedMicros"],
            "reservation charged micros",
            minimum=0,
            maximum=10**15,
        )
        if charged != observations["costMicros"]:
            _fail("reservation charged micros 与 provider cost 不一致")
        _require_value(
            observations["usageCostPolicyVersion"],
            "durable-agent-v2-provider-canary-budget/1",
            "provider usage/cost policy version",
        )
        _hex(
            observations["usageCostPolicySha256"],
            64,
            "provider usage/cost policy SHA",
        )
        _hex(
            observations["usageCostSummarySha256"],
            64,
            "provider usage/cost summary SHA",
        )
        for key in (
            "credentialsStored",
            "requestPayloadStored",
            "responsePayloadStored",
        ):
            _require_value(observations[key], False, key)
        _hex(observations["providerIdentitySha256"], 64, "provider identity SHA")
        return
    _fail("未知 candidate report type")


def _validate_migration_report(
    document: dict[str, Any],
    *,
    report_type: str,
    binding: dict[str, Any],
    pre_contract: str,
    post_contract: str,
    backup_report_sha: str | None,
) -> None:
    _exact(document, MIGRATION_REPORT_KEYS, f"{report_type} report")
    if document["format"] != REPORT_FORMATS[report_type]:
        _fail(f"{report_type} report format 无效")
    if document["reportType"] != report_type:
        _fail(f"{report_type} reportType 无效")
    _require_value(
        document["sensitiveContentAbsent"],
        True,
        f"{report_type} sensitiveContentAbsent",
    )
    for key in (
        "database",
        "developmentScopeSha256",
        "issuedAt",
        "expiresAt",
        "migrationBundleFingerprint",
        "producer",
    ):
        if document[key] != binding[key]:
            _fail(f"{report_type} report {key} 绑定漂移")
    _validate_producer(document["producer"], expected=binding["producer"])
    _validate_migration_observations(
        report_type,
        document["observations"],
        pre_contract=pre_contract,
        post_contract=post_contract,
        backup_report_sha=backup_report_sha,
    )


def _validate_candidate_report(
    document: dict[str, Any],
    *,
    report_type: str,
    binding: dict[str, Any],
) -> None:
    _exact(document, CANDIDATE_REPORT_KEYS, f"{report_type} report")
    if document["format"] != REPORT_FORMATS[report_type]:
        _fail(f"{report_type} report format 无效")
    if document["reportType"] != report_type:
        _fail(f"{report_type} reportType 无效")
    _require_value(
        document["sensitiveContentAbsent"],
        True,
        f"{report_type} sensitiveContentAbsent",
    )
    for key in (
        "canaryScenarioFingerprint",
        "developmentScopeSha256",
        "executionManifestFingerprint",
        "expiresAt",
        "images",
        "issuedAt",
        "producer",
        "targetReleaseCommit",
    ):
        if document[key] != binding[key]:
            _fail(f"{report_type} report {key} 绑定漂移")
    _validate_producer(document["producer"], expected=binding["producer"])
    _validate_images(document["images"], expected=binding["images"])
    _validate_candidate_observations(report_type, document["observations"])
    observations = document["observations"]
    policies = binding["policies"]
    subjects = binding["subjects"]
    if report_type == "resource-constrained" and (
        observations["performancePolicyVersion"] != policies["resourcePerformancePolicyVersion"]
        or observations["performancePolicySha256"] != policies["resourcePerformancePolicySha256"]
    ):
        _fail("resource report policy 与 candidate 绑定不一致")
    if report_type == "provider-canary" and (
        observations["usageCostPolicyVersion"] != policies["providerUsageCostPolicyVersion"]
        or observations["usageCostPolicySha256"] != policies["providerUsageCostPolicySha256"]
    ):
        _fail("provider report policy 与 candidate 绑定不一致")
    if report_type == "provider-canary":
        cap_bindings = {
            "maxPromptTokens": "providerMaxPromptTokens",
            "maxCompletionTokens": "providerMaxCompletionTokens",
            "maxReasoningTokens": "providerMaxReasoningTokens",
            "maxTotalTokens": "providerMaxTotalTokens",
            "maxCostMicros": "providerMaxCostMicros",
        }
        if any(
            observations[report_key] != policies[policy_key]
            for report_key, policy_key in cap_bindings.items()
        ):
            _fail("provider report usage/cost 上限与 candidate policy 不一致")
    if report_type == "resource-constrained" and (
        observations["hostIdentitySha256"] != subjects["resourceHostIdentitySha256"]
    ):
        _fail("resource report host identity 与 candidate subject 不一致")
    if report_type == "provider-canary" and (
        observations["providerIdentitySha256"] != subjects["providerIdentitySha256"]
    ):
        _fail("provider report identity 与 candidate subject 不一致")


def _validate_qualification_summary(
    document: dict[str, Any],
    *,
    now: datetime,
    expected_producer: dict[str, str] | None = None,
    expected_development_scope: str | None = None,
    expected_migration: dict[str, str] | None = None,
) -> tuple[datetime, datetime]:
    _exact(document, QUALIFICATION_KEYS, "migration qualification")
    if document["format"] != QUALIFICATION_FORMAT:
        _fail("migration qualification format 无效")
    if document["database"] != "novelwriterdev":
        _fail("migration qualification 数据库必须是 novelwriterdev")
    scope = _hex(document["developmentScopeSha256"], 64, "development scope SHA")
    if expected_development_scope is not None and scope != _hex(
        expected_development_scope, 64, "预期 development scope SHA"
    ):
        _fail("migration qualification development scope 不一致")
    producer = _validate_producer(document["producer"], expected=expected_producer)
    migration = _exact(document["migration"], MIGRATION_KEYS, "migration bundle")
    for key in (
        "forwardSqlSha256",
        "postContractFingerprint",
        "preContractFingerprint",
        "rollbackSqlSha256",
        "bundleFingerprint",
    ):
        _hex(migration[key], 64, key)
    _hex(migration["migrationSourceCommit"], 40, "migration source commit")
    if producer["headSha"] != migration["migrationSourceCommit"]:
        _fail("migration producer head 与 source commit 不一致")
    if migration["bundleFingerprint"] != _migration_fingerprint(migration):
        _fail("migration bundle fingerprint 不自洽")
    if expected_migration is not None:
        normalized_expected = {
            **expected_migration,
            "bundleFingerprint": _migration_fingerprint(expected_migration),
        }
        if migration != normalized_expected:
            _fail("migration bundle 与可信 source 不一致")
    reports = _exact(
        document["reports"],
        QUALIFICATION_REPORT_HASH_KEYS,
        "qualification report hashes",
    )
    for key in QUALIFICATION_REPORT_HASH_KEYS:
        _hex(reports[key], 64, key)
    return _validate_window(
        document["issuedAt"],
        document["expiresAt"],
        now=now,
        maximum_ttl=QUALIFICATION_TTL,
        label="migration qualification",
    )


def _validate_candidate_summary(
    document: dict[str, Any],
    *,
    now: datetime,
    expected_producer: dict[str, str] | None = None,
    expected_target_commit: str | None = None,
    expected_development_scope: str | None = None,
    expected_scenario: str | None = None,
    expected_execution_fingerprint: str | None = None,
    expected_images: dict[str, str] | None = None,
    expected_policies: dict[str, Any] | None = None,
    expected_subjects: dict[str, str] | None = None,
    expected_qualification_sha: str | None = None,
) -> tuple[datetime, datetime]:
    _exact(document, CANDIDATE_KEYS, "candidate evidence")
    if document["format"] != CANDIDATE_FORMAT:
        _fail("candidate evidence format 无效")
    target = _hex(document["targetReleaseCommit"], 40, "target release commit")
    scope = _hex(document["developmentScopeSha256"], 64, "development scope SHA")
    scenario = _hex(document["canaryScenarioFingerprint"], 64, "canary scenario fingerprint")
    execution = _hex(
        document["executionManifestFingerprint"],
        64,
        "execution manifest fingerprint",
    )
    qualification_sha = _hex(
        document["migrationQualificationSha256"],
        64,
        "migration qualification SHA",
    )
    if scope == scenario:
        _fail("development scope 与 canary scenario 不得混用")
    producer = _validate_producer(document["producer"], expected=expected_producer)
    if producer["headSha"] != target:
        _fail("candidate producer head 与 target commit 不一致")
    images = _validate_images(document["images"], expected_images)
    policies = _validate_policies(document["policies"], expected_policies)
    subjects = _validate_subjects(document["subjects"], expected_subjects)
    reports = _exact(
        document["reports"],
        CANDIDATE_REPORT_HASH_KEYS,
        "candidate report hashes",
    )
    for key in CANDIDATE_REPORT_HASH_KEYS:
        _hex(reports[key], 64, key)
    if expected_target_commit is not None and target != _hex(
        expected_target_commit, 40, "预期 target release commit"
    ):
        _fail("candidate target commit 与可信 source 不一致")
    if expected_development_scope is not None and scope != _hex(
        expected_development_scope, 64, "预期 development scope SHA"
    ):
        _fail("candidate development scope 不一致")
    if expected_scenario is not None and scenario != _hex(
        expected_scenario, 64, "预期 canary scenario fingerprint"
    ):
        _fail("candidate canary scenario 不一致")
    if expected_execution_fingerprint is not None and execution != _hex(
        expected_execution_fingerprint, 64, "预期 execution fingerprint"
    ):
        _fail("candidate execution fingerprint 不一致")
    if expected_qualification_sha is not None and qualification_sha != _hex(
        expected_qualification_sha, 64, "预期 migration qualification SHA"
    ):
        _fail("candidate migration qualification SHA 不一致")
    if expected_images is not None and images != expected_images:
        _fail("candidate images 不一致")
    if expected_policies is not None and policies != expected_policies:
        _fail("candidate policies 不一致")
    if expected_subjects is not None and subjects != expected_subjects:
        _fail("candidate subjects 不一致")
    return _validate_window(
        document["issuedAt"],
        document["expiresAt"],
        now=now,
        maximum_ttl=CANDIDATE_TTL,
        label="candidate evidence",
    )


def _qualification_binding(document: dict[str, Any]) -> dict[str, Any]:
    migration = document["migration"]
    return {
        "database": document["database"],
        "developmentScopeSha256": document["developmentScopeSha256"],
        "expiresAt": document["expiresAt"],
        "issuedAt": document["issuedAt"],
        "migrationBundleFingerprint": migration["bundleFingerprint"],
        "producer": document["producer"],
    }


def _candidate_binding(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "canaryScenarioFingerprint": document["canaryScenarioFingerprint"],
        "developmentScopeSha256": document["developmentScopeSha256"],
        "executionManifestFingerprint": document["executionManifestFingerprint"],
        "expiresAt": document["expiresAt"],
        "images": document["images"],
        "issuedAt": document["issuedAt"],
        "policies": document["policies"],
        "producer": document["producer"],
        "subjects": document["subjects"],
        "targetReleaseCommit": document["targetReleaseCommit"],
    }


def verify_qualification_bundle(
    directory: Path,
    *,
    now: datetime,
    expected_sha: str | None = None,
    expected_producer: dict[str, str] | None = None,
    expected_development_scope: str | None = None,
    expected_migration: dict[str, str] | None = None,
) -> tuple[dict[str, Any], str]:
    summary, reports, payloads, digest = _load_bundle(
        directory,
        "migration-qualification.json",
        QUALIFICATION_REPORT_FILES,
    )
    _validate_qualification_summary(
        summary,
        now=now,
        expected_producer=expected_producer,
        expected_development_scope=expected_development_scope,
        expected_migration=expected_migration,
    )
    if expected_sha is not None and digest != _hex(
        expected_sha, 64, "预期 migration qualification SHA"
    ):
        _fail("migration qualification artifact SHA 不一致")
    hash_map = {
        "migration-backup": "backupSha256",
        "live-contract": "liveContractSha256",
        "idempotent-forward": "idempotentForwardSha256",
        "rollback-rehearsal": "rollbackRehearsalSha256",
    }
    for report_type, file_name in QUALIFICATION_REPORT_FILES.items():
        if _sha256(payloads[file_name]) != summary["reports"][hash_map[report_type]]:
            _fail(f"{report_type} report SHA 与 qualification 不一致")
    migration = summary["migration"]
    binding = _qualification_binding(summary)
    backup_sha = _sha256(payloads[QUALIFICATION_REPORT_FILES["migration-backup"]])
    for report_type in QUALIFICATION_REPORT_FILES:
        _validate_migration_report(
            reports[report_type],
            report_type=report_type,
            binding=binding,
            pre_contract=migration["preContractFingerprint"],
            post_contract=migration["postContractFingerprint"],
            backup_report_sha=(backup_sha if report_type == "idempotent-forward" else None),
        )
    return summary, digest


def verify_candidate_bundle(
    directory: Path,
    *,
    qualification_directory: Path,
    now: datetime,
    expected_sha: str | None = None,
    expected_producer: dict[str, str] | None = None,
    expected_target_commit: str | None = None,
    expected_development_scope: str | None = None,
    expected_scenario: str | None = None,
    expected_execution_fingerprint: str | None = None,
    expected_images: dict[str, str] | None = None,
    expected_policies: dict[str, Any] | None = None,
    expected_subjects: dict[str, str] | None = None,
    expected_qualification_sha: str | None = None,
) -> tuple[dict[str, Any], str]:
    summary, reports, payloads, digest = _load_bundle(
        directory,
        "candidate-evidence.json",
        CANDIDATE_REPORT_FILES,
    )
    candidate_issued, candidate_expires = _validate_candidate_summary(
        summary,
        now=now,
        expected_producer=expected_producer,
        expected_target_commit=expected_target_commit,
        expected_development_scope=expected_development_scope,
        expected_scenario=expected_scenario,
        expected_execution_fingerprint=expected_execution_fingerprint,
        expected_images=expected_images,
        expected_policies=expected_policies,
        expected_subjects=expected_subjects,
        expected_qualification_sha=expected_qualification_sha,
    )
    if expected_sha is not None and digest != _hex(expected_sha, 64, "预期 candidate evidence SHA"):
        _fail("candidate evidence artifact SHA 不一致")
    qualification, qualification_digest = verify_qualification_bundle(
        qualification_directory,
        now=now,
        expected_sha=summary["migrationQualificationSha256"],
        expected_development_scope=summary["developmentScopeSha256"],
    )
    if expected_qualification_sha is not None and qualification_digest != _hex(
        expected_qualification_sha, 64, "预期 qualification SHA"
    ):
        _fail("candidate 引用的 qualification 与可信输入不一致")
    qualification_issued = _parse_time(qualification["issuedAt"], "qualification issuedAt")
    qualification_expires = _parse_time(qualification["expiresAt"], "qualification expiresAt")
    if candidate_issued < qualification_issued:
        _fail("candidate 签发时间早于 migration qualification")
    if candidate_expires > qualification_expires:
        _fail("candidate 有效期超过 migration qualification")
    hash_map = {
        "fault-injection": "faultInjectionSha256",
        "resource-constrained": "resourceConstrainedSha256",
        "provider-canary": "providerCanarySha256",
    }
    for report_type, file_name in CANDIDATE_REPORT_FILES.items():
        if _sha256(payloads[file_name]) != summary["reports"][hash_map[report_type]]:
            _fail(f"{report_type} report SHA 与 candidate 不一致")
    binding = _candidate_binding(summary)
    for report_type in CANDIDATE_REPORT_FILES:
        _validate_candidate_report(
            reports[report_type],
            report_type=report_type,
            binding=binding,
        )
    return summary, digest


def _producer_from_arguments(arguments: argparse.Namespace) -> dict[str, str]:
    return {
        "headSha": arguments.producer_head_sha,
        "repository": arguments.producer_repository,
        "runAttempt": arguments.producer_run_attempt,
        "runId": arguments.producer_run_id,
        "workflowPath": PRODUCER_WORKFLOW,
    }


def _images_from_arguments(arguments: argparse.Namespace) -> dict[str, str]:
    return {
        "agent": arguments.agent_digest,
        "core": arguments.core_digest,
        "web": arguments.web_digest,
    }


def _policies_from_arguments(arguments: argparse.Namespace) -> dict[str, Any]:
    return {
        "providerMaxCompletionTokens": arguments.provider_max_completion_tokens,
        "providerMaxCostMicros": arguments.provider_max_cost_micros,
        "providerMaxPromptTokens": arguments.provider_max_prompt_tokens,
        "providerMaxReasoningTokens": arguments.provider_max_reasoning_tokens,
        "providerMaxTotalTokens": arguments.provider_max_total_tokens,
        "providerUsageCostPolicySha256": arguments.provider_usage_cost_policy_sha256,
        "providerUsageCostPolicyVersion": ("durable-agent-v2-provider-canary-budget/1"),
        "resourcePerformancePolicySha256": (arguments.resource_performance_policy_sha256),
        "resourcePerformancePolicyVersion": "durable-agent-v2-resource-slo/1",
    }


def _subjects_from_arguments(arguments: argparse.Namespace) -> dict[str, str]:
    return {
        "providerIdentitySha256": arguments.provider_identity_sha256,
        "resourceHostIdentitySha256": arguments.resource_host_identity_sha256,
    }


def create_qualification(arguments: argparse.Namespace) -> str:
    now = _parse_trusted_now(arguments.trusted_now)
    producer = _producer_from_arguments(arguments)
    migration: dict[str, Any] = {
        "forwardSqlSha256": arguments.forward_sql_sha256,
        "migrationSourceCommit": arguments.migration_source_commit,
        "postContractFingerprint": arguments.post_contract_fingerprint,
        "preContractFingerprint": arguments.pre_contract_fingerprint,
        "rollbackSqlSha256": arguments.rollback_sql_sha256,
    }
    migration["bundleFingerprint"] = _migration_fingerprint(migration)
    report_documents, report_payloads, report_digests = _load_report_source(
        arguments.reports_dir,
        QUALIFICATION_REPORT_FILES,
    )
    summary: dict[str, Any] = {
        "database": "novelwriterdev",
        "developmentScopeSha256": arguments.development_scope_sha256,
        "expiresAt": arguments.expires_at,
        "format": QUALIFICATION_FORMAT,
        "issuedAt": arguments.issued_at,
        "migration": migration,
        "producer": producer,
        "reports": {
            "backupSha256": report_digests[QUALIFICATION_REPORT_FILES["migration-backup"]],
            "idempotentForwardSha256": report_digests[
                QUALIFICATION_REPORT_FILES["idempotent-forward"]
            ],
            "liveContractSha256": report_digests[QUALIFICATION_REPORT_FILES["live-contract"]],
            "rollbackRehearsalSha256": report_digests[
                QUALIFICATION_REPORT_FILES["rollback-rehearsal"]
            ],
        },
    }
    _validate_qualification_summary(
        summary,
        now=now,
        expected_producer=producer,
        expected_development_scope=arguments.development_scope_sha256,
        expected_migration={
            key: migration[key] for key in MIGRATION_KEYS if key != "bundleFingerprint"
        },
    )
    binding = _qualification_binding(summary)
    backup_sha = report_digests[QUALIFICATION_REPORT_FILES["migration-backup"]]
    for report_type in QUALIFICATION_REPORT_FILES:
        _validate_migration_report(
            report_documents[report_type],
            report_type=report_type,
            binding=binding,
            pre_contract=migration["preContractFingerprint"],
            post_contract=migration["postContractFingerprint"],
            backup_report_sha=(backup_sha if report_type == "idempotent-forward" else None),
        )
    return _create_bundle(
        arguments.output_dir,
        summary_name="migration-qualification.json",
        summary=summary,
        report_payloads=report_payloads,
        report_files=QUALIFICATION_REPORT_FILES,
    )


def create_candidate(arguments: argparse.Namespace) -> str:
    now = _parse_trusted_now(arguments.trusted_now)
    producer = _producer_from_arguments(arguments)
    images = _images_from_arguments(arguments)
    policies = _policies_from_arguments(arguments)
    subjects = _subjects_from_arguments(arguments)
    qualification, qualification_sha = verify_qualification_bundle(
        arguments.qualification_dir,
        now=now,
        expected_sha=arguments.migration_qualification_sha256,
        expected_development_scope=arguments.development_scope_sha256,
    )
    report_documents, report_payloads, report_digests = _load_report_source(
        arguments.reports_dir,
        CANDIDATE_REPORT_FILES,
    )
    summary: dict[str, Any] = {
        "canaryScenarioFingerprint": arguments.canary_scenario_fingerprint,
        "developmentScopeSha256": arguments.development_scope_sha256,
        "executionManifestFingerprint": arguments.execution_manifest_fingerprint,
        "expiresAt": arguments.expires_at,
        "format": CANDIDATE_FORMAT,
        "images": images,
        "issuedAt": arguments.issued_at,
        "migrationQualificationSha256": qualification_sha,
        "policies": policies,
        "producer": producer,
        "reports": {
            "faultInjectionSha256": report_digests[CANDIDATE_REPORT_FILES["fault-injection"]],
            "providerCanarySha256": report_digests[CANDIDATE_REPORT_FILES["provider-canary"]],
            "resourceConstrainedSha256": report_digests[
                CANDIDATE_REPORT_FILES["resource-constrained"]
            ],
        },
        "subjects": subjects,
        "targetReleaseCommit": arguments.target_release_commit,
    }
    candidate_issued, candidate_expires = _validate_candidate_summary(
        summary,
        now=now,
        expected_producer=producer,
        expected_target_commit=arguments.target_release_commit,
        expected_development_scope=arguments.development_scope_sha256,
        expected_scenario=arguments.canary_scenario_fingerprint,
        expected_execution_fingerprint=arguments.execution_manifest_fingerprint,
        expected_images=images,
        expected_policies=policies,
        expected_subjects=subjects,
        expected_qualification_sha=qualification_sha,
    )
    qualification_issued = _parse_time(qualification["issuedAt"], "qualification issuedAt")
    qualification_expires = _parse_time(qualification["expiresAt"], "qualification expiresAt")
    if candidate_issued < qualification_issued:
        _fail("candidate 签发时间早于 migration qualification")
    if candidate_expires > qualification_expires:
        _fail("candidate 有效期超过 migration qualification")
    binding = _candidate_binding(summary)
    for report_type in CANDIDATE_REPORT_FILES:
        _validate_candidate_report(
            report_documents[report_type],
            report_type=report_type,
            binding=binding,
        )
    return _create_bundle(
        arguments.output_dir,
        summary_name="candidate-evidence.json",
        summary=summary,
        report_payloads=report_payloads,
        report_files=CANDIDATE_REPORT_FILES,
    )


def _add_producer_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--producer-repository", required=True)
    parser.add_argument("--producer-run-id", required=True)
    parser.add_argument("--producer-run-attempt", required=True)
    parser.add_argument("--producer-head-sha", required=True)


def _add_image_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--web-digest", required=True)
    parser.add_argument("--core-digest", required=True)
    parser.add_argument("--agent-digest", required=True)


def _add_time_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--issued-at", required=True)
    parser.add_argument("--expires-at", required=True)
    parser.add_argument("--trusted-now")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)

    scope = actions.add_parser("development-scope-fingerprint")
    scope.add_argument("--database-identity-sha256", required=True)
    scope.add_argument("--ordinary-redis-identity-sha256", required=True)
    scope.add_argument("--execution-redis-identity-sha256", required=True)
    scope.add_argument("--topology-sha256", required=True)

    scenario = actions.add_parser("canary-scenario-fingerprint")
    scenario.add_argument("--actor-scope-sha256", required=True)
    scenario.add_argument("--assertions-sha256", required=True)
    scenario.add_argument("--fixture-sha256", required=True)
    scenario.add_argument("--operation", required=True)
    scenario.add_argument("--scenario-version", required=True)

    create_qualification_parser = actions.add_parser("create-qualification")
    create_qualification_parser.add_argument("--reports-dir", type=Path, required=True)
    create_qualification_parser.add_argument("--output-dir", type=Path, required=True)
    create_qualification_parser.add_argument("--development-scope-sha256", required=True)
    create_qualification_parser.add_argument("--migration-source-commit", required=True)
    create_qualification_parser.add_argument("--forward-sql-sha256", required=True)
    create_qualification_parser.add_argument("--rollback-sql-sha256", required=True)
    create_qualification_parser.add_argument("--pre-contract-fingerprint", required=True)
    create_qualification_parser.add_argument("--post-contract-fingerprint", required=True)
    _add_producer_arguments(create_qualification_parser)
    _add_time_arguments(create_qualification_parser)

    verify_qualification_parser = actions.add_parser("verify-qualification")
    verify_qualification_parser.add_argument("--qualification-dir", type=Path, required=True)
    verify_qualification_parser.add_argument("--expected-sha256", required=True)
    verify_qualification_parser.add_argument("--expected-development-scope-sha256", required=True)
    verify_qualification_parser.add_argument("--expected-migration-source-commit", required=True)
    verify_qualification_parser.add_argument("--expected-forward-sql-sha256", required=True)
    verify_qualification_parser.add_argument("--expected-rollback-sql-sha256", required=True)
    verify_qualification_parser.add_argument("--expected-pre-contract-fingerprint", required=True)
    verify_qualification_parser.add_argument("--expected-post-contract-fingerprint", required=True)
    verify_qualification_parser.add_argument("--expected-repository", required=True)
    verify_qualification_parser.add_argument("--expected-run-id", required=True)
    verify_qualification_parser.add_argument("--expected-run-attempt", required=True)
    verify_qualification_parser.add_argument("--trusted-now")

    create_candidate_parser = actions.add_parser("create-candidate")
    create_candidate_parser.add_argument("--reports-dir", type=Path, required=True)
    create_candidate_parser.add_argument("--output-dir", type=Path, required=True)
    create_candidate_parser.add_argument("--qualification-dir", type=Path, required=True)
    create_candidate_parser.add_argument("--migration-qualification-sha256", required=True)
    create_candidate_parser.add_argument("--target-release-commit", required=True)
    create_candidate_parser.add_argument("--development-scope-sha256", required=True)
    create_candidate_parser.add_argument("--canary-scenario-fingerprint", required=True)
    create_candidate_parser.add_argument("--execution-manifest-fingerprint", required=True)
    create_candidate_parser.add_argument("--resource-performance-policy-sha256", required=True)
    create_candidate_parser.add_argument("--provider-usage-cost-policy-sha256", required=True)
    create_candidate_parser.add_argument("--provider-max-prompt-tokens", type=int, required=True)
    create_candidate_parser.add_argument(
        "--provider-max-completion-tokens", type=int, required=True
    )
    create_candidate_parser.add_argument("--provider-max-reasoning-tokens", type=int, required=True)
    create_candidate_parser.add_argument("--provider-max-total-tokens", type=int, required=True)
    create_candidate_parser.add_argument("--provider-max-cost-micros", type=int, required=True)
    create_candidate_parser.add_argument("--resource-host-identity-sha256", required=True)
    create_candidate_parser.add_argument("--provider-identity-sha256", required=True)
    _add_image_arguments(create_candidate_parser)
    _add_producer_arguments(create_candidate_parser)
    _add_time_arguments(create_candidate_parser)

    verify_candidate_parser = actions.add_parser("verify-candidate")
    verify_candidate_parser.add_argument("--candidate-dir", type=Path, required=True)
    verify_candidate_parser.add_argument("--qualification-dir", type=Path, required=True)
    verify_candidate_parser.add_argument("--expected-sha256", required=True)
    verify_candidate_parser.add_argument("--expected-migration-qualification-sha256", required=True)
    verify_candidate_parser.add_argument("--expected-target-release-commit", required=True)
    verify_candidate_parser.add_argument("--expected-development-scope-sha256", required=True)
    verify_candidate_parser.add_argument("--expected-canary-scenario-fingerprint", required=True)
    verify_candidate_parser.add_argument("--expected-execution-manifest-fingerprint", required=True)
    verify_candidate_parser.add_argument("--expected-web-digest", required=True)
    verify_candidate_parser.add_argument("--expected-core-digest", required=True)
    verify_candidate_parser.add_argument("--expected-agent-digest", required=True)
    verify_candidate_parser.add_argument(
        "--expected-resource-performance-policy-sha256", required=True
    )
    verify_candidate_parser.add_argument(
        "--expected-provider-usage-cost-policy-sha256", required=True
    )
    verify_candidate_parser.add_argument(
        "--expected-provider-max-prompt-tokens", type=int, required=True
    )
    verify_candidate_parser.add_argument(
        "--expected-provider-max-completion-tokens", type=int, required=True
    )
    verify_candidate_parser.add_argument(
        "--expected-provider-max-reasoning-tokens", type=int, required=True
    )
    verify_candidate_parser.add_argument(
        "--expected-provider-max-total-tokens", type=int, required=True
    )
    verify_candidate_parser.add_argument(
        "--expected-provider-max-cost-micros", type=int, required=True
    )
    verify_candidate_parser.add_argument("--expected-resource-host-identity-sha256", required=True)
    verify_candidate_parser.add_argument("--expected-provider-identity-sha256", required=True)
    verify_candidate_parser.add_argument("--expected-repository", required=True)
    verify_candidate_parser.add_argument("--expected-run-id", required=True)
    verify_candidate_parser.add_argument("--expected-run-attempt", required=True)
    verify_candidate_parser.add_argument("--trusted-now")
    return parser


def _expected_producer_from_verify(
    arguments: argparse.Namespace,
    head_sha: str,
) -> dict[str, str]:
    return {
        "headSha": head_sha,
        "repository": arguments.expected_repository,
        "runAttempt": arguments.expected_run_attempt,
        "runId": arguments.expected_run_id,
        "workflowPath": PRODUCER_WORKFLOW,
    }


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.action == "development-scope-fingerprint":
            print(
                development_scope_fingerprint(
                    database_identity_sha256=arguments.database_identity_sha256,
                    ordinary_redis_identity_sha256=(arguments.ordinary_redis_identity_sha256),
                    execution_redis_identity_sha256=(arguments.execution_redis_identity_sha256),
                    topology_sha256=arguments.topology_sha256,
                )
            )
            return 0
        if arguments.action == "canary-scenario-fingerprint":
            print(
                canary_scenario_fingerprint(
                    actor_scope_sha256=arguments.actor_scope_sha256,
                    assertions_sha256=arguments.assertions_sha256,
                    fixture_sha256=arguments.fixture_sha256,
                    operation=arguments.operation,
                    scenario_version=arguments.scenario_version,
                )
            )
            return 0
        if arguments.action == "create-qualification":
            digest = create_qualification(arguments)
            print(f"development-qualification-created:{digest}")
            return 0
        if arguments.action == "verify-qualification":
            now = _parse_trusted_now(arguments.trusted_now)
            expected_migration = {
                "forwardSqlSha256": arguments.expected_forward_sql_sha256,
                "migrationSourceCommit": (arguments.expected_migration_source_commit),
                "postContractFingerprint": (arguments.expected_post_contract_fingerprint),
                "preContractFingerprint": (arguments.expected_pre_contract_fingerprint),
                "rollbackSqlSha256": arguments.expected_rollback_sql_sha256,
            }
            producer = _expected_producer_from_verify(
                arguments,
                arguments.expected_migration_source_commit,
            )
            _, digest = verify_qualification_bundle(
                arguments.qualification_dir,
                now=now,
                expected_sha=arguments.expected_sha256,
                expected_producer=producer,
                expected_development_scope=(arguments.expected_development_scope_sha256),
                expected_migration=expected_migration,
            )
            print(f"development-qualification-verified:{digest}")
            return 0
        if arguments.action == "create-candidate":
            digest = create_candidate(arguments)
            print(f"development-candidate-created:{digest}")
            return 0
        now = _parse_trusted_now(arguments.trusted_now)
        expected_images = {
            "agent": _digest(arguments.expected_agent_digest, "预期 agent image"),
            "core": _digest(arguments.expected_core_digest, "预期 core image"),
            "web": _digest(arguments.expected_web_digest, "预期 web image"),
        }
        expected_policies = {
            "providerMaxCompletionTokens": (arguments.expected_provider_max_completion_tokens),
            "providerMaxCostMicros": arguments.expected_provider_max_cost_micros,
            "providerMaxPromptTokens": arguments.expected_provider_max_prompt_tokens,
            "providerMaxReasoningTokens": (arguments.expected_provider_max_reasoning_tokens),
            "providerMaxTotalTokens": arguments.expected_provider_max_total_tokens,
            "providerUsageCostPolicySha256": _hex(
                arguments.expected_provider_usage_cost_policy_sha256,
                64,
                "预期 provider usage/cost policy SHA",
            ),
            "providerUsageCostPolicyVersion": ("durable-agent-v2-provider-canary-budget/1"),
            "resourcePerformancePolicySha256": _hex(
                arguments.expected_resource_performance_policy_sha256,
                64,
                "预期 resource performance policy SHA",
            ),
            "resourcePerformancePolicyVersion": "durable-agent-v2-resource-slo/1",
        }
        expected_subjects = {
            "providerIdentitySha256": _hex(
                arguments.expected_provider_identity_sha256,
                64,
                "预期 provider identity SHA",
            ),
            "resourceHostIdentitySha256": _hex(
                arguments.expected_resource_host_identity_sha256,
                64,
                "预期 resource host identity SHA",
            ),
        }
        producer = _expected_producer_from_verify(
            arguments,
            arguments.expected_target_release_commit,
        )
        _, digest = verify_candidate_bundle(
            arguments.candidate_dir,
            qualification_directory=arguments.qualification_dir,
            now=now,
            expected_sha=arguments.expected_sha256,
            expected_producer=producer,
            expected_target_commit=arguments.expected_target_release_commit,
            expected_development_scope=(arguments.expected_development_scope_sha256),
            expected_scenario=arguments.expected_canary_scenario_fingerprint,
            expected_execution_fingerprint=(arguments.expected_execution_manifest_fingerprint),
            expected_images=expected_images,
            expected_policies=expected_policies,
            expected_subjects=expected_subjects,
            expected_qualification_sha=(arguments.expected_migration_qualification_sha256),
        )
        print(f"development-candidate-verified:{digest}")
        return 0
    except (EvidenceV2Invalid, OSError) as error:
        print(f"development-evidence-v2-error:{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
