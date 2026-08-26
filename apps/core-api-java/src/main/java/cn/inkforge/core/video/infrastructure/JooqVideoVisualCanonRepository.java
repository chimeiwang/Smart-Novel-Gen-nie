package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHARACTER;
import static cn.inkforge.core.db.generated.Tables.ITEM;
import static cn.inkforge.core.db.generated.Tables.LOCATION;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATIONHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTVISUALREFERENCE;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTVISUALREFERENCEBINDING;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTVISUALREFERENCESET;
import static cn.inkforge.core.db.generated.Tables.VIDEOVISUALCANON;
import static cn.inkforge.core.db.generated.Tables.VIDEOVISUALCANONVERSION;

import cn.inkforge.contracts.api.ShotVisualReferenceSetResponse;
import cn.inkforge.contracts.api.ShotVisualReferenceSnapshot;
import cn.inkforge.contracts.api.VideoAssetResponse;
import cn.inkforge.contracts.api.VisualCanonLibraryResponse;
import cn.inkforge.contracts.api.VisualCanonResponse;
import cn.inkforge.contracts.api.VisualCanonVersionResponse;
import cn.inkforge.core.db.generated.tables.records.VideoassetRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotpromptvisualreferenceRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotvisualreferencebindingRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotvisualreferencesetRecord;
import cn.inkforge.core.db.generated.tables.records.VideovisualcanonRecord;
import cn.inkforge.core.db.generated.tables.records.VideovisualcanonversionRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.VideoVisualCanonRepository;
import cn.inkforge.core.video.application.ShotVisualReferenceSelection;
import cn.inkforge.core.video.application.ShotVisualReferencesCommand;
import cn.inkforge.core.video.application.VisualCanonApproval;
import cn.inkforge.core.video.application.VisualCanonCandidateCommand;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import org.jooq.DSLContext;
import org.jooq.impl.DSL;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 视觉设定候选与不可变版本链的 jOOQ 实现。
 *
 * <p>上传或选择图片只更新候选；只有作者确认素材权利并批准后才创建不可变 CanonVersion。逐镜参考集合
 * 使用独立 revision CAS，提示词保存时复制精确版本与素材哈希，后续切换当前 Canon 不会改写历史提示词依据。
 */
public final class JooqVideoVisualCanonRepository implements VideoVisualCanonRepository {

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    public JooqVideoVisualCanonRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public VisualCanonLibraryResponse list(String userId, String projectId) {
        VideoDatabaseAccess.ownedProject(database.dsl(), userId, projectId, false);
        return library(database.dsl(), projectId);
    }

