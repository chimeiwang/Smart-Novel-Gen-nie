package cn.inkforge.core.video.infrastructure;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

/** 只有供应商媒体 URL 与令牌均为非空配置时才创建令牌编码器。 */
final class ProviderAssetTokenConfiguredCondition implements Condition {

    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata ignoredMetadata) {
        return hasText(context.getEnvironment().getProperty("VIDEO_PROVIDER_MEDIA_BASE_URL"))
                && hasText(context.getEnvironment()
                        .getProperty("VIDEO_PROVIDER_MEDIA_TOKEN_SECRET"));
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
