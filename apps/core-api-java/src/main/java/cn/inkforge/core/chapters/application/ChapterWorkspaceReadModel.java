package cn.inkforge.core.chapters.application;

import static cn.inkforge.core.db.generated.Tables.CHAPTERBEATPLAN;
import static cn.inkforge.core.db.generated.Tables.CHAPTERPROGRESS;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.SCENEBEAT;

import cn.inkforge.contracts.api.BeatPlanDto;
import cn.inkforge.contracts.api.BeatPlanStatus;
import cn.inkforge.contracts.api.ApprovedBeatPlanSummary;
import cn.inkforge.contracts.api.ChapterProgressDto;
import cn.inkforge.contracts.api.ChapterStatus;
import cn.inkforge.contracts.api.QualityCheckDto;
import cn.inkforge.contracts.api.QualityCheckStatus;
import cn.inkforge.contracts.api.QualityCheckType;
import cn.inkforge.contracts.api.QualityGate;
import cn.inkforge.contracts.api.SceneBeatDto;
import cn.inkforge.contracts.api.WorkspaceChapter;
import cn.inkforge.core.chapters.domain.TextLength;
import cn.inkforge.core.db.generated.enums.Beatplanstatus;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.db.generated.tables.records.ChapterbeatplanRecord;
import cn.inkforge.core.db.generated.tables.records.ChapterprogressRecord;
import cn.inkforge.core.db.generated.tables.records.ChapterqualitycheckRecord;
import cn.inkforge.core.db.generated.tables.records.ScenebeatRecord;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.jooq.DSLContext;

/** 章节聚合只读映射；批量加载相关行，查询数不随章节数量线性增长。 */
public final class ChapterWorkspaceReadModel {

    /** 为工作区启动页批量读取每章最新正式 Beat Plan 的轻量摘要。 */
    public Map<String, ApprovedBeatPlanSummary> approvedPlanSummaries(
            DSLContext context, List<String> chapterIds) {
        if (chapterIds.isEmpty()) return Map.of();
        Map<String, ChapterbeatplanRecord> latestPlanByChapter = new LinkedHashMap<>();
        context.selectFrom(CHAPTERBEATPLAN)
                .where(
                        CHAPTERBEATPLAN.CHAPTERID.in(chapterIds),
                        CHAPTERBEATPLAN.STATUS.eq(Beatplanstatus.approved))
                .orderBy(CHAPTERBEATPLAN.UPDATEDAT.desc(), CHAPTERBEATPLAN.ID.asc())
                .fetch()
                .forEach(value -> latestPlanByChapter.putIfAbsent(value.getChapterid(), value));
        if (latestPlanByChapter.isEmpty()) return Map.of();

        Map<String, Integer> sceneCountByPlan = new HashMap<>();
        context.select(SCENEBEAT.BEATPLANID, org.jooq.impl.DSL.count())
                .from(SCENEBEAT)
                .where(SCENEBEAT.BEATPLANID.in(latestPlanByChapter.values().stream()
                        .map(ChapterbeatplanRecord::getId)
                        .toList()))
                .groupBy(SCENEBEAT.BEATPLANID)
                .forEach(row -> sceneCountByPlan.put(
                        row.get(SCENEBEAT.BEATPLANID),
                        row.get(org.jooq.impl.DSL.count())));
        Map<String, ApprovedBeatPlanSummary> result = new HashMap<>();
        latestPlanByChapter.forEach((chapterId, plan) -> result.put(
                chapterId,
                new ApprovedBeatPlanSummary(
                        sceneCountByPlan.getOrDefault(plan.getId(), 0),
                        plan.getTotalestimatedwords())));
        return Map.copyOf(result);
    }

    public List<WorkspaceChapter> load(
            DSLContext context, List<ChapterRecord> chapters) {
        if (chapters.isEmpty()) {
            return List.of();
        }
        List<String> chapterIds = chapters.stream().map(ChapterRecord::getId).toList();
        Map<String, ChapterprogressRecord> progressByChapter = new HashMap<>();
        context.selectFrom(CHAPTERPROGRESS)
                .where(CHAPTERPROGRESS.CHAPTERID.in(chapterIds))
                .fetch()
                .forEach(value -> progressByChapter.put(value.getChapterid(), value));

        Map<String, List<ChapterqualitycheckRecord>> checksByChapter = new HashMap<>();
        context.selectFrom(CHAPTERQUALITYCHECK)
                .where(CHAPTERQUALITYCHECK.CHAPTERID.in(chapterIds))
                .orderBy(CHAPTERQUALITYCHECK.CREATEDAT.asc(), CHAPTERQUALITYCHECK.ID.asc())
                .fetch()
                .forEach(value -> checksByChapter
                        .computeIfAbsent(value.getChapterid(), ignored -> new ArrayList<>())
                        .add(value));

        Map<String, ChapterbeatplanRecord> latestPlanByChapter = new LinkedHashMap<>();
        context.selectFrom(CHAPTERBEATPLAN)
                .where(
                        CHAPTERBEATPLAN.CHAPTERID.in(chapterIds),
                        CHAPTERBEATPLAN.STATUS.eq(Beatplanstatus.approved))
                .orderBy(CHAPTERBEATPLAN.UPDATEDAT.desc(), CHAPTERBEATPLAN.ID.asc())
                .fetch()
                .forEach(value -> latestPlanByChapter.putIfAbsent(value.getChapterid(), value));

        Map<String, List<ScenebeatRecord>> beatsByPlan = new HashMap<>();
        List<String> planIds = latestPlanByChapter.values().stream()
                .map(ChapterbeatplanRecord::getId)
                .toList();
        if (!planIds.isEmpty()) {
            context.selectFrom(SCENEBEAT)
                    .where(SCENEBEAT.BEATPLANID.in(planIds))
                    .orderBy(SCENEBEAT.ORDER.asc(), SCENEBEAT.ID.asc())
                    .fetch()
                    .forEach(value -> beatsByPlan
                            .computeIfAbsent(value.getBeatplanid(), ignored -> new ArrayList<>())
                            .add(value));
        }

        return chapters.stream()
                .map(chapter -> map(
                        chapter,
                        progressByChapter.get(chapter.getId()),
                        checksByChapter.getOrDefault(chapter.getId(), List.of()),
                        latestPlanByChapter.get(chapter.getId()),
                        beatsByPlan))
                .toList();
    }

