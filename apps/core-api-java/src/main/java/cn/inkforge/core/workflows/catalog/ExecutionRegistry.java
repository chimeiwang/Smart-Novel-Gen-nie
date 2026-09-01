package cn.inkforge.core.workflows.catalog;

import cn.inkforge.core.workflows.domain.WorkflowRunBudget;
import cn.inkforge.core.workflows.domain.WorkflowRunBudgetCharge;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.domain.WorkflowStepBudget;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import java.util.regex.Pattern;
import tools.jackson.core.StreamReadFeature;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/** 经 manifest 哈希约束的 Operation、Profile、预算、输出和系统用途单一注册表。 */
public final class ExecutionRegistry {

    private static final ObjectMapper JSON = JsonMapper.builder()
            .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
            .build();
    private static final Pattern DOCUMENT_PATH =
            Pattern.compile("^[a-z0-9][a-z0-9.-]*\\.json$");
    private static final Set<String> DOCUMENT_ENTRIES = Set.of(
            "catalog",
            "schema",
            "profileRegistry",
            "profileRegistrySchema",
            "deploymentProfileRegistry",
            "deploymentProfileRegistrySchema",
            "promptProfileRegistry",
            "promptProfileRegistrySchema",
            "outputSchemaRegistry",
            "outputSchemaRegistrySchema",
            "systemPurposeRegistry",
            "systemPurposeRegistrySchema",
            "stepBudgetRegistry",
            "stepBudgetRegistrySchema",
            "hashVectors");
    private static final Set<String> MANIFEST_ENTRIES;

    static {
        Set<String> entries = new LinkedHashSet<>(DOCUMENT_ENTRIES);
        entries.add("manifestVersion");
        entries.add("catalogVersion");
        MANIFEST_ENTRIES = Set.copyOf(entries);
    }

    private final Map<String, Operation> operations;
    private final Map<String, Profile> profiles;
    private final Map<String, DeploymentProfile> deploymentProfiles;
    private final Map<String, PromptProfile> promptProfiles;
    private final Map<String, OutputSchema> outputSchemas;
    private final Map<String, StepBudgetProfile> stepBudgets;
    private final Map<String, SystemPurpose> systemPurposes;
    private final Environment environment;
    private final String catalogVersion;
    private final String manifestFingerprint;

    private ExecutionRegistry(
            Map<String, Operation> operations,
            Map<String, Profile> profiles,
            Map<String, DeploymentProfile> deploymentProfiles,
            Map<String, PromptProfile> promptProfiles,
            Map<String, OutputSchema> outputSchemas,
            Map<String, StepBudgetProfile> stepBudgets,
            Map<String, SystemPurpose> systemPurposes,
            Environment environment,
            String catalogVersion,
            String manifestFingerprint) {
        this.operations = Map.copyOf(operations);
        this.profiles = Map.copyOf(profiles);
        this.deploymentProfiles = Map.copyOf(deploymentProfiles);
        this.promptProfiles = Map.copyOf(promptProfiles);
        this.outputSchemas = Map.copyOf(outputSchemas);
        this.stepBudgets = Map.copyOf(stepBudgets);
        this.systemPurposes = Map.copyOf(systemPurposes);
        this.environment = Objects.requireNonNull(environment);
        this.catalogVersion = Objects.requireNonNull(catalogVersion);
        this.manifestFingerprint = Objects.requireNonNull(manifestFingerprint);
    }

    public static ExecutionRegistry loadClasspath(Environment environment) {
        return load(ExecutionRegistry::readClasspathDocument, environment);
    }

    static ExecutionRegistry load(Function<String, byte[]> documents) {
        return load(documents, Environment.TEST);
    }

    static ExecutionRegistry load(
            Function<String, byte[]> documents, Environment environment) {
        Objects.requireNonNull(documents, "执行契约文档源不能为空");
        Objects.requireNonNull(environment, "执行环境不能为空");
        Map<String, Object> manifest = object(parse(documents.apply("manifest.json")), "manifest");
        if (!manifest.keySet().equals(MANIFEST_ENTRIES)) {
            throw invalid("execution manifest 文档集合不完整或包含未知条目");
        }
        String catalogVersion = string(manifest, "catalogVersion");
        if (!"1".equals(string(manifest, "manifestVersion"))
                || !"1".equals(catalogVersion)) {
            throw invalid("不支持的 execution manifest 或 catalog 版本");
        }

        Map<String, byte[]> verified = new HashMap<>();
        Set<String> paths = new LinkedHashSet<>();
        for (String entryName : DOCUMENT_ENTRIES) {
            Map<String, Object> entry = exactObject(
                    manifest.get(entryName), entryName, Set.of("path", "sha256"));
            String path = string(entry, "path");
            if (!DOCUMENT_PATH.matcher(path).matches() || !paths.add(path)) {
                throw invalid("execution manifest 包含非法或重复路径：" + path);
            }
            byte[] bytes = requireBytes(documents.apply(path), path);
            if (!sha256(bytes).equals(sha256Text(entry, "sha256"))) {
                throw invalid("execution 契约文档哈希不一致：" + path);
            }
            // Schema 文档同样必须是严格、无重复 key 的 JSON，不能只验证字节摘要。
            parse(bytes);
            verified.put(entryName, bytes);
        }

        Map<String, PromptProfile> prompts =
                parsePromptProfiles(verified.get("promptProfileRegistry"));
        Map<String, DeploymentProfile> deployments =
                parseDeploymentProfiles(verified.get("deploymentProfileRegistry"));
        Map<String, Profile> profiles =
                parseProfiles(verified.get("profileRegistry"), prompts, deployments);
        Map<String, OutputSchema> outputs =
                parseOutputSchemas(verified.get("outputSchemaRegistry"));
        Map<String, StepBudgetProfile> budgets =
                parseStepBudgets(verified.get("stepBudgetRegistry"));
        Map<String, Operation> operations =
                parseOperations(verified.get("catalog"), profiles, outputs, budgets);
        Map<String, SystemPurpose> purposes = parseSystemPurposes(
                verified.get("systemPurposeRegistry"),
                operations,
                profiles,
                outputs,
                budgets);
        return new ExecutionRegistry(
                operations,
                profiles,
                deployments,
                prompts,
                outputs,
                budgets,
                purposes,
                environment,
                catalogVersion,
                ExecutionCanonicalJson.sha256(manifest));
    }

