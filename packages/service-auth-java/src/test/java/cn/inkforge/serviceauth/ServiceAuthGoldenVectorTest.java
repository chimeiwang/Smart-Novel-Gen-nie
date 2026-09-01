package cn.inkforge.serviceauth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.InputStream;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.spec.EdECPrivateKeySpec;
import java.security.spec.NamedParameterSpec;
import java.time.Instant;
import java.time.Duration;
import java.util.Base64;
import java.util.List;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class ServiceAuthGoldenVectorTest {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    @org.junit.jupiter.api.Test
    void Java签发结果必须与Python逐字节一致() throws Exception {
        JsonNode fixture = fixture();
        PrivateKey privateKey = KeyFactory.getInstance("Ed25519")
                .generatePrivate(new EdECPrivateKeySpec(
                        NamedParameterSpec.ED25519,
                        java.util.HexFormat.of().parseHex(fixture.path("testOnlyPrivateKeySeedHex").asString())));
        ServiceTokenSigner signer = new ServiceTokenSigner(
                privateKey,
                "inkforge-core-fixture",
                "core-api",
                "inkforge-agent-fixture",
                "migration-fixture-v1",
                120,
                List.of(ServiceScope.TOOL_READ));

        SignedServiceRequest signed = signer.sign(new ServiceRequest(
                Base64.getDecoder().decode(fixture.path("bodyBase64").asString()),
                "POST",
                "/internal/v1/tools/get_novel_summary",
                Base64.getDecoder().decode(fixture.path("queryStringBase64").asString()),
                "migration-fixture-request-0001",
                List.of(ServiceScope.TOOL_READ),
                "task-fixture",
                "run-fixture",
                "novel-fixture",
                Instant.ofEpochSecond(1_800_000_000L),
                120,
                "jti-migration-fixture-0001"));

        assertThat(signed.token()).isEqualTo(fixture.path("token").asString());
        assertThat(signed.headers()).containsAllEntriesOf(OBJECT_MAPPER.convertValue(
                fixture.path("headers"),
                new tools.jackson.core.type.TypeReference<>() {}));
    }

    @org.junit.jupiter.api.Test
    void Java验签必须接受Python令牌并校验全部绑定() throws Exception {
        JsonNode fixture = fixture();
        InMemoryReplayStore replayStore = new InMemoryReplayStore();
        ServiceTokenVerifier verifier = ServiceTokenVerifier.fromJwks(
                jwks(),
                "inkforge-core-fixture",
                "core-api",
                "inkforge-agent-fixture",
                replayStore,
                ReplayPolicy.ALL_SCOPES,
                10,
                List.of(ServiceScope.TOOL_READ));

        VerifiedServiceRequest verified = verifier.verify(new ServiceVerificationRequest(
                fixture.path("token").asString(),
                Base64.getDecoder().decode(fixture.path("bodyBase64").asString()),
                "POST",
                "/internal/v1/tools/get_novel_summary",
                Base64.getDecoder().decode(fixture.path("queryStringBase64").asString()),
                "migration-fixture-request-0001",
                "1800000000",
                fixture.path("claims").path("body_sha256").asString(),
                ServiceScope.TOOL_READ,
                "task-fixture",
                "run-fixture",
                "novel-fixture",
                Instant.ofEpochSecond(1_800_000_000L)));

        assertThat(verified.claims().jti()).isEqualTo("jti-migration-fixture-0001");
        assertThat(replayStore.consumed()).containsExactly("jti-migration-fixture-0001");
    }

    @org.junit.jupiter.api.Test
    void 摘要篡改与重复令牌必须返回稳定错误码() throws Exception {
        JsonNode fixture = fixture();
        InMemoryReplayStore replayStore = new InMemoryReplayStore();
        ServiceTokenVerifier verifier = ServiceTokenVerifier.fromJwks(
                jwks(),
                "inkforge-core-fixture",
                "core-api",
                "inkforge-agent-fixture",
                replayStore,
                ReplayPolicy.ALL_SCOPES,
                10,
                List.of(ServiceScope.TOOL_READ));
        ServiceVerificationRequest valid = request(fixture, fixture.path("claims").path("body_sha256").asString());

        assertThatThrownBy(() -> verifier.verify(request(fixture, "0".repeat(64))))
                .isInstanceOf(ServiceAuthException.class)
                .extracting(error -> ((ServiceAuthException) error).code())
                .isEqualTo("SERVICE_REQUEST_BINDING_INVALID");
        verifier.verify(valid);
        assertThatThrownBy(() -> verifier.verify(valid))
                .isInstanceOf(ServiceAuthException.class)
                .extracting(error -> ((ServiceAuthException) error).code())
                .isEqualTo("SERVICE_TOKEN_REPLAYED");
    }

    @org.junit.jupiter.api.Test
    void 用户级Execution令牌允许null小说并固定Step资源身份() throws Exception {
        byte[] body = "{\"runId\":\"run-user-1\",\"novelId\":null,\"stepId\":\"step-user-1\"}"
                .getBytes(java.nio.charset.StandardCharsets.UTF_8);
        ServiceTokenSigner signer = executionSigner(List.of(ServiceScope.EXECUTION_SUBMIT));
        SignedServiceRequest signed = signer.sign(executionRequest(
                body,
                List.of(ServiceScope.EXECUTION_SUBMIT),
                null,
                "jti-user-execution"));
        ServiceTokenVerifier verifier = ServiceTokenVerifier.fromJwks(
                jwks(),
                "inkforge-core-fixture",
                "core-api",
                "inkforge-agent-fixture",
                new InMemoryReplayStore(),
                ReplayPolicy.ALL_SCOPES,
                10,
                List.of(ServiceScope.EXECUTION_SUBMIT));

        VerifiedServiceRequest verified = verifier.verify(executionVerification(
                signed,
                body,
                ServiceScope.EXECUTION_SUBMIT,
                null));

        assertThat(verified.claims().taskId()).isEqualTo("step-user-1");
        assertThat(verified.claims().runId()).isEqualTo("run-user-1");
        assertThat(verified.claims().novelId()).isNull();
    }

    @org.junit.jupiter.api.Test
    void 计费对账使用独立写Scope并允许null小说且必须防重放() throws Exception {
        byte[] body = "{\"runId\":\"run-user-1\",\"novelId\":null,\"stepId\":\"step-user-1\"}"
                .getBytes(java.nio.charset.StandardCharsets.UTF_8);
        ServiceTokenSigner signer = executionSigner(List.of(ServiceScope.BILLING_RECONCILE));
        SignedServiceRequest signed = signer.sign(executionRequest(
                body,
                List.of(ServiceScope.BILLING_RECONCILE),
                null,
                "jti-billing-reconcile"));
        ServiceTokenVerifier verifier = ServiceTokenVerifier.fromJwks(
                jwks(),
                "inkforge-core-fixture",
                "core-api",
                "inkforge-agent-fixture",
                new InMemoryReplayStore(),
                ReplayPolicy.WRITE_SCOPES_ONLY,
                10,
                List.of(ServiceScope.BILLING_RECONCILE));
        ServiceVerificationRequest request = executionVerification(
                signed,
                body,
                ServiceScope.BILLING_RECONCILE,
                null);

        assertThat(verifier.verify(request).claims().scope())
                .containsExactly(ServiceScope.BILLING_RECONCILE);
        assertThatThrownBy(() -> verifier.verify(request))
                .isInstanceOf(ServiceAuthException.class)
                .extracting(error -> ((ServiceAuthException) error).code())
                .isEqualTo("SERVICE_TOKEN_REPLAYED");
    }

    @org.junit.jupiter.api.Test
    void 旧Scope与混合Scope不得放宽null小说约束() throws Exception {
        byte[] body = "{}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        List<List<ServiceScope>> invalidScopes = List.of(
                List.of(ServiceScope.AGENT_RUN),
                List.of(ServiceScope.EXECUTION_SUBMIT, ServiceScope.AGENT_RUN));

        for (List<ServiceScope> scopes : invalidScopes) {
            ServiceTokenSigner signer = executionSigner(scopes);
            assertThatThrownBy(() -> signer.sign(executionRequest(
                            body,
                            scopes,
                            null,
                            "jti-null-novel")))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("纯 execution scope");
            assertThatThrownBy(() -> claims(scopes, null))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("纯 execution scope");
        }
    }

    @org.junit.jupiter.api.Test
    void Execution正文小说与Jwt小说不一致必须拒绝() throws Exception {
        byte[] body = "{\"runId\":\"run-user-1\",\"novelId\":\"novel-body\",\"stepId\":\"step-user-1\"}"
                .getBytes(java.nio.charset.StandardCharsets.UTF_8);
        ServiceTokenSigner signer = executionSigner(List.of(ServiceScope.EXECUTION_SUBMIT));
        SignedServiceRequest signed = signer.sign(executionRequest(
                body,
                List.of(ServiceScope.EXECUTION_SUBMIT),
                null,
                "jti-resource-mismatch"));
        ServiceTokenVerifier verifier = ServiceTokenVerifier.fromJwks(
                jwks(),
                "inkforge-core-fixture",
                "core-api",
                "inkforge-agent-fixture",
                new InMemoryReplayStore(),
                ReplayPolicy.ALL_SCOPES,
                10,
                List.of(ServiceScope.EXECUTION_SUBMIT));

        assertThatThrownBy(() -> verifier.verify(executionVerification(
                        signed,
                        body,
                        ServiceScope.EXECUTION_SUBMIT,
                        "novel-body")))
                .isInstanceOf(ServiceAuthException.class)
                .satisfies(error -> assertThat(((ServiceAuthException) error).code())
                        .isEqualTo("SERVICE_RESOURCE_MISMATCH"));
    }

    @org.junit.jupiter.api.Test
    void Redis重放适配必须使用固定前缀与300秒TTL() {
        java.util.List<Object> calls = new java.util.ArrayList<>();
        RedisReplayStore store = new RedisReplayStore((key, value, ttl) -> {
            calls.add(java.util.List.of(key, value, ttl));
            return true;
        }, "service-auth:replay:");

        assertThat(store.consume("jti-1", 300)).isTrue();
        assertThat(calls).containsExactly(
                java.util.List.of("service-auth:replay:jti-1", "1", Duration.ofSeconds(300)));

        RedisReplayStore duplicate = new RedisReplayStore((key, value, ttl) -> false, "prefix:");
        assertThat(duplicate.consume("jti-1", 300)).isFalse();
    }

    @org.junit.jupiter.api.Test
    void 重放存储故障必须关闭写请求且不泄露底层异常() throws Exception {
        JsonNode fixture = fixture();
        ServiceTokenVerifier verifier = ServiceTokenVerifier.fromJwks(
                jwks(),
                "inkforge-core-fixture",
                "core-api",
                "inkforge-agent-fixture",
                (jti, ttl) -> {
                    throw new IllegalStateException("包含敏感 Redis 地址");
                },
                ReplayPolicy.ALL_SCOPES,
                10,
                List.of(ServiceScope.TOOL_READ));

        assertThatThrownBy(() -> verifier.verify(
                        request(fixture, fixture.path("claims").path("body_sha256").asString())))
                .isInstanceOf(ServiceAuthException.class)
                .satisfies(error -> {
                    ServiceAuthException authError = (ServiceAuthException) error;
                    assertThat(authError.code()).isEqualTo("SERVICE_REPLAY_STORE_UNAVAILABLE");
                    assertThat(authError).hasMessageNotContaining("敏感 Redis 地址");
                    assertThat(authError.getCause()).isNull();
                });
    }

    private ServiceVerificationRequest request(JsonNode fixture, String bodyDigest) {
        return new ServiceVerificationRequest(
                fixture.path("token").asString(),
                Base64.getDecoder().decode(fixture.path("bodyBase64").asString()),
                "POST",
                "/internal/v1/tools/get_novel_summary",
                Base64.getDecoder().decode(fixture.path("queryStringBase64").asString()),
                "migration-fixture-request-0001",
                "1800000000",
                bodyDigest,
                ServiceScope.TOOL_READ,
                "task-fixture",
                "run-fixture",
                "novel-fixture",
                Instant.ofEpochSecond(1_800_000_000L));
    }

    private ServiceTokenSigner executionSigner(List<ServiceScope> allowedScopes) throws Exception {
        JsonNode fixture = fixture();
        PrivateKey privateKey = KeyFactory.getInstance("Ed25519")
                .generatePrivate(new EdECPrivateKeySpec(
                        NamedParameterSpec.ED25519,
                        java.util.HexFormat.of().parseHex(
                                fixture.path("testOnlyPrivateKeySeedHex").asString())));
        return new ServiceTokenSigner(
                privateKey,
                "inkforge-core-fixture",
                "core-api",
                "inkforge-agent-fixture",
                "migration-fixture-v1",
                120,
                allowedScopes);
    }

    private ServiceRequest executionRequest(
            byte[] body,
            List<ServiceScope> scopes,
            String novelId,
            String jti) {
        return new ServiceRequest(
                body,
                "POST",
                "/internal/v1/execution/steps",
                new byte[0],
                "idem-user-execution",
                scopes,
                "step-user-1",
                "run-user-1",
                novelId,
                Instant.ofEpochSecond(1_800_000_000L),
                120,
                jti);
    }

    private ServiceVerificationRequest executionVerification(
            SignedServiceRequest signed,
            byte[] body,
            ServiceScope requiredScope,
            String novelId) {
        return new ServiceVerificationRequest(
                signed.token(),
                body,
                "POST",
                "/internal/v1/execution/steps",
                new byte[0],
                "idem-user-execution",
                "1800000000",
                signed.headers().get("X-InkForge-Body-SHA256"),
                requiredScope,
                "step-user-1",
                "run-user-1",
                novelId,
                Instant.ofEpochSecond(1_800_000_000L));
    }

    private ServiceJwtClaims claims(List<ServiceScope> scopes, String novelId) {
        return new ServiceJwtClaims(
                "inkforge-core-fixture",
                "core-api",
                "inkforge-agent-fixture",
                scopes,
                "step-user-1",
                "run-user-1",
                novelId,
                "jti-claims",
                1_800_000_000L,
                1_800_000_120L,
                "0".repeat(64),
                "0".repeat(64),
                "idem-user-execution",
                1_800_000_000L,
                "POST",
                "/internal/v1/execution/steps");
    }

    private JsonNode fixture() throws Exception {
        return read("/service-auth-fixtures/golden-request.json");
    }

    private JsonNode jwks() throws Exception {
        return read("/service-auth-fixtures/public-jwks.json");
    }

    private JsonNode read(String path) throws Exception {
        try (InputStream input = getClass().getResourceAsStream(path)) {
            if (input == null) {
                throw new IllegalStateException("缺少测试向量：" + path);
            }
            return OBJECT_MAPPER.readTree(input);
        }
    }
}
