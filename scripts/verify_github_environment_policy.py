#!/usr/bin/env python3
"""复验 GitHub environment 的外部审批与部署分支策略。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

MAX_RESPONSE_BYTES = 1_048_576
NEW_RELEASE_SSH_SECRET = "DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY"  # noqa: S105
RETIRED_RELEASE_SSH_SECRET = "SERVER_SSH_KEY"  # noqa: S105
REQUIRED_ATTESTATION_VARIABLES = {
    "DURABLE_AGENT_V2_RELEASE_OLD_KEY_REVOCATION_EVIDENCE_SHA256",
    "DURABLE_AGENT_V2_RELEASE_FORCED_COMMAND_EVIDENCE_SHA256",
    "DURABLE_AGENT_V2_RELEASE_MINIMUM_PERMISSION_EVIDENCE_SHA256",
}


class PolicyInvalid(ValueError):
    """GitHub environment 策略不能证明生产发布边界。"""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyInvalid(f"JSON 存在重复 key：{key}")
        result[key] = value
    return result


def _load(path: Path) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            raise PolicyInvalid("API 响应必须是普通文件")
        if path.stat().st_size > MAX_RESPONSE_BYTES:
            raise PolicyInvalid("API 响应超过大小上限")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda raw: (_ for _ in ()).throw(
                PolicyInvalid(f"JSON 包含非法数字：{raw}")
            ),
        )
    except PolicyInvalid:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PolicyInvalid("API 响应不是有效 UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise PolicyInvalid("API 响应顶层必须是对象")
    return value


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyInvalid(f"{label} 必须是布尔值")
    return value


def verify(
    environment: dict[str, Any],
    policies: dict[str, Any],
    *,
    expected_environment: str,
    expected_branch: str,
) -> None:
    if environment.get("name") != expected_environment:
        raise PolicyInvalid("environment 名称不一致")

    deployment_policy = environment.get("deployment_branch_policy")
    if not isinstance(deployment_policy, dict):
        raise PolicyInvalid("缺少 deployment branch policy")
    protected = _require_bool(
        deployment_policy.get("protected_branches"), "protected_branches"
    )
    custom = _require_bool(
        deployment_policy.get("custom_branch_policies"),
        "custom_branch_policies",
    )
    if protected or not custom:
        raise PolicyInvalid("production 必须只使用自定义部署分支策略")

    rules = environment.get("protection_rules")
    if not isinstance(rules, list):
        raise PolicyInvalid("缺少 environment protection rules")
    reviewer_rules = [
        rule
        for rule in rules
        if isinstance(rule, dict) and rule.get("type") == "required_reviewers"
    ]
    if len(reviewer_rules) != 1:
        raise PolicyInvalid("required reviewers 规则必须且只能有一条")
    reviewer_rule = reviewer_rules[0]
    if reviewer_rule.get("prevent_self_review") is not True:
        raise PolicyInvalid("production 必须禁止发起人自审")
    reviewers = reviewer_rule.get("reviewers")
    if not isinstance(reviewers, list) or not reviewers:
        raise PolicyInvalid("production 至少需要一名 required reviewer")
    for reviewer in reviewers:
        if (
            not isinstance(reviewer, dict)
            or reviewer.get("type") not in {"User", "Team"}
            or not isinstance(reviewer.get("reviewer"), dict)
            or not reviewer["reviewer"].get("id")
        ):
            raise PolicyInvalid("required reviewer 身份无效")

    total = policies.get("total_count")
    branch_policies = policies.get("branch_policies")
    if (
        isinstance(total, bool)
        or not isinstance(total, int)
        or not isinstance(branch_policies, list)
        or total != len(branch_policies)
    ):
        raise PolicyInvalid("部署分支策略分页或计数不完整")
    names = [
        policy.get("name") if isinstance(policy, dict) else None
        for policy in branch_policies
    ]
    if total != 1 or names != [expected_branch]:
        raise PolicyInvalid("production 部署分支策略必须精确只允许 main")


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
        raise PolicyInvalid(f"{label} 分页或计数不完整")
    return items


def verify_release_ssh_identity(
    secrets: dict[str, Any],
    variables: dict[str, Any],
) -> None:
    secret_items = _paged_items(
        secrets,
        collection_key="secrets",
        label="environment secrets",
    )
    secret_names = [item.get("name") for item in secret_items]
    if any(not isinstance(name, str) or not name for name in secret_names):
        raise PolicyInvalid("environment secret 名称无效")
    if len(secret_names) != len(set(secret_names)):
        raise PolicyInvalid("environment secret 名称重复")
    if RETIRED_RELEASE_SSH_SECRET in secret_names:
        raise PolicyInvalid("旧 SERVER_SSH_KEY 尚未删除")
    if NEW_RELEASE_SSH_SECRET not in secret_names:
        raise PolicyInvalid("缺少 Durable Agent V2 专用 SSH secret")

    variable_items = _paged_items(
        variables,
        collection_key="variables",
        label="environment variables",
    )
    actual_variables: dict[str, str] = {}
    for item in variable_items:
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or not isinstance(value, str) or name in actual_variables:
            raise PolicyInvalid("environment variable 身份无效或重复")
        actual_variables[name] = value
    attestation_hashes: list[str] = []
    for name in REQUIRED_ATTESTATION_VARIABLES:
        value = actual_variables.get(name)
        if (
            value is None
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            or value == "0" * 64
        ):
            raise PolicyInvalid(f"缺少或无效的 SSH 外部证据 hash：{name}")
        attestation_hashes.append(value)
    if len(set(attestation_hashes)) != len(attestation_hashes):
        raise PolicyInvalid("SSH 外部证据 hash 不得复用")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment-json", type=Path, required=True)
    parser.add_argument("--branch-policies-json", type=Path, required=True)
    parser.add_argument("--secrets-json", type=Path, required=True)
    parser.add_argument("--variables-json", type=Path, required=True)
    parser.add_argument("--expected-environment", default="production")
    parser.add_argument("--expected-branch", default="main")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        verify(
            _load(arguments.environment_json),
            _load(arguments.branch_policies_json),
            expected_environment=arguments.expected_environment,
            expected_branch=arguments.expected_branch,
        )
        verify_release_ssh_identity(
            _load(arguments.secrets_json),
            _load(arguments.variables_json),
        )
    except PolicyInvalid as error:
        print(f"github-environment-policy:error:{error}", file=sys.stderr)
        return 1
    print("github-environment-policy-ok:production:main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
