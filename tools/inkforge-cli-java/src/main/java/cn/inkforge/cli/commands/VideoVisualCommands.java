package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CliInputException;
import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.runtime.CommandHandler;
import cn.inkforge.cli.runtime.CommandResult;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 视觉设定候选、批准版本与逐镜参考绑定命令。 */
final class VideoVisualCommands {

    private static final Set<String> SETTING_KINDS = Set.of("character", "location", "item");
    private static final Set<String> CANON_DUTIES = Set.of("identity", "costume", "scene", "prop");
    private static final Map<String, String> EXPECTED_KIND = Map.of(
            "identity", "character",
            "costume", "character",
            "scene", "location",
            "prop", "item");
    private static final Pattern VARIANT_KEY =
            Pattern.compile("[a-z0-9][a-z0-9_-]{0,63}");

    private VideoVisualCommands() {}

    static void register(Map<String, CommandHandler> handlers) {
        handlers.put("long.video.canon.list", VideoVisualCommands::list);
        handlers.put("long.video.canon.candidate.set", VideoVisualCommands::setCandidate);
        handlers.put("long.video.canon.approve", VideoVisualCommands::approve);
        handlers.put("long.video.reference.save", VideoVisualCommands::saveReferences);
    }

    private static CommandResult list(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(payload, Set.of("projectId"), Set.of(), true);
        return VideoPayloads.get(
                context,
                "/api/v1/video/projects/"
                        + id(payload, "projectId")
                        + "/visual-canons");
    }

    private static CommandResult setCandidate(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of(
                        "projectId",
                        "clientRequestId",
                        "settingKind",
                        "settingId",
                        "duty",
                        "variantKey",
                        "label",
                        "candidateAssetId"),
                Set.of("includeFeatures", "excludeFeatures", "defaultStrength"),
                false);
        String settingKind = VideoPayloads.enumeration(
                payload, "settingKind", SETTING_KINDS, null);
        String duty = VideoPayloads.enumeration(payload, "duty", CANON_DUTIES, null);
        if (!EXPECTED_KIND.get(duty).equals(settingKind)) {
            throw new CliInputException(
                    "VISUAL_CANON_KIND_DUTY_MISMATCH",
                    "视觉设定职责与文字设定类型不匹配");
        }
        String variantKey = VideoPayloads.string(payload, "variantKey", 1, 64);
        if (!VARIANT_KEY.matcher(variantKey).matches()) {
            throw new CliInputException(
                    "INVALID_VARIANT_KEY",
                    "variantKey 必须以小写字母或数字开头，且只能包含小写字母、数字、下划线和连字符");
        }
        ArrayNode include = features(context, payload, "includeFeatures");
        ArrayNode exclude = features(context, payload, "excludeFeatures");
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put("settingKind", settingKind);
        body.put("settingId", VideoPayloads.string(payload, "settingId"));
        body.put("duty", duty);
        body.put("variantKey", variantKey);
        body.put("label", VideoPayloads.string(payload, "label", 1, 120));
        body.put("candidateAssetId", VideoPayloads.string(payload, "candidateAssetId"));
        body.set("includeFeatures", include);
        body.set("excludeFeatures", exclude);
        body.put(
                "defaultStrength",
                payload.has("defaultStrength")
                        ? VideoPayloads.integer(payload, "defaultStrength", 1, 100)
                        : 70);
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/projects/"
                        + id(payload, "projectId")
                        + "/visual-canons",
                body);
    }

    private static CommandResult approve(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("canonId", "clientRequestId", "expectedRevision", "candidateAssetId"));
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put("clientRequestId", VideoPayloads.clientRequestId(payload));
        body.put(
                "expectedRevision",
                VideoPayloads.integer(payload, "expectedRevision", 1, null));
        body.put("candidateAssetId", VideoPayloads.string(payload, "candidateAssetId"));
        return VideoPayloads.request(
                context,
                "POST",
                "/api/v1/video/visual-canons/"
                        + id(payload, "canonId")
                        + "/approve",
                body);
    }

    private static CommandResult saveReferences(CommandContext context, ObjectNode payload) {
        VideoPayloads.fields(
                payload,
                Set.of("adaptationId", "shotId", "expectedRevision", "references"));
        JsonNode raw = payload.get("references");
        if (raw == null || !raw.isArray() || raw.size() > 20) {
            throw new CliInputException(
                    "INVALID_FIELD", "references 必须是最多 20 项的数组");
        }
        ArrayNode references = context.dependencies().json().createArrayNode();
        HashSet<String> versionIds = new HashSet<>();
        for (JsonNode item : raw) {
            if (!(item instanceof ObjectNode reference)) {
                throw new CliInputException(
                        "INVALID_FIELD", "references 每一项必须是 JSON 对象");
            }
            VideoPayloads.fields(reference, Set.of("canonVersionId", "strength"));
            String versionId = VideoPayloads.string(reference, "canonVersionId");
            if (!versionIds.add(versionId)) {
                throw new CliInputException(
                        "DUPLICATE_CANON_VERSION",
                        "同一镜头不能重复绑定同一视觉设定版本");
            }
            ObjectNode normalized = references.addObject();
            normalized.put("canonVersionId", versionId);
            normalized.put(
                    "strength",
                    VideoPayloads.integer(reference, "strength", 1, 100));
        }
        ObjectNode body = context.dependencies().json().createObjectNode();
        body.put(
                "expectedRevision",
                VideoPayloads.integer(payload, "expectedRevision", 0, null));
        body.set("references", references);
        return VideoPayloads.request(
                context,
                "PUT",
                "/api/v1/video/chapter-adaptations/"
                        + id(payload, "adaptationId")
                        + "/shots/"
                        + id(payload, "shotId")
                        + "/visual-references",
                body);
    }

    private static ArrayNode features(
            CommandContext context, ObjectNode payload, String field) {
        ArrayNode values = VideoPayloads.stringList(context, payload, field, 20, true);
        for (JsonNode value : values) {
            if (value.textValue().codePointCount(0, value.textValue().length()) > 120) {
                throw new CliInputException(
                        "INVALID_FIELD", field + " 单项长度不能超过 120");
            }
        }
        return values;
    }

    private static String id(ObjectNode payload, String field) {
        return Payloads.segment(VideoPayloads.string(payload, field));
    }
}
