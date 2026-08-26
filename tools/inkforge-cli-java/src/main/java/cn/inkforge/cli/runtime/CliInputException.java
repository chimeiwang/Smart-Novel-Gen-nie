package cn.inkforge.cli.runtime;

/** 可安全返回给调用方的本地输入错误。 */
public final class CliInputException extends RuntimeException {

    private final String code;
    private final int exitCode;

    public CliInputException(String code, String message) {
        this(code, message, 2);
    }

    public CliInputException(String code, String message, int exitCode) {
        super(message);
        this.code = code;
        this.exitCode = exitCode;
    }

    public String code() {
        return code;
    }

    public int exitCode() {
        return exitCode;
    }
}
