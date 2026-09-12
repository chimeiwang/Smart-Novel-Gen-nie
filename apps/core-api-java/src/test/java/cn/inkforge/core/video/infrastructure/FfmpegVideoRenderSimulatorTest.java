package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import cn.inkforge.core.video.application.VideoEpisodeRenderClaim;
import cn.inkforge.core.video.application.VideoEpisodeRenderInput;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;

class FfmpegVideoRenderSimulatorTest {
    @TempDir Path temporary;

    @Test
    void 模拟生成真实可播放带标记的视频并清理独立工作目录() throws Exception {
        Path ffmpeg = FfprobeVideoMediaProbe.findExecutable("ffmpeg", System.getenv("PATH"));
        var probe = FfprobeVideoMediaProbe.discover("ffprobe", System.getenv("PATH"), Duration.ofSeconds(30), new ObjectMapper());
        assumeTrue(ffmpeg != null && probe.available(), "当前测试环境未安装媒体工具");
        var storage = new VideoAssetStorage(temporary);
        Path working = temporary.resolve("simulation-work");
        var simulator = new FfmpegVideoRenderSimulator(ffmpeg, working, storage, probe, Duration.ofSeconds(30));
        var input = new VideoEpisodeRenderInput(
                "video-production-shot-input/1.0", "shot-1", "shot-version-1", 1,
                "a".repeat(64), "scene-1", List.of(), "seedance", "seedance-test",
                "reference", "simulated", false, "prompt-1", "冻结提示词", "9:16", 4,
                "720p", true, false, "mp4", List.of(), List.of(), Map.of());
        var claim = new VideoEpisodeRenderClaim(
                "task", "episode", "baseline", "project", "novel", "shot-1",
                "shot-version-1", "submitting", null, 0, "b".repeat(64), input);
        var result = simulator.render(claim);
        assertThat(result.durationMs()).isBetween(3_950, 4_100);
        assertThat(result.stored().byteSize()).isGreaterThan(1_000);
        assertThat(probe.probeVideoDurationMs(result.stored().absolutePath())).isEqualTo(result.durationMs());
        try (var files = Files.list(working)) { assertThat(files.toList()).isEmpty(); }
    }
}
