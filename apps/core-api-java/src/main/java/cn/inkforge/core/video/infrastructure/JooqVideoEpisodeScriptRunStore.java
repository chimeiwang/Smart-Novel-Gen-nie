package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.VideoEpisodeScriptRunStore;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Supplier;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 以 Episode 草稿及选定来源为唯一输入创建 V2 Run，不建立旧 VideoAdaptationTask。 */
final class JooqVideoEpisodeScriptRunStore implements VideoEpisodeScriptRunStore {

    private static final Set<String> OPERATIONS =
            Set.of("episode_script_generate", "episode_script_revise");
    private static final int MAX_CONTEXT_BYTES = 600_000;
    private static final int MAX_CONTEXT_CODE_POINTS = 200_000;

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final CoreSettings settings;
    private final ExecutionRegistry registry;
    private final Supplier<DurableWorkflowService> workflows;
    private final ObjectMapper json;

    JooqVideoEpisodeScriptRunStore(
            CoreDatabase database,
            CuidV1Generator ids,
            CoreSettings settings,
            ExecutionRegistry registry,
            Supplier<DurableWorkflowService> workflows,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.settings = Objects.requireNonNull(settings);
        this.registry = Objects.requireNonNull(registry);
        this.workflows = Objects.requireNonNull(workflows);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public ObjectNode start(String userId, String episodeId, JsonNode request) {
        requireIdentity(userId, "用户 ID");
        requireIdentity(episodeId, "分集 ID");
        if (request == null || !request.isObject()) {
            throw invalid("VIDEO_SCRIPT_RUN_INPUT_INVALID", "剧本任务请求必须是对象");
        }
        NormalizedRequest normalized = normalize(episodeId, request);
        if (!settings.durableAgentExecutionSchemaReady()) {
            throw unavailable("耐久 Agent 结构尚未就绪，不能创建剧本任务");
        }
        requireNewRunEnabled();
        return database.transactionResult(transaction -> {
            // 先取得所有 V2 Run 共用的幂等锁，再取得视频命令锁；随后才锁 Novel/Project。
            // 该顺序避免同一请求键被其他 Workflow 与分集命令同时使用时形成反向等待。
            transaction.fetchOne(
                    "SELECT pg_advisory_xact_lock(?)",
                    CommandIdempotency.advisoryLockKey(
                            userId, normalized.clientRequestId()));
            lockCommand(transaction, userId, normalized.clientRequestId());
            Record command = existingCommand(
                    transaction, userId, normalized.clientRequestId());
            if (command != null) {
                return replayCommand(command, episodeId, normalized.requestHash());
            }
            Record existing = existingRun(
                    transaction, userId, normalized.clientRequestId());
            if (existing != null) {
                requireReplay(existing, episodeId, normalized.operation(), normalized.requestHash());
                ObjectNode response = runResponse(transaction, existing, episodeId);
                ReceiptScope scope = receiptScope(transaction, userId, episodeId);
                insertCommand(
                        transaction,
                        userId,
                        normalized,
                        scope.projectId(),
                        scope.novelId(),
                        episodeId,
                        response);
                return response;
            }
            FrozenEpisode frozen = freezeEpisode(
                    transaction, userId, episodeId, normalized);
            if (!settings.routesNewDurableAgentRun(userId, frozen.novelId())) {
                throw unavailable("当前小说未启用耐久剧本执行");
            }

            String operationKey = "video." + normalized.operation();
            boolean development = settings.environment() != CoreSettings.EnvironmentName.PRODUCTION;
            if (!registry.enabledOperationKeys("video", development).contains(operationKey)) {
                throw unavailable("单集剧本 Operation 尚未启用");
            }
            ExecutionRegistry.ResolvedOperation operation =
                    registry.resolve(operationKey, development);
            requireCatalog(operation.operation());
            ExecutionRegistry.ResolvedStage firstStage = operation.stageSteps().stream()
                    .filter(stage -> "episode_script".equals(stage.stageKey()))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException("剧本执行计划缺少首阶段"));
            DurableWorkflowService workflowService = workflows.get();
            if (workflowService == null) {
                throw unavailable("耐久剧本执行服务暂时不可用");
            }

            Map<String, Object> runInput = new LinkedHashMap<>(normalized.body());
            runInput.put("dispatchNamespace", settings.videoDispatchNamespace());
            Map<String, Object> stepInput = new LinkedHashMap<>();
            stepInput.put("stageKey", "episode_script");
            stepInput.put("cycle", 0);
            stepInput.put("candidate", null);
            stepInput.put("requiredChanges", List.of());
            stepInput.put("dependencies", List.of());
            WorkflowStartPlan plan = new WorkflowStartPlan(
                    userId,
                    normalized.clientRequestId(),
                    normalized.requestHash(),
                    "video",
                    normalized.operation(),
                    registry.catalogVersion(),
                    "chat",
                    frozen.novelId(),
                    null,
                    null,
                    "video_episode_script",
                    episodeId,
                    runInput,
                    operation.operation().evidencePolicy(),
                    List.of(new WorkflowEvidenceItemPlan(
                            "video_episode_script_context",
                            episodeId,
                            true,
                            frozen.draftRevision(),
                            frozen.draftUpdatedAt(),
                            null,
                            frozen.context(),
                            null,
                            null,
                            Map.of(
                                    "role", "video_episode_script_context",
                                    "schemaVersion", "video-episode-script-context/1.0"))),
                    operation.operation().runBudget(),
                    registry.freezePlan(operationKey, development),
                    new WorkflowInitialStepPlan(
                            "generation",
                            operation.operation().lane(),
                            stepInput,
                            firstStage.profile(),
                            firstStage.stepBudget(),
                            firstStage.outputSchema()),
                    null,
                    new WorkflowStartPlan.SourceBinding("video_episode_script", episodeId));
            String runId = workflowService.startFresh(plan).runId();
            Record created = requireRun(transaction, userId, episodeId, runId);
            ObjectNode response = runResponse(transaction, created, episodeId);
            insertCommand(
                    transaction,
                    userId,
                    normalized,
                    frozen.projectId(),
                    frozen.novelId(),
                    episodeId,
                    response);
            return response;
        });
    }

