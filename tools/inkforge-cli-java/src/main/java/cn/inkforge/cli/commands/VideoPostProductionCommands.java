package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 关键帧、非破坏性粗剪、声音字幕和整集导出命令。 */
final class VideoPostProductionCommands {

    private static final Set<String> KEYFRAME_ROLES =
            Set.of("initial_state", "transition_anchor", "end_state");
    private static final Set<String> RESOLUTIONS = Set.of("720p", "1080p");

    private VideoPostProductionCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.video.post.show", VideoPostProductionCommands::show);
        handlers.put("long.video.keyframe.set", VideoPostProductionCommands::setKeyframe);
        handlers.put("long.video.keyframe.clear", VideoPostProductionCommands::clearKeyframe);
        handlers.put("long.video.keyframe.extract", VideoPostProductionCommands::extractKeyframe);
        handlers.put("long.video.edit.save", VideoPostProductionCommands::saveEdit);
        handlers.put("long.video.edit.get", VideoPostProductionCommands::getEdit);
        handlers.put("long.video.mix.save", VideoPostProductionCommands::saveMix);
        handlers.put("long.video.mix.get", VideoPostProductionCommands::getMix);
        handlers.put("long.video.export.start", VideoPostProductionCommands::startExport);
        handlers.put("long.video.export.get", VideoPostProductionCommands::getExport);
        handlers.put("long.video.export.retry", VideoPostProductionCommands::retryExport);
        handlers.put("long.video.export.download", VideoPostProductionCommands::downloadExport);
    }

    private static CommandResult show(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("adaptationId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                adaptation(payload) + "/post-production");
    }

    private static CommandResult setKeyframe(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "adaptationId",
                        "shotId",
                        "role",
                        "assetId",
                        "clientRequestId",
                        "expectedRevision"),
                Set.of("sourceTakeId", "sourceTimeMs"),
                false);
        String sourceTakeId = VideoPayloads.optionalString(payload, "sourceTakeId", null);
        Integer sourceTimeMs = VideoPayloads.optionalInteger(payload, "sourceTimeMs", 0);
        if ((sourceTakeId == null) != (sourceTimeMs == null)) {
            throw new CliInputException(
                    "INVALID_FIELD",
                    "sourceTakeId 与 sourceTimeMs 必须同时提供");
        }
        return saveKeyframe(
                context,
                payload,
                VideoPayloads.string(payload, "assetId"),
                sourceTakeId,
                sourceTimeMs);
    }

    private static CommandResult clearKeyframe(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "adaptationId",
                        "shotId",
                        "role",
                        "clientRequestId",
                        "expectedRevision"));
        return saveKeyframe(context, payload, null, null, null);
    }

    private static CommandResult saveKeyframe(
            CommandContext context,
            ObjectNode payload,
            String assetId,
            String sourceTakeId,
            Integer sourceTimeMs) {
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedRevision",
                VideoPayloads.integer(payload, "expectedRevision", 1, null));
        body.put(
                "role",
                VideoPayloads.enumeration(payload, "role", KEYFRAME_ROLES, null));
        putNullable(body, "assetId", assetId);
        putNullable(body, "sourceTakeId", sourceTakeId);
        if (sourceTimeMs == null) body.putNull("sourceTimeMs");
        else body.put("sourceTimeMs", sourceTimeMs);
        return VideoPayloads.request(
                context,
                "POST",
                adaptation(payload)
                        + "/shots/"
                        + id(payload, "shotId")
                        + "/keyframe-versions",
                body);
    }

    private static CommandResult extractKeyframe(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("takeId", "clientRequestId", "timestampMs", "name"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("timestampMs", VideoPayloads.integer(payload, "timestampMs", 0, null));
        body.put("name", VideoPayloads.string(payload, "name", 1, 200));
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/takes/" + id(payload, "takeId") + "/frames",
                body);
    }

    private static CommandResult saveEdit(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "adaptationId",
                        "episodeNo",
                        "clientRequestId",
                        "expectedRevision"),
                Set.of("basedOnVersionId", "edit", "editFile"),
                false);
        ObjectNode edit = VideoPayloads.jsonSource(context, payload, "edit", "editFile");
        JsonNode clips = edit.get("clips");
        if (clips == null || !clips.isArray()) {
            throw new CliInputException("INVALID_FIELD", "edit.clips 必须是数组");
        }
        int episodeNo = VideoPayloads.integer(payload, "episodeNo", 1, null);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedRevision",
                VideoPayloads.integer(payload, "expectedRevision", 1, null));
        putNullable(
                body,
                "basedOnVersionId",
                VideoPayloads.optionalString(payload, "basedOnVersionId", null));
        body.set("clips", clips.deepCopy());
        return VideoPayloads.request(
                context,
                "POST",
                adaptation(payload)
                        + "/episodes/"
                        + episodeNo
                        + "/edit-versions",
                body);
    }

    private static CommandResult getEdit(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("versionId"), Set.of(), true);
        return VideoPayloads.get(
                context, "/api/v1/video/edit-versions/" + id(payload, "versionId"));
    }

    private static CommandResult saveMix(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "adaptationId",
                        "episodeNo",
                        "clientRequestId",
                        "expectedRevision",
                        "editVersionId"),
                Set.of("basedOnVersionId", "mix", "mixFile"),
                false);
        ObjectNode mix = VideoPayloads.jsonSource(context, payload, "mix", "mixFile");
        JsonNode audio = mix.has("audioClips")
                ? mix.get("audioClips")
                : context.dependencies().json().createArrayNode();
        JsonNode subtitles = mix.has("subtitleCues")
                ? mix.get("subtitleCues")
                : context.dependencies().json().createArrayNode();
        if (!audio.isArray() || !subtitles.isArray()) {
            throw new CliInputException(
                    "INVALID_FIELD",
                    "mix.audioClips 与 mix.subtitleCues 必须是数组");
        }
        int episodeNo = VideoPayloads.integer(payload, "episodeNo", 1, null);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedRevision",
                VideoPayloads.integer(payload, "expectedRevision", 1, null));
        putNullable(
                body,
                "basedOnVersionId",
                VideoPayloads.optionalString(payload, "basedOnVersionId", null));
        body.put("editVersionId", VideoPayloads.string(payload, "editVersionId"));
        body.set("audioClips", audio.deepCopy());
        body.set("subtitleCues", subtitles.deepCopy());
        return VideoPayloads.request(
                context,
                "POST",
                adaptation(payload)
                        + "/episodes/"
                        + episodeNo
                        + "/mix-versions",
                body);
    }

    private static CommandResult getMix(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("versionId"), Set.of(), true);
        return VideoPayloads.get(
                context, "/api/v1/video/mix-versions/" + id(payload, "versionId"));
    }

    private static CommandResult startExport(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "adaptationId",
                        "episodeNo",
                        "editVersionId",
                        "mixVersionId",
                        "clientRequestId"),
                Set.of("resolution", "framesPerSecond", "burnSubtitles"),
                false);
        int episodeNo = VideoPayloads.integer(payload, "episodeNo", 1, null);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("editVersionId", VideoPayloads.string(payload, "editVersionId"));
        body.put("mixVersionId", VideoPayloads.string(payload, "mixVersionId"));
        body.put(
                "resolution",
                VideoPayloads.enumeration(payload, "resolution", RESOLUTIONS, "720p"));
        body.put(
                "framesPerSecond",
                VideoPayloads.enumInteger(
                        payload, "framesPerSecond", Set.of(24, 25, 30), 24));
        body.put(
                "burnSubtitles",
                VideoPayloads.optionalBoolean(payload, "burnSubtitles", true));
        return VideoPayloads.request(
                context,
                "POST",
                adaptation(payload)
                        + "/episodes/"
                        + episodeNo
                        + "/export-tasks",
                body);
    }

    private static CommandResult getExport(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("taskId"), Set.of(), true);
        return export(context, VideoPayloads.string(payload, "taskId"));
    }

    private static CommandResult retryExport(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("taskId", "clientRequestId"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/export-tasks/"
                        + id(payload, "taskId")
                        + "/retry",
                body);
    }

    private static CommandResult downloadExport(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload, Set.of("exportId", "outputFile"), Set.of(), true);
        String exportId = VideoPayloads.string(payload, "exportId");
        return VideoPayloads.download(
                context,
                payload,
                "exportId",
                "/api/v1/video/exports/"
                        + Payloads.segment(exportId)
                        + "/content");
    }

    static CommandResult export(CommandContext context, String taskId) {
        return VideoPayloads.get(
                context,
                "/api/v1/video/export-tasks/" + Payloads.segment(taskId));
    }

    private static String adaptation(ObjectNode payload) {
        return "/api/v1/video/chapter-adaptations/" + id(payload, "adaptationId");
    }

    private static String id(ObjectNode payload, String field) {
        return Payloads.segment(VideoPayloads.string(payload, field));
    }

    private static void putNullable(ObjectNode body, String field, String value) {
        if (value == null) body.putNull(field);
        else body.put(field, value);
    }
}
