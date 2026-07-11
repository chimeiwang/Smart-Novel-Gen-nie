from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from ..errors import ApiError
from .grants import ModelGrantCodec, ModelGrantError
from .pricing import (
    MIN_OUTPUT_TOKEN_BUDGET,
    OUTPUT_MICROS_PER_TOKEN,
    UNCACHED_INPUT_MICROS_PER_TOKEN,
    format_credit_micros,
)
from .repository import (
    AuthorizationContext,
    BillingRepository,
    ChargeResult,
    ChargeUsage,
    InsufficientCreditsError,
    SummarySnapshot,
    UsageConflictError,
    UsageSnapshot,
)
from .schemas import (
    AuthorizeModelCallRequest,
    AuthorizeModelCallResponse,
    BillingSummaryResponse,
    BillingUsageResponse,
    LedgerEntryResponse,
    ModelGrantClaims,
    ReportModelUsageRequest,
    TokenUsageBreakdown,
    UsageChargeResponse,
)


class BillingRepositoryPort(Protocol):
    async def get_authorization_context(
        self, user_id: str, task_id: str, novel_id: str
    ) -> AuthorizationContext | None: ...
    async def get_balance(self, user_id: str) -> int | None: ...
    async def charge_usage(self, usage: ChargeUsage) -> ChargeResult: ...
    async def get_summary(self, user_id: str) -> SummarySnapshot | None: ...
    async def get_usage(
        self, user_id: str, month_start: datetime
    ) -> tuple[UsageSnapshot, UsageSnapshot]: ...


