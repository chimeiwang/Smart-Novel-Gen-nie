package cn.inkforge.core.platform.storage;

import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

/** 流式、排他、拒绝符号链接的受控素材存储。 */
public final class ControlledFileStorage {

    private static final Pattern SAFE_SEGMENT = Pattern.compile("[a-z0-9][a-z0-9_-]{0,63}");
    private static final Pattern SAFE_EXTENSION = Pattern.compile("[a-z0-9]{1,12}");
    private static final int BUFFER_SIZE = 64 * 1024;

    private final Path root;

    public ControlledFileStorage(Path root) {
        if (root == null || !root.isAbsolute()) {
            throw new IllegalArgumentException("受控文件根目录必须是绝对路径");
        }
        this.root = root.normalize();
    }

    public StoredFile store(String namespace, String extension, InputStream input, long maximumBytes)
            throws IOException {
        if (!SAFE_SEGMENT.matcher(namespace).matches()
                || !SAFE_EXTENSION.matcher(extension).matches()
                || input == null
                || maximumBytes < 1) {
            throw new IllegalArgumentException("受控文件写入参数无效");
        }
        Path directory = resolve(namespace);
        createSecureDirectory(directory);
        String stem = UUID.randomUUID().toString();
        Path temporary = resolve(namespace + "/." + stem + ".tmp");
        Path destination = resolve(namespace + "/" + stem + "." + extension);
        MessageDigest digest = sha256();
        long size = 0;
        boolean completed = false;
        try (FileChannel output = FileChannel.open(
                temporary,
                Set.of(
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE,
                        LinkOption.NOFOLLOW_LINKS))) {
            byte[] buffer = new byte[BUFFER_SIZE];
            while (true) {
                int read = input.read(buffer);
                if (read < 0) {
                    break;
                }
                if (read == 0) {
                    continue;
                }
                size += read;
                if (size > maximumBytes) {
                    throw new IOException("上传文件超过允许大小");
                }
                digest.update(buffer, 0, read);
                ByteBuffer bytes = ByteBuffer.wrap(buffer, 0, read);
                while (bytes.hasRemaining()) {
                    output.write(bytes);
                }
            }
            output.force(true);
            Files.move(
                    temporary,
                    destination,
                    StandardCopyOption.ATOMIC_MOVE);
            completed = true;
            return new StoredFile(
                    root.relativize(destination).toString().replace(java.io.File.separatorChar, '/'),
                    HexFormat.of().formatHex(digest.digest()),
                    size);
        } finally {
            if (!completed) {
                Files.deleteIfExists(temporary);
            }
        }
    }

    public InputStream open(String relativePath) throws IOException {
        Path path = resolve(relativePath);
        validateExistingParents(path.getParent());
        BasicFileAttributes attributes = Files.readAttributes(
                path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!attributes.isRegularFile() || attributes.isSymbolicLink()) {
            throw new IOException("受控文件不是普通文件");
        }
        Set<OpenOption> options = Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS);
        return Channels.newInputStream(Files.newByteChannel(path, options));
    }

    private void createSecureDirectory(Path directory) throws IOException {
        Files.createDirectories(directory);
        validateExistingParents(directory);
    }

    private void validateExistingParents(Path leaf) throws IOException {
        Path current = root;
        BasicFileAttributes rootAttributes = Files.readAttributes(
                root, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!rootAttributes.isDirectory() || rootAttributes.isSymbolicLink()) {
            throw new IOException("受控文件根目录不安全");
        }
        Path relative = root.relativize(leaf);
        for (Path segment : relative) {
            current = current.resolve(segment);
            BasicFileAttributes attributes = Files.readAttributes(
                    current, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!attributes.isDirectory() || attributes.isSymbolicLink()) {
                throw new IOException("受控文件父目录不安全");
            }
        }
    }

    private Path resolve(String relativePath) {
        if (relativePath == null
                || relativePath.isBlank()
                || relativePath.indexOf('\0') >= 0
                || Path.of(relativePath).isAbsolute()) {
            throw new IllegalArgumentException("受控文件路径无效");
        }
        Path resolved = root.resolve(relativePath).normalize();
        if (!resolved.startsWith(root)) {
            throw new IllegalArgumentException("受控文件路径越界");
        }
        return resolved;
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }
}
