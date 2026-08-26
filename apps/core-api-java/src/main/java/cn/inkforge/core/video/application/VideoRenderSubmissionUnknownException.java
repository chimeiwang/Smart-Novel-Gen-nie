package cn.inkforge.core.video.application;

/** 创建请求可能已经到达供应商，必须停止自动重提以避免重复计费。 */
public final class VideoRenderSubmissionUnknownException extends RuntimeException {

    public VideoRenderSubmissionUnknownException() {
        super("Seedance 创建结果未知");
    }
}
