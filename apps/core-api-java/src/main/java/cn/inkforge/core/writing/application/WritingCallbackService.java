package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.AgentEvent;
import cn.inkforge.contracts.api.CallbackReceipt;
import cn.inkforge.contracts.api.CheckpointCallback;
import cn.inkforge.contracts.api.RunCompletionCallback;
import cn.inkforge.contracts.api.RunFailureCallback;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.writing.domain.WritingBoundaryEvent;
import cn.inkforge.core.writing.domain.WritingCallbackAcceptance;
import cn.inkforge.core.writing.domain.WritingEventSequenceGap;
import cn.inkforge.core.writing.domain.WritingEventSourceConflict;
import cn.inkforge.core.writing.domain.WritingGraphSnapshot;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import tools.jackson.databind.ObjectMapper;

/**
 * 校验 Agent 回调并协调 PostgreSQL 耐久事实与 Redis 短期事件流。
 *
 * <p>仓储先授权并落库序号、检查点、终态及 outbox 边界；Redis 事件随后发布，发布失败不回滚已经提交的业务事实，
 * 由 outbox/replay 补齐。eventId、序号与完整事件内容共同定义幂等，不能只按序号吞掉不同回调。
 */
public final class WritingCallbackService {

    private static final Logger LOGGER = LoggerFactory.getLogger(WritingCallbackService.class);
    private static final Set<String> SHORT_OPERATIONS = Set.of(
            "generate_outline", "generate_manuscript", "replace_selection", "full_check");

    private final WritingCallbackRepository repository;
    private final WritingEventStore events;
    private final ObjectMapper json;

    public WritingCallbackService(
            WritingCallbackRepository repository,
            WritingEventStore events,
            ObjectMapper json) {
        this.repository = Objects.requireNonNull(repository);
        this.events = Objects.requireNonNull(events);
        this.json = Objects.requireNonNull(json);
    }

    public CallbackReceipt acceptEvent(AgentEvent body) {
        requireCallback(body.getProtocolVersion(), body.getSequence());
        Preparation preparation = prepare(
                body.getTaskId(),
                body.getJobId(),
                body.getEventId(),
                body.getSequence(),
                body.getEvent(),
                body.getData(),
                false,
                true,
                false);
        if (!preparation.shouldContinue()) return receipt(preparation.acceptance());
        WritingCallbackAcceptance acceptance = repository.markProcessing(
                body.getTaskId(), body.getJobId(), body.getSequence());
        if (!acceptance.accepted()) {
            log(acceptance, body.getTaskId(), body.getJobId(), body.getEventId());
            return receipt(acceptance);
        }
        if (preparation.shouldPublish()) {
            try {
                append(
                        body.getTaskId(),
                        body.getEventId(),
                        body.getSequence(),
                        body.getEvent(),
                        body.getData(),
                        preparation.durableBaseline());
            } catch (WritingEventSourceConflict exception) {
                return receipt(reject(acceptance, "WRITING_EVENT_SOURCE_CONFLICT"));
            }
        }
        return receipt(acceptance);
    }

