package cn.inkforge.serviceauth;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.Base64;
import java.util.Set;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

final class ServiceKeyFiles {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final int MAX_KEY_FILE_BYTES = 65_536;

    private ServiceKeyFiles() {}

    static PrivateKey readPrivateKey(Path path) {
        try {
            BasicFileAttributes before = attributes(path);
            validateRegular(before);
            validatePosixPermissions(path);
            byte[] pem = readBoundedWithoutFollowing(path);
            BasicFileAttributes after = attributes(path);
            validateRegular(after);
            if (!java.util.Objects.equals(before.fileKey(), after.fileKey())) {
                throw new IllegalArgumentException();
            }
            String text = new String(pem, java.nio.charset.StandardCharsets.US_ASCII);
            if (!text.startsWith("-----BEGIN PRIVATE KEY-----")) {
                throw new IllegalArgumentException();
            }
            String encoded = text.replace("-----BEGIN PRIVATE KEY-----", "")
                    .replace("-----END PRIVATE KEY-----", "")
                    .replaceAll("\\s", "");
            return KeyFactory.getInstance("Ed25519")
                    .generatePrivate(new PKCS8EncodedKeySpec(Base64.getDecoder().decode(encoded)));
        } catch (Exception exception) {
            throw ServiceAuthException.authentication("无法加载 Ed25519 PKCS8 私钥");
        }
    }

    static JsonNode readJwks(Path path) {
        try {
            BasicFileAttributes attributes = attributes(path);
            validateRegular(attributes);
            return OBJECT_MAPPER.readTree(readBoundedWithoutFollowing(path));
        } catch (Exception exception) {
            throw ServiceAuthException.authentication("无法加载本地 Ed25519 JWKS");
        }
    }

    private static BasicFileAttributes attributes(Path path) throws Exception {
        return Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
    }

    private static void validateRegular(BasicFileAttributes attributes) {
        if (!attributes.isRegularFile() || attributes.isSymbolicLink()) {
            throw new IllegalArgumentException();
        }
    }

    private static void validatePosixPermissions(Path path) throws Exception {
        PosixFileAttributes attributes;
        try {
            attributes = Files.readAttributes(path, PosixFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        } catch (UnsupportedOperationException exception) {
            return;
        }
        Set<PosixFilePermission> forbidden = Set.of(
                PosixFilePermission.GROUP_READ,
                PosixFilePermission.GROUP_WRITE,
                PosixFilePermission.GROUP_EXECUTE,
                PosixFilePermission.OTHERS_READ,
                PosixFilePermission.OTHERS_WRITE,
                PosixFilePermission.OTHERS_EXECUTE);
        if (attributes.permissions().stream().anyMatch(forbidden::contains)
                || !attributes.owner().getName().equals(System.getProperty("user.name"))) {
            throw new IllegalArgumentException();
        }
    }

    private static byte[] readBoundedWithoutFollowing(Path path) throws Exception {
        Set<OpenOption> options = Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS);
        try (SeekableByteChannel channel = Files.newByteChannel(path, options)) {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            ByteBuffer buffer = ByteBuffer.allocate(8192);
            int total = 0;
            while (channel.read(buffer) >= 0) {
                buffer.flip();
                int chunk = buffer.remaining();
                total += chunk;
                if (total > MAX_KEY_FILE_BYTES) {
                    throw new IllegalArgumentException();
                }
                output.write(buffer.array(), 0, chunk);
                buffer.clear();
            }
            return output.toByteArray();
        }
    }
}
