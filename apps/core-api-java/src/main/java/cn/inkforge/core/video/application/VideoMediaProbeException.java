package cn.inkforge.core.video.application;

/** ffprobe 无法返回可信正有限时长时抛出；不得把原始工具输出泄漏给浏览器。 */
public final class VideoMediaProbeException extends RuntimeException {

    public VideoMediaProbeException(String message) {
        super(message);
    }

    public VideoMediaProbeException(String message, Throwable cause) {
        super(message, cause);
    }
}
