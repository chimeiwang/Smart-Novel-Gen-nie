from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ...api import CoreApiError
from ...io import atomic_write_text, sha256_text
from ...json_types import JsonObject
from ...runtime import (
    CliInputError,
    CliRuntime,
    ensure_command_json_result,
    require_client_request_id,
)
from .snapshots import export_snapshot, load_snapshot_manifest


def _require_string(payload: JsonObject, name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise CliInputError("FIELD_REQUIRED", f"缺少字符串字段 {name}")
    return value


def _public_id(value: str) -> str:
    return quote(value, safe="")


def _without(payload: JsonObject, *names: str) -> JsonObject:
    excluded = set(names)
    return {key: value for key, value in payload.items() if key not in excluded}


def list_novels(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    del payload
    response = runtime.require_api().request(
        "GET",
        "/api/v1/novels",
        params={"storyLengthProfile": "short_medium"},
    )
    if isinstance(response, dict) and isinstance(response.get("novels"), list):
        return ensure_command_json_result(response)
    return ensure_command_json_result({"novels": response})


def create(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_client_request_id(payload)
    response = runtime.require_api().request(
        "POST",
        "/api/v1/novels",
        json=_without(payload, "profile"),
    )
    return ensure_command_json_result(response)


def pull(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    api = runtime.require_api()
    novel_id = _require_string(payload, "novelId")
    target = Path(_require_string(payload, "outputDirectory"))
    encoded_novel_id = _public_id(novel_id)
    bootstrap = api.request(
        "GET",
        f"/api/v1/novels/{encoded_novel_id}/workspace/bootstrap",
    )
    if not isinstance(bootstrap, dict):
        raise CoreApiError(
            500,
            code="INVALID_BOOTSTRAP_RESPONSE",
            message="作品工作区响应格式无效",
        )
    current_chapter = bootstrap.get("currentChapter")
    if not isinstance(current_chapter, dict):
        chapters = bootstrap.get("chapters")
        first_chapter = chapters[0] if isinstance(chapters, list) and chapters else None
        chapter_id = first_chapter.get("id") if isinstance(first_chapter, dict) else None
        if isinstance(chapter_id, str):
            bootstrap = api.request(
                "GET",
                f"/api/v1/novels/{encoded_novel_id}/workspace/bootstrap",
                params={"chapterId": chapter_id},
            )
            current_chapter = (
                bootstrap.get("currentChapter")
                if isinstance(bootstrap, dict)
                else None
            )
    if not isinstance(current_chapter, dict):
        raise CoreApiError(
            500,
            code="MANUSCRIPT_CHAPTER_MISSING",
            message="中短篇作品缺少唯一全文章节",
        )

    planning = api.request(
        "GET",
        f"/api/v1/novels/{encoded_novel_id}/workspace/planning",
    )
    outline_record = planning.get("outline") if isinstance(planning, dict) else None
    outline = (
        outline_record.get("content", "")
        if isinstance(outline_record, dict)
        else ""
    )
    manuscript = current_chapter.get("content", "")
    if not isinstance(outline, str) or not isinstance(manuscript, str):
        raise CoreApiError(
            500,
            code="INVALID_DOCUMENT_CONTENT",
            message="服务端返回了无效的文档内容",
        )
    chapter_id = current_chapter.get("id")
    if not isinstance(chapter_id, str):
        raise CoreApiError(
            500,
            code="MANUSCRIPT_CHAPTER_MISSING",
            message="全文章节缺少 id",
        )
    outline_versions = api.request(
        "GET",
        f"/api/v1/novels/{encoded_novel_id}/versions",
        params={"documentType": "outline"},
    )
    manuscript_versions = api.request(
        "GET",
        f"/api/v1/novels/{encoded_novel_id}/versions",
        params={"documentType": "manuscript", "chapterId": chapter_id},
    )
    metadata: JsonObject = {
        "chapterId": chapter_id,
        "outlineUpdatedAt": (
            outline_record.get("updatedAt")
            if isinstance(outline_record, dict)
            else None
        ),
        "manuscriptUpdatedAt": current_chapter.get("updatedAt"),
        "outlineVersions": outline_versions,
        "manuscriptVersions": manuscript_versions,
    }
    return export_snapshot(
        target,
        novel_id=novel_id,
        outline=outline,
        manuscript=manuscript,
        metadata=metadata,
    )


def draft_save(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    api = runtime.require_api()
    novel_id = _require_string(payload, "novelId")
    document_type = _require_string(payload, "documentType")
    if document_type not in {"outline", "manuscript"}:
        raise CliInputError(
            "INVALID_DOCUMENT_TYPE",
            "documentType 只能是 outline 或 manuscript",
        )
    file_path = Path(_require_string(payload, "filePath")).resolve()
    manifest_path = Path(_require_string(payload, "manifestPath")).resolve()
    manifest = load_snapshot_manifest(manifest_path, novel_id=novel_id)
    documents = manifest["documents"]
    if not isinstance(documents, dict):
        raise CliInputError("INVALID_MANIFEST", "manifest 缺少 documents 对象")
    descriptor = documents.get(document_type)
    if not isinstance(descriptor, dict):
        raise CliInputError(
            "INVALID_MANIFEST",
            f"manifest 缺少 {document_type} 文档描述符",
        )
    if descriptor["path"] != str(file_path):
        raise CliInputError(
            "INVALID_MANIFEST",
            "filePath 与 manifest 中的文档路径不一致",
        )
    content = file_path.read_text(encoding="utf-8")
    updated_at_field = (
        "outlineUpdatedAt" if document_type == "outline" else "manuscriptUpdatedAt"
    )
    expected_updated_at = manifest.get(updated_at_field)
    if not isinstance(expected_updated_at, str) or not expected_updated_at:
        raise CliInputError(
            "INVALID_MANIFEST",
            f"manifest 缺少 {updated_at_field}",
        )
    if document_type == "outline":
        response: Any = api.request(
            "PUT",
            f"/api/v1/novels/{_public_id(novel_id)}/outline",
            json={"content": content, "expectedUpdatedAt": expected_updated_at},
        )
    else:
        chapter_id = manifest.get("chapterId")
        if not isinstance(chapter_id, str) or not chapter_id:
            raise CliInputError("INVALID_MANIFEST", "manifest 缺少 chapterId")
        title = payload.get("title", "全文")
        if not isinstance(title, str) or not title:
            raise CliInputError("INVALID_TITLE", "title 必须是非空字符串")
        response = api.request(
            "PATCH",
            f"/api/v1/chapters/{_public_id(chapter_id)}",
            json={
                "title": title,
                "content": content,
                "expectedUpdatedAt": expected_updated_at,
            },
        )

    next_updated_at = response.get("updatedAt") if isinstance(response, dict) else None
    if not isinstance(next_updated_at, str) or not next_updated_at:
        raise CoreApiError(
            500,
            code="INVALID_DRAFT_SAVE_RESPONSE",
            message="工作稿保存响应缺少 updatedAt，未推进本地 manifest",
        )
    content_hash = sha256_text(content)
    manifest[updated_at_field] = next_updated_at
    descriptor["contentHash"] = content_hash
    atomic_write_text(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    result = dict(response)
    result["manifestPath"] = str(manifest_path)
    result["contentHash"] = content_hash
    return ensure_command_json_result(result)
