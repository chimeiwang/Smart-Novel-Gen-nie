package cn.inkforge.core.writing.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class WritingToolGatewayTest {

    @Test
    void 未授权智能体在资源查询和处理器之前被拒绝() {
        RecordingAuthorizer authorizer = new RecordingAuthorizer();
        boolean[] handled = {false};
        WritingToolGateway gateway = new WritingToolGateway(authorizer);
        gateway.register("submit_quality_report", java.util.Set.of("编辑"), false, request -> {
            handled[0] = true;
            return Map.of("content", "不应执行");
        });

        assertThatThrownBy(() -> gateway.execute(request(
                        "submit_quality_report", "写作", null, Map.of())))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(403);
                    assertThat(error.code()).isEqualTo("TOOL_AGENT_FORBIDDEN");
                });
        assertThat(authorizer.bindingCalled).isFalse();
        assertThat(handled[0]).isFalse();
    }

    @Test
    void 资源校验后完整返回超长工具结果() {
        RecordingAuthorizer authorizer = new RecordingAuthorizer();
        String complete = "完整结果".repeat(20_000);
        WritingToolGateway gateway = new WritingToolGateway(authorizer);
        gateway.register("get_writing_context", java.util.Set.of("写作"), true, request -> {
            assertThat(request.arguments()).containsEntry("query", "问题");
            return Map.of("content", complete);
        });

        Map<String, Object> result = gateway.execute(request(
                "get_writing_context", "写作", null, Map.of("query", "问题")));

        assertThat(authorizer.bindingCalled).isTrue();
        assertThat(result.get("content")).isEqualTo(complete);
    }

    @Test
    void 写工具必须携带并匹配当前耐久命令() {
        RecordingAuthorizer authorizer = new RecordingAuthorizer();
        WritingToolGateway gateway = new WritingToolGateway(authorizer);
        gateway.register("submit_artifact", java.util.Set.of("写作"), false, request -> Map.of());

        assertThatThrownBy(() -> gateway.execute(request(
                        "submit_artifact", "写作", null, Map.of())))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(409);
                    assertThat(error.code()).isEqualTo("WRITING_JOB_MISMATCH");
                });

        gateway.execute(request("submit_artifact", "写作", "command-1", Map.of()));
        assertThat(authorizer.jobCalled).isTrue();
    }

    @Test
    void 共享读取工具注册完整并严格校验参数() {
        RecordingAuthorizer authorizer = new RecordingAuthorizer();
        RecordingReadService service = new RecordingReadService();
        WritingToolGateway gateway = new WritingToolGateway(authorizer);
        WritingReadToolArguments.register(gateway, service);

        assertThat(gateway.registeredNames())
                .containsExactlyInAnyOrderElementsOf(WritingReadToolArguments.names());
        assertThat(gateway.registeredNames()).allSatisfy(name -> assertThat(gateway.isReadOnly(name)).isTrue());

        gateway.execute(request("get_recent_chapters", "写作", null, Map.of("count", 20)));
        assertThat(service.lastArguments).containsExactlyEntriesOf(Map.of("count", 20));

        assertArgumentsInvalid(gateway, "get_recent_chapters", Map.of("count", 21));
        assertArgumentsInvalid(gateway, "get_review_artifact", Map.of("artifactId", "artifact-1"));
        assertArgumentsInvalid(gateway, "get_outline_node", Map.of());

        Map<String, Object> semantic = new LinkedHashMap<>();
        semantic.put("query", "文字");
        semantic.put("topK", 5);
        semantic.put("query_embedding", java.util.List.of(0.1, 0.2));
        gateway.execute(request("semantic_search_references", "写作", null, semantic));
        assertThat(service.lastArguments).containsExactlyEntriesOf(semantic);
    }

    private static void assertArgumentsInvalid(
            WritingToolGateway gateway, String name, Map<String, Object> arguments) {
        assertThatThrownBy(() -> gateway.execute(request(name, "写作", null, arguments)))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(422);
                    assertThat(error.code()).isEqualTo("TOOL_ARGUMENTS_INVALID");
                });
    }

    private static WritingToolRequest request(
            String name, String agentId, String jobId, Map<String, Object> arguments) {
        return new WritingToolRequest(
                "user-1",
                "novel-1",
                "task-1",
                "run-1",
                jobId,
                agentId,
                name,
                arguments);
    }

    private static final class RecordingAuthorizer implements WritingToolAuthorizer {
        private boolean bindingCalled;
        private boolean jobCalled;

        @Override
        public void requireBinding(String userId, String novelId, String taskId) {
            assertThat(userId).isEqualTo("user-1");
            assertThat(novelId).isEqualTo("novel-1");
            assertThat(taskId).isEqualTo("task-1");
            bindingCalled = true;
        }

        @Override
        public void requireWritingJob(
                String userId, String novelId, String taskId, String jobId) {
            requireBinding(userId, novelId, taskId);
            assertThat(jobId).isEqualTo("command-1");
            jobCalled = true;
        }
    }

    private static final class RecordingReadService implements WritingReadToolExecutor {
        private Map<String, Object> lastArguments;

        @Override
        public Map<String, Object> execute(WritingToolRequest request) {
            lastArguments = request.arguments();
            return Map.of("tool", request.toolName(), "arguments", request.arguments());
        }
    }
}