    public String catalogVersion() {
        return catalogVersion;
    }

    /** manifest canonical SHA；其内容已绑定所有原始 Registry 文档 SHA。 */
    public String manifestFingerprint() {
        return manifestFingerprint;
    }

    public ExecutionPlanSnapshot freezePlan(
            String key, boolean allowDevelopmentOperations) {
        return ExecutionPlanSnapshot.freeze(
                catalogVersion,
                manifestFingerprint,
                resolve(key, allowDevelopmentOperations));
    }

    public ResolvedOperation resolve(String key, boolean allowDevelopmentOperations) {
        Operation operation = requireKnownOperation(key);
        if (!operation.v2Enabled()) throw invalid("V2 Operation 尚未启用：" + key);
        if (operation.developmentOnly() && !allowDevelopmentOperations) {
            throw invalid("开发专用 V2 Operation 不能在当前环境运行：" + key);
        }
        Profile generator = profiles.get(operation.generatorProfile());
        StepBudgetProfile generatorBudget = stepBudgets.get(operation.generatorStepBudgetProfile());
        OutputSchema output = outputSchemas.get(operation.outputSchema());
        ReviewPolicy policy = operation.reviewPolicy();
        List<ResolvedReviewer> reviewers = new ArrayList<>();
        for (String reviewerKey : policy.reviewerProfiles()) {
            reviewers.add(new ResolvedReviewer(
                    profiles.get(reviewerKey),
                    stepBudgets.get(policy.reviewerStepBudgetProfiles().get(reviewerKey))));
        }
        OutputSchema reviewerOutput = policy.reviewerOutputSchema() == null
                ? null
                : outputSchemas.get(policy.reviewerOutputSchema());
        requireExecutable(operation, generator, generatorBudget, output, reviewers, reviewerOutput);
        return new ResolvedOperation(
                operation,
                generator,
                generatorBudget,
                output,
                List.copyOf(reviewers),
                reviewerOutput);
    }

    public ResolvedSystemPurpose resolveSystemPurpose(String purpose) {
        SystemPurpose value = systemPurposes.get(purpose);
        if (value == null) throw invalid("未知 System Purpose：" + purpose);
        if (!value.supported()) throw invalid("System Purpose 尚未启用：" + purpose);
        Profile profile = profiles.get(value.modelProfile());
        OutputSchema output = outputSchemas.get(value.outputSchema());
        StepBudgetProfile budget = stepBudgets.get(value.stepBudgetProfile());
        if (!profile.supported()
                || !profile.promptProfile().supported()
                || !output.supported()
                || !budget.supported()) {
            throw invalid("System Purpose 的 Profile、Output 或 Step Budget 尚未实现：" + purpose);
        }
        requireReasoningBudget(profile, budget, purpose);
        return new ResolvedSystemPurpose(value, profile, output, budget);
    }

    public Operation requireKnownOperation(String key) {
        Operation operation = operations.get(key);
        if (operation == null) throw invalid("未知 Operation：" + key);
        return operation;
    }

    public AuthorizedDeployment requireAuthorizedDeployment(WorkflowResolvedModel resolved) {
        Objects.requireNonNull(resolved, "解析部署模型不能为空");
        DeploymentProfile profile = deploymentProfiles.get(resolved.deploymentProfileKey());
        if (profile == null || !profile.supported()) {
            throw invalid("Deployment Profile 未发布或不存在");
        }
        for (DeploymentModel allowed : profile.allowedModels()) {
            if (allowed.provider().equals(resolved.provider())
                    && allowed.model().equals(resolved.model())
                    && allowed.transportProfile().equals(resolved.transportProfile())
                    && allowed.endpointProfile().equals(resolved.endpointProfile())
                    && allowed.structuredOutputRoute().equals(resolved.structuredOutputRoute())
                    && allowed.capabilityVersion().equals(resolved.capabilityVersion())
                    && allowed.reasoningMode().equals(resolved.reasoningMode())
                    && allowed.supportsRequestIdempotency()
                            == resolved.supportsRequestIdempotency()
                    && allowed.allowedEnvironments().contains(environment.contractName())) {
                return new AuthorizedDeployment(
                        profile.key(),
                        allowed.provider(),
                        allowed.model(),
                        allowed.transportProfile(),
                        allowed.endpointProfile(),
                        allowed.structuredOutputRoute(),
                        allowed.capabilityVersion(),
                        allowed.reasoningMode(),
                        allowed.supportsRequestIdempotency(),
                        allowed.pricingVersion(),
                        allowed.billable());
            }
        }
        throw invalid("部署模型未被当前环境的 Deployment Profile 授权");
    }