    @Override
    public VisualCanonResponse setCandidate(
            String userId,
            String projectId,
            VisualCanonCandidateCommand command) {
        String canonId = database.transactionResult(transaction -> {
            VideoprojectRecord project = VideoDatabaseAccess.ownedProject(
                    transaction, userId, projectId, true);
            VideoDatabaseAccess.requireLongSerial(transaction, project.getNovelid(), true);
            String settingName = requireSetting(
                    transaction,
                    project.getNovelid(),
                    command.settingKind(),
                    command.settingId());
            VideoassetRecord asset = requireCandidateAsset(
                    transaction,
                    projectId,
                    command.candidateAssetId(),
                    command.duty());
            VideovisualcanonRecord canon = transaction.selectFrom(VIDEOVISUALCANON)
                    .where(
                            VIDEOVISUALCANON.PROJECTID.eq(projectId),
                            VIDEOVISUALCANON.SETTINGKIND.eq(command.settingKind()),
                            VIDEOVISUALCANON.SETTINGID.eq(command.settingId()),
                            VIDEOVISUALCANON.DUTY.eq(command.duty()),
                            VIDEOVISUALCANON.VARIANTKEY.eq(command.variantKey()))
                    .forUpdate()
                    .fetchOne();
            String includeJson = json.writeValueAsString(command.includeFeatures());
            String excludeJson = json.writeValueAsString(command.excludeFeatures());
            LocalDateTime now = DatabaseTimestamp.now(clock);
            // 候选区允许反复调整，但不会产生正式版本，也不会被既有 Prompt/Render 任务引用。
            if (canon == null) {
                String createdId = ids.next();
                transaction.insertInto(VIDEOVISUALCANON)
                        .set(VIDEOVISUALCANON.ID, createdId)
                        .set(VIDEOVISUALCANON.PROJECTID, projectId)
                        .set(VIDEOVISUALCANON.NOVELID, project.getNovelid())
                        .set(VIDEOVISUALCANON.SETTINGKIND, command.settingKind())
                        .set(VIDEOVISUALCANON.SETTINGID, command.settingId())
                        .set(VIDEOVISUALCANON.SETTINGNAME, settingName)
                        .set(VIDEOVISUALCANON.DUTY, command.duty())
                        .set(VIDEOVISUALCANON.VARIANTKEY, command.variantKey())
                        .set(VIDEOVISUALCANON.LABEL, command.label())
                        .set(VIDEOVISUALCANON.CANDIDATEASSETID, asset.getId())
                        .set(VIDEOVISUALCANON.CANDIDATEINCLUDEFEATURESJSON, includeJson)
                        .set(VIDEOVISUALCANON.CANDIDATEEXCLUDEFEATURESJSON, excludeJson)
                        .set(
                                VIDEOVISUALCANON.CANDIDATEDEFAULTSTRENGTH,
                                command.defaultStrength())
                        .set(VIDEOVISUALCANON.REVISION, 1)
                        .set(VIDEOVISUALCANON.CREATEDAT, now)
                        .set(VIDEOVISUALCANON.UPDATEDAT, now)
                        .execute();
                return createdId;
            }
            boolean unchanged = Objects.equals(canon.getSettingname(), settingName)
                    && Objects.equals(canon.getLabel(), command.label())
                    && Objects.equals(canon.getCandidateassetid(), asset.getId())
                    && Objects.equals(canon.getCandidateincludefeaturesjson(), includeJson)
                    && Objects.equals(canon.getCandidateexcludefeaturesjson(), excludeJson)
                    && Objects.equals(
                            canon.getCandidatedefaultstrength(), command.defaultStrength());
            if (!unchanged) {
                LocalDateTime updated = DatabaseTimestamp.next(clock, canon.getUpdatedat());
                transaction.update(VIDEOVISUALCANON)
                        .set(VIDEOVISUALCANON.SETTINGNAME, settingName)
                        .set(VIDEOVISUALCANON.LABEL, command.label())
                        .set(VIDEOVISUALCANON.CANDIDATEASSETID, asset.getId())
                        .set(VIDEOVISUALCANON.CANDIDATEINCLUDEFEATURESJSON, includeJson)
                        .set(VIDEOVISUALCANON.CANDIDATEEXCLUDEFEATURESJSON, excludeJson)
                        .set(
                                VIDEOVISUALCANON.CANDIDATEDEFAULTSTRENGTH,
                                command.defaultStrength())
                        .set(VIDEOVISUALCANON.REVISION, canon.getRevision() + 1)
                        .set(VIDEOVISUALCANON.UPDATEDAT, updated)
                        .where(VIDEOVISUALCANON.ID.eq(canon.getId()))
                        .execute();
            }
            return canon.getId();
        });
        return canonById(library(database.dsl(), projectId), canonId);
    }

