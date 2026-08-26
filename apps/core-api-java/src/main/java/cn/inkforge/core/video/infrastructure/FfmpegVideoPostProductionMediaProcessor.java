package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.video.application.MediaToolReadiness;
import cn.inkforge.core.video.application.StoredVideoAsset;
import cn.inkforge.core.video.application.VideoAssetStore;
import cn.inkforge.core.video.application.VideoEpisodeExportManifest;
import cn.inkforge.core.video.application.VideoMediaProcessingException;
import cn.inkforge.core.video.application.VideoPostProductionMediaProcessor;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 无 shell、带超时和冻结哈希复核的 FFmpeg/ffprobe 媒体适配器。
 *
 * <p>所有输入先按 manifest 中的 SHA-256 复核，再用参数数组启动子进程；stdout/stderr 有界落入临时文件，
 * 超时强制回收进程。临时目录不承载业务事实，只有结果完整写入受控存储并返回哈希后，调用方才可登记数据库。
 */
final class FfmpegVideoPostProductionMediaProcessor
        implements VideoPostProductionMediaProcessor {

    private static final long MAX_FRAME_BYTES = 30L * 1024 * 1024;
    private static final long MAX_EXPORT_BYTES = 1024L * 1024 * 1024;

    private final Path ffmpeg;
    private final Path ffprobe;
    private final Duration timeout;
    private final ObjectMapper json;

    static FfmpegVideoPostProductionMediaProcessor discover(
            String ffmpegName,
            String ffprobeName,
            String pathEnvironment,
            Duration timeout,
            ObjectMapper json) {
        return new FfmpegVideoPostProductionMediaProcessor(
                findExecutable(ffmpegName, pathEnvironment),
                findExecutable(ffprobeName, pathEnvironment),
                timeout,
                json);
    }

    FfmpegVideoPostProductionMediaProcessor(
            Path ffmpeg, Path ffprobe, Duration timeout, ObjectMapper json) {
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("媒体命令超时必须为正数");
        }
        this.ffmpeg = normalize(ffmpeg);
        this.ffprobe = normalize(ffprobe);
        this.timeout = timeout;
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public MediaToolReadiness readiness() {
        return new MediaToolReadiness(available(ffmpeg), available(ffprobe));
    }

    @Override
    public StoredVideoAsset extractFrame(
            Path sourcePath,
            String expectedSha256,
            int timestampMs,
            VideoAssetStore storage,
            String projectId,
            String assetId) {
        requireReady();
        Path source = Objects.requireNonNull(sourcePath).toAbsolutePath().normalize();
        if (!sha256(source).equals(expectedSha256)) {
            throw new VideoMediaProcessingException(
                    "VIDEO_KEYFRAME_SOURCE_HASH_MISMATCH",
                    "来源 Take 文件与数据库冻结哈希不一致");
        }
        Path temporary = temporary("inkforge-frame-");
        try {
            Path output = temporary.resolve("frame.png");
            run(
                    List.of(
                            ffmpeg.toString(),
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-y",
                            "-ss",
                            VideoEpisodeFfmpegPlan.seconds(timestampMs),
                            "-i",
                            source.toString(),
                            "-frames:v",
                            "1",
                            "-vf",
                            "scale=w='min(2048,iw)':h=-2:flags=lanczos",
                            output.toString()),
                    temporary,
                    "VIDEO_KEYFRAME_EXTRACTION_FAILED");
            if (!Files.isRegularFile(output) || size(output) == 0) {
                throw new VideoMediaProcessingException(
                        "VIDEO_KEYFRAME_EXTRACTION_FAILED",
                        "FFmpeg 未生成关键帧图片");
            }
            try (InputStream input = Files.newInputStream(output)) {
                return storage.saveStream(
                        projectId, assetId, "image", input, MAX_FRAME_BYTES);
            } catch (IOException exception) {
                throw new VideoMediaProcessingException(
                        "VIDEO_KEYFRAME_EXTRACTION_FAILED",
                        "无法读取 FFmpeg 关键帧结果",
                        exception);
            }
        } finally {
            deleteTemporary(temporary);
        }
    }

    @Override
    public StoredVideoAsset renderEpisode(
            VideoEpisodeExportManifest manifest,
            VideoAssetStore storage,
            String assetId) {
        requireReady();
        List<Path> videos = manifest.videoClips().stream()
                .filter(clip -> clip.asset() != null)
                .map(clip -> resolveAndVerify(
                        storage, clip.asset().storageKey(), clip.asset().sha256()))
                .toList();
        List<Path> audio = manifest.audioClips().stream()
                .map(clip -> resolveAndVerify(
                        storage, clip.asset().storageKey(), clip.asset().sha256()))
                .toList();
        if (videos.size() != manifest.videoClips().size()) {
            throw new VideoMediaProcessingException(
                    "VIDEO_EXPORT_PLACEHOLDER_REMAINING",
                    "导出清单仍包含占位镜头");
        }
        List<Boolean> audioStreams = videos.stream().map(this::hasAudioStream).toList();
        var dimensions = VideoEpisodeFfmpegPlan.dimensions(
                manifest.targetAspectRatio(), manifest.resolution());
        Path temporary = temporary("inkforge-export-");
        try {
            Path subtitles = temporary.resolve("subtitles.srt");
            boolean includeSubtitles = manifest.burnSubtitles()
                    && !manifest.subtitleCues().isEmpty();
            if (includeSubtitles) {
                write(subtitles, VideoEpisodeFfmpegPlan.subtitles(manifest));
            }
            Path filter = temporary.resolve("filters.txt");
            write(
                    filter,
                    VideoEpisodeFfmpegPlan.filterGraph(
                            manifest,
                            audioStreams,
                            dimensions.width(),
                            dimensions.height(),
                            includeSubtitles));
            Path output = temporary.resolve("episode.mp4");
            List<String> command = new ArrayList<>(List.of(
                    ffmpeg.toString(), "-hide_banner", "-loglevel", "error", "-y"));
            videos.forEach(path -> {
                command.add("-i");
                command.add(path.toString());
            });
            audio.forEach(path -> {
                command.add("-i");
                command.add(path.toString());
            });
            command.addAll(List.of(
                    "-filter_complex_script",
                    filter.toString(),
                    "-map",
                    "[outv]",
                    "-map",
                    "[outa]",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    "-t",
                    VideoEpisodeFfmpegPlan.seconds(manifest.totalDurationMs()),
                    output.toString()));
            run(command, temporary, "VIDEO_EPISODE_EXPORT_FAILED");
            if (!Files.isRegularFile(output) || size(output) == 0) {
                throw new VideoMediaProcessingException(
                        "VIDEO_EPISODE_EXPORT_FAILED",
                        "FFmpeg 未生成整集视频");
            }
            try (InputStream input = Files.newInputStream(output)) {
                return storage.saveStream(
                        manifest.projectId(), assetId, "video", input, MAX_EXPORT_BYTES);
            } catch (IOException exception) {
                throw new VideoMediaProcessingException(
                        "VIDEO_EPISODE_EXPORT_FAILED",
                        "无法读取 FFmpeg 整集结果",
                        exception);
            }
        } finally {
            deleteTemporary(temporary);
        }
    }

    private Path resolveAndVerify(
            VideoAssetStore storage, String storageKey, String expectedSha256) {
        Path path = storage.resolve(storageKey);
        if (!Files.isRegularFile(path)) {
            throw new VideoMediaProcessingException(
                    "VIDEO_EXPORT_ASSET_MISSING",
                    "导出清单引用的受控素材文件不存在");
        }
        if (!sha256(path).equals(expectedSha256)) {
            throw new VideoMediaProcessingException(
                    "VIDEO_EXPORT_ASSET_HASH_MISMATCH",
                    "导出清单引用的素材文件哈希已经变化");
        }
        return path;
    }

    private boolean hasAudioStream(Path path) {
        String output = run(
                List.of(
                        ffprobe.toString(),
                        "-v",
                        "error",
                        "-select_streams",
                        "a:0",
                        "-show_entries",
                        "stream=index",
                        "-of",
                        "json",
                        path.toString()),
                path.getParent(),
                "VIDEO_EXPORT_PROBE_FAILED");
        try {
            JsonNode streams = json.readTree(output).path("streams");
            return streams.isArray() && !streams.isEmpty();
        } catch (RuntimeException exception) {
            throw new VideoMediaProcessingException(
                    "VIDEO_EXPORT_PROBE_FAILED",
                    "ffprobe 返回了无效结果",
                    exception);
        }
    }

    private String run(List<String> command, Path workingDirectory, String errorCode) {
        Path stdout = workingDirectory.resolve("process-stdout-" + System.nanoTime() + ".log");
        Path stderr = workingDirectory.resolve("process-stderr-" + System.nanoTime() + ".log");
        Process process;
        try {
            process = new ProcessBuilder(command)
                    .directory(workingDirectory.toFile())
                    .redirectOutput(stdout.toFile())
                    .redirectError(stderr.toFile())
                    .start();
            process.getOutputStream().close();
        } catch (IOException exception) {
            throw new VideoMediaProcessingException(
                    errorCode, "无法启动媒体处理进程", exception);
        }
        try {
            if (!process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS)) {
                stop(process);
                throw new VideoMediaProcessingException(
                        errorCode, "媒体处理超时，进程已终止");
            }
            String out = read(stdout, errorCode);
            String error = read(stderr, errorCode).strip();
            if (process.exitValue() != 0) {
                throw new VideoMediaProcessingException(
                        errorCode,
                        error.isEmpty()
                                ? "媒体进程退出码为 " + process.exitValue()
                                : error);
            }
            return out;
        } catch (InterruptedException exception) {
            stop(process);
            Thread.currentThread().interrupt();
            throw new VideoMediaProcessingException(
                    errorCode, "媒体处理被中断", exception);
        } finally {
            if (process.isAlive()) stop(process);
        }
    }

    private void requireReady() {
        if (!readiness().ready()) {
            throw new VideoMediaProcessingException(
                    "VIDEO_MEDIA_TOOLS_UNAVAILABLE",
                    "当前环境缺少 ffmpeg 或 ffprobe");
        }
    }

    private static Path findExecutable(String name, String pathEnvironment) {
        if (name == null || name.isBlank()) return null;
        Path direct = Path.of(name);
        if (direct.getNameCount() > 1 || direct.isAbsolute()) {
            Path candidate = direct.toAbsolutePath().normalize();
            return available(candidate) ? candidate : null;
        }
        if (pathEnvironment == null || pathEnvironment.isBlank()) return null;
        for (String directory : pathEnvironment.split(
                java.util.regex.Pattern.quote(File.pathSeparator))) {
            if (directory.isBlank()) continue;
            Path candidate = Path.of(directory).resolve(name).toAbsolutePath().normalize();
            if (available(candidate)) return candidate;
        }
        return null;
    }

    private static Path normalize(Path value) {
        return value == null ? null : value.toAbsolutePath().normalize();
    }

    private static boolean available(Path value) {
        return value != null && Files.isRegularFile(value) && Files.isExecutable(value);
    }

    private static String sha256(Path path) {
        try (InputStream input = Files.newInputStream(path)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[1024 * 1024];
            int read;
            while ((read = input.read(buffer)) >= 0) {
                if (read > 0) digest.update(buffer, 0, read);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (IOException exception) {
            throw new VideoMediaProcessingException(
                    "VIDEO_EXPORT_ASSET_MISSING",
                    "无法读取受控媒体文件",
                    exception);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }

    private static Path temporary(String prefix) {
        try {
            return Files.createTempDirectory(prefix);
        } catch (IOException exception) {
            throw new VideoMediaProcessingException(
                    "VIDEO_EPISODE_EXPORT_FAILED",
                    "无法创建媒体处理临时目录",
                    exception);
        }
    }

    private static void write(Path path, String value) {
        try {
            Files.writeString(
                    path,
                    value,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);
        } catch (IOException exception) {
            throw new VideoMediaProcessingException(
                    "VIDEO_EPISODE_EXPORT_FAILED",
                    "无法写入媒体处理计划",
                    exception);
        }
    }

    private static String read(Path path, String errorCode) {
        try {
            return Files.exists(path) ? Files.readString(path) : "";
        } catch (IOException exception) {
            throw new VideoMediaProcessingException(
                    errorCode, "无法读取媒体进程输出", exception);
        }
    }

    private static long size(Path path) {
        try {
            return Files.size(path);
        } catch (IOException exception) {
            throw new VideoMediaProcessingException(
                    "VIDEO_EPISODE_EXPORT_FAILED",
                    "无法读取媒体结果大小",
                    exception);
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

    private static void deleteTemporary(Path directory) {
        if (directory == null || !Files.exists(directory)) return;
        try (var paths = Files.walk(directory)) {
            paths.sorted(java.util.Comparator.reverseOrder()).forEach(path -> {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException ignored) {
                    // 临时文件不含业务事实；失败时由操作系统临时目录巡检回收。
                }
            });
        } catch (IOException ignored) {
            // 原媒体处理结果优先，临时目录清理不能覆盖业务异常。
        }
    }
}
