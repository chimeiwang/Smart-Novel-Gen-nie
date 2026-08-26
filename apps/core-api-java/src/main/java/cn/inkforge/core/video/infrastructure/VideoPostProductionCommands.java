package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import org.jooq.DSLContext;
import tools.jackson.databind.ObjectMapper;

/** 后期制作各命令仓储共用的幂等键规范、事务锁和规范哈希。 */
final class VideoPostProductionCommands {

    private VideoPostProductionCommands() {}

    static void lock(
            DSLContext context, String namespace, String userId, String clientRequestId) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(("video-post-production\0"
                                    + namespace
                                    + "\0"
                                    + userId
                                    + "\0"
                                    + clientRequestId)
                            .getBytes(StandardCharsets.UTF_8));
            context.fetch(
                    "SELECT pg_advisory_xact_lock(?)",
                    ByteBuffer.wrap(digest, 0, Long.BYTES).getLong());
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }

    static String requestId(String value) {
        String normalized = value == null ? "" : value.strip();
        int length = normalized.codePointCount(0, normalized.length());
        if (length < 16 || length > 128) {
            throw error(422, "VALIDATION_ERROR", "请求标识长度无效");
        }
        return normalized;
    }

    static String hash(Object value, ObjectMapper json) {
        return CommandIdempotency.sha256(
                CommandIdempotency.canonicalJsonBytes(value, json));
    }

    static ApiException error(int status, String code, String message) {
        return new ApiException(status, code, message);
    }
}
