package cn.inkforge.core.workflows.catalog;

import cn.inkforge.core.workflows.domain.WorkflowModelProfile;
import cn.inkforge.core.workflows.domain.WorkflowStepBudget;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Run 创建时冻结的语言中立执行计划。
 *
 * <p>该快照只保存版本化逻辑引用、Schema、预算和确定性策略，不保存 Prompt 正文、作品正文、端点或凭据。
 * 在途 Run 的派发、终报、Reviewer 和返修只能读取本快照；当前 Registry 只负责创建新快照和 provider 前的
 * 部署授权。
 */
public final class ExecutionPlanSnapshot {

    public static final String PLAN_VERSION = "1";
    private static final Set<String> ROOT_KEYS =
            Set.of("planVersion", "hashAlgorithm", "planSha256", "plan");
    private static final Set<String> PLAN_KEYS = Set.of(
            "operationCatalogVersion",
            "executionManifestFingerprint",
            "operation",
            "generator",
            "reviewers",
            "systemSteps",
            "reviewPolicy",
            "runBudget");

    private final String operationCatalogVersion;
    private final String executionManifestFingerprint;
    private final Operation operation;
    private final Step generator;
    private final List<Step> reviewers;
    private final List<Step> systemSteps;
    private final ReviewPolicy reviewPolicy;
    private final ExecutionRegistry.RunBudget runBudget;
    private final Map<String, Object> plan;
    private final String sha256;
    private final Map<String, Object> stored;

    private ExecutionPlanSnapshot(
            String operationCatalogVersion,
            String executionManifestFingerprint,
            Operation operation,
            Step generator,
            List<Step> reviewers,
            List<Step> systemSteps,
            ReviewPolicy reviewPolicy,
            ExecutionRegistry.RunBudget runBudget,
            String expectedSha256) {
        this.operationCatalogVersion = nonBlank(
                operationCatalogVersion, "Operation Catalog 版本");
        if (executionManifestFingerprint == null
                || !executionManifestFingerprint.matches("^[0-9a-f]{64}$")) {
            throw invalid("execution manifest fingerprint 必须是小写 SHA-256");
        }
        this.executionManifestFingerprint = executionManifestFingerprint;
        this.operation = Objects.requireNonNull(operation);
        this.generator = Objects.requireNonNull(generator);
        this.reviewers = List.copyOf(reviewers);
        this.systemSteps = List.copyOf(systemSteps);
        this.reviewPolicy = Objects.requireNonNull(reviewPolicy);
        this.runBudget = Objects.requireNonNull(runBudget);
        validateCrossReferences();
        this.plan = planMap();
        this.sha256 = ExecutionCanonicalJson.sha256(plan);
        if (expectedSha256 != null && !sha256.equals(expectedSha256)) {
            throw invalid("执行计划 canonical SHA-256 不一致");
        }
        Map<String, Object> wrapper = new LinkedHashMap<>();
        wrapper.put("planVersion", PLAN_VERSION);
        wrapper.put("hashAlgorithm", ExecutionCanonicalJson.ALGORITHM);
        wrapper.put("planSha256", sha256);
        wrapper.put("plan", plan);
        this.stored = immutableMap(wrapper);
    }

