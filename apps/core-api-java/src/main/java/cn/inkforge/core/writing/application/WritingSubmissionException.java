package cn.inkforge.core.writing.application;

/** Agent HTTP/队列暂时不可用；命令保留在 PostgreSQL 等待补投。 */
public final class WritingSubmissionException extends RuntimeException {

    private final String code;

    public WritingSubmissionException(String code) {
        super(code);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
