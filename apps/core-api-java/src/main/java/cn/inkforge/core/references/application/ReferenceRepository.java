package cn.inkforge.core.references.application;

import cn.inkforge.core.references.domain.RagDispatchRecord;
import cn.inkforge.core.references.domain.RagDispatchStatus;
import cn.inkforge.core.references.domain.RagIndexIntent;
import cn.inkforge.core.references.domain.RagSearchHit;
import cn.inkforge.core.references.domain.ReferenceCreateResult;
import cn.inkforge.core.references.domain.ReferenceData;
import cn.inkforge.core.references.domain.ReferenceDeleteImpact;
import cn.inkforge.core.references.domain.ReferencePatch;
import cn.inkforge.core.references.domain.ReferenceSnapshot;
import cn.inkforge.core.references.domain.ReferenceUpdateResult;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;

/** 参考资料正式事实、RAG 派生状态和后台投递状态的唯一持久化端口。 */
public interface ReferenceRepository {

    List<ReferenceSnapshot> list(String novelId, String userId);

    ReferenceCreateResult create(
            String novelId,
            String userId,
            String clientRequestId,
            ReferenceData data,
            boolean indexEnabled);

    ReferenceUpdateResult update(
            String novelId,
            String userId,
            String referenceId,
            ReferencePatch patch,
            OffsetDateTime expectedUpdatedAt,
            boolean indexEnabled);

    ReferenceDeleteImpact delete(
            String novelId,
            String userId,
            String referenceId,
            OffsetDateTime expectedUpdatedAt);

    ReferenceSnapshot requireIndexContext(
            String novelId,
            String userId,
            String referenceId,
            String taskId,
            String runId,
            String expectedContentHash);

    ReferenceSnapshot replaceIndex(
            String novelId,
            String referenceId,
            String taskId,
            String runId,
            String expectedContentHash,
            List<List<BigDecimal>> embeddings);

    RagIndexIntent prepareReindex(
            String novelId,
            String userId,
            String referenceId,
            String expectedContentHash);

    void markIndexFailed(
            String novelId,
            String referenceId,
            String taskId,
            String runId,
            String expectedContentHash,
            String message);

    List<RagSearchHit> search(
            String novelId, String userId, List<BigDecimal> embedding, int topK);

    List<RagDispatchRecord> listPending(int limit);

    void markDispatchTerminal(RagDispatchRecord record, RagDispatchStatus status);
}
