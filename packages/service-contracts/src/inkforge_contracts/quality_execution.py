"""一致性终检的不可变来源与独立协议纠正输入；报告仍使用原共享契约。"""

import hashlib
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .execution import ExecutionId, Sha256


class QualityContextV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    checkId: ExecutionId
    novelId: ExecutionId
    chapterId: ExecutionId
    chapterContent: str
    chapterContentSha256: Sha256
    sourceUpdatedAt: Annotated[str, Field(min_length=1)]
    message: str | None
    sourceTaskId: ExecutionId | None

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        if (
            hashlib.sha256(self.chapterContent.encode("utf-8")).hexdigest()
            != self.chapterContentSha256
        ):
            raise ValueError("质量检查正文与原始 UTF-8 哈希不一致")
        return self


class QualityStepInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    userInstruction: Annotated[str, Field(min_length=1)]
    failedStepId: ExecutionId | None = None
    failedResultHash: Sha256 | None = None
    failureCode: Literal["MODEL_TOOL_PROTOCOL_CORRECTION_REQUIRED"] | None = None

    @model_validator(mode="after")
    def validate_correction(self) -> Self:
        correction = {"failedStepId", "failedResultHash", "failureCode"}
        supplied = correction.intersection(self.model_fields_set)
        if supplied and (
            supplied != correction or any(getattr(self, key) is None for key in correction)
        ):
            raise ValueError("协议纠正必须完整绑定失败 Step、结果哈希和稳定错误码")
        return self
