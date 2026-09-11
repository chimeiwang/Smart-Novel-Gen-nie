package cn.inkforge.core.video.application;

/** 独立剧集协调器一次只能对同一耐久任务执行 submit 或 query。 */
public record VideoEpisodeRenderClaim(
        String taskId,
        String episodeId,
        String productionBaselineId,
        String projectId,
        String novelId,
        String shotId,
        String shotVersionId,
        String status,
        String providerTaskId,
        int pollCount,
        String inputHash,
        VideoEpisodeRenderInput input) {

    public boolean submission() {
        return "submitting".equals(status);
    }
}
