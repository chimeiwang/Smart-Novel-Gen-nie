package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import cn.inkforge.cli.transport.CoreApiException;
import cn.inkforge.cli.transport.CoreResponseContractException;
import cn.inkforge.cli.transport.CoreSseConnectionException;
import cn.inkforge.cli.transport.CoreTransportException;
import cn.inkforge.cli.transport.SseStream;
import java.util.List;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 长篇写作任务观察器，以 outcome.state 为唯一权威生命周期。 */
final class LongWatchCommands {

    private static final Set<String> OUTCOME_STATES = Set.of(
            "queued",
            "running",
            "waiting_user",
            "succeeded",
            "failed",
            "cancelled",
            "inconsistent");
    private static final Set<String> FAILED_STATES =
            Set.of("failed", "cancelled", "inconsistent");

    private LongWatchCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.task.watch", LongWatchCommands::watch);
    }

    private static CommandResult watch(CommandContext context, ObjectNode payload) {
        Payloads.validateRead(payload, List.of("taskId"), List.of(), false);
        String taskId = Payloads.requireString(payload, "taskId");
        return CommandResult.jsonl(emitter -> produce(context, taskId, emitter));
    }

    private static int produce(
            CommandContext context,
            String taskId,
            CommandResult.FrameEmitter emitter)
            throws Exception {
        String taskPath = "/api/v1/writing/runs/" + Payloads.segment(taskId);
        String lastEventId = null;
        ObjectNode lastSnapshot = null;
        Double unreachableSince = null;
        int backoffIndex = 0;
        boolean snapshotEmitted = false;
        boolean needsStatus = true;
        boolean backoffAfterStatus = false;
        try {
            while (true) {
                if (needsStatus) {
                    double attemptStarted = context.dependencies().monotonicClock().now();
                    ObjectNode snapshot;
                    try {
                        snapshot = VideoPayloads.object(
                                context.requireApi().request("GET", taskPath),
                                "任务状态响应不是 JSON 对象");
                    } catch (CoreApiException | CoreTransportException error) {
                        if (!WatchSupport.retryable(error, true)) throw error;
                        double now = context.dependencies().monotonicClock().now();
                        if (unreachableSince == null) unreachableSince = attemptStarted;
                        if (now - unreachableSince > WatchSupport.UNREACHABLE_TIMEOUT_SECONDS) {
                            emitter.emit(unreachable(
                                    context, taskId, lastEventId, lastSnapshot));
                            return 5;
                        }
                        backoffIndex = WatchSupport.sleep(context, backoffIndex);
                        backoffAfterStatus = false;
                        continue;
                    }
                    unreachableSince = null;
                    lastSnapshot = snapshot;
                    needsStatus = false;
                    String state = outcomeState(snapshot);
                    if (!snapshotEmitted) {
                        emitter.emit(frame(context, "snapshot", snapshot));
                        snapshotEmitted = true;
                    }
                    Integer terminal = terminal(
                            context, emitter, taskId, snapshot, state);
                    if (terminal != null) return terminal;
                    if (backoffAfterStatus) {
                        backoffIndex = WatchSupport.sleep(context, backoffIndex);
                        backoffAfterStatus = false;
                    }
                }

                boolean receivedEvent = false;
                double sseAttemptStarted = context.dependencies().monotonicClock().now();
                try (SseStream stream = context.requireApi().openSse(taskId, lastEventId)) {
                    while (stream.hasNext()) {
                        ObjectNode event = VideoPayloads.object(
                                stream.next(), "SSE 事件不是 JSON 对象");
                        String eventId = eventId(event);
                        if (eventId != null) lastEventId = eventId;
                        receivedEvent = true;
                        emitter.emit(eventFrame(context, event));
                    }
                } catch (CoreSseConnectionException ignored) {
                    // 断线后先用持久化状态对账，再携带最新游标重连。
                } catch (CoreApiException | CoreTransportException error) {
                    if (!WatchSupport.retryable(error, true)) throw error;
                    double unavailableStarted = receivedEvent
                            ? context.dependencies().monotonicClock().now()
                            : sseAttemptStarted;
                    if (unreachableSince == null) unreachableSince = unavailableStarted;
                    if (context.dependencies().monotonicClock().now() - unreachableSince
                            > WatchSupport.UNREACHABLE_TIMEOUT_SECONDS) {
                        emitter.emit(unreachable(
                                context, taskId, lastEventId, lastSnapshot));
                        return 5;
                    }
                }
                if (receivedEvent) backoffIndex = 0;
                needsStatus = true;
                backoffAfterStatus = true;
            }
        } catch (InterruptedException exception) {
            ObjectNode frame = context.dependencies().json().createObjectNode();
            frame.put("type", "error");
            ObjectNode error = frame.putObject("error");
            error.put("code", "WATCH_INTERRUPTED");
            error.put("message", "仅停止观察，服务端任务未取消");
            error.put("taskId", taskId);
            if (lastEventId == null) error.putNull("lastEventId");
            else error.put("lastEventId", lastEventId);
            emitter.emit(frame);
            return 130;
        }
    }

    private static Integer terminal(
            CommandContext context,
            CommandResult.FrameEmitter emitter,
            String taskId,
            ObjectNode snapshot,
            String state) {
        if (state.equals("waiting_user")) {
            ObjectNode frame = context.dependencies().json().createObjectNode();
            frame.put("type", "waiting_user");
            frame.put("taskId", taskId);
            frame.put("artifactId", waitingArtifact(snapshot));
            frame.set("data", snapshot.deepCopy());
            emitter.emit(frame);
            return 0;
        }
        if (state.equals("succeeded")) {
            emitter.emit(frame(context, "terminal", snapshot));
            return 0;
        }
        if (FAILED_STATES.contains(state)) {
            emitter.emit(frame(context, "terminal", snapshot));
            return 5;
        }
        return null;
    }

    private static String outcomeState(ObjectNode snapshot) {
        JsonNode outcome = snapshot.get("outcome");
        JsonNode state = outcome != null && outcome.isObject() ? outcome.get("state") : null;
        if (state == null || !state.isTextual() || !OUTCOME_STATES.contains(state.textValue())) {
            throw new CoreResponseContractException(
                    "任务状态响应缺少有效的 outcome.state");
        }
        return state.textValue();
    }

    private static String waitingArtifact(ObjectNode snapshot) {
        JsonNode outcome = snapshot.get("outcome");
        JsonNode result = outcome != null && outcome.isObject() ? outcome.get("result") : null;
        JsonNode id = result != null && result.isObject() ? result.get("id") : null;
        if (id == null || !id.isTextual() || id.textValue().isEmpty()) {
            throw new CoreResponseContractException(
                    "waiting_user 任务缺少权威 Artifact ID");
        }
        return id.textValue();
    }

    private static ObjectNode eventFrame(CommandContext context, ObjectNode event) {
        ObjectNode frame = context.dependencies().json().createObjectNode();
        frame.put("type", "event");
        JsonNode id = event.get("id");
        if (id != null && id.isTextual()) frame.put("id", id.textValue());
        else frame.putNull("id");
        JsonNode name = event.get("event");
        frame.put("event", name != null && name.isTextual() ? name.textValue() : "message");
        JsonNode data = event.get("data");
        if (data == null) frame.putNull("data");
        else frame.set("data", data.deepCopy());
        return frame;
    }

    private static String eventId(ObjectNode event) {
        JsonNode id = event.get("id");
        return id != null && id.isTextual() && !id.textValue().isEmpty()
                ? id.textValue()
                : null;
    }

    private static ObjectNode frame(
            CommandContext context, String type, JsonNode data) {
        ObjectNode frame = context.dependencies().json().createObjectNode();
        frame.put("type", type);
        frame.set("data", data.deepCopy());
        return frame;
    }

    private static ObjectNode unreachable(
            CommandContext context,
            String taskId,
            String lastEventId,
            ObjectNode lastSnapshot) {
        ObjectNode frame = context.dependencies().json().createObjectNode();
        frame.put("type", "error");
        ObjectNode error = frame.putObject("error");
        error.put("code", "WATCH_CORE_UNREACHABLE");
        error.put("message", "Core API 连续不可达超过 300 秒；仅停止观察，服务端任务未取消");
        error.put("taskId", taskId);
        if (lastEventId == null) error.putNull("lastEventId");
        else error.put("lastEventId", lastEventId);
        if (lastSnapshot == null) error.putNull("state");
        else error.put("state", outcomeState(lastSnapshot));
        return frame;
    }
}
