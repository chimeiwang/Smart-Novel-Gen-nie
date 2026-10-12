package cn.inkforge.core.workflows.application;

import java.util.Map;
import org.jooq.DSLContext;

/** 单集分镜候选物化端口；完成不得修改工作稿、正式分镜或制作基线。 */
public interface WorkflowVideoEpisodeStoryboardCompletion {
    boolean targetExists(DSLContext transaction, String runId);

    /** 返回新建或幂等回读的候选 Artifact；采用由另一条带 revision CAS 的命令完成。 */
    String completeCandidate(
            DSLContext transaction,
            String runId,
            Map<String, Object> document,
            Map<String, Object> review);
}