class BillingService:
    def __init__(
        self,
        repository: BillingRepository,
        grant_codec: ModelGrantCodec | None,
    ) -> None:
        self._repository = repository
        self._grant_codec = grant_codec

    async def authorize(
        self, request: AuthorizeModelCallRequest, *, now: datetime | None = None
    ) -> AuthorizeModelCallResponse:
        codec = self._require_codec()
        billable = _validate_provider_model(request.provider, request.model)
        context = await self._repository.get_authorization_context(
            request.userId, request.taskId, request.novelId
        )
        if context is None:
            raise ApiError(
                status_code=403, code="MODEL_CALL_FORBIDDEN", message="模型调用资源无权访问"
            )

        max_output = request.requestedMaxOutputTokens
        if billable:
            available = context.balance_micros - (
                request.estimatedPromptTokens * UNCACHED_INPUT_MICROS_PER_TOKEN
            )
            affordable = max(available, 0) // OUTPUT_MICROS_PER_TOKEN
            max_output = min(max_output, affordable)
            if max_output < MIN_OUTPUT_TOKEN_BUDGET:
                raise ApiError(
                    status_code=402,
                    code="INSUFFICIENT_CREDITS",
                    message="积分不足，请充值后再使用人工智能功能",
                )

        issued_at = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
        request_id = str(uuid4())
        claims = ModelGrantClaims(
            requestId=request_id,
            taskId=request.taskId,
            runId=request.runId,
            novelId=request.novelId,
            userId=request.userId,
            provider=request.provider,
            model=request.model,
            agentId=request.agentId,
            maxOutputTokens=max_output,
            billable=billable,
            iat=int(issued_at.timestamp()),
            exp=int(issued_at.timestamp()) + 120,
        )
        return AuthorizeModelCallResponse(
            requestId=request_id,
            provider=request.provider,
            model=request.model,
            maxOutputTokens=max_output,
            billable=billable,
            grantToken=codec.issue(claims),
            expiresAt=datetime.fromtimestamp(claims.exp, UTC),
        )

    async def charge(
        self, request: ReportModelUsageRequest, *, now: datetime | None = None
    ) -> UsageChargeResponse:
        try:
            claims = self._require_codec().verify(request.grantToken, now=now)
        except ModelGrantError:
            raise ApiError(
                status_code=401, code="MODEL_GRANT_INVALID", message="模型授权无效或已过期"
            ) from None
        if (
            request.requestId != claims.requestId
            or request.taskId != claims.taskId
            or request.runId != claims.runId
            or request.novelId != claims.novelId
        ):
            raise ApiError(
                status_code=409, code="MODEL_GRANT_MISMATCH", message="用量回调与模型授权不匹配"
            )
        if request.completionTokens > claims.maxOutputTokens:
            raise ApiError(
                status_code=409,
                code="MODEL_USAGE_EXCEEDS_GRANT",
                message="模型输出用量超过授权上限",
            )
        if not claims.billable:
            balance = await self._repository.get_balance(claims.userId)
            return UsageChargeResponse(
                requestId=claims.requestId,
                chargedMicros="0",
                balanceAfterMicros=str(balance or 0),
                idempotent=False,
                billable=False,
            )
        try:
            result = await self._repository.charge_usage(
                ChargeUsage(
                    request_id=claims.requestId,
                    user_id=claims.userId,
                    novel_id=claims.novelId,
                    model=claims.model,
                    agent_id=claims.agentId,
                    prompt_tokens=request.promptTokens,
                    cached_tokens=request.cachedTokens,
                    completion_tokens=request.completionTokens,
                    total_tokens=request.totalTokens,
                )
            )
        except InsufficientCreditsError:
            raise ApiError(
                status_code=402,
                code="INSUFFICIENT_CREDITS",
                message="积分不足，请充值后再使用人工智能功能",
            ) from None
        except UsageConflictError:
            raise ApiError(
                status_code=409, code="MODEL_USAGE_CONFLICT", message="相同请求标识的用量载荷不一致"
            ) from None
        return UsageChargeResponse(
            requestId=result.request_id,
            chargedMicros=str(result.charged_micros),
            balanceAfterMicros=str(result.balance_after_micros),
            idempotent=result.idempotent,
            billable=True,
        )

    async def summary(self, user_id: str) -> BillingSummaryResponse:
        snapshot = await self._repository.get_summary(user_id)
        if snapshot is None:
            raise ApiError(status_code=404, code="USER_NOT_FOUND", message="用户不存在")
        return BillingSummaryResponse(
            username=snapshot.username,
            balanceMicros=str(snapshot.balance_micros),
            balanceCredits=format_credit_micros(snapshot.balance_micros),
            recentLedger=[
                LedgerEntryResponse(
                    id=item.id,
                    type=item.type,
                    amountMicros=str(item.amount_micros),
                    balanceAfterMicros=str(item.balance_after_micros),
                    note=item.note,
                    createdAt=item.created_at,
                )
                for item in snapshot.entries
            ],
        )

    async def usage(self, user_id: str, *, now: datetime | None = None) -> BillingUsageResponse:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        month_start = datetime(current.year, current.month, 1)
        total, monthly = await self._repository.get_usage(user_id, month_start)
        return BillingUsageResponse(
            totalUsage=_usage_response(total),
            monthlyUsage=_usage_response(monthly),
        )

    def _require_codec(self) -> ModelGrantCodec:
        if self._grant_codec is None:
            raise ApiError(
                status_code=503, code="MODEL_GRANT_UNAVAILABLE", message="模型授权服务暂时不可用"
            )
        return self._grant_codec


def _validate_provider_model(provider: str, model: str) -> bool:
    if provider == "fake" and model == "fake":
        return False
    if provider == "openai_compatible" and model == "deepseek-v4-flash":
        return True
    raise ApiError(status_code=400, code="UNKNOWN_MODEL", message="模型提供方或模型不受支持")


def _usage_response(snapshot: UsageSnapshot) -> TokenUsageBreakdown:
    return TokenUsageBreakdown(
        promptTokens=snapshot.prompt_tokens,
        cachedTokens=snapshot.cached_tokens,
        completionTokens=snapshot.completion_tokens,
        totalTokens=snapshot.total_tokens,
    )
