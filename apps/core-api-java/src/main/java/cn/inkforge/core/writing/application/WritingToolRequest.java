package cn.inkforge.core.writing.application;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** Agent 工具调用在认证、资源绑定和处理器之间传递的不可变请求。 */
public record WritingToolRequest(
        String userId,
        String novelId,
        String taskId,
        String runId,
        String jobId,
        String agentId,
        String toolName,
        Map<String, Object> arguments) {

    public WritingToolRequest {
        arguments = Collections.unmodifiableMap(new LinkedHashMap<>(
                arguments == null ? Map.of() : arguments));
    }
}
