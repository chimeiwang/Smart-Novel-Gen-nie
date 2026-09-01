#!/usr/bin/env python3
"""离线验证 Durable Agent 发布 SSH broker 的固定请求与 allowlist。

本模块故意不执行任何系统命令。真实 forced-command、流式上传和固定程序
dispatcher 尚未接入前，它只生成可审计的 dispatch plan，确保协议本身不能
携带 shell、argv、cwd 或任意环境变量名。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUEST_FORMAT = "inkforge-release-broker-request/1"
PLAN_FORMAT = "inkforge-release-broker-dispatch-plan/1"
POLICY_FORMAT = "inkforge-release-broker-policy/1"
ORIGINAL_COMMAND = "inkforge-release-broker/1"
MAX_REQUEST_BYTES = 65_536

HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
POSITIVE_DECIMAL = re.compile(r"[1-9][0-9]{0,19}\Z")


class BrokerInvalid(ValueError):
    """broker 请求不在固定协议和 allowlist 内。"""


Validator = Callable[[Any, str], Any]


@dataclass(frozen=True)
class Operation:
    role: str
    program: str
    argv: tuple[str, ...]
    fields: dict[str, Validator]


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


def _hex40(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX_40.fullmatch(value) is None:
        raise BrokerInvalid(f"{label} 必须是 40 位小写十六进制")
    return value


def _hex64(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX_64.fullmatch(value) is None:
        raise BrokerInvalid(f"{label} 必须是 64 位小写十六进制")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise BrokerInvalid(f"{label} 必须是不可变 sha256 digest")
    _hex64(value.removeprefix("sha256:"), label)
    return value


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise BrokerInvalid(f"{label} 包含不允许的字符")
    return value


def _decimal(value: Any, label: str) -> str:
    if not isinstance(value, str) or POSITIVE_DECIMAL.fullmatch(value) is None:
        raise BrokerInvalid(f"{label} 必须是正十进制字符串")
    return value


def _byte_length(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 8_589_934_592:
        raise BrokerInvalid(f"{label} 超出固定上传上限")
    return int(value)


def _route(value: Any, label: str) -> str:
    if value not in {"off", "allowlist"}:
        raise BrokerInvalid(f"{label} 无效")
    return str(value)


def _off_route(value: Any, label: str) -> str:
    if value != "off":
        raise BrokerInvalid(f"{label} 必须精确为 off")
    return str(value)


def _release_action(value: Any, label: str) -> str:
    if value not in {"route_off_release", "allowlist_release", "rollback"}:
        raise BrokerInvalid(f"{label} 无效")
    return str(value)


def _database(value: Any, label: str) -> str:
    if value != "novelwriter":
        raise BrokerInvalid(f"{label} 只允许 novelwriter")
    return str(value)


def _service(value: Any, label: str) -> str:
    if value not in {"web", "core", "agent"}:
        raise BrokerInvalid(f"{label} 无效")
    return str(value)


COMMON_EXECUTION_FIELDS: dict[str, Validator] = {
    "controlBundleSha256": _hex64,
    "lockId": _hex64,
    "manifestSha256": _hex64,
    "releaseAction": _release_action,
    "runAttempt": _decimal,
    "runId": _decimal,
    "targetReleaseCommit": _hex40,
    "workflowTrustedCommit": _hex40,
}


def _execution(
    action: str,
    *extra: tuple[str, Validator],
    program: str = "release-driver",
) -> Operation:
    fields = dict(COMMON_EXECUTION_FIELDS)
    fields.update(dict(extra))
    return Operation("execution", program, (action,), fields)


OPERATIONS: dict[str, Operation] = {
    "put_control_bundle": Operation(
        "upload",
        "content-addressed-upload-sink",
        ("put-control-bundle",),
        {
            "bundleSha256": _hex64,
            "byteLength": _byte_length,
            "runAttempt": _decimal,
            "runId": _decimal,
            "targetReleaseCommit": _hex40,
            "workflowTrustedCommit": _hex40,
        },
    ),
    "put_release_manifest": Operation(
        "upload",
        "content-addressed-upload-sink",
        ("put-release-manifest",),
        {
            "byteLength": _byte_length,
            "manifestSha256": _hex64,
            "runAttempt": _decimal,
            "runId": _decimal,
            "targetReleaseCommit": _hex40,
        },
    ),
    "put_deploy_bundle": Operation(
        "upload",
        "content-addressed-upload-sink",
        ("put-deploy-bundle",),
        {
            "byteLength": _byte_length,
            "deployCommit": _hex40,
            "payloadSha256": _hex64,
            "runAttempt": _decimal,
            "runId": _decimal,
        },
    ),
    "put_image_archive": Operation(
        "upload",
        "content-addressed-upload-sink",
        ("put-image-archive",),
        {
            "byteLength": _byte_length,
            "imageDigest": _digest,
            "payloadSha256": _hex64,
            "runAttempt": _decimal,
            "runId": _decimal,
            "service": _service,
            "targetReleaseCommit": _hex40,
        },
    ),
    "begin_snapshot": _execution(
        "begin-snapshot",
        ("canaryScopeSha256", _hex64),
        ("routeMode", _route),
    ),
    "begin_rollback": _execution(
        "begin-rollback",
        ("rollbackSourceReleaseCommit", _hex40),
    ),
    "transition_route_off": _execution(
        "transition-runtime-config",
        ("canaryNovelId", _safe_id),
        ("canaryUserId", _safe_id),
        ("routeMode", _off_route),
    ),
    "prepare_release": _execution("prepare-release"),
    "deploy_release": _execution(
        "deploy-release",
        ("deployCommit", _hex40),
        ("verifiedDrainSha256", _hex64),
        program="deploy-driver",
    ),
    "release_database": _execution(
        "release-database",
        ("database", _database),
        ("verifiedDrainSha256", _hex64),
    ),
    "finalize_allowlist": _execution(
        "finalize-allowlist-transaction",
        ("canaryNovelId", _safe_id),
        ("canaryUserId", _safe_id),
        ("verifiedDrainSha256", _hex64),
    ),
    "rollback_postflight": _execution("rollback-postflight", ("verifiedDrainSha256", _hex64)),
    "transaction_postflight": _execution("transaction-postflight", ("verifiedDrainSha256", _hex64)),
    "commit_transaction": _execution("commit-transaction", ("verifiedDrainSha256", _hex64)),
    "mark_transaction_failed": _execution("mark-transaction-failed"),
    "cleanup_failed_transaction": _execution(
        "cleanup-failed-transaction", ("cleanupConfirm", _safe_id)
    ),
    "transaction_status": _execution("transaction-status"),
}

OPERATION_ACTIONS: dict[str, frozenset[str]] = {
    "begin_snapshot": frozenset({"route_off_release", "allowlist_release"}),
    "begin_rollback": frozenset({"rollback"}),
    "transition_route_off": frozenset({"route_off_release", "allowlist_release", "rollback"}),
    "prepare_release": frozenset({"route_off_release", "allowlist_release", "rollback"}),
    "deploy_release": frozenset({"route_off_release", "allowlist_release", "rollback"}),
    "release_database": frozenset({"route_off_release"}),
    "finalize_allowlist": frozenset({"allowlist_release"}),
    "rollback_postflight": frozenset({"rollback"}),
    "transaction_postflight": frozenset({"route_off_release", "allowlist_release", "rollback"}),
    "commit_transaction": frozenset({"route_off_release", "allowlist_release", "rollback"}),
    "mark_transaction_failed": frozenset({"route_off_release", "allowlist_release", "rollback"}),
    "cleanup_failed_transaction": frozenset({"route_off_release", "allowlist_release", "rollback"}),
    "transaction_status": frozenset({"route_off_release", "allowlist_release", "rollback"}),
}


def policy_document() -> dict[str, Any]:
    roles = {
        role: sorted(name for name, operation in OPERATIONS.items() if operation.role == role)
        for role in ("execution", "upload")
    }
    return {
        "format": POLICY_FORMAT,
        "originalCommand": ORIGINAL_COMMAND,
        "requestFormat": REQUEST_FORMAT,
        "restrictions": {
            "agentForwarding": False,
            "arbitraryArgv": False,
            "arbitraryEnvironment": False,
            "shell": False,
            "tcpForwarding": False,
            "tty": False,
            "userRc": False,
            "x11Forwarding": False,
        },
        "roles": roles,
    }


def policy_sha256() -> str:
    return hashlib.sha256(_canonical(policy_document())).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BrokerInvalid(f"broker JSON key 重复：{key}")
        result[key] = value
    return result


def load_request(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise BrokerInvalid("broker 请求必须是普通文件")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise BrokerInvalid("broker 请求文件权限必须禁止 group/other")
    payload = path.read_bytes()
    if not payload or len(payload) > MAX_REQUEST_BYTES:
        raise BrokerInvalid("broker 请求大小无效")
    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=lambda _raw: (_ for _ in ()).throw(BrokerInvalid("broker 请求禁止浮点")),
            parse_constant=lambda raw: (_ for _ in ()).throw(
                BrokerInvalid(f"broker 请求包含非法数字：{raw}")
            ),
        )
    except BrokerInvalid:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise BrokerInvalid("broker 请求不是有效 UTF-8 JSON") from error
    if not isinstance(document, dict) or set(document) != {
        "format",
        "operation",
        "payload",
    }:
        raise BrokerInvalid("broker 请求顶层字段无效")
    if payload != _canonical(document):
        raise BrokerInvalid("broker 请求不是 canonical JSON")
    return document, payload


def dispatch_plan(*, role: str, original_command: str, request_path: Path) -> dict[str, Any]:
    if role not in {"execution", "upload"}:
        raise BrokerInvalid("broker role 无效")
    if original_command != ORIGINAL_COMMAND:
        raise BrokerInvalid("SSH_ORIGINAL_COMMAND 不匹配固定协议")
    document, request_payload = load_request(request_path)
    if document["format"] != REQUEST_FORMAT:
        raise BrokerInvalid("broker request format 无效")
    operation_name = document["operation"]
    if not isinstance(operation_name, str) or operation_name not in OPERATIONS:
        raise BrokerInvalid("broker operation 不在 allowlist")
    operation = OPERATIONS[operation_name]
    if operation.role != role:
        raise BrokerInvalid("broker operation 不属于当前 key role")
    payload = document["payload"]
    if not isinstance(payload, dict) or set(payload) != set(operation.fields):
        raise BrokerInvalid("broker operation payload 字段无效")
    normalized: dict[str, Any] = {}
    for name, validator in operation.fields.items():
        normalized[name] = validator(payload[name], name)
    if normalized != payload:
        raise BrokerInvalid("broker payload 规范化后漂移")
    allowed_actions = OPERATION_ACTIONS.get(operation_name)
    if allowed_actions is not None and normalized["releaseAction"] not in allowed_actions:
        raise BrokerInvalid("broker operation 与 releaseAction 不匹配")
    if (
        operation_name == "cleanup_failed_transaction"
        and normalized["cleanupConfirm"] != f"cleanup-failed-release:{normalized['lockId']}"
    ):
        raise BrokerInvalid("cleanup confirm 未绑定精确 lock ID")
    return {
        "argv": list(operation.argv),
        "format": PLAN_FORMAT,
        "operation": operation_name,
        "program": operation.program,
        "requestSha256": hashlib.sha256(request_payload).hexdigest(),
        "role": role,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("policy")
    verify = actions.add_parser("verify-request")
    verify.add_argument("--role", choices=("execution", "upload"), required=True)
    verify.add_argument("--original-command", required=True)
    verify.add_argument("--request-file", type=Path, required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.action == "policy":
            document = policy_document()
            sys.stdout.buffer.write(_canonical(document))
            print(f"broker-policy-sha256:{policy_sha256()}", file=sys.stderr)
        else:
            plan = dispatch_plan(
                role=arguments.role,
                original_command=arguments.original_command,
                request_path=arguments.request_file,
            )
            sys.stdout.buffer.write(_canonical(plan))
        return 0
    except BrokerInvalid as error:
        print(f"release-broker-error:{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
