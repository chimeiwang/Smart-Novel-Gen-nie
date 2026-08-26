package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import cn.inkforge.cli.runtime.LocalFileException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.node.ObjectNode;

/** 视频项目与用户素材命令。 */
final class VideoProjectCommands {

    private static final Set<String> PROJECT_MODES =
            Set.of("concept", "trailer", "highlight", "series");
    private static final Set<String> ASPECT_RATIOS =
            Set.of("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive");
    private static final Set<String> ASSET_MODALITIES = Set.of("image", "video", "audio");
    private static final Set<String> ASSET_DUTIES = Set.of(
            "identity",
            "costume",
            "scene",
            "prop",
            "style",
            "storyboard",
            "keyframe",
            "motion",
            "camera",
            "voice",
            "ambience",
            "sfx",
            "music");
    private static final Set<String> SOURCE_KINDS =
            Set.of("user_upload", "authorized_real", "virtual", "model_generated");
    private static final Set<String> RIGHTS_STATUSES =
            Set.of("confirmed", "restricted", "rejected");

    private VideoProjectCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.video.project.list", VideoProjectCommands::list);
        handlers.put("long.video.project.get", VideoProjectCommands::get);
        handlers.put("long.video.project.create", VideoProjectCommands::create);
        handlers.put("long.video.asset.upload", VideoProjectCommands::upload);
        handlers.put("long.video.asset.rights", VideoProjectCommands::rights);
        handlers.put("long.video.asset.download", (context, payload) ->
                assetFile(context, payload, "content"));
        handlers.put("long.video.asset.preview", (context, payload) ->
                assetFile(context, payload, "preview"));
    }

    private static CommandResult list(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("novelId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                "/api/v1/video/novels/"
                        + Payloads.segment(VideoPayloads.string(payload, "novelId"))
                        + "/projects");
    }

    private static CommandResult get(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("projectId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                "/api/v1/video/projects/"
                        + Payloads.segment(VideoPayloads.string(payload, "projectId")));
    }

    private static CommandResult create(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("novelId", "title"),
                Set.of("mode", "targetAspectRatio", "targetLanguage"),
                false);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("title", VideoPayloads.string(payload, "title", 1, 200));
        body.put(
                "mode",
                VideoPayloads.enumeration(
                        payload, "mode", PROJECT_MODES, "highlight"));
        body.put(
                "targetAspectRatio",
                VideoPayloads.enumeration(
                        payload, "targetAspectRatio", ASPECT_RATIOS, "16:9"));
        body.put(
                "targetLanguage",
                payload.has("targetLanguage")
                        ? VideoPayloads.string(payload, "targetLanguage", 2, 32)
                        : "zh-CN");
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/novels/"
                        + Payloads.segment(VideoPayloads.string(payload, "novelId"))
                        + "/projects",
                body);
    }

    private static CommandResult upload(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("projectId", "filePath", "name", "modality", "duty"),
                Set.of("sourceKind"),
                false);
        String projectId = VideoPayloads.string(payload, "projectId");
        Path file = VideoPayloads.localPath(VideoPayloads.string(payload, "filePath"));
        if (!Files.isRegularFile(file) || !Files.isReadable(file)) {
            throw new CliInputException(
                    "LOCAL_FILE_NOT_FOUND", "filePath 不是可读取的普通文件");
        }
        LinkedHashMap<String, String> form = new LinkedHashMap<>();
        form.put("name", VideoPayloads.string(payload, "name", 1, 200));
        form.put(
                "modality",
                VideoPayloads.enumeration(
                        payload, "modality", ASSET_MODALITIES, null));
        form.put(
                "duty",
                VideoPayloads.enumeration(payload, "duty", ASSET_DUTIES, null));
        form.put(
                "sourceKind",
                VideoPayloads.enumeration(
                        payload, "sourceKind", SOURCE_KINDS, "user_upload"));
        try {
            return CommandResult.json(context.requireApi().upload(
                    "/api/v1/video/projects/"
                            + Payloads.segment(projectId)
                            + "/assets",
                    file,
                    VideoPayloads.mediaType(file),
                    form));
        } catch (IOException exception) {
            throw new LocalFileException("素材文件读取失败", exception);
        }
    }

    private static CommandResult rights(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("assetId", "rightsStatus"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put(
                "rightsStatus",
                VideoPayloads.enumeration(
                        payload, "rightsStatus", RIGHTS_STATUSES, null));
        return VideoPayloads.request(
                context,
                "PATCH",
                "/api/v1/video/assets/"
                        + Payloads.segment(VideoPayloads.string(payload, "assetId"))
                        + "/rights",
                body);
    }

    private static CommandResult assetFile(
            CommandContext context, ObjectNode payload, String endpoint) {
        VideoPayloads.fields(
                payload, Set.of("assetId", "outputFile"), Set.of(), true);
        String assetId = VideoPayloads.string(payload, "assetId");
        return VideoPayloads.download(
                context,
                payload,
                "assetId",
                "/api/v1/video/assets/"
                        + Payloads.segment(assetId)
                        + "/"
                        + endpoint);
    }
}
