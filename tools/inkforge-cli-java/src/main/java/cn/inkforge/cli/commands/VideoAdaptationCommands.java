package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import cn.inkforge.cli.transport.CoreApiException;
import java.util.Map;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 章节改编、镜头方案、分集和逐镜提示词命令。 */
final class VideoAdaptationCommands {

    private static final Set<String> PACING_PRESETS =
            Set.of("short_drama", "cinematic", "dialogue_driven");
    private static final Set<Integer> EPISODE_SECONDS = Set.of(60, 90, 120);

    private VideoAdaptationCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.video.adaptation.list", VideoAdaptationCommands::list);
        handlers.put("long.video.adaptation.get", VideoAdaptationCommands::get);
        handlers.put("long.video.adaptation.create", VideoAdaptationCommands::create);
        handlers.put("long.video.plan.start", VideoAdaptationCommands::startPlan);
        handlers.put("long.video.plan.confirm", VideoAdaptationCommands::confirmPlan);
        handlers.put("long.video.plan.discard", VideoAdaptationCommands::discardPlan);
        handlers.put("long.video.episode.save", VideoAdaptationCommands::saveEpisode);
        handlers.put("long.video.prompt.start", VideoAdaptationCommands::startPrompts);
        handlers.put("long.video.prompt.save", VideoAdaptationCommands::savePrompt);
    }

    private static CommandResult list(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("projectId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                "/api/v1/video/projects/"
                        + id(payload, "projectId")
                        + "/chapter-adaptations");
    }

    private static CommandResult get(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("adaptationId"), Set.of(), true);
        return VideoPayloads.get(context, adaptationPath(payload));
    }

    private static CommandResult create(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "projectId",
                        "chapterId",
                        "expectedChapterUpdatedAt",
                        "clientRequestId"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("chapterId", VideoPayloads.string(payload, "chapterId"));
        body.put(
                "expectedChapterUpdatedAt",
                VideoPayloads.string(payload, "expectedChapterUpdatedAt"));
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/projects/"
                        + id(payload, "projectId")
                        + "/chapter-adaptations",
                body);
    }

    private static CommandResult startPlan(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("adaptationId", "clientRequestId"),
                Set.of(
                        "pacingPreset",
                        "targetEpisodeSeconds",
                        "baseShotPlanVersionId",
                        "revisionBrief"),
                false);
        String baseVersion =
                VideoPayloads.optionalString(payload, "baseShotPlanVersionId", null);
        String revisionBrief =
                VideoPayloads.optionalString(payload, "revisionBrief", 1200);
        if (revisionBrief != null && baseVersion == null) {
            throw new CliInputException(
                    "REVISION_BASE_REQUIRED",
                    "没有正式镜头方案基线时不能提交修订重点");
        }
        int targetSeconds = payload.has("targetEpisodeSeconds")
                ? VideoPayloads.integer(payload, "targetEpisodeSeconds", null, null)
                : 90;
        if (!EPISODE_SECONDS.contains(targetSeconds)) {
            throw new CliInputException(
                    "INVALID_TARGET_EPISODE_SECONDS",
                    "targetEpisodeSeconds 必须是 60、90 或 120");
        }
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "pacingPreset",
                VideoPayloads.enumeration(
                        payload, "pacingPreset", PACING_PRESETS, "short_drama"));
        body.put("targetEpisodeSeconds", targetSeconds);
        if (baseVersion == null) body.putNull("baseShotPlanVersionId");
        else body.put("baseShotPlanVersionId", baseVersion);
        if (revisionBrief == null) body.putNull("revisionBrief");
        else body.put("revisionBrief", revisionBrief);
        return VideoPayloads.request(
                context,
                "POST",
                adaptationPath(payload) + "/shot-plan-runs",
                body);
    }

    private static CommandResult confirmPlan(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "adaptationId",
                        "clientRequestId",
                        "expectedArtifactRevision",
                        "expectedAdaptationRevision"),
                Set.of("plan", "planFile"),
                false);
        String adaptationId = VideoPayloads.string(payload, "adaptationId");
        int artifactRevision =
                VideoPayloads.integer(payload, "expectedArtifactRevision", 1, null);
        int adaptationRevision =
                VideoPayloads.integer(payload, "expectedAdaptationRevision", 1, null);
        ObjectNode plan = VideoPayloads.jsonSource(
                context, payload, "plan", "planFile");
        preflight(
                adaptation(context, adaptationId), artifactRevision, adaptationRevision, context);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedArtifactRevision", artifactRevision);
        body.put("expectedAdaptationRevision", adaptationRevision);
        body.set("plan", plan);
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/chapter-adaptations/"
                        + Payloads.segment(adaptationId)
                        + "/shot-plan/confirm",
                body);
    }

    private static CommandResult discardPlan(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "adaptationId",
                        "clientRequestId",
                        "expectedArtifactRevision",
                        "expectedAdaptationRevision"));
        String adaptationId = VideoPayloads.string(payload, "adaptationId");
        int artifactRevision =
                VideoPayloads.integer(payload, "expectedArtifactRevision", 1, null);
        int adaptationRevision =
                VideoPayloads.integer(payload, "expectedAdaptationRevision", 1, null);
        preflight(
                adaptation(context, adaptationId), artifactRevision, adaptationRevision, context);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("expectedArtifactRevision", artifactRevision);
        body.put("expectedAdaptationRevision", adaptationRevision);
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/chapter-adaptations/"
                        + Payloads.segment(adaptationId)
                        + "/candidate/discard",
                body);
    }

    private static CommandResult saveEpisode(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "adaptationId",
                        "clientRequestId",
                        "expectedAdaptationRevision",
                        "shotPlanVersionId",
                        "breakAfterShotIds"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedAdaptationRevision",
                VideoPayloads.integer(payload, "expectedAdaptationRevision", 1, null));
        body.put("shotPlanVersionId", VideoPayloads.string(payload, "shotPlanVersionId"));
        body.set(
                "breakAfterShotIds",
                VideoPayloads.stringList(
                        context, payload, "breakAfterShotIds", 119, true));
        return VideoPayloads.request(
                context, "PUT", adaptationPath(payload) + "/episode-plan", body);
    }

    private static CommandResult startPrompts(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "adaptationId",
                        "clientRequestId",
                        "expectedAdaptationRevision",
                        "shotPlanVersionId"),
                Set.of("shotIds"),
                false);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedAdaptationRevision",
                VideoPayloads.integer(payload, "expectedAdaptationRevision", 1, null));
        body.put("shotPlanVersionId", VideoPayloads.string(payload, "shotPlanVersionId"));
        body.set(
                "shotIds",
                VideoPayloads.stringList(context, payload, "shotIds", 120, true));
        return VideoPayloads.request(
                context, "POST", adaptationPath(payload) + "/prompt-runs", body);
    }

    private static CommandResult savePrompt(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("adaptationId", "shotId", "expectedPromptRevision"),
                Set.of("candidateTaskId", "currentPrompt", "currentPromptFile"),
                false);
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put(
                "expectedPromptRevision",
                VideoPayloads.integer(payload, "expectedPromptRevision", 1, null));
        String candidateTaskId =
                VideoPayloads.optionalString(payload, "candidateTaskId", null);
        if (candidateTaskId == null) body.putNull("candidateTaskId");
        else body.put("candidateTaskId", candidateTaskId);
        body.put(
                "currentPrompt",
                VideoPayloads.textSource(
                        payload, "currentPrompt", "currentPromptFile", 2000));
        return VideoPayloads.request(
                context,
                "PUT",
                adaptationPath(payload)
                        + "/shots/"
                        + id(payload, "shotId")
                        + "/prompt",
                body);
    }

    static ObjectNode adaptation(CommandContext context, String adaptationId) {
        return VideoPayloads.object(
                context.requireApi().request(
                        "GET",
                        "/api/v1/video/chapter-adaptations/"
                                + Payloads.segment(adaptationId)),
                "章节影视化响应不是 JSON 对象");
    }

    private static void preflight(
            ObjectNode snapshot,
            int artifactRevision,
            int adaptationRevision,
            CommandContext context) {
        JsonNode currentRevision = snapshot.get("headRevision");
        if (currentRevision == null
                || !currentRevision.isIntegralNumber()
                || currentRevision.intValue() != adaptationRevision) {
            ObjectNode details = context.dependencies().json().createObjectNode();
            if (currentRevision == null) details.putNull("currentRevision");
            else details.set("currentRevision", currentRevision.deepCopy());
            throw conflict(
                    "VIDEO_ADAPTATION_REVISION_CONFLICT",
                    "改编 revision 已变化，请重新读取并确认候选",
                    details);
        }
        if (!(snapshot.get("reviewArtifact") instanceof ObjectNode review)
                || !(snapshot.get("candidatePlan") instanceof ObjectNode)) {
            throw conflict(
                    "VIDEO_ADAPTATION_CANDIDATE_MISSING",
                    "当前没有可确认或丢弃的完整镜头候选",
                    null);
        }
        JsonNode currentArtifactRevision = review.get("revision");
        if (currentArtifactRevision == null
                || !currentArtifactRevision.isIntegralNumber()
                || currentArtifactRevision.intValue() != artifactRevision) {
            ObjectNode details = context.dependencies().json().createObjectNode();
            if (currentArtifactRevision == null) details.putNull("currentRevision");
            else details.set("currentRevision", currentArtifactRevision.deepCopy());
            throw conflict(
                    "VIDEO_ARTIFACT_REVISION_CONFLICT",
                    "候选 revision 已变化，请重新读取并确认完整候选",
                    details);
        }
        JsonNode status = review.get("status");
        if (status == null || !status.isTextual() || !status.textValue().equals("awaiting_user")) {
            ObjectNode details = context.dependencies().json().createObjectNode();
            if (status == null) details.putNull("status");
            else details.set("status", status.deepCopy());
            throw conflict(
                    "VIDEO_ADAPTATION_CANDIDATE_NOT_REVIEWABLE",
                    "当前候选不处于等待用户确认状态",
                    details);
        }
    }

    private static CoreApiException conflict(
            String code, String message, JsonNode details) {
        return new CoreApiException(409, code, message, details, null);
    }

    private static String adaptationPath(ObjectNode payload) {
        return "/api/v1/video/chapter-adaptations/" + id(payload, "adaptationId");
    }

    private static String id(ObjectNode payload, String field) {
        return Payloads.segment(VideoPayloads.string(payload, field));
    }
}
