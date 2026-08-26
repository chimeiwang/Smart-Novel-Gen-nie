package cn.inkforge.core.video.application;

import java.nio.file.Path;

/** 已通过业务归属和受控存储路径校验的下载文件。 */
public record ResolvedVideoFile(Path path, String mimeType, String filename) {}