    @Override
    public VisualCanonResponse approve(
            String userId, String canonId, VisualCanonApproval approval) {
        String projectId = database.transactionResult(transaction -> {
            VideovisualcanonRecord canon = ownedCanon(transaction, userId, canonId, true);
            VideovisualcanonversionRecord current = canon.getCurrentversionid() == null
                    ? null
                    : transaction.selectFrom(VIDEOVISUALCANONVERSION)
                            .where(VIDEOVISUALCANONVERSION.ID.eq(canon.getCurrentversionid()))
                            .fetchOne();
            if (canon.getCandidateassetid() == null
                    && current != null
                    && current.getAssetid().equals(approval.candidateAssetId())) {
                return canon.getProjectid();
            }
            if (canon.getRevision() != approval.expectedRevision()) {
                throw revisionConflict(canon.getRevision());
            }
            if (!Objects.equals(canon.getCandidateassetid(), approval.candidateAssetId())) {
                throw new ApiException(
                        409,
                        "VIDEO_VISUAL_CANON_CANDIDATE_CHANGED",
                        "视觉设定候选已经变化，请刷新后重试");
            }
            if (canon.getCandidateincludefeaturesjson() == null
                    || canon.getCandidateexcludefeaturesjson() == null
                    || canon.getCandidatedefaultstrength() == null) {
                throw new ApiException(
                        409,
                        "VIDEO_VISUAL_CANON_CANDIDATE_INVALID",
                        "视觉设定候选元数据不完整");
            }
            VideoassetRecord asset = requireCandidateAsset(
                    transaction,
                    canon.getProjectid(),
                    approval.candidateAssetId(),
                    canon.getDuty());
            Integer maximum = transaction.select(
                            DSL.coalesce(DSL.max(VIDEOVISUALCANONVERSION.VERSIONNO), 0))
                    .from(VIDEOVISUALCANONVERSION)
                    .where(VIDEOVISUALCANONVERSION.CANONID.eq(canonId))
                    .fetchOne(0, Integer.class);
            int versionNo = (maximum == null ? 0 : maximum) + 1;
            String versionId = ids.next();
            LocalDateTime now = DatabaseTimestamp.now(clock);
            String hash = versionHash(canon, asset, versionNo);
            // 批准才把已确认权利的素材和描述冻结成不可变 CanonVersion，并清空可变候选区。
            transaction.insertInto(VIDEOVISUALCANONVERSION)
                    .set(VIDEOVISUALCANONVERSION.ID, versionId)
                    .set(VIDEOVISUALCANONVERSION.CANONID, canonId)
                    .set(VIDEOVISUALCANONVERSION.PROJECTID, canon.getProjectid())
                    .set(VIDEOVISUALCANONVERSION.NOVELID, canon.getNovelid())
                    .set(VIDEOVISUALCANONVERSION.VERSIONNO, versionNo)
                    .set(VIDEOVISUALCANONVERSION.ASSETID, asset.getId())
                    .set(VIDEOVISUALCANONVERSION.SETTINGNAME, canon.getSettingname())
                    .set(VIDEOVISUALCANONVERSION.LABEL, canon.getLabel())
                    .set(
                            VIDEOVISUALCANONVERSION.INCLUDEFEATURESJSON,
                            canon.getCandidateincludefeaturesjson())
                    .set(
                            VIDEOVISUALCANONVERSION.EXCLUDEFEATURESJSON,
                            canon.getCandidateexcludefeaturesjson())
                    .set(
                            VIDEOVISUALCANONVERSION.DEFAULTSTRENGTH,
                            canon.getCandidatedefaultstrength())
                    .set(VIDEOVISUALCANONVERSION.APPROVEDBYUSERID, userId)
                    .set(VIDEOVISUALCANONVERSION.CONTENTHASH, hash)
                    .set(VIDEOVISUALCANONVERSION.CREATEDAT, now)
                    .execute();
            LocalDateTime updated = DatabaseTimestamp.next(clock, canon.getUpdatedat());
            transaction.update(VIDEOVISUALCANON)
                    .set(VIDEOVISUALCANON.CURRENTVERSIONID, versionId)
                    .set(VIDEOVISUALCANON.CANDIDATEASSETID, (String) null)
                    .set(VIDEOVISUALCANON.CANDIDATEINCLUDEFEATURESJSON, (String) null)
                    .set(VIDEOVISUALCANON.CANDIDATEEXCLUDEFEATURESJSON, (String) null)
                    .set(VIDEOVISUALCANON.CANDIDATEDEFAULTSTRENGTH, (Integer) null)
                    .set(VIDEOVISUALCANON.REVISION, canon.getRevision() + 1)
                    .set(VIDEOVISUALCANON.UPDATEDAT, updated)
                    .where(VIDEOVISUALCANON.ID.eq(canonId))
                    .execute();
            return canon.getProjectid();
        });
        return canonById(library(database.dsl(), projectId), canonId);
    }

