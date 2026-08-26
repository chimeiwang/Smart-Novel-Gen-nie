package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.VideoPlanCallReservationRequest;
import cn.inkforge.contracts.api.VideoPlanCallReservationResponse;
import cn.inkforge.contracts.api.VideoPlanCompletionCallback;
import cn.inkforge.contracts.api.VideoPlanFailureCallback;
import cn.inkforge.contracts.api.VideoPlanProgressQuery;
import cn.inkforge.contracts.api.VideoPlanProgressResponse;
import cn.inkforge.contracts.api.VideoStoryPlanCheckpointCallback;

/** 已存在旧 VideoScene 任务的唯一收敛端口；不提供创建、重试或返工入口。 */
public interface LegacyVideoPlanStore {

    VideoPlanProgressResponse getProgress(VideoPlanProgressQuery query);

    VideoPlanCallReservationResponse reserveCall(VideoPlanCallReservationRequest request);

    void saveCheckpoint(VideoStoryPlanCheckpointCallback callback);

    void complete(VideoPlanCompletionCallback callback);

    void fail(VideoPlanFailureCallback callback);
}
