package cn.inkforge.core.video.application;

/** 本机 FFmpeg/ffprobe 可用性；两者同时存在才能抽帧和导出。 */
public record MediaToolReadiness(boolean ffmpegAvailable, boolean ffprobeAvailable) {

    public boolean ready() {
        return ffmpegAvailable && ffprobeAvailable;
    }
}
