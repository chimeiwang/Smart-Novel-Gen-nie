package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class WorkflowResolvedModelTest {

    @Test
    void 解析模型必须绑定公开材料并匹配逻辑授权() {
        String fingerprint = WorkflowResolvedModel.fingerprint(
                "deployment.writer.chapter_selection.v1",
                "openai_compatible",
                "deepseek-v4-flash",
                "transport.deepseek-v4.v1",
                "endpoint.deepseek-official.v1",
                "chat_json_output_v1",
                "capability.deepseek-v4.chat-json.v1",
                "bounded",
                false);
        WorkflowResolvedModel resolved = new WorkflowResolvedModel(
                "deployment.writer.chapter_selection.v1",
                fingerprint,
                "openai_compatible",
                "deepseek-v4-flash",
                "transport.deepseek-v4.v1",
                "endpoint.deepseek-official.v1",
                "chat_json_output_v1",
                "capability.deepseek-v4.chat-json.v1",
                "bounded",
                false);
        WorkflowModelProfile logical = new WorkflowModelProfile(
                "writer.chapter_selection.v1",
                1,
                "bounded",
                "deployment.writer.chapter_selection.v1");

        assertThat(resolved.requireAuthorizedBy(logical)).isSameAs(resolved);
        assertThat(fingerprint)
                .isEqualTo("85be298fe59d3f12031f6bcdc0be909bb57153e5aa1b7527a1fb75b2d911301c");
    }

    @Test
    void 拒绝指纹篡改和部署键或reasoning漂移() {
        assertThatThrownBy(() -> new WorkflowResolvedModel(
                        "deployment.writer.chapter_selection.v1",
                        "0".repeat(64),
                        "openai_compatible",
                        "deepseek-v4-flash",
                        "transport.deepseek-v4.v1",
                        "endpoint.deepseek-official.v1",
                        "chat_json_output_v1",
                        "capability.deepseek-v4.chat-json.v1",
                        "bounded",
                        false))
                .hasMessageContaining("fingerprint");

        String fingerprint = WorkflowResolvedModel.fingerprint(
                "deployment.writer.chapter_selection.v1",
                "openai_compatible",
                "deepseek-v4-flash",
                "transport.deepseek-v4.v1",
                "endpoint.deepseek-official.v1",
                "chat_json_output_v1",
                "capability.deepseek-v4.chat-json.v1",
                "bounded",
                false);
        WorkflowResolvedModel resolved = new WorkflowResolvedModel(
                "deployment.writer.chapter_selection.v1",
                fingerprint,
                "openai_compatible",
                "deepseek-v4-flash",
                "transport.deepseek-v4.v1",
                "endpoint.deepseek-official.v1",
                "chat_json_output_v1",
                "capability.deepseek-v4.chat-json.v1",
                "bounded",
                false);
        assertThatThrownBy(() -> resolved.requireAuthorizedBy(new WorkflowModelProfile(
                        "writer.chapter_selection.v1",
                        1,
                        "disabled",
                        "deployment.writer.chapter_selection.v1")))
                .hasMessageContaining("超出");
    }
}
