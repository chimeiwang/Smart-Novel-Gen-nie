#!/usr/bin/env python3
"""生产发布前复验 Durable Agent V2 开发证据的完整语义与来源。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, NoReturn

from durable_agent_v2_development_evidence_v2 import (
    EvidenceV2Invalid,
    _digest,
    _hex,
    _parse_trusted_now,
    _positive_decimal,
    verify_candidate_bundle,
    verify_qualification_bundle,
)
from durable_agent_v2_development_producer import (
    DEVELOPMENT_WORKFLOW,
    ProducerInvalid,
    _policy_variables,
    source_tree_sha256,
    verify_images,
)
from durable_agent_v2_release_manifest import ManifestError, repository_facts
from github_api_evidence import read_regular
from verify_github_environment_policy import PolicyInvalid
from verify_github_environment_policy import _load as load_github_document
from verify_github_workflow_run_provenance import (
    ProvenanceInvalid,
)
from verify_github_workflow_run_provenance import (
    verify as verify_run_provenance,
)

SNAPSHOT_KEYS = {
    "targetAgentDigest",
    "targetCoreDigest",
    "targetManifestFingerprint",
    "targetWebDigest",
}


class DevelopmentConsumerInvalid(ValueError):
    """开发证据不能授权生产发布。"""


def _fail(message: str) -> NoReturn:
    raise DevelopmentConsumerInvalid(message)


def _positive_attempt(value: str, label: str) -> str:
    attempt = _positive_decimal(value, label)
    if attempt != "1":
        _fail(f"{label} 只接受 runAttempt=1")
    return attempt


def _resolved_directory(path: Path, label: str) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        _fail(f"{label} 必须是绝对普通目录")
    resolved = path.resolve(strict=True)
    if resolved != path:
        _fail(f"{label} 必须是已解析目录")
    return resolved


def _read_snapshot(path: Path) -> dict[str, str]:
    try:
        payload = read_regular(
            path,
            "实际目标镜像 snapshot",
            error_type=DevelopmentConsumerInvalid,
            max_bytes=4096,
        ).decode("ascii")
    except UnicodeDecodeError as error:
        raise DevelopmentConsumerInvalid("实际目标镜像 snapshot 不是 ASCII") from error
    values: dict[str, str] = {}
    for line in payload.splitlines():
        if line.count("=") != 1:
            _fail("实际目标镜像 snapshot 格式无效")
        key, value = line.split("=", 1)
        if key not in SNAPSHOT_KEYS or key in values or not value:
            _fail("实际目标镜像 snapshot 字段无效")
        values[key] = value
    if set(values) != SNAPSHOT_KEYS:
        _fail("实际目标镜像 snapshot 字段不完整")
    for key in ("targetAgentDigest", "targetCoreDigest", "targetWebDigest"):
        _digest(values[key], key)
    _hex(
        values["targetManifestFingerprint"],
        64,
        "target execution manifest fingerprint",
    )
    return values


def _producer(
    *,
    repository: str,
    head_sha: str,
    run_id: str,
    run_attempt: str,
) -> dict[str, str]:
    return {
        "headSha": head_sha,
        "repository": repository,
        "runAttempt": run_attempt,
        "runId": run_id,
        "workflowPath": DEVELOPMENT_WORKFLOW,
    }


def _verify_completed_run(
    *,
    path: Path,
    repository: str,
    head_sha: str,
    run_id: str,
    run_attempt: str,
) -> None:
    verify_run_provenance(
        argparse.Namespace(
            run_json=path,
            expected_run_id=run_id,
            expected_head_sha=head_sha,
            expected_repository=repository,
            expected_workflow_path=DEVELOPMENT_WORKFLOW,
            expected_run_attempt=run_attempt,
        )
    )


def _expected_policies(variables: dict[str, str]) -> dict[str, Any]:
    return {
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
        "providerUsageCostPolicyVersion": "durable-agent-v2-provider-canary-budget/1",
        "resourcePerformancePolicySha256": variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_RESOURCE_POLICY_SHA256"
        ],
        "resourcePerformancePolicyVersion": "durable-agent-v2-resource-slo/1",
    }


def verify(arguments: argparse.Namespace) -> str:
    repository = arguments.expected_repository
    target_commit = _hex(arguments.expected_target_commit, 40, "预期 target commit")
    qualification_commit = _hex(
        arguments.qualification_source_commit,
        40,
        "qualification source commit",
    )
    candidate_run_id = _positive_decimal(arguments.candidate_run_id, "candidate run ID")
    candidate_attempt = _positive_attempt(
        arguments.candidate_run_attempt,
        "candidate producer run attempt",
    )
    qualification_run_id = _positive_decimal(
        arguments.qualification_run_id,
        "qualification run ID",
    )
    qualification_attempt = _positive_attempt(
        arguments.qualification_run_attempt,
        "qualification producer run attempt",
    )

    variables = _policy_variables(load_github_document(arguments.variables_json))
    now = _parse_trusted_now(arguments.trusted_now)
    snapshot = _read_snapshot(arguments.target_images_snapshot)
    actual_images = {
        "agent": snapshot["targetAgentDigest"],
        "core": snapshot["targetCoreDigest"],
        "web": snapshot["targetWebDigest"],
    }
    execution_fingerprint = variables[
        "DURABLE_AGENT_V2_DEVELOPMENT_EXECUTION_MANIFEST_FINGERPRINT"
    ]
    if snapshot["targetManifestFingerprint"] != execution_fingerprint:
        _fail("实际 execution manifest fingerprint 与受保护期望不一致")

    _verify_completed_run(
        path=arguments.candidate_run_json,
        repository=repository,
        head_sha=target_commit,
        run_id=candidate_run_id,
        run_attempt=candidate_attempt,
    )
    _verify_completed_run(
        path=arguments.qualification_run_json,
        repository=repository,
        head_sha=qualification_commit,
        run_id=qualification_run_id,
        run_attempt=qualification_attempt,
    )

    expected_source_tree_sha = source_tree_sha256(
        arguments.source_tree_manifest,
        target_commit=target_commit,
    )
    image_document, image_sha = verify_images(
        arguments.images_dir,
        expected_sha=None,
        expected_repository=repository,
        expected_commit=target_commit,
        expected_run_id=candidate_run_id,
        expected_run_attempt=candidate_attempt,
        repository_root=arguments.repository_root,
        source_tree_manifest=arguments.source_tree_manifest,
        expected_source_tree_sha256=expected_source_tree_sha,
        expected_build_definition_sha256=variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_BUILD_DEFINITION_SHA256"
        ],
    )
    if image_document["images"] != actual_images:
        _fail("development image provenance 与实际目标镜像不一致")
    if image_document["executionManifestFingerprint"] != execution_fingerprint:
        _fail("development image provenance execution fingerprint 不一致")

    facts = repository_facts(
        _resolved_directory(
            arguments.qualification_source_root,
            "qualification source root",
        )
    )
    expected_qualification_producer = _producer(
        repository=repository,
        head_sha=qualification_commit,
        run_id=qualification_run_id,
        run_attempt=qualification_attempt,
    )
    qualification_sha = variables[
        "DURABLE_AGENT_V2_DEVELOPMENT_MIGRATION_QUALIFICATION_SHA256"
    ]
    verify_qualification_bundle(
        arguments.qualification_dir,
        now=now,
        expected_sha=qualification_sha,
        expected_producer=expected_qualification_producer,
        expected_development_scope=variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_DEVELOPMENT_SCOPE_SHA256"
        ],
        expected_migration={
            "forwardSqlSha256": facts["forwardSqlSha256"],
            "migrationSourceCommit": qualification_commit,
            "postContractFingerprint": facts["postContractFingerprint"],
            "preContractFingerprint": facts["preContractFingerprint"],
            "rollbackSqlSha256": facts["rollbackSqlSha256"],
        },
    )

    expected_candidate_producer = _producer(
        repository=repository,
        head_sha=target_commit,
        run_id=candidate_run_id,
        run_attempt=candidate_attempt,
    )
    _, candidate_sha = verify_candidate_bundle(
        arguments.candidate_dir,
        qualification_directory=arguments.qualification_dir,
        now=now,
        expected_sha=None,
        expected_producer=expected_candidate_producer,
        expected_target_commit=target_commit,
        expected_development_scope=variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_DEVELOPMENT_SCOPE_SHA256"
        ],
        expected_scenario=variables[
            "DURABLE_AGENT_V2_DEVELOPMENT_CANARY_SCENARIO_FINGERPRINT"
        ],
        expected_execution_fingerprint=execution_fingerprint,
        expected_images=actual_images,
        expected_policies=_expected_policies(variables),
        expected_subjects={
            "providerIdentitySha256": variables[
                "DURABLE_AGENT_V2_DEVELOPMENT_PROVIDER_IDENTITY_SHA256"
            ],
            "resourceHostIdentitySha256": variables[
                "DURABLE_AGENT_V2_DEVELOPMENT_RESOURCE_HOST_IDENTITY_SHA256"
            ],
        },
        expected_qualification_sha=qualification_sha,
    )
    if len({candidate_sha, image_sha, qualification_sha}) != 3:
        _fail("candidate/image/qualification artifact SHA 不得复用")
    return f"{candidate_sha}:{image_sha}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--candidate-run-json", type=Path, required=True)
    parser.add_argument("--candidate-run-id", required=True)
    parser.add_argument("--candidate-run-attempt", required=True)
    parser.add_argument("--qualification-dir", type=Path, required=True)
    parser.add_argument("--qualification-run-json", type=Path, required=True)
    parser.add_argument("--qualification-run-id", required=True)
    parser.add_argument("--qualification-run-attempt", required=True)
    parser.add_argument("--qualification-source-root", type=Path, required=True)
    parser.add_argument("--qualification-source-commit", required=True)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--target-images-snapshot", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--source-tree-manifest", type=Path, required=True)
    parser.add_argument("--variables-json", type=Path, required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-target-commit", required=True)
    parser.add_argument("--trusted-now")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        evidence_identity = verify(arguments)
    except (
        DevelopmentConsumerInvalid,
        EvidenceV2Invalid,
        ManifestError,
        OSError,
        PolicyInvalid,
        ProducerInvalid,
        ProvenanceInvalid,
    ) as error:
        print(f"development-v2-consumer:error:{error}", file=sys.stderr)
        return 1
    print(f"development-v2-consumer-ok:{evidence_identity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
