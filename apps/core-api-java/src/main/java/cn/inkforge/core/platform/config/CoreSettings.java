package cn.inkforge.core.platform.config;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.regex.Pattern;

/** 兼容现有部署环境变量的不可变 Java Core 配置。 */
public final class CoreSettings {

    public static final String OLD_DEFAULT_JWT_SECRET = "inkforge-default-secret-change-me";
    private static final Pattern VIDEO_NAMESPACE =
            Pattern.compile("[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?");

    public enum EnvironmentName {
        DEV,
        TEST,
        PRODUCTION
    }

    private final EnvironmentName environment;
    private final boolean allowInsecureHttpAuth;
    private final SecretValue databaseUrl;
    private final SecretValue redisUrl;
    private final SecretValue jwtSecret;
    private final boolean usernameRegistrationEnabled;
    private final boolean phoneAuthEnabled;
    private final boolean phoneAuthSendEnabled;
    private final SecretValue phoneAuthHmacSecret;
    private final String phoneAuthConsentVersion;
    private final String phoneAuthRedisPrefix;
    private final SecretValue aliyunAccessKeyId;
    private final SecretValue aliyunAccessKeySecret;
    private final String aliyunPnvsSignName;
    private final String aliyunPnvsTemplateCode;
    private final String aliyunPnvsSchemeName;
    private final String aliyunCaptchaPrefix;
    private final String aliyunCaptchaSceneId;
    private final List<CidrBlock> trustedProxyCidrs;
    private final List<CidrBlock> trustedAgentCidrs;
    private final Path coreServicePrivateKeyPath;
    private final String coreServiceKeyId;
    private final Path agentServicePublicKeyPath;
    private final URI agentServiceUrl;
    private final boolean ragIndexEnabled;
    private final boolean workflowEventDebugEnabled;
    private final Path uploadsRoot;
    private final boolean videoPreviewEnabled;
    private final boolean videoDispatchEnabled;
    private final String videoDispatchNamespace;
    private final boolean seedanceConfigured;
    private final boolean seedanceEnabled;
    private final String seedanceModel;
    private final URI videoProviderMediaBaseUrl;
    private final SecretValue videoProviderMediaTokenSecret;
    private final List<String> seedanceResultAllowedHostSuffixes;