    public static ExecutionPlanSnapshot freeze(
            String operationCatalogVersion,
            String executionManifestFingerprint,
            ExecutionRegistry.ResolvedOperation resolved) {
        Objects.requireNonNull(resolved, "解析 Operation 不能为空");
        ExecutionRegistry.Operation source = resolved.operation();
        Operation operation = new Operation(
                source.key(),
                source.workflow(),
                source.operation(),
                source.targetKinds(),
                source.scopeKinds(),
                source.mutating(),
                source.deterministicValidators(),
                source.applyHandler());
        Step generator = step(
                "generation",
                source.lane(),
                source.evidencePolicy(),
                resolved.generatorProfile(),
                resolved.outputSchema(),
                resolved.generatorStepBudget());
        List<Step> reviewers = new ArrayList<>();
        for (ExecutionRegistry.ResolvedReviewer reviewer : resolved.reviewers()) {
            reviewers.add(step(
                    "review",
                    source.reviewPolicy().lane(),
                    source.reviewPolicy().evidencePolicy(),
                    reviewer.profile(),
                    resolved.reviewerOutputSchema(),
                    reviewer.stepBudget()));
        }
        ExecutionRegistry.ReviewPolicy review = source.reviewPolicy();
        return new ExecutionPlanSnapshot(
                operationCatalogVersion,
                executionManifestFingerprint,
                operation,
                generator,
                reviewers,
                List.of(),
                new ReviewPolicy(
                        review.profile(),
                        review.mode(),
                        review.rubricVersion(),
                        review.mergePolicy(),
                        review.onUnavailable(),
                        review.maxAutomaticRevisions()),
                source.runBudget(),
                null);
    }

    public static ExecutionPlanSnapshot fromStored(Map<String, Object> value) {
        Map<String, Object> root = exactObject(value, "执行计划快照", ROOT_KEYS);
        if (!PLAN_VERSION.equals(string(root, "planVersion"))) {
            throw invalid("不支持的执行计划快照版本");
        }
        if (!ExecutionCanonicalJson.ALGORITHM.equals(string(root, "hashAlgorithm"))) {
            throw invalid("执行计划快照哈希算法不受支持");
        }
        String expectedSha256 = sha256(root, "planSha256");
        Map<String, Object> plan = exactObject(root.get("plan"), "执行计划", PLAN_KEYS);
        Operation operation = parseOperation(plan.get("operation"));
        Step generator = parseStep(plan.get("generator"), "生成 Step");
        List<Step> reviewers = parseSteps(plan.get("reviewers"), "Reviewer Steps");
        List<Step> systemSteps = parseSteps(plan.get("systemSteps"), "System Steps");
        ReviewPolicy reviewPolicy = parseReviewPolicy(plan.get("reviewPolicy"));
        ExecutionRegistry.RunBudget runBudget = parseRunBudget(plan.get("runBudget"));
        return new ExecutionPlanSnapshot(
                string(plan, "operationCatalogVersion"),
                sha256(plan, "executionManifestFingerprint"),
                operation,
                generator,
                reviewers,
                systemSteps,
                reviewPolicy,
                runBudget,
                expectedSha256);
    }

    public String operationCatalogVersion() {
        return operationCatalogVersion;
    }

    public Operation operation() {
        return operation;
    }

    public String executionManifestFingerprint() {
        return executionManifestFingerprint;
    }

    public Step generator() {
        return generator;
    }

    public List<Step> reviewers() {
        return reviewers;
    }

    public List<Step> systemSteps() {
        return systemSteps;
    }

    public ReviewPolicy reviewPolicy() {
        return reviewPolicy;
    }

    public ExecutionRegistry.RunBudget runBudget() {
        return runBudget;
    }

    public String sha256() {
        return sha256;
    }

    public Map<String, Object> stored() {
        return stored;
    }

    public Step requireStep(
            String purpose,
            String lane,
            String profile,
            int profileVersion,
            String outputSchema,
            int outputSchemaVersion,
            Map<String, Object> storedBudget) {
        StepBudgetProfile databaseBudget = parseStepBudget(storedBudget);
        List<Step> candidates = switch (purpose) {
            case "generation" -> List.of(generator);
            case "review" -> reviewers;
            default -> systemSteps.stream()
                    .filter(step -> step.purpose().equals(purpose))
                    .toList();
        };
        Step matched = null;
        for (Step candidate : candidates) {
            if (candidate.modelProfile().profile().equals(profile)) {
                if (matched != null) throw invalid("执行计划包含重复逻辑 Profile");
                matched = candidate;
            }
        }
        if (matched == null
                || !matched.lane().equals(lane)
                || matched.modelProfile().version() != profileVersion
                || !matched.outputSchema().name().equals(outputSchema)
                || matched.outputSchema().version() != outputSchemaVersion
                || !matched.stepBudget().equals(databaseBudget)) {
            throw invalid("Workflow Step 与冻结执行计划不一致");
        }
        return matched;
    }

