package cn.inkforge.cli.transport;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/** 在目标目录流式写入、同步并原子替换，失败时精确清理临时文件。 */
public final class AtomicFiles {

    private AtomicFiles() {}

    public static FileDescriptor write(
            Path target, InputStream source, String mediaType) throws IOException {
        Path resolved = target.toAbsolutePath().normalize();
        Path parent = resolved.getParent();
        if (parent == null) throw new IOException("输出文件缺少父目录");
        Files.createDirectories(parent);
        Path temporary = Files.createTempFile(
                parent, "." + resolved.getFileName() + ".", ".tmp");
        long count = 0;
        MessageDigest digest = sha256();
        try {
            try (InputStream input = new BufferedInputStream(source);
                    FileOutputStream file = new FileOutputStream(temporary.toFile());
                    BufferedOutputStream output = new BufferedOutputStream(file)) {
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = input.read(buffer)) >= 0) {
                    if (read == 0) continue;
                    output.write(buffer, 0, read);
                    digest.update(buffer, 0, read);
                    count += read;
                }
                output.flush();
                file.getFD().sync();
            }
            Files.move(
                    temporary,
                    resolved,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
            temporary = null;
            return new FileDescriptor(
                    resolved.toString(),
                    count,
                    HexFormat.of().formatHex(digest.digest()),
                    mediaType);
        } finally {
            if (temporary != null) Files.deleteIfExists(temporary);
        }
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JRE 缺少 SHA-256", exception);
        }
    }
}
