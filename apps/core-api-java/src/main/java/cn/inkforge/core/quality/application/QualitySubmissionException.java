package cn.inkforge.core.quality.application;

/** Agent 网络或临时服务失败；运行仍保持可补投。 */
public final class QualitySubmissionException extends RuntimeException {

    private final String code;

    public QualitySubmissionException(String code) {
        super("质量检查提交暂时失败");
        this.code = code == null || code.isBlank() ? "QUALITY_SUBMIT_FAILED" : code;
    }

    public String code() {
        return code;
    }
}
