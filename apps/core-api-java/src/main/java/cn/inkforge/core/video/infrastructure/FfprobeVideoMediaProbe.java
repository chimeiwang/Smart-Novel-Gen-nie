package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.video.application.VideoMediaProbe;
import cn.inkforge.core.video.application.VideoMediaProbeException;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
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
        if (!available()) {
            throw new VideoMediaProbeException("当前环境缺少 ffprobe");
        }
        Path media = Objects.requireNonNull(path).toAbsolutePath().normalize();
        Process process;
        try {
            process = new ProcessBuilder(
                            executable.toString(),
                            "-v",
                            "error",
                            "-show_entries",
                            "format=duration",
                            "-of",
                            "json",
                            media.toString())
                    .directory(media.getParent().toFile())
                    .start();
            process.getOutputStream().close();
        } catch (IOException exception) {
            throw new VideoMediaProbeException("无法启动 ffprobe", exception);
        }

        CompletableFuture<byte[]> stdout = readAsync(process.getInputStream());
        CompletableFuture<byte[]> stderr = readAsync(process.getErrorStream());
        try {
            boolean completed = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (!completed) {
                stop(process);
                throw new VideoMediaProbeException("媒体时长探测超时");
            }
            byte[] output = await(stdout);
            await(stderr);
            if (process.exitValue() != 0) {
                throw new VideoMediaProbeException("ffprobe 无法读取媒体时长");
            }
            return durationMs(output);
        } catch (InterruptedException exception) {
            stop(process);
            Thread.currentThread().interrupt();
            throw new VideoMediaProbeException("媒体时长探测被中断", exception);
        } finally {
            if (process.isAlive()) stop(process);
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

    private static Path findExecutable(String name, String pathEnvironment) {
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
