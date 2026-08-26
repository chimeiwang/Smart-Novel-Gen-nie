package cn.inkforge.cli.transport;

/** 原子写入后的完整文件事实。 */
public record FileDescriptor(String path, long bytes, String sha256, String mediaType) {}
