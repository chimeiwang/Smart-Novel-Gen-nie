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
    TaskUsageCallSnapshot,
    UsageConflictError,
    UsageSnapshot,
)
from .request_ids import video_task_billing_request_prefix
from .schemas import (
    MODEL_GRANT_LIFETIME_SECONDS,
    AuthorizeModelCallRequest,
    AuthorizeModelCallResponse,
    BillingSummaryResponse,
    BillingUsageResponse,
    LedgerEntryResponse,
    ModelGrantClaims,
    ReportModelUsageRequest,
    TaskModelUsageCall,
    TaskModelUsageResponse,
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
    async def get_task_usage(
        self, user_id: str, task_id: str
    ) -> tuple[TaskUsageCallSnapshot, ...] | None: ...


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
        issued_at_seconds = int(issued_at.timestamp())
        request_id = (
            f"{video_task_billing_request_prefix(request.taskId)}{uuid4()}"
            if context.resource_kind == "video"
            else str(uuid4())
        )
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
            iat=issued_at_seconds,
            exp=issued_at_seconds + MODEL_GRANT_LIFETIME_SECONDS,
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
                    task_id=claims.taskId,
                    run_id=claims.runId,
                    model=claims.model,
                    agent_id=claims.agentId,
                    prompt_tokens=request.promptTokens,
                    cached_tokens=request.cachedTokens,
                    completion_tokens=request.completionTokens,
                    total_tokens=request.totalTokens,
                    prompt_cache_miss_tokens=request.promptCacheMissTokens,
                    reasoning_tokens=request.reasoningTokens,
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

    async def task_usage(self, user_id: str, task_id: str) -> TaskModelUsageResponse:
        calls = await self._repository.get_task_usage(user_id, task_id)
        if calls is None:
            raise ApiError(
                status_code=404,
                code="WRITING_TASK_NOT_FOUND",
                message="写作任务不存在或无权访问",
            )
        details_complete = bool(calls) and all(
            item.prompt_cache_miss_tokens is not None
            and item.reasoning_tokens is not None
            for item in calls
        )
        return TaskModelUsageResponse(
            taskId=task_id,
            requestCount=len(calls),
            promptTokens=sum(item.prompt_tokens for item in calls),
            cachedTokens=sum(item.cached_tokens for item in calls),
            promptCacheMissTokens=(
                sum(item.prompt_cache_miss_tokens or 0 for item in calls)
                if details_complete
                else None
            ),
            completionTokens=sum(item.completion_tokens for item in calls),
            reasoningTokens=(
                sum(item.reasoning_tokens or 0 for item in calls)
                if details_complete
                else None
            ),
            visibleCompletionTokens=(
                sum(item.completion_tokens - (item.reasoning_tokens or 0) for item in calls)
                if details_complete
                else None
            ),
            tokenDetailsComplete=details_complete,
            totalTokens=sum(item.total_tokens for item in calls),
            calls=[_task_usage_call_response(item) for item in calls],
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


def _task_usage_call_response(snapshot: TaskUsageCallSnapshot) -> TaskModelUsageCall:
    return TaskModelUsageCall(
        requestId=snapshot.request_id,
        runId=snapshot.run_id,
        agentId=snapshot.agent_id,
        model=snapshot.model,
        promptTokens=snapshot.prompt_tokens,
        cachedTokens=snapshot.cached_tokens,
        promptCacheMissTokens=snapshot.prompt_cache_miss_tokens,
        completionTokens=snapshot.completion_tokens,
        reasoningTokens=snapshot.reasoning_tokens,
        visibleCompletionTokens=(
            snapshot.completion_tokens - snapshot.reasoning_tokens
            if snapshot.prompt_cache_miss_tokens is not None
            and snapshot.reasoning_tokens is not None
            else None
        ),
        tokenDetailsComplete=(
            snapshot.prompt_cache_miss_tokens is not None
            and snapshot.reasoning_tokens is not None
        ),
        totalTokens=snapshot.total_tokens,
        createdAt=snapshot.created_at,
    )
