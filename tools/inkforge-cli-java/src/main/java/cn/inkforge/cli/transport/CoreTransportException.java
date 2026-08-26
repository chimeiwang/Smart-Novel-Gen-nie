package cn.inkforge.cli.transport;

/** 网络层只暴露稳定公共错误，不附带可能含凭据的底层异常文本。 */
public final class CoreTransportException extends RuntimeException {

    public CoreTransportException() {
        super("Core API 连接失败");
    }
}