    @Override
    public ObjectNode get(String userId, String episodeId, String runId) {
        requireIdentity(userId, "用户 ID");
        requireIdentity(episodeId, "分集 ID");
        requireIdentity(runId, "Run ID");
        if (!settings.durableAgentExecutionSchemaReady()) {
            throw unavailable("耐久 Agent 结构尚未就绪，不能读取剧本任务");
        }
        return database.transactionResult(transaction -> runResponse(
                transaction,
                requireRun(transaction, userId, episodeId, runId),
                episodeId));
    }

    private void requireNewRunEnabled() {
        if (!settings.videoPreviewEnabled()) {
            throw new ApiException(
                    503, "VIDEO_PREVIEW_DISABLED", "长篇视频开发预览暂未启用");
        }
        if (!settings.videoDispatchEnabled()
                || settings.videoDispatchNamespace() == null
                || settings.videoDispatchNamespace().isBlank()) {
            throw new ApiException(
                    503, "VIDEO_SCRIPT_DISPATCH_DISABLED", "单集剧本后台执行暂未启用");
        }
        if (settings.environment() == CoreSettings.EnvironmentName.PRODUCTION) {
            throw new ApiException(
                    503, "VIDEO_SCRIPT_PRODUCTION_DISABLED", "生产环境未开放单集剧本生成");
        }
    }

