package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

class DurableAgentUpdatesArtifactTest {
    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final TypeReference<Map<String, Object>> OBJECT = new TypeReference<>() {};
    private static final String HASH = "a".repeat(64);
    private static final Map<String, Object> PROVIDER_SCHEMA = providerSchema();

    @ParameterizedTest(name = "{0}")
    @MethodSource("parityCases")
    void 跨语言固定候选保持相同接受结果(String name, boolean accepted, Map<String, Object> provider) {
        Map<String, Object> result = result(provider);
        if (accepted) {
            assertThatCode(() -> DurableAgentUpdatesArtifact.validateOutput(result, PROVIDER_SCHEMA)).doesNotThrowAnyException();
        } else {
            assertThatThrownBy(() -> DurableAgentUpdatesArtifact.validateOutput(result, PROVIDER_SCHEMA))
                    .as(name).isInstanceOf(IllegalArgumentException.class);
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {"create_lore", "revise_lore", "create_outline", "revise_outline", "manage_foreshadowing"})
    void 五项操作只保存一份候选并绑定原始身份(String operation) {
        String fullText = "  完整候选😀\r\n".repeat(5000) + "尾部不可丢失";
        Map<String, Object> output = result(Map.of("summary", " ", "updates", Map.of("worldSetting", fullText)));
        var stored = DurableAgentUpdatesArtifact.create(operation, "bundle", HASH, "novel", output, "step", HASH, PROVIDER_SCHEMA);
        assertThat(stored.payload()).containsEntry("operation", operation).containsEntry("novelId", "novel")
                .doesNotContainKeys("before", "after", "materializedUpdates", "expectedUpdatedAt");
        assertThat(stored.diff()).containsOnlyKeys("schema", "type");
        assertThat(DurableAgentUpdatesArtifact.reconstruct(operation, stored.payload(), stored.diff(), "bundle", HASH,
                "novel", "step", HASH, PROVIDER_SCHEMA)).isEqualTo(output);
        assertThat(DurableAgentUpdatesArtifact.output(stored.payload(), PROVIDER_SCHEMA)).isEqualTo(output);
    }

    @Test
    @SuppressWarnings("unchecked")
    void 字段缺省显式空值和嵌套候选均不被序列化或调用方修改覆盖() {
        Map<String, Object> character = new LinkedHashMap<>(Map.of("action", "update", "id", "c"));
        character.put("aliases", null);
        Map<String, Object> updates = new LinkedHashMap<>(Map.of("characters", new ArrayList<>(List.of(character)), "worldSetting", ""));
        var output = result(Map.of("summary", "原说明", "updates", updates));
        var stored = DurableAgentUpdatesArtifact.create("revise_lore", "bundle", HASH, "novel", output, "step", HASH, PROVIDER_SCHEMA);
        character.put("aliases", "调用方随后修改");
        updates.put("storyBackground", "不可改变已冻结数据");
        Map<String, Object> preserved = (Map<String, Object>) stored.payload().get("updates");
        Map<String, Object> item = (Map<String, Object>) ((List<?>) preserved.get("characters")).getFirst();
        assertThat(item).containsEntry("aliases", null).doesNotContainKey("factionId");
        assertThat(preserved).doesNotContainKey("storyBackground").containsEntry("worldSetting", "");
        assertThatThrownBy(() -> item.put("name", "篡改")).isInstanceOf(UnsupportedOperationException.class);
        assertThatThrownBy(() -> ((List<?>) preserved.get("characters")).clear()).isInstanceOf(UnsupportedOperationException.class);
        assertThat(DurableAgentUpdatesArtifact.output(stored.payload(), PROVIDER_SCHEMA).get("updatesSha256"))
                .isEqualTo(output.get("updatesSha256"));
    }

    @Test
    void 结果字段和哈希必须精确且缺省与显式null不能互换() {
        Map<String, Object> value = result(Map.of("summary", "说明", "updates", Map.of("worldSetting", "")));
        for (String field : List.of("updatesSha256", "extra", "summary")) {
            Map<String, Object> invalid = new LinkedHashMap<>(value);
            invalid.put(field, field.equals("summary") ? "" : "非法值");
            assertThatThrownBy(() -> DurableAgentUpdatesArtifact.validateOutput(invalid, PROVIDER_SCHEMA))
                    .isInstanceOf(IllegalArgumentException.class);
        }
        value.remove("updatesSha256");
        assertThatThrownBy(() -> DurableAgentUpdatesArtifact.validateOutput(value, PROVIDER_SCHEMA))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 候选哈希和绑定身份不一致不能当作可重建结果() {
        var output = result(Map.of("summary", "说明", "updates", Map.of("worldSetting", "")));
        var stored = DurableAgentUpdatesArtifact.create("revise_lore", "bundle", HASH, "novel", output, "step", HASH, PROVIDER_SCHEMA);
        for (String field : List.of("schema", "kind", "operation", "novelId", "evidenceBundleId", "evidenceManifestSha256",
                "producingStepId", "producingResultHash", "updatesSha256", "extra")) {
            Map<String, Object> corrupt = new LinkedHashMap<>(stored.payload());
            corrupt.put(field, "");
            assertThatThrownBy(() -> DurableAgentUpdatesArtifact.reconstruct("revise_lore", corrupt, stored.diff(),
                    "bundle", HASH, "novel", "step", HASH, PROVIDER_SCHEMA)).isInstanceOfSatisfying(ApiException.class,
                            error -> assertThat(error.code()).isEqualTo("ARTIFACT_REVISION_INTEGRITY_ERROR"));
        }
        assertThatThrownBy(() -> DurableAgentUpdatesArtifact.reconstruct("create_lore", stored.payload(), stored.diff(),
                "bundle", HASH, "novel", "step", HASH, PROVIDER_SCHEMA)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> DurableAgentUpdatesArtifact.reconstruct("revise_lore", stored.payload(), Map.of(),
                "bundle", HASH, "novel", "step", HASH, PROVIDER_SCHEMA)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> DurableAgentUpdatesArtifact.create("write_chapter", "bundle", HASH, "novel", output,
                "step", HASH, PROVIDER_SCHEMA)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 格式合法的生成Step或结果Hash替换仍须与权威生产记录匹配() {
        var output = result(Map.of("summary", "说明", "updates", Map.of("worldSetting", "")));
        var stored = DurableAgentUpdatesArtifact.create("revise_lore", "bundle", HASH, "novel", output, "step", HASH, PROVIDER_SCHEMA);
        for (Map<String, Object> replacement : List.of(Map.<String, Object>of("producingStepId", "other-step"),
                Map.<String, Object>of("producingResultHash", "b".repeat(64)))) {
            Map<String, Object> corrupt = new LinkedHashMap<>(stored.payload());
            corrupt.putAll(replacement);
            assertThatThrownBy(() -> DurableAgentUpdatesArtifact.reconstruct("revise_lore", corrupt, stored.diff(),
                    "bundle", HASH, "novel", "step", HASH, PROVIDER_SCHEMA)).isInstanceOf(ApiException.class);
        }
    }

    private static Map<String, Object> result(Map<String, Object> provider) {
        Map<String, Object> result = new LinkedHashMap<>(provider);
        result.put("updatesSha256", ExecutionCanonicalJson.sha256(provider.get("updates")));
        return result;
    }

    private static Stream<Arguments> parityCases() throws Exception {
        try (var input = DurableAgentUpdatesArtifactTest.class.getResourceAsStream("/protocol-fixtures/agent-updates-semantics.v1.json")) {
            List<Map<String, Object>> cases = JSON.readValue(input, new TypeReference<>() {});
            return cases.stream().map(value -> Arguments.of(value.get("name"), value.get("accept"), value.get("value")));
        }
    }

    private static Map<String, Object> providerSchema() {
        try (var input = DurableAgentUpdatesArtifactTest.class.getResourceAsStream("/agent-execution/output-schema-registry.v1.json")) {
            var root = JSON.readTree(input);
            for (var schema : root.path("schemas")) {
                if (schema.path("key").asString().equals("output.agent_updates.v2")) {
                    assertThat(schema.path("sha256").asString())
                            .isEqualTo("1ebda5ea441d2f421199725ebdad05f9add5abc44875e040252e2b41810a3467");
                    return JSON.convertValue(schema.path("jsonSchema"), OBJECT);
                }
            }
            throw new IllegalStateException("缺少结构化资料的严格 Provider Schema");
        } catch (Exception exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }
}
