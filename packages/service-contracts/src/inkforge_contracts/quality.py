from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ConsistencyDimension = Literal[
    "character",
    "world_rule",
    "timeline",
    "causality",
    "foreshadowing",
]


class ConsistencyScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    characterConsistency: float = Field(ge=0, le=100)
    worldRuleConsistency: float = Field(ge=0, le=100)
    timelineConsistency: float = Field(ge=0, le=100)
    causalityConsistency: float = Field(ge=0, le=100)
    foreshadowingConsistency: float = Field(ge=0, le=100)


class ConsistencyIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: ConsistencyDimension
    severity: Literal["warning", "error"]
    message: str = Field(min_length=1, max_length=500)
    evidence: str = Field(min_length=1, max_length=1000)
    location: str | None = Field(default=None, max_length=200)
    suggestion: str = Field(min_length=1, max_length=1000)


class ConsistencyQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: ConsistencyScores
    qualityGate: Literal["pass", "revise"]
    issues: list[ConsistencyIssue] = Field(max_length=100)
    report: str = Field(min_length=1)
    rewriteBrief: str | None = Field(default=None, max_length=1000)

    @field_validator("report")
    @classmethod
    def validate_report(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("一致性终检报告不能为空")
        return value