    /** 公开状态只需要验证并投影 Step 的冻结逻辑模型身份。 */
    public ModelProfile requireStepProfile(
            String purpose, String lane, String profile, int profileVersion) {
        List<Step> candidates = switch (purpose) {
            case "generation" -> List.of(generator);
            case "review" -> reviewers;
            default -> systemSteps.stream()
                    .filter(step -> step.purpose().equals(purpose))
                    .toList();
        };
        Step matched = null;
        for (Step candidate : candidates) {
            if (candidate.modelProfile().profile().equals(profile)) {
                if (matched != null) throw invalid("执行计划包含重复逻辑 Profile");
                matched = candidate;
            }
        }
        if (matched == null
                || !matched.lane().equals(lane)
                || matched.modelProfile().version() != profileVersion) {
            throw invalid("Workflow Step 模型身份与冻结执行计划不一致");
        }
        return matched.modelProfile();
    }

    public void requireOperation(
            String workflow, String operationName, String catalogVersion) {
        if (!operation.workflow().equals(workflow)
                || !operation.operation().equals(operationName)
                || !operationCatalogVersion.equals(catalogVersion)) {
            throw invalid("Workflow Run 身份与冻结执行计划不一致");
        }
    }

    private void validateCrossReferences() {
        if (!operation.key().equals(operation.workflow() + "." + operation.operation())) {
            throw invalid("执行计划 Operation key 与 workflow/operation 不一致");
        }
        if (!"generation".equals(generator.purpose())) {
            throw invalid("执行计划 generator purpose 必须是 generation");
        }
        if (reviewers.stream().anyMatch(step -> !"review".equals(step.purpose()))) {
            throw invalid("执行计划 Reviewer purpose 必须是 review");
        }
        Set<String> profiles = new LinkedHashSet<>();
        profiles.add(generator.modelProfile().profile());
        for (Step reviewer : reviewers) {
            if (!profiles.add(reviewer.modelProfile().profile())) {
                throw invalid("执行计划逻辑 Profile 不能重复");
            }
        }
        int expectedReviewers = switch (reviewPolicy.mode()) {
            case "none" -> 0;
            case "single" -> 1;
            case "parallel" -> 2;
            default -> throw invalid("执行计划 Reviewer mode 不受支持");
        };
        if (reviewers.size() != expectedReviewers) {
            throw invalid("执行计划 Reviewer 数量与 mode 不一致");
        }
        if (reviewers.isEmpty()) {
            if (reviewPolicy.rubricVersion() != null
                    || reviewPolicy.maxAutomaticRevisions() != 0
                    || !"continue".equals(reviewPolicy.onUnavailable())) {
                throw invalid("无 Reviewer 的执行计划夹带了评审策略");
            }
        } else if (reviewPolicy.rubricVersion() == null
                || !"awaiting_user".equals(reviewPolicy.onUnavailable())) {
            throw invalid("Reviewer 执行计划缺少 rubric 或不可用策略");
        }
        runBudget.toDomain().requireStepFits(generator.stepBudget().budget());
        for (Step reviewer : reviewers) {
            runBudget.toDomain().requireStepFits(reviewer.stepBudget().budget());
        }
    }

    private Map<String, Object> planMap() {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("operationCatalogVersion", operationCatalogVersion);
        value.put("executionManifestFingerprint", executionManifestFingerprint);
        value.put("operation", operation.toMap());
        value.put("generator", generator.toMap());
        value.put("reviewers", reviewers.stream().map(Step::toMap).toList());
        value.put("systemSteps", systemSteps.stream().map(Step::toMap).toList());
        value.put("reviewPolicy", reviewPolicy.toMap());
        value.put("runBudget", runBudgetMap(runBudget));
        return immutableMap(value);
    }

