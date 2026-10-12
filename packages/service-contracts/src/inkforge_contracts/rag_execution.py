"""参考资料索引 V2 的完整来源、批次输入及有限向量输出。"""

import hashlib
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .execution import ExecutionId, Sha256

IndexGeneration = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RagEmbeddingRunInput(_StrictModel):
    referenceId: ExecutionId
    contentHash: Sha256
    indexGeneration: IndexGeneration

    @field_validator("indexGeneration")
    @classmethod
    def validate_generation(cls, value: str) -> str:
        datetime.fromisoformat(value)
        return value


class RagEmbeddingContextV2(RagEmbeddingRunInput):
    content: Annotated[str, Field(min_length=1)]
    chunkCount: Annotated[int, Field(ge=1, le=64)]

    @property
    def chunks(self) -> list[str]:
        return [self.content[index : index + 1800] for index in range(0, len(self.content), 1800)]

    def batch(self, index: int) -> list[str]:
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or index * 10 >= self.chunkCount
        ):
            raise ValueError("索引批号不在完整冻结来源范围内")
        return self.chunks[index * 10 : (index + 1) * 10]

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if hashlib.sha256(self.content.encode("utf-8")).hexdigest() != self.contentHash:
            raise ValueError("索引完整原文与 UTF-8 哈希不一致")
        if (len(self.content) + 1799) // 1800 != self.chunkCount:
            raise ValueError("索引冻结分块数量与完整原文不一致")
        return self


class RagEmbeddingStepInput(_StrictModel):
    batchIndex: Annotated[int, Field(ge=0, le=6)]


class RagEmbeddingBatchOutput(_StrictModel):
    embeddings: Annotated[
        list[
            Annotated[
                list[Annotated[float, Field(allow_inf_nan=False)]],
                Field(min_length=1, max_length=4096),
            ]
        ],
        Field(min_length=1, max_length=10),
    ]

    @model_validator(mode="after")
    def validate_dimensions(self) -> Self:
        if len({len(vector) for vector in self.embeddings}) != 1:
            raise ValueError("同批索引向量维度必须一致")
        return self
