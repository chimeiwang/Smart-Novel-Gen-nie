package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATION;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATIONHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;

import cn.inkforge.contracts.api.CreateChapterAdaptationRequest;
import cn.inkforge.contracts.api.ChapterAdaptationListResponse;
import cn.inkforge.contracts.api.ChapterAdaptationResponse;
import cn.inkforge.core.db.generated.tables.records.ChapterRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.VideoAdaptationRepository;
import cn.inkforge.core.video.application.VideoAdaptationSnapshot;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/** 冻结章节全文的改编根仓储；不把章节选区或旧 VideoScene 当作新改编来源。 */
public final class JooqVideoAdaptationRepository implements VideoAdaptationRepository {

    private static final int MAX_SOURCE_CODE_POINTS = 120_000;

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final JooqVideoAdaptationReadModel readModel;

    public JooqVideoAdaptationRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            JooqVideoVisualCanonRepository visualCanons) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.readModel = new JooqVideoAdaptationReadModel(json, visualCanons);
    }

    @Override
    public VideoAdaptationSnapshot create(
            String userId, String projectId, CreateChapterAdaptationRequest request) {
        String adaptationId = database.transactionResult(transaction -> {
            VideoprojectRecord project = VideoDatabaseAccess.ownedProject(
                    transaction, userId, projectId, true);
            VideoDatabaseAccess.requireLongSerial(transaction, project.getNovelid(), true);
            ChapterRecord chapter = transaction.selectFrom(CHAPTER)
                    .where(
                            CHAPTER.ID.eq(request.getChapterId()),
                            CHAPTER.NOVELID.eq(project.getNovelid()))
                    .forUpdate()
                    .fetchOne();
            if (chapter == null) {
                throw new ApiException(
                        404,
                        "VIDEO_ADAPTATION_CHAPTER_NOT_FOUND",
                        "章节不存在或不属于当前小说");
            }
            if (!DatabaseTimestamp.sameInstant(
                    chapter.getUpdatedat(), request.getExpectedChapterUpdatedAt())) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_SOURCE_CHANGED",
                        "章节已经变化，请刷新后重新创建改编");
            }
            String source = chapter.getContent();
            if (source == null || source.strip().isEmpty()) {
                throw new ApiException(
                        422,
                        "VIDEO_ADAPTATION_SOURCE_EMPTY",
                        "章节正文为空，不能创建影视化改编");
            }
            if (source.codePointCount(0, source.length()) > MAX_SOURCE_CODE_POINTS) {
                throw new ApiException(
                        422,
                        "VIDEO_ADAPTATION_SOURCE_TOO_LONG",
                        "单章正文超过 120000 字，当前工作台不能安全处理");
            }
            String sourceHash = sha256(source);
            String existing = transaction.select(VIDEOCHAPTERADAPTATION.ID)
                    .from(VIDEOCHAPTERADAPTATION)
                    .where(
                            VIDEOCHAPTERADAPTATION.PROJECTID.eq(projectId),
                            VIDEOCHAPTERADAPTATION.CHAPTERID.eq(chapter.getId()),
                            VIDEOCHAPTERADAPTATION.SOURCEHASH.eq(sourceHash),
                            VIDEOCHAPTERADAPTATION.LIFECYCLESTATUS.eq("active"))
                    .fetchOne(VIDEOCHAPTERADAPTATION.ID);
            if (existing != null) return existing;

            String createdId = ids.next();
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.insertInto(VIDEOCHAPTERADAPTATION)
                    .set(VIDEOCHAPTERADAPTATION.ID, createdId)
                    .set(VIDEOCHAPTERADAPTATION.PROJECTID, projectId)
                    .set(VIDEOCHAPTERADAPTATION.NOVELID, project.getNovelid())
                    .set(VIDEOCHAPTERADAPTATION.CHAPTERID, chapter.getId())
                    .set(
                            VIDEOCHAPTERADAPTATION.CHAPTERTITLE,
                            chapter.getTitle() == null || chapter.getTitle().isEmpty()
                                    ? "未命名章节"
                                    : chapter.getTitle())
                    .set(VIDEOCHAPTERADAPTATION.CHAPTERUPDATEDAT, chapter.getUpdatedat())
                    .set(VIDEOCHAPTERADAPTATION.SOURCETEXT, source)
                    .set(VIDEOCHAPTERADAPTATION.SOURCEHASH, sourceHash)
                    .set(VIDEOCHAPTERADAPTATION.LIFECYCLESTATUS, "active")
                    .set(VIDEOCHAPTERADAPTATION.CREATEDAT, now)
                    .execute();
            transaction.insertInto(VIDEOCHAPTERADAPTATIONHEAD)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID, createdId)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.REVISION, 1)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.UPDATEDAT, now)
                    .execute();
            return createdId;
        });
        return get(userId, adaptationId);
    }

    @Override
    public VideoAdaptationSnapshot get(String userId, String adaptationId) {
        return read(database.dsl(), userId, adaptationId);
    }

    @Override
    public List<VideoAdaptationSnapshot> list(String userId, String projectId) {
        VideoDatabaseAccess.ownedProject(database.dsl(), userId, projectId, false);
        List<String> ids = database.dsl()
                .select(VIDEOCHAPTERADAPTATION.ID)
                .from(VIDEOCHAPTERADAPTATION)
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOCHAPTERADAPTATION.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(
                        VIDEOCHAPTERADAPTATION.PROJECTID.eq(projectId),
                        VIDEOCHAPTERADAPTATION.LIFECYCLESTATUS.eq("active"),
                        NOVEL.USERID.eq(userId))
                .orderBy(
                        VIDEOCHAPTERADAPTATION.CREATEDAT.desc(),
                        VIDEOCHAPTERADAPTATION.ID)
                .fetch(VIDEOCHAPTERADAPTATION.ID);
        return ids.stream().map(id -> read(database.dsl(), userId, id)).toList();
    }

    @Override
    public ChapterAdaptationResponse getDetail(String userId, String adaptationId) {
        return readModel.load(database.dsl(), userId, adaptationId);
    }

    @Override
    public ChapterAdaptationListResponse listDetails(String userId, String projectId) {
        VideoDatabaseAccess.ownedProject(database.dsl(), userId, projectId, false);
        List<String> adaptationIds = database.dsl()
                .select(VIDEOCHAPTERADAPTATION.ID)
                .from(VIDEOCHAPTERADAPTATION)
                .where(
                        VIDEOCHAPTERADAPTATION.PROJECTID.eq(projectId),
                        VIDEOCHAPTERADAPTATION.LIFECYCLESTATUS.eq("active"))
                .orderBy(
                        VIDEOCHAPTERADAPTATION.CREATEDAT.desc(),
                        VIDEOCHAPTERADAPTATION.ID)
                .fetch(VIDEOCHAPTERADAPTATION.ID);
        return new ChapterAdaptationListResponse(adaptationIds.stream()
                .map(id -> readModel.load(database.dsl(), userId, id))
                .toList());
    }

    private static VideoAdaptationSnapshot read(
            DSLContext context, String userId, String adaptationId) {
        VideochapteradaptationRecord adaptation = context.select(VIDEOCHAPTERADAPTATION.fields())
                .from(VIDEOCHAPTERADAPTATION)
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOCHAPTERADAPTATION.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(
                        VIDEOCHAPTERADAPTATION.ID.eq(adaptationId),
                        NOVEL.USERID.eq(userId))
                .fetchOneInto(VideochapteradaptationRecord.class);
        if (adaptation == null) {
            throw new ApiException(
                    404,
                    "VIDEO_ADAPTATION_NOT_FOUND",
                    "章节影视化改编不存在");
        }
        VideochapteradaptationheadRecord head = context.selectFrom(VIDEOCHAPTERADAPTATIONHEAD)
                .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(adaptationId))
                .fetchOne();
        if (head == null) {
            throw new ApiException(
                    409,
                    "VIDEO_ADAPTATION_HEAD_MISSING",
                    "章节影视化改编缺少正式版本指针");
        }
        return new VideoAdaptationSnapshot(
                adaptation.getId(),
                adaptation.getProjectid(),
                adaptation.getNovelid(),
                adaptation.getChapterid(),
                adaptation.getChaptertitle(),
                DatabaseTimestamp.api(adaptation.getChapterupdatedat()),
                adaptation.getSourcetext(),
                adaptation.getSourcehash(),
                adaptation.getLifecyclestatus(),
                head.getRevision(),
                DatabaseTimestamp.api(adaptation.getCreatedat()));
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }
}
