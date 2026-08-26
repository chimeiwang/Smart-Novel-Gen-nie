package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATION;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTKEYFRAMEHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTKEYFRAMEVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTVISUALREFERENCE;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTRENDERTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTTAKE;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTTAKEDECISIONCOMMAND;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTTAKEHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOVISUALCANON;
import static cn.inkforge.core.db.generated.Tables.VIDEOVISUALCANONVERSION;

import cn.inkforge.contracts.api.ChapterRenderWorkspaceResponse;
import cn.inkforge.contracts.api.ConfirmShotTakeRequest;
import cn.inkforge.contracts.api.RetryShotRenderRequest;
import cn.inkforge.contracts.api.ShotRenderKeyframeManifest;
import cn.inkforge.contracts.api.ShotRenderReferenceManifest;
import cn.inkforge.contracts.api.ShotRenderTaskResponse;
import cn.inkforge.contracts.api.ShotTakeDecisionResponse;
import cn.inkforge.contracts.api.ShotTakeHeadResponse;
import cn.inkforge.contracts.api.ShotTakeResponse;
import cn.inkforge.contracts.api.StartShotRenderRequest;
import cn.inkforge.contracts.api.VideoAssetResponse;
import cn.inkforge.contracts.api.VideoRenderReadinessResponse;
import cn.inkforge.contracts.api.VideoShotRenderManifest;
import cn.inkforge.core.db.generated.tables.records.VideoassetRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotkeyframeheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotkeyframeversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotpromptheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotpromptversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotpromptvisualreferenceRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotrendertaskRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshottakeRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshottakedecisioncommandRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshottakeheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideovisualcanonRecord;
import cn.inkforge.core.db.generated.tables.records.VideovisualcanonversionRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.CompletedVideoTake;
import cn.inkforge.core.video.application.VideoAssetFile;
import cn.inkforge.core.video.application.VideoRenderClaim;
import cn.inkforge.core.video.application.VideoRenderRepository;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.impl.DSL;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 当前正式镜头、提示词和图片事实到 Seedance 耐久任务的 jOOQ 实现。
 *
 * <p>创建任务时把 PromptVersion、视觉参考、关键帧、画幅和时长冻结成不可变 manifest；显式重试复制原
 * manifest，不读取后来变化的 Head。供应商成功 URL 只用于归档，只有受控文件、VideoAsset、不可变 Take 与
 * 任务终态在一个事务内落库后，结果才算成功。{@code submission_unknown} 刻意不自动重提，以避免重复计费。
 */
public final class JooqVideoRenderRepository implements VideoRenderRepository {

    private static final Set<String> TERMINAL =
            Set.of("submission_unknown", "succeeded", "failed", "expired", "cancelled");
    private static final Set<String> ACTIVE =
            Set.of("pending", "submitting", "queued", "running", "archiving");
    private static final Set<String> QUERY = Set.of("queued", "running", "archiving");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final VideoRenderManifestCodec manifests;

