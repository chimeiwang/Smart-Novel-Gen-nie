package cn.inkforge.core.video.application;

/** Agent 提交失败；网络与服务暂不可用可由同一耐久任务安全重试。 */
public final class VideoAdaptationSubmissionException extends RuntimeException {

    private final String code;

    public VideoAdaptationSubmissionException(String code) {
        super("章节影视化任务提交失败");
        this.code = code;
    }

    public String code() {
        return code;
    }
}
