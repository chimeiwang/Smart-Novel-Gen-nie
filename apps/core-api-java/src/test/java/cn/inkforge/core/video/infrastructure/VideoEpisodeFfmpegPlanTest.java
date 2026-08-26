package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.video.application.VideoEpisodeExportManifest;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAsset;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAudioClip;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenSubtitleCue;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenVideoClip;
import java.util.List;
import org.junit.jupiter.api.Test;

class VideoEpisodeFfmpegPlanTest {

    @Test
    void 固定画幅始终生成偶数像素尺寸() {
        assertThat(VideoEpisodeFfmpegPlan.dimensions("16:9", "720p"))
                .isEqualTo(new VideoEpisodeFfmpegPlan.Dimensions(1_280, 720));
        assertThat(VideoEpisodeFfmpegPlan.dimensions("9:16", "720p"))
                .isEqualTo(new VideoEpisodeFfmpegPlan.Dimensions(720, 1_280));
        assertThat(VideoEpisodeFfmpegPlan.dimensions("21:9", "1080p").width())
                .isEven();
    }

    @Test
    void 无原音轨时补静音并混入外部音轨和烧录字幕() {
        VideoEpisodeExportManifest manifest = manifest();
        String graph = VideoEpisodeFfmpegPlan.filterGraph(
                manifest, List.of(false), 1_280, 720, true);

        assertThat(graph)
                .contains("anullsrc=r=48000:cl=stereo")
                .contains("[1:a:0]")
                .contains("amix=inputs=2")
                .contains("subtitles=subtitles.srt")
                .contains("[outv]")
                .contains("[outa]");
        assertThat(VideoEpisodeFfmpegPlan.subtitles(manifest))
                .isEqualTo("1\n00:00:00,200 --> 00:00:02,500\n林岚：门终于开了\n");
    }

    private static VideoEpisodeExportManifest manifest() {
        return new VideoEpisodeExportManifest(
                VideoEpisodeExportManifest.SCHEMA_VERSION,
                "adaptation",
                "project",
                "novel",
                "episode-plan",
                "shot-plan",
                1,
                "edit",
                "a".repeat(64),
                "mix",
                "b".repeat(64),
                "16:9",
                "720p",
                24,
                true,
                4_000,
                List.of(new FrozenVideoClip(
                        1,
                        "shot",
                        "take",
                        new FrozenAsset(
                                "video",
                                "project/video.mp4",
                                "c".repeat(64),
                                "video/mp4",
                                5_000),
                        500,
                        4_500,
                        4_000,
                        "cut",
                        0)),
                List.of(new FrozenAudioClip(
                        1,
                        "dialogue",
                        "shot",
                        new FrozenAsset(
                                "audio",
                                "project/audio.wav",
                                "d".repeat(64),
                                "audio/wav",
                                4_000),
                        0,
                        0,
                        3_000,
                        0,
                        0,
                        0)),
                List.of(new FrozenSubtitleCue(
                        1, "shot", 200, 2_500, "林岚", "门终于开了")));
    }
}
