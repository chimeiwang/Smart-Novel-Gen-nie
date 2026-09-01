package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import tools.jackson.databind.ObjectMapper;

/** Agent 工作流消息的稳定元数据；启动命令与终态回调必须复用同一规范化实现。 */
public final class WorkflowMessageMetadata {

    private WorkflowMessageMetadata() {}

    public static String serialize(
            String taskId,
            String eventType,
            String content,
            String agentId,
            Object source,
            ObjectMapper json) {
        Objects.requireNonNull(taskId, "写作任务标识不能为空");
        Objects.requireNonNull(eventType, "消息事件类型不能为空");
        Objects.requireNonNull(content, "消息内容不能为空");
        Objects.requireNonNull(source, "消息来源不能为空");
        Objects.requireNonNull(json, "JSON 编解码器不能为空");
        String visible = content.strip();
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("source", source);
        metadata.put("taskId", taskId);
        metadata.put("eventType", eventType);
        metadata.put("agentId", agentId);
        metadata.put(
                "contentHash",
                CommandIdempotency.sha256(visible.getBytes(StandardCharsets.UTF_8))
                        .substring(0, 24));
        return new String(
                CommandIdempotency.canonicalJsonBytes(metadata, json),
                StandardCharsets.UTF_8);
    }
}
