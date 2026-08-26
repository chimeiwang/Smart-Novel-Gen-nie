package cn.inkforge.core.novels.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;

import cn.inkforge.core.db.generated.tables.records.NovelRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import java.util.Objects;
import java.util.function.BiFunction;
import org.jooq.DSLContext;
import org.jooq.impl.DSL;

/** 在归属查询前建立只读可重复读快照，保证跨分组工作区不会拼接不同时刻的数据。 */
final class WorkspaceReadTransaction {

    private final CoreDatabase database;

    WorkspaceReadTransaction(CoreDatabase database) {
        this.database = Objects.requireNonNull(database);
    }

    <T> T read(
            String novelId,
            String userId,
            boolean hideForbidden,
            BiFunction<DSLContext, NovelRecord, T> work) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            // PostgreSQL 要求该语句位于事务中且先于任何查询。
            transaction.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY");
            NovelRecord novel = transaction.selectFrom(NOVEL)
                    .where(NOVEL.ID.eq(novelId))
                    .fetchOne();
            if (novel == null
                    || (hideForbidden && !Objects.equals(novel.getUserid(), userId))) {
                throw new ApiException(404, "NOVEL_NOT_FOUND", "小说不存在");
            }
            if (!Objects.equals(novel.getUserid(), userId)) {
                throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
            }
            return work.apply(transaction, novel);
        });
    }
}
