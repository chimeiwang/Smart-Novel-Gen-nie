package cn.inkforge.core.styles.infrastructure;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.styles.application.StoredStyleFile;
import cn.inkforge.core.styles.application.StyleFileStorage;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.text.Normalizer;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.web.multipart.MultipartFile;

/** 文风参考资料的受控本地文件边界；数据库永远不接触任意主机路径。 */
public final class StyleStorage implements StyleFileStorage {

    static final long MAX_UPLOAD_BYTES = 50L * 1024 * 1024;
    private static final int COPY_BUFFER_BYTES = 1024 * 1024;
    private static final int MAX_STORAGE_BASENAME_BYTES = 240;
    private static final Pattern ID_PATTERN = Pattern.compile("^[A-Za-z0-9_-]{1,128}$");
    private static final Pattern LEGACY_SUFFIX = Pattern.compile(
            "(?:^|/)uploads/styles/(.+)$", Pattern.CASE_INSENSITIVE);

    private final Path root;

    public StyleStorage(Path root) {
        this.root = java.util.Objects.requireNonNull(root).toAbsolutePath().normalize();
    }

    @Override
    public StoredStyleFile save(
            String styleId, String referenceId, MultipartFile upload) {
        validateId(styleId);
        validateId(referenceId);
        int filenameBudget = MAX_STORAGE_BASENAME_BYTES
                - referenceId.getBytes(StandardCharsets.UTF_8).length
                - 1;
        String filename = sanitizeFilename(upload.getOriginalFilename(), filenameBudget);
        Path parent = root.resolve("styles").resolve(styleId);
        secureDirectories(parent);
        Path target = parent.resolve(referenceId + "_" + filename);
        boolean created = false;
        try {
            rejectSymlinks(parent);
            try (SeekableByteChannel output = Files.newByteChannel(
                            target,
                            Set.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE));
                    InputStream input = upload.getInputStream()) {
                created = true;
                setOwnerOnlyPermissions(target);
                byte[] buffer = new byte[COPY_BUFFER_BYTES];
                long size = 0;
                int read;
                while ((read = input.read(buffer)) != -1) {
                    size += read;
                    if (size > MAX_UPLOAD_BYTES) {
                        throw error(413, "STYLE_REFERENCE_TOO_LARGE", "文件不能超过 50 MiB");
                    }
                    ByteBuffer bytes = ByteBuffer.wrap(buffer, 0, read);
                    while (bytes.hasRemaining()) {
                        int written = output.write(bytes);
                        if (written <= 0) throw new IOException("文件写入未取得进展");
                    }
                }
            }
            int charCount = countStrictUtf8(target);
            if (charCount == 0) {
                throw error(422, "STYLE_REFERENCE_EMPTY", "文件内容不能为空");
            }
            return new StoredStyleFile(
                    filename,
                    target,
                    "/app/uploads/styles/" + styleId + "/" + target.getFileName(),
                    charCount);
        } catch (FileAlreadyExistsException exception) {
            throw error(409, "STYLE_REFERENCE_FILE_CONFLICT", "参考资料文件名冲突");
        } catch (ApiException exception) {
            if (created) safeDeleteCreated(target);
            throw exception;
        } catch (IOException exception) {
            if (created) safeDeleteCreated(target);
            throw new UncheckedIOException("文风文件写入失败", exception);
        } catch (RuntimeException exception) {
            if (created) safeDeleteCreated(target);
            throw exception;
        }
    }

    Path resolve(String databasePath) {
        if (databasePath == null || databasePath.indexOf('\0') >= 0) throw pathError();
        String normalized = databasePath.replace('\\', '/');
        Matcher match = LEGACY_SUFFIX.matcher(normalized);
        if (!match.find()) throw pathError();
        String[] parts = match.group(1).split("/", -1);
        if (parts.length != 2
                || parts[0].isEmpty()
                || parts[1].isEmpty()
                || parts[0].equals(".")
                || parts[0].equals("..")
                || parts[1].equals(".")
                || parts[1].equals("..")) {
            throw pathError();
        }
        validateId(parts[0]);
        if (parts[1].indexOf('/') >= 0 || parts[1].indexOf('\\') >= 0) throw pathError();
        Path candidate = root.resolve("styles").resolve(parts[0]).resolve(parts[1]);
        requireContained(candidate);
        rejectSymlinks(candidate);
        return candidate;
    }

    @Override
    public String read(String databasePath) {
        Path target = resolve(databasePath);
        try {
            return Files.readString(target, StandardCharsets.UTF_8);
        } catch (IOException exception) {
            throw new UncheckedIOException("读取文风参考资料失败", exception);
        }
    }

    @Override
    public boolean delete(String databasePath) {
        try {
            Path target = resolve(databasePath);
            if (!Files.exists(target, LinkOption.NOFOLLOW_LINKS)) return false;
            rejectSymlinks(target);
            Files.deleteIfExists(target);
            return true;
        } catch (ApiException | IOException exception) {
            return false;
        }
    }

    private void secureDirectories(Path target) {
        try {
            Files.createDirectories(root);
            rejectDirectory(root);
            Path current = root;
            Path relative = root.relativize(target);
            for (Path part : relative) {
                current = current.resolve(part);
                try {
                    Files.createDirectory(current);
                } catch (FileAlreadyExistsException ignored) {
                    // 紧接着按 NOFOLLOW 校验，已有符号链接或普通文件都不会被接受。
                }
                rejectDirectory(current);
            }
        } catch (ApiException exception) {
            throw exception;
        } catch (IOException exception) {
            throw new UncheckedIOException("创建文风文件目录失败", exception);
        }
    }

    private static void rejectDirectory(Path value) {
        if (Files.isSymbolicLink(value)
                || !Files.isDirectory(value, LinkOption.NOFOLLOW_LINKS)) {
            throw pathError();
        }
    }

    private void requireContained(Path target) {
        Path normalized = target.toAbsolutePath().normalize();
        if (!normalized.startsWith(root)) throw pathError();
    }

    private void rejectSymlinks(Path target) {
        requireContained(target);
        if (Files.exists(root, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(root)) {
            throw pathError();
        }
        Path current = root;
        for (Path part : root.relativize(target.toAbsolutePath().normalize())) {
            current = current.resolve(part);
            if (Files.isSymbolicLink(current)) throw pathError();
        }
    }

    private static int countStrictUtf8(Path target) {
        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        int count = 0;
        Character pendingHigh = null;
        try (Reader reader = new InputStreamReader(Files.newInputStream(target), decoder)) {
            char[] buffer = new char[8192];
            int read;
            while ((read = reader.read(buffer)) != -1) {
                String text = (pendingHigh == null ? "" : pendingHigh.toString())
                        + new String(buffer, 0, read);
                pendingHigh = null;
                int end = text.length();
                if (end > 0 && Character.isHighSurrogate(text.charAt(end - 1))) {
                    pendingHigh = text.charAt(end - 1);
                    end--;
                }
                for (int index = 0; index < end; ) {
                    int codePoint = text.codePointAt(index);
                    if (!pythonWhitespace(codePoint)) count++;
                    index += Character.charCount(codePoint);
                }
            }
            if (pendingHigh != null) {
                throw error(422, "STYLE_REFERENCE_ENCODING_INVALID", "文件必须使用严格 UTF-8 编码");
            }
            return count;
        } catch (CharacterCodingException exception) {
            throw error(422, "STYLE_REFERENCE_ENCODING_INVALID", "文件必须使用严格 UTF-8 编码");
        } catch (IOException exception) {
            if (exception instanceof CharacterCodingException) {
                throw error(422, "STYLE_REFERENCE_ENCODING_INVALID", "文件必须使用严格 UTF-8 编码");
            }
            throw new UncheckedIOException("读取文风文件失败", exception);
        }
    }

    private static boolean pythonWhitespace(int value) {
        return Character.isWhitespace(value)
                || Character.isSpaceChar(value)
                || value == 0x0085;
    }

    private static String sanitizeFilename(String input, int maxBytes) {
        String normalized = Normalizer.normalize(
                stripPythonWhitespace(input == null ? "" : input),
                Normalizer.Form.NFC);
        StringBuilder cleaned = new StringBuilder();
        normalized.codePoints().forEach(value -> {
            int type = Character.getType(value);
            boolean categoryC = type == Character.CONTROL
                    || type == Character.FORMAT
                    || type == Character.SURROGATE
                    || type == Character.PRIVATE_USE
                    || type == Character.UNASSIGNED;
            cleaned.appendCodePoint(value == '/' || value == '\\' || categoryC ? '_' : value);
        });
        String name = cleaned.toString();
        if (!name.toLowerCase(Locale.ROOT).endsWith(".txt")) {
            throw error(422, "STYLE_REFERENCE_TYPE_INVALID", "只允许上传扩展名为 .txt 的文件");
        }
        String suffix = name.substring(name.length() - 4);
        String stem = name.substring(0, name.length() - 4);
        if (trimFilenamePadding(stem).isEmpty()) {
            throw error(422, "STYLE_REFERENCE_TYPE_INVALID", "只允许上传扩展名为 .txt 的文件");
        }
        int budget = maxBytes - suffix.getBytes(StandardCharsets.UTF_8).length;
        if (budget < 1) throw nameTooLong();
        StringBuilder bounded = new StringBuilder();
        int used = 0;
        for (int index = 0; index < stem.length(); ) {
            int codePoint = stem.codePointAt(index);
            String character = new String(Character.toChars(codePoint));
            int bytes = character.getBytes(StandardCharsets.UTF_8).length;
            if (used + bytes > budget) break;
            bounded.append(character);
            used += bytes;
            index += Character.charCount(codePoint);
        }
        if (trimFilenamePadding(bounded.toString()).isEmpty()) throw nameTooLong();
        return bounded + suffix;
    }

    private static String stripPythonWhitespace(String value) {
        int start = 0;
        int end = value.length();
        while (start < end) {
            int point = value.codePointAt(start);
            if (!pythonWhitespace(point)) break;
            start += Character.charCount(point);
        }
        while (start < end) {
            int point = value.codePointBefore(end);
            if (!pythonWhitespace(point)) break;
            end -= Character.charCount(point);
        }
        return value.substring(start, end);
    }

    private static String trimFilenamePadding(String value) {
        int start = 0;
        int end = value.length();
        while (start < end && padding(value.charAt(start))) start++;
        while (start < end && padding(value.charAt(end - 1))) end--;
        return value.substring(start, end);
    }

    private static boolean padding(char value) {
        return value == ' ' || value == '.' || value == '_';
    }

    private static void validateId(String value) {
        if (value == null || !ID_PATTERN.matcher(value).matches()) throw pathError();
    }

    private static void setOwnerOnlyPermissions(Path target) {
        try {
            Files.setPosixFilePermissions(target, PosixFilePermissions.fromString("rw-------"));
        } catch (UnsupportedOperationException ignored) {
            // 非 POSIX 测试环境没有该能力；生产 Linux 会执行权限收紧。
        } catch (IOException exception) {
            throw new UncheckedIOException("设置文风文件权限失败", exception);
        }
    }

    private static void safeDeleteCreated(Path target) {
        try {
            if (!Files.isSymbolicLink(target)) Files.deleteIfExists(target);
        } catch (IOException ignored) {
            // 写入失败后的清理是尽力动作，原始业务错误必须保留。
        }
    }

    private static ApiException nameTooLong() {
        return error(422, "STYLE_REFERENCE_NAME_TOO_LONG", "参考资料文件名过长");
    }

    private static ApiException pathError() {
        return error(422, "STYLE_STORAGE_PATH_INVALID", "文风文件路径无效");
    }

    private static ApiException error(int status, String code, String message) {
        return new ApiException(status, code, message);
    }
}
