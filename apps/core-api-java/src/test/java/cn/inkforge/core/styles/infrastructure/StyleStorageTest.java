package cn.inkforge.core.styles.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.styles.application.StoredStyleFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

class StyleStorageTest {

    @TempDir
    Path root;

    @Test
    void 必须严格UTF8逐字保存并按Python空白语义统计字符() throws Exception {
        StyleStorage storage = new StyleStorage(root);
        String source = " 甲\u00a0乙\r\n😀\u0085 ";

        StoredStyleFile stored = storage.save(
                "style-1",
                "reference-1",
                new MockMultipartFile(
                        "file", "作品.txt", "text/plain", source.getBytes(StandardCharsets.UTF_8)));

        assertThat(Files.readString(stored.absolutePath())).isEqualTo(source);
        assertThat(stored.charCount()).isEqualTo(3);
        assertThat(stored.databasePath())
                .isEqualTo("/app/uploads/styles/style-1/reference-1_作品.txt");
        assertThat(stored.filename()).isEqualTo("作品.txt");
    }

    @Test
    void 文件名必须NFC净化路径控制字符并按UTF8预算保留txt后缀() {
        StyleStorage storage = new StyleStorage(root);
        String filename = "e\u0301\u0000/..\\" + "章".repeat(300) + ".txt";

        StoredStyleFile stored = storage.save(
                "style-1",
                "ref-1",
                new MockMultipartFile(
                        "file", filename, "text/plain", "正文".getBytes(StandardCharsets.UTF_8)));

        assertThat(stored.filename()).startsWith("é__.._章").endsWith(".txt");
        assertThat(stored.absolutePath().getFileName().toString().getBytes(StandardCharsets.UTF_8))
                .hasSizeLessThanOrEqualTo(240);
        assertThat(stored.absolutePath().getParent()).isEqualTo(root.resolve("styles/style-1"));
    }

    @Test
    void 非txt空文件非法编码和排他冲突必须失败且不留半文件() {
        StyleStorage storage = new StyleStorage(root);
        assertCode(
                () -> storage.save(
                        "style-1",
                        "bad-type",
                        new MockMultipartFile("file", "作品.md", "text/plain", "正文".getBytes())),
                "STYLE_REFERENCE_TYPE_INVALID");
        assertCode(
                () -> storage.save(
                        "style-1",
                        "empty",
                        new MockMultipartFile("file", "空.txt", "text/plain", " \r\n".getBytes())),
                "STYLE_REFERENCE_EMPTY");
        assertCode(
                () -> storage.save(
                        "style-1",
                        "encoding",
                        new MockMultipartFile("file", "坏.txt", "text/plain", new byte[] {(byte) 0xC3})),
                "STYLE_REFERENCE_ENCODING_INVALID");
        storage.save(
                "style-1",
                "same",
                new MockMultipartFile("file", "作品.txt", "text/plain", "原文".getBytes()));
        assertCode(
                () -> storage.save(
                        "style-1",
                        "same",
                        new MockMultipartFile("file", "作品.txt", "text/plain", "篡改".getBytes())),
                "STYLE_REFERENCE_FILE_CONFLICT");
        assertThat(root.resolve("styles/style-1/same_作品.txt"))
                .hasContent("原文");
        assertThat(root.resolve("styles/style-1/encoding_坏.txt")).doesNotExist();
    }

    @Test
    void 解析只接受兼容uploads后缀且拒绝穿越NUL和符号链接() throws Exception {
        StyleStorage storage = new StyleStorage(root);
        Path expected = root.resolve("styles/style-1/ref-1_作品.txt");
        assertThat(storage.resolve("C:\\repo\\uploads\\styles\\style-1\\ref-1_作品.txt"))
                .isEqualTo(expected);
        assertThat(storage.resolve("/data/uploads/styles/style-1/ref-1_作品.txt"))
                .isEqualTo(expected);
        for (String invalid : java.util.List.of(
                "../uploads/styles/style-1/../../secret.txt",
                "/etc/passwd",
                "notuploads/styles/style-1/ref.txt",
                "uploads/styles/style-1/a\u0000.txt",
                "uploads/styles/style-1/sub/secret.txt")) {
            assertCode(() -> storage.resolve(invalid), "STYLE_STORAGE_PATH_INVALID");
        }

        Path outside = root.getParent().resolve("outside-" + System.nanoTime());
        Files.createDirectories(outside);
        Files.writeString(outside.resolve("secret.txt"), "secret");
        Files.createDirectories(root.resolve("styles"));
        try {
            Files.createSymbolicLink(root.resolve("styles/style-1"), outside);
            assertCode(
                    () -> storage.resolve("/app/uploads/styles/style-1/secret.txt"),
                    "STYLE_STORAGE_PATH_INVALID");
            assertThat(storage.delete("/app/uploads/styles/style-1/secret.txt")).isFalse();
            assertThat(outside.resolve("secret.txt")).exists();
        } finally {
            Files.deleteIfExists(root.resolve("styles/style-1"));
            Files.deleteIfExists(outside.resolve("secret.txt"));
            Files.deleteIfExists(outside);
        }
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo(code));
    }
}
