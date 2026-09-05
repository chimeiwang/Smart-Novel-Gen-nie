package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;
import org.jooq.DSLContext;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 原业务事务只登记冻结的执行授权；调度关闭或网络不可达都不会偷偷切换已绑定任务的引擎。 */
final class JooqVideoModelRunStarter {
    private final CoreSettings settings;
    private final ExecutionRegistry registry;
    private final Supplier<DurableWorkflowService> workflows;
    private final ObjectMapper json;

    JooqVideoModelRunStarter(CoreSettings settings, ExecutionRegistry registry,
            Supplier<DurableWorkflowService> workflows, ObjectMapper json) {
        this.settings = Objects.requireNonNull(settings); this.registry = Objects.requireNonNull(registry);
        this.workflows = Objects.requireNonNull(workflows); this.json = Objects.requireNonNull(json);
    }

    void bind(String userId, String novelId, String taskId, String payloadJson, String inheritedJson) {
        var payload = VideoAdaptationTaskPayload.parse(json, payloadJson);
        String key = "video." + payload.workflow();
        boolean development = settings.environment() != CoreSettings.EnvironmentName.PRODUCTION;
        if (!development || !settings.routesNewDurableAgentRun(userId, novelId)
                || !registry.enabledOperationKeys("video", true).contains(key)) return;
        var service = workflows.get();
        if (service == null) throw new ApiException(503, "VIDEO_ADAPTATION_SERVICE_UNAVAILABLE", "章节影视化执行服务暂时不可用");
        var operation = registry.resolve(key, true);
        String stageKey = payload.isPrompt() ? "shot_prompt" : inheritedJson == null ? "dramatic_structure" : "shot_design";
        var stage = operation.stageSteps().stream().filter(value -> stageKey.equals(value.stageKey())).findFirst()
                .orElseThrow(() -> new IllegalStateException("视频冻结计划缺少首阶段"));
        Map<String, Object> inherited = inheritedJson == null ? null
                : json.readValue(inheritedJson, new TypeReference<>() {});
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("taskId", taskId); context.put("payload", payload.agentPayload()); context.put("inheritedCheckpoint", inherited);
        Map<String, Object> input = Map.of("taskId", taskId);
        Map<String, Object> first = new LinkedHashMap<>();
        first.put("stageKey", stageKey); first.put("cycle", 0); first.put("correction", false);
        first.put("dependencies", List.of()); first.put("correctionFindings", List.of());
        if (inherited != null) { first.put("checkpoint", inherited); first.put("requiredChanges", List.of()); }
        var plan = new WorkflowStartPlan(userId, "video-model." + taskId,
                ExecutionCanonicalJson.sha256(Map.of("taskId", taskId, "novelId", novelId, "context", context)),
                "video", payload.workflow(), registry.catalogVersion(), "chat", novelId, null, null,
                payload.isPlan() ? "video_adaptation" : "video_shot_prompt", payload.adaptationId(), input,
                operation.operation().evidencePolicy(), List.of(new WorkflowEvidenceItemPlan("video_task_context", taskId,
                        true, null, null, null, context, null, null, Map.of("role", "video_task_context"))),
                operation.operation().runBudget(), registry.freezePlan(key, true),
                new WorkflowInitialStepPlan("generation", operation.operation().lane(), first,
                        stage.profile(), stage.stepBudget(), stage.outputSchema()), null,
                new WorkflowStartPlan.SourceBinding(DurableVideoAdaptationRun.SOURCE_TYPE, taskId));
        service.startFresh(plan);
    }

    static void lockStartOwner(DSLContext tx, String userId) {
        if (tx.fetchOne("SELECT id FROM public.\"User\" WHERE id=? FOR KEY SHARE", userId) == null) {
            throw new ApiException(404, "VIDEO_PROJECT_NOT_FOUND", "视频项目不存在");
        }
    }
}
