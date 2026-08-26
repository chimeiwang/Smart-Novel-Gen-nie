package cn.inkforge.core.video.application;

/** 受控媒体执行失败，code 可进入耐久导出任务，message 不得静默截断。 */
public final class VideoMediaProcessingException extends RuntimeException {

    private final String code;

    public VideoMediaProcessingException(String code, String message) {
        super(message);
        this.code = code;
    }

    public VideoMediaProcessingException(String code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
