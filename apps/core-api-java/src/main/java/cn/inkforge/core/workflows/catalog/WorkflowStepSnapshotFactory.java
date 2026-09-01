package cn.inkforge.core.workflows.catalog;

import cn.inkforge.contracts.api.ModelProfileRef;
import cn.inkforge.contracts.api.PromptProfileRef;
import cn.inkforge.contracts.api.ResolvedModelRef;
import cn.inkforge.contracts.api.StepProgressEventPayload;
import cn.inkforge.contracts.api.WorkflowCurrentStepSnapshot;
import cn.inkforge.contracts.api.WorkflowStepProgressSnapshot;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import java.util.Map;
import java.util.Objects;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.ObjectMapper;

/** 从 Run 冻结计划和 Step 持久事实生成无敏感信息的公共 Step snapshot。 */
public final class WorkflowStepSnapshotFactory {

    private static final TypeReference<Map<String, Object>> JSON_OBJECT =
            new TypeReference<>() {};

    private final ObjectMapper json;

    public WorkflowStepSnapshotFactory(ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
    }

    public ExecutionPlanSnapshot executionPlan(String storedJson) {
        try {
            return ExecutionPlanSnapshot.fromStored(json.readValue(storedJson, JSON_OBJECT));
        } catch (RuntimeException exception) {
            throw new IllegalStateException("WorkflowRun 冻结执行计划损坏", exception);
        }
    }

    public WorkflowCurrentStepSnapshot modelStep(
            ExecutionPlanSnapshot plan,
            String stepId,
            int ordinal,
            String purpose,
            String lane,
            String status,
            int attemptCount,
            long fencingToken,
            String errorCode,
            String modelProfile,
            int modelProfileVersion,
            String resolvedModelJson) {
        return modelStep(
                plan,
                stepId,
                ordinal,
                purpose,
                lane,
                status,
                attemptCount,
                fencingToken,
                errorCode,
                modelProfile,
                modelProfileVersion,
                resolvedModelJson,
                null);
    }

    public WorkflowCurrentStepSnapshot modelStep(
            ExecutionPlanSnapshot plan,
            String stepId,
            int ordinal,
            String purpose,
            String lane,
            String status,
            int attemptCount,
            long fencingToken,
            String errorCode,
            String modelProfile,
            int modelProfileVersion,
            String resolvedModelJson,
            String latestProgressJson) {
        ExecutionPlanSnapshot.ModelProfile frozen = plan.requireStepProfile(
                purpose, lane, modelProfile, modelProfileVersion);
        ModelProfileRef logical = logical(frozen);
        ResolvedModelRef resolved = resolved(resolvedModelJson, frozen);
        if ("running".equals(status) && resolved == null) {
            throw new IllegalStateException("running WorkflowStep 缺少冻结 resolvedModel");
        }
        WorkflowStepProgressSnapshot latestProgress = latestProgress(
                latestProgressJson, stepId, fencingToken, status, logical, resolved);
        return new WorkflowCurrentStepSnapshot(
                        attemptCount,
                        Math.toIntExact(fencingToken),
                        WorkflowCurrentStepSnapshot.LaneEnum.fromValue(lane),
                        latestProgress,
                        logical,
                        ordinal,
                        purpose,
                        resolved,
                        WorkflowCurrentStepSnapshot.StatusEnum.fromValue(status),
                        stepId)
                .errorCode(errorCode);
    }

    public WorkflowCurrentStepSnapshot controlStep(
            String stepId,
            int ordinal,
            String purpose,
            String status,
            int attemptCount,
            long fencingToken,
            String errorCode) {
        return new WorkflowCurrentStepSnapshot(
                attemptCount,
                Math.toIntExact(fencingToken),
                WorkflowCurrentStepSnapshot.LaneEnum.CONTROL,
                null,
                null,
                ordinal,
                purpose,
                        null,
                        WorkflowCurrentStepSnapshot.StatusEnum.fromValue(status),
                        stepId)
                .errorCode(errorCode);
    }

