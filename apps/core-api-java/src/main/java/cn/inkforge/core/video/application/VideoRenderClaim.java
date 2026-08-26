package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.VideoShotRenderManifest;

/** 协调器一次只能对供应商执行 submit 或 query 中的一种短操作。 */
public record VideoRenderClaim(
        String taskId,
        String projectId,
        String novelId,
        String status,
        String providerTaskId,
        int pollCount,
        String inputHash,
        VideoShotRenderManifest manifest) {

    public boolean submission() {
        return "submitting".equals(status);
    }
}
