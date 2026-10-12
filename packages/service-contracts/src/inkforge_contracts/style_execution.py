"""文风画像 V2 的完整来源、单节输入和原始纯文本结果。"""

import hashlib
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .execution import ExecutionId, Sha256

PortraitSection = Literal[
    "creativeMethodology", "uniqueMarkers", "generationStyle", "expressionFeatures", "styleTraits"
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StylePortraitReference(_StrictModel):
    referenceId: ExecutionId
    filename: Annotated[str, Field(min_length=1)]
    charCount: Annotated[int, Field(ge=0)]
    content: Annotated[str, Field(min_length=1)]
    contentSha256: Sha256

    @model_validator(mode="after")
    def validate_original_content(self) -> Self:
        if hashlib.sha256(self.content.encode("utf-8")).hexdigest() != self.contentSha256:
            raise ValueError("画像参考资料原文与 UTF-8 哈希不一致")
        return self


class StylePortraitContextV2(_StrictModel):
    styleId: ExecutionId
    mode: Literal["full", "section"]
    section: PortraitSection | None
    references: Annotated[list[StylePortraitReference], Field(min_length=1)]
    originalCharCount: Annotated[int, Field(ge=0)]
    sourceTextSha256: Sha256

    @property
    def source_text(self) -> str:
        return "\n\n".join(
            f"参考资料：{value.filename}\n\n{value.content}" for value in self.references
        )

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if (self.mode == "section") != (self.section is not None):
            raise ValueError("单节画像必须且只能绑定目标节")
        if len({value.referenceId for value in self.references}) != len(self.references):
            raise ValueError("画像来源不能重复引用同一资料")
        if self.originalCharCount != sum(value.charCount for value in self.references):
            raise ValueError("画像原始字数必须等于冻结参考资料元数据字数之和")
        if hashlib.sha256(self.source_text.encode("utf-8")).hexdigest() != self.sourceTextSha256:
            raise ValueError("画像完整拼接来源与 UTF-8 哈希不一致")
        return self


class StylePortraitStepInput(_StrictModel):
    section: PortraitSection


class StylePortraitSectionOutput(_StrictModel):
    content: Annotated[str, Field(min_length=1)]

    @field_validator("content")
    @classmethod
    def require_visible_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("画像模型回复按原空白规则检查后不能为空")
        return value
