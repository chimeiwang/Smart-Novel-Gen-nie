package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.video.application.StoredVideoAsset;
import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

class VideoAssetStorageTest {

    @TempDir
    private Path temporaryDirectory;

    @Test
    void 图片必须按业务标识完整保存并返回可信文件事实() throws Exception {
        VideoAssetStorage storage = storage();
        byte[] content = png("完整素材".repeat(2_000).getBytes(java.nio.charset.StandardCharsets.UTF_8));

        StoredVideoAsset stored = storage.save(
                "project_1",
                "asset_1",
                "image",
                new MockMultipartFile("file", "伪装扩展名.exe", "application/octet-stream", content));

        assertThat(stored.storageKey()).isEqualTo("project_1/asset_1.png");
        assertThat(stored.mimeType()).isEqualTo("image/png");
        assertThat(stored.byteSize()).isEqualTo(content.length);
        assertThat(stored.sha256())
                .isEqualTo(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content)));
        assertThat(Files.readAllBytes(stored.absolutePath())).isEqualTo(content);
        assertThat(storage.resolve(stored.storageKey())).isEqualTo(stored.absolutePath());
    }

    @Test
    void 声明模态与文件内容不一致时必须拒绝且不创建文件() throws Exception {
        VideoAssetStorage storage = storage();

        assertApiError(
                () -> storage.save(
                        "project_1",
                        "asset_1",
                        "video",
                        new MockMultipartFile("file", "image.png", "image/png", png(new byte[0]))),
                422,
                "VIDEO_ASSET_TYPE_MISMATCH");
        assertThat(Files.exists(temporaryDirectory.resolve("uploads/video-assets/project_1/asset_1.png")))
                .isFalse();
    }

    @Test
    void 空文件和未知魔数必须使用稳定业务错误拒绝() {
        VideoAssetStorage storage = storage();

        assertApiError(
                () -> storage.save(
                        "project_1",
                        "asset_1",
                        "image",
                        new MockMultipartFile("file", new byte[0])),
                422,
                "VIDEO_ASSET_EMPTY");
        assertApiError(
                () -> storage.save(
                        "project_1",
                        "asset_2",
                        "image",
                        new MockMultipartFile("file", "bad.png", "image/png", "not an image".getBytes())),
                422,
                "VIDEO_ASSET_FORMAT_UNSUPPORTED");
    }

    @Test
    void 超限写入必须删除半截文件() throws Exception {
        VideoAssetStorage storage = storage();
        byte[] content = png("payload".getBytes());

        assertApiError(
                () -> storage.saveStream(
                        "project_1",
                        "asset_1",
                        "image",
                        new ByteArrayInputStream(content),
                        12),
                413,
                "VIDEO_ASSET_TOO_LARGE");
        Path directory = temporaryDirectory.resolve("uploads/video-assets/project_1");
        try (var files = Files.list(directory)) {
            assertThat(files.toList()).isEmpty();
        }
    }

    @Test
    void 路径穿越符号链接和覆盖必须被拒绝() throws Exception {
        VideoAssetStorage storage = storage();

        assertApiError(
                () -> storage.resolve("../outside/asset.png"),
                422,
                "VIDEO_STORAGE_PATH_INVALID");
        assertApiError(
                () -> storage.save(
                        "../outside",
                        "asset_1",
                        "image",
                        new MockMultipartFile("file", png(new byte[0]))),
                422,
                "VIDEO_STORAGE_PATH_INVALID");

        byte[] content = png(new byte[0]);
        storage.save(
                "project_1",
                "asset_1",
                "image",
                new MockMultipartFile("file", content));
        assertApiError(
                () -> storage.save(
                        "project_1",
                        "asset_1",
                        "image",
                        new MockMultipartFile("file", content)),
                409,
                "VIDEO_ASSET_FILE_CONFLICT");

        Path outside = temporaryDirectory.resolve("outside");
        Files.createDirectories(outside);
        Path linkedProject = temporaryDirectory.resolve("uploads/video-assets/project_2");
        try {
            Files.createSymbolicLink(linkedProject, outside);
        } catch (UnsupportedOperationException exception) {
            return;
        }
        assertApiError(
                () -> storage.save(
                        "project_2",
                        "asset_2",
                        "image",
                        new MockMultipartFile("file", content)),
                422,
                "VIDEO_STORAGE_PATH_INVALID");
    }

    @Test
    void 删除只允许精确存储键且可幂等调用() {
        VideoAssetStorage storage = storage();
        StoredVideoAsset stored = storage.save(
                "project_1",
                "asset_1",
                "image",
                new MockMultipartFile("file", png(new byte[0])));

        assertThat(storage.delete(stored.storageKey())).isTrue();
        assertThat(Files.exists(stored.absolutePath())).isFalse();
        assertThat(storage.delete(stored.storageKey())).isTrue();
        assertThat(storage.delete("../outside.txt")).isFalse();
    }

    private VideoAssetStorage storage() {
        return new VideoAssetStorage(temporaryDirectory.resolve("uploads").toAbsolutePath());
    }

    private static byte[] png(byte[] payload) {
        byte[] header = new byte[] {(byte) 0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n', 0, 0, 0, 0};
        byte[] value = new byte[header.length + payload.length];
        System.arraycopy(header, 0, value, 0, header.length);
        System.arraycopy(payload, 0, value, header.length, payload.length);
        return value;
    }

    private static void assertApiError(ThrowingCall call, int status, String code) {
        assertThatThrownBy(call::run)
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.statusCode()).isEqualTo(status);
                    assertThat(exception.code()).isEqualTo(code);
                });
    }

    @FunctionalInterface
    private interface ThrowingCall {
        void run() throws Exception;
    }
}
