"""构建并复验耐久 Agent 迁移后的只读结构证据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

_FINGERPRINT = re.compile(r"[0-9a-f]{64}")
_PROFILES = {
    "full",
    "without-video-preview",
    "without-phone-auth",
    "without-video-preview-and-phone-auth",
}
_VIDEO_TABLES = {
    "VideoProject",
    "VideoScene",
    "VideoAsset",
    "VideoAssetBinding",
    "VideoGenerationTask",
    "VideoReviewDecisionCommand",
    "VideoChapterAdaptation",
    "VideoChapterAdaptationHead",
    "VideoAdaptationTask",
    "VideoShotPlanVersion",
    "VideoCinematicScene",
    "VideoDramaticBeat",
    "VideoDramaticBeatSourceAnchor",
    "VideoShot",
    "VideoShotSourceAnchor",
    "VideoEpisodePlanVersion",
    "VideoEpisodeBoundary",
    "VideoShotPromptVersion",
    "VideoShotPromptHead",
    "VideoAdaptationDecisionCommand",
    "VideoVisualCanon",
    "VideoVisualCanonVersion",
    "VideoShotVisualReferenceSet",
    "VideoShotVisualReferenceBinding",
    "VideoShotPromptVisualReference",
    "VideoShotRenderTask",
    "VideoShotTake",
    "VideoShotTakeHead",
    "VideoShotTakeDecisionCommand",
    "VideoTakeFrameExtraction",
    "VideoShotKeyframeVersion",
    "VideoShotKeyframeHead",
    "VideoEpisodeEditVersion",
    "VideoEpisodeEditClip",
    "VideoEpisodeEditHead",
    "VideoEpisodeMixVersion",
    "VideoEpisodeAudioClip",
    "VideoEpisodeSubtitleCue",
    "VideoEpisodeMixHead",
    "VideoEpisodeExportTask",
    "VideoEpisodeExport",
}
_REVIEW_VIDEO_COLUMNS = {
    "videoSceneId",
    "videoAdaptationId",
    "videoAdaptationTaskId",
}
_TOKEN_DETAIL_COLUMNS = {"promptCacheMissTokens", "reasoningTokens"}
_TOKEN_DETAIL_CHECKS = {
    "TokenUsage_prompt_cache_details_check",
    "TokenUsage_reasoning_details_check",
    "TokenUsage_token_details_nonnegative_check",
}
_EVIDENCE_FILES = {
    "schema-contract.json",
    "schema-only.sql",
    "contract-verification.meta",
    "SHA256SUMS",
}


def _canonical_fingerprint(contract: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in contract.items()
        if key not in {"fingerprint", "source"}
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _load_contract(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("contract 顶层必须是对象")
    fingerprint = value.get("fingerprint")
    if not isinstance(fingerprint, str) or fingerprint != _canonical_fingerprint(value):
        raise ValueError("contract fingerprint 不自洽")
    return value


def _remove_named(table: dict[str, Any], collection: str, names: set[str]) -> None:
    values = table.get(collection)
    if isinstance(values, list):
        table[collection] = [
            item
            for item in values
            if not isinstance(item, dict) or item.get("name") not in names
        ]


def _index_references(index: dict[str, Any], column: str) -> bool:
    include_columns = index.get("includeColumns")
    if isinstance(include_columns, list) and column in include_columns:
        return True
    key_items = index.get("keyItems")
    return isinstance(key_items, list) and any(
        isinstance(item, dict) and item.get("column") == column for item in key_items
    )


def _project_review_artifact(table: dict[str, Any]) -> None:
    _remove_named(table, "columns", _REVIEW_VIDEO_COLUMNS)
    for collection in ("foreignKeys", "uniqueConstraints"):
        values = table.get(collection)
        if isinstance(values, list):
            table[collection] = [
                item
                for item in values
                if not isinstance(item, dict)
                or _REVIEW_VIDEO_COLUMNS.isdisjoint(item.get("columns", []))
            ]
    indexes = table.get("indexes")
    if isinstance(indexes, list):
        table["indexes"] = [
            item
            for item in indexes
            if not isinstance(item, dict)
            or not any(_index_references(item, column) for column in _REVIEW_VIDEO_COLUMNS)
        ]
    checks = table.get("checkConstraints")
    if isinstance(checks, list):
        table["checkConstraints"] = [
            item
            for item in checks
            if not isinstance(item, dict)
            or not any(
                column in f"{item.get('expression', '')}{item.get('definition', '')}"
                for column in _REVIEW_VIDEO_COLUMNS
            )
        ]


def _project_contract(contract: dict[str, Any], profile: str) -> dict[str, Any]:
    if profile not in _PROFILES:
        raise ValueError("schema profile 无效")
    projected = deepcopy(contract)
    projected.pop("fingerprint", None)
    include_video = profile in {"full", "without-phone-auth"}
    include_phone = profile in {"full", "without-video-preview"}

    tables = projected.get("tables")
    if not isinstance(tables, list):
        raise ValueError("post contract tables 无效")
    remaining: list[Any] = []
    for item in tables:
        if not isinstance(item, dict):
            remaining.append(item)
            continue
        name = str(item.get("name", ""))
        if not include_video and name in _VIDEO_TABLES:
            continue
        if not include_phone and name == "UserPhoneIdentity":
            continue
        if not include_video and name == "Novel":
            _remove_named(item, "uniqueConstraints", {"Novel_id_userId_key"})
            _remove_named(item, "indexes", {"Novel_id_userId_key"})
        elif not include_video and name == "Chapter":
            _remove_named(item, "uniqueConstraints", {"Chapter_id_novelId_key"})
            _remove_named(item, "indexes", {"Chapter_id_novelId_key"})
        elif not include_video and name == "TokenUsage":
            _remove_named(item, "columns", _TOKEN_DETAIL_COLUMNS)
            _remove_named(item, "checkConstraints", _TOKEN_DETAIL_CHECKS)
        elif not include_video and name == "ReviewArtifact":
            _project_review_artifact(item)
        remaining.append(item)
    projected["tables"] = remaining

    enums = projected.get("enums")
    if not include_video and isinstance(enums, list):
        for enum in enums:
            if not isinstance(enum, dict) or enum.get("name") != "ReviewArtifactKind":
                continue
            values = enum.get("values")
            if isinstance(values, list):
                enum["values"] = [
                    value
                    for value in values
                    if value not in {"video_scene_plan", "video_adaptation_plan"}
                ]

    projected["fingerprint"] = _canonical_fingerprint(projected)
    return projected


def _load_source(path: Path, expected_database: str) -> tuple[dict[str, Any], str]:
    source_row = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(source_row, dict) or source_row.get("databaseName") != expected_database:
        raise ValueError("实时来源数据库身份不一致")
    version = source_row.get("serverVersion")
    version_number = source_row.get("serverVersionNum")
    address = source_row.get("serverAddress")
    port = source_row.get("serverPort")
    if not isinstance(version, str) or not isinstance(version_number, int):
        raise ValueError("实时 PostgreSQL 版本元数据无效")
    if address is not None and not isinstance(address, str):
        raise ValueError("实时 PostgreSQL 地址元数据无效")
    if port is not None and not isinstance(port, int):
        raise ValueError("实时 PostgreSQL 端口元数据无效")
    identity = json.dumps(
        [expected_database, address, port],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    source_id = hashlib.sha256(identity).hexdigest()
    return (
        {
            "product": "PostgreSQL",
            "serverVersion": version,
            "serverVersionNum": version_number,
            "sourceId": source_id,
        },
        source_id,
    )


def _write_exclusive(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
        target.write(content)
        target.flush()
        os.fsync(target.fileno())


def _metadata(values: dict[str, str]) -> str:
    if any("\n" in value or "\r" in value for value in values.values()):
        raise ValueError("证据元数据包含换行")
    order = (
        "format",
        "database",
        "schemaState",
        "schemaProfile",
        "contractFingerprint",
        "guardFingerprint",
        "frozenPostContractFileSha256",
        "schemaOnlySha256",
        "sourceId",
    )
    return "".join(f"{key}={values[key]}\n" for key in order)


def _parse_metadata(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            raise ValueError("证据元数据格式无效")
        key, value = line.split("=", 1)
        if not key or key in result:
            raise ValueError("证据元数据字段重复或为空")
        result[key] = value
    return result


def _build(args: argparse.Namespace) -> str:
    output_dir = args.evidence_dir
    initial_names = {path.name for path in output_dir.iterdir()} if output_dir.is_dir() else set()
    if initial_names != {"schema-only.sql", "source.json"} or any(
        path.is_symlink() or not path.is_file() for path in output_dir.iterdir()
    ):
        raise ValueError("证据临时目录初始文件集合无效")
    actual_schema_sha = hashlib.sha256(
        (output_dir / "schema-only.sql").read_bytes()
    ).hexdigest()
    if actual_schema_sha != args.schema_only_sha256:
        raise ValueError("schema-only dump SHA 与构建参数不一致")
    post = _load_contract(args.post_contract)
    projected = _project_contract(post, args.profile)
    fingerprint = projected["fingerprint"]
    if fingerprint != args.guard_fingerprint:
        raise ValueError("Java guard fingerprint 与冻结 post contract 投影不一致")
    source, source_id = _load_source(args.source_json, args.database)
    projected["source"] = source
    if _canonical_fingerprint(projected) != fingerprint:
        raise ValueError("替换来源元数据改变了结构 fingerprint")

    contract_content = json.dumps(
        projected,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    _write_exclusive(output_dir / "schema-contract.json", contract_content)
    meta = _metadata(
        {
            "format": "inkforge-durable-agent-contract-evidence/1",
            "database": args.database,
            "schemaState": args.schema_state,
            "schemaProfile": args.profile,
            "contractFingerprint": fingerprint,
            "guardFingerprint": args.guard_fingerprint,
            "frozenPostContractFileSha256": args.post_contract_sha256,
            "schemaOnlySha256": args.schema_only_sha256,
            "sourceId": source_id,
        }
    )
    _write_exclusive(output_dir / "contract-verification.meta", meta)
    return fingerprint


def _verify(args: argparse.Namespace) -> str:
    evidence_dir = args.evidence_dir
    names = {path.name for path in evidence_dir.iterdir()}
    if names != _EVIDENCE_FILES:
        raise ValueError("证据目录文件集合不符合白名单")
    if any(path.is_symlink() or not path.is_file() for path in evidence_dir.iterdir()):
        raise ValueError("证据目录包含符号链接或非普通文件")
    actual_schema_sha = hashlib.sha256(
        (evidence_dir / "schema-only.sql").read_bytes()
    ).hexdigest()
    if actual_schema_sha != args.schema_only_sha256:
        raise ValueError("证据 schema-only dump 与当前数据库不一致")

    post = _load_contract(args.post_contract)
    expected = _project_contract(post, args.profile)
    actual = _load_contract(evidence_dir / "schema-contract.json")
    if args.source_json is None:
        raise ValueError("verify 缺少实时来源 JSON")
    current_source, current_source_id = _load_source(args.source_json, args.database)
    if actual.get("source") != current_source:
        raise ValueError("导出 contract 的来源与当前数据库不一致")
    if _canonical_fingerprint(actual) != expected["fingerprint"]:
        raise ValueError("导出 contract 与冻结 post contract 投影不一致")
    expected_without_source = deepcopy(expected)
    actual_without_source = deepcopy(actual)
    expected_without_source.pop("source", None)
    actual_without_source.pop("source", None)
    if expected_without_source != actual_without_source:
        raise ValueError("导出 contract 结构正文与冻结 post contract 投影不一致")
    if actual["fingerprint"] != args.guard_fingerprint:
        raise ValueError("导出 contract 与实时 Java guard fingerprint 不一致")

    metadata = _parse_metadata(evidence_dir / "contract-verification.meta")
    expected_metadata = {
        "format": "inkforge-durable-agent-contract-evidence/1",
        "database": args.database,
        "schemaState": args.schema_state,
        "schemaProfile": args.profile,
        "contractFingerprint": actual["fingerprint"],
        "guardFingerprint": args.guard_fingerprint,
        "frozenPostContractFileSha256": args.post_contract_sha256,
        "schemaOnlySha256": args.schema_only_sha256,
        "sourceId": current_source_id,
    }
    if metadata != expected_metadata:
        raise ValueError("证据元数据与当前复验事实不一致")
    return str(actual["fingerprint"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--post-contract", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--database", required=True, choices=("novelwriterdev", "novelwriter"))
    parser.add_argument(
        "--schema-state",
        required=True,
        choices=("migrated-empty-v2", "migrated-with-v2"),
    )
    parser.add_argument("--profile", required=True, choices=sorted(_PROFILES))
    parser.add_argument("--guard-fingerprint", required=True)
    parser.add_argument("--post-contract-sha256", required=True)
    parser.add_argument("--schema-only-sha256", required=True)
    parser.add_argument("--source-json", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    for digest in (
        args.guard_fingerprint,
        args.post_contract_sha256,
        args.schema_only_sha256,
    ):
        if _FINGERPRINT.fullmatch(digest) is None:
            raise SystemExit("结构证据 SHA-256 参数无效")
    try:
        if args.action == "build":
            if args.source_json is None:
                raise ValueError("build 缺少实时来源 JSON")
            fingerprint = _build(args)
        else:
            fingerprint = _verify(args)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"结构证据校验失败：{error}") from None
    print(fingerprint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
