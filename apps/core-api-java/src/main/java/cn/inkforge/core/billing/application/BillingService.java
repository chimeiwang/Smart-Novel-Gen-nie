package cn.inkforge.core.billing.application;

import cn.inkforge.contracts.api.AuthorizeModelCallRequest;
import cn.inkforge.contracts.api.AuthorizeModelCallResponse;
import cn.inkforge.contracts.api.BillingSummaryResponse;
import cn.inkforge.contracts.api.BillingUsageResponse;
import cn.inkforge.contracts.api.LedgerEntryResponse;
import cn.inkforge.contracts.api.ReportModelUsageRequest;
import cn.inkforge.contracts.api.TaskModelUsageCall;
import cn.inkforge.contracts.api.TaskModelUsageResponse;
import cn.inkforge.contracts.api.TokenUsageBreakdown;
import cn.inkforge.contracts.api.UsageChargeResponse;
import cn.inkforge.core.billing.domain.BillingPricing;
import cn.inkforge.core.billing.domain.ModelGrantClaims;
import cn.inkforge.core.billing.domain.ModelGrantCodec;
import cn.inkforge.core.billing.domain.ModelGrantException;
import cn.inkforge.core.platform.http.ApiException;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Objects;
import java.util.function.Supplier;
import org.openapitools.jackson.nullable.JsonNullable;

/** 模型授权、原子结算和浏览器账单查询的应用服务。 */
public final class BillingService {

    private final BillingRepository repository;
    private final ModelGrantCodec grantCodec;
    private final Clock clock;
    private final Supplier<String> requestIdSupplier;

    public BillingService(
            BillingRepository repository,
            ModelGrantCodec grantCodec,
            Clock clock,
            Supplier<String> requestIdSupplier) {
        this.repository = Objects.requireNonNull(repository);
        this.grantCodec = grantCodec;
        this.clock = Objects.requireNonNull(clock);
        this.requestIdSupplier = Objects.requireNonNull(requestIdSupplier);
    }

    public AuthorizeModelCallResponse authorize(AuthorizeModelCallRequest request) {
        ModelGrantCodec codec = requireCodec();
        String provider = request.getProvider().getValue();
        boolean billable = validateProviderModel(provider, request.getModel());
        AuthorizationContext context = repository.authorizationContext(
                request.getUserId(), request.getTaskId(), request.getNovelId());
        if (context == null) {
            throw new ApiException(
                    403,
                    "MODEL_CALL_FORBIDDEN",
                    "模型调用资源无权访问");
        }
        int maxOutputTokens = request.getRequestedMaxOutputTokens();
        if (billable) {
            long available = context.balanceMicros()
                    - request.getEstimatedPromptTokens()
                            * BillingPricing.UNCACHED_INPUT_MICROS_PER_TOKEN;
            long affordable = Math.max(available, 0)
                    / BillingPricing.OUTPUT_MICROS_PER_TOKEN;
            maxOutputTokens = (int) Math.min(maxOutputTokens, affordable);
            if (maxOutputTokens < BillingPricing.MIN_OUTPUT_TOKEN_BUDGET) {
                throw insufficient();
            }
        }
        long issuedAt = clock.instant().getEpochSecond();
        String randomId = requestIdSupplier.get();
        String requestId = "video".equals(context.resourceKind())
                ? BillingPricing.videoRequestPrefix(request.getTaskId()) + randomId
                : randomId;
        ModelGrantClaims claims = new ModelGrantClaims(
                requestId,
                request.getTaskId(),
                request.getRunId(),
                request.getNovelId(),
                request.getUserId(),
                provider,
                request.getModel(),
                request.getAgentId(),
                maxOutputTokens,
                billable,
                issuedAt,
                issuedAt + ModelGrantClaims.LIFETIME_SECONDS);
        AuthorizeModelCallResponse response = new AuthorizeModelCallResponse();
        response.setRequestId(requestId);
        response.setProvider(AuthorizeModelCallResponse.ProviderEnum.fromValue(provider));
        response.setModel(request.getModel());
        response.setMaxOutputTokens(maxOutputTokens);
        response.setBillable(billable);
        response.setGrantToken(codec.issue(claims));
        response.setExpiresAt(OffsetDateTime.ofInstant(
                Instant.ofEpochSecond(claims.expiresAt()), ZoneOffset.UTC));
        return response;
    }