    private CoreSettings(Function<String, String> value) {
        this.environment = parseEnvironment(value.apply("ENVIRONMENT"));
        this.allowInsecureHttpAuth = bool(value, "ALLOW_INSECURE_HTTP_AUTH", false);
        this.databaseUrl = secret(value.apply("DATABASE_URL"));
        this.redisUrl = secret(value.apply("REDIS_URL"));
        this.jwtSecret = secret(value.apply("JWT_SECRET"));
        this.usernameRegistrationEnabled = bool(
                value, "USERNAME_REGISTRATION_ENABLED", true);
        this.phoneAuthEnabled = bool(value, "PHONE_AUTH_ENABLED", false);
        this.phoneAuthSendEnabled = bool(value, "PHONE_AUTH_SEND_ENABLED", false);
        this.phoneAuthHmacSecret = secret(value.apply("PHONE_AUTH_HMAC_SECRET"));
        this.phoneAuthConsentVersion = nonBlankOrDefault(
                value.apply("PHONE_AUTH_CONSENT_VERSION"), "2026-08-27");
        this.phoneAuthRedisPrefix = nonBlankOrDefault(
                value.apply("PHONE_AUTH_REDIS_PREFIX"), "phone-auth:v1:");
        this.aliyunAccessKeyId = secret(value.apply("ALIYUN_ACCESS_KEY_ID"));
        this.aliyunAccessKeySecret = secret(value.apply("ALIYUN_ACCESS_KEY_SECRET"));
        this.aliyunPnvsSignName = optional(value.apply("ALIYUN_PNVS_SIGN_NAME"));
        this.aliyunPnvsTemplateCode = optional(value.apply("ALIYUN_PNVS_TEMPLATE_CODE"));
        this.aliyunPnvsSchemeName = optional(value.apply("ALIYUN_PNVS_SCHEME_NAME"));
        this.aliyunCaptchaPrefix = optional(value.apply("ALIYUN_CAPTCHA_PREFIX"));
        this.aliyunCaptchaSceneId = optional(value.apply("ALIYUN_CAPTCHA_SCENE_ID"));
        this.trustedProxyCidrs = cidrs(value.apply("TRUSTED_PROXY_CIDRS"), "可信代理网段");
        String agentCidrs = firstNonBlank(
                value.apply("TRUSTED_AGENT_CIDRS"), value.apply("AGENT_SERVICE_CIDRS"));
        this.trustedAgentCidrs = cidrs(agentCidrs, "可信智能体网段");
        this.coreServicePrivateKeyPath = optionalPath(value.apply("CORE_SERVICE_PRIVATE_KEY_PATH"));
        this.coreServiceKeyId = nonBlankOrDefault(value.apply("CORE_SERVICE_KEY_ID"), "core-api-v1");
        this.agentServicePublicKeyPath = optionalPath(value.apply("AGENT_SERVICE_PUBLIC_KEY_PATH"));
        this.agentServiceUrl = optionalHttpUri(value.apply("AGENT_SERVICE_URL"), "智能体服务地址");
        this.ragIndexEnabled = bool(value, "RAG_INDEX_ENABLED", false);
        this.workflowEventDebugEnabled = bool(
                value, "WORKFLOW_EVENT_DEBUG_ENABLED", false);
        this.uploadsRoot = absolutePath(nonBlankOrDefault(value.apply("UPLOADS_ROOT"), "/data/uploads"));
        this.videoPreviewEnabled = bool(value, "VIDEO_PREVIEW_ENABLED", false);
        this.videoDispatchEnabled = bool(value, "VIDEO_DISPATCH_ENABLED", false);
        this.videoDispatchNamespace = optional(value.apply("VIDEO_DISPATCH_NAMESPACE"));
        this.seedanceConfigured = bool(value, "SEEDANCE_CONFIGURED", false);
        this.seedanceEnabled = bool(value, "SEEDANCE_ENABLED", false);
        this.seedanceModel = nonBlankOrDefault(
                value.apply("SEEDANCE_MODEL"), "doubao-seedance-2-5-260628");
        this.videoProviderMediaBaseUrl = optionalHttpUri(
                value.apply("VIDEO_PROVIDER_MEDIA_BASE_URL"), "供应商素材公网基址");
        this.videoProviderMediaTokenSecret = secret(value.apply("VIDEO_PROVIDER_MEDIA_TOKEN_SECRET"));
        this.seedanceResultAllowedHostSuffixes = hostSuffixes(
                nonBlankOrDefault(value.apply("SEEDANCE_RESULT_ALLOWED_HOST_SUFFIXES"), ".volces.com"));
        validate();
    }

    public static CoreSettings from(Map<String, String> values) {
        Map<String, String> snapshot = Map.copyOf(values);
        return new CoreSettings(snapshot::get);
    }

    public static CoreSettings fromLookup(Function<String, String> values) {
        return new CoreSettings(values);
    }

    public EnvironmentName environment() {
        return environment;
    }

    public SecretValue databaseUrl() {
        return databaseUrl;
    }

    public SecretValue redisUrl() {
        return redisUrl;
    }

    public SecretValue jwtSecret() {
        return jwtSecret;
    }

    public boolean usernameRegistrationEnabled() {
        return usernameRegistrationEnabled;
    }

    public boolean phoneAuthEnabled() {
        return phoneAuthEnabled;
    }

    public boolean phoneAuthSendEnabled() {
        return phoneAuthSendEnabled;
    }

    public SecretValue phoneAuthHmacSecret() {
        return phoneAuthHmacSecret;
    }

    public String phoneAuthConsentVersion() {
        return phoneAuthConsentVersion;
    }

    public String phoneAuthRedisPrefix() {
        return phoneAuthRedisPrefix;
    }

