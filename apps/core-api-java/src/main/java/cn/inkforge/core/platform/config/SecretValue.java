package cn.inkforge.core.platform.config;

/** 防止配置对象在日志、调试器常规展开或异常消息中直接泄露密钥。 */
public final class SecretValue {

    private final String value;

    SecretValue(String value) {
        this.value = value;
    }

    public String reveal() {
        return value;
    }

    @Override
    public String toString() {
        return "********";
    }
}
