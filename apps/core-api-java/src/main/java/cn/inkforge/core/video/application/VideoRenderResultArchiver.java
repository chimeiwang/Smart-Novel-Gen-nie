package cn.inkforge.core.video.application;

/** 视频域只依赖“安全归档结果”，不感知具体 HTTP 客户端。 */
@FunctionalInterface
public interface VideoRenderResultArchiver {

    ArchivedVideoRender archive(String projectId, String assetId, String videoUrl);
}
