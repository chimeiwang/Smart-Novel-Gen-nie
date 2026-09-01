#!/usr/bin/env python3
"""原子发布并严格复验 Core fresh-V2 release guard。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

FORMAT = "inkforge-durable-agent-v2-release-guard/1"
HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
POSITIVE = re.compile(r"[1-9][0-9]*\Z")
KEYS = {
    "canaryScopeSha256",
    "committedReceiptSha256",
    "controlBundleSha256",
    "executionManifestFingerprint",
    "expiresAt",
    "format",
    "issuedAt",
    "leaseId",
    "lockId",
    "manifestSha256",
    "runAttempt",
    "runId",
    "state",
}
MAX_BYTES = 16_384
LEASE_SECONDS = 60


class GuardInvalid(ValueError):
    """guard 不能安全授权 fresh V2。"""


def canonical(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GuardInvalid(f"guard JSON key 重复：{key}")
        result[key] = value
    return result


def parse(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise GuardInvalid("guard 文件无效")
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise GuardInvalid("guard 文件权限必须为 0444")
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_object)
    except GuardInvalid:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GuardInvalid("guard JSON 无效") from error
    if not isinstance(value, dict) or set(value) != KEYS or payload != canonical(value):
        raise GuardInvalid("guard 字段或 canonical 编码无效")
    validate(value)
    return value, payload


def require_hex(value: Any, label: str, *, commit: bool = False) -> str:
    pattern = HEX_40 if commit else HEX_64
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise GuardInvalid(f"{label} 无效")
    return value


def parse_instant(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GuardInvalid(f"{label} 无效")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise GuardInvalid(f"{label} 无效") from error
    return parsed.astimezone(UTC)


def validate(document: dict[str, Any]) -> None:
    if document["format"] != FORMAT or document["state"] not in {
        "off",
        "pending",
        "committed",
    }:
        raise GuardInvalid("guard format/state 无效")
    state = document["state"]
    nullable = KEYS - {"format", "state"}
    if state == "off":
        if any(document[key] is not None for key in nullable):
            raise GuardInvalid("off guard 必须清空全部授权字段")
        return
    for key in (
        "canaryScopeSha256",
        "controlBundleSha256",
        "executionManifestFingerprint",
        "leaseId",
        "lockId",
        "manifestSha256",
    ):
        require_hex(document[key], key)
    for key in ("runId", "runAttempt"):
        if not isinstance(document[key], str) or POSITIVE.fullmatch(document[key]) is None:
            raise GuardInvalid(f"{key} 无效")
    issued = parse_instant(document["issuedAt"], "issuedAt")
    if state == "pending":
        expires = parse_instant(document["expiresAt"], "expiresAt")
        if expires - issued != timedelta(seconds=LEASE_SECONDS):
            raise GuardInvalid("pending lease 时长无效")
        if document["committedReceiptSha256"] is not None:
            raise GuardInvalid("pending guard 禁止绑定 receipt")
    else:
        if document["expiresAt"] is not None:
            raise GuardInvalid("committed guard 禁止保留过期时间")
        require_hex(document["committedReceiptSha256"], "committed receipt SHA")


def ensure_parent(path: Path) -> Path:
    if not path.is_absolute():
        raise GuardInvalid("guard 路径必须为绝对路径")
    parent = path.parent
    if not parent.exists():
        parent.mkdir(mode=0o755)
        os.chmod(parent, 0o755)  # noqa: S103 - Core 只读挂载需要固定可遍历权限
    resolved = parent.resolve(strict=True)
    if resolved != parent or parent.is_symlink() or not parent.is_dir():
        raise GuardInvalid("guard 目录无效")
    if stat.S_IMODE(parent.stat().st_mode) != 0o755:
        raise GuardInvalid("guard 目录权限必须为 0755")
    return parent


def document(arguments: argparse.Namespace) -> dict[str, Any]:
    state = arguments.state
    value: dict[str, Any] = {key: None for key in KEYS}
    value.update({"format": FORMAT, "state": state})
    if state == "off":
        return value
    issued = datetime.now(UTC)
    value.update(
        {
            "canaryScopeSha256": arguments.canary_scope_sha256,
            "controlBundleSha256": arguments.control_bundle_sha256,
            "executionManifestFingerprint": arguments.execution_manifest_fingerprint,
            "issuedAt": issued.isoformat().replace("+00:00", "Z"),
            "leaseId": arguments.lease_id,
            "lockId": arguments.lock_id,
            "manifestSha256": arguments.manifest_sha256,
            "runAttempt": arguments.run_attempt,
            "runId": arguments.run_id,
        }
    )
    if state == "pending":
        value["expiresAt"] = (issued + timedelta(seconds=LEASE_SECONDS)).isoformat().replace(
            "+00:00", "Z"
        )
    else:
        value["committedReceiptSha256"] = arguments.committed_receipt_sha256
    validate(value)
    return value


def write(arguments: argparse.Namespace) -> str:
    target = arguments.path
    parent = ensure_parent(target)
    existing: dict[str, Any] | None = None
    existing_payload = b""
    if target.exists():
        existing, existing_payload = parse(target)
    if arguments.state == "pending" and existing is not None:
        if existing["state"] == "pending":
            raise GuardInvalid("pending lease 不可续租、重发或更换 lease")
        if existing["state"] not in {"off", "committed"}:
            raise GuardInvalid("pending guard 前态无效")
    if arguments.state == "committed":
        if existing is None or existing["state"] not in {"pending", "committed"}:
            raise GuardInvalid("committed guard 必须来自既有 pending")
        bindings = {
            "canaryScopeSha256": arguments.canary_scope_sha256,
            "controlBundleSha256": arguments.control_bundle_sha256,
            "executionManifestFingerprint": arguments.execution_manifest_fingerprint,
            "leaseId": arguments.lease_id,
            "lockId": arguments.lock_id,
            "manifestSha256": arguments.manifest_sha256,
            "runAttempt": arguments.run_attempt,
            "runId": arguments.run_id,
        }
        if any(existing.get(key) != value for key, value in bindings.items()):
            raise GuardInvalid("committed guard 与 pending owner/lease 漂移")
        if existing["state"] == "committed":
            if existing["committedReceiptSha256"] != arguments.committed_receipt_sha256:
                raise GuardInvalid("committed guard receipt 漂移")
            return hashlib.sha256(existing_payload).hexdigest()
    value = document(arguments)
    payload = canonical(value)
    temporary = parent / ".guard.json.partial"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o444)
        os.replace(temporary, target)
        directory = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()
    actual, actual_payload = parse(target)
    if actual != value or actual_payload != payload:
        raise GuardInvalid("guard 原子发布后重读漂移")
    return hashlib.sha256(payload).hexdigest()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    actions = root.add_subparsers(dest="action", required=True)
    write_parser = actions.add_parser("write")
    write_parser.add_argument("--path", type=Path, required=True)
    write_parser.add_argument("--state", choices=("off", "pending", "committed"), required=True)
    for name in (
        "canary-scope-sha256",
        "committed-receipt-sha256",
        "control-bundle-sha256",
        "execution-manifest-fingerprint",
        "lease-id",
        "lock-id",
        "manifest-sha256",
        "run-attempt",
        "run-id",
    ):
        write_parser.add_argument(f"--{name}")
    verify_parser = actions.add_parser("verify")
    verify_parser.add_argument("--path", type=Path, required=True)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.action == "write":
            sha = write(arguments)
            print(f"release-guard-written:{arguments.state}:{sha}")
        else:
            value, payload = parse(arguments.path)
            print(f"release-guard-valid:{value['state']}:{hashlib.sha256(payload).hexdigest()}")
        return 0
    except GuardInvalid as error:
        print(f"release-guard:error:{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
