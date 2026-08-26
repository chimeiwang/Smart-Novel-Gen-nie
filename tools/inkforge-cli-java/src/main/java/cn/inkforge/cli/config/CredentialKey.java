package cn.inkforge.cli.config;

import cn.inkforge.cli.transport.CoreOrigin;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

record CredentialKey(String service, String account) {

    static CredentialKey of(String profile, String origin) {
        if (profile == null || profile.isEmpty()) {
            throw new IllegalArgumentException("profile 必须是非空字符串");
        }
        String normalized = CoreOrigin.validate(origin);
        return new CredentialKey(
                "InkForge CLI/" + sha256(normalized),
                "inkforge-token:" + profile);
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JRE 缺少 SHA-256", exception);
        }
    }
}
