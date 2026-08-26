package cn.inkforge.core.writing.domain;

import cn.inkforge.contracts.api.WritingRunCheckpointResponse;
import cn.inkforge.contracts.api.WritingRunOutcome;
import cn.inkforge.contracts.api.WritingRunOutcomeResult;
import cn.inkforge.contracts.api.WritingRunStatusResponse;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.WritingruncommandRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 从 PostgreSQL 中的任务、命令和审核产物投影统一写作状态。
 *
 * <p>投影只信任相互印证的耐久身份，不根据阶段名称猜测候选草案，也不会把损坏 JSON 当成成功结果。
 * 最早的 start 命令提供不可变工作流来源，最新命令提供当前控制状态；若最新命令是无效取消，则沿取消链
 * 找回被取消前的有效命令。任何链路冲突都会把 {@code ready} 降为 false，而不是向前端暴露可操作结果。
 */
public final class WritingRunStatusProjector {

    private static final String TERMINAL_CALLBACK_RESULT = "_inkforgeTerminalCallbackResult";
    private static final Set<String> PUBLIC_OPERATIONS = Set.of(
            "generate_outline",
            "generate_manuscript",
            "replace_selection",
            "full_check",
            "plan_chapter",
            "rewrite_scene",
            "rewrite_chapter_selection",
            "rewrite_outline_selection",
            "write_chapter",
            "review_chapter");
    private static final Map<String, String> LONG_ARTIFACT_KINDS = Map.of(
            "plan_chapter", "beat_plan",
            "rewrite_scene", "chapter_draft",
            "rewrite_chapter_selection", "chapter_draft",
            "rewrite_outline_selection", "outline_draft",
            "write_chapter", "chapter_draft");
    private static final Set<String> ACTIVE_OUTCOMES = Set.of("queued", "running", "waiting_user");

    private final ObjectMapper json;
    private final WritingRunOutcomeProjector outcomes;
    private final Clock clock;

    public WritingRunStatusProjector(
            ObjectMapper json, WritingRunOutcomeProjector outcomes, Clock clock) {
        this.json = Objects.requireNonNull(json);
        this.outcomes = Objects.requireNonNull(outcomes);
        this.clock = Objects.requireNonNull(clock);
    }

