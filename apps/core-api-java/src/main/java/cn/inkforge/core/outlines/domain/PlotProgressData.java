package cn.inkforge.core.outlines.domain;

/** 剧情进度单例的完整业务字段。 */
public record PlotProgressData(
        String currentStage,
        String currentGoal,
        String currentConflict,
        String nextMilestone) {}
