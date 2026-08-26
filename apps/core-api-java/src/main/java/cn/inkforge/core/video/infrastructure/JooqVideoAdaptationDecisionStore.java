package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.VIDEOADAPTATIONDECISIONCOMMAND;
import static cn.inkforge.core.db.generated.Tables.VIDEOADAPTATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOCHAPTERADAPTATIONHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEBOUNDARY;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEPLANVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOT;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTHEAD;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOTPROMPTVISUALREFERENCE;

import cn.inkforge.contracts.api.ConfirmAdaptationPlanRequest;
import cn.inkforge.contracts.api.DiscardAdaptationCandidateRequest;
import cn.inkforge.contracts.api.SaveEpisodePlanRequest;
import cn.inkforge.contracts.api.SaveShotPromptRequest;
import cn.inkforge.contracts.api.SeedanceShotPromptSpec;
import cn.inkforge.contracts.api.ShotPromptSpecBatch;
import cn.inkforge.contracts.api.ShotVisualReferenceSnapshot;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.VideoadaptationdecisioncommandRecord;
import cn.inkforge.core.db.generated.tables.records.VideoadaptationtaskRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeplanversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotpromptheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotpromptversionRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.VideoAdaptationDecisionStore;
import cn.inkforge.core.video.domain.SeedancePromptCompiler;
import cn.inkforge.core.video.domain.VideoAdaptationPlans;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.impl.DSL;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 用户批准、分集和逐镜提示词版本的 jOOQ 事务实现。
 *
 * <p>镜头方案批准会在同一事务中物化 Scene/Beat/Shot、推进不可变版本、切换 Head、标记 Artifact 并保存
 * 幂等决定命令。分集和提示词同样新增版本后以 revision CAS 切换，不修改旧方案，也不把 Agent 候选冒充正式版本。
 */
public final class JooqVideoAdaptationDecisionStore implements VideoAdaptationDecisionStore {

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final JooqVideoVisualCanonRepository visualCanons;
    private final JooqVideoPlanMaterializer plans;

