package cn.inkforge.core.outlines.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.FORESHADOWING;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.OUTLINENODE;
import static cn.inkforge.core.db.generated.Tables.PLOTPROGRESS;

import cn.inkforge.contracts.api.DeleteOutlineNodeResponse;
import cn.inkforge.contracts.api.ForeshadowingResponse;
import cn.inkforge.contracts.api.OutlineContentResponse;
import cn.inkforge.contracts.api.OutlineNodeMutationResponse;
import cn.inkforge.contracts.api.OutlineNodeResponse;
import cn.inkforge.contracts.api.PlotProgressResponse;
import cn.inkforge.core.db.generated.enums.Foreshadowingstatus;
import cn.inkforge.core.db.generated.enums.Outlinenodekind;
import cn.inkforge.core.db.generated.enums.Outlinenodestatus;
import cn.inkforge.core.db.generated.tables.records.ForeshadowingRecord;
import cn.inkforge.core.db.generated.tables.records.NovelRecord;
import cn.inkforge.core.db.generated.tables.records.OutlineRecord;
import cn.inkforge.core.db.generated.tables.records.OutlinenodeRecord;
import cn.inkforge.core.db.generated.tables.records.PlotprogressRecord;
import cn.inkforge.core.outlines.application.OutlineRepository;
import cn.inkforge.core.outlines.domain.ForeshadowingData;
import cn.inkforge.core.outlines.domain.ForeshadowingPatch;
import cn.inkforge.core.outlines.domain.OutlineNodeData;
import cn.inkforge.core.outlines.domain.OutlineNodePatch;
import cn.inkforge.core.outlines.domain.OutlineNodeSnapshot;
import cn.inkforge.core.outlines.domain.OutlineNodeValidator;
import cn.inkforge.core.outlines.domain.PlotProgressData;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CommandResourceId;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.patch.PatchField;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.impl.DSL;

/**
 * 大纲 PostgreSQL 仓储。
 *
 * <p>结构写入先锁小说行和事务级 advisory lock，再校验父子层级、章节归属与时间戳 CAS。
 * 节点创建使用请求标识派生确定性资源 ID；伏笔仍保留现有独立 CRUD 兼容语义，二者不可互相覆盖。
 */
public final class JooqOutlineRepository implements OutlineRepository {

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;

