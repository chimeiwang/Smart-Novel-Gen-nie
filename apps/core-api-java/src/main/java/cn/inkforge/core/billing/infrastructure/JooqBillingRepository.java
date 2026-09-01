package cn.inkforge.core.billing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.CREDITLEDGER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.STYLEPORTRAITTASK;
import static cn.inkforge.core.db.generated.Tables.TOKENUSAGE;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.VIDEOADAPTATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOGENERATIONTASK;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;
import static cn.inkforge.core.db.generated.Tables.WRITINGSTYLE;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.core.billing.application.AuthorizationContext;
import cn.inkforge.core.billing.application.BillingRepository;
import cn.inkforge.core.billing.application.ChargeResult;
import cn.inkforge.core.billing.application.ChargeUsage;
import cn.inkforge.core.billing.application.InsufficientCreditsException;
import cn.inkforge.core.billing.application.LedgerSnapshot;
import cn.inkforge.core.billing.application.SummarySnapshot;
import cn.inkforge.core.billing.application.TaskUsageCallSnapshot;
import cn.inkforge.core.billing.application.UsageConflictException;
import cn.inkforge.core.billing.application.UsageDataIntegrityException;
import cn.inkforge.core.billing.application.UsagePair;
import cn.inkforge.core.billing.application.UsageSnapshot;
import cn.inkforge.core.billing.domain.BillingPricing;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Workflowrunkind;
import cn.inkforge.core.db.generated.enums.Workflowrunstatus;
import cn.inkforge.core.db.generated.tables.records.CreditledgerRecord;
import cn.inkforge.core.db.generated.tables.records.TokenusageRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Field;
import org.jooq.Record;
import org.jooq.impl.DSL;

/**
 * PostgreSQL 计费与用量事实仓储。
 *
 * <p>授权先通过任务到用户的真实归属链解析，覆盖写作、质量、文风和视频任务；扣费按 {@code requestId}
 * 串行化，并在一个短事务内完成余额条件扣减、账本与 TokenUsage。Redis 或模型回调不能成为余额权威。
 */
final class JooqBillingRepository implements BillingRepository {

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;

    JooqBillingRepository(CoreDatabase database, CuidV1Generator ids, Clock clock) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public AuthorizationContext authorizationContext(
            String userId, String taskId, String novelId) {
        return database.dsl().transactionResult(configuration ->
                authorizationContext(DSL.using(configuration), userId, taskId, novelId));
    }

