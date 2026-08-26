package cn.inkforge.core.platform.id;

import java.security.SecureRandom;
import java.time.Clock;
import java.util.concurrent.atomic.AtomicInteger;

/** 生成与现有 Python/Prisma cuid() 相同的 25 字符 CUID v1 布局。 */
public final class CuidV1Generator {

    private static final char[] BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz".toCharArray();
    private static final int COUNTER_MODULUS = 36 * 36 * 36 * 36;
    private static final long RANDOM_MODULUS = 2_821_109_907_456L; // 36^8

    private final Clock clock;
    private final SecureRandom random = new SecureRandom();
    private final AtomicInteger counter;
    private final int processFingerprint;

    public CuidV1Generator(Clock clock) {
        this.clock = java.util.Objects.requireNonNull(clock);
        this.counter = new AtomicInteger(random.nextInt(COUNTER_MODULUS));
        this.processFingerprint = random.nextInt(COUNTER_MODULUS);
    }

    public String next() {
        int current = counter.getAndUpdate(value -> (value + 1) % COUNTER_MODULUS);
        return "c"
                + base36(clock.millis(), 8)
                + base36(current, 4)
                + base36(processFingerprint, 4)
                + base36(random.nextLong(RANDOM_MODULUS), 8);
    }

    private static String base36(long value, int width) {
        char[] encoded = new char[width];
        long remaining = value;
        for (int index = width - 1; index >= 0; index--) {
            encoded[index] = BASE36[(int) (remaining % 36)];
            remaining /= 36;
        }
        return new String(encoded);
    }
}