    public JooqOutlineRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public OutlineContentResponse saveOutline(
            String novelId,
            String userId,
            String content,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireOwner(transaction, novelId, userId);
            lockNovel(transaction, novelId, userId);
            OutlineRecord outline = transaction.selectFrom(OUTLINE)
                    .where(OUTLINE.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne();
            if (outline == null) {
                throw new ApiException(404, "OUTLINE_NOT_FOUND", "小说大纲不存在");
            }
            LocalDateTime current = outline.getUpdatedat();
            requireOutlineVersion(
                    current, expectedUpdatedAt, outline.getContent(), content);
            if (!outline.getContent().equals(content)) {
                outline.setContent(content);
                outline.setUpdatedat(DatabaseTimestamp.next(clock, current));
                outline.store();
            }
            return outline(outline);
        });
    }

    @Override
    public PlotProgressResponse savePlot(
            String novelId,
            String userId,
            PlotProgressData data,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireOwner(transaction, novelId, userId);
            lockNovel(transaction, novelId, userId);
            PlotprogressRecord current = transaction.selectFrom(PLOTPROGRESS)
                    .where(PLOTPROGRESS.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne();
            requireVersion(
                    current == null ? null : current.getUpdatedat(),
                    expectedUpdatedAt,
                    "PLOT_PROGRESS_VERSION_CONFLICT");
            if (current == null) {
                LocalDateTime now = DatabaseTimestamp.now(clock);
                current = transaction.insertInto(PLOTPROGRESS)
                        .set(PLOTPROGRESS.ID, ids.next())
                        .set(PLOTPROGRESS.NOVELID, novelId)
                        .set(PLOTPROGRESS.CURRENTSTAGE, data.currentStage())
                        .set(PLOTPROGRESS.CURRENTGOAL, data.currentGoal())
                        .set(PLOTPROGRESS.CURRENTCONFLICT, data.currentConflict())
                        .set(PLOTPROGRESS.NEXTMILESTONE, data.nextMilestone())
                        .set(PLOTPROGRESS.UPDATEDAT, now)
                        .returning()
                        .fetchSingle();
            } else if (!samePlot(current, data)) {
                current.setCurrentstage(data.currentStage());
                current.setCurrentgoal(data.currentGoal());
                current.setCurrentconflict(data.currentConflict());
                current.setNextmilestone(data.nextMilestone());
                current.setUpdatedat(DatabaseTimestamp.next(clock, current.getUpdatedat()));
                current.store();
            }
            return plot(current);
        });
    }

    @Override
    public List<OutlineNodeResponse> listNodes(String novelId, String userId) {
        DSLContext context = database.dsl();
        requireOwner(context, novelId, userId);
        return context.selectFrom(OUTLINENODE)
                .where(OUTLINENODE.NOVELID.eq(novelId))
                .orderBy(
                        OUTLINENODE.ORDER.asc(),
                        OUTLINENODE.CREATEDAT.asc(),
                        OUTLINENODE.ID.asc())
                .fetch()
                .map(JooqOutlineRepository::node);
    }

    @Override
    public OutlineNodeMutationResponse createNode(
            String novelId,
            String userId,
            String clientRequestId,
            OutlineNodeData data) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireOwner(transaction, novelId, userId);
            lockNovel(transaction, novelId, userId);
            // 确定性 ID 让“请求已提交但响应丢失”可安全重放；内容不同则拒绝复用同一请求标识。
            String nodeId = CommandResourceId.derive(
                    "outline_nodes", userId, novelId, clientRequestId);
            OutlinenodeRecord existing = transaction.selectFrom(OUTLINENODE)
                    .where(OUTLINENODE.ID.eq(nodeId))
                    .forUpdate()
                    .fetchOne();
            if (existing != null) {
                if (existing.getNovelid().equals(novelId)
                        && existing.getCreatedat().equals(existing.getUpdatedat())
                        && sameNode(existing, data)) {
                    return mutation(existing, false);
                }
                throw new ApiException(
                        409,
                        "RESOURCE_CREATE_CONFLICT",
                        "同一创建请求标识已用于其他大纲节点内容");
            }
            validateLinkedChapter(transaction, novelId, data.linkedChapterId());
            // 在持有小说级写锁时用完整快照校验，防止并发写入环、非法层级或重叠章节范围。
            List<OutlineNodeSnapshot> snapshots = snapshots(transaction, novelId);
            OutlineNodeValidator.validate(snapshot(nodeId, data), snapshots, data.title());
            LocalDateTime now = DatabaseTimestamp.now(clock);
            OutlinenodeRecord created = transaction.insertInto(OUTLINENODE)
                    .set(OUTLINENODE.ID, nodeId)
                    .set(OUTLINENODE.NOVELID, novelId)
                    .set(OUTLINENODE.PARENTID, data.parentId())
                    .set(OUTLINENODE.TITLE, data.title())
                    .set(OUTLINENODE.CONTENT, data.content())
                    .set(OUTLINENODE.ORDER, data.order())
                    .set(OUTLINENODE.STATUS, Outlinenodestatus.lookupLiteral(data.status()))
                    .set(OUTLINENODE.ESTIMATEDWORDCOUNT, data.estimatedWordCount())
                    .set(OUTLINENODE.ACTUALWORDCOUNT, data.actualWordCount())
                    .set(OUTLINENODE.LINKEDCHAPTERID, data.linkedChapterId())
                    .set(OUTLINENODE.CREATEDAT, now)
                    .set(OUTLINENODE.UPDATEDAT, now)
                    .set(OUTLINENODE.KIND, Outlinenodekind.lookupLiteral(data.kind()))
                    .set(OUTLINENODE.CHAPTERSTARTORDER, data.chapterStartOrder())
                    .set(OUTLINENODE.CHAPTERENDORDER, data.chapterEndOrder())
                    .returning()
                    .fetchSingle();
            return mutation(created, true);
        });
    }

    @Override
    public OutlineNodeMutationResponse updateNode(
            String novelId,
            String userId,
            String nodeId,
            OutlineNodePatch patch,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireOwner(transaction, novelId, userId);
            lockNovel(transaction, novelId, userId);
            OutlinenodeRecord current = transaction.selectFrom(OUTLINENODE)
                    .where(
                            OUTLINENODE.ID.eq(nodeId),
                            OUTLINENODE.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne();
            if (current == null) {
                throw nodeNotFound();
            }
            requireVersion(
                    current.getUpdatedat(),
                    expectedUpdatedAt,
                    "OUTLINE_NODE_VERSION_CONFLICT");
            if (!nodeChanged(current, patch)) {
                return mutation(current, false);
            }
            apply(current, patch);
            validateLinkedChapter(transaction, novelId, current.getLinkedchapterid());
            OutlineNodeValidator.validate(
                    snapshot(current), snapshots(transaction, novelId), current.getTitle());
            current.setUpdatedat(DatabaseTimestamp.next(clock, current.getUpdatedat()));
            current.store();
            return mutation(current, true);
        });
    }

    @Override
    public DeleteOutlineNodeResponse deleteNode(
            String novelId,
            String userId,
            String nodeId,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireOwner(transaction, novelId, userId);
            lockNovel(transaction, novelId, userId);
            OutlinenodeRecord current = transaction.selectFrom(OUTLINENODE)
                    .where(
                            OUTLINENODE.ID.eq(nodeId),
                            OUTLINENODE.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne();
            if (current == null) {
                throw nodeNotFound();
            }
            requireVersion(
                    current.getUpdatedat(),
                    expectedUpdatedAt,
                    "OUTLINE_NODE_VERSION_CONFLICT");
            boolean hasChild = transaction.fetchExists(
                    DSL.selectOne()
                            .from(OUTLINENODE)
                            .where(OUTLINENODE.PARENTID.eq(nodeId)));
            // 不级联删除子树；节点层级是作者数据，必须由调用方明确整理后再删除。
            if (hasChild) {
                throw new ApiException(
                        409, "OUTLINE_NODE_HAS_CHILDREN", "大纲节点仍有子节点，不能删除");
            }
            int deleted = transaction.deleteFrom(OUTLINENODE)
                    .where(
                            OUTLINENODE.ID.eq(nodeId),
                            OUTLINENODE.NOVELID.eq(novelId))
                    .execute();
            if (deleted != 1) {
                throw nodeNotFound();
            }
            return new DeleteOutlineNodeResponse(nodeId, true);
        });
    }

    @Override
    public List<ForeshadowingResponse> listForeshadowings(
            String novelId, String userId) {
        DSLContext context = database.dsl();
        requireOwner(context, novelId, userId);
        return context.selectFrom(FORESHADOWING)
                .where(FORESHADOWING.NOVELID.eq(novelId))
                .orderBy(FORESHADOWING.CREATEDAT.asc(), FORESHADOWING.ID.asc())
                .fetch()
                .map(JooqOutlineRepository::foreshadowing);
    }

    @Override
    public ForeshadowingResponse createForeshadowing(
            String novelId, String userId, ForeshadowingData data) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireOwner(transaction, novelId, userId);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            ForeshadowingRecord created = transaction.insertInto(FORESHADOWING)
                    .set(FORESHADOWING.ID, ids.next())
                    .set(FORESHADOWING.NOVELID, novelId)
                    .set(FORESHADOWING.NAME, data.name())
                    .set(FORESHADOWING.PLANTEDAT, data.plantedAt())
                    .set(FORESHADOWING.PLANTEDCONTENT, data.plantedContent())
                    .set(FORESHADOWING.EXPECTEDPAYOFF, data.expectedPayoff())
                    .set(FORESHADOWING.PAYOFFAT, data.payoffAt())
                    .set(FORESHADOWING.STATUS, Foreshadowingstatus.lookupLiteral(data.status()))
                    .set(FORESHADOWING.CREATEDAT, now)
                    .set(FORESHADOWING.UPDATEDAT, now)
                    .returning()
                    .fetchSingle();
            return foreshadowing(created);
        });
    }

    @Override
    public ForeshadowingResponse updateForeshadowing(
            String novelId,
            String userId,
            String foreshadowingId,
            ForeshadowingPatch patch) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireOwner(transaction, novelId, userId);
            ForeshadowingRecord current = transaction.selectFrom(FORESHADOWING)
                    .where(
                            FORESHADOWING.ID.eq(foreshadowingId),
                            FORESHADOWING.NOVELID.eq(novelId))
                    .fetchOne();
            if (current == null) {
                throw foreshadowingNotFound();
            }
            apply(current, patch);
            current.setUpdatedat(DatabaseTimestamp.now(clock));
            if (current.store() != 1) {
                throw foreshadowingNotFound();
            }
            return foreshadowing(current);
        });
    }

    @Override
    public void deleteForeshadowing(
            String novelId, String userId, String foreshadowingId) {
        database.dsl().transaction(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireOwner(transaction, novelId, userId);
            int deleted = transaction.deleteFrom(FORESHADOWING)
                    .where(
                            FORESHADOWING.ID.eq(foreshadowingId),
                            FORESHADOWING.NOVELID.eq(novelId))
                    .execute();
            if (deleted != 1) {
                throw foreshadowingNotFound();
            }
        });
    }

    private static void requireOwner(
            DSLContext context, String novelId, String userId) {
        String owner = context.select(NOVEL.USERID)
                .from(NOVEL)
                .where(NOVEL.ID.eq(novelId))
                .fetchOne(NOVEL.USERID);
        if (owner == null || !owner.equals(userId)) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
    }

    private static void lockNovel(
            DSLContext transaction, String novelId, String userId) {
        NovelRecord novel = transaction.selectFrom(NOVEL)
                .where(NOVEL.ID.eq(novelId))
                .forUpdate()
                .fetchOne();
        if (novel == null
                || novel.getUserid() == null
                || !novel.getUserid().equals(userId)) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
        transaction.fetch("select pg_advisory_xact_lock(?)", advisoryKey(novelId));
    }

    private static long advisoryKey(String novelId) {
        return ByteBuffer.wrap(sha256(novelId.getBytes(StandardCharsets.UTF_8))).getLong();
    }

    private static void validateLinkedChapter(
            DSLContext transaction, String novelId, String chapterId) {
        if (chapterId == null) {
            return;
        }
        String linkedNovel = transaction.select(CHAPTER.NOVELID)
                .from(CHAPTER)
                .where(CHAPTER.ID.eq(chapterId))
                .fetchOne(CHAPTER.NOVELID);
        if (!novelId.equals(linkedNovel)) {
            throw new ApiException(
                    422,
                    "OUTLINE_CHAPTER_CROSS_NOVEL",
                    "关联章节不属于当前小说");
        }
    }

    private static List<OutlineNodeSnapshot> snapshots(
            DSLContext transaction, String novelId) {
        return transaction.selectFrom(OUTLINENODE)
                .where(OUTLINENODE.NOVELID.eq(novelId))
                .fetch()
                .map(JooqOutlineRepository::snapshot);
    }

    private static OutlineNodeSnapshot snapshot(
            String id, OutlineNodeData value) {
        return new OutlineNodeSnapshot(
                id,
                value.kind(),
                value.parentId(),
                value.chapterStartOrder(),
                value.chapterEndOrder());
    }

    private static OutlineNodeSnapshot snapshot(OutlinenodeRecord value) {
        return new OutlineNodeSnapshot(
                value.getId(),
                value.getKind().getLiteral(),
                value.getParentid(),
                value.getChapterstartorder(),
                value.getChapterendorder());
    }

    private static boolean sameNode(OutlinenodeRecord current, OutlineNodeData data) {
        return Objects.equals(current.getTitle(), data.title())
                && Objects.equals(current.getContent(), data.content())
                && Objects.equals(current.getKind().getLiteral(), data.kind())
                && Objects.equals(current.getStatus().getLiteral(), data.status())
                && Objects.equals(current.getOrder(), data.order())
                && Objects.equals(current.getParentid(), data.parentId())
                && Objects.equals(current.getLinkedchapterid(), data.linkedChapterId())
                && Objects.equals(current.getEstimatedwordcount(), data.estimatedWordCount())
                && Objects.equals(current.getActualwordcount(), data.actualWordCount())
                && Objects.equals(current.getChapterstartorder(), data.chapterStartOrder())
                && Objects.equals(current.getChapterendorder(), data.chapterEndOrder());
    }

    private static boolean samePlot(PlotprogressRecord current, PlotProgressData data) {
        return Objects.equals(current.getCurrentstage(), data.currentStage())
                && Objects.equals(current.getCurrentgoal(), data.currentGoal())
                && Objects.equals(current.getCurrentconflict(), data.currentConflict())
                && Objects.equals(current.getNextmilestone(), data.nextMilestone());
    }

    private static boolean nodeChanged(
            OutlinenodeRecord current, OutlineNodePatch patch) {
        return differs(patch.title(), current.getTitle())
                || differs(patch.content(), current.getContent())
                || differs(patch.kind(), current.getKind().getLiteral())
                || differs(patch.status(), current.getStatus().getLiteral())
                || differs(patch.order(), current.getOrder())
                || differs(patch.parentId(), current.getParentid())
                || differs(patch.linkedChapterId(), current.getLinkedchapterid())
                || differs(patch.estimatedWordCount(), current.getEstimatedwordcount())
                || differs(patch.actualWordCount(), current.getActualwordcount())
                || differs(patch.chapterStartOrder(), current.getChapterstartorder())
                || differs(patch.chapterEndOrder(), current.getChapterendorder());
    }

    private static <T> boolean differs(PatchField<T> patch, T current) {
        return patch.present() && !Objects.equals(patch.value(), current);
    }

    private static void apply(OutlinenodeRecord current, OutlineNodePatch patch) {
        if (patch.title().present()) current.setTitle(patch.title().value());
        if (patch.content().present()) current.setContent(patch.content().value());
        if (patch.kind().present()) {
            current.setKind(Outlinenodekind.lookupLiteral(patch.kind().value()));
        }
        if (patch.status().present()) {
            current.setStatus(Outlinenodestatus.lookupLiteral(patch.status().value()));
        }
        if (patch.order().present()) current.setOrder(patch.order().value());
        if (patch.parentId().present()) current.setParentid(patch.parentId().value());
        if (patch.linkedChapterId().present()) {
            current.setLinkedchapterid(patch.linkedChapterId().value());
        }
        if (patch.estimatedWordCount().present()) {
            current.setEstimatedwordcount(patch.estimatedWordCount().value());
        }
        if (patch.actualWordCount().present()) {
            current.setActualwordcount(patch.actualWordCount().value());
        }
        if (patch.chapterStartOrder().present()) {
            current.setChapterstartorder(patch.chapterStartOrder().value());
        }
        if (patch.chapterEndOrder().present()) {
            current.setChapterendorder(patch.chapterEndOrder().value());
        }
    }

    private static void apply(
            ForeshadowingRecord current, ForeshadowingPatch patch) {
        if (patch.name().present()) current.setName(patch.name().value());
        if (patch.plantedAt().present()) current.setPlantedat(patch.plantedAt().value());
        if (patch.plantedContent().present()) {
            current.setPlantedcontent(patch.plantedContent().value());
        }
        if (patch.expectedPayoff().present()) {
            current.setExpectedpayoff(patch.expectedPayoff().value());
        }
        if (patch.payoffAt().present()) current.setPayoffat(patch.payoffAt().value());
        if (patch.status().present()) {
            current.setStatus(Foreshadowingstatus.lookupLiteral(patch.status().value()));
        }
    }

    private static OutlineContentResponse outline(OutlineRecord value) {
        OutlineContentResponse result = new OutlineContentResponse();
        result.setId(value.getId());
        result.setContent(value.getContent());
        result.setContentHash(hexSha256(value.getContent()));
        result.setCreatedAt(DatabaseTimestamp.api(value.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
        return result;
    }

    private static PlotProgressResponse plot(PlotprogressRecord value) {
        PlotProgressResponse result = new PlotProgressResponse();
        result.setId(value.getId());
        result.setCurrentStage(value.getCurrentstage());
        result.setCurrentGoal(value.getCurrentgoal());
        result.setCurrentConflict(value.getCurrentconflict());
        result.setNextMilestone(value.getNextmilestone());
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
        return result;
    }

    private static OutlineNodeResponse node(OutlinenodeRecord value) {
        OutlineNodeResponse result = new OutlineNodeResponse();
        copyNode(result, value);
        return result;
    }

    private static OutlineNodeMutationResponse mutation(
            OutlinenodeRecord value, boolean effective) {
        OutlineNodeMutationResponse result = new OutlineNodeMutationResponse();
        copyNode(result, value);
        result.setEffective(effective);
        return result;
    }

    private static void copyNode(
            OutlineNodeResponse result, OutlinenodeRecord value) {
        result.setId(value.getId());
        result.setTitle(value.getTitle());
        result.setContent(value.getContent());
        result.setKind(OutlineNodeResponse.KindEnum.fromValue(value.getKind().getLiteral()));
        result.setStatus(
                OutlineNodeResponse.StatusEnum.fromValue(value.getStatus().getLiteral()));
        result.setOrder(value.getOrder());
        result.setParentId(value.getParentid());
        result.setLinkedChapterId(value.getLinkedchapterid());
        result.setEstimatedWordCount(value.getEstimatedwordcount());
        result.setActualWordCount(value.getActualwordcount());
        result.setChapterStartOrder(value.getChapterstartorder());
        result.setChapterEndOrder(value.getChapterendorder());
        result.setCreatedAt(DatabaseTimestamp.api(value.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static void copyNode(
            OutlineNodeMutationResponse result, OutlinenodeRecord value) {
        result.setId(value.getId());
        result.setTitle(value.getTitle());
        result.setContent(value.getContent());
        result.setKind(
                OutlineNodeMutationResponse.KindEnum.fromValue(value.getKind().getLiteral()));
        result.setStatus(OutlineNodeMutationResponse.StatusEnum.fromValue(
                value.getStatus().getLiteral()));
        result.setOrder(value.getOrder());
        result.setParentId(value.getParentid());
        result.setLinkedChapterId(value.getLinkedchapterid());
        result.setEstimatedWordCount(value.getEstimatedwordcount());
        result.setActualWordCount(value.getActualwordcount());
        result.setChapterStartOrder(value.getChapterstartorder());
        result.setChapterEndOrder(value.getChapterendorder());
        result.setCreatedAt(DatabaseTimestamp.api(value.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static ForeshadowingResponse foreshadowing(ForeshadowingRecord value) {
        ForeshadowingResponse result = new ForeshadowingResponse();
        result.setId(value.getId());
        result.setName(value.getName());
        result.setPlantedAt(value.getPlantedat());
        result.setPlantedContent(value.getPlantedcontent());
        result.setExpectedPayoff(value.getExpectedpayoff());
        result.setPayoffAt(value.getPayoffat());
        result.setStatus(ForeshadowingResponse.StatusEnum.fromValue(
                value.getStatus().getLiteral()));
        result.setCreatedAt(DatabaseTimestamp.api(value.getCreatedat()));
        result.setUpdatedAt(DatabaseTimestamp.api(value.getUpdatedat()));
        return result;
    }

    private static void requireOutlineVersion(
            LocalDateTime current,
            OffsetDateTime expected,
            String currentContent,
            String requestedContent) {
        if (expected == null) {
            if (!currentContent.equals(requestedContent)) {
                throw new ApiException(
                        409,
                        "OUTLINE_PRECONDITION_REQUIRED",
                        "旧版大纲草案缺少并发前置条件，不能覆盖当前大纲",
                        Map.of("currentUpdatedAt", DatabaseTimestamp.api(current)));
            }
            return;
        }
        if (!DatabaseTimestamp.sameInstant(current, expected)) {
            throw new ApiException(
                    409,
                    "OUTLINE_VERSION_CONFLICT",
                    "大纲已在其他位置更新，请保留当前草稿并重新加载",
                    Map.of("currentUpdatedAt", DatabaseTimestamp.api(current)));
        }
    }

    private static void requireVersion(
            LocalDateTime current, OffsetDateTime expected, String code) {
        if (!DatabaseTimestamp.sameInstant(current, expected)) {
            throw new ApiException(
                    409,
                    code,
                    "资源版本已变化，请重新读取",
                    java.util.Collections.singletonMap(
                            "currentUpdatedAt", DatabaseTimestamp.api(current)));
        }
    }

    private static ApiException nodeNotFound() {
        return new ApiException(404, "OUTLINE_NODE_NOT_FOUND", "大纲节点不存在");
    }

    private static ApiException foreshadowingNotFound() {
        return new ApiException(404, "FORESHADOWING_NOT_FOUND", "伏笔不存在");
    }

    private static String hexSha256(String value) {
        return HexFormat.of().formatHex(
                sha256(value.getBytes(StandardCharsets.UTF_8)));
    }

    private static byte[] sha256(byte[] value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JDK 缺少 SHA-256", exception);
        }
    }
}
