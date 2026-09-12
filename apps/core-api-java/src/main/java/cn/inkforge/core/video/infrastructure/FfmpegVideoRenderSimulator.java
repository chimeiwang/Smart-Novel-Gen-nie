package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.video.application.ArchivedVideoRender;
import cn.inkforge.core.video.application.VideoAssetStore;
import cn.inkforge.core.video.application.VideoMediaProbe;
import cn.inkforge.core.video.application.VideoEpisodeRenderClaim;
import cn.inkforge.core.video.application.VideoRenderSimulator;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

/** 生成清晰标记为模拟的静态试片；真实请求归档与本实现完全分开。 */
final class FfmpegVideoRenderSimulator implements VideoRenderSimulator {
    private final Path ffmpeg;
    private final Path workingRoot;
    private final VideoAssetStore storage;
    private final VideoMediaProbe probe;
    private final Duration timeout;
    private static final List<String> FONT_CANDIDATES = List.of(
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc");

    FfmpegVideoRenderSimulator(
            Path ffmpeg, Path workingRoot, VideoAssetStore storage, VideoMediaProbe probe, Duration timeout) {
        this.ffmpeg = ffmpeg;
        this.workingRoot = Objects.requireNonNull(workingRoot);
        this.storage = Objects.requireNonNull(storage);
        this.probe = Objects.requireNonNull(probe);
        this.timeout = Objects.requireNonNull(timeout);
    }

    @Override
    public boolean available() {
        return ffmpeg != null && Files.isExecutable(ffmpeg) && probe.available();
    }

    @Override
    public ArchivedVideoRender render(VideoEpisodeRenderClaim claim) {
        return render(new SimulationInput(
                claim.taskId(),
                claim.projectId(),
                claim.input().executionMode(),
                claim.input().ratio(),
                claim.input().durationSeconds(),
                claim.input().generateAudio()));
    }

    private ArchivedVideoRender render(SimulationInput input) {
        if (!available()) throw new IllegalStateException("VIDEO_SIMULATION_MEDIA_TOOLS_UNAVAILABLE");
        if (!"simulated".equals(input.executionMode())) {
            throw new IllegalArgumentException("只有模拟任务可以生成本地试片");
        }
        Path temporary = null;
        Process process = null;
        try {
            Files.createDirectories(workingRoot);
            temporary = Files.createTempDirectory(workingRoot, "simulated-");
            Path output = temporary.resolve("simulated.mp4");
            Path errors = temporary.resolve("ffmpeg-errors.log");
            String ratio = input.ratio();
            var size = VideoEpisodeFfmpegPlan.dimensions("adaptive".equals(ratio) ? "16:9" : ratio, "720p");
            String font = FONT_CANDIDATES.stream().map(Path::of).filter(Files::isRegularFile)
                    .findFirst().map(path -> "fontfile='" + path + "':").orElse("");
            String filter = "drawtext=" + font + "text='模拟视频 · 未调用真实模型':fontcolor=white:fontsize=30:"
                    + "x=(w-text_w)/2:y=(h-text_h)/2";
            List<String> command = new ArrayList<>(List.of(
                    ffmpeg.toString(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=0x193047:s=" + size.width() + "x" + size.height() + ":r=24"));
            if (input.generateAudio()) {
                command.addAll(List.of("-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=48000"));
            }
            command.addAll(List.of("-vf", filter, "-t", Integer.toString(input.durationSeconds()),
                    "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1", "-pix_fmt", "yuv420p"));
            if (input.generateAudio()) {
                command.addAll(List.of("-c:a", "aac", "-b:a", "64k"));
            }
            command.addAll(List.of("-movflags", "+faststart", output.toString()));
            process = new ProcessBuilder(command).directory(temporary.toFile())
                    .redirectOutput(ProcessBuilder.Redirect.DISCARD).redirectError(errors.toFile()).start();
            process.getOutputStream().close();
            if (!process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS)) {
                throw new IllegalStateException("VIDEO_SIMULATION_MEDIA_TIMEOUT");
            }
            if (process.exitValue() != 0) throw new IllegalStateException("VIDEO_SIMULATION_MEDIA_FAILED");
            int durationMs = probe.probeVideoDurationMs(output);
            try (InputStream stream = Files.newInputStream(output)) {
                var stored = storage.saveStream(
                        input.projectId(), input.taskId(), "video", stream, 200L * 1024 * 1024);
                return new ArchivedVideoRender(input.taskId(), stored, durationMs);
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("模拟试片生成被中断", exception);
        } catch (IOException exception) {
            throw new IllegalStateException("模拟试片文件处理失败", exception);
        } finally {
            if (process != null && process.isAlive()) process.destroyForcibly();
            if (temporary != null) {
                try (var files = Files.walk(temporary)) {
                    for (Path file : files.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(file);
                } catch (IOException ignored) {
                    // 文件位于专用模拟工作目录；失败残留不登记为素材，不覆盖原业务异常。
                }
            }
        }
    }

    private record SimulationInput(
            String taskId,
            String projectId,
            String executionMode,
            String ratio,
            int durationSeconds,
            boolean generateAudio) {}
}
