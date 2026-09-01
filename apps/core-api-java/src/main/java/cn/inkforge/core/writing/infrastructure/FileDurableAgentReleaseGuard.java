package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.core.platform.http.ApiException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Pattern;
import tools.jackson.core.StreamReadFeature;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/** 每次 fresh V2 start 都从只读持久文件重新判定的 allowlist release guard。 */
final class FileDurableAgentReleaseGuard implements DurableAgentReleaseGuard {

    static final String FORMAT = "inkforge-durable-agent-v2-release-guard/1";
    private static final int MAXIMUM_BYTES = 16 * 1024;
    private static final Duration MAXIMUM_PENDING_TTL = Duration.ofSeconds(120);
    private static final Duration MINIMUM_PENDING_REMAINING = Duration.ofSeconds(5);
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");
    private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
    private static final Pattern DECIMAL = Pattern.compile("[1-9][0-9]{0,19}");
    private static final Set<PosixFilePermission> READ_ONLY_FILE = Set.of(
            PosixFilePermission.OWNER_READ,
            PosixFilePermission.GROUP_READ,
            PosixFilePermission.OTHERS_READ);
    private static final Set<String> GUARD_FIELDS = Set.of(
            "format",
            "state",
            "lockId",
            "runId",
            "runAttempt",
            "manifestSha256",
            "controlBundleSha256",
            "canaryScopeSha256",
            "executionManifestFingerprint",
            "leaseId",
            "issuedAt",
            "expiresAt",
            "committedReceiptSha256");
    private static final ObjectMapper JSON = JsonMapper.builder()
            .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
            .build();

    private final Path path;
    private final Clock clock;
    private final String expectedExecutionManifestFingerprint;

    FileDurableAgentReleaseGuard(
            Path path, Clock clock, String expectedExecutionManifestFingerprint) {
        this.path = path == null ? null : path.normalize();
        this.clock = Objects.requireNonNull(clock);
        if (expectedExecutionManifestFingerprint == null
                || !SHA256.matcher(expectedExecutionManifestFingerprint).matches()) {
            throw new IllegalArgumentException("当前 execution manifest fingerprint 无效");
        }
        this.expectedExecutionManifestFingerprint = expectedExecutionManifestFingerprint;
        // 启动只预读同一份持久事实，不让损坏 guard 阻断既有 Run 的回调、取消或物化入口。
        // fresh V2 不信任这个缓存，下面每次都重新打开并复验文件。
        inspectAtStartup();
    }

    @Override
    public void requireFreshStart(String userId, String novelId) {
        try {
            GuardDocument guard = readAndValidate();
            String expectedScope = scopeSha256(userId, novelId);
            if (!MessageDigest.isEqual(
                    expectedScope.getBytes(StandardCharsets.US_ASCII),
                    guard.canaryScopeSha256().getBytes(StandardCharsets.US_ASCII))) {
                throw new InvalidGuardException();
            }
        } catch (IOException | RuntimeException exception) {
            throw unavailable();
        }
    }

    private void inspectAtStartup() {
        try {
            readAndValidate();
        } catch (IOException | RuntimeException exception) {
            // 启动时把不可验证事实视为关闭；不能让它阻断已有 Run 的收敛 HTTP 入口。
        }
    }

    private GuardDocument readAndValidate() throws IOException {
        byte[] bytes = readSecureFile();
        Map<String, Object> document = JSON.readValue(
                bytes, new TypeReference<Map<String, Object>>() {});
        byte[] canonical = (JSON.writeValueAsString(new TreeMap<>(document)) + "\n")
                .getBytes(StandardCharsets.UTF_8);
        if (!Arrays.equals(bytes, canonical)) throw new InvalidGuardException();
        String format = text(document, "format");
        String state = text(document, "state");
        if (!FORMAT.equals(format)) throw new InvalidGuardException();
        if (!document.keySet().equals(GUARD_FIELDS)) throw new InvalidGuardException();
        if (!("pending".equals(state) || "committed".equals(state))) {
            throw new InvalidGuardException();
        }

        String lockId = sha256(document, "lockId");
        String runId = decimal(document, "runId");
        String runAttempt = decimal(document, "runAttempt");
        String manifestSha256 = sha256(document, "manifestSha256");
        String controlBundleSha256 = sha256(document, "controlBundleSha256");
        String canaryScopeSha256 = sha256(document, "canaryScopeSha256");
        String executionManifestFingerprint = sha256(
                document, "executionManifestFingerprint");
        if (!MessageDigest.isEqual(
                expectedExecutionManifestFingerprint.getBytes(StandardCharsets.US_ASCII),
                executionManifestFingerprint.getBytes(StandardCharsets.US_ASCII))) {
            throw new InvalidGuardException();
        }
        String leaseId = sha256(document, "leaseId");
        Instant issuedAt = instant(document, "issuedAt");
        Instant now = clock.instant();
        if (now.isBefore(issuedAt)) throw new InvalidGuardException();
        Instant expiresAt;
        if ("pending".equals(state)) {
            expiresAt = instant(document, "expiresAt");
            requireNull(document, "committedReceiptSha256");
            Duration ttl = Duration.between(issuedAt, expiresAt);
            if (ttl.isZero()
                    || ttl.isNegative()
                    || ttl.compareTo(MAXIMUM_PENDING_TTL) > 0) {
                throw new InvalidGuardException();
            }
            if (!now.isBefore(expiresAt)) {
                throw new InvalidGuardException();
            }
            if (Duration.between(now, expiresAt)
                            .compareTo(MINIMUM_PENDING_REMAINING)
                    < 0) {
                throw new InvalidGuardException();
            }
        } else {
            requireNull(document, "expiresAt");
            expiresAt = null;
            sha256(document, "committedReceiptSha256");
        }
        return new GuardDocument(
                state,
                lockId,
                runId,
                runAttempt,
                manifestSha256,
                controlBundleSha256,
                canaryScopeSha256,
                executionManifestFingerprint,
                leaseId,
                issuedAt,
                expiresAt);
    }

