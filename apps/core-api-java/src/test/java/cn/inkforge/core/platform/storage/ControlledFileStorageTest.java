package cn.inkforge.core.platform.storage;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ControlledFileStorageTest {

    @TempDir
    private Path temporaryDirectory;

    @Test
    void 文件必须完整流式保存并返回准确摘要() throws Exception {
        ControlledFileStorage storage = new ControlledFileStorage(temporaryDirectory.resolve("uploads"));
        byte[] content = "完整素材-".repeat(20_000).getBytes(java.nio.charset.StandardCharsets.UTF_8);

        StoredFile stored = storage.store("video-assets", "bin", new ByteArrayInputStream(content), content.length);

        assertThat(stored.size()).isEqualTo(content.length);
        assertThat(stored.sha256())
                .isEqualTo(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content)));
        try (var input = storage.open(stored.relativePath())) {
            assertThat(input.readAllBytes()).isEqualTo(content);
        }
    }

    @Test
    void 超限路径穿越和符号链接必须拒绝且不留下半截文件() throws Exception {
        Path root = temporaryDirectory.resolve("uploads");
        ControlledFileStorage storage = new ControlledFileStorage(root);

        assertThatThrownBy(() -> storage.store(
                        "video-assets", "bin", new ByteArrayInputStream(new byte[11]), 10))
                .isInstanceOf(IOException.class)
                .hasMessageContaining("超过");
        try (var files = Files.list(root.resolve("video-assets"))) {
            assertThat(files.toList()).isEmpty();
        }
        assertThatThrownBy(() -> storage.open("../outside.txt"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("越界");

        Path outside = temporaryDirectory.resolve("outside.txt");
        Files.writeString(outside, "secret");
        Path link = root.resolve("video-assets/link.bin");
        try {
            Files.createSymbolicLink(link, outside);
        } catch (UnsupportedOperationException exception) {
            return;
        }
        assertThatThrownBy(() -> storage.open("video-assets/link.bin"))
                .isInstanceOf(IOException.class)
                .hasMessageContaining("普通文件");
    }
}