    private static Map<String, PromptProfile> parsePromptProfiles(byte[] bytes) {
        Map<String, Object> root = exactObject(
                parse(bytes),
                "prompt profile registry",
                Set.of("registryVersion", "hashAlgorithm", "prompts"));
        requireRegistryVersion(root, "Prompt Profile Registry");
        if (!"sha256-utf8/1".equals(string(root, "hashAlgorithm"))) {
            throw invalid("Prompt Profile Registry 哈希算法不受支持");
        }
        Map<String, PromptProfile> result = new LinkedHashMap<>();
        for (Object raw : list(root, "prompts")) {
            Map<String, Object> value = exactObject(
                    raw,
                    "prompt profile",
                    Set.of("key", "version", "supported", "purpose", "sha256", "systemPrompt"));
            String key = string(value, "key");
            int version = positiveInt(value, "version");
            String systemPrompt = string(value, "systemPrompt");
            String expectedHash = sha256Text(value, "sha256");
            if (!sha256(systemPrompt.getBytes(StandardCharsets.UTF_8)).equals(expectedHash)) {
                throw invalid("Prompt Profile UTF-8 SHA-256 不一致：" + key);
            }
            PromptProfile prompt = new PromptProfile(
                    key,
                    version,
                    bool(value, "supported"),
                    enumText(
                            value,
                            "purpose",
                            Set.of("generation", "evaluation", "embedding", "review", "media")),
                    expectedHash,
                    systemPrompt);
            requireVersionedKey(key, version);
            putUnique(result, key, prompt, "Prompt Profile");
        }
        return result;
    }

    private static Map<String, DeploymentProfile> parseDeploymentProfiles(byte[] bytes) {
        Map<String, Object> root = exactObject(
                parse(bytes), "deployment profile registry", Set.of("registryVersion", "profiles"));
        requireRegistryVersion(root, "Deployment Profile Registry");
        Map<String, DeploymentProfile> result = new LinkedHashMap<>();
        for (Object raw : list(root, "profiles")) {
            Map<String, Object> value = exactObject(
                    raw,
                    "deployment profile",
                    Set.of("key", "version", "supported", "purpose", "allowedModels"));
            String key = string(value, "key");
            int version = positiveInt(value, "version");
            boolean supported = bool(value, "supported");
            List<DeploymentModel> allowedModels = new ArrayList<>();
            Set<String> identities = new LinkedHashSet<>();
            for (Object rawModel : list(value, "allowedModels")) {
                Map<String, Object> model = exactObject(
                        rawModel,
                        "deployment model",
                        Set.of(
                                "provider",
                                "model",
                                "transportProfile",
                                "endpointProfile",
                                "structuredOutputRoute",
                                "capabilityVersion",
                                "reasoningMode",
                                "supportsRequestIdempotency",
                                "allowedEnvironments",
                                "pricingVersion",
                                "billable"));
                List<String> environments = strings(model, "allowedEnvironments");
                requireUnique(environments, "Deployment allowedEnvironments");
                for (String environment : environments) {
                    if (!Set.of("dev", "test", "production").contains(environment)) {
                        throw invalid("Deployment Profile 包含未知环境：" + environment);
                    }
                }
                String transportProfile = string(model, "transportProfile");
                String endpointProfile = string(model, "endpointProfile");
                String capabilityVersion = string(model, "capabilityVersion");
                String pricingVersion = string(model, "pricingVersion");
                requirePositiveVersionedIdentifier(transportProfile, "transportProfile");
                requirePositiveVersionedIdentifier(endpointProfile, "endpointProfile");
                requirePositiveVersionedIdentifier(capabilityVersion, "capabilityVersion");
                requirePositiveVersionedIdentifier(pricingVersion, "pricingVersion");
                DeploymentModel allowed = new DeploymentModel(
                        string(model, "provider"),
                        string(model, "model"),
                        transportProfile,
                        endpointProfile,
                        enumText(
                                model,
                                "structuredOutputRoute",
                                Set.of("responses_json_schema_v1", "chat_json_output_v1")),
                        capabilityVersion,
                        enumText(model, "reasoningMode", Set.of("disabled", "bounded")),
                        bool(model, "supportsRequestIdempotency"),
                        environments,
                        pricingVersion,
                        bool(model, "billable"));
                String identity = String.join(
                        "\u0000",
                        allowed.provider(),
                        allowed.model(),
                        allowed.transportProfile(),
                        allowed.endpointProfile(),
                        allowed.structuredOutputRoute(),
                        allowed.capabilityVersion(),
                        allowed.reasoningMode(),
                        Boolean.toString(allowed.supportsRequestIdempotency()));
                if (!identities.add(identity)) {
                    throw invalid("Deployment Profile 存在重复授权元组：" + key);
                }
                allowedModels.add(allowed);
            }
            if (supported != !allowedModels.isEmpty()) {
                throw invalid("Deployment Profile supported 与 allowedModels 不一致：" + key);
            }
            DeploymentProfile profile = new DeploymentProfile(
                    key,
                    version,
                    supported,
                    enumText(
                            value,
                            "purpose",
                            Set.of("generation", "evaluation", "embedding", "review", "media")),
                    allowedModels);
            requireVersionedKey(key, version);
            putUnique(result, key, profile, "Deployment Profile");
        }
        return result;
    }

