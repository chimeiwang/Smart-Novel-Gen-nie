package cn.inkforge.core.styles.application;

/** Agent 网关暂时未接受画像任务。 */
public final class PortraitSubmissionException extends RuntimeException {

    private final String code;

    public PortraitSubmissionException(String code) {
        super("画像任务投递失败");
        this.code = java.util.Objects.requireNonNull(code);
    }

    public String code() {
        return code;
    }
}
