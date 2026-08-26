package cn.inkforge.core.writing.application;

import cn.inkforge.core.writing.domain.WritingEvent;
import java.util.List;
import java.util.Map;

/** 写作 SSE 的短期 Redis Stream 端口。 */
public interface WritingEventStore {

    boolean validateSource(
            String taskId,
            String sourceEventId,
            int sequence,
            String event,
            Map<String, Object> data);

    boolean validate(
            String taskId,
            String sourceEventId,
            int sequence,
            String event,
            Map<String, Object> data,
            int durableBaseline,
            boolean allowRebase);

    WritingEvent appendAgent(
            String taskId,
            String sourceEventId,
            int sequence,
            String event,
            Map<String, Object> data,
            int durableBaseline,
            boolean allowRebase);

    List<WritingEvent> replay(String taskId, String lastEventId);
}
