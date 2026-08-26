package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import cn.inkforge.cli.transport.CoreApiException;
import cn.inkforge.cli.transport.CoreResponseContractException;
import cn.inkforge.cli.transport.CoreTransportException;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 视频耐久任务观察器；轮询停止不改变任何服务端任务。 */
final class VideoWatchCommands {

    private static final Definition ADAPTATION = new Definition(
            Set.of("pending", "submitted", "processing", "completed", "failed", "cancelled"),
            Set.of("completed"),
            Set.of("failed", "cancelled"),
            "章节影视化任务缺少有效 status",
            new String[] {
                "status", "checkpointStage", "updatedAt", "lastErrorCode", "lastErrorMessage"
            });
    private static final Definition RENDER = new Definition(
            Set.of(
                    "pending",
                    "submitting",
                    "queued",
                    "running",
                    "archiving",
                    "submission_unknown",
                    "succeeded",
                    "failed",
                    "expired",
                    "cancelled"),
            Set.of("succeeded"),
            Set.of("submission_unknown", "failed", "expired", "cancelled"),
            "逐镜视频任务缺少有效 status",
            new String[] {
                "status", "pollCount", "updatedAt", "lastErrorCode", "lastErrorMessage"
            });
    private static final Definition EXPORT = new Definition(
            Set.of("pending", "rendering", "succeeded", "failed"),
            Set.of("succeeded"),
            Set.of("failed"),
            "整集导出任务缺少有效 status",
            new String[] {
                "status", "attemptCount", "updatedAt", "lastErrorCode", "lastErrorMessage"
            });

