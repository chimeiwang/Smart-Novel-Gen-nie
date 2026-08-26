package cn.inkforge.core.lore.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;

import cn.inkforge.core.db.generated.tables.records.NovelRecord;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.Collections;
import org.jooq.DSLContext;

/** 设定写事务统一的归属、小说锁、advisory lock 与 CAS 门禁。 */
final class LoreTransactionGuard {

    private LoreTransactionGuard() {}

    static void requireOwner(DSLContext context, String novelId, String userId) {
        String owner = context.select(NOVEL.USERID)
                .from(NOVEL)
                .where(NOVEL.ID.eq(novelId))
                .fetchOne(NOVEL.USERID);
        if (owner == null || !owner.equals(userId)) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
    }

    static NovelRecord lockNovel(
            DSLContext transaction, String novelId, String userId) {
        NovelRecord novel = transaction.selectFrom(NOVEL)
                .where(NOVEL.ID.eq(novelId))
                .forUpdate()
                .fetchOne();
        if (novel == null
                || novel.getUserid() == null
                || !novel.getUserid().equals(userId)) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
        transaction.fetch("select pg_advisory_xact_lock(?)", advisoryKey(novelId));
        return novel;
    }

    static void requireVersion(
            LocalDateTime current, OffsetDateTime expected, String code) {
        if (!DatabaseTimestamp.sameInstant(current, expected)) {
            throw new ApiException(
                    409,
                    code,
                    "资源版本已变化，请重新读取",
                    Collections.singletonMap(
                            "currentUpdatedAt", DatabaseTimestamp.api(current)));
        }
    }

    private static long advisoryKey(String novelId) {
        return ByteBuffer.wrap(sha256(novelId.getBytes(StandardCharsets.UTF_8))).getLong();
    }

    private static byte[] sha256(byte[] value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JDK 缺少 SHA-256", exception);
        }
    }
}