    public WritingRunStatusResponse project(
            WritingtaskRecord task,
            List<WritingruncommandRecord> commandValues,
            List<ReviewartifactRecord> artifactValues) {
        Objects.requireNonNull(task);
        // 相同毫秒内以 ID 打破平局，保证重放、分页和取消链在不同 JVM 上选择同一条命令。
        List<WritingruncommandRecord> commands = new ArrayList<>(commandValues);
        commands.sort(Comparator.comparing(
                        WritingruncommandRecord::getCreatedat,
                        Comparator.nullsFirst(Comparator.naturalOrder()))
                .thenComparing(WritingruncommandRecord::getId)
                .reversed());
        List<ReviewartifactRecord> artifacts = new ArrayList<>(artifactValues);
        artifacts.sort(Comparator.comparing(
                        ReviewartifactRecord::getCreatedat,
                        Comparator.nullsFirst(Comparator.naturalOrder()))
                .thenComparing(ReviewartifactRecord::getId)
                .reversed());

        WritingruncommandRecord current = commands.isEmpty() ? null : commands.getFirst();
        // start 提供冻结 operation/target/scope；恢复或决定命令只能改变控制状态，不能重定义原任务身份。
        WritingruncommandRecord start = null;
        for (int index = commands.size() - 1; index >= 0; index--) {
            if ("start".equals(commands.get(index).getKind())) {
                start = commands.get(index);
                break;
            }
        }
        if (start == null) start = current;
        Map<String, Object> startPayload = commandJob(start);
        Map<String, Object> snapshot = object(task.getGraphstatejson());
        String workflow = "short_medium".equals(startPayload.get("workflow"))
                        || "short_medium".equals(snapshot.get("workflow"))
                ? "short_medium"
                : "long_serial";
        Object operationValue = startPayload.get("operation");
        if (operationValue == null) {
            if ("short_medium".equals(workflow)) {
                operationValue = snapshot.get("operation");
            } else if (snapshot.get("currentOperation") instanceof Map<?, ?> classifiedOperation) {
                // 自然语言入口的操作身份由受信 Agent 回调分类并持久化在任务快照中。
                operationValue = classifiedOperation.get("kind");
            }
        }
        String operation = operationValue instanceof String value && PUBLIC_OPERATIONS.contains(value)
                ? value
                : null;
        Map<String, Object> target = objectOrDefault(
                startPayload.get("target"), Map.of("type", "chapter", "id", task.getChapterid()));
        Map<String, Object> scope = objectOrDefault(
                startPayload.get("scope"),
                Map.of("kind", "chapter", "chapterId", task.getChapterid()));
        WritingRunCheckpointResponse checkpoint = checkpoint(task.getGraphstatejson());

        // 无效取消要沿 priorOutcome 回到被取消前事实；当前命令仍保留在响应中供用户理解最近动作。
        EffectiveCommand resolved = resolveEffective(current, commands);
        WritingruncommandRecord effective = resolved.command();
        String resultKind = "none";
        String resultId = null;
        boolean resultReady = false;
        String activeArtifactId = null;
        String reviewReport = null;
        String candidateVersionId = null;
        Map<String, Object> checkReport = null;
        Map<String, Object> effectiveResult = fullResult(effective);

        // resultReady 不是“字段存在”：候选、命令、任务和 Artifact 归属必须全部相互印证。
        if ("short_medium".equals(workflow)) {
            Object candidateValue = effectiveResult.get("candidateVersionId");
            candidateVersionId = candidateValue instanceof String value ? value : null;
            if (operation != null
                    && Set.of("generate_outline", "generate_manuscript", "replace_selection")
                            .contains(operation)) {
                resultKind = "short_candidate";
                resultId = candidateVersionId;
                ReviewartifactRecord candidate = artifactById(artifacts, candidateVersionId);
                resultReady = shortCandidateReady(
                        task, effective, startPayload, candidateVersionId, candidate);
            } else if ("full_check".equals(operation)) {
                resultKind = "check_report";
                resultId = effective == null ? null : effective.getId();
                Object report = effectiveResult.get("checkReport");
                if (report instanceof Map<?, ?> map) {
                    checkReport = stringMap(map);
                    resultReady = checkReport != null;
                }
            }
        } else if (operation != null && LONG_ARTIFACT_KINDS.containsKey(operation)) {
            String expectedKind = LONG_ARTIFACT_KINDS.get(operation);
            String decisionArtifactId = decisionArtifactId(effective);
            ReviewartifactRecord persistedDecisionArtifact =
                    artifactById(artifacts, decisionArtifactId);
            String hint = decisionArtifactId != null
                    ? decisionArtifactId
                    : snapshotActiveArtifactId(task.getGraphstatejson());
            ReviewartifactRecord artifact = longArtifact(
                    task, artifacts, expectedKind, hint);
            resultKind = "review_artifact";
            resultId = artifact == null ? decisionArtifactId : artifact.getId();
            if (artifact != null && awaitingArtifactReady(task, effective, artifact)) {
                activeArtifactId = artifact.getId();
                resultReady = true;
            } else if (appliedArtifactReady(task, effective, artifact)) {
                resultReady = true;
            } else if (task.getPhase().getLiteral().equals("completed")
                    && persistedDecisionArtifact == null
                    && discardDecisionReady(effective, task, resultId)) {
                resultReady = true;
            }
        } else if ("review_chapter".equals(operation)) {
            resultKind = "final_message";
            Object callback = effectiveResult.get(TERMINAL_CALLBACK_RESULT);
            Object report = callback instanceof Map<?, ?> map ? map.get("finalResponse") : null;
            if (effective != null
                    && "succeeded".equals(effective.getStatus())
                    && task.getPhase().getLiteral().equals("completed")
                    && report instanceof String text
                    && !text.isBlank()) {
                reviewReport = text;
                resultReady = true;
            }
        } else {
            String activeId = snapshotActiveArtifactId(task.getGraphstatejson());
            ReviewartifactRecord artifact = artifactById(artifacts, activeId);
            if (activeId != null) {
                resultKind = "review_artifact";
                resultId = activeId;
                resultReady = artifact != null && authoritative(task, artifact, "awaiting_user");
                if (resultReady) activeArtifactId = activeId;
            }
        }

        OffsetDateTime observedAt = OffsetDateTime.now(clock);
        WritingRunOutcome outcome = outcomes.project(
                new WritingRunOutcomeFacts(
                        task.getPhase().getLiteral(),
                        DatabaseTimestamp.api(task.getUpdatedat()),
                        "short_medium".equals(workflow) ? "short_medium" : "long_form",
                        current == null ? null : current.getId(),
                        current == null ? null : logicalKind(current),
                        current == null ? null : current.getStatus(),
                        current == null ? null : DatabaseTimestamp.api(current.getUpdatedat()),
                        operation,
                        resultKind,
                        resultId,
                        resultReady,
                        effective == null ? null : effective.getStatus(),
                        resolved.cancelEffective(),
                        resolved.chainValid()),
                observedAt);
        if ("long_serial".equals(workflow)
                && operation != null
                && Set.of(
                                "plan_chapter",
                                "rewrite_scene",
                                "rewrite_chapter_selection",
                                "rewrite_outline_selection",
                                "write_chapter",
                                "review_chapter")
                        .contains(operation)
                && task.getPhase().getLiteral().equals("completed")
                && outcome.getState() == WritingRunOutcome.StateEnum.SUCCEEDED
                && !resultReady) {
            // 长篇写操作没有权威草案/报告时，即使命令和任务都成功也不能对外宣称可用。
            outcome.setState(WritingRunOutcome.StateEnum.INCONSISTENT);
            outcome.setCode("LONG_SERIAL_RESULT_MISSING");
            outcome.setStreamShouldClose(true);
            outcome.setReconciliationRequired(true);
            WritingRunOutcomeResult original = outcome.getResult();
            outcome.setResult(new WritingRunOutcomeResult(original.getKind(), false)
                    .id(original.getId()));
        }

        Map<String, Object> error = commandError(effective, effectiveResult);
        boolean recoverable = ACTIVE_OUTCOMES.contains(outcome.getState().getValue())
                && WritingRecoverability.resolve(task, commands, json) != null;
        WritingRunStatusResponse response = new WritingRunStatusResponse();
        response.setTaskId(task.getId());
        response.setNovelId(task.getNovelid());
        response.setChapterId(task.getChapterid());
        response.setWritingSessionId(task.getWritingsessionid());
        response.setWorkflow(WritingRunStatusResponse.WorkflowEnum.fromValue(workflow));
        response.setOperation(operation == null
                ? null
                : WritingRunStatusResponse.OperationEnum.fromValue(operation));
        response.setTarget(target);
        response.setScope(scope);
        response.setPhase(task.getPhase().getLiteral());
        response.setCheckpoint(checkpoint);
        response.setActiveArtifactId(activeArtifactId);
        response.setRecoverable(recoverable);
        response.setReviewReport(reviewReport);
        response.setCreatedAt(DatabaseTimestamp.api(task.getCreatedat()));
        response.setUpdatedAt(DatabaseTimestamp.api(task.getUpdatedat()));
        response.setCommandId(current == null ? null : current.getId());
        response.setCommandStatus(current == null
                ? null
                : WritingRunStatusResponse.CommandStatusEnum.fromValue(current.getStatus()));
        response.setCandidateVersionId(candidateVersionId);
        response.setCheckReport(checkReport);
        response.setError(error);
        response.setOutcome(outcome);
        return response;
    }

