package cn.inkforge.core.video.application;

import java.nio.file.Path;

/** 已通过媒体魔数、大小和受控路径校验的完整文件事实。 */
public record StoredVideoAsset(
        String storageKey,
        Path absolutePath,
        String mimeType,
        long byteSize,
        String sha256) {}
