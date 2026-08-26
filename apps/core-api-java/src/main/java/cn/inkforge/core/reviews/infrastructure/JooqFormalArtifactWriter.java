package cn.inkforge.core.reviews.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERBEATPLAN;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.OUTLINENODE;
import static cn.inkforge.core.db.generated.Tables.SCENEBEAT;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;

import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;
import cn.inkforge.contracts.api.ArtifactSelectionRef;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Beatplanstatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.db.generated.enums.Workflowrunkind;
import cn.inkforge.core.db.generated.enums.Workflowrunstatus;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.db.generated.tables.records.ChapterqualitycheckRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.application.FormalArtifactWriter;
import cn.inkforge.core.reviews.application.AgentUpdatesExecutor;
import cn.inkforge.core.reviews.application.ReviewArtifactState;
import cn.inkforge.core.reviews.domain.ReviewArtifactRules;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.impl.DSL;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.databind.ObjectMapper;

/**
 * 审核批准后的正式数据写入；所有动作加入调用方通过 {@code CoreDatabase} 建立的事务。
 *
 * <p>本类不提交事务、不改变 Artifact 状态，也不投递 Agent。它只把已锁定且已通过来源预检的草案写入对应
 * 正式领域；任何异常交给 {@link JooqReviewDecisionStore} 回滚整次决定。章节正文变化必须同步重开章节并
 * 失效旧质量结果，不能只替换 content 字段。
 */
final class JooqFormalArtifactWriter implements FormalArtifactWriter {

    private static final String QUALITY_SOURCE_CHANGED = "QUALITY_SOURCE_CHANGED";

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final AgentUpdatesExecutor agentUpdates;

    JooqFormalArtifactWriter(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this(database, ids, clock, json, null);
    }

