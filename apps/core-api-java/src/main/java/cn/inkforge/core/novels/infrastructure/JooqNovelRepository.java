package cn.inkforge.core.novels.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.PLOTPROGRESS;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTREVISION;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static cn.inkforge.core.db.generated.Tables.WRITINGSTYLE;

import cn.inkforge.contracts.api.AppliedStyleSummary;
import cn.inkforge.contracts.api.ChapterIdSummary;
import cn.inkforge.contracts.api.CreateNovelResponse;
import cn.inkforge.contracts.api.DashboardNovel;
import cn.inkforge.contracts.api.DashboardResponse;
import cn.inkforge.contracts.api.NovelResponse;
import cn.inkforge.contracts.api.StoryLengthProfile;
import cn.inkforge.contracts.api.WorkspaceBootstrapResponse;
import cn.inkforge.contracts.api.WorkspaceLoreResponse;
import cn.inkforge.contracts.api.WorkspacePlanningResponse;
import cn.inkforge.contracts.api.WorkspaceResourcesResponse;
import cn.inkforge.contracts.api.WorkspaceResponse;
import cn.inkforge.contracts.api.WorkspaceNovel;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.tables.records.NovelRecord;
import cn.inkforge.core.db.generated.tables.records.WritingstyleRecord;
import cn.inkforge.core.novels.application.NovelRepository;
import cn.inkforge.core.novels.domain.NovelCreation;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.Condition;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.impl.DSL;
import tools.jackson.databind.ObjectMapper;

/**
 * PostgreSQL 小说与工作区聚合仓储。
 *
 * <p>创建在一个事务内建立小说、首章、大纲、进展和写作圣经；中短篇还保存完整起始素材及首个 revision，
 * 并用作者行串行化 {@code clientRequestId} 重放。工作区分片读仍共享同一只读事务快照，避免跨请求拼接漂移数据。
 */
public final class JooqNovelRepository implements NovelRepository {

    private static final String SHORT_SOURCE_KEY_PREFIX = "short-medium:source:";
    private static final String CREATION_SUMMARY_PREFIX = "创建请求摘要：";

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final NovelReadMapper mapper = new NovelReadMapper();
    private final WorkspaceReadTransaction workspaceTransactions;
    private final WorkspaceChapterReader workspaceChapters = new WorkspaceChapterReader();
    private final WorkspaceLoreReader workspaceLore = new WorkspaceLoreReader();
    private final WorkspacePlanningReader workspacePlanning = new WorkspacePlanningReader();
    private final WorkspaceResourcesReader workspaceResources = new WorkspaceResourcesReader();

