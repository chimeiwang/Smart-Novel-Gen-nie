package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** V2 Run 与原视频 Task 的不可变绑定；不读取实时 Chapter 或要求当前 PromptHead 未变化。 */
record DurableVideoAdaptationRun(String id, String userId, String novelId, String taskId, String adaptationId,
        String operation, String bundleId) {
    static final String SOURCE_TYPE = "video_adaptation_task_v2";

    static DurableVideoAdaptationRun load(DSLContext tx, ObjectMapper json, String runId) {
        var row = tx.fetchOne("""
                SELECT id,"userId","novelId","chapterId","writingSessionId",workflow,operation,
                  "sourceType","sourceId","targetType","targetId",input,"currentEvidenceBundleId"
                FROM public."WorkflowRun" WHERE id=? AND "engineVersion"=2
                """, runId);
        if (row == null || !"video".equals(row.get("workflow")) || !SOURCE_TYPE.equals(row.get("sourceType"))
                || row.get("novelId") == null || row.get("chapterId") != null || row.get("writingSessionId") != null) {
            throw new IllegalArgumentException("视频 V2 Run 身份无效");
        }
        String operation = row.get("operation", String.class);
        String target = VideoAdaptationTaskPayload.PLAN_WORKFLOW.equals(operation) ? "video_adaptation"
                : VideoAdaptationTaskPayload.PROMPT_WORKFLOW.equals(operation) ? "video_shot_prompt" : null;
        Map<String, Object> input = json.readValue(row.get("input", String.class), new TypeReference<>() {});
        if (target == null || !target.equals(row.get("targetType")) || row.get("targetId") == null
                || !input.keySet().equals(Set.of("taskId")) || !Objects.equals(input.get("taskId"), row.get("sourceId"))) {
            throw new IllegalArgumentException("视频 V2 Run 来源或目标无效");
        }
        return new DurableVideoAdaptationRun(runId, row.get("userId", String.class), row.get("novelId", String.class),
                row.get("sourceId", String.class), row.get("targetId", String.class), operation,
                row.get("currentEvidenceBundleId", String.class));
    }

    Map<String, Object> frozenContext(DSLContext tx, ObjectMapper json) {
        var rows = tx.fetch("""
                SELECT i."resourceType",i."resourceId",i.exists,i."contentType",i."contentJson",
                    i."contentSha256",i."byteCount",i."rangeJson"
                FROM public."WorkflowEvidenceItem" i JOIN public."WorkflowEvidenceBundle" b ON b.id=i."bundleId"
                WHERE b.id=? AND b."runId"=? ORDER BY i.ordinal
                """, bundleId, id);
        if (rows.size() != 1) throw new IllegalArgumentException("视频任务必须包含唯一完整 Evidence");
        var row = rows.getFirst();
        Map<String, Object> context = json.readValue(row.get("contentJson", String.class), new TypeReference<>() {});
        if (!"video_task_context".equals(row.get("resourceType")) || !taskId.equals(row.get("resourceId"))
                || !Boolean.TRUE.equals(row.get("exists")) || !"json".equals(row.get("contentType")) || row.get("rangeJson") != null
                || !ExecutionCanonicalJson.sha256(context).equals(row.get("contentSha256"))
                || ExecutionCanonicalJson.bytes(context).length != row.get("byteCount", Long.class)
                || !context.keySet().equals(Set.of("taskId", "payload", "inheritedCheckpoint"))
                || !taskId.equals(context.get("taskId")) || !(context.get("payload") instanceof Map<?, ?>)) {
            throw new IllegalArgumentException("视频任务 Evidence 绑定无效");
        }
        var payload = VideoAdaptationTaskPayload.parse(json, json.writeValueAsString(context.get("payload")));
        if (!adaptationId.equals(payload.adaptationId()) || !operation.equals(payload.workflow())
                || (payload.isPrompt() && context.get("inheritedCheckpoint") != null)) {
            throw new IllegalArgumentException("视频任务 Evidence 来源范围无效");
        }
        if (context.get("inheritedCheckpoint") != null) json.convertValue(context.get("inheritedCheckpoint"),
                cn.inkforge.contracts.api.DramaticStructureCheckpoint.class);
        return context;
    }
}
