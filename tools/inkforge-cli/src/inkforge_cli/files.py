from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DirtySnapshotError(RuntimeError):
    pass


def atomic_write_text(path: str | Path, content: str) -> None:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_snapshot_manifest(
    manifest_path: str | Path,
    *,
    novel_id: str | None = None,
) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    if path.name != "manifest.json":
        raise DirtySnapshotError("快照清单必须命名为 manifest.json")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DirtySnapshotError("manifest.json 不可读或格式无效") from exc
    if not isinstance(manifest, dict):
        raise DirtySnapshotError("manifest.json 顶层必须是对象")
    if novel_id is not None and manifest.get("novelId") != novel_id:
        raise DirtySnapshotError("manifest.json 与目标作品不匹配")

    documents = manifest.get("documents")
    if not isinstance(documents, dict):
        raise DirtySnapshotError("manifest.json 缺少 documents")
    root = path.parent
    for document_name, filename in (
        ("outline", "outline.md"),
        ("manuscript", "manuscript.txt"),
    ):
        descriptor = documents.get(document_name)
        if not isinstance(descriptor, dict):
            raise DirtySnapshotError(f"manifest.json 缺少 {document_name} 文档描述")
        raw_path = descriptor.get("path")
        content_hash = descriptor.get("contentHash")
        expected_path = root / filename
        if not isinstance(raw_path, str) or raw_path != str(expected_path):
            raise DirtySnapshotError(
                f"{document_name} 路径必须精确等于快照目录中的 {filename}"
            )
        if not _SHA256_PATTERN.fullmatch(content_hash or ""):
            raise DirtySnapshotError(f"{document_name} contentHash 不是小写 SHA-256")
        if not expected_path.is_file():
            raise DirtySnapshotError(f"快照缺少 {filename}")
    return manifest


def ensure_snapshot_clean(
    manifest_path: str | Path,
    *,
    novel_id: str | None = None,
) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    manifest = load_snapshot_manifest(path, novel_id=novel_id)
    documents = manifest["documents"]
    for document_name, filename in (
        ("outline", "outline.md"),
        ("manuscript", "manuscript.txt"),
    ):
        document_path = path.parent / filename
        current_hash = sha256_text(document_path.read_text(encoding="utf-8"))
        expected_hash = documents[document_name]["contentHash"]
        if current_hash != expected_hash:
            raise DirtySnapshotError(
                f"{document_name} 存在尚未同步的本地修改，拒绝继续"
            )
    return manifest


def export_snapshot(
    directory: str | Path,
    *,
    novel_id: str,
    outline: str,
    manuscript: str,
    metadata: dict[str, Any],
) -> dict[str, object]:
    root = Path(directory).resolve()
    manifest_path = root / "manifest.json"
    outline_path = root / "outline.md"
    manuscript_path = root / "manuscript.txt"

    if manifest_path.exists():
        ensure_snapshot_clean(manifest_path, novel_id=novel_id)
    elif outline_path.exists() or manuscript_path.exists():
        raise DirtySnapshotError("目标目录已有文稿但缺少 manifest.json，拒绝覆盖")

    atomic_write_text(outline_path, outline)
    atomic_write_text(manuscript_path, manuscript)

    outline_hash = sha256_text(outline)
    manuscript_hash = sha256_text(manuscript)
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "novelId": novel_id,
        **metadata,
        "documents": {
            "outline": {
                "path": str(outline_path),
                "contentHash": outline_hash,
            },
            "manuscript": {
                "path": str(manuscript_path),
                "contentHash": manuscript_hash,
            },
        },
    }
    atomic_write_text(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return {
        "manifestPath": str(manifest_path),
        "outlinePath": str(outline_path),
        "manuscriptPath": str(manuscript_path),
        "outlineContentHash": outline_hash,
        "manuscriptContentHash": manuscript_hash,
    }


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_large_result(path: str | Path, content: str) -> dict[str, object]:
    target = Path(path).resolve()
    atomic_write_text(target, content)
    return {
        "path": str(target),
        "contentHash": sha256_text(content),
        "byteLength": len(content.encode("utf-8")),
        "charCount": len(content),
    }
