package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.node.ObjectNode;

/** 逐镜 Seedance 耐久任务、候选 Take 与选片确认命令。 */
final class VideoRenderCommands {

    private static final Set<String> RESOLUTIONS = Set.of("480p", "720p", "1080p");

    private VideoRenderCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.video.render.list", VideoRenderCommands::list);
        handlers.put("long.video.render.start", VideoRenderCommands::start);
        handlers.put("long.video.render.get", VideoRenderCommands::get);
        handlers.put("long.video.render.retry", VideoRenderCommands::retry);
        handlers.put("long.video.take.confirm", VideoRenderCommands::confirmTake);
        handlers.put("long.video.take.download", VideoRenderCommands::downloadTake);
    }

    private static CommandResult list(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("adaptationId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                "/api/v1/video/chapter-adaptations/"
                        + id(payload, "adaptationId")
                        + "/renders");
    }

    private static CommandResult start(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "adaptationId",
                        "shotId",
                        "clientRequestId",
                        "expectedPromptRevision",
                        "durationSeconds"),
                Set.of("resolution", "generateAudio", "watermark"),
                false);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedPromptRevision",
                VideoPayloads.integer(payload, "expectedPromptRevision", 1, null));
        body.put(
                "durationSeconds",
                VideoPayloads.integer(payload, "durationSeconds", 2, 12));
        body.put(
                "resolution",
                VideoPayloads.enumeration(payload, "resolution", RESOLUTIONS, "720p"));
        body.put(
                "generateAudio",
                VideoPayloads.optionalBoolean(payload, "generateAudio", true));
        body.put(
                "watermark",
                VideoPayloads.optionalBoolean(payload, "watermark", false));
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/chapter-adaptations/"
                        + id(payload, "adaptationId")
                        + "/shots/"
                        + id(payload, "shotId")
                        + "/render-tasks",
                body);
    }

    private static CommandResult get(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("taskId"), Set.of(), true);
        return render(context, VideoPayloads.string(payload, "taskId"));
    }

    private static CommandResult retry(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("taskId", "clientRequestId"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/render-tasks/"
                        + id(payload, "taskId")
                        + "/retry",
                body);
    }

    private static CommandResult confirmTake(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "adaptationId",
                        "shotId",
                        "takeId",
                        "clientRequestId",
                        "expectedTakeRevision"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedTakeRevision",
                VideoPayloads.integer(payload, "expectedTakeRevision", 1, null));
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/chapter-adaptations/"
                        + id(payload, "adaptationId")
                        + "/shots/"
                        + id(payload, "shotId")
                        + "/takes/"
                        + id(payload, "takeId")
                        + "/confirm",
                body);
    }

    private static CommandResult downloadTake(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload, Set.of("takeId", "outputFile"), Set.of(), true);
        String takeId = VideoPayloads.string(payload, "takeId");
        return VideoPayloads.download(
                context,
                payload,
                "takeId",
                "/api/v1/video/takes/" + Payloads.segment(takeId) + "/content");
    }

    static CommandResult render(CommandContext context, String taskId) {
        return VideoPayloads.get(
                context,
                "/api/v1/video/render-tasks/" + Payloads.segment(taskId));
    }

    private static String id(ObjectNode payload, String field) {
        return Payloads.segment(VideoPayloads.string(payload, field));
    }
}
