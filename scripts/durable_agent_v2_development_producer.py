#!/usr/bin/env python3
"""复验 Durable Agent V2 development producer 前提并生成固定阻断计划。"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from durable_agent_v2_control_bundle import BundleInvalid
from durable_agent_v2_control_bundle import verify as verify_control_bundle
from durable_agent_v2_development_evidence import _canonical_bytes as canonical_bytes
from durable_agent_v2_development_evidence_v2 import (
    EvidenceV2Invalid,
    _create_bundle,
    _digest,
    _exact,
    _hex,
    _load_bundle,
    _positive_decimal,
    verify_candidate_bundle,
    verify_qualification_bundle,
)
from verify_github_environment_policy import PolicyInvalid
from verify_github_environment_policy import _load as load_github_document
from verify_github_environment_policy import verify as verify_environment_base
from verify_github_workflow_run_provenance import ProvenanceInvalid
from verify_github_workflow_run_provenance import _load as load_run_document
from verify_github_workflow_run_provenance import verify as verify_run_provenance

DEVELOPMENT_WORKFLOW = ".github/workflows/durable-agent-v2-development-evidence.yml"
IMAGE_FORMAT = "inkforge-durable-agent-v2-development-images/1"
PLAN_FORMAT = "inkforge-durable-agent-v2-development-remote-plan/1"
POLICY_VERSION = "inkforge-durable-agent-v2-development-producer-policy/1"
BUILD_DEFINITION_FORMAT = "inkforge-durable-agent-v2-build-definition/1"
MAX_SOURCE_TREE_MANIFEST_BYTES = 16 * 1_048_576
MAX_BUILD_DEFINITION_FILE_BYTES = 8 * 1_048_576

BUILD_DEFINITION_FILES = (
    ".dockerignore",
    ".mvn/wrapper/maven-wrapper.properties",
    ".python-version",
    "apps/agent-service/pyproject.toml",
    "apps/core-api-java/pom.xml",
    "apps/web/package.json",
    "infra/compose.yaml",
    "infra/docker/agent-service.Dockerfile",
    "infra/docker/core-api.Dockerfile",
    "infra/docker/inkforge-schema-guard",
    "infra/docker/web.Dockerfile",
    "mvnw",
    "package-lock.json",
    "package.json",
    "packages/api-client/package.json",
    "packages/service-auth-java/pom.xml",
    "packages/service-auth/pyproject.toml",
    "packages/service-contracts-java/pom.xml",
    "packages/service-contracts/pyproject.toml",
    "pom.xml",
    "pyproject.toml",
    "tools/inkforge-cli-java/pom.xml",
    "uv.lock",
)

PRODUCER_KEYS = {"headSha", "repository", "runAttempt", "runId", "workflowPath"}
IMAGE_KEYS = {
    "buildDefinitionSha256",
    "executionManifestFingerprint",
    "format",
    "images",
    "producer",
    "sourceTreeSha256",
    "targetReleaseCommit",
}
PLAN_KEYS = {
    "decision",
    "format",
    "localFaultEvidenceClass",
    "producer",
    "reasonCodes",
    "targetReleaseCommit",
}
SERVICE_KEYS = {"agent", "core", "web"}
PLAN_REASONS = [
    "provider-identity-unavailable",
    "remote-driver-unavailable",
    "resource-host-unavailable",
    "route-off-cleanup-unavailable",
]

REQUIRED_HEX_VARIABLES = {
    "DURABLE_AGENT_V2_DEVELOPMENT_BUILD_DEFINITION_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_CANARY_SCENARIO_FINGERPRINT",
    "DURABLE_AGENT_V2_DEVELOPMENT_DEVELOPMENT_SCOPE_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_EXECUTION_MANIFEST_FINGERPRINT",
    "DURABLE_AGENT_V2_DEVELOPMENT_MIGRATION_QUALIFICATION_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_IDENTITY_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_POLICY_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_RESOURCE_HOST_IDENTITY_SHA256",
    "DURABLE_AGENT_V2_DEVELOPMENT_RESOURCE_POLICY_SHA256",
}
REQUIRED_INTEGER_VARIABLES = {
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_COMPLETION_TOKENS",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_COST_MICROS",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_PROMPT_TOKENS",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_REASONING_TOKENS",
    "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_TOTAL_TOKENS",
}
POLICY_VERSION_VARIABLE = "DURABLE_AGENT_V2_DEVELOPMENT_PRODUCER_POLICY_VERSION"
FORBIDDEN_REMOTE_SECRETS = {
    "DURABLE_AGENT_V2_DEVELOPMENT_SSH_PRIVATE_KEY",
    "DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY",
    "OPENAI_API_KEY",
    "SERVER_SSH_KEY",
}


class ProducerInvalid(ValueError):
    """development producer 不能建立可信远程证据。"""


def _fail(message: str) -> NoReturn:
    raise ProducerInvalid(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _nonzero_hex(value: Any, length: int, label: str) -> str:
    validated = _hex(value, length, label)
    if validated == "0" * length:
        _fail(f"{label} 不得是零占位")
    return validated


def _secure_checkout_read(path: Path, *, maximum: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ProducerInvalid(f"{label} 无法安全打开") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > maximum
        ):
            _fail(f"{label} 不是有界单链接普通文件")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1_048_576, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if any(getattr(before, field) != getattr(after, field) for field in identity):
        _fail(f"{label} 读取中发生漂移")
    if len(payload) != before.st_size or len(payload) > maximum:
        _fail(f"{label} 长度漂移或超限")
    return payload


def _repository_root(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        _fail("checkout repository root 无效")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ProducerInvalid("checkout repository root 无法解析") from error
    if resolved != path:
        _fail("checkout repository root 必须是已解析绝对路径")
    return resolved


def source_tree_sha256(manifest_path: Path, *, target_commit: str) -> str:
    target = _hex(target_commit, 40, "source tree target commit")
    payload = _secure_checkout_read(
        manifest_path,
        maximum=MAX_SOURCE_TREE_MANIFEST_BYTES,
        label="git source tree manifest",
    )
    if not payload.endswith(b"\0"):
        _fail("git source tree manifest 必须是 NUL 终止")
    records = payload[:-1].split(b"\0")
    if len(records) < 2 or any(not record for record in records):
        _fail("git source tree manifest 不得为空或包含空记录")
    if records[0] != f"target {target}".encode("ascii"):
        _fail("git source tree manifest target 与可信 commit 不一致")
    paths: list[str] = []
    previous_path: bytes | None = None
    for record in records[1:]:
        matched = re.fullmatch(rb"(100644|100755) blob ([0-9a-f]{40})\t(.+)", record)
        if matched is None:
            _fail("git source tree manifest 记录格式或类型无效")
        path_bytes = matched.group(3)
        if previous_path is not None and path_bytes <= previous_path:
            _fail("git source tree manifest 路径必须唯一且严格有序")
        previous_path = path_bytes
        try:
            path_text = path_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ProducerInvalid("git source tree manifest 路径不是 UTF-8") from error
        pure = PurePosixPath(path_text)
        if (
            pure.is_absolute()
            or ".." in pure.parts
            or "." in pure.parts
            or not pure.parts
            or pure.parts[0] == ".git"
            or pure.as_posix() != path_text
        ):
            _fail("git source tree manifest 包含不安全路径")
        paths.append(path_text)
    missing = set(BUILD_DEFINITION_FILES).difference(paths)
    if missing:
        _fail("git source tree manifest 缺少冻结 build definition 文件")
    return _sha256(payload)


def build_definition_sha256(repository_root: Path) -> str:
    root = _repository_root(repository_root)
    files: dict[str, str] = {}
    for relative in BUILD_DEFINITION_FILES:
        path = root / relative
        payload = _secure_checkout_read(
            path,
            maximum=MAX_BUILD_DEFINITION_FILE_BYTES,
            label=f"build definition {relative}",
        )
        files[relative] = _sha256(payload)
    binding = {
        "filesSha256": files,
        "format": BUILD_DEFINITION_FORMAT,
    }
    return _sha256(canonical_bytes(binding))


def checkout_bindings(
    *,
    repository_root: Path,
    source_tree_manifest: Path,
    target_commit: str,
    expected_build_definition_sha256: str,
    expected_source_tree_sha256: str | None = None,
) -> dict[str, str]:
    source_sha = source_tree_sha256(
        source_tree_manifest,
        target_commit=target_commit,
    )
    build_sha = build_definition_sha256(repository_root)
    expected_build = _nonzero_hex(
        expected_build_definition_sha256,
        64,
        "trusted build definition SHA",
    )
    if build_sha != expected_build:
        _fail("checkout build definition 与独立 trusted expected 不一致")
    if expected_source_tree_sha256 is not None:
        expected_source = _nonzero_hex(
            expected_source_tree_sha256,
            64,
            "trusted source tree SHA",
        )
        if source_sha != expected_source:
            _fail("checkout source tree 与独立 trusted expected 不一致")
    return {
        "buildDefinitionSha256": build_sha,
        "sourceTreeSha256": source_sha,
    }


def _producer(
    value: Any,
    *,
    expected_repository: str,
    expected_commit: str,
    expected_run_id: str,
    expected_run_attempt: str,
) -> dict[str, Any]:
    producer = _exact(value, PRODUCER_KEYS, "development producer")
    expected = {
        "headSha": _hex(expected_commit, 40, "预期 target commit"),
        "repository": expected_repository,
        "runAttempt": _positive_decimal(expected_run_attempt, "预期 run attempt"),
        "runId": _positive_decimal(expected_run_id, "预期 run ID"),
        "workflowPath": DEVELOPMENT_WORKFLOW,
    }
    if expected["runAttempt"] != "1":
        _fail("development producer 只接受 runAttempt=1")
    if producer != expected:
        _fail("development producer 与可信 GitHub context 不一致")
    return producer


def _paged_items(
    document: dict[str, Any],
    *,
    collection_key: str,
    label: str,
) -> list[dict[str, Any]]:
    total = document.get("total_count")
    items = document.get(collection_key)
    if (
        isinstance(total, bool)
        or not isinstance(total, int)
        or not isinstance(items, list)
        or total != len(items)
        or any(not isinstance(item, dict) for item in items)
    ):
        _fail(f"{label} 分页或计数不完整")
    return items


def _policy_variables(document: dict[str, Any]) -> dict[str, str]:
    items = _paged_items(
        document,
        collection_key="variables",
        label="development variables",
    )
    variables: dict[str, str] = {}
    for item in items:
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not isinstance(value, str) or name in variables:
            _fail("development variable 身份无效或重复")
        variables[name] = value
    required_names = REQUIRED_HEX_VARIABLES | REQUIRED_INTEGER_VARIABLES | {POLICY_VERSION_VARIABLE}
    if set(variables) != required_names:
        _fail("development variables 必须精确匹配 producer policy 白名单")
    if variables[POLICY_VERSION_VARIABLE] != POLICY_VERSION:
        _fail("development producer policy version 无效")
    hashes: list[str] = []
    for name in sorted(REQUIRED_HEX_VARIABLES):
        value = _hex(variables[name], 64, f"development variable {name}")
        if value == "0" * 64:
            _fail(f"development variable {name} 不得是零占位")
        hashes.append(value)
    if len(set(hashes)) != len(hashes):
        _fail("development policy/subject/artifact SHA 不得复用")
    zero_allowed = {
        "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_COST_MICROS",
        "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_REASONING_TOKENS",
    }
    for name in sorted(REQUIRED_INTEGER_VARIABLES):
        value = variables[name]
        if (
            not value.isascii()
            or not value.isdecimal()
            or (value.startswith("0") and value != "0")
            or (value == "0" and name not in zero_allowed)
        ):
            _fail(f"development integer variable {name} 无效")
    return variables


def verify_environment_policy(
    *,
    environment_path: Path,
    branch_policies_path: Path,
    secrets_path: Path,
    variables_path: Path,
) -> dict[str, str]:
    try:
        environment = load_github_document(environment_path)
        branches = load_github_document(branch_policies_path)
        secrets = load_github_document(secrets_path)
        variables = load_github_document(variables_path)
        verify_environment_base(
            environment,
            branches,
            expected_environment="development",
            expected_branch="main",
        )
    except PolicyInvalid as error:
        raise ProducerInvalid("development environment policy 无效") from error
    secret_items = _paged_items(
        secrets,
        collection_key="secrets",
        label="development secrets",
    )
    secret_names = [item.get("name") for item in secret_items]
    if any(not isinstance(name, str) or not name for name in secret_names):
        _fail("development secret 名称无效")
    if len(secret_names) != len(set(secret_names)):
        _fail("development secret 名称重复")
    forbidden = FORBIDDEN_REMOTE_SECRETS.intersection(secret_names)
    if forbidden:
        _fail("development environment 当前不得配置远程 SSH/provider secret")
    if set(secret_names) != {"GH_ENVIRONMENT_POLICY_AUDIT_TOKEN"}:
        _fail("development secret inventory 必须精确只有只读 audit token")
    return _policy_variables(variables)


def _image_document(arguments: argparse.Namespace) -> dict[str, Any]:
    bindings = checkout_bindings(
        repository_root=arguments.repository_root,
        source_tree_manifest=arguments.source_tree_manifest,
        target_commit=arguments.target_release_commit,
        expected_build_definition_sha256=arguments.expected_build_definition_sha256,
        expected_source_tree_sha256=arguments.expected_source_tree_sha256,
    )
    return {
        "buildDefinitionSha256": bindings["buildDefinitionSha256"],
        "executionManifestFingerprint": arguments.execution_manifest_fingerprint,
        "format": IMAGE_FORMAT,
        "images": {
            "agent": arguments.agent_digest,
            "core": arguments.core_digest,
            "web": arguments.web_digest,
        },
        "producer": {
            "headSha": arguments.target_release_commit,
            "repository": arguments.repository,
            "runAttempt": arguments.run_attempt,
            "runId": arguments.run_id,
            "workflowPath": DEVELOPMENT_WORKFLOW,
        },
        "sourceTreeSha256": bindings["sourceTreeSha256"],
        "targetReleaseCommit": arguments.target_release_commit,
    }


def _validate_images(
    document: dict[str, Any],
    *,
    expected_repository: str,
    expected_commit: str,
    expected_run_id: str,
    expected_run_attempt: str,
    repository_root: Path,
    source_tree_manifest: Path,
    expected_source_tree_sha256: str,
    expected_build_definition_sha256: str,
) -> None:
    _exact(document, IMAGE_KEYS, "development image provenance")
    if document["format"] != IMAGE_FORMAT:
        _fail("development image provenance format 无效")
    target = _hex(document["targetReleaseCommit"], 40, "image target commit")
    if target != _hex(expected_commit, 40, "预期 target commit"):
        _fail("development image target commit 不一致")
    _producer(
        document["producer"],
        expected_repository=expected_repository,
        expected_commit=expected_commit,
        expected_run_id=expected_run_id,
        expected_run_attempt=expected_run_attempt,
    )
    _hex(document["executionManifestFingerprint"], 64, "execution fingerprint")
    bindings = checkout_bindings(
        repository_root=repository_root,
        source_tree_manifest=source_tree_manifest,
        target_commit=target,
        expected_build_definition_sha256=expected_build_definition_sha256,
        expected_source_tree_sha256=expected_source_tree_sha256,
    )
    if document["sourceTreeSha256"] != bindings["sourceTreeSha256"]:
        _fail("development image source tree 不是 checkout 重算值")
    if document["buildDefinitionSha256"] != bindings["buildDefinitionSha256"]:
        _fail("development image build definition 不是 checkout 重算值")
    images = _exact(document["images"], SERVICE_KEYS, "development images")
    digests = [_digest(images[name], f"{name} image") for name in sorted(SERVICE_KEYS)]
    if len(set(digests)) != 3:
        _fail("development images digest 必须互不相同")


def create_images(arguments: argparse.Namespace) -> str:
    document = _image_document(arguments)
    _validate_images(
        document,
        expected_repository=arguments.repository,
        expected_commit=arguments.target_release_commit,
        expected_run_id=arguments.run_id,
        expected_run_attempt=arguments.run_attempt,
        repository_root=arguments.repository_root,
        source_tree_manifest=arguments.source_tree_manifest,
        expected_source_tree_sha256=arguments.expected_source_tree_sha256,
        expected_build_definition_sha256=arguments.expected_build_definition_sha256,
    )
    return _create_bundle(
        arguments.output_dir,
        summary_name="development-images.json",
        summary=document,
        report_payloads={},
        report_files={},
    )


def verify_images(
    directory: Path,
    *,
    expected_sha: str | None,
    expected_repository: str,
    expected_commit: str,
    expected_run_id: str,
    expected_run_attempt: str,
    repository_root: Path,
    source_tree_manifest: Path,
    expected_source_tree_sha256: str,
    expected_build_definition_sha256: str,
) -> tuple[dict[str, Any], str]:
    document, reports, _, digest = _load_bundle(
        directory,
        "development-images.json",
        {},
    )
    if reports:
        _fail("development image provenance 不得包含 report")
    if expected_sha is not None and digest != _hex(
        expected_sha,
        64,
        "预期 image provenance SHA",
    ):
        _fail("development image provenance artifact SHA 不一致")
    _validate_images(
        document,
        expected_repository=expected_repository,
        expected_commit=expected_commit,
        expected_run_id=expected_run_id,
        expected_run_attempt=expected_run_attempt,
        repository_root=repository_root,
        source_tree_manifest=source_tree_manifest,
        expected_source_tree_sha256=expected_source_tree_sha256,
        expected_build_definition_sha256=expected_build_definition_sha256,
    )
    return document, digest


def _plan_document(arguments: argparse.Namespace) -> dict[str, Any]:
    return {
        "decision": "blocked",
        "format": PLAN_FORMAT,
        "localFaultEvidenceClass": "local-fake-prerequisite-only",
        "producer": {
            "headSha": arguments.target_release_commit,
            "repository": arguments.repository,
            "runAttempt": arguments.run_attempt,
            "runId": arguments.run_id,
            "workflowPath": DEVELOPMENT_WORKFLOW,
        },
        "reasonCodes": PLAN_REASONS,
        "targetReleaseCommit": arguments.target_release_commit,
    }


def _validate_plan(
    document: dict[str, Any],
    *,
    expected_repository: str,
    expected_commit: str,
    expected_run_id: str,
    expected_run_attempt: str,
) -> None:
    _exact(document, PLAN_KEYS, "development remote plan")
    if document["format"] != PLAN_FORMAT:
        _fail("development remote plan format 无效")
    if document["decision"] != "blocked":
        _fail("development remote plan 只能是 blocked")
    if document["localFaultEvidenceClass"] != "local-fake-prerequisite-only":
        _fail("本地 Fake evidence 只能作为前置")
    if document["reasonCodes"] != PLAN_REASONS:
        _fail("development remote plan reasonCodes 不完整")
    if document["targetReleaseCommit"] != expected_commit:
        _fail("development remote plan target commit 不一致")
    _producer(
        document["producer"],
        expected_repository=expected_repository,
        expected_commit=expected_commit,
        expected_run_id=expected_run_id,
        expected_run_attempt=expected_run_attempt,
    )


def create_blocked_plan(arguments: argparse.Namespace) -> str:
    document = _plan_document(arguments)
    _validate_plan(
        document,
        expected_repository=arguments.repository,
        expected_commit=arguments.target_release_commit,
        expected_run_id=arguments.run_id,
        expected_run_attempt=arguments.run_attempt,
    )
    return _create_bundle(
        arguments.output_dir,
        summary_name="development-remote-plan.json",
        summary=document,
        report_payloads={},
        report_files={},
    )


def verify_blocked_plan(
    directory: Path,
    *,
    expected_sha: str,
    expected_repository: str,
    expected_commit: str,
    expected_run_id: str,
    expected_run_attempt: str,
) -> str:
    document, reports, _, digest = _load_bundle(
        directory,
        "development-remote-plan.json",
        {},
    )
    if reports:
        _fail("development remote plan 不得包含 report")
    if digest != _hex(expected_sha, 64, "预期 remote plan SHA"):
        _fail("development remote plan artifact SHA 不一致")
    _validate_plan(
        document,
        expected_repository=expected_repository,
        expected_commit=expected_commit,
        expected_run_id=expected_run_id,
        expected_run_attempt=expected_run_attempt,
    )
    return digest


def verify_prerequisites(arguments: argparse.Namespace) -> dict[str, Any]:
    variables_document = load_github_document(arguments.variables_json)
    variables = _policy_variables(variables_document)
    target = _hex(arguments.target_release_commit, 40, "target release commit")
    _positive_decimal(arguments.run_id, "producer run ID")
    if _positive_decimal(arguments.run_attempt, "producer run attempt") != "1":
        _fail("development producer 只接受 runAttempt=1")

    image_document, image_sha = verify_images(
        arguments.images_dir,
        expected_sha=None,
        expected_repository=arguments.repository,
        expected_commit=target,
        expected_run_id=arguments.run_id,
        expected_run_attempt=arguments.run_attempt,
        repository_root=arguments.repository_root,
        source_tree_manifest=arguments.source_tree_manifest,
        expected_source_tree_sha256=arguments.expected_source_tree_sha256,
        expected_build_definition_sha256=variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_BUILD_DEFINITION_SHA256"
        ],
    )
    expected_images: dict[str, str] = {
        name: image_document["images"][name] for name in sorted(SERVICE_KEYS)
    }
    expected_execution = variables["DURABLE_AGENT_V2_DEVELOPMENT_EXECUTION_MANIFEST_FINGERPRINT"]
    if image_document["executionManifestFingerprint"] != expected_execution:
        _fail("development image execution fingerprint 不一致")
    try:
        control, control_sha = verify_control_bundle(
            arguments.control_bundle_dir,
            None,
        )
    except (BundleInvalid, OSError) as error:
        raise ProducerInvalid("development control bundle provenance 无效") from error
    expected_control = {
        "producerRunAttempt": arguments.run_attempt,
        "producerRunId": arguments.run_id,
        "targetReleaseCommit": target,
        "workflowTrustedCommit": target,
    }
    if any(control[key] != value for key, value in expected_control.items()):
        _fail("development control bundle producer/context 不一致")

    now = datetime.now(UTC).replace(microsecond=0)
    qualification, _ = verify_qualification_bundle(
        arguments.qualification_dir,
        now=now,
        expected_sha=variables["DURABLE_AGENT_V2_DEVELOPMENT_MIGRATION_QUALIFICATION_SHA256"],
        expected_development_scope=variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_DEVELOPMENT_SCOPE_SHA256"
        ],
    )
    producer = qualification["producer"]
    if producer["repository"] != arguments.repository:
        _fail("migration qualification producer repository 与可信仓库不一致")
    provenance_arguments = argparse.Namespace(
        run_json=arguments.qualification_run_json,
        expected_run_id=producer["runId"],
        expected_head_sha=producer["headSha"],
        expected_repository=arguments.repository,
        expected_workflow_path=DEVELOPMENT_WORKFLOW,
        expected_run_attempt=producer["runAttempt"],
    )
    try:
        verify_run_provenance(provenance_arguments)
    except ProvenanceInvalid as error:
        raise ProducerInvalid("migration qualification producer provenance 无效") from error
    if producer["runAttempt"] != "1":
        _fail("migration qualification producer 只接受 runAttempt=1")

    expected_policies: dict[str, Any] = {
        "providerMaxCompletionTokens": int(
            variables["DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_COMPLETION_TOKENS"]
        ),
        "providerMaxCostMicros": int(
            variables["DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_COST_MICROS"]
        ),
        "providerMaxPromptTokens": int(
            variables["DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_PROMPT_TOKENS"]
        ),
        "providerMaxReasoningTokens": int(
            variables["DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_REASONING_TOKENS"]
        ),
        "providerMaxTotalTokens": int(
            variables["DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_MAX_TOTAL_TOKENS"]
        ),
        "providerUsageCostPolicySha256": variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_POLICY_SHA256"
        ],
        "providerUsageCostPolicyVersion": ("durable-agent-v2-provider-canary-budget/1"),
        "resourcePerformancePolicySha256": variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_RESOURCE_POLICY_SHA256"
        ],
        "resourcePerformancePolicyVersion": "durable-agent-v2-resource-slo/1",
    }
    expected_subjects = {
        "providerIdentitySha256": variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_IDENTITY_SHA256"
        ],
        "resourceHostIdentitySha256": variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_RESOURCE_HOST_IDENTITY_SHA256"
        ],
    }
    expected_candidate_producer = {
        "headSha": target,
        "repository": arguments.repository,
        "runAttempt": arguments.run_attempt,
        "runId": arguments.run_id,
        "workflowPath": DEVELOPMENT_WORKFLOW,
    }
    _, candidate_sha = verify_candidate_bundle(
        arguments.candidate_dir,
        qualification_directory=arguments.qualification_dir,
        now=now,
        expected_sha=None,
        expected_producer=expected_candidate_producer,
        expected_target_commit=target,
        expected_development_scope=variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_DEVELOPMENT_SCOPE_SHA256"
        ],
        expected_scenario=variables["DURABLE_AGENT_V2_DEVELOPMENT_CANARY_SCENARIO_FINGERPRINT"],
        expected_execution_fingerprint=expected_execution,
        expected_images=expected_images,
        expected_policies=expected_policies,
        expected_subjects=expected_subjects,
        expected_qualification_sha=variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_MIGRATION_QUALIFICATION_SHA256"
        ],
    )
    verify_current_candidate_run(
        run_json=arguments.candidate_run_json,
        expected_run_id=arguments.run_id,
        expected_head_sha=target,
        expected_repository=arguments.repository,
        expected_run_attempt=arguments.run_attempt,
    )
    return {
        "buildDefinitionSha256": image_document["buildDefinitionSha256"],
        "candidateEvidenceSha256": candidate_sha,
        "controlBundleSha256": control_sha,
        "imageProvenanceSha256": image_sha,
        "images": expected_images,
        "sourceTreeSha256": image_document["sourceTreeSha256"],
    }


def verify_current_candidate_run(
    *,
    run_json: Path,
    expected_run_id: str,
    expected_head_sha: str,
    expected_repository: str,
    expected_run_attempt: str,
) -> None:
    """复验当前 candidate producer run，不把进行中阶段伪装成已完成证据。"""

    trusted_run_id = _positive_decimal(expected_run_id, "candidate current run ID")
    trusted_attempt = _positive_decimal(
        expected_run_attempt,
        "candidate current run attempt",
    )
    if trusted_attempt != "1":
        _fail("candidate producer current-run 只接受 runAttempt=1")
    trusted_head = _hex(expected_head_sha, 40, "candidate current head SHA")
    try:
        document = load_run_document(run_json)
        run_id = str(document["id"])
        repository = document["repository"]["full_name"]
    except ProvenanceInvalid as error:
        raise ProducerInvalid("candidate producer current-run provenance 无效") from error
    except (KeyError, TypeError) as error:
        raise ProducerInvalid("candidate producer current-run 缺少身份字段") from error
    expected = {
        "run ID": (run_id, trusted_run_id),
        "workflow path": (document.get("path"), DEVELOPMENT_WORKFLOW),
        "head SHA": (document.get("head_sha"), trusted_head),
        "head branch": (document.get("head_branch"), "main"),
        "event": (document.get("event"), "workflow_dispatch"),
        "status": (document.get("status"), "in_progress"),
        "conclusion": (document.get("conclusion"), None),
        "repository": (repository, expected_repository),
        "run attempt": (str(document.get("run_attempt")), trusted_attempt),
    }
    for label, (actual, wanted) in expected.items():
        if actual != wanted:
            _fail(f"candidate producer current-run {label} 不一致")


def _add_context_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository", required=True)
    parser.add_argument("--target-release-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)


def _add_verify_plan_arguments(parser: argparse.ArgumentParser) -> None:
    _add_context_arguments(parser)
    parser.add_argument("--expected-sha256", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)

    environment = actions.add_parser("verify-environment-policy")
    environment.add_argument("--environment-json", type=Path, required=True)
    environment.add_argument("--branch-policies-json", type=Path, required=True)
    environment.add_argument("--secrets-json", type=Path, required=True)
    environment.add_argument("--variables-json", type=Path, required=True)

    checkout = actions.add_parser("verify-checkout-bindings")
    checkout.add_argument("--repository-root", type=Path, required=True)
    checkout.add_argument("--source-tree-manifest", type=Path, required=True)
    checkout.add_argument("--target-release-commit", required=True)
    checkout.add_argument("--variables-json", type=Path, required=True)
    checkout.add_argument("--expected-source-tree-sha256")

    create_image = actions.add_parser("create-images")
    _add_context_arguments(create_image)
    create_image.add_argument("--output-dir", type=Path, required=True)
    create_image.add_argument("--web-digest", required=True)
    create_image.add_argument("--core-digest", required=True)
    create_image.add_argument("--agent-digest", required=True)
    create_image.add_argument("--execution-manifest-fingerprint", required=True)
    create_image.add_argument("--repository-root", type=Path, required=True)
    create_image.add_argument("--source-tree-manifest", type=Path, required=True)
    create_image.add_argument("--expected-source-tree-sha256", required=True)
    create_image.add_argument("--expected-build-definition-sha256", required=True)

    verify_image = actions.add_parser("verify-images")
    _add_verify_plan_arguments(verify_image)
    verify_image.add_argument("--images-dir", type=Path, required=True)
    verify_image.add_argument("--repository-root", type=Path, required=True)
    verify_image.add_argument("--source-tree-manifest", type=Path, required=True)
    verify_image.add_argument("--expected-source-tree-sha256", required=True)
    verify_image.add_argument("--expected-build-definition-sha256", required=True)

    prerequisites = actions.add_parser("verify-prerequisites")
    _add_context_arguments(prerequisites)
    prerequisites.add_argument("--variables-json", type=Path, required=True)
    prerequisites.add_argument("--images-dir", type=Path, required=True)
    prerequisites.add_argument("--control-bundle-dir", type=Path, required=True)
    prerequisites.add_argument("--qualification-dir", type=Path, required=True)
    prerequisites.add_argument("--qualification-run-json", type=Path, required=True)
    prerequisites.add_argument("--candidate-dir", type=Path, required=True)
    prerequisites.add_argument("--candidate-run-json", type=Path, required=True)
    prerequisites.add_argument("--repository-root", type=Path, required=True)
    prerequisites.add_argument("--source-tree-manifest", type=Path, required=True)
    prerequisites.add_argument("--expected-source-tree-sha256", required=True)

    local = actions.add_parser("assert-local-fault-boundary")
    local.add_argument(
        "--evidence-class",
        choices=("local-fake-prerequisite-only",),
        required=True,
    )

    create_plan = actions.add_parser("create-blocked-plan")
    _add_context_arguments(create_plan)
    create_plan.add_argument("--output-dir", type=Path, required=True)

    verify_plan = actions.add_parser("verify-blocked-plan")
    _add_verify_plan_arguments(verify_plan)
    verify_plan.add_argument("--plan-dir", type=Path, required=True)

    assert_blocked = actions.add_parser("assert-remote-blocked")
    _add_verify_plan_arguments(assert_blocked)
    assert_blocked.add_argument("--plan-dir", type=Path, required=True)

    unavailable = actions.add_parser("assert-remote-capabilities-unavailable")
    _add_context_arguments(unavailable)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.action == "verify-environment-policy":
            verify_environment_policy(
                environment_path=arguments.environment_json,
                branch_policies_path=arguments.branch_policies_json,
                secrets_path=arguments.secrets_json,
                variables_path=arguments.variables_json,
            )
            print("development-producer-policy-ok:development:main")
            return 0
        if arguments.action == "verify-checkout-bindings":
            variables = _policy_variables(load_github_document(arguments.variables_json))
            bindings = checkout_bindings(
                repository_root=arguments.repository_root,
                source_tree_manifest=arguments.source_tree_manifest,
                target_commit=arguments.target_release_commit,
                expected_build_definition_sha256=variables[
                    "DURABLE_AGENT_V2_DEVELOPMENT_BUILD_DEFINITION_SHA256"
                ],
                expected_source_tree_sha256=arguments.expected_source_tree_sha256,
            )
            print(
                "development-checkout-bindings-verified:"
                f"{bindings['sourceTreeSha256']}:"
                f"{bindings['buildDefinitionSha256']}"
            )
            return 0
        if arguments.action == "create-images":
            digest = create_images(arguments)
            print(f"development-images-created:{digest}")
            return 0
        if arguments.action == "verify-images":
            _, digest = verify_images(
                arguments.images_dir,
                expected_sha=arguments.expected_sha256,
                expected_repository=arguments.repository,
                expected_commit=arguments.target_release_commit,
                expected_run_id=arguments.run_id,
                expected_run_attempt=arguments.run_attempt,
                repository_root=arguments.repository_root,
                source_tree_manifest=arguments.source_tree_manifest,
                expected_source_tree_sha256=arguments.expected_source_tree_sha256,
                expected_build_definition_sha256=(arguments.expected_build_definition_sha256),
            )
            print(f"development-images-verified:{digest}")
            return 0
        if arguments.action == "verify-prerequisites":
            current = verify_prerequisites(arguments)
            print(
                "development-prerequisites-verified:"
                + canonical_bytes(current).decode("utf-8").rstrip("\n")
            )
            return 0
        if arguments.action == "assert-local-fault-boundary":
            print("development-local-fault-prerequisite-only")
            return 0
        if arguments.action == "create-blocked-plan":
            digest = create_blocked_plan(arguments)
            print(f"development-remote-plan-created:{digest}")
            return 0
        if arguments.action == "assert-remote-capabilities-unavailable":
            _producer(
                {
                    "headSha": arguments.target_release_commit,
                    "repository": arguments.repository,
                    "runAttempt": arguments.run_attempt,
                    "runId": arguments.run_id,
                    "workflowPath": DEVELOPMENT_WORKFLOW,
                },
                expected_repository=arguments.repository,
                expected_commit=arguments.target_release_commit,
                expected_run_id=arguments.run_id,
                expected_run_attempt=arguments.run_attempt,
            )
            raise ProducerInvalid(
                "remote driver、2C2G、provider identity 与 route-off cleanup 未实现"
            )
        digest = verify_blocked_plan(
            arguments.plan_dir,
            expected_sha=arguments.expected_sha256,
            expected_repository=arguments.repository,
            expected_commit=arguments.target_release_commit,
            expected_run_id=arguments.run_id,
            expected_run_attempt=arguments.run_attempt,
        )
        if arguments.action == "assert-remote-blocked":
            raise ProducerInvalid(
                "remote driver、2C2G、provider identity 与 route-off cleanup 未实现"
            )
        print(f"development-remote-plan-verified:{digest}")
        return 0
    except (
        BundleInvalid,
        EvidenceV2Invalid,
        OSError,
        PolicyInvalid,
        ProducerInvalid,
        ProvenanceInvalid,
    ) as error:
        print(f"development-producer-error:{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
