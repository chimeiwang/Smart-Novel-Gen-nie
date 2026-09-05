package cn.inkforge.core.workflows.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

class IntentExecutionPlanSnapshotTest {

    private static final List<String> OPERATIONS = List.of(
            "long_serial.answer_question", "long_serial.plan_chapter", "long_serial.write_chapter");
    private static final List<String> FIVE_OPERATIONS = List.of(
            "long_serial.answer_question", "long_serial.plan_chapter", "long_serial.review_chapter",
            "long_serial.rewrite_scene", "long_serial.write_chapter");
    private final ObjectMapper json = new ObjectMapper();

    @Test
    void 冻结真实解析器与三个完整旧版子计划并可严格重建() {
        ExecutionRegistry registry = registry();
        IntentExecutionPlanSnapshot snapshot = IntentExecutionPlanSnapshot.freeze(registry, OPERATIONS);

        assertThat(snapshot.stored().get("planVersion")).isEqualTo("2");
        assertThat(snapshot.operationCatalogVersion()).isEqualTo(registry.catalogVersion());
        assertThat(snapshot.executionManifestFingerprint()).isEqualTo(registry.manifestFingerprint());
        assertThat(snapshot.resolver().purpose()).isEqualTo("resolve_intent");
        assertThat(snapshot.resolver().lane()).isEqualTo("interactive");
        assertThat(snapshot.resolver().modelProfile().profile()).isEqualTo("system.intent_resolver.v1");
        assertThat(snapshot.resolver().modelProfile().reasoningMode()).isEqualTo("disabled");
        assertThat(snapshot.resolver().modelProfile().promptProfile().name())
                .isEqualTo("prompt.system.intent_resolver.v1");
        assertThat(snapshot.resolver().outputSchema().name()).isEqualTo("output.proposed_command.v1");
        assertThat(snapshot.resolver().evidencePolicy()).isEqualTo("evidence.system.intent.v1");
        assertThat(snapshot.maxClarifications()).isEqualTo(2);
        assertThat(snapshot.maxResolverSteps()).isEqualTo(3);
        assertThat(snapshot.operationPlans()).extracting(plan -> plan.operation().key()).containsExactlyElementsOf(OPERATIONS);
        for (String operation : OPERATIONS) {
            ExecutionPlanSnapshot original = registry.freezePlan(operation, false);
            assertThat(snapshot.requireOperationPlan(operation).stored()).isEqualTo(original.stored());
            assertThat(snapshot.requireOperationPlan(operation, original.sha256()).sha256()).isEqualTo(original.sha256());
            assertThat(original.stored().get("planVersion")).isEqualTo("1");
        }
        assertThat(IntentExecutionPlanSnapshot.fromStored(copy(snapshot.stored())).stored()).isEqualTo(snapshot.stored());
        assertThat(json.writeValueAsString(snapshot.stored())).doesNotContain("systemPrompt", "endpointProfile", "apiKey");
        snapshot.requireInitialIdentity("long_serial", null, registry.catalogVersion());
    }

