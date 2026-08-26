package cn.inkforge.cli.runtime;

/** 文件输入输出失败的稳定本地错误边界。 */
public final class LocalFileException extends RuntimeException {

    public LocalFileException(String message) {
        super(message);
    }

    public LocalFileException(String message, Throwable cause) {
        super(message, cause);
    }
}