    private static Step step(
            String purpose,
            String lane,
            String evidencePolicy,
            ExecutionRegistry.Profile profile,
            ExecutionRegistry.OutputSchema output,
            ExecutionRegistry.StepBudgetProfile budget) {
        return new Step(
                purpose,
                lane,
                evidencePolicy,
                new ModelProfile(
                        profile.key(),
                        profile.version(),
                        profile.reasoningMode(),
                        profile.deploymentProfileKey(),
                        new PromptProfile(
                                profile.promptProfile().key(),
                                profile.promptProfile().version(),
                                profile.promptProfile().sha256())),
                new OutputSchema(
                        output.key(),
                        output.version(),
                        output.sha256(),
                        output.jsonSchema()),
                new StepBudgetProfile(
                        budget.key(), budget.version(), budget.budget()));
    }

    private static Operation parseOperation(Object raw) {
        Map<String, Object> value = exactObject(
                raw,
                "执行计划 Operation",
                Set.of(
                        "key",
                        "workflow",
                        "operation",
                        "targetKinds",
                        "scopeKinds",
                        "mutating",
                        "deterministicValidators",
                        "applyHandler"));
        return new Operation(
                string(value, "key"),
                string(value, "workflow"),
                string(value, "operation"),
                strings(value, "targetKinds"),
                strings(value, "scopeKinds"),
                bool(value, "mutating"),
                strings(value, "deterministicValidators"),
                string(value, "applyHandler"));
    }

    private static List<Step> parseSteps(Object raw, String label) {
        if (!(raw instanceof List<?> values)) throw invalid(label + " 必须是数组");
        List<Step> result = new ArrayList<>();
        for (Object value : values) result.add(parseStep(value, label));
        return List.copyOf(result);
    }

    private static Step parseStep(Object raw, String label) {
        Map<String, Object> value = exactObject(
                raw,
                label,
                Set.of(
                        "purpose",
                        "lane",
                        "evidencePolicy",
                        "modelProfile",
                        "outputSchema",
                        "stepBudget"));
        return new Step(
                string(value, "purpose"),
                enumText(value, "lane", Set.of("interactive", "creative", "batch_media")),
                string(value, "evidencePolicy"),
                parseModelProfile(value.get("modelProfile")),
                parseOutputSchema(value.get("outputSchema")),
                parseStepBudget(value.get("stepBudget")));
    }

    private static ModelProfile parseModelProfile(Object raw) {
        Map<String, Object> value = exactObject(
                raw,
                "执行计划 Model Profile",
                Set.of(
                        "profile",
                        "version",
                        "reasoningMode",
                        "deploymentProfileKey",
                        "promptProfile"));
        return new ModelProfile(
                string(value, "profile"),
                positiveInt(value, "version"),
                enumText(value, "reasoningMode", Set.of("disabled", "bounded")),
                string(value, "deploymentProfileKey"),
                parsePrompt(value.get("promptProfile")));
    }

    private static PromptProfile parsePrompt(Object raw) {
        Map<String, Object> value = exactObject(
                raw,
                "执行计划 Prompt Profile",
                Set.of("name", "version", "sha256"));
        return new PromptProfile(
                string(value, "name"),
                positiveInt(value, "version"),
                sha256(value, "sha256"));
    }

    private static OutputSchema parseOutputSchema(Object raw) {
        Map<String, Object> value = exactObject(
                raw,
                "执行计划 Output Schema",
                Set.of("name", "version", "sha256", "jsonSchema"));
        Map<String, Object> schema = immutableMap(object(value.get("jsonSchema"), "jsonSchema"));
        String expected = sha256(value, "sha256");
        if (!ExecutionCanonicalJson.sha256(schema).equals(expected)) {
            throw invalid("执行计划 Output Schema canonical SHA-256 不一致");
        }
        return new OutputSchema(
                string(value, "name"), positiveInt(value, "version"), expected, schema);
    }

    private static StepBudgetProfile parseStepBudget(Object raw) {
        Map<String, Object> value = exactObject(
                raw,
                "执行计划 Step Budget",
                Set.of("profile", "version", "budget"));
        return new StepBudgetProfile(
                string(value, "profile"),
                positiveInt(value, "version"),
                workflowStepBudget(value.get("budget")));
    }

