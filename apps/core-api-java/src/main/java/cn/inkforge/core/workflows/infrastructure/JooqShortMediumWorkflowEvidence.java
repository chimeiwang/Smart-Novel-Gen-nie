package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.contracts.api.ResolvedModelRef;
import cn.inkforge.contracts.api.StepUsage;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.catalog.ExecutionPlanSnapshot;
import cn.inkforge.core.workflows.domain.ShortMediumSegments;
import cn.inkforge.core.workflows.domain.ShortMediumSegments.Segment;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.workflows.protocol.ExecutionProtocolDateTime;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 校验短篇当前来源清单与全部已完成段，下一段只复制这些冻结事实，不读可变工作稿。 */
final class JooqShortMediumWorkflowEvidence {
    private final ObjectMapper json;

    JooqShortMediumWorkflowEvidence(ObjectMapper json) { this.json = Objects.requireNonNull(json); }

    Snapshot load(DSLContext tx, String runId, String novelId, String bundleId, ExecutionPlanSnapshot plan) {
        Record bundle = tx.fetchOne("SELECT * FROM public.\"WorkflowEvidenceBundle\" WHERE id = ? AND \"runId\" = ?", bundleId, runId);
        if (bundle == null || !plan.generator().evidencePolicy().equals(bundle.get("policyVersion", String.class))) {
            throw invalid("冻结来源不存在或策略不一致");
        }
        List<Record> rows = tx.fetch("SELECT * FROM public.\"WorkflowEvidenceItem\" WHERE \"bundleId\" = ? ORDER BY ordinal", bundleId);
        if (rows.isEmpty() || rows.size() > 6) throw invalid("来源必须包含唯一上下文和最多五个已完成段");
        List<Map<String, Object>> manifestItems = new ArrayList<>();
        List<WorkflowEvidenceItemPlan> items = new ArrayList<>();
        long totalBytes = 0;
        for (int index = 0; index < rows.size(); index++) {
            Record row = rows.get(index);
            String type = index == 0 ? "short_medium_context" : "short_medium_segment";
            if (!Integer.valueOf(index + 1).equals(row.get("ordinal", Integer.class))
                    || !type.equals(row.get("resourceType", String.class))
                    || !Boolean.TRUE.equals(row.get("exists", Boolean.class))
                    || !"json".equals(row.get("contentType", String.class))
                    || row.get("contentText") != null || row.get("rangeJson") != null
                    || index == 0 && !novelId.equals(row.get("resourceId", String.class))) {
                throw invalid("上下文或已完成段来源身份无效");
            }
            Map<String, Object> content = read(row.get("contentJson", String.class));
            long bytes = ExecutionCanonicalJson.bytes(content).length;
            String hash = ExecutionCanonicalJson.sha256(content);
            if (!hash.equals(row.get("contentSha256", String.class)) || !Long.valueOf(bytes).equals(row.get("byteCount", Long.class))) {
                throw invalid("来源原文、哈希或字节数不一致");
            }
            Map<String, Object> metadata = read(row.get("metadataJson", String.class));
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("itemId", row.get("id", String.class));
            entry.put("ordinal", index + 1);
            entry.put("resourceType", type);
            entry.put("resourceId", row.get("resourceId", String.class));
            entry.put("exists", true);
            Integer revision = row.get("resourceRevision", Integer.class);
            if (revision != null) entry.put("resourceRevision", revision);
            LocalDateTime updatedAt = row.get("resourceUpdatedAt", LocalDateTime.class);
            if (updatedAt != null) entry.put("resourceUpdatedAt", ExecutionProtocolDateTime.format(DatabaseTimestamp.api(updatedAt)));
            entry.put("contentType", "json");
            entry.put("contentSha256", hash);
            entry.put("byteCount", bytes);
            entry.put("metadata", metadata);
            manifestItems.add(entry);
            items.add(new WorkflowEvidenceItemPlan(type, row.get("resourceId", String.class), true, revision,
                    DatabaseTimestamp.api(updatedAt), null, content, null, null, metadata));
            totalBytes += bytes;
        }
        int version = bundle.get("version", Integer.class);
        Map<String, Object> manifest = Map.of("bundleId", bundleId, "bundleVersion", version,
                "itemCount", rows.size(), "items", manifestItems);
        String hash = ExecutionCanonicalJson.sha256(manifest);
        if (!hash.equals(bundle.get("manifestSha256", String.class))
                || !hash.equals(ExecutionCanonicalJson.sha256(read(bundle.get("manifestJson", String.class))))
                || !Long.valueOf(totalBytes).equals(bundle.get("totalBytes", Long.class))) {
            throw invalid("来源清单与真实来源不一致");
        }
        Map<String, Object> context = read(rows.getFirst().get("contentJson", String.class));
        int segmentCount = ShortMediumSegments.segmentCount(plan.operation().operation(), context);
        List<Segment> segments = new ArrayList<>();
        for (int index = 1; index < rows.size(); index++) {
            Record row = rows.get(index);
            Map<String, Object> content = read(row.get("contentJson", String.class));
            Segment segment = completed(tx, runId, row.get("resourceId", String.class), plan, context);
            Map<String, Object> expected = Map.of("index", index - 1, "content", segment.content(), "contentSha256", segment.contentSha256());
            if (!content.keySet().equals(Set.of("index", "content", "contentSha256"))
                    || segment.index() != index - 1 || !"generate_manuscript".equals(plan.operation().operation())
                    || !ExecutionCanonicalJson.sha256(expected).equals(ExecutionCanonicalJson.sha256(content))) {
                throw invalid("已完成段与生产 Step 的结果不一致");
            }
            segments.add(segment);
        }
        ShortMediumSegments.join(segments, segments.size());
        if (segments.size() >= segmentCount) throw invalid("来源前缀已超过当前未完成段");
        return new Snapshot(bundleId, version, rows.getFirst().get("id", String.class),
                rows.getFirst().get("contentSha256", String.class), items, segments);
    }

