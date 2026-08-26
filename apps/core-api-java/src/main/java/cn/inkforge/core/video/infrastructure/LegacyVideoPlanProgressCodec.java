package cn.inkforge.core.video.infrastructure;

import cn.inkforge.contracts.api.SceneAssetsStageArguments;
import cn.inkforge.contracts.api.StoryPlanStageArguments;
import cn.inkforge.contracts.api.VideoPlanAttemptState;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.video.application.LegacyVideoPlanProgress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * Python 旧 VideoScene 进度、终态和冻结任务 JSON 的严格兼容编解码器。
 *
 * <p>该编解码器用于已落库历史任务的终态收敛，字段集合、计数账本和 canonical JSON 都属于冻结兼容面。
 * 它不能被新章节改编流程复用；删除条件是历史活动任务清零并取得独立的数据迁移批准。
 */
final class LegacyVideoPlanProgressCodec {

    static final String PROGRESS_KIND = "video_plan_progress_checkpoint";
    static final String TERMINAL_KIND = "video_plan_terminal_result";
    private static final Set<String> ACTIVE_STAGES =
            Set.of("empty", "scene_assets", "story");
    private static final Set<String> MODEL_STAGES =
            Set.of("scene_assets", "story_beats", "cinematography");
    private static final Set<String> LEGACY_PROGRESS_FIELDS = Set.of(
            "kind",
            "schemaVersion",
            "checkpointStage",
            "sceneAssetsPlan",
            "storyPlan",
            "attemptState",
            "reservations");
    private static final Set<String> CURRENT_PROGRESS_FIELDS;

    static {
        var fields = new HashSet<>(LEGACY_PROGRESS_FIELDS);
        fields.add("inheritedFromTaskId");
        fields.add("inheritedInputFingerprint");
        CURRENT_PROGRESS_FIELDS = Set.copyOf(fields);
    }

    private final ObjectMapper json;

    LegacyVideoPlanProgressCodec(ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
    }

    LegacyVideoPlanProgress emptyProgress() {
        return new LegacyVideoPlanProgress(
                "empty", null, null, attempt(0, 0, null), List.of(), null, null);
    }

    LegacyVideoPlanProgress decodeActiveProgress(String serialized) {
        if (serialized == null) return emptyProgress();
        JsonNode root = object(serialized, "视频规划进度必须是 JSON 对象");
        String version = text(root, "schemaVersion");
        Set<String> expected = switch (version) {
            case "1.0" -> LEGACY_PROGRESS_FIELDS;
            case "2.0" -> CURRENT_PROGRESS_FIELDS;
            default -> throw invalid("视频规划进度版本不受支持");
        };
        require(Set.copyOf(root.propertyNames()).equals(expected), "视频规划进度字段不完整");
        require(PROGRESS_KIND.equals(text(root, "kind")), "视频规划进度类型无效");
        String checkpoint = text(root, "checkpointStage");
        require(ACTIVE_STAGES.contains(checkpoint), "视频规划进度阶段无效");

        SceneAssetsStageArguments sceneAssets = nullableConvert(
                root.get("sceneAssetsPlan"), SceneAssetsStageArguments.class);
        StoryPlanStageArguments story =
                nullableConvert(root.get("storyPlan"), StoryPlanStageArguments.class);
        validatePlanShape(checkpoint, sceneAssets, story);

        JsonNode attemptNode = requireObject(root.get("attemptState"), "视频规划调用状态无效");
        require(
                Set.copyOf(attemptNode.propertyNames())
                        .equals(Set.of("reservedCalls", "inheritedCalls", "pendingStage")),
                "视频规划调用状态字段不完整");
        int reserved = integer(attemptNode, "reservedCalls");
        int inherited = integer(attemptNode, "inheritedCalls");
        String pending = nullableText(attemptNode, "pendingStage");
        validateAttempt(reserved, inherited, pending);

        String inheritedTask = version.equals("1.0")
                ? null
                : nullableText(root, "inheritedFromTaskId");
        String inheritedFingerprint = version.equals("1.0")
                ? null
                : nullableText(root, "inheritedInputFingerprint");
        validateInheritance(inherited, inheritedTask, inheritedFingerprint);

        JsonNode rawReservations = root.get("reservations");
        require(rawReservations != null && rawReservations.isArray(), "视频规划调用预留账本无效");
        List<LegacyVideoPlanProgress.Reservation> reservations = new ArrayList<>();
        Set<String> eventIds = new HashSet<>();
        int index = 0;
        for (JsonNode raw : rawReservations) {
            JsonNode value = requireObject(raw, "视频规划调用预留记录无效");
            require(
                    Set.copyOf(value.propertyNames()).equals(Set.of(
                            "eventId", "checkpointStage", "stage", "reservedCallsBefore")),
                    "视频规划调用预留记录字段不完整");
            String eventId = text(value, "eventId");
            String reservationCheckpoint = text(value, "checkpointStage");
            String stage = text(value, "stage");
            int before = integer(value, "reservedCallsBefore");
            require(eventIds.add(eventId), "视频规划调用预留事件不能重复");
            require(ACTIVE_STAGES.contains(reservationCheckpoint), "视频规划调用预留阶段无效");
            require(MODEL_STAGES.contains(stage), "视频规划模型阶段无效");
            require(before == index, "视频规划调用预留账本计数不连续");
            reservations.add(new LegacyVideoPlanProgress.Reservation(
                    eventId, reservationCheckpoint, stage, before));
            index++;
        }
        require(reservations.size() == reserved, "视频规划调用预留账本与计数不一致");
        return new LegacyVideoPlanProgress(
                checkpoint,
                sceneAssets,
                story,
                attempt(reserved, inherited, pending),
                reservations,
                inheritedTask,
                inheritedFingerprint);
    }

