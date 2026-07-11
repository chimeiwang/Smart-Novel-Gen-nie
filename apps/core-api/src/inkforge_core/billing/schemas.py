from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

ProviderName = Literal["openai_compatible", "fake"]


class BillingSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuthorizeModelCallRequest(BillingSchema):
    userId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    agentId: str = Field(min_length=1, max_length=64)
    provider: ProviderName
    model: str = Field(min_length=1, max_length=256)
    estimatedPromptTokens: StrictInt = Field(ge=0)
    requestedMaxOutputTokens: StrictInt = Field(ge=1, le=1_000_000)


class ModelGrantClaims(BillingSchema):
    requestId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    userId: str = Field(min_length=1, max_length=256)
    provider: ProviderName
    model: str = Field(min_length=1, max_length=256)
    agentId: str = Field(min_length=1, max_length=64)
    maxOutputTokens: StrictInt = Field(ge=1, le=1_000_000)
    billable: bool
    iat: StrictInt
    exp: StrictInt

    @model_validator(mode="after")
    def validate_lifetime(self) -> Self:
        if self.exp <= self.iat or self.exp - self.iat > 300:
            raise ValueError("模型授权令牌有效期无效")
        return self


class AuthorizeModelCallResponse(BillingSchema):
    requestId: str
    provider: ProviderName
    model: str
    maxOutputTokens: int
    billable: bool
    grantToken: str
    expiresAt: datetime


class ReportModelUsageRequest(BillingSchema):
    requestId: str = Field(min_length=1, max_length=256)
    taskId: str = Field(min_length=1, max_length=256)
    runId: str = Field(min_length=1, max_length=256)
    novelId: str = Field(min_length=1, max_length=256)
    grantToken: str = Field(min_length=1, max_length=8192)
    promptTokens: StrictInt = Field(ge=0)
    cachedTokens: StrictInt = Field(ge=0)
    completionTokens: StrictInt = Field(ge=0)
    totalTokens: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def validate_usage(self) -> Self:
        if self.cachedTokens > self.promptTokens:
            raise ValueError("缓存输入 token 不能超过提示词 token")
        if self.totalTokens != self.promptTokens + self.completionTokens:
            raise ValueError("总 token 必须等于提示词与输出 token 之和")
        return self


class UsageChargeResponse(BillingSchema):
    requestId: str
    chargedMicros: str
    balanceAfterMicros: str
    idempotent: bool
    billable: bool


class LedgerEntryResponse(BillingSchema):
    id: str
    type: str
    amountMicros: str
    balanceAfterMicros: str
    note: str | None
    createdAt: datetime


class BillingSummaryResponse(BillingSchema):
    username: str
    balanceMicros: str
    balanceCredits: str
    recentLedger: list[LedgerEntryResponse]


class TokenUsageBreakdown(BillingSchema):
    promptTokens: int
    cachedTokens: int
    completionTokens: int
    totalTokens: int


class BillingUsageResponse(BillingSchema):
    totalUsage: TokenUsageBreakdown
    monthlyUsage: TokenUsageBreakdown