    Segment completed(DSLContext tx, String runId, String stepId, ExecutionPlanSnapshot plan, Map<String, Object> context) {
        Record step = tx.fetchOne("SELECT * FROM public.\"WorkflowStep\" WHERE id = ? AND \"runId\" = ?", stepId, runId);
        if (step == null || !"completed".equals(step.get("status", String.class))
                || !"agent".equals(step.get("stepType", String.class)) || !"generation".equals(step.get("purpose", String.class))
                || step.get("output") == null || step.get("resultHash") == null || step.get("resolvedModelJson") == null
                || step.get("usageJson") == null || step.get("artifactId") != null) {
            throw invalid("已完成段缺少真实生成 Step");
        }
        Map<String, Object> input = read(step.get("input", String.class));
        if (!ExecutionCanonicalJson.sha256(input).equals(step.get("inputHash", String.class))) throw invalid("生成输入哈希不一致");
        int index = ShortMediumSegments.index(plan.operation().operation(), context, input);
        var frozen = plan.requireStep("generation", step.get("lane", String.class), step.get("modelProfile", String.class),
                Integer.parseInt(step.get("modelProfileVersion", String.class)), step.get("outputSchema", String.class),
                Integer.parseInt(step.get("outputSchemaVersion", String.class)), read(step.get("budgetJson", String.class)));
        Map<String, Object> output = read(step.get("output", String.class));
        String text = ShortMediumSegments.output(plan.operation().operation(), output, frozen.outputSchema().jsonSchema());
        Map<String, Object> resolved = read(step.get("resolvedModelJson", String.class));
        Map<String, Object> usage = read(step.get("usageJson", String.class));
        var model = WorkflowCallbackValues.resolvedModel(json.convertValue(resolved, ResolvedModelRef.class));
        model.requireAuthorizedBy(frozen.modelProfile().toDomain());
        var stepUsage = WorkflowCallbackValues.usage(json.convertValue(usage, StepUsage.class));
        frozen.stepBudget().budget().requireWithin(stepUsage);
        if (!ExecutionCanonicalJson.sha256(resolved).equals(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.resolvedModelMap(model)))
                || !ExecutionCanonicalJson.sha256(usage).equals(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.usageMap(stepUsage)))) {
            throw invalid("生成部署或用量字段不完整");
        }
        String resultHash = step.get("resultHash", String.class);
        if (!resultHash.equals(ExecutionCanonicalJson.sha256(Map.of("resultKind", "output", "value", output,
                "resolvedModel", resolved, "usage", usage)))) throw invalid("生成完整结果哈希不一致");
        return new Segment(stepId, index, text, ShortMediumSegments.sha256(text), resultHash);
    }

    private Map<String, Object> read(String value) {
        if (value == null) throw invalid("缺少持久化 JSON");
        return json.readValue(value, new TypeReference<>() {});
    }

    record Snapshot(String bundleId, int version, String contextItemId, String contextHash,
            List<WorkflowEvidenceItemPlan> items, List<Segment> segments) {
        Snapshot {
            items = List.copyOf(items);
            segments = List.copyOf(segments);
        }

        @SuppressWarnings("unchecked")
        Map<String, Object> context() {
            // 首项已经由 WorkflowEvidenceItemPlan 深冻结，复用同一份完整来源。
            return (Map<String, Object>) items.getFirst().contentJson();
        }
    }

    private static IllegalArgumentException invalid(String message) {
        return new IllegalArgumentException("中短篇耐久来源：" + message);
    }
}