    private FrozenEpisode freezeEpisode(
            DSLContext transaction,
            String userId,
            String episodeId,
            NormalizedRequest request) {
        Record identity = transaction.fetchOne(
                """
                SELECT "projectId"
                FROM public."VideoEpisode"
                WHERE id = ? AND "archivedAt" IS NULL
                """,
                episodeId);
        if (identity == null) {
            throw notFound("VIDEO_EPISODE_NOT_FOUND", "分集不存在");
        }
        String projectId = identity.get("projectId", String.class);
        var project = VideoDatabaseAccess.ownedProject(
                transaction, userId, projectId, true);
        VideoDatabaseAccess.requireLongSerial(transaction, project.getNovelid(), true);
        Record episode = transaction.fetchOne(
                """
                SELECT * FROM public."VideoEpisode"
                WHERE id = ? AND "projectId" = ? AND "archivedAt" IS NULL
                FOR UPDATE
                """,
                episodeId,
                projectId);
        if (episode == null) {
            throw notFound("VIDEO_EPISODE_NOT_FOUND", "分集不存在");
        }
        Record draft = transaction.fetchOne(
                """
                SELECT * FROM public."VideoEpisodeScriptDraft"
                WHERE "episodeId" = ?
                FOR UPDATE
                """,
                episodeId);
        if (draft == null) {
            throw new ApiException(
                    409, "VIDEO_SCRIPT_DRAFT_MISSING", "分集缺少可冻结的剧本工作稿");
        }
        int draftRevision = draft.get("revision", Integer.class);
        if (draftRevision != request.expectedDraftRevision()) {
            throw new ApiException(
                    409,
                    "VIDEO_SCRIPT_DRAFT_REVISION_CONFLICT",
                    "剧本工作稿已变化，请保留输入并重新读取",
                    Map.of("currentRevision", draftRevision));
        }

        ObjectNode document = readObject(draft, "documentJson", "剧本工作稿");
        requireSceneScope(document, request.operation(), request.selectedSceneIds());
        String sourceSetVersionId = draft.get("sourceSetVersionId", String.class);
        if (sourceSetVersionId == null) {
            throw new ApiException(
                    409, "VIDEO_SCRIPT_SOURCE_REQUIRED", "请先为当前工作稿选择明确来源");
        }
        List<Map<String, Object>> sources = selectedSources(
                transaction, episodeId, sourceSetVersionId);
        List<Map<String, Object>> characters = characters(
                transaction, project.getNovelid());
        List<Map<String, Object>> inheritedStates = inheritedStates(
                transaction, projectId, document);

        Map<String, Object> context = new LinkedHashMap<>();
        context.put("schemaVersion", "video-episode-script-context/1.0");
        context.put("episodeId", episodeId);
        context.put("projectId", projectId);
        context.put("novelId", project.getNovelid());
        context.put("episodeTitle", episode.get("title", String.class));
        context.put("operation", request.operation());
        context.put("draftRevision", draftRevision);
        context.put("sourceSetVersionId", sourceSetVersionId);
        context.put(
                "baseScriptVersionId",
                draft.get("basedOnScriptVersionId", String.class));
        context.put("draft", toMap(document));
        context.put("sources", sources);
        context.put("characters", characters);
        context.put("inheritedStates", inheritedStates);
        context.put("selectedSceneIds", request.selectedSceneIds());
        context.put("instruction", request.instruction());
        byte[] canonicalContext = ExecutionCanonicalJson.bytes(context);
        int byteCount = canonicalContext.length;
        String canonicalText = new String(canonicalContext, StandardCharsets.UTF_8);
        int codePointCount = canonicalText.codePointCount(0, canonicalText.length());
        if (byteCount > MAX_CONTEXT_BYTES || codePointCount > MAX_CONTEXT_CODE_POINTS) {
            throw new ApiException(
                    422,
                    "VIDEO_SCRIPT_CONTEXT_TOO_LARGE",
                    "所选来源与剧本上下文超过单次生成上限，请缩小取材范围",
                    Map.of(
                            "actualBytes", byteCount,
                            "maxBytes", MAX_CONTEXT_BYTES,
                            "actualCodePoints", codePointCount,
                            "maxCodePoints", MAX_CONTEXT_CODE_POINTS));
        }
        return new FrozenEpisode(
                projectId,
                project.getNovelid(),
                draftRevision,
                DatabaseTimestamp.api(draft.get("updatedAt", LocalDateTime.class)),
                context);
    }

