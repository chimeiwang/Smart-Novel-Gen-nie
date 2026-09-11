package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import cn.inkforge.cli.runtime.LocalFileException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 独立分集 P2/P3 制作、后期与交付命令。 */
final class VideoEpisodeProductionCommands {

    private static final Pattern SHA256 = Pattern.compile("^[0-9a-f]{64}$");
    private static final Set<String> STORYBOARD_OPERATIONS =
            Set.of("episode_storyboard_generate", "episode_storyboard_revise");
    private static final Set<String> IMPACT_STATUSES = Set.of("pending", "resolved");
    private static final Set<String> IMPACT_ACTIONS =
            Set.of("keep_existing", "revise_target", "not_applicable", "defer");

    private VideoEpisodeProductionCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.video.production.capabilities.get", VideoEpisodeProductionCommands::getCapabilities);
        handlers.put("long.video.episode.storyboard.draft.get", VideoEpisodeProductionCommands::getStoryboardDraft);
        handlers.put("long.video.episode.storyboard.draft.save", VideoEpisodeProductionCommands::saveStoryboardDraft);
        handlers.put("long.video.episode.storyboard.run.start", VideoEpisodeProductionCommands::startStoryboardRun);
        handlers.put("long.video.episode.storyboard.run.list", VideoEpisodeProductionCommands::listStoryboardRuns);
        handlers.put("long.video.episode.storyboard.run.get", VideoEpisodeProductionCommands::getStoryboardRun);
        handlers.put("long.video.episode.storyboard.candidate.get", VideoEpisodeProductionCommands::getStoryboardCandidate);
        handlers.put("long.video.episode.storyboard.candidate.adopt", VideoEpisodeProductionCommands::adoptStoryboardCandidate);
        handlers.put("long.video.episode.storyboard.confirmation.prepare", VideoEpisodeProductionCommands::prepareStoryboardConfirmation);
        handlers.put("long.video.episode.storyboard.confirmation.get", VideoEpisodeProductionCommands::getStoryboardConfirmation);
        handlers.put("long.video.episode.storyboard.confirmation.approve", VideoEpisodeProductionCommands::approveStoryboardConfirmation);
        handlers.put("long.video.episode.storyboard.version.list", VideoEpisodeProductionCommands::listStoryboardVersions);
        handlers.put("long.video.episode.storyboard.version.get", VideoEpisodeProductionCommands::getStoryboardVersion);
        handlers.put("long.video.episode.take.list", VideoEpisodeProductionCommands::listTakes);
        handlers.put("long.video.episode.take.download", VideoEpisodeProductionCommands::downloadTake);
        handlers.put("long.video.episode.adoption.create", VideoEpisodeProductionCommands::createAdoption);
        handlers.put("long.video.episode.adoption.get", VideoEpisodeProductionCommands::getAdoption);
        handlers.put("long.video.episode.baseline.create", VideoEpisodeProductionCommands::createBaseline);
        handlers.put("long.video.episode.baseline.list", VideoEpisodeProductionCommands::listBaselines);
        handlers.put("long.video.episode.baseline.get", VideoEpisodeProductionCommands::getBaseline);
        handlers.put("long.video.episode.impact.list", VideoEpisodeProductionCommands::listImpacts);
        handlers.put("long.video.episode.impact.get", VideoEpisodeProductionCommands::getImpact);
        handlers.put("long.video.episode.impact.decide", VideoEpisodeProductionCommands::decideImpact);
        handlers.put("long.video.episode.render.start", VideoEpisodeProductionCommands::startRender);
        handlers.put("long.video.episode.render.get", VideoEpisodeProductionCommands::getRender);
        handlers.put("long.video.episode.render.retry", VideoEpisodeProductionCommands::retryRender);
        handlers.put("long.video.episode.edit.create", VideoEpisodeProductionCommands::createEdit);
        handlers.put("long.video.episode.edit.list", VideoEpisodeProductionCommands::listEdits);
        handlers.put("long.video.episode.edit.get", VideoEpisodeProductionCommands::getEdit);
        handlers.put("long.video.episode.mix.create", VideoEpisodeProductionCommands::createMix);
        handlers.put("long.video.episode.mix.list", VideoEpisodeProductionCommands::listMixes);
        handlers.put("long.video.episode.mix.get", VideoEpisodeProductionCommands::getMix);
        handlers.put("long.video.episode.export.start", VideoEpisodeProductionCommands::startExport);
        handlers.put("long.video.episode.export.get", VideoEpisodeProductionCommands::getExport);
        handlers.put("long.video.episode.export.retry", VideoEpisodeProductionCommands::retryExport);
        handlers.put("long.video.episode.delivery.get", VideoEpisodeProductionCommands::getDelivery);
        handlers.put("long.video.episode.delivery.download", VideoEpisodeProductionCommands::downloadDelivery);
    }

    private static CommandResult getCapabilities(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of(), Set.of(), true);
        return VideoPayloads.get(context, "/api/v1/video/production-capabilities");
    }

    private static CommandResult getStoryboardDraft(CommandContext context, ObjectNode payload) {
        readFields(payload, "episodeId");
        return VideoPayloads.get(context, episodePath(payload) + "/storyboard/draft");
    }

    private static CommandResult saveStoryboardDraft(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("episodeId", "clientRequestId", "expectedRevision", "scriptVersionId", "baseStoryboardVersionId"),
                Set.of("document", "documentFile"),
                false);
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedRevision", VideoPayloads.integer(payload, "expectedRevision", 1, null));
        body.put("scriptVersionId", VideoPayloads.string(payload, "scriptVersionId", 1, 128));
        putNullableIdentifier(body, payload, "baseStoryboardVersionId", true);
        body.set("document", VideoPayloads.jsonSource(context, payload, "document", "documentFile"));
        return VideoPayloads.request(context, "PUT", episodePath(payload) + "/storyboard/draft", body);
    }

    private static CommandResult startStoryboardRun(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("episodeId", "clientRequestId", "expectedDraftRevision", "scriptVersionId", "operation", "instruction"),
                Set.of("selectedShotIds"),
                false);
        String operation = VideoPayloads.enumeration(payload, "operation", STORYBOARD_OPERATIONS, null);
        ArrayNode selected = VideoPayloads.stringList(context, payload, "selectedShotIds", 300, true);
        if (operation.equals("episode_storyboard_generate") && !selected.isEmpty()) {
            throw invalid("分镜起草不能携带局部修订范围");
        }
        if (operation.equals("episode_storyboard_revise") && selected.isEmpty()) {
            throw invalid("分镜修订必须选择至少一个稳定镜头");
        }
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedDraftRevision", VideoPayloads.integer(payload, "expectedDraftRevision", 1, null));
        body.put("scriptVersionId", VideoPayloads.string(payload, "scriptVersionId", 1, 128));
        body.put("operation", operation);
        body.set("selectedShotIds", selected);
        body.put("instruction", VideoPayloads.string(payload, "instruction", 1, 8_000));
        return VideoPayloads.request(context, "POST", episodePath(payload) + "/storyboard/runs", body);
    }

    private static CommandResult listStoryboardRuns(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId"), Set.of("limit", "beforeRunId"), true);
        return VideoPayloads.get(context, episodePath(payload) + "/storyboard/runs" + pageQuery(payload, 50, "beforeRunId"));
    }

    private static CommandResult getStoryboardRun(CommandContext context, ObjectNode payload) {
        readFields(payload, "episodeId", "runId");
        return VideoPayloads.get(context, episodePath(payload) + "/storyboard/runs/" + id(payload, "runId"));
    }

    private static CommandResult getStoryboardCandidate(CommandContext context, ObjectNode payload) {
        readFields(payload, "episodeId", "artifactId");
        return VideoPayloads.get(context, episodePath(payload) + "/storyboard/candidates/" + id(payload, "artifactId"));
    }

    private static CommandResult adoptStoryboardCandidate(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "artifactId", "clientRequestId", "expectedArtifactRevision", "expectedDraftRevision"));
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedArtifactRevision", VideoPayloads.integer(payload, "expectedArtifactRevision", 1, null));
        body.put("expectedDraftRevision", VideoPayloads.integer(payload, "expectedDraftRevision", 1, null));
        return VideoPayloads.request(context, "POST", episodePath(payload) + "/storyboard/candidates/" + id(payload, "artifactId") + "/adopt", body);
    }

    private static CommandResult prepareStoryboardConfirmation(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "clientRequestId", "expectedDraftRevision", "expectedEpisodeRevision"));
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedDraftRevision", VideoPayloads.integer(payload, "expectedDraftRevision", 1, null));
        body.put("expectedEpisodeRevision", VideoPayloads.integer(payload, "expectedEpisodeRevision", 1, null));
        return VideoPayloads.request(context, "POST", episodePath(payload) + "/storyboard/confirmations", body);
    }

    private static CommandResult getStoryboardConfirmation(CommandContext context, ObjectNode payload) {
        readFields(payload, "episodeId", "artifactId");
        return VideoPayloads.get(context, episodePath(payload) + "/storyboard/confirmations/" + id(payload, "artifactId"));
    }

    private static CommandResult approveStoryboardConfirmation(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "artifactId", "clientRequestId", "expectedArtifactRevision", "expectedDraftRevision", "expectedEpisodeRevision", "confirmationHash"));
        String confirmationHash = sha256(payload, "confirmationHash");
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedArtifactRevision", VideoPayloads.integer(payload, "expectedArtifactRevision", 1, null));
        body.put("expectedDraftRevision", VideoPayloads.integer(payload, "expectedDraftRevision", 1, null));
        body.put("expectedEpisodeRevision", VideoPayloads.integer(payload, "expectedEpisodeRevision", 1, null));
        body.put("confirmationHash", confirmationHash);
        return VideoPayloads.request(context, "POST", episodePath(payload) + "/storyboard/confirmations/" + id(payload, "artifactId") + "/approve", body);
    }

    private static CommandResult listStoryboardVersions(CommandContext context, ObjectNode payload) {
        return listEpisodeVersions(context, payload, "storyboard/versions");
    }

    private static CommandResult getStoryboardVersion(CommandContext context, ObjectNode payload) {
        readFields(payload, "episodeId", "versionId");
        return VideoPayloads.get(context, episodePath(payload) + "/storyboard/versions/" + id(payload, "versionId"));
    }

    private static CommandResult listTakes(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "targetShotVersionId"), Set.of("limit", "beforeTakeId"), true);
        StringBuilder query = new StringBuilder("?targetShotVersionId=")
                .append(queryValue(VideoPayloads.string(payload, "targetShotVersionId", 1, 128)))
                .append("&limit=").append(limit(payload, 100));
        String before = VideoPayloads.optionalString(payload, "beforeTakeId", 128);
        if (before != null) query.append("&beforeTakeId=").append(queryValue(before));
        return VideoPayloads.get(context, episodePath(payload) + "/takes" + query);
    }

    private static CommandResult downloadTake(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "takeId", "outputFile"), Set.of(), true);
        return VideoPayloads.download(context, payload, "takeId", episodePath(payload) + "/takes/" + id(payload, "takeId") + "/content");
    }

    private static CommandResult createAdoption(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("episodeId", "clientRequestId", "expectedProductionRevision", "targetShotVersionId", "sourceTakeId", "sourceBaselineId"),
                Set.of("comparison", "comparisonFile"),
                false);
        ObjectNode comparison = VideoPayloads.jsonSource(context, payload, "comparison", "comparisonFile");
        requireExactFields(comparison, Set.of("sourceBaselineId", "targetShotVersionId", "directInputsUnchanged", "referenceHashesChecked", "summary"), "comparison");
        String sourceBaseline = VideoPayloads.string(payload, "sourceBaselineId", 1, 128);
        String targetShot = VideoPayloads.string(payload, "targetShotVersionId", 1, 128);
        if (!sourceBaseline.equals(VideoPayloads.string(comparison, "sourceBaselineId", 1, 128))
                || !targetShot.equals(VideoPayloads.string(comparison, "targetShotVersionId", 1, 128))) {
            throw invalid("comparison 的源基线或目标镜头版本与请求不一致");
        }
        JsonNode direct = comparison.get("directInputsUnchanged");
        if (direct == null || !direct.isBoolean()) throw invalid("directInputsUnchanged 必须是布尔值");
        ArrayNode hashes = array(comparison, "referenceHashesChecked", 0, 20);
        for (JsonNode hash : hashes) {
            if (!hash.isTextual() || !SHA256.matcher(hash.textValue()).matches()) {
                throw invalid("referenceHashesChecked 必须是小写 SHA-256 数组");
            }
        }
        VideoPayloads.string(comparison, "summary", 1, 4_000);
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedProductionRevision", VideoPayloads.integer(payload, "expectedProductionRevision", 1, null));
        body.put("targetShotVersionId", targetShot);
        body.put("sourceTakeId", VideoPayloads.string(payload, "sourceTakeId", 1, 128));
        body.put("sourceBaselineId", sourceBaseline);
        body.set("comparison", comparison);
        return VideoPayloads.request(context, "POST", episodePath(payload) + "/take-adoptions", body);
    }

    private static CommandResult getAdoption(CommandContext context, ObjectNode payload) {
        readFields(payload, "episodeId", "adoptionId");
        return VideoPayloads.get(context, episodePath(payload) + "/take-adoptions/" + id(payload, "adoptionId"));
    }

    private static CommandResult createBaseline(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("episodeId", "clientRequestId", "expectedEpisodeRevision", "expectedProductionRevision", "basedOnBaselineId", "scriptVersionId", "storyboardVersionId"),
                Set.of("shotAdoptions", "shotAdoptionsFile", "keyframes", "keyframesFile"),
                false);
        ArrayNode adoptions = arraySource(context, payload, "shotAdoptions", "shotAdoptionsFile", 0, 300, true);
        Set<String> shots = new HashSet<>();
        for (JsonNode raw : adoptions) {
            if (!(raw instanceof ObjectNode item)) throw invalid("shotAdoptions 每项必须是对象");
            requireExactFields(item, Set.of("shotVersionId", "adoptionId"), "shotAdoptions");
            String shot = VideoPayloads.string(item, "shotVersionId", 1, 128);
            VideoPayloads.string(item, "adoptionId", 1, 128);
            if (!shots.add(shot)) throw invalid("shotAdoptions 不能重复镜头版本");
        }
        ArrayNode keyframes = arraySource(context, payload, "keyframes", "keyframesFile", 0, 900, true);
        Set<String> keyframeKeys = new HashSet<>();
        for (JsonNode raw : keyframes) {
            if (!(raw instanceof ObjectNode item)) throw invalid("keyframes 每项必须是对象");
            requireExactFields(item, Set.of("shotVersionId", "role", "assetId"), "keyframes");
            String shotVersionId = VideoPayloads.string(item, "shotVersionId", 1, 128);
            String role = VideoPayloads.enumeration(
                    item,
                    "role",
                    Set.of("initial_state", "transition_anchor", "end_state"),
                    null);
            VideoPayloads.string(item, "assetId", 1, 128);
            if (!keyframeKeys.add(shotVersionId + "\n" + role)) {
                throw invalid("keyframes 不能重复镜头版本与角色");
            }
        }
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedEpisodeRevision", VideoPayloads.integer(payload, "expectedEpisodeRevision", 1, null));
        body.put("expectedProductionRevision", VideoPayloads.integer(payload, "expectedProductionRevision", 1, null));
        putNullableIdentifier(body, payload, "basedOnBaselineId", true);
        body.put("scriptVersionId", VideoPayloads.string(payload, "scriptVersionId", 1, 128));
        body.put("storyboardVersionId", VideoPayloads.string(payload, "storyboardVersionId", 1, 128));
        body.set("shotAdoptions", adoptions);
        body.set("keyframes", keyframes);
        return VideoPayloads.request(context, "POST", episodePath(payload) + "/production-baselines", body);
    }

    private static CommandResult listBaselines(CommandContext context, ObjectNode payload) {
        return listEpisodeVersions(context, payload, "production-baselines");
    }

    private static CommandResult getBaseline(CommandContext context, ObjectNode payload) {
        readFields(payload, "episodeId", "baselineId");
        return VideoPayloads.get(context, baselinePath(payload));
    }

    private static CommandResult listImpacts(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId"), Set.of("status", "limit", "beforeReviewId"), true);
        StringBuilder query = new StringBuilder("?");
        if (payload.hasNonNull("status")) {
            query.append("status=").append(queryValue(VideoPayloads.enumeration(payload, "status", IMPACT_STATUSES, null))).append('&');
        }
        query.append("limit=").append(limit(payload, 100));
        String before = VideoPayloads.optionalString(payload, "beforeReviewId", 128);
        if (before != null) query.append("&beforeReviewId=").append(queryValue(before));
        return VideoPayloads.get(context, episodePath(payload) + "/impact-reviews" + query);
    }

    private static CommandResult getImpact(CommandContext context, ObjectNode payload) {
        readFields(payload, "episodeId", "reviewId");
        return VideoPayloads.get(context, episodePath(payload) + "/impact-reviews/" + id(payload, "reviewId"));
    }

    private static CommandResult decideImpact(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "reviewId", "clientRequestId", "expectedRevision"), Set.of("decisions", "decisionsFile"), false);
        ArrayNode decisions = arraySource(context, payload, "decisions", "decisionsFile", 1, 500, false);
        Set<String> items = new HashSet<>();
        for (JsonNode raw : decisions) {
            if (!(raw instanceof ObjectNode item)) throw invalid("decisions 每项必须是对象");
            Set<String> names = Set.copyOf(item.propertyNames());
            if (!names.containsAll(Set.of("itemId", "action")) || !Set.of("itemId", "action", "note").containsAll(names)) {
                throw invalid("decisions 项字段必须精确匹配公共契约");
            }
            String itemId = VideoPayloads.string(item, "itemId", 1, 128);
            if (!items.add(itemId)) throw invalid("decisions 不能重复影响项");
            String action = VideoPayloads.enumeration(item, "action", IMPACT_ACTIONS, null);
            String note = item.has("note") ? text(item, "note", 0, 4_000) : "";
            if (!action.equals("defer") && note.trim().isEmpty()) throw invalid("影响决定必须包含有效依据");
            item.put("note", note);
        }
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedRevision", VideoPayloads.integer(payload, "expectedRevision", 1, null));
        body.set("decisions", decisions);
        return VideoPayloads.request(context, "POST", episodePath(payload) + "/impact-reviews/" + id(payload, "reviewId") + "/decisions", body);
    }

    private static CommandResult startRender(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "baselineId", "shotId", "clientRequestId"), Set.of("feeConfirmed"), false);
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("feeConfirmed", VideoPayloads.optionalBoolean(payload, "feeConfirmed", false));
        return VideoPayloads.request(context, "POST", baselinePath(payload) + "/shots/" + id(payload, "shotId") + "/render-tasks", body);
    }

    private static CommandResult getRender(CommandContext context, ObjectNode payload) {
        readFields(payload, "episodeId", "taskId");
        return VideoPayloads.get(context, episodePath(payload) + "/render-tasks/" + id(payload, "taskId"));
    }

    private static CommandResult retryRender(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "taskId", "clientRequestId"), Set.of("feeConfirmed"), false);
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("feeConfirmed", VideoPayloads.optionalBoolean(payload, "feeConfirmed", false));
        return VideoPayloads.request(context, "POST", episodePath(payload) + "/render-tasks/" + id(payload, "taskId") + "/retry", body);
    }

    private static CommandResult createEdit(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "baselineId", "clientRequestId", "expectedHeadRevision", "basedOnVersionId"), Set.of("edit", "editFile"), false);
        ObjectNode edit = VideoPayloads.jsonSource(context, payload, "edit", "editFile");
        requireExactFields(edit, Set.of("clips", "omissions"), "edit");
        ArrayNode clips = array(edit, "clips", 1, 500);
        ArrayNode omissions = array(edit, "omissions", 0, 300);
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedHeadRevision", VideoPayloads.integer(payload, "expectedHeadRevision", 1, null));
        putNullableIdentifier(body, payload, "basedOnVersionId", true);
        body.set("clips", clips.deepCopy());
        body.set("omissions", omissions.deepCopy());
        return VideoPayloads.request(context, "POST", baselinePath(payload) + "/edit-versions", body);
    }

    private static CommandResult listEdits(CommandContext context, ObjectNode payload) {
        return listPostVersions(context, payload, "edit-versions");
    }

    private static CommandResult getEdit(CommandContext context, ObjectNode payload) {
        return getPostVersion(context, payload, "edit-versions");
    }

    private static CommandResult createMix(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "baselineId", "clientRequestId", "expectedHeadRevision", "basedOnVersionId", "editVersionId"), Set.of("mix", "mixFile"), false);
        ObjectNode mix = VideoPayloads.jsonSource(context, payload, "mix", "mixFile");
        requireExactFields(mix, Set.of("audioClips", "subtitleCues"), "mix");
        ArrayNode audio = array(mix, "audioClips", 0, 1_000);
        ArrayNode subtitles = array(mix, "subtitleCues", 0, 2_000);
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedHeadRevision", VideoPayloads.integer(payload, "expectedHeadRevision", 1, null));
        putNullableIdentifier(body, payload, "basedOnVersionId", true);
        body.put("editVersionId", VideoPayloads.string(payload, "editVersionId", 1, 128));
        body.set("audioClips", audio.deepCopy());
        body.set("subtitleCues", subtitles.deepCopy());
        return VideoPayloads.request(context, "POST", baselinePath(payload) + "/mix-versions", body);
    }

    private static CommandResult listMixes(CommandContext context, ObjectNode payload) {
        return listPostVersions(context, payload, "mix-versions");
    }

    private static CommandResult getMix(CommandContext context, ObjectNode payload) {
        return getPostVersion(context, payload, "mix-versions");
    }

    private static CommandResult startExport(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "baselineId", "clientRequestId", "editVersionId", "mixVersionId"), Set.of("resolution", "framesPerSecond", "burnSubtitles"), false);
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("editVersionId", VideoPayloads.string(payload, "editVersionId", 1, 128));
        body.put("mixVersionId", VideoPayloads.string(payload, "mixVersionId", 1, 128));
        body.put("resolution", VideoPayloads.enumeration(payload, "resolution", Set.of("720p", "1080p"), "720p"));
        body.put("framesPerSecond", VideoPayloads.enumInteger(payload, "framesPerSecond", Set.of(24, 25, 30), 24));
        body.put("burnSubtitles", VideoPayloads.optionalBoolean(payload, "burnSubtitles", true));
        return VideoPayloads.request(context, "POST", baselinePath(payload) + "/export-tasks", body);
    }

    private static CommandResult getExport(CommandContext context, ObjectNode payload) {
        readFields(payload, "episodeId", "baselineId", "taskId");
        return VideoPayloads.get(context, baselinePath(payload) + "/export-tasks/" + id(payload, "taskId"));
    }

    private static CommandResult retryExport(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "baselineId", "taskId", "clientRequestId"));
        ObjectNode body = object(context);
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        return VideoPayloads.request(context, "POST", baselinePath(payload) + "/export-tasks/" + id(payload, "taskId") + "/retry", body);
    }

    private static CommandResult getDelivery(CommandContext context, ObjectNode payload) {
        readFields(payload, "episodeId", "baselineId", "exportId");
        return VideoPayloads.get(context, baselinePath(payload) + "/exports/" + id(payload, "exportId"));
    }

    private static CommandResult downloadDelivery(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("episodeId", "baselineId", "exportId", "outputFile"), Set.of(), true);
        return VideoPayloads.download(context, payload, "exportId", baselinePath(payload) + "/exports/" + id(payload, "exportId") + "/content");
    }

    private static CommandResult listEpisodeVersions(CommandContext context, ObjectNode payload, String suffix) {
        VideoPayloads.fields(payload, Set.of("episodeId"), Set.of("limit", "beforeVersionNo"), true);
        return VideoPayloads.get(context, episodePath(payload) + "/" + suffix + pageQuery(payload, 100, "beforeVersionNo"));
    }

    private static CommandResult listPostVersions(CommandContext context, ObjectNode payload, String suffix) {
        VideoPayloads.fields(payload, Set.of("episodeId", "baselineId"), Set.of("limit", "beforeVersionNo"), true);
        return VideoPayloads.get(context, baselinePath(payload) + "/" + suffix + pageQuery(payload, 100, "beforeVersionNo"));
    }

    private static CommandResult getPostVersion(CommandContext context, ObjectNode payload, String suffix) {
        readFields(payload, "episodeId", "baselineId", "versionId");
        return VideoPayloads.get(context, baselinePath(payload) + "/" + suffix + "/" + id(payload, "versionId"));
    }

    private static String pageQuery(ObjectNode payload, int maximum, String cursor) {
        StringBuilder query = new StringBuilder("?limit=").append(limit(payload, maximum));
        if (payload.hasNonNull(cursor)) {
            query.append('&').append(cursor).append('=');
            if (cursor.equals("beforeVersionNo")) {
                query.append(VideoPayloads.integer(payload, cursor, 1, null));
            } else {
                query.append(queryValue(VideoPayloads.string(payload, cursor, 1, 128)));
            }
        }
        return query.toString();
    }

    private static int limit(ObjectNode payload, int maximum) {
        return payload.has("limit") ? VideoPayloads.integer(payload, "limit", 1, maximum) : 20;
    }

    private static String episodePath(ObjectNode payload) {
        return "/api/v1/video/episodes/" + id(payload, "episodeId");
    }

    private static String baselinePath(ObjectNode payload) {
        return episodePath(payload) + "/production-baselines/" + id(payload, "baselineId");
    }

    private static String id(ObjectNode payload, String name) {
        return Payloads.segment(VideoPayloads.string(payload, name, 1, 128));
    }

    private static String queryValue(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }

    private static ObjectNode object(CommandContext context) {
        return context.dependencies().json().createObjectNode();
    }

    private static void readFields(ObjectNode payload, String... names) {
        VideoPayloads.fields(payload, Set.of(names), Set.of(), true);
    }

    private static void putNullableIdentifier(ObjectNode body, ObjectNode payload, String name, boolean required) {
        if (required && !payload.has(name)) throw new CliInputException("FIELD_REQUIRED", "命令缺少字段：" + name);
        String value = VideoPayloads.optionalString(payload, name, 128);
        if (value == null) body.putNull(name); else body.put(name, value);
    }

    private static String sha256(ObjectNode payload, String name) {
        String value = VideoPayloads.string(payload, name);
        if (!SHA256.matcher(value).matches()) throw invalid(name + " 必须是小写 SHA-256");
        return value;
    }

    private static void requireExactFields(ObjectNode value, Set<String> fields, String name) {
        if (!Set.copyOf(value.propertyNames()).equals(fields)) throw invalid(name + " 字段必须精确匹配公共契约");
    }

    private static ArrayNode array(ObjectNode value, String name, int minimum, int maximum) {
        JsonNode raw = value.get(name);
        if (!(raw instanceof ArrayNode array) || array.size() < minimum || array.size() > maximum) {
            throw invalid(name + " 数量无效");
        }
        return array;
    }

    private static ArrayNode arraySource(
            CommandContext context,
            ObjectNode payload,
            String inline,
            String fileField,
            int minimum,
            int maximum,
            boolean defaultEmpty) {
        boolean hasInline = payload.has(inline);
        boolean hasFile = payload.has(fileField);
        if (!hasInline && !hasFile && defaultEmpty) return context.dependencies().json().createArrayNode();
        if (hasInline == hasFile) throw new CliInputException("JSON_SOURCE_REQUIRED", inline + " 与 " + fileField + " 必须且只能提供一个");
        JsonNode value;
        if (hasInline) {
            value = payload.get(inline);
        } else {
            try {
                value = context.dependencies().json().readTree(MutationPayloads.readUtf8(VideoPayloads.string(payload, fileField)));
            } catch (RuntimeException exception) {
                throw new LocalFileException(fileField + " 不是有效 JSON", exception);
            }
        }
        if (!(value instanceof ArrayNode array) || array.size() < minimum || array.size() > maximum) throw invalid(inline + " 数量无效");
        return array.deepCopy();
    }

    private static String text(ObjectNode value, String name, int minimum, int maximum) {
        JsonNode raw = value.get(name);
        if (raw == null || !raw.isTextual()) throw invalid(name + " 必须是字符串");
        int length = raw.textValue().codePointCount(0, raw.textValue().length());
        if (length < minimum || length > maximum) throw invalid(name + " 长度无效");
        return raw.textValue();
    }

    private static CliInputException invalid(String message) {
        return new CliInputException("INVALID_FIELD", message);
    }
}