    public UsageChargeResponse charge(ReportModelUsageRequest request) {
        Integer promptCacheMiss = nullable(request.getPromptCacheMissTokens());
        Integer reasoning = nullable(request.getReasoningTokens());
        validateUsage(request, promptCacheMiss, reasoning);
        ModelGrantClaims claims;
        try {
            claims = requireCodec().verify(request.getGrantToken(), clock.instant());
        } catch (ModelGrantException exception) {
            throw new ApiException(
                    401,
                    "MODEL_GRANT_INVALID",
                    "模型授权无效或已过期");
        }
        if (!request.getRequestId().equals(claims.requestId())
                || !request.getTaskId().equals(claims.taskId())
                || !request.getRunId().equals(claims.runId())
                || !request.getNovelId().equals(claims.novelId())) {
            throw new ApiException(
                    409,
                    "MODEL_GRANT_MISMATCH",
                    "用量回调与模型授权不匹配");
        }
        if (request.getCompletionTokens() > claims.maxOutputTokens()) {
            throw new ApiException(
                    409,
                    "MODEL_USAGE_EXCEEDS_GRANT",
                    "模型输出用量超过授权上限");
        }
        if (!claims.billable()) {
            Long balance = repository.balance(claims.userId());
            return response(claims.requestId(), 0, balance == null ? 0 : balance, false, false);
        }
        try {
            ChargeResult result = repository.charge(new ChargeUsage(
                    claims.requestId(),
                    claims.userId(),
                    claims.novelId(),
                    claims.taskId(),
                    claims.runId(),
                    claims.model(),
                    claims.agentId(),
                    request.getPromptTokens(),
                    request.getCachedTokens(),
                    request.getCompletionTokens(),
                    request.getTotalTokens(),
                    promptCacheMiss,
                    reasoning));
            return response(
                    result.requestId(),
                    result.chargedMicros(),
                    result.balanceAfterMicros(),
                    result.idempotent(),
                    true);
        } catch (InsufficientCreditsException exception) {
            throw insufficient();
        } catch (UsageConflictException exception) {
            throw new ApiException(
                    409,
                    "MODEL_USAGE_CONFLICT",
                    "相同请求标识的用量载荷不一致");
        }
    }

    public BillingSummaryResponse summary(String userId) {
        SummarySnapshot snapshot = repository.summary(userId);
        if (snapshot == null) {
            throw new ApiException(404, "USER_NOT_FOUND", "用户不存在");
        }
        List<LedgerEntryResponse> entries = snapshot.entries().stream()
                .map(BillingService::ledger)
                .toList();
        return new BillingSummaryResponse(
                BillingPricing.formatCreditMicros(snapshot.balanceMicros()),
                Long.toString(snapshot.balanceMicros()),
                entries,
                snapshot.username());
    }

    public BillingUsageResponse usage(String userId) {
        OffsetDateTime now = OffsetDateTime.ofInstant(clock.instant(), ZoneOffset.UTC);
        OffsetDateTime monthStart = OffsetDateTime.of(
                now.getYear(), now.getMonthValue(), 1, 0, 0, 0, 0, ZoneOffset.UTC);
        UsagePair pair = repository.usage(userId, monthStart);
        return new BillingUsageResponse(
                breakdown(pair.monthly()), breakdown(pair.total()));
    }

    public TaskModelUsageResponse taskUsage(String userId, String taskId) {
        List<TaskUsageCallSnapshot> calls = repository.taskUsage(userId, taskId);
        if (calls == null) {
            throw new ApiException(
                    404,
                    "WRITING_TASK_NOT_FOUND",
                    "写作任务不存在或无权访问");
        }
        boolean detailsComplete = !calls.isEmpty() && calls.stream().allMatch(call ->
                call.promptCacheMissTokens() != null && call.reasoningTokens() != null);
        TaskModelUsageResponse response = new TaskModelUsageResponse();
        response.setTaskId(taskId);
        response.setRequestCount(calls.size());
        response.setPromptTokens(sum(calls, TaskUsageCallSnapshot::promptTokens));
        response.setCachedTokens(sum(calls, TaskUsageCallSnapshot::cachedTokens));
        response.setPromptCacheMissTokens(detailsComplete
                ? sum(calls, call -> call.promptCacheMissTokens())
                : null);
        response.setCompletionTokens(sum(calls, TaskUsageCallSnapshot::completionTokens));
        response.setReasoningTokens(detailsComplete
                ? sum(calls, call -> call.reasoningTokens())
                : null);
        response.setVisibleCompletionTokens(detailsComplete
                ? sum(calls, call -> call.completionTokens() - call.reasoningTokens())
                : null);
        response.setTokenDetailsComplete(detailsComplete);
        response.setTotalTokens(sum(calls, TaskUsageCallSnapshot::totalTokens));
        response.setCalls(calls.stream().map(BillingService::taskCall).toList());
        return response;
    }

