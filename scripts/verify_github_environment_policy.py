#!/usr/bin/env python3
"""复验 GitHub environment 的外部审批与部署分支策略。"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from github_api_evidence import read_regular

MAX_PAGES = 100
MAX_PAGE_ITEMS = 100
MAX_TOTAL_ITEMS = MAX_PAGES * MAX_PAGE_ITEMS
MAX_PAGED_RESPONSE_BYTES = 8 * 1_048_576
ORGANIZATION_INVENTORY_FORMAT = "inkforge-github-organization-secret-inventory/1"
ACTIVE_RELEASE_SSH_SECRETS = {
    "DURABLE_AGENT_V2_RELEASE_EXECUTION_SSH_PRIVATE_KEY",  # noqa: S105
    "DURABLE_AGENT_V2_RELEASE_UPLOAD_SSH_PRIVATE_KEY",  # noqa: S105
}
KNOWN_HOSTS_SECRET = "DURABLE_AGENT_V2_RELEASE_SSH_KNOWN_HOSTS"  # noqa: S105
AUDIT_TOKEN_SECRET = "GH_ENVIRONMENT_POLICY_AUDIT_TOKEN"  # noqa: S105
RETIRED_RELEASE_SSH_SECRETS = {
    "DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY",  # noqa: S105
    "SERVER_SSH_KEY",  # noqa: S105
}
DIAGNOSTIC_ATTESTATION_VARIABLES = {
    "DURABLE_AGENT_V2_RELEASE_OLD_KEY_REVOCATION_EVIDENCE_SHA256",
    "DURABLE_AGENT_V2_RELEASE_FORCED_COMMAND_EVIDENCE_SHA256",
    "DURABLE_AGENT_V2_RELEASE_MINIMUM_PERMISSION_EVIDENCE_SHA256",
}
SERVER_HOST_VARIABLE = "DURABLE_AGENT_V2_RELEASE_SERVER_HOST"
SERVER_PORT_VARIABLE = "DURABLE_AGENT_V2_RELEASE_SERVER_PORT"
SERVER_USER_VARIABLE = "DURABLE_AGENT_V2_RELEASE_SERVER_USER"
HOST_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}\Z")
USER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}\Z")


class PolicyInvalid(ValueError):
    """GitHub environment 策略不能证明生产发布边界。"""


@dataclass(frozen=True)
class ReleaseSshSubject:
    host: str
    port: int
    user: str


@dataclass(frozen=True)
class RepositoryOwner:
    login: str
    kind: str


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyInvalid(f"JSON 存在重复 key：{key}")
        result[key] = value
    return result


def _decode(payload: bytes, label: str) -> Any:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=lambda _raw: (_ for _ in ()).throw(
                PolicyInvalid(f"{label} 禁止浮点数")
            ),
            parse_constant=lambda raw: (_ for _ in ()).throw(
                PolicyInvalid(f"{label} 包含非法数字：{raw}")
            ),
        )
    except PolicyInvalid:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PolicyInvalid(f"{label} 不是有效 UTF-8 JSON") from error
    return value


def _load_value(path: Path, label: str, *, max_bytes: int = 1_048_576) -> Any:
    return _decode(
        read_regular(path, label, error_type=PolicyInvalid, max_bytes=max_bytes),
        label,
    )


def _load(path: Path, label: str = "API 响应") -> dict[str, Any]:
    value = _load_value(path, label)
    if not isinstance(value, dict):
        raise PolicyInvalid(f"{label} 顶层必须是对象")
    return value


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


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyInvalid(f"{label} 必须是布尔值")
    return value


def _repository_owner(
    repository: dict[str, Any], *, expected_repository: str
) -> RepositoryOwner:
    parts = expected_repository.split("/")
    if len(parts) != 2 or any(not part or part in {".", ".."} for part in parts):
        raise PolicyInvalid("expected repository 格式无效")
    owner_login, _repository_name = parts
    if repository.get("full_name") != expected_repository:
        raise PolicyInvalid("repository full_name 不一致")
    owner = repository.get("owner")
    if not isinstance(owner, dict):
        raise PolicyInvalid("repository owner 缺失")
    login = owner.get("login")
    kind = owner.get("type")
    if login != owner_login or kind not in {"User", "Organization"}:
        raise PolicyInvalid("repository owner login/type 无效")
    return RepositoryOwner(login=login, kind=kind)


def _merge_pages(path: Path, *, collection_key: str, label: str) -> dict[str, Any]:
    pages = _load_value(path, label, max_bytes=MAX_PAGED_RESPONSE_BYTES)
    if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES:
        raise PolicyInvalid(f"{label} 页数无效")
    expected_total: int | None = None
    merged: list[dict[str, Any]] = []
    identities: set[str] = set()
    for page in pages:
        if not isinstance(page, dict):
            raise PolicyInvalid(f"{label} 页面必须是对象")
        total = page.get("total_count")
        items = page.get(collection_key)
        if (
            isinstance(total, bool)
            or not isinstance(total, int)
            or total < 0
            or total > MAX_TOTAL_ITEMS
            or not isinstance(items, list)
            or len(items) > MAX_PAGE_ITEMS
            or any(not isinstance(item, dict) for item in items)
        ):
            raise PolicyInvalid(f"{label} 页面计数或条目无效")
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise PolicyInvalid(f"{label} 跨页 total_count 漂移")
        for item in items:
            name = item.get("name")
            if not isinstance(name, str) or not name or name in identities:
                raise PolicyInvalid(f"{label} 名称无效或跨页重复")
            identities.add(name)
            merged.append(item)
    if expected_total is None or expected_total != len(merged):
        raise PolicyInvalid(f"{label} 分页或计数不完整")
    merged.sort(key=lambda item: str(item["name"]))
    return {collection_key: merged, "total_count": expected_total}


def _write_canonical_output(directory: Path, name: str, document: dict[str, Any]) -> None:
    directory_stat = directory.stat() if directory.exists() else None
    if (
        not directory.is_absolute()
        or directory.is_symlink()
        or not directory.is_dir()
        or directory_stat is None
        or directory_stat.st_uid != os.geteuid()
        or stat.S_IMODE(directory_stat.st_mode) & 0o077
    ):
        raise PolicyInvalid("canonical API evidence 输出目录无效")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise PolicyInvalid("当前平台缺少 O_NOFOLLOW，拒绝写入 canonical API evidence")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(directory / name, flags, 0o600)
    except OSError as error:
        raise PolicyInvalid(f"无法安全创建 canonical API evidence：{name}") from error
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(_canonical(document))
            target.flush()
            os.fsync(target.fileno())
    except OSError as error:
        raise PolicyInvalid(f"无法稳定写入 canonical API evidence：{name}") from error


def normalize_pages(arguments: argparse.Namespace) -> RepositoryOwner:
    repository = _load(arguments.repository_json, "repository metadata")
    owner = _repository_owner(repository, expected_repository=arguments.expected_repository)
    outputs = {
        "branch-policies.json": _merge_pages(
            arguments.branch_policies_pages_json,
            collection_key="branch_policies",
            label="deployment branch policies",
        ),
        "environment-secrets.json": _merge_pages(
            arguments.environment_secrets_pages_json,
            collection_key="secrets",
            label="environment secrets",
        ),
        "repository-secrets.json": _merge_pages(
            arguments.repository_secrets_pages_json,
            collection_key="secrets",
            label="repository secrets",
        ),
        "variables.json": _merge_pages(
            arguments.variables_pages_json,
            collection_key="variables",
            label="environment variables",
        ),
    }
    organization_pages = arguments.organization_secrets_pages_json
    if owner.kind == "Organization":
        if organization_pages is None:
            raise PolicyInvalid("Organization owner 缺少 organization secret 分页")
        organization = _merge_pages(
            organization_pages,
            collection_key="secrets",
            label="organization secrets",
        )
    else:
        if organization_pages is not None:
            raise PolicyInvalid("User owner 不得伪造 organization secret 分页")
        organization = {"secrets": [], "total_count": 0}
    outputs["organization-secrets.json"] = {
        "format": ORGANIZATION_INVENTORY_FORMAT,
        "owner": {"login": owner.login, "type": owner.kind},
        **organization,
    }
    for name, document in outputs.items():
        _write_canonical_output(arguments.output_directory, name, document)
    return owner


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


def _secret_names(document: dict[str, Any], label: str) -> set[str]:
    items = _paged_items(
        document,
        collection_key="secrets",
        label=label,
    )
    secret_names: list[str] = []
    for item in items:
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise PolicyInvalid(f"{label} 名称无效")
        secret_names.append(name)
    if len(secret_names) != len(set(secret_names)):
        raise PolicyInvalid(f"{label} 名称重复")
    return set(secret_names)


def _organization_secret_names(
    document: dict[str, Any], owner: RepositoryOwner
) -> set[str]:
    if set(document) != {"format", "owner", "secrets", "total_count"}:
        raise PolicyInvalid("organization secret inventory 字段无效")
    if document.get("format") != ORGANIZATION_INVENTORY_FORMAT:
        raise PolicyInvalid("organization secret inventory format 无效")
    expected_owner = {"login": owner.login, "type": owner.kind}
    if document.get("owner") != expected_owner:
        raise PolicyInvalid("organization secret inventory owner 漂移")
    names = _secret_names(document, "organization secrets")
    if owner.kind == "User" and names:
        raise PolicyInvalid("User owner 的 organization secret scope 必须不存在")
    return names


def verify_release_ssh_identity(
    repository: dict[str, Any],
    environment_secrets: dict[str, Any],
    repository_secrets: dict[str, Any],
    organization_secrets: dict[str, Any],
    variables: dict[str, Any],
    *,
    expected_repository: str,
) -> ReleaseSshSubject:
    owner = _repository_owner(repository, expected_repository=expected_repository)
    environment_names = _secret_names(environment_secrets, "environment secrets")
    repository_names = _secret_names(repository_secrets, "repository secrets")
    organization_names = _organization_secret_names(organization_secrets, owner)
    environment_only = ACTIVE_RELEASE_SSH_SECRETS | {
        KNOWN_HOSTS_SECRET,
        AUDIT_TOKEN_SECRET,
    }
    if not environment_only.issubset(environment_names):
        raise PolicyInvalid("production environment 缺少双角色 SSH key、known_hosts 或审计 token")
    for scope, names in (
        ("environment", environment_names),
        ("repository", repository_names),
        ("organization", organization_names),
    ):
        if names.intersection(RETIRED_RELEASE_SSH_SECRETS):
            raise PolicyInvalid(f"{scope} scope 仍包含 retired release SSH secret")
    for scope, names in (
        ("repository", repository_names),
        ("organization", organization_names),
    ):
        if names.intersection(environment_only):
            raise PolicyInvalid(f"{scope} scope 不得包含 production release 或审计 secret")

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
    host = actual_variables.get(SERVER_HOST_VARIABLE)
    port_raw = actual_variables.get(SERVER_PORT_VARIABLE)
    user = actual_variables.get(SERVER_USER_VARIABLE)
    if not isinstance(host, str) or HOST_PATTERN.fullmatch(host) is None:
        raise PolicyInvalid("release server host variable 无效")
    if (
        not isinstance(port_raw, str)
        or not port_raw.isascii()
        or not port_raw.isdecimal()
        or port_raw.startswith("0")
    ):
        raise PolicyInvalid("release server port variable 无效")
    port = int(port_raw)
    if not 1 <= port <= 65_535:
        raise PolicyInvalid("release server port variable 超出范围")
    if not isinstance(user, str) or USER_PATTERN.fullmatch(user) is None:
        raise PolicyInvalid("release server user variable 无效")

    # 三个旧 hash 只保留为可选诊断；它们不再参与授权，也不能替代 semantic artifact。
    for name in DIAGNOSTIC_ATTESTATION_VARIABLES:
        value = actual_variables.get(name)
        if value is not None and (
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise PolicyInvalid(f"可选 SSH 诊断 hash 格式无效：{name}")
    return ReleaseSshSubject(host=host, port=port, user=user)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-json", type=Path, required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--environment-json", type=Path, required=True)
    parser.add_argument("--branch-policies-json", type=Path, required=True)
    parser.add_argument("--secrets-json", type=Path, required=True)
    parser.add_argument("--repository-secrets-json", type=Path, required=True)
    parser.add_argument("--organization-secrets-json", type=Path, required=True)
    parser.add_argument("--variables-json", type=Path, required=True)
    parser.add_argument("--expected-environment", default="production")
    parser.add_argument("--expected-branch", default="main")
    return parser


def _normalize_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-json", type=Path, required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--branch-policies-pages-json", type=Path, required=True)
    parser.add_argument("--environment-secrets-pages-json", type=Path, required=True)
    parser.add_argument("--repository-secrets-pages-json", type=Path, required=True)
    parser.add_argument("--organization-secrets-pages-json", type=Path)
    parser.add_argument("--variables-pages-json", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "normalize-pages":
        arguments = _normalize_parser().parse_args(sys.argv[2:])
        try:
            owner = normalize_pages(arguments)
        except PolicyInvalid as error:
            print(f"github-environment-policy:error:{error}", file=sys.stderr)
            return 1
        print(f"github-api-evidence-normalized:{owner.kind}:{owner.login}")
        return 0
    arguments = _parser().parse_args()
    try:
        verify(
            _load(arguments.environment_json, "environment API response"),
            _load(arguments.branch_policies_json, "branch policy API response"),
            expected_environment=arguments.expected_environment,
            expected_branch=arguments.expected_branch,
        )
        subject = verify_release_ssh_identity(
            _load(arguments.repository_json, "repository metadata"),
            _load(arguments.secrets_json, "environment secret inventory"),
            _load(arguments.repository_secrets_json, "repository secret inventory"),
            _load(arguments.organization_secrets_json, "organization secret inventory"),
            _load(arguments.variables_json, "environment variable inventory"),
            expected_repository=arguments.expected_repository,
        )
    except PolicyInvalid as error:
        print(f"github-environment-policy:error:{error}", file=sys.stderr)
        return 1
    print("github-environment-policy-ok:production:main")
    print(f"releaseServerHost={subject.host}")
    print(f"releaseServerPort={subject.port}")
    print(f"releaseServerUser={subject.user}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
