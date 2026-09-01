package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.contracts.api.WritingRunStartResponse;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.idempotency.CommandIdempotencyStore;
import cn.inkforge.core.writing.application.ParsedWritingRunStartRequest;
import cn.inkforge.core.writing.application.WritingCommandRepository;
import cn.inkforge.core.writing.application.WritingRunStarter;
import java.util.Objects;

/** 迁移前结构仍可关闭 V1 fresh start；只读重放先于门禁，且门禁前不取业务锁、不写数据。 */
final class V1FreshWritingRunStarter implements WritingRunStarter {

    private final CoreDatabase database;
    private final WritingCommandRepository legacy;
    private final CommandIdempotencyStore idempotency;
    private final boolean freshStartsEnabled;

    V1FreshWritingRunStarter(
            CoreDatabase database,
            WritingCommandRepository legacy,
            CommandIdempotencyStore idempotency,
            boolean freshStartsEnabled) {
        this.database = Objects.requireNonNull(database);
        this.legacy = Objects.requireNonNull(legacy);
        this.idempotency = Objects.requireNonNull(idempotency);
        this.freshStartsEnabled = freshStartsEnabled;
    }

    @Override
    public WritingRunStartResponse start(
            String userId, ParsedWritingRunStartRequest request) {
        String clientRequestId = RoutingWritingRunStarter.clientRequestId(request);
        CommandIdempotencyStore.Resolution existing = database.transactionResult(
                transaction -> idempotency.resolve(
                        transaction, userId, clientRequestId, null));
        if (existing != null) {
            if (existing.recordKind()
                    != CommandIdempotencyStore.RecordKind.WRITING_COMMAND) {
                throw CommandIdempotencyStore.reused(clientRequestId);
            }
            return legacy.start(userId, request);
        }
        if (!freshStartsEnabled) throw V1FreshAgentStartGate.draining();
        return legacy.start(userId, request);
    }
}
