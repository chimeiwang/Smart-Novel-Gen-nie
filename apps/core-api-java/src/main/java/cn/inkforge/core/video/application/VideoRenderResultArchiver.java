package cn.inkforge.core.video.application;

/** 视频域只依赖“安全归档结果”，不感知具体 HTTP 客户端。 */
@FunctionalInterface
public interface VideoRenderResultArchiver {

    ArchivedVideoRender archive(String projectId, String assetId, String videoUrl);

    /** 可选尾帧使用同一 URL 白名单和受控存储策略归档；默认实现保持旧测试替身兼容。 */
    default ArchivedVideoFrame archiveImage(
            String projectId, String assetId, String imageUrl) {
        throw new UnsupportedOperationException("当前归档器不支持尾帧图片");
    }
}
