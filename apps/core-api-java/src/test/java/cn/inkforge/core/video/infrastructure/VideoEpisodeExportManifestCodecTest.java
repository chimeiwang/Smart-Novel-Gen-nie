package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.video.application.VideoEpisodeExportManifest;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAsset;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenAudioClip;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenSubtitleCue;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest.FrozenVideoClip;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class VideoEpisodeExportManifestCodecTest {

    @Test
    void 与Python字段顺序和UTF8哈希完全一致() {
        VideoEpisodeExportManifest manifest = new VideoEpisodeExportManifest(
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
        VideoEpisodeExportManifestCodec codec = new VideoEpisodeExportManifestCodec(
                JsonMapper.builder().findAndAddModules().build());

        assertThat(codec.hash(manifest))
                .isEqualTo("2816564da4260da9c9718b9b25d6eeadd0e165378b8b66ab1ce36d703de33554");
        assertThat(codec.parse(codec.serialize(manifest), codec.hash(manifest)))
                .isEqualTo(manifest);
    }
}
