package cn.inkforge.core.identity.infrastructure;

import java.security.SecureRandom;
import java.util.Base64;
import java.util.function.Supplier;

/** 生成不可枚举、可安全放入 URL path 的 192 位手机号挑战标识。 */
public final class SecurePhoneChallengeIdGenerator implements Supplier<String> {

    private final SecureRandom random;

    public SecurePhoneChallengeIdGenerator() {
        this(new SecureRandom());
    }

    SecurePhoneChallengeIdGenerator(SecureRandom random) {
        this.random = java.util.Objects.requireNonNull(random);
    }

    @Override
    public String get() {
        byte[] entropy = new byte[24];
        random.nextBytes(entropy);
        return "ph_" + Base64.getUrlEncoder().withoutPadding().encodeToString(entropy);
    }
}
