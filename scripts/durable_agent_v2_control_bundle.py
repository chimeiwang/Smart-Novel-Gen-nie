#!/usr/bin/env python3
"""构建并复验 Durable Agent V2 不可变发布控制包。"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath

FORMAT = "inkforge-durable-agent-v2-control-bundle/1"
PAYLOAD_FILES = (
    "apps/core-api-java/src/main/resources/db/post-durable-agent-v2/schema-contract.json",
    "apps/core-api-java/src/main/resources/db/pre-durable-agent-v2/schema-contract.json",
    "contracts/agent-execution/manifest.json",
    "infra/compose.python-core-rollback.yaml",
    "infra/compose.durable-agent-release-guard.yaml",
    "infra/compose.yaml",
    "infra/nginx/nginx.conf",
    "infra/redis/execution-redis.conf",
    "infra/redis/redis.conf",
    "scripts/agent_readiness_probe.py",
    "scripts/backup.sh",
    "scripts/compose_smoke.sh",
    "scripts/deploy-production.sh",
    "scripts/durable-agent-execution-migration.sh",
    "scripts/durable-agent-v2-release.sh",
    "scripts/durable-agent-v2-rollout-gate.sh",
    "scripts/durable_agent_contract_evidence.py",
    "scripts/durable_agent_joint_drain.py",
    "scripts/durable_agent_release_broker.py",
    "scripts/durable_agent_release_boundary.py",
    "scripts/durable_agent_release_guard.py",
    "scripts/durable_agent_release_trust.py",
    "scripts/durable_agent_v1_drain_index_initialize.lua",
    "scripts/durable_agent_v1_pre_activation_snapshot.lua",
    "scripts/durable_agent_v1_queue_snapshot.lua",
    "scripts/durable_agent_v2_drain_index_initialize.lua",
    "scripts/durable_agent_v2_execution_snapshot.lua",
    "scripts/durable_agent_v2_pre_activation_snapshot.lua",
    "scripts/durable_agent_v2_control_bundle.py",
    "scripts/durable_agent_v2_release_manifest.py",
    "scripts/durable_agent_v2_release_receipt.py",
    "scripts/migrations/20260823_token_usage_details.production.sql",
    "scripts/migrations/20260831_durable_agent_execution.rollback.sql",
    "scripts/migrations/20260831_durable_agent_execution.sql",
    "scripts/migrations/rollback_20260823_token_usage_details.sql",
    "scripts/token-usage-production-migration.sh",
    "scripts/verify-durable-agent-v2-image.sh",
)
META_KEYS = {
    "filesSha256",
    "format",
    "producerRunAttempt",
    "producerRunId",
    "targetReleaseCommit",
    "workflowTrustedCommit",
}


class BundleInvalid(ValueError):
    """控制包无法作为发布信任根。"""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_hex(value: str, length: int, label: str) -> str:
    if len(value) != length or any(character not in "0123456789abcdef" for character in value):
        raise BundleInvalid(f"{label} 格式无效")
    return value


def _require_decimal(value: str, label: str) -> str:
    if not value.isascii() or not value.isdecimal() or value.startswith("0"):
        raise BundleInvalid(f"{label} 格式无效")
    return value


def _canonical(document: dict[str, str]) -> bytes:
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


def _expected_names() -> set[str]:
    names = {"control-bundle.json", "SHA256SUMS"}
    names.update(PAYLOAD_FILES)
    return names


def _all_relative_files(root: Path) -> set[str]:
    result: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise BundleInvalid("控制包禁止符号链接")
        if path.is_file():
            result.add(path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise BundleInvalid("控制包含非普通文件")
    return result


def _checksum_payload(root: Path) -> bytes:
    lines = [f"{_sha256_file(root / relative)}  {relative}\n" for relative in PAYLOAD_FILES]
    return "".join(lines).encode("ascii")


def _bundle_sha(meta_payload: bytes, checksum_payload: bytes) -> str:
    return _sha256(meta_payload + checksum_payload)


def _validate_modes(root: Path) -> None:
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise BundleInvalid("控制包根目录权限必须为 0700")
    for path in root.rglob("*"):
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir() and mode != 0o700:
            raise BundleInvalid("控制包子目录权限必须为 0700")
        if path.is_file() and mode != 0o600:
            raise BundleInvalid("控制包文件权限必须为 0600")


def _fsync_path(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_no_replace(source: Path, target: Path) -> None:
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise BundleInvalid("当前 Linux 缺少 renameat2，拒绝非原子发布")
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
            raise BundleInvalid("当前 macOS 缺少 renamex_np，拒绝非原子发布")
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(os.fsencode(source), os.fsencode(target), 4)
    else:
        raise BundleInvalid("当前平台不支持目录 no-replace 原子发布")
    if result != 0:
        raise BundleInvalid(f"控制包目录原子发布失败：errno={ctypes.get_errno()}")


def _load_meta(path: Path) -> tuple[dict[str, str], bytes]:
    try:
        pairs = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=list)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BundleInvalid("控制包元数据不是有效 JSON") from error
    if not isinstance(pairs, list):
        raise BundleInvalid("控制包元数据顶层无效")
    document: dict[str, str] = {}
    for pair in pairs:
        if not isinstance(pair, tuple | list) or len(pair) != 2:
            raise BundleInvalid("控制包元数据对象无效")
        key, value = pair
        if not isinstance(key, str) or not isinstance(value, str) or key in document:
            raise BundleInvalid("控制包元数据字段无效或重复")
        document[key] = value
    payload = path.read_bytes()
    if set(document) != META_KEYS or payload != _canonical(document):
        raise BundleInvalid("控制包元数据字段或 canonical 编码无效")
    return document, payload


def verify(root: Path, expected_sha: str | None = None) -> tuple[dict[str, str], str]:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise BundleInvalid("控制包目录无效")
    if _all_relative_files(root) != _expected_names():
        raise BundleInvalid("控制包文件白名单不匹配")
    _validate_modes(root)
    document, meta_payload = _load_meta(root / "control-bundle.json")
    if document["format"] != FORMAT:
        raise BundleInvalid("控制包 format 无效")
    _require_hex(document["workflowTrustedCommit"], 40, "workflow trusted commit")
    _require_hex(document["targetReleaseCommit"], 40, "target release commit")
    _require_decimal(document["producerRunId"], "producer run ID")
    _require_decimal(document["producerRunAttempt"], "producer run attempt")
    checksum_payload = (root / "SHA256SUMS").read_bytes()
    expected_checksum_payload = _checksum_payload(root)
    if checksum_payload != expected_checksum_payload:
        raise BundleInvalid("控制包 SHA256SUMS 不一致")
    if document["filesSha256"] != _sha256(checksum_payload):
        raise BundleInvalid("控制包 filesSha256 不一致")
    actual_sha = _bundle_sha(meta_payload, checksum_payload)
    if expected_sha is not None and actual_sha != _require_hex(
        expected_sha, 64, "预期 control bundle SHA"
    ):
        raise BundleInvalid("控制包 SHA 不一致")
    return document, actual_sha


def create(arguments: argparse.Namespace) -> str:
    repository = arguments.repository_root.resolve(strict=True)
    output = arguments.output_dir
    if not output.is_absolute() or os.path.lexists(output):
        raise BundleInvalid("控制包输出目录必须是尚不存在的绝对路径")
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir() or parent.is_symlink():
        raise BundleInvalid("控制包输出目录父目录无效")
    output = parent / output.name
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.partial.", dir=parent))
    os.chmod(temporary, 0o700)
    try:
        for relative in PAYLOAD_FILES:
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts:
                raise BundleInvalid("控制包白名单路径无效")
            source = repository / relative
            if source.is_symlink() or not source.is_file():
                raise BundleInvalid(f"控制包源文件缺失：{relative}")
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(target.parent, 0o700)
            shutil.copyfile(source, target)
            os.chmod(target, 0o600)
        checksums = _checksum_payload(temporary)
        (temporary / "SHA256SUMS").write_bytes(checksums)
        os.chmod(temporary / "SHA256SUMS", 0o600)
        document = {
            "filesSha256": _sha256(checksums),
            "format": FORMAT,
            "producerRunAttempt": _require_decimal(
                arguments.producer_run_attempt, "producer run attempt"
            ),
            "producerRunId": _require_decimal(arguments.producer_run_id, "producer run ID"),
            "targetReleaseCommit": _require_hex(
                arguments.target_release_commit, 40, "target release commit"
            ),
            "workflowTrustedCommit": _require_hex(
                arguments.workflow_trusted_commit, 40, "workflow trusted commit"
            ),
        }
        meta_payload = _canonical(document)
        (temporary / "control-bundle.json").write_bytes(meta_payload)
        os.chmod(temporary / "control-bundle.json", 0o600)
        bundle_sha = _bundle_sha(meta_payload, checksums)
        verify(temporary, bundle_sha)
        for path in sorted(temporary.rglob("*"), reverse=True):
            _fsync_path(path)
        _fsync_path(temporary)
        _publish_no_replace(temporary, output)
        _fsync_path(parent)
        return bundle_sha
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def publish(arguments: argparse.Namespace) -> str:
    source = arguments.bundle_dir
    target = arguments.target_dir
    document, bundle_sha = verify(source, arguments.expected_sha256)
    if not target.is_absolute() or os.path.lexists(target):
        raise BundleInvalid("control bundle 发布目标必须是尚不存在的绝对路径")
    source_parent = source.parent.resolve(strict=True)
    target_parent = target.parent.resolve(strict=True)
    if source_parent != target_parent or target_parent.is_symlink():
        raise BundleInvalid("control bundle 必须在同一受保护目录原子发布")
    target = target_parent / target.name
    _publish_no_replace(source, target)
    _fsync_path(target_parent)
    published_document, published_sha = verify(target, bundle_sha)
    if published_document != document:
        raise BundleInvalid("control bundle 发布后 provenance 漂移")
    return published_sha


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    actions = root.add_subparsers(dest="action", required=True)
    create_parser = actions.add_parser("create")
    create_parser.add_argument("--repository-root", type=Path, required=True)
    create_parser.add_argument("--output-dir", type=Path, required=True)
    create_parser.add_argument("--workflow-trusted-commit", required=True)
    create_parser.add_argument("--target-release-commit", required=True)
    create_parser.add_argument("--producer-run-id", required=True)
    create_parser.add_argument("--producer-run-attempt", required=True)
    verify_parser = actions.add_parser("verify")
    verify_parser.add_argument("--bundle-dir", type=Path, required=True)
    verify_parser.add_argument("--expected-sha256")
    publish_parser = actions.add_parser("publish")
    publish_parser.add_argument("--bundle-dir", type=Path, required=True)
    publish_parser.add_argument("--target-dir", type=Path, required=True)
    publish_parser.add_argument("--expected-sha256", required=True)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.action == "create":
            digest = create(arguments)
            print(f"control-bundle-created:{digest}")
        elif arguments.action == "publish":
            digest = publish(arguments)
            print(f"control-bundle-published:{digest}")
        else:
            _document, digest = verify(arguments.bundle_dir, arguments.expected_sha256)
            print(f"control-bundle-verified:{digest}")
        return 0
    except BundleInvalid as error:
        print(f"control-bundle-error:{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
