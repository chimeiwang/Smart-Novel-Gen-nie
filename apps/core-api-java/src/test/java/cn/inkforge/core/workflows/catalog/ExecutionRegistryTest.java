package cn.inkforge.core.workflows.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class ExecutionRegistryTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @Test
    void RAG配置绑定不能被复制给聊天或改为用户收费() {
        for (String mutation : List.of("other-profile", "billable", "unknown-field", "empty-environments")) {
            Map<String, byte[]> documents = classpathDocuments();
            JsonNode deployment = JSON.readTree(documents.get("deployment-profile-registry.v1.json"));
            var rag = findByKey(deployment.get("profiles"), "deployment.rag.embedding.v2").asObject();
            switch (mutation) {
                case "other-profile" -> rag.put("key", "deployment.other.embedding.v2");
                case "billable" -> rag.get("configuredBinding").asObject().put("billable", true);
                case "unknown-field" -> rag.get("configuredBinding").asObject().put("allowAnyModel", true);
                case "empty-environments" -> rag.get("configuredBinding").asObject().putArray("allowedEnvironments");
                default -> throw new IllegalStateException("未知测试变体");
            }
            replaceDocumentAndHash(documents, "deploymentProfileRegistry", "deployment-profile-registry.v1.json", JSON.writeValueAsBytes(deployment));
            assertThatThrownBy(() -> ExecutionRegistry.load(documents::get, ExecutionRegistry.Environment.TEST))
                    .as(mutation).isInstanceOf(IllegalStateException.class);
        }
    }

    @Test
    void 只解析目录中真实启用且依赖完整的纵切() {
        ExecutionRegistry registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);

        assertThat(registry.enabledOperationKeys("long_serial", false))
                .containsExactly(
                        "long_serial.answer_question",
                        "long_serial.create_lore",
                        "long_serial.create_outline",
                        "long_serial.manage_foreshadowing",
                        "long_serial.plan_chapter",
                        "long_serial.review_chapter",
                        "long_serial.revise_lore",
                        "long_serial.revise_outline",
                        "long_serial.rewrite_chapter_selection",
                        "long_serial.rewrite_outline_selection",
                        "long_serial.rewrite_scene",
                        "long_serial.write_chapter");
        assertThat(registry.enabledOperationKeys("style", false)).containsExactly("style.portrait");
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
    void 章节规划冻结专用生成复审与四调用预算() {
        ExecutionRegistry registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        ExecutionRegistry.ResolvedOperation plan = registry.resolve("long_serial.plan_chapter", false);
        assertThat(plan.generatorProfile().key()).isEqualTo("plot.chapter_plan.v1");
        assertThat(plan.generatorProfile().promptProfile().systemPrompt()).contains("章节规划");
        assertThat(plan.outputSchema().jsonSchema().get("required"))
                .isEqualTo(java.util.List.of("title", "summary", "chapterGoal", "sceneBeats"));
        assertThat(plan.reviewers()).extracting(reviewer -> reviewer.profile().key())
                .containsExactly("reviewer.chapter_plan_editorial.v1");
        assertThat(plan.operation().reviewPolicy().rubricVersion()).isEqualTo("rubric.chapter_plan.review.v1");
        assertThat(plan.operation().reviewPolicy().maxAutomaticRevisions()).isEqualTo(1);
        assertThat(plan.operation().runBudget().maxModelCalls()).isEqualTo(4);
        assertThat(plan.generatorStepBudget().budget().maxPromptCacheMissTokens()).isEqualTo(30_000);
        assertThat(plan.reviewers().getFirst().stepBudget().budget().maxPromptCacheMissTokens())
                .isEqualTo(30_000);
        assertThat(plan.operation().runBudget().maxPromptCacheMissTokens()).isEqualTo(120_000);
    }

    @Test
    void 未启用操作和系统用途不能借目录存在绕过门禁() {
        ExecutionRegistry registry = ExecutionRegistryFixtures.selectionOperationDownlined(
                ExecutionRegistry.Environment.TEST);

        assertThatThrownBy(() -> registry.resolve("long_serial.rewrite_chapter_selection", false))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("尚未启用");
        assertThatThrownBy(() -> registry.resolve(
                        "video.chapter_cinematic_adaptation_v2", false))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("开发专用");
        assertThatThrownBy(() -> registry.resolveSystemPurpose("summarize_evidence"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("尚未启用");
    }

    @Test
    void 画像冻结五次串行纯文本预算且不借用质量纠正或审核计划() {
        ExecutionRegistry registry = ExecutionRegistryFixtures.styleOperationEnabled(ExecutionRegistry.Environment.TEST);
        ExecutionPlanSnapshot plan = registry.freezePlan("style.portrait", false);
        assertThat(plan.generator().lane()).isEqualTo("batch_media");
        assertThat(plan.generator().modelProfile().profile()).isEqualTo("style.portrait.v2");
        assertThat(plan.generator().modelProfile().deploymentProfileKey()).isEqualTo("deployment.style.portrait.v2");
        assertThat(plan.generator().outputSchema().name()).isEqualTo("output.style_portrait_section.v2");
        assertThat(plan.generator().stepBudget().budget().maxModelCalls()).isEqualTo(1);
        assertThat(plan.generator().stepBudget().budget().maxProtocolCorrections()).isZero();
        assertThat(plan.runBudget().maxModelCalls()).isEqualTo(5);
        assertThat(plan.runBudget().maxPromptCacheMissTokens()).isEqualTo(300000);
        assertThat(plan.runBudget().maxProtocolCorrectionSteps()).isZero();
        assertThat(plan.systemSteps()).isEmpty();
        assertThat(plan.reviewers()).isEmpty();
        assertThat(ExecutionPlanSnapshot.fromStored(plan.stored()).stored()).isEqualTo(plan.stored());
        ExecutionRegistry production = ExecutionRegistryFixtures.styleOperationEnabled(ExecutionRegistry.Environment.PRODUCTION);
        JsonNode profile = findByKey(JSON.readTree(classpathDocuments().get("deployment-profile-registry.v1.json")).get("profiles"),
                "deployment.style.portrait.v2");
        boolean found = false;
        for (JsonNode model : profile.get("allowedModels")) {
            boolean allowed = false;
            for (JsonNode environment : model.get("allowedEnvironments")) {
                if ("production".equals(environment.asString())) allowed = true;
            }
            if (!allowed) continue;
            found = true;
            assertThat(production.requireAuthorizedDeployment(resolved("deployment.style.portrait.v2", model, "plain_text_v1"))
                    .structuredOutputRoute()).isEqualTo("plain_text_v1");
            for (String wrong : List.of("chat_json_output_v1", "quality_strict_tool_v1")) {
                assertThatThrownBy(() -> production.requireAuthorizedDeployment(resolved("deployment.style.portrait.v2", model, wrong)))
                        .isInstanceOf(IllegalStateException.class).hasMessageContaining("未被");
            }
        }
        assertThat(found).isTrue();
    }

    @Test
    void 质量计划只冻结自身获准的一次独立协议纠正() {
        ExecutionRegistry registry = ExecutionRegistryFixtures.qualityOperationEnabled(ExecutionRegistry.Environment.TEST);
        ExecutionPlanSnapshot plan = registry.freezePlan("quality.consistency", false);

        assertThat(plan.generator().modelProfile().profile()).isEqualTo("quality.consistency.v2");
        assertThat(plan.systemSteps()).hasSize(1);
        ExecutionPlanSnapshot.Step correction = plan.systemSteps().getFirst();
        assertThat(correction.purpose()).isEqualTo("protocol_correction");
        assertThat(correction.modelProfile().profile()).isEqualTo("system.quality_protocol_corrector.v2");
        assertThat(correction.outputSchema().name()).isEqualTo("output.consistency_quality_report.v2");
        assertThat(correction.stepBudget().profile()).isEqualTo("step_budget.system.quality_protocol_correction.v2");
        assertThat(correction.stepBudget().budget().maxModelCalls()).isEqualTo(1);
        assertThat(correction.stepBudget().budget().maxProtocolCorrections()).isEqualTo(1);
        assertThat(plan.runBudget().maxModelCalls()).isEqualTo(2);
        assertThat(plan.runBudget().maxProtocolCorrectionSteps()).isEqualTo(1);
        assertThat(plan.reviewers()).isEmpty();
        assertThat(ExecutionPlanSnapshot.fromStored(plan.stored()).systemSteps()).containsExactly(correction);
        for (String workflow : List.of("long_serial", "short_medium")) {
            for (String key : registry.enabledOperationKeys(workflow, false)) {
                assertThat(registry.freezePlan(key, false).systemSteps()).as(key).isEmpty();
            }
        }
    }

    @Test
    void 未支持或没有精确父操作绑定的系统用途不会进入业务计划() {
        for (boolean supported : List.of(false, true)) {
            Map<String, byte[]> documents = qualityEnabledDocuments();
            JsonNode purposes = JSON.readTree(documents.get("system-purpose-registry.v1.json"));
            JsonNode correction = findByPurpose(purposes.get("purposes"), "protocol_correction");
            correction.asObject().put("supported", supported);
            if (supported) correction.asObject().putArray("parentOperations");
            replaceDocumentAndHash(documents, "systemPurposeRegistry", "system-purpose-registry.v1.json",
                    JSON.writeValueAsBytes(purposes));

            ExecutionRegistry registry = ExecutionRegistry.load(documents::get);
            assertThat(registry.freezePlan("quality.consistency", false).systemSteps()).isEmpty();
        }
    }

    @Test
    void 质量Strict路由只接受其完整部署授权元组且不能替换成普通JSON路由() {
        Map<String, byte[]> documents = classpathDocuments();
        ExecutionRegistry registry = ExecutionRegistryFixtures.qualityOperationEnabled(ExecutionRegistry.Environment.PRODUCTION);
        ExecutionPlanSnapshot plan = registry.freezePlan("quality.consistency", false);
        JsonNode profiles = JSON.readTree(documents.get("deployment-profile-registry.v1.json")).get("profiles");
        for (ExecutionPlanSnapshot.Step step : List.of(plan.generator(), plan.systemSteps().getFirst())) {
            String deployment = step.modelProfile().deploymentProfileKey();
            JsonNode profile = findByKey(profiles, deployment);
            boolean found = false;
            for (JsonNode model : profile.get("allowedModels")) {
                if (!"quality_strict_tool_v1".equals(model.get("structuredOutputRoute").asString())) continue;
                boolean production = false;
                for (JsonNode environment : model.get("allowedEnvironments")) {
                    if ("production".equals(environment.asString())) production = true;
                }
                if (!production) continue;
                found = true;
                WorkflowResolvedModel resolved = resolved(deployment, model, "quality_strict_tool_v1");
                assertThat(registry.requireAuthorizedDeployment(resolved).structuredOutputRoute())
                        .isEqualTo("quality_strict_tool_v1");
                assertThatThrownBy(() -> registry.requireAuthorizedDeployment(
                        resolved(deployment, model, "chat_json_output_v1")))
                        .isInstanceOf(IllegalStateException.class).hasMessageContaining("未被");
            }
            assertThat(found).as(deployment).isTrue();
        }
    }

    @Test
    void 正文冻结完整输出专用双复审和六调用总预算() {
        ExecutionRegistry registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        var draft = registry.resolve("long_serial.write_chapter", false);
        assertThat(draft.generatorProfile().key()).isEqualTo("writer.chapter_draft.v1");
        assertThat(draft.outputSchema().jsonSchema().get("required"))
                .isEqualTo(java.util.List.of("summary", "content"));
        assertThat(draft.reviewers()).extracting(reviewer -> reviewer.profile().key())
                .containsExactly("reviewer.chapter_draft_consistency.v1", "reviewer.chapter_draft_editorial.v1");
        assertThat(draft.operation().reviewPolicy().mergePolicy())
                .isEqualTo("review.chapter_draft.patch_or_author.v1");
        assertThat(draft.operation().reviewPolicy().maxAutomaticRevisions()).isEqualTo(1);
        assertThat(draft.operation().runBudget().maxModelCalls()).isEqualTo(6);
        assertThat(draft.operation().runBudget().profile()).isEqualTo("budget.long_serial.chapter_draft.v2");
        assertThat(draft.operation().runBudget().maxInputTokens()).isEqualTo(600_000);
        assertThat(draft.operation().runBudget().maxPromptCacheMissTokens()).isEqualTo(600_000);
        assertThat(draft.generatorStepBudget().key())
                .isEqualTo("step_budget.long_serial.write_chapter.generator.v2");
        assertThat(draft.generatorStepBudget().budget().maxInputTokens()).isEqualTo(100_000);
        assertThat(draft.generatorStepBudget().budget().maxPromptCacheMissTokens()).isEqualTo(100_000);
        assertThat(draft.generatorStepBudget().budget().maxCompletionTokens()).isEqualTo(16_000);
        assertThat(draft.reviewers())
                .extracting(reviewer -> reviewer.stepBudget().key())
                .containsExactly(
                        "step_budget.long_serial.write_chapter.reviewer_consistency.v2",
                        "step_budget.long_serial.write_chapter.reviewer_editorial.v2");
        assertThat(draft.reviewers()).allSatisfy(reviewer -> {
            assertThat(reviewer.profile().key()).startsWith("reviewer.chapter_draft_").endsWith(".v1");
            assertThat(reviewer.stepBudget().budget().maxInputTokens()).isEqualTo(100_000);
            assertThat(reviewer.stepBudget().budget().maxPromptCacheMissTokens()).isEqualTo(100_000);
            assertThat(reviewer.stepBudget().budget().maxReasoningTokens()).isZero();
        });
    }

    @Test
    void 场景改写继续使用原有v1输入与运行预算() {
        ExecutionRegistry registry = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
        var rewrite = registry.resolve("long_serial.rewrite_scene", false);

        assertThat(rewrite.generatorProfile().key()).isEqualTo("writer.scene_rewrite.v1");
        assertThat(rewrite.generatorStepBudget().key())
                .isEqualTo("step_budget.long_serial.rewrite_scene.generator.v1");
        assertThat(rewrite.generatorStepBudget().budget().maxInputTokens()).isEqualTo(30_000);
        assertThat(rewrite.generatorStepBudget().budget().maxPromptCacheMissTokens()).isEqualTo(30_000);
        assertThat(rewrite.operation().runBudget().profile()).isEqualTo("budget.long_serial.chapter_draft.v1");
        assertThat(rewrite.operation().runBudget().maxInputTokens()).isEqualTo(180_000);
        assertThat(rewrite.operation().runBudget().maxPromptCacheMissTokens()).isEqualTo(180_000);
        assertThat(rewrite.reviewers())
                .extracting(reviewer -> reviewer.stepBudget().key())
                .containsExactly(
                        "step_budget.long_serial.write_chapter.reviewer_consistency.v1",
                        "step_budget.long_serial.write_chapter.reviewer_editorial.v1");
        assertThat(rewrite.reviewers()).allSatisfy(reviewer -> {
            assertThat(reviewer.stepBudget().budget().maxInputTokens()).isEqualTo(30_000);
            assertThat(reviewer.stepBudget().budget().maxPromptCacheMissTokens()).isEqualTo(30_000);
        });
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

    private static Map<String, byte[]> qualityEnabledDocuments() {
        Map<String, byte[]> documents = classpathDocuments();
        JsonNode catalog = JSON.readTree(documents.get("operation-catalog.v1.json"));
        findByKey(catalog.get("operations"), "quality.consistency").asObject().put("v2Enabled", true);
        replaceDocumentAndHash(documents, "catalog", "operation-catalog.v1.json", JSON.writeValueAsBytes(catalog));
        return documents;
    }

    private static WorkflowResolvedModel resolved(String deployment, JsonNode model, String route) {
        String provider = model.get("provider").asString();
        String modelName = model.get("model").asString();
        String transport = model.get("transportProfile").asString();
        String endpoint = model.get("endpointProfile").asString();
        String capability = model.get("capabilityVersion").asString();
        String reasoning = model.get("reasoningMode").asString();
        boolean idempotent = model.get("supportsRequestIdempotency").asBoolean();
        String fingerprint = WorkflowResolvedModel.fingerprint(deployment, provider, modelName, transport,
                endpoint, route, capability, reasoning, idempotent);
        return new WorkflowResolvedModel(deployment, fingerprint, provider, modelName, transport, endpoint,
                route, capability, reasoning, idempotent);
    }

    private static JsonNode findByPurpose(JsonNode values, String purpose) {
        for (JsonNode value : values) {
            if (purpose.equals(value.get("purpose").asString())) return value;
        }
        throw new IllegalStateException("测试夹具缺少 purpose：" + purpose);
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