    private EffectiveCommand resolveEffective(
            WritingruncommandRecord current, List<WritingruncommandRecord> commands) {
        if (current == null
                || !"cancel".equals(logicalKind(current))
                || !"succeeded".equals(current.getStatus())) {
            return new EffectiveCommand(current, null, true);
        }
        Map<String, Object> result = fullResult(current);
        Object effectiveValue = result.get("effective");
        if (Boolean.TRUE.equals(effectiveValue)) {
            return new EffectiveCommand(current, true, true);
        }
        if (!Boolean.FALSE.equals(effectiveValue)) {
            return new EffectiveCommand(current, false, false);
        }
        Map<String, WritingruncommandRecord> byId = new HashMap<>();
        commands.forEach(command -> byId.put(command.getId(), command));
        Set<String> seen = new HashSet<>();
        seen.add(current.getId());
        WritingruncommandRecord candidate = current;
        // priorOutcome 只接受同一任务中的已知命令，并用 seen 拒绝损坏数据形成的取消环。
        while ("cancel".equals(logicalKind(candidate))) {
            if ("failed".equals(candidate.getStatus())) {
                return new EffectiveCommand(candidate, false, true);
            }
            if (!"succeeded".equals(candidate.getStatus())) {
                return new EffectiveCommand(current, false, false);
            }
            Map<String, Object> candidateResult = fullResult(candidate);
            Object candidateEffective = candidateResult.get("effective");
            if (Boolean.TRUE.equals(candidateEffective)) {
                return new EffectiveCommand(candidate, true, true);
            }
            if (!Boolean.FALSE.equals(candidateEffective)) {
                return new EffectiveCommand(current, false, false);
            }
            Object prior = candidateResult.get("priorOutcome");
            Object priorCommand = prior instanceof Map<?, ?> map ? map.get("currentCommand") : null;
            Object priorId = priorCommand instanceof Map<?, ?> map ? map.get("id") : null;
            if (!(priorId instanceof String id) || !seen.add(id)) {
                return new EffectiveCommand(current, false, false);
            }
            WritingruncommandRecord previous = byId.get(id);
            if (previous == null || !Objects.equals(previous.getTaskid(), current.getTaskid())) {
                return new EffectiveCommand(current, false, false);
            }
            candidate = previous;
        }
        return new EffectiveCommand(candidate, false, true);
    }

