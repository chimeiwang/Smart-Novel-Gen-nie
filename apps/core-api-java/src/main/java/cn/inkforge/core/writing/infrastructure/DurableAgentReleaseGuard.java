package cn.inkforge.core.writing.infrastructure;

/** fresh V2 写入前必须实时通过的服务器发布事务保护。 */
@FunctionalInterface
interface DurableAgentReleaseGuard {

    void requireFreshStart(String userId, String novelId);
}
