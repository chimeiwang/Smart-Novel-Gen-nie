package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.contracts.api.EvidenceExpansionItem;
import cn.inkforge.contracts.api.EvidenceExpansionRequest;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.ResourceKind;
import cn.inkforge.core.reviews.application.AgentUpdatesEvidenceReader.Source;
import cn.inkforge.core.reviews.application.AgentUpdatesFrozenSources;
import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/** 审核域的定向来源补齐；调用方持有 Run/fence 事务并负责新 bundle 与后继 Step 的原子提交。 */
final class JooqAgentUpdatesEvidenceExpansion {
    private static final Set<ResourceKind> SINGLETONS = EnumSet.of(
            ResourceKind.OUTLINE_CONTENT, ResourceKind.WORLD_SETTING, ResourceKind.STORY_BACKGROUND);
    private static final Set<ResourceKind> DELETE_IMPACTS = EnumSet.of(
            ResourceKind.CHARACTER, ResourceKind.LOCATION, ResourceKind.FACTION, ResourceKind.OUTLINE_NODE);
    private final ObjectMapper json;
    private final AgentUpdatesEvidenceReader reader;

    JooqAgentUpdatesEvidenceExpansion(ObjectMapper json, AgentUpdatesEvidenceReader reader) {
        this.json = Objects.requireNonNull(json);
        this.reader = Objects.requireNonNull(reader);
    }

    List<WorkflowEvidenceItemPlan> expand(DSLContext tx, String userId, String novelId, String runId,
            String bundleId, EvidenceExpansionRequest request) {
        if (request == null || !Objects.equals(bundleId, request.getSourceBundleId())
                || !"agent_updates_sources_required".equals(request.getReasonCode())
                || request.getMaxAdditionalBytes() == null || request.getMaxAdditionalBytes() <= 0
                || request.getItems() == null || request.getItems().isEmpty() || request.getItems().size() > 100) {
            throw invalid("资料补齐请求或来源身份无效");
        }
        var run = tx.fetchOne("SELECT \"userId\", \"novelId\" FROM public.\"WorkflowRun\" WHERE id = ? AND \"engineVersion\" = 2 AND workflow = 'long_serial'", runId);
        if (run == null || !Objects.equals(userId, run.get("userId", String.class))
                || !Objects.equals(novelId, run.get("novelId", String.class))) throw invalid("资料补齐必须属于同一用户、小说及 Run");
        var original = DurableAgentUpdatesReviewEvidence.readPlans(tx, json, runId, bundleId);
        if (!Objects.equals(original.version(), request.getSourceBundleVersion())) throw invalid("资料补齐的来源版本不匹配");
        var frozen = new AgentUpdatesFrozenSources(novelId, original.items());
        Set<Identity> index = index(frozen.requireCollection("agent_updates_index", novelId));
        List<Source> requested = new ArrayList<>();
        Set<Identity> requestedIds = new LinkedHashSet<>();
        boolean tree = false;
        for (EvidenceExpansionItem item : request.getItems()) {
            if (item == null || item.getRange() != null || item.getResourceType() == null
                    || item.getResourceId() == null || item.getResourceId().isBlank()) throw invalid("资料补齐不接受空身份或正文范围");
            Identity identity = new Identity(item.getResourceType(), item.getResourceId());
            if (!requestedIds.add(identity)) throw invalid("资料补齐不能重复请求同一资源");
            if ("replace_tree".equals(item.getPurposeCode())) {
                if (!"outline_tree".equals(item.getResourceType()) || !novelId.equals(item.getResourceId())) {
                    throw invalid("整树来源只能使用当前小说的 outline_tree");
                }
                tree = true;
                continue;
            }
            ResourceKind kind = kind(item.getResourceType());
            boolean delete = "delete_impact".equals(item.getPurposeCode());
            if (!("target".equals(item.getPurposeCode()) || delete && DELETE_IMPACTS.contains(kind))) {
                throw invalid("资料补齐用途不受该资源读取器支持");
            }
            if (SINGLETONS.contains(kind) ? !novelId.equals(item.getResourceId()) : !index.contains(identity)) {
                throw invalid("资料补齐资源不在本次冻结名录中");
            }
            requested.add(new Source(kind, item.getResourceId(), delete));
        }
        // 与采用及既有领域写入完全相同的 Novel → advisory 顺序；空集合也在锁内冻结。
        // 锁的串行范围不是全小说 CAS，不回读或比较请求外的业务 Head。
        lockNovel(tx, novelId, userId);
        List<WorkflowEvidenceItemPlan> additions = new ArrayList<>(reader.capture(tx, novelId, requested));
        if (tree) {
            List<WorkflowEvidenceItemPlan> treeItems = reader.captureOutlineTree(tx, novelId);
            Set<Identity> currentNodes = new LinkedHashSet<>();
            for (var item : treeItems) if (ResourceKind.OUTLINE_NODE.wireName().equals(item.resourceType())) {
                currentNodes.add(new Identity(item.resourceType(), item.resourceId()));
            }
            Set<Identity> frozenNodes = new LinkedHashSet<>();
            for (Identity identity : index) if (ResourceKind.OUTLINE_NODE.wireName().equals(identity.type())) frozenNodes.add(identity);
            if (!currentNodes.equals(frozenNodes)) throw changed();
            additions.addAll(treeItems);
        }
        Map<Identity, WorkflowEvidenceItemPlan> merged = new LinkedHashMap<>();
        for (var item : original.items()) merge(merged, item);
        long originalBytes = bytes(merged.values());
        int originalCount = merged.size();
        for (var item : additions) merge(merged, item);
        List<WorkflowEvidenceItemPlan> result = List.copyOf(merged.values());
        // 同一真实行可能分别以 target、直接引用或嵌套完整行出现，统一索引拒绝别名下的新 Head 覆盖。
        try { new AgentUpdatesFrozenSources(novelId, result); }
        catch (ApiException error) { throw changed(); }
        if (merged.size() == originalCount) throw new ApiException(409, "AGENT_UPDATES_EVIDENCE_NO_PROGRESS", "资料补齐没有新增来源，不能继续重复生成");
        if (bytes(merged.values()) - originalBytes > request.getMaxAdditionalBytes()) {
            throw new ApiException(409, "AGENT_UPDATES_EVIDENCE_BUDGET_EXCEEDED", "资料补齐的完整新增字节数超过本次预算");
        }
        return result;
    }

