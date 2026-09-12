package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import cn.inkforge.core.video.application.VideoEpisodeExportManifest;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAsset;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAudioClip;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenSubtitleCue;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenVideoClip;
import cn.inkforge.core.video.application.VideoEpisodeRenderClaim;
import cn.inkforge.core.video.application.VideoEpisodeRenderInput;
import cn.inkforge.core.video.application.VideoAssetStore;
import cn.inkforge.core.video.application.StoredVideoAsset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;

/** 可选的真实媒体回归：覆盖抽帧、双片段拼接、附加音轨和中文字幕烧录。 */
class FfmpegVideoPostProductionMediaProcessorTest {

    @TempDir Path temporary;

    @Test
    void 真实媒体链路能够抽帧并输出带中文字幕音轨的整集视频() throws Exception {
        assumeTrue("true".equalsIgnoreCase(System.getenv("INKFORGE_MEDIA_SMOKE")),
                "设置 INKFORGE_MEDIA_SMOKE=true 才运行真实 FFmpeg smoke");
        Path ffmpeg = FfprobeVideoMediaProbe.findExecutable("ffmpeg", System.getenv("PATH"));
        Path ffprobe = FfprobeVideoMediaProbe.findExecutable("ffprobe", System.getenv("PATH"));
        assumeTrue(ffmpeg != null && ffprobe != null, "当前测试环境未安装媒体工具");

        ObjectMapper json = new ObjectMapper();
        VideoAssetStore storage = new cn.inkforge.core.video.infrastructure.VideoAssetStorage(temporary);
        FfprobeVideoMediaProbe probe = new FfprobeVideoMediaProbe(
                ffprobe, Duration.ofSeconds(30), json);
        FfmpegVideoRenderSimulator simulator = new FfmpegVideoRenderSimulator(
                ffmpeg, temporary.resolve("simulation"), storage, probe, Duration.ofSeconds(30));
        StoredVideoAsset first = simulator.render(claim("source-1", "project-1")).stored();
        StoredVideoAsset second = simulator.render(claim("source-2", "project-1")).stored();
        FfmpegVideoPostProductionMediaProcessor processor =
                new FfmpegVideoPostProductionMediaProcessor(
                        ffmpeg, ffprobe, Duration.ofSeconds(60), json);

        StoredVideoAsset frame = processor.extractFrame(
                first.absolutePath(), first.sha256(), 1_000, storage, "project-1", "frame-1");
        assertThat(Files.size(frame.absolutePath())).isGreaterThan(0);

        FrozenAsset firstAsset = new FrozenAsset(
                "source-1", first.storageKey(), first.sha256(), "video/mp4", 4_000);
        FrozenAsset secondAsset = new FrozenAsset(
                "source-2", second.storageKey(), second.sha256(), "video/mp4", 4_000);
        VideoEpisodeExportManifest manifest = new VideoEpisodeExportManifest(
                VideoEpisodeExportManifest.NATIVE_SCHEMA_VERSION,
                null, "episode-1", "baseline-1", "b".repeat(64), null, null,
                "project-1", "novel-1", null, null, null, null, null, null, null,
                "16:9", "720p", 24, true, 2_000,
                VideoEpisodeExportManifest.FfmpegSettings.productionDefault(),
                List.of(
                        new FrozenVideoClip(1, "shot-1", "take-1", firstAsset,
                                0, 1_000, 1_000, "none", 0),
                        new FrozenVideoClip(2, "shot-2", "take-2", secondAsset,
                                0, 1_000, 1_000, "none", 0)),
                List.of(new FrozenAudioClip(
                        1, "voice", "shot-1", firstAsset, 250, 0, 1_000, 0, 0, 0)),
                List.of(new FrozenSubtitleCue(1, "shot-1", 0, 1_000, "林岚", "你好")));

        StoredVideoAsset exported = processor.renderEpisode(manifest, storage, "export-1");
        assertThat(probe.probeVideoDurationMs(exported.absolutePath()))
                .isBetween(1_900, 2_100);
        assertThat(Files.size(exported.absolutePath())).isGreaterThan(1_000);
    }

    private static VideoEpisodeRenderClaim claim(String taskId, String projectId) {
        VideoEpisodeRenderInput input = new VideoEpisodeRenderInput(
                "video-production-shot-input/1.0", "shot-1", "version-1", 1,
                "a".repeat(64), "scene-1", List.of(), "seedance", "seedance-test",
                "reference", "simulated", false, "prompt-1", "冻结提示词", "16:9", 4,
                "720p", true, false, "mp4", List.of(), List.of(), Map.of());
        return new VideoEpisodeRenderClaim(
                taskId, "episode-1", "baseline-1", projectId, "novel-1", "shot-1",
                "version-1", "submitting", null, 0, "b".repeat(64), input);
    }
}