    public JooqVideoRenderRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.manifests = new VideoRenderManifestCodec(json);
    }

    @Override
    public ShotRenderTaskResponse createTask(
            String userId,
            String adaptationId,
            String shotId,
            StartShotRenderRequest request,
            String model,
            boolean referenceTransportConfigured) {
        String requestId = requestId(request.getClientRequestId());
        return database.transactionResult(transaction -> {
            // advisory lock 先串行化同镜头同请求；随后再查重，避免并发创建两条供应商计费任务。
            renderLock(transaction, "render-task", shotId, requestId);
            VideoshotrendertaskRecord existing = ownedTaskByRequest(
                    transaction, userId, shotId, requestId);
            if (existing != null) {
                VideoShotRenderManifest manifest = manifest(existing);
                validateStartReplay(existing, manifest, adaptationId, request);
                return taskResponse(existing, manifest);
            }
            var context = VideoDatabaseAccess.ownedAdaptation(
                    transaction, userId, adaptationId, true);
            String planId = context.head().getCurrentshotplanversionid();
            if (planId == null) {
                throw new ApiException(
                        409,
                        "VIDEO_RENDER_FORMAL_PLAN_REQUIRED",
                        "请先确认正式镜头方案");
            }
            VideoshotRecord shot = transaction.selectFrom(VIDEOSHOT)
                    .where(VIDEOSHOT.ID.eq(shotId), VIDEOSHOT.PLANVERSIONID.eq(planId))
                    .forUpdate()
                    .fetchOne();
            if (shot == null) {
                throw new ApiException(
                        404,
                        "VIDEO_RENDER_SHOT_NOT_FOUND",
                        "当前正式镜头不存在");
            }
            existing = transaction.selectFrom(VIDEOSHOTRENDERTASK)
                    .where(
                            VIDEOSHOTRENDERTASK.SHOTID.eq(shotId),
                            VIDEOSHOTRENDERTASK.CLIENTREQUESTID.eq(requestId))
                    .fetchOne();
            if (existing != null) {
                VideoShotRenderManifest manifest = manifest(existing);
                validateStartReplay(existing, manifest, adaptationId, request);
                return taskResponse(existing, manifest);
            }
            requireNoActiveTask(transaction, shotId);
            VideoshotpromptheadRecord promptHead = transaction
                    .selectFrom(VIDEOSHOTPROMPTHEAD)
                    .where(
                            VIDEOSHOTPROMPTHEAD.SHOTID.eq(shotId),
                            VIDEOSHOTPROMPTHEAD.SHOTPLANVERSIONID.eq(planId))
                    .forUpdate()
                    .fetchOne();
            if (promptHead == null || promptHead.getCurrentversionid() == null) {
                throw new ApiException(
                        409,
                        "VIDEO_RENDER_PROMPT_REQUIRED",
                        "请先保存当前镜头的正式提示词");
            }
            if (!Objects.equals(promptHead.getRevision(), request.getExpectedPromptRevision())) {
                throw new ApiException(
                        409,
                        "VIDEO_RENDER_PROMPT_REVISION_CONFLICT",
                        "提示词版本已经变化，请刷新后重新生成");
            }
            VideoshotpromptversionRecord prompt = transaction
                    .selectFrom(VIDEOSHOTPROMPTVERSION)
                    .where(VIDEOSHOTPROMPTVERSION.ID.eq(promptHead.getCurrentversionid()))
                    .fetchOne();
            if (prompt == null
                    || !shotId.equals(prompt.getShotid())
                    || !planId.equals(prompt.getShotplanversionid())) {
                throw new ApiException(
                        409,
                        "VIDEO_RENDER_PROMPT_HEAD_INVALID",
                        "当前正式提示词指针无效");
            }
            List<ShotRenderReferenceManifest> references =
                    promptReferences(transaction, prompt.getId());
            List<ShotRenderKeyframeManifest> keyframes = keyframes(transaction, shotId);
            if ((!references.isEmpty() || !keyframes.isEmpty())
                    && !referenceTransportConfigured) {
                throw new ApiException(
                        503,
                        "VIDEO_RENDER_REFERENCE_TRANSPORT_NOT_CONFIGURED",
                        "当前环境尚未配置供应商可访问的视觉参考图地址");
            }
            String providerPrompt = providerPrompt(prompt.getCurrenttext(), references, keyframes);
            if (providerPrompt.codePointCount(0, providerPrompt.length()) > 2_500) {
                throw new ApiException(
                        422,
                        "VIDEO_RENDER_PROVIDER_PROMPT_TOO_LONG",
                        "加入关键帧控制语句后的供应商提示词超过 2500 字符，请精简正式提示词");
            }
            VideoShotRenderManifest manifest = new VideoShotRenderManifest(
                    adaptationId,
                    request.getDurationSeconds(),
                    model,
                    context.adaptation().getNovelid(),
                    context.project().getId(),
                    prompt.getContenthash(),
                    prompt.getCurrenttext(),
                    prompt.getId(),
                    VideoShotRenderManifest.RatioEnum.fromValue(
                            context.project().getTargetaspectratio()),
                    shotId,
                    shot.getShotkey(),
                    planId,
                    shot.getTimelinedurationms());
            manifest.setSchemaVersion(
                    VideoShotRenderManifest.SchemaVersionEnum.VIDEO_SHOT_RENDER_MANIFEST_1_1);
            manifest.setProvider("seedance");
            manifest.setProviderPromptText(keyframes.isEmpty() ? null : providerPrompt);
            manifest.setResolution(VideoShotRenderManifest.ResolutionEnum.fromValue(
                    request.getResolution().getValue()));
            manifest.setGenerateAudio(request.getGenerateAudio());
            manifest.setWatermark(request.getWatermark());
            manifest.setReferences(references);
            manifest.setKeyframes(keyframes);
            // 从这一行起，供应商输入以 manifest 为准；后续 Prompt/Canon/关键帧 Head 变化不回写本任务。
            String taskId = ids.next();
            String hash = manifests.hash(manifest);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.insertInto(VIDEOSHOTRENDERTASK)
                    .set(VIDEOSHOTRENDERTASK.ID, taskId)
                    .set(VIDEOSHOTRENDERTASK.ADAPTATIONID, adaptationId)
                    .set(VIDEOSHOTRENDERTASK.PROJECTID, context.project().getId())
                    .set(VIDEOSHOTRENDERTASK.NOVELID, context.adaptation().getNovelid())
                    .set(VIDEOSHOTRENDERTASK.SHOTID, shotId)
                    .set(VIDEOSHOTRENDERTASK.SHOTPLANVERSIONID, planId)
                    .set(VIDEOSHOTRENDERTASK.PROMPTVERSIONID, prompt.getId())
                    .set(VIDEOSHOTRENDERTASK.PROVIDER, "seedance")
                    .set(VIDEOSHOTRENDERTASK.MODEL, model)
                    .set(VIDEOSHOTRENDERTASK.STATUS, "pending")
                    .set(VIDEOSHOTRENDERTASK.CLIENTREQUESTID, requestId)
                    .set(VIDEOSHOTRENDERTASK.INPUTHASH, hash)
                    .set(VIDEOSHOTRENDERTASK.REQUESTMANIFESTJSON, manifests.serialize(manifest))
                    .set(VIDEOSHOTRENDERTASK.POLLCOUNT, 0)
                    .set(VIDEOSHOTRENDERTASK.ATTEMPTCOUNT, 0)
                    .set(VIDEOSHOTRENDERTASK.NEXTATTEMPTAT, now)
                    .set(VIDEOSHOTRENDERTASK.CREATEDAT, now)
                    .set(VIDEOSHOTRENDERTASK.UPDATEDAT, now)
                    .execute();
            return taskResponse(
                    transaction.selectFrom(VIDEOSHOTRENDERTASK)
                            .where(VIDEOSHOTRENDERTASK.ID.eq(taskId))
                            .fetchOne(),
                    manifest);
        });
    }

    @Override
    public ShotRenderTaskResponse retryTask(
            String userId,
            String taskId,
            RetryShotRenderRequest request,
            boolean referenceTransportConfigured) {
        String requestId = requestId(request.getClientRequestId());
        return database.transactionResult(transaction -> {
            VideoshotrendertaskRecord source = ownedTask(transaction, userId, taskId, true);
            renderLock(transaction, "render-task", source.getShotid(), requestId);
            VideoshotrendertaskRecord existing = transaction.selectFrom(VIDEOSHOTRENDERTASK)
                    .where(
                            VIDEOSHOTRENDERTASK.SHOTID.eq(source.getShotid()),
                            VIDEOSHOTRENDERTASK.CLIENTREQUESTID.eq(requestId))
                    .fetchOne();
            if (existing != null) {
                if (!source.getId().equals(existing.getRetryoftaskid())) {
                    throw clientRequestReused("clientRequestId 已用于另一条视频任务");
                }
                return taskResponse(existing, manifest(existing));
            }
            if (!TERMINAL.contains(source.getStatus())) {
                throw new ApiException(
                        409,
                        "VIDEO_RENDER_TASK_STILL_ACTIVE",
                        "当前任务仍在执行，不能重复提交同一输入");
            }
            var context = VideoDatabaseAccess.ownedAdaptation(
                    transaction, userId, source.getAdaptationid(), true);
            if (!Objects.equals(
                    context.head().getCurrentshotplanversionid(),
                    source.getShotplanversionid())) {
                throw new ApiException(
                        409,
                        "VIDEO_RENDER_RETRY_STALE_PLAN",
                        "原任务不属于当前正式镜头方案，请从当前镜头重新生成候选");
            }
            String lockedShot = transaction.select(VIDEOSHOT.ID)
                    .from(VIDEOSHOT)
                    .where(
                            VIDEOSHOT.ID.eq(source.getShotid()),
                            VIDEOSHOT.PLANVERSIONID.eq(source.getShotplanversionid()))
                    .forUpdate()
                    .fetchOne(VIDEOSHOT.ID);
            if (lockedShot == null) throw new IllegalStateException("原逐镜视频任务引用的正式镜头不存在");
            requireNoActiveTask(transaction, source.getShotid());
            // “重试”重放原任务的不可变输入，而不是用当前 Head 重新拼装；想采用新设定必须新建任务。
            VideoShotRenderManifest manifest = manifest(source);
            if ((!list(manifest.getReferences()).isEmpty()
                            || !list(manifest.getKeyframes()).isEmpty())
                    && !referenceTransportConfigured) {
                throw new ApiException(
                        503,
                        "VIDEO_RENDER_REFERENCE_TRANSPORT_NOT_CONFIGURED",
                        "当前环境尚未配置供应商可访问的视觉参考图地址");
            }
            String retryId = ids.next();
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.insertInto(VIDEOSHOTRENDERTASK)
                    .set(VIDEOSHOTRENDERTASK.ID, retryId)
                    .set(VIDEOSHOTRENDERTASK.ADAPTATIONID, source.getAdaptationid())
                    .set(VIDEOSHOTRENDERTASK.PROJECTID, source.getProjectid())
                    .set(VIDEOSHOTRENDERTASK.NOVELID, source.getNovelid())
                    .set(VIDEOSHOTRENDERTASK.SHOTID, source.getShotid())
                    .set(VIDEOSHOTRENDERTASK.SHOTPLANVERSIONID, source.getShotplanversionid())
                    .set(VIDEOSHOTRENDERTASK.PROMPTVERSIONID, source.getPromptversionid())
                    .set(VIDEOSHOTRENDERTASK.RETRYOFTASKID, source.getId())
                    .set(VIDEOSHOTRENDERTASK.PROVIDER, source.getProvider())
                    .set(VIDEOSHOTRENDERTASK.MODEL, source.getModel())
                    .set(VIDEOSHOTRENDERTASK.STATUS, "pending")
                    .set(VIDEOSHOTRENDERTASK.CLIENTREQUESTID, requestId)
                    .set(VIDEOSHOTRENDERTASK.INPUTHASH, source.getInputhash())
                    .set(
                            VIDEOSHOTRENDERTASK.REQUESTMANIFESTJSON,
                            source.getRequestmanifestjson())
                    .set(VIDEOSHOTRENDERTASK.POLLCOUNT, 0)
                    .set(VIDEOSHOTRENDERTASK.ATTEMPTCOUNT, 0)
                    .set(VIDEOSHOTRENDERTASK.NEXTATTEMPTAT, now)
                    .set(VIDEOSHOTRENDERTASK.CREATEDAT, now)
                    .set(VIDEOSHOTRENDERTASK.UPDATEDAT, now)
                    .execute();
            return taskResponse(
                    transaction.selectFrom(VIDEOSHOTRENDERTASK)
                            .where(VIDEOSHOTRENDERTASK.ID.eq(retryId))
                            .fetchOne(),
                    manifest);
        });
    }

    @Override
    public ShotRenderTaskResponse getTask(String userId, String taskId) {
        VideoshotrendertaskRecord task = ownedTask(database.dsl(), userId, taskId, false);
        return taskResponse(task, manifest(task));
    }

    @Override
    public ChapterRenderWorkspaceResponse getWorkspace(
            String userId,
            String adaptationId,
            VideoRenderReadinessResponse readiness) {
        var context = VideoDatabaseAccess.ownedAdaptation(
                database.dsl(), userId, adaptationId, false);
        String planId = context.head().getCurrentshotplanversionid();
        if (planId == null) {
            return new ChapterRenderWorkspaceResponse(
                    adaptationId, readiness, List.of(), List.of(), List.of());
        }
        List<VideoshotrendertaskRecord> taskRows = database.dsl()
                .selectFrom(VIDEOSHOTRENDERTASK)
                .where(
                        VIDEOSHOTRENDERTASK.ADAPTATIONID.eq(adaptationId),
                        VIDEOSHOTRENDERTASK.SHOTPLANVERSIONID.eq(planId))
                .orderBy(VIDEOSHOTRENDERTASK.CREATEDAT.desc(), VIDEOSHOTRENDERTASK.ID.desc())
                .fetch();
        List<Record> takeRows = database.dsl().select(VIDEOSHOTTAKE.fields())
                .select(VIDEOASSET.fields())
                .from(VIDEOSHOTTAKE)
                .join(VIDEOASSET)
                .on(VIDEOASSET.ID.eq(VIDEOSHOTTAKE.ASSETID))
                .where(
                        VIDEOSHOTTAKE.ADAPTATIONID.eq(adaptationId),
                        VIDEOSHOTTAKE.SHOTPLANVERSIONID.eq(planId))
                .orderBy(VIDEOSHOTTAKE.SHOTID, VIDEOSHOTTAKE.TAKENO)
                .fetch();
        Map<String, VideoshottakeheadRecord> heads = new HashMap<>();
        database.dsl().selectFrom(VIDEOSHOTTAKEHEAD)
                .where(VIDEOSHOTTAKEHEAD.SHOTPLANVERSIONID.eq(planId))
                .fetch()
                .forEach(value -> heads.put(value.getShotid(), value));
        List<String> shotIds = database.dsl().select(VIDEOSHOT.ID)
                .from(VIDEOSHOT)
                .where(VIDEOSHOT.PLANVERSIONID.eq(planId))
                .orderBy(VIDEOSHOT.ORDINAL)
                .fetch(VIDEOSHOT.ID);
        var takeHeads = shotIds.stream()
                .map(shotId -> headResponse(
                        heads.get(shotId), shotId, DatabaseTimestamp.now(clock)))
                .toList();
        return new ChapterRenderWorkspaceResponse(
                adaptationId,
                readiness,
                takeHeads,
                takeRows.stream()
                        .map(row -> takeResponse(
                                row.into(VIDEOSHOTTAKE), row.into(VIDEOASSET)))
                        .toList(),
                taskRows.stream().map(task -> taskResponse(task, manifest(task))).toList());
    }

    @Override
    public ShotTakeDecisionResponse confirmTake(
            String userId,
            String adaptationId,
            String shotId,
            String takeId,
            ConfirmShotTakeRequest request) {
        String requestId = requestId(request.getClientRequestId());
        String requestHash = canonicalHash(Map.of(
                "userId", userId,
                "adaptationId", adaptationId,
                "shotId", shotId,
                "takeId", takeId,
                "expectedTakeRevision", request.getExpectedTakeRevision()));
        return database.transactionResult(transaction -> {
            // 决定命令和 TakeHead 使用同一幂等锁；无论成功还是 CAS 冲突，都留下可重放的事实。
            renderLock(transaction, "take-decision", userId, requestId);
            VideoshottakedecisioncommandRecord existing = transaction
                    .selectFrom(VIDEOSHOTTAKEDECISIONCOMMAND)
                    .where(
                            VIDEOSHOTTAKEDECISIONCOMMAND.REQUESTEDBYUSERID.eq(userId),
                            VIDEOSHOTTAKEDECISIONCOMMAND.CLIENTREQUESTID.eq(requestId))
                    .fetchOne();
            if (existing != null) {
                if (!requestHash.equals(existing.getRequesthash())) {
                    throw new ApiException(
                            409,
                            "VIDEO_TAKE_CLIENT_REQUEST_REUSED",
                            "clientRequestId 已用于不同的选片确认请求");
                }
                return decisionResponse(existing);
            }
            var context = VideoDatabaseAccess.ownedAdaptation(
                    transaction, userId, adaptationId, true);
            VideoshottakeRecord take = transaction.selectFrom(VIDEOSHOTTAKE)
                    .where(
                            VIDEOSHOTTAKE.ID.eq(takeId),
                            VIDEOSHOTTAKE.SHOTID.eq(shotId),
                            VIDEOSHOTTAKE.ADAPTATIONID.eq(adaptationId))
                    .fetchOne();
            if (take == null
                    || !Objects.equals(
                            take.getShotplanversionid(),
                            context.head().getCurrentshotplanversionid())) {
                throw new ApiException(
                        404,
                        "VIDEO_TAKE_NOT_FOUND",
                        "当前正式方案中不存在该候选 Take");
            }
            VideoshottakeheadRecord head = transaction.selectFrom(VIDEOSHOTTAKEHEAD)
                    .where(VIDEOSHOTTAKEHEAD.SHOTID.eq(shotId))
                    .forUpdate()
                    .fetchOne();
            LocalDateTime now = DatabaseTimestamp.now(clock);
            if (head == null) {
                transaction.insertInto(VIDEOSHOTTAKEHEAD)
                        .set(VIDEOSHOTTAKEHEAD.SHOTID, shotId)
                        .set(
                                VIDEOSHOTTAKEHEAD.SHOTPLANVERSIONID,
                                take.getShotplanversionid())
                        .set(VIDEOSHOTTAKEHEAD.REVISION, 1)
                        .set(VIDEOSHOTTAKEHEAD.UPDATEDAT, now)
                        .execute();
                head = transaction.selectFrom(VIDEOSHOTTAKEHEAD)
                        .where(VIDEOSHOTTAKEHEAD.SHOTID.eq(shotId))
                        .forUpdate()
                        .fetchOne();
            }
            String status;
            Integer resultingRevision;
            String errorCode;
            String currentTakeId;
            if (!Objects.equals(head.getRevision(), request.getExpectedTakeRevision())) {
                status = "conflict";
                resultingRevision = null;
                errorCode = "VIDEO_TAKE_REVISION_CONFLICT";
                currentTakeId = head.getCurrenttakeid();
            } else {
                resultingRevision = head.getRevision() + 1;
                transaction.update(VIDEOSHOTTAKEHEAD)
                        .set(VIDEOSHOTTAKEHEAD.CURRENTTAKEID, takeId)
                        .set(VIDEOSHOTTAKEHEAD.REVISION, resultingRevision)
                        .set(VIDEOSHOTTAKEHEAD.UPDATEDAT, now)
                        .where(VIDEOSHOTTAKEHEAD.SHOTID.eq(shotId))
                        .execute();
                status = "succeeded";
                errorCode = null;
                currentTakeId = takeId;
            }
            // 冲突也写命令记录，客户端重试时返回第一次观察到的结果，而不是重新参与一次竞态。
            String commandId = ids.next();
            transaction.insertInto(VIDEOSHOTTAKEDECISIONCOMMAND)
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.ID, commandId)
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.REQUESTEDBYUSERID, userId)
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.NOVELID, context.adaptation().getNovelid())
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.PROJECTID, context.project().getId())
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.ADAPTATIONID, adaptationId)
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.SHOTID, shotId)
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.TAKEID, takeId)
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.CLIENTREQUESTID, requestId)
                    .set(
                            VIDEOSHOTTAKEDECISIONCOMMAND.EXPECTEDREVISION,
                            request.getExpectedTakeRevision())
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.REQUESTHASH, requestHash)
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.STATUS, status)
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.OBSERVEDCURRENTTAKEID, currentTakeId)
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.RESULTINGREVISION, resultingRevision)
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.ERRORCODE, errorCode)
                    .set(VIDEOSHOTTAKEDECISIONCOMMAND.CREATEDAT, now)
                    .execute();
            return decisionResponse(transaction.selectFrom(VIDEOSHOTTAKEDECISIONCOMMAND)
                    .where(VIDEOSHOTTAKEDECISIONCOMMAND.ID.eq(commandId))
                    .fetchOne());
        });
    }

    @Override
    public VideoAssetFile getTakeFile(String userId, String takeId) {
        VideoassetRecord asset = database.dsl().select(VIDEOASSET.fields())
                .from(VIDEOASSET)
                .join(VIDEOSHOTTAKE)
                .on(VIDEOSHOTTAKE.ASSETID.eq(VIDEOASSET.ID))
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOSHOTTAKE.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(VIDEOSHOTTAKE.ID.eq(takeId), NOVEL.USERID.eq(userId))
                .fetchOneInto(VideoassetRecord.class);
        if (asset == null) {
            throw new ApiException(404, "VIDEO_TAKE_NOT_FOUND", "候选 Take 不存在");
        }
        return new VideoAssetFile(asset.getStoragekey(), asset.getMimetype(), asset.getName());
    }

    @Override
    public VideoAssetFile getProviderAssetFile(String assetId, String sha256) {
        VideoassetRecord asset = database.dsl().selectFrom(VIDEOASSET)
                .where(
                        VIDEOASSET.ID.eq(assetId),
                        VIDEOASSET.SHA256.eq(sha256),
                        VIDEOASSET.MODALITY.eq("image"),
                        VIDEOASSET.RIGHTSSTATUS.eq("confirmed"),
                        VIDEOASSET.LOCKEDAT.isNotNull())
                .fetchOne();
        if (asset == null) {
            throw new ApiException(
                    404,
                    "VIDEO_PROVIDER_ASSET_NOT_FOUND",
                    "供应商参考素材不存在或不可用");
        }
        return new VideoAssetFile(asset.getStoragekey(), asset.getMimetype(), asset.getName());
    }

    @Override
    public List<VideoRenderClaim> claimDue(int limit) {
        if (limit < 1) throw new IllegalArgumentException("逐镜渲染任务领取数量必须为正整数");
        LocalDateTime now = DatabaseTimestamp.now(clock);
        LocalDateTime lease = now.plusSeconds(90);
        return database.transactionResult(transaction -> {
            // 每次领取都先在数据库续租；SKIP LOCKED 允许多个 reconciler 安全并行。
            List<VideoshotrendertaskRecord> tasks = transaction.selectFrom(VIDEOSHOTRENDERTASK)
                    .where(
                            VIDEOSHOTRENDERTASK.STATUS.in(
                                    "pending", "submitting", "queued", "running", "archiving"),
                            VIDEOSHOTRENDERTASK.NEXTATTEMPTAT.le(now))
                    .orderBy(VIDEOSHOTRENDERTASK.NEXTATTEMPTAT, VIDEOSHOTRENDERTASK.CREATEDAT)
                    .limit(limit)
                    .forUpdate()
                    .skipLocked()
                    .fetch();
            List<VideoRenderClaim> claims = new ArrayList<>();
            for (VideoshotrendertaskRecord task : tasks) {
                if ("submitting".equals(task.getStatus())) {
                    // 进程可能已让供应商创建任务但尚未保存 providerTaskId；自动重提会造成重复视频和重复计费。
                    finish(
                            transaction,
                            task,
                            Set.of("submitting"),
                            "submission_unknown",
                            "SEEDANCE_SUBMISSION_RECOVERY_UNKNOWN",
                            "服务在供应商创建请求期间中断，未自动重提以避免重复计费");
                    continue;
                }
                VideoShotRenderManifest manifest = manifest(task);
                String claimedStatus = task.getStatus();
                int attempts = task.getAttemptcount();
                int polls = task.getPollcount();
                if ("pending".equals(task.getStatus())) {
                    claimedStatus = "submitting";
                    attempts++;
                } else {
                    polls++;
                }
                transaction.update(VIDEOSHOTRENDERTASK)
                        .set(VIDEOSHOTRENDERTASK.STATUS, claimedStatus)
                        .set(VIDEOSHOTRENDERTASK.ATTEMPTCOUNT, attempts)
                        .set(VIDEOSHOTRENDERTASK.POLLCOUNT, polls)
                        .set(VIDEOSHOTRENDERTASK.NEXTATTEMPTAT, lease)
                        .set(VIDEOSHOTRENDERTASK.UPDATEDAT, now)
                        .where(VIDEOSHOTRENDERTASK.ID.eq(task.getId()))
                        .execute();
                claims.add(new VideoRenderClaim(
                        task.getId(),
                        task.getProjectid(),
                        task.getNovelid(),
                        claimedStatus,
                        task.getProvidertaskid(),
                        polls,
                        task.getInputhash(),
                        manifest));
            }
            return List.copyOf(claims);
        });
    }

    @Override
    public void markSubmitted(String taskId, String providerTaskId) {
        database.transactionResult(transaction -> {
            VideoshotrendertaskRecord task = lockTask(transaction, taskId);
            if (task == null || !"submitting".equals(task.getStatus())) return null;
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.update(VIDEOSHOTRENDERTASK)
                    .set(VIDEOSHOTRENDERTASK.PROVIDERTASKID, providerTaskId)
                    .set(VIDEOSHOTRENDERTASK.STATUS, "queued")
                    .set(VIDEOSHOTRENDERTASK.SUBMITTEDAT, now)
                    .set(VIDEOSHOTRENDERTASK.NEXTATTEMPTAT, now.plusSeconds(5))
                    .set(VIDEOSHOTRENDERTASK.LASTERRORCODE, (String) null)
                    .set(VIDEOSHOTRENDERTASK.LASTERRORMESSAGE, (String) null)
                    .set(VIDEOSHOTRENDERTASK.UPDATEDAT, now)
                    .where(VIDEOSHOTRENDERTASK.ID.eq(taskId))
                    .execute();
            return null;
        });
    }

    @Override
    public void markSubmissionUnknown(String taskId, String message) {
        finishTask(taskId, Set.of("submitting"), "submission_unknown", "SEEDANCE_SUBMISSION_UNKNOWN", message);
    }

    @Override
    public void markSubmissionRejected(String taskId, String code, String message) {
        finishTask(taskId, Set.of("submitting"), "failed", code, message);
    }

    @Override
    public void markQueryProgress(String taskId, String status) {
        if (!Set.of("queued", "running").contains(status)) {
            throw new IllegalArgumentException("Seedance 活动状态无效");
        }
        database.transactionResult(transaction -> {
            VideoshotrendertaskRecord task = lockTask(transaction, taskId);
            if (task == null || !QUERY.contains(task.getStatus())) return null;
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.update(VIDEOSHOTRENDERTASK)
                    .set(VIDEOSHOTRENDERTASK.STATUS, status)
                    .set(VIDEOSHOTRENDERTASK.NEXTATTEMPTAT, now.plusSeconds(pollBackoff(task.getPollcount())))
                    .set(VIDEOSHOTRENDERTASK.LASTERRORCODE, (String) null)
                    .set(VIDEOSHOTRENDERTASK.LASTERRORMESSAGE, (String) null)
                    .set(VIDEOSHOTRENDERTASK.UPDATEDAT, now)
                    .where(VIDEOSHOTRENDERTASK.ID.eq(taskId))
                    .execute();
            return null;
        });
    }

    @Override
    public void markQueryError(String taskId, String message) {
        database.transactionResult(transaction -> {
            VideoshotrendertaskRecord task = lockTask(transaction, taskId);
            if (task == null || !QUERY.contains(task.getStatus())) return null;
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.update(VIDEOSHOTRENDERTASK)
                    .set(VIDEOSHOTRENDERTASK.ATTEMPTCOUNT, task.getAttemptcount() + 1)
                    .set(VIDEOSHOTRENDERTASK.NEXTATTEMPTAT, now.plusSeconds(pollBackoff(task.getPollcount())))
                    .set(VIDEOSHOTRENDERTASK.LASTERRORCODE, "SEEDANCE_QUERY_RETRY")
                    .set(VIDEOSHOTRENDERTASK.LASTERRORMESSAGE, message)
                    .set(VIDEOSHOTRENDERTASK.UPDATEDAT, now)
                    .where(VIDEOSHOTRENDERTASK.ID.eq(taskId))
                    .execute();
            return null;
        });
    }

    @Override
    public boolean beginArchiving(String taskId) {
        return database.transactionResult(transaction -> {
            VideoshotrendertaskRecord task = lockTask(transaction, taskId);
            if (task == null || !QUERY.contains(task.getStatus())) return false;
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.update(VIDEOSHOTRENDERTASK)
                    .set(VIDEOSHOTRENDERTASK.STATUS, "archiving")
                    .set(VIDEOSHOTRENDERTASK.NEXTATTEMPTAT, now.plusMinutes(3))
                    .set(VIDEOSHOTRENDERTASK.UPDATEDAT, now)
                    .where(VIDEOSHOTRENDERTASK.ID.eq(taskId))
                    .execute();
            return true;
        });
    }

    @Override
    public void markProviderTerminal(String taskId, String status, String code, String message) {
        if (!Set.of("failed", "expired", "cancelled").contains(status)) {
            throw new IllegalArgumentException("Seedance 终态无效");
        }
        finishTask(taskId, QUERY, status, code, message);
    }

    @Override
    public boolean failArchiving(String taskId, String message) {
        return finishTaskResult(
                taskId,
                Set.of("archiving"),
                "failed",
                "SEEDANCE_RESULT_ARCHIVE_FAILED",
                message);
    }

    @Override
    public void completeTake(String taskId, CompletedVideoTake completed) {
        database.transactionResult(transaction -> {
            VideoshotrendertaskRecord task = lockTask(transaction, taskId);
            if (task == null) throw new IllegalStateException("逐镜渲染任务不存在");
            VideoshottakeRecord existing = transaction.selectFrom(VIDEOSHOTTAKE)
                    .where(VIDEOSHOTTAKE.TASKID.eq(taskId))
                    .fetchOne();
            if (existing != null) return null;
            if (!"archiving".equals(task.getStatus()) || task.getProvidertaskid() == null) {
                throw new IllegalStateException("逐镜渲染任务不在归档阶段");
            }
            if (!taskId.equals(completed.assetId())) {
                throw new IllegalArgumentException("归档素材必须使用任务确定性标识");
            }
            transaction.select(VIDEOSHOT.ID)
                    .from(VIDEOSHOT)
                    .where(VIDEOSHOT.ID.eq(task.getShotid()))
                    .forUpdate()
                    .fetchOne();
            Integer maximum = transaction.select(DSL.coalesce(DSL.max(VIDEOSHOTTAKE.TAKENO), 0))
                    .from(VIDEOSHOTTAKE)
                    .where(VIDEOSHOTTAKE.SHOTID.eq(task.getShotid()))
                    .fetchOne(0, Integer.class);
            int takeNo = (maximum == null ? 0 : maximum) + 1;
            VideoShotRenderManifest manifest = manifest(task);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            // Asset、不可变 Take 与任务成功必须同事务提交；缺少任一事实都不能对外宣称渲染完成。
            transaction.insertInto(VIDEOASSET)
                    .set(VIDEOASSET.ID, completed.assetId())
                    .set(VIDEOASSET.PROJECTID, task.getProjectid())
                    .set(VIDEOASSET.NAME, manifest.getShotKey() + " · Take " + takeNo)
                    .set(VIDEOASSET.MODALITY, "video")
                    .set(VIDEOASSET.DUTY, "motion")
                    .set(VIDEOASSET.STORAGEKEY, completed.stored().storageKey())
                    .set(VIDEOASSET.MIMETYPE, completed.stored().mimeType())
                    .set(VIDEOASSET.BYTESIZE, completed.stored().byteSize())
                    .set(VIDEOASSET.DURATIONMS, completed.durationMs())
                    .set(VIDEOASSET.SHA256, completed.stored().sha256())
                    .set(VIDEOASSET.SOURCEKIND, "model_generated")
                    .set(VIDEOASSET.RIGHTSSTATUS, "confirmed")
                    .set(VIDEOASSET.LOCKEDAT, now)
                    .set(VIDEOASSET.CREATEDAT, now)
                    .set(VIDEOASSET.UPDATEDAT, now)
                    .execute();
            transaction.insertInto(VIDEOSHOTTAKE)
                    .set(VIDEOSHOTTAKE.ID, ids.next())
                    .set(VIDEOSHOTTAKE.TASKID, taskId)
                    .set(VIDEOSHOTTAKE.ADAPTATIONID, task.getAdaptationid())
                    .set(VIDEOSHOTTAKE.PROJECTID, task.getProjectid())
                    .set(VIDEOSHOTTAKE.NOVELID, task.getNovelid())
                    .set(VIDEOSHOTTAKE.SHOTID, task.getShotid())
                    .set(VIDEOSHOTTAKE.SHOTPLANVERSIONID, task.getShotplanversionid())
                    .set(VIDEOSHOTTAKE.PROMPTVERSIONID, task.getPromptversionid())
                    .set(VIDEOSHOTTAKE.ASSETID, completed.assetId())
                    .set(VIDEOSHOTTAKE.TAKENO, takeNo)
                    .set(VIDEOSHOTTAKE.PROVIDER, task.getProvider())
                    .set(VIDEOSHOTTAKE.MODEL, task.getModel())
                    .set(VIDEOSHOTTAKE.PROVIDERTASKID, task.getProvidertaskid())
                    .set(VIDEOSHOTTAKE.INPUTHASH, task.getInputhash())
                    .set(
                            VIDEOSHOTTAKE.PROVIDERMETADATAJSON,
                            canonicalJson(completed.providerMetadata()))
                    .set(VIDEOSHOTTAKE.CREATEDAT, now)
                    .execute();
            transaction.update(VIDEOSHOTRENDERTASK)
                    .set(VIDEOSHOTRENDERTASK.STATUS, "succeeded")
                    .set(VIDEOSHOTRENDERTASK.LASTERRORCODE, (String) null)
                    .set(VIDEOSHOTRENDERTASK.LASTERRORMESSAGE, (String) null)
                    .set(VIDEOSHOTRENDERTASK.COMPLETEDAT, now)
                    .set(VIDEOSHOTRENDERTASK.NEXTATTEMPTAT, now)
                    .set(VIDEOSHOTRENDERTASK.UPDATEDAT, now)
                    .where(VIDEOSHOTRENDERTASK.ID.eq(taskId))
                    .execute();
            return null;
        });
    }

    private List<ShotRenderReferenceManifest> promptReferences(
            DSLContext context, String promptVersionId) {
        List<VideoshotpromptvisualreferenceRecord> bindings = context
                .selectFrom(VIDEOSHOTPROMPTVISUALREFERENCE)
                .where(VIDEOSHOTPROMPTVISUALREFERENCE.PROMPTVERSIONID.eq(promptVersionId))
                .orderBy(VIDEOSHOTPROMPTVISUALREFERENCE.ORDINAL)
                .fetch();
        List<ShotRenderReferenceManifest> result = new ArrayList<>();
        for (VideoshotpromptvisualreferenceRecord binding : bindings) {
            VideovisualcanonversionRecord version = context
                    .selectFrom(VIDEOVISUALCANONVERSION)
                    .where(VIDEOVISUALCANONVERSION.ID.eq(binding.getCanonversionid()))
                    .fetchOne();
            VideovisualcanonRecord canon = version == null
                    ? null
                    : context.selectFrom(VIDEOVISUALCANON)
                            .where(VIDEOVISUALCANON.ID.eq(version.getCanonid()))
                            .fetchOne();
            VideoassetRecord asset = version == null
                    ? null
                    : context.selectFrom(VIDEOASSET)
                            .where(VIDEOASSET.ID.eq(version.getAssetid()))
                            .fetchOne();
            if (version == null
                    || canon == null
                    || asset == null
                    || !"image".equals(asset.getModality())
                    || !"confirmed".equals(asset.getRightsstatus())
                    || asset.getLockedat() == null) {
                throw new ApiException(
                        409,
                        "VIDEO_RENDER_REFERENCE_NOT_READY",
                        "视觉参考未完成权利确认和锁定");
            }
            result.add(new ShotRenderReferenceManifest(
                    asset.getId(),
                    version.getId(),
                    ShotRenderReferenceManifest.DutyEnum.fromValue(canon.getDuty()),
                    asset.getMimetype(),
                    binding.getOrdinal(),
                    asset.getSha256(),
                    binding.getStrength()));
        }
        return List.copyOf(result);
    }

    private List<ShotRenderKeyframeManifest> keyframes(DSLContext context, String shotId) {
        List<VideoshotkeyframeheadRecord> heads = context.selectFrom(VIDEOSHOTKEYFRAMEHEAD)
                .where(
                        VIDEOSHOTKEYFRAMEHEAD.SHOTID.eq(shotId),
                        VIDEOSHOTKEYFRAMEHEAD.CURRENTVERSIONID.isNotNull())
                .fetch();
        Map<String, Integer> order = Map.of(
                "initial_state", 1, "transition_anchor", 2, "end_state", 3);
        heads.sort(Comparator.comparingInt(value -> order.getOrDefault(value.getRole(), 99)));
        List<ShotRenderKeyframeManifest> result = new ArrayList<>();
        for (VideoshotkeyframeheadRecord head : heads) {
            Integer ordinal = order.get(head.getRole());
            if (ordinal == null) {
                throw new ApiException(
                        409,
                        "VIDEO_RENDER_KEYFRAME_ROLE_INVALID",
                        "当前关键帧包含未知角色");
            }
            VideoshotkeyframeversionRecord version = context
                    .selectFrom(VIDEOSHOTKEYFRAMEVERSION)
                    .where(VIDEOSHOTKEYFRAMEVERSION.ID.eq(head.getCurrentversionid()))
                    .fetchOne();
            VideoassetRecord asset = version == null || version.getAssetid() == null
                    ? null
                    : context.selectFrom(VIDEOASSET)
                            .where(VIDEOASSET.ID.eq(version.getAssetid()))
                            .fetchOne();
            if (version == null
                    || asset == null
                    || !shotId.equals(version.getShotid())
                    || !head.getRole().equals(version.getRole())
                    || !"image".equals(asset.getModality())
                    || !Set.of("keyframe", "storyboard").contains(asset.getDuty())
                    || !"confirmed".equals(asset.getRightsstatus())
                    || asset.getLockedat() == null) {
                throw new ApiException(
                        409,
                        "VIDEO_RENDER_KEYFRAME_NOT_READY",
                        "当前关键帧素材不存在或未完成权利确认和锁定");
            }
            result.add(new ShotRenderKeyframeManifest(
                    asset.getId(),
                    ShotRenderKeyframeManifest.DutyEnum.fromValue(asset.getDuty()),
                    version.getId(),
                    asset.getMimetype(),
                    ordinal,
                    ShotRenderKeyframeManifest.RoleEnum.fromValue(head.getRole()),
                    asset.getSha256()));
        }
        return List.copyOf(result);
    }

    private static String providerPrompt(
            String prompt,
            List<ShotRenderReferenceManifest> references,
            List<ShotRenderKeyframeManifest> keyframes) {
        if (keyframes.isEmpty()) return prompt;
        int imageIndex = 1;
        List<String> instructions = new ArrayList<>();
        Map<String, ShotRenderKeyframeManifest> byRole = new HashMap<>();
        keyframes.forEach(frame -> byRole.put(frame.getRole().getValue(), frame));
        if (byRole.containsKey("initial_state")) {
            instructions.add("图片" + imageIndex + "严格作为首帧构图与人物状态");
            imageIndex++;
        }
        imageIndex += references.size();
        if (byRole.containsKey("transition_anchor")) {
            instructions.add("图片" + imageIndex + "作为镜头中段的状态过渡锚点");
            imageIndex++;
        }
        if (byRole.containsKey("end_state")) {
            instructions.add("图片" + imageIndex + "严格作为尾帧状态与最终构图");
        }
        return "关键帧控制：" + String.join("；", instructions) + "。\n" + prompt;
    }

    private VideoshotrendertaskRecord ownedTask(
            DSLContext context, String userId, String taskId, boolean lock) {
        var query = context.select(VIDEOSHOTRENDERTASK.fields())
                .from(VIDEOSHOTRENDERTASK)
                .join(VIDEOCHAPTERADAPTATION)
                .on(VIDEOCHAPTERADAPTATION.ID.eq(VIDEOSHOTRENDERTASK.ADAPTATIONID))
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOCHAPTERADAPTATION.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(VIDEOSHOTRENDERTASK.ID.eq(taskId), NOVEL.USERID.eq(userId));
        VideoshotrendertaskRecord task = lock
                ? query.forUpdate().fetchOneInto(VideoshotrendertaskRecord.class)
                : query.fetchOneInto(VideoshotrendertaskRecord.class);
        if (task == null) {
            throw new ApiException(
                    404,
                    "VIDEO_RENDER_TASK_NOT_FOUND",
                    "逐镜视频任务不存在");
        }
        return task;
    }

    private VideoshotrendertaskRecord ownedTaskByRequest(
            DSLContext context, String userId, String shotId, String requestId) {
        return context.select(VIDEOSHOTRENDERTASK.fields())
                .from(VIDEOSHOTRENDERTASK)
                .join(VIDEOCHAPTERADAPTATION)
                .on(VIDEOCHAPTERADAPTATION.ID.eq(VIDEOSHOTRENDERTASK.ADAPTATIONID))
                .join(VIDEOPROJECT)
                .on(VIDEOPROJECT.ID.eq(VIDEOCHAPTERADAPTATION.PROJECTID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(VIDEOPROJECT.NOVELID))
                .where(
                        VIDEOSHOTRENDERTASK.SHOTID.eq(shotId),
                        VIDEOSHOTRENDERTASK.CLIENTREQUESTID.eq(requestId),
                        NOVEL.USERID.eq(userId))
                .fetchOneInto(VideoshotrendertaskRecord.class);
    }

    private static VideoshotrendertaskRecord lockTask(DSLContext context, String taskId) {
        return context.selectFrom(VIDEOSHOTRENDERTASK)
                .where(VIDEOSHOTRENDERTASK.ID.eq(taskId))
                .forUpdate()
                .fetchOne();
    }

    private VideoShotRenderManifest manifest(VideoshotrendertaskRecord task) {
        return manifests.parse(task.getRequestmanifestjson(), task.getInputhash());
    }

    private static void validateStartReplay(
            VideoshotrendertaskRecord task,
            VideoShotRenderManifest manifest,
            String adaptationId,
            StartShotRenderRequest request) {
        if (!task.getAdaptationid().equals(adaptationId)
                || !manifest.getDurationSeconds().equals(request.getDurationSeconds())
                || !manifest.getResolution().getValue().equals(request.getResolution().getValue())
                || !manifest.getGenerateAudio().equals(request.getGenerateAudio())
                || !manifest.getWatermark().equals(request.getWatermark())) {
            throw clientRequestReused("clientRequestId 已用于不同的视频生成请求");
        }
    }

    private static void requireNoActiveTask(DSLContext context, String shotId) {
        String active = context.select(VIDEOSHOTRENDERTASK.ID)
                .from(VIDEOSHOTRENDERTASK)
                .where(
                        VIDEOSHOTRENDERTASK.SHOTID.eq(shotId),
                        VIDEOSHOTRENDERTASK.STATUS.in(ACTIVE))
                .fetchAny(VIDEOSHOTRENDERTASK.ID);
        if (active != null) {
            throw new ApiException(
                    409,
                    "VIDEO_RENDER_SHOT_TASK_ACTIVE",
                    "当前镜头已有生成任务在执行，请等待完成后再创建新候选");
        }
    }

    private ShotRenderTaskResponse taskResponse(
            VideoshotrendertaskRecord task, VideoShotRenderManifest manifest) {
        return new ShotRenderTaskResponse(
                task.getAdaptationid(),
                task.getAttemptcount(),
                DatabaseTimestamp.api(task.getCompletedat()),
                DatabaseTimestamp.api(task.getCreatedat()),
                task.getId(),
                task.getInputhash(),
                task.getLasterrorcode(),
                task.getLasterrormessage(),
                manifest,
                task.getModel(),
                task.getPollcount(),
                task.getPromptversionid(),
                task.getProvider(),
                task.getProvidertaskid(),
                task.getRetryoftaskid(),
                task.getShotid(),
                task.getShotplanversionid(),
                ShotRenderTaskResponse.StatusEnum.fromValue(task.getStatus()),
                DatabaseTimestamp.api(task.getSubmittedat()),
                DatabaseTimestamp.api(task.getUpdatedat()));
    }

    private ShotTakeResponse takeResponse(
            VideoshottakeRecord take, VideoassetRecord asset) {
        Map<String, Object> metadata;
        try {
            metadata = json.readValue(
                    take.getProvidermetadatajson(),
                    new TypeReference<Map<String, Object>>() {});
        } catch (RuntimeException exception) {
            throw new IllegalStateException("候选 Take 的供应商元数据无效", exception);
        }
        return new ShotTakeResponse(
                take.getAdaptationid(),
                assetResponse(asset),
                DatabaseTimestamp.api(take.getCreatedat()),
                take.getId(),
                take.getInputhash(),
                take.getModel(),
                take.getPromptversionid(),
                take.getProvider(),
                metadata,
                take.getProvidertaskid(),
                take.getShotid(),
                take.getShotplanversionid(),
                take.getTakeno(),
                take.getTaskid());
    }

    private static VideoAssetResponse assetResponse(VideoassetRecord asset) {
        return new VideoAssetResponse(
                asset.getBytesize(),
                DatabaseTimestamp.api(asset.getCreatedat()),
                asset.getDurationms(),
                VideoAssetResponse.DutyEnum.fromValue(asset.getDuty()),
                asset.getId(),
                DatabaseTimestamp.api(asset.getLockedat()),
                asset.getMimetype(),
                VideoAssetResponse.ModalityEnum.fromValue(asset.getModality()),
                asset.getName(),
                asset.getProjectid(),
                asset.getRightsstatus(),
                asset.getSha256(),
                asset.getSourcekind(),
                DatabaseTimestamp.api(asset.getUpdatedat()));
    }

    private static ShotTakeHeadResponse headResponse(
            VideoshottakeheadRecord head, String shotId, LocalDateTime fallback) {
        return head == null
                ? new ShotTakeHeadResponse(null, 1, shotId, DatabaseTimestamp.api(fallback))
                : new ShotTakeHeadResponse(
                        head.getCurrenttakeid(),
                        head.getRevision(),
                        shotId,
                        DatabaseTimestamp.api(head.getUpdatedat()));
    }

    private static ShotTakeDecisionResponse decisionResponse(
            VideoshottakedecisioncommandRecord command) {
        return new ShotTakeDecisionResponse(
                command.getId(),
                command.getObservedcurrenttakeid(),
                command.getErrorcode(),
                command.getResultingrevision(),
                command.getShotid(),
                ShotTakeDecisionResponse.StatusEnum.fromValue(command.getStatus()),
                command.getTakeid());
    }

    private void finishTask(
            String taskId,
            Set<String> expected,
            String status,
            String code,
            String message) {
        finishTaskResult(taskId, expected, status, code, message);
    }

    private boolean finishTaskResult(
            String taskId,
            Set<String> expected,
            String status,
            String code,
            String message) {
        return database.transactionResult(transaction -> {
            VideoshotrendertaskRecord task = lockTask(transaction, taskId);
            return task != null && finish(transaction, task, expected, status, code, message);
        });
    }

    private boolean finish(
            DSLContext transaction,
            VideoshotrendertaskRecord task,
            Set<String> expected,
            String status,
            String code,
            String message) {
        if (!expected.contains(task.getStatus())) return false;
        LocalDateTime now = DatabaseTimestamp.now(clock);
        transaction.update(VIDEOSHOTRENDERTASK)
                .set(VIDEOSHOTRENDERTASK.STATUS, status)
                .set(VIDEOSHOTRENDERTASK.LASTERRORCODE, code)
                .set(VIDEOSHOTRENDERTASK.LASTERRORMESSAGE, message)
                .set(VIDEOSHOTRENDERTASK.COMPLETEDAT, now)
                .set(VIDEOSHOTRENDERTASK.NEXTATTEMPTAT, now)
                .set(VIDEOSHOTRENDERTASK.UPDATEDAT, now)
                .where(VIDEOSHOTRENDERTASK.ID.eq(task.getId()))
                .execute();
        return true;
    }

    private static void renderLock(
            DSLContext context, String namespace, String identity, String requestId) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(("video-shot-render\0"
                                    + namespace
                                    + "\0"
                                    + identity
                                    + "\0"
                                    + requestId)
                            .getBytes(StandardCharsets.UTF_8));
            context.fetch(
                    "SELECT pg_advisory_xact_lock(?)",
                    ByteBuffer.wrap(digest, 0, Long.BYTES).getLong());
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }

    private String canonicalHash(Object value) {
        return CommandIdempotency.sha256(
                CommandIdempotency.canonicalJsonBytes(value, json));
    }

    private String canonicalJson(Object value) {
        return new String(
                CommandIdempotency.canonicalJsonBytes(value, json),
                StandardCharsets.UTF_8);
    }

    private static int pollBackoff(int pollCount) {
        return Math.min(5 + Math.max(pollCount - 1, 0) * 2, 30);
    }

    private static String requestId(String value) {
        String normalized = value == null ? "" : value.strip();
        int length = normalized.codePointCount(0, normalized.length());
        if (length < 16 || length > 128) {
            throw new ApiException(422, "VALIDATION_ERROR", "请求标识长度无效");
        }
        return normalized;
    }

    private static ApiException clientRequestReused(String message) {
        return new ApiException(409, "VIDEO_RENDER_CLIENT_REQUEST_REUSED", message);
    }

    private static <T> List<T> list(List<T> value) {
        return value == null ? List.of() : value;
    }
}
