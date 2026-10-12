package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.core.lore.infrastructure.JooqLoreRepository;
import cn.inkforge.core.outlines.infrastructure.JooqOutlineRepository;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.references.infrastructure.ReferenceRepositoryTestFactory;
import cn.inkforge.core.reviews.application.AgentUpdatesExecutor;
import cn.inkforge.core.reviews.application.ReviewRepository;
import cn.inkforge.core.workflows.application.WorkflowStructuredCandidatePreparation;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.time.Clock;
import java.util.List;
import java.util.Map;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 仅测试的跨模块装配：复用真实审核实现与已注册的测试模型，绝不修改部署资产。 */
public final class AgentUpdatesReviewTestSupport {
    private AgentUpdatesReviewTestSupport() {}

    public static WorkflowStructuredCandidatePreparation preparation(ObjectMapper json) {
        return new ReviewConfiguration().structuredCandidatePreparation(json);
    }

    public static ReviewRepository repository(CoreDatabase database, CuidV1Generator ids, Clock clock, ObjectMapper json, ExecutionRegistry registry) {
        var writer = new AgentUpdatesExecutor(new JooqLoreRepository(database, ids, clock), new JooqOutlineRepository(database, ids, clock),
                ReferenceRepositoryTestFactory.create(database, ids, clock), ids, false);
        return new JooqReviewRepository(database, ids, clock, json, new JooqFormalArtifactWriter(database, ids, clock, json, writer), registry, true);
    }

    public static ExecutionRegistry.ResolvedOperation operation(ExecutionRegistry registry, ObjectMapper json, String name) {
        var base = registry.resolve("long_serial.plan_chapter", false);
        var old = base.operation();
        ExecutionRegistry.OutputSchema schema = null;
        try (var stream = AgentUpdatesReviewTestSupport.class.getResourceAsStream("/agent-execution/output-schema-registry.v1.json")) {
            Map<String, Object> document = json.readValue(stream, new TypeReference<>() {});
            for (Object raw : (List<?>) document.get("schemas")) {
                if ("output.agent_updates.v2".equals(((Map<?, ?>) raw).get("key"))) schema = json.convertValue(raw, ExecutionRegistry.OutputSchema.class);
            }
        } catch (java.io.IOException error) { throw new IllegalStateException("测试输出契约读取失败", error); }
        if (schema == null) throw new IllegalStateException("测试输出契约缺失");
        var review = old.reviewPolicy();
        var policy = new ExecutionRegistry.ReviewPolicy(review.profile(), review.mode(), review.reviewerProfiles(), review.reviewerStepBudgetProfiles(),
                review.reviewerOutputSchema(), review.rubricVersion(), review.evidencePolicy(), review.lane(), "review.merge_all_pass_else_author.v1",
                review.maxAutomaticRevisions(), review.onUnavailable());
        var operation = new ExecutionRegistry.Operation("long_serial." + name, "long_serial", name, List.of("novel"), List.of("novel"),
                true, false, true, old.lane(), old.evidencePolicy(), old.generatorProfile(), old.generatorStepBudgetProfile(), schema.key(),
                old.deterministicValidators(), policy, "apply.agent_updates.v1", old.runBudget());
        return new ExecutionRegistry.ResolvedOperation(operation, base.generatorProfile(), base.generatorStepBudget(), schema, base.reviewers(), base.reviewerOutputSchema());
    }
}
