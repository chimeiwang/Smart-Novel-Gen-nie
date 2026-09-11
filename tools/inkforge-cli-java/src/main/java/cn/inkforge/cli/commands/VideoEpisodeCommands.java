package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import cn.inkforge.cli.runtime.LocalFileException;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 独立分集、来源集和剧本生产命令。 */
final class VideoEpisodeCommands {

    private static final Set<String> SCRIPT_OPERATIONS =
            Set.of("episode_script_generate", "episode_script_revise");
    private static final Pattern SHA256 = Pattern.compile("^[0-9a-f]{64}$");

    private VideoEpisodeCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.video.episode.list", VideoEpisodeCommands::listEpisodes);
        handlers.put("long.video.episode.get", VideoEpisodeCommands::getEpisode);
        handlers.put("long.video.episode.create", VideoEpisodeCommands::createEpisode);
        handlers.put("long.video.episode.update", VideoEpisodeCommands::updateEpisode);
        handlers.put("long.video.episode.reorder", VideoEpisodeCommands::reorderEpisodes);
        handlers.put("long.video.episode.source.create", VideoEpisodeCommands::createSourceSet);
        handlers.put("long.video.episode.source.list", VideoEpisodeCommands::listSourceSets);
        handlers.put("long.video.episode.source.get", VideoEpisodeCommands::getSourceSet);
        handlers.put("long.video.episode.script.draft.get", VideoEpisodeCommands::getScriptDraft);
        handlers.put("long.video.episode.script.draft.save", VideoEpisodeCommands::saveScriptDraft);
        handlers.put("long.video.episode.script.run.start", VideoEpisodeCommands::startScriptRun);
        handlers.put("long.video.episode.script.run.get", VideoEpisodeCommands::getScriptRun);
        handlers.put(
                "long.video.episode.script.candidate.adopt",
                VideoEpisodeCommands::adoptScriptCandidate);
        handlers.put(
                "long.video.episode.script.confirmation.prepare",
                VideoEpisodeCommands::prepareScriptConfirmation);
        handlers.put(
                "long.video.episode.script.confirmation.get",
                VideoEpisodeCommands::getScriptConfirmation);
        handlers.put(
                "long.video.episode.script.confirmation.approve",
                VideoEpisodeCommands::approveScriptConfirmation);
        handlers.put(
                "long.video.episode.script.version.list",
                VideoEpisodeCommands::listScriptVersions);
        handlers.put(
                "long.video.episode.script.version.get",
                VideoEpisodeCommands::getScriptVersion);
        handlers.put("long.video.episode.command.get", VideoEpisodeCommands::getEpisodeCommand);
        handlers.put(
                "long.video.episode.project-command.get",
                VideoEpisodeCommands::getProjectEpisodeCommand);
    }

    private static CommandResult listEpisodes(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("projectId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                "/api/v1/video/projects/" + id(payload, "projectId") + "/episodes");
    }

    private static CommandResult getEpisode(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId"), Set.of(), true);
        return VideoPayloads.get(context, episodePath(payload));
    }

    private static CommandResult createEpisode(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("projectId", "clientRequestId", "title"),
                Set.of("creativeIntent", "targetDurationSeconds"),
                false);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("title", VideoPayloads.string(payload, "title", 1, 240));
        body.put("creativeIntent", optionalText(payload, "creativeIntent", "", 4_000));
        putNullableInteger(body, payload, "targetDurationSeconds", 1, 86_400);
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/projects/" + id(payload, "projectId") + "/episodes",
                body);
    }

    private static CommandResult updateEpisode(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("episodeId", "clientRequestId", "expectedRevision"),
                Set.of("title", "creativeIntent", "targetDurationSeconds"),
                false);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedRevision",
                VideoPayloads.integer(payload, "expectedRevision", 1, null));
        if (payload.has("title")) {
            putNullableText(body, payload, "title", 240, true);
        }
        if (payload.has("creativeIntent")) {
            putNullableText(body, payload, "creativeIntent", 4_000, false);
        }
        if (payload.has("targetDurationSeconds")) {
            putNullableInteger(body, payload, "targetDurationSeconds", 1, 86_400);
        }
        return VideoPayloads.request(context, "PATCH", episodePath(payload), body);
    }

    private static CommandResult reorderEpisodes(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "projectId",
                        "clientRequestId",
                        "expectedProjectRevision",
                        "episodeIds"));
        ArrayNode episodeIds =
                VideoPayloads.stringList(context, payload, "episodeIds", 1_000, true);
        if (episodeIds.isEmpty()) {
            throw new CliInputException("INVALID_FIELD", "episodeIds 不能为空");
        }
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedProjectRevision",
                VideoPayloads.integer(payload, "expectedProjectRevision", 1, null));
        body.set("episodeIds", episodeIds);
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/projects/" + id(payload, "projectId") + "/episodes/reorder",
                body);
    }

    private static CommandResult createSourceSet(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("episodeId", "clientRequestId", "expectedRevision"),
                Set.of("basedOnVersionId", "sources", "sourcesFile"),
                false);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedRevision",
                VideoPayloads.integer(payload, "expectedRevision", 1, null));
        putNullableText(body, payload, "basedOnVersionId", 128, true);
        body.set("sources", sourceSelections(context, payload));
        return VideoPayloads.request(
                context, "POST", episodePath(payload) + "/source-sets", body);
    }

    private static CommandResult listSourceSets(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId"), Set.of(), true);
        return VideoPayloads.get(context, episodePath(payload) + "/source-sets");
    }

    private static CommandResult getSourceSet(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload, Set.of("episodeId", "versionId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                episodePath(payload) + "/source-sets/" + id(payload, "versionId"));
    }

    private static CommandResult getScriptDraft(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId"), Set.of(), true);
        return VideoPayloads.get(context, episodePath(payload) + "/script/draft");
    }

    private static CommandResult saveScriptDraft(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "episodeId",
                        "clientRequestId",
                        "expectedRevision",
                        "sourceSetVersionId",
                        "baseScriptVersionId"),
                Set.of("document", "documentFile"),
                false);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedRevision",
                VideoPayloads.integer(payload, "expectedRevision", 1, null));
        putRequiredNullableIdentifier(body, payload, "sourceSetVersionId");
        putRequiredNullableIdentifier(body, payload, "baseScriptVersionId");
        body.set(
                "document",
                VideoPayloads.jsonSource(context, payload, "document", "documentFile"));
        return VideoPayloads.request(
                context, "PUT", episodePath(payload) + "/script/draft", body);
    }

    private static CommandResult startScriptRun(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "episodeId",
                        "clientRequestId",
                        "expectedDraftRevision",
                        "operation",
                        "instruction"),
                Set.of("selectedSceneIds"),
                false);
        String operation =
                VideoPayloads.enumeration(payload, "operation", SCRIPT_OPERATIONS, null);
        ArrayNode selectedSceneIds =
                VideoPayloads.stringList(context, payload, "selectedSceneIds", 60, true);
        if (operation.equals("episode_script_generate") && !selectedSceneIds.isEmpty()) {
            throw new CliInputException(
                    "INVALID_FIELD", "起草操作不能携带局部修订范围");
        }
        if (operation.equals("episode_script_revise") && selectedSceneIds.isEmpty()) {
            throw new CliInputException(
                    "INVALID_FIELD", "修订必须选择至少一个稳定场次");
        }
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedDraftRevision",
                VideoPayloads.integer(payload, "expectedDraftRevision", 1, null));
        body.put("operation", operation);
        body.set("selectedSceneIds", selectedSceneIds);
        body.put("instruction", VideoPayloads.string(payload, "instruction", 1, 8_000));
        return VideoPayloads.request(
                context, "POST", episodePath(payload) + "/script/runs", body);
    }

    private static CommandResult getScriptRun(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "runId"), Set.of(), true);
        return VideoPayloads.get(
                context, episodePath(payload) + "/script/runs/" + id(payload, "runId"));
    }

    private static CommandResult adoptScriptCandidate(
            CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "episodeId",
                        "artifactId",
                        "clientRequestId",
                        "expectedArtifactRevision",
                        "expectedDraftRevision"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedArtifactRevision",
                VideoPayloads.integer(payload, "expectedArtifactRevision", 1, null));
        body.put(
                "expectedDraftRevision",
                VideoPayloads.integer(payload, "expectedDraftRevision", 1, null));
        return VideoPayloads.request(
                context,
                "POST",
                episodePath(payload)
                        + "/script/candidates/"
                        + id(payload, "artifactId")
                        + "/adopt",
                body);
    }

    private static CommandResult prepareScriptConfirmation(
            CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "episodeId",
                        "clientRequestId",
                        "expectedDraftRevision",
                        "expectedEpisodeRevision"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedDraftRevision",
                VideoPayloads.integer(payload, "expectedDraftRevision", 1, null));
        body.put(
                "expectedEpisodeRevision",
                VideoPayloads.integer(payload, "expectedEpisodeRevision", 1, null));
        return VideoPayloads.request(
                context, "POST", episodePath(payload) + "/script/confirmations", body);
    }

    private static CommandResult getScriptConfirmation(
            CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload, Set.of("episodeId", "artifactId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                episodePath(payload)
                        + "/script/confirmations/"
                        + id(payload, "artifactId"));
    }

    private static CommandResult approveScriptConfirmation(
            CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "episodeId",
                        "artifactId",
                        "clientRequestId",
                        "expectedArtifactRevision",
                        "expectedDraftRevision",
                        "expectedEpisodeRevision",
                        "confirmationHash"));
        String confirmationHash = VideoPayloads.string(payload, "confirmationHash");
        if (!SHA256.matcher(confirmationHash).matches()) {
            throw new CliInputException(
                    "INVALID_FIELD", "confirmationHash 必须是小写 SHA-256");
        }
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedArtifactRevision",
                VideoPayloads.integer(payload, "expectedArtifactRevision", 1, null));
        body.put(
                "expectedDraftRevision",
                VideoPayloads.integer(payload, "expectedDraftRevision", 1, null));
        body.put(
                "expectedEpisodeRevision",
                VideoPayloads.integer(payload, "expectedEpisodeRevision", 1, null));
        body.put("confirmationHash", confirmationHash);
        return VideoPayloads.request(
                context,
                "POST",
                episodePath(payload)
                        + "/script/confirmations/"
                        + id(payload, "artifactId")
                        + "/approve",
                body);
    }

    private static CommandResult listScriptVersions(
            CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId"), Set.of(), true);
        return VideoPayloads.get(context, episodePath(payload) + "/script/versions");
    }

    private static CommandResult getScriptVersion(
            CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload, Set.of("episodeId", "versionId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                episodePath(payload) + "/script/versions/" + id(payload, "versionId"));
    }

    private static CommandResult getEpisodeCommand(
            CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload, Set.of("episodeId", "clientRequestId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                episodePath(payload)
                        + "/commands/"
                        + Payloads.segment(VideoPayloads.clientRequestId(payload)));
    }

    private static CommandResult getProjectEpisodeCommand(
            CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload, Set.of("projectId", "clientRequestId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                "/api/v1/video/projects/"
                        + id(payload, "projectId")
                        + "/episode-commands/"
                        + Payloads.segment(VideoPayloads.clientRequestId(payload)));
    }

    private static String episodePath(ObjectNode payload) {
        return "/api/v1/video/episodes/" + id(payload, "episodeId");
    }

    private static String id(ObjectNode payload, String name) {
        return Payloads.segment(VideoPayloads.string(payload, name));
    }

    private static String optionalText(
            ObjectNode payload,
            String name,
            String defaultValue,
            int maximum) {
        JsonNode value = payload.get(name);
        if (value == null) return defaultValue;
        if (!value.isTextual()) {
            throw new CliInputException("INVALID_FIELD", name + " 必须是字符串");
        }
        if (value.textValue().codePointCount(0, value.textValue().length()) > maximum) {
            throw new CliInputException(
                    "INVALID_FIELD", name + " 长度不能超过 " + maximum);
        }
        return value.textValue();
    }

    private static void putNullableText(
            ObjectNode body,
            ObjectNode payload,
            String name,
            int maximum,
            boolean nonEmpty) {
        JsonNode value = payload.get(name);
        if (value == null || value.isNull()) {
            body.putNull(name);
            return;
        }
        if (!value.isTextual() || nonEmpty && value.textValue().trim().isEmpty()) {
            throw new CliInputException(
                    "INVALID_FIELD",
                    name + " 必须是" + (nonEmpty ? "非空字符串或 null" : "字符串或 null"));
        }
        if (value.textValue().codePointCount(0, value.textValue().length()) > maximum) {
            throw new CliInputException(
                    "INVALID_FIELD", name + " 长度不能超过 " + maximum);
        }
        body.put(name, value.textValue());
    }

    private static void putRequiredNullableIdentifier(
            ObjectNode body, ObjectNode payload, String name) {
        JsonNode value = payload.get(name);
        if (value == null || value.isNull()) {
            body.putNull(name);
            return;
        }
        if (!value.isTextual()
                || value.textValue().trim().isEmpty()
                || value.textValue().codePointCount(0, value.textValue().length()) > 128) {
            throw new CliInputException(
                    "INVALID_FIELD", name + " 必须是非空字符串或 null");
        }
        body.put(name, value.textValue());
    }

    private static void putNullableInteger(
            ObjectNode body,
            ObjectNode payload,
            String name,
            int minimum,
            int maximum) {
        JsonNode value = payload.get(name);
        if (value == null || value.isNull()) {
            body.putNull(name);
            return;
        }
        body.put(name, VideoPayloads.integer(payload, name, minimum, maximum));
    }

    private static ArrayNode sourceSelections(
            CommandContext context, ObjectNode payload) {
        boolean inline = payload.has("sources");
        boolean file = payload.has("sourcesFile");
        if (inline == file) {
            throw new CliInputException(
                    "JSON_SOURCE_REQUIRED", "sources 与 sourcesFile 必须且只能提供一个");
        }
        JsonNode value;
        if (inline) {
            value = payload.get("sources");
        } else {
            String source = MutationPayloads.readUtf8(
                    VideoPayloads.string(payload, "sourcesFile"));
            try {
                value = context.dependencies().json().readTree(source);
            } catch (RuntimeException exception) {
                throw new LocalFileException("sourcesFile 不是有效 JSON", exception);
            }
        }
        if (!(value instanceof ArrayNode sources)
                || sources.isEmpty()
                || sources.size() > 40) {
            throw new CliInputException(
                    "INVALID_FIELD", "sources 必须包含 1 到 40 个来源");
        }
        Set<String> chapterIds = new HashSet<>();
        for (JsonNode raw : sources) {
            if (!(raw instanceof ObjectNode source)) {
                throw new CliInputException(
                        "INVALID_FIELD", "sources 每项必须是 JSON 对象");
            }
            if (!Set.copyOf(source.propertyNames())
                    .equals(Set.of("chapterId", "expectedUpdatedAt", "sourceHash", "ranges"))) {
                throw new CliInputException(
                        "INVALID_FIELD", "sources 项字段必须精确匹配公共契约");
            }
            String chapterId = VideoPayloads.string(source, "chapterId", 1, 128);
            if (!chapterIds.add(chapterId)) {
                throw new CliInputException(
                        "INVALID_FIELD", "sources 不能包含重复章节");
            }
            VideoPayloads.string(source, "expectedUpdatedAt");
            String sourceHash = VideoPayloads.string(source, "sourceHash");
            if (!SHA256.matcher(sourceHash).matches()) {
                throw new CliInputException(
                        "INVALID_FIELD", "sourceHash 必须是小写 SHA-256");
            }
            JsonNode rawRanges = source.get("ranges");
            if (!(rawRanges instanceof ArrayNode ranges)
                    || ranges.isEmpty()
                    || ranges.size() > 100) {
                throw new CliInputException(
                        "INVALID_FIELD", "ranges 必须包含 1 到 100 个范围");
            }
            for (JsonNode rawRange : ranges) {
                if (!(rawRange instanceof ObjectNode range)
                        || !Set.copyOf(range.propertyNames()).equals(Set.of("start", "end"))) {
                    throw new CliInputException(
                            "INVALID_FIELD", "ranges 项必须只包含 start 和 end");
                }
                JsonNode start = range.get("start");
                JsonNode end = range.get("end");
                if (start == null
                        || end == null
                        || !start.isIntegralNumber()
                        || !start.canConvertToInt()
                        || !end.isIntegralNumber()
                        || !end.canConvertToInt()
                        || start.intValue() < 0
                        || end.intValue() <= start.intValue()) {
                    throw new CliInputException(
                            "INVALID_FIELD", "ranges 必须是非空 Unicode 半开区间");
                }
            }
        }
        return sources.deepCopy();
    }
}
