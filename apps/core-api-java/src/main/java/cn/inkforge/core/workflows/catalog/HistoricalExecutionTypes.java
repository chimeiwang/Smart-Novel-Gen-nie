package cn.inkforge.core.workflows.catalog;

import cn.inkforge.core.workflows.domain.WorkflowRunBudget;
import cn.inkforge.core.workflows.domain.WorkflowStepBudget;
import java.util.List;
import java.util.Map;

/** 历史冻结执行快照的数据类型；不读取注册表、不授权模型或创建任务。 */
public class HistoricalExecutionTypes {
    protected HistoricalExecutionTypes() {}

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
            List<DeploymentModel> allowedModels,
            ConfiguredDeploymentBinding configuredBinding) {
        public DeploymentProfile(String key, int version, boolean supported, String purpose,
                List<DeploymentModel> allowedModels) {
            this(key, version, supported, purpose, allowedModels, null);
        }
        public DeploymentProfile {
            allowedModels = List.copyOf(allowedModels);
        }
    }

    public record ConfiguredDeploymentBinding(String key, List<String> allowedEnvironments,
            String pricingVersion, boolean billable) {
        public ConfiguredDeploymentBinding {
            allowedEnvironments = List.copyOf(allowedEnvironments);
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
            RunBudget runBudget,
            List<Stage> stageSteps,
            String videoStagePolicy) {
        public Operation {
            targetKinds = List.copyOf(targetKinds);
            scopeKinds = List.copyOf(scopeKinds);
            deterministicValidators = List.copyOf(deterministicValidators);
            stageSteps = List.copyOf(stageSteps);
        }

        public Operation(String key, String workflow, String operation, List<String> targetKinds,
                List<String> scopeKinds, boolean v2Enabled, boolean developmentOnly, boolean mutating,
                String lane, String evidencePolicy, String generatorProfile, String generatorStepBudgetProfile,
                String outputSchema, List<String> deterministicValidators, ReviewPolicy reviewPolicy,
                String applyHandler, RunBudget runBudget) {
            this(key, workflow, operation, targetKinds, scopeKinds, v2Enabled, developmentOnly, mutating,
                    lane, evidencePolicy, generatorProfile, generatorStepBudgetProfile, outputSchema,
                    deterministicValidators, reviewPolicy, applyHandler, runBudget, List.of(), null);
        }
    }

    public record Stage(String stageKey, String modelProfile, String outputSchema,
            String stepBudgetProfile, int maxInvocations) {}

    public record ResolvedStage(String stageKey, Profile profile, OutputSchema outputSchema,
            StepBudgetProfile stepBudget, int maxInvocations) {}

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
            OutputSchema reviewerOutputSchema,
            List<ResolvedStage> stageSteps) {
        public ResolvedOperation {
            reviewers = List.copyOf(reviewers);
            stageSteps = List.copyOf(stageSteps);
        }

        public ResolvedOperation(Operation operation, Profile generatorProfile, StepBudgetProfile generatorStepBudget,
                OutputSchema outputSchema, List<ResolvedReviewer> reviewers, OutputSchema reviewerOutputSchema) {
            this(operation, generatorProfile, generatorStepBudget, outputSchema, reviewers, reviewerOutputSchema, List.of());
        }
    }

    public record ResolvedSystemPurpose(
            SystemPurpose purpose,
            Profile modelProfile,
            OutputSchema outputSchema,
            StepBudgetProfile stepBudget) {}
}