    private static AuthorizationContext authorizationContext(
            DSLContext context, String userId, String taskId, String novelId) {
        // V1 grant 与 V2 预留统一以 User 行作为跨引擎临界区。这里只冻结授权读取；真正扣费仍会在
        // charge 事务内再次锁 User、重算 outstanding reservation，不能信任较早的 grant 快照。
        Long lockedBalance = context.select(USER.CREDITBALANCEMICROS)
                .from(USER)
                .where(USER.ID.eq(userId))
                .forUpdate()
                .fetchOne(USER.CREDITBALANCEMICROS);
        if (lockedBalance == null) return null;
        Long balance = context.select(USER.CREDITBALANCEMICROS)
                .from(USER)
                .join(NOVEL)
                .on(NOVEL.USERID.eq(USER.ID))
                .join(WRITINGTASK)
                .on(WRITINGTASK.NOVELID.eq(NOVEL.ID))
                .where(
                        USER.ID.eq(userId),
                        NOVEL.ID.eq(novelId),
                        WRITINGTASK.ID.eq(taskId))
                .fetchOne(USER.CREDITBALANCEMICROS);
        if (balance == null && novelId.startsWith("style:")) {
            String styleId = novelId.substring("style:".length());
            balance = context.select(USER.CREDITBALANCEMICROS)
                    .from(USER)
                    .join(WRITINGSTYLE)
                    .on(WRITINGSTYLE.USERID.eq(USER.ID))
                    .join(STYLEPORTRAITTASK)
                    .on(STYLEPORTRAITTASK.STYLEID.eq(WRITINGSTYLE.ID))
                    .where(
                            USER.ID.eq(userId),
                            WRITINGSTYLE.ID.eq(styleId),
                            STYLEPORTRAITTASK.ID.eq(taskId))
                    .fetchOne(USER.CREDITBALANCEMICROS);
        } else if (balance == null) {
            // 没有来源 WritingTask 的质量任务按跨服务契约使用 WorkflowRun.id 计费。必须沿活动运行的
            // 完整归属链授权，不能把公开检查项 ID 当成当前队列任务 ID，也不能只凭 runId 命中任意运行。
            balance = context.select(USER.CREDITBALANCEMICROS)
                    .from(USER)
                    .join(NOVEL)
                    .on(NOVEL.USERID.eq(USER.ID))
                    .join(CHAPTER)
                    .on(CHAPTER.NOVELID.eq(NOVEL.ID))
                    .join(CHAPTERQUALITYCHECK)
                    .on(CHAPTERQUALITYCHECK.CHAPTERID.eq(CHAPTER.ID))
                    .join(WORKFLOWRUN)
                    .on(
                            WORKFLOWRUN.SOURCEID.eq(CHAPTERQUALITYCHECK.ID),
                            WORKFLOWRUN.NOVELID.eq(NOVEL.ID),
                            WORKFLOWRUN.CHAPTERID.eq(CHAPTER.ID),
                            WORKFLOWRUN.USERID.eq(USER.ID))
                    .where(
                            USER.ID.eq(userId),
                            NOVEL.ID.eq(novelId),
                            CHAPTERQUALITYCHECK.STATUS.eq(Qualitycheckstatus.running),
                            WORKFLOWRUN.ID.eq(taskId),
                            WORKFLOWRUN.KIND.eq(Workflowrunkind.quality_check),
                            WORKFLOWRUN.SOURCETYPE.eq("quality_check"),
                            WORKFLOWRUN.STATUS.in(
                                    Workflowrunstatus.pending,
                                    Workflowrunstatus.running))
                    .fetchOne(USER.CREDITBALANCEMICROS);
            if (balance == null) {
                // 观察期仍需兼容冻结基线中直接使用检查项 ID 的历史计费调用；当前新运行不会走这条分支。
                balance = context.select(USER.CREDITBALANCEMICROS)
                        .from(USER)
                        .join(NOVEL)
                        .on(NOVEL.USERID.eq(USER.ID))
                        .join(CHAPTER)
                        .on(CHAPTER.NOVELID.eq(NOVEL.ID))
                        .join(CHAPTERQUALITYCHECK)
                        .on(CHAPTERQUALITYCHECK.CHAPTERID.eq(CHAPTER.ID))
                        .where(
                                USER.ID.eq(userId),
                                NOVEL.ID.eq(novelId),
                                CHAPTERQUALITYCHECK.ID.eq(taskId))
                        .fetchOne(USER.CREDITBALANCEMICROS);
            }
        }
        String resourceKind = "default";
        if (balance == null) {
            balance = context.select(USER.CREDITBALANCEMICROS)
                    .from(USER)
                    .join(NOVEL)
                    .on(NOVEL.USERID.eq(USER.ID))
                    .join(VIDEOPROJECT)
                    .on(VIDEOPROJECT.NOVELID.eq(NOVEL.ID))
                    .join(VIDEOGENERATIONTASK)
                    .on(VIDEOGENERATIONTASK.PROJECTID.eq(VIDEOPROJECT.ID))
                    .where(
                            USER.ID.eq(userId),
                            NOVEL.ID.eq(novelId),
                            VIDEOGENERATIONTASK.ID.eq(taskId),
                            VIDEOGENERATIONTASK.STATUS.in(
                                    "pending", "submitted", "processing"))
                    .fetchOne(USER.CREDITBALANCEMICROS);
            if (balance != null) {
                resourceKind = "video";
            }
        }
        if (balance == null) {
            balance = context.select(USER.CREDITBALANCEMICROS)
                    .from(USER)
                    .join(NOVEL)
                    .on(NOVEL.USERID.eq(USER.ID))
                    .join(VIDEOADAPTATIONTASK)
                    .on(VIDEOADAPTATIONTASK.NOVELID.eq(NOVEL.ID))
                    .where(
                            USER.ID.eq(userId),
                            NOVEL.ID.eq(novelId),
                            VIDEOADAPTATIONTASK.ID.eq(taskId),
                            VIDEOADAPTATIONTASK.STATUS.in(
                                    "pending", "submitted", "processing"))
                    .fetchOne(USER.CREDITBALANCEMICROS);
            if (balance != null) {
                resourceKind = "video";
            }
        }
        return balance == null
                ? null
                : new AuthorizationContext(
                        availableBalance(context, userId, balance), resourceKind);
    }

