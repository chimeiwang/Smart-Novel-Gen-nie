package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ExecutionStepResult;
import cn.inkforge.contracts.api.PlotProgressRequest;
import cn.inkforge.contracts.api.ProposedCommand;
import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.exc.InvalidNullException;

/** 直接使用应用扫描产生的 mapper，不在测试中单独安装模块。 */
@SpringBootTest(
        classes = CoreApplication.class,
        properties = {"DATABASE_URL=false", "REDIS_URL=false"})
class WorkflowProposedCommandJsonConfigurationTest {

    private static final String RESOLVED = """
            {"workflow":"long_serial","operation":"write_chapter","confidence":0.9}
            """;

    @Autowired
    private ObjectMapper json;

    @Test
    void 应用实际Mapper拒绝显式空参数且嵌套回调同样生效() {
        String explicitNull = """
                {"workflow":"long_serial","operation":"write_chapter",
                 "confidence":0.9,"arguments":null}
                """;

        assertThatThrownBy(() -> json.readValue(explicitNull, ProposedCommand.class))
                .isInstanceOf(InvalidNullException.class);
        assertThatThrownBy(() -> json.readValue(
                "{\"proposedCommand\":" + explicitNull + "}", ExecutionStepResult.class))
                .isInstanceOf(InvalidNullException.class);
    }

    @Test
    void 缺省参数仍由共享兼容投影补空对象且哈希等同显式空对象() {
        ProposedCommand missing = json.readValue(RESOLVED, ProposedCommand.class);
        ProposedCommand empty = json.readValue("""
                {"workflow":"long_serial","operation":"write_chapter",
                 "confidence":0.9,"arguments":{}}
                """, ProposedCommand.class);

        assertThat(missing.getArguments()).isNull();
        assertThat(WorkflowCallbackValues.proposedCommandMap(missing))
                .containsEntry("arguments", Map.of());
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.proposedCommandMap(missing)))
                .isEqualTo(ExecutionCanonicalJson.sha256(
                        WorkflowCallbackValues.proposedCommandMap(empty)));
    }

    @Test
    void 非空对象完整透传且不改变内层空值或原文() {
        String payload = """
                {"workflow":"long_serial","operation":"write_chapter","confidence":0.9,
                 "arguments":{"message":"  完整😀\\r\\n要求  ","nested":{"value":null}}}
                """;
        ProposedCommand command = json.readValue(payload, ProposedCommand.class);
        JsonNode arguments = json.valueToTree(command.getArguments());

        assertThat(arguments).isEqualTo(json.readTree(payload).get("arguments"));
        assertThat(command.getArguments()).containsEntry("message", "  完整😀\r\n要求  ");
    }

    @Test
    void 精确字段约束不改变其他可空DTO字段() {
        PlotProgressRequest progress = json.readValue("""
                {"currentStage":"第一幕","expectedUpdatedAt":null}
                """, PlotProgressRequest.class);
        ProposedCommand command = json.readValue("""
                {"workflow":null,"operation":null,"targetId":null,"confidence":0.2,
                 "clarification":{"code":"uncertain","prompt":"  请选择\\r\\n  "}}
                """, ProposedCommand.class);

        assertThat(progress.getExpectedUpdatedAt().isPresent()).isTrue();
        assertThat(progress.getExpectedUpdatedAt().orElse(null)).isNull();
        assertThat(command.getWorkflow().isPresent()).isTrue();
        assertThat(command.getWorkflow().orElse(null)).isNull();
        assertThat(command.getClarification().getPrompt()).isEqualTo("  请选择\r\n  ");
    }
}
