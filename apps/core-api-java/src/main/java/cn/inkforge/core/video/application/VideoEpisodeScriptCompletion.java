package cn.inkforge.core.video.application;

import java.util.Map;
import org.jooq.DSLContext;

/** 独立剧集候选的领域物化端口；候选与业务任务共享事务，不触碰工作稿或正式版。 */
public interface VideoEpisodeScriptCompletion {
    boolean targetExists(DSLContext transaction, String runId);

    /** 返回新建或幂等回读的候选 Artifact 身份，作者采用由另一个 Core 命令完成。 */
    String completeCandidate(DSLContext transaction, String runId,
            Map<String, Object> document, Map<String, Object> review);
}