    @Test
    void 新计划冻结五项而旧三项存储计划继续按原内容恢复() {
        ExecutionRegistry registry = registry();
        IntentExecutionPlanSnapshot old = IntentExecutionPlanSnapshot.freeze(registry, OPERATIONS);
        Map<String, Object> oldStored = copy(old.stored());
        IntentExecutionPlanSnapshot current = IntentExecutionPlanSnapshot.freeze(registry, FIVE_OPERATIONS);
        assertThat(current.operationPlans()).extracting(plan -> plan.operation().key())
                .containsExactlyElementsOf(FIVE_OPERATIONS);
        IntentExecutionPlanSnapshot restoredOld = IntentExecutionPlanSnapshot.fromStored(oldStored);
        assertThat(restoredOld.stored()).isEqualTo(old.stored());
        assertThat(restoredOld.operationPlans()).extracting(plan -> plan.operation().key())
                .containsExactlyElementsOf(OPERATIONS);
        assertThat(current.requireOperationPlan("long_serial.review_chapter").operation().operation())
                .isEqualTo("review_chapter");
        assertThat(current.requireOperationPlan("long_serial.rewrite_scene").operation().operation())
                .isEqualTo("rewrite_scene");
        assertThatThrownBy(() -> current.requireOperationPlan("long_serial.rewrite_outline_selection"))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 总预算逐维取业务最大值后追加三次解析而每Step重试上限不累计() {
        IntentExecutionPlanSnapshot snapshot = snapshot();
        Map<String, Object> total = snapshot.runBudgetStored();
        Map<String, Object> resolver = snapshot.resolver().stepBudget().budgetMap();
        for (String key : List.of("maxModelCalls", "maxInputTokens", "maxPromptCacheMissTokens",
                "maxCompletionTokens", "maxReasoningTokens", "maxVisibleOutputTokens", "maxCostMicros", "maxWallClockSeconds")) {
            long businessMaximum = snapshot.operationPlans().stream()
                    .map(plan -> object(object(plan.stored().get("plan")).get("runBudget")))
                    .mapToLong(budget -> ((Number) budget.get(key)).longValue()).max().orElseThrow();
            assertThat(((Number) total.get(key)).longValue())
                    .as(key).isEqualTo(businessMaximum + 3 * ((Number) resolver.get(key)).longValue());
        }
        assertThat(snapshot.runBudget().maxProviderRetriesPerStep()).isEqualTo(2);
        assertThat(snapshot.runBudget().maxProtocolCorrectionSteps()).isEqualTo(
                snapshot.operationPlans().stream().mapToInt(plan -> plan.runBudget().maxProtocolCorrectionSteps()).max().orElseThrow());
        snapshot.runBudget().toDomain().requireStepFits(snapshot.resolver().stepBudget().budget());
    }

    @Test
    void 授权集合排序不影响哈希但未冻结的操作不能被选择() {
        IntentExecutionPlanSnapshot all = snapshot();
        assertThat(IntentExecutionPlanSnapshot.freeze(registry(), OPERATIONS.reversed()).stored()).isEqualTo(all.stored());
        IntentExecutionPlanSnapshot answerOnly = IntentExecutionPlanSnapshot.freeze(registry(), List.of(OPERATIONS.getFirst()));
        assertThat(answerOnly.operationPlans()).hasSize(1);
        assertThatThrownBy(() -> answerOnly.requireOperationPlan("long_serial.write_chapter"))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> all.requireOperationPlan(OPERATIONS.getFirst(), "0".repeat(64)))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 空授权重复授权和越界操作均明确拒绝而不静默过滤() {
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.freeze(registry(), List.of()))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.freeze(registry(), List.of(OPERATIONS.getFirst(), OPERATIONS.getFirst())))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.freeze(registry(), List.of("long_serial.rewrite_chapter_selection")))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.freeze(registry(), List.of("long_serial.unknown")))
                .isInstanceOf(IllegalStateException.class);
    }

    @ParameterizedTest
    @ValueSource(strings = {"root", "plan", "resolver", "modelProfile", "promptProfile", "stepBudget", "budget", "runBudget", "child"})
    void 任意结构层夹带额外字段即使重算外层哈希也拒绝(String location) {
        Map<String, Object> stored = copy(snapshot().stored());
        Map<String, Object> plan = object(stored.get("plan"));
        Map<String, Object> resolver = object(plan.get("resolver"));
        Map<String, Object> target = switch (location) {
            case "root" -> stored;
            case "plan" -> plan;
            case "resolver" -> resolver;
            case "modelProfile" -> object(resolver.get("modelProfile"));
            case "promptProfile" -> object(object(resolver.get("modelProfile")).get("promptProfile"));
            case "stepBudget" -> object(resolver.get("stepBudget"));
            case "budget" -> object(object(resolver.get("stepBudget")).get("budget"));
            case "runBudget" -> object(plan.get("runBudget"));
            case "child" -> children(plan).getFirst();
            default -> throw new AssertionError(location);
        };
        target.put("unexpected", "不允许的内容");
        rehash(stored);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(stored)).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 拒绝重复子操作错误子哈希和嵌入未授权的真实旧版操作() {
        Map<String, Object> duplicate = copy(snapshot().stored());
        List<Map<String, Object>> plans = children(object(duplicate.get("plan")));
        plans.set(1, copy(plans.getFirst()));
        rehash(duplicate);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(duplicate)).isInstanceOf(IllegalStateException.class);

        Map<String, Object> brokenHash = copy(snapshot().stored());
        children(object(brokenHash.get("plan"))).getFirst().put("planSha256", "0".repeat(64));
        rehash(brokenHash);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(brokenHash)).isInstanceOf(IllegalStateException.class);

        Map<String, Object> unauthorized = copy(snapshot().stored());
        children(object(unauthorized.get("plan"))).set(0, copy(registry().freezePlan("long_serial.rewrite_chapter_selection", false).stored()));
        rehash(unauthorized);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(unauthorized)).isInstanceOf(IllegalStateException.class);
    }

    @ParameterizedTest
    @ValueSource(strings = {"operationCatalogVersion", "executionManifestFingerprint"})
    void 子计划即使自洽也不能换Catalog或Manifest(String key) {
        Map<String, Object> stored = copy(snapshot().stored());
        Map<String, Object> child = children(object(stored.get("plan"))).getFirst();
        object(child.get("plan")).put(key, "executionManifestFingerprint".equals(key) ? "0".repeat(64) : "其他版本");
        rehash(child);
        rehash(stored);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(stored)).isInstanceOf(IllegalStateException.class);
    }

    @ParameterizedTest
    @ValueSource(ints = {-1, 0, 1, 3, 100})
    void 澄清上限是固定二次不能重写(int value) {
        Map<String, Object> stored = copy(snapshot().stored());
        object(stored.get("plan")).put("maxClarifications", value);
        rehash(stored);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(stored)).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 非整数澄清和擅自追加总预算均拒绝() {
        Map<String, Object> decimal = copy(snapshot().stored());
        object(decimal.get("plan")).put("maxClarifications", 2.0);
        rehash(decimal);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(decimal)).isInstanceOf(IllegalStateException.class);

        Map<String, Object> changed = copy(snapshot().stored());
        Map<String, Object> budget = object(object(changed.get("plan")).get("runBudget"));
        budget.put("maxCostMicros", ((Number) budget.get("maxCostMicros")).longValue() + 1);
        rehash(changed);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(changed)).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 子计划加解析预算超过既有Run硬上限时拒绝() {
        Map<String, Object> stored = copy(snapshot().stored());
        Map<String, Object> child = children(object(stored.get("plan"))).getFirst();
        object(object(child.get("plan")).get("runBudget")).put("maxModelCalls", 64);
        rehash(child);
        rehash(stored);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(stored)).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 解析器不能被换成生成器或扩充预算() {
        Map<String, Object> changedPurpose = copy(snapshot().stored());
        object(object(changedPurpose.get("plan")).get("resolver")).put("purpose", "generation");
        rehash(changedPurpose);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(changedPurpose)).isInstanceOf(IllegalStateException.class);
        Map<String, Object> changedBudget = copy(snapshot().stored());
        object(object(object(object(changedBudget.get("plan")).get("resolver")).get("stepBudget")).get("budget"))
                .put("maxInputTokens", 8001);
        rehash(changedBudget);
        assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(changedBudget)).isInstanceOf(IllegalStateException.class);
    }

    @ParameterizedTest
    @ValueSource(strings = {"modelProfile", "promptProfile", "outputSchema", "stepBudget"})
    void 解析器全部版本固定为一且改名升级也不能绕过(String component) {
        for (boolean changeName : List.of(false, true)) {
            Map<String, Object> stored = copy(snapshot().stored());
            Map<String, Object> resolver = object(object(stored.get("plan")).get("resolver"));
            Map<String, Object> reference = "promptProfile".equals(component)
                    ? object(object(resolver.get("modelProfile")).get("promptProfile"))
                    : object(resolver.get(component));
            reference.put("version", 2);
            if (changeName) {
                String nameKey = List.of("modelProfile", "stepBudget").contains(component) ? "profile" : "name";
                reference.put(nameKey, ((String) reference.get(nameKey)).replace(".v1", ".v2"));
            }
            rehash(stored);
            assertThatThrownBy(() -> IntentExecutionPlanSnapshot.fromStored(stored))
                    .isInstanceOf(IllegalStateException.class);
        }
    }

    @Test
    void 解析器复用现有部署授权且测试Fake不获生产授权() {
        IntentExecutionPlanSnapshot plan = snapshot();
        WorkflowResolvedModel fake = resolvedModel(
                "fake", "fake", "transport.fake.v1", "endpoint.local-fake.v1",
                "responses_json_schema_v1", "capability.fake.structured-output.v1", true);
        fake.requireAuthorizedBy(plan.resolver().modelProfile().toDomain());
        assertThat(registry().requireAuthorizedDeployment(fake).billable()).isFalse();

        ExecutionRegistry production = ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.PRODUCTION);
        assertThatThrownBy(() -> production.requireAuthorizedDeployment(fake)).isInstanceOf(IllegalStateException.class);
        WorkflowResolvedModel official = resolvedModel(
                "openai_compatible", "deepseek-v4-flash", "transport.deepseek-v4.v1", "endpoint.deepseek-official.v1",
                "chat_json_output_v1", "capability.deepseek-v4.chat-json.v1", false);
        official.requireAuthorizedBy(plan.resolver().modelProfile().toDomain());
        assertThat(production.requireAuthorizedDeployment(official).billable()).isTrue();
        WorkflowResolvedModel custom = resolvedModel(
                "openai_compatible", "deepseek-v4-flash", "transport.deepseek-v4.v1", "endpoint.deepseek-custom.v1",
                "chat_json_output_v1", "capability.deepseek-v4.chat-json.v1", false);
        assertThatThrownBy(() -> production.requireAuthorizedDeployment(custom)).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 旧计划拒绝新信封且自然Run身份不能假装已选业务() {
        IntentExecutionPlanSnapshot snapshot = snapshot();
        assertThatThrownBy(() -> ExecutionPlanSnapshot.fromStored(snapshot.stored())).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> snapshot.requireInitialIdentity("long_serial", "write_chapter", snapshot.operationCatalogVersion()))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> snapshot.requireInitialIdentity("short_medium", null, snapshot.operationCatalogVersion()))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> snapshot.requireInitialIdentity("long_serial", null, "不同版本"))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 快照深层不可变且不受来源Map修改影响() {
        Map<String, Object> source = copy(snapshot().stored());
        IntentExecutionPlanSnapshot restored = IntentExecutionPlanSnapshot.fromStored(source);
        String hash = restored.sha256();
        object(source.get("plan")).put("maxClarifications", 100);
        assertThat(restored.sha256()).isEqualTo(hash);
        assertThat(restored.maxClarifications()).isEqualTo(2);
        assertThatThrownBy(() -> object(restored.stored().get("plan")).put("maxClarifications", 100))
                .isInstanceOf(UnsupportedOperationException.class);
        assertThatThrownBy(() -> restored.operationPlans().clear()).isInstanceOf(UnsupportedOperationException.class);
    }

    private static ExecutionRegistry registry() {
        return ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);
    }

    private static IntentExecutionPlanSnapshot snapshot() {
        return IntentExecutionPlanSnapshot.freeze(registry(), OPERATIONS);
    }

    private static WorkflowResolvedModel resolvedModel(
            String provider, String model, String transport, String endpoint,
            String outputRoute, String capability, boolean supportsIdempotency) {
        String deploymentProfile = "deployment.system.intent_resolver.v1";
        return new WorkflowResolvedModel(
                deploymentProfile,
                WorkflowResolvedModel.fingerprint(deploymentProfile, provider, model, transport, endpoint,
                        outputRoute, capability, "disabled", supportsIdempotency),
                provider, model, transport, endpoint, outputRoute, capability, "disabled", supportsIdempotency);
    }

    private Map<String, Object> copy(Map<String, Object> value) {
        return json.readValue(json.writeValueAsString(value), new TypeReference<>() {});
    }

    private static void rehash(Map<String, Object> stored) {
        stored.put("planSha256", ExecutionCanonicalJson.sha256(object(stored.get("plan"))));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        return (Map<String, Object>) value;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> children(Map<String, Object> plan) {
        return (List<Map<String, Object>>) plan.get("operationPlans");
    }
}
