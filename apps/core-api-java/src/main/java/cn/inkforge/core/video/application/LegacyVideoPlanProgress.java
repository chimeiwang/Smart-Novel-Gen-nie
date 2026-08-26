package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.SceneAssetsStageArguments;
import cn.inkforge.contracts.api.StoryPlanStageArguments;
import cn.inkforge.contracts.api.VideoPlanAttemptState;
import java.util.List;

/** 已退役 VideoScene 任务仍需收敛的耐久阶段事实；不得用于创建新的旧任务。 */
public record LegacyVideoPlanProgress(
        String checkpointStage,
        SceneAssetsStageArguments sceneAssetsPlan,
        StoryPlanStageArguments storyPlan,
        VideoPlanAttemptState attemptState,
        List<Reservation> reservations,
        String inheritedFromTaskId,
        String inheritedInputFingerprint) {

    public LegacyVideoPlanProgress {
        reservations = List.copyOf(reservations);
    }

    /** 单次供应商调用预留；列表顺序就是不可变调用序号。 */
    public record Reservation(
            String eventId,
            String checkpointStage,
            String stage,
            int reservedCallsBefore) {}
}