    public SecretValue aliyunAccessKeyId() {
        return aliyunAccessKeyId;
    }

    public SecretValue aliyunAccessKeySecret() {
        return aliyunAccessKeySecret;
    }

    public String aliyunPnvsSignName() {
        return aliyunPnvsSignName;
    }

    public String aliyunPnvsTemplateCode() {
        return aliyunPnvsTemplateCode;
    }

    public String aliyunPnvsSchemeName() {
        return aliyunPnvsSchemeName;
    }

    public String aliyunCaptchaPrefix() {
        return aliyunCaptchaPrefix;
    }

    public String aliyunCaptchaSceneId() {
        return aliyunCaptchaSceneId;
    }

    public List<CidrBlock> trustedProxyCidrs() {
        return trustedProxyCidrs;
    }

    public List<CidrBlock> trustedAgentCidrs() {
        return trustedAgentCidrs;
    }

    public Path coreServicePrivateKeyPath() {
        return coreServicePrivateKeyPath;
    }

    public String coreServiceKeyId() {
        return coreServiceKeyId;
    }

    public Path agentServicePublicKeyPath() {
        return agentServicePublicKeyPath;
    }

    public URI agentServiceUrl() {
        return agentServiceUrl;
    }

    public boolean ragIndexEnabled() {
        return ragIndexEnabled;
    }

    public boolean workflowEventDebugEnabled() {
        return workflowEventDebugEnabled;
    }

    public Path uploadsRoot() {
        return uploadsRoot;
    }

    public boolean sessionCookieSecure() {
        return environment == EnvironmentName.PRODUCTION && !allowInsecureHttpAuth;
    }

    public boolean videoPreviewEnabled() {
        return videoPreviewEnabled;
    }

    public boolean videoDispatchEnabled() {
        return videoDispatchEnabled;
    }

    public String videoDispatchNamespace() {
        return videoDispatchNamespace;
    }

    public boolean seedanceEnabled() {
        return seedanceEnabled;
    }

    public boolean seedanceConfigured() {
        return seedanceConfigured;
    }

    public String seedanceModel() {
        return seedanceModel;
    }

    public URI videoProviderMediaBaseUrl() {
        return videoProviderMediaBaseUrl;
    }

    public SecretValue videoProviderMediaTokenSecret() {
        return videoProviderMediaTokenSecret;
    }

    public List<String> seedanceResultAllowedHostSuffixes() {
        return seedanceResultAllowedHostSuffixes;
    }

