package cn.inkforge.serviceauth;

/** 指定全部请求或仅写请求需要一次性消费 jti。 */
public enum ReplayPolicy {
    ALL_SCOPES,
    WRITE_SCOPES_ONLY
}
