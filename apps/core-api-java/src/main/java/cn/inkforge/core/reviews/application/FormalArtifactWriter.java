package cn.inkforge.core.reviews.application;

import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;

/** 把已锁定且已批准的审核产物写入正式领域数据；调用方负责外层原子事务。 */
public interface FormalArtifactWriter {

    int apply(
            String userId,
            ReviewArtifactState artifact,
            ReviewArtifactDecisionRequest request);

    /** V2 结构化草案必须携带从权威 Evidence 重建的来源，不能降级为 V1 无来源写入。 */
    default int applyAgentUpdates(String userId, ReviewArtifactState artifact,
            ReviewArtifactDecisionRequest request, AgentUpdatesFrozenSources sources) {
        throw new UnsupportedOperationException("结构化草案采用适配尚未装配");
    }
}
