from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

type DocumentType = Literal["outline", "manuscript"]
type VersionSource = Literal["agent", "manual", "restore"]
type VersionStatus = Literal["awaiting_user", "applied"]
type AgentId = Literal["设定", "剧情", "写作", "校验", "编辑"]

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _parse_json_datetime(value: object) -> object:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


JsonDatetime = Annotated[datetime, BeforeValidator(_parse_json_datetime)]


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def count_text_length(content: str) -> int:
    return sum(1 for character in content if not character.isspace() and character != "\ufeff")


class DocumentVersionPayload(StrictModel):
    kind: Literal["outline_draft", "chapter_draft"]
    documentType: DocumentType
    versionNumber: int = Field(ge=1)
    baseVersionId: str | None = None
    clientRequestId: str | None = Field(default=None, min_length=16, max_length=128)
    source: VersionSource
    content: str
    contentHash: str = Field(pattern=SHA256_PATTERN)
    sourceTaskId: str | None = None
    sourceJobId: str | None = None
    sourceOutlineVersionId: str | None = None
    userInstruction: str | None = None
    sourceKind: Literal["idea", "opening", "ending", "outline", "mixed"] | None = None
    sourceText: str | None = None
    restoredFromVersionId: str | None = None
    createdFromSelection: bool = False
    selectionStart: int | None = Field(default=None, ge=0)
    selectionEnd: int | None = Field(default=None, ge=0)
    selectedTextHash: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_identity_and_content(self) -> Self:
        if self.contentHash != content_sha256(self.content):
            raise ValueError("contentHash 必须匹配完整 content")
        if self.documentType == "outline":
            if self.kind != "outline_draft" or self.sourceOutlineVersionId is not None:
                raise ValueError("大纲版本必须使用 outline_draft 且不能绑定来源大纲")
        elif self.kind != "chapter_draft" or self.sourceOutlineVersionId is None:
            raise ValueError("正文版本必须使用 chapter_draft 并绑定 sourceOutlineVersionId")
        if self.source == "agent":
            if self.sourceTaskId is None or self.sourceJobId is None:
                raise ValueError("Agent 版本必须绑定 sourceTaskId 和 sourceJobId")
            if self.clientRequestId is not None or self.restoredFromVersionId is not None:
                raise ValueError("Agent 版本不能冒充人工或恢复版本")
        else:
            if self.clientRequestId is None:
                raise ValueError("人工提交和恢复必须携带 clientRequestId")
            if self.sourceTaskId is not None or self.sourceJobId is not None:
                raise ValueError("人工提交和恢复不能绑定 Agent 任务")
        if self.source == "restore":
            if self.restoredFromVersionId is None:
                raise ValueError("恢复版本必须绑定 restoredFromVersionId")
        elif self.restoredFromVersionId is not None:
            raise ValueError("只有恢复版本可以绑定 restoredFromVersionId")
        selection_fields = (
            self.selectionStart,
            self.selectionEnd,
            self.selectedTextHash,
        )
        if self.createdFromSelection:
            if any(value is None for value in selection_fields):
                raise ValueError("选区版本必须保存完整选区身份")
            if self.selectionStart is not None and self.selectionEnd is not None:
                if self.selectionStart >= self.selectionEnd:
                    raise ValueError("selectionEnd 必须大于 selectionStart")
        elif any(value is not None for value in selection_fields):
            raise ValueError("非选区版本不能携带选区字段")
        return self


class DiffBlock(StrictModel):
    type: Literal["insert", "delete", "replace"]
    oldStart: int = Field(ge=0)
    oldEnd: int = Field(ge=0)
    newStart: int = Field(ge=0)
    newEnd: int = Field(ge=0)
    oldText: str | None = None
    newText: str | None = None


class VersionDiffResponse(StrictModel):
    fromVersionId: str | None
    toVersionId: str | None
    fromWordCount: int = Field(ge=0)
    toWordCount: int = Field(ge=0)
    wordCountDelta: int
    blocks: list[DiffBlock]
    confirmationHash: str = Field(pattern=SHA256_PATTERN)


