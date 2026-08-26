package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.video.application.VideoEpisodeExportManifest;
import cn.inkforge.core.video.application.VideoMediaProcessingException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** 从冻结清单生成确定性的 FFmpeg filter graph、SRT 和输出尺寸。 */
final class VideoEpisodeFfmpegPlan {

    private VideoEpisodeFfmpegPlan() {}

    static String filterGraph(
            VideoEpisodeExportManifest manifest,
            List<Boolean> audioStreams,
            int width,
            int height,
            boolean includeSubtitles) {
        if (manifest.videoClips().size() != audioStreams.size()) {
            throw new IllegalArgumentException("视频片段与音轨探测结果数量不一致");
        }
        List<String> filters = new ArrayList<>();
        List<String> concatInputs = new ArrayList<>();
        for (int index = 0; index < manifest.videoClips().size(); index++) {
            var clip = manifest.videoClips().get(index);
            if (clip.sourceInMs() == null || clip.sourceOutMs() == null) {
                throw new VideoMediaProcessingException(
                        "VIDEO_EXPORT_PLACEHOLDER_REMAINING",
                        "导出清单包含没有源入出点的镜头");
            }
            double durationSeconds = clip.outputDurationMs() / 1_000d;
            List<String> video = new ArrayList<>(List.of(
                    "trim=start=" + seconds(clip.sourceInMs())
                            + ":end=" + seconds(clip.sourceOutMs()),
                    "setpts=PTS-STARTPTS",
                    "scale=" + width + ":" + height
                            + ":force_original_aspect_ratio=decrease:flags=lanczos",
                    "pad=" + width + ":" + height
                            + ":(ow-iw)/2:(oh-ih)/2:color=black",
                    "fps=" + manifest.framesPerSecond(),
                    "setsar=1",
                    "format=yuv420p"));
            if (index > 0) {
                var previous = manifest.videoClips().get(index - 1);
                if ("fade_black".equals(previous.transitionAfter())) {
                    video.add("fade=t=in:st=0:d="
                            + decimal(previous.transitionDurationMs() / 1_000d));
                }
            }
            if ("fade_black".equals(clip.transitionAfter())) {
                video.add("fade=t=out:st="
                        + decimal(Math.max(
                                durationSeconds - clip.transitionDurationMs() / 1_000d,
                                0))
                        + ":d=" + decimal(clip.transitionDurationMs() / 1_000d));
            }
            filters.add("[" + index + ":v:0]" + String.join(",", video)
                    + "[v" + index + "]");

            List<String> audio = new ArrayList<>(List.of(
                    "atrim=start=" + seconds(clip.sourceInMs())
                            + ":end=" + seconds(clip.sourceOutMs()),
                    "asetpts=PTS-STARTPTS",
                    "aresample=48000",
                    "aformat=sample_fmts=fltp:channel_layouts=stereo"));
            if (index > 0) {
                var previous = manifest.videoClips().get(index - 1);
                if ("fade_black".equals(previous.transitionAfter())) {
                    audio.add("afade=t=in:st=0:d="
                            + decimal(previous.transitionDurationMs() / 1_000d));
                }
            }
            if ("fade_black".equals(clip.transitionAfter())) {
                audio.add("afade=t=out:st="
                        + decimal(Math.max(
                                durationSeconds - clip.transitionDurationMs() / 1_000d,
                                0))
                        + ":d=" + decimal(clip.transitionDurationMs() / 1_000d));
            }
            if (audioStreams.get(index)) {
                filters.add("[" + index + ":a:0]" + String.join(",", audio)
                        + "[a" + index + "]");
            } else {
                List<String> silent = new ArrayList<>(List.of(
                        "anullsrc=r=48000:cl=stereo",
                        "atrim=duration=" + decimal(durationSeconds),
                        "asetpts=PTS-STARTPTS"));
                if (index > 0
                        && "fade_black".equals(
                                manifest.videoClips().get(index - 1).transitionAfter())) {
                    silent.add("afade=t=in:st=0:d="
                            + decimal(manifest.videoClips()
                                            .get(index - 1)
                                            .transitionDurationMs()
                                    / 1_000d));
                }
                filters.add(String.join(",", silent) + "[a" + index + "]");
            }
            concatInputs.add("[v" + index + "]");
            concatInputs.add("[a" + index + "]");
        }
        filters.add(String.join("", concatInputs)
                + "concat=n=" + manifest.videoClips().size()
                + ":v=1:a=1[basev][basea]");
        double totalSeconds = manifest.totalDurationMs() / 1_000d;
        filters.add("[basea]apad,atrim=duration=" + decimal(totalSeconds)
                + ",asetpts=PTS-STARTPTS[baseaudio]");
        List<String> mixInputs = new ArrayList<>(List.of("[baseaudio]"));
        int inputOffset = manifest.videoClips().size();
        for (int index = 0; index < manifest.audioClips().size(); index++) {
            var clip = manifest.audioClips().get(index);
            double duration = (clip.sourceOutMs() - clip.sourceInMs()) / 1_000d;
            List<String> chain = new ArrayList<>(List.of(
                    "atrim=start=" + seconds(clip.sourceInMs())
                            + ":end=" + seconds(clip.sourceOutMs()),
                    "asetpts=PTS-STARTPTS",
                    "aresample=48000",
                    "aformat=sample_fmts=fltp:channel_layouts=stereo",
                    String.format(
                            Locale.ROOT,
                            "volume=%.2fdB",
                            clip.gainMillibels() / 100d)));
            if (clip.fadeInMs() != 0) {
                chain.add("afade=t=in:st=0:d=" + decimal(clip.fadeInMs() / 1_000d));
            }
            if (clip.fadeOutMs() != 0) {
                chain.add("afade=t=out:st="
                        + decimal(Math.max(duration - clip.fadeOutMs() / 1_000d, 0))
                        + ":d=" + decimal(clip.fadeOutMs() / 1_000d));
            }
            chain.add("adelay=" + clip.timelineStartMs() + ":all=1");
            chain.add("apad");
            chain.add("atrim=duration=" + decimal(totalSeconds));
            String label = "extra" + index;
            filters.add("[" + (inputOffset + index) + ":a:0]"
                    + String.join(",", chain) + "[" + label + "]");
            mixInputs.add("[" + label + "]");
        }
        if (mixInputs.size() == 1) {
            filters.add("[baseaudio]anull[outa]");
        } else {
            filters.add(String.join("", mixInputs)
                    + "amix=inputs=" + mixInputs.size()
                    + ":duration=longest:dropout_transition=0:normalize=0,"
                    + "alimiter=limit=0.95[outa]");
        }
        if (includeSubtitles) {
            filters.add("[basev]subtitles=subtitles.srt:charenc=UTF-8:"
                    + "force_style='FontName=Noto Sans CJK SC,FontSize=22,"
                    + "PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,"
                    + "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=42'[outv]");
        } else {
            filters.add("[basev]null[outv]");
        }
        return String.join(";\n", filters);
    }