    private static Map<String, Profile> parseProfiles(
            byte[] bytes,
            Map<String, PromptProfile> prompts,
            Map<String, DeploymentProfile> deployments) {
        Map<String, Object> root = exactObject(
                parse(bytes), "profile registry", Set.of("registryVersion", "profiles"));
        requireRegistryVersion(root, "Profile Registry");
        Map<String, Profile> result = new LinkedHashMap<>();
        for (Object raw : list(root, "profiles")) {
            Map<String, Object> value = exactObject(
                    raw,
                    "profile",
                    Set.of(
                            "key",
                            "version",
                            "supported",
                            "reasoningMode",
                            "purpose",
                            "promptProfile",
                            "deploymentProfileKey"));
            String key = string(value, "key");
            String purpose = enumText(
                    value,
                    "purpose",
                    Set.of("generation", "evaluation", "embedding", "review", "media"));
            PromptProfile prompt = prompts.get(string(value, "promptProfile"));
            if (prompt == null) {
                throw invalid("Profile 引用了缺失 Prompt Profile：" + key);
            }
            if (!purpose.equals(prompt.purpose())) {
                throw invalid("Profile 与 Prompt Profile purpose 不一致：" + key);
            }
            boolean supported = bool(value, "supported");
            if (supported && !prompt.supported()) {
                throw invalid("已启用 Profile 引用了未发布 Prompt Profile：" + key);
            }
            String deploymentKey = string(value, "deploymentProfileKey");
            DeploymentProfile deployment = deployments.get(deploymentKey);
            if (deployment == null) {
                throw invalid("Profile 引用了缺失 Deployment Profile：" + key);
            }
            if (!purpose.equals(deployment.purpose())) {
                throw invalid("Profile 与 Deployment Profile purpose 不一致：" + key);
            }
            if (supported && !deployment.supported()) {
                throw invalid("已启用 Profile 引用了未发布 Deployment Profile：" + key);
            }
            String reasoningMode =
                    enumText(value, "reasoningMode", Set.of("disabled", "bounded"));
            if (deployment.allowedModels().stream()
                    .anyMatch(allowed -> !reasoningMode.equals(allowed.reasoningMode()))) {
                throw invalid("Profile 与 Deployment Profile reasoningMode 不一致：" + key);
            }
            Profile profile = new Profile(
                    key,
                    positiveInt(value, "version"),
                    supported,
                    reasoningMode,
                    purpose,
                    prompt,
                    deploymentKey);
            requireVersionedKey(profile.key(), profile.version());
            putUnique(result, profile.key(), profile, "Profile");
        }
        return result;
    }

    private static Map<String, OutputSchema> parseOutputSchemas(byte[] bytes) {
        Map<String, Object> root = exactObject(
                parse(bytes),
                "output schema registry",
                Set.of("registryVersion", "hashAlgorithm", "schemas"));
        requireRegistryVersion(root, "Output Schema Registry");
        if (!ExecutionCanonicalJson.ALGORITHM.equals(string(root, "hashAlgorithm"))) {
            throw invalid("Output Schema Registry 哈希算法不受支持");
        }
        Map<String, OutputSchema> result = new LinkedHashMap<>();
        for (Object raw : list(root, "schemas")) {
            Map<String, Object> value = exactObject(
                    raw,
                    "output schema",
                    Set.of("key", "version", "supported", "purpose", "sha256", "jsonSchema"));
            String key = string(value, "key");
            int version = positiveInt(value, "version");
            Map<String, Object> schema = immutableObject(value.get("jsonSchema"), "jsonSchema");
            String expectedHash = sha256Text(value, "sha256");
            if (!ExecutionCanonicalJson.sha256(schema).equals(expectedHash)) {
                throw invalid("Output Schema canonical SHA-256 不一致：" + key);
            }
            OutputSchema output = new OutputSchema(
                    key,
                    version,
                    bool(value, "supported"),
                    enumText(
                            value,
                            "purpose",
                            Set.of("generation", "evaluation", "embedding", "media")),
                    expectedHash,
                    schema);
            requireVersionedKey(output.key(), output.version());
            putUnique(result, key, output, "Output Schema");
        }
        return result;
    }

    private static Map<String, StepBudgetProfile> parseStepBudgets(byte[] bytes) {
        Map<String, Object> root = exactObject(
                parse(bytes), "step budget registry", Set.of("registryVersion", "budgets"));
        requireRegistryVersion(root, "Step Budget Registry");
        Map<String, StepBudgetProfile> result = new LinkedHashMap<>();
        for (Object raw : list(root, "budgets")) {
            Map<String, Object> value = exactObject(
                    raw, "step budget profile", Set.of("key", "version", "supported", "budget"));
            String key = string(value, "key");
            int version = positiveInt(value, "version");
            WorkflowStepBudget budget = stepBudget(object(value.get("budget"), "step budget"));
            StepBudgetProfile profile =
                    new StepBudgetProfile(key, version, bool(value, "supported"), budget);
            requireVersionedKey(key, version);
            putUnique(result, key, profile, "Step Budget");
        }
        return result;
    }

    private static Map<String, Operation> parseOperations(
            byte[] bytes,
            Map<String, Profile> profiles,
            Map<String, OutputSchema> outputs,
            Map<String, StepBudgetProfile> budgets) {
        Map<String, Object> root = exactObject(
                parse(bytes), "operation catalog", Set.of("catalogVersion", "operations"));
        if (!"1".equals(string(root, "catalogVersion"))) {
            throw invalid("不支持的 Operation Catalog 版本");
        }
        Map<String, Operation> result = new LinkedHashMap<>();
        for (Object raw : list(root, "operations")) {
            Map<String, Object> value = object(raw, "operation");
            String workflow = string(value, "workflow");
            String operationName = string(value, "operation");
            String key = string(value, "key");
            if (!key.equals(workflow + "." + operationName)) {
                throw invalid("Operation key 与 workflow/operation 不一致：" + key);
            }
            ReviewPolicy review = reviewPolicy(object(value.get("reviewPolicy"), "reviewPolicy"));
            Operation parsed = new Operation(
                    key,
                    workflow,
                    operationName,
                    strings(value, "targetKinds"),
                    strings(value, "scopeKinds"),
                    bool(value, "v2Enabled"),
                    bool(value, "developmentOnly"),
                    bool(value, "mutating"),
                    enumText(value, "lane", Set.of("interactive", "creative", "batch_media")),
                    string(value, "evidencePolicy"),
                    string(value, "generatorProfile"),
                    optionalString(value, "generatorStepBudgetProfile"),
                    string(value, "outputSchema"),
                    strings(value, "deterministicValidators"),
                    review,
                    string(value, "applyHandler"),
                    runBudget(object(value.get("runBudgetProfile"), "runBudgetProfile")));
            validateOperationReferences(parsed, profiles, outputs, budgets);
            putUnique(result, key, parsed, "Operation");
        }
        return result;
    }