    private WritingRunCheckpointResponse checkpoint(String serialized) {
        Map<String, Object> snapshot = object(serialized);
        Object sequence = snapshot.get("eventSequence");
        Object phase = snapshot.get("phase");
        if (!(sequence instanceof Number number)
                || sequence instanceof Double
                || sequence instanceof Float
                || !(phase instanceof String phaseValue)) {
            return null;
        }
        Object stage = snapshot.get("operationStage");
        Object step = snapshot.get("operationStep");
        return new WritingRunCheckpointResponse(
                number.intValue(),
                stage instanceof String text ? text : null,
                step instanceof String text ? text : null,
                phaseValue);
    }

    private boolean shortCandidateReady(
            WritingtaskRecord task,
            WritingruncommandRecord command,
            Map<String, Object> payload,
            String candidateId,
            ReviewartifactRecord candidate) {
        if (command == null || candidateId == null || candidate == null) return false;
        if (!candidateId.equals(candidate.getId())
                || !candidateId.equals(command.getArtifactid())
                || !task.getId().equals(candidate.getTaskid())
                || !task.getNovelid().equals(candidate.getNovelid())
                || !Set.of("awaiting_user", "applied").contains(candidate.getStatus().getLiteral())) {
            return false;
        }
        Object operation = payload.get("operation");
        Object documentType = payload.get("documentType");
        if ("generate_outline".equals(operation) && !"outline".equals(documentType)) return false;
        if ("generate_manuscript".equals(operation) && !"manuscript".equals(documentType)) {
            return false;
        }
        if ("outline".equals(documentType)) {
            return "outline_draft".equals(candidate.getKind().getLiteral())
                    && candidate.getChapterid() == null;
        }
        if ("manuscript".equals(documentType)) {
            return Objects.equals(payload.get("chapterId"), task.getChapterid())
                    && "chapter_draft".equals(candidate.getKind().getLiteral())
                    && task.getChapterid().equals(candidate.getChapterid());
        }
        return false;
    }

    private boolean awaitingArtifactReady(
            WritingtaskRecord task,
            WritingruncommandRecord command,
            ReviewartifactRecord artifact) {
        if (!"awaiting_user_review".equals(task.getPhase().getLiteral())
                || !authoritative(task, artifact, "awaiting_user")
                || command == null
                || !task.getId().equals(command.getTaskid())
                || !"succeeded".equals(command.getStatus())) {
            return false;
        }
        if ("start".equals(command.getKind())) return true;
        return artifactDecisionMatches(command, task, artifact.getId(), "revise")
                && artifact.getRevision() >= 2
                && !artifact.getUpdatedat().isBefore(command.getCreatedat());
    }

    private boolean appliedArtifactReady(
            WritingtaskRecord task,
            WritingruncommandRecord command,
            ReviewartifactRecord artifact) {
        return "completed".equals(task.getPhase().getLiteral())
                && artifact != null
                && authoritative(task, artifact, "applied")
                && artifactDecisionMatches(command, task, artifact.getId(), "approve");
    }

    private boolean artifactDecisionMatches(
            WritingruncommandRecord command,
            WritingtaskRecord task,
            String artifactId,
            String decision) {
        if (command == null) return false;
        Map<String, Object> payload = commandJob(command);
        Object resumeInput = payload.get("resumeInput");
        Map<String, Object> result = fullResult(command);
        return task.getId().equals(command.getTaskid())
                && "artifact_decision".equals(command.getKind())
                && "succeeded".equals(command.getStatus())
                && decision.equals(command.getDecision())
                && artifactId.equals(command.getArtifactid())
                && Boolean.TRUE.equals(payload.get("resume"))
                && resumeInput instanceof Map<?, ?> resume
                && artifactId.equals(resume.get("artifactId"))
                && decision.equals(resume.get("decision"))
                && artifactId.equals(result.get("artifactId"))
                && task.getId().equals(result.get("taskId"))
                && command.getId().equals(result.get("commandId"))
                && decision.equals(result.get("decision"))
                && result.get("status") instanceof String status
                && Set.of("pending", "submitted", "processing", "succeeded", "failed")
                        .contains(status);
    }