    @Override
    public ShotVisualReferenceSetResponse saveShotReferences(
            String userId,
            String adaptationId,
            String shotId,
            ShotVisualReferencesCommand command) {
        return database.transactionResult(transaction -> {
            VideochapteradaptationRecord adaptation = VideoDatabaseAccess
                    .ownedAdaptation(transaction, userId, adaptationId, true)
                    .adaptation();
            VideochapteradaptationheadRecord head = transaction
                    .selectFrom(VIDEOCHAPTERADAPTATIONHEAD)
                    .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(adaptationId))
                    .forUpdate()
                    .fetchOne();
            if (head == null) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_HEAD_MISSING",
                        "章节影视化改编缺少正式版本指针");
            }
            if (head.getCurrentshotplanversionid() == null) {
                throw new ApiException(
                        409, "VIDEO_SHOT_PLAN_REQUIRED", "请先确认正式镜头方案");
            }
            VideoshotRecord shot = transaction.selectFrom(VIDEOSHOT)
                    .where(
                            VIDEOSHOT.ID.eq(shotId),
                            VIDEOSHOT.PLANVERSIONID.eq(head.getCurrentshotplanversionid()))
                    .forUpdate()
                    .fetchOne();
            if (shot == null) {
                throw new ApiException(
                        404,
                        "VIDEO_SHOT_NOT_FOUND",
                        "正式镜头不存在或不属于当前方案");
            }
            requireReferenceVersions(
                    transaction,
                    adaptation.getProjectid(),
                    adaptation.getNovelid(),
                    command.references().stream()
                            .map(ShotVisualReferenceSelection::canonVersionId)
                            .toList());
            VideoshotvisualreferencesetRecord referenceSet = transaction
                    .selectFrom(VIDEOSHOTVISUALREFERENCESET)
                    .where(VIDEOSHOTVISUALREFERENCESET.SHOTID.eq(shotId))
                    .forUpdate()
                    .fetchOne();
            List<ShotVisualReferenceSelection> existing = transaction
                    .selectFrom(VIDEOSHOTVISUALREFERENCEBINDING)
                    .where(VIDEOSHOTVISUALREFERENCEBINDING.SHOTID.eq(shotId))
                    .orderBy(VIDEOSHOTVISUALREFERENCEBINDING.ORDINAL)
                    .fetch()
                    .stream()
                    .map(value -> new ShotVisualReferenceSelection(
                            value.getCanonversionid(), value.getStrength()))
                    .toList();
            int currentRevision = referenceSet == null ? 0 : referenceSet.getRevision();
            if (currentRevision != command.expectedRevision()) {
                // 迟到的完全相同请求可视为成功；内容不同才是真正的并发修改冲突。
                if (!existing.equals(command.references())) {
                    throw shotReferenceRevisionConflict(currentRevision);
                }
                return shotReference(transaction, shot);
            }
            if (existing.equals(command.references())) {
                return shotReference(transaction, shot);
            }

