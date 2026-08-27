package cn.inkforge.core.identity.application;

/** 对低熵手机号做带密钥摘要，避免手机号进入 Redis key 或挑战正文。 */
public interface PhoneIdentityDigester {

    String digest(String value);
}
