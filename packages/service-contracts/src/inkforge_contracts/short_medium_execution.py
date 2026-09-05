"""中短篇 V2 单 Step 契约；独立保留冻结原文，不复用 V1 strip 类型。"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .execution import ExecutionId, Sha256

Text = Annotated[str, Field(min_length=1)]
Index = Annotated[int, Field(strict=True, ge=0, le=5)]
Count = Annotated[int, Field(strict=True, ge=1, le=6)]
Operation = Literal["generate_outline", "generate_manuscript", "replace_selection", "full_check"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ShortMediumContextV2(_StrictModel):
    """原 assembler 二十字段全部必填，可空字段仍显式携带 null。"""

    workflow: Literal["short_medium"]
    operation: Operation
    documentType: Literal["outline", "manuscript"]
    chapterId: ExecutionId | None
    baseVersionId: ExecutionId | None
    baseContent: str | None
    baseContentHash: Sha256 | None
    sourceOutlineVersionId: ExecutionId | None
    sourceOutlineContent: str | None
    sourceOutlineContentHash: Sha256 | None
    selectionStart: Annotated[int, Field(strict=True, ge=0)] | None
    selectionEnd: Annotated[int, Field(strict=True, ge=0)] | None
    selectedText: str | None
    selectedTextHash: Sha256 | None
    contextBefore: str | None
    contextAfter: str | None
    userInstruction: Text | None
    targetTotalWordCount: Annotated[int, Field(strict=True, ge=6000, le=80000)] | None
    sourceKind: Literal["idea", "opening", "ending", "outline", "mixed"] | None
    sourceText: str | None

    @property
    def segment_count(self) -> int:
        if self.operation != "generate_manuscript":
            return 1
        if self.targetTotalWordCount is None:
            raise ValueError("正文生成缺少冻结目标字数")
        return (self.targetTotalWordCount + 14999) // 15000

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        for identity, content, digest in (
            (self.baseVersionId, self.baseContent, self.baseContentHash),
            (self.sourceOutlineVersionId, self.sourceOutlineContent, self.sourceOutlineContentHash),
        ):
            if all(value is None for value in (identity, content, digest)):
                continue
            if identity is None or content is None or digest != _hash(content):
                raise ValueError("中短篇完整来源三元组或哈希不一致")
        if (self.documentType == "manuscript") != (self.chapterId is not None):
            raise ValueError("正文必须绑定章节，蓝图不得绑定章节")
        if self.documentType == "outline" and self.sourceOutlineVersionId is not None:
            raise ValueError("蓝图不得绑定来源蓝图版本")
        if self.operation == "generate_outline" and self.documentType != "outline":
            raise ValueError("蓝图生成文档类型不一致")
        if (
            self.operation in {"generate_manuscript", "full_check"}
            and self.documentType != "manuscript"
        ):
            raise ValueError("正文操作文档类型不一致")
        if self.operation in {"generate_outline", "generate_manuscript"}:
            if self.sourceKind is None or self.sourceText is None or not self.sourceText.strip():
                raise ValueError("生成必须冻结完整起始素材")
        if self.operation == "generate_manuscript":
            if self.targetTotalWordCount is None or self.sourceOutlineVersionId is None:
                raise ValueError("正文生成必须冻结目标字数和来源蓝图")
        if self.operation in {"replace_selection", "full_check"} and self.baseVersionId is None:
            raise ValueError("修改与检查必须冻结完整基础版本")
        selection = (
            self.selectionStart,
            self.selectionEnd,
            self.selectedText,
            self.selectedTextHash,
            self.contextBefore,
            self.contextAfter,
        )
        if self.operation != "replace_selection":
            if any(value is not None for value in selection):
                raise ValueError("非选区操作不得携带选区")
        else:
            if any(value is None for value in selection) or self.userInstruction is None:
                raise ValueError("选区操作缺少完整来源与指令")
            if (
                self.baseContent is None
                or self.selectionStart is None
                or self.selectionEnd is None
                or self.selectedText is None
            ):
                raise ValueError("选区操作缺少完整基础正文或选区")
            if not 0 <= self.selectionStart < self.selectionEnd <= len(self.baseContent):
                raise ValueError("选区 Unicode 码点范围无效")
            if (
                self.baseContent[: self.selectionStart] != self.contextBefore
                or self.baseContent[self.selectionStart : self.selectionEnd] != self.selectedText
                or self.baseContent[self.selectionEnd :] != self.contextAfter
                or _hash(self.selectedText) != self.selectedTextHash
            ):
                raise ValueError("选区不能逐字重建基础版本")
            if self.documentType == "manuscript" and self.sourceOutlineVersionId is None:
                raise ValueError("正文选区必须绑定来源蓝图")
        return self


class ShortMediumStepInput(_StrictModel):
    segmentIndex: Index
    segmentCount: Count

    @model_validator(mode="after")
    def validate_index(self) -> Self:
        if self.segmentIndex >= self.segmentCount:
            raise ValueError("段号必须小于冻结段数")
        return self


class ShortMediumContentOutput(_StrictModel):
    content: Text


class ShortMediumContentResult(ShortMediumContentOutput):
    contentSha256: Sha256

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if self.contentSha256 != _hash(self.content):
            raise ValueError("完整内容哈希不一致")
        return self


class ShortMediumPriorSegment(ShortMediumContentResult):
    index: Index


class ShortMediumReplacementOutput(_StrictModel):
    replacement: Text


class ShortMediumReplacementResult(ShortMediumReplacementOutput):
    replacementSha256: Sha256

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if self.replacementSha256 != _hash(self.replacement):
            raise ValueError("完整替换文本哈希不一致")
        return self


class ShortMediumCheckOutput(_StrictModel):
    text: Text


class ShortMediumCheckResult(ShortMediumCheckOutput):
    textSha256: Sha256

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if self.textSha256 != _hash(self.text):
            raise ValueError("完整报告哈希不一致")
        return self


def materialize_short_medium_output(operation: str, value: object) -> dict[str, JsonValue]:
    """模型只产语义文本，程序按完整 UTF-8 原文派生哈希。"""
    if operation in {"generate_outline", "generate_manuscript"}:
        content = ShortMediumContentOutput.model_validate(value).content
        return {"content": content, "contentSha256": _hash(content)}
    if operation == "replace_selection":
        replacement = ShortMediumReplacementOutput.model_validate(value).replacement
        return {"replacement": replacement, "replacementSha256": _hash(replacement)}
    if operation == "full_check":
        text = ShortMediumCheckOutput.model_validate(value).text
        return {"text": text, "textSha256": _hash(text)}
    raise ValueError("中短篇操作未实现")
