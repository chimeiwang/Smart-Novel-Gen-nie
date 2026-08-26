package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.ChapterAdaptationTaskResponse;
import cn.inkforge.contracts.api.DramaticStructureCheckpoint;
import cn.inkforge.contracts.api.StartPromptRunRequest;
import cn.inkforge.contracts.api.StartShotPlanRunRequest;
import cn.inkforge.contracts.api.VideoAdaptationCheckpointCallback;
import cn.inkforge.contracts.api.VideoAdaptationFailureCallback;
import cn.inkforge.contracts.api.VideoAdaptationPlanCompletionCallback;
import cn.inkforge.contracts.api.VideoAdaptationPromptCompletionCallback;
import cn.inkforge.contracts.api.VideoAdaptationWorkflowProgressQuery;
import cn.inkforge.contracts.api.VideoAdaptationWorkflowProgressResponse;
import java.util.List;

/** 章节拆镜和逐镜提示词耐久任务、投递租约与回调状态机。 */
public interface VideoAdaptationTaskStore {

    VideoAdaptationTaskAcceptance createPlanTask(
            String userId, String adaptationId, StartShotPlanRunRequest request);

    VideoAdaptationTaskAcceptance createPromptTask(
            String userId, String adaptationId, StartPromptRunRequest request);

    ChapterAdaptationTaskResponse getTask(String userId, String taskId);

    List<VideoAdaptationTaskDispatch> claimDue(int limit);

    void markSubmitted(String taskId);

    void recordDispatchFailure(String taskId, String errorCode, boolean transientFailure);

    void settleDispatchTerminal(String taskId, VideoAdaptationAgentStatus status);

    VideoAdaptationWorkflowProgressResponse progress(
            VideoAdaptationWorkflowProgressQuery query);

    void saveCheckpoint(VideoAdaptationCheckpointCallback callback);

    void completePlan(VideoAdaptationPlanCompletionCallback callback);

    void completePrompts(VideoAdaptationPromptCompletionCallback callback);

    void fail(VideoAdaptationFailureCallback callback);
}
