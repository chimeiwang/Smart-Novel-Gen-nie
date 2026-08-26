package cn.inkforge.core.billing.domain;

import java.util.Set;

/** 与 Python Agent 共享的模型授权 JWT 权威 claims。 */
public record ModelGrantClaims(
        String requestId,
        String taskId,
        String runId,
        String novelId,
        String userId,
        String provider,
        String model,
        String agentId,
        int maxOutputTokens,
        boolean billable,
        long issuedAt,
        long expiresAt) {

    public static final int LIFETIME_SECONDS = 1_200;
    private static final Set<String> PROVIDERS = Set.of("openai_compatible", "fake");

    public ModelGrantClaims {
        requireLength(requestId, 1, 256, "requestId");
        requireLength(taskId, 1, 256, "taskId");
        requireLength(runId, 1, 256, "runId");
        requireLength(novelId, 1, 256, "novelId");
        requireLength(userId, 1, 256, "userId");
        requireLength(model, 1, 256, "model");
        requireLength(agentId, 1, 64, "agentId");
        if (!PROVIDERS.contains(provider)) {
            throw new IllegalArgumentException("模型提供方无效");
        }
        if (maxOutputTokens < 1 || maxOutputTokens > 1_000_000) {
            throw new IllegalArgumentException("模型输出授权范围无效");
        }
        if (expiresAt <= issuedAt || expiresAt - issuedAt > LIFETIME_SECONDS) {
            throw new IllegalArgumentException("模型授权令牌有效期无效");
        }
    }

    private static void requireLength(String value, int minimum, int maximum, String name) {
        int length = value == null ? 0 : value.codePointCount(0, value.length());
        if (length < minimum || length > maximum) {
            throw new IllegalArgumentException(name + " 长度无效");
        }
    }
}
