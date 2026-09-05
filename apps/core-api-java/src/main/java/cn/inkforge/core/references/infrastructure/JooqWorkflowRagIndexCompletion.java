package cn.inkforge.core.references.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.RAGDOCUMENT;
import static cn.inkforge.core.db.generated.Tables.REFERENCEMATERIAL;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;

import cn.inkforge.core.db.generated.enums.Ragdocumentstatus;
import cn.inkforge.core.db.generated.enums.Ragsourcetype;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.references.domain.RagRules;
import cn.inkforge.core.workflows.application.WorkflowRagIndexCompletion;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/** 执行账务收敛后才锁资料并物化当前代次，向量批次不产生部分可检索结果。 */
final class JooqWorkflowRagIndexCompletion implements WorkflowRagIndexCompletion {
    private final CoreDatabase database;
    private final ObjectMapper json;
    private final JooqReferenceRepository writer;

    JooqWorkflowRagIndexCompletion(CoreDatabase database, CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database); this.json = Objects.requireNonNull(json);
        this.writer = new JooqReferenceRepository(database, ids, clock);
    }

    @Override
    public int frozenChunkCount(DSLContext transaction, String runId) {
        var run = DurableRagIndexRun.load(transaction, json, runId);
        return (Integer) run.context(transaction, json).get("chunkCount");
    }

    @Override
    public boolean isCurrent(DSLContext transaction, String runId) {
        var run = DurableRagIndexRun.load(transaction, json, runId);
        run.context(transaction, json);
        return current(transaction, run, true) != null;
    }

    @Override
    public String complete(DSLContext transaction, String runId, List<List<BigDecimal>> embeddings) {
        var run = DurableRagIndexRun.load(transaction, json, runId);
        var context = run.context(transaction, json);
        var locked = current(transaction, run, true);
        if (locked == null) return "cancelled";
        writer.replaceCurrentIndex(transaction, locked, embeddings);
        Map<String, Object> output = Map.of("referenceId", run.referenceId(), "contentHash", run.contentHash(),
                "indexGeneration", run.generation(), "chunkCount", context.get("chunkCount"));
        transaction.update(WORKFLOWRUN).set(WORKFLOWRUN.OUTPUT, json.writeValueAsString(output)).where(WORKFLOWRUN.ID.eq(runId)).execute();
        return "completed";
    }

    @Override
    public String finish(DSLContext transaction, String runId, String requestedTerminal) {
        if (!Set.of("failed", "cancelled").contains(requestedTerminal)) throw new IllegalArgumentException("RAG 失败投影终态无效");
        var run = DurableRagIndexRun.load(transaction, json, runId);
        var locked = current(transaction, run, true);
        if (locked == null) return "cancelled";
        // ready 已经是业务成功；正常通用 Run 锁会让成功终报先于后续重复失败返回。
        if (locked.document().getStatus() != Ragdocumentstatus.ready) {
            locked.document().setStatus(Ragdocumentstatus.failed);
            locked.document().setErrormessage("索引生成失败");
            locked.document().store();
        }
        return requestedTerminal;
    }

    @Override
    public List<InvalidatedRun> findInvalidatedRuns(int limit) {
        if (limit < 1 || limit > 256) throw new IllegalArgumentException("索引失效扫描批次必须为 1 到 256");
        return database.dsl().fetch("""
                SELECT run.id,run."userId" FROM public."WorkflowRun" run
                LEFT JOIN public."ReferenceMaterial" reference ON reference.id=run."sourceId" AND reference."novelId"=run."novelId"
                LEFT JOIN public."RagDocument" document ON document."sourceType"='reference_material'
                  AND document."sourceId"=run."sourceId" AND document."novelId"=run."novelId"
                WHERE run."engineVersion"=2 AND run.workflow='rag' AND run.operation='embedding'
                  AND run."sourceType"='rag_index_v2' AND run.status IN ('pending','running') AND run."cancelRequestedAt" IS NULL
                  AND (reference.id IS NULL OR document.id IS NULL
                    OR document."contentHash" IS DISTINCT FROM run.input::jsonb->>'contentHash'
                    OR document."updatedAt" IS DISTINCT FROM (run.input::jsonb->>'indexGeneration')::timestamp)
                ORDER BY run.id LIMIT ?
                """, limit).map(row -> new InvalidatedRun(row.get("userId", String.class), row.get("id", String.class)));
    }

    @Override
    public boolean isInvalidated(DSLContext transaction, String runId) {
        // 取消事务先锁 Run/User，后续只读重验已提交代次；不在业务修改事务里反锁 Run。
        return current(transaction, DurableRagIndexRun.load(transaction, json, runId), false) == null;
    }

    private static JooqReferenceRepository.LockedReference current(DSLContext tx, DurableRagIndexRun run, boolean lock) {
        var ownerQuery = tx.select(NOVEL.USERID).from(NOVEL).where(NOVEL.ID.eq(run.novelId()));
        // 不完整用量分支未必锁 User；先锁 Novel 可防止后续 RagChunk FK 在 Reference 锁后反等 Novel。
        String owner = lock ? ownerQuery.forKeyShare().fetchOne(NOVEL.USERID) : ownerQuery.fetchOne(NOVEL.USERID);
        if (!run.userId().equals(owner)) return null;
        var referenceQuery = tx.selectFrom(REFERENCEMATERIAL).where(REFERENCEMATERIAL.ID.eq(run.referenceId()), REFERENCEMATERIAL.NOVELID.eq(run.novelId()));
        var reference = lock ? referenceQuery.forUpdate().fetchOne() : referenceQuery.fetchOne();
        if (reference == null) return null;
        var documentQuery = tx.selectFrom(RAGDOCUMENT).where(RAGDOCUMENT.SOURCETYPE.eq(Ragsourcetype.reference_material),
                RAGDOCUMENT.SOURCEID.eq(run.referenceId()), RAGDOCUMENT.NOVELID.eq(run.novelId()));
        var document = lock ? documentQuery.forUpdate().fetchOne() : documentQuery.fetchOne();
        if (document == null || !run.contentHash().equals(document.getContenthash())
                || !run.contentHash().equals(RagRules.sha256(reference.getContent()))
                || !DatabaseTimestamp.sameInstant(document.getUpdatedat(), OffsetDateTime.parse(run.generation()))) return null;
        return new JooqReferenceRepository.LockedReference(reference, document);
    }
}
