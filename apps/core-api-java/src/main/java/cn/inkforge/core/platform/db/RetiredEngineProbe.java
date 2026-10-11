package cn.inkforge.core.platform.db;

import java.util.LinkedHashMap;
import java.util.Map;
import tools.jackson.databind.ObjectMapper;

/** 发布探针只读验证旧结构可读取，并明确报告旧执行与账务是否仍需收尾。 */
public final class RetiredEngineProbe {
    private RetiredEngineProbe() {}

    public static void main(String[] args) throws Exception {
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("engineRetired", missing("cn.inkforge.core.workflows.application.WorkflowStepDispatcher")
                && missing("cn.inkforge.core.workflows.infrastructure.JooqWorkflowCallbackRepository")
                && missing("cn.inkforge.core.agentgateway.WorkflowAgentExecutionSubmitter")
                && missing("cn.inkforge.core.workflows.catalog.ExecutionRegistry"));
        // 契约是历史数据库结构事实，保留它并不重新开放模型执行能力。
        report.put("legacySchemaSupported", SchemaContracts.loadPostDurableAgentV2() != null);
        if (args.length == 1 && "--database".equals(args[0])) {
            try (CoreDatabase db = CoreDatabase.connect(PostgresConnectionSettings.parse(System.getenv("DATABASE_URL")))) {
                report.put("activeV2Runs", count(db, """
                        SELECT count(*) FROM public."WorkflowRun"
                        WHERE "engineVersion" = 2 AND status::text NOT IN ('completed','failed','cancelled')
                        """));
                report.put("nonterminalV2Steps", count(db, """
                        SELECT count(*) FROM public."WorkflowStep" s
                        JOIN public."WorkflowRun" r ON r.id = s."runId"
                        WHERE r."engineVersion" = 2 AND s.status::text NOT IN ('completed','failed','skipped','cancelled')
                        """));
                report.put("unsettledReservations", count(db, """
                        SELECT count(*) FROM public."WorkflowBillingReservation"
                        WHERE status IN ('reserved','reconciliation_required')
                        """));
                report.put("unknownProviderUsage", count(db, """
                        SELECT count(*) FROM public."WorkflowStep" s
                        JOIN public."WorkflowRun" r ON r.id = s."runId"
                        WHERE r."engineVersion" = 2
                          AND s."usageJson"::jsonb ->> 'usageStatus' = 'unknown'
                          AND COALESCE((s."usageJson"::jsonb ->> 'providerAttempts')::int, 0) > 0
                        """));
            }
        } else if (args.length != 0) {
            throw new IllegalArgumentException("探针仅接受可选 --database");
        }
        System.out.println(new ObjectMapper().writeValueAsString(report));
        if (!Boolean.TRUE.equals(report.get("engineRetired"))) System.exit(2);
    }

    private static long count(CoreDatabase database, String sql) {
        return database.dsl().fetchOne(sql).get(0, Long.class);
    }

    private static boolean missing(String type) {
        try {
            Class.forName(type, false, RetiredEngineProbe.class.getClassLoader());
            return false;
        } catch (ClassNotFoundException expected) {
            return true;
        }
    }
}
