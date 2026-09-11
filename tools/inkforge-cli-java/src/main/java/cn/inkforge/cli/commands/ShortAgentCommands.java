package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import cn.inkforge.cli.transport.CoreResponseContractException;
import cn.inkforge.cli.transport.CoreSseConnectionException;
import cn.inkforge.cli.transport.SseStream;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 中短篇 Agent 启动命令；本地快照只作为并发门禁，不进入公共请求。 */
final class ShortAgentCommands {

    private static final String[] PUBLIC_START_FIELDS = {
        "clientRequestId",
        "novelId",
        "documentType",
        "chapterId",
        "baseVersionId",
        "sourceOutlineVersionId",
        "selectionStart",
        "selectionEnd",
        "selectedTextHash",
        "userInstruction"
    };
    private static final Map<String, String> OPERATIONS = operations();

    private ShortAgentCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("short.agent.start", ShortAgentCommands::start);
        handlers.put("short.agent.watch", ShortAgentCommands::watch);
    }

    private static CommandResult watch(CommandContext context, ObjectNode payload) {
        String taskId = Payloads.requireShortString(payload, "taskId");
        JsonNode rawLastEventId = payload.get("lastEventId");
        if (rawLastEventId != null
                && !rawLastEventId.isNull()
                && !rawLastEventId.isTextual()) {
            throw new CliInputException(
                    "INVALID_LAST_EVENT_ID", "lastEventId 必须是字符串");
        }
        String initialCursor = rawLastEventId != null && rawLastEventId.isTextual()
                ? rawLastEventId.textValue()
                : null;
        return CommandResult.jsonl(emitter -> watch(context, taskId, initialCursor, emitter));
    }

    /** 观察 SSE 并以 PostgreSQL 状态回读确认终态，最多执行三次有界重连。 */
    private static int watch(
            CommandContext context,
            String taskId,
            String initialCursor,
            CommandResult.FrameEmitter emitter) {
        String cursor = initialCursor;
        int reconnects = 0;
        Integer observedEngine = null;
        while (true) {
            boolean disconnected = false;
            try (SseStream stream = context.requireApi().openSse(taskId, cursor)) {
                while (stream.hasNext()) {
                    ObjectNode event = VideoPayloads.object(
                            stream.next(), "SSE 事件不是 JSON 对象");
                    Observation observation = observe(event, taskId);
                    if (observation.cursor() != null) cursor = observation.cursor();
                    if (observation.engine() != null) {
                        requireSameEngine(observedEngine, observation.engine());
                        observedEngine = observation.engine();
                    }
                    ObjectNode frame = context.dependencies().json().createObjectNode();
                    frame.put("type", "event");
                    event.properties().forEach(entry ->
                            frame.set(entry.getKey(), entry.getValue().deepCopy()));
                    emitter.emit(frame);
                    if (observation.terminalHint()) break;
                }
            } catch (CoreSseConnectionException exception) {
                disconnected = true;
            }

            // SSE 终态只是提示；断流或终态后必须回读同一任务的权威状态。
            JsonNode state = null;
            if (!disconnected || Integer.valueOf(2).equals(observedEngine) || reconnects >= 3) {
                state = context.requireApi().request(
                        "GET",
                        "/api/v1/writing/runs/" + Payloads.segment(taskId));
                int engine = engineVersion(state);
                requireSameEngine(observedEngine, engine);
                observedEngine = engine;
                Integer terminalExit = terminalExit(state, taskId);
                if (terminalExit != null) {
                    ObjectNode frame = context.dependencies().json().createObjectNode();
                    frame.put("type", "terminal");
                    frame.set("data", state.deepCopy());
                    emitter.emit(frame);
                    return terminalExit;
                }
            }
            if (reconnects >= 3) {
                ObjectNode stateFrame = context.dependencies().json().createObjectNode();
                stateFrame.put("type", "state");
                if (state == null) stateFrame.putNull("data");
                else stateFrame.set("data", state.deepCopy());
                emitter.emit(stateFrame);
                ObjectNode errorFrame = context.dependencies().json().createObjectNode();
                errorFrame.put("type", "error");
                ObjectNode error = errorFrame.putObject("error");
                error.put("code", "SSE_RECONNECT_EXHAUSTED");
                error.put("message", "SSE 重连次数已达上限，任务仍未进入终态");
                emitter.emit(errorFrame);
                return 5;
            }
            reconnects++;
        }
    }

    /** 校验 V1/V2 状态契约，返回终态退出码；非终态返回 null。 */
    private static Integer terminalExit(JsonNode state, String taskId) {
        if (!(state instanceof ObjectNode object)) return null;
        if (engineVersion(state) == 2) {
            if (!object.path("workflow").asText().equals("short_medium")
                    || !object.path("runId").asText().equals(taskId)
                    || !object.path("activeSteps").isArray()
                    || !object.path("status").isTextual()
                    || !Set.of("pending", "running", "completed", "failed", "cancelled")
                            .contains(object.path("status").asText())) {
                throw new CoreResponseContractException("V2 中短篇任务身份或状态无效");
            }
            for (String field : Set.of("artifact", "error", "checkReport")) {
                JsonNode value = object.get(field);
                if (value != null && !value.isNull() && !value.isObject()) {
                    throw new CoreResponseContractException("V2 中短篇任务结果字段无效");
                }
            }
            JsonNode candidate = object.get("candidateVersionId");
            boolean hasCandidate = candidate != null && !candidate.isNull();
            if (hasCandidate && (!candidate.isTextual() || candidate.textValue().isEmpty())) {
                throw new CoreResponseContractException("V2 中短篇候选版本身份无效");
            }
            String status = object.path("status").asText();
            if (Set.of("failed", "cancelled").contains(status)) return 5;
            if (!status.equals("completed")) return null;
            JsonNode report = object.get("checkReport");
            if (object.path("operation").asText().equals("full_check")) {
                if (hasCandidate || report == null || !report.isObject()
                        || !report.path("text").isTextual() || report.path("text").asText().isEmpty()) {
                    throw new CoreResponseContractException("V2 全文检查缺少权威完整报告");
                }
            } else if (!Set.of("generate_outline", "generate_manuscript", "replace_selection")
                            .contains(object.path("operation").asText())
                    || !hasCandidate || (report != null && !report.isNull())) {
                throw new CoreResponseContractException("V2 中短篇生成缺少权威候选版本");
            }
            return 0;
        }
        JsonNode phase = object.get("phase");
        JsonNode commandStatus = object.get("commandStatus");
        boolean terminal = phase != null
                        && phase.isTextual()
                        && Set.of("completed", "error", "cancelled", "canceled")
                                .contains(phase.textValue())
                || commandStatus != null
                        && commandStatus.isTextual()
                        && Set.of("succeeded", "failed").contains(commandStatus.textValue());
        return terminal ? 0 : null;
    }

    private static int engineVersion(JsonNode state) {
        if (state == null || !state.isObject()) {
            throw new CoreResponseContractException("任务状态不是 JSON 对象");
        }
        JsonNode value = state.get("engineVersion");
        if (value == null) return 1;
        if (!value.isIntegralNumber() || !value.canConvertToInt()
                || (value.intValue() != 1 && value.intValue() != 2)) {
            throw new CoreResponseContractException("任务状态缺少有效 engineVersion");
        }
        return value.intValue();
    }

    private static void requireSameEngine(Integer observed, int current) {
        // 同一 taskId 不能在观察期间从 V1 变为 V2，否则游标和终态语义将不可判定。
        if (observed != null && observed != current) {
            throw new CoreResponseContractException("同一任务的 engineVersion 在观察期间发生变化");
        }
    }

    private static Observation observe(ObjectNode event, String taskId) {
        JsonNode rawCursor = event.get("id");
        String cursor = null;
        if (rawCursor != null && !rawCursor.isNull()) {
            if (rawCursor.isTextual()) {
                if (!rawCursor.textValue().isEmpty()) cursor = rawCursor.textValue();
            } else if (rawCursor.isIntegralNumber() && rawCursor.bigIntegerValue().signum() >= 0) {
                cursor = rawCursor.asText();
            } else {
                throw new CoreResponseContractException("SSE 事件包含无效游标");
            }
        }
        JsonNode data = event.get("data");
        Integer engine = data != null && data.isObject() && data.has("engineVersion")
                ? engineVersion(data) : null;
        boolean terminalHint = false;
        if (Integer.valueOf(2).equals(engine)) {
            if (data.has("runId") && !data.path("runId").asText().equals(taskId)) {
                throw new CoreResponseContractException("V2 SSE 事件不属于当前任务");
            }
            String eventName = event.path("event").asText();
            terminalHint = Set.of("completed", "failed", "cancelled").contains(eventName);
            if (eventName.equals("run_snapshot")) {
                JsonNode base = data.get("baseSequence");
                JsonNode snapshot = data.get("snapshot");
                if (base == null || !base.isIntegralNumber() || base.bigIntegerValue().signum() < 0
                        || snapshot == null || !snapshot.isObject()
                        || (cursor != null && !cursor.equals(base.asText()))) {
                    throw new CoreResponseContractException("V2 run_snapshot 游标或快照无效");
                }
                cursor = base.asText();
                terminalHint = Set.of("completed", "failed", "cancelled")
                        .contains(snapshot.path("status").asText());
            }
        }
        return new Observation(cursor, engine, terminalHint);
    }

    private record Observation(String cursor, Integer engine, boolean terminalHint) {}


    private static CommandResult start(CommandContext context, ObjectNode payload) {
        String novelId = Payloads.requireShortString(payload, "novelId");
        new ShortSnapshotStore(context.dependencies().json())
                .requireCleanManifest(payload, novelId);
        JsonNode operationNode = payload.get("operation");
        if (operationNode == null
                || !operationNode.isTextual()
                || !OPERATIONS.containsKey(operationNode.textValue())) {
            throw new CliInputException(
                    "INVALID_AGENT_OPERATION",
                    "operation 只能是 outline、manuscript、selection 或 full_check");
        }
        String operation = operationNode.textValue();
        if (operation.equals("selection")) {
            JsonNode instruction = payload.get("userInstruction");
            if (instruction == null
                    || !instruction.isTextual()
                    || instruction.textValue().trim().isEmpty()) {
                throw new CliInputException(
                        "FIELD_REQUIRED",
                        "selection 操作必须提供非空 userInstruction");
            }
        }
        ObjectNode body = context.dependencies().json().createObjectNode();
        for (String field : PUBLIC_START_FIELDS) {
            if (payload.has(field)) body.set(field, payload.get(field).deepCopy());
        }
        body.put("workflow", "short_medium");
        body.put("operation", OPERATIONS.get(operation));
        return CommandResult.json(context.requireApi().request(
                "POST", "/api/v1/writing/runs", body));
    }

    private static Map<String, String> operations() {
        LinkedHashMap<String, String> values = new LinkedHashMap<>();
        values.put("outline", "generate_outline");
        values.put("manuscript", "generate_manuscript");
        values.put("selection", "replace_selection");
        values.put("full_check", "full_check");
        return Map.copyOf(values);
    }
}