    public CallbackReceipt saveCheckpoint(
            CheckpointCallback body, String userId, String novelId) {
        requireCallback(body.getProtocolVersion(), body.getSequence());
        Map<String, Object> checkpoint = new LinkedHashMap<>(body.getCheckpoint());
        checkpoint.put("callbackJobId", body.getJobId());
        boolean shortMedium = "short_medium".equals(checkpoint.get("workflow"));
        if (shortMedium) {
            if (!SHORT_OPERATIONS.contains(checkpoint.get("operation"))
                    || !Set.of("generating", "completed").contains(checkpoint.get("phase"))) {
                throw new ApiException(
                        409, "WRITING_SNAPSHOT_INVALID", "中短篇检查点格式无效");
            }
        } else {
            try {
                WritingGraphSnapshot.parse(
                        json.writeValueAsString(checkpoint),
                        json,
                        body.getTaskId(),
                        userId,
                        novelId,
                        null);
            } catch (IllegalArgumentException exception) {
                throw new ApiException(
                        409, "WRITING_SNAPSHOT_INVALID", exception.getMessage());
            }
        }
        int checkpointSequence = checkpointSequence(checkpoint);
        if (checkpointSequence != body.getSequence()) {
            throw new ApiException(
                    409,
                    "WRITING_CHECKPOINT_SEQUENCE_MISMATCH",
                    "检查点事件序号与回调序号不一致");
        }
        String phase = checkpoint.get("phase") instanceof String text ? text : "active";
        String persistedPhase = shortMedium ? "active" : phase;
        String serialized = json.writeValueAsString(checkpoint);
        WritingBoundaryEvent boundary = null;
        if (!shortMedium && "awaiting_user_review".equals(persistedPhase)) {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("taskId", body.getTaskId());
            Object artifactId = checkpoint.get("activeArtifactId");
            if (artifactId instanceof String id && !id.isEmpty()) {
                payload.put("artifactId", id);
                Object activeAgent = checkpoint.get("activeAgent");
                payload.put(
                        "agentId",
                        activeAgent instanceof String agent && !agent.isEmpty()
                                ? agent
                                : "系统");
            }
            boundary = new WritingBoundaryEvent(
                    body.getEventId(),
                    body.getSequence(),
                    "writing:"
                            + body.getJobId()
                            + ":waiting:"
                            + body.getSequence(),
                    "artifact_awaiting_user_approval",
                    payload);
        }
        if (boundary != null) {
            // “等待用户”是业务边界：检查点和通知必须同事务进入 PostgreSQL，不能先发 Redis 再补状态。
            WritingCallbackAcceptance acceptance = repository.saveCheckpoint(
                    body.getTaskId(),
                    body.getJobId(),
                    serialized,
                    persistedPhase,
                    body.getSequence(),
                    boundary);
            if (!acceptance.accepted()) {
                log(acceptance, body.getTaskId(), body.getJobId(), body.getEventId());
            }
            return receipt(acceptance);
        }
        Map<String, Object> eventData = new LinkedHashMap<>();
        eventData.put("phase", checkpoint.get("phase"));
        Preparation preparation = prepare(
                body.getTaskId(),
                body.getJobId(),
                body.getEventId(),
                body.getSequence(),
                "checkpoint",
                eventData,
                true,
                false,
                true);
        if (!preparation.shouldContinue()) return receipt(preparation.acceptance());
        WritingCallbackAcceptance acceptance = repository.saveCheckpoint(
                body.getTaskId(),
                body.getJobId(),
                serialized,
                persistedPhase,
                body.getSequence(),
                null);
        if (!acceptance.accepted()) {
            log(acceptance, body.getTaskId(), body.getJobId(), body.getEventId());
            return receipt(acceptance);
        }
        if (preparation.shouldPublish()) {
            try {
                append(
                        body.getTaskId(),
                        body.getEventId(),
                        body.getSequence(),
                        "checkpoint",
                        eventData,
                        preparation.durableBaseline());
            } catch (WritingEventSourceConflict exception) {
                return receipt(reject(acceptance, "WRITING_EVENT_SOURCE_CONFLICT"));
            }
        }
        return receipt(acceptance);
    }

    public CallbackReceipt complete(RunCompletionCallback body) {
        requireCallback(body.getProtocolVersion(), body.getSequence());
        validateShortResultDiscriminator(body.getResult());
        Object response = body.getResult().get("finalResponse");
        String visible = response instanceof String text ? text.strip() : "";
        WritingBoundaryEvent boundary = new WritingBoundaryEvent(
                body.getEventId(),
                body.getSequence(),
                "writing:" + body.getJobId() + ":terminal",
                "completed",
                Map.of(
                        "taskId", body.getTaskId(),
                        "resultSha256", resultDigest(body.getResult())));
        WritingCallbackAcceptance acceptance = repository.complete(
                body.getTaskId(),
                body.getJobId(),
                body.getResult(),
                visible,
                body.getSequence(),
                boundary);
        if (!acceptance.accepted()) {
            log(acceptance, body.getTaskId(), body.getJobId(), body.getEventId());
        }
        return receipt(acceptance);
    }

    public CallbackReceipt fail(RunFailureCallback body) {
        requireCallback(body.getProtocolVersion(), body.getSequence());
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("message", "智能体运行失败");
        payload.put("code", body.getCode());
        payload.put("recoverable", body.getRecoverable());
        WritingBoundaryEvent boundary = new WritingBoundaryEvent(
                body.getEventId(),
                body.getSequence(),
                "writing:" + body.getJobId() + ":terminal",
                "error",
                payload);
        WritingCallbackAcceptance acceptance = repository.fail(
                body.getTaskId(),
                body.getJobId(),
                body.getCode(),
                body.getSequence(),
                boundary);
        if (!acceptance.accepted()) {
            log(acceptance, body.getTaskId(), body.getJobId(), body.getEventId());
        }
        return receipt(acceptance);
    }