    public JooqVideoAdaptationDecisionStore(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            JooqVideoVisualCanonRepository visualCanons) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.visualCanons = Objects.requireNonNull(visualCanons);
        this.plans = new JooqVideoPlanMaterializer(ids, clock, json);
    }

    @Override
    public String confirmPlan(
            String userId, String adaptationId, ConfirmAdaptationPlanRequest request) {
        String requestHash = canonicalHash(Map.of(
                "adaptationId", adaptationId,
                "expectedArtifactRevision", request.getExpectedArtifactRevision(),
                "expectedAdaptationRevision", request.getExpectedAdaptationRevision(),
                "plan", VideoAdaptationPlans.candidateMap(request.getPlan())));
        return database.transactionResult(transaction -> {
            // 先锁幂等键再读命令，保证并发批准只会有一个请求进入物化阶段。
            transaction.fetch(
                    "SELECT pg_advisory_xact_lock(?)",
                    decisionLockKey(userId, request.getClientRequestId()));
            VideoadaptationdecisioncommandRecord existing = transaction
                    .selectFrom(VIDEOADAPTATIONDECISIONCOMMAND)
                    .where(
                            VIDEOADAPTATIONDECISIONCOMMAND.REQUESTEDBYUSERID.eq(userId),
                            VIDEOADAPTATIONDECISIONCOMMAND.CLIENTREQUESTID.eq(
                                    request.getClientRequestId()))
                    .fetchOne();
            if (existing != null) {
                if (!existing.getRequesthash().equals(requestHash)) {
                    throw new ApiException(
                            409,
                            "VIDEO_ADAPTATION_DECISION_IDEMPOTENCY_CONFLICT",
                            "同一批准请求标识不能绑定不同镜头方案");
                }
                return existing.getAdaptationid();
            }

            var owned = VideoDatabaseAccess.ownedAdaptation(
                    transaction, userId, adaptationId, true);
            var adaptation = owned.adaptation();
            var project = owned.project();
            var head = owned.head();
            if (!Objects.equals(head.getRevision(), request.getExpectedAdaptationRevision())) {
                throw revisionConflict(head.getRevision());
            }
            ReviewartifactRecord artifact = transaction.selectFrom(REVIEWARTIFACT)
                    .where(
                            REVIEWARTIFACT.VIDEOADAPTATIONID.eq(adaptationId),
                            REVIEWARTIFACT.REVISION.eq(request.getExpectedArtifactRevision()))
                    .orderBy(REVIEWARTIFACT.CREATEDAT.desc())
                    .limit(1)
                    .forUpdate()
                    .fetchOne();
            if (artifact == null || artifact.getStatus() != Reviewartifactstatus.awaiting_user) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_REVIEW_NOT_PENDING",
                        "当前没有匹配版本的待确认镜头方案");
            }
            VideoadaptationtaskRecord task = artifact.getVideoadaptationtaskid() == null
                    ? null
                    : transaction.selectFrom(VIDEOADAPTATIONTASK)
                            .where(VIDEOADAPTATIONTASK.ID.eq(artifact.getVideoadaptationtaskid()))
                            .forUpdate()
                            .fetchOne();
            if (task == null
                    || !adaptationId.equals(task.getAdaptationid())
                    || !"completed".equals(task.getStatus())
                    || !"shot_plan".equals(task.getKind())) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_SOURCE_TASK_INVALID",
                        "待确认方案缺少可核验的完成任务");
            }
            if (!Objects.equals(
                    task.getBaseshotplanversionid(), head.getCurrentshotplanversionid())) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_BASE_PLAN_STALE",
                        "正式镜头方案已经变化，请基于当前版本重新生成修订候选");
            }
            try {
                VideoAdaptationPlans.validateAgainstSource(
                        request.getPlan(),
                        adaptationId,
                        adaptation.getSourcetext(),
                        adaptation.getSourcehash());
            } catch (IllegalArgumentException exception) {
                throw new ApiException(
                        422,
                        "VALIDATION_ERROR",
                        exception.getMessage());
            }
            // 正式版本、Artifact 状态、Head 和决定命令必须同事务提交；任一步失败都不能留下“半批准”。
            String planVersionId = plans.materialize(
                    transaction, adaptation, artifact, task, userId, request.getPlan());
            LocalDateTime now = DatabaseTimestamp.now(clock);
            transaction.update(REVIEWARTIFACT)
                    .set(REVIEWARTIFACT.STATUS, Reviewartifactstatus.applied)
                    .set(REVIEWARTIFACT.APPLIEDAT, now)
                    .set(REVIEWARTIFACT.UPDATEDAT, now)
                    .where(REVIEWARTIFACT.ID.eq(artifact.getId()))
                    .execute();
            int nextRevision = head.getRevision() + 1;
            transaction.update(VIDEOCHAPTERADAPTATIONHEAD)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.CURRENTSHOTPLANVERSIONID, planVersionId)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.CURRENTEPISODEPLANVERSIONID, (String) null)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.REVISION, nextRevision)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.UPDATEDAT, now)
                    .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(adaptationId))
                    .execute();
            Map<String, Object> result = Map.of(
                    "adaptationId", adaptationId,
                    "planVersionId", planVersionId,
                    "headRevision", nextRevision);
            transaction.insertInto(VIDEOADAPTATIONDECISIONCOMMAND)
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.ID, ids.next())
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.REQUESTEDBYUSERID, userId)
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.NOVELID, adaptation.getNovelid())
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.PROJECTID, project.getId())
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.ADAPTATIONID, adaptationId)
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.ARTIFACTID, artifact.getId())
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.SOURCETASKID, task.getId())
                    .set(
                            VIDEOADAPTATIONDECISIONCOMMAND.CLIENTREQUESTID,
                            request.getClientRequestId())
                    .set(
                            VIDEOADAPTATIONDECISIONCOMMAND.EXPECTEDARTIFACTREVISION,
                            request.getExpectedArtifactRevision())
                    .set(
                            VIDEOADAPTATIONDECISIONCOMMAND.EXPECTEDADAPTATIONREVISION,
                            request.getExpectedAdaptationRevision())
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.REQUESTHASH, requestHash)
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.DECISION, "approve")
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.STATUS, "succeeded")
                    .set(
                            VIDEOADAPTATIONDECISIONCOMMAND.RESULTJSON,
                            json.writeValueAsString(result))
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.CREATEDAT, now)
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.UPDATEDAT, now)
                    .set(VIDEOADAPTATIONDECISIONCOMMAND.COMPLETEDAT, now)
                    .execute();
            return adaptationId;
        });
    }

    @Override
    public String saveEpisodePlan(
            String userId, String adaptationId, SaveEpisodePlanRequest request) {
        return database.transactionResult(transaction -> {
            var owned = VideoDatabaseAccess.ownedAdaptation(
                    transaction, userId, adaptationId, true);
            var head = owned.head();
            if (!Objects.equals(
                    head.getCurrentshotplanversionid(), request.getShotPlanVersionId())) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_PLAN_CHANGED",
                        "保存分集时正式镜头方案已经变化");
            }
            List<VideoshotRecord> shots = transaction.selectFrom(VIDEOSHOT)
                    .where(VIDEOSHOT.PLANVERSIONID.eq(request.getShotPlanVersionId()))
                    .orderBy(VIDEOSHOT.ORDINAL)
                    .forUpdate()
                    .fetch();
            List<String> boundaries = list(request.getBreakAfterShotIds());
            try {
                VideoAdaptationPlans.validateEpisodeBoundaries(
                        boundaries, shots.stream().map(VideoshotRecord::getId).toList());
            } catch (IllegalArgumentException exception) {
                throw new ApiException(
                        409,
                        "VIDEO_EPISODE_BOUNDARY_INVALID",
                        exception.getMessage());
            }
            String contentHash = canonicalHash(Map.of(
                    "shotPlanVersionId", request.getShotPlanVersionId(),
                    "breakAfterShotIds", boundaries));
            VideoepisodeplanversionRecord current = head.getCurrentepisodeplanversionid() == null
                    ? null
                    : transaction.selectFrom(VIDEOEPISODEPLANVERSION)
                            .where(VIDEOEPISODEPLANVERSION.ID.eq(
                                    head.getCurrentepisodeplanversionid()))
                            .fetchOne();
            if (current != null && contentHash.equals(current.getContenthash())) {
                return adaptationId;
            }
            if (!Objects.equals(head.getRevision(), request.getExpectedAdaptationRevision())) {
                throw revisionConflict(head.getRevision());
            }
            Integer maximum = transaction.select(DSL.coalesce(
                            DSL.max(VIDEOEPISODEPLANVERSION.VERSIONNO), 0))
                    .from(VIDEOEPISODEPLANVERSION)
                    .where(VIDEOEPISODEPLANVERSION.ADAPTATIONID.eq(adaptationId))
                    .fetchOne(0, Integer.class);
            String versionId = ids.next();
            LocalDateTime now = DatabaseTimestamp.now(clock);
            // 分集是镜头方案之上的不可变版本；边界先完整落库，最后才用 revision CAS 推进 Head。
            transaction.insertInto(VIDEOEPISODEPLANVERSION)
                    .set(VIDEOEPISODEPLANVERSION.ID, versionId)
                    .set(VIDEOEPISODEPLANVERSION.ADAPTATIONID, adaptationId)
                    .set(
                            VIDEOEPISODEPLANVERSION.SHOTPLANVERSIONID,
                            request.getShotPlanVersionId())
                    .set(VIDEOEPISODEPLANVERSION.VERSIONNO, (maximum == null ? 0 : maximum) + 1)
                    .set(
                            VIDEOEPISODEPLANVERSION.BASEDONVERSIONID,
                            current == null ? null : current.getId())
                    .set(VIDEOEPISODEPLANVERSION.CREATEDBYUSERID, userId)
                    .set(VIDEOEPISODEPLANVERSION.CONTENTHASH, contentHash)
                    .set(VIDEOEPISODEPLANVERSION.CREATEDAT, now)
                    .execute();
            for (int index = 0; index < boundaries.size(); index++) {
                transaction.insertInto(VIDEOEPISODEBOUNDARY)
                        .set(VIDEOEPISODEBOUNDARY.EPISODEPLANVERSIONID, versionId)
                        .set(
                                VIDEOEPISODEBOUNDARY.SHOTPLANVERSIONID,
                                request.getShotPlanVersionId())
                        .set(VIDEOEPISODEBOUNDARY.AFTERSHOTID, boundaries.get(index))
                        .set(VIDEOEPISODEBOUNDARY.ORDINAL, index + 1)
                        .execute();
            }
            transaction.update(VIDEOCHAPTERADAPTATIONHEAD)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.CURRENTEPISODEPLANVERSIONID, versionId)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.REVISION, head.getRevision() + 1)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.UPDATEDAT, now)
                    .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(adaptationId))
                    .execute();
            return adaptationId;
        });
    }

    @Override
    public String discardCandidate(
            String userId,
            String adaptationId,
            DiscardAdaptationCandidateRequest request) {
        return database.transactionResult(transaction -> {
            var owned = VideoDatabaseAccess.ownedAdaptation(
                    transaction, userId, adaptationId, true);
            var head = owned.head();
            if (!Objects.equals(head.getRevision(), request.getExpectedAdaptationRevision())) {
                throw revisionConflict(head.getRevision());
            }
            ReviewartifactRecord artifact = transaction.selectFrom(REVIEWARTIFACT)
                    .where(
                            REVIEWARTIFACT.VIDEOADAPTATIONID.eq(adaptationId),
                            REVIEWARTIFACT.STATUS.eq(Reviewartifactstatus.awaiting_user),
                            REVIEWARTIFACT.REVISION.eq(request.getExpectedArtifactRevision()))
                    .orderBy(REVIEWARTIFACT.CREATEDAT.desc())
                    .limit(1)
                    .forUpdate()
                    .fetchOne();
            if (artifact == null) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_REVIEW_NOT_PENDING",
                        "当前没有匹配版本的待审镜头方案");
            }
            transaction.deleteFrom(REVIEWARTIFACT)
                    .where(REVIEWARTIFACT.ID.eq(artifact.getId()))
                    .execute();
            transaction.update(VIDEOCHAPTERADAPTATIONHEAD)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.REVISION, head.getRevision() + 1)
                    .set(VIDEOCHAPTERADAPTATIONHEAD.UPDATEDAT, DatabaseTimestamp.now(clock))
                    .where(VIDEOCHAPTERADAPTATIONHEAD.ADAPTATIONID.eq(adaptationId))
                    .execute();
            return adaptationId;
        });
    }

    @Override
    public String savePrompt(
            String userId,
            String adaptationId,
            String shotId,
            SaveShotPromptRequest request) {
        return database.transactionResult(transaction -> {
            var owned = VideoDatabaseAccess.ownedAdaptation(
                    transaction, userId, adaptationId, true);
            var adaptation = owned.adaptation();
            var project = owned.project();
            var head = owned.head();
            if (head.getCurrentshotplanversionid() == null) {
                throw new ApiException(
                        409,
                        "VIDEO_ADAPTATION_PLAN_REQUIRED",
                        "请先确认电影化镜头方案");
            }
            VideoshotRecord shot = transaction.selectFrom(VIDEOSHOT)
                    .where(
                            VIDEOSHOT.ID.eq(shotId),
                            VIDEOSHOT.PLANVERSIONID.eq(head.getCurrentshotplanversionid()))
                    .forUpdate()
                    .fetchOne();
            VideoshotpromptheadRecord promptHead = transaction
                    .selectFrom(VIDEOSHOTPROMPTHEAD)
                    .where(VIDEOSHOTPROMPTHEAD.SHOTID.eq(shotId))
                    .forUpdate()
                    .fetchOne();
            if (shot == null || promptHead == null) {
                throw new ApiException(
                        404,
                        "VIDEO_ADAPTATION_SHOT_NOT_FOUND",
                        "正式镜头不存在");
            }
            VideoshotpromptversionRecord current = promptHead.getCurrentversionid() == null
                    ? null
                    : transaction.selectFrom(VIDEOSHOTPROMPTVERSION)
                            .where(VIDEOSHOTPROMPTVERSION.ID.eq(
                                    promptHead.getCurrentversionid()))
                            .fetchOne();
            String generatedText = current == null ? null : current.getGeneratedtext();
            String sourceTaskId = current == null ? null : current.getSourcetaskid();
            List<ShotVisualReferenceSnapshot> references = visualCanons
                    .shotReferences(transaction, List.of(shot))
                    .getFirst()
                    .getReferences();
            String candidateTaskId = nullable(request.getCandidateTaskId());
            if (candidateTaskId != null) {
                PromptCandidate candidate = promptCandidate(
                        transaction,
                        candidateTaskId,
                        adaptationId,
                        head.getCurrentshotplanversionid(),
                        shot,
                        project.getTargetaspectratio());
                generatedText = candidate.compiledPrompt();
                references = candidate.references();
                sourceTaskId = candidateTaskId;
            }
            // 保存时同时冻结候选原文、用户编辑稿和视觉参考版本，之后 CanonHead 变化不改写历史提示词。
            String contentHash = promptContentHash(
                    shotId, generatedText, request.getCurrentPrompt(), references);
            if (current != null && contentHash.equals(current.getContenthash())) {
                return adaptationId;
            }
            if (!Objects.equals(promptHead.getRevision(), request.getExpectedPromptRevision())) {
                throw new ApiException(
                        409,
                        "VIDEO_SHOT_PROMPT_REVISION_CONFLICT",
                        "镜头提示词版本已经变化",
                        Map.of("currentRevision", promptHead.getRevision()));
            }
            Integer maximum = transaction.select(DSL.coalesce(
                            DSL.max(VIDEOSHOTPROMPTVERSION.VERSIONNO), 0))
                    .from(VIDEOSHOTPROMPTVERSION)
                    .where(VIDEOSHOTPROMPTVERSION.SHOTID.eq(shotId))
                    .fetchOne(0, Integer.class);
            String versionId = ids.next();
            LocalDateTime now = DatabaseTimestamp.now(clock);
            // PromptVersion 与其参考绑定先完整写入，最后推进 PromptHead；旧版本始终只读可追溯。
            transaction.insertInto(VIDEOSHOTPROMPTVERSION)
                    .set(VIDEOSHOTPROMPTVERSION.ID, versionId)
                    .set(VIDEOSHOTPROMPTVERSION.SHOTID, shotId)
                    .set(
                            VIDEOSHOTPROMPTVERSION.SHOTPLANVERSIONID,
                            shot.getPlanversionid())
                    .set(VIDEOSHOTPROMPTVERSION.VERSIONNO, (maximum == null ? 0 : maximum) + 1)
                    .set(
                            VIDEOSHOTPROMPTVERSION.BASEDONVERSIONID,
                            current == null ? null : current.getId())
                    .set(VIDEOSHOTPROMPTVERSION.GENERATEDTEXT, generatedText)
                    .set(VIDEOSHOTPROMPTVERSION.CURRENTTEXT, request.getCurrentPrompt())
                    .set(VIDEOSHOTPROMPTVERSION.SOURCETASKID, sourceTaskId)
                    .set(VIDEOSHOTPROMPTVERSION.CREATEDBYUSERID, userId)
                    .set(VIDEOSHOTPROMPTVERSION.CONTENTHASH, contentHash)
                    .set(VIDEOSHOTPROMPTVERSION.CREATEDAT, now)
                    .execute();
            for (int index = 0; index < references.size(); index++) {
                ShotVisualReferenceSnapshot reference = references.get(index);
                transaction.insertInto(VIDEOSHOTPROMPTVISUALREFERENCE)
                        .set(VIDEOSHOTPROMPTVISUALREFERENCE.PROMPTVERSIONID, versionId)
                        .set(VIDEOSHOTPROMPTVISUALREFERENCE.SHOTID, shotId)
                        .set(
                                VIDEOSHOTPROMPTVISUALREFERENCE.SHOTPLANVERSIONID,
                                shot.getPlanversionid())
                        .set(VIDEOSHOTPROMPTVISUALREFERENCE.ADAPTATIONID, adaptationId)
                        .set(
                                VIDEOSHOTPROMPTVISUALREFERENCE.PROJECTID,
                                adaptation.getProjectid())
                        .set(
                                VIDEOSHOTPROMPTVISUALREFERENCE.NOVELID,
                                adaptation.getNovelid())
                        .set(VIDEOSHOTPROMPTVISUALREFERENCE.ORDINAL, index + 1)
                        .set(
                                VIDEOSHOTPROMPTVISUALREFERENCE.CANONVERSIONID,
                                reference.getCanonVersionId())
                        .set(
                                VIDEOSHOTPROMPTVISUALREFERENCE.STRENGTH,
                                reference.getStrength())
                        .execute();
            }
            transaction.update(VIDEOSHOTPROMPTHEAD)
                    .set(VIDEOSHOTPROMPTHEAD.CURRENTVERSIONID, versionId)
                    .set(VIDEOSHOTPROMPTHEAD.REVISION, promptHead.getRevision() + 1)
                    .set(VIDEOSHOTPROMPTHEAD.UPDATEDAT, now)
                    .where(VIDEOSHOTPROMPTHEAD.SHOTID.eq(shotId))
                    .execute();
            return adaptationId;
        });
    }

    private PromptCandidate promptCandidate(
            DSLContext transaction,
            String taskId,
            String adaptationId,
            String planVersionId,
            VideoshotRecord shot,
            String ratio) {
        VideoadaptationtaskRecord task = transaction.selectFrom(VIDEOADAPTATIONTASK)
                .where(VIDEOADAPTATIONTASK.ID.eq(taskId))
                .forUpdate()
                .fetchOne();
        if (task == null
                || !adaptationId.equals(task.getAdaptationid())
                || !planVersionId.equals(task.getBaseshotplanversionid())
                || !"shot_prompt".equals(task.getKind())
                || !"completed".equals(task.getStatus())
                || task.getResultjson() == null) {
            throw promptCandidateInvalid();
        }
        try {
            JsonNode result = json.readTree(task.getResultjson());
            ShotPromptSpecBatch batch =
                    json.convertValue(result.get("promptBatch"), ShotPromptSpecBatch.class);
            if (!"shot_prompt_spec_batch_v2".equals(batch.getSchemaVersion())) {
                throw new IllegalArgumentException();
            }
            var matching = batch.getPrompts().stream()
                    .filter(item -> shot.getShotkey().equals(item.getShotKey()))
                    .toList();
            if (matching.size() != 1) throw new IllegalArgumentException();
            VideoAdaptationTaskPayload payload =
                    VideoAdaptationTaskPayload.parse(json, task.getRequestjson());
            if (!payload.isPrompt()) throw new IllegalArgumentException();
            SeedanceShotPromptSpec specification = matching.getFirst().getSpec();
            return new PromptCandidate(
                    SeedancePromptCompiler.compile(
                            specification, ratio, shot.getTimelinedurationms()),
                    payload.visualReferencesByShot()
                            .getOrDefault(shot.getShotkey(), List.of()));
        } catch (RuntimeException exception) {
            throw promptCandidateInvalid();
        }
    }

    private String promptContentHash(
            String shotId,
            String generatedText,
            String currentText,
            List<ShotVisualReferenceSnapshot> references) {
        LinkedHashMap<String, Object> value = new LinkedHashMap<>();
        value.put("shotId", shotId);
        value.put("generatedText", generatedText);
        value.put("currentText", currentText);
        value.put("visualReferences", references.stream()
                .map(reference -> Map.<String, Object>of(
                        "canonVersionId", reference.getCanonVersionId(),
                        "strength", reference.getStrength()))
                .toList());
        return canonicalHash(value);
    }

    private String canonicalHash(Object value) {
        return CommandIdempotency.sha256(
                CommandIdempotency.canonicalJsonBytes(value, json));
    }

    private static long decisionLockKey(String userId, String requestId) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(("video-adaptation-decision:" + userId + ":" + requestId)
                            .getBytes(StandardCharsets.UTF_8));
            return ByteBuffer.wrap(digest, 0, Long.BYTES).getLong();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }

    private static ApiException revisionConflict(int currentRevision) {
        return new ApiException(
                409,
                "VIDEO_ADAPTATION_REVISION_CONFLICT",
                "章节影视化版本已经变化，请刷新后重试",
                Map.of("currentRevision", currentRevision));
    }

    private static ApiException promptCandidateInvalid() {
        return new ApiException(
                409,
                "VIDEO_SHOT_PROMPT_CANDIDATE_INVALID",
                "提示词候选内容损坏或不包含当前镜头");
    }

    private static String nullable(JsonNullable<String> value) {
        return value != null && value.isPresent() ? value.get() : null;
    }

    private static <T> List<T> list(List<T> value) {
        return value == null ? List.of() : List.copyOf(value);
    }

    private record PromptCandidate(
            String compiledPrompt, List<ShotVisualReferenceSnapshot> references) {}
}
