package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
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

    private static int watch(
            CommandContext context,
            String taskId,
            String initialCursor,
            CommandResult.FrameEmitter emitter) {
        String cursor = initialCursor;
        int reconnects = 0;
        while (true) {
            boolean disconnected = false;
            try (SseStream stream = context.requireApi().openSse(taskId, cursor)) {
                while (stream.hasNext()) {
                    ObjectNode event = VideoPayloads.object(
                            stream.next(), "SSE 事件不是 JSON 对象");
                    JsonNode eventId = event.get("id");
                    if (eventId != null
                            && eventId.isTextual()
                            && !eventId.textValue().isEmpty()) {
                        cursor = eventId.textValue();
                    }
                    ObjectNode frame = context.dependencies().json().createObjectNode();
                    frame.put("type", "event");
                    event.properties().forEach(entry ->
                            frame.set(entry.getKey(), entry.getValue().deepCopy()));
                    emitter.emit(frame);
                }
            } catch (CoreSseConnectionException exception) {
                disconnected = true;
            }

            JsonNode state = null;
            if (!disconnected || reconnects >= 3) {
                state = context.requireApi().request(
                        "GET",
                        "/api/v1/writing/runs/" + Payloads.segment(taskId));
                if (shortTerminal(state)) {
                    ObjectNode frame = context.dependencies().json().createObjectNode();
                    frame.put("type", "terminal");
                    frame.set("data", state.deepCopy());
                    emitter.emit(frame);
                    return 0;
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

    private static boolean shortTerminal(JsonNode state) {
        if (!(state instanceof ObjectNode object)) return false;
        JsonNode phase = object.get("phase");
        JsonNode commandStatus = object.get("commandStatus");
        return phase != null
                        && phase.isTextual()
                        && Set.of("completed", "error", "cancelled", "canceled")
                                .contains(phase.textValue())
                || commandStatus != null
                        && commandStatus.isTextual()
                        && Set.of("succeeded", "failed").contains(commandStatus.textValue());
    }

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