    private Preparation prepare(
            String taskId,
            String jobId,
            String eventId,
            int sequence,
            String event,
            Map<String, Object> data,
            boolean allowPersistedEqual,
            boolean ignoreAlreadyApplied,
            boolean continueOnDuplicate) {
        WritingCallbackAcceptance authorization = repository.authorize(taskId, jobId);
        if (!authorization.accepted()) {
            WritingCallbackAcceptance rejection = reject(
                    authorization,
                    authorization.rejectionCode() == null
                            ? "WRITING_JOB_MISMATCH"
                            : authorization.rejectionCode());
            log(rejection, taskId, jobId, eventId);
            return new Preparation(false, false, authorization.persistedSequence(), rejection);
        }
        // 先校验源事件身份，再比较数据库序号；同 eventId 不同内容始终是冲突而非重复。
        boolean sourceUnseen;
        try {
            sourceUnseen = events.validateSource(
                    taskId, eventId, sequence, event, data);
        } catch (WritingEventSourceConflict exception) {
            WritingCallbackAcceptance rejection = reject(
                    authorization, "WRITING_EVENT_SOURCE_CONFLICT");
            log(rejection, taskId, jobId, eventId);
            return new Preparation(false, false, authorization.persistedSequence(), rejection);
        }
        if (!sourceUnseen && !continueOnDuplicate) {
            return new Preparation(
                    false,
                    false,
                    authorization.persistedSequence(),
                    withAlreadyApplied(authorization));
        }
        if (ignoreAlreadyApplied && authorization.alreadyApplied()) {
            logCode("WRITING_CALLBACK_ALREADY_APPLIED", taskId, jobId, eventId);
            return new Preparation(
                    false, false, authorization.persistedSequence(), authorization);
        }
        if (sequence < authorization.persistedSequence()) {
            WritingCallbackAcceptance rejection = reject(
                    authorization, "WRITING_CALLBACK_SEQUENCE_STALE");
            log(rejection, taskId, jobId, eventId);
            return new Preparation(false, false, authorization.persistedSequence(), rejection);
        }
        int durableBaseline;
        if (sequence == authorization.persistedSequence()) {
            // 只有检查点允许“同序号、同快照”重放；普通事件同序号必须按陈旧回调拒绝。
            if (!allowPersistedEqual) {
                WritingCallbackAcceptance rejection = reject(
                        authorization, "WRITING_CALLBACK_SEQUENCE_STALE");
                log(rejection, taskId, jobId, eventId);
                return new Preparation(
                        false, false, authorization.persistedSequence(), rejection);
            }
            durableBaseline = Math.max(0, sequence - 1);
        } else {
            durableBaseline = authorization.persistedSequence();
        }
        boolean shouldPublish;
        try {
            shouldPublish = events.validate(
                    taskId,
                    eventId,
                    sequence,
                    event,
                    data,
                    durableBaseline,
                    true);
        } catch (WritingEventSourceConflict exception) {
            WritingCallbackAcceptance rejection = reject(
                    authorization, "WRITING_EVENT_SOURCE_CONFLICT");
            log(rejection, taskId, jobId, eventId);
            return new Preparation(false, false, durableBaseline, rejection);
        } catch (WritingEventSequenceGap exception) {
            throw gap(exception);
        }
        if (!shouldPublish && !continueOnDuplicate) {
            return new Preparation(
                    false,
                    false,
                    durableBaseline,
                    withAlreadyApplied(authorization));
        }
        return new Preparation(true, shouldPublish, durableBaseline, authorization);
    }

    private void append(
            String taskId,
            String eventId,
            int sequence,
            String event,
            Map<String, Object> data,
            int durableBaseline) {
        try {
            events.appendAgent(
                    taskId,
                    eventId,
                    sequence,
                    event,
                    data,
                    durableBaseline,
                    true);
        } catch (WritingEventSequenceGap exception) {
            throw gap(exception);
        }
    }