    private WorkflowStepProgressSnapshot latestProgress(
            String serialized,
            String stepId,
            long fencingToken,
            String status,
            ModelProfileRef logical,
            ResolvedModelRef resolved) {
        if (!"running".equals(status) || serialized == null) return null;
        final StepProgressEventPayload progress;
        try {
            progress = json.readerFor(StepProgressEventPayload.class)
                    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                    .readValue(serialized);
        } catch (RuntimeException exception) {
            throw new IllegalStateException("WorkflowStep 最新进度事件损坏", exception);
        }
        if (!Objects.equals(stepId, progress.getStepId())) {
            throw new IllegalStateException("WorkflowStep 最新进度事件引用了其他 Step");
        }
        if (progress.getFencingToken() == null
                || progress.getFencingToken().longValue() != fencingToken) {
            // 租约换 fence 后，旧 fence 的最后一条进度不再代表当前执行尝试。
            return null;
        }
        if (progress.getProgressSequence() == null || progress.getProgressSequence() < 1) {
            throw new IllegalStateException("WorkflowStep 最新进度序号无效");
        }
        if (progress.getElapsedSeconds() == null || progress.getElapsedSeconds() < 0) {
            throw new IllegalStateException("WorkflowStep 最新进度耗时无效");
        }
        if (progress.getPhase() == null
                || progress.getUsageStatus() == null
                || progress.getWaitingOnProvider() == null) {
            throw new IllegalStateException("WorkflowStep 最新进度缺少必填字段");
        }
        boolean waiting = Boolean.TRUE.equals(progress.getWaitingOnProvider());
        boolean waitingPhase = progress.getPhase()
                == StepProgressEventPayload.PhaseEnum.WAITING_PROVIDER;
        if (waiting != waitingPhase) {
            throw new IllegalStateException("WorkflowStep 最新进度等待状态不一致");
        }
        if (!Objects.equals(logical, progress.getModelProfile())
                || resolved == null
                || !Objects.equals(resolved, progress.getResolvedModel())) {
            throw new IllegalStateException("WorkflowStep 最新进度的模型身份与当前 fence 不一致");
        }
        return new WorkflowStepProgressSnapshot(
                progress.getElapsedSeconds(),
                WorkflowStepProgressSnapshot.PhaseEnum.fromValue(
                        progress.getPhase().getValue()),
                progress.getProgressSequence(),
                WorkflowStepProgressSnapshot.UsageStatusEnum.fromValue(
                        progress.getUsageStatus().getValue()),
                progress.getWaitingOnProvider());
    }

    public ModelProfileRef logical(ExecutionPlanSnapshot.ModelProfile profile) {
        ExecutionPlanSnapshot.PromptProfile prompt = profile.promptProfile();
        return new ModelProfileRef(
                profile.deploymentProfileKey(),
                profile.profile(),
                new PromptProfileRef(prompt.name(), prompt.sha256(), prompt.version()),
                ModelProfileRef.ReasoningModeEnum.fromValue(profile.reasoningMode()),
                profile.version());
    }

    private ResolvedModelRef resolved(
            String value, ExecutionPlanSnapshot.ModelProfile logical) {
        if (value == null) return null;
        final ResolvedModelRef resolved;
        try {
            resolved = json.readValue(value, ResolvedModelRef.class);
        } catch (RuntimeException exception) {
            throw new IllegalStateException("WorkflowStep resolvedModel 损坏", exception);
        }
        new WorkflowResolvedModel(
                        resolved.getDeploymentProfileKey(),
                        resolved.getDeploymentFingerprint(),
                        resolved.getProvider(),
                        resolved.getModel(),
                        resolved.getTransportProfile(),
                        resolved.getEndpointProfile(),
                        resolved.getStructuredOutputRoute().getValue(),
                        resolved.getCapabilityVersion(),
                        resolved.getReasoningMode().getValue(),
                        resolved.getSupportsRequestIdempotency())
                .requireAuthorizedBy(logical.toDomain());
        return resolved;
    }
}
