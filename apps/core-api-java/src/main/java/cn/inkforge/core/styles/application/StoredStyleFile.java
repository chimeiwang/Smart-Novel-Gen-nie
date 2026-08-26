package cn.inkforge.core.styles.application;

import java.nio.file.Path;

/** 已通过安全文件边界持久化、尚待写入数据库的文风参考文件。 */
public record StoredStyleFile(
        String filename, Path absolutePath, String databasePath, int charCount) {}
