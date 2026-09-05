package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Set;
import org.junit.jupiter.api.Test;

class WorkflowResultMaterializerRegistryTest {

    @Test
    void 既有审阅与两种改写都有独立语义的物化入口() {
        assertThat(WorkflowResultMaterializerRegistry.supportedOperationKeys()).contains(
                "long_serial.review_chapter", "long_serial.rewrite_scene", "long_serial.rewrite_outline_selection");
    }

    @Test
    void 支持集合允许保留旧Operation但拒绝启用Operation漏接物化器() {
        Set<String> supported = WorkflowResultMaterializerRegistry.supportedOperationKeys();

        assertThat(supported)
                .contains(
                        "long_serial.answer_question",
                        "long_serial.rewrite_chapter_selection");
        WorkflowResultMaterializerRegistry.requireEnabledOperationKeys(
                Set.of("long_serial.answer_question"));
        assertThatThrownBy(() -> WorkflowResultMaterializerRegistry.requireEnabledOperationKeys(
                        Set.of("long_serial.answer_question", "long_serial.future_operation")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("long_serial.future_operation");
    }
}
