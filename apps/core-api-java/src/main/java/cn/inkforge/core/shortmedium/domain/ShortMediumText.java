package cn.inkforge.core.shortmedium.domain;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/** 中短篇完整文本的共享 Unicode 计数和 UTF-8 身份规则。 */
public final class ShortMediumText {

    private ShortMediumText() {}

    public static String sha256(String content) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(content.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JRE 缺少 SHA-256", exception);
        }
    }

    public static int count(String content) {
        return (int) content.codePoints()
                .filter(codePoint -> codePoint != 0xfeff)
                .filter(codePoint -> codePoint != 0x0085)
                .filter(codePoint -> !Character.isWhitespace(codePoint))
                .filter(codePoint -> !Character.isSpaceChar(codePoint))
                .count();
    }

    public static int codePointLength(String content) {
        return content.codePointCount(0, content.length());
    }
}
