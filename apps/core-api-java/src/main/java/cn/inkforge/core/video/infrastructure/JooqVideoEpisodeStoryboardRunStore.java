package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.VideoEpisodeStoryboardRunStore;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashSet;
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

/** 以正式剧本、分镜工作稿及已批准视觉参考创建 V2 Run，不建立旧 VideoAdaptationTask。 */
final class JooqVideoEpisodeStoryboardRunStore implements VideoEpisodeStoryboardRunStore {

    private static final Set<String> OPERATIONS =
            Set.of("episode_storyboard_generate", "episode_storyboard_revise");
    private static final int MAX_CONTEXT_BYTES = 800_000;
    private static final int MAX_CONTEXT_CODE_POINTS = 250_000;

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final CoreSettings settings;
    private final ExecutionRegistry registry;
    private final Supplier<DurableWorkflowService> workflows;
    private final ObjectMapper json;

    JooqVideoEpisodeStoryboardRunStore(
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
            throw invalid("VIDEO_STORYBOARD_RUN_INPUT_INVALID", "分镜任务请求必须是对象");
        }
        NormalizedRequest normalized = normalize(episodeId, request);
        if (!settings.durableAgentExecutionSchemaReady()) {
            throw unavailable("耐久 Agent 结构尚未就绪，不能创建分镜任务");
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
                throw unavailable("当前小说未启用耐久分镜执行");
            }

