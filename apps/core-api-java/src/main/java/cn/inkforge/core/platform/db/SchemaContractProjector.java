package cn.inkforge.core.platform.db;

import java.util.List;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 与 Python Core 相同的生产能力投影；不放宽任何非目标结构差异。 */
final class SchemaContractProjector {

    private static final Set<String> VIDEO_TABLES = Set.of(
            "VideoProject",
            "VideoScene",
            "VideoAsset",
            "VideoAssetBinding",
            "VideoGenerationTask",
            "VideoReviewDecisionCommand",
            "VideoChapterAdaptation",
            "VideoChapterAdaptationHead",
            "VideoAdaptationTask",
            "VideoShotPlanVersion",
            "VideoCinematicScene",
            "VideoDramaticBeat",
            "VideoDramaticBeatSourceAnchor",
            "VideoShot",
            "VideoShotSourceAnchor",
            "VideoEpisodePlanVersion",
            "VideoEpisodeBoundary",
            "VideoShotPromptVersion",
            "VideoShotPromptHead",
            "VideoAdaptationDecisionCommand",
            "VideoVisualCanon",
            "VideoVisualCanonVersion",
            "VideoShotVisualReferenceSet",
            "VideoShotVisualReferenceBinding",
            "VideoShotPromptVisualReference",
            "VideoShotRenderTask",
            "VideoShotTake",
            "VideoShotTakeHead",
            "VideoShotTakeDecisionCommand",
            "VideoTakeFrameExtraction",
            "VideoShotKeyframeVersion",
            "VideoShotKeyframeHead",
            "VideoEpisodeEditVersion",
            "VideoEpisodeEditClip",
            "VideoEpisodeEditHead",
            "VideoEpisodeMixVersion",
            "VideoEpisodeAudioClip",
            "VideoEpisodeSubtitleCue",
            "VideoEpisodeMixHead",
            "VideoEpisodeExportTask",
            "VideoEpisodeExport");
    private static final Set<String> REVIEW_VIDEO_COLUMNS =
            Set.of("videoSceneId", "videoAdaptationId", "videoAdaptationTaskId");

    private SchemaContractProjector() {}

    static SchemaContract project(SchemaContract contract, SchemaProfile profile) {
        ObjectNode document = contract.document().asObject();
        document.remove("fingerprint");
        if (!profile.includesVideoPreview()) {
            projectWithoutVideo(document);
        }
        if (!profile.includesPhoneAuth()) {
            projectWithoutPhoneAuth(document);
        }
        document.put("fingerprint", SchemaContract.canonicalFingerprint(document));
        return SchemaContract.load(document);
    }

    private static void projectWithoutPhoneAuth(ObjectNode document) {
        ArrayNode remaining = document.arrayNode();
        for (JsonNode tableNode : document.path("tables")) {
            if (tableNode.isObject()
                    && tableNode.path("name").asString().equals("UserPhoneIdentity")) {
                continue;
            }
            remaining.add(tableNode);
        }
        document.set("tables", remaining);
    }

    private static void projectWithoutVideo(ObjectNode document) {
        ArrayNode remaining = document.arrayNode();
        for (JsonNode tableNode : document.path("tables")) {
            if (!tableNode.isObject()) {
                remaining.add(tableNode);
                continue;
            }
            ObjectNode table = tableNode.asObject();
            String name = table.path("name").asString();
            if (VIDEO_TABLES.contains(name)) {
                continue;
            }
            if (name.equals("Novel")) {
                removeNamed(table, "uniqueConstraints", Set.of("Novel_id_userId_key"));
                removeNamed(table, "indexes", Set.of("Novel_id_userId_key"));
            } else if (name.equals("Chapter")) {
                removeNamed(table, "uniqueConstraints", Set.of("Chapter_id_novelId_key"));
                removeNamed(table, "indexes", Set.of("Chapter_id_novelId_key"));
            } else if (name.equals("TokenUsage")) {
                removeNamed(table, "columns", Set.of("promptCacheMissTokens", "reasoningTokens"));
                removeNamed(
                        table,
                        "checkConstraints",
                        Set.of(
                                "TokenUsage_prompt_cache_details_check",
                                "TokenUsage_reasoning_details_check",
                                "TokenUsage_token_details_nonnegative_check"));
            } else if (name.equals("ReviewArtifact")) {
                projectReviewArtifact(table);
            }
            remaining.add(table);
        }
        document.set("tables", remaining);

        for (JsonNode enumNode : document.path("enums")) {
            if (enumNode.isObject() && enumNode.path("name").asString().equals("ReviewArtifactKind")) {
                ArrayNode values = enumNode.asObject().withArray("values");
                removeTextValues(values, Set.of("video_scene_plan", "video_adaptation_plan"));
            }
        }
    }

    private static void projectReviewArtifact(ObjectNode table) {
        removeNamed(table, "columns", REVIEW_VIDEO_COLUMNS);
        for (String collection : List.of("foreignKeys", "uniqueConstraints")) {
            removeIf(table.withArray(collection), item -> item.isObject()
                    && intersects(item.path("columns"), REVIEW_VIDEO_COLUMNS));
        }
        removeIf(table.withArray("indexes"), item -> item.isObject()
                && REVIEW_VIDEO_COLUMNS.stream().anyMatch(column -> indexReferences(item, column)));
        removeIf(table.withArray("checkConstraints"), item -> {
            if (!item.isObject()) {
                return false;
            }
            String definition = item.path("expression").asString("")
                    + item.path("definition").asString("");
            return REVIEW_VIDEO_COLUMNS.stream().anyMatch(definition::contains);
        });
    }

    private static boolean indexReferences(JsonNode index, String column) {
        for (JsonNode included : index.path("includeColumns")) {
            if (included.asString().equals(column)) {
                return true;
            }
        }
        for (JsonNode keyItem : index.path("keyItems")) {
            if (keyItem.path("column").asString().equals(column)) {
                return true;
            }
        }
        return false;
    }

    private static boolean intersects(JsonNode values, Set<String> expected) {
        for (JsonNode value : values) {
            if (expected.contains(value.asString())) {
                return true;
            }
        }
        return false;
    }

    private static void removeNamed(ObjectNode owner, String collection, Set<String> names) {
        removeIf(owner.withArray(collection), item -> item.isObject()
                && names.contains(item.path("name").asString()));
    }

    private static void removeTextValues(ArrayNode array, Set<String> values) {
        removeIf(array, item -> values.contains(item.asString()));
    }

    private static void removeIf(
            ArrayNode array, java.util.function.Predicate<JsonNode> predicate) {
        List<JsonNode> retained = new java.util.ArrayList<>();
        array.forEach(item -> {
            if (!predicate.test(item)) {
                retained.add(item);
            }
        });
        array.removeAll();
        retained.forEach(array::add);
    }
}
