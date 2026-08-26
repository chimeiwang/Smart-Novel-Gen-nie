package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERBEATPLAN;
import static cn.inkforge.core.db.generated.Tables.CHAPTERWRITINGGOAL;
import static cn.inkforge.core.db.generated.Tables.FORESHADOWING;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINENODE;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.SCENEBEAT;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.core.db.generated.enums.Beatplanstatus;
import cn.inkforge.core.db.generated.enums.Outlinenodekind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.tables.records.ChapterbeatplanRecord;
import cn.inkforge.core.db.generated.tables.records.ChapterwritinggoalRecord;
import cn.inkforge.core.db.generated.tables.records.ForeshadowingRecord;
import cn.inkforge.core.db.generated.tables.records.OutlinenodeRecord;
import cn.inkforge.core.db.generated.tables.records.ReviewartifactRecord;
import cn.inkforge.core.db.generated.tables.records.ScenebeatRecord;
import cn.inkforge.core.db.generated.tables.records.WritingruncommandRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.writing.application.WritingCommandPayload;
import cn.inkforge.core.writing.application.WritingContextRepository;
import cn.inkforge.core.writing.domain.WritingGraphSnapshot;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 从 PostgreSQL 权威事实重建 Agent 写作规划上下文。
 *
 * <p>上下文包含批准的 Beat Plan、章节组路径、伏笔摘要、活动 Artifact 与首个 start 命令冻结的来源绑定；
 * Redis/SSE 只负责观察，不能参与重建。持久 JSON 采用严格字段与资源身份校验，损坏时停止模型调用而非猜测补全。
 */
final class JooqWritingContextRepository implements WritingContextRepository {

    private static final Set<String> ACTIVE_COMMANDS = Set.of("pending", "submitted", "processing");
    private static final Set<Reviewartifactstatus> ACTIVE_ARTIFACTS = Set.of(
            Reviewartifactstatus.draft,
            Reviewartifactstatus.under_review,
            Reviewartifactstatus.awaiting_user,
            Reviewartifactstatus.applying);
    private static final Set<String> SOURCE_BINDING_FIELDS = Set.of(
            "resourceType",
            "resourceId",
            "exists",
            "updatedAt",
            "contentSha256",
            "revision",
            "absenceSentinel");

    private final CoreDatabase database;
    private final ObjectMapper json;