    String encodeProgress(LegacyVideoPlanProgress progress) {
        Objects.requireNonNull(progress);
        validatePlanShape(
                progress.checkpointStage(), progress.sceneAssetsPlan(), progress.storyPlan());
        int reserved = progress.attemptState().getReservedCalls();
        int inherited = inheritedCalls(progress.attemptState());
        String pending = pendingStage(progress.attemptState());
        validateAttempt(reserved, inherited, pending);
        validateInheritance(
                inherited,
                progress.inheritedFromTaskId(),
                progress.inheritedInputFingerprint());
        require(progress.reservations().size() == reserved, "视频规划调用预留账本与计数不一致");
        for (int index = 0; index < progress.reservations().size(); index++) {
            require(
                    progress.reservations().get(index).reservedCallsBefore() == index,
                    "视频规划调用预留账本计数不连续");
        }

        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("kind", PROGRESS_KIND);
        value.put("schemaVersion", "2.0");
        value.put("checkpointStage", progress.checkpointStage());
        value.put("sceneAssetsPlan", modelMap(progress.sceneAssetsPlan()));
        value.put("storyPlan", modelMap(progress.storyPlan()));
        value.put("attemptState", attemptMap(progress.attemptState()));
        value.put("inheritedFromTaskId", progress.inheritedFromTaskId());
        value.put("inheritedInputFingerprint", progress.inheritedInputFingerprint());
        value.put("reservations", progress.reservations().stream()
                .map(reservation -> {
                    LinkedHashMap<String, Object> record = new LinkedHashMap<>();
                    record.put("eventId", reservation.eventId());
                    record.put("checkpointStage", reservation.checkpointStage());
                    record.put("stage", reservation.stage());
                    record.put("reservedCallsBefore", reservation.reservedCallsBefore());
                    return record;
                })
                .toList());
        return canonical(value);
    }

    String encodeTerminal(
            String progressJson,
            String status,
            String eventId,
            Map<String, Object> result) {
        require(Set.of("completed", "failed").contains(status), "视频规划终态类型无效");
        require(eventId != null && !eventId.isEmpty(), "视频规划终态事件不能为空");
        require(result != null, "视频规划终态结果不能为空");
        JsonNode progress = progressJson == null ? null : parse(progressJson);
        if (progressJson != null && decodeTerminal(progressJson) != null) {
            throw invalid("视频规划终态不能重复包装");
        }
        LinkedHashMap<String, Object> outcome = new LinkedHashMap<>();
        outcome.put("status", status);
        outcome.put("eventId", eventId);
        outcome.put("result", result);
        LinkedHashMap<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("kind", TERMINAL_KIND);
        envelope.put("schemaVersion", "1.0");
        envelope.put("progress", progress == null ? null : nodeValue(progress));
        envelope.put("outcome", outcome);
        return canonical(envelope);
    }