    private ModelGrantCodec requireCodec() {
        if (grantCodec == null) {
            throw new ApiException(
                    503,
                    "MODEL_GRANT_UNAVAILABLE",
                    "模型授权服务暂时不可用");
        }
        return grantCodec;
    }

    private static boolean validateProviderModel(String provider, String model) {
        if ("fake".equals(provider) && "fake".equals(model)) {
            return false;
        }
        if ("openai_compatible".equals(provider)
                && "deepseek-v4-flash".equals(model)) {
            return true;
        }
        throw new ApiException(
                400,
                "UNKNOWN_MODEL",
                "模型提供方或模型不受支持");
    }

    private static void validateUsage(
            ReportModelUsageRequest request,
            Integer promptCacheMiss,
            Integer reasoning) {
        boolean invalid = request.getCachedTokens() > request.getPromptTokens()
                || (promptCacheMiss != null
                        && request.getCachedTokens() + promptCacheMiss
                                != request.getPromptTokens())
                || (reasoning != null && reasoning > request.getCompletionTokens())
                || request.getTotalTokens()
                        != request.getPromptTokens() + request.getCompletionTokens();
        if (invalid) {
            throw new ApiException(
                    422,
                    "VALIDATION_ERROR",
                    "请求参数校验失败");
        }
    }

    private static UsageChargeResponse response(
            String requestId,
            long charged,
            long balance,
            boolean idempotent,
            boolean billable) {
        return new UsageChargeResponse(
                Long.toString(balance),
                billable,
                Long.toString(charged),
                idempotent,
                requestId);
    }

    private static LedgerEntryResponse ledger(LedgerSnapshot value) {
        return new LedgerEntryResponse(
                Long.toString(value.amountMicros()),
                Long.toString(value.balanceAfterMicros()),
                value.createdAt(),
                value.id(),
                value.note(),
                value.type());
    }

    private static TokenUsageBreakdown breakdown(UsageSnapshot value) {
        return new TokenUsageBreakdown(
                value.cachedTokens(),
                value.completionTokens(),
                value.promptTokens(),
                value.totalTokens());
    }

    private static TaskModelUsageCall taskCall(TaskUsageCallSnapshot value) {
        boolean complete = value.promptCacheMissTokens() != null
                && value.reasoningTokens() != null;
        TaskModelUsageCall result = new TaskModelUsageCall();
        result.setRequestId(value.requestId());
        result.setRunId(value.runId());
        result.setAgentId(value.agentId());
        result.setModel(value.model());
        result.setPromptTokens(value.promptTokens());
        result.setCachedTokens(value.cachedTokens());
        result.setPromptCacheMissTokens(value.promptCacheMissTokens());
        result.setCompletionTokens(value.completionTokens());
        result.setReasoningTokens(value.reasoningTokens());
        result.setVisibleCompletionTokens(complete
                ? value.completionTokens() - value.reasoningTokens()
                : null);
        result.setTokenDetailsComplete(complete);
        result.setTotalTokens(value.totalTokens());
        result.setCreatedAt(value.createdAt());
        return result;
    }

    private static int sum(
            List<TaskUsageCallSnapshot> calls,
            java.util.function.ToIntFunction<TaskUsageCallSnapshot> value) {
        return calls.stream().mapToInt(value).sum();
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }

    private static ApiException insufficient() {
        return new ApiException(
                402,
                "INSUFFICIENT_CREDITS",
                "积分不足，请充值后再使用人工智能功能");
    }
}