    private static ReviewPolicy reviewPolicy(Map<String, Object> value) {
        String mode = enumText(value, "mode", Set.of("none", "single", "parallel"));
        List<String> reviewers = strings(value, "reviewerProfiles");
        requireUnique(reviewers, "reviewerProfiles");
        Map<String, String> reviewerBudgets = optionalStringMap(
                value, "reviewerStepBudgetProfiles");
        ReviewPolicy result = new ReviewPolicy(
                string(value, "profile"),
                mode,
                reviewers,
                reviewerBudgets,
                optionalString(value, "reviewerOutputSchema"),
                optionalString(value, "rubricVersion"),
                optionalString(value, "evidencePolicy"),
                optionalString(value, "lane"),
                string(value, "mergePolicy"),
                nonNegativeInt(value, "maxAutomaticRevisions"),
                enumText(value, "onUnavailable", Set.of("continue", "awaiting_user", "fail")));
        if ("none".equals(mode)) {
            if (!reviewers.isEmpty()
                    || !reviewerBudgets.isEmpty()
                    || result.reviewerOutputSchema() != null
                    || result.rubricVersion() != null
                    || result.evidencePolicy() != null
                    || result.lane() != null
                    || result.maxAutomaticRevisions() != 0
                    || !"continue".equals(result.onUnavailable())) {
                throw invalid("无 Reviewer 策略不能夹带 Reviewer 执行配置");
            }
            return result;
        }
        int expectedReviewers = "single".equals(mode) ? 1 : 2;
        if (reviewers.size() != expectedReviewers
                || !"awaiting_user".equals(result.onUnavailable())) {
            throw invalid("Reviewer 策略的 mode、Profile 数量或不可用策略不一致");
        }
        boolean hasExecutionConfig = !reviewerBudgets.isEmpty()
                || result.reviewerOutputSchema() != null
                || result.rubricVersion() != null
                || result.evidencePolicy() != null
                || result.lane() != null;
        if (hasExecutionConfig
                && (!reviewerBudgets.keySet().equals(Set.copyOf(reviewers))
                        || result.reviewerOutputSchema() == null
                        || result.rubricVersion() == null
                        || result.evidencePolicy() == null
                        || result.lane() == null
                        || !Set.of("interactive", "creative", "batch_media")
                                .contains(result.lane()))) {
            throw invalid("Reviewer 策略缺少精确 Profile、预算、Schema、rubric、Evidence 或 lane");
        }
        return result;
    }

    private static Map<String, SystemPurpose> parseSystemPurposes(
            byte[] bytes,
            Map<String, Operation> operations,
            Map<String, Profile> profiles,
            Map<String, OutputSchema> outputs,
            Map<String, StepBudgetProfile> budgets) {
        Map<String, Object> root = exactObject(
                parse(bytes), "system purpose registry", Set.of("registryVersion", "purposes"));
        requireRegistryVersion(root, "System Purpose Registry");
        Map<String, SystemPurpose> result = new LinkedHashMap<>();
        for (Object raw : list(root, "purposes")) {
            Map<String, Object> value = exactObject(
                    raw,
                    "system purpose",
                    Set.of(
                            "purpose",
                            "supported",
                            "modelProfile",
                            "outputSchema",
                            "evidencePolicy",
                            "lane",
                            "stepBudgetProfile",
                            "workflows",
                            "parentOperations"));
            SystemPurpose purpose = new SystemPurpose(
                    string(value, "purpose"),
                    bool(value, "supported"),
                    string(value, "modelProfile"),
                    string(value, "outputSchema"),
                    string(value, "evidencePolicy"),
                    enumText(value, "lane", Set.of("interactive", "creative", "batch_media")),
                    string(value, "stepBudgetProfile"),
                    strings(value, "workflows"),
                    strings(value, "parentOperations"));
            requireUnique(purpose.workflows(), "System Purpose workflows");
            requireUnique(purpose.parentOperations(), "System Purpose parentOperations");
            requireReference(profiles, purpose.modelProfile(), purpose.purpose(), "modelProfile");
            requireReference(outputs, purpose.outputSchema(), purpose.purpose(), "outputSchema");
            requireReference(budgets, purpose.stepBudgetProfile(), purpose.purpose(), "stepBudgetProfile");
            for (String parent : purpose.parentOperations()) {
                requireReference(operations, parent, purpose.purpose(), "parentOperation");
            }
            if (purpose.supported()) {
                Profile profile = profiles.get(purpose.modelProfile());
                OutputSchema output = outputs.get(purpose.outputSchema());
                StepBudgetProfile budget = budgets.get(purpose.stepBudgetProfile());
                if (!profile.supported() || !output.supported() || !budget.supported()) {
                    throw invalid("已启用 System Purpose 引用了未实现依赖：" + purpose.purpose());
                }
                requireReasoningBudget(profile, budget, purpose.purpose());
            }
            putUnique(result, purpose.purpose(), purpose, "System Purpose");
        }
        if (!result.keySet().containsAll(
                Set.of("resolve_intent", "summarize_evidence", "protocol_correction"))) {
            throw invalid("System Purpose Registry 缺少必需用途");
        }
        return result;
    }