    @Override
    public Long balance(String userId) {
        return database.dsl().select(USER.CREDITBALANCEMICROS)
                .from(USER)
                .where(USER.ID.eq(userId))
                .fetchOne(USER.CREDITBALANCEMICROS);
    }

    @Override
    public ChargeResult charge(ChargeUsage usage) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            // 锁定计费请求而非用户：同一用户的不同模型调用可并发，同一调用重放只能结算一次。
            transaction.fetch(
                    "SELECT pg_advisory_xact_lock(?)", advisoryLockKey(usage.requestId()));
            if (workflowReservationOwnsRequestId(transaction, usage.requestId())) {
                throw new UsageConflictException();
            }
            long amount = BillingPricing.usageCostMicros(
                    usage.promptTokens(),
                    usage.cachedTokens(),
                    usage.completionTokens());
            TokenusageRecord existing = transaction.selectFrom(TOKENUSAGE)
                    .where(TOKENUSAGE.REQUESTID.eq(usage.requestId()))
                    .fetchOne();
            if (existing != null) {
                return idempotentResult(transaction, existing, usage, amount);
            }
            if (amount > 0) {
                // Java 切换期先识别历史 Python 账本，避免已有扣费缺少 TokenUsage 时再次扣款。
                ChargeResult legacy = legacyResult(transaction, usage, amount);
                if (legacy != null) {
                    return legacy;
                }
            }
            // V1 结算仍沿用原 grant/report 契约，但不得花掉 V2 已在 User 行锁内保留的额度。
            // 迁移前的 V1-only schema 没有 Reservation 表时，availableBalance 保持原行为。
            Long settledBalance = transaction.select(USER.CREDITBALANCEMICROS)
                    .from(USER)
                    .where(USER.ID.eq(usage.userId()))
                    .forUpdate()
                    .fetchOne(USER.CREDITBALANCEMICROS);
            // V2 对账不使用 V1 requestId advisory lock。User 锁后必须重查 reservation 与
            // TokenUsage，避免“V1 先查无记录 → 等 User → V2 提交 → V1 唯一键 500”。
            if (workflowReservationOwnsRequestId(transaction, usage.requestId())) {
                throw new UsageConflictException();
            }
            TokenusageRecord serializedExisting = transaction.selectFrom(TOKENUSAGE)
                    .where(TOKENUSAGE.REQUESTID.eq(usage.requestId()))
                    .fetchOne();
            if (serializedExisting != null) {
                return idempotentResult(transaction, serializedExisting, usage, amount);
            }
            if (settledBalance == null
                    || availableBalance(transaction, usage.userId(), settledBalance) < amount) {
                throw new InsufficientCreditsException();
            }
            long balanceAfter = Math.subtractExact(settledBalance, amount);
            if (amount > 0) {
                transaction.update(USER)
                        .set(USER.CREDITBALANCEMICROS, balanceAfter)
                        .where(USER.ID.eq(usage.userId()))
                        .execute();
            }
            LocalDateTime now = DatabaseTimestamp.now(clock);
            // 余额、CreditLedger 与 TokenUsage 同事务提交；不能出现“已扣余额但查不到调用明细”。
            if (amount > 0) {
                transaction.insertInto(CREDITLEDGER)
                        .set(CREDITLEDGER.ID, ids.next())
                        .set(CREDITLEDGER.USERID, usage.userId())
                        .set(CREDITLEDGER.TYPE, "ai_charge")
                        .set(CREDITLEDGER.AMOUNTMICROS, -amount)
                        .set(CREDITLEDGER.BALANCEAFTERMICROS, balanceAfter)
                        .set(CREDITLEDGER.MODEL, usage.model())
                        .set(CREDITLEDGER.PROMPTTOKENS, usage.promptTokens())
                        .set(CREDITLEDGER.CACHEDTOKENS, usage.cachedTokens())
                        .set(CREDITLEDGER.COMPLETIONTOKENS, usage.completionTokens())
                        .set(CREDITLEDGER.TOTALTOKENS, usage.totalTokens())
                        .set(CREDITLEDGER.AGENTID, usage.agentId())
                        .set(CREDITLEDGER.NOVELID, usage.novelId())
                        .set(CREDITLEDGER.REQUESTID, usage.requestId())
                        .set(CREDITLEDGER.NOTE, "人工智能模型调用")
                        .set(CREDITLEDGER.CREATEDAT, now)
                        .execute();
            }
            transaction.insertInto(TOKENUSAGE)
                    .set(TOKENUSAGE.ID, ids.next())
                    .set(TOKENUSAGE.USERID, usage.userId())
                    .set(TOKENUSAGE.MODEL, usage.model())
                    .set(TOKENUSAGE.PROMPTTOKENS, usage.promptTokens())
                    .set(TOKENUSAGE.CACHEDTOKENS, usage.cachedTokens())
                    .set(TOKENUSAGE.PROMPTCACHEMISSTOKENS, usage.promptCacheMissTokens())
                    .set(TOKENUSAGE.COMPLETIONTOKENS, usage.completionTokens())
                    .set(TOKENUSAGE.REASONINGTOKENS, usage.reasoningTokens())
                    .set(TOKENUSAGE.TOTALTOKENS, usage.totalTokens())
                    .set(TOKENUSAGE.AGENTID, usage.agentId())
                    .set(TOKENUSAGE.NOVELID, usage.novelId())
                    .set(TOKENUSAGE.REQUESTID, usage.requestId())
                    .set(TOKENUSAGE.TASKID, usage.taskId())
                    .set(TOKENUSAGE.RUNID, usage.runId())
                    .set(TOKENUSAGE.CREATEDAT, now)
                    .execute();
            return new ChargeResult(
                    usage.requestId(), amount, balanceAfter, false);
        });
    }

    @Override
    public SummarySnapshot summary(String userId) {
        Record user = database.dsl().select(USER.USERNAME, USER.CREDITBALANCEMICROS)
                .from(USER)
                .where(USER.ID.eq(userId))
                .fetchOne();
        if (user == null) {
            return null;
        }
        List<LedgerSnapshot> entries = database.dsl().selectFrom(CREDITLEDGER)
                .where(CREDITLEDGER.USERID.eq(userId))
                .orderBy(CREDITLEDGER.CREATEDAT.desc(), CREDITLEDGER.ID.desc())
                .limit(20)
                .fetch(record -> new LedgerSnapshot(
                        record.getId(),
                        record.getType(),
                        record.getAmountmicros(),
                        record.getBalanceaftermicros(),
                        record.getNote(),
                        DatabaseTimestamp.api(record.getCreatedat())));
        return new SummarySnapshot(
                user.get(USER.USERNAME), user.get(USER.CREDITBALANCEMICROS), entries);
    }

    @Override
    public UsagePair usage(String userId, OffsetDateTime monthStart) {
        return new UsagePair(
                aggregate(database.dsl(), usageOwnerCondition(userId)),
                aggregate(
                        database.dsl(),
                        usageOwnerCondition(userId).and(TOKENUSAGE.CREATEDAT.ge(
                                DatabaseTimestamp.database(monthStart)))));
    }

    @Override
    public List<TaskUsageCallSnapshot> taskUsage(String userId, String taskId) {
        String owned = database.dsl().select(WRITINGTASK.ID)
                .from(WRITINGTASK)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(WRITINGTASK.ID.eq(taskId), NOVEL.USERID.eq(userId))
                .fetchOne(WRITINGTASK.ID);
        if (owned == null) {
            return null;
        }
        return database.dsl().selectFrom(TOKENUSAGE)
                .where(TOKENUSAGE.USERID.eq(userId), TOKENUSAGE.TASKID.eq(taskId))
                .orderBy(TOKENUSAGE.CREATEDAT.asc(), TOKENUSAGE.ID.asc())
                .fetch(this::taskCall);
    }

    private static org.jooq.Condition usageOwnerCondition(String userId) {
        return TOKENUSAGE.USERID.eq(userId);
    }

    private static UsageSnapshot aggregate(
            DSLContext context, org.jooq.Condition condition) {
        Field<BigDecimal> prompt = DSL.coalesce(DSL.sum(TOKENUSAGE.PROMPTTOKENS), BigDecimal.ZERO);
        Field<BigDecimal> cached = DSL.coalesce(DSL.sum(TOKENUSAGE.CACHEDTOKENS), BigDecimal.ZERO);
        Field<BigDecimal> completion = DSL.coalesce(DSL.sum(TOKENUSAGE.COMPLETIONTOKENS), BigDecimal.ZERO);
        Field<BigDecimal> total = DSL.coalesce(DSL.sum(TOKENUSAGE.TOTALTOKENS), BigDecimal.ZERO);
        Record row = context.select(prompt, cached, completion, total)
                .from(TOKENUSAGE)
                .where(condition)
                .fetchSingle();
        return new UsageSnapshot(
                row.get(prompt).intValueExact(),
                row.get(cached).intValueExact(),
                row.get(completion).intValueExact(),
                row.get(total).intValueExact());
    }

    private TaskUsageCallSnapshot taskCall(TokenusageRecord record) {
        if (record.getRequestid() == null
                || record.getRequestid().isBlank()
                || record.getRunid() == null
                || record.getRunid().isBlank()) {
            throw new UsageDataIntegrityException(record.getId());
        }
        return new TaskUsageCallSnapshot(
                record.getRequestid(),
                record.getRunid(),
                record.getAgentid(),
                record.getModel(),
                record.getPrompttokens(),
                record.getCachedtokens(),
                record.getPromptcachemisstokens(),
                record.getCompletiontokens(),
                record.getReasoningtokens(),
                record.getTotaltokens(),
                DatabaseTimestamp.api(record.getCreatedat()));
    }

    private static ChargeResult idempotentResult(
            DSLContext transaction,
            TokenusageRecord existing,
            ChargeUsage usage,
            long amount) {
        if (!sameUsage(existing, usage)) {
            throw new UsageConflictException();
        }
        Long balanceAfter;
        if (amount == 0) {
            balanceAfter = transaction.select(USER.CREDITBALANCEMICROS)
                    .from(USER)
                    .where(USER.ID.eq(usage.userId()))
                    .fetchOne(USER.CREDITBALANCEMICROS);
        } else {
            balanceAfter = transaction.select(CREDITLEDGER.BALANCEAFTERMICROS)
                    .from(CREDITLEDGER)
                    .where(
                            CREDITLEDGER.REQUESTID.eq(usage.requestId()),
                            CREDITLEDGER.TYPE.eq("ai_charge"),
                            CREDITLEDGER.AMOUNTMICROS.eq(-amount))
                    .orderBy(CREDITLEDGER.CREATEDAT.asc(), CREDITLEDGER.ID.asc())
                    .limit(1)
                    .fetchOne(CREDITLEDGER.BALANCEAFTERMICROS);
        }
        if (balanceAfter == null) {
            throw new UsageConflictException();
        }
        return new ChargeResult(usage.requestId(), amount, balanceAfter, true);
    }

    private static ChargeResult legacyResult(
            DSLContext transaction, ChargeUsage usage, long amount) {
        List<CreditledgerRecord> entries = transaction.selectFrom(CREDITLEDGER)
                .where(
                        CREDITLEDGER.REQUESTID.eq(usage.requestId()),
                        CREDITLEDGER.TYPE.eq("ai_charge"))
                .orderBy(CREDITLEDGER.CREATEDAT.asc(), CREDITLEDGER.ID.asc())
                .limit(2)
                .fetch();
        if (entries.isEmpty()) {
            return null;
        }
        if (entries.size() != 1 || !sameLegacy(entries.getFirst(), usage, amount)) {
            throw new UsageConflictException();
        }
        return new ChargeResult(
                usage.requestId(), amount, entries.getFirst().getBalanceaftermicros(), true);
    }

    private static boolean sameUsage(TokenusageRecord existing, ChargeUsage usage) {
        return Objects.equals(existing.getUserid(), usage.userId())
                && Objects.equals(existing.getNovelid(), usage.novelId())
                && Objects.equals(existing.getTaskid(), usage.taskId())
                && Objects.equals(existing.getRunid(), usage.runId())
                && Objects.equals(existing.getModel(), usage.model())
                && Objects.equals(existing.getAgentid(), usage.agentId())
                && existing.getPrompttokens() == usage.promptTokens()
                && existing.getCachedtokens() == usage.cachedTokens()
                && Objects.equals(
                        existing.getPromptcachemisstokens(), usage.promptCacheMissTokens())
                && existing.getCompletiontokens() == usage.completionTokens()
                && Objects.equals(existing.getReasoningtokens(), usage.reasoningTokens())
                && existing.getTotaltokens() == usage.totalTokens();
    }

    private static boolean sameLegacy(
            CreditledgerRecord existing, ChargeUsage usage, long amount) {
        return Objects.equals(existing.getUserid(), usage.userId())
                && Objects.equals(existing.getNovelid(), usage.novelId())
                && Objects.equals(existing.getModel(), usage.model())
                && Objects.equals(existing.getAgentid(), usage.agentId())
                && existing.getPrompttokens() == usage.promptTokens()
                && existing.getCachedtokens() == usage.cachedTokens()
                && existing.getCompletiontokens() == usage.completionTokens()
                && existing.getTotaltokens() == usage.totalTokens()
                && existing.getAmountmicros() == -amount
                && usage.promptCacheMissTokens() == null
                && usage.reasoningTokens() == null;
    }

    private static long advisoryLockKey(String requestId) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(requestId.getBytes(StandardCharsets.UTF_8));
            long value = 0;
            for (int index = 0; index < 8; index++) {
                value = (value << 8) | (digest[index] & 0xffL);
            }
            return value;
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JRE 缺少 SHA-256", exception);
        }
    }

    private static long availableBalance(
            DSLContext context, String userId, long settledBalance) {
        Record relation = context.fetchOne(
                "SELECT to_regclass('public.\"WorkflowBillingReservation\"') AS relation");
        if (relation == null || relation.get("relation") == null) return settledBalance;
        BigDecimal outstanding = context.fetchOne(
                        """
                        SELECT COALESCE(sum("reservedMicros"), 0)::numeric AS reserved
                        FROM public."WorkflowBillingReservation"
                        WHERE "userId" = ?
                          AND status IN ('reserved', 'reconciliation_required')
                        """,
                        userId)
                .get("reserved", BigDecimal.class);
        return Math.max(
                0L,
                Math.subtractExact(settledBalance, outstanding.longValueExact()));
    }

    private static boolean workflowReservationOwnsRequestId(
            DSLContext context, String requestId) {
        Record relation = context.fetchOne(
                "SELECT to_regclass('public.\"WorkflowBillingReservation\"') AS relation");
        if (relation == null || relation.get("relation") == null) return false;
        return Boolean.TRUE.equals(context.fetchOne(
                        """
                        SELECT EXISTS (
                          SELECT 1 FROM public."WorkflowBillingReservation"
                          WHERE "requestId" = ?
                        ) AS owned
                        """,
                        requestId)
                .get("owned", Boolean.class));
    }
}