    static String subtitles(VideoEpisodeExportManifest manifest) {
        List<String> blocks = new ArrayList<>();
        for (int index = 0; index < manifest.subtitleCues().size(); index++) {
            var cue = manifest.subtitleCues().get(index);
            String text = cue.speaker() == null
                    ? cue.text()
                    : cue.speaker() + "：" + cue.text();
            blocks.add((index + 1) + "\n"
                    + srtTime(cue.startMs()) + " --> " + srtTime(cue.endMs())
                    + "\n" + text + "\n");
        }
        return String.join("\n", blocks);
    }

    static Dimensions dimensions(String ratio, String resolution) {
        String[] values = ratio.split(":", -1);
        int left = Integer.parseInt(values[0]);
        int right = Integer.parseInt(values[1]);
        int base = "720p".equals(resolution) ? 720 : 1_080;
        if (left >= right) {
            return new Dimensions(even(round(base * (double) left / right)), base);
        }
        return new Dimensions(base, even(round(base * (double) right / left)));
    }

    static String seconds(int milliseconds) {
        return decimal(milliseconds / 1_000d);
    }

    private static String srtTime(int milliseconds) {
        int hours = milliseconds / 3_600_000;
        int remainder = milliseconds % 3_600_000;
        int minutes = remainder / 60_000;
        remainder %= 60_000;
        int seconds = remainder / 1_000;
        int millis = remainder % 1_000;
        return String.format(
                Locale.ROOT, "%02d:%02d:%02d,%03d", hours, minutes, seconds, millis);
    }

    private static String decimal(double value) {
        return String.format(Locale.ROOT, "%.3f", value);
    }

    private static int round(double value) {
        return BigDecimal.valueOf(value).setScale(0, RoundingMode.HALF_EVEN).intValueExact();
    }

    private static int even(int value) {
        return value % 2 == 0 ? value : value + 1;
    }

    record Dimensions(int width, int height) {}
}