    TerminalResult decodeTerminal(String serialized) {
        if (serialized == null) return null;
        JsonNode root = parse(serialized);
        if (!root.isObject() || !TERMINAL_KIND.equals(nullableText(root, "kind"))) return null;
        require(
                Set.copyOf(root.propertyNames())
                        .equals(Set.of("kind", "schemaVersion", "progress", "outcome")),
                "视频规划终态信封字段不完整");
        require("1.0".equals(text(root, "schemaVersion")), "视频规划终态版本不受支持");
        JsonNode outcome = requireObject(root.get("outcome"), "视频规划终态结果无效");
        require(
                Set.copyOf(outcome.propertyNames()).equals(Set.of("status", "eventId", "result")),
                "视频规划终态结果字段不完整");
        String status = text(outcome, "status");
        require(Set.of("completed", "failed").contains(status), "视频规划终态类型无效");
        String eventId = text(outcome, "eventId");
        JsonNode result = requireObject(outcome.get("result"), "视频规划终态业务结果无效");
        JsonNode progress = root.get("progress");
        return new TerminalResult(
                status,
                eventId,
                Collections.unmodifiableMap(json.convertValue(
                        result, new TypeReference<LinkedHashMap<String, Object>>() {})),
                progress == null || progress.isNull() ? null : progress.deepCopy());
    }

    VideoPlanAttemptState terminalAttemptState(String serialized) {
        try {
            TerminalResult terminal = decodeTerminal(serialized);
            JsonNode progress = terminal == null ? parse(serialized) : terminal.progress();
            if (progress == null || progress.isNull()) return attempt(0, 0, null);
            LegacyVideoPlanProgress active = decodeActiveProgress(canonical(nodeValue(progress)));
            return attempt(
                    active.attemptState().getReservedCalls(),
                    inheritedCalls(active.attemptState()),
                    null);
        } catch (RuntimeException ignored) {
            // 历史终态没有可证明账本时只返回安全的零计数，绝不暴露候选内容。
            return attempt(0, 0, null);
        }
    }

    FrozenPayload parseFrozenPayload(String serialized) {
        JsonNode root = object(serialized, "视频规划冻结任务必须是 JSON 对象");
        LinkedHashMap<String, Object> value = json.convertValue(
                root, new TypeReference<LinkedHashMap<String, Object>>() {});
        putDefault(value, "revisionInstruction", null);
        putDefault(value, "revisionBaseline", null);
        putDefault(value, "planningRoute", "legacy_strict_tool_v1");
        putDefault(value, "planningModel", "deepseek-v4-flash");
        putDefault(value, "directorDraftVersion", "1.0");
        String projectId = nonBlank(value.get("projectId"), "projectId");
        String sceneId = nonBlank(value.get("sceneId"), "sceneId");
        String chapterId = nullableString(value.get("chapterId"), "chapterId");
        String title = nonBlank(value.get("title"), "title");
        String sourceText = nonBlank(value.get("sourceText"), "sourceText");
        int duration = exactInteger(value.get("durationSeconds"), "durationSeconds");
        require(duration >= 4 && duration <= 15, "视频规划冻结时长无效");
        String ratio = nonBlank(value.get("ratio"), "ratio");
        require(Set.of("16:9", "9:16", "1:1").contains(ratio), "视频规划冻结画幅无效");
        normalizeSettingSnapshot(value);
        String fingerprint = CommandIdempotency.sha256(
                CommandIdempotency.canonicalJsonBytes(value, json));
        return new FrozenPayload(
                projectId,
                sceneId,
                chapterId,
                title,
                sourceText,
                duration,
                ratio,
                value.get("revisionInstruction") != null,
                fingerprint,
                Collections.unmodifiableMap(new LinkedHashMap<>(value)),
                settingKeys(value));
    }

    boolean jsonEquivalent(Object left, Object right) {
        return java.util.Arrays.equals(
                CommandIdempotency.canonicalJsonBytes(left, json),
                CommandIdempotency.canonicalJsonBytes(right, json));
    }

    Map<String, Object> modelMap(Object value) {
        if (value == null) return null;
        return json.convertValue(value, new TypeReference<LinkedHashMap<String, Object>>() {});
    }

    private void normalizeSettingSnapshot(Map<String, Object> payload) {
        Object raw = payload.get("settingSnapshot");
        require(raw instanceof Map<?, ?>, "视频规划冻结设定快照无效");
        @SuppressWarnings("unchecked")
        Map<String, Object> source = (Map<String, Object>) raw;
        LinkedHashMap<String, Object> snapshot = new LinkedHashMap<>(source);
        putDefault(snapshot, "schemaVersion", "1.0");
        require("1.0".equals(snapshot.get("schemaVersion")), "视频规划冻结设定版本无效");
        Object entriesValue = snapshot.get("entries");
        require(entriesValue instanceof List<?>, "视频规划冻结设定条目无效");
        List<Map<String, Object>> entries = new ArrayList<>();
        Set<String> keys = new HashSet<>();
        for (Object item : (List<?>) entriesValue) {
            require(item instanceof Map<?, ?>, "视频规划冻结设定条目无效");
            @SuppressWarnings("unchecked")
            LinkedHashMap<String, Object> entry =
                    new LinkedHashMap<>((Map<String, Object>) item);
            String kind = nonBlank(entry.get("kind"), "setting.kind");
            String id = nonBlank(entry.get("id"), "setting.id");
            require(keys.add(kind + "\0" + id), "视频规划冻结设定身份重复");
            normalizeSettingEntry(entry, kind);
            entries.add(Collections.unmodifiableMap(entry));
        }
        List<Map<String, Object>> sorted = entries.stream()
                .sorted(java.util.Comparator
                        .comparing((Map<String, Object> item) -> item.get("kind").toString())
                        .thenComparing(item -> item.get("id").toString()))
                .toList();
        String expected = CommandIdempotency.sha256(
                CommandIdempotency.canonicalJsonBytes(sorted, json));
        require(expected.equals(snapshot.get("fingerprint")), "视频规划冻结设定指纹无效");
        snapshot.put("entries", List.copyOf(entries));
        payload.put("settingSnapshot", Collections.unmodifiableMap(snapshot));
    }

