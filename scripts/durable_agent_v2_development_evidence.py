#!/usr/bin/env python3
"""复验 Durable Agent V2 独立开发环境证据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any, NoReturn

FORMAT = "inkforge-durable-agent-v2-development-evidence/1"
HEX_DIGITS = frozenset("0123456789abcdef")
RESOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
TOP_LEVEL_KEYS = {
    "canaryScopeSha256",
    "composeValidation",
    "developmentMigration",
    "executionManifestFingerprint",
    "format",
    "images",
    "producerRunId",
    "providerCanary",
    "targetReleaseCommit",
}
COMPOSE_KEYS = {
    "faultInjectionReportSha256",
    "resourceConstrainedReportSha256",
}
MIGRATION_KEYS = {
    "backupEvidenceSha256",
    "database",
    "idempotentForwardReportSha256",
    "liveContractEvidenceSha256",
    "rollbackRehearsalReportSha256",
}
PROVIDER_KEYS = {"mode", "reportSha256", "status"}
IMAGE_KEYS = {"agent", "core", "web"}
FIELD_PATHS = {
    "canary-scope-sha256": ("canaryScopeSha256",),
    "execution-manifest-fingerprint": ("executionManifestFingerprint",),
    "producer-run-id": ("producerRunId",),
    "target-release-commit": ("targetReleaseCommit",),
    "target-web-digest": ("images", "web"),
    "target-core-digest": ("images", "core"),
    "target-agent-digest": ("images", "agent"),
}
REPORT_HASH_PATHS = {
    "migration-backup-evidence.json": ("developmentMigration", "backupEvidenceSha256"),
    "live-contract-evidence.json": (
        "developmentMigration",
        "liveContractEvidenceSha256",
    ),
    "idempotent-forward-report.json": (
        "developmentMigration",
        "idempotentForwardReportSha256",
    ),
    "rollback-rehearsal-report.json": (
        "developmentMigration",
        "rollbackRehearsalReportSha256",
    ),
    "fault-injection-report.json": (
        "composeValidation",
        "faultInjectionReportSha256",
    ),
    "resource-constrained-report.json": (
        "composeValidation",
        "resourceConstrainedReportSha256",
    ),
    "provider-canary-report.json": ("providerCanary", "reportSha256"),
}


class EvidenceInvalid(ValueError):
    """开发环境证据不能满足严格协议。"""


def _fail(message: str) -> NoReturn:
    raise EvidenceInvalid(message)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"JSON 存在重复 key：{key}")
        result[key] = value
    return result


def _canonical(value: Any) -> str:
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
            _fail("JSON 含未配对 Unicode 代理字符")
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, list):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{_canonical(key)}:{_canonical(value[key])}" for key in sorted(value)
        ) + "}"
    _fail(f"JSON 含不支持的类型：{type(value).__name__}")


def _canonical_bytes(document: dict[str, Any]) -> bytes:
    return (_canonical(document) + "\n").encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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
        _fail(f"{label} 必须是 sha256 digest")
    _hex(value.removeprefix("sha256:"), 64, label)
    return value


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(f"{label} 字段集合无效")
    return value


def scope_fingerprint(user_id: str, novel_id: str) -> str:
    if not RESOURCE_ID.fullmatch(user_id) or not RESOURCE_ID.fullmatch(novel_id):
        _fail("canary userId 或 novelId 格式无效")
    return _sha256(
        _canonical({"novelId": novel_id, "userId": user_id}).encode()
    )


def _load_directory(directory: Path) -> tuple[dict[str, Any], str]:
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        _fail("开发证据目录无效")
    if stat.S_IMODE(directory.stat().st_mode) & 0o077:
        _fail("开发证据目录权限过宽")
    expected_names = {"development-evidence.json", "SHA256SUMS"}
    if {path.name for path in directory.iterdir()} != expected_names:
        _fail("开发证据目录文件白名单不匹配")
    evidence_path = directory / "development-evidence.json"
    checksums_path = directory / "SHA256SUMS"
    for path in (evidence_path, checksums_path):
        if path.is_symlink() or not path.is_file():
            _fail("开发证据文件必须是普通文件")
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            _fail("开发证据文件权限过宽")
    try:
        document = json.loads(
            evidence_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=lambda _: _fail("开发证据禁止浮点数"),
            parse_constant=lambda _: _fail("开发证据禁止非有限数字"),
        )
    except EvidenceInvalid:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceInvalid("开发证据不是有效 UTF-8 JSON") from error
    if not isinstance(document, dict):
        _fail("开发证据顶层必须是对象")
    payload = evidence_path.read_bytes()
    if payload != _canonical_bytes(document):
        _fail("development-evidence.json 不是 canonical JSON")
    evidence_sha = _sha256(payload)
    if checksums_path.read_text(encoding="ascii") != (
        f"{evidence_sha}  development-evidence.json\n"
    ):
        _fail("开发证据 SHA256SUMS 不一致")
    return document, evidence_sha


def _verify_report_bundle(document: dict[str, Any], directory: Path) -> None:
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        _fail("development reports 目录无效")
    if stat.S_IMODE(directory.stat().st_mode) & 0o077:
        _fail("development reports 目录权限过宽")
    expected_names = set(REPORT_HASH_PATHS) | {"SHA256SUMS"}
    if {path.name for path in directory.iterdir()} != expected_names:
        _fail("development reports 文件白名单不匹配")
    checksum_lines: list[str] = []
    for name in sorted(REPORT_HASH_PATHS):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            _fail(f"development report 不是普通文件：{name}")
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            _fail(f"development report 权限过宽：{name}")
        digest = _sha256(path.read_bytes())
        value: Any = document
        for key in REPORT_HASH_PATHS[name]:
            if not isinstance(value, dict):
                _fail("development report hash 路径无效")
            value = value[key]
        if digest != value:
            _fail(f"development report SHA 不一致：{name}")
        checksum_lines.append(f"{digest}  {name}\n")
    checksums = directory / "SHA256SUMS"
    if checksums.is_symlink() or not checksums.is_file():
        _fail("development reports SHA256SUMS 无效")
    if stat.S_IMODE(checksums.stat().st_mode) & 0o077:
        _fail("development reports SHA256SUMS 权限过宽")
    if checksums.read_text(encoding="ascii") != "".join(checksum_lines):
        _fail("development reports SHA256SUMS 不一致")


def _validate(
    document: dict[str, Any],
    *,
    production: bool,
    expected_run_id: str | None,
    expected_target_commit: str | None,
    expected_scope_sha: str | None,
    expected_images: dict[str, str] | None,
    expected_fingerprint: str | None,
) -> None:
    _exact(document, TOP_LEVEL_KEYS, "development evidence")
    if document["format"] != FORMAT:
        _fail("development evidence format 无效")
    target_commit = _hex(
        document["targetReleaseCommit"], 40, "target release commit"
    )
    run_id = document["producerRunId"]
    if not isinstance(run_id, str) or not run_id.isdigit() or run_id.startswith("0"):
        _fail("producer run ID 格式无效")
    scope_sha = _hex(document["canaryScopeSha256"], 64, "canary scope SHA")
    fingerprint = _hex(
        document["executionManifestFingerprint"],
        64,
        "execution manifest fingerprint",
    )

    images = _exact(document["images"], IMAGE_KEYS, "images")
    normalized_images = {
        component: _digest(images[component], f"{component} image")
        for component in IMAGE_KEYS
    }
    if len(set(normalized_images.values())) != 3:
        _fail("开发证据三镜像 digest 必须互不相同")

    compose = _exact(
        document["composeValidation"], COMPOSE_KEYS, "composeValidation"
    )
    for key in COMPOSE_KEYS:
        _hex(compose[key], 64, key)

    migration = _exact(
        document["developmentMigration"],
        MIGRATION_KEYS,
        "developmentMigration",
    )
    if migration["database"] != "novelwriterdev":
        _fail("开发迁移数据库必须是 novelwriterdev")
    for key in MIGRATION_KEYS - {"database"}:
        _hex(migration[key], 64, key)

    provider = _exact(document["providerCanary"], PROVIDER_KEYS, "providerCanary")
    provider_tuple = (
        provider["status"],
        provider["mode"],
        provider["reportSha256"],
    )
    if provider_tuple[:2] == ("pending", "unavailable"):
        if provider_tuple[2] is not None:
            _fail("pending provider canary 不得伪造 report SHA")
    elif provider_tuple[:2] == ("passed", "real"):
        _hex(provider_tuple[2], 64, "真实 provider canary report SHA")
    else:
        _fail("provider canary 状态组合无效")
    if production and provider_tuple[:2] != ("passed", "real"):
        _fail("production 禁止使用 pending provider canary 证据")

    if expected_run_id is not None and run_id != expected_run_id:
        _fail("producer run ID 与可信 artifact 来源不一致")
    if expected_target_commit is not None and target_commit != _hex(
        expected_target_commit, 40, "预期 target release commit"
    ):
        _fail("开发证据 target commit 不一致")
    if expected_scope_sha is not None and scope_sha != _hex(
        expected_scope_sha, 64, "预期 canary scope SHA"
    ):
        _fail("开发证据 canary scope 不一致")
    if expected_fingerprint is not None and fingerprint != _hex(
        expected_fingerprint, 64, "预期 execution manifest fingerprint"
    ):
        _fail("开发证据 execution manifest fingerprint 不一致")
    if expected_images is not None and normalized_images != expected_images:
        _fail("开发证据目标镜像 digest 不一致")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)

    scope = subparsers.add_parser("scope-fingerprint")
    scope.add_argument("--user-id", required=True)
    scope.add_argument("--novel-id", required=True)

    for action in ("verify", "verify-production", "read"):
        command = subparsers.add_parser(action)
        command.add_argument("--evidence-dir", type=Path, required=True)
        command.add_argument("--expected-sha256")
        command.add_argument("--expected-run-id")
        command.add_argument("--expected-target-commit")
        command.add_argument("--expected-canary-scope-sha256")
        command.add_argument("--expected-execution-fingerprint")
        command.add_argument("--expected-web-digest")
        command.add_argument("--expected-core-digest")
        command.add_argument("--expected-agent-digest")
        command.add_argument("--reports-dir", type=Path)
        if action == "read":
            command.add_argument("--field", choices=tuple(FIELD_PATHS), required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.action == "scope-fingerprint":
            print(scope_fingerprint(arguments.user_id, arguments.novel_id))
            return 0
        document, evidence_sha = _load_directory(arguments.evidence_dir)
        if arguments.expected_sha256 is not None and evidence_sha != _hex(
            arguments.expected_sha256, 64, "预期 development evidence SHA"
        ):
            _fail("development evidence artifact SHA 不一致")
        digest_arguments = (
            arguments.expected_web_digest,
            arguments.expected_core_digest,
            arguments.expected_agent_digest,
        )
        expected_images = None
        if any(value is not None for value in digest_arguments):
            if any(value is None for value in digest_arguments):
                _fail("预期目标镜像 digest 必须完整提供")
            expected_images = {
                "web": _digest(digest_arguments[0], "预期 web image"),
                "core": _digest(digest_arguments[1], "预期 core image"),
                "agent": _digest(digest_arguments[2], "预期 agent image"),
            }
        _validate(
            document,
            production=arguments.action == "verify-production",
            expected_run_id=arguments.expected_run_id,
            expected_target_commit=arguments.expected_target_commit,
            expected_scope_sha=arguments.expected_canary_scope_sha256,
            expected_images=expected_images,
            expected_fingerprint=arguments.expected_execution_fingerprint,
        )
        if arguments.action == "verify-production":
            if arguments.reports_dir is None:
                _fail("production 必须提供完整 development reports artifact")
            _verify_report_bundle(document, arguments.reports_dir)
        elif arguments.reports_dir is not None:
            _verify_report_bundle(document, arguments.reports_dir)
        if arguments.action == "read":
            value: Any = document
            for key in FIELD_PATHS[arguments.field]:
                if not isinstance(value, dict):
                    _fail("开发证据字段路径无效")
                value = value[key]
            if not isinstance(value, str):
                _fail("开发证据字段不是字符串")
            print(value)
        else:
            print(f"development-evidence-verified:{evidence_sha}")
        return 0
    except EvidenceInvalid as error:
        print(f"development-evidence-error:{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
