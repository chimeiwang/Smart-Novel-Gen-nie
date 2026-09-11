package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import cn.inkforge.contracts.api.VideoShotRenderManifest;
import cn.inkforge.core.video.application.VideoRenderClaim;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
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
        var manifest = new VideoShotRenderManifest().durationSeconds(4).generateAudio(true)
                .executionMode(VideoShotRenderManifest.ExecutionModeEnum.SIMULATED)
                .ratio(VideoShotRenderManifest.RatioEnum.fromValue("9:16"));
        var result = simulator.render(new VideoRenderClaim("task", "project", "novel", "archiving",
                "simulated-task", 1, "hash", manifest));
        assertThat(result.durationMs()).isBetween(3_950, 4_100);
        assertThat(result.stored().byteSize()).isGreaterThan(1_000);
        assertThat(probe.probeVideoDurationMs(result.stored().absolutePath())).isEqualTo(result.durationMs());
        try (var files = Files.list(working)) { assertThat(files.toList()).isEmpty(); }
    }
}
