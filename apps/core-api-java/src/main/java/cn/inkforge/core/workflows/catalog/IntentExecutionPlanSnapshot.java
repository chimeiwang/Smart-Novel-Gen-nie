package cn.inkforge.core.workflows.catalog;

import cn.inkforge.core.workflows.domain.WorkflowStepBudget;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.ToLongFunction;

/**
 * 自然入口的不可变外层计划；解析前没有业务 Operation，解析后只选择已冻结的旧版子计划。
 *
 * <p>该类型不更新 Run、不调度 Step，也不读取当前 Registry 恢复在途事实。总预算始终包含最多三次
 * 意图解析；业务阶段还必须独立遵守所选子计划预算，不能把外层余额当作扩充业务额度。
 */
public final class IntentExecutionPlanSnapshot {

    public static final String PLAN_VERSION = "2";
    public static final String WORKFLOW = "long_serial";
    public static final String RUN_BUDGET_PROFILE = "budget.long_serial.natural.v1";
    public static final int MAX_CLARIFICATIONS = 2;
    public static final int MAX_RESOLVER_STEPS = MAX_CLARIFICATIONS + 1;
    private static final Set<String> CHAPTER_OPERATIONS = Set.of(
            "long_serial.answer_question", "long_serial.plan_chapter", "long_serial.review_chapter",
            "long_serial.rewrite_scene", "long_serial.write_chapter");
    private static final Map<String, String> STRUCTURED_TARGET_KINDS = Map.of(
            "long_serial.create_lore", "lore", "long_serial.revise_lore", "lore",
            "long_serial.create_outline", "outline", "long_serial.revise_outline", "outline",
            "long_serial.manage_foreshadowing", "foreshadowing");
    private static final Set<String> ROOT_KEYS = Set.of("planVersion", "hashAlgorithm", "planSha256", "plan");
    private static final Set<String> PLAN_KEYS = Set.of(
            "workflow", "operationCatalogVersion", "executionManifestFingerprint", "resolver",
            "operationPlans", "maxClarifications", "runBudget");
    private static final String RESOLVER_OUTPUT_SCHEMA_SHA256 =
            "d01c3444cfd4da13d9df6fe5dee58dfe5a75c413ad89ac28a766d18f6e8bde25";
    private static final WorkflowStepBudget RESOLVER_BUDGET = new WorkflowStepBudget(
            1, 8_000, 8_000, 1_000, 0, 1_000, 50_000, 30, 2, 0);
    private static final ResolverTuple RESOLVER_V1 = new ResolverTuple(
            1,
            "system.intent_resolver.v1",
            "deployment.system.intent_resolver.v1",
            "prompt.system.intent_resolver.v1",
            "4ebf30f06de85e21db42275f10e88a9ce309ee037dfebfd0fc921bfc77796f63");
    private static final ResolverTuple RESOLVER_V2 = new ResolverTuple(
            2,
            "system.intent_resolver.v2",
            "deployment.system.intent_resolver.v2",
            "prompt.system.intent_resolver.v2",
            "5f1b980a61c8c66f9e43b06824816cfbdff723eada0784b2e2f5d7c6796fb5bd");
    private static final ResolverTuple RESOLVER_V3 = new ResolverTuple(
            3,
            "system.intent_resolver.v3",
            "deployment.system.intent_resolver.v3",
            "prompt.system.intent_resolver.v3",
            "a0f495e7f011eb8f8f0741a3b4e643bfb4d821a7cf62f29e422ac038ff9217e4");

    private final String operationCatalogVersion;
    private final String executionManifestFingerprint;
    private final ExecutionPlanSnapshot.Step resolver;
    private final List<ExecutionPlanSnapshot> operationPlans;
    private final ExecutionRegistry.RunBudget runBudget;
    private final String sha256;
    private final Map<String, Object> stored;

