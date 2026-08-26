package cn.inkforge.serviceauth;

/** 对外只暴露稳定中文信息与错误码，不串联底层敏感异常。 */
public final class ServiceAuthException extends RuntimeException {

    private final String code;
    private final int statusCode;

    public ServiceAuthException(String message, String code, int statusCode) {
        super(message);
        this.code = code;
        this.statusCode = statusCode;
    }

    public String code() {
        return code;
    }

    public int statusCode() {
        return statusCode;
    }

    static ServiceAuthException authentication(String message) {
        return new ServiceAuthException(message, "SERVICE_AUTHENTICATION_FAILED", 401);
    }

    static ServiceAuthException binding(String message) {
        return new ServiceAuthException(message, "SERVICE_REQUEST_BINDING_INVALID", 401);
    }

    static ServiceAuthException scope() {
        return new ServiceAuthException("服务令牌缺少所需权限范围", "SERVICE_SCOPE_FORBIDDEN", 403);
    }

    static ServiceAuthException resource(String field) {
        return new ServiceAuthException(
                "服务令牌资源绑定不匹配：" + field, "SERVICE_RESOURCE_MISMATCH", 403);
    }

    static ServiceAuthException replayed() {
        return new ServiceAuthException("服务令牌已被使用", "SERVICE_TOKEN_REPLAYED", 409);
    }

    static ServiceAuthException replayUnavailable() {
        return new ServiceAuthException(
                "服务请求重放保护暂不可用", "SERVICE_REPLAY_STORE_UNAVAILABLE", 503);
    }
}
