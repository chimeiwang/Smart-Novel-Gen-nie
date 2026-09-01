package cn.inkforge.core.platform.http;

import java.io.IOException;

/** 已完成同步校验、可交给单条 SSE 连接执行的协议流。 */
public interface SseStream extends AutoCloseable {

    /** 在调用线程顺序发送协议帧；返回表示终态或调用方已要求停止。 */
    void run(FrameSender sender) throws IOException;

    /** 关闭只释放本连接资源，不改变远端任务状态。 */
    @Override
    default void close() {}

    /** 单次发送一个已经完整格式化的 UTF-8 SSE frame。 */
    @FunctionalInterface
    interface FrameSender {

        void send(String frame) throws IOException;
    }
}
