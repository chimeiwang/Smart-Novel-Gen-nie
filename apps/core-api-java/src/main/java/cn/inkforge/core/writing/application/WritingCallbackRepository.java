package cn.inkforge.core.writing.application;

import cn.inkforge.core.writing.domain.WritingBoundaryEvent;
import cn.inkforge.core.writing.domain.WritingCallbackAcceptance;
import java.util.Map;

/** 检查点、终态回调、命令与 Outbox 的单事务端口。 */
public interface WritingCallbackRepository {

    TaskResources resources(String taskId);

    WritingCallbackAcceptance authorize(String taskId, String jobId);

    WritingCallbackAcceptance markProcessing(String taskId, String jobId, int sequence);

    WritingCallbackAcceptance saveCheckpoint(
            String taskId,
            String jobId,
            String serialized,
            String phase,
            int sequence,
            WritingBoundaryEvent boundary);

    WritingCallbackAcceptance complete(
            String taskId,
            String jobId,
            Map<String, Object> result,
            String visibleResponse,
            int sequence,
            WritingBoundaryEvent boundary);

    WritingCallbackAcceptance fail(
            String taskId,
            String jobId,
            String code,
            int sequence,
            WritingBoundaryEvent boundary);

    record TaskResources(String novelId, String userId) {}
}