    private boolean discardDecisionReady(
            WritingruncommandRecord command, WritingtaskRecord task, String artifactId) {
        return artifactId != null
                && artifactDecisionMatches(command, task, artifactId, "discard")
                && Boolean.TRUE.equals(fullResult(command).get("deleted"));
    }

    private static boolean authoritative(
            WritingtaskRecord task, ReviewartifactRecord artifact, String status) {
        return Objects.equals(artifact.getTaskid(), task.getId())
                && Objects.equals(artifact.getNovelid(), task.getNovelid())
                && Objects.equals(artifact.getChapterid(), task.getChapterid())
                && artifact.getStatus() != null
                && status.equals(artifact.getStatus().getLiteral());
    }

    private static ReviewartifactRecord longArtifact(
            WritingtaskRecord task,
            List<ReviewartifactRecord> artifacts,
            String expectedKind,
            String artifactId) {
        List<ReviewartifactRecord> candidates = artifacts.stream()
                .filter(item -> artifactId == null || artifactId.equals(item.getId()))
                .filter(item -> Objects.equals(item.getTaskid(), task.getId()))
                .filter(item -> Objects.equals(item.getNovelid(), task.getNovelid()))
                .filter(item -> Objects.equals(item.getChapterid(), task.getChapterid()))
                .filter(item -> item.getKind() != null
                        && expectedKind.equals(item.getKind().getLiteral()))
                .toList();
        return candidates.size() == 1 ? candidates.getFirst() : null;
    }

    private static ReviewartifactRecord artifactById(
            List<ReviewartifactRecord> artifacts, String id) {
        if (id == null) return null;
        return artifacts.stream().filter(item -> id.equals(item.getId())).findFirst().orElse(null);
    }

    private static String decisionArtifactId(WritingruncommandRecord command) {
        return command != null && "artifact_decision".equals(command.getKind())
                ? command.getArtifactid()
                : null;
    }

    private Map<String, Object> commandError(
            WritingruncommandRecord command, Map<String, Object> result) {
        if (command == null || !"failed".equals(command.getStatus())) return null;
        Map<String, Object> error = new LinkedHashMap<>();
        Object resultCode = result.get("code");
        error.put(
                "code",
                command.getLasterror() != null
                        ? command.getLasterror()
                        : resultCode instanceof String value ? value : "WRITING_RUN_FAILED");
        Object message = result.get("message");
        if (message instanceof String value) error.put("message", value);
        return error;
    }

    private String snapshotActiveArtifactId(String serialized) {
        Object review = object(serialized).get("artifactReview");
        Object candidate = review instanceof Map<?, ?> map ? map.get("activeArtifactId") : null;
        if (candidate instanceof String value) return value;
        Object legacy = object(serialized).get("activeArtifactId");
        return legacy instanceof String value ? value : null;
    }

    private String logicalKind(WritingruncommandRecord command) {
        Object metadata = object(command.getPayloadjson()).get("_inkforgeCommand");
        Object kind = metadata instanceof Map<?, ?> map ? map.get("commandKind") : null;
        return kind instanceof String value && !value.isEmpty() ? value : command.getKind();
    }

    private Map<String, Object> commandJob(WritingruncommandRecord command) {
        if (command == null) return Map.of();
        Map<String, Object> payload = object(command.getPayloadjson());
        Object job = payload.get("job");
        if (job instanceof Map<?, ?> map) {
            Map<String, Object> converted = stringMap(map);
            return converted == null ? Map.of() : converted;
        }
        return payload;
    }

    private Map<String, Object> fullResult(WritingruncommandRecord command) {
        return command == null ? Map.of() : object(command.getResultjson());
    }

    private Map<String, Object> object(String serialized) {
        if (serialized == null) return Map.of();
        try {
            Object parsed = json.readValue(serialized, new TypeReference<Object>() {});
            if (!(parsed instanceof Map<?, ?> map)) return Map.of();
            Map<String, Object> converted = stringMap(map);
            return converted == null ? Map.of() : converted;
        } catch (RuntimeException exception) {
            return Map.of();
        }
    }

    private static Map<String, Object> objectOrDefault(Object value, Map<String, Object> fallback) {
        if (!(value instanceof Map<?, ?> map)) return fallback;
        Map<String, Object> converted = stringMap(map);
        return converted == null ? fallback : converted;
    }

    private static Map<String, Object> stringMap(Map<?, ?> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) return null;
            result.put(key, entry.getValue());
        }
        return result;
    }

    private record EffectiveCommand(
            WritingruncommandRecord command, Boolean cancelEffective, boolean chainValid) {}
}
