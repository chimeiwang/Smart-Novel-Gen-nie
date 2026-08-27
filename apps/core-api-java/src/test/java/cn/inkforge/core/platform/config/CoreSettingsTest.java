package cn.inkforge.core.platform.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class CoreSettingsTest {

    @Test
    void 开发默认值与CIDR必须规范化() {
        CoreSettings settings = CoreSettings.from(Map.of(
                "TRUSTED_PROXY_CIDRS", "10.0.0.7/24,2001:db8::1/64",
                "UPLOADS_ROOT", "/tmp/inkforge-uploads"));

        assertThat(settings.environment()).isEqualTo(CoreSettings.EnvironmentName.DEV);
        assertThat(settings.trustedProxyCidrs()).extracting(Object::toString)
                .containsExactly("10.0.0.0/24", "2001:db8::/64");
        assertThat(settings.trustedProxyCidrs().getFirst().contains("10.0.0.99")).isTrue();
        assertThat(settings.trustedProxyCidrs().getFirst().contains("10.0.1.1")).isFalse();
        assertThat(settings.sessionCookieSecure()).isFalse();
        assertThat(settings.ragIndexEnabled()).isFalse();
        assertThat(settings.phoneAuthEnabled()).isFalse();
        assertThat(settings.phoneAuthSendEnabled()).isFalse();
        assertThat(settings.usernameRegistrationEnabled()).isTrue();
    }

    @Test
    void 生产必须拒绝缺失配置和弱密钥() {
        assertThatThrownBy(() -> CoreSettings.from(Map.of("ENVIRONMENT", "production")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("database_url")
                .hasMessageContaining("trusted_agent_cidrs");

        Map<String, String> production = validProduction();
        production.put("JWT_SECRET", "short");
        assertThatThrownBy(() -> CoreSettings.from(production))
                .hasMessageContaining("至少需要 32");
    }

    @Test
    void 生产禁止开发视频能力且路径URL必须安全() {
        Map<String, String> production = validProduction();
        production.put("VIDEO_PREVIEW_ENABLED", "true");
        assertThatThrownBy(() -> CoreSettings.from(production))
                .hasMessageContaining("生产环境禁止");

        assertThatThrownBy(() -> CoreSettings.from(Map.of("UPLOADS_ROOT", "relative/uploads")))
                .hasMessageContaining("绝对路径");
        assertThatThrownBy(() -> CoreSettings.from(Map.of(
                        "AGENT_SERVICE_URL", "https://user:secret@example.com?token=x")))
                .hasMessageContaining("无凭据");
    }

    @Test
    void 配置字符串不得泄露密钥() {
        CoreSettings settings = CoreSettings.from(Map.of(
                "DATABASE_URL", "postgresql://secret@db/dev",
                "JWT_SECRET", "very-sensitive",
                "PHONE_AUTH_HMAC_SECRET", "phone-hmac-secret-0000000000000000",
                "ALIYUN_ACCESS_KEY_ID", "access-key-id-sensitive",
                "ALIYUN_ACCESS_KEY_SECRET", "access-key-secret-sensitive"));

        assertThat(settings.toString()).doesNotContain(
                "secret", "very-sensitive", "access-key-id-sensitive");
        assertThat(settings.databaseUrl().toString()).isEqualTo("********");
    }

    @Test
    void 真实手机号认证必须完整配置且生产关闭用户名新注册() {
        Map<String, String> enabled = validPhoneAuth();
        CoreSettings settings = CoreSettings.from(enabled);
        assertThat(settings.phoneAuthEnabled()).isTrue();
        assertThat(settings.phoneAuthSendEnabled()).isTrue();
        assertThat(settings.aliyunPnvsSchemeName()).isNull();

        enabled.remove("ALIYUN_CAPTCHA_SCENE_ID");
        assertThatThrownBy(() -> CoreSettings.from(enabled))
                .hasMessageContaining("aliyun_captcha_scene_id");

        Map<String, String> production = validProduction();
        production.putAll(validPhoneAuth());
        production.put("ENVIRONMENT", "production");
        production.put("USERNAME_REGISTRATION_ENABLED", "true");
        assertThatThrownBy(() -> CoreSettings.from(production))
                .hasMessageContaining("关闭用户名新注册");
        production.put("USERNAME_REGISTRATION_ENABLED", "false");
        assertThat(CoreSettings.from(production).usernameRegistrationEnabled()).isFalse();
    }

    @Test
    void 短信发送不能绕过总开关且摘要密钥不能过短() {
        assertThatThrownBy(() -> CoreSettings.from(Map.of(
                        "PHONE_AUTH_SEND_ENABLED", "true")))
                .hasMessageContaining("先开启手机号认证");
        assertThatThrownBy(() -> CoreSettings.from(Map.of(
                        "PHONE_AUTH_HMAC_SECRET", "too-short")))
                .hasMessageContaining("至少需要 32");
        assertThatThrownBy(() -> CoreSettings.from(Map.of(
                        "PHONE_AUTH_CONSENT_VERSION", "v".repeat(65))))
                .hasMessageContaining("版本或 Redis 前缀格式无效");
        assertThatThrownBy(() -> CoreSettings.from(Map.of(
                        "ALIYUN_CAPTCHA_PREFIX", "p".repeat(129))))
                .hasMessageContaining("阿里云手机号认证配置格式无效");
    }

    @Test
    void RAG索引开关必须兼容现有环境变量() {
        CoreSettings settings = CoreSettings.from(Map.of("RAG_INDEX_ENABLED", "true"));

        assertThat(settings.ragIndexEnabled()).isTrue();
    }

    @Test
    void 供应商媒体配置必须成对出现且双空值等价于未配置() {
        CoreSettings empty = CoreSettings.from(Map.of(
                "VIDEO_PROVIDER_MEDIA_BASE_URL", "",
                "VIDEO_PROVIDER_MEDIA_TOKEN_SECRET", ""));
        assertThat(empty.videoProviderMediaBaseUrl()).isNull();
        assertThat(empty.videoProviderMediaTokenSecret()).isNull();

        assertThatThrownBy(() -> CoreSettings.from(Map.of(
                        "VIDEO_PROVIDER_MEDIA_BASE_URL", "https://media.example.com")))
                .hasMessageContaining("必须同时配置");
        assertThatThrownBy(() -> CoreSettings.from(Map.of(
                        "VIDEO_PROVIDER_MEDIA_TOKEN_SECRET", "x".repeat(32))))
                .hasMessageContaining("必须同时配置");
    }

    private Map<String, String> validProduction() {
        Map<String, String> values = new HashMap<>();
        values.put("ENVIRONMENT", "production");
        values.put("DATABASE_URL", "postgresql://user:pass@db/novelwriter");
        values.put("REDIS_URL", "redis://redis:6379/0");
        values.put("JWT_SECRET", "x".repeat(32));
        values.put("TRUSTED_PROXY_CIDRS", "10.0.0.0/24");
        values.put("TRUSTED_AGENT_CIDRS", "10.1.0.0/24");
        values.put("CORE_SERVICE_PRIVATE_KEY_PATH", "/run/secrets/core.pem");
        values.put("AGENT_SERVICE_PUBLIC_KEY_PATH", "/run/secrets/agent.jwks.json");
        values.put("AGENT_SERVICE_URL", "http://agent-service:8001");
        return values;
    }

    private Map<String, String> validPhoneAuth() {
        Map<String, String> values = new HashMap<>();
        values.put("PHONE_AUTH_ENABLED", "true");
        values.put("PHONE_AUTH_SEND_ENABLED", "true");
        values.put("DATABASE_URL", "postgresql://user:pass@db/novelwriterdev");
        values.put("REDIS_URL", "redis://redis:6379/0");
        values.put("JWT_SECRET", "j".repeat(32));
        values.put("PHONE_AUTH_HMAC_SECRET", "h".repeat(32));
        values.put("ALIYUN_ACCESS_KEY_ID", "test-access-key-id");
        values.put("ALIYUN_ACCESS_KEY_SECRET", "test-access-key-secret");
        values.put("ALIYUN_PNVS_SIGN_NAME", "测试签名");
        values.put("ALIYUN_PNVS_TEMPLATE_CODE", "100001");
        values.put("ALIYUN_CAPTCHA_PREFIX", "test-prefix");
        values.put("ALIYUN_CAPTCHA_SCENE_ID", "test-scene");
        return values;
    }
}