    private IntentExecutionPlanSnapshot(
            String operationCatalogVersion,
            String executionManifestFingerprint,
            ExecutionPlanSnapshot.Step resolver,
            List<ExecutionPlanSnapshot> operationPlans,
            ExecutionRegistry.RunBudget expectedBudget,
            String expectedSha256) {
        this.operationCatalogVersion = nonBlank(operationCatalogVersion, "Operation Catalog 版本");
        this.executionManifestFingerprint = requireSha256(executionManifestFingerprint, "Manifest fingerprint");
        this.resolver = Objects.requireNonNull(resolver, "解析器 Step 不能为空");
        requireResolver(resolver);
        this.operationPlans = List.copyOf(operationPlans.stream()
                .sorted(Comparator.comparing(plan -> plan.operation().key())).toList());
        validateOperationPlans();
        this.runBudget = totalBudget(this.operationPlans, resolver.stepBudget().budget());
        if (expectedBudget != null && !runBudget.equals(expectedBudget)) {
            throw invalid("自然入口外层预算必须精确等于业务最大预算加三次解析预算");
        }
        Map<String, Object> plan = new LinkedHashMap<>();
        plan.put("workflow", WORKFLOW);
        plan.put("operationCatalogVersion", operationCatalogVersion);
        plan.put("executionManifestFingerprint", executionManifestFingerprint);
        plan.put("resolver", resolver.toMap());
        plan.put("operationPlans", this.operationPlans.stream().map(ExecutionPlanSnapshot::stored).toList());
        plan.put("maxClarifications", MAX_CLARIFICATIONS);
        plan.put("runBudget", runBudgetStored());
        Map<String, Object> frozenPlan = Collections.unmodifiableMap(plan);
        this.sha256 = ExecutionCanonicalJson.sha256(frozenPlan);
        if (expectedSha256 != null && !sha256.equals(expectedSha256)) {
            throw invalid("自然入口执行计划 canonical SHA-256 不一致");
        }
        this.stored = Map.of(
                "planVersion", PLAN_VERSION,
                "hashAlgorithm", ExecutionCanonicalJson.ALGORITHM,
                "planSha256", sha256,
                "plan", frozenPlan);
    }

    /** 授权列表由 Core 业务入口给出；不补齐、丢弃或猜测任何未授权操作。 */
    public static IntentExecutionPlanSnapshot freeze(
            ExecutionRegistry registry, List<String> authorizedOperationKeys) {
        Objects.requireNonNull(registry, "Registry 不能为空");
        requireOperationKeys(authorizedOperationKeys, true);
        ExecutionRegistry.ResolvedSystemPurpose resolved = registry.resolveSystemPurpose("resolve_intent");
        if (!resolved.purpose().workflows().contains(WORKFLOW)
                || !resolved.purpose().parentOperations().isEmpty()) {
            throw invalid("自然入口解析器未授权无父业务操作的 long_serial 用途");
        }
        List<ExecutionPlanSnapshot> plans = authorizedOperationKeys.stream()
                .map(key -> registry.freezePlan(key, false)).toList();
        ExecutionPlanSnapshot.Step resolver = ExecutionPlanSnapshot.freezeSystemPurpose(resolved);
        requireCurrentResolver(resolver);
        return new IntentExecutionPlanSnapshot(
                registry.catalogVersion(), registry.manifestFingerprint(),
                resolver, plans, null, null);
    }

    /** 只验证持久化的冻结事实，不要求当前部署仍保有同一份 Registry。 */
    public static IntentExecutionPlanSnapshot fromStored(Map<String, Object> value) {
        Map<String, Object> root = exactObject(value, ROOT_KEYS, "自然入口执行计划快照");
        if (!PLAN_VERSION.equals(root.get("planVersion"))
                || !ExecutionCanonicalJson.ALGORITHM.equals(root.get("hashAlgorithm"))) {
            throw invalid("自然入口执行计划版本或哈希算法不受支持");
        }
        Map<String, Object> plan = exactObject(root.get("plan"), PLAN_KEYS, "自然入口执行计划");
        if (!WORKFLOW.equals(plan.get("workflow"))) throw invalid("自然入口只允许 long_serial");
        if (integer(plan.get("maxClarifications"), "maxClarifications") != MAX_CLARIFICATIONS) {
            throw invalid("自然入口只允许最多两次澄清");
        }
        if (!(plan.get("operationPlans") instanceof List<?> children)) {
            throw invalid("自然入口子计划必须是数组");
        }
        List<ExecutionPlanSnapshot> plans = new ArrayList<>();
        for (Object child : children) plans.add(ExecutionPlanSnapshot.fromStored(object(child, "业务子计划")));
        Map<String, Object> resolver = object(plan.get("resolver"), "解析器 Step");
        requireResolverIntegers(resolver);
        Map<String, Object> budget = object(plan.get("runBudget"), "自然入口总预算");
        requireBudgetIntegers(budget, Set.of("profile"));
        return new IntentExecutionPlanSnapshot(
                text(plan.get("operationCatalogVersion"), "Operation Catalog 版本"),
                text(plan.get("executionManifestFingerprint"), "Manifest fingerprint"),
                ExecutionPlanSnapshot.parseStep(resolver, "解析器 Step"), plans,
                ExecutionPlanSnapshot.parseRunBudget(budget),
                requireSha256(text(root.get("planSha256"), "计划哈希"), "计划哈希"));
    }