    private static void validateOperationReferences(
            Operation operation,
            Map<String, Profile> profiles,
            Map<String, OutputSchema> outputs,
            Map<String, StepBudgetProfile> budgets) {
        requireReference(
                profiles, operation.generatorProfile(), operation.key(), "generatorProfile");
        requireReference(outputs, operation.outputSchema(), operation.key(), "outputSchema");
        if (operation.generatorStepBudgetProfile() != null) {
            requireReference(
                    budgets,
                    operation.generatorStepBudgetProfile(),
                    operation.key(),
                    "generatorStepBudgetProfile");
        }
        ReviewPolicy review = operation.reviewPolicy();
        for (String reviewer : review.reviewerProfiles()) {
            requireReference(profiles, reviewer, operation.key(), "reviewerProfile");
            String reviewerBudget = review.reviewerStepBudgetProfiles().get(reviewer);
            if (reviewerBudget != null) {
                requireReference(
                        budgets,
                        reviewerBudget,
                        operation.key(),
                        "reviewerStepBudgetProfile");
            }
        }
        if (review.reviewerOutputSchema() != null) {
            requireReference(
                    outputs,
                    review.reviewerOutputSchema(),
                    operation.key(),
                    "reviewerOutputSchema");
        }
        if (operation.v2Enabled() && operation.generatorStepBudgetProfile() == null) {
            throw invalid("已启用 Operation 缺少 generator Step Budget：" + operation.key());
        }
        if (operation.v2Enabled()
                && !"none".equals(review.mode())
                && (!review.reviewerStepBudgetProfiles().keySet()
                                .equals(Set.copyOf(review.reviewerProfiles()))
                        || review.reviewerOutputSchema() == null
                        || review.rubricVersion() == null
                        || review.evidencePolicy() == null
                        || review.lane() == null)) {
            throw invalid("已启用 Operation 的 Reviewer 执行配置不完整：" + operation.key());
        }
    }

    private static void requireExecutable(
            Operation operation,
            Profile generator,
            StepBudgetProfile generatorBudget,
            OutputSchema output,
            List<ResolvedReviewer> reviewers,
            OutputSchema reviewerOutput) {
        if (generator == null
                || generatorBudget == null
                || output == null
                || !generator.supported()
                || !generator.promptProfile().supported()
                || !generatorBudget.supported()
                || !output.supported()) {
            throw invalid("V2 Operation 的生成 Profile、Step Budget 或 Output 尚未实现：" + operation.key());
        }
        requireReasoningBudget(generator, generatorBudget, operation.key());
        WorkflowRunBudget run = operation.runBudget().toDomain();
        run.requireStepFits(generatorBudget.budget());
        List<WorkflowRunBudgetCharge> initialCharges = new ArrayList<>();
        initialCharges.add(WorkflowRunBudgetCharge.active(generatorBudget.budget()));
        for (ResolvedReviewer reviewer : reviewers) {
            if (reviewer.profile() == null
                    || reviewer.stepBudget() == null
                    || !reviewer.profile().supported()
                    || !reviewer.profile().promptProfile().supported()
                    || !reviewer.stepBudget().supported()) {
                throw invalid("V2 Operation 的 Reviewer Profile 或 Step Budget 尚未实现：" + operation.key());
            }
            if (!"review".equals(reviewer.profile().purpose())) {
                throw invalid("Reviewer Profile purpose 必须是 review：" + reviewer.profile().key());
            }
            requireReasoningBudget(reviewer.profile(), reviewer.stepBudget(), operation.key());
            run.requireStepFits(reviewer.stepBudget().budget());
            initialCharges.add(WorkflowRunBudgetCharge.active(reviewer.stepBudget().budget()));
        }
        if (!reviewers.isEmpty()
                && (reviewerOutput == null
                        || !reviewerOutput.supported()
                        || !"evaluation".equals(reviewerOutput.purpose()))) {
            throw invalid("V2 Operation 的 Reviewer Output 尚未实现或用途错误：" + operation.key());
        }
        run.requireWithin(initialCharges);
    }

    private static void requireReasoningBudget(
            Profile profile, StepBudgetProfile budget, String owner) {
        long reasoning = budget.budget().maxReasoningTokens();
        if (("disabled".equals(profile.reasoningMode()) && reasoning != 0)
                || ("bounded".equals(profile.reasoningMode()) && reasoning == 0)) {
            throw invalid(owner + " 的 Profile reasoningMode 与 Step Budget 不一致");
        }
    }

