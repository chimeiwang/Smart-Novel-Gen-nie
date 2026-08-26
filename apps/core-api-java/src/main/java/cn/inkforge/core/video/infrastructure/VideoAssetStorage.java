package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.video.application.StoredVideoAsset;
import cn.inkforge.core.video.application.VideoAssetStore;
import java.io.IOException;
import java.io.InputStream;
import java.io.PushbackInputStream;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.web.multipart.MultipartFile;

/** 视频素材专用流式存储；使用稳定业务 ID 定位文件并拒绝路径穿越、覆盖和符号链接。 */
public final class VideoAssetStorage implements VideoAssetStore {

    private static final int SNIFF_BYTES = 12;
    private static final int BUFFER_BYTES = 1024 * 1024;
    private static final long MAX_INTERNAL_STREAM_BYTES = 2L * 1024 * 1024 * 1024;
    private static final Pattern ID = Pattern.compile("[A-Za-z0-9_-]{1,128}");
    private static final Map<String, Long> MAX_BYTES = Map.of(
            "image", 30L * 1024 * 1024,
            "video", 200L * 1024 * 1024,
            "audio", 100L * 1024 * 1024);
    private static final Set<PosixFilePermission> OWNER_ONLY = Set.of(
            PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE);

    private final Path root;

    public VideoAssetStorage(Path uploadsRoot) {
        if (uploadsRoot == null || !uploadsRoot.isAbsolute()) {
            throw new IllegalArgumentException("视频素材根目录必须是绝对路径");
        }
        this.root = uploadsRoot.toAbsolutePath().normalize().resolve("video-assets");
    }

    @Override
    public StoredVideoAsset save(
            String projectId, String assetId, String modality, MultipartFile upload) {
        if (upload == null) throw error(422, "VIDEO_ASSET_EMPTY", "素材文件不能为空");
        try (InputStream input = upload.getInputStream()) {
            return save(projectId, assetId, modality, input, maximum(modality));
        } catch (ApiException exception) {
            throw exception;
        } catch (IOException exception) {
            throw new UncheckedIOException("视频素材读取失败", exception);
        }
    }

    @Override
    public StoredVideoAsset saveStream(
            String projectId,
            String assetId,
            String modality,
            InputStream input,
            long maximumBytes) {
        if (maximumBytes < SNIFF_BYTES || maximumBytes > MAX_INTERNAL_STREAM_BYTES) {
            throw new IllegalArgumentException("内部媒体流大小上限无效");
        }
        return save(projectId, assetId, modality, input, maximumBytes);
    }

    @Override
    public Path resolve(String storageKey) {
        if (storageKey == null
                || storageKey.isBlank()
                || storageKey.indexOf('\0') >= 0
                || storageKey.indexOf('\\') >= 0) {
            throw pathError();
        }
        String[] parts = storageKey.split("/", -1);
        if (parts.length != 2 || !ID.matcher(parts[0]).matches()) throw pathError();
        String filename = parts[1];
        int dot = filename.lastIndexOf('.');
        if (dot < 1
                || !ID.matcher(filename.substring(0, dot)).matches()
                || !Set.of("jpg", "png", "webp", "mp4", "wav", "mp3")
                        .contains(filename.substring(dot + 1))) {
            throw pathError();
        }
        Path target = root.resolve(parts[0]).resolve(filename).normalize();
        requireContained(target);
        rejectSymlinks(target);
        return target;
    }

    @Override
    public boolean delete(String storageKey) {
        try {
            Path target = resolve(storageKey);
            Files.deleteIfExists(target);
            return true;
        } catch (ApiException | IOException exception) {
            return false;
        }
    }

    private StoredVideoAsset save(
            String projectId,
            String assetId,
            String modality,
            InputStream source,
            long maximumBytes) {
        validateId(projectId);
        validateId(assetId);
        if (source == null) throw error(422, "VIDEO_ASSET_EMPTY", "素材文件不能为空");
        maximum(modality);
        Path target = null;
        boolean created = false;
        try (PushbackInputStream input = new PushbackInputStream(source, SNIFF_BYTES)) {
            byte[] prefix = input.readNBytes(SNIFF_BYTES);
            if (prefix.length == 0) throw error(422, "VIDEO_ASSET_EMPTY", "素材文件不能为空");
            input.unread(prefix);
            MediaType media = detect(prefix);
            if (!media.modality().equals(modality)) {
                throw error(422, "VIDEO_ASSET_TYPE_MISMATCH", "素材文件内容与声明模态不一致");
            }
            Path directory = root.resolve(projectId);
            secureDirectories(directory);
            target = directory.resolve(assetId + media.suffix());
            requireContained(target);
            rejectSymlinks(directory);
            MessageDigest digest = sha256();
            long size = 0;
            try (FileChannel output = FileChannel.open(
                    target,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE,
                    LinkOption.NOFOLLOW_LINKS)) {
                created = true;
                setOwnerOnly(target);
                byte[] buffer = new byte[BUFFER_BYTES];
                while (true) {
                    int read = input.read(buffer);
                    if (read < 0) break;
                    if (read == 0) continue;
                    size += read;
                    if (size > maximumBytes) {
                        throw error(
                                413,
                                "VIDEO_ASSET_TOO_LARGE",
                                modality + " 素材超过允许大小");
                    }
                    digest.update(buffer, 0, read);
                    ByteBuffer bytes = ByteBuffer.wrap(buffer, 0, read);
                    while (bytes.hasRemaining()) {
                        if (output.write(bytes) <= 0) {
                            throw new IOException("视频素材写入未取得进展");
                        }
                    }
                }
                output.force(true);
            }
            return new StoredVideoAsset(
                    projectId + "/" + target.getFileName(),
                    target,
                    media.mimeType(),
                    size,
                    HexFormat.of().formatHex(digest.digest()));
        } catch (FileAlreadyExistsException exception) {
            throw error(409, "VIDEO_ASSET_FILE_CONFLICT", "素材文件标识冲突");
        } catch (ApiException exception) {
            if (created) deleteCreated(target);
            throw exception;
        } catch (IOException exception) {
            if (created) deleteCreated(target);
            throw new UncheckedIOException("视频素材写入失败", exception);
        } catch (RuntimeException exception) {
            if (created) deleteCreated(target);
            throw exception;
        }
    }