            String operationKey = "video." + normalized.operation();
            boolean development = settings.environment() != CoreSettings.EnvironmentName.PRODUCTION;
            if (!registry.enabledOperationKeys("video", development).contains(operationKey)) {
                throw unavailable("单集分镜 Operation 尚未启用");
            }
            ExecutionRegistry.ResolvedOperation operation =
                    registry.resolve(operationKey, development);
            requireCatalog(operation.operation());
            ExecutionRegistry.ResolvedStage firstStage = operation.stageSteps().stream()
                    .filter(stage -> "episode_storyboard".equals(stage.stageKey()))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException("分镜执行计划缺少首阶段"));
            DurableWorkflowService workflowService = workflows.get();
            if (workflowService == null) {
                throw unavailable("耐久分镜执行服务暂时不可用");
            }

            Map<String, Object> runInput = new LinkedHashMap<>(normalized.body());
            runInput.put("dispatchNamespace", settings.videoDispatchNamespace());
            Map<String, Object> stepInput = new LinkedHashMap<>();
            stepInput.put("stageKey", "episode_storyboard");
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
                    "video_episode_storyboard",
                    episodeId,
                    runInput,
                    operation.operation().evidencePolicy(),
                    List.of(new WorkflowEvidenceItemPlan(
                            "video_episode_storyboard_context",
                            episodeId,
                            true,
                            frozen.draftRevision(),
                            frozen.draftUpdatedAt(),
                            null,
                            frozen.context(),
                            null,
                            null,
                            Map.of(
                                    "role", "video_episode_storyboard_context",
                                    "schemaVersion", "video-episode-storyboard-context/1.0"))),
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
                    new WorkflowStartPlan.SourceBinding("video_episode_storyboard", episodeId));
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
            throw unavailable("耐久 Agent 结构尚未就绪，不能读取分镜任务");
        }
        return database.transactionResult(transaction -> runResponse(
                transaction,
                requireRun(transaction, userId, episodeId, runId),
                episodeId));
    }

    @Override
    public ObjectNode list(String userId, String episodeId, String beforeRunId, int limit) {
        requireIdentity(userId, "用户 ID");
        requireIdentity(episodeId, "分集 ID");
        if (limit < 1 || limit > 50) {
            throw invalid("VIDEO_STORYBOARD_RUN_LIMIT_INVALID", "分镜任务列表 limit 必须为 1 至 50");
        }
        if (!settings.durableAgentExecutionSchemaReady()) {
            throw unavailable("耐久 Agent 结构尚未就绪，不能读取分镜任务");
        }
        return database.transactionResult(transaction -> {
            receiptScope(transaction, userId, episodeId);
            Record cursor = beforeRunId == null
                    ? null
                    : requireRun(transaction, userId, episodeId, beforeRunId);
            List<Record> rows = cursor == null
                    ? transaction.fetch(
                            """
                            SELECT * FROM public."WorkflowRun"
                            WHERE "engineVersion"=2 AND "userId"=? AND workflow='video'
                              AND operation IN ('episode_storyboard_generate','episode_storyboard_revise')
                              AND "targetType"='video_episode_storyboard' AND "targetId"=?
                              AND "sourceType"='video_episode_storyboard' AND "sourceId"=?
                            ORDER BY "createdAt" DESC,id DESC LIMIT ?
                            """,
                            userId, episodeId, episodeId, limit + 1)
                    : transaction.fetch(
                            """
                            SELECT * FROM public."WorkflowRun"
                            WHERE "engineVersion"=2 AND "userId"=? AND workflow='video'
                              AND operation IN ('episode_storyboard_generate','episode_storyboard_revise')
                              AND "targetType"='video_episode_storyboard' AND "targetId"=?
                              AND "sourceType"='video_episode_storyboard' AND "sourceId"=?
                              AND ("createdAt",id) < (?,?)
                            ORDER BY "createdAt" DESC,id DESC LIMIT ?
                            """,
                            userId,
                            episodeId,
                            episodeId,
                            cursor.get("createdAt", LocalDateTime.class),
                            cursor.get("id", String.class),
                            limit + 1);
            boolean hasMore = rows.size() > limit;
            List<Record> visible = hasMore ? rows.subList(0, limit) : rows;
            ObjectNode response = json.createObjectNode();
            response.set(
                    "runs",
                    json.valueToTree(
                            visible.stream()
                                    .map(run -> runResponse(transaction, run, episodeId))
                                    .toList()));
            putNullable(
                    response,
                    "nextBeforeRunId",
                    hasMore && !visible.isEmpty()
                            ? visible.get(visible.size() - 1).get("id", String.class)
                            : null);
            return response;
        });
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
                    503, "VIDEO_STORYBOARD_DISPATCH_DISABLED", "单集分镜后台执行暂未启用");
        }
        if (settings.environment() == CoreSettings.EnvironmentName.PRODUCTION) {
            throw new ApiException(
                    503, "VIDEO_STORYBOARD_PRODUCTION_DISABLED", "生产环境未开放单集分镜生成");
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
                SELECT * FROM public."VideoStoryboardDraft"
                WHERE "episodeId" = ?
                FOR UPDATE
                """,
                episodeId);
        if (draft == null) {
            throw new ApiException(
                    409, "VIDEO_STORYBOARD_DRAFT_MISSING", "分集缺少可冻结的分镜工作稿");
        }
        int draftRevision = draft.get("revision", Integer.class);
        if (draftRevision != request.expectedDraftRevision()) {
            throw new ApiException(
                    409,
                    "VIDEO_STORYBOARD_DRAFT_REVISION_CONFLICT",
                    "分镜工作稿已变化，请保留输入并重新读取",
                    Map.of("currentRevision", draftRevision));
        }
        String draftScriptVersionId = draft.get("scriptVersionId", String.class);
        if (!request.scriptVersionId().equals(draftScriptVersionId)) {
            throw new ApiException(
                    409,
                    "VIDEO_STORYBOARD_SCRIPT_VERSION_CONFLICT",
                    "分镜工作稿绑定的正式剧本版本已经变化，请重新读取");
        }
        Record scriptVersion = transaction.fetchOne(
                """
                SELECT * FROM public."VideoEpisodeScriptVersion"
                WHERE id = ? AND "episodeId" = ? AND "projectId" = ?
                """,
                request.scriptVersionId(),
                episodeId,
                projectId);
        if (scriptVersion == null) {
            throw invalid(
                    "VIDEO_STORYBOARD_SCRIPT_VERSION_INVALID",
                    "分镜必须绑定当前分集的正式剧本版本");
        }

        ObjectNode document = readObject(draft, "documentJson", "分镜工作稿");
        String draftHash = ExecutionCanonicalJson.sha256(toMap(document));
        if (!draftHash.equals(draft.get("contentHash", String.class))) {
            throw new IllegalStateException("分镜工作稿哈希不一致");
        }
        List<String> stableShotIds = requireShotScope(
                document, request.operation(), request.selectedShotIds());
        ObjectNode script = readObject(scriptVersion, "documentJson", "正式剧本版本");
        String scriptHash = ExecutionCanonicalJson.sha256(toMap(script));
        if (!scriptHash.equals(scriptVersion.get("contentHash", String.class))) {
            throw new IllegalStateException("正式剧本版本哈希不一致");
        }
        requireStableScript(script);
        List<Map<String, Object>> references = availableReferences(transaction, projectId);

        Map<String, Object> defaults = new LinkedHashMap<>();
        defaults.put("provider", "seedance");
        defaults.put("model", settings.seedanceModel());
        defaults.put("generationMode", "reference");
        // AI 起草永远不代表用户确认真实费用；作者可在采用后另行手工调整工作稿。
        defaults.put("executionMode", "simulated");
        defaults.put("feeConfirmed", false);
        defaults.put("ratio", project.getTargetaspectratio());
        defaults.put("resolution", "720p");
        defaults.put("generateAudio", true);
        defaults.put("watermark", false);
        defaults.put("outputFormat", "mp4");

        Map<String, Object> context = new LinkedHashMap<>();
        context.put("schemaVersion", "video-episode-storyboard-context/1.0");
        context.put("episodeId", episodeId);
        context.put("projectId", projectId);
        context.put("novelId", project.getNovelid());
        context.put("episodeTitle", episode.get("title", String.class));
        context.put("operation", request.operation());
        context.put("draftRevision", draftRevision);
        context.put("draftContentHash", draftHash);
        context.put("scriptVersionId", request.scriptVersionId());
        context.put("scriptContentHash", scriptHash);
        context.put(
                "baseStoryboardVersionId",
                draft.get("basedOnStoryboardVersionId", String.class));
        context.put("script", toMap(script));
        context.put("draft", toMap(document));
        context.put("stableShotIds", stableShotIds);
        context.put("selectedShotIds", request.selectedShotIds());
        context.put("productionDefaults", Map.copyOf(defaults));
        context.put("availableReferences", references);
        context.put("instruction", request.instruction());
        byte[] canonicalContext = ExecutionCanonicalJson.bytes(context);
        int byteCount = canonicalContext.length;
        String canonicalText = new String(canonicalContext, StandardCharsets.UTF_8);
        int codePointCount = canonicalText.codePointCount(0, canonicalText.length());
        if (byteCount > MAX_CONTEXT_BYTES || codePointCount > MAX_CONTEXT_CODE_POINTS) {
            throw new ApiException(
                    422,
                    "VIDEO_STORYBOARD_CONTEXT_TOO_LARGE",
                    "正式剧本、分镜工作稿与视觉参考超过单次生成上限，请缩小分镜范围或精简输入",
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

    private void requireStableScript(ObjectNode script) {
        JsonNode scenes = script.path("scenes");
        if (!scenes.isArray() || scenes.isEmpty() || scenes.size() > 60) {
            throw invalid(
                    "VIDEO_STORYBOARD_SCRIPT_INVALID",
                    "正式剧本必须包含 1 至 60 个稳定场次");
        }
        Set<String> identities = new HashSet<>();
        for (JsonNode scene : scenes) {
            if (scene.hasNonNull("tempKey") || !scene.hasNonNull("id")
                    || !identities.add(text(scene, "id"))) {
                throw invalid(
                        "VIDEO_STORYBOARD_SCRIPT_INVALID",
                        "正式剧本场次必须使用唯一稳定身份");
            }
            JsonNode lines = scene.path("lines");
            if (!lines.isArray() || lines.size() > 500) {
                throw invalid("VIDEO_STORYBOARD_SCRIPT_INVALID", "正式剧本台词结构无效");
            }
            for (JsonNode line : lines) {
                if (line.hasNonNull("tempKey") || !line.hasNonNull("id")
                        || !identities.add(text(line, "id"))) {
                    throw invalid(
                            "VIDEO_STORYBOARD_SCRIPT_INVALID",
                            "正式剧本台词必须使用唯一稳定身份");
                }
            }
        }
    }

    private List<Map<String, Object>> availableReferences(
            DSLContext transaction, String projectId) {
        var rows = transaction.fetch(
                """
                SELECT version.id, version."contentHash", version."assetId",
                       version."defaultStrength", version."settingName", version.label,
                       version."includeFeaturesJson", version."excludeFeaturesJson",
                       asset.sha256, asset."mimeType", asset.duty,
                       asset."rightsStatus", asset."lockedAt"
                FROM public."VideoVisualCanon" canon
                JOIN public."VideoVisualCanonVersion" version
                  ON version.id = canon."currentVersionId"
                 AND version."canonId" = canon.id
                 AND version."projectId" = canon."projectId"
                JOIN public."VideoAsset" asset
                  ON asset.id = version."assetId"
                 AND asset."projectId" = version."projectId"
                WHERE canon."projectId" = ?
                ORDER BY canon."settingKind", canon."settingId", canon.duty,
                         canon."variantKey", version.id
                """,
                projectId);
        if (rows.isEmpty()) {
            throw new ApiException(
                    409,
                    "VIDEO_STORYBOARD_REFERENCE_REQUIRED",
                    "请先完成至少一份已批准、权利已确认的视觉定妆");
        }
        if (rows.size() > 200) {
            throw invalid(
                    "VIDEO_STORYBOARD_REFERENCE_LIMIT_EXCEEDED",
                    "当前项目视觉参考超过 200 份，不能完整冻结到一次分镜任务");
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Record row : rows) {
            if (!"confirmed".equals(row.get("rightsStatus", String.class))
                    || row.get("lockedAt") == null
                    || !Set.of("image/jpeg", "image/png", "image/webp")
                            .contains(row.get("mimeType", String.class))
                    || !Set.of("identity", "costume", "scene", "prop")
                            .contains(row.get("duty", String.class))) {
                throw new ApiException(
                        409,
                        "VIDEO_STORYBOARD_REFERENCE_INVALID",
                        "当前视觉参考包含未锁定、权利未确认或格式不支持的素材");
            }
            Map<String, Object> reference = new LinkedHashMap<>();
            reference.put("canonVersionId", row.get("id", String.class));
            reference.put("canonContentHash", row.get("contentHash", String.class));
            reference.put("assetId", row.get("assetId", String.class));
            reference.put("sha256", row.get("sha256", String.class));
            reference.put("mimeType", row.get("mimeType", String.class));
            reference.put("duty", row.get("duty", String.class));
            reference.put("defaultStrength", row.get("defaultStrength", Integer.class));
            reference.put("settingName", row.get("settingName", String.class));
            reference.put("label", row.get("label", String.class));
            reference.put(
                    "includeFeatures",
                    stringArray(row.get("includeFeaturesJson", String.class), "正向特征"));
            reference.put(
                    "excludeFeatures",
                    stringArray(row.get("excludeFeaturesJson", String.class), "排除特征"));
            result.add(Map.copyOf(reference));
        }
        return List.copyOf(result);
    }

    private List<String> stringArray(String raw, String label) {
        JsonNode value = json.readTree(raw);
        if (!(value instanceof ArrayNode array) || array.size() > 50) {
            throw new IllegalStateException("视觉参考" + label + "不是不超过 50 项的数组");
        }
        List<String> result = new ArrayList<>();
        for (JsonNode item : array) {
            if (!item.isTextual()) {
                throw new IllegalStateException("视觉参考" + label + "包含非文本值");
            }
            result.add(item.textValue());
        }
        return List.copyOf(result);
    }

    private NormalizedRequest normalize(String episodeId, JsonNode request) {
        String clientRequestId = text(request, "clientRequestId");
        if (clientRequestId.length() < 16 || clientRequestId.length() > 128) {
            throw invalid(
                    "VIDEO_STORYBOARD_CLIENT_REQUEST_ID_INVALID",
                    "clientRequestId 长度必须为 16 至 128 个字符");
        }
        String operation = text(request, "operation");
        if (!OPERATIONS.contains(operation)) {
            throw invalid("VIDEO_STORYBOARD_OPERATION_INVALID", "分镜任务类型无效");
        }
        int expectedRevision = request.path("expectedDraftRevision").asInt(-1);
        if (expectedRevision < 1) {
            throw invalid("VIDEO_STORYBOARD_DRAFT_REVISION_INVALID", "工作稿 revision 必须为正数");
        }
        String scriptVersionId = text(request, "scriptVersionId");
        String instruction = text(request, "instruction").strip();
        int instructionLength = instruction.codePointCount(0, instruction.length());
        if (instruction.isEmpty() || instructionLength > 8_000) {
            throw invalid("VIDEO_STORYBOARD_INSTRUCTION_INVALID", "分镜任务说明长度必须为 1 至 8000 字");
        }
        JsonNode selectedValue = request.path("selectedShotIds");
        if (!selectedValue.isArray() || selectedValue.size() > 300) {
            throw invalid("VIDEO_STORYBOARD_SHOT_SCOPE_INVALID", "分镜修订镜头范围无效");
        }
        List<String> selected = new ArrayList<>();
        selectedValue.forEach(value -> selected.add(requireTextValue(value, "镜头 ID")));
        if (new HashSet<>(selected).size() != selected.size()
                || (operation.equals("episode_storyboard_generate") && !selected.isEmpty())
                || (operation.equals("episode_storyboard_revise") && selected.isEmpty())) {
            throw invalid(
                    "VIDEO_STORYBOARD_SHOT_SCOPE_INVALID",
                    "起草不得携带镜头范围，局部修订必须选择至少一个稳定镜头");
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("episodeId", episodeId);
        body.put("operation", operation);
        body.put("expectedDraftRevision", expectedRevision);
        body.put("scriptVersionId", scriptVersionId);
        body.put("selectedShotIds", List.copyOf(selected));
        body.put("instruction", instruction);
        String requestHash = CommandIdempotency.requestFingerprint(
                "video_episode_storyboard_run.start",
                Map.of("episodeId", episodeId),
                body,
                json);
        return new NormalizedRequest(
                clientRequestId,
                operation,
                expectedRevision,
                scriptVersionId,
                List.copyOf(selected),
                instruction,
                Map.copyOf(body),
                requestHash);
    }

    private List<String> requireShotScope(
            ObjectNode document, String operation, List<String> selectedShotIds) {
        if (!"video-episode-storyboard/1.0".equals(document.path("schemaVersion").asText())) {
            throw invalid("VIDEO_STORYBOARD_DOCUMENT_INVALID", "分镜工作稿版本无效");
        }
        JsonNode shots = document.path("shots");
        if (!shots.isArray() || shots.size() > 300) {
            throw invalid("VIDEO_STORYBOARD_DOCUMENT_INVALID", "工作稿镜头结构无效");
        }
        List<String> stableIds = new ArrayList<>();
        Set<String> unique = new HashSet<>();
        for (JsonNode shot : shots) {
            if (shot.hasNonNull("tempKey") || !shot.hasNonNull("id")) {
                throw invalid(
                        "VIDEO_STORYBOARD_DOCUMENT_INVALID",
                        "发送给模型前，工作稿镜头必须已有 Core 稳定身份");
            }
            String id = text(shot, "id");
            if (!unique.add(id)) {
                throw invalid("VIDEO_STORYBOARD_DOCUMENT_INVALID", "工作稿镜头身份重复");
            }
            stableIds.add(id);
        }
        if (operation.equals("episode_storyboard_revise")
                && !unique.containsAll(selectedShotIds)) {
            throw invalid(
                    "VIDEO_STORYBOARD_SHOT_SCOPE_INVALID",
                    "局部修订只能引用当前冻结工作稿中的稳定镜头");
        }
        return List.copyOf(stableIds);
    }

    private void requireCatalog(ExecutionRegistry.Operation operation) {
        if (!"video".equals(operation.workflow())
                || !OPERATIONS.contains(operation.operation())
                || !operation.targetKinds().contains("video_episode_storyboard")
                || !operation.scopeKinds().contains("episode")
                || !"evidence.video.episode_storyboard.v1".equals(operation.evidencePolicy())
                || !operation.developmentOnly()) {
            throw new IllegalStateException("单集分镜 Operation Catalog 身份不一致");
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
        if (!"episode.storyboard.run".equals(command.get("operation", String.class))
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
            throw new IllegalStateException("分镜任务命令回执已损坏");
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
                ) VALUES (?, ?, ?, ?, ?, ?, 'episode.storyboard.run', ?, ?)
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
                || !"video_episode_storyboard".equals(run.get("targetType", String.class))
                || !episodeId.equals(run.get("targetId", String.class))
                || !"video_episode_storyboard".equals(run.get("sourceType", String.class))
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
                  AND operation IN ('episode_storyboard_generate', 'episode_storyboard_revise')
                  AND "targetType" = 'video_episode_storyboard'
                  AND "targetId" = ?
                  AND "sourceType" = 'video_episode_storyboard'
                  AND "sourceId" = ?
                """,
                runId,
                userId,
                episodeId,
                episodeId);
        if (run == null) {
            throw notFound("VIDEO_STORYBOARD_RUN_NOT_FOUND", "分镜任务不存在或不属于当前分集");
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
                  AND kind::text = 'video_episode_storyboard'
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

    private static String text(JsonNode owner, String field) {
        JsonNode value = owner.get(field);
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw invalid("VIDEO_STORYBOARD_RUN_INPUT_INVALID", field + " 必须是非空字符串");
        }
        return value.textValue();
    }

    private static String requireTextValue(JsonNode value, String label) {
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw invalid("VIDEO_STORYBOARD_SHOT_SCOPE_INVALID", label + " 必须是非空字符串");
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
        return new ApiException(503, "VIDEO_STORYBOARD_WORKFLOW_UNAVAILABLE", message);
    }

    private record NormalizedRequest(
            String clientRequestId,
            String operation,
            int expectedDraftRevision,
            String scriptVersionId,
            List<String> selectedShotIds,
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
