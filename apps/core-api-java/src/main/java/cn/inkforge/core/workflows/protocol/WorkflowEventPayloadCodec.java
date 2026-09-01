package cn.inkforge.core.workflows.protocol;

import cn.inkforge.contracts.api.ApplyingEventPayload;
import cn.inkforge.contracts.api.AwaitingUserEventPayload;
import cn.inkforge.contracts.api.CancelledEventPayload;
import cn.inkforge.contracts.api.CandidateReadyEventPayload;
import cn.inkforge.contracts.api.ClarificationRequiredEventPayload;
import cn.inkforge.contracts.api.CompletedEventPayload;
import cn.inkforge.contracts.api.EvidenceReadyEventPayload;
import cn.inkforge.contracts.api.FailedEventPayload;
import cn.inkforge.contracts.api.IntentResolvedEventPayload;
import cn.inkforge.contracts.api.ReviewCompletedEventPayload;
import cn.inkforge.contracts.api.ReviewPendingStepSnapshot;
import cn.inkforge.contracts.api.ReviewStartedEventPayload;
import cn.inkforge.contracts.api.RunAcceptedEventPayload;
import cn.inkforge.contracts.api.StepProgressEventPayload;
import cn.inkforge.contracts.api.StepFinishedEventPayload;
import cn.inkforge.contracts.api.StepQueuedEventPayload;
import cn.inkforge.contracts.api.StepStartedEventPayload;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 按 eventType 使用机械生成的精确 DTO 解码并校验持久 WorkflowEvent payload。 */
public final class WorkflowEventPayloadCodec {

    private final ObjectMapper json;
    private final Validator validator;

    public WorkflowEventPayloadCodec(ObjectMapper json, Validator validator) {
        this.json = Objects.requireNonNull(json);
        this.validator = Objects.requireNonNull(validator);
    }

    public Object parse(String eventType, String serialized) {
        try {
            JsonNode raw = json.readTree(serialized);
            if (raw == null || !raw.isObject()) throw invalid();
            if ("step_finished".equals(eventType) && !raw.has("errorCode")) throw invalid();
            Class<?> payloadType = payloadType(eventType);
            Object payload = json.readerFor(payloadType)
                    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                    .readValue(raw);
            validateBean(payload);
            rejectScalarCoercion(raw, json.valueToTree(payload));
            validateInvariants(eventType, payload);
            return payload;
        } catch (JacksonException | ArithmeticException ignored) {
            // Jackson 解析异常可能带输入片段；稳定错误不保留 cause，避免日志泄露 payload。
            throw invalid();
        }
    }

    private static Class<?> payloadType(String eventType) {
        return switch (eventType) {
            case "run_accepted" -> RunAcceptedEventPayload.class;
            case "intent_resolved" -> IntentResolvedEventPayload.class;
            case "clarification_required" -> ClarificationRequiredEventPayload.class;
            case "evidence_ready" -> EvidenceReadyEventPayload.class;
            case "step_queued" -> StepQueuedEventPayload.class;
            case "step_started" -> StepStartedEventPayload.class;
            case "step_progress" -> StepProgressEventPayload.class;
            case "step_finished" -> StepFinishedEventPayload.class;
            case "candidate_ready" -> CandidateReadyEventPayload.class;
            case "review_started" -> ReviewStartedEventPayload.class;
            case "review_completed" -> ReviewCompletedEventPayload.class;
            case "awaiting_user" -> AwaitingUserEventPayload.class;
            case "applying" -> ApplyingEventPayload.class;
            case "completed" -> CompletedEventPayload.class;
            case "failed" -> FailedEventPayload.class;
            case "cancelled" -> CancelledEventPayload.class;
            default -> throw invalid();
        };
    }

    private <T> void validateBean(T payload) {
        Set<ConstraintViolation<T>> violations = validator.validate(payload);
        if (!violations.isEmpty()) throw invalid();
    }

    /**
     * Jackson 默认允许部分标量强制转换。逐字段比较原树与生成 DTO 的回写树，既保留可选字段省略，
     * 又拒绝把数字悄悄转成字符串、把字符串转成布尔值等协议漂移。
     */
    private static void rejectScalarCoercion(JsonNode raw, JsonNode parsed) {
        for (String field : raw.propertyNames()) {
            if (!Objects.equals(raw.get(field), parsed.get(field))) throw invalid();
        }
    }

