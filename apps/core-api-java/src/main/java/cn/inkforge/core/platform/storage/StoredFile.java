package cn.inkforge.core.platform.storage;

public record StoredFile(String relativePath, String sha256, long size) {}
