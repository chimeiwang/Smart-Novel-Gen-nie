package cn.inkforge.core.references.application;

/** Agent 网关暂时未接受 RAG 任务；不携带地址、远端正文或底层异常。 */
public final class RagSubmissionException extends RuntimeException {

    private final String code;

    public RagSubmissionException(String code) {
        super("检索索引任务投递失败");
        this.code = java.util.Objects.requireNonNull(code);
    }

    public String code() {
        return code;
    }
}
