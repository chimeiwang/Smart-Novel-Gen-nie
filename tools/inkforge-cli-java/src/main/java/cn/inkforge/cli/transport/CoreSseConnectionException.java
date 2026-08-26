package cn.inkforge.cli.transport;

/** SSE 已建立或读取期间意外断开；观察器可据此执行有界重连。 */
public final class CoreSseConnectionException extends RuntimeException {

    public CoreSseConnectionException() {
        super("SSE 连接意外中断");
    }
}
