package cn.inkforge.core.references.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.RAGCHUNK;
import static cn.inkforge.core.db.generated.Tables.RAGDOCUMENT;
import static cn.inkforge.core.db.generated.Tables.REFERENCEMATERIAL;

import cn.inkforge.core.db.generated.enums.Ragdocumentstatus;
import cn.inkforge.core.db.generated.enums.Ragsourcetype;
import cn.inkforge.core.db.generated.enums.Referencematerialtype;
import cn.inkforge.core.db.generated.tables.records.RagdocumentRecord;
import cn.inkforge.core.db.generated.tables.records.ReferencematerialRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CommandResourceId;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.patch.PatchField;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.references.application.ReferenceRepository;
import cn.inkforge.core.references.application.RagIndexRunStarter;
import cn.inkforge.core.references.application.RagIndexRegistrationUnavailable;
import cn.inkforge.core.references.application.RagSubmissionException;
import cn.inkforge.core.references.domain.RagDispatchRecord;
import cn.inkforge.core.references.domain.RagDispatchStatus;
import cn.inkforge.core.references.domain.RagIndexIntent;
import cn.inkforge.core.references.domain.RagJobIdentity;
import cn.inkforge.core.references.domain.RagRules;
import cn.inkforge.core.references.domain.RagSearchHit;
import cn.inkforge.core.references.domain.ReferenceCreateResult;
import cn.inkforge.core.references.domain.ReferenceData;
import cn.inkforge.core.references.domain.ReferenceDeleteImpact;
import cn.inkforge.core.references.domain.ReferencePatch;
import cn.inkforge.core.references.domain.ReferenceSnapshot;
import cn.inkforge.core.references.domain.ReferenceUpdateResult;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Supplier;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.impl.DSL;
import tools.jackson.databind.ObjectMapper;

/**
 * 基于冻结 PostgreSQL 结构的参考资料与 pgvector 仓储。
 *
 * <p>ReferenceMaterial 保存作者原文，RagDocument/RagChunk 只是可重建索引。正文变化会在同一事务删除旧 chunk 并
 * 推进索引代次；Agent 回调必须同时匹配 task、run 和 contentHash，旧代次结果不能覆盖新正文。
 */
final class JooqReferenceRepository implements ReferenceRepository {

    private static final String SOURCE_TYPE = "reference_material";
    private static final String WAITING = "等待重新索引";
    private static final String DISABLED = "检索索引服务未配置";
    private static final String REGISTRATION_UNAVAILABLE = "RAG_DURABLE_REGISTRATION_UNAVAILABLE";
    private static final int EMBEDDING_BATCH_SIZE = 10;

    private static final String SEARCH_SQL = """
            SELECT
              d."title",
              d."sourceId",
              c."chunkIndex",
              c."text",
              1 - CASE WHEN c."embeddingDimension" = ?
                  THEN c."embedding" <=> CAST(? AS vector) END AS "score"
            FROM "RagChunk" AS c
            JOIN "RagDocument" AS d ON d."id" = c."documentId"
            WHERE c."novelId" = ?
              AND d."novelId" = ?
              AND d."sourceType" = CAST(? AS "RagSourceType")
              AND d."status" = 'ready'
              AND c."embeddingDimension" = ?
            ORDER BY CASE WHEN c."embeddingDimension" = ?
                THEN c."embedding" <=> CAST(? AS vector) END
            LIMIT ?
            """;

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final boolean durableSchemaReady;
    private final ObjectMapper json;
    private final Supplier<RagIndexRunStarter> starters;

    JooqReferenceRepository(CoreDatabase database, CuidV1Generator ids, Clock clock) {
        this(database, ids, clock, false, new ObjectMapper(), () -> null);
    }

