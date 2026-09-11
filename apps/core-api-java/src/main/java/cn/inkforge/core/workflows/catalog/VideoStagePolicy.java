package cn.inkforge.core.workflows.catalog;

import java.util.List;

/** 视频模型业务的封闭阶段策略，不提供可配置 DAG。 */
public final class VideoStagePolicy {
    /** 仅供未装配旧源码编译；stages() 不再接受该策略。 */
    @Deprecated(forRemoval = true)
    public static final String CINEMATIC = "video.cinematic-stages.v1";
    /** 仅供未装配旧源码编译；stages() 不再接受该策略。 */
    @Deprecated(forRemoval = true)
    public static final String PROMPT = "video.shot-prompt-stages.v1";
    public static final String EPISODE_SCRIPT = "video.episode-script-stages.v1";
    public static final String EPISODE_STORYBOARD = "video.episode-storyboard-stages.v1";

    private VideoStagePolicy() {}

    public static List<Limit> stages(String operationKey, String policy) {
        if (java.util.Set.of("video.episode_script_generate", "video.episode_script_revise").contains(operationKey)
                && EPISODE_SCRIPT.equals(policy)) {
            return List.of(new Limit("episode_script", 2), new Limit("episode_script_review", 2));
        }
        if (java.util.Set.of("video.episode_storyboard_generate", "video.episode_storyboard_revise")
                        .contains(operationKey)
                && EPISODE_STORYBOARD.equals(policy)) {
            return List.of(
                    new Limit("episode_storyboard", 2),
                    new Limit("episode_storyboard_review", 2));
        }
        throw new IllegalStateException("视频阶段策略与 Operation 不匹配或版本不受支持");
    }

    public record Limit(String stageKey, int maxInvocations) {}
}
