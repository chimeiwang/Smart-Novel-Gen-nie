package cn.inkforge.core.video.application;

import java.nio.file.Path;

/** 把音视频容器转换成可信时长事实的外部媒体工具边界。 */
public interface VideoMediaProbe {

    boolean available();

    int probeDurationMs(Path path);

    /** 仅接受有可读取画面的完整视频，返回实际容器时长。 */
    int probeVideoDurationMs(Path path);
}
