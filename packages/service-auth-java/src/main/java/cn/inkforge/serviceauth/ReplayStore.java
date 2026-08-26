package cn.inkforge.serviceauth;

/** 原子消费 jti；首次返回 true，重复返回 false，基础设施故障抛出异常。 */
@FunctionalInterface
public interface ReplayStore {
    boolean consume(String jti, int ttlSeconds);
}
