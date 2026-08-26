package cn.inkforge.core.video.application;

/** Agent 明确确认创建请求未被供应商接受。 */
public final class VideoRenderSubmissionRejectedException extends RuntimeException {

    public VideoRenderSubmissionRejectedException(String detail) {
        super(detail);
    }
}