    private void secureDirectories(Path target) throws IOException {
        Files.createDirectories(root);
        rejectDirectory(root);
        Path current = root;
        for (Path part : root.relativize(target)) {
            current = current.resolve(part);
            try {
                Files.createDirectory(current);
            } catch (FileAlreadyExistsException ignored) {
                // 紧接着按 NOFOLLOW 复核，已有普通文件和符号链接都会被拒绝。
            }
            rejectDirectory(current);
        }
    }

    private static void rejectDirectory(Path path) {
        if (Files.isSymbolicLink(path)
                || !Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
            throw pathError();
        }
    }

    private void rejectSymlinks(Path target) {
        requireContained(target);
        Path current = root;
        if (Files.exists(current, LinkOption.NOFOLLOW_LINKS)
                && Files.isSymbolicLink(current)) {
            throw pathError();
        }
        for (Path part : root.relativize(target.toAbsolutePath().normalize())) {
            current = current.resolve(part);
            if (Files.isSymbolicLink(current)) throw pathError();
        }
    }

    private void requireContained(Path target) {
        if (!target.toAbsolutePath().normalize().startsWith(root)) throw pathError();
    }

    private static void setOwnerOnly(Path target) throws IOException {
        try {
            Files.setPosixFilePermissions(target, OWNER_ONLY);
        } catch (UnsupportedOperationException ignored) {
            // 非 POSIX 测试文件系统仍依赖排他创建与 NOFOLLOW；生产镜像使用 POSIX 文件系统。
        }
    }

    private static void deleteCreated(Path target) {
        if (target == null) return;
        try {
            Files.deleteIfExists(target);
        } catch (IOException ignored) {
            // 原异常优先；残留的不可引用文件由受控存储巡检处理。
        }
    }

    private static long maximum(String modality) {
        Long value = MAX_BYTES.get(modality);
        if (value == null) throw error(422, "VIDEO_ASSET_MODALITY_INVALID", "素材模态无效");
        return value;
    }

    private static void validateId(String value) {
        if (value == null || !ID.matcher(value).matches()) throw pathError();
    }

    private static MediaType detect(byte[] value) {
        if (startsWith(value, new byte[] {(byte) 0xff, (byte) 0xd8, (byte) 0xff})) {
            return new MediaType("image", "image/jpeg", ".jpg");
        }
        if (startsWith(value, new byte[] {
            (byte) 0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'
        })) {
            return new MediaType("image", "image/png", ".png");
        }
        if (value.length >= 12
                && ascii(value, 0, "RIFF")
                && ascii(value, 8, "WEBP")) {
            return new MediaType("image", "image/webp", ".webp");
        }
        if (value.length >= 12 && ascii(value, 4, "ftyp")) {
            return new MediaType("video", "video/mp4", ".mp4");
        }
        if (value.length >= 12
                && ascii(value, 0, "RIFF")
                && ascii(value, 8, "WAVE")) {
            return new MediaType("audio", "audio/wav", ".wav");
        }
        if (ascii(value, 0, "ID3")
                || value.length >= 2
                        && (value[0] & 0xff) == 0xff
                        && ((value[1] & 0xff) & 0xe0) == 0xe0) {
            return new MediaType("audio", "audio/mpeg", ".mp3");
        }
        throw error(
                422,
                "VIDEO_ASSET_FORMAT_UNSUPPORTED",
                "只支持 JPEG、PNG、WebP、MP4/MOV、WAV 和 MP3");
    }

    private static boolean startsWith(byte[] value, byte[] prefix) {
        if (value.length < prefix.length) return false;
        for (int index = 0; index < prefix.length; index++) {
            if (value[index] != prefix[index]) return false;
        }
        return true;
    }

    private static boolean ascii(byte[] value, int offset, String expected) {
        if (value.length < offset + expected.length()) return false;
        for (int index = 0; index < expected.length(); index++) {
            if (value[offset + index] != (byte) expected.charAt(index)) return false;
        }
        return true;
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }

    private static ApiException pathError() {
        return error(422, "VIDEO_STORAGE_PATH_INVALID", "视频素材路径无效");
    }

    private static ApiException error(int status, String code, String message) {
        return new ApiException(status, code, message);
    }

    private record MediaType(String modality, String mimeType, String suffix) {}
}
