package cn.inkforge.core.identity.application;

/** 阿里云调用没有得到可信业务结果，调用方必须失败关闭。 */
public final class PhoneProviderUnavailableException extends RuntimeException {

    public PhoneProviderUnavailableException() {
        super("手机号认证供应商暂时不可用");
    }

    public PhoneProviderUnavailableException(Throwable cause) {
        super("手机号认证供应商暂时不可用", cause);
    }
}
