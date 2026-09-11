package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.video.application.VideoMediaProbe;
import cn.inkforge.core.video.application.VideoMediaProbeException;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 使用无 shell 的受控 ffprobe 子进程读取音视频时长。 */
public final class FfprobeVideoMediaProbe implements VideoMediaProbe {

    private static final int MAX_TOOL_OUTPUT_BYTES = 1024 * 1024;

    private final Path executable;
    private final Duration timeout;
    private final ObjectMapper json;

    public FfprobeVideoMediaProbe(Path executable, Duration timeout, ObjectMapper json) {
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("媒体探测超时必须为正数");
        }
        this.executable = executable == null ? null : executable.toAbsolutePath().normalize();
        this.timeout = timeout;
        this.json = Objects.requireNonNull(json);
    }

    /** 从显式路径或 PATH 中发现可执行文件；未找到时返回不可用探针。 */
    public static FfprobeVideoMediaProbe discover(
            String executableName,
            String pathEnvironment,
            Duration timeout,
            ObjectMapper json) {
        return new FfprobeVideoMediaProbe(
                findExecutable(executableName, pathEnvironment), timeout, json);
    }

    @Override
    public boolean available() {
        return executable != null
                && Files.isRegularFile(executable)
                && Files.isExecutable(executable);
    }

    @Override
    public int probeDurationMs(Path path) {
        return probe(path, false);
    }

    @Override
    public int probeVideoDurationMs(Path path) {
        return probe(path, true);
    }

    /** 有界执行 ffprobe；可选要求至少存在一帧有效视频画面。 */
    private int probe(Path path, boolean requireVideo) {
        if (!available()) {
            throw new VideoMediaProbeException("当前环境缺少 ffprobe");
        }
        Path media = Objects.requireNonNull(path).toAbsolutePath().normalize();
        Process process;
        try {
            List<String> command = new ArrayList<>(List.of(executable.toString(), "-v", "error"));
            if (requireVideo) command.addAll(List.of("-count_frames", "-select_streams", "v:0"));
            command.addAll(List.of(
                    "-show_entries",
                    requireVideo
                            ? "format=duration:stream=codec_type,width,height,nb_read_frames"
                            : "format=duration",
                    "-of", "json", media.toString()));
            process = new ProcessBuilder(command)
                    .directory(media.getParent().toFile())
                    .start();
            process.getOutputStream().close();
        } catch (IOException exception) {
            throw new VideoMediaProbeException("无法启动 ffprobe", exception);
        }

        // stdout/stderr 必须并行排空，否则子进程可能因管道写满而在 waitFor 前死锁。
        CompletableFuture<byte[]> stdout = readAsync(process.getInputStream());
        CompletableFuture<byte[]> stderr = readAsync(process.getErrorStream());
        try {
            boolean completed = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (!completed) {
                stop(process);
                throw new VideoMediaProbeException("媒体时长探测超时");
            }
            byte[] output = await(stdout);
            byte[] errors = await(stderr);
            if (process.exitValue() != 0 || (requireVideo && errors.length > 0)) {
                throw new VideoMediaProbeException("ffprobe 无法读取媒体时长");
            }
            if (requireVideo) requireVideoFrames(output);
            return durationMs(output);
        } catch (InterruptedException exception) {
            stop(process);
            Thread.currentThread().interrupt();
            throw new VideoMediaProbeException("媒体时长探测被中断", exception);
        } finally {
            if (process.isAlive()) stop(process);
        }
    }

    private void requireVideoFrames(byte[] output) {
        try {
            JsonNode streams = json.readTree(output).path("streams");
            if (!streams.isArray() || streams.size() != 1) {
                throw new VideoMediaProbeException("归档结果没有可读取的视频画面");
            }
            JsonNode video = streams.get(0);
            if (!"video".equals(video.path("codec_type").asString())
                    || video.path("width").asInt() <= 0
                    || video.path("height").asInt() <= 0
                    || Long.parseLong(video.path("nb_read_frames").asString()) <= 0) {
                throw new VideoMediaProbeException("归档结果没有可读取的视频画面");
            }
        } catch (VideoMediaProbeException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new VideoMediaProbeException("归档结果视频探测数据无效", exception);
        }
    }

    private int durationMs(byte[] output) {
        try {
            JsonNode durationNode = json.readTree(output).path("format").path("duration");
            double seconds = Double.parseDouble(durationNode.asString());
            double milliseconds = seconds * 1_000d;
            if (!Double.isFinite(seconds)
                    || seconds <= 0
                    || milliseconds > Integer.MAX_VALUE) {
                throw new VideoMediaProbeException("媒体时长必须是可表示的正有限值");
            }
            return Math.max(1, (int) Math.round(milliseconds));
        } catch (VideoMediaProbeException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new VideoMediaProbeException("ffprobe 没有返回有效媒体时长", exception);
        }
    }

    /** 异步读取并限制工具输出，避免异常媒体导致无界内存占用。 */
    private static CompletableFuture<byte[]> readAsync(InputStream input) {
        return CompletableFuture.supplyAsync(() -> {
            try (input) {
                byte[] value = input.readNBytes(MAX_TOOL_OUTPUT_BYTES + 1);
                if (value.length > MAX_TOOL_OUTPUT_BYTES) {
                    throw new IOException("ffprobe 输出超过安全上限");
                }
                return value;
            } catch (IOException exception) {
                throw new CompletionException(exception);
            }
        });
    }

    private static byte[] await(CompletableFuture<byte[]> output) {
        try {
            return output.join();
        } catch (CompletionException exception) {
            throw new VideoMediaProbeException("读取 ffprobe 输出失败", exception.getCause());
        }
    }

    private static void stop(Process process) {
        process.destroyForcibly();
        try {
            process.waitFor(5, TimeUnit.SECONDS);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    static Path findExecutable(String name, String pathEnvironment) {
        if (name == null || name.isBlank()) return null;
        Path direct = Path.of(name);
        if (direct.getNameCount() > 1 || direct.isAbsolute()) {
            Path candidate = direct.toAbsolutePath().normalize();
            return Files.isRegularFile(candidate) && Files.isExecutable(candidate)
                    ? candidate
                    : null;
        }
        if (pathEnvironment == null || pathEnvironment.isBlank()) return null;
        for (String directory : pathEnvironment.split(java.util.regex.Pattern.quote(File.pathSeparator))) {
            if (directory.isBlank()) continue;
            Path candidate = Path.of(directory).resolve(name).toAbsolutePath().normalize();
            if (Files.isRegularFile(candidate) && Files.isExecutable(candidate)) return candidate;
        }
        return null;
    }
}