    JooqWritingContextRepository(CoreDatabase database, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public void requireBinding(String userId, String novelId, String taskId) {
        String found = database.dsl()
                .select(WRITINGTASK.ID)
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(
                        WRITINGTASK.ID.eq(taskId),
                        WRITINGTASK.NOVELID.eq(novelId),
                        NOVEL.USERID.eq(userId))
                .fetchOne(WRITINGTASK.ID);
        if (found == null) {
            throw new ApiException(403, "WRITING_TASK_FORBIDDEN", "写作任务资源绑定不匹配");
        }
    }

    @Override
    public void requireWritingJob(
            String userId, String novelId, String taskId, String jobId) {
        String found = database.dsl()
                .select(WRITINGRUNCOMMAND.ID)
                .from(WRITINGRUNCOMMAND)
                .join(WRITINGTASK)
                .on(WRITINGTASK.ID.eq(WRITINGRUNCOMMAND.TASKID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(
                        WRITINGRUNCOMMAND.ID.eq(jobId),
                        WRITINGRUNCOMMAND.TASKID.eq(taskId),
                        WRITINGTASK.NOVELID.eq(novelId),
                        NOVEL.USERID.eq(userId),
                        WRITINGRUNCOMMAND.STATUS.in(ACTIVE_COMMANDS))
                .fetchOne(WRITINGRUNCOMMAND.ID);
        if (found == null) {
            throw new ApiException(409, "WRITING_JOB_MISMATCH", "写入工具作业不是当前活动命令");
        }
    }

    @Override
    public Map<String, Object> planningContext(String userId, String taskId) {
        return database.transactionResult(transaction -> planningContext(
                transaction, userId, taskId));
    }

    private Map<String, Object> planningContext(
            DSLContext transaction, String userId, String taskId) {
        WritingtaskRecord task = transaction.select(WRITINGTASK.fields())
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGTASK.ID.eq(taskId), NOVEL.USERID.eq(userId))
                .fetchOneInto(WRITINGTASK);
        if (task == null) {
            throw new ApiException(403, "WRITING_TASK_FORBIDDEN", "无权访问该写作任务");
        }
        Integer chapterOrder = transaction.select(CHAPTER.ORDER)
                .from(CHAPTER)
                .where(
                        CHAPTER.ID.eq(task.getChapterid()),
                        CHAPTER.NOVELID.eq(task.getNovelid()))
                .fetchOne(CHAPTER.ORDER);
        if (chapterOrder == null) {
            throw new ApiException(403, "WRITING_TASK_FORBIDDEN", "无权访问该写作任务");
        }
        OutlinenodeRecord group = chapterGroup(transaction, task.getNovelid(), chapterOrder);
        ChapterwritinggoalRecord goal = transaction.selectFrom(CHAPTERWRITINGGOAL)
                .where(CHAPTERWRITINGGOAL.CHAPTERID.eq(task.getChapterid()))
                .orderBy(
                        CHAPTERWRITINGGOAL.UPDATEDAT.desc(),
                        CHAPTERWRITINGGOAL.ID.desc())
                .limit(1)
                .fetchOne();
        ChapterbeatplanRecord plan = transaction.selectFrom(CHAPTERBEATPLAN)
                .where(
                        CHAPTERBEATPLAN.CHAPTERID.eq(task.getChapterid()),
                        CHAPTERBEATPLAN.STATUS.eq(Beatplanstatus.approved))
                .orderBy(CHAPTERBEATPLAN.UPDATEDAT.desc(), CHAPTERBEATPLAN.ID.desc())
                .limit(1)
                .fetchOne();
        List<ScenebeatRecord> scenes = plan == null
                ? List.of()
                : transaction.selectFrom(SCENEBEAT)
                        .where(SCENEBEAT.BEATPLANID.eq(plan.getId()))
                        .orderBy(SCENEBEAT.ORDER.asc(), SCENEBEAT.ID.asc())
                        .fetch();
        List<Map<String, Object>> history = conversation(task.getConversationhistory());
        CurrentMessage current = currentMessage(history);
        Map<String, Object> graph = task.getGraphstatejson() == null
                ? null
                : jsonObject(task.getGraphstatejson(), snapshotInvalid());

        // 返回的是一个同事务读取的规划快照；Agent 不应再分别回读这些表并自行决定“当前”版本。
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("taskId", task.getId());
        result.put("novelId", task.getNovelid());
        result.put("chapterId", task.getChapterid());
        result.put("chapterOrder", chapterOrder);
        result.put("chapterGoal", goal(goal));
        result.put("approvedBeatPlan", beatPlan(plan, scenes));
        result.put("chapterGroup", group(group));
        result.put("outlinePath", group == null ? List.of() : outlinePath(transaction, group));
        result.put("foreshadowingSummaries", foreshadowingSummaries(transaction, task.getNovelid()));
        result.put("activeArtifact", activeArtifact(transaction, task, userId));
        result.put("sourceBindings", sourceBindings(transaction, task.getId()));
        result.put("phase", task.getPhase().getLiteral());
        result.put("targetWordCount", task.getTargetwordcount());
        result.put(
                "selectedAgents",
                java.util.Arrays.stream(task.getSelectedagents().split(",", -1))
                        .filter(value -> !value.isEmpty())
                        .toList());
        result.put("conversationHistory", current.history());
        result.put("userMessage", current.message());
        result.put("graphState", graph);
        return result;
    }

    private static OutlinenodeRecord chapterGroup(
            DSLContext transaction, String novelId, int chapterOrder) {
        List<OutlinenodeRecord> matches = transaction.selectFrom(OUTLINENODE)
                .where(
                        OUTLINENODE.NOVELID.eq(novelId),
                        OUTLINENODE.KIND.eq(Outlinenodekind.chapter_group))
                .fetch()
                .stream()
                .filter(group -> value(group.getChapterstartorder()) <= chapterOrder
                        && chapterOrder <= value(group.getChapterendorder()))
                .toList();
        if (matches.size() > 1) {
            throw new ApiException(
                    409,
                    "CHAPTER_GROUP_MAPPING_CONFLICT",
                    "当前章节没有唯一对应的章节组，不能调用写作模型");
        }
        return matches.isEmpty() ? null : matches.getFirst();
    }

    private static int value(Integer value) {
        return value == null ? 0 : value;
    }

    private static Map<String, Object> goal(ChapterwritinggoalRecord goal) {
        if (goal == null) return null;
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", goal.getId());
        result.put("narrativeGoal", goal.getNarrativegoal());
        result.put("desiredEmotion", goal.getDesiredemotion());
        result.put("requiredForeshadowing", goal.getRequiredforeshadowing());
        result.put("requiredCharacters", goal.getRequiredcharacters());
        result.put("wordCountMin", goal.getWordcountmin());
        result.put("wordCountMax", goal.getWordcountmax());
        result.put("specialNotes", goal.getSpecialnotes());
        return result;
    }

    private static Map<String, Object> beatPlan(
            ChapterbeatplanRecord plan, List<ScenebeatRecord> scenes) {
        if (plan == null) return null;
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", plan.getId());
        result.put("chapterGoal", plan.getChaptergoal());
        result.put("mainPlotConnection", plan.getMainplotconnection());
        result.put("chapterAcceptanceCriteria", plan.getChapteracceptancecriteria());
        result.put("totalEstimatedWords", plan.getTotalestimatedwords());
        result.put("generatedBy", plan.getGeneratedby());
        result.put("sceneBeats", scenes.stream().map(JooqWritingContextRepository::scene).toList());
        return result;
    }

    private static Map<String, Object> scene(ScenebeatRecord scene) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", scene.getId());
        result.put("order", scene.getOrder());
        result.put("goal", scene.getGoal());
        result.put("conflict", scene.getConflict());
        result.put("characters", scene.getCharacters());
        result.put("foreshadowingRefs", scene.getForeshadowingrefs());
        result.put("estimatedWords", scene.getEstimatedwords());
        result.put("acceptanceCriteria", scene.getAcceptancecriteria());
        return result;
    }

    private static Map<String, Object> group(OutlinenodeRecord group) {
        if (group == null) return null;
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", group.getId());
        result.put("title", group.getTitle());
        result.put("chapterStartOrder", value(group.getChapterstartorder()));
        result.put("chapterEndOrder", value(group.getChapterendorder()));
        result.put("content", Objects.toString(group.getContent(), ""));
        return result;
    }

    private static List<Map<String, Object>> outlinePath(
            DSLContext transaction, OutlinenodeRecord group) {
        List<Map<String, Object>> path = new ArrayList<>();
        Set<String> visited = new HashSet<>();
        String parentId = group.getParentid();
        while (parentId != null) {
            if (!visited.add(parentId)) {
                throw new ApiException(409, "OUTLINE_PARENT_CYCLE", "章节组父级大纲节点存在循环");
            }
            OutlinenodeRecord node = transaction.selectFrom(OUTLINENODE)
                    .where(OUTLINENODE.ID.eq(parentId))
                    .fetchOne();
            if (node == null) {
                throw new ApiException(409, "OUTLINE_PARENT_MISSING", "章节组父级大纲节点不存在");
            }
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("id", node.getId());
            value.put("kind", node.getKind().getLiteral());
            value.put("title", node.getTitle());
            value.put("chapterStartOrder", node.getChapterstartorder());
            value.put("chapterEndOrder", node.getChapterendorder());
            path.add(value);
            parentId = node.getParentid();
        }
        Collections.reverse(path);
        return List.copyOf(path);
    }

    private static List<Map<String, Object>> foreshadowingSummaries(
            DSLContext transaction, String novelId) {
        return transaction.selectFrom(FORESHADOWING)
                .where(FORESHADOWING.NOVELID.eq(novelId))
                .orderBy(FORESHADOWING.CREATEDAT.asc(), FORESHADOWING.ID.asc())
                .fetch()
                .stream()
                .map(JooqWritingContextRepository::foreshadowingSummary)
                .toList();
    }

    private static Map<String, Object> foreshadowingSummary(ForeshadowingRecord value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", value.getId());
        result.put("name", value.getName());
        result.put("status", value.getStatus().getLiteral());
        result.put("plantedAt", value.getPlantedat());
        result.put("expectedPayoff", value.getExpectedpayoff());
        result.put("payoffAt", value.getPayoffat());
        return result;
    }

    private Map<String, Object> activeArtifact(
            DSLContext transaction, WritingtaskRecord task, String userId) {
        if (task.getGraphstatejson() == null) return null;
        Map<String, Object> raw = jsonObject(task.getGraphstatejson(), snapshotInvalid());
        if ("short_medium".equals(raw.get("workflow"))) return null;
        WritingGraphSnapshot.Parsed snapshot;
        try {
            snapshot = WritingGraphSnapshot.parse(
                    task.getGraphstatejson(),
                    json,
                    task.getId(),
                    userId,
                    task.getNovelid(),
                    task.getChapterid());
        } catch (IllegalArgumentException exception) {
            throw snapshotInvalid();
        }
        if (snapshot.activeArtifactId() == null) return null;
        ReviewartifactRecord artifact = transaction.selectFrom(REVIEWARTIFACT)
                .where(
                        REVIEWARTIFACT.ID.eq(snapshot.activeArtifactId()),
                        REVIEWARTIFACT.TASKID.eq(task.getId()),
                        REVIEWARTIFACT.NOVELID.eq(task.getNovelid()))
                .fetchOne();
        if (artifact != null && ACTIVE_ARTIFACTS.contains(artifact.getStatus())) {
            Map<String, Object> payload = jsonObject(
                    artifact.getPayloadjson(), artifactPayloadInvalid());
            if (!Objects.equals(payload.get("kind"), artifact.getKind().getLiteral())) {
                throw artifactPayloadInvalid();
            }
            Object diff = artifact.getDiffjson() == null
                    ? null
                    : jsonValue(artifact.getDiffjson(), artifactPayloadInvalid());
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("id", artifact.getId());
            result.put("taskId", artifact.getTaskid());
            result.put("novelId", artifact.getNovelid());
            result.put("chapterId", artifact.getChapterid());
            result.put("workflowRunId", artifact.getWorkflowrunid());
            result.put("artifactKey", artifact.getArtifactkey());
            result.put("kind", artifact.getKind().getLiteral());
            result.put("status", artifact.getStatus().getLiteral());
            result.put("title", artifact.getTitle());
            result.put("summary", artifact.getSummary());
            result.put("payload", payload);
            result.put("diff", diff);
            result.put("createdByAgent", artifact.getCreatedbyagent());
            result.put("reviewerAgent", artifact.getRevieweragent());
            result.put("revision", artifact.getRevision());
            return result;
        }
        // 应用命令进行中时 Artifact 可暂时退出活动状态；只有不存在活动决定命令才判定快照损坏。
        String activeDecision = transaction.select(WRITINGRUNCOMMAND.ID)
                .from(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.TASKID.eq(task.getId()),
                        WRITINGRUNCOMMAND.ARTIFACTID.eq(snapshot.activeArtifactId()),
                        WRITINGRUNCOMMAND.KIND.eq("artifact_decision"),
                        WRITINGRUNCOMMAND.STATUS.in(ACTIVE_COMMANDS))
                .fetchOne(WRITINGRUNCOMMAND.ID);
        if (activeDecision != null) return null;
        throw new ApiException(
                409, "ACTIVE_ARTIFACT_MISMATCH", "稳定快照引用的待审核草案与任务不匹配");
    }

    private List<Map<String, Object>> sourceBindings(
            DSLContext transaction, String taskId) {
        WritingruncommandRecord command = transaction.selectFrom(WRITINGRUNCOMMAND)
                .where(
                        WRITINGRUNCOMMAND.TASKID.eq(taskId),
                        WRITINGRUNCOMMAND.KIND.eq("start"))
                .orderBy(WRITINGRUNCOMMAND.CREATEDAT.asc(), WRITINGRUNCOMMAND.ID.asc())
                .limit(1)
                .fetchOne();
        // 来源绑定属于最初 start 命令的不可变输入，不能从后来变化的设定/章节重新计算。
        if (command == null) return List.of();
        Map<String, Object> job;
        try {
            job = WritingCommandPayload.parse(command.getKind(), command.getPayloadjson(), json).job();
        } catch (RuntimeException exception) {
            throw sourceBindingsInvalid();
        }
        Object rawBindings = job.get("sourceBindings");
        if (rawBindings == null) return List.of();
        if (!(rawBindings instanceof List<?> values)) throw sourceBindingsInvalid();
        List<Map<String, Object>> result = new ArrayList<>(values.size());
        for (Object value : values) result.add(sourceBinding(value));
        return List.copyOf(result);
    }

    private static Map<String, Object> sourceBinding(Object raw) {
        if (!(raw instanceof Map<?, ?> map)) throw sourceBindingsInvalid();
        Map<String, Object> value = stringMap(map, sourceBindingsInvalid());
        if (!value.keySet().equals(SOURCE_BINDING_FIELDS)
                || !(value.get("resourceType") instanceof String resourceType)
                || resourceType.isEmpty()
                || !(value.get("resourceId") instanceof String resourceId)
                || resourceId.isEmpty()
                || !(value.get("exists") instanceof Boolean exists)
                || (value.get("revision") != null
                        && (!(value.get("revision") instanceof Number revision)
                                || revision.intValue() < 0
                                || revision.doubleValue() != revision.intValue()))) {
            throw sourceBindingsInvalid();
        }
        Map<String, Object> normalized = new LinkedHashMap<>();
        normalized.put("resourceType", resourceType);
        normalized.put("resourceId", resourceId);
        normalized.put("exists", exists);
        if (exists) {
            Object rawUpdatedAt = value.get("updatedAt");
            Object hash = value.get("contentSha256");
            if (!(rawUpdatedAt instanceof String updatedAt)
                    || !(hash instanceof String digest)
                    || !digest.matches("[0-9a-f]{64}")
                    || value.get("absenceSentinel") != null) {
                throw sourceBindingsInvalid();
            }
            try {
                normalized.put(
                        "updatedAt",
                        OffsetDateTime.parse(updatedAt)
                                .withOffsetSameInstant(ZoneOffset.UTC)
                                .toInstant()
                                .toString());
            } catch (RuntimeException exception) {
                throw sourceBindingsInvalid();
            }
            normalized.put("contentSha256", digest);
            normalized.put(
                    "revision",
                    value.get("revision") == null
                            ? null
                            : ((Number) value.get("revision")).intValue());
            normalized.put("absenceSentinel", null);
        } else {
            if (value.get("updatedAt") != null
                    || value.get("contentSha256") != null
                    || value.get("revision") != null
                    || !(value.get("absenceSentinel") instanceof Map<?, ?> sentinel)) {
                throw sourceBindingsInvalid();
            }
            Map<String, Object> absence = stringMap(sentinel, sourceBindingsInvalid());
            if (!absence.keySet().equals(Set.of("resourceType", "resourceId"))
                    || !(absence.get("resourceType") instanceof String type)
                    || type.isEmpty()
                    || !(absence.get("resourceId") instanceof String id)
                    || id.isEmpty()) {
                throw sourceBindingsInvalid();
            }
            normalized.put("updatedAt", null);
            normalized.put("contentSha256", null);
            normalized.put("revision", null);
            normalized.put("absenceSentinel", Map.of("resourceType", type, "resourceId", id));
        }
        return normalized;
    }

    private List<Map<String, Object>> conversation(String serialized) {
        if (serialized == null || serialized.isEmpty()) return List.of();
        Object parsed = jsonValue(serialized, conversationInvalid());
        if (!(parsed instanceof List<?> values)) throw conversationInvalid();
        List<Map<String, Object>> result = new ArrayList<>(values.size());
        for (Object value : values) {
            if (!(value instanceof Map<?, ?> map)) throw conversationInvalid();
            result.add(stringMap(map, conversationInvalid()));
        }
        return result;
    }

    private static CurrentMessage currentMessage(List<Map<String, Object>> history) {
        for (int index = history.size() - 1; index >= 0; index--) {
            Map<String, Object> value = history.get(index);
            if ("user".equals(value.get("role")) && value.get("content") instanceof String text) {
                List<Map<String, Object>> prior = new ArrayList<>(history);
                prior.remove(index);
                return new CurrentMessage(List.copyOf(prior), text);
            }
        }
        return new CurrentMessage(List.copyOf(history), "");
    }

    private Map<String, Object> jsonObject(String serialized, ApiException failure) {
        Object value = jsonValue(serialized, failure);
        if (!(value instanceof Map<?, ?> map)) throw failure;
        return stringMap(map, failure);
    }

    private Object jsonValue(String serialized, ApiException failure) {
        try {
            return json.readValue(serialized, new TypeReference<Object>() {});
        } catch (RuntimeException exception) {
            throw failure;
        }
    }

    private static Map<String, Object> stringMap(Map<?, ?> value, ApiException failure) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) throw failure;
            result.put(key, entry.getValue());
        }
        return result;
    }

    private static ApiException snapshotInvalid() {
        return new ApiException(409, "WRITING_SNAPSHOT_INVALID", "写作任务稳定快照格式错误");
    }

    private static ApiException artifactPayloadInvalid() {
        return new ApiException(409, "ARTIFACT_PAYLOAD_INVALID", "待审核草案的持久化内容格式无效");
    }

    private static ApiException sourceBindingsInvalid() {
        return new ApiException(409, "WRITING_SOURCE_BINDINGS_INVALID", "写作任务的冻结来源格式无效");
    }

    private static ApiException conversationInvalid() {
        return new ApiException(409, "WRITING_CONVERSATION_INVALID", "写作任务对话历史格式错误");
    }

    private record CurrentMessage(List<Map<String, Object>> history, String message) {}
}
