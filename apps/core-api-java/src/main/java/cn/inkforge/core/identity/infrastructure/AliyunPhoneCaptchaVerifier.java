package cn.inkforge.core.identity.infrastructure;

import cn.inkforge.core.identity.application.PhoneCaptchaVerifier;
import cn.inkforge.core.identity.application.PhoneProviderUnavailableException;
import com.aliyun.captcha20230305.models.VerifyIntelligentCaptchaRequest;
import com.aliyun.captcha20230305.models.VerifyIntelligentCaptchaResponse;
import com.aliyun.captcha20230305.models.VerifyIntelligentCaptchaResponseBody;
import com.aliyun.teautil.models.RuntimeOptions;
import java.util.Objects;

/** 阿里云验证码 2.0 服务端验签；网络或业务响应不可信时一律失败关闭。 */
public final class AliyunPhoneCaptchaVerifier implements PhoneCaptchaVerifier {

    private final Gateway gateway;
    private final String sceneId;

    public AliyunPhoneCaptchaVerifier(
            com.aliyun.captcha20230305.Client client, String sceneId) {
        this((request, options) ->
                        client.verifyIntelligentCaptchaWithOptions(request, options),
                sceneId);
    }

    AliyunPhoneCaptchaVerifier(Gateway gateway, String sceneId) {
        this.gateway = Objects.requireNonNull(gateway);
        if (sceneId == null
                || sceneId.isBlank()
                || sceneId.length() > 128
                || sceneId.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("阿里云验证码场景标识格式无效");
        }
        this.sceneId = sceneId.strip();
    }

    @Override
    public boolean verify(String captchaVerifyParam) {
        if (captchaVerifyParam == null
                || captchaVerifyParam.isBlank()
                || captchaVerifyParam.length() > 16_384) {
            return false;
        }
        VerifyIntelligentCaptchaRequest request = new VerifyIntelligentCaptchaRequest()
                .setSceneId(sceneId)
                .setCaptchaVerifyParam(captchaVerifyParam);
        try {
            VerifyIntelligentCaptchaResponse response = gateway.verify(
                    request, runtimeOptions());
            if (response == null
                    || response.getStatusCode() == null
                    || response.getStatusCode() != 200) {
                throw unavailable();
            }
            VerifyIntelligentCaptchaResponseBody body = response.getBody();
            VerifyIntelligentCaptchaResponseBody.VerifyIntelligentCaptchaResponseBodyResult result =
                    body == null ? null : body.getResult();
            if (body == null
                    || !Boolean.TRUE.equals(body.getSuccess())
                    || !"Success".equals(body.getCode())
                    || result == null) {
                throw unavailable();
            }
            return Boolean.TRUE.equals(result.getVerifyResult());
        } catch (PhoneProviderUnavailableException exception) {
            throw exception;
        } catch (Exception exception) {
            throw unavailable();
        }
    }

    private static RuntimeOptions runtimeOptions() {
        return new RuntimeOptions()
                .setAutoretry(false)
                .setMaxAttempts(1)
                .setConnectTimeout(2_000)
                .setReadTimeout(4_000)
                .setIgnoreSSL(false);
    }

    private static PhoneProviderUnavailableException unavailable() {
        return new PhoneProviderUnavailableException();
    }

    @FunctionalInterface
    interface Gateway {

        VerifyIntelligentCaptchaResponse verify(
                VerifyIntelligentCaptchaRequest request, RuntimeOptions options) throws Exception;
    }
}