    private static ReviewPolicy parseReviewPolicy(Object raw) {
        Map<String, Object> value = exactObject(
                raw,
                "执行计划 Review Policy",
                Set.of(
                        "profile",
                        "mode",
                        "rubricVersion",
                        "mergePolicy",
                        "onUnavailable",
                        "maxAutomaticRevisions"));
        return new ReviewPolicy(
                string(value, "profile"),
                enumText(value, "mode", Set.of("none", "single", "parallel")),
                optionalString(value, "rubricVersion"),
                string(value, "mergePolicy"),
                enumText(value, "onUnavailable", Set.of("continue", "awaiting_user", "fail")),
                nonNegativeInt(value, "maxAutomaticRevisions"));
    }

    private static ExecutionRegistry.RunBudget parseRunBudget(Object raw) {
        Map<String, Object> value = exactObject(
                raw,
                "执行计划 Run Budget",
                Set.of(
                        "profile",
                        "maxModelCalls",
                        "maxInputTokens",
                        "maxPromptCacheMissTokens",
                        "maxCompletionTokens",
                        "maxReasoningTokens",
                        "maxVisibleOutputTokens",
                        "maxCostMicros",
                        "maxWallClockSeconds",
                        "maxProviderRetriesPerStep",
                        "maxProtocolCorrectionSteps"));
        return new ExecutionRegistry.RunBudget(
                string(value, "profile"),
                positiveInt(value, "maxModelCalls"),
                positiveLong(value, "maxInputTokens"),
                positiveLong(value, "maxPromptCacheMissTokens"),
                nonNegativeLong(value, "maxCompletionTokens"),
                nonNegativeLong(value, "maxReasoningTokens"),
                nonNegativeLong(value, "maxVisibleOutputTokens"),
                nonNegativeLong(value, "maxCostMicros"),
                positiveLong(value, "maxWallClockSeconds"),
                nonNegativeInt(value, "maxProviderRetriesPerStep"),
                nonNegativeInt(value, "maxProtocolCorrectionSteps"));
    }

    private static WorkflowStepBudget workflowStepBudget(Object raw) {
        Map<String, Object> value = exactObject(
                raw,
                "Step Budget",
                Set.of(
                        "maxModelCalls",
                        "maxInputTokens",
                        "maxPromptCacheMissTokens",
                        "maxCompletionTokens",
                        "maxReasoningTokens",
                        "maxVisibleOutputTokens",
                        "maxCostMicros",
                        "maxWallClockSeconds",
                        "maxProviderRetries",
                        "maxProtocolCorrections"));
        return new WorkflowStepBudget(
                positiveInt(value, "maxModelCalls"),
                positiveLong(value, "maxInputTokens"),
                positiveLong(value, "maxPromptCacheMissTokens"),
                nonNegativeLong(value, "maxCompletionTokens"),
                nonNegativeLong(value, "maxReasoningTokens"),
                nonNegativeLong(value, "maxVisibleOutputTokens"),
                nonNegativeLong(value, "maxCostMicros"),
                positiveLong(value, "maxWallClockSeconds"),
                nonNegativeInt(value, "maxProviderRetries"),
                nonNegativeInt(value, "maxProtocolCorrections"));
    }