    private static void normalizeSettingEntry(Map<String, Object> entry, String kind) {
        switch (kind) {
            case "character" -> {
                putDefault(entry, "aliases", List.of());
                putDefault(entry, "appearance", null);
                putDefault(entry, "identity", null);
            }
            case "relationship" -> putDefault(entry, "description", null);
            case "location" -> {
                putDefault(entry, "aliases", List.of());
                putDefault(entry, "locationType", null);
                putDefault(entry, "parentLocationId", null);
                putDefault(entry, "climate", null);
                putDefault(entry, "culture", null);
                putDefault(entry, "description", null);
            }
            case "item" -> {
                putDefault(entry, "aliases", List.of());
                putDefault(entry, "itemType", null);
                putDefault(entry, "ownerCharacterId", null);
                putDefault(entry, "description", null);
            }
            case "world_setting" -> { }
            default -> throw invalid("视频规划冻结设定类型无效");
        }
    }

    private static Set<String> settingKeys(Map<String, Object> payload) {
        @SuppressWarnings("unchecked")
        Map<String, Object> snapshot = (Map<String, Object>) payload.get("settingSnapshot");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> entries = (List<Map<String, Object>>) snapshot.get("entries");
        return entries.stream()
                .map(entry -> entry.get("kind") + "\0" + entry.get("id"))
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }

    private void validatePlanShape(
            String checkpoint,
            SceneAssetsStageArguments sceneAssets,
            StoryPlanStageArguments story) {
        require(ACTIVE_STAGES.contains(checkpoint), "视频规划进度阶段无效");
        switch (checkpoint) {
            case "empty" -> require(
                    sceneAssets == null && story == null,
                    "空阶段不能携带故事或素材计划");
            case "scene_assets" -> require(
                    sceneAssets != null && story == null,
                    "素材阶段必须只携带素材计划");
            case "story" -> require(
                    sceneAssets == null && story != null,
                    "故事阶段必须只携带故事计划");
            default -> throw invalid("视频规划进度阶段无效");
        }
    }

    private static void validateAttempt(int reserved, int inherited, String pending) {
        require(reserved >= 0 && reserved <= 5, "视频规划调用计数无效");
        require(inherited >= 0 && inherited <= 2, "视频规划继承调用计数无效");
        require(reserved + inherited <= 5, "视频规划有效调用超过上限");
        require(pending == null || MODEL_STAGES.contains(pending), "视频规划待确认阶段无效");
        require(reserved != 0 || pending == null, "零次预留不能携带待确认阶段");
    }

    private static void validateInheritance(
            int inherited, String sourceTaskId, String inputFingerprint) {
        if (inherited == 0) {
            require(
                    sourceTaskId == null && inputFingerprint == null,
                    "没有继承调用时不能携带来源");
            return;
        }
        require(sourceTaskId != null && !sourceTaskId.isEmpty(), "视频规划继承来源任务无效");
        require(
                inputFingerprint != null && inputFingerprint.matches("[0-9a-f]{64}"),
                "视频规划继承输入指纹无效");
    }

    static boolean frozenSceneAssetsEqual(
            SceneAssetsStageArguments assets, StoryPlanStageArguments story) {
        return Objects.equals(assets.getTitle(), story.getTitle())
                && Objects.equals(assets.getSummary(), story.getSummary())
                && Objects.equals(assets.getDramaticArc(), story.getDramaticArc())
                && Objects.equals(assets.getVisualStyle(), story.getVisualStyle())
                && Objects.equals(assets.getGlobalDirection(), story.getGlobalDirection())
                && Objects.equals(assets.getAssets(), story.getAssets())
                && Objects.equals(assets.getNegativeConstraints(), story.getNegativeConstraints());
    }

