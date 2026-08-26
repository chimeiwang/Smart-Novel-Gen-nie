package cn.inkforge.core.billing.domain;

/** grant 被篡改、过期或不符合严格 JWT 契约。 */
public final class ModelGrantException extends RuntimeException {

    public ModelGrantException() {
        super("模型授权令牌无效或已过期");
    }
}
