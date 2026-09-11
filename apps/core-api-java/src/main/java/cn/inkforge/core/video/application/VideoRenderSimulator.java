package cn.inkforge.core.video.application;

/** 默认模拟执行的本地媒体端口，不访问任何供应商地址。 */
public interface VideoRenderSimulator {
    boolean available();

    ArchivedVideoRender render(VideoRenderClaim claim);

    /** 独立剧集分支复用同一 FFmpeg 模拟器，但保持原生 episode/baseline 身份。 */
    default ArchivedVideoRender render(VideoEpisodeRenderClaim claim) {
        throw new UnsupportedOperationException("当前模拟器不支持独立剧集任务");
    }
}
