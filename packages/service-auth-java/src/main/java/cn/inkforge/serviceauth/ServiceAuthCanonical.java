package cn.inkforge.serviceauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.regex.Pattern;

final class ServiceAuthCanonical {

    private static final Pattern METHOD = Pattern.compile("[A-Z]{3,16}");

    private ServiceAuthCanonical() {}

    static String method(String value) {
        String method = value == null ? "" : value.strip().toUpperCase();
        if (!METHOD.matcher(method).matches() || !StandardCharsets.US_ASCII.newEncoder().canEncode(method)) {
            throw new IllegalArgumentException("HTTP 方法无效");
        }
        return method;
    }

    static String path(String value) {
        if (value == null
                || !value.startsWith("/")
                || value.length() > 2048
                || value.contains("?")
                || value.contains("#")
                || value.contains("\\")
                || value.contains("%")
                || (value.length() > 1 && value.endsWith("/"))) {
            throw new IllegalArgumentException("HTTP 路径不是规范路径");
        }
        if (!value.equals("/")) {
            for (String segment : value.substring(1).split("/", -1)) {
                if (segment.isEmpty() || segment.equals(".") || segment.equals("..")) {
                    throw new IllegalArgumentException("HTTP 路径不是规范路径");
                }
            }
        }
        for (int index = 0; index < value.length(); index++) {
            int character = value.charAt(index);
            if (character < 0x21 || character == 0x7f) {
                throw new IllegalArgumentException("HTTP 路径不是规范路径");
            }
        }
        return value;
    }

    static String sha256(byte[] value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 不支持 SHA-256", exception);
        }
    }

    static boolean digestEquals(String left, String right) {
        return left != null
                && right != null
                && MessageDigest.isEqual(
                        left.getBytes(StandardCharsets.US_ASCII), right.getBytes(StandardCharsets.US_ASCII));
    }

    static String nonBlank(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + "不能为空");
        }
        return value;
    }
}
