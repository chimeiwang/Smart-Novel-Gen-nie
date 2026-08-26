package cn.inkforge.core.billing.application;

/** 模型调用资源归属核验后的当前余额和请求标识命名空间。 */
public record AuthorizationContext(long balanceMicros, String resourceKind) {
    public AuthorizationContext {
        if (!("default".equals(resourceKind) || "video".equals(resourceKind))) {
            throw new IllegalArgumentException("计费资源类型无效");
        }
    }
}