    public JooqNovelRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.workspaceTransactions = new WorkspaceReadTransaction(database);
    }

    @Override
    public CreateNovelResponse create(NovelCreation creation) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            if (creation.clientRequestId() != null) {
                // 与 Python Core 一致：锁作者行，让同一作者的创建重试先完成再查重。
                transaction.select(USER.ID)
                        .from(USER)
                        .where(USER.ID.eq(creation.userId()))
                        .forUpdate()
                        .fetchOne();
                CreateNovelResponse replay = findShortMediumCreation(
                        transaction, creation.userId(), creation.clientRequestId());
                if (replay != null) return replay;
            }

            LocalDateTime now = DatabaseTimestamp.now(clock);
            String novelId = ids.next();
            String chapterId = ids.next();
            // 这些基础行共同定义“作品已创建”；任一写入失败都必须回滚，不能留下缺大纲或写作圣经的半作品。
            transaction.insertInto(NOVEL)
                    .set(NOVEL.ID, novelId)
                    .set(NOVEL.NAME, creation.name())
                    .set(NOVEL.SUMMARY, creation.summary())
                    .set(NOVEL.STORYPROGRESS, creation.storyProgress())
                    .set(NOVEL.USERID, creation.userId())
                    .set(NOVEL.CREATEDAT, now)
                    .set(NOVEL.UPDATEDAT, now)
                    .execute();
            transaction.insertInto(CHAPTER)
                    .set(CHAPTER.ID, chapterId)
                    .set(CHAPTER.NOVELID, novelId)
                    .set(CHAPTER.TITLE, creation.firstChapterTitle())
                    .set(CHAPTER.CONTENT, creation.chapterContent())
                    .set(CHAPTER.ORDER, creation.firstChapterOrder())
                    .set(CHAPTER.STATUS, Chapterstatus.drafting)
                    .set(CHAPTER.CREATEDAT, now)
                    .set(CHAPTER.UPDATEDAT, now)
                    .execute();
            transaction.insertInto(OUTLINE)
                    .set(OUTLINE.ID, ids.next())
                    .set(OUTLINE.NOVELID, novelId)
                    .set(OUTLINE.CONTENT, creation.outlineContent())
                    .set(OUTLINE.CREATEDAT, now)
                    .set(OUTLINE.UPDATEDAT, now)
                    .execute();
            transaction.insertInto(PLOTPROGRESS)
                    .set(PLOTPROGRESS.ID, ids.next())
                    .set(PLOTPROGRESS.NOVELID, novelId)
                    .set(PLOTPROGRESS.CURRENTSTAGE, creation.currentStage())
                    .set(PLOTPROGRESS.CURRENTGOAL, creation.currentGoal())
                    .set(PLOTPROGRESS.UPDATEDAT, now)
                    .execute();
            Storylengthprofile profile = Storylengthprofile.lookupLiteral(
                    creation.storyLengthProfile());
            if (profile == null) {
                throw new IllegalArgumentException("未知篇幅类型：" + creation.storyLengthProfile());
            }
            transaction.insertInto(WRITINGBIBLE)
                    .set(WRITINGBIBLE.ID, ids.next())
                    .set(WRITINGBIBLE.NOVELID, novelId)
                    .set(WRITINGBIBLE.GENRE, creation.genre())
                    .set(WRITINGBIBLE.CORESELLINGPOINT, creation.coreSellingPoint())
                    .set(WRITINGBIBLE.READERPROMISE, creation.readerPromise())
                    .set(WRITINGBIBLE.NOTES, creation.notes())
                    .set(WRITINGBIBLE.CREATEDAT, now)
                    .set(WRITINGBIBLE.UPDATEDAT, now)
                    .set(WRITINGBIBLE.STORYLENGTHPROFILE, profile)
                    .set(WRITINGBIBLE.TARGETTOTALWORDCOUNT, creation.targetTotalWordCount())
                    .execute();

            if (creation.sourceKind() != null && creation.sourceText() != null) {
                saveShortMediumSource(transaction, creation, novelId, now);
            }
            return new CreateNovelResponse(chapterId, novelId);
        });
    }

    @Override
    public DashboardResponse dashboard(String userId) {
        DSLContext context = database.dsl();
        List<NovelRecord> novels = context.selectFrom(NOVEL)
                .where(NOVEL.USERID.eq(userId))
                .orderBy(NOVEL.UPDATEDAT.desc(), NOVEL.ID.asc())
                .fetch();
        if (novels.isEmpty()) return new DashboardResponse(List.of());

        List<String> novelIds = novels.stream().map(NovelRecord::getId).toList();
        Map<String, List<ChapterIdSummary>> chapters = new HashMap<>();
        context.select(CHAPTER.NOVELID, CHAPTER.ID)
                .from(CHAPTER)
                .where(CHAPTER.NOVELID.in(novelIds))
                .orderBy(CHAPTER.ORDER.asc(), CHAPTER.ID.asc())
                .forEach(row -> chapters
                        .computeIfAbsent(row.get(CHAPTER.NOVELID), ignored -> new ArrayList<>())
                        .add(new ChapterIdSummary(row.get(CHAPTER.ID))));

        List<String> styleIds = novels.stream()
                .map(NovelRecord::getAppliedstyleid)
                .filter(Objects::nonNull)
                .distinct()
                .toList();
        Map<String, WritingstyleRecord> styles = styleIds.isEmpty()
                ? Map.of()
                : context.selectFrom(WRITINGSTYLE)
                        .where(WRITINGSTYLE.ID.in(styleIds)
                                .and(WRITINGSTYLE.USERID.eq(userId)))
                        .fetchMap(WRITINGSTYLE.ID);

        List<DashboardNovel> values = novels.stream()
                .map(novel -> dashboardNovel(
                        novel,
                        chapters.getOrDefault(novel.getId(), List.of()),
                        novel.getAppliedstyleid() == null
                                ? null
                                : styles.get(novel.getAppliedstyleid())))
                .toList();
        return new DashboardResponse(values);
    }

    @Override
    public List<NovelResponse> list(String userId, StoryLengthProfile profile) {
        Condition condition = NOVEL.USERID.eq(userId);
        if (profile != null) {
            condition = condition.and(WRITINGBIBLE.STORYLENGTHPROFILE.eq(
                    Storylengthprofile.lookupLiteral(profile.getValue())));
        }
        return database.dsl()
                .select(NOVEL.fields())
                .select(
                        WRITINGBIBLE.STORYLENGTHPROFILE,
                        WRITINGBIBLE.TARGETTOTALWORDCOUNT)
                .from(NOVEL)
                .leftJoin(WRITINGBIBLE)
                .on(WRITINGBIBLE.NOVELID.eq(NOVEL.ID))
                .where(condition)
                .orderBy(NOVEL.UPDATEDAT.desc(), NOVEL.ID.asc())
                .fetch(this::mapNovel);
    }

    @Override
    public NovelResponse get(String novelId, String userId) {
        DSLContext context = database.dsl();
        NovelRecord novel = requireOwner(context, novelId, userId, false);
        Record bible = context.select(
                        WRITINGBIBLE.STORYLENGTHPROFILE,
                        WRITINGBIBLE.TARGETTOTALWORDCOUNT)
                .from(WRITINGBIBLE)
                .where(WRITINGBIBLE.NOVELID.eq(novelId))
                .fetchOne();
        return mapper.novel(
                novel,
                bible == null ? null : bible.get(WRITINGBIBLE.STORYLENGTHPROFILE),
                bible == null ? null : bible.get(WRITINGBIBLE.TARGETTOTALWORDCOUNT));
    }

    @Override
    public NovelResponse updateSummary(
            String novelId,
            String userId,
            String summary,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            NovelRecord novel = requireOwner(transaction, novelId, userId, true);
            requireVersion(novel.getUpdatedat(), expectedUpdatedAt);
            if (!Objects.equals(novel.getSummary(), summary)) {
                LocalDateTime updatedAt = DatabaseTimestamp.next(clock, novel.getUpdatedat());
                transaction.update(NOVEL)
                        .set(NOVEL.SUMMARY, summary)
                        .set(NOVEL.UPDATEDAT, updatedAt)
                        .where(NOVEL.ID.eq(novelId))
                        .execute();
                novel.setSummary(summary);
                novel.setUpdatedat(updatedAt);
            }
            Record bible = transaction.select(
                            WRITINGBIBLE.STORYLENGTHPROFILE,
                            WRITINGBIBLE.TARGETTOTALWORDCOUNT)
                    .from(WRITINGBIBLE)
                    .where(WRITINGBIBLE.NOVELID.eq(novelId))
                    .fetchOne();
            return mapper.novel(
                    novel,
                    bible == null ? null : bible.get(WRITINGBIBLE.STORYLENGTHPROFILE),
                    bible == null ? null : bible.get(WRITINGBIBLE.TARGETTOTALWORDCOUNT));
        });
    }

    @Override
    public WorkspaceResponse workspace(String novelId, String userId, String chapterId) {
        return workspaceTransactions.read(novelId, userId, false, (transaction, novel) -> {
            // 各 reader 只负责投影自己的数据域，但全部复用当前 transaction，保证一次响应内部视图一致。
            WorkspaceChapterReader.FullChapters chapters =
                    workspaceChapters.full(transaction, novelId, chapterId);
            WorkspaceLoreResponse lore = workspaceLore.read(transaction, novelId);
            WorkspacePlanningResponse planning = workspacePlanning.read(transaction, novel);
            WorkspaceResourcesResponse resources =
                    workspaceResources.read(transaction, novel, userId);
            WorkspaceResponse response = new WorkspaceResponse();
            response.setNovel(workspaceNovel(novel, planning, resources.getAppliedStyle()));
            response.setChapters(chapters.chapters());
            response.setCurrentChapterId(chapters.currentChapterId());
            response.setCharacters(lore.getCharacters());
            response.setItems(lore.getItems());
            response.setLocations(lore.getLocations());
            response.setFactions(lore.getFactions());
            response.setGlossaries(lore.getGlossaries());
            response.setStoryBackground(planning.getStoryBackground());
            response.setWorldSetting(planning.getWorldSetting());
            response.setWritingBible(planning.getWritingBible());
            response.setOutline(planning.getOutline());
            response.setOutlineNodes(planning.getOutlineNodes());
            response.setPlotProgress(planning.getPlotProgress());
            response.setReferences(resources.getReferences());
            response.setStyles(resources.getStyles());
            return response;
        });
    }

    @Override
    public WorkspaceBootstrapResponse workspaceBootstrap(
            String novelId, String userId, String chapterId) {
        return workspaceTransactions.read(novelId, userId, true, (transaction, novel) -> {
            WorkspaceChapterReader.BootstrapChapters chapters =
                    workspaceChapters.bootstrap(transaction, novelId, chapterId);
            Record bible = transaction.select(
                            WRITINGBIBLE.STORYLENGTHPROFILE,
                            WRITINGBIBLE.TARGETTOTALWORDCOUNT)
                    .from(WRITINGBIBLE)
                    .where(WRITINGBIBLE.NOVELID.eq(novelId))
                    .fetchOne();
            WorkspaceBootstrapResponse response = new WorkspaceBootstrapResponse();
            response.setNovel(mapper.workspaceNovel(
                    novel,
                    bible == null ? null : bible.get(WRITINGBIBLE.STORYLENGTHPROFILE),
                    bible == null ? null : bible.get(WRITINGBIBLE.TARGETTOTALWORDCOUNT),
                    workspaceResources.appliedStyle(transaction, novel, userId)));
            response.setChapters(chapters.chapters());
            response.setCurrentChapter(chapters.currentChapter());
            response.setCurrentChapterId(chapters.currentChapterId());
            return response;
        });
    }

    @Override
    public WorkspaceLoreResponse workspaceLore(String novelId, String userId) {
        return workspaceTransactions.read(
                novelId,
                userId,
                true,
                (transaction, novel) -> workspaceLore.read(transaction, novel.getId()));
    }

    @Override
    public WorkspacePlanningResponse workspacePlanning(String novelId, String userId) {
        return workspaceTransactions.read(
                novelId,
                userId,
                true,
                (transaction, novel) -> workspacePlanning.read(transaction, novel));
    }

    @Override
    public WorkspaceResourcesResponse workspaceResources(String novelId, String userId) {
        return workspaceTransactions.read(
                novelId,
                userId,
                true,
                (transaction, novel) -> workspaceResources.read(
                        transaction, novel, userId));
    }

    private WorkspaceNovel workspaceNovel(
            NovelRecord novel,
            WorkspacePlanningResponse planning,
            AppliedStyleSummary appliedStyle) {
        var bible = planning.getWritingBible();
        return mapper.workspaceNovel(
                novel,
                bible == null
                        ? null
                        : Storylengthprofile.lookupLiteral(
                                bible.getStoryLengthProfile().getValue()),
                bible == null ? null : bible.getTargetTotalWordCount(),
                appliedStyle);
    }

    private void saveShortMediumSource(
            DSLContext transaction,
            NovelCreation creation,
            String novelId,
            LocalDateTime now) {
        if (creation.clientRequestId() == null) {
            throw new IllegalStateException("中短篇来源素材缺少创建请求标识");
        }
        Map<String, Object> sourcePayload = new LinkedHashMap<>();
        sourcePayload.put("kind", "freeform_markdown");
        sourcePayload.put("profile", "short_medium");
        sourcePayload.put("clientRequestId", creation.clientRequestId());
        sourcePayload.put("sourceKind", creation.sourceKind());
        sourcePayload.put("sourceText", creation.sourceText());
        sourcePayload.put("contentHash", sha256(creation.sourceText()));
        String payloadJson = json.writeValueAsString(sourcePayload);
        String summary = creationSummary(creation.clientRequestId());
        String artifactId = ids.next();
        // 起始素材不是待审草案，而是创建时已确认的不可变来源事实；当前行与 revision 1 必须一起保存。
        transaction.insertInto(REVIEWARTIFACT)
                .set(REVIEWARTIFACT.ID, artifactId)
                .set(REVIEWARTIFACT.NOVELID, novelId)
                .set(REVIEWARTIFACT.ARTIFACTKEY, SHORT_SOURCE_KEY_PREFIX + novelId)
                .set(REVIEWARTIFACT.KIND, Reviewartifactkind.freeform_markdown)
                .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.applied)
                .set(REVIEWARTIFACT.TITLE, "中短篇起始素材")
                .set(REVIEWARTIFACT.SUMMARY, summary)
                .set(REVIEWARTIFACT.PAYLOADJSON, payloadJson)
                .set(REVIEWARTIFACT.REVISION, 1)
                .set(REVIEWARTIFACT.APPLIEDAT, now)
                .set(REVIEWARTIFACT.CREATEDAT, now)
                .set(REVIEWARTIFACT.UPDATEDAT, now)
                .execute();
        transaction.insertInto(REVIEWARTIFACTREVISION)
                .set(REVIEWARTIFACTREVISION.ID, ids.next())
                .set(REVIEWARTIFACTREVISION.ARTIFACTID, artifactId)
                .set(REVIEWARTIFACTREVISION.REVISION, 1)
                .set(REVIEWARTIFACTREVISION.SUMMARY, summary)
                .set(REVIEWARTIFACTREVISION.PAYLOADJSON, payloadJson)
                .set(REVIEWARTIFACTREVISION.CREATEDAT, now)
                .execute();
    }

    private static CreateNovelResponse findShortMediumCreation(
            DSLContext transaction, String userId, String clientRequestId) {
        Record artifact = transaction.select(
                        REVIEWARTIFACT.NOVELID)
                .from(REVIEWARTIFACT)
                .join(NOVEL)
                .on(NOVEL.ID.eq(REVIEWARTIFACT.NOVELID))
                .where(NOVEL.USERID.eq(userId)
                        .and(REVIEWARTIFACT.ARTIFACTKEY.like(SHORT_SOURCE_KEY_PREFIX + "%"))
                        .and(REVIEWARTIFACT.SUMMARY.eq(creationSummary(clientRequestId))))
                .limit(1)
                .fetchOne();
        if (artifact == null) return null;
        String novelId = artifact.get(REVIEWARTIFACT.NOVELID);
        String chapterId = transaction.select(CHAPTER.ID)
                .from(CHAPTER)
                .where(CHAPTER.NOVELID.eq(novelId))
                .orderBy(CHAPTER.ORDER.asc(), CHAPTER.ID.asc())
                .limit(1)
                .fetchOne(CHAPTER.ID);
        if (chapterId == null) {
            throw new IllegalStateException("中短篇作品缺少全文章节");
        }
        return new CreateNovelResponse(chapterId, novelId);
    }

    private NovelResponse mapNovel(Record record) {
        return mapper.novel(
                record.into(NOVEL),
                record.get(WRITINGBIBLE.STORYLENGTHPROFILE),
                record.get(WRITINGBIBLE.TARGETTOTALWORDCOUNT));
    }

    private static DashboardNovel dashboardNovel(
            NovelRecord novel,
            List<ChapterIdSummary> chapters,
            WritingstyleRecord style) {
        AppliedStyleSummary appliedStyle = style == null
                ? null
                : new AppliedStyleSummary(style.getId(), style.getName());
        return new DashboardNovel(
                appliedStyle,
                chapters,
                novel.getId(),
                novel.getName(),
                novel.getSummary(),
                DatabaseTimestamp.api(novel.getUpdatedat()));
    }

    private static NovelRecord requireOwner(
            DSLContext context, String novelId, String userId, boolean lock) {
        var query = context.selectFrom(NOVEL).where(NOVEL.ID.eq(novelId));
        NovelRecord novel = lock ? query.forUpdate().fetchOne() : query.fetchOne();
        if (novel == null) {
            throw new ApiException(404, "NOVEL_NOT_FOUND", "小说不存在");
        }
        if (novel.getUserid() == null || !novel.getUserid().equals(userId)) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
        return novel;
    }

    private static void requireVersion(
            LocalDateTime current, OffsetDateTime expected) {
        if (!DatabaseTimestamp.sameInstant(current, expected)) {
            throw new ApiException(
                    409,
                    "NOVEL_VERSION_CONFLICT",
                    "资源版本已变化，请重新读取",
                    Collections.singletonMap(
                            "currentUpdatedAt", DatabaseTimestamp.api(current)));
        }
    }

    private static String creationSummary(String clientRequestId) {
        return CREATION_SUMMARY_PREFIX + sha256(clientRequestId);
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("JDK 缺少 SHA-256", error);
        }
    }
}