    public String operationCatalogVersion() { return operationCatalogVersion; }
    public String executionManifestFingerprint() { return executionManifestFingerprint; }
    public ExecutionPlanSnapshot.Step resolver() { return resolver; }
    public List<ExecutionPlanSnapshot> operationPlans() { return operationPlans; }
    public int maxClarifications() { return MAX_CLARIFICATIONS; }
    public int maxResolverSteps() { return MAX_RESOLVER_STEPS; }
    public ExecutionRegistry.RunBudget runBudget() { return runBudget; }
    public Map<String, Object> runBudgetStored() { return ExecutionPlanSnapshot.runBudgetMap(runBudget); }
    public String sha256() { return sha256; }
    public Map<String, Object> stored() { return stored; }

    public boolean supportsNovelScopes() { return RESOLVER_V3.matches(resolver.modelProfile()); }

    /** 只能投影本次已冻结授权；历史解析器的范围绝不因当前目录扩展而变化。 */
    public String scopeKindForOperation(String operationKey) {
        requireOperationPlan(operationKey);
        return supportsNovelScopes() ? defaultScopeKind(operationKey) : "chapter";
    }

    /** 新自然入口的固定范围，不接收模型参数，也不查询当前 Registry。 */
    public static String defaultScopeKind(String operationKey) {
        if (operationKey == null) throw invalid("自然操作不能为空");
        if (CHAPTER_OPERATIONS.contains(operationKey) || "long_serial.manage_foreshadowing".equals(operationKey)) {
            return "chapter";
        }
        if (STRUCTURED_TARGET_KINDS.containsKey(operationKey)) return "novel";
        throw invalid("操作不在已接通的自然默认范围集合中");
    }

    public ExecutionPlanSnapshot requireOperationPlan(String operationKey) {
        return operationPlans.stream().filter(plan -> plan.operation().key().equals(operationKey))
                .findFirst().orElseThrow(() -> invalid("操作不在自然入口冻结的授权集合中"));
    }

    public ExecutionPlanSnapshot requireOperationPlan(String operationKey, String expectedPlanSha256) {
        ExecutionPlanSnapshot selected = requireOperationPlan(operationKey);
        if (!selected.sha256().equals(expectedPlanSha256)) throw invalid("所选业务子计划哈希不匹配");
        return selected;
    }

    public void requireInitialIdentity(String workflow, String operation, String catalogVersion) {
        if (!WORKFLOW.equals(workflow) || operation != null || !operationCatalogVersion.equals(catalogVersion)) {
            throw invalid("自然入口 Run 初始身份必须保留未决 operation 与冻结 Catalog 版本");
        }
    }

