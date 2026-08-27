package cn.inkforge.core.identity.infrastructure;

import cn.inkforge.core.identity.application.PhoneIdentityDigester;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** 用独立密钥摘要手机号和幂等来源，避免低熵手机号被离线枚举。 */
public final class HmacSha256PhoneIdentityDigester implements PhoneIdentityDigester {

    private static final String ALGORITHM = "HmacSHA256";
    private final SecretKeySpec key;

    public HmacSha256PhoneIdentityDigester(String secret) {
        if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
            throw new IllegalArgumentException("手机号认证摘要密钥至少需要 32 个 UTF-8 字节");
        }
        this.key = new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), ALGORITHM);
    }

    @Override
    public String digest(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("手机号认证摘要输入不能为空");
        }
        try {
            Mac mac = Mac.getInstance(ALGORITHM);
            mac.init(key);
            return HexFormat.of().formatHex(
                    mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("JVM 不支持 HMAC-SHA-256", exception);
        }
    }

    @Override
    public String toString() {
        return "HmacSha256PhoneIdentityDigester[key=********]";
    }
}
