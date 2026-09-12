package cn.inkforge.core.video.application;

/** 默认模拟执行的本地媒体端口，不访问任何供应商地址。 */
public interface VideoRenderSimulator {
    boolean available();

    ArchivedVideoRender render(VideoEpisodeRenderClaim claim);
}
