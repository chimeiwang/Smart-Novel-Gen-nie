package cn.inkforge.core.billing.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.AuthorizeModelCallRequest;
import cn.inkforge.contracts.api.ReportModelUsageRequest;
import cn.inkforge.core.billing.domain.ModelGrantCodec;
import cn.inkforge.core.platform.http.ApiException;
import java.security.KeyPairGenerator;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class BillingServiceTest {

    private static final Instant NOW = Instant.parse("2026-08-25T06:00:00Z");
    private MemoryRepository repository;
    private BillingService service;

    @BeforeEach
    void setUp() throws Exception {
        repository = new MemoryRepository();
        var keyPair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        service = new BillingService(
                repository,
                new ModelGrantCodec(
                        keyPair.getPrivate(), keyPair.getPublic(), new ObjectMapper()),
                Clock.fixed(NOW, ZoneOffset.UTC),
                () -> "uuid-fixed");
    }

    @Test
    void 授权必须校验资源模型余额并缩小输出上限() {
        repository.authorization = new AuthorizationContext(500_000L, "default");
        var response = service.authorize(authorize(
                "openai_compatible", "deepseek-v4-flash", 100, 500));

        assertThat(response.getMaxOutputTokens()).isEqualTo(200);
        assertThat(response.getBillable()).isTrue();
        assertThat(response.getRequestId()).isEqualTo("uuid-fixed");
        assertThat(response.getExpiresAt())
                .isEqualTo(OffsetDateTime.ofInstant(NOW.plusSeconds(1_200), ZoneOffset.UTC));

        repository.authorization = new AuthorizationContext(100_000L, "default");
        assertCode(
                () -> service.authorize(authorize(
                        "openai_compatible", "deepseek-v4-flash", 100, 500)),
                "INSUFFICIENT_CREDITS");
        assertCode(
                () -> service.authorize(authorize("openai_compatible", "unknown", 0, 500)),
                "UNKNOWN_MODEL");
        repository.authorization = null;
        assertCode(
                () -> service.authorize(authorize("fake", "fake", 0, 500)),
                "MODEL_CALL_FORBIDDEN");
    }

    @Test
    void fake授权不计费而视频请求标识使用匿名前缀() {
        repository.authorization = new AuthorizationContext(0, "video");
        var response = service.authorize(authorize("fake", "fake", 999, 4_096));

        assertThat(response.getBillable()).isFalse();
        assertThat(response.getMaxOutputTokens()).isEqualTo(4_096);
        assertThat(response.getRequestId())
                .matches("video-task-[0-9a-f]{32}-uuid-fixed")
                .doesNotContain("task-1");
    }

    @Test
    void 用量结算必须验证grant身份上限并把完整诊断传给原子仓储() {
        repository.authorization = new AuthorizationContext(2_000_000L, "default");
        var authorization = service.authorize(authorize(
                "openai_compatible", "deepseek-v4-flash", 0, 500));
        ReportModelUsageRequest request = usage(
                authorization.getRequestId(), authorization.getGrantToken(), 100, 20, 25, 125)
                .promptCacheMissTokens(80)
                .reasoningTokens(5);
        repository.chargeResult = new ChargeResult(
                authorization.getRequestId(), 130_400L, 1_869_600L, false);

        var charged = service.charge(request);

        assertThat(charged.getChargedMicros()).isEqualTo("130400");
        assertThat(repository.lastCharge.promptCacheMissTokens()).isEqualTo(80);
        assertThat(repository.lastCharge.reasoningTokens()).isEqualTo(5);
        assertThat(repository.lastCharge.taskId()).isEqualTo("task-1");

        assertCode(
                () -> service.charge(usage(
                        "another-request", authorization.getGrantToken(), 1, 0, 1, 2)),
                "MODEL_GRANT_MISMATCH");
        assertCode(
                () -> service.charge(usage(
                        authorization.getRequestId(),
                        authorization.getGrantToken(),
                        1,
                        0,
                        501,
                        502)),
                "MODEL_USAGE_EXCEEDS_GRANT");
        assertCode(
                () -> service.charge(usage(
                        authorization.getRequestId(),
                        authorization.getGrantToken(),
                        1,
                        2,
                        0,
                        1)),
                "VALIDATION_ERROR");
    }

    @Test
    void 零调用任务诊断不完整而完整明细派生可见输出() {
        repository.taskCalls = List.of();
        var empty = service.taskUsage("user-1", "task-1");
        assertThat(empty.getRequestCount()).isZero();
        assertThat(empty.getTokenDetailsComplete()).isFalse();
        assertThat(empty.getReasoningTokens()).isNull();

        repository.taskCalls = List.of(
                new TaskUsageCallSnapshot(
                        "request-1",
                        "run-1",
                        "写作",
                        "deepseek-v4-flash",
                        100,
                        20,
                        80,
                        25,
                        5,
                        125,
                        OffsetDateTime.parse("2026-08-25T06:00:00Z")),
                new TaskUsageCallSnapshot(
                        "request-2",
                        "run-1",
                        null,
                        "deepseek-v4-flash",
                        50,
                        10,
                        40,
                        20,
                        4,
                        70,
                        OffsetDateTime.parse("2026-08-25T06:01:00Z")));
        var complete = service.taskUsage("user-1", "task-1");
        assertThat(complete.getTokenDetailsComplete()).isTrue();
        assertThat(complete.getPromptCacheMissTokens()).isEqualTo(120);
        assertThat(complete.getReasoningTokens()).isEqualTo(9);
        assertThat(complete.getVisibleCompletionTokens()).isEqualTo(36);
        assertThat(complete.getCalls().getFirst().getVisibleCompletionTokens()).isEqualTo(20);
    }

    private static AuthorizeModelCallRequest authorize(
            String provider, String model, int prompt, int output) {
        return new AuthorizeModelCallRequest(
                "写作",
                prompt,
                model,
                "novel-1",
                AuthorizeModelCallRequest.ProviderEnum.fromValue(provider),
                output,
                "run-1",
                "task-1",
                "user-1");
    }

    private static ReportModelUsageRequest usage(
            String requestId,
            String token,
            int prompt,
            int cached,
            int completion,
            int total) {
        return new ReportModelUsageRequest(
                cached,
                completion,
                token,
                "novel-1",
                prompt,
                requestId,
                "run-1",
                "task-1",
                total);
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo(code));
    }

    private static final class MemoryRepository implements BillingRepository {
        private AuthorizationContext authorization;
        private ChargeUsage lastCharge;
        private ChargeResult chargeResult;
        private List<TaskUsageCallSnapshot> taskCalls = List.of();

        @Override
        public AuthorizationContext authorizationContext(
                String userId, String taskId, String novelId) {
            return authorization;
        }

        @Override
        public Long balance(String userId) {
            return 123L;
        }

        @Override
        public ChargeResult charge(ChargeUsage usage) {
            lastCharge = usage;
            return chargeResult;
        }

        @Override
        public SummarySnapshot summary(String userId) {
            return null;
        }

        @Override
        public UsagePair usage(String userId, OffsetDateTime monthStart) {
            return new UsagePair(UsageSnapshot.ZERO, UsageSnapshot.ZERO);
        }

        @Override
        public List<TaskUsageCallSnapshot> taskUsage(String userId, String taskId) {
            return taskCalls;
        }
    }
}
