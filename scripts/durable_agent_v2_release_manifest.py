#!/usr/bin/env python3
"""构建并验证 Durable Agent V2 机器可读发布清单。"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn

FORMAT = "inkforge-durable-agent-v2-release/3"
HEX_DIGITS = frozenset("0123456789abcdef")
TOP_LEVEL_KEYS = {
    "canaryScopeSha256",
    "cliCommit",
    "controlBundleSha256",
    "developmentEvidenceSha256",
    "executionManifestFingerprints",
    "format",
    "images",
    "migration",
    "producer",
    "rollbackSourceReleaseCommit",
    "rollbackSourceReceiptSha256",
    "routeMode",
    "targetReleaseCommit",
    "workflowTrustedCommit",
}
PRODUCER_KEYS = {"repository", "runAttempt", "runId", "workflowPath"}
IMAGE_COMPONENTS = {"agent", "core", "web"}
IMAGE_GROUPS = {"rollback", "target"}
FINGERPRINT_KEYS = {"rollback", "source", "target"}
MIGRATION_KEYS = {
    "forwardSqlSha256",
    "postContractFingerprint",
    "preContractFingerprint",
    "rollbackSqlSha256",
}
FIELD_PATHS: Mapping[str, Sequence[str]] = {
    "canary-scope-sha256": ("canaryScopeSha256",),
    "cli-commit": ("cliCommit",),
    "development-evidence-sha256": ("developmentEvidenceSha256",),
    "control-bundle-sha256": ("controlBundleSha256",),
    "workflow-trusted-commit": ("workflowTrustedCommit",),
    "target-release-commit": ("targetReleaseCommit",),
    "rollback-source-release-commit": ("rollbackSourceReleaseCommit",),
    "rollback-source-receipt-sha256": ("rollbackSourceReceiptSha256",),
    "producer-run-id": ("producer", "runId"),
    "producer-run-attempt": ("producer", "runAttempt"),
    "producer-repository": ("producer", "repository"),
    "producer-workflow-path": ("producer", "workflowPath"),
    "route-mode": ("routeMode",),
    "source-manifest-fingerprint": (
        "executionManifestFingerprints",
        "source",
    ),
    "target-manifest-fingerprint": (
        "executionManifestFingerprints",
        "target",
    ),
    "rollback-manifest-fingerprint": (
        "executionManifestFingerprints",
        "rollback",
    ),
    "target-web-digest": ("images", "target", "web"),
    "target-core-digest": ("images", "target", "core"),
    "target-agent-digest": ("images", "target", "agent"),
    "rollback-web-digest": ("images", "rollback", "web"),
    "rollback-core-digest": ("images", "rollback", "core"),
    "rollback-agent-digest": ("images", "rollback", "agent"),
}


class ManifestError(ValueError):
    """发布清单校验失败。"""


def fail(message: str) -> NoReturn:
    raise ManifestError(message)


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            fail(f"JSON 存在重复 key：{key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        fail(f"JSON 文件必须是普通文件：{path}")
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_float=lambda _: fail("发布清单禁止浮点数"),
            parse_constant=lambda _: fail("发布清单禁止非有限数字"),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"JSON 无法安全读取：{path.name}：{error}")
    if not isinstance(document, dict):
        fail(f"JSON 顶层必须是对象：{path.name}")
    return document


def canonical(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            fail("JSON 含未配对 Unicode 代理字符")
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, list):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            fail("JSON 对象 key 必须是字符串")
        return "{" + ",".join(
            f"{canonical(key)}:{canonical(value[key])}" for key in sorted(value)
        ) + "}"
    fail(f"JSON 含不支持的类型：{type(value).__name__}")


def canonical_bytes(document: Mapping[str, object]) -> bytes:
    return (canonical(dict(document)) + "\n").encode()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_hex(value: object, length: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != length:
        fail(f"{label} 格式无效")
    if any(character not in HEX_DIGITS for character in value):
        fail(f"{label} 格式无效")
    return value


def require_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        fail(f"{label} 必须是 sha256 digest")
    require_hex(value.removeprefix("sha256:"), 64, label)
    return value


def require_positive_decimal(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or not value.isdecimal()
        or value.startswith("0")
    ):
        fail(f"{label} 格式无效")
    return value


def require_exact_keys(
    value: object,
    expected: set[str],
    label: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        fail(f"{label} 字段集合无效")
    return value


def execution_manifest_fingerprint(path: Path) -> str:
    return sha256_bytes(canonical(load_json(path)).encode())


def contract_fingerprint(path: Path) -> str:
    document = load_json(path)
    embedded = require_hex(document.get("fingerprint"), 64, f"{path.name} fingerprint")
    payload = {
        key: value
        for key, value in document.items()
        if key not in {"fingerprint", "source"}
    }
    actual = sha256_bytes(canonical(payload).encode())
    if actual != embedded:
        fail(f"{path.name} 内嵌 fingerprint 不自洽")
    return actual


def repository_facts(root: Path) -> dict[str, str]:
    paths = {
        "sourceManifestFingerprint": root
        / "contracts/agent-execution/manifest.json",
        "forwardSqlSha256": root
        / "scripts/migrations/20260831_durable_agent_execution.sql",
        "rollbackSqlSha256": root
        / "scripts/migrations/20260831_durable_agent_execution.rollback.sql",
        "preContractFingerprint": root
        / "apps/core-api-java/src/main/resources/db/pre-durable-agent-v2/schema-contract.json",
        "postContractFingerprint": root
        / "apps/core-api-java/src/main/resources/db/post-durable-agent-v2/schema-contract.json",
    }
    for path in paths.values():
        if path.is_symlink() or not path.is_file():
            fail(f"发布源文件缺失或为符号链接：{path}")
    return {
        "sourceManifestFingerprint": execution_manifest_fingerprint(
            paths["sourceManifestFingerprint"]
        ),
        "forwardSqlSha256": sha256_file(paths["forwardSqlSha256"]),
        "rollbackSqlSha256": sha256_file(paths["rollbackSqlSha256"]),
        "preContractFingerprint": contract_fingerprint(paths["preContractFingerprint"]),
        "postContractFingerprint": contract_fingerprint(
            paths["postContractFingerprint"]
        ),
    }


def validate_document(
    document: dict[str, object],
    *,
    root: Path | None = None,
    expected_target_commit: str | None = None,
) -> None:
    require_exact_keys(document, TOP_LEVEL_KEYS, "release manifest")
    if document["format"] != FORMAT:
        fail("release manifest format 无效")
    workflow_commit = require_hex(
        document["workflowTrustedCommit"], 40, "workflow trusted commit"
    )
    target_commit = require_hex(
        document["targetReleaseCommit"], 40, "target release commit"
    )
    require_hex(
        document["rollbackSourceReleaseCommit"],
        40,
        "rollback source release commit",
    )
    cli_commit = require_hex(document["cliCommit"], 40, "CLI commit")
    if workflow_commit != target_commit or cli_commit != target_commit:
        fail("workflow、target 与 CLI commit 不一致")
    require_hex(document["canaryScopeSha256"], 64, "canary scope SHA")
    require_hex(document["controlBundleSha256"], 64, "control bundle SHA")
    require_hex(
        document["developmentEvidenceSha256"],
        64,
        "development evidence SHA",
    )
    require_hex(
        document["rollbackSourceReceiptSha256"],
        64,
        "rollback source receipt SHA",
    )
    producer = require_exact_keys(document["producer"], PRODUCER_KEYS, "producer")
    require_positive_decimal(producer["runId"], "producer run ID")
    require_positive_decimal(producer["runAttempt"], "producer run attempt")
    repository = producer["repository"]
    if (
        not isinstance(repository, str)
        or repository.count("/") != 1
        or any(not part or part in {".", ".."} for part in repository.split("/"))
    ):
        fail("producer repository 格式无效")
    if producer["workflowPath"] != ".github/workflows/durable-agent-v2-release.yml":
        fail("producer workflow path 无效")
    if expected_target_commit is not None and target_commit != require_hex(
        expected_target_commit, 40, "预期 target release commit"
    ):
        fail("release manifest 与预期 target commit 不一致")
    route_mode = document["routeMode"]
    if route_mode not in {"off", "allowlist"}:
        fail("release manifest routeMode 无效")

    fingerprints = require_exact_keys(
        document["executionManifestFingerprints"],
        FINGERPRINT_KEYS,
        "execution manifest fingerprints",
    )
    for key in FINGERPRINT_KEYS:
        require_hex(fingerprints[key], 64, f"{key} execution manifest fingerprint")
    if fingerprints["target"] != fingerprints["source"]:
        fail("source/target execution manifest fingerprint 不一致")
    if route_mode == "allowlist" and fingerprints["rollback"] != fingerprints["source"]:
        fail("allowlist rollback execution manifest fingerprint 不兼容")

    images = require_exact_keys(document["images"], IMAGE_GROUPS, "images")
    all_digests: list[str] = []
    for group in IMAGE_GROUPS:
        image_group = require_exact_keys(images[group], IMAGE_COMPONENTS, f"images.{group}")
        for component in IMAGE_COMPONENTS:
            all_digests.append(
                require_digest(image_group[component], f"{group} {component} digest")
            )
    if len(set(all_digests[:3])) != 3 or len(set(all_digests[3:])) != 3:
        fail("同一镜像组的三个组件 digest 必须互不相同")

    migration = require_exact_keys(document["migration"], MIGRATION_KEYS, "migration")
    for key in MIGRATION_KEYS:
        require_hex(migration[key], 64, key)

    if root is not None:
        facts = repository_facts(root.resolve(strict=True))
        if fingerprints["source"] != facts["sourceManifestFingerprint"]:
            fail("source execution manifest fingerprint 与仓库不一致")
        for key in MIGRATION_KEYS:
            if migration[key] != facts[key]:
                fail(f"{key} 与仓库冻结事实不一致")


def safe_output_directory(path: Path) -> tuple[Path, Path]:
    if not path.is_absolute():
        fail("发布清单输出目录必须是绝对路径")
    if os.path.lexists(path):
        fail("发布清单输出目录已存在")
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir() or parent.is_symlink():
        fail("发布清单输出目录父目录无效")
    return parent, parent / path.name


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
            fail("当前 Linux 缺少 renameat2，拒绝非原子发布")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            -100,
            os.fsencode(source),
            -100,
            os.fsencode(target),
            1,
        )
    elif sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renamex_np = getattr(libc, "renamex_np", None)
        if renamex_np is None:
            fail("当前 macOS 缺少 renamex_np，拒绝非原子发布")
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(os.fsencode(source), os.fsencode(target), 4)
    else:
        fail("当前平台不支持目录 no-replace 原子发布")
    if result != 0:
        error_number = ctypes.get_errno()
        fail(f"发布清单目录原子发布失败：errno={error_number}")


def write_manifest_directory(path: Path, document: dict[str, object]) -> str:
    parent, target = safe_output_directory(path)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.partial.", dir=parent))
    os.chmod(temporary, 0o700)
    try:
        manifest_path = temporary / "release-manifest.json"
        manifest_payload = canonical_bytes(document)
        manifest_path.write_bytes(manifest_payload)
        os.chmod(manifest_path, 0o600)
        manifest_sha = sha256_bytes(manifest_payload)
        checksums_path = temporary / "SHA256SUMS"
        checksums_path.write_text(
            f"{manifest_sha}  release-manifest.json\n",
            encoding="ascii",
        )
        os.chmod(checksums_path, 0o600)
        fsync_path(manifest_path)
        fsync_path(checksums_path)
        fsync_path(temporary)
        publish_no_replace(temporary, target)
        fsync_path(parent)
        return manifest_sha
    finally:
        if temporary.exists():
            for child in temporary.iterdir():
                child.unlink(missing_ok=True)
            temporary.rmdir()


def verify_directory(
    directory: Path,
    *,
    root: Path | None,
    expected_target_commit: str | None,
    expected_artifact_sha256: str | None,
) -> tuple[dict[str, object], str]:
    if not directory.is_absolute():
        fail("发布清单目录必须是绝对路径")
    if directory.is_symlink() or not directory.is_dir():
        fail("发布清单目录无效")
    names = {path.name for path in directory.iterdir()}
    if names != {"release-manifest.json", "SHA256SUMS"}:
        fail("发布清单目录文件白名单不匹配")
    if stat.S_IMODE(directory.stat().st_mode) & 0o077:
        fail("发布清单目录权限过宽")
    manifest_path = directory / "release-manifest.json"
    checksums_path = directory / "SHA256SUMS"
    for path in (manifest_path, checksums_path):
        if path.is_symlink() or not path.is_file():
            fail("发布清单文件无效")
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            fail("发布清单文件权限过宽")
    manifest_sha = sha256_file(manifest_path)
    if expected_artifact_sha256 is not None and manifest_sha != require_hex(
        expected_artifact_sha256, 64, "预期 release manifest artifact SHA"
    ):
        fail("release manifest artifact SHA 不一致")
    expected_checksum = f"{manifest_sha}  release-manifest.json\n"
    if checksums_path.read_text(encoding="ascii") != expected_checksum:
        fail("发布清单 SHA256SUMS 不一致")
    document = load_json(manifest_path)
    if manifest_path.read_bytes() != canonical_bytes(document):
        fail("release-manifest.json 不是 canonical JSON")
    validate_document(
        document,
        root=root,
        expected_target_commit=expected_target_commit,
    )
    return document, manifest_sha


def build_document(arguments: argparse.Namespace) -> dict[str, object]:
    workflow_commit = require_hex(
        arguments.workflow_trusted_commit, 40, "workflow trusted commit"
    )
    target_commit = require_hex(
        arguments.target_release_commit, 40, "target release commit"
    )
    rollback_source_commit = require_hex(
        arguments.rollback_source_release_commit,
        40,
        "rollback source release commit",
    )
    cli_commit = require_hex(arguments.cli_commit, 40, "CLI commit")
    facts = repository_facts(arguments.repository_root.resolve(strict=True))
    document: dict[str, object] = {
        "canaryScopeSha256": require_hex(
            arguments.canary_scope_sha256, 64, "canary scope SHA"
        ),
        "cliCommit": cli_commit,
        "controlBundleSha256": require_hex(
            arguments.control_bundle_sha256, 64, "control bundle SHA"
        ),
        "developmentEvidenceSha256": require_hex(
            arguments.development_evidence_sha256,
            64,
            "development evidence SHA",
        ),
        "executionManifestFingerprints": {
            "rollback": require_hex(
                arguments.rollback_manifest_fingerprint,
                64,
                "rollback execution manifest fingerprint",
            ),
            "source": facts["sourceManifestFingerprint"],
            "target": require_hex(
                arguments.target_manifest_fingerprint,
                64,
                "target execution manifest fingerprint",
            ),
        },
        "format": FORMAT,
        "images": {
            "rollback": {
                "agent": require_digest(arguments.rollback_agent_digest, "rollback agent"),
                "core": require_digest(arguments.rollback_core_digest, "rollback core"),
                "web": require_digest(arguments.rollback_web_digest, "rollback web"),
            },
            "target": {
                "agent": require_digest(arguments.target_agent_digest, "target agent"),
                "core": require_digest(arguments.target_core_digest, "target core"),
                "web": require_digest(arguments.target_web_digest, "target web"),
            },
        },
        "migration": {
            "forwardSqlSha256": facts["forwardSqlSha256"],
            "postContractFingerprint": facts["postContractFingerprint"],
            "preContractFingerprint": facts["preContractFingerprint"],
            "rollbackSqlSha256": facts["rollbackSqlSha256"],
        },
        "producer": {
            "repository": arguments.producer_repository,
            "runAttempt": require_positive_decimal(
                arguments.producer_run_attempt, "producer run attempt"
            ),
            "runId": require_positive_decimal(arguments.producer_run_id, "producer run ID"),
            "workflowPath": ".github/workflows/durable-agent-v2-release.yml",
        },
        "rollbackSourceReleaseCommit": rollback_source_commit,
        "rollbackSourceReceiptSha256": require_hex(
            arguments.rollback_source_receipt_sha256,
            64,
            "rollback source receipt SHA",
        ),
        "routeMode": arguments.route_mode,
        "targetReleaseCommit": target_commit,
        "workflowTrustedCommit": workflow_commit,
    }
    validate_document(
        document,
        root=arguments.repository_root,
        expected_target_commit=target_commit,
    )
    return document


def parser() -> argparse.ArgumentParser:
    root_parser = argparse.ArgumentParser()
    subparsers = root_parser.add_subparsers(dest="action", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--repository-root", type=Path, required=True)
    create.add_argument("--output-dir", type=Path, required=True)
    create.add_argument("--workflow-trusted-commit", required=True)
    create.add_argument("--target-release-commit", required=True)
    create.add_argument("--rollback-source-release-commit", required=True)
    create.add_argument("--cli-commit", required=True)
    create.add_argument("--development-evidence-sha256", required=True)
    create.add_argument("--control-bundle-sha256", required=True)
    create.add_argument("--rollback-source-receipt-sha256", required=True)
    create.add_argument("--producer-run-id", required=True)
    create.add_argument("--producer-run-attempt", required=True)
    create.add_argument("--producer-repository", required=True)
    create.add_argument("--canary-scope-sha256", required=True)
    create.add_argument("--route-mode", choices=("off", "allowlist"), required=True)
    create.add_argument("--target-web-digest", required=True)
    create.add_argument("--target-core-digest", required=True)
    create.add_argument("--target-agent-digest", required=True)
    create.add_argument("--rollback-web-digest", required=True)
    create.add_argument("--rollback-core-digest", required=True)
    create.add_argument("--rollback-agent-digest", required=True)
    create.add_argument("--target-manifest-fingerprint", required=True)
    create.add_argument("--rollback-manifest-fingerprint", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--repository-root", type=Path)
    verify.add_argument("--manifest-dir", type=Path, required=True)
    verify.add_argument("--expected-target-commit")
    verify.add_argument("--expected-artifact-sha256")

    read = subparsers.add_parser("read")
    read.add_argument("--repository-root", type=Path)
    read.add_argument("--manifest-dir", type=Path, required=True)
    read.add_argument("--expected-target-commit")
    read.add_argument("--expected-artifact-sha256")
    read.add_argument("--field", choices=tuple(FIELD_PATHS), required=True)

    source = subparsers.add_parser("source-fingerprint")
    source.add_argument("--repository-root", type=Path, required=True)
    return root_parser


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.action == "create":
            document = build_document(arguments)
            manifest_sha = write_manifest_directory(arguments.output_dir, document)
            print(f"release-manifest-created:{manifest_sha}")
            return 0
        if arguments.action == "source-fingerprint":
            print(repository_facts(arguments.repository_root)["sourceManifestFingerprint"])
            return 0
        document, manifest_sha = verify_directory(
            arguments.manifest_dir,
            root=arguments.repository_root,
            expected_target_commit=arguments.expected_target_commit,
            expected_artifact_sha256=arguments.expected_artifact_sha256,
        )
        if arguments.action == "verify":
            print(f"release-manifest-verified:{manifest_sha}")
            return 0
        value: object = document
        for key in FIELD_PATHS[arguments.field]:
            if not isinstance(value, dict):
                fail("发布清单字段路径无效")
            value = value[key]
        if not isinstance(value, str):
            fail("发布清单字段值不是字符串")
        print(value)
        return 0
    except ManifestError as error:
        print(f"release-manifest-error:{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