    private static WorkflowStepBudget stepBudget(Map<String, Object> value) {
        Set<String> expected = Set.of(
                "maxModelCalls",
                "maxInputTokens",
                "maxPromptCacheMissTokens",
                "maxCompletionTokens",
                "maxReasoningTokens",
                "maxVisibleOutputTokens",
                "maxCostMicros",
                "maxWallClockSeconds",
                "maxProviderRetries",
                "maxProtocolCorrections");
        if (!value.keySet().equals(expected)) throw invalid("Step Budget 字段集合无效");
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

    private static RunBudget runBudget(Map<String, Object> value) {
        return new RunBudget(
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

    private static byte[] readClasspathDocument(String path) {
        try (InputStream input = ExecutionRegistry.class
                .getResourceAsStream("/agent-execution/" + path)) {
            if (input == null) throw invalid("缺少 execution 契约资源：" + path);
            return input.readAllBytes();
        } catch (IOException exception) {
            throw new IllegalStateException("读取 execution 契约资源失败：" + path, exception);
        }
    }

    private static Object parse(byte[] bytes) {
        try {
            return JSON.readValue(requireBytes(bytes, "JSON"), Object.class);
        } catch (RuntimeException exception) {
            throw new IllegalStateException("execution 契约 JSON 无法严格解析", exception);
        }
    }

    private static byte[] requireBytes(byte[] bytes, String name) {
        if (bytes == null || bytes.length == 0) throw invalid("缺少 execution 文档：" + name);
        return bytes;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value, String name) {
        if (!(value instanceof Map<?, ?> raw)) throw invalid(name + " 必须是 JSON 对象");
        for (Object key : raw.keySet()) {
            if (!(key instanceof String)) throw invalid(name + " 的 key 必须是字符串");
        }
        return (Map<String, Object>) raw;
    }

    private static Map<String, Object> exactObject(
            Object value, String name, Set<String> expectedKeys) {
        Map<String, Object> result = object(value, name);
        if (!result.keySet().equals(expectedKeys)) {
            throw invalid(name + " 字段集合无效");
        }
        return result;
    }

    private static Map<String, Object> immutableObject(Object value, String name) {
        return castImmutableMap(freeze(object(value, name)));
    }

    private static Object freeze(Object value) {
        if (value instanceof Map<?, ?> raw) {
            Map<String, Object> copy = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : raw.entrySet()) {
                if (!(entry.getKey() instanceof String key)) {
                    throw invalid("JSON 对象 key 必须是字符串");
                }
                copy.put(key, freeze(entry.getValue()));
            }
            return Collections.unmodifiableMap(copy);
        }
        if (value instanceof List<?> raw) {
            List<Object> copy = new ArrayList<>(raw.size());
            for (Object item : raw) copy.add(freeze(item));
            return Collections.unmodifiableList(copy);
        }
        return value;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> castImmutableMap(Object value) {
        return (Map<String, Object>) value;
    }

    private static List<Object> list(Map<String, Object> value, String field) {
        Object raw = value.get(field);
        if (!(raw instanceof List<?> items)) throw invalid(field + " 必须是数组");
        return List.copyOf(items);
    }

    private static List<String> strings(Map<String, Object> value, String field) {
        List<String> result = new ArrayList<>();
        for (Object item : list(value, field)) {
            if (!(item instanceof String text) || text.isBlank()) {
                throw invalid(field + " 必须只包含非空字符串");
            }
            result.add(text);
        }
        return List.copyOf(result);
    }

    private static Map<String, String> optionalStringMap(
            Map<String, Object> value, String field) {
        Object raw = value.get(field);
        if (raw == null) return Map.of();
        Map<String, Object> source = object(raw, field);
        Map<String, String> result = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : source.entrySet()) {
            if (entry.getKey().isBlank()
                    || !(entry.getValue() instanceof String text)
                    || text.isBlank()) {
                throw invalid(field + " 必须是非空字符串映射");
            }
            result.put(entry.getKey(), text);
        }
        return Map.copyOf(result);
    }

    private static String string(Map<String, Object> value, String field) {
        Object raw = value.get(field);
        if (!(raw instanceof String text) || text.isBlank()) {
            throw invalid(field + " 必须是非空字符串");
        }
        return text;
    }

    private static String optionalString(Map<String, Object> value, String field) {
        Object raw = value.get(field);
        if (raw == null) return null;
        if (!(raw instanceof String text) || text.isBlank()) {
            throw invalid(field + " 必须是非空字符串");
        }
        return text;
    }

    private static String enumText(
            Map<String, Object> value, String field, Set<String> allowed) {
        String result = string(value, field);
        if (!allowed.contains(result)) throw invalid(field + " 值不受支持：" + result);
        return result;
    }

    private static String sha256Text(Map<String, Object> value, String field) {
        String result = string(value, field);
        if (!result.matches("^[0-9a-f]{64}$")) throw invalid(field + " 必须是小写 SHA-256");
        return result;
    }

    private static boolean bool(Map<String, Object> value, String field) {
        Object raw = value.get(field);
        if (!(raw instanceof Boolean result)) throw invalid(field + " 必须是布尔值");
        return result;
    }

    private static int positiveInt(Map<String, Object> value, String field) {
        int result = exactInt(value, field);
        if (result < 1) throw invalid(field + " 必须为正整数");
        return result;
    }

    private static int nonNegativeInt(Map<String, Object> value, String field) {
        int result = exactInt(value, field);
        if (result < 0) throw invalid(field + " 不能为负数");
        return result;
    }

    private static int exactInt(Map<String, Object> value, String field) {
        Object raw = value.get(field);
        if (!(raw instanceof Number number)) throw invalid(field + " 必须是整数");
        long result = number.longValue();
        if (number.doubleValue() != result
                || result < Integer.MIN_VALUE
                || result > Integer.MAX_VALUE) {
            throw invalid(field + " 超出整数范围");
        }
        return (int) result;
    }

    private static long positiveLong(Map<String, Object> value, String field) {
        long result = exactLong(value, field);
        if (result < 1) throw invalid(field + " 必须为正整数");
        return result;
    }

    private static long nonNegativeLong(Map<String, Object> value, String field) {
        long result = exactLong(value, field);
        if (result < 0) throw invalid(field + " 不能为负数");
        return result;
    }

    private static long exactLong(Map<String, Object> value, String field) {
        Object raw = value.get(field);
        if (!(raw instanceof Number number)) throw invalid(field + " 必须是整数");
        long result = number.longValue();
        if (number.doubleValue() != result) throw invalid(field + " 必须是整数");
        return result;
    }

    private static void requireRegistryVersion(Map<String, Object> root, String name) {
        if (!"1".equals(string(root, "registryVersion"))) {
            throw invalid("不支持的 " + name + " 版本");
        }
    }

    private static void requireVersionedKey(String key, int version) {
        if (!key.endsWith(".v" + version)) {
            throw invalid("版本化 key 与 version 不一致：" + key);
        }
    }

    private static void requirePositiveVersionedIdentifier(String value, String field) {
        if (!value.matches("^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\\.v[1-9][0-9]*$")) {
            throw invalid(field + " 必须是正版本标识：" + value);
        }
    }

    private static void requireUnique(List<String> values, String field) {
        if (new LinkedHashSet<>(values).size() != values.size()) {
            throw invalid(field + " 不能重复");
        }
    }

    private static <T> void requireReference(
            Map<String, T> values, String reference, String owner, String field) {
        if (reference == null || !values.containsKey(reference)) {
            throw invalid(owner + " 的 " + field + " 引用不存在：" + reference);
        }
    }

    private static <T> void putUnique(
            Map<String, T> values, String key, T value, String kind) {
        if (values.putIfAbsent(key, value) != null) {
            throw invalid(kind + " key 重复：" + key);
        }
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of()
                    .formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 缺少 SHA-256", exception);
        }
    }

    private static IllegalStateException invalid(String message) {
        return new IllegalStateException(message);
    }

    public record RunBudget(
            String profile,
            int maxModelCalls,
            long maxInputTokens,
            long maxPromptCacheMissTokens,
            long maxCompletionTokens,
            long maxReasoningTokens,
            long maxVisibleOutputTokens,
            long maxCostMicros,
            long maxWallClockSeconds,
            int maxProviderRetriesPerStep,
            int maxProtocolCorrectionSteps) {

        public WorkflowRunBudget toDomain() {
            return new WorkflowRunBudget(
                    maxModelCalls,
                    maxInputTokens,
                    maxPromptCacheMissTokens,
                    maxCompletionTokens,
                    maxReasoningTokens,
                    maxVisibleOutputTokens,
                    maxCostMicros,
                    maxWallClockSeconds,
                    maxProviderRetriesPerStep,
                    maxProtocolCorrectionSteps);
        }
    }

    public record PromptProfile(
            String key,
            int version,
            boolean supported,
            String purpose,
            String sha256,
            String systemPrompt) {}

    public enum Environment {
        DEV("dev"),
        TEST("test"),
        PRODUCTION("production");

        private final String contractName;

        Environment(String contractName) {
            this.contractName = contractName;
        }

        public String contractName() {
            return contractName;
        }
    }

    public record DeploymentModel(
            String provider,
            String model,
            String transportProfile,
            String endpointProfile,
            String structuredOutputRoute,
            String capabilityVersion,
            String reasoningMode,
            boolean supportsRequestIdempotency,
            List<String> allowedEnvironments,
            String pricingVersion,
            boolean billable) {
        public DeploymentModel {
            allowedEnvironments = List.copyOf(allowedEnvironments);
        }
    }

    public record DeploymentProfile(
            String key,
            int version,
            boolean supported,
            String purpose,
            List<DeploymentModel> allowedModels) {
        public DeploymentProfile {
            allowedModels = List.copyOf(allowedModels);
        }
    }

    public record AuthorizedDeployment(
            String deploymentProfileKey,
            String provider,
            String model,
            String transportProfile,
            String endpointProfile,
            String structuredOutputRoute,
            String capabilityVersion,
            String reasoningMode,
            boolean supportsRequestIdempotency,
            String pricingVersion,
            boolean billable) {}

    public record Profile(
            String key,
            int version,
            boolean supported,
            String reasoningMode,
            String purpose,
            PromptProfile promptProfile,
            String deploymentProfileKey) {}

    public record OutputSchema(
            String key,
            int version,
            boolean supported,
            String purpose,
            String sha256,
            Map<String, Object> jsonSchema) {}

    public record StepBudgetProfile(
            String key,
            int version,
            boolean supported,
            WorkflowStepBudget budget) {}

    public record ReviewPolicy(
            String profile,
            String mode,
            List<String> reviewerProfiles,
            Map<String, String> reviewerStepBudgetProfiles,
            String reviewerOutputSchema,
            String rubricVersion,
            String evidencePolicy,
            String lane,
            String mergePolicy,
            int maxAutomaticRevisions,
            String onUnavailable) {
        public ReviewPolicy {
            reviewerProfiles = List.copyOf(reviewerProfiles);
            reviewerStepBudgetProfiles = Map.copyOf(reviewerStepBudgetProfiles);
        }
    }

    public record Operation(
            String key,
            String workflow,
            String operation,
            List<String> targetKinds,
            List<String> scopeKinds,
            boolean v2Enabled,
            boolean developmentOnly,
            boolean mutating,
            String lane,
            String evidencePolicy,
            String generatorProfile,
            String generatorStepBudgetProfile,
            String outputSchema,
            List<String> deterministicValidators,
            ReviewPolicy reviewPolicy,
            String applyHandler,
            RunBudget runBudget) {
        public Operation {
            targetKinds = List.copyOf(targetKinds);
            scopeKinds = List.copyOf(scopeKinds);
            deterministicValidators = List.copyOf(deterministicValidators);
        }
    }

    public record SystemPurpose(
            String purpose,
            boolean supported,
            String modelProfile,
            String outputSchema,
            String evidencePolicy,
            String lane,
            String stepBudgetProfile,
            List<String> workflows,
            List<String> parentOperations) {
        public SystemPurpose {
            workflows = List.copyOf(workflows);
            parentOperations = List.copyOf(parentOperations);
        }
    }

    public record ResolvedReviewer(Profile profile, StepBudgetProfile stepBudget) {}

    public record ResolvedOperation(
            Operation operation,
            Profile generatorProfile,
            StepBudgetProfile generatorStepBudget,
            OutputSchema outputSchema,
            List<ResolvedReviewer> reviewers,
            OutputSchema reviewerOutputSchema) {
        public ResolvedOperation {
            reviewers = List.copyOf(reviewers);
        }
    }

    public record ResolvedSystemPurpose(
            SystemPurpose purpose,
            Profile modelProfile,
            OutputSchema outputSchema,
            StepBudgetProfile stepBudget) {}
}
