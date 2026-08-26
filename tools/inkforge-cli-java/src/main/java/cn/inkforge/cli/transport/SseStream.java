package cn.inkforge.cli.transport;

import java.util.Iterator;
import tools.jackson.databind.JsonNode;

/** 必须显式关闭的逐事件 SSE 流。 */
public interface SseStream extends Iterator<JsonNode>, AutoCloseable {

    @Override
    void close();
}