    private static int checkpointSequence(Map<String, Object> checkpoint) {
        Object value = checkpoint.get("eventSequence");
        if (!(value instanceof Number number)
                || value instanceof Double
                || value instanceof Float
                || number.longValue() < 0
                || number.longValue() > Integer.MAX_VALUE) {
            throw new ApiException(
                    409,
                    "WRITING_CHECKPOINT_SEQUENCE_INVALID",
                    "检查点缺少有效事件序号");
        }
        return number.intValue();
    }

    private static void requireCallback(String protocolVersion, Integer sequence) {
        if (!"1.1".equals(protocolVersion) || sequence == null || sequence < 1) {
            throw new ApiException(422, "VALIDATION_ERROR", "写作回调协议或序号无效");
        }
    }

    private static void validateShortResultDiscriminator(Map<String, Object> result) {
        Object resultType = result.get("resultType");
        Object operation = result.get("operation");
        if (resultType == null
                        && operation instanceof String operationName
                        && SHORT_OPERATIONS.contains(operationName)
                || resultType instanceof String text
                        && text.startsWith("short_medium_")
                        && !Set.of(
                                        "short_medium_document",
                                        "short_medium_replacement",
                                        "short_medium_check")
                                .contains(text)) {
            throw new ApiException(422, "VALIDATION_ERROR", "中短篇完成结果类型无效");
        }
    }

    private String resultDigest(Map<String, Object> result) {
        return CommandIdempotency.sha256(
                CommandIdempotency.canonicalJsonBytes(result, json));
    }

    private static CallbackReceipt receipt(WritingCallbackAcceptance acceptance) {
        CallbackReceipt.DispositionEnum disposition;
        String reason;
        if (acceptance.accepted() && acceptance.alreadyApplied()) {
            disposition = CallbackReceipt.DispositionEnum.ALREADY_APPLIED;
            reason = "WRITING_CALLBACK_ALREADY_APPLIED";
        } else if (acceptance.accepted()) {
            disposition = CallbackReceipt.DispositionEnum.APPLIED;
            reason = "WRITING_CALLBACK_APPLIED";
        } else {
            disposition = CallbackReceipt.DispositionEnum.REJECTED;
            reason = acceptance.rejectionCode() == null
                    ? "WRITING_CALLBACK_STATE_NOOP"
                    : acceptance.rejectionCode();
        }
        CallbackReceipt result = new CallbackReceipt(
                acceptance.commandStatus() == null
                        ? null
                        : CallbackReceipt.CommandStatusEnum.fromValue(
                                acceptance.commandStatus()),
                disposition,
                "1.0",
                reason,
                false,
                acceptance.taskPhase() == null ? "unknown" : acceptance.taskPhase());
        result.setOutboxEventId(acceptance.outboxEventId());
        return result;
    }

    private static WritingCallbackAcceptance reject(
            WritingCallbackAcceptance value, String code) {
        return new WritingCallbackAcceptance(
                false,
                value.persistedSequence(),
                false,
                code,
                value.taskPhase(),
                value.commandStatus(),
                value.outboxEventId());
    }

    private static WritingCallbackAcceptance withAlreadyApplied(
            WritingCallbackAcceptance value) {
        return new WritingCallbackAcceptance(
                value.accepted(),
                value.persistedSequence(),
                true,
                value.rejectionCode(),
                value.taskPhase(),
                value.commandStatus(),
                value.outboxEventId());
    }

    private static ApiException gap(WritingEventSequenceGap exception) {
        return new ApiException(
                409,
                "AGENT_EVENT_SEQUENCE_GAP",
                "智能体事件序号不连续，需要状态对账",
                Map.of(
                        "expectedSequence", exception.expectedSequence(),
                        "receivedSequence", exception.receivedSequence(),
                        "recoverable", true));
    }

    private static void log(
            WritingCallbackAcceptance acceptance,
            String taskId,
            String jobId,
            String eventId) {
        logCode(
                acceptance.rejectionCode() == null
                        ? "WRITING_CALLBACK_STATE_NOOP"
                        : acceptance.rejectionCode(),
                taskId,
                jobId,
                eventId);
    }

    private static void logCode(
            String code, String taskId, String jobId, String eventId) {
        LOGGER.warn("{} task_id={} job_id={} event_id={}", code, taskId, jobId, eventId);
    }

    private record Preparation(
            boolean shouldContinue,
            boolean shouldPublish,
            int durableBaseline,
            WritingCallbackAcceptance acceptance) {}
}
