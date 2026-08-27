package cn.inkforge.core.identity.api;

import static cn.inkforge.core.db.generated.Tables.CREDITLEDGER;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.identity.application.PhoneAuthRateLimiter;
import cn.inkforge.core.identity.application.PhoneCaptchaVerifier;
import cn.inkforge.core.identity.application.PhoneSmsProvider;
import cn.inkforge.core.platform.db.CoreDatabase;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.atomic.AtomicInteger;
import org.jooq.impl.DSL;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest(
        classes = CoreApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(PhoneIdentityRuntimeIntegrationTest.FakeProviderConfiguration.class)
class PhoneIdentityRuntimeIntegrationTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("DATABASE_URL", PhoneIdentityRuntimeIntegrationTest::databaseUrl);
        registry.add("REDIS_URL", () -> "redis://"
                + REDIS.getHost()
                + ":"
                + REDIS.getMappedPort(6379)
                + "/0");
        registry.add("JWT_SECRET", () -> "手机号运行时测试会话密钥-长度超过三十二字节-不可用于生产");
        registry.add("ENVIRONMENT", () -> "test");
        registry.add("VIDEO_PREVIEW_ENABLED", () -> "true");
        registry.add("PHONE_AUTH_ENABLED", () -> "true");
        registry.add("PHONE_AUTH_SEND_ENABLED", () -> "true");
        registry.add("USERNAME_REGISTRATION_ENABLED", () -> "false");
        registry.add("PHONE_AUTH_HMAC_SECRET", () -> "phone-runtime-hmac-secret-0000000000000000");
        registry.add("ALIYUN_ACCESS_KEY_ID", () -> "test-access-key-id");
        registry.add("ALIYUN_ACCESS_KEY_SECRET", () -> "test-access-key-secret");
        registry.add("ALIYUN_PNVS_SIGN_NAME", () -> "测试签名");
        registry.add("ALIYUN_PNVS_TEMPLATE_CODE", () -> "100001");
        registry.add("ALIYUN_CAPTCHA_PREFIX", () -> "test-prefix");
        registry.add("ALIYUN_CAPTCHA_SCENE_ID", () -> "test-scene");
    }

    @BeforeAll
    static void restoreSchemaAndApplyNamedMigration() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("migrations/20260827_user_phone_identity.sql"),
                "/tmp/20260827_user_phone_identity.sql");
        executeSql("/tmp/novelwriterdev-schema.sql");
        executeSql("/tmp/20260827_user_phone_identity.sql");
    }

    @LocalServerPort
    private int port;

    @Autowired
    private CoreDatabase database;

    @Autowired
    private FakeSmsProvider sms;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();

    @AfterEach
    void cleanup() {
        database.dsl().deleteFrom(USER).execute();
    }

    @Test
    void 新手机号自动建号再次登录复用账号且当前用户展示脱敏手机号() throws Exception {
        JsonNode firstChallenge = createChallenge(
                "phone-send-runtime-request-0001");
        HttpResponse<String> firstLogin = verify(
                firstChallenge.get("challengeId").asText(),
                "phone-verify-runtime-request-0001");

        assertThat(firstLogin.statusCode()).isEqualTo(200);
        JsonNode firstBody = json.readTree(firstLogin.body());
        assertThat(firstBody.get("isNewUser").asBoolean()).isTrue();
        assertThat(firstBody.get("maskedPhone").asText()).isEqualTo("138****8000");
        assertThat(firstBody.get("username").asText())
                .startsWith("mobile_c")
                .doesNotContain("13800138000");
        String cookie = firstLogin.headers()
                .firstValue("set-cookie")
                .orElseThrow()
                .split(";", 2)[0];
        HttpResponse<String> me = get("/api/v1/auth/me", cookie);
        assertThat(me.statusCode()).isEqualTo(200);
        assertThat(json.readTree(me.body()).get("maskedPhone").asText())
                .isEqualTo("138****8000");

        JsonNode secondChallenge = createChallenge(
                "phone-send-runtime-request-0002");
        HttpResponse<String> secondLogin = verify(
                secondChallenge.get("challengeId").asText(),
                "phone-verify-runtime-request-0002");
        assertThat(secondLogin.statusCode()).isEqualTo(200);
        JsonNode secondBody = json.readTree(secondLogin.body());
        assertThat(secondBody.get("isNewUser").asBoolean()).isFalse();
        assertThat(secondBody.get("id").asText()).isEqualTo(firstBody.get("id").asText());

        assertThat(database.dsl().fetchCount(USER)).isEqualTo(1);
        assertThat(database.dsl().fetchCount(CREDITLEDGER)).isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        DSL.table(DSL.name("UserPhoneIdentity"))))
                .isEqualTo(1);
        assertThat(sms.sendCalls.get()).isEqualTo(2);
        assertThat(sms.verifyCalls.get()).isEqualTo(2);
    }

    @Test
    void 手机号入口开启后用户名新注册必须关闭而旧登录接口仍保留() throws Exception {
        HttpResponse<String> registration = post(
                "/api/v1/auth/register",
                "{\"username\":\"new_user\",\"password\":\"密码1234\",\"confirmPassword\":\"密码1234\"}");
        assertThat(registration.statusCode()).isEqualTo(404);
        assertThat(registration.body()).contains("USERNAME_REGISTRATION_DISABLED");

        HttpResponse<String> login = post(
                "/api/v1/auth/login",
                "{\"username\":\"legacy_user\",\"password\":\"密码1234\"}");
        assertThat(login.statusCode()).isEqualTo(401);
        assertThat(login.body()).contains("INVALID_CREDENTIALS");
    }

    private JsonNode createChallenge(String requestId) throws Exception {
        HttpResponse<String> response = post(
                "/api/v1/auth/phone/challenges",
                "{\"phone\":\"13800138000\","
                        + "\"captchaVerifyParam\":\"opaque-proof\","
                        + "\"consentVersion\":\"2026-08-27\","
                        + "\"acceptedTerms\":true,"
                        + "\"clientRequestId\":\"" + requestId + "\"}");
        assertThat(response.statusCode()).isEqualTo(201);
        return json.readTree(response.body());
    }

    private HttpResponse<String> verify(String challengeId, String requestId)
            throws Exception {
        return post(
                "/api/v1/auth/phone/challenges/" + challengeId + "/verify",
                "{\"phone\":\"13800138000\","
                        + "\"code\":\"123456\","
                        + "\"clientRequestId\":\"" + requestId + "\"}");
    }

    private HttpResponse<String> post(String path, String body) throws Exception {
        return client.send(
                HttpRequest.newBuilder(uri(path))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(body))
                        .build(),
                HttpResponse.BodyHandlers.ofString());
    }

    private HttpResponse<String> get(String path, String cookie) throws Exception {
        return client.send(
                HttpRequest.newBuilder(uri(path))
                        .header("Cookie", cookie)
                        .GET()
                        .build(),
                HttpResponse.BodyHandlers.ofString());
    }

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private static void executeSql(String path) throws Exception {
        ExecResult result = POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                POSTGRES.getDatabaseName(),
                "-f",
                path);
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@127.0.0.1:"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FakeProviderConfiguration {

        @Bean
        @Primary
        PhoneCaptchaVerifier fakePhoneCaptchaVerifier() {
            return value -> "opaque-proof".equals(value);
        }

        @Bean
        @Primary
        PhoneAuthRateLimiter fakePhoneAuthRateLimiter() {
            return new PhoneAuthRateLimiter() {
                @Override
                public void checkHumanVerification(String clientIdentity) {}

                @Override
                public void checkPhoneSend(String phoneDigest) {}
            };
        }

        @Bean
        @Primary
        FakeSmsProvider fakePhoneSmsProvider() {
            return new FakeSmsProvider();
        }
    }

    static final class FakeSmsProvider implements PhoneSmsProvider {

        private final AtomicInteger sendCalls = new AtomicInteger();
        private final AtomicInteger verifyCalls = new AtomicInteger();

        @Override
        public void sendVerificationCode(String nationalPhone, String challengeId) {
            assertThat(nationalPhone).isEqualTo("13800138000");
            sendCalls.incrementAndGet();
        }

        @Override
        public boolean verifyCode(String nationalPhone, String challengeId, String code) {
            verifyCalls.incrementAndGet();
            return "13800138000".equals(nationalPhone) && "123456".equals(code);
        }
    }
}