def bind_confirmation_hash(
    diff: VersionDiffResponse,
    *,
    document_type: DocumentType | None,
    chapter_id: str | None,
    base_version_id: str | None,
    current_draft_hash: str,
    target_version_id: str | None,
) -> VersionDiffResponse:
    canonical = {
        "documentType": document_type,
        "chapterId": chapter_id,
        "baseVersionId": base_version_id,
        "currentDraftHash": current_draft_hash,
        "targetVersionId": target_version_id,
        "diff": diff.model_dump(exclude={"confirmationHash"}, mode="json"),
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return diff.model_copy(
        update={"confirmationHash": hashlib.sha256(encoded).hexdigest()}
    )


def _paragraphs(content: str) -> list[str]:
    if not content:
        return []
    parts = re.split(r"(\n[ \t]*\n)", content)
    return [
        "".join(parts[index : index + 2])
        for index in range(0, len(parts), 2)
        if "".join(parts[index : index + 2])
    ]


def build_document_diff(
    before: str,
    after: str,
    *,
    from_version_id: str | None,
    to_version_id: str | None,
) -> VersionDiffResponse:
    old_parts = _paragraphs(before)
    new_parts = _paragraphs(after)
    matcher = SequenceMatcher(a=old_parts, b=new_parts, autojunk=False)
    old_offsets = [0]
    new_offsets = [0]
    for value in old_parts:
        old_offsets.append(old_offsets[-1] + len(value))
    for value in new_parts:
        new_offsets.append(new_offsets[-1] + len(value))
    blocks: list[DiffBlock] = []
    for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if operation == "equal":
            continue
        old_text = "".join(old_parts[old_start:old_end])
        new_text = "".join(new_parts[new_start:new_end])
        blocks.append(
            DiffBlock(
                type=operation,
                oldStart=old_offsets[old_start],
                oldEnd=old_offsets[old_end],
                newStart=new_offsets[new_start],
                newEnd=new_offsets[new_end],
                oldText=old_text if operation != "insert" else None,
                newText=new_text if operation != "delete" else None,
            )
        )
    from_word_count = count_text_length(before)
    to_word_count = count_text_length(after)
    result = VersionDiffResponse(
        fromVersionId=from_version_id,
        toVersionId=to_version_id,
        fromWordCount=from_word_count,
        toWordCount=to_word_count,
        wordCountDelta=to_word_count - from_word_count,
        blocks=blocks,
        confirmationHash="0" * 64,
    )
    return bind_confirmation_hash(
        result,
        document_type=None,
        chapter_id=None,
        base_version_id=from_version_id,
        current_draft_hash=content_sha256(before),
        target_version_id=to_version_id,
    )


class DocumentBinding(StrictModel):
    documentType: DocumentType
    chapterId: str | None = None

    @model_validator(mode="after")
    def validate_chapter_binding(self) -> Self:
        if self.documentType == "manuscript" and self.chapterId is None:
            raise ValueError("正文版本必须绑定 chapterId")
        if self.documentType == "outline" and self.chapterId is not None:
            raise ValueError("大纲版本不能绑定 chapterId")
        return self


class VersionPreviewRequest(DocumentBinding):
    baseVersionId: str | None = None


class ManualVersionRequest(DocumentBinding):
    clientRequestId: str = Field(min_length=16, max_length=128)
    baseVersionId: str | None = None
    expectedUpdatedAt: JsonDatetime
    contentHash: str = Field(pattern=SHA256_PATTERN)
    confirmationHash: str = Field(pattern=SHA256_PATTERN)
    summary: str | None = None


class VersionActionRequest(DocumentBinding):
    clientRequestId: str = Field(min_length=16, max_length=128)
    baseVersionId: str | None = None
    confirmationHash: str = Field(pattern=SHA256_PATTERN)


class AgentCandidateCreate(DocumentBinding):
    baseVersionId: str | None = None
    baseContentHash: str = Field(pattern=SHA256_PATTERN)
    content: str
    sourceTaskId: str
    sourceJobId: str
    sourceOutlineVersionId: str | None = None
    userInstruction: str | None = None
    createdByAgent: AgentId
    createdFromSelection: bool = False
    selectionStart: int | None = Field(default=None, ge=0)
    selectionEnd: int | None = Field(default=None, ge=0)
    selectedTextHash: str | None = Field(default=None, pattern=SHA256_PATTERN)


class VersionListItem(StrictModel):
    id: str
    documentType: DocumentType
    versionNumber: int = Field(ge=1)
    status: VersionStatus
    source: VersionSource
    wordCount: int = Field(ge=0)
    baseVersionId: str | None
    sourceOutlineVersionId: str | None
    restoredFromVersionId: str | None
    summary: str | None
    createdByAgent: str | None
    createdAt: datetime
    updatedAt: datetime
    appliedAt: datetime | None


class VersionDetailResponse(StrictModel):
    id: str
    novelId: str
    chapterId: str | None
    artifactKey: str
    status: VersionStatus
    summary: str | None
    payload: DocumentVersionPayload
    documentType: DocumentType
    versionNumber: int = Field(ge=1)
    source: VersionSource
    content: str
    contentHash: str = Field(pattern=SHA256_PATTERN)
    baseVersionId: str | None
    sourceOutlineVersionId: str | None
    restoredFromVersionId: str | None
    diff: VersionDiffResponse | None
    createdByAgent: str | None
    taskId: str | None
    createdAt: datetime
    updatedAt: datetime
    appliedAt: datetime | None


class VersionPreviewResponse(StrictModel):
    documentType: DocumentType
    chapterId: str | None
    baseVersionId: str | None
    expectedUpdatedAt: datetime
    contentHash: str = Field(pattern=SHA256_PATTERN)
    dirty: bool
    confirmationSummary: str
    confirmationHash: str = Field(pattern=SHA256_PATTERN)
    diff: VersionDiffResponse