    private void validate() {
        if (phoneAuthSendEnabled && !phoneAuthEnabled) {
            throw new IllegalArgumentException("开启真实短信发送前必须先开启手机号认证");
        }
        if (phoneAuthHmacSecret != null
                && utf8Length(phoneAuthHmacSecret.reveal()) < 32) {
            throw new IllegalArgumentException("手机号认证摘要密钥至少需要 32 个 UTF-8 字节");
        }
        if (phoneAuthConsentVersion.length() > 64
                || phoneAuthConsentVersion.indexOf('\0') >= 0
                || phoneAuthRedisPrefix.length() > 128
                || phoneAuthRedisPrefix.indexOf('\0') >= 0
                || !phoneAuthRedisPrefix.endsWith(":")) {
            throw new IllegalArgumentException("手机号认证版本或 Redis 前缀格式无效");
        }
        if (invalidOptionalText(aliyunPnvsSignName, 128)
                || invalidOptionalText(aliyunPnvsTemplateCode, 64)
                || invalidOptionalText(aliyunPnvsSchemeName, 20)
                || invalidOptionalText(aliyunCaptchaPrefix, 128)
                || invalidOptionalText(aliyunCaptchaSceneId, 128)) {
            throw new IllegalArgumentException("阿里云手机号认证配置格式无效");
        }
        if (phoneAuthEnabled && phoneAuthSendEnabled) {
            List<String> missing = new ArrayList<>();
            required(missing, "database_url", databaseUrl);
            required(missing, "redis_url", redisUrl);
            required(missing, "jwt_secret", jwtSecret);
            required(missing, "phone_auth_hmac_secret", phoneAuthHmacSecret);
            required(missing, "aliyun_access_key_id", aliyunAccessKeyId);
            required(missing, "aliyun_access_key_secret", aliyunAccessKeySecret);
            required(missing, "aliyun_pnvs_sign_name", aliyunPnvsSignName);
            required(missing, "aliyun_pnvs_template_code", aliyunPnvsTemplateCode);
            required(missing, "aliyun_captcha_prefix", aliyunCaptchaPrefix);
            required(missing, "aliyun_captcha_scene_id", aliyunCaptchaSceneId);
            if (!missing.isEmpty()) {
                throw new IllegalArgumentException(
                        "开启手机号认证缺少必需配置：" + String.join("、", missing));
            }
        }
        if (videoDispatchEnabled && !videoPreviewEnabled) {
            throw new IllegalArgumentException("开启视频后台调度前必须先开启视频预览");
        }
        if (videoDispatchEnabled
                && (videoDispatchNamespace == null
                        || !VIDEO_NAMESPACE.matcher(videoDispatchNamespace).matches())) {
            throw new IllegalArgumentException("开启视频后台调度必须配置稳定的视频调度命名空间");
        }
        if (videoDispatchNamespace != null
                && !VIDEO_NAMESPACE.matcher(videoDispatchNamespace).matches()) {
            throw new IllegalArgumentException("视频调度命名空间格式无效");
        }
        if (seedanceEnabled && !seedanceConfigured) {
            throw new IllegalArgumentException("开启 Seedance 前必须先确认供应商已配置");
        }
        if ((videoProviderMediaBaseUrl == null) != (videoProviderMediaTokenSecret == null)) {
            throw new IllegalArgumentException("供应商素材公网基址与令牌密钥必须同时配置");
        }
        if (videoProviderMediaTokenSecret != null
                && utf8Length(videoProviderMediaTokenSecret.reveal()) < 32) {
            throw new IllegalArgumentException("供应商素材短时令牌密钥至少需要 32 个 UTF-8 字节");
        }
        if (environment != EnvironmentName.PRODUCTION) {
            return;
        }
        if (phoneAuthEnabled
                && phoneAuthSendEnabled
                && usernameRegistrationEnabled) {
            throw new IllegalArgumentException(
                    "生产开放手机号认证时必须关闭用户名新注册入口");
        }
        if (videoPreviewEnabled || videoDispatchEnabled || seedanceEnabled) {
            throw new IllegalArgumentException("生产环境禁止开启仅获开发库授权的视频能力");
        }
        List<String> missing = new ArrayList<>();
        required(missing, "database_url", databaseUrl);
        required(missing, "redis_url", redisUrl);
        required(missing, "jwt_secret", jwtSecret);
        required(missing, "trusted_proxy_cidrs", trustedProxyCidrs);
        required(missing, "trusted_agent_cidrs", trustedAgentCidrs);
        required(missing, "core_service_private_key_path", coreServicePrivateKeyPath);
        required(missing, "agent_service_public_key_path", agentServicePublicKeyPath);
        required(missing, "agent_service_url", agentServiceUrl);
        if (!missing.isEmpty()) {
            throw new IllegalArgumentException("生产环境缺少必需配置：" + String.join("、", missing));
        }
        if (OLD_DEFAULT_JWT_SECRET.equals(jwtSecret.reveal())) {
            throw new IllegalArgumentException("生产环境禁止使用旧默认会话签名密钥");
        }
        if (utf8Length(jwtSecret.reveal()) < 32) {
            throw new IllegalArgumentException("生产环境会话签名密钥至少需要 32 个 UTF-8 字节");
        }
    }

