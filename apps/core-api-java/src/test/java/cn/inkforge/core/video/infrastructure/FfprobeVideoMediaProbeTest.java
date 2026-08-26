package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.video.application.VideoMediaProbeException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;

class FfprobeVideoMediaProbeTest {

    @TempDir
    private Path temporaryDirectory;

    @Test
    void 必须以无shell参数调用并把正有限秒数转换为毫秒() throws Exception {
        Path executable = executable(
                "ffprobe fixture",
                "#!/bin/sh\nprintf '%s' '{\"format\":{\"duration\":\"1.2345\"}}'\n");
        Path media = temporaryDirectory.resolve("带 空格;不会执行.mp4");
        Files.write(media, new byte[] {1});
        FfprobeVideoMediaProbe probe = new FfprobeVideoMediaProbe(
                executable, Duration.ofSeconds(1), new ObjectMapper());

        assertThat(probe.available()).isTrue();
        assertThat(probe.probeDurationMs(media)).isEqualTo(1_235);
    }

    @Test
    void 非零退出畸形输出和非正时长必须拒绝为不可信事实() throws Exception {
        Path media = temporaryDirectory.resolve("asset.mp4");
        Files.write(media, new byte[] {1});

        assertProbeError(executable("failed", "#!/bin/sh\nexit 2\n"), media);
        assertProbeError(executable("malformed", "#!/bin/sh\nprintf 'not-json'\n"), media);
        assertProbeError(
                executable(
                        "negative",
                        "#!/bin/sh\nprintf '%s' '{\"format\":{\"duration\":\"-1\"}}'\n"),
                media);
    }

    @Test
    void 超时必须强制终止而缺少可执行文件必须显式不可用() throws Exception {
        Path media = temporaryDirectory.resolve("asset.mp4");
        Files.write(media, new byte[] {1});
        FfprobeVideoMediaProbe timeout = new FfprobeVideoMediaProbe(
                executable("slow", "#!/bin/sh\nsleep 2\n"),
                Duration.ofMillis(100),
                new ObjectMapper());

        assertThatThrownBy(() -> timeout.probeDurationMs(media))
                .isInstanceOf(VideoMediaProbeException.class)
                .hasMessageContaining("超时");

        FfprobeVideoMediaProbe unavailable = FfprobeVideoMediaProbe.discover(
                "definitely-missing-ffprobe", "", Duration.ofSeconds(1), new ObjectMapper());
        assertThat(unavailable.available()).isFalse();
        assertThatThrownBy(() -> unavailable.probeDurationMs(media))
                .isInstanceOf(VideoMediaProbeException.class)
                .hasMessageContaining("缺少 ffprobe");
    }

    private Path executable(String name, String content) throws Exception {
        Path directory = temporaryDirectory.resolve("工具 目录");
        Files.createDirectories(directory);
        Path executable = directory.resolve(name);
        Files.writeString(executable, content);
        assertThat(executable.toFile().setExecutable(true)).isTrue();
        return executable;
    }

    private static void assertProbeError(Path executable, Path media) {
        FfprobeVideoMediaProbe probe = new FfprobeVideoMediaProbe(
                executable, Duration.ofSeconds(1), new ObjectMapper());
        assertThatThrownBy(() -> probe.probeDurationMs(media))
                .isInstanceOf(VideoMediaProbeException.class);
    }
}