    private static Map<String, Object> runBudgetMap(ExecutionRegistry.RunBudget budget) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("profile", budget.profile());
        value.put("maxModelCalls", budget.maxModelCalls());
        value.put("maxInputTokens", budget.maxInputTokens());
        value.put("maxPromptCacheMissTokens", budget.maxPromptCacheMissTokens());
        value.put("maxCompletionTokens", budget.maxCompletionTokens());
        value.put("maxReasoningTokens", budget.maxReasoningTokens());
        value.put("maxVisibleOutputTokens", budget.maxVisibleOutputTokens());
        value.put("maxCostMicros", budget.maxCostMicros());
        value.put("maxWallClockSeconds", budget.maxWallClockSeconds());
        value.put("maxProviderRetriesPerStep", budget.maxProviderRetriesPerStep());
        value.put("maxProtocolCorrectionSteps", budget.maxProtocolCorrectionSteps());
        return immutableMap(value);
    }

    private static Map<String, Object> budgetMap(WorkflowStepBudget budget) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("maxModelCalls", budget.maxModelCalls());
        value.put("maxInputTokens", budget.maxInputTokens());
        value.put("maxPromptCacheMissTokens", budget.maxPromptCacheMissTokens());
        value.put("maxCompletionTokens", budget.maxCompletionTokens());
        value.put("maxReasoningTokens", budget.maxReasoningTokens());
        value.put("maxVisibleOutputTokens", budget.maxVisibleOutputTokens());
        value.put("maxCostMicros", budget.maxCostMicros());
        value.put("maxWallClockSeconds", budget.maxWallClockSeconds());
        value.put("maxProviderRetries", budget.maxProviderRetries());
        value.put("maxProtocolCorrections", budget.maxProtocolCorrections());
        return immutableMap(value);
    }

    private static void requireVersioned(String value, int version, String label) {
        if (!value.endsWith(".v" + version)) {
            throw invalid(label + " 与 version 不一致");
        }
    }

    private static Map<String, Object> exactObject(
            Object value, String label, Set<String> keys) {
        Map<String, Object> result = object(value, label);
        if (!result.keySet().equals(keys)) throw invalid(label + " 字段集合无效");
        return result;
    }

    private static Map<String, Object> object(Object value, String label) {
        if (!(value instanceof Map<?, ?> raw)) throw invalid(label + " 必须是 JSON 对象");
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw invalid(label + " key 必须是字符串");
            }
            result.put(key, freeze(entry.getValue()));
        }
        return Collections.unmodifiableMap(result);
    }

    private static Object freeze(Object value) {
        if (value instanceof Map<?, ?> raw) return object(raw, "JSON 对象");
        if (value instanceof List<?> raw) {
            List<Object> result = new ArrayList<>(raw.size());
            for (Object item : raw) result.add(freeze(item));
            return Collections.unmodifiableList(result);
        }
        return value;
    }

    private static Map<String, Object> immutableMap(Map<String, Object> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : value.entrySet()) {
            result.put(entry.getKey(), freeze(entry.getValue()));
        }
        return Collections.unmodifiableMap(result);
    }

    private static List<String> strings(Map<String, Object> value, String key) {
        Object raw = value.get(key);
        if (!(raw instanceof List<?> list)) throw invalid(key + " 必须是数组");
        List<String> result = new ArrayList<>();
        for (Object item : list) {
            if (!(item instanceof String text) || text.isBlank()) {
                throw invalid(key + " 必须只包含非空字符串");
            }
            result.add(text);
        }
        if (new LinkedHashSet<>(result).size() != result.size()) {
            throw invalid(key + " 不能包含重复值");
        }
        return List.copyOf(result);
    }

    private static String string(Map<String, Object> value, String key) {
        return nonBlank(value.get(key) instanceof String text ? text : null, key);
    }

    private static String optionalString(Map<String, Object> value, String key) {
        Object raw = value.get(key);
        if (raw == null) return null;
        if (!(raw instanceof String text)) throw invalid(key + " 必须是字符串或 null");
        return nonBlank(text, key);
    }

    private static String enumText(
            Map<String, Object> value, String key, Set<String> allowed) {
        String result = string(value, key);
        if (!allowed.contains(result)) throw invalid(key + " 值不受支持");
        return result;
    }

    private static String sha256(Map<String, Object> value, String key) {
        String result = string(value, key);
        if (!result.matches("^[0-9a-f]{64}$")) throw invalid(key + " 必须是小写 SHA-256");
        return result;
    }

    private static boolean bool(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof Boolean result)) throw invalid(key + " 必须是布尔值");
        return result;
    }

    private static int positiveInt(Map<String, Object> value, String key) {
        int result = exactInt(value, key);
        if (result < 1) throw invalid(key + " 必须为正整数");
        return result;
    }

    private static int nonNegativeInt(Map<String, Object> value, String key) {
        int result = exactInt(value, key);
        if (result < 0) throw invalid(key + " 不能为负数");
        return result;
    }

    private static int exactInt(Map<String, Object> value, String key) {
        long result = exactLong(value, key);
        return Math.toIntExact(result);
    }

    private static long positiveLong(Map<String, Object> value, String key) {
        long result = exactLong(value, key);
        if (result < 1) throw invalid(key + " 必须为正整数");
        return result;
    }

    private static long nonNegativeLong(Map<String, Object> value, String key) {
        long result = exactLong(value, key);
        if (result < 0) throw invalid(key + " 不能为负数");
        return result;
    }

    private static long exactLong(Map<String, Object> value, String key) {
        Object raw = value.get(key);
        if (!(raw instanceof Number number)
                || number.doubleValue() != number.longValue()) {
            throw invalid(key + " 必须是整数");
        }
        return number.longValue();
    }

    private static String nonBlank(String value, String label) {
        if (value == null || value.isBlank()) throw invalid(label + " 不能为空");
        return value;
    }

    private static IllegalStateException invalid(String message) {
        return new IllegalStateException(message);
    }

    public record Operation(
            String key,
            String workflow,
            String operation,
            List<String> targetKinds,
            List<String> scopeKinds,
            boolean mutating,
            List<String> deterministicValidators,
            String applyHandler) {
        public Operation {
            key = nonBlank(key, "Operation key");
            workflow = nonBlank(workflow, "workflow");
            operation = nonBlank(operation, "operation");
            targetKinds = List.copyOf(targetKinds);
            scopeKinds = List.copyOf(scopeKinds);
            deterministicValidators = List.copyOf(deterministicValidators);
            applyHandler = nonBlank(applyHandler, "applyHandler");
        }

        Map<String, Object> toMap() {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("key", key);
            value.put("workflow", workflow);
            value.put("operation", operation);
            value.put("targetKinds", targetKinds);
            value.put("scopeKinds", scopeKinds);
            value.put("mutating", mutating);
            value.put("deterministicValidators", deterministicValidators);
            value.put("applyHandler", applyHandler);
            return immutableMap(value);
        }
    }

    public record PromptProfile(String name, int version, String sha256) {
        public PromptProfile {
            name = nonBlank(name, "Prompt Profile name");
            if (version < 1) throw invalid("Prompt Profile version 必须为正整数");
            requireVersioned(name, version, "Prompt Profile name");
            if (sha256 == null || !sha256.matches("^[0-9a-f]{64}$")) {
                throw invalid("Prompt Profile sha256 无效");
            }
        }

        Map<String, Object> toMap() {
            return Map.of("name", name, "version", version, "sha256", sha256);
        }
    }

    public record ModelProfile(
            String profile,
            int version,
            String reasoningMode,
            String deploymentProfileKey,
            PromptProfile promptProfile) {
        public ModelProfile {
            profile = nonBlank(profile, "Model Profile");
            if (version < 1) throw invalid("Model Profile version 必须为正整数");
            requireVersioned(profile, version, "Model Profile");
            if (!Set.of("disabled", "bounded").contains(reasoningMode)) {
                throw invalid("Model Profile reasoningMode 无效");
            }
            deploymentProfileKey = nonBlank(
                    deploymentProfileKey, "Deployment Profile key");
            Objects.requireNonNull(promptProfile);
        }

        public WorkflowModelProfile toDomain() {
            return new WorkflowModelProfile(
                    profile, version, reasoningMode, deploymentProfileKey);
        }

        public Map<String, Object> toMap() {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("profile", profile);
            value.put("version", version);
            value.put("reasoningMode", reasoningMode);
            value.put("deploymentProfileKey", deploymentProfileKey);
            value.put("promptProfile", promptProfile.toMap());
            return immutableMap(value);
        }
    }

    public record OutputSchema(
            String name, int version, String sha256, Map<String, Object> jsonSchema) {
        public OutputSchema {
            name = nonBlank(name, "Output Schema name");
            if (version < 1) throw invalid("Output Schema version 必须为正整数");
            requireVersioned(name, version, "Output Schema name");
            if (sha256 == null || !sha256.matches("^[0-9a-f]{64}$")) {
                throw invalid("Output Schema sha256 无效");
            }
            jsonSchema = immutableMap(jsonSchema);
            if (!ExecutionCanonicalJson.sha256(jsonSchema).equals(sha256)) {
                throw invalid("Output Schema hash 与完整 JSON 不一致");
            }
        }

        public Map<String, Object> toMap() {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("name", name);
            value.put("version", version);
            value.put("sha256", sha256);
            value.put("jsonSchema", jsonSchema);
            return immutableMap(value);
        }
    }

    public record StepBudgetProfile(
            String profile, int version, WorkflowStepBudget budget) {
        public StepBudgetProfile {
            profile = nonBlank(profile, "Step Budget Profile");
            if (version < 1) throw invalid("Step Budget Profile version 必须为正整数");
            requireVersioned(profile, version, "Step Budget Profile");
            Objects.requireNonNull(budget);
        }

        public Map<String, Object> budgetMap() {
            return ExecutionPlanSnapshot.budgetMap(budget);
        }

        public Map<String, Object> stored() {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("profile", profile);
            value.put("version", version);
            value.put("budget", budgetMap());
            return immutableMap(value);
        }
    }

    public record Step(
            String purpose,
            String lane,
            String evidencePolicy,
            ModelProfile modelProfile,
            OutputSchema outputSchema,
            StepBudgetProfile stepBudget) {
        public Step {
            purpose = nonBlank(purpose, "Step purpose");
            if (!Set.of("interactive", "creative", "batch_media").contains(lane)) {
                throw invalid("Step lane 无效");
            }
            evidencePolicy = nonBlank(evidencePolicy, "Evidence policy");
            Objects.requireNonNull(modelProfile);
            Objects.requireNonNull(outputSchema);
            Objects.requireNonNull(stepBudget);
            if (("disabled".equals(modelProfile.reasoningMode())
                            && stepBudget.budget().maxReasoningTokens() != 0)
                    || ("bounded".equals(modelProfile.reasoningMode())
                            && stepBudget.budget().maxReasoningTokens() == 0)) {
                throw invalid("Model Profile reasoning 与 Step Budget 不一致");
            }
        }

        public Map<String, Object> toMap() {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("purpose", purpose);
            value.put("lane", lane);
            value.put("evidencePolicy", evidencePolicy);
            value.put("modelProfile", modelProfile.toMap());
            value.put("outputSchema", outputSchema.toMap());
            value.put("stepBudget", stepBudget.stored());
            return immutableMap(value);
        }
    }

    public record ReviewPolicy(
            String profile,
            String mode,
            String rubricVersion,
            String mergePolicy,
            String onUnavailable,
            int maxAutomaticRevisions) {
        public ReviewPolicy {
            profile = nonBlank(profile, "Review Policy profile");
            if (!Set.of("none", "single", "parallel").contains(mode)) {
                throw invalid("Review Policy mode 无效");
            }
            if (rubricVersion != null) rubricVersion = nonBlank(rubricVersion, "rubricVersion");
            mergePolicy = nonBlank(mergePolicy, "mergePolicy");
            if (!Set.of("continue", "awaiting_user", "fail").contains(onUnavailable)) {
                throw invalid("Review Policy onUnavailable 无效");
            }
            if (maxAutomaticRevisions < 0) {
                throw invalid("maxAutomaticRevisions 不能为负数");
            }
        }

        Map<String, Object> toMap() {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("profile", profile);
            value.put("mode", mode);
            value.put("rubricVersion", rubricVersion);
            value.put("mergePolicy", mergePolicy);
            value.put("onUnavailable", onUnavailable);
            value.put("maxAutomaticRevisions", maxAutomaticRevisions);
            return immutableMap(value);
        }
    }
}
