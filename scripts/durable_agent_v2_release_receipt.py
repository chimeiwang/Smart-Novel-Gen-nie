#!/usr/bin/env python3
"""构建并验证受保护发布成功后的不可变服务器 receipt。"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

FORMAT = "inkforge-durable-agent-v2-release-receipt/1"
HEX = frozenset("0123456789abcdef")
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
TOP_KEYS = {
    "activeReleaseCommit",
    "canaryScopeSha256",
    "controlBundleSha256",
    "executionManifestFingerprint",
    "finalConfig",
    "format",
    "images",
    "lock",
    "manifestSha256",
    "previousReceiptSha256",
    "runtimeIdentity",
    "targetReleaseCommit",
    "workflowTrustedCommit",
}
FIELD_PATHS = {
    "active-release-commit": ("activeReleaseCommit",),
    "agent-digest": ("images", "agent"),
    "canary-scope-sha256": ("canaryScopeSha256",),
    "control-bundle-sha256": ("controlBundleSha256",),
    "core-digest": ("images", "core"),
    "execution-manifest-fingerprint": ("executionManifestFingerprint",),
    "manifest-sha256": ("manifestSha256",),
    "lock-id": ("lock", "lockId"),
    "release-action": ("lock", "action"),
    "run-attempt": ("lock", "runAttempt"),
    "run-id": ("lock", "runId"),
    "previous-receipt-sha256": ("previousReceiptSha256",),
    "route-mode": ("finalConfig", "routeMode"),
    "schema-ready": ("finalConfig", "schemaReady"),
    "v1-fresh-starts-enabled": ("finalConfig", "v1FreshStartsEnabled"),
    "web-digest": ("images", "web"),
    "target-release-commit": ("targetReleaseCommit",),
    "workflow-trusted-commit": ("workflowTrustedCommit",),
    "boundary-ledger-sha256": ("runtimeIdentity", "boundaryLedgerSha256"),
}


class ReceiptInvalid(ValueError):
    """receipt 不能证明一次成功受保护发布。"""


def fsync_path(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_no_replace(source: Path, target: Path) -> None:
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise ReceiptInvalid("当前 Linux 缺少 renameat2，拒绝非原子发布")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1)
    elif sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renamex_np = getattr(libc, "renamex_np", None)
        if renamex_np is None:
            raise ReceiptInvalid("当前 macOS 缺少 renamex_np，拒绝非原子发布")
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(os.fsencode(source), os.fsencode(target), 4)
    else:
        raise ReceiptInvalid("当前平台不支持目录 no-replace 原子发布")
    if result != 0:
        raise ReceiptInvalid(f"receipt 目录原子发布失败：errno={ctypes.get_errno()}")


def canonical(document: dict[str, Any]) -> bytes:
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


def require_hex(value: Any, length: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != length or any(c not in HEX for c in value):
        raise ReceiptInvalid(f"{label} 格式无效")
    return value


def require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ReceiptInvalid(f"{label} 格式无效")
    return value


def require_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ReceiptInvalid(f"{label} 字段无效")
    return value


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptInvalid(f"receipt JSON key 重复：{key}")
        result[key] = value
    return result


def validate(document: dict[str, Any]) -> None:
    require_keys(document, TOP_KEYS, "receipt")
    if document["format"] != FORMAT:
        raise ReceiptInvalid("receipt format 无效")
    for key in (
        "activeReleaseCommit",
        "targetReleaseCommit",
        "workflowTrustedCommit",
    ):
        require_hex(document[key], 40, key)
    for key in (
        "canaryScopeSha256",
        "controlBundleSha256",
        "executionManifestFingerprint",
        "manifestSha256",
    ):
        require_hex(document[key], 64, key)
    previous = document["previousReceiptSha256"]
    if previous is not None:
        require_hex(previous, 64, "previous receipt SHA")
    images = require_keys(document["images"], {"agent", "core", "web"}, "images")
    for name, digest in images.items():
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise ReceiptInvalid(f"{name} image digest 无效")
        require_hex(digest.removeprefix("sha256:"), 64, f"{name} image digest")
    config = require_keys(
        document["finalConfig"],
        {"routeMode", "schemaReady", "v1FreshStartsEnabled"},
        "finalConfig",
    )
    if config["routeMode"] not in {"off", "allowlist"}:
        raise ReceiptInvalid("receipt route 无效")
    if not isinstance(config["schemaReady"], bool) or not isinstance(
        config["v1FreshStartsEnabled"], bool
    ):
        raise ReceiptInvalid("receipt 布尔配置无效")
    if config["routeMode"] == "allowlist" and (
        config["schemaReady"] is not True or config["v1FreshStartsEnabled"] is not True
    ):
        raise ReceiptInvalid("allowlist receipt 配置无效")
    lock = require_keys(
        document["lock"],
        {"action", "lockId", "runAttempt", "runId"},
        "lock",
    )
    if lock["action"] not in {"route_off_release", "allowlist_release", "rollback"}:
        raise ReceiptInvalid("receipt action 无效")
    require_hex(lock["lockId"], 64, "lock ID")
    for key in ("runId", "runAttempt"):
        value = lock[key]
        if (
            not isinstance(value, str)
            or not value.isascii()
            or not value.isdecimal()
            or value.startswith("0")
        ):
            raise ReceiptInvalid(f"{key} 无效")
    identity = require_keys(
        document["runtimeIdentity"],
        {"boundaryLedgerSha256", "coreContainerId"},
        "runtimeIdentity",
    )
    require_id(identity["coreContainerId"], "Core container ID")
    require_hex(identity["boundaryLedgerSha256"], 64, "boundary ledger SHA")


def verify(directory: Path, expected_sha: str | None = None) -> tuple[dict[str, Any], str]:
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise ReceiptInvalid("receipt 目录无效")
    if stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise ReceiptInvalid("receipt 目录权限无效")
    if {path.name for path in directory.iterdir()} != {"release-receipt.json", "SHA256SUMS"}:
        raise ReceiptInvalid("receipt 文件白名单无效")
    receipt = directory / "release-receipt.json"
    checksums = directory / "SHA256SUMS"
    for path in (receipt, checksums):
        if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ReceiptInvalid("receipt 文件或权限无效")
    try:
        document = json.loads(
            receipt.read_text(encoding="utf-8"), object_pairs_hook=unique_object
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReceiptInvalid("receipt JSON 无效") from error
    if not isinstance(document, dict):
        raise ReceiptInvalid("receipt 顶层无效")
    validate(document)
    payload = receipt.read_bytes()
    if payload != canonical(document):
        raise ReceiptInvalid("receipt 不是 canonical JSON")
    digest = hashlib.sha256(payload).hexdigest()
    if checksums.read_text(encoding="ascii") != f"{digest}  release-receipt.json\n":
        raise ReceiptInvalid("receipt checksum 无效")
    if expected_sha is not None and digest != require_hex(expected_sha, 64, "预期 receipt SHA"):
        raise ReceiptInvalid("receipt SHA 不一致")
    return document, digest


def create(arguments: argparse.Namespace) -> str:
    previous = arguments.previous_receipt_sha256
    document: dict[str, Any] = {
        "activeReleaseCommit": arguments.active_release_commit,
        "canaryScopeSha256": arguments.canary_scope_sha256,
        "controlBundleSha256": arguments.control_bundle_sha256,
        "executionManifestFingerprint": arguments.execution_manifest_fingerprint,
        "finalConfig": {
            "routeMode": arguments.route_mode,
            "schemaReady": arguments.schema_ready == "true",
            "v1FreshStartsEnabled": arguments.v1_fresh_starts_enabled == "true",
        },
        "format": FORMAT,
        "images": {
            "agent": arguments.agent_digest,
            "core": arguments.core_digest,
            "web": arguments.web_digest,
        },
        "lock": {
            "action": arguments.release_action,
            "lockId": arguments.lock_id,
            "runAttempt": arguments.run_attempt,
            "runId": arguments.run_id,
        },
        "manifestSha256": arguments.manifest_sha256,
        "previousReceiptSha256": None if previous == "none" else previous,
        "runtimeIdentity": {
            "boundaryLedgerSha256": arguments.boundary_ledger_sha256,
            "coreContainerId": arguments.core_container_id,
        },
        "targetReleaseCommit": arguments.target_release_commit,
        "workflowTrustedCommit": arguments.workflow_trusted_commit,
    }
    validate(document)
    output = arguments.output_dir
    if not output.is_absolute() or os.path.lexists(output):
        raise ReceiptInvalid("receipt 输出目录必须尚不存在")
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir() or parent.is_symlink():
        raise ReceiptInvalid("receipt 输出目录父目录无效")
    output = parent / output.name
    temporary = parent / f".{output.name}.partial"
    try:
        temporary.mkdir(mode=0o700)
    except FileExistsError as error:
        raise ReceiptInvalid("receipt partial 输出目录已存在") from error
    os.chmod(temporary, 0o700)
    try:
        payload = canonical(document)
        receipt = temporary / "release-receipt.json"
        receipt.write_bytes(payload)
        os.chmod(receipt, 0o600)
        digest = hashlib.sha256(payload).hexdigest()
        checksums = temporary / "SHA256SUMS"
        checksums.write_text(f"{digest}  release-receipt.json\n", encoding="ascii")
        os.chmod(checksums, 0o600)
        verify(temporary, digest)
        fsync_path(receipt)
        fsync_path(checksums)
        fsync_path(temporary)
        publish_no_replace(temporary, output)
        fsync_path(parent)
        return digest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def publish(arguments: argparse.Namespace) -> str:
    source = arguments.receipt_dir
    target = arguments.target_dir
    document, digest = verify(source, arguments.expected_sha256)
    if not target.is_absolute() or os.path.lexists(target):
        raise ReceiptInvalid("receipt 发布目标必须是尚不存在的绝对路径")
    source_parent = source.parent.resolve(strict=True)
    target_parent = target.parent.resolve(strict=True)
    if source_parent.stat().st_dev != target_parent.stat().st_dev:
        raise ReceiptInvalid("receipt 必须在同一文件系统原子发布")
    target = target_parent / target.name
    publish_no_replace(source, target)
    fsync_path(target_parent)
    published_document, published_digest = verify(target, digest)
    if published_document != document:
        raise ReceiptInvalid("receipt 发布后内容漂移")
    return published_digest


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    actions = root.add_subparsers(dest="action", required=True)
    create_parser = actions.add_parser("create")
    for name in (
        "active-release-commit",
        "agent-digest",
        "canary-scope-sha256",
        "control-bundle-sha256",
        "core-container-id",
        "core-digest",
        "boundary-ledger-sha256",
        "execution-manifest-fingerprint",
        "lock-id",
        "manifest-sha256",
        "previous-receipt-sha256",
        "release-action",
        "route-mode",
        "run-attempt",
        "run-id",
        "schema-ready",
        "target-release-commit",
        "v1-fresh-starts-enabled",
        "web-digest",
        "workflow-trusted-commit",
    ):
        create_parser.add_argument(f"--{name}", required=True)
    create_parser.add_argument("--output-dir", type=Path, required=True)
    verify_parser = actions.add_parser("verify")
    verify_parser.add_argument("--receipt-dir", type=Path, required=True)
    verify_parser.add_argument("--expected-sha256")
    publish_parser = actions.add_parser("publish")
    publish_parser.add_argument("--receipt-dir", type=Path, required=True)
    publish_parser.add_argument("--target-dir", type=Path, required=True)
    publish_parser.add_argument("--expected-sha256", required=True)
    read_parser = actions.add_parser("read")
    read_parser.add_argument("--receipt-dir", type=Path, required=True)
    read_parser.add_argument("--expected-sha256", required=True)
    read_parser.add_argument("--field", choices=tuple(FIELD_PATHS), required=True)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.action == "create":
            digest = create(arguments)
            print(f"release-receipt-created:{digest}")
        elif arguments.action == "publish":
            digest = publish(arguments)
            print(f"release-receipt-published:{digest}")
        else:
            document, digest = verify(arguments.receipt_dir, arguments.expected_sha256)
            if arguments.action == "verify":
                print(f"release-receipt-verified:{digest}")
            else:
                value: Any = document
                for key in FIELD_PATHS[arguments.field]:
                    if not isinstance(value, dict):
                        raise ReceiptInvalid("receipt 字段路径无效")
                    value = value[key]
                if isinstance(value, bool):
                    print("true" if value else "false")
                elif isinstance(value, str):
                    print(value)
                else:
                    raise ReceiptInvalid("receipt 字段类型无效")
        return 0
    except ReceiptInvalid as error:
        print(f"release-receipt-error:{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