    private void validateOperationPlans() {
        requireOperationKeys(operationPlans.stream().map(plan -> plan.operation().key()).toList(), supportsNovelScopes());
        for (ExecutionPlanSnapshot plan : operationPlans) {
            if (!operationCatalogVersion.equals(plan.operationCatalogVersion())
                    || !executionManifestFingerprint.equals(plan.executionManifestFingerprint())) {
                throw invalid("自然入口和业务子计划必须绑定同一 Catalog 与 Manifest");
            }
            String key = plan.operation().key();
            List<String> scopes = switch (key) {
                case "long_serial.revise_outline" -> List.of("novel", "outline_node");
                case "long_serial.manage_foreshadowing" -> List.of("novel", "chapter");
                default -> List.of(CHAPTER_OPERATIONS.contains(key) ? "chapter" : "novel");
            };
            String target = STRUCTURED_TARGET_KINDS.getOrDefault(key, "chapter");
            if (!WORKFLOW.equals(plan.operation().workflow())
                    || !List.of(target).equals(plan.operation().targetKinds())
                    || !scopes.equals(plan.operation().scopeKinds()) || !plan.systemSteps().isEmpty()) {
                throw invalid("自然入口子计划的业务目标或范围不匹配已接通语义");
            }
            try {
                plan.runBudget().toDomain();
            } catch (IllegalArgumentException exception) {
                throw new IllegalStateException("业务子计划预算超出既有硬上限", exception);
            }
        }
    }

    private static void requireOperationKeys(List<String> keys, boolean structured) {
        int maximum = CHAPTER_OPERATIONS.size() + (structured ? STRUCTURED_TARGET_KINDS.size() : 0);
        if (keys == null || keys.isEmpty() || keys.size() > maximum
                || new LinkedHashSet<>(keys).size() != keys.size()
                || keys.stream().anyMatch(key -> key == null || !(CHAPTER_OPERATIONS.contains(key)
                        || structured && STRUCTURED_TARGET_KINDS.containsKey(key)))) {
            throw invalid("自然入口授权操作必须非空、无重复且匹配冻结解析器支持的集合");
        }
    }

    private static void requireResolver(ExecutionPlanSnapshot.Step step) {
        if (!"resolve_intent".equals(step.purpose()) || !"interactive".equals(step.lane())
                || !"evidence.system.intent.v1".equals(step.evidencePolicy())
                || !"disabled".equals(step.modelProfile().reasoningMode())
                || !"output.proposed_command.v1".equals(step.outputSchema().name())
                || step.outputSchema().version() != 1
                || !RESOLVER_OUTPUT_SCHEMA_SHA256.equals(step.outputSchema().sha256())
                || !"step_budget.system.resolve_intent.v1".equals(step.stepBudget().profile())
                || step.stepBudget().version() != 1
                || !RESOLVER_BUDGET.equals(step.stepBudget().budget())) {
            throw invalid("自然入口解析器的用途、Profile、Schema、Evidence 或预算不受支持");
        }
        if (!RESOLVER_V1.matches(step.modelProfile())
                && !RESOLVER_V2.matches(step.modelProfile())
                && !RESOLVER_V3.matches(step.modelProfile())) {
            throw invalid("自然入口解析器的 Profile、Prompt 与 Deployment 版本组合不受支持");
        }
    }

    private static void requireCurrentResolver(ExecutionPlanSnapshot.Step step) {
        requireResolver(step);
        if (!RESOLVER_V3.matches(step.modelProfile())) {
            throw invalid("新自然入口必须冻结当前 v3 意图解析器依赖");
        }
    }

    private static ExecutionRegistry.RunBudget totalBudget(
            List<ExecutionPlanSnapshot> plans, WorkflowStepBudget resolver) {
        try {
            ExecutionRegistry.RunBudget result = new ExecutionRegistry.RunBudget(
                    RUN_BUDGET_PROFILE,
                    Math.toIntExact(total(plans, ExecutionRegistry.RunBudget::maxModelCalls, resolver.maxModelCalls())),
                    total(plans, ExecutionRegistry.RunBudget::maxInputTokens, resolver.maxInputTokens()),
                    total(plans, ExecutionRegistry.RunBudget::maxPromptCacheMissTokens, resolver.maxPromptCacheMissTokens()),
                    total(plans, ExecutionRegistry.RunBudget::maxCompletionTokens, resolver.maxCompletionTokens()),
                    total(plans, ExecutionRegistry.RunBudget::maxReasoningTokens, resolver.maxReasoningTokens()),
                    total(plans, ExecutionRegistry.RunBudget::maxVisibleOutputTokens, resolver.maxVisibleOutputTokens()),
                    total(plans, ExecutionRegistry.RunBudget::maxCostMicros, resolver.maxCostMicros()),
                    total(plans, ExecutionRegistry.RunBudget::maxWallClockSeconds, resolver.maxWallClockSeconds()),
                    Math.toIntExact(Math.max(maximum(plans, ExecutionRegistry.RunBudget::maxProviderRetriesPerStep), resolver.maxProviderRetries())),
                    Math.toIntExact(total(plans, ExecutionRegistry.RunBudget::maxProtocolCorrectionSteps, resolver.maxProtocolCorrections())));
            result.toDomain().requireStepFits(resolver);
            return result;
        } catch (ArithmeticException | IllegalArgumentException exception) {
            throw new IllegalStateException("自然入口累计预算超出既有 Run 硬上限", exception);
        }
    }

