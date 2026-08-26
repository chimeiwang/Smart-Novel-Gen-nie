package cn.inkforge.core.reviews.application;

import cn.inkforge.contracts.api.ArtifactConflictQuarantineRequest;
import cn.inkforge.contracts.api.ArtifactConflictQuarantineResponse;
import cn.inkforge.contracts.api.ArtifactDecisionAcceptedResponse;
import cn.inkforge.contracts.api.CreateArtifactRequest;
import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;
import cn.inkforge.contracts.api.ReviewArtifactListResponse;
import cn.inkforge.contracts.api.ReviewArtifactResponse;
import cn.inkforge.contracts.api.SubmitArtifactEvaluationRequest;
import cn.inkforge.core.reviews.domain.ReviewArtifactSummary;
import java.util.List;

/** ReviewArtifact 读取、Agent 修订与复审结论的持久化端口。 */
public interface ReviewRepository {

    ReviewArtifactResponse get(String userId, String artifactId);

    ReviewArtifactResponse getTaskArtifact(String userId, String taskId);

    ReviewArtifactListResponse list(
            String userId,
            String novelId,
            String chapterId,
            String taskId,
            String status,
            String kind,
            String cursor,
            int limit);

    /** Agent 读取工具使用的完整任务摘要集合；此读取不分页，也不得静默截断。 */
    List<ReviewArtifactSummary> listTaskSummaries(
            String userId,
            String novelId,
            String taskId,
            String status,
            String kind);

    ReviewArtifactResponse createOrRevise(CreateArtifactRequest request);

    ReviewArtifactResponse submitEvaluation(
            String artifactId, SubmitArtifactEvaluationRequest request);

    ArtifactConflictQuarantineResponse quarantine(
            String artifactId, ArtifactConflictQuarantineRequest request);

    ArtifactDecisionAcceptedResponse decide(
            String userId, String artifactId, ReviewArtifactDecisionRequest request);
}
