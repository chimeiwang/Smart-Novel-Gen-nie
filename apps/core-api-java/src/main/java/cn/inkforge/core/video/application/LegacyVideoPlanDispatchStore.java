package cn.inkforge.core.video.application;

import java.util.List;

/** 已存在旧 VideoScene 任务的后台补投端口；不承载 Agent 回调状态机。 */
public interface LegacyVideoPlanDispatchStore {

    List<VideoAdaptationTaskDispatch> claimDue(int limit);

    void markSubmitted(String taskId);

    void recordDispatchFailure(String taskId, String errorCode, boolean transientFailure);

    void settleDispatchTerminal(String taskId, VideoAdaptationAgentStatus status);
}