    JooqReferenceRepository(CoreDatabase database, CuidV1Generator ids, Clock clock,
            boolean durableSchemaReady, ObjectMapper json, Supplier<RagIndexRunStarter> starters) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.durableSchemaReady = durableSchemaReady;
        this.json = Objects.requireNonNull(json);
        this.starters = Objects.requireNonNull(starters);
    }

    @Override
    public List<ReferenceSnapshot> list(String novelId, String userId) {
        DSLContext context = database.dsl();
        requireOwner(context, novelId, userId);
        return context.select(REFERENCEMATERIAL.fields())
                .select(RAGDOCUMENT.fields())
                .from(REFERENCEMATERIAL)
                .leftJoin(RAGDOCUMENT)
                .on(RAGDOCUMENT.SOURCETYPE.eq(Ragsourcetype.reference_material)
                        .and(RAGDOCUMENT.SOURCEID.eq(REFERENCEMATERIAL.ID)))
                .where(REFERENCEMATERIAL.NOVELID.eq(novelId))
                .orderBy(REFERENCEMATERIAL.CREATEDAT.asc(), REFERENCEMATERIAL.ID.asc())
                .fetch(record -> snapshot(
                        record.into(REFERENCEMATERIAL),
                        record.get(RAGDOCUMENT.ID) == null ? null : record.into(RAGDOCUMENT)));
    }

    @Override
    public ReferenceCreateResult create(
            String novelId,
            String userId,
            String clientRequestId,
            ReferenceData data,
            boolean indexEnabled) {
        return database.transactionResult(transaction -> {
            requireOwner(transaction, novelId, userId);
            lockUserBeforeNovel(transaction, userId);
            lockNovel(transaction, novelId, userId);
            // 确定性资料 ID 支持创建响应丢失后的安全重放，同时保证原文与索引壳原子建立。
            String id = CommandResourceId.derive(
                    "reference", userId, novelId, clientRequestId);
            ReferencematerialRecord existing = transaction.selectFrom(REFERENCEMATERIAL)
                    .where(REFERENCEMATERIAL.ID.eq(id))
                    .forUpdate()
                    .fetchOne();
            if (existing != null) {
                if (existing.getNovelid().equals(novelId)
                        && existing.getCreatedat().equals(existing.getUpdatedat())
                        && same(existing, data)) {
                    RagdocumentRecord document = requireDocument(transaction, novelId, id, false);
                    return new ReferenceCreateResult(
                            snapshot(existing, document),
                            false,
                            DatabaseTimestamp.api(document.getUpdatedat()));
                }
                throw createConflict();
            }
            LocalDateTime now = DatabaseTimestamp.now(clock);
            ReferencematerialRecord reference = transaction.insertInto(REFERENCEMATERIAL)
                    .set(REFERENCEMATERIAL.ID, id)
                    .set(REFERENCEMATERIAL.NOVELID, novelId)
                    .set(REFERENCEMATERIAL.TITLE, data.title())
                    .set(REFERENCEMATERIAL.TYPE, Referencematerialtype.lookupLiteral(data.type()))
                    .set(REFERENCEMATERIAL.CONTENT, data.content())
                    .set(REFERENCEMATERIAL.SOURCEURL, data.sourceUrl())
                    .set(REFERENCEMATERIAL.CREATEDAT, now)
                    .set(REFERENCEMATERIAL.UPDATEDAT, now)
                    .returning()
                    .fetchSingle();
            RagdocumentRecord document = transaction.insertInto(RAGDOCUMENT)
                    .set(RAGDOCUMENT.ID, ids.next())
                    .set(RAGDOCUMENT.NOVELID, novelId)
                    .set(RAGDOCUMENT.SOURCETYPE, Ragsourcetype.reference_material)
                    .set(RAGDOCUMENT.SOURCEID, id)
                    .set(RAGDOCUMENT.TITLE, data.title())
                    .set(RAGDOCUMENT.CONTENTHASH, RagRules.sha256(data.content()))
                    .set(RAGDOCUMENT.STATUS, Ragdocumentstatus.disabled)
                    .set(RAGDOCUMENT.ERRORMESSAGE, indexEnabled ? WAITING : DISABLED)
                    .set(RAGDOCUMENT.CREATEDAT, now)
                    .set(RAGDOCUMENT.UPDATEDAT, now)
                    .returning()
                    .fetchSingle();
            prepareNewIndex(transaction, userId, reference, document, indexEnabled);
            return new ReferenceCreateResult(
                    snapshot(reference, document), true, DatabaseTimestamp.api(now));
        });
    }

    @Override
    public ReferenceUpdateResult update(
            String novelId,
            String userId,
            String referenceId,
            ReferencePatch patch,
            OffsetDateTime expectedUpdatedAt,
            boolean indexEnabled) {
        return database.transactionResult(transaction -> {
            requireOwner(transaction, novelId, userId);
            lockUserBeforeNovel(transaction, userId);
            lockNovel(transaction, novelId, userId);
            LockedReference locked = lockReference(transaction, novelId, referenceId);
            ReferencematerialRecord reference = locked.reference();
            RagdocumentRecord document = locked.document();
            requireVersion(reference.getUpdatedat(), expectedUpdatedAt);

            boolean titleChanged = changed(patch.title(), reference.getTitle());
            boolean typeChanged = changed(patch.type(), reference.getType().getLiteral());
            boolean contentChanged = changed(patch.content(), reference.getContent());
            boolean sourceUrlChanged = changed(patch.sourceUrl(), reference.getSourceurl());
            if (!titleChanged && !typeChanged && !contentChanged && !sourceUrlChanged) {
                return new ReferenceUpdateResult(
                        snapshot(reference, document),
                        false,
                        DatabaseTimestamp.api(document.getUpdatedat()));
            }
            if (titleChanged) reference.setTitle(patch.title().value());
            if (typeChanged) {
                reference.setType(Referencematerialtype.lookupLiteral(patch.type().value()));
            }
            if (contentChanged) reference.setContent(patch.content().value());
            if (sourceUrlChanged) reference.setSourceurl(patch.sourceUrl().value());
            reference.setUpdatedat(DatabaseTimestamp.next(clock, reference.getUpdatedat()));
            reference.store();

            if (titleChanged) document.setTitle(reference.getTitle());
            if (contentChanged) {
                // chunk 是派生数据；原文一变立即删除并标记待重建，搜索不能继续返回旧内容。
                transaction.deleteFrom(RAGCHUNK)
                        .where(RAGCHUNK.DOCUMENTID.eq(document.getId()))
                        .execute();
                document.setContenthash(RagRules.sha256(reference.getContent()));
                document.setStatus(Ragdocumentstatus.disabled);
                document.setErrormessage(indexEnabled ? WAITING : DISABLED);
                document.setUpdatedat(DatabaseTimestamp.next(clock, document.getUpdatedat()));
            }
            if (titleChanged || contentChanged) document.store();
            if (contentChanged) prepareNewIndex(transaction, userId, reference, document, indexEnabled);
            return new ReferenceUpdateResult(
                    snapshot(reference, document),
                    contentChanged,
                    DatabaseTimestamp.api(document.getUpdatedat()));
        });
    }

    @Override
    public ReferenceDeleteImpact delete(
            String novelId,
            String userId,
            String referenceId,
            OffsetDateTime expectedUpdatedAt) {
        return database.transactionResult(transaction -> {
            requireOwner(transaction, novelId, userId);
            lockNovel(transaction, novelId, userId);
            LockedReference locked = lockReference(transaction, novelId, referenceId);
            requireVersion(locked.reference().getUpdatedat(), expectedUpdatedAt);
            int chunks = transaction.fetchCount(
                    RAGCHUNK, RAGCHUNK.DOCUMENTID.eq(locked.document().getId()));
            transaction.deleteFrom(RAGCHUNK)
                    .where(RAGCHUNK.DOCUMENTID.eq(locked.document().getId()))
                    .execute();
            int documents = transaction.deleteFrom(RAGDOCUMENT)
                    .where(RAGDOCUMENT.ID.eq(locked.document().getId()))
                    .execute();
            int references = transaction.deleteFrom(REFERENCEMATERIAL)
                    .where(REFERENCEMATERIAL.ID.eq(referenceId)
                            .and(REFERENCEMATERIAL.NOVELID.eq(novelId)))
                    .execute();
            if (references != 1) throw notFound();
            return new ReferenceDeleteImpact(referenceId, documents, chunks);
        });
    }

    @Override
    public ReferenceSnapshot requireIndexContext(
            String novelId,
            String userId,
            String referenceId,
            String taskId,
            String runId,
            String expectedContentHash) {
        return database.transactionResult(transaction -> {
            requireOwner(transaction, novelId, userId);
            LockedReference locked = lockReference(transaction, novelId, referenceId);
            requireCurrentJob(transaction, locked, expectedContentHash, taskId, runId);
            return snapshot(locked.reference(), locked.document());
        });
    }

    @Override
    public ReferenceSnapshot replaceIndex(
            String novelId,
            String referenceId,
            String taskId,
            String runId,
            String expectedContentHash,
            List<List<BigDecimal>> embeddings) {
        return database.transactionResult(transaction -> {
            LockedReference locked = lockReference(transaction, novelId, referenceId);
            requireCurrentJob(transaction, locked, expectedContentHash, taskId, runId);
            return replaceCurrentIndex(transaction, locked, embeddings);
        });
    }

    ReferenceSnapshot replaceCurrentIndex(DSLContext transaction, LockedReference locked, List<List<BigDecimal>> embeddings) {
            ReferencematerialRecord reference = locked.reference();
            RagdocumentRecord document = locked.document();
            String novelId = reference.getNovelid();
            if (document.getStatus() == Ragdocumentstatus.ready) {
                return snapshot(reference, document);
            }
            if (document.getStatus() == Ragdocumentstatus.failed) {
                throw terminalConflict();
            }
            List<String> chunks = RagRules.chunks(reference.getContent());
            List<List<BigDecimal>> normalized;
            if (chunks.isEmpty()) {
                if (!embeddings.isEmpty()) throw embeddingCountMismatch();
                normalized = List.of();
            } else {
                normalized = RagRules.embeddings(embeddings);
            }
            if (chunks.size() != normalized.size()) throw embeddingCountMismatch();
            // 先清空并完整写入新代次，最后才标记 ready；事务外永远看不到半套向量。
            transaction.deleteFrom(RAGCHUNK)
                    .where(RAGCHUNK.DOCUMENTID.eq(document.getId()))
                    .execute();
            LocalDateTime now = DatabaseTimestamp.now(clock);
            for (int offset = 0; offset < chunks.size(); offset += EMBEDDING_BATCH_SIZE) {
                int end = Math.min(offset + EMBEDDING_BATCH_SIZE, chunks.size());
                for (int index = offset; index < end; index++) {
                    String chunk = chunks.get(index);
                    List<BigDecimal> vector = normalized.get(index);
                    transaction.query(
                                    """
                                    INSERT INTO "RagChunk"
                                      ("id", "documentId", "novelId", "chunkIndex", "text",
                                       "charCount", "embeddingDimension", "embedding", "createdAt")
                                    VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS vector), ?)
                                    """,
                                    ids.next(),
                                    document.getId(),
                                    novelId,
                                    index,
                                    chunk,
                                    chunk.codePointCount(0, chunk.length()),
                                    vector.size(),
                                    vectorLiteral(vector),
                                    now)
                            .execute();
                }
            }
            document.setStatus(Ragdocumentstatus.ready);
            document.setErrormessage(null);
            document.setContenthash(RagRules.sha256(reference.getContent()));
            // 成功回调属于当前代次的终态，不推进 updatedAt，重放身份必须继续有效。
            document.store();
            return snapshot(reference, document);
    }

    @Override
    public RagIndexIntent prepareReindex(
            String novelId,
            String userId,
            String referenceId,
            String expectedContentHash) {
        return database.transactionResult(transaction -> {
            requireOwner(transaction, novelId, userId);
            lockUserBeforeNovel(transaction, userId);
            lockNovel(transaction, novelId, userId);
            LockedReference locked = lockReference(transaction, novelId, referenceId);
            requireCurrentHash(locked, expectedContentHash);
            if (pending(locked, expectedContentHash)) {
                return new RagIndexIntent(
                        expectedContentHash,
                        DatabaseTimestamp.api(locked.document().getUpdatedat()));
            }
            transaction.deleteFrom(RAGCHUNK)
                    .where(RAGCHUNK.DOCUMENTID.eq(locked.document().getId()))
                    .execute();
            RagdocumentRecord document = locked.document();
            document.setTitle(locked.reference().getTitle());
            document.setContenthash(expectedContentHash);
            document.setStatus(Ragdocumentstatus.disabled);
            document.setErrormessage(WAITING);
            document.setUpdatedat(DatabaseTimestamp.next(clock, document.getUpdatedat()));
            document.store();
            prepareNewIndex(transaction, userId, locked.reference(), document, true);
            return new RagIndexIntent(
                    expectedContentHash, DatabaseTimestamp.api(document.getUpdatedat()));
        });
    }

    @Override
    public void markIndexFailed(
            String novelId,
            String referenceId,
            String taskId,
            String runId,
            String expectedContentHash,
            String message) {
        database.transactionResult(transaction -> {
            LockedReference locked = lockReference(transaction, novelId, referenceId);
            requireCurrentJob(transaction, locked, expectedContentHash, taskId, runId);
            RagdocumentRecord document = locked.document();
            if (document.getStatus() == Ragdocumentstatus.failed) return null;
            if (document.getStatus() == Ragdocumentstatus.ready) throw terminalConflict();
            document.setStatus(Ragdocumentstatus.failed);
            document.setErrormessage(message);
            document.store();
            return null;
        });
    }

    @Override
    public List<RagSearchHit> search(
            String novelId, String userId, List<BigDecimal> embedding, int topK) {
        List<BigDecimal> vector = RagRules.embeddings(List.of(embedding)).getFirst();
        int boundedTopK = RagRules.topK(topK);
        DSLContext context = database.dsl();
        requireOwner(context, novelId, userId);
        String literal = vectorLiteral(vector);
        return context.fetch(
                        SEARCH_SQL,
                        vector.size(),
                        literal,
                        novelId,
                        novelId,
                        SOURCE_TYPE,
                        vector.size(),
                        vector.size(),
                        literal,
                        boundedTopK)
                .map(record -> new RagSearchHit(
                        record.get("title", String.class),
                        record.get("sourceId", String.class),
                        record.get("chunkIndex", Integer.class),
                        record.get("score", BigDecimal.class),
                        record.get("text", String.class)));
    }

    @Override
    public List<RagDispatchRecord> listPending(int limit) {
        if (limit < 1) throw new IllegalArgumentException("领取数量必须大于零");
        List<RagDispatchRecord> values = new ArrayList<>();
        database.dsl().select(
                        NOVEL.USERID,
                        REFERENCEMATERIAL.NOVELID,
                        REFERENCEMATERIAL.ID,
                        REFERENCEMATERIAL.CONTENT,
                        RAGDOCUMENT.CONTENTHASH,
                        RAGDOCUMENT.UPDATEDAT)
                .from(RAGDOCUMENT)
                .join(REFERENCEMATERIAL)
                .on(RAGDOCUMENT.SOURCETYPE.eq(Ragsourcetype.reference_material)
                        .and(RAGDOCUMENT.SOURCEID.eq(REFERENCEMATERIAL.ID)))
                .join(NOVEL)
                .on(NOVEL.ID.eq(REFERENCEMATERIAL.NOVELID))
                .where(RAGDOCUMENT.STATUS.eq(Ragdocumentstatus.disabled)
                        .and(RAGDOCUMENT.ERRORMESSAGE.eq(WAITING)))
                .and(durableSchemaReady ? DSL.condition("""
                        NOT EXISTS (SELECT 1 FROM public."WorkflowRun" run WHERE run."engineVersion"=2
                          AND run.workflow='rag' AND run.operation='embedding' AND run."sourceType"='rag_index_v2'
                          AND run."sourceId"="RagDocument"."sourceId"
                          AND run.input::jsonb->>'contentHash'="RagDocument"."contentHash"
                          AND (run.input::jsonb->>'indexGeneration')::timestamp="RagDocument"."updatedAt")
                        """) : DSL.trueCondition())
                .orderBy(RAGDOCUMENT.UPDATEDAT.asc(), RAGDOCUMENT.ID.asc())
                .limit(limit)
                .forEach(record -> {
                    String content = record.get(REFERENCEMATERIAL.CONTENT);
                    String currentHash = RagRules.sha256(content);
                    // 仅派发仍与原文一致的代次；漂移记录等待写路径重新建立索引意图。
                    if (currentHash.equals(record.get(RAGDOCUMENT.CONTENTHASH))) {
                        values.add(new RagDispatchRecord(
                                record.get(NOVEL.USERID),
                                record.get(REFERENCEMATERIAL.NOVELID),
                                record.get(REFERENCEMATERIAL.ID),
                                currentHash,
                                DatabaseTimestamp.api(record.get(RAGDOCUMENT.UPDATEDAT))));
                    }
                });
        return List.copyOf(values);
    }

    @Override
    public void markDispatchTerminal(RagDispatchRecord record, RagDispatchStatus status) {
        if (status == RagDispatchStatus.QUEUED || status == RagDispatchStatus.RUNNING) return;
        database.transactionResult(transaction -> {
            LockedReference locked = lockReference(
                    transaction, record.novelId(), record.referenceId());
            if (!pending(locked, record.contentHash())
                    || !DatabaseTimestamp.sameInstant(
                            locked.document().getUpdatedat(), record.generation())) {
                return null;
            }
            if (boundRun(transaction, record.referenceId(), record.contentHash(), record.generation()) != null) return null;
            locked.document().setStatus(Ragdocumentstatus.failed);
            locked.document().setErrormessage(
                    "智能体索引任务已终止：" + status.name().toLowerCase(java.util.Locale.ROOT));
            locked.document().store();
            return null;
        });
    }

    static LockedReference lockReference(
            DSLContext transaction, String novelId, String referenceId) {
        ReferencematerialRecord reference = transaction.selectFrom(REFERENCEMATERIAL)
                .where(REFERENCEMATERIAL.ID.eq(referenceId)
                        .and(REFERENCEMATERIAL.NOVELID.eq(novelId)))
                .forUpdate()
                .fetchOne();
        if (reference == null) throw notFound();
        RagdocumentRecord document = requireDocument(transaction, novelId, referenceId, true);
        return new LockedReference(reference, document);
    }

    static RagdocumentRecord requireDocument(
            DSLContext context, String novelId, String referenceId, boolean lock) {
        var query = context.selectFrom(RAGDOCUMENT)
                .where(RAGDOCUMENT.NOVELID.eq(novelId)
                        .and(RAGDOCUMENT.SOURCETYPE.eq(Ragsourcetype.reference_material))
                        .and(RAGDOCUMENT.SOURCEID.eq(referenceId)));
        RagdocumentRecord document = lock
                ? query.forUpdate().fetchOne()
                : query.fetchOne();
        if (document == null) {
            throw new ApiException(409, "RAG_DOCUMENT_MISSING", "检索文档不存在");
        }
        return document;
    }

    private static void requireCurrentHash(
            LockedReference locked, String expectedContentHash) {
        if (!RagRules.sha256(locked.reference().getContent()).equals(expectedContentHash)
                || !locked.document().getContenthash().equals(expectedContentHash)) {
            throw stale();
        }
    }

    private void requireCurrentJob(
            DSLContext transaction,
            LockedReference locked,
            String expectedContentHash,
            String taskId,
            String runId) {
        requireCurrentHash(locked, expectedContentHash);
        if (boundRun(transaction, locked.reference().getId(), expectedContentHash,
                DatabaseTimestamp.api(locked.document().getUpdatedat())) != null) throw stale();
        RagJobIdentity current = RagJobIdentity.create(
                locked.reference().getId(),
                expectedContentHash,
                DatabaseTimestamp.api(locked.document().getUpdatedat()));
        if (!current.taskId().equals(taskId) || !current.runId().equals(runId)) {
            throw stale();
        }
    }

    private static boolean pending(LockedReference locked, String expectedContentHash) {
        return RagRules.sha256(locked.reference().getContent()).equals(expectedContentHash)
                && locked.document().getContenthash().equals(expectedContentHash)
                && locked.document().getStatus() == Ragdocumentstatus.disabled
                && WAITING.equals(locked.document().getErrormessage());
    }

    private static ReferenceSnapshot snapshot(
            ReferencematerialRecord reference, RagdocumentRecord document) {
        String status = document == null ? "disabled" : document.getStatus().getLiteral();
        String hash = document == null
                ? RagRules.sha256(reference.getContent())
                : document.getContenthash();
        return new ReferenceSnapshot(
                reference.getId(),
                reference.getTitle(),
                reference.getType().getLiteral(),
                reference.getContent(),
                reference.getSourceurl(),
                status,
                hash,
                publicError(document),
                DatabaseTimestamp.api(reference.getCreatedat()),
                DatabaseTimestamp.api(reference.getUpdatedat()));
    }

    private static String publicError(RagdocumentRecord document) {
        if (document == null || document.getStatus() == Ragdocumentstatus.ready) return null;
        if (document.getStatus() == Ragdocumentstatus.failed) return "索引生成失败";
        String message = document.getErrormessage();
        if (WAITING.equals(message) || DISABLED.equals(message)) return message;
        return message == null ? null : "检索索引暂不可用";
    }

    private static boolean same(ReferencematerialRecord value, ReferenceData data) {
        return value.getTitle().equals(data.title())
                && value.getType().getLiteral().equals(data.type())
                && value.getContent().equals(data.content())
                && Objects.equals(value.getSourceurl(), data.sourceUrl());
    }

    private static boolean changed(PatchField<String> patch, String current) {
        return patch.present() && !Objects.equals(patch.value(), current);
    }

    private static String vectorLiteral(List<BigDecimal> vector) {
        StringBuilder result = new StringBuilder("[");
        for (int index = 0; index < vector.size(); index++) {
            if (index > 0) result.append(',');
            result.append(vector.get(index).toString());
        }
        return result.append(']').toString();
    }

    private static void requireOwner(DSLContext context, String novelId, String userId) {
        String owner = context.select(NOVEL.USERID)
                .from(NOVEL)
                .where(NOVEL.ID.eq(novelId))
                .fetchOne(NOVEL.USERID);
        if (!Objects.equals(owner, userId)) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
    }

    private static void lockNovel(DSLContext context, String novelId, String userId) {
        String value = context.select(NOVEL.ID)
                .from(NOVEL)
                .where(NOVEL.ID.eq(novelId).and(NOVEL.USERID.eq(userId)))
                .forUpdate()
                .fetchOne(NOVEL.ID);
        if (value == null) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
    }

    private static void requireVersion(LocalDateTime current, OffsetDateTime expected) {
        if (!DatabaseTimestamp.sameInstant(current, expected)) {
            throw new ApiException(
                    409,
                    "REFERENCE_VERSION_CONFLICT",
                    "资源版本已变化，请重新读取",
                    java.util.Collections.singletonMap(
                            "currentUpdatedAt", DatabaseTimestamp.api(current)));
        }
    }

    private static ApiException createConflict() {
        return new ApiException(409, "RESOURCE_CREATE_CONFLICT", "创建请求已绑定其他内容");
    }

    private static ApiException notFound() {
        return new ApiException(404, "REFERENCE_NOT_FOUND", "参考资料不存在");
    }

    private static ApiException stale() {
        return new ApiException(409, "RAG_INDEX_STALE", "参考资料内容已变化，拒绝写入过期索引结果");
    }

    private static ApiException terminalConflict() {
        return new ApiException(409, "RAG_INDEX_TERMINAL_CONFLICT", "索引任务已进入其他终态");
    }

    private static ApiException embeddingCountMismatch() {
        return new ApiException(422, "EMBEDDING_COUNT_MISMATCH", "嵌入向量数量与资料分块数量不一致");
    }

    record LockedReference(
            ReferencematerialRecord reference, RagdocumentRecord document) {}

    /** 新代次的空结果/容量失败在 Core 确定性收敛，不触发供应商，也不撤销资料 CRUD。 */
    private void prepareNewIndex(DSLContext transaction, String userId, ReferencematerialRecord reference,
            RagdocumentRecord document, boolean indexEnabled) {
        if (!indexEnabled) return;
        String content = reference.getContent();
        int count = content.codePointCount(0, content.length());
        if (count == 0 || count > RagRules.MAX_CHUNK_CODE_POINTS * RagRules.MAX_INDEX_CHUNKS) {
            document.setStatus(count == 0 ? Ragdocumentstatus.ready : Ragdocumentstatus.failed);
            document.setErrormessage(count == 0 ? null : "索引生成失败");
            document.store();
            return;
        }
        RagIndexRunStarter starter = starters.get();
        if (starter != null) {
            try {
                starter.bindNewGeneration(transaction, userId, reference.getNovelid(), reference.getId(),
                        content, document.getContenthash(), DatabaseTimestamp.api(document.getUpdatedat()));
            } catch (RagIndexRegistrationUnavailable exception) {
                // 该精确异常仅发生在任何 Run 写入前；SQL 或登记中途错误绝不能被吞掉。
                document.setStatus(Ragdocumentstatus.failed);
                document.setErrormessage(REGISTRATION_UNAVAILABLE);
                document.store();
            }
        }
    }

    private void lockUserBeforeNovel(DSLContext transaction, String userId) {
        if (durableSchemaReady) transaction.fetchOne("SELECT id FROM public.\"User\" WHERE id=? FOR KEY SHARE", userId);
    }

    DurableRagIndexRun boundRun(DSLContext transaction, String referenceId, String hash, OffsetDateTime generation) {
        if (!durableSchemaReady) return null;
        Record run = transaction.fetchOne("""
                SELECT id FROM public."WorkflowRun" WHERE "engineVersion"=2 AND "sourceType"='rag_index_v2'
                  AND "sourceId"=? AND "idempotencyKey"=?
                """, referenceId, RagJobIdentity.create(referenceId, hash, generation).runId());
        return run == null ? null : DurableRagIndexRun.load(transaction, json, run.get("id", String.class));
    }

    RagDispatchStatus recordedSubmission(String userId, String novelId, String referenceId, String hash, OffsetDateTime generation) {
        return database.transactionResult(tx -> {
            requireOwner(tx, novelId, userId);
            LockedReference locked = lockReference(tx, novelId, referenceId);
            requireCurrentHash(locked, hash);
            if (!DatabaseTimestamp.sameInstant(locked.document().getUpdatedat(), generation)) throw stale();
            if (REGISTRATION_UNAVAILABLE.equals(locked.document().getErrormessage())) {
                throw new RagSubmissionException("RAG_INDEX_UNAVAILABLE");
            }
            DurableRagIndexRun run = boundRun(tx, referenceId, hash, generation);
            if (run != null) {
                if (!userId.equals(run.userId()) || !novelId.equals(run.novelId())) throw stale();
                return switch (run.status()) {
                    case "pending" -> RagDispatchStatus.QUEUED;
                    case "running" -> RagDispatchStatus.RUNNING;
                    case "completed" -> RagDispatchStatus.COMPLETED;
                    case "failed" -> RagDispatchStatus.FAILED;
                    case "cancelled" -> RagDispatchStatus.CANCELLED;
                    default -> throw new IllegalArgumentException("RAG 运行状态无效");
                };
            }
            return switch (locked.document().getStatus()) {
                case ready -> RagDispatchStatus.COMPLETED;
                case failed -> RagDispatchStatus.FAILED;
                default -> null;
            };
        });
    }
}
