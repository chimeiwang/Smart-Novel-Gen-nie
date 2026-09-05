package cn.inkforge.core.workflows.catalog;

import java.util.List;

/** 两项既有视频模型业务的封闭阶段策略，不提供可配置 DAG。 */
public final class VideoStagePolicy {
    public static final String CINEMATIC = "video.cinematic-stages.v1";
    public static final String PROMPT = "video.shot-prompt-stages.v1";

    private VideoStagePolicy() {}

    public static List<Limit> stages(String operationKey, String policy) {
        if ("video.chapter_cinematic_adaptation_v2".equals(operationKey) && CINEMATIC.equals(policy)) {
            return List.of(new Limit("dramatic_structure", 2), new Limit("shot_design", 3),
                    new Limit("missing_beat_shots", 3), new Limit("cinematic_review", 2));
        }
        if ("video.chapter_shot_prompt_v2".equals(operationKey) && PROMPT.equals(policy)) {
            return List.of(new Limit("shot_prompt", 2));
        }
        throw new IllegalStateException("视频阶段策略与 Operation 不匹配或版本不受支持");
    }

    public record Limit(String stageKey, int maxInvocations) {}
}
