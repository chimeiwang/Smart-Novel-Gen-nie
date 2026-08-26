package cn.inkforge.core.reviews.application;

import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;

/** 把已锁定且已批准的审核产物写入正式领域数据；调用方负责外层原子事务。 */
public interface FormalArtifactWriter {

    int apply(
            String userId,
            ReviewArtifactState artifact,
            ReviewArtifactDecisionRequest request);
}