    private List<Map<String, Object>> selectedSources(
            DSLContext transaction, String episodeId, String sourceSetVersionId) {
        Record sourceSet = transaction.fetchOne(
                """
                SELECT id
                FROM public."VideoEpisodeSourceSetVersion"
                WHERE id = ? AND "episodeId" = ?
                """,
                sourceSetVersionId,
                episodeId);
        if (sourceSet == null) {
            throw new ApiException(
                    409, "VIDEO_SCRIPT_SOURCE_MISMATCH", "当前工作稿引用的来源集合不存在");
        }
        var rows = transaction.fetch(
                """
                SELECT *
                FROM public."VideoEpisodeSourceSnapshot"
                WHERE "sourceSetVersionId" = ?
                ORDER BY ordinal, id
                """,
                sourceSetVersionId);
        if (rows.isEmpty() || rows.size() > 40) {
            throw invalid("VIDEO_SCRIPT_SOURCE_INVALID", "剧本来源集合必须包含 1 至 40 个章节快照");
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Record row : rows) {
            String snapshotId = row.get("id", String.class);
            String sourceText = row.get("sourceText", String.class);
            String sourceHash = row.get("sourceHash", String.class);
            if (sourceText == null || !sha256(sourceText).equals(sourceHash)) {
                throw new IllegalStateException("剧本来源快照哈希不一致");
            }
            JsonNode parsedRanges = json.readTree(row.get("rangesJson", String.class));
            if (!(parsedRanges instanceof ArrayNode ranges)
                    || ranges.isEmpty()
                    || ranges.size() > 100) {
                throw new IllegalStateException("剧本来源快照范围无效");
            }
            int codePoints = sourceText.codePointCount(0, sourceText.length());
            List<Map<String, Object>> selected = new ArrayList<>();
            for (JsonNode range : ranges) {
                int start = range.path("start").asInt(-1);
                int end = range.path("end").asInt(-1);
                if (start < 0 || end <= start || end > codePoints) {
                    throw new IllegalStateException("剧本来源快照范围越界");
                }
                String text = codePointSlice(sourceText, start, end);
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("sourceSnapshotId", snapshotId);
                item.put("start", start);
                item.put("end", end);
                item.put("text", text);
                item.put("textHash", sha256(text));
                selected.add(item);
            }
            Map<String, Object> source = new LinkedHashMap<>();
            source.put("sourceSnapshotId", snapshotId);
            source.put("chapterId", row.get("chapterId", String.class));
            source.put("chapterTitle", row.get("chapterTitle", String.class));
            source.put("sourceHash", sourceHash);
            source.put("selectedRanges", selected);
            result.add(source);
        }
        return List.copyOf(result);
    }

    private List<Map<String, Object>> characters(
            DSLContext transaction, String novelId) {
        var rows = transaction.fetch(
                """
                SELECT id, name, aliases, gender, age, appearance, personality, identity,
                       background, "coreDesire", "behaviorBoundaries", "speechStyle",
                       "shortTermGoal", "currentStatus"::text AS "currentStatus", "statusNote"
                FROM public."Character"
                WHERE "novelId" = ?
                ORDER BY id
                """,
                novelId);
        if (rows.size() > 200) {
            throw invalid(
                    "VIDEO_SCRIPT_CHARACTER_LIMIT_EXCEEDED",
                    "小说角色超过 200 个，不能在一次剧本任务中完整冻结");
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Record row : rows) {
            String description = characterDescription(row);
            if (description.codePointCount(0, description.length()) > 20_000) {
                throw invalid(
                        "VIDEO_SCRIPT_CHARACTER_TOO_LARGE",
                        "角色设定超过单个剧本上下文上限");
            }
            result.add(Map.of(
                    "id", row.get("id", String.class),
                    "name", row.get("name", String.class),
                    "description", description));
        }
        return List.copyOf(result);
    }

