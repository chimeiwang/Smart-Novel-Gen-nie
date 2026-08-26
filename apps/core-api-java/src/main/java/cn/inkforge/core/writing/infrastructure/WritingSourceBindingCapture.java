package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERBEATPLAN;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.SCENEBEAT;

import cn.inkforge.core.db.generated.enums.Beatplanstatus;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.db.generated.tables.records.ChapterbeatplanRecord;
import cn.inkforge.core.db.generated.tables.records.OutlineRecord;
import cn.inkforge.core.db.generated.tables.records.ScenebeatRecord;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/** 在统一事务锁内冻结章节、总纲和已批准 Beat Plan 的来源事实。 */
final class WritingSourceBindingCapture {

    private final ObjectMapper json;

    WritingSourceBindingCapture(ObjectMapper json) {
        this.json = java.util.Objects.requireNonNull(json);
    }

    List<Map<String, Object>> capture(
            DSLContext transaction, String novelId, String chapterId) {
        String lockedNovel = transaction.select(NOVEL.ID)
                .from(NOVEL)
                .where(NOVEL.ID.eq(novelId))
                .forUpdate()
                .fetchOne(NOVEL.ID);
        if (!novelId.equals(lockedNovel)) {
            throw new ApiException(404, "NOVEL_NOT_FOUND", "小说不存在");
        }
        ChapterRecord chapter = transaction.selectFrom(CHAPTER)
                .where(CHAPTER.ID.eq(chapterId), CHAPTER.NOVELID.eq(novelId))
                .forUpdate()
                .fetchOne();
        if (chapter == null) {
            throw new ApiException(404, "CHAPTER_NOT_FOUND", "章节不存在或不属于该小说");
        }
        OutlineRecord outline = transaction.selectFrom(OUTLINE)
                .where(OUTLINE.NOVELID.eq(novelId))
                .forUpdate()
                .fetchOne();
        List<ChapterbeatplanRecord> plans = transaction.selectFrom(CHAPTERBEATPLAN)
                .where(
                        CHAPTERBEATPLAN.CHAPTERID.eq(chapterId),
                        CHAPTERBEATPLAN.STATUS.eq(Beatplanstatus.approved))
                .orderBy(CHAPTERBEATPLAN.ID.asc())
                .forUpdate()
                .fetch();
        if (plans.size() > 1) {
            throw new ApiException(
                    409,
                    "BEAT_PLAN_SOURCE_AMBIGUOUS",
                    "章节存在多个已批准计划，无法确定权威来源",
                    Map.of("chapterId", chapterId));
        }

        List<Map<String, Object>> bindings = new ArrayList<>();
        bindings.add(existingText(
                "chapter", chapter.getId(), chapter.getUpdatedat(), chapter.getContent()));
        bindings.add(outline == null
                ? absent(
                        "outline",
                        "novel:" + novelId + ":outline",
                        "novel",
                        novelId)
                : existingText(
                        "outline", outline.getId(), outline.getUpdatedat(), outline.getContent()));
        if (plans.isEmpty()) {
            bindings.add(absent(
                    "approved_beat_plan",
                    "chapter:" + chapterId + ":approved_beat_plan",
                    "chapter",
                    chapterId));
        } else {
            ChapterbeatplanRecord plan = plans.getFirst();
            List<ScenebeatRecord> beats = transaction.selectFrom(SCENEBEAT)
                    .where(SCENEBEAT.BEATPLANID.eq(plan.getId()))
                    .orderBy(SCENEBEAT.ORDER.asc(), SCENEBEAT.ID.asc())
                    .forUpdate()
                    .fetch();
            bindings.add(approvedPlan(plan, beats));
        }
        return List.copyOf(bindings);
    }

    private Map<String, Object> existingText(
            String resourceType,
            String resourceId,
            java.time.LocalDateTime updatedAt,
            String content) {
        Map<String, Object> result = emptyBinding(resourceType, resourceId, true);
        result.put("updatedAt", DatabaseTimestamp.api(updatedAt));
        result.put("contentSha256", sha256(content));
        return result;
    }

    private Map<String, Object> absent(
            String resourceType,
            String resourceId,
            String sentinelType,
            String sentinelId) {
        Map<String, Object> result = emptyBinding(resourceType, resourceId, false);
        result.put("absenceSentinel", Map.of(
                "resourceType", sentinelType,
                "resourceId", sentinelId));
        return result;
    }

    private Map<String, Object> approvedPlan(
            ChapterbeatplanRecord plan, List<ScenebeatRecord> beats) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("id", plan.getId());
        payload.put("chapterId", plan.getChapterid());
        payload.put("goalId", plan.getGoalid());
        payload.put("status", plan.getStatus().getLiteral());
        payload.put("chapterGoal", plan.getChaptergoal());
        payload.put("mainPlotConnection", plan.getMainplotconnection());
        payload.put("chapterAcceptanceCriteria", plan.getChapteracceptancecriteria());
        payload.put("totalEstimatedWords", plan.getTotalestimatedwords());
        payload.put("generatedBy", plan.getGeneratedby());
        payload.put("createdAt", DatabaseTimestamp.api(plan.getCreatedat()));
        payload.put("updatedAt", DatabaseTimestamp.api(plan.getUpdatedat()));
        payload.put("sceneBeats", beats.stream().map(beat -> {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("id", beat.getId());
            value.put("order", beat.getOrder());
            value.put("goal", beat.getGoal());
            value.put("conflict", beat.getConflict());
            value.put("characters", beat.getCharacters());
            value.put("foreshadowingRefs", beat.getForeshadowingrefs());
            value.put("estimatedWords", beat.getEstimatedwords());
            value.put("acceptanceCriteria", beat.getAcceptancecriteria());
            return value;
        }).toList());
        Map<String, Object> result = emptyBinding(
                "approved_beat_plan", plan.getId(), true);
        result.put("updatedAt", DatabaseTimestamp.api(plan.getUpdatedat()));
        result.put(
                "contentSha256",
                CommandIdempotency.sha256(CommandIdempotency.canonicalJsonBytes(payload, json)));
        return result;
    }

    private static Map<String, Object> emptyBinding(
            String resourceType, String resourceId, boolean exists) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("resourceType", resourceType);
        result.put("resourceId", resourceId);
        result.put("exists", exists);
        result.put("updatedAt", null);
        result.put("contentSha256", null);
        result.put("revision", null);
        result.put("absenceSentinel", null);
        return result;
    }

    private static String sha256(String value) {
        return CommandIdempotency.sha256(value.getBytes(StandardCharsets.UTF_8));
    }
}