    private static long total(List<ExecutionPlanSnapshot> plans, ToLongFunction<ExecutionRegistry.RunBudget> field, long resolver) {
        return Math.addExact(maximum(plans, field), Math.multiplyExact(MAX_RESOLVER_STEPS, resolver));
    }

    private static long maximum(List<ExecutionPlanSnapshot> plans, ToLongFunction<ExecutionRegistry.RunBudget> field) {
        return plans.stream().map(ExecutionPlanSnapshot::runBudget).mapToLong(field).max().orElseThrow();
    }

    private static void requireResolverIntegers(Map<String, Object> resolver) {
        Map<String, Object> profile = object(resolver.get("modelProfile"), "解析器 Profile");
        integer(profile.get("version"), "Profile version");
        integer(object(profile.get("promptProfile"), "解析器 Prompt").get("version"), "Prompt version");
        integer(object(resolver.get("outputSchema"), "解析器 Schema").get("version"), "Schema version");
        Map<String, Object> stepBudget = object(resolver.get("stepBudget"), "解析器预算");
        integer(stepBudget.get("version"), "Step Budget version");
        requireBudgetIntegers(object(stepBudget.get("budget"), "解析器预算值"), Set.of());
    }

    private static void requireBudgetIntegers(Map<String, Object> budget, Set<String> excluded) {
        budget.forEach((key, value) -> {
            if (!excluded.contains(key)) integer(value, key);
        });
    }

    private static long integer(Object value, String label) {
        if (value instanceof Byte || value instanceof Short || value instanceof Integer || value instanceof Long) {
            return ((Number) value).longValue();
        }
        if (value instanceof BigInteger number) {
            try {
                return number.longValueExact();
            } catch (ArithmeticException exception) {
                throw new IllegalStateException(label + " 超出整数范围", exception);
            }
        }
        throw invalid(label + " 必须是整数");
    }

    private static Map<String, Object> exactObject(Object raw, Set<String> fields, String label) {
        Map<String, Object> value = object(raw, label);
        if (!value.keySet().equals(fields)) throw invalid(label + " 字段集合无效");
        return value;
    }

    private static Map<String, Object> object(Object raw, String label) {
        if (!(raw instanceof Map<?, ?> map)) throw invalid(label + " 必须是对象");
        Map<String, Object> value = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            if (!(entry.getKey() instanceof String key)) throw invalid(label + " key 必须是字符串");
            value.put(key, entry.getValue());
        }
        return value;
    }

    private static String text(Object raw, String label) {
        return nonBlank(raw instanceof String value ? value : null, label);
    }

    private static String nonBlank(String value, String label) {
        if (value == null || value.isBlank()) throw invalid(label + " 不能为空");
        return value;
    }

    private static String requireSha256(String value, String label) {
        if (value == null || !value.matches("^[0-9a-f]{64}$")) throw invalid(label + " 必须为小写 SHA-256");
        return value;
    }

    private record ResolverTuple(
            int version,
            String profile,
            String deploymentProfile,
            String promptProfile,
            String promptSha256) {

        private boolean matches(ExecutionPlanSnapshot.ModelProfile value) {
            return version == value.version()
                    && profile.equals(value.profile())
                    && deploymentProfile.equals(value.deploymentProfileKey())
                    && version == value.promptProfile().version()
                    && promptProfile.equals(value.promptProfile().name())
                    && promptSha256.equals(value.promptProfile().sha256());
        }
    }

    private static IllegalStateException invalid(String message) { return new IllegalStateException(message); }
}