    private static Set<Identity> index(List<Map<String, Object>> rows) {
        Set<Identity> identities = new LinkedHashSet<>();
        for (Map<String, Object> row : rows) {
            if (!(row.get("resourceType") instanceof String type) || !(row.get("id") instanceof String id) || id.isBlank()
                    || SINGLETONS.contains(kind(type)) || !identities.add(new Identity(type, id))) {
                throw invalid("冻结名录的资源身份无效或重复");
            }
        }
        return identities;
    }

    private static ResourceKind kind(String type) {
        for (ResourceKind kind : ResourceKind.values()) if (kind.wireName().equals(type)) return kind;
        throw invalid("资料补齐资源类型不受支持");
    }

    private static void merge(Map<Identity, WorkflowEvidenceItemPlan> result, WorkflowEvidenceItemPlan item) {
        Identity key = new Identity(item.resourceType(), item.resourceId());
        WorkflowEvidenceItemPlan old = result.get(key);
        if (old == null) {
            result.put(key, item);
            return;
        }
        Map<String, Object> oldMetadata = new LinkedHashMap<>(old.metadata());
        Map<String, Object> metadata = new LinkedHashMap<>(item.metadata());
        Object oldRoles = oldMetadata.remove("roles");
        Object newRoles = metadata.remove("roles");
        if (old.exists() != item.exists() || !Objects.equals(old.resourceRevision(), item.resourceRevision())
                || !Objects.equals(old.resourceUpdatedAt(), item.resourceUpdatedAt())
                || !Objects.equals(old.contentText(), item.contentText())
                || !ExecutionCanonicalJson.sha256(old.contentJson()).equals(ExecutionCanonicalJson.sha256(item.contentJson()))
                || !Objects.equals(old.rangeStartCodePoint(), item.rangeStartCodePoint())
                || !Objects.equals(old.rangeEndCodePoint(), item.rangeEndCodePoint())
                || !ExecutionCanonicalJson.sha256(oldMetadata).equals(ExecutionCanonicalJson.sha256(metadata))) throw changed();
        if (Objects.equals(oldRoles, newRoles)) return;
        if (!(oldRoles instanceof List<?> left) || !(newRoles instanceof List<?> right)) throw changed();
        Set<Object> roles = new LinkedHashSet<>(left);
        roles.addAll(right);
        metadata.put("roles", List.copyOf(roles));
        result.put(key, new WorkflowEvidenceItemPlan(old.resourceType(), old.resourceId(), old.exists(), old.resourceRevision(),
                old.resourceUpdatedAt(), old.contentText(), old.contentJson(), old.rangeStartCodePoint(), old.rangeEndCodePoint(), metadata));
    }

    private static long bytes(Iterable<WorkflowEvidenceItemPlan> items) {
        long result = 0;
        for (var item : items) if (item.exists()) result += item.contentText() == null
                ? ExecutionCanonicalJson.bytes(item.contentJson()).length : item.contentText().getBytes(StandardCharsets.UTF_8).length;
        return result;
    }

    private static void lockNovel(DSLContext tx, String novelId, String userId) {
        var owner = tx.fetchOne("SELECT \"userId\" FROM public.\"Novel\" WHERE id = ? FOR UPDATE", novelId);
        if (owner == null || !Objects.equals(userId, owner.get("userId", String.class))) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
        try {
            long key = ByteBuffer.wrap(MessageDigest.getInstance("SHA-256").digest(novelId.getBytes(StandardCharsets.UTF_8))).getLong();
            tx.fetch("SELECT pg_advisory_xact_lock(?)", key);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("JDK 缺少 SHA-256", error);
        }
    }

    private static ApiException invalid(String message) { return new ApiException(409, "AGENT_UPDATES_EVIDENCE_REQUEST_INVALID", message); }
    private static ApiException changed() { return new ApiException(409, "AGENT_UPDATES_SOURCE_CHANGED", "资料补齐遇到与已冻结来源冲突的记录，请重新发起任务"); }
    private record Identity(String type, String id) {}
}
