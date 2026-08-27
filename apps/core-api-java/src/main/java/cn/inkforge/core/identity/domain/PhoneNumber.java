package cn.inkforge.core.identity.domain;

import java.util.Objects;
import java.util.regex.Pattern;

/** 首期只接受中国大陆 11 位手机号，并统一保存为 E.164。 */
public record PhoneNumber(String national, String e164) {

    private static final Pattern MAINLAND = Pattern.compile("^1[3-9][0-9]{9}$");

    public PhoneNumber {
        Objects.requireNonNull(national);
        Objects.requireNonNull(e164);
        if (!MAINLAND.matcher(national).matches() || !("+86" + national).equals(e164)) {
            throw new IllegalArgumentException("手机号格式无效");
        }
    }

    public static PhoneNumber mainland(String value) {
        if (value == null || !MAINLAND.matcher(value).matches()) {
            throw new IllegalArgumentException("手机号格式无效");
        }
        return new PhoneNumber(value, "+86" + value);
    }

    public String masked() {
        return national.substring(0, 3) + "****" + national.substring(7);
    }
}
