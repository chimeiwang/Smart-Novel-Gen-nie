package cn.inkforge.core.platform.redis;

/** Redis 网络、认证或协议故障的稳定边界异常；不携带可能包含凭据的底层消息。 */
public final class RedisUnavailableException extends RuntimeException {

    public RedisUnavailableException() {
        super("Redis 暂时不可用");
    }
}
