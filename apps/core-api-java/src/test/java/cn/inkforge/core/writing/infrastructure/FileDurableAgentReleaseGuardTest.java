package cn.inkforge.core.writing.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

class FileDurableAgentReleaseGuardTest {

    private static final String USER_ID = "user-release-guard";
    private static final String NOVEL_ID = "novel-release-guard";
    private static final Instant NOW = Instant.parse("2026-09-01T03:00:00Z");
    private static final String SHA_A = "a".repeat(64);
    private static final String SHA_B = "b".repeat(64);
    private static final String SHA_C = "c".repeat(64);
    private static final String SHA_D = "d".repeat(64);
    private static final String SHA_E = "e".repeat(64);
    private static final ObjectMapper JSON = JsonMapper.builder().build();

    @TempDir
    Path directory;

    private Path guardPath;

    @BeforeEach
    void prepareDirectory() throws IOException {
        Files.setPosixFilePermissions(
                directory, PosixFilePermissions.fromString("rwxr-xr-x"));
        guardPath = directory.resolve("guard.json");
    }

    @Test
    void pending在闭区间起点允许且到期后稳定关闭() throws Exception {
        Files.setPosixFilePermissions(
                directory, PosixFilePermissions.fromString("rwxr-xr-x"));
        writeGuard(guard(
                "pending",
                NOW,
                NOW.plusSeconds(120),
                null,
                USER_ID,
                NOVEL_ID));

        assertThatCode(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID))
                .doesNotThrowAnyException();
        assertThatCode(() -> fileGuard(NOW.plusSeconds(115))
                        .requireFreshStart(USER_ID, NOVEL_ID))
                .doesNotThrowAnyException();
        assertUnavailable(() -> fileGuard(NOW.plusSeconds(115).plusMillis(1))
                .requireFreshStart(USER_ID, NOVEL_ID));
        assertUnavailable(() -> fileGuard(NOW.plusSeconds(120))
                .requireFreshStart(USER_ID, NOVEL_ID));
    }

    @Test
    void pending拒绝超长租期与未来签发且不允许scope漂移() throws Exception {
        writeGuard(guard(
                "pending",
                NOW,
                NOW.plusSeconds(121),
                null,
                USER_ID,
                NOVEL_ID));
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));

        writeGuard(guard(
                "pending",
                NOW.plusSeconds(1),
                NOW.plusSeconds(61),
                null,
                USER_ID,
                NOVEL_ID));
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));

        writeGuard(guard(
                "pending",
                NOW.minusSeconds(1),
                NOW.plusSeconds(60),
                null,
                USER_ID,
                NOVEL_ID));
        assertUnavailable(() -> fileGuard(NOW)
                .requireFreshStart(USER_ID, "novel-release-guard-drift"));

        assertUnavailable(() -> new FileDurableAgentReleaseGuard(
                        guardPath,
                        Clock.fixed(NOW, ZoneOffset.UTC),
                        SHA_A)
                .requireFreshStart(USER_ID, NOVEL_ID));
    }

    @Test
    void committed只凭精确scope与receipt持续允许且拒绝未来签发() throws Exception {
        writeGuard(guard(
                "committed",
                NOW.minusSeconds(3_600),
                null,
                SHA_D,
                USER_ID,
                NOVEL_ID));

        assertThatCode(() -> fileGuard(NOW.plusSeconds(86_400))
                        .requireFreshStart(USER_ID, NOVEL_ID))
                .doesNotThrowAnyException();

        writeGuard(guard(
                "committed",
                NOW.plusSeconds(1),
                null,
                SHA_D,
                USER_ID,
                NOVEL_ID));
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));
    }

    @Test
    void 同一实例每次重读且启动失败不会缓存成永久状态() throws Exception {
        FileDurableAgentReleaseGuard releaseGuard = fileGuard(NOW);

        writeGuard(guard(
                "pending",
                NOW.minusSeconds(1),
                NOW.plusSeconds(60),
                null,
                USER_ID,
                NOVEL_ID));
        assertThatCode(() -> releaseGuard.requireFreshStart(USER_ID, NOVEL_ID))
                .doesNotThrowAnyException();

        Map<String, Object> off = guard(
                "off", null, null, null, USER_ID, NOVEL_ID);
        off.replaceAll((key, value) -> "format".equals(key) || "state".equals(key)
                ? value
                : null);
        writeGuard(off);
        assertUnavailable(() -> releaseGuard.requireFreshStart(USER_ID, NOVEL_ID));
    }

    @Test
    void 缺失off重复字段未知字段与错误null组合全部关闭() throws Exception {
        FileDurableAgentReleaseGuard missing = fileGuard(NOW);
        assertUnavailable(() -> missing.requireFreshStart(USER_ID, NOVEL_ID));
        assertUnavailable(() -> new FileDurableAgentReleaseGuard(
                        null,
                        Clock.fixed(NOW, ZoneOffset.UTC),
                        SHA_E)
                .requireFreshStart(USER_ID, NOVEL_ID));

        Map<String, Object> off = guard(
                "off", null, null, null, USER_ID, NOVEL_ID);
        off.replaceAll((key, value) -> "format".equals(key) || "state".equals(key)
                ? value
                : null);
        writeGuard(off);
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));

        String duplicate = JSON.writeValueAsString(guard(
                        "pending",
                        NOW,
                        NOW.plusSeconds(60),
                        null,
                        USER_ID,
                        NOVEL_ID))
                .replaceFirst("\\{", "{\"state\":\"pending\",");
        writeRaw(duplicate, "r--r--r--");
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));

        Map<String, Object> unknown = guard(
                "pending",
                NOW,
                NOW.plusSeconds(60),
                null,
                USER_ID,
                NOVEL_ID);
        unknown.put("unexpected", true);
        writeGuard(unknown);
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));

        Map<String, Object> wrongPendingReceipt = guard(
                "pending",
                NOW,
                NOW.plusSeconds(60),
                SHA_D,
                USER_ID,
                NOVEL_ID);
        writeGuard(wrongPendingReceipt);
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));
    }

    @Test
    void 可写文件和符号链接都不能成为授权事实() throws Exception {
        writeRaw(
                JSON.writeValueAsString(guard(
                        "pending",
                        NOW,
                        NOW.plusSeconds(60),
                        null,
                        USER_ID,
                        NOVEL_ID)),
                "rw-r--r--");
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));

        writeGuard(guard(
                "pending",
                NOW,
                NOW.plusSeconds(60),
                null,
                USER_ID,
                NOVEL_ID));
        Files.setPosixFilePermissions(
                directory, PosixFilePermissions.fromString("rwxrwx---"));
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));
        Files.setPosixFilePermissions(
                directory, PosixFilePermissions.fromString("rwxr-xr-x"));

        Path target = directory.resolve("target.json");
        Files.deleteIfExists(guardPath);
        Files.writeString(
                target,
                JSON.writeValueAsString(guard(
                        "pending",
                        NOW,
                        NOW.plusSeconds(60),
                        null,
                        USER_ID,
                        NOVEL_ID)),
                StandardCharsets.UTF_8);
        Files.setPosixFilePermissions(
                target, PosixFilePermissions.fromString("r--r--r--"));
        Files.createSymbolicLink(guardPath, target.getFileName());
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));
    }

    @Test
    void 非canonical字节与非0755父目录都稳定关闭() throws Exception {
        Map<String, Object> pending = guard(
                "pending", NOW, NOW.plusSeconds(60), null, USER_ID, NOVEL_ID);
        writeRaw(JSON.writeValueAsString(pending), "r--r--r--");
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));

        writeGuard(pending);
        Files.setPosixFilePermissions(
                directory, PosixFilePermissions.fromString("rwx------"));
        assertUnavailable(() -> fileGuard(NOW).requireFreshStart(USER_ID, NOVEL_ID));
    }

    private FileDurableAgentReleaseGuard fileGuard(Instant now) {
        return new FileDurableAgentReleaseGuard(
                guardPath, Clock.fixed(now, ZoneOffset.UTC), SHA_E);
    }

    private void writeGuard(Map<String, Object> document) throws IOException {
        writeRaw(JSON.writeValueAsString(new TreeMap<>(document)) + "\n", "r--r--r--");
    }

    private void writeRaw(String document, String permissions) throws IOException {
        Files.deleteIfExists(guardPath);
        Files.writeString(guardPath, document, StandardCharsets.UTF_8);
        Files.setPosixFilePermissions(
                guardPath, PosixFilePermissions.fromString(permissions));
    }

    private static Map<String, Object> guard(
            String state,
            Instant issuedAt,
            Instant expiresAt,
            String committedReceiptSha256,
            String userId,
            String novelId) {
        Map<String, Object> document = new LinkedHashMap<>();
        document.put("format", FileDurableAgentReleaseGuard.FORMAT);
        document.put("state", state);
        document.put("lockId", SHA_A);
        document.put("runId", "123456");
        document.put("runAttempt", "1");
        document.put("manifestSha256", SHA_B);
        document.put("controlBundleSha256", SHA_C);
        document.put("canaryScopeSha256", scopeSha256(userId, novelId));
        document.put("executionManifestFingerprint", SHA_E);
        document.put("leaseId", SHA_D);
        document.put("issuedAt", issuedAt == null ? null : issuedAt.toString());
        document.put("expiresAt", expiresAt == null ? null : expiresAt.toString());
        document.put("committedReceiptSha256", committedReceiptSha256);
        return document;
    }

    private static String scopeSha256(String userId, String novelId) {
        String canonical = "{\"novelId\":\"" + novelId + "\",\"userId\":\"" + userId + "\"}";
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(canonical.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private static void assertUnavailable(ThrowingOperation operation) {
        assertThatThrownBy(operation::run)
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code())
                            .isEqualTo("DURABLE_AGENT_RELEASE_GUARD_UNAVAILABLE");
                    assertThat(error.details()).isNull();
                });
    }

    @FunctionalInterface
    private interface ThrowingOperation {
        void run() throws Exception;
    }
}
