package cn.inkforge.core.video.application;

/** 查询同一供应商任务暂时失败，耐久任务可安全稍后重查。 */
public final class VideoRenderQueryException extends RuntimeException {

    public VideoRenderQueryException() {
        super("Seedance 查询暂时失败");
    }
}
