package cn.inkforge.core.video.application;

import java.nio.file.Path;

/** 把音视频容器转换成可信时长事实的外部媒体工具边界。 */
public interface VideoMediaProbe {

    boolean available();

    int probeDurationMs(Path path);
}
