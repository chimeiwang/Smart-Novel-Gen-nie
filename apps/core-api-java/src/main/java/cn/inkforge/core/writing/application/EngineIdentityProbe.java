package cn.inkforge.core.writing.application;

/** 只判别持久 V2 身份；未命中时由 V1 仓储继续决定缺失、越权与恢复语义。 */
@FunctionalInterface
public interface EngineIdentityProbe {

    EngineIdentity probe(String userId, String runId);

    enum EngineIdentity {
        V1_OR_MISSING,
        V2
    }

    static EngineIdentityProbe v1Only() {
        return (userId, runId) -> EngineIdentity.V1_OR_MISSING;
    }
}