    JooqFormalArtifactWriter(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            AgentUpdatesExecutor agentUpdates) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.agentUpdates = agentUpdates;
    }

    @Override
    public int apply(
            String userId,
            ReviewArtifactState artifact,
            ReviewArtifactDecisionRequest request) {
        DSLContext transaction = database.dsl();
        requireOwner(transaction, artifact.novelId(), userId);
        String target = resolveTarget(artifact.payload());
        if (target == null) {
            throw new ApiException(400, "ARTIFACT_NOT_APPLICABLE", "该草案类型不能写入正式数据");
        }
        if ("selection".equals(target)) {
            // 选区在批准时再次校验时间、全文哈希、范围和选区哈希，防止审核期间来源已变化。
            return applySelection(transaction, artifact, request);
        }
        String content = nullable(request.getEditedContent());
        if (content == null) content = string(artifact.payload().get("content"));
        if ("outline_content".equals(target) || "chapter_content".equals(target)) {
            if (content == null || content.isEmpty()) {
                throw new IllegalArgumentException("文本草案缺少完整内容");
            }
            if ("outline_content".equals(target)) {
                applyOutline(transaction, artifact.novelId(), content);
            } else {
                applyChapter(transaction, artifact, content);
            }
            return 1;
        }
        if ("beat_plan".equals(target)) {
            Map<String, Object> beatPlan = beatPlan(artifact, content);
            applyBeatPlan(transaction, artifact, beatPlan);
            return 1;
        }
        if ("agent_updates".equals(target)) {
            if (agentUpdates == null) {
                throw new ApiException(503, "REVIEW_APPLIER_UNAVAILABLE", "审核正式写入服务暂时不可用");
            }
            Object raw = artifact.payload().get("updates");
            if (!(raw instanceof Map<?, ?> values)) {
                throw new IllegalArgumentException("agent_updates 草案缺少结构化更新");
            }
            return agentUpdates.apply(
                    artifact.novelId(),
                    userId,
                    stringMap(values),
                    nullable(request.getSelectedUpdateRefs()),
                    optionalTime(artifact.payload().get("baseOutlineUpdatedAt"), "baseOutlineUpdatedAt"),
                    optionalTimeMap(artifact.payload().get("baseLoreUpdatedAt")));
        }
        throw new ApiException(400, "ARTIFACT_NOT_APPLICABLE", "该草案类型不能写入正式数据");
    }

    private int applySelection(
            DSLContext transaction,
            ReviewArtifactState artifact,
            ReviewArtifactDecisionRequest request) {
        if (nullable(request.getEditedContent()) != null) {
            throw new IllegalArgumentException("选区草案不允许再提供 editedContent 全文内容");
        }
        String replacement = nullable(request.getEditedReplacement());
        if (replacement == null) replacement = string(artifact.payload().get("replacement"));
        if (replacement == null || replacement.strip().isEmpty()) {
            throw new IllegalArgumentException("选区草案缺少非空 replacement");
        }
        Map<String, Object> payload = artifact.payload();
        Map<?, ?> target = payload.get("target") instanceof Map<?, ?> value ? value : null;
        String mode = target == null ? null : string(target.get("mode"));
        String resourceType = string(payload.get("resourceType"));
        String resourceId = string(payload.get("resourceId"));
        String expectedType = switch (mode) {
            case "replace_selection" -> "chapter_content";
            case "outline_content_selection" -> "outline_content";
            case "outline_node_content_selection" -> "outline_node_content";
            default -> throw new IllegalArgumentException("选区草案缺少有效 target mode");
        };
        if (!expectedType.equals(resourceType) || resourceId == null) {
            throw selectionConflict(resourceType, resourceId);
        }
        if ("replace_selection".equals(mode)) {
            if (artifact.chapterId() != null && !artifact.chapterId().equals(resourceId)) {
                throw selectionConflict(resourceType, resourceId);
            }
            var chapter = transaction.selectFrom(CHAPTER)
                    .where(CHAPTER.ID.eq(resourceId), CHAPTER.NOVELID.eq(artifact.novelId()))
                    .forUpdate()
                    .fetchOne();
            if (chapter == null) {
                throw new ApiException(404, "CHAPTER_NOT_FOUND", "正文草案目标章节不存在");
            }
            String source = chapter.getContent();
            requireSelectionMatches(payload, source, chapter.getUpdatedat(), resourceType, resourceId);
            applyChapter(transaction, artifact,
                    splice(source, integer(payload.get("selectionStart")),
                            integer(payload.get("selectionEnd")), replacement));
            return 1;
        }
        if ("outline_content_selection".equals(mode)) {
            var outline = transaction.selectFrom(OUTLINE)
                    .where(OUTLINE.ID.eq(resourceId), OUTLINE.NOVELID.eq(artifact.novelId()))
                    .forUpdate()
                    .fetchOne();
            if (outline == null) {
                throw new ApiException(404, "OUTLINE_NOT_FOUND", "大纲不存在或不属于该小说");
            }
            requireSelectionMatches(
                    payload, outline.getContent(), outline.getUpdatedat(), resourceType, resourceId);
            transaction.update(OUTLINE)
                    .set(OUTLINE.CONTENT, splice(
                            outline.getContent(),
                            integer(payload.get("selectionStart")),
                            integer(payload.get("selectionEnd")),
                            replacement))
                    .set(OUTLINE.UPDATEDAT, DatabaseTimestamp.next(clock, outline.getUpdatedat()))
                    .where(OUTLINE.ID.eq(resourceId))
                    .execute();
            return 1;
        }
        var node = transaction.selectFrom(OUTLINENODE)
                .where(OUTLINENODE.ID.eq(resourceId), OUTLINENODE.NOVELID.eq(artifact.novelId()))
                .forUpdate()
                .fetchOne();
        if (node == null || node.getContent() == null) {
            throw new ApiException(404, "OUTLINE_NODE_NOT_FOUND", "大纲节点不存在或没有正文");
        }
        requireSelectionMatches(
                payload, node.getContent(), node.getUpdatedat(), resourceType, resourceId);
        transaction.update(OUTLINENODE)
                .set(OUTLINENODE.CONTENT, splice(
                        node.getContent(),
                        integer(payload.get("selectionStart")),
                        integer(payload.get("selectionEnd")),
                        replacement))
                .set(OUTLINENODE.UPDATEDAT, DatabaseTimestamp.next(clock, node.getUpdatedat()))
                .where(OUTLINENODE.ID.eq(resourceId))
                .execute();
        return 1;
    }

    private void applyOutline(DSLContext transaction, String novelId, String content) {
        var outline = transaction.selectFrom(OUTLINE)
                .where(OUTLINE.NOVELID.eq(novelId))
                .forUpdate()
                .fetchOne();
        LocalDateTime now = DatabaseTimestamp.now(clock);
        if (outline == null) {
            transaction.insertInto(OUTLINE)
                    .set(OUTLINE.ID, ids.next())
                    .set(OUTLINE.NOVELID, novelId)
                    .set(OUTLINE.CONTENT, content)
                    .set(OUTLINE.CREATEDAT, now)
                    .set(OUTLINE.UPDATEDAT, now)
                    .execute();
            return;
        }
        transaction.update(OUTLINE)
                .set(OUTLINE.CONTENT, content)
                .set(OUTLINE.UPDATEDAT, DatabaseTimestamp.next(clock, outline.getUpdatedat()))
                .where(OUTLINE.ID.eq(outline.getId()))
                .execute();
    }

    private void applyChapter(
            DSLContext transaction, ReviewArtifactState artifact, String content) {
        Map<?, ?> target = artifact.payload().get("target") instanceof Map<?, ?> value
                ? value
                : null;
        if (target != null && "new_next_chapter".equals(target.get("mode"))) {
            Integer maximum = transaction.select(DSL.max(CHAPTER.ORDER))
                    .from(CHAPTER)
                    .where(CHAPTER.NOVELID.eq(artifact.novelId()))
                    .fetchOne(DSL.max(CHAPTER.ORDER));
            int order = (maximum == null ? 0 : maximum) + 1;
            String requestedTitle = string(target.get("title"));
            LocalDateTime now = DatabaseTimestamp.now(clock);
            String chapterId = ids.next();
            transaction.insertInto(CHAPTER)
                    .set(CHAPTER.ID, chapterId)
                    .set(CHAPTER.NOVELID, artifact.novelId())
                    .set(CHAPTER.TITLE,
                            requestedTitle == null || requestedTitle.isEmpty()
                                    ? "第 " + order + " 章"
                                    : requestedTitle)
                    .set(CHAPTER.CONTENT, content)
                    .set(CHAPTER.ORDER, order)
                    .set(CHAPTER.STATUS, Chapterstatus.drafting)
                    .set(CHAPTER.CREATEDAT, now)
                    .set(CHAPTER.UPDATEDAT, now)
                    .execute();
            ensureConsistencyCheck(transaction, chapterId, now);
            return;
        }
        String chapterId = target != null && "existing_chapter".equals(target.get("mode"))
                ? string(target.get("chapterId"))
                : artifact.chapterId();
        if (chapterId == null || chapterId.isEmpty()) {
            throw new IllegalArgumentException("正文草案缺少目标章节");
        }
        ChapterRecord chapter = transaction.selectFrom(CHAPTER)
                .where(
                        CHAPTER.ID.eq(chapterId),
                        CHAPTER.NOVELID.eq(artifact.novelId()))
                .forUpdate()
                .fetchOne();
        if (chapter == null) {
            throw new ApiException(404, "CHAPTER_NOT_FOUND", "正文草案目标章节不存在");
        }
        ChapterqualitycheckRecord check = transaction.selectFrom(CHAPTERQUALITYCHECK)
                .where(
                        CHAPTERQUALITYCHECK.CHAPTERID.eq(chapterId),
                        CHAPTERQUALITYCHECK.TYPE.eq(Qualitychecktype.consistency))
                .forUpdate()
                .fetchOne();
        LocalDateTime now = DatabaseTimestamp.now(clock);
        LocalDateTime updatedAt = DatabaseTimestamp.next(clock, chapter.getUpdatedat());
        // 正文正式变化等价于编辑器保存：章节回到 drafting，旧质量运行同时失效。
        transaction.update(CHAPTER)
                .set(CHAPTER.CONTENT, content)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .setNull(CHAPTER.COMPLETEDAT)
                .set(CHAPTER.UPDATEDAT, updatedAt)
                .where(CHAPTER.ID.eq(chapterId))
                .execute();
        if (check == null) {
            ensureConsistencyCheck(transaction, chapterId, now);
        } else {
            invalidateConsistencyCheck(transaction, check, now);
        }
    }

    private void ensureConsistencyCheck(
            DSLContext transaction, String chapterId, LocalDateTime now) {
        String existing = transaction.select(CHAPTERQUALITYCHECK.ID)
                .from(CHAPTERQUALITYCHECK)
                .where(
                        CHAPTERQUALITYCHECK.CHAPTERID.eq(chapterId),
                        CHAPTERQUALITYCHECK.TYPE.eq(Qualitychecktype.consistency))
                .forUpdate()
                .fetchOne(CHAPTERQUALITYCHECK.ID);
        if (existing != null) return;
        transaction.insertInto(CHAPTERQUALITYCHECK)
                .set(CHAPTERQUALITYCHECK.ID, ids.next())
                .set(CHAPTERQUALITYCHECK.CHAPTERID, chapterId)
                .set(CHAPTERQUALITYCHECK.TYPE, Qualitychecktype.consistency)
                .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.pending)
                .set(CHAPTERQUALITYCHECK.TITLE, "一致性终检")
                .set(CHAPTERQUALITYCHECK.CREATEDAT, now)
                .set(CHAPTERQUALITYCHECK.UPDATEDAT, now)
                .execute();
    }

    private static void invalidateConsistencyCheck(
            DSLContext transaction,
            ChapterqualitycheckRecord check,
            LocalDateTime now) {
        transaction.update(CHAPTERQUALITYCHECK)
                .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.pending)
                .setNull(CHAPTERQUALITYCHECK.RESULT)
                .setNull(CHAPTERQUALITYCHECK.SCOREHOOK)
                .setNull(CHAPTERQUALITYCHECK.SCORETENSION)
                .setNull(CHAPTERQUALITYCHECK.SCOREPAYOFF)
                .setNull(CHAPTERQUALITYCHECK.SCOREPACING)
                .setNull(CHAPTERQUALITYCHECK.SCOREENDINGHOOK)
                .setNull(CHAPTERQUALITYCHECK.SCOREREADERPROMISE)
                .setNull(CHAPTERQUALITYCHECK.SCOREOVERALL)
                .setNull(CHAPTERQUALITYCHECK.QUALITYGATE)
                .setNull(CHAPTERQUALITYCHECK.REWRITEBRIEF)
                .set(CHAPTERQUALITYCHECK.UPDATEDAT, now)
                .where(CHAPTERQUALITYCHECK.ID.eq(check.getId()))
                .execute();
        transaction.update(WORKFLOWRUN)
                .set(WORKFLOWRUN.STATUS, Workflowrunstatus.cancelled)
                .set(WORKFLOWRUN.ERRORMESSAGE, QUALITY_SOURCE_CHANGED)
                .set(WORKFLOWRUN.UPDATEDAT, now)
                .where(
                        WORKFLOWRUN.KIND.eq(Workflowrunkind.quality_check),
                        WORKFLOWRUN.SOURCEID.eq(check.getId()),
                        WORKFLOWRUN.STATUS.in(
                                Workflowrunstatus.pending,
                                Workflowrunstatus.running))
                .execute();
    }

    private Map<String, Object> beatPlan(
            ReviewArtifactState artifact, String editedContent) {
        if ("beat_plan_draft".equals(artifact.kind())) {
            if (editedContent == null || editedContent.isEmpty()) {
                throw new IllegalArgumentException("章节计划草案缺少完整内容");
            }
            Map<String, Object> scene = new LinkedHashMap<>();
            scene.put("order", 1);
            scene.put("goal", editedContent);
            scene.put("characters", List.of());
            scene.put("estimatedWords", 0);
            scene.put("acceptanceCriteria", "按完整文本草案执行，并在写作前由作者确认细化。");
            Map<String, Object> plan = new LinkedHashMap<>();
            plan.put("title", "章节计划草案");
            plan.put("summary", editedContent);
            plan.put("chapterGoal", editedContent);
            plan.put("totalEstimatedWords", 0);
            plan.put("sceneBeats", List.of(scene));
            return normalizeBeatPlan(plan);
        }
        Object raw = artifact.payload().get("beatPlan");
        if (!(raw instanceof Map<?, ?> values)) {
            throw new IllegalArgumentException("章节计划草案结构无效");
        }
        return normalizeBeatPlan(stringMap(values));
    }

    private void applyBeatPlan(
            DSLContext transaction,
            ReviewArtifactState artifact,
            Map<String, Object> beatPlan) {
        if (artifact.chapterId() == null) {
            throw new IllegalArgumentException("章节计划草案缺少目标章节");
        }
        String chapter = transaction.select(CHAPTER.ID)
                .from(CHAPTER)
                .where(
                        CHAPTER.ID.eq(artifact.chapterId()),
                        CHAPTER.NOVELID.eq(artifact.novelId()))
                .forUpdate()
                .fetchOne(CHAPTER.ID);
        if (chapter == null) {
            throw new ApiException(404, "CHAPTER_NOT_FOUND", "章节计划目标章节不存在");
        }
        // 先 supersede 旧批准计划再创建新版本；历史计划与 SceneBeat 保留，不原地覆盖。
        transaction.update(CHAPTERBEATPLAN)
                .set(CHAPTERBEATPLAN.STATUS, Beatplanstatus.superseded)
                .where(
                        CHAPTERBEATPLAN.CHAPTERID.eq(artifact.chapterId()),
                        CHAPTERBEATPLAN.STATUS.eq(Beatplanstatus.approved))
                .execute();
        LocalDateTime now = DatabaseTimestamp.now(clock);
        String planId = ids.next();
        transaction.insertInto(CHAPTERBEATPLAN)
                .set(CHAPTERBEATPLAN.ID, planId)
                .set(CHAPTERBEATPLAN.CHAPTERID, artifact.chapterId())
                .set(CHAPTERBEATPLAN.STATUS, Beatplanstatus.approved)
                .set(CHAPTERBEATPLAN.CHAPTERGOAL, string(beatPlan.get("chapterGoal")))
                .set(CHAPTERBEATPLAN.MAINPLOTCONNECTION,
                        optionalString(beatPlan.get("mainPlotConnection")))
                .set(CHAPTERBEATPLAN.CHAPTERACCEPTANCECRITERIA,
                        optionalString(beatPlan.get("chapterAcceptanceCriteria")))
                .set(CHAPTERBEATPLAN.TOTALESTIMATEDWORDS,
                        optionalInteger(beatPlan.get("totalEstimatedWords"), 0))
                .set(CHAPTERBEATPLAN.CREATEDAT, now)
                .set(CHAPTERBEATPLAN.UPDATEDAT, now)
                .execute();
        List<?> scenes = (List<?>) beatPlan.get("sceneBeats");
        for (Object value : scenes) {
            Map<String, Object> scene = stringMap((Map<?, ?>) value);
            @SuppressWarnings("unchecked")
            List<String> characters = (List<String>) scene.get("characters");
            @SuppressWarnings("unchecked")
            List<String> refs = (List<String>) scene.get("foreshadowingRefs");
            transaction.insertInto(SCENEBEAT)
                    .set(SCENEBEAT.ID, ids.next())
                    .set(SCENEBEAT.BEATPLANID, planId)
                    .set(SCENEBEAT.ORDER, (Integer) scene.get("order"))
                    .set(SCENEBEAT.GOAL, string(scene.get("goal")))
                    .set(SCENEBEAT.CONFLICT, optionalString(scene.get("conflict")))
                    .set(SCENEBEAT.CHARACTERS, json.writeValueAsString(characters))
                    .set(SCENEBEAT.FORESHADOWINGREFS,
                            refs == null ? null : json.writeValueAsString(refs))
                    .set(SCENEBEAT.ESTIMATEDWORDS,
                            optionalInteger(scene.get("estimatedWords"), 0))
                    .set(SCENEBEAT.ACCEPTANCECRITERIA,
                            optionalString(scene.get("acceptanceCriteria")) == null
                                    ? string(scene.get("goal"))
                                    : string(scene.get("acceptanceCriteria")))
                    .execute();
        }
    }

    private static Map<String, Object> normalizeBeatPlan(Map<String, Object> raw) {
        String chapterGoal = nonEmptyString(raw.get("chapterGoal"));
        if (chapterGoal == null) {
            throw new IllegalArgumentException("章节计划 chapterGoal 必须是非空字符串");
        }
        requireOptionalString(raw, "mainPlotConnection");
        requireOptionalString(raw, "chapterAcceptanceCriteria");
        requireNonNegativeInteger(raw, "totalEstimatedWords");
        Object sceneValue = raw.get("sceneBeats");
        if (!(sceneValue instanceof List<?> scenes) || scenes.isEmpty()) {
            throw new IllegalArgumentException("章节计划场景必须是非空列表");
        }
        List<Map<String, Object>> normalizedScenes = new ArrayList<>();
        for (int index = 0; index < scenes.size(); index++) {
            normalizedScenes.add(normalizeScene(scenes.get(index), index));
        }
        Map<String, Object> result = new LinkedHashMap<>(raw);
        result.put("chapterGoal", chapterGoal);
        result.put("sceneBeats", normalizedScenes);
        return result;
    }

    private static Map<String, Object> normalizeScene(Object raw, int index) {
        if (!(raw instanceof Map<?, ?> values)) {
            throw new IllegalArgumentException("章节计划场景必须是对象");
        }
        Map<String, Object> scene = stringMap(values);
        java.util.Set<String> allowed = java.util.Set.of(
                "order",
                "goal",
                "conflict",
                "characters",
                "foreshadowingRefs",
                "estimatedWords",
                "acceptanceCriteria",
                "sceneName",
                "sceneGoal",
                "foreshadowingReferences");
        if (!allowed.containsAll(scene.keySet())) {
            throw new IllegalArgumentException("章节计划场景包含未知字段");
        }
        Map<String, Object> result = new LinkedHashMap<>(scene);
        String goal = nonEmptyString(scene.get("goal"));
        if (goal != null) {
            if (scene.containsKey("sceneName") || scene.containsKey("sceneGoal")) {
                throw new IllegalArgumentException(
                        "章节计划场景不能同时包含 goal 与 sceneName/sceneGoal");
            }
        } else {
            String name = trimmedString(scene.get("sceneName"));
            String legacyGoal = trimmedString(scene.get("sceneGoal"));
            if (name == null) throw new IllegalArgumentException("章节计划旧场景缺少有效 sceneName");
            if (legacyGoal == null) {
                throw new IllegalArgumentException("章节计划场景缺少有效 goal 或 sceneGoal");
            }
            goal = name + "：" + legacyGoal;
            result.remove("sceneName");
            result.remove("sceneGoal");
        }
        result.put("goal", goal);
        Object orderValue = scene.get("order");
        if (orderValue == null) {
            result.put("order", index + 1);
        } else if (!(orderValue instanceof Integer order) || order < 1) {
            throw new IllegalArgumentException("章节计划场景 order 必须是正整数");
        }
        Object characterValue = scene.getOrDefault("characters", List.of());
        if (characterValue instanceof String text) {
            List<String> names = java.util.Arrays.stream(text.split("[、，,]"))
                    .map(String::strip)
                    .filter(value -> !value.isEmpty())
                    .toList();
            result.put("characters", names);
        } else {
            result.put("characters", stringList(characterValue, "characters"));
        }
        if (scene.containsKey("foreshadowingRefs")) {
            if (scene.containsKey("foreshadowingReferences")) {
                throw new IllegalArgumentException(
                        "章节计划场景不能同时包含 foreshadowingRefs 与 foreshadowingReferences");
            }
            if (scene.get("foreshadowingRefs") != null) {
                result.put("foreshadowingRefs",
                        stringList(scene.get("foreshadowingRefs"), "foreshadowingRefs"));
            }
        } else if (scene.containsKey("foreshadowingReferences")) {
            String legacy = optionalString(scene.get("foreshadowingReferences"));
            if (legacy == null) {
                throw new IllegalArgumentException(
                        "章节计划旧场景 foreshadowingReferences 必须是字符串");
            }
            result.put("foreshadowingRefs", legacy.strip().isEmpty()
                    ? List.of()
                    : List.of(legacy));
            result.remove("foreshadowingReferences");
        }
        requireNonNegativeInteger(scene, "estimatedWords");
        requireOptionalString(scene, "conflict");
        if (scene.containsKey("acceptanceCriteria")
                && nonEmptyString(scene.get("acceptanceCriteria")) == null) {
            throw new IllegalArgumentException(
                    "章节计划场景 acceptanceCriteria 必须是非空字符串");
        }
        return result;
    }

    private static void requireSelectionMatches(
            Map<String, Object> payload,
            String source,
            LocalDateTime currentUpdatedAt,
            String resourceType,
            String resourceId) {
        int start = integer(payload.get("selectionStart"));
        int end = integer(payload.get("selectionEnd"));
        int length = ReviewArtifactRules.codePointLength(source);
        String selected = start >= 0 && end > start && end <= length
                ? ReviewArtifactRules.slice(source, start, end)
                : null;
        OffsetDateTime expectedUpdatedAt;
        try {
            expectedUpdatedAt = OffsetDateTime.parse(string(payload.get("baseUpdatedAt")));
        } catch (DateTimeParseException | NullPointerException exception) {
            throw selectionConflict(resourceType, resourceId);
        }
        boolean matches = DatabaseTimestamp.api(currentUpdatedAt).toInstant()
                        .equals(expectedUpdatedAt.toInstant())
                && Objects.equals(
                        ReviewArtifactRules.sha256(source), payload.get("baseContentHash"))
                && selected != null
                && Objects.equals(
                        ReviewArtifactRules.sha256(selected), payload.get("selectedTextHash"))
                && (payload.get("selectedText") == null
                        || Objects.equals(payload.get("selectedText"), selected))
                && (payload.get("candidatePrefix") == null
                        || Objects.equals(
                                payload.get("candidatePrefix"),
                                ReviewArtifactRules.slice(source, 0, start)))
                && (payload.get("candidateSuffix") == null
                        || Objects.equals(
                                payload.get("candidateSuffix"),
                                ReviewArtifactRules.slice(source, end, length)));
        if (!matches) throw selectionConflict(resourceType, resourceId);
    }

    private static String splice(String source, int start, int end, String replacement) {
        int length = ReviewArtifactRules.codePointLength(source);
        if (start < 0 || end <= start || end > length) {
            throw new IllegalArgumentException("选区草案范围无效");
        }
        return ReviewArtifactRules.slice(source, 0, start)
                + replacement
                + ReviewArtifactRules.slice(source, end, length);
    }

    private static String resolveTarget(Map<String, Object> payload) {
        Object targetValue = payload.get("target");
        if (targetValue instanceof Map<?, ?> target) {
            Object mode = target.get("mode");
            if (List.of(
                            "replace_selection",
                            "outline_content_selection",
                            "outline_node_content_selection")
                    .contains(mode)) {
                return List.of("chapter_draft", "outline_draft").contains(payload.get("kind"))
                        ? "selection"
                        : null;
            }
            if (mode != null
                    && !List.of("existing_chapter", "new_next_chapter", "normal_outline")
                            .contains(mode)) return null;
        }
        Object kind = payload.get("kind");
        if ("agent_updates".equals(kind)) return "agent_updates";
        if ("outline_draft".equals(kind)) return "outline_content";
        if ("chapter_content".equals(kind) || "chapter_draft".equals(kind)) {
            return "chapter_content";
        }
        if ("beat_plan".equals(kind) || "beat_plan_draft".equals(kind)) {
            return "beat_plan";
        }
        return null;
    }

    private static ApiException selectionConflict(String resourceType, String resourceId) {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("resourceType", resourceType);
        details.put("resourceId", resourceId);
        return new ApiException(
                409,
                "ARTIFACT_SOURCE_VERSION_CONFLICT",
                "选区草案的来源版本已变化",
                details);
    }

    private static Map<String, Object> stringMap(Map<?, ?> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalArgumentException("JSON 对象键必须是字符串");
            }
            result.put(key, entry.getValue());
        }
        return result;
    }

    private static List<String> stringList(Object value, String field) {
        if (!(value instanceof List<?> values)
                || values.stream().anyMatch(item -> !(item instanceof String text) || text.isEmpty())) {
            throw new IllegalArgumentException("章节计划场景 " + field + " 只能包含非空字符串");
        }
        return values.stream().map(String.class::cast).toList();
    }

    private static void requireOptionalString(Map<String, Object> value, String field) {
        if (value.containsKey(field)
                && value.get(field) != null
                && !(value.get(field) instanceof String)) {
            throw new IllegalArgumentException(field + " 必须是字符串");
        }
    }

    private static void requireNonNegativeInteger(Map<String, Object> value, String field) {
        if (value.containsKey(field)
                && value.get(field) != null
                && (!(value.get(field) instanceof Integer number) || number < 0)) {
            throw new IllegalArgumentException(field + " 必须是非负整数");
        }
    }

    private static String nonEmptyString(Object value) {
        return value instanceof String text && !text.isEmpty() ? text : null;
    }

    private static String trimmedString(Object value) {
        return value instanceof String text && !text.strip().isEmpty() ? text.strip() : null;
    }

    private static String optionalString(Object value) {
        return value instanceof String text ? text : null;
    }

    private static int integer(Object value) {
        return value instanceof Integer number ? number : -1;
    }

    private static int optionalInteger(Object value, int fallback) {
        return value instanceof Integer number ? number : fallback;
    }

    private static OffsetDateTime optionalTime(Object value, String field) {
        if (value == null) return null;
        if (!(value instanceof String text) || text.isEmpty()) {
            throw new IllegalArgumentException(field + " 必须是 ISO 8601 时间");
        }
        try {
            return OffsetDateTime.parse(text);
        } catch (DateTimeParseException exception) {
            throw new IllegalArgumentException(field + " 必须是 ISO 8601 时间");
        }
    }

    private static Map<String, OffsetDateTime> optionalTimeMap(Object value) {
        if (value == null) return null;
        if (!(value instanceof Map<?, ?> raw)) {
            throw new IllegalArgumentException("baseLoreUpdatedAt 必须是对象");
        }
        Map<String, Object> source = stringMap(raw);
        if (!java.util.Set.of("worldSetting", "storyBackground").containsAll(source.keySet())) {
            throw new IllegalArgumentException("baseLoreUpdatedAt 包含未知字段");
        }
        Map<String, OffsetDateTime> result = new LinkedHashMap<>();
        source.forEach((key, item) -> result.put(key, optionalTime(item, "baseLoreUpdatedAt." + key)));
        return result;
    }

    private static void requireOwner(DSLContext context, String novelId, String userId) {
        String owner = context.select(NOVEL.USERID)
                .from(NOVEL)
                .where(NOVEL.ID.eq(novelId))
                .forUpdate()
                .fetchOne(NOVEL.USERID);
        if (!Objects.equals(owner, userId)) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
    }

    private static String string(Object value) {
        return value instanceof String text ? text : null;
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }
}