    private byte[] readSecureFile() throws IOException {
        if (path == null || !path.isAbsolute() || path.getParent() == null) {
            throw new InvalidGuardException();
        }
        Path parent = path.getParent();
        BasicFileAttributes parentBefore = secureParent(parent);
        BasicFileAttributes before = secureFileAttributes(path);
        if (before.size() < 2 || before.size() > MAXIMUM_BYTES) {
            throw new InvalidGuardException();
        }
        byte[] bytes = new byte[(int) before.size()];
        Set<OpenOption> options = Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS);
        try (FileChannel channel = FileChannel.open(path, options)) {
            ByteBuffer buffer = ByteBuffer.wrap(bytes);
            while (buffer.hasRemaining()) {
                if (channel.read(buffer) < 0) throw new InvalidGuardException();
            }
            if (channel.read(ByteBuffer.allocate(1)) >= 0) throw new InvalidGuardException();
        }
        BasicFileAttributes after = secureFileAttributes(path);
        BasicFileAttributes parentAfter = secureParent(parent);
        if (!sameIdentity(before, after) || !sameIdentity(parentBefore, parentAfter)) {
            throw new InvalidGuardException();
        }
        return bytes;
    }

    private static BasicFileAttributes secureParent(Path parent) throws IOException {
        BasicFileAttributes attributes = Files.readAttributes(
                parent, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!attributes.isDirectory()
                || attributes.isSymbolicLink()
                || attributes.fileKey() == null) {
            throw new InvalidGuardException();
        }
        Set<PosixFilePermission> permissions = Files.getPosixFilePermissions(
                parent, LinkOption.NOFOLLOW_LINKS);
        if (!permissions.equals(PosixFilePermissions.fromString("rwxr-xr-x"))) {
            throw new InvalidGuardException();
        }
        return attributes;
    }

    private static BasicFileAttributes secureFileAttributes(Path path) throws IOException {
        BasicFileAttributes attributes = Files.readAttributes(
                path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!attributes.isRegularFile()
                || attributes.isSymbolicLink()
                || attributes.fileKey() == null
                || !Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS)
                        .equals(READ_ONLY_FILE)) {
            throw new InvalidGuardException();
        }
        return attributes;
    }

    private static boolean sameIdentity(
            BasicFileAttributes before, BasicFileAttributes after) {
        return Objects.equals(before.fileKey(), after.fileKey())
                && before.size() == after.size()
                && before.lastModifiedTime().equals(after.lastModifiedTime());
    }

    private static String text(Map<String, Object> document, String field) {
        Object value = document.get(field);
        if (!(value instanceof String text) || text.isEmpty()) {
            throw new InvalidGuardException();
        }
        return text;
    }

    private static String sha256(Map<String, Object> document, String field) {
        String value = text(document, field);
        if (!SHA256.matcher(value).matches()) throw new InvalidGuardException();
        return value;
    }

    private static String decimal(Map<String, Object> document, String field) {
        String value = text(document, field);
        if (!DECIMAL.matcher(value).matches()) throw new InvalidGuardException();
        return value;
    }

    private static Instant instant(Map<String, Object> document, String field) {
        try {
            return Instant.parse(text(document, field));
        } catch (DateTimeParseException exception) {
            throw new InvalidGuardException();
        }
    }

    private static void requireNull(Map<String, Object> document, String field) {
        if (document.get(field) != null) throw new InvalidGuardException();
    }

    private static String scopeSha256(String userId, String novelId) {
        if (userId == null
                || novelId == null
                || !SAFE_ID.matcher(userId).matches()
                || !SAFE_ID.matcher(novelId).matches()) {
            throw new InvalidGuardException();
        }
        String canonical = "{\"novelId\":\"" + novelId + "\",\"userId\":\"" + userId + "\"}";
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(canonical.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }

    private static ApiException unavailable() {
        return new ApiException(
                503,
                "DURABLE_AGENT_RELEASE_GUARD_UNAVAILABLE",
                "耐久 Agent 发布保护当前不可用");
    }

    private record GuardDocument(
            String state,
            String lockId,
            String runId,
            String runAttempt,
            String manifestSha256,
            String controlBundleSha256,
            String canaryScopeSha256,
            String executionManifestFingerprint,
            String leaseId,
            Instant issuedAt,
            Instant expiresAt) {}

    private static final class InvalidGuardException extends RuntimeException {}
}
