package cn.inkforge.core.workflows.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class ExecutionRegistryTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @Test
    void 只解析目录中真实启用且依赖完整的首个纵切() {
        ExecutionRegistry registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);

        assertThat(registry.enabledOperationKeys("long_serial", false))
                .containsExactly(
                        "long_serial.answer_question",
                        "long_serial.rewrite_chapter_selection");
        ExecutionRegistry.ResolvedOperation resolved =
                registry.resolve("long_serial.rewrite_chapter_selection", false);

        assertThat(resolved.operation().v2Enabled()).isTrue();
        assertThat(resolved.operation().developmentOnly()).isFalse();
        assertThat(resolved.operation().runBudget().maxModelCalls()).isEqualTo(6);
        assertThat(resolved.operation().runBudget().maxProtocolCorrectionSteps()).isEqualTo(1);
        assertThat(resolved.generatorProfile().deploymentProfileKey())
                .isEqualTo("deployment.writer.chapter_selection.v1");
        assertThat(resolved.generatorProfile().promptProfile().key())
                .isEqualTo("prompt.writer.chapter_selection.v1");
        assertThat(sha256(resolved.generatorProfile()
                        .promptProfile()
                        .systemPrompt()
                        .getBytes(java.nio.charset.StandardCharsets.UTF_8)))
                .isEqualTo(resolved.generatorProfile().promptProfile().sha256());
        assertThat(resolved.generatorStepBudget().budget().maxModelCalls()).isEqualTo(1);
        assertThat(resolved.generatorStepBudget().budget().maxInputTokens()).isEqualTo(30_000);
        assertThat(resolved.outputSchema().jsonSchema())
                .containsKeys("type", "additionalProperties", "required", "properties");
        assertThat(resolved.outputSchema().jsonSchema().get("required"))
                .isEqualTo(java.util.List.of("replacement"));
        assertThat(resolved.reviewers())
                .extracting(reviewer -> reviewer.profile().key())
                .containsExactly("reviewer.consistency.v1", "reviewer.editorial.v1");
        assertThat(resolved.reviewers())
                .allSatisfy(reviewer -> assertThat(reviewer.stepBudget().budget().maxModelCalls())
                        .isEqualTo(1));
        assertThat(resolved.reviewers())
                .extracting(reviewer -> reviewer.profile().promptProfile().sha256())
                .doesNotHaveDuplicates();
        assertThat(resolved.reviewerOutputSchema().purpose()).isEqualTo("evaluation");
        assertThat(resolved.operation().reviewPolicy().rubricVersion())
                .isEqualTo("rubric.chapter_selection.review.v1");
        assertThat(resolved.operation().reviewPolicy().evidencePolicy())
                .isEqualTo("evidence.review.same_bundle_artifact_revision.v1");
        assertThat(resolved.operation().reviewPolicy().lane()).isEqualTo("interactive");
    }

    @Test
    void 未启用操作和系统用途不能借目录存在绕过门禁() {
        ExecutionRegistry registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);

        assertThatThrownBy(() -> registry.resolve("long_serial.write_chapter", false))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("尚未启用");
        assertThatThrownBy(() -> registry.resolve(
                        "video.chapter_cinematic_adaptation_v2", false))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("尚未启用");
        assertThatThrownBy(() -> registry.resolveSystemPurpose("protocol_correction"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("尚未启用");
    }

    @Test
    void deployment授权绑定传输端点能力和运行环境() {
        ExecutionRegistry testing =
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        ExecutionRegistry.AuthorizedDeployment fake =
                testing.requireAuthorizedDeployment(resolved(
                        "fake",
                        "fake",
                        "transport.fake.v1",
                        "endpoint.local-fake.v1",
                        "responses_json_schema_v1",
                        "capability.fake.structured-output.v1",
                        true));
        assertThat(fake.billable()).isFalse();
        assertThat(fake.pricingVersion()).isEqualTo("credit-pricing.v1");

        ExecutionRegistry production =
                ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.PRODUCTION);
        assertThatThrownBy(() -> production.requireAuthorizedDeployment(resolved(
                        "fake",
                        "fake",
                        "transport.fake.v1",
                        "endpoint.local-fake.v1",
                        "responses_json_schema_v1",
                        "capability.fake.structured-output.v1",
                        true)))
                .hasMessageContaining("当前环境");
        ExecutionRegistry.AuthorizedDeployment deepseek =
                production.requireAuthorizedDeployment(resolved(
                        "openai_compatible",
                        "deepseek-v4-flash",
                        "transport.deepseek-v4.v1",
                        "endpoint.deepseek-official.v1",
                        "chat_json_output_v1",
                        "capability.deepseek-v4.chat-json.v1",
                        false));
        assertThat(deepseek.billable()).isTrue();

        assertThatThrownBy(() -> production.requireAuthorizedDeployment(resolved(
                        "openai_compatible",
                        "deepseek-v4-flash",
                        "transport.openai-compatible.v1",
                        "endpoint.deepseek-official.v1",
                        "chat_json_output_v1",
                        "capability.openai-compatible.structured-output.v1",
                        false)))
                .hasMessageContaining("未被");
        assertThatThrownBy(() -> production.requireAuthorizedDeployment(resolved(
                        "openai_compatible",
                        "deepseek-v4-flash",
                        "transport.deepseek-v4.v1",
                        "endpoint.deepseek-custom.v1",
                        "chat_json_output_v1",
                        "capability.deepseek-v4.chat-json.v1",
                        false)))
                .hasMessageContaining("当前环境");
    }

    @Test
    void run总预算与单step预算保持独立语义() {
        ExecutionRegistry registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        ExecutionRegistry.Operation operation =
                registry.requireKnownOperation("long_serial.rewrite_chapter_selection");
        ExecutionRegistry.ResolvedOperation resolved =
                registry.resolve("long_serial.rewrite_chapter_selection", false);

        assertThat(operation.runBudget().maxModelCalls()).isEqualTo(6);
        assertThat(operation.runBudget().maxProviderRetriesPerStep()).isEqualTo(2);
        assertThat(resolved.generatorStepBudget().budget().maxModelCalls()).isEqualTo(1);
        assertThat(resolved.generatorStepBudget().budget().maxProviderRetries()).isEqualTo(2);
    }

    @Test
    void 任一manifest文档字节漂移都会阻止启动() {
        Map<String, byte[]> documents = classpathDocuments();
        byte[] catalog = documents.get("operation-catalog.v1.json");
        byte[] tampered = new byte[catalog.length + 1];
        System.arraycopy(catalog, 0, tampered, 0, catalog.length);
        tampered[tampered.length - 1] = '\n';
        documents.put("operation-catalog.v1.json", tampered);

        assertThatThrownBy(() -> ExecutionRegistry.load(documents::get))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("哈希不一致");
    }

    @Test
    void prompt正文即使重算manifest哈希也不能绕过内层绑定() {
        Map<String, byte[]> documents = classpathDocuments();
        JsonNode prompts = JSON.readTree(documents.get("prompt-profile-registry.v1.json"));
        findByKey(prompts.get("prompts"), "prompt.writer.chapter_selection.v1")
                .asObject()
                .put("systemPrompt", "被篡改的 prompt");
        replaceDocumentAndHash(
                documents,
                "promptProfileRegistry",
                "prompt-profile-registry.v1.json",
                JSON.writeValueAsBytes(prompts));

        assertThatThrownBy(() -> ExecutionRegistry.load(documents::get))
                .hasMessageContaining("Prompt Profile UTF-8 SHA-256");
    }

    @Test
    void manifest缺项未知项和JSON重复key全部failClosed() {
        Map<String, byte[]> missing = classpathDocuments();
        JsonNode missingManifest = JSON.readTree(missing.get("manifest.json"));
        missingManifest.asObject().remove("stepBudgetRegistry");
        missing.put("manifest.json", JSON.writeValueAsBytes(missingManifest));
        assertThatThrownBy(() -> ExecutionRegistry.load(missing::get))
                .hasMessageContaining("文档集合");

        Map<String, byte[]> unknown = classpathDocuments();
        JsonNode unknownManifest = JSON.readTree(unknown.get("manifest.json"));
        unknownManifest.asObject().putObject("unknownRegistry")
                .put("path", "unknown.json")
                .put("sha256", "0".repeat(64));
        unknown.put("manifest.json", JSON.writeValueAsBytes(unknownManifest));
        assertThatThrownBy(() -> ExecutionRegistry.load(unknown::get))
                .hasMessageContaining("未知条目");

        Map<String, byte[]> duplicate = classpathDocuments();
        String profiles = new String(
                duplicate.get("profile-registry.v1.json"), java.nio.charset.StandardCharsets.UTF_8);
        profiles = profiles.replaceFirst(
                "\"registryVersion\": \"1\"",
                "\"registryVersion\": \"1\",\\n  \"registryVersion\": \"1\"");
        replaceDocumentAndHash(
                duplicate,
                "profileRegistry",
                "profile-registry.v1.json",
                profiles.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        assertThatThrownBy(() -> ExecutionRegistry.load(duplicate::get))
                .hasMessageContaining("严格解析");
    }

    @Test
    void 启用操作不能引用未支持Profile或不完整Reviewer预算映射() {
        Map<String, byte[]> unsupported = classpathDocuments();
        JsonNode profiles = JSON.readTree(unsupported.get("profile-registry.v1.json"));
        findByKey(profiles.get("profiles"), "writer.chapter_selection.v1")
                .asObject()
                .put("supported", false);
        replaceDocumentAndHash(
                unsupported,
                "profileRegistry",
                "profile-registry.v1.json",
                JSON.writeValueAsBytes(profiles));
        ExecutionRegistry unsupportedRegistry = ExecutionRegistry.load(unsupported::get);
        assertThatThrownBy(() -> unsupportedRegistry.resolve(
                        "long_serial.rewrite_chapter_selection", false))
                .hasMessageContaining("尚未实现");

        Map<String, byte[]> incomplete = classpathDocuments();
        JsonNode catalog = JSON.readTree(incomplete.get("operation-catalog.v1.json"));
        findByKey(catalog.get("operations"), "long_serial.rewrite_chapter_selection")
                .get("reviewPolicy")
                .get("reviewerStepBudgetProfiles")
                .asObject()
                .remove("reviewer.editorial.v1");
        replaceDocumentAndHash(
                incomplete,
                "catalog",
                "operation-catalog.v1.json",
                JSON.writeValueAsBytes(catalog));
        assertThatThrownBy(() -> ExecutionRegistry.load(incomplete::get))
                .hasMessageContaining("Reviewer 策略缺少精确");
    }

    private static Map<String, byte[]> classpathDocuments() {
        String[] paths = {
            "manifest.json",
            "operation-catalog.v1.json",
            "operation-catalog.schema.json",
            "profile-registry.v1.json",
            "profile-registry.schema.json",
            "deployment-profile-registry.v1.json",
            "deployment-profile-registry.schema.json",
            "prompt-profile-registry.v1.json",
            "prompt-profile-registry.schema.json",
            "output-schema-registry.v1.json",
            "output-schema-registry.schema.json",
            "system-purpose-registry.v1.json",
            "system-purpose-registry.schema.json",
            "step-budget-registry.v1.json",
            "step-budget-registry.schema.json",
            "hash-vectors.v1.json"
        };
        Map<String, byte[]> result = new HashMap<>();
        for (String path : paths) result.put(path, resource(path));
        return result;
    }

    private static WorkflowResolvedModel resolved(
            String provider,
            String model,
            String transportProfile,
            String endpointProfile,
            String structuredOutputRoute,
            String capabilityVersion,
            boolean supportsRequestIdempotency) {
        String deployment = "deployment.writer.chapter_selection.v1";
        String fingerprint = WorkflowResolvedModel.fingerprint(
                deployment,
                provider,
                model,
                transportProfile,
                endpointProfile,
                structuredOutputRoute,
                capabilityVersion,
                "bounded",
                supportsRequestIdempotency);
        return new WorkflowResolvedModel(
                deployment,
                fingerprint,
                provider,
                model,
                transportProfile,
                endpointProfile,
                structuredOutputRoute,
                capabilityVersion,
                "bounded",
                supportsRequestIdempotency);
    }

    private static void replaceDocumentAndHash(
            Map<String, byte[]> documents,
            String manifestEntry,
            String path,
            byte[] replacement) {
        documents.put(path, replacement);
        JsonNode manifest = JSON.readTree(documents.get("manifest.json"));
        manifest.get(manifestEntry).asObject().put("sha256", sha256(replacement));
        documents.put("manifest.json", JSON.writeValueAsBytes(manifest));
    }

    private static JsonNode findByKey(JsonNode values, String key) {
        for (JsonNode value : values) {
            if (key.equals(value.get("key").asString())) return value;
        }
        throw new IllegalStateException("测试夹具缺少 key：" + key);
    }

    private static String sha256(byte[] value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private static byte[] resource(String path) {
        try (InputStream input = ExecutionRegistryTest.class
                .getResourceAsStream("/agent-execution/" + path)) {
            if (input == null) throw new IllegalStateException("缺少测试资源：" + path);
            return input.readAllBytes();
        } catch (IOException exception) {
            throw new IllegalStateException("读取测试资源失败：" + path, exception);
        }
    }
}
