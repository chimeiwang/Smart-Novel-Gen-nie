package cn.inkforge.core.identity.application;

/** 服务端复核浏览器产生的阿里云验证码 2.0 不透明参数。 */
public interface PhoneCaptchaVerifier {

    boolean verify(String captchaVerifyParam);
}
