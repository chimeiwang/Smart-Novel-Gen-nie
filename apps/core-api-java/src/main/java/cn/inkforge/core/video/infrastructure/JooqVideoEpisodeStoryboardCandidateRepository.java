package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.VideoEpisodeStoryboardCandidateRepository;
import cn.inkforge.core.workflows.application.WorkflowVideoEpisodeStoryboardCompletion;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 分镜 V2 候选与工作稿 CAS。
 *
 * <p>Workflow 完成只插入 awaiting_user Artifact；采用命令才分配临时镜头身份并更新工作稿，正式分镜和
 * 制作基线始终由后续独立作者命令创建。
 */
final class JooqVideoEpisodeStoryboardCandidateRepository
        implements VideoEpisodeStoryboardCandidateRepository,
                WorkflowVideoEpisodeStoryboardCompletion {
    private static final Set<String> OPERATIONS =
            Set.of("episode_storyboard_generate", "episode_storyboard_revise");
    private static final Set<String> FRAMINGS = Set.of(
            "extreme_wide", "wide", "medium", "close_up", "detail", "over_shoulder", "pov");
    private static final Set<String> CAMERA_MOVEMENTS = Set.of(
            "static", "pan", "tilt", "dolly", "truck", "crane", "handheld", "orbit", "zoom");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    JooqVideoEpisodeStoryboardCandidateRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public boolean targetExists(DSLContext tx, String runId) {
        return tx.fetchOne(
                        """
                        SELECT episode.id
                        FROM public."WorkflowRun" run
                        JOIN public."VideoEpisode" episode
                          ON episode.id=run."targetId" AND episode."novelId"=run."novelId"
                        JOIN public."Novel" novel
                          ON novel.id=episode."novelId" AND novel."userId"=run."userId"
                        WHERE run.id=? AND run."engineVersion"=2 AND run.workflow='video'
                          AND run.operation IN ('episode_storyboard_generate','episode_storyboard_revise')
                          AND run."sourceType"='video_episode_storyboard'
                          AND run."targetType"='video_episode_storyboard'
                          AND run."sourceId"=run."targetId"
                          AND episode."archivedAt" IS NULL
                        """,
                        runId)
                != null;
    }

    @Override
    public String completeCandidate(
            DSLContext tx,
            String runId,
            Map<String, Object> document,
            Map<String, Object> review) {
        if (!targetExists(tx, runId)) {
            throw notFound("VIDEO_EPISODE_NOT_FOUND", "分镜候选目标集已不存在");
        }
        Record run = tx.fetchOne(
                """
                SELECT run."targetId",run."userId",run.operation,item."contentJson"
                FROM public."WorkflowRun" run
                JOIN public."WorkflowEvidenceItem" item
                  ON item."bundleId"=run."currentEvidenceBundleId"
                WHERE run.id=? AND item."resourceType"='video_episode_storyboard_context'
                  AND item."resourceId"=run."targetId"
                """,
                runId);
        if (run == null || !OPERATIONS.contains(run.get("operation", String.class))) {
            throw invalid("VIDEO_STORYBOARD_EVIDENCE_MISSING", "分镜候选缺少冻结输入证据");
        }
        String episodeId = run.get("targetId", String.class);
        Record episode = ownedEpisode(tx, run.get("userId", String.class), episodeId, true);
        Record old = tx.fetchOne(
                """
                SELECT id FROM public."ReviewArtifact"
                WHERE "workflowRunId"=? AND "videoEpisodeId"=?
                  AND kind::text='video_episode_storyboard'
                """,
                runId,
                episodeId);
        if (old != null) return old.get("id", String.class);

        ObjectNode context = readObject(run, "contentJson", "分镜冻结证据");
        ObjectNode payload = object(
                "applyTarget", "video_episode_storyboard_draft",
                "episodeId", episodeId,
                "expectedDraftRevision", context.path("draftRevision"),
                "scriptVersionId", context.path("scriptVersionId"),
                "baseStoryboardVersionId", context.path("baseStoryboardVersionId"),
                "document", document,
                "review", review,
                "reviewFindings", review.getOrDefault("findings", List.of()));
        String artifactId = ids.next();
        LocalDateTime now = now();
        tx.execute(
                """
                INSERT INTO public."ReviewArtifact" (
                  id,"novelId","videoEpisodeId","workflowRunId","artifactKey",kind,status,
                  title,"payloadJson",revision,"createdAt","updatedAt"
                ) VALUES (?,?,?,?,?,'video_episode_storyboard','awaiting_user',?,?,1,?,?)
                """,
                artifactId,
                episode.get("novelId"),
                episodeId,
                runId,
                "video-storyboard-candidate:" + episodeId,
                "分镜候选",
                payload.toString(),
                now,
                now);
        tx.execute(
                """
                INSERT INTO public."ReviewArtifactRevision"
                  (id,"artifactId",revision,"payloadJson","createdAt")
                VALUES (?,?,1,?,?)
                """,
                ids.next(), artifactId, payload.toString(), now);
        return artifactId;
    }

    @Override
    public ObjectNode get(String userId, String episodeId, String artifactId) {
        requireIdentity(userId, "用户 ID");
        requireIdentity(episodeId, "分集 ID");
        requireIdentity(artifactId, "候选 ID");
        return database.transactionResult(tx -> {
            ownedEpisode(tx, userId, episodeId, false);
            return candidate(requireArtifact(tx, episodeId, artifactId, false));
        });
    }

    @Override
    public ObjectNode adopt(
            String userId, String episodeId, String artifactId, JsonNode request) {
        requireIdentity(userId, "用户 ID");
        requireIdentity(episodeId, "分集 ID");
        requireIdentity(artifactId, "候选 ID");
        if (request == null || !request.isObject()) {
            throw invalid("VIDEO_STORYBOARD_ADOPT_INPUT_INVALID", "采用请求必须是对象");
        }
        String clientRequestId = text(request, "clientRequestId");
        if (clientRequestId.length() < 16 || clientRequestId.length() > 128) {
            throw invalid(
                    "VIDEO_STORYBOARD_CLIENT_REQUEST_ID_INVALID",
                    "clientRequestId 长度必须为 16 至 128 个字符");
        }
        int expectedArtifactRevision = request.path("expectedArtifactRevision").asInt(-1);
        int expectedDraftRevision = request.path("expectedDraftRevision").asInt(-1);
        if (expectedArtifactRevision < 1 || expectedDraftRevision < 1) {
            throw invalid("VIDEO_STORYBOARD_ADOPT_REVISION_INVALID", "采用 revision 必须为正数");
        }
        ObjectNode requestBody = (ObjectNode) request.deepCopy();
        requestBody.put("artifactId", artifactId);
        String requestHash = CommandIdempotency.requestFingerprint(
                "video_episode_storyboard_candidate.adopt",
                Map.of("episodeId", episodeId, "artifactId", artifactId),
                toMap(requestBody),
                json);

        return database.transactionResult(tx -> {
            // 锁序与其他 V2/视频命令一致：共用幂等锁、视频命令锁、Novel/Project/Episode、Artifact、Draft。
            tx.fetchOne(
                    "SELECT pg_advisory_xact_lock(?)",
                    CommandIdempotency.advisoryLockKey(userId, clientRequestId));
            tx.fetchOne(
                    "SELECT pg_advisory_xact_lock(hashtextextended(?,0))",
                    "video-episode-command:" + userId + ":" + clientRequestId);
            Record previous = tx.fetchOne(
                    """
                    SELECT * FROM public."VideoEpisodeCommand"
                    WHERE "actorUserId"=? AND "clientRequestId"=? FOR UPDATE
                    """,
                    userId, clientRequestId);
            if (previous != null) {
                if (!"episode.storyboard.adopt".equals(previous.get("operation", String.class))
                        || !episodeId.equals(previous.get("episodeId", String.class))
                        || !requestHash.equals(previous.get("requestHash", String.class))) {
                    throw conflict(
                            "VIDEO_EPISODE_CLIENT_REQUEST_REUSED",
                            "clientRequestId 已用于不同的分集命令");
                }
                return readObject(previous, "resultJson", "分镜采用命令回执");
            }

            Record episode = ownedEpisode(tx, userId, episodeId, true);
            Record artifact = requireArtifact(tx, episodeId, artifactId, true);
            if (artifact.get("revision", Integer.class) != expectedArtifactRevision) {
                throw conflict(
                        "VIDEO_STORYBOARD_ARTIFACT_REVISION_CONFLICT",
                        "分镜候选 revision 已变化，请重新读取");
            }
            if (!"awaiting_user".equals(artifact.get("status", String.class))) {
                throw conflict("VIDEO_STORYBOARD_ARTIFACT_NOT_PENDING", "分镜候选已经处理");
            }
            ObjectNode payload = readObject(artifact, "payloadJson", "分镜候选");
            if (!"video_episode_storyboard_draft".equals(payload.path("applyTarget").asText())
                    || !episodeId.equals(payload.path("episodeId").asText())) {
                throw invalid("VIDEO_STORYBOARD_ARTIFACT_TARGET_INVALID", "候选不属于当前分镜工作稿");
            }
            Record draft = tx.fetchOne(
                    "SELECT * FROM public.\"VideoStoryboardDraft\" WHERE \"episodeId\"=? FOR UPDATE",
                    episodeId);
            if (draft == null) {
                throw conflict("VIDEO_STORYBOARD_DRAFT_MISSING", "分镜工作稿不存在");
            }
            int currentRevision = draft.get("revision", Integer.class);
            if (currentRevision != expectedDraftRevision
                    || currentRevision != payload.path("expectedDraftRevision").asInt(-1)) {
                throw new ApiException(
                        409,
                        "VIDEO_STORYBOARD_DRAFT_REVISION_CONFLICT",
                        "分镜工作稿已变化，请保留当前输入并重新发起修订",
                        Map.of("currentRevision", currentRevision));
            }
            String scriptVersionId = payload.path("scriptVersionId").asText();
            if (scriptVersionId.isBlank()
                    || !scriptVersionId.equals(draft.get("scriptVersionId", String.class))) {
                throw conflict(
                        "VIDEO_STORYBOARD_SCRIPT_VERSION_CONFLICT",
                        "候选依据的正式剧本已经变化");
            }
            String baseVersionId = nullableText(payload.get("baseStoryboardVersionId"));
            if (!Objects.equals(
                    baseVersionId, draft.get("basedOnStoryboardVersionId", String.class))) {
                throw conflict(
                        "VIDEO_STORYBOARD_BASE_VERSION_CONFLICT",
                        "候选依据的基础分镜版本已经变化");
            }
            ObjectNode currentDocument = readObject(draft, "documentJson", "当前分镜工作稿");
            ObjectNode adopted = normalizeCandidate(
                    tx,
                    episode,
                    userId,
                    scriptVersionId,
                    payload.path("document"),
                    currentDocument);
            Map<String, String> mappings = readMappings(adopted);
            LocalDateTime now = now();
            tx.execute(
                    """
                    UPDATE public."VideoStoryboardDraft"
                    SET "documentJson"=?,"contentHash"=?,revision=revision+1,"updatedAt"=?
                    WHERE "episodeId"=?
                    """,
                    adopted.toString(), hash(adopted), now, episodeId);
            tx.execute(
                    """
                    UPDATE public."ReviewArtifact"
                    SET status='applied',"appliedAt"=?,"updatedAt"=? WHERE id=?
                    """,
                    now, now, artifactId);
            ObjectNode response = draftResponse(
                    episodeId,
                    currentRevision + 1,
                    scriptVersionId,
                    baseVersionId,
                    adopted,
                    mappings,
                    now);
            tx.execute(
                    """
                    INSERT INTO public."VideoEpisodeCommand" (
                      id,"actorUserId","clientRequestId","projectId","novelId","episodeId",
                      operation,"requestHash","resultJson"
                    ) VALUES (?,?,?,?,?,?,'episode.storyboard.adopt',?,?)
                    """,
                    ids.next(),
                    userId,
                    clientRequestId,
                    episode.get("projectId"),
                    episode.get("novelId"),
                    episodeId,
                    requestHash,
                    response.toString());
            return response;
        });
    }

    private ObjectNode normalizeCandidate(
            DSLContext tx,
            Record episode,
            String userId,
            String scriptVersionId,
            JsonNode raw,
            ObjectNode current) {
        if (!(raw instanceof ObjectNode document)
                || !"video-episode-storyboard/1.0".equals(document.path("schemaVersion").asText())
                || !document.path("shots").isArray()
                || document.path("shots").size() > 300) {
            throw invalid("VIDEO_STORYBOARD_DOCUMENT_INVALID", "候选分镜文档无效");
        }
        Record script = tx.fetchOne(
                """
                SELECT "documentJson" FROM public."VideoEpisodeScriptVersion"
                WHERE id=? AND "episodeId"=? AND "projectId"=?
                """,
                scriptVersionId, episode.get("id"), episode.get("projectId"));
        if (script == null) {
            throw conflict("VIDEO_STORYBOARD_SCRIPT_VERSION_CONFLICT", "候选正式剧本版本不存在");
        }
        Map<String, Set<String>> scriptNodes = scriptNodes(
                readObject(script, "documentJson", "候选正式剧本"));
        Set<String> permitted = new HashSet<>();
        for (JsonNode shot : current.path("shots")) {
            String id = text(shot, "id");
            permitted.add(id);
        }
        Set<String> used = new HashSet<>();
        Set<String> tempKeys = new HashSet<>();
        Set<String> replacementTargets = new HashSet<>();
        Map<String, String> mappings = new LinkedHashMap<>();
        ObjectNode result = (ObjectNode) document.deepCopy();
        for (JsonNode rawShot : result.path("shots")) {
            if (!(rawShot instanceof ObjectNode shot)) {
                throw invalid("VIDEO_STORYBOARD_SHOT_INVALID", "候选镜头必须是对象");
            }
            String id = nullableText(shot.get("id"));
            String tempKey = nullableText(shot.get("tempKey"));
            if ((id == null) == (tempKey == null)) {
                throw invalid("VIDEO_STORYBOARD_SHOT_ID_INVALID", "候选镜头身份无效");
            }
            if (id != null) {
                if (!permitted.contains(id)) {
                    throw invalid("VIDEO_STORYBOARD_SHOT_ID_INVALID", "候选伪造稳定镜头身份");
                }
                ArrayNode recorded = lineage(tx, id);
                if (!recorded.equals(shot.path("lineage"))) {
                    throw invalid("VIDEO_STORYBOARD_LINEAGE_INVALID", "稳定镜头沿袭事实已变化");
                }
            } else {
                if (!tempKeys.add(tempKey)) {
                    throw invalid("VIDEO_STORYBOARD_SHOT_ID_DUPLICATE", "候选临时镜头身份重复");
                }
                List<Lineage> lineage = validateLineage(shot.path("lineage"), permitted);
                id = ids.next();
                tx.execute(
                        """
                        INSERT INTO public."VideoEpisodeShot"
                          (id,"episodeId","projectId","createdByUserId","createdAt")
                        VALUES (?,?,?,?,?)
                        """,
                        id,
                        episode.get("id"),
                        episode.get("projectId"),
                        userId,
                        now());
                int ordinal = 0;
                for (Lineage item : lineage) {
                    tx.execute(
                            """
                            INSERT INTO public."VideoShotLineage"
                              ("childShotId","sourceShotId","episodeId",ordinal,relation)
                            VALUES (?,?,?,?,?)
                            """,
                            id,
                            item.sourceShotId(),
                            episode.get("id"),
                            ++ordinal,
                            item.relation());
                    if ("replacement".equals(item.relation())
                            && !replacementTargets.add(item.sourceShotId())) {
                        throw invalid(
                                "VIDEO_STORYBOARD_LINEAGE_INVALID",
                                "同一候选不能重复替换一个稳定镜头");
                    }
                }
                mappings.put(tempKey, id);
                shot.put("id", id);
                shot.putNull("tempKey");
            }
            if (!used.add(id)) {
                throw invalid("VIDEO_STORYBOARD_SHOT_ID_DUPLICATE", "候选镜头身份重复");
            }
            validateShot(tx, episode, shot, scriptNodes);
        }
        if (used.stream().anyMatch(replacementTargets::contains)) {
            throw invalid(
                    "VIDEO_STORYBOARD_LINEAGE_INVALID",
                    "替换镜头与被替换镜头不能同时留在采用后的工作稿");
        }
        result.set("shotIdMappings", json.valueToTree(mappings));
        return result;
    }

    private void validateShot(
            DSLContext tx,
            Record episode,
            ObjectNode shot,
            Map<String, Set<String>> scriptNodes) {
        Set<String> allowedLines = scriptNodes.get(text(shot, "scriptSceneId"));
        JsonNode lineIds = shot.path("scriptLineIds");
        if (allowedLines == null || !lineIds.isArray() || lineIds.size() > 100) {
            throw invalid("VIDEO_STORYBOARD_SCRIPT_TARGET_INVALID", "候选镜头剧本范围无效");
        }
        Set<String> seen = new HashSet<>();
        for (JsonNode line : lineIds) {
            String id = textValue(line, "台词 ID");
            if (!seen.add(id) || !allowedLines.contains(id)) {
                throw invalid(
                        "VIDEO_STORYBOARD_SCRIPT_TARGET_INVALID",
                        "候选镜头引用的台词不属于指定场次");
            }
        }
        text(shot, "title");
        text(shot, "action");
        if (!FRAMINGS.contains(shot.path("framing").asText())
                || !CAMERA_MOVEMENTS.contains(shot.path("cameraMovement").asText())) {
            throw invalid("VIDEO_STORYBOARD_SHOT_INVALID", "候选镜头景别或机位运动无效");
        }
        JsonNode intent = shot.path("productionIntent");
        int durationMs = shot.path("durationMs").asInt(-1);
        if (!(intent instanceof ObjectNode production)
                || durationMs < 4_000
                || durationMs > 12_000
                || durationMs != production.path("durationSeconds").asInt(-1) * 1_000) {
            throw invalid("VIDEO_STORYBOARD_DURATION_INVALID", "候选镜头时长无效");
        }
        if (!"seedance".equals(production.path("provider").asText())
                || !"reference".equals(production.path("generationMode").asText())
                || !"simulated".equals(production.path("executionMode").asText())
                || production.path("feeConfirmed").asBoolean(true)
                || !"720p".equals(production.path("resolution").asText())
                || !"mp4".equals(production.path("outputFormat").asText())
                || !production.path("generateAudio").isBoolean()
                || !production.path("watermark").isBoolean()
                || text(production, "model").length() > 200
                || text(production, "prompt").length() > 2_500) {
            throw invalid(
                    "VIDEO_STORYBOARD_INTENT_INVALID",
                    "候选只能保存冻结的模拟 Seedance 制作意图");
        }
        JsonNode references = production.path("references");
        if (!references.isArray() || references.isEmpty() || references.size() > 20) {
            throw invalid("VIDEO_STORYBOARD_REFERENCE_INVALID", "候选镜头参考数量无效");
        }
        Set<String> versions = new HashSet<>();
        int ordinal = 0;
        for (JsonNode reference : references) {
            ordinal++;
            String versionId = text(reference, "canonVersionId");
            if (!versions.add(versionId) || reference.path("ordinal").asInt(-1) != ordinal) {
                throw invalid("VIDEO_STORYBOARD_REFERENCE_INVALID", "候选视觉参考顺序或身份无效");
            }
            Record frozen = tx.fetchOne(
                    """
                    SELECT version."contentHash",version."assetId",asset.sha256,
                           asset."mimeType",asset.duty,asset."rightsStatus",asset."lockedAt"
                    FROM public."VideoVisualCanonVersion" version
                    JOIN public."VideoAsset" asset
                      ON asset.id=version."assetId" AND asset."projectId"=version."projectId"
                    WHERE version.id=? AND version."projectId"=?
                    """,
                    versionId, episode.get("projectId"));
            if (frozen == null
                    || !"confirmed".equals(frozen.get("rightsStatus", String.class))
                    || frozen.get("lockedAt") == null
                    || !Objects.equals(
                            frozen.get("contentHash", String.class),
                            reference.path("canonContentHash").asText())
                    || !Objects.equals(
                            frozen.get("assetId", String.class), reference.path("assetId").asText())
                    || !Objects.equals(
                            frozen.get("sha256", String.class), reference.path("sha256").asText())
                    || !Objects.equals(
                            frozen.get("mimeType", String.class), reference.path("mimeType").asText())
                    || !Objects.equals(
                            frozen.get("duty", String.class), reference.path("duty").asText())
                    || reference.path("strength").asInt(-1) < 1
                    || reference.path("strength").asInt(-1) > 100) {
                throw conflict(
                        "VIDEO_STORYBOARD_REFERENCE_CHANGED",
                        "候选视觉参考事实已变化或不再满足权利门禁");
            }
        }
    }

    private Record ownedEpisode(
            DSLContext tx, String userId, String episodeId, boolean lock) {
        Record identity = tx.fetchOne(
                "SELECT \"projectId\" FROM public.\"VideoEpisode\" WHERE id=? AND \"archivedAt\" IS NULL",
                episodeId);
        if (identity == null) throw notFound("VIDEO_EPISODE_NOT_FOUND", "分集不存在");
        String projectId = identity.get("projectId", String.class);
        var project = VideoDatabaseAccess.ownedProject(tx, userId, projectId, lock);
        VideoDatabaseAccess.requireLongSerial(tx, project.getNovelid(), lock);
        String sql = "SELECT * FROM public.\"VideoEpisode\""
                + " WHERE id=? AND \"projectId\"=? AND \"archivedAt\" IS NULL"
                + (lock ? " FOR UPDATE" : "");
        Record episode = tx.fetchOne(sql, episodeId, projectId);
        if (episode == null) throw notFound("VIDEO_EPISODE_NOT_FOUND", "分集不存在");
        return episode;
    }

    private Record requireArtifact(
            DSLContext tx, String episodeId, String artifactId, boolean lock) {
        Record artifact = tx.fetchOne(
                "SELECT * FROM public.\"ReviewArtifact\" WHERE id=? AND \"videoEpisodeId\"=?"
                        + " AND kind::text='video_episode_storyboard' AND \"workflowRunId\" IS NOT NULL"
                        + (lock ? " FOR UPDATE" : ""),
                artifactId,
                episodeId);
        if (artifact == null) {
            throw notFound("VIDEO_STORYBOARD_CANDIDATE_NOT_FOUND", "分镜候选不存在");
        }
        return artifact;
    }

    private ObjectNode candidate(Record artifact) {
        ObjectNode payload = readObject(artifact, "payloadJson", "分镜候选");
        JsonNode review = payload.path("review");
        return object(
                "artifactId", artifact.get("id"),
                "workflowRunId", artifact.get("workflowRunId"),
                "episodeId", artifact.get("videoEpisodeId"),
                "revision", artifact.get("revision"),
                "status", artifact.get("status", String.class),
                "title", artifact.get("title", String.class),
                "summary", review.isObject() ? review.path("summary").asText(null) : null,
                "expectedDraftRevision", payload.path("expectedDraftRevision"),
                "scriptVersionId", payload.path("scriptVersionId"),
                "baseStoryboardVersionId", payload.path("baseStoryboardVersionId"),
                "document", payload.path("document"),
                "reviewFindings", payload.path("reviewFindings"),
                "review", review.isObject() ? review : null,
                "createdAt", DatabaseTimestamp.api(artifact.get("createdAt", LocalDateTime.class)));
    }

    private ObjectNode draftResponse(
            String episodeId,
            int revision,
            String scriptVersionId,
            String baseVersionId,
            ObjectNode adopted,
            Map<String, String> mappings,
            LocalDateTime updatedAt) {
        ObjectNode document = (ObjectNode) adopted.deepCopy();
        document.remove("shotIdMappings");
        return object(
                "episodeId", episodeId,
                "revision", revision,
                "scriptVersionId", scriptVersionId,
                "baseStoryboardVersionId", baseVersionId,
                "document", document,
                "shotIdMappings", mappings,
                "updatedAt", DatabaseTimestamp.api(updatedAt));
    }

    private Map<String, String> readMappings(ObjectNode adopted) {
        JsonNode value = adopted.path("shotIdMappings");
        Map<String, String> result = new LinkedHashMap<>();
        if (value.isObject()) {
            value.properties().forEach(entry -> result.put(entry.getKey(), entry.getValue().asText()));
        }
        adopted.remove("shotIdMappings");
        return Map.copyOf(result);
    }

    private List<Lineage> validateLineage(JsonNode raw, Set<String> permitted) {
        if (!raw.isArray() || raw.size() > 20) {
            throw invalid("VIDEO_STORYBOARD_LINEAGE_INVALID", "候选镜头沿袭无效");
        }
        List<Lineage> result = new ArrayList<>();
        Set<String> sources = new HashSet<>();
        Set<String> relations = new HashSet<>();
        for (JsonNode item : raw) {
            String source = text(item, "sourceShotId");
            String relation = text(item, "relation");
            if (!permitted.contains(source)
                    || !sources.add(source)
                    || !Set.of("replacement", "copy", "split", "merge").contains(relation)) {
                throw invalid("VIDEO_STORYBOARD_LINEAGE_INVALID", "候选镜头沿袭来源或关系无效");
            }
            relations.add(relation);
            result.add(new Lineage(source, relation));
        }
        if (relations.size() > 1
                || (relations.contains("merge") && result.size() < 2)
                || (!relations.contains("merge") && result.size() > 1)) {
            throw invalid(
                    "VIDEO_STORYBOARD_LINEAGE_INVALID",
                    "替换、复制和拆分各有一个来源，合并至少有两个来源");
        }
        return List.copyOf(result);
    }

    private ArrayNode lineage(DSLContext tx, String shotId) {
        ArrayNode result = json.createArrayNode();
        tx.fetch(
                        """
                        SELECT "sourceShotId",relation FROM public."VideoShotLineage"
                        WHERE "childShotId"=? ORDER BY ordinal
                        """,
                        shotId)
                .forEach(row -> result.add(object(
                        "sourceShotId", row.get("sourceShotId"),
                        "relation", row.get("relation"))));
        return result;
    }

    private Map<String, Set<String>> scriptNodes(ObjectNode document) {
        Map<String, Set<String>> result = new HashMap<>();
        for (JsonNode scene : document.path("scenes")) {
            Set<String> lines = new HashSet<>();
            for (JsonNode line : scene.path("lines")) lines.add(text(line, "id"));
            result.put(text(scene, "id"), Set.copyOf(lines));
        }
        return Map.copyOf(result);
    }

    private String hash(ObjectNode value) {
        return ExecutionCanonicalJson.sha256(toMap(value));
    }

    private Map<String, Object> toMap(JsonNode value) {
        return json.convertValue(value, new TypeReference<Map<String, Object>>() {});
    }

    private ObjectNode readObject(Record row, String column, String label) {
        JsonNode value = json.readTree(row.get(column, String.class));
        if (!(value instanceof ObjectNode object)) {
            throw new IllegalStateException(label + "不是 JSON 对象");
        }
        return object;
    }

    private ObjectNode object(Object... values) {
        ObjectNode result = json.createObjectNode();
        for (int index = 0; index < values.length; index += 2) {
            result.set((String) values[index], json.valueToTree(values[index + 1]));
        }
        return result;
    }

    private static String text(JsonNode owner, String field) {
        return requiredTextValue(owner.get(field), field);
    }

    private static String requiredTextValue(JsonNode value, String label) {
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw invalid("VIDEO_STORYBOARD_VALUE_INVALID", label + " 必须是非空字符串");
        }
        return value.textValue();
    }

    private static String textValue(JsonNode value, String label) {
        return requiredTextValue(value, label);
    }

    private static String nullableText(JsonNode value) {
        return value == null || value.isNull() ? null : requiredTextValue(value, "可空身份");
    }

    private static void requireIdentity(String value, String label) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(label + "不能为空");
    }

    private LocalDateTime now() {
        return DatabaseTimestamp.now(clock);
    }

    private static ApiException invalid(String code, String message) {
        return new ApiException(422, code, message);
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(409, code, message);
    }

    private static ApiException notFound(String code, String message) {
        return new ApiException(404, code, message);
    }

    private record Lineage(String sourceShotId, String relation) {}
}