    private List<Map<String, Object>> inheritedStates(
            DSLContext transaction, String projectId, ObjectNode draft) {
        JsonNode dependencies = draft.path("dependencies");
        if (!dependencies.isArray() || dependencies.size() > 200) {
            throw invalid("VIDEO_SCRIPT_DOCUMENT_INVALID", "剧本承接关系无效");
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (JsonNode dependency : dependencies) {
            String producerEpisodeId = text(dependency, "producerEpisodeId");
            String producerVersionId = text(dependency, "producerScriptVersionId");
            String stateKey = text(dependency, "producerStateKey");
            Record version = transaction.fetchOne(
                    """
                    SELECT version."documentJson", version."contentHash"
                    FROM public."VideoEpisodeScriptVersion" version
                    JOIN public."VideoEpisode" episode
                      ON episode.id = version."episodeId"
                    WHERE version.id = ?
                      AND version."episodeId" = ?
                      AND episode."projectId" = ?
                    """,
                    producerVersionId,
                    producerEpisodeId,
                    projectId);
            if (version == null) {
                throw invalid(
                        "VIDEO_SCRIPT_DEPENDENCY_INVALID",
                        "剧本承接引用的正式版本不存在或不属于当前项目");
            }
            ObjectNode producerDocument = readObject(
                    version, "documentJson", "承接来源剧本");
            JsonNode state = null;
            for (JsonNode candidate : producerDocument.path("endingStates")) {
                if (stateKey.equals(candidate.path("key").asText())) {
                    state = candidate;
                    break;
                }
            }
            if (state == null || !state.isObject()) {
                throw invalid(
                        "VIDEO_SCRIPT_DEPENDENCY_STATE_MISSING",
                        "剧本承接引用的结尾状态不存在");
            }
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("episodeId", producerEpisodeId);
            item.put("scriptVersionId", producerVersionId);
            item.put("state", toMap((ObjectNode) state));
            item.put("contentHash", version.get("contentHash", String.class));
            result.add(item);
        }
        return List.copyOf(result);
    }

    private NormalizedRequest normalize(String episodeId, JsonNode request) {
        String clientRequestId = text(request, "clientRequestId");
        if (clientRequestId.length() < 16 || clientRequestId.length() > 128) {
            throw invalid(
                    "VIDEO_SCRIPT_CLIENT_REQUEST_ID_INVALID",
                    "clientRequestId 长度必须为 16 至 128 个字符");
        }
        String operation = text(request, "operation");
        if (!OPERATIONS.contains(operation)) {
            throw invalid("VIDEO_SCRIPT_OPERATION_INVALID", "剧本任务类型无效");
        }
        int expectedRevision = request.path("expectedDraftRevision").asInt(-1);
        if (expectedRevision < 1) {
            throw invalid("VIDEO_SCRIPT_DRAFT_REVISION_INVALID", "工作稿 revision 必须为正数");
        }
        String instruction = text(request, "instruction").strip();
        int instructionLength = instruction.codePointCount(0, instruction.length());
        if (instruction.isEmpty() || instructionLength > 8_000) {
            throw invalid("VIDEO_SCRIPT_INSTRUCTION_INVALID", "剧本任务说明长度必须为 1 至 8000 字");
        }
        JsonNode selectedValue = request.path("selectedSceneIds");
        if (!selectedValue.isArray() || selectedValue.size() > 60) {
            throw invalid("VIDEO_SCRIPT_SCENE_SCOPE_INVALID", "剧本修订场次范围无效");
        }
        List<String> selected = new ArrayList<>();
        selectedValue.forEach(value -> selected.add(requireTextValue(value, "场次 ID")));
        if (new HashSet<>(selected).size() != selected.size()
                || (operation.equals("episode_script_generate") && !selected.isEmpty())
                || (operation.equals("episode_script_revise") && selected.isEmpty())) {
            throw invalid(
                    "VIDEO_SCRIPT_SCENE_SCOPE_INVALID",
                    "起草不得携带场次范围，局部修订必须选择至少一个稳定场次");
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("episodeId", episodeId);
        body.put("operation", operation);
        body.put("expectedDraftRevision", expectedRevision);
        body.put("selectedSceneIds", List.copyOf(selected));
        body.put("instruction", instruction);
        String requestHash = CommandIdempotency.requestFingerprint(
                "video_episode_script_run.start",
                Map.of("episodeId", episodeId),
                body,
                json);
        return new NormalizedRequest(
                clientRequestId,
                operation,
                expectedRevision,
                List.copyOf(selected),
                instruction,
                Map.copyOf(body),
                requestHash);
    }

    private void requireSceneScope(
            ObjectNode document, String operation, List<String> selectedSceneIds) {
        JsonNode scenes = document.path("scenes");
        if (!scenes.isArray()) {
            throw invalid("VIDEO_SCRIPT_DOCUMENT_INVALID", "工作稿场次结构无效");
        }
        Set<String> stableIds = new HashSet<>();
        for (JsonNode scene : scenes) {
            if (scene.hasNonNull("tempKey") || !scene.hasNonNull("id")) {
                throw invalid(
                        "VIDEO_SCRIPT_DOCUMENT_INVALID",
                        "发送给模型前，工作稿场次必须已有 Core 稳定身份");
            }
            stableIds.add(text(scene, "id"));
        }
        if (operation.equals("episode_script_revise")
                && !stableIds.containsAll(selectedSceneIds)) {
            throw invalid(
                    "VIDEO_SCRIPT_SCENE_SCOPE_INVALID",
                    "局部修订只能引用当前冻结工作稿中的稳定场次");
        }
    }

    private void requireCatalog(ExecutionRegistry.Operation operation) {
        if (!"video".equals(operation.workflow())
                || !OPERATIONS.contains(operation.operation())
                || !operation.targetKinds().contains("video_episode_script")
                || !operation.scopeKinds().contains("episode")
                || !"evidence.video.episode_script.v1".equals(operation.evidencePolicy())
                || !operation.developmentOnly()) {
            throw new IllegalStateException("单集剧本 Operation Catalog 身份不一致");
        }
    }

    private Record existingRun(
            DSLContext transaction, String userId, String clientRequestId) {
        return transaction.fetchOne(
                """
                SELECT *
                FROM public."WorkflowRun"
                WHERE "engineVersion" = 2
                  AND "userId" = ?
                  AND "idempotencyKey" = ?
                FOR UPDATE
                """,
                userId,
                clientRequestId);
    }

    private void lockCommand(
            DSLContext transaction, String userId, String clientRequestId) {
        transaction.fetchOne(
                "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
                "video-episode-command:" + userId + ":" + clientRequestId);
    }

    private Record existingCommand(
            DSLContext transaction, String userId, String clientRequestId) {
        return transaction.fetchOne(
                """
                SELECT *
                FROM public."VideoEpisodeCommand"
                WHERE "actorUserId" = ? AND "clientRequestId" = ?
                FOR UPDATE
                """,
                userId,
                clientRequestId);
    }

    private ObjectNode replayCommand(
            Record command, String episodeId, String requestHash) {
        if (!"episode.script.run".equals(command.get("operation", String.class))
                || !episodeId.equals(command.get("episodeId", String.class))
                || !requestHash.equals(command.get("requestHash", String.class))) {
            throw new ApiException(
                    409,
                    "VIDEO_EPISODE_CLIENT_REQUEST_REUSED",
                    "clientRequestId 已用于不同的分集命令");
        }
        JsonNode result = json.readTree(command.get("resultJson", String.class));
        if (!(result instanceof ObjectNode response)
                || !episodeId.equals(response.path("episodeId").asText())
                || response.path("runId").asText().isBlank()) {
            throw new IllegalStateException("剧本任务命令回执已损坏");
        }
        return response;
    }

    private ReceiptScope receiptScope(
            DSLContext transaction, String userId, String episodeId) {
        Record scope = transaction.fetchOne(
                """
                SELECT episode."projectId", episode."novelId"
                FROM public."VideoEpisode" episode
                JOIN public."VideoProject" project
                  ON project.id = episode."projectId"
                 AND project."novelId" = episode."novelId"
                JOIN public."Novel" novel
                  ON novel.id = episode."novelId"
                WHERE episode.id = ?
                  AND episode."archivedAt" IS NULL
                  AND project."deletedAt" IS NULL
                  AND novel."userId" = ?
                """,
                episodeId,
                userId);
        if (scope == null) {
            throw notFound("VIDEO_EPISODE_NOT_FOUND", "分集不存在");
        }
        return new ReceiptScope(
                scope.get("projectId", String.class),
                scope.get("novelId", String.class));
    }

    private void insertCommand(
            DSLContext transaction,
            String userId,
            NormalizedRequest request,
            String projectId,
            String novelId,
            String episodeId,
            ObjectNode response) {
        transaction.execute(
                """
                INSERT INTO public."VideoEpisodeCommand" (
                  id, "actorUserId", "clientRequestId", "projectId", "novelId",
                  "episodeId", operation, "requestHash", "resultJson"
                ) VALUES (?, ?, ?, ?, ?, ?, 'episode.script.run', ?, ?)
                """,
                ids.next(),
                userId,
                request.clientRequestId(),
                projectId,
                novelId,
                episodeId,
                request.requestHash(),
                response.toString());
    }

    private void requireReplay(
            Record run, String episodeId, String operation, String requestHash) {
        if (!requestHash.equals(run.get("requestHash", String.class))
                || !"video".equals(run.get("workflow", String.class))
                || !operation.equals(run.get("operation", String.class))
                || !"video_episode_script".equals(run.get("targetType", String.class))
                || !episodeId.equals(run.get("targetId", String.class))
                || !"video_episode_script".equals(run.get("sourceType", String.class))
                || !episodeId.equals(run.get("sourceId", String.class))) {
            throw new ApiException(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "同一 clientRequestId 已用于不同 Agent 请求");
        }
    }

    private Record requireRun(
            DSLContext transaction, String userId, String episodeId, String runId) {
        Record run = transaction.fetchOne(
                """
                SELECT *
                FROM public."WorkflowRun"
                WHERE id = ?
                  AND "engineVersion" = 2
                  AND "userId" = ?
                  AND workflow = 'video'
                  AND operation IN ('episode_script_generate', 'episode_script_revise')
                  AND "targetType" = 'video_episode_script'
                  AND "targetId" = ?
                  AND "sourceType" = 'video_episode_script'
                  AND "sourceId" = ?
                """,
                runId,
                userId,
                episodeId,
                episodeId);
        if (run == null) {
            throw notFound("VIDEO_SCRIPT_RUN_NOT_FOUND", "剧本任务不存在或不属于当前分集");
        }
        return run;
    }

    private ObjectNode runResponse(
            DSLContext transaction, Record run, String episodeId) {
        Record artifact = transaction.fetchOne(
                """
                SELECT id
                FROM public."ReviewArtifact"
                WHERE "workflowRunId" = ?
                  AND kind::text = 'video_episode_script'
                ORDER BY "createdAt" DESC, id DESC
                LIMIT 1
                """,
                run.get("id", String.class));
        ObjectNode response = json.createObjectNode();
        response.put("runId", run.get("id", String.class));
        response.put("episodeId", episodeId);
        response.put("status", run.get("status", String.class));
        putNullable(response, "artifactId", artifact == null ? null : artifact.get("id", String.class));
        putNullable(response, "errorCode", run.get("errorCode", String.class));
        putNullable(response, "errorMessage", run.get("errorMessage", String.class));
        response.set(
                "createdAt",
                json.valueToTree(DatabaseTimestamp.api(
                        run.get("createdAt", LocalDateTime.class))));
        response.set(
                "updatedAt",
                json.valueToTree(DatabaseTimestamp.api(
                        run.get("updatedAt", LocalDateTime.class))));
        return response;
    }

    private static String characterDescription(Record row) {
        StringBuilder result = new StringBuilder();
        append(result, "别名", row.get("aliases", String.class));
        append(result, "性别", row.get("gender", String.class));
        append(result, "年龄", row.get("age", String.class));
        append(result, "外貌", row.get("appearance", String.class));
        append(result, "性格", row.get("personality", String.class));
        append(result, "身份", row.get("identity", String.class));
        append(result, "背景", row.get("background", String.class));
        append(result, "核心欲望", row.get("coreDesire", String.class));
        append(result, "行为边界", row.get("behaviorBoundaries", String.class));
        append(result, "说话方式", row.get("speechStyle", String.class));
        append(result, "短期目标", row.get("shortTermGoal", String.class));
        append(result, "当前状态", row.get("currentStatus", String.class));
        append(result, "状态说明", row.get("statusNote", String.class));
        return result.toString();
    }

    private static void append(StringBuilder target, String label, String value) {
        if (value == null || value.isBlank()) return;
        if (!target.isEmpty()) target.append('\n');
        target.append(label).append("：").append(value);
    }

    private ObjectNode readObject(Record row, String column, String label) {
        JsonNode value = json.readTree(row.get(column, String.class));
        if (!(value instanceof ObjectNode object)) {
            throw new IllegalStateException(label + "不是 JSON 对象");
        }
        return object;
    }

    private Map<String, Object> toMap(ObjectNode value) {
        return json.convertValue(value, new TypeReference<Map<String, Object>>() {});
    }

    private static String codePointSlice(String value, int start, int end) {
        int from = value.offsetByCodePoints(0, start);
        int to = value.offsetByCodePoints(from, end - start);
        return value.substring(from, to);
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 缺少 SHA-256", exception);
        }
    }

    private static String text(JsonNode owner, String field) {
        JsonNode value = owner.get(field);
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw invalid("VIDEO_SCRIPT_RUN_INPUT_INVALID", field + " 必须是非空字符串");
        }
        return value.textValue();
    }

    private static String requireTextValue(JsonNode value, String label) {
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw invalid("VIDEO_SCRIPT_SCENE_SCOPE_INVALID", label + " 必须是非空字符串");
        }
        return value.textValue();
    }

    private static void requireIdentity(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + "不能为空");
        }
    }

    private static void putNullable(ObjectNode owner, String field, String value) {
        if (value == null) owner.putNull(field);
        else owner.put(field, value);
    }

    private static ApiException invalid(String code, String message) {
        return new ApiException(422, code, message);
    }

    private static ApiException notFound(String code, String message) {
        return new ApiException(404, code, message);
    }

    private static ApiException unavailable(String message) {
        return new ApiException(503, "VIDEO_SCRIPT_WORKFLOW_UNAVAILABLE", message);
    }

    private record NormalizedRequest(
            String clientRequestId,
            String operation,
            int expectedDraftRevision,
            List<String> selectedSceneIds,
            String instruction,
            Map<String, Object> body,
            String requestHash) {}

    private record FrozenEpisode(
            String projectId,
            String novelId,
            int draftRevision,
            OffsetDateTime draftUpdatedAt,
            Map<String, Object> context) {}

    private record ReceiptScope(String projectId, String novelId) {}
}
