from __future__ import annotations

import hashlib
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

from .identity import Identifier, NonBlankString

ShortMediumOperation = Literal[
    "generate_outline",
    "generate_manuscript",
    "replace_selection",
    "full_check",
]
ShortMediumDocumentType = Literal["outline", "manuscript"]
ShortMediumSourceKind = Literal["idea", "opening", "ending", "outline", "mixed"]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ContentText = Annotated[str, StringConstraints(min_length=1)]

_SELECTION_FIELDS = (
    "selectionStart",
    "selectionEnd",
    "selectedText",
    "selectedTextHash",
    "contextBefore",
    "contextAfter",
)


class ShortMediumRunPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: Literal["short_medium"]
    operation: ShortMediumOperation
    documentType: ShortMediumDocumentType
    chapterId: Identifier | None = None
    baseVersionId: Identifier | None = None
    baseContent: str | None = None
    baseContentHash: Sha256 | None = None
    sourceOutlineVersionId: Identifier | None = None
    sourceOutlineContent: str | None = None
    sourceOutlineContentHash: Sha256 | None = None
    selectionStart: int | None = Field(default=None, ge=0)
    selectionEnd: int | None = Field(default=None, ge=0)
    selectedText: str | None = None
    selectedTextHash: Sha256 | None = None
    contextBefore: str | None = None
    contextAfter: str | None = None
    userInstruction: NonBlankString | None = None
    targetTotalWordCount: int | None = Field(default=None, ge=6_000, le=80_000)
    sourceKind: ShortMediumSourceKind | None = None
    sourceText: str | None = None

    @model_validator(mode="after")
    def validate_operation_binding(self) -> Self:
        selection_values = [getattr(self, field) for field in _SELECTION_FIELDS]

        if self.operation == "generate_outline":
            if self.documentType != "outline":
                raise ValueError("生成大纲必须绑定大纲文档")
            if self.chapterId is not None or self.sourceOutlineVersionId is not None:
                raise ValueError("生成大纲不能绑定正文或来源大纲版本")
            if self.sourceKind is None or self.sourceText is None or not self.sourceText.strip():
                raise ValueError("生成大纲必须携带权威起始素材")
            self._validate_optional_base_snapshot()
            if any(value is not None for value in selection_values):
                raise ValueError("生成大纲不能携带选区字段")
            return self

        if self.operation == "generate_manuscript":
            if self.documentType != "manuscript":
                raise ValueError("生成正文必须绑定正文文档")
            if self.chapterId is None or self.sourceOutlineVersionId is None:
                raise ValueError("生成正文必须绑定全文章节和来源大纲版本")
            if self.targetTotalWordCount is None:
                raise ValueError("生成正文必须携带目标总字数")
            self._validate_required_snapshot(
                self.sourceOutlineContent,
                self.sourceOutlineContentHash,
                "来源大纲",
            )
            self._validate_optional_base_snapshot()
            if any(value is not None for value in selection_values):
                raise ValueError("生成正文不能携带选区字段")
            return self

        if self.operation == "replace_selection":
            required = (
                self.baseVersionId,
                self.baseContentHash,
                self.selectionStart,
                self.selectionEnd,
                self.selectedText,
                self.selectedTextHash,
                self.contextBefore,
                self.contextAfter,
                self.userInstruction,
            )
            if any(value is None for value in required):
                raise ValueError("选区修改必须携带完整的版本、全文和选区身份")
            if self.selectionStart is not None and self.selectionEnd is not None:
                if self.selectionStart >= self.selectionEnd:
                    raise ValueError("选区结束位置必须大于开始位置")
            self._validate_required_snapshot(
                self.selectedText,
                self.selectedTextHash,
                "原始选区",
            )
            if self.documentType == "manuscript":
                if self.chapterId is None or self.sourceOutlineVersionId is None:
                    raise ValueError("正文选区修改必须绑定全文章节和来源大纲版本")
            elif self.chapterId is not None or self.sourceOutlineVersionId is not None:
                raise ValueError("大纲选区修改不能绑定正文来源")
            return self

        if self.documentType != "manuscript":
            raise ValueError("全文检查只能绑定正文文档")
        if self.chapterId is None or self.baseVersionId is None:
            raise ValueError("全文检查必须绑定全文章节和正文版本")
        self._validate_required_snapshot(
            self.baseContent,
            self.baseContentHash,
            "正文基础版本",
        )
        if any(value is not None for value in selection_values):
            raise ValueError("全文检查不能携带选区字段")
        return self

    def _validate_optional_base_snapshot(self) -> None:
        values = (self.baseVersionId, self.baseContent, self.baseContentHash)
        if all(value is None for value in values):
            return
        if any(value is None for value in values):
            raise ValueError("基础版本 ID、完整内容和 hash 必须同时提供")
        self._validate_required_snapshot(
            self.baseContent,
            self.baseContentHash,
            "基础版本",
        )

    @staticmethod
    def _validate_required_snapshot(
        content: str | None,
        content_hash: str | None,
        label: str,
    ) -> None:
        if content is None or content_hash is None:
            raise ValueError(f"{label}必须携带完整内容和 hash")
        actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if actual_hash != content_hash:
            raise ValueError(f"{label} hash 与完整内容不匹配")


class ShortMediumDocumentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resultType: Literal["short_medium_document"]
    operation: Literal["generate_outline", "generate_manuscript"]
    documentType: ShortMediumDocumentType
    content: ContentText
    sourceOutlineVersionId: Identifier | None = None

    @model_validator(mode="after")
    def validate_document_binding(self) -> Self:
        if self.operation == "generate_outline":
            if self.documentType != "outline" or self.sourceOutlineVersionId is not None:
                raise ValueError("大纲结果必须绑定大纲文档")
        elif self.documentType != "manuscript" or self.sourceOutlineVersionId is None:
            raise ValueError("正文结果必须绑定正文文档和来源大纲版本")
        return self


class ShortMediumReplacementResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resultType: Literal["short_medium_replacement"]
    operation: Literal["replace_selection"]
    documentType: ShortMediumDocumentType
    replacement: str
    baseVersionId: Identifier
    baseContentHash: Sha256
    selectionStart: int = Field(ge=0)
    selectionEnd: int = Field(ge=0)
    selectedTextHash: Sha256

    @model_validator(mode="after")
    def validate_selection_range(self) -> Self:
        if self.selectionStart >= self.selectionEnd:
            raise ValueError("选区结束位置必须大于开始位置")
        return self


class ShortMediumCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resultType: Literal["short_medium_check"]
    operation: Literal["full_check"]
    documentType: Literal["manuscript"]
    baseVersionId: Identifier
    report: dict[str, JsonValue]


def validate_short_medium_result(result: dict[str, JsonValue]) -> None:
    result_type = result.get("resultType")
    operation = result.get("operation")
    models: dict[str, type[BaseModel]] = {
        "short_medium_document": ShortMediumDocumentResult,
        "short_medium_replacement": ShortMediumReplacementResult,
        "short_medium_check": ShortMediumCheckResult,
    }
    if not isinstance(result_type, str):
        if operation in {
            "generate_outline",
            "generate_manuscript",
            "replace_selection",
            "full_check",
        }:
            raise ValueError("中短篇完成结果必须提供 resultType")
        return
    model = models.get(result_type)
    if model is not None:
        model.model_validate(result)
    elif result_type.startswith("short_medium_"):
        raise ValueError("未知的中短篇完成结果类型")