    private static WorkspaceChapter map(
            ChapterRecord chapter,
            ChapterprogressRecord progress,
            List<ChapterqualitycheckRecord> checks,
            ChapterbeatplanRecord plan,
            Map<String, List<ScenebeatRecord>> beatsByPlan) {
        WorkspaceChapter result = new WorkspaceChapter();
        result.setId(chapter.getId());
        result.setTitle(chapter.getTitle());
        result.setContent(chapter.getContent());
        result.setOrder(chapter.getOrder());
        result.setStatus(ChapterStatus.fromValue(chapter.getStatus().getLiteral()));
        result.setCompletedAt(DatabaseTimestamp.api(chapter.getCompletedat()));
        result.setCreatedAt(DatabaseTimestamp.api(chapter.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(chapter.getUpdatedat()));
        result.setWordCount(TextLength.count(chapter.getContent()));
        result.setProgress(progress == null ? null : progress(progress));
        result.setQualityChecks(checks.stream()
                .map(ChapterWorkspaceReadModel::quality)
                .toList());
        result.setApprovedBeatPlan(
                plan == null
                        ? null
                        : plan(plan, beatsByPlan.getOrDefault(plan.getId(), List.of())));
        return result;
    }

    private static ChapterProgressDto progress(ChapterprogressRecord value) {
        ChapterProgressDto result = new ChapterProgressDto();
        result.setId(value.getId());
        result.setChapterId(value.getChapterid());
        result.setContent(value.getContent());
        result.setCreatedAt(DatabaseTimestamp.api(value.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
        return result;
    }

    private static QualityCheckDto quality(ChapterqualitycheckRecord value) {
        QualityCheckDto result = new QualityCheckDto();
        result.setId(value.getId());
        result.setChapterId(value.getChapterid());
        result.setType(QualityCheckType.fromValue(value.getType().getLiteral()));
        result.setStatus(QualityCheckStatus.fromValue(value.getStatus().getLiteral()));
        result.setTitle(value.getTitle());
        result.setSummary(value.getSummary());
        result.setResult(value.getResult());
        result.setScoreHook(value.getScorehook());
        result.setScoreTension(value.getScoretension());
        result.setScorePayoff(value.getScorepayoff());
        result.setScorePacing(value.getScorepacing());
        result.setScoreEndingHook(value.getScoreendinghook());
        result.setScoreReaderPromise(value.getScorereaderpromise());
        result.setScoreOverall(value.getScoreoverall());
        result.setQualityGate(
                value.getQualitygate() == null
                        ? null
                        : QualityGate.fromValue(value.getQualitygate()));
        result.setRewriteBrief(value.getRewritebrief());
        result.setCreatedAt(DatabaseTimestamp.api(value.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
        return result;
    }

    private static BeatPlanDto plan(
            ChapterbeatplanRecord value, List<ScenebeatRecord> beats) {
        BeatPlanDto result = new BeatPlanDto();
        result.setId(value.getId());
        result.setChapterId(value.getChapterid());
        result.setGoalId(value.getGoalid());
        result.setStatus(BeatPlanStatus.fromValue(value.getStatus().getLiteral()));
        result.setChapterGoal(value.getChaptergoal());
        result.setMainPlotConnection(value.getMainplotconnection());
        result.setChapterAcceptanceCriteria(value.getChapteracceptancecriteria());
        result.setTotalEstimatedWords(value.getTotalestimatedwords());
        result.setGeneratedBy(value.getGeneratedby());
        result.setCreatedAt(DatabaseTimestamp.api(value.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
        result.setSceneBeats(beats.stream()
                .map(ChapterWorkspaceReadModel::beat)
                .toList());
        return result;
    }

    private static SceneBeatDto beat(ScenebeatRecord value) {
        SceneBeatDto result = new SceneBeatDto();
        result.setId(value.getId());
        result.setOrder(value.getOrder());
        result.setGoal(value.getGoal());
        result.setConflict(value.getConflict());
        result.setCharacters(value.getCharacters());
        result.setForeshadowingRefs(value.getForeshadowingrefs());
        result.setEstimatedWords(value.getEstimatedwords());
        result.setAcceptanceCriteria(value.getAcceptancecriteria());
        return result;
    }
}
