package cn.inkforge.core.identity.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.identity.application.PhoneProviderUnavailableException;
import com.aliyun.captcha20230305.models.VerifyIntelligentCaptchaRequest;
import com.aliyun.captcha20230305.models.VerifyIntelligentCaptchaResponse;
import com.aliyun.captcha20230305.models.VerifyIntelligentCaptchaResponseBody;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class AliyunPhoneCaptchaVerifierTest {

    @Test
    void 必须原样透传场景与不透明参数并只接受明确成功结果() {
        AtomicReference<VerifyIntelligentCaptchaRequest> captured = new AtomicReference<>();
        AtomicReference<Boolean> verified = new AtomicReference<>(true);
        AliyunPhoneCaptchaVerifier verifier = new AliyunPhoneCaptchaVerifier(
                (request, options) -> {
                    captured.set(request);
                    assertThat(options.getAutoretry()).isFalse();
                    assertThat(options.getMaxAttempts()).isEqualTo(1);
                    return response(verified.get());
                },
                "scene-test-1");

        String opaque = "opaque-captcha-verify-param";
        assertThat(verifier.verify(opaque)).isTrue();
        assertThat(captured.get().getSceneId()).isEqualTo("scene-test-1");
        assertThat(captured.get().getCaptchaVerifyParam()).isEqualTo(opaque);
        verified.set(false);
        assertThat(verifier.verify(opaque)).isFalse();
    }

    @Test
    void 网络故障或畸形响应必须失败关闭且不能泄露底层消息() {
        AliyunPhoneCaptchaVerifier unavailable = new AliyunPhoneCaptchaVerifier(
                (request, options) -> {
                    throw new Exception("底层敏感详情");
                },
                "scene-test-1");
        assertThatThrownBy(() -> unavailable.verify("opaque-param"))
                .isInstanceOf(PhoneProviderUnavailableException.class)
                .hasMessageNotContaining("底层敏感详情");

        AliyunPhoneCaptchaVerifier malformed = new AliyunPhoneCaptchaVerifier(
                (request, options) -> new VerifyIntelligentCaptchaResponse()
                        .setStatusCode(200)
                        .setBody(new VerifyIntelligentCaptchaResponseBody()
                                .setCode("Success")
                                .setSuccess(true)),
                "scene-test-1");
        assertThatThrownBy(() -> malformed.verify("opaque-param"))
                .isInstanceOf(PhoneProviderUnavailableException.class);
    }

    private static VerifyIntelligentCaptchaResponse response(boolean verified) {
        var result = new VerifyIntelligentCaptchaResponseBody
                        .VerifyIntelligentCaptchaResponseBodyResult()
                .setVerifyResult(verified)
                .setVerifyCode(verified ? "T001" : "F001");
        return new VerifyIntelligentCaptchaResponse()
                .setStatusCode(200)
                .setBody(new VerifyIntelligentCaptchaResponseBody()
                        .setCode("Success")
                        .setSuccess(true)
                        .setResult(result));
    }
}