    private Map<String, Object> attemptMap(VideoPlanAttemptState value) {
        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        result.put("reservedCalls", value.getReservedCalls());
        result.put("inheritedCalls", inheritedCalls(value));
        result.put("pendingStage", pendingStage(value));
        return result;
    }

    private static VideoPlanAttemptState attempt(int reserved, int inherited, String pending) {
        VideoPlanAttemptState result = new VideoPlanAttemptState(
                pending == null
                        ? null
                        : VideoPlanAttemptState.PendingStageEnum.fromValue(pending),
                reserved);
        result.setPendingStage(JsonNullable.of(
                pending == null
                        ? null
                        : VideoPlanAttemptState.PendingStageEnum.fromValue(pending)));
        result.setInheritedCalls(inherited);
        return result;
    }

    static int inheritedCalls(VideoPlanAttemptState value) {
        return value.getInheritedCalls() == null ? 0 : value.getInheritedCalls();
    }

    static String pendingStage(VideoPlanAttemptState value) {
        if (value.getPendingStage() == null || !value.getPendingStage().isPresent()) return null;
        VideoPlanAttemptState.PendingStageEnum pending = value.getPendingStage().orElse(null);
        return pending == null ? null : pending.getValue();
    }

    private JsonNode object(String serialized, String message) {
        JsonNode value = parse(serialized);
        return requireObject(value, message);
    }

    private JsonNode parse(String serialized) {
        try {
            return json.readTree(serialized);
        } catch (RuntimeException exception) {
            throw new IllegalArgumentException("视频规划 JSON 已损坏", exception);
        }
    }

    private static JsonNode requireObject(JsonNode value, String message) {
        require(value != null && value.isObject(), message);
        return value;
    }

    private <T> T nullableConvert(JsonNode value, Class<T> type) {
        if (value == null || value.isNull()) return null;
        try {
            return json.convertValue(value, type);
        } catch (RuntimeException exception) {
            throw new IllegalArgumentException("视频规划阶段载荷无效", exception);
        }
    }

    private Object nodeValue(JsonNode value) {
        return json.convertValue(value, new TypeReference<Object>() {});
    }

    private String canonical(Object value) {
        return new String(
                CommandIdempotency.canonicalJsonBytes(value, json),
                StandardCharsets.UTF_8);
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        require(value != null && value.isString() && !value.asString().isEmpty(),
                "视频规划字段无效：" + field);
        return value.asString();
    }

    private static String nullableText(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        if (value == null || value.isNull()) return null;
        require(value.isString() && !value.asString().isEmpty(), "视频规划字段无效：" + field);
        return value.asString();
    }

    private static int integer(JsonNode node, String field) {
        JsonNode value = node == null ? null : node.get(field);
        require(value != null && value.isInt(), "视频规划字段无效：" + field);
        return value.asInt();
    }

    private static String nonBlank(Object value, String field) {
        require(value instanceof String text && !text.isEmpty(), "视频规划冻结字段无效：" + field);
        return (String) value;
    }

    private static String nullableString(Object value, String field) {
        if (value == null) return null;
        return nonBlank(value, field);
    }

    private static int exactInteger(Object value, String field) {
        require(value instanceof Integer || value instanceof Long, "视频规划冻结字段无效：" + field);
        long number = ((Number) value).longValue();
        require(number >= Integer.MIN_VALUE && number <= Integer.MAX_VALUE,
                "视频规划冻结字段无效：" + field);
        return (int) number;
    }

    private static void putDefault(Map<String, Object> value, String key, Object fallback) {
        if (!value.containsKey(key)) value.put(key, fallback);
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw invalid(message);
    }

    private static IllegalArgumentException invalid(String message) {
        return new IllegalArgumentException(message);
    }

    record TerminalResult(
            String status,
            String eventId,
            Map<String, Object> result,
            JsonNode progress) {

        TerminalResult {
            result = Collections.unmodifiableMap(new LinkedHashMap<>(result));
            progress = progress == null ? null : progress.deepCopy();
        }
    }

    record FrozenPayload(
            String projectId,
            String sceneId,
            String chapterId,
            String title,
            String sourceText,
            int durationSeconds,
            String ratio,
            boolean revision,
            String inputFingerprint,
            Map<String, Object> agentPayload,
            Set<String> settingKeys) {

        FrozenPayload {
            agentPayload = Collections.unmodifiableMap(new LinkedHashMap<>(agentPayload));
            settingKeys = Set.copyOf(settingKeys);
        }
    }
}
