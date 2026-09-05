package cn.inkforge.core.styles.infrastructure;

import static cn.inkforge.core.db.generated.Tables.STYLEREFERENCE;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.styles.application.PortraitRunSubmitter;
import cn.inkforge.core.styles.application.StyleFileStorage;
import cn.inkforge.core.styles.application.StylePortraitExecutionReadiness;
import cn.inkforge.core.styles.application.StylePortraitRunStarter;
import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.core.styles.domain.PortraitTaskSnapshot;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.application.WorkflowInitialStepPlan;
import cn.inkforge.core.workflows.application.WorkflowStartPlan;
import cn.inkforge.core.workflows.application.WorkflowStylePortraitCompletion;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.Clock;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/** 原无请求体画像入口；一次新请求产生服务器内部 key，跨引擎互斥以锁定的 Style 为准。 */
final class JooqStylePortraitRunStarter implements StylePortraitRunStarter {
    private final CoreDatabase database;
    private final JooqStyleRepository repository;
    private final StyleFileStorage storage;
    private final Supplier<PortraitRunSubmitter> legacySubmitter;
    private final Supplier<DurableWorkflowService> workflows;
    private final StylePortraitExecutionReadiness readiness;
    private final ExecutionRegistry registry;
    private final CoreSettings settings;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    JooqStylePortraitRunStarter(CoreDatabase database, JooqStyleRepository repository, StyleFileStorage storage,
            Supplier<PortraitRunSubmitter> legacySubmitter, Supplier<DurableWorkflowService> workflows,
            StylePortraitExecutionReadiness readiness, ExecutionRegistry registry, CoreSettings settings,
            CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database); this.repository = Objects.requireNonNull(repository);
        this.storage = Objects.requireNonNull(storage); this.legacySubmitter = Objects.requireNonNull(legacySubmitter);
        this.workflows = Objects.requireNonNull(workflows); this.readiness = Objects.requireNonNull(readiness);
        this.registry = Objects.requireNonNull(registry); this.settings = Objects.requireNonNull(settings);
        this.ids = Objects.requireNonNull(ids); this.clock = Objects.requireNonNull(clock); this.json = Objects.requireNonNull(json);
    }

    @Override
    public PortraitTaskSnapshot start(String userId, String styleId, PortraitSection section) {
        JooqStyleRepository.requireOwnedStyle(database.dsl(), userId, styleId, false);
        boolean durable = settings.routesNewUserScopedDurableAgentRun(userId)
                && registry.enabledOperationKeys("style", false).contains("style.portrait");
        if (!durable) {
            if (!settings.v1FreshAgentStartsEnabled()) throw new ApiException(503,
                    "AGENT_FRESH_STARTS_DRAINING", "Agent 新建入口正在受控 drain，请稍后重试");
            PortraitRunSubmitter submitter = legacySubmitter.get();
            if (submitter == null) throw unavailable();
            PortraitTaskSnapshot task = repository.createPortraitTask(userId, styleId, section);
            try { submitter.submit(userId, styleId, task.id(), task.id(), section); }
            catch (RuntimeException ignored) {
                // V1 pending 已提交，原 dispatcher 按同一任务继续补投。
            }
            return task;
        }
        if (workflows.get() == null || !readiness.check()) throw unavailable();
        return database.transactionResult(tx -> startDurable(tx, userId, styleId, section));
    }

    private PortraitTaskSnapshot startDurable(DSLContext tx, String userId, String styleId, PortraitSection section) {
        // 新 Run 的 User FK 在 Style 锁之前核验，避免与结果计费的 User→Style 锁序相反。
        if (tx.fetchOne("SELECT id FROM public.\"User\" WHERE id = ? FOR KEY SHARE", userId) == null) {
            throw new ApiException(404, "STYLE_NOT_FOUND", "文风不存在");
        }
        var style = JooqStyleRepository.requireOwnedStyle(tx, userId, styleId, true);
        repository.requireNoActivePortrait(tx, styleId);
        var references = tx.select(STYLEREFERENCE.ID, STYLEREFERENCE.FILENAME,
                        STYLEREFERENCE.FILEPATH, STYLEREFERENCE.CHARCOUNT).from(STYLEREFERENCE)
                .where(STYLEREFERENCE.STYLEID.eq(styleId), STYLEREFERENCE.STATUS.eq("ready"))
                .orderBy(STYLEREFERENCE.CREATEDAT.asc(), STYLEREFERENCE.ID.asc()).fetch();
        if (references.isEmpty()) throw new ApiException(409, "STYLE_REFERENCE_REQUIRED", "请先上传可用的文风参考资料");
        List<Map<String, Object>> frozen = new ArrayList<>();
        List<String> sourceParts = new ArrayList<>();
        int total = 0;
        for (var reference : references) {
            String path = reference.get(STYLEREFERENCE.FILEPATH);
            String filename = reference.get(STYLEREFERENCE.FILENAME);
            Integer count = reference.get(STYLEREFERENCE.CHARCOUNT);
            if (path == null || filename == null || count == null || count < 0) {
                throw new ApiException(409, "STYLE_REFERENCE_INVALID", "文风参考资料元数据无效");
            }
            String content = storage.read(path);
            total = Math.addExact(total, count);
            frozen.add(Map.of("referenceId", reference.get(STYLEREFERENCE.ID), "filename", filename,
                    "charCount", count, "content", content, "contentSha256", DurableStylePortraitEvidence.sha256(content)));
            sourceParts.add("参考资料：" + filename + "\n\n" + content);
        }
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("mode", section == null ? "full" : "section"); input.put("section", section == null ? null : section.value());
        Map<String, Object> context = new LinkedHashMap<>(input);
        context.put("styleId", styleId); context.put("references", frozen); context.put("originalCharCount", total);
        context.put("sourceTextSha256", DurableStylePortraitEvidence.sha256(String.join("\n\n", sourceParts)));
        DurableStylePortraitEvidence.validate(context, styleId, (String) input.get("mode"), (String) input.get("section"));
        var operation = registry.resolve("style.portrait", false);
        if (!operation.operation().targetKinds().contains("style_profile") || !operation.operation().scopeKinds().contains("user")) {
            throw new IllegalStateException("文风画像 Catalog 目标范围不匹配");
        }
        String first = section == null ? WorkflowStylePortraitCompletion.SECTIONS.getFirst() : section.value();
        Map<String, Object> fingerprint = new LinkedHashMap<>(input); fingerprint.put("styleId", styleId);
        WorkflowStartPlan plan = new WorkflowStartPlan(userId, "style-portrait." + ids.next(),
                ExecutionCanonicalJson.sha256(fingerprint), "style", "portrait", registry.catalogVersion(), "chat",
                null, null, null, "style_profile", styleId, input, operation.operation().evidencePolicy(),
                List.of(new WorkflowEvidenceItemPlan("style_portrait_context", styleId, true, null, null,
                        null, context, null, null, Map.of("role", "style_portrait_context"))), operation.operation().runBudget(),
                registry.freezePlan("style.portrait", false), new WorkflowInitialStepPlan("generation", operation.operation().lane(),
                        Map.of("section", first), operation.generatorProfile(), operation.generatorStepBudget(), operation.outputSchema()),
                null, new WorkflowStartPlan.SourceBinding(DurableStylePortraitRun.SOURCE_TYPE, styleId));
        String runId = workflows.get().startFresh(plan).runId();
        if (style.getErrormessage() != null) {
            style.setErrormessage(null); style.setUpdatedat(DatabaseTimestamp.next(clock, style.getUpdatedat())); style.store();
        }
        return Objects.requireNonNull(DurableStylePortraitRun.load(tx, json, runId)).snapshot();
    }

    private static ApiException unavailable() {
        return new ApiException(503, "PORTRAIT_SERVICE_UNAVAILABLE", "画像生成服务暂时不可用");
    }
}