    private VideoWatchCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.video.adaptation.watch", VideoWatchCommands::adaptation);
        handlers.put("long.video.render.watch", (context, payload) ->
                task(context, payload, "render", RENDER));
        handlers.put("long.video.export.watch", (context, payload) ->
                task(context, payload, "export", EXPORT));
    }

    private static CommandResult adaptation(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("adaptationId", "taskId"));
        String adaptationId = VideoPayloads.string(payload, "adaptationId");
        String taskId = VideoPayloads.string(payload, "taskId");
        return CommandResult.jsonl(emitter -> poll(
                context,
                taskId,
                adaptationId,
                ADAPTATION,
                () -> {
                    ObjectNode snapshot = VideoAdaptationCommands.adaptation(context, adaptationId);
                    ObjectNode task = VideoPayloads.object(
                            snapshot.get("latestTask"),
                            "章节影视化响应缺少 latestTask");
                    JsonNode currentTaskId = task.get("id");
                    if (currentTaskId == null
                            || !currentTaskId.isTextual()
                            || !currentTaskId.textValue().equals(taskId)) {
                        return Snapshot.superseded(snapshot, task);
                    }
                    return new Snapshot(snapshot, task, false);
                },
                emitter));
    }

    private static CommandResult task(
            CommandContext context,
            ObjectNode payload,
            String kind,
            Definition definition) {
        VideoPayloads.fields(payload, Set.of("taskId"));
        String taskId = VideoPayloads.string(payload, "taskId");
        return CommandResult.jsonl(emitter -> poll(
                context,
                taskId,
                null,
                definition,
                () -> {
                    String path = kind.equals("render")
                            ? "/api/v1/video/render-tasks/"
                            : "/api/v1/video/export-tasks/";
                    ObjectNode task = VideoPayloads.object(
                            context.requireApi().request(
                                    "GET", path + Payloads.segment(taskId)),
                            kind.equals("render")
                                    ? "逐镜视频任务响应不是 JSON 对象"
                                    : "整集导出任务响应不是 JSON 对象");
                    return new Snapshot(task, task, false);
                },
                emitter));
    }

    private static int poll(
            CommandContext context,
            String taskId,
            String adaptationId,
            Definition definition,
            Fetcher fetcher,
            CommandResult.FrameEmitter emitter)
            throws Exception {
        Double unreachableSince = null;
        int backoffIndex = 0;
        ArrayNode lastSignature = null;
        boolean first = true;
        try {
            while (true) {
                double attemptStarted = context.dependencies().monotonicClock().now();
                Snapshot snapshot;
                try {
                    snapshot = fetcher.fetch();
                } catch (CoreApiException | CoreTransportException error) {
                    if (!WatchSupport.retryable(error, false)) throw error;
                    double now = context.dependencies().monotonicClock().now();
                    if (unreachableSince == null) unreachableSince = attemptStarted;
                    if (now - unreachableSince > WatchSupport.UNREACHABLE_TIMEOUT_SECONDS) {
                        emitter.emit(unreachable(context, taskId, adaptationId));
                        return 5;
                    }
                    backoffIndex = WatchSupport.sleep(context, backoffIndex);
                    continue;
                }
                unreachableSince = null;
                if (snapshot.superseded()) {
                    emitter.emit(superseded(context, taskId, adaptationId, snapshot.task()));
                    return 5;
                }
                String status = status(snapshot.task(), definition);
                ArrayNode signature = signature(context, snapshot.task(), definition.signatureFields());
                if (first) {
                    emitter.emit(frame(context, "snapshot", snapshot.aggregate()));
                    first = false;
                } else if (!signature.equals(lastSignature)) {
                    ObjectNode progress = context.dependencies().json().createObjectNode();
                    progress.put("type", "progress");
                    if (adaptationId != null) progress.put("adaptationId", adaptationId);
                    progress.put("taskId", taskId);
                    progress.set("data", snapshot.task().deepCopy());
                    emitter.emit(progress);
                }
                lastSignature = signature;
                if (definition.success().contains(status)) {
                    emitter.emit(frame(context, "terminal", snapshot.aggregate()));
                    return 0;
                }
                if (definition.failed().contains(status)) {
                    emitter.emit(frame(context, "terminal", snapshot.aggregate()));
                    return 5;
                }
                backoffIndex = WatchSupport.sleep(context, backoffIndex);
            }
        } catch (InterruptedException exception) {
            ObjectNode frame = context.dependencies().json().createObjectNode();
            frame.put("type", "error");
            ObjectNode error = frame.putObject("error");
            error.put("code", "WATCH_INTERRUPTED");
            error.put("message", "仅停止观察，服务端任务未取消");
            if (adaptationId != null) error.put("adaptationId", adaptationId);
            error.put("taskId", taskId);
            emitter.emit(frame);
            return 130;
        }
    }

    private static String status(ObjectNode task, Definition definition) {
        JsonNode status = task.get("status");
        if (status == null
                || !status.isTextual()
                || !definition.statuses().contains(status.textValue())) {
            throw new CoreResponseContractException(definition.invalidStatusMessage());
        }
        return status.textValue();
    }

    private static ArrayNode signature(
            CommandContext context, ObjectNode task, String[] fields) {
        ArrayNode result = context.dependencies().json().createArrayNode();
        for (String field : fields) {
            JsonNode value = task.get(field);
            if (value == null) result.addNull();
            else result.add(value.deepCopy());
        }
        return result;
    }

    private static ObjectNode superseded(
            CommandContext context,
            String taskId,
            String adaptationId,
            ObjectNode latestTask) {
        ObjectNode frame = context.dependencies().json().createObjectNode();
        frame.put("type", "error");
        ObjectNode error = frame.putObject("error");
        error.put("code", "VIDEO_TASK_SUPERSEDED");
        error.put("message", "改编当前最新任务与目标 taskId 不一致；仅停止观察");
        error.put("adaptationId", adaptationId);
        error.put("taskId", taskId);
        JsonNode latestId = latestTask.get("id");
        if (latestId == null) error.putNull("latestTaskId");
        else error.set("latestTaskId", latestId.deepCopy());
        return frame;
    }

    private static ObjectNode unreachable(
            CommandContext context, String taskId, String adaptationId) {
        ObjectNode frame = context.dependencies().json().createObjectNode();
        frame.put("type", "error");
        ObjectNode error = frame.putObject("error");
        error.put("code", "WATCH_CORE_UNREACHABLE");
        error.put("message", "Core API 连续不可达超过 300 秒；仅停止观察，服务端任务未取消");
        if (adaptationId != null) error.put("adaptationId", adaptationId);
        error.put("taskId", taskId);
        return frame;
    }

    private static ObjectNode frame(
            CommandContext context, String type, JsonNode data) {
        ObjectNode frame = context.dependencies().json().createObjectNode();
        frame.put("type", type);
        frame.set("data", data.deepCopy());
        return frame;
    }

    @FunctionalInterface
    private interface Fetcher {
        Snapshot fetch();
    }

    private record Snapshot(ObjectNode aggregate, ObjectNode task, boolean superseded) {
        private static Snapshot superseded(ObjectNode aggregate, ObjectNode task) {
            return new Snapshot(aggregate, task, true);
        }
    }

    private record Definition(
            Set<String> statuses,
            Set<String> success,
            Set<String> failed,
            String invalidStatusMessage,
            String[] signatureFields) {}
}