    private static EnvironmentName parseEnvironment(String value) {
        String normalized = nonBlankOrDefault(value, "dev").toLowerCase();
        return switch (normalized) {
            case "dev" -> EnvironmentName.DEV;
            case "test" -> EnvironmentName.TEST;
            case "production" -> EnvironmentName.PRODUCTION;
            default -> throw new IllegalArgumentException("environment 必须是 dev、test 或 production");
        };
    }

    private static List<CidrBlock> cidrs(String value, String label) {
        String normalized = optional(value);
        if (normalized == null) {
            return List.of();
        }
        try {
            return java.util.Arrays.stream(normalized.split(","))
                    .map(String::strip)
                    .filter(item -> !item.isEmpty())
                    .map(CidrBlock::parse)
                    .toList();
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(label + "无效");
        }
    }

    private static List<String> hostSuffixes(String value) {
        List<String> result = java.util.Arrays.stream(value.split(","))
                .map(item -> item.strip().toLowerCase())
                .filter(item -> !item.isEmpty())
                .toList();
        if (result.isEmpty()
                || result.stream().anyMatch(item -> !item.startsWith(".")
                        || item.contains("/")
                        || item.contains(":")
                        || item.chars().filter(character -> character == '.').count() < 2)) {
            throw new IllegalArgumentException("Seedance 结果域名后缀格式无效");
        }
        return result;
    }

    private static URI optionalHttpUri(String value, String label) {
        String normalized = optional(value);
        if (normalized == null) {
            return null;
        }
        try {
            URI uri = URI.create(normalized.endsWith("/") ? normalized.substring(0, normalized.length() - 1) : normalized);
            if (!("http".equals(uri.getScheme()) || "https".equals(uri.getScheme()))
                    || uri.getHost() == null
                    || uri.getRawUserInfo() != null
                    || uri.getRawQuery() != null
                    || uri.getRawFragment() != null) {
                throw new IllegalArgumentException();
            }
            return uri;
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(label + "必须是无凭据、无查询参数的 HTTP(S) URL");
        }
    }

    private static Path absolutePath(String value) {
        if (value.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("上传根目录必须是绝对路径");
        }
        Path path = Path.of(value).normalize();
        if (!path.isAbsolute()) {
            throw new IllegalArgumentException("上传根目录必须是绝对路径");
        }
        return path;
    }

    private static Path optionalPath(String value) {
        String normalized = optional(value);
        return normalized == null ? null : absolutePath(normalized);
    }

    private static boolean bool(Function<String, String> values, String name, boolean fallback) {
        String value = optional(values.apply(name));
        if (value == null) {
            return fallback;
        }
        return switch (value.toLowerCase()) {
            case "true", "1" -> true;
            case "false", "0" -> false;
            default -> throw new IllegalArgumentException(name + " 必须是布尔值");
        };
    }

    private static SecretValue secret(String value) {
        String normalized = optional(value);
        return normalized == null ? null : new SecretValue(normalized);
    }

    private static String optional(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.strip();
    }

    private static String nonBlankOrDefault(String value, String fallback) {
        String normalized = optional(value);
        return normalized == null ? fallback : normalized;
    }

    private static String firstNonBlank(String first, String second) {
        String normalized = optional(first);
        return normalized == null ? optional(second) : normalized;
    }

    private static void required(List<String> missing, String name, Object value) {
        if (value == null || value instanceof List<?> list && list.isEmpty()) {
            missing.add(name);
        }
    }

    private static int utf8Length(String value) {
        return value.getBytes(StandardCharsets.UTF_8).length;
    }

    private static boolean invalidOptionalText(String value, int maximumLength) {
        return value != null && (value.length() > maximumLength || value.indexOf('\0') >= 0);
    }

    @Override
    public String toString() {
        return "CoreSettings[environment="
                + environment
                + ", databaseUrl=********, redisUrl=********, jwtSecret=********"
                + ", phoneAuthEnabled="
                + phoneAuthEnabled
                + ", phoneAuthSendEnabled="
                + phoneAuthSendEnabled
                + ", phoneAuthHmacSecret=********, aliyunAccessKeyId=********"
                + ", aliyunAccessKeySecret=********]";
    }
}
