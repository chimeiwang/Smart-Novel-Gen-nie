package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.contracts.api.SourceBinding;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.ResourceKind;
import cn.inkforge.core.reviews.application.AgentUpdatesFrozenSources;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.domain.DurableAgentUpdatesArtifact;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.workflows.protocol.ExecutionProtocolDateTime;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.exception.DataAccessException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 只从 Run、生成 Step 与不可变 Evidence 重建草案，不读取当前小说资料 Head。 */
record DurableAgentUpdatesReviewEvidence(String userId, AgentUpdatesFrozenSources sources,
        Map<String, Object> output, List<SourceBinding> sourceBindings) {
    static AgentUpdatesFrozenSources readSources(DSLContext tx, ObjectMapper json, String runId, String bundleId, String novelId) {
        return new AgentUpdatesFrozenSources(novelId, readPlans(tx, json, runId, bundleId).items());
    }

    /** 补齐只追加事实；完整复验旧 bundle 后交还原始计划，不能以当前 Head 修补历史来源。 */
    static VerifiedBundle readPlans(DSLContext tx, ObjectMapper json, String runId, String bundleId) {
        try {
            Record bundle = tx.fetchOne("SELECT version, \"manifestJson\", \"manifestSha256\", \"totalBytes\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ? AND \"runId\" = ?", bundleId, runId);
            if (bundle == null) throw invalid();
            return new VerifiedBundle(bundle.get("version", Integer.class), readItems(tx, json, bundleId, bundle));
        } catch (DataAccessException error) {
            // 临时数据库故障仍交由调用方回滚重试，不能被确认为不可变来源已损坏。
            throw error;
        } catch (ApiException error) {
            throw error;
        } catch (RuntimeException error) {
            throw invalid();
        }
    }

    record VerifiedBundle(int version, List<WorkflowEvidenceItemPlan> items) {}

    static DurableAgentUpdatesReviewEvidence read(DSLContext tx, ObjectMapper json, String runId,
            String novelId, String artifactId, int revision, String operation, Map<String, Object> payload,
            Map<String, Object> diff, Map<String, Object> providerSchema) {
        try {
            Record run = tx.fetchOne("SELECT \"userId\" FROM public.\"WorkflowRun\" WHERE id = ? AND \"novelId\" = ? AND \"engineVersion\" = 2 AND workflow = 'long_serial'", runId, novelId);
            if (run == null) throw invalid();
            // 从产出指针查找生成记录，不能拿候选自报 producingStepId 当成验证的期望值。
            List<Record> producers = new ArrayList<>();
            for (Record step : tx.fetch("""
                    SELECT id, "evidenceBundleId", "artifactId", "artifactRevision", output, "resultHash",
                           "resolvedModelJson", "usageJson"
                    FROM public."WorkflowStep" WHERE "runId" = ? AND purpose = 'generation' AND status = 'completed'
                    """, runId)) {
                Map<String, Object> receipt = object(json, step.get("output", String.class));
                if (artifactId.equals(receipt.get("artifactId")) && Objects.equals(revision, receipt.get("artifactRevision"))) {
                    if (!receipt.keySet().equals(java.util.Set.of("artifactId", "artifactRevision", "updatesSha256"))
                            || !Objects.equals(payload.get("updatesSha256"), receipt.get("updatesSha256"))) throw invalid();
                    producers.add(step);
                }
            }
            if (producers.size() != 1) throw invalid();
            Record step = producers.getFirst();
            Integer boundRevision = step.get("artifactRevision", Integer.class);
            if (!artifactId.equals(step.get("artifactId", String.class)) || boundRevision == null
                    || !(boundRevision == revision || revision > 1 && boundRevision == revision - 1)) throw invalid();
            String bundleId = step.get("evidenceBundleId", String.class);
            Record bundle = tx.fetchOne("SELECT version, \"manifestJson\", \"manifestSha256\", \"totalBytes\" FROM public.\"WorkflowEvidenceBundle\" WHERE id = ? AND \"runId\" = ?", bundleId, runId);
            if (bundle == null) throw invalid();
            List<WorkflowEvidenceItemPlan> evidence = readItems(tx, json, bundleId, bundle);
            Map<String, Object> output = DurableAgentUpdatesArtifact.reconstruct(operation, payload, diff, bundleId,
                    bundle.get("manifestSha256", String.class), novelId, step.get("id", String.class), step.get("resultHash", String.class), providerSchema);
            // 完整结果由唯一候选重建，再与生成 Step 的真实模型、用量组成原回调哈希，摘要也在校验范围内。
            Map<String, Object> result = Map.of("resultKind", "output", "value", output,
                    "resolvedModel", object(json, step.get("resolvedModelJson", String.class)),
                    "usage", object(json, step.get("usageJson", String.class)));
            if (!ExecutionCanonicalJson.sha256(result).equals(step.get("resultHash", String.class))) throw invalid();
            AgentUpdatesFrozenSources sources = new AgentUpdatesFrozenSources(novelId, evidence);
            List<SourceBinding> bindings = new ArrayList<>();
            for (ResourceKind kind : ResourceKind.values()) {
                for (var source : sources.snapshots(kind)) {
                    Map<String, Object> binding = new LinkedHashMap<>();
                    binding.put("resourceType", kind.wireName());
                    binding.put("resourceId", source.id());
                    binding.put("exists", source.exists());
                    binding.put("updatedAt", source.updatedAt() == null ? null : source.updatedAt().toString());
                    binding.put("contentSha256", source.exists() ? ExecutionCanonicalJson.sha256(source.before()) : null);
                    binding.put("revision", null);
                    binding.put("absenceSentinel", source.exists() ? null : Map.of("resourceType", "novel", "resourceId", novelId));
                    if (source.exists() && source.updatedAt() == null) throw invalid();
                    bindings.add(json.convertValue(binding, SourceBinding.class));
                }
            }
            return new DurableAgentUpdatesReviewEvidence(run.get("userId", String.class), sources, output, List.copyOf(bindings));
        } catch (ApiException error) {
            throw error;
        } catch (RuntimeException error) {
            throw invalid();
        }
    }

    private static List<WorkflowEvidenceItemPlan> readItems(DSLContext tx, ObjectMapper json, String bundleId, Record bundle) {
        List<WorkflowEvidenceItemPlan> evidence = new ArrayList<>();
        List<Map<String, Object>> manifestItems = new ArrayList<>();
        long bytes = 0;
        for (Record row : tx.fetch("SELECT * FROM public.\"WorkflowEvidenceItem\" WHERE \"bundleId\" = ? ORDER BY ordinal", bundleId)) {
            int ordinal = row.get("ordinal", Integer.class);
            if (ordinal != evidence.size() + 1) throw invalid();
            boolean exists = row.get("exists", Boolean.class);
            String type = row.get("contentType", String.class);
            String text = row.get("contentText", String.class);
            String rawJson = row.get("contentJson", String.class);
            if (exists ? !("text".equals(type) && text != null && rawJson == null
                    || "json".equals(type) && rawJson != null && text == null)
                    : type != null || text != null || rawJson != null) throw invalid();
            Object content = rawJson == null ? null : json.readValue(rawJson, Object.class);
            byte[] body = !exists ? new byte[0] : "text".equals(type)
                    ? Objects.requireNonNull(text).getBytes(StandardCharsets.UTF_8) : ExecutionCanonicalJson.bytes(content);
            String hash = exists ? sha256(body) : null;
            if (body.length != row.get("byteCount", Long.class) || !Objects.equals(hash, row.get("contentSha256", String.class))) throw invalid();
            Map<String, Object> metadata = object(json, row.get("metadataJson", String.class));
            Map<String, Object> range = row.get("rangeJson", String.class) == null ? null : object(json, row.get("rangeJson", String.class));
            LocalDateTime time = row.get("resourceUpdatedAt", LocalDateTime.class);
            OffsetDateTime updated = time == null ? null : DatabaseTimestamp.api(time);
            var item = new WorkflowEvidenceItemPlan(row.get("resourceType", String.class), row.get("resourceId", String.class), exists,
                    row.get("resourceRevision", Integer.class), updated, text, content,
                    range == null ? null : (Integer) range.get("startCodePoint"), range == null ? null : (Integer) range.get("endCodePoint"), metadata);
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("itemId", row.get("id", String.class));
            entry.put("ordinal", ordinal);
            entry.put("resourceType", item.resourceType());
            entry.put("resourceId", item.resourceId());
            entry.put("exists", exists);
            if (item.resourceRevision() != null) entry.put("resourceRevision", item.resourceRevision());
            if (updated != null) entry.put("resourceUpdatedAt", ExecutionProtocolDateTime.format(updated));
            if (type != null) entry.put("contentType", type);
            if (hash != null) entry.put("contentSha256", hash);
            entry.put("byteCount", body.length);
            if (range != null) entry.put("range", range);
            entry.put("metadata", metadata);
            manifestItems.add(entry);
            evidence.add(item);
            bytes += body.length;
        }
        Map<String, Object> rebuilt = Map.of("bundleId", bundleId, "bundleVersion", bundle.get("version", Integer.class),
                "itemCount", evidence.size(), "items", manifestItems);
        String hash = bundle.get("manifestSha256", String.class);
        if (bytes != bundle.get("totalBytes", Long.class) || !ExecutionCanonicalJson.sha256(rebuilt).equals(hash)
                || !ExecutionCanonicalJson.sha256(object(json, bundle.get("manifestJson", String.class))).equals(hash)) throw invalid();
        return List.copyOf(evidence);
    }

    private static Map<String, Object> object(ObjectMapper json, String value) {
        if (value == null) throw invalid();
        return json.readValue(value, new TypeReference<>() {});
    }

    private static String sha256(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (NoSuchAlgorithmException error) { throw new IllegalStateException("JDK 缺少 SHA-256", error); }
    }

    private static ApiException invalid() {
        return new ApiException(409, "ARTIFACT_REVISION_INTEGRITY_ERROR", "结构化候选、生成 Step 或冻结来源无法通过完整性校验");
    }
}
