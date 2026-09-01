package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class WorkflowMessageMetadataTest {

    private final ObjectMapper json = new ObjectMapper();

    @Test
    void 普通流程消息必须与Python使用相同的规范化JSON() {
        String value = WorkflowMessageMetadata.serialize(
                "task-1", "user", "  完整消息  ", null, "workflow", json);

        assertThat(value).isEqualTo(
                "{\"agentId\":null,\"contentHash\":\"f0235a9050ab3322eae4e125\","
                        + "\"eventType\":\"user\",\"source\":\"workflow\",\"taskId\":\"task-1\"}");
    }

    @Test
    void 选区来源必须替换source且递归稳定排序() {
        Map<String, Object> selection = new LinkedHashMap<>();
        selection.put("start", 2);
        selection.put("chapterId", "chapter-1");
        selection.put("end", 8);

        String value = WorkflowMessageMetadata.serialize(
                "task-2", "user", "完整消息", null, selection, json);

        assertThat(value).contains(
                "\"source\":{\"chapterId\":\"chapter-1\",\"end\":8,\"start\":2}");
    }
}