            LocalDateTime now = DatabaseTimestamp.now(clock);
            if (referenceSet == null) {
                transaction.insertInto(VIDEOSHOTVISUALREFERENCESET)
                        .set(VIDEOSHOTVISUALREFERENCESET.SHOTID, shotId)
                        .set(VIDEOSHOTVISUALREFERENCESET.PLANVERSIONID, shot.getPlanversionid())
                        .set(VIDEOSHOTVISUALREFERENCESET.ADAPTATIONID, adaptationId)
                        .set(
                                VIDEOSHOTVISUALREFERENCESET.PROJECTID,
                                adaptation.getProjectid())
                        .set(VIDEOSHOTVISUALREFERENCESET.NOVELID, adaptation.getNovelid())
                        .set(VIDEOSHOTVISUALREFERENCESET.REVISION, 1)
                        .set(VIDEOSHOTVISUALREFERENCESET.UPDATEDAT, now)
                        .execute();
            } else {
                LocalDateTime updated = DatabaseTimestamp.next(clock, referenceSet.getUpdatedat());
                transaction.update(VIDEOSHOTVISUALREFERENCESET)
                        .set(
                                VIDEOSHOTVISUALREFERENCESET.REVISION,
                                referenceSet.getRevision() + 1)
                        .set(VIDEOSHOTVISUALREFERENCESET.UPDATEDAT, updated)
                        .where(VIDEOSHOTVISUALREFERENCESET.SHOTID.eq(shotId))
                        .execute();
            }
            // 绑定保存的是 CanonVersion 而非 CanonHead，保证后续批准新形象不会改写该镜头的既有选择。
            transaction.deleteFrom(VIDEOSHOTVISUALREFERENCEBINDING)
                    .where(VIDEOSHOTVISUALREFERENCEBINDING.SHOTID.eq(shotId))
                    .execute();
            for (int index = 0; index < command.references().size(); index++) {
                ShotVisualReferenceSelection reference = command.references().get(index);
                transaction.insertInto(VIDEOSHOTVISUALREFERENCEBINDING)
                        .set(VIDEOSHOTVISUALREFERENCEBINDING.SHOTID, shotId)
                        .set(VIDEOSHOTVISUALREFERENCEBINDING.ORDINAL, index + 1)
                        .set(
                                VIDEOSHOTVISUALREFERENCEBINDING.PLANVERSIONID,
                                shot.getPlanversionid())
                        .set(VIDEOSHOTVISUALREFERENCEBINDING.ADAPTATIONID, adaptationId)
                        .set(
                                VIDEOSHOTVISUALREFERENCEBINDING.PROJECTID,
                                adaptation.getProjectid())
                        .set(
                                VIDEOSHOTVISUALREFERENCEBINDING.NOVELID,
                                adaptation.getNovelid())
                        .set(
                                VIDEOSHOTVISUALREFERENCEBINDING.CANONVERSIONID,
                                reference.canonVersionId())
                        .set(VIDEOSHOTVISUALREFERENCEBINDING.STRENGTH, reference.strength())
                        .execute();
            }
            return shotReference(transaction, shot);
        });
    }

    private VisualCanonLibraryResponse library(DSLContext context, String projectId) {
        List<VideovisualcanonRecord> canons = context.selectFrom(VIDEOVISUALCANON)
                .where(VIDEOVISUALCANON.PROJECTID.eq(projectId))
                .orderBy(
                        VIDEOVISUALCANON.SETTINGKIND,
                        VIDEOVISUALCANON.SETTINGNAME,
                        VIDEOVISUALCANON.DUTY,
                        VIDEOVISUALCANON.VARIANTKEY)
                .fetch();
        if (canons.isEmpty()) return new VisualCanonLibraryResponse(List.of());
        List<String> canonIds = canons.stream().map(VideovisualcanonRecord::getId).toList();
        List<VideovisualcanonversionRecord> versions = context
                .selectFrom(VIDEOVISUALCANONVERSION)
                .where(VIDEOVISUALCANONVERSION.CANONID.in(canonIds))
                .orderBy(
                        VIDEOVISUALCANONVERSION.CANONID,
                        VIDEOVISUALCANONVERSION.VERSIONNO.desc())
                .fetch();
        LinkedHashSet<String> assetIds = new LinkedHashSet<>();
        for (VideovisualcanonRecord canon : canons) {
            if (canon.getCandidateassetid() != null) assetIds.add(canon.getCandidateassetid());
        }
        versions.forEach(version -> assetIds.add(version.getAssetid()));
        Map<String, VideoassetRecord> assets = new HashMap<>();
        if (!assetIds.isEmpty()) {
            context.selectFrom(VIDEOASSET)
                    .where(VIDEOASSET.ID.in(assetIds))
                    .fetch()
                    .forEach(asset -> assets.put(asset.getId(), asset));
        }

        Map<String, List<VisualCanonVersionResponse>> versionsByCanon = new HashMap<>();
        for (VideovisualcanonversionRecord version : versions) {
            VideoassetRecord asset = assets.get(version.getAssetid());
            if (asset == null) throw corrupt("正式视觉版本引用的素材不存在");
            versionsByCanon.computeIfAbsent(version.getCanonid(), ignored -> new ArrayList<>())
                    .add(new VisualCanonVersionResponse(
                            asset(asset),
                            version.getCanonid(),
                            version.getContenthash(),
                            DatabaseTimestamp.api(version.getCreatedat()),
                            version.getDefaultstrength(),
                            stringList(version.getExcludefeaturesjson()),
                            version.getId(),
                            stringList(version.getIncludefeaturesjson()),
                            version.getLabel(),
                            version.getSettingname(),
                            version.getVersionno()));
        }
        List<VisualCanonResponse> responses = new ArrayList<>();
        for (VideovisualcanonRecord canon : canons) {
            VideoassetRecord candidate = canon.getCandidateassetid() == null
                    ? null
                    : assets.get(canon.getCandidateassetid());
            if (canon.getCandidateassetid() != null && candidate == null) {
                throw corrupt("视觉设定候选引用的素材不存在");
            }
            responses.add(new VisualCanonResponse(
                    candidate == null ? null : asset(candidate),
                    canon.getCandidatedefaultstrength(),
                    canon.getCandidateexcludefeaturesjson() == null
                            ? List.of()
                            : stringList(canon.getCandidateexcludefeaturesjson()),
                    canon.getCandidateincludefeaturesjson() == null
                            ? List.of()
                            : stringList(canon.getCandidateincludefeaturesjson()),
                    DatabaseTimestamp.api(canon.getCreatedat()),
                    canon.getCurrentversionid(),
                    VisualCanonResponse.DutyEnum.fromValue(canon.getDuty()),
                    canon.getId(),
                    canon.getLabel(),
                    canon.getNovelid(),
                    canon.getProjectid(),
                    canon.getRevision(),
                    canon.getSettingid(),
                    VisualCanonResponse.SettingKindEnum.fromValue(canon.getSettingkind()),
                    canon.getSettingname(),
                    DatabaseTimestamp.api(canon.getUpdatedat()),
                    canon.getVariantkey(),
                    versionsByCanon.getOrDefault(canon.getId(), List.of())));
        }
        return new VisualCanonLibraryResponse(responses);
    }

    private static String requireSetting(
            DSLContext context, String novelId, String kind, String settingId) {
        String name = switch (kind) {
            case "character" -> context.select(CHARACTER.NAME)
                    .from(CHARACTER)
                    .where(CHARACTER.ID.eq(settingId), CHARACTER.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne(CHARACTER.NAME);
            case "location" -> context.select(LOCATION.NAME)
                    .from(LOCATION)
                    .where(LOCATION.ID.eq(settingId), LOCATION.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne(LOCATION.NAME);
            case "item" -> context.select(ITEM.NAME)
                    .from(ITEM)
                    .where(ITEM.ID.eq(settingId), ITEM.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne(ITEM.NAME);
            default -> null;
        };
        if (name == null) {
            throw new ApiException(
                    404,
                    "VIDEO_VISUAL_SETTING_NOT_FOUND",
                    "文字设定不存在或不属于当前小说");
        }
        return name;
    }

    private static VideoassetRecord requireCandidateAsset(
            DSLContext context, String projectId, String assetId, String duty) {
        VideoassetRecord asset = context.selectFrom(VIDEOASSET)
                .where(VIDEOASSET.ID.eq(assetId), VIDEOASSET.PROJECTID.eq(projectId))
                .forUpdate()
                .fetchOne();
        if (asset == null) {
            throw new ApiException(
                    404, "VIDEO_ASSET_NOT_FOUND", "视觉设定图片不存在");
        }
        if (!"image".equals(asset.getModality()) || !duty.equals(asset.getDuty())) {
            throw new ApiException(
                    422,
                    "VIDEO_VISUAL_CANON_ASSET_INVALID",
                    "视觉设定只能使用职责匹配的图片素材");
        }
        if (!"confirmed".equals(asset.getRightsstatus()) || asset.getLockedat() == null) {
            // 未确认使用权或仍可替换的文件不能进入长期可重建的视觉设定链。
            throw new ApiException(
                    409,
                    "VIDEO_VISUAL_CANON_ASSET_UNCONFIRMED",
                    "请先确认图片使用权再设置视觉设定");
        }
        return asset;
    }

    private static VideovisualcanonRecord ownedCanon(
            DSLContext context, String userId, String canonId, boolean lock) {
        var query = context.select(VIDEOVISUALCANON.fields())
                .from(VIDEOVISUALCANON)
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOVISUALCANON.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOVISUALCANON.NOVELID))
                .where(
                        VIDEOVISUALCANON.ID.eq(canonId),
                        VIDEOPROJECT.DELETEDAT.isNull(),
                        NOVEL.USERID.eq(userId));
        VideovisualcanonRecord canon = lock
                ? query.forUpdate().fetchOneInto(VideovisualcanonRecord.class)
                : query.fetchOneInto(VideovisualcanonRecord.class);
        if (canon == null) {
            throw new ApiException(
                    404, "VIDEO_VISUAL_CANON_NOT_FOUND", "视觉设定不存在");
        }
        return canon;
    }

    private static void requireReferenceVersions(
            DSLContext context,
            String projectId,
            String novelId,
            List<String> versionIds) {
        if (versionIds.isEmpty()) return;
        List<String> found = context.select(VIDEOVISUALCANONVERSION.ID)
                .from(VIDEOVISUALCANONVERSION)
                .where(
                        VIDEOVISUALCANONVERSION.ID.in(versionIds),
                        VIDEOVISUALCANONVERSION.PROJECTID.eq(projectId),
                        VIDEOVISUALCANONVERSION.NOVELID.eq(novelId))
                .fetch(VIDEOVISUALCANONVERSION.ID);
        if (!new java.util.HashSet<>(found).equals(new java.util.HashSet<>(versionIds))) {
            throw new ApiException(
                    422,
                    "VIDEO_VISUAL_REFERENCE_INVALID",
                    "镜头引用了未批准或其他项目的视觉设定版本");
        }
    }

    private ShotVisualReferenceSetResponse shotReference(
            DSLContext context, VideoshotRecord shot) {
        return shotReferences(context, List.of(shot)).getFirst();
    }

    List<ShotVisualReferenceSetResponse> shotReferences(
            DSLContext context, List<VideoshotRecord> shots) {
        if (shots.isEmpty()) return List.of();
        List<String> shotIds = shots.stream().map(VideoshotRecord::getId).toList();
        Map<String, VideoshotvisualreferencesetRecord> sets = new HashMap<>();
        context.selectFrom(VIDEOSHOTVISUALREFERENCESET)
                .where(VIDEOSHOTVISUALREFERENCESET.SHOTID.in(shotIds))
                .fetch()
                .forEach(value -> sets.put(value.getShotid(), value));
        List<VideoshotvisualreferencebindingRecord> bindings = context
                .selectFrom(VIDEOSHOTVISUALREFERENCEBINDING)
                .where(VIDEOSHOTVISUALREFERENCEBINDING.SHOTID.in(shotIds))
                .orderBy(
                        VIDEOSHOTVISUALREFERENCEBINDING.SHOTID,
                        VIDEOSHOTVISUALREFERENCEBINDING.ORDINAL)
                .fetch();
        Map<String, List<ShotVisualReferenceSnapshot>> references = referenceSnapshots(
                context,
                bindings.stream()
                        .map(value -> new ReferenceOwner(
                                value.getShotid(),
                                value.getCanonversionid(),
                                value.getStrength()))
                        .toList());
        return shots.stream()
                .map(shot -> new ShotVisualReferenceSetResponse(
                        references.getOrDefault(shot.getId(), List.of()),
                        sets.containsKey(shot.getId()) ? sets.get(shot.getId()).getRevision() : 0,
                        shot.getId(),
                        shot.getShotkey()))
                .toList();
    }

    Map<String, List<ShotVisualReferenceSnapshot>> promptReferences(
            DSLContext context, List<String> promptVersionIds) {
        if (promptVersionIds.isEmpty()) return Map.of();
        List<VideoshotpromptvisualreferenceRecord> rows = context
                .selectFrom(VIDEOSHOTPROMPTVISUALREFERENCE)
                .where(VIDEOSHOTPROMPTVISUALREFERENCE.PROMPTVERSIONID.in(promptVersionIds))
                .orderBy(
                        VIDEOSHOTPROMPTVISUALREFERENCE.PROMPTVERSIONID,
                        VIDEOSHOTPROMPTVISUALREFERENCE.ORDINAL)
                .fetch();
        return referenceSnapshots(
                context,
                rows.stream()
                        .map(value -> new ReferenceOwner(
                                value.getPromptversionid(),
                                value.getCanonversionid(),
                                value.getStrength()))
                        .toList());
    }

    private Map<String, List<ShotVisualReferenceSnapshot>> referenceSnapshots(
            DSLContext context, List<ReferenceOwner> owners) {
        if (owners.isEmpty()) return Map.of();
        List<String> versionIds = owners.stream()
                .map(ReferenceOwner::canonVersionId)
                .distinct()
                .toList();
        Map<String, VideovisualcanonversionRecord> versions = new HashMap<>();
        context.selectFrom(VIDEOVISUALCANONVERSION)
                .where(VIDEOVISUALCANONVERSION.ID.in(versionIds))
                .fetch()
                .forEach(value -> versions.put(value.getId(), value));
        Map<String, VideovisualcanonRecord> canons = new HashMap<>();
        context.selectFrom(VIDEOVISUALCANON)
                .where(VIDEOVISUALCANON.ID.in(
                        versions.values().stream()
                                .map(VideovisualcanonversionRecord::getCanonid)
                                .toList()))
                .fetch()
                .forEach(value -> canons.put(value.getId(), value));
        Map<String, VideoassetRecord> assets = new HashMap<>();
        context.selectFrom(VIDEOASSET)
                .where(VIDEOASSET.ID.in(
                        versions.values().stream()
                                .map(VideovisualcanonversionRecord::getAssetid)
                                .toList()))
                .fetch()
                .forEach(value -> assets.put(value.getId(), value));
        Map<String, List<ShotVisualReferenceSnapshot>> snapshots = new HashMap<>();
        for (ReferenceOwner owner : owners) {
            VideovisualcanonversionRecord version = versions.get(owner.canonVersionId());
            VideovisualcanonRecord canon = version == null ? null : canons.get(version.getCanonid());
            VideoassetRecord asset = version == null ? null : assets.get(version.getAssetid());
            if (version == null || canon == null || asset == null) {
                throw corrupt("镜头参考的视觉设定关系不完整");
            }
            ShotVisualReferenceSnapshot snapshot = new ShotVisualReferenceSnapshot(
                    asset.getId(),
                    asset.getSha256(),
                    version.getId(),
                    ShotVisualReferenceSnapshot.DutyEnum.fromValue(canon.getDuty()),
                    version.getLabel(),
                    canon.getSettingid(),
                    ShotVisualReferenceSnapshot.SettingKindEnum.fromValue(
                            canon.getSettingkind()),
                    version.getSettingname(),
                    owner.strength(),
                    canon.getVariantkey());
            snapshot.setIncludeFeatures(stringList(version.getIncludefeaturesjson()));
            snapshot.setExcludeFeatures(stringList(version.getExcludefeaturesjson()));
            snapshots.computeIfAbsent(owner.ownerId(), ignored -> new ArrayList<>())
                    .add(snapshot);
        }
        return snapshots;
    }

    private record ReferenceOwner(String ownerId, String canonVersionId, int strength) {}

    private String versionHash(
            VideovisualcanonRecord canon, VideoassetRecord asset, int versionNo) {
        TreeMap<String, Object> value = new TreeMap<>();
        value.put("assetId", asset.getId());
        value.put("assetSha256", asset.getSha256());
        value.put("canonId", canon.getId());
        value.put("defaultStrength", canon.getCandidatedefaultstrength());
        value.put("duty", canon.getDuty());
        value.put("excludeFeatures", stringList(canon.getCandidateexcludefeaturesjson()));
        value.put("includeFeatures", stringList(canon.getCandidateincludefeaturesjson()));
        value.put("label", canon.getLabel());
        value.put("settingId", canon.getSettingid());
        value.put("settingKind", canon.getSettingkind());
        value.put("variantKey", canon.getVariantkey());
        value.put("versionNo", versionNo);
        return sha256(json.writeValueAsString(value));
    }

    private List<String> stringList(String serialized) {
        try {
            Object value = json.readValue(serialized, new TypeReference<Object>() {});
            if (!(value instanceof List<?> list)
                    || list.stream().anyMatch(item -> !(item instanceof String))) {
                throw corrupt("视觉设定特征必须是字符串数组");
            }
            return list.stream().map(String.class::cast).toList();
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw corrupt("视觉设定特征不是合法 JSON");
        }
    }

    private static VideoAssetResponse asset(VideoassetRecord value) {
        return new VideoAssetResponse(
                value.getBytesize(),
                DatabaseTimestamp.api(value.getCreatedat()),
                value.getDurationms(),
                VideoAssetResponse.DutyEnum.fromValue(value.getDuty()),
                value.getId(),
                DatabaseTimestamp.api(value.getLockedat()),
                value.getMimetype(),
                VideoAssetResponse.ModalityEnum.fromValue(value.getModality()),
                value.getName(),
                value.getProjectid(),
                value.getRightsstatus(),
                value.getSha256(),
                value.getSourcekind(),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static VisualCanonResponse canonById(
            VisualCanonLibraryResponse library, String canonId) {
        return library.getCanons().stream()
                .filter(canon -> canon.getId().equals(canonId))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("视觉设定写入后读模型缺失"));
    }

    private static ApiException revisionConflict(int currentRevision) {
        return new ApiException(
                409,
                "VIDEO_VISUAL_CANON_REVISION_CONFLICT",
                "视觉设定已经变化，请刷新后重试",
                Map.of("currentRevision", currentRevision));
    }

    private static ApiException shotReferenceRevisionConflict(int currentRevision) {
        return new ApiException(
                409,
                "VIDEO_SHOT_VISUAL_REFERENCE_REVISION_CONFLICT",
                "镜头视觉参考已经变化，请刷新后重试",
                Map.of("currentRevision", currentRevision));
    }

    private static ApiException corrupt(String message) {
        return new ApiException(
                409, "VIDEO_VISUAL_CANON_DATA_INVALID", message);
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