    private static void validateInvariants(String eventType, Object payload) {
        switch (eventType) {
            case "run_accepted" -> {
                RunAcceptedEventPayload value = (RunAcceptedEventPayload) payload;
                positive(value.getRunRevision());
                if ((value.getTargetType() == null) != (value.getTargetId() == null)) {
                    throw invalid();
                }
            }
            case "intent_resolved" -> {
                // 数值范围和全部资源标识由生成 DTO 的 Bean Validation 约束。
            }
            case "clarification_required" -> {
                ClarificationRequiredEventPayload value =
                        (ClarificationRequiredEventPayload) payload;
                if (value.getPrompt().isBlank()) throw invalid();
            }
            case "evidence_ready" -> {
                EvidenceReadyEventPayload value = (EvidenceReadyEventPayload) payload;
                positive(value.getBundleVersion());
                nonNegative(value.getTotalBytes());
            }
            case "step_queued" -> {
                StepQueuedEventPayload value = (StepQueuedEventPayload) payload;
                positive(value.getOrdinal());
                positive(value.getAttemptCount());
                positive(value.getFencingToken());
            }
            case "step_started" -> {
                StepStartedEventPayload value = (StepStartedEventPayload) payload;
                positive(value.getOrdinal());
                positive(value.getAttemptCount());
                positive(value.getFencingToken());
            }
            case "step_progress" -> {
                StepProgressEventPayload value = (StepProgressEventPayload) payload;
                positive(value.getFencingToken());
                positive(value.getProgressSequence());
                nonNegative(value.getElapsedSeconds());
                boolean waiting = Boolean.TRUE.equals(value.getWaitingOnProvider());
                boolean waitingPhase =
                        value.getPhase() == StepProgressEventPayload.PhaseEnum.WAITING_PROVIDER;
                if (waiting != waitingPhase) throw invalid();
            }
            case "step_finished" -> {
                StepFinishedEventPayload value = (StepFinishedEventPayload) payload;
                positive(value.getFencingToken());
                boolean failed = value.getStatus() == StepFinishedEventPayload.StatusEnum.FAILED;
                if (failed != (value.getErrorCode() != null && !value.getErrorCode().isBlank())) {
                    throw invalid();
                }
            }
            case "candidate_ready" -> positive(
                    ((CandidateReadyEventPayload) payload).getArtifactRevision());
            case "review_started" -> {
                ReviewStartedEventPayload value = (ReviewStartedEventPayload) payload;
                positive(value.getArtifactRevision());
                validateReviewerSteps(value.getReviewerSteps());
            }
            case "review_completed" -> {
                ReviewCompletedEventPayload value = (ReviewCompletedEventPayload) payload;
                positive(value.getArtifactRevision());
                unique(value.getEvaluationIds());
                if (value.getReviewAvailability()
                                == ReviewCompletedEventPayload.ReviewAvailabilityEnum.UNAVAILABLE
                        && value.getMergedVerdict()
                                != ReviewCompletedEventPayload.MergedVerdictEnum.CANNOT_ASSESS) {
                    throw invalid();
                }
            }
            case "awaiting_user" -> {
                AwaitingUserEventPayload value = (AwaitingUserEventPayload) payload;
                positive(value.getArtifactRevision());
                unique(value.getAllowedDecisions());
            }
            case "applying" -> positive(
                    ((ApplyingEventPayload) payload).getArtifactRevision());
            case "completed" -> {
                CompletedEventPayload value = (CompletedEventPayload) payload;
                if ((value.getArtifactId() == null) != (value.getArtifactRevision() == null)) {
                    throw invalid();
                }
                if (value.getArtifactRevision() != null) positive(value.getArtifactRevision());
            }
            case "failed", "cancelled" -> {
                // 其余字段由生成 DTO 的枚举、pattern、required 和 additionalProperties 约束。
            }
            default -> throw invalid();
        }
    }

    private static void positive(Integer value) {
        if (value == null || value < 1) throw invalid();
    }

    private static void nonNegative(Integer value) {
        if (value == null || value < 0) throw invalid();
    }

    private static void unique(List<?> values) {
        if (values == null || values.isEmpty() || new HashSet<>(values).size() != values.size()) {
            throw invalid();
        }
    }

    private static void validateReviewerSteps(List<ReviewPendingStepSnapshot> values) {
        if (values == null || values.isEmpty()) throw invalid();
        Set<String> stepIds = new HashSet<>();
        Set<Integer> ordinals = new HashSet<>();
        String previousId = null;
        int previousOrdinal = -1;
        for (ReviewPendingStepSnapshot value : values) {
            if (value == null
                    || value.getStepId() == null
                    || value.getOrdinal() == null
                    || value.getOrdinal() < 1
                    || !"review".equals(value.getPurpose())
                    || !"pending".equals(value.getStatus())
                    || !Objects.equals(value.getAttemptCount(), 0)
                    || !Objects.equals(value.getFencingToken(), 0)
                    || value.getLane() == null
                    || value.getModelProfile() == null
                    || !stepIds.add(value.getStepId())
                    || !ordinals.add(value.getOrdinal())) {
                throw invalid();
            }
            if (value.getOrdinal() < previousOrdinal
                    || (value.getOrdinal() == previousOrdinal
                            && value.getStepId().compareTo(previousId) < 0)) {
                throw invalid();
            }
            previousOrdinal = value.getOrdinal();
            previousId = value.getStepId();
        }
    }

    private static IllegalStateException invalid() {
        return new IllegalStateException("持久 WorkflowEvent payload 不符合共享契约");
    }
}
