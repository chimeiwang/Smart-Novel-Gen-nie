package cn.inkforge.core.writing.application;

import cn.inkforge.core.platform.http.ApiException;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Agent 工具的唯一注册和授权入口；处理器执行前先完成工具、智能体与资源三层校验。 */
public final class WritingToolGateway {

    private final WritingToolAuthorizer authorizer;
    private final Map<String, Registration> registrations = new LinkedHashMap<>();

    public WritingToolGateway(WritingToolAuthorizer authorizer) {
        this.authorizer = Objects.requireNonNull(authorizer);
    }

    public void register(
            String name,
            Set<String> agentIds,
            boolean readOnly,
            WritingToolHandler handler) {
        if (name == null
                || name.isBlank()
                || registrations.containsKey(name)
                || agentIds == null
                || agentIds.isEmpty()
                || handler == null) {
            throw new IllegalArgumentException("工具注册信息无效或名称重复");
        }
        registrations.put(name, new Registration(Set.copyOf(agentIds), readOnly, handler));
    }

    public Map<String, Object> execute(WritingToolRequest request) {
        Objects.requireNonNull(request);
        Registration registration = registration(request.toolName());
        if (!registration.agentIds().contains(request.agentId())) {
            throw new ApiException(403, "TOOL_AGENT_FORBIDDEN", "当前智能体无权调用该工具");
        }
        authorizer.requireBinding(request.userId(), request.novelId(), request.taskId());
        if (!registration.readOnly()) {
            if (request.jobId() == null || request.jobId().isEmpty()) {
                throw new ApiException(409, "WRITING_JOB_MISMATCH", "写入工具缺少当前作业标识");
            }
            authorizer.requireWritingJob(
                    request.userId(), request.novelId(), request.taskId(), request.jobId());
        }
        Map<String, Object> result = registration.handler().handle(request);
        if (result == null) throw new IllegalStateException("工具处理器必须返回对象");
        // 这里只复制容器，不检查或截断结果正文。
        return Collections.unmodifiableMap(new LinkedHashMap<>(result));
    }

    public boolean isReadOnly(String name) {
        return registration(name).readOnly();
    }

    public Set<String> registeredNames() {
        return Collections.unmodifiableSet(registrations.keySet());
    }

    private Registration registration(String name) {
        Registration value = registrations.get(name);
        if (value == null) {
            throw new ApiException(404, "TOOL_NOT_FOUND", "工具不存在或未注册");
        }
        return value;
    }

    private record Registration(
            Set<String> agentIds,
            boolean readOnly,
            WritingToolHandler handler) {}
}
