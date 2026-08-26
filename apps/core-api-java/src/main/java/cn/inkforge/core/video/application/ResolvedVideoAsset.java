package cn.inkforge.core.video.application;

import java.nio.file.Path;

/** 已校验数据库归属且解析到受控存储根目录内的媒体文件。 */
public record ResolvedVideoAsset(Path path, String mimeType, String name) {}
