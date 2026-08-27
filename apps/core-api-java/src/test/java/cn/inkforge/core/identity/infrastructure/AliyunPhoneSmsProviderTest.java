package cn.inkforge.core.identity.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.identity.application.PhoneProviderUnavailableException;
import com.aliyun.dypnsapi20170525.models.CheckSmsVerifyCodeRequest;
import com.aliyun.dypnsapi20170525.models.CheckSmsVerifyCodeResponse;
import com.aliyun.dypnsapi20170525.models.CheckSmsVerifyCodeResponseBody;
import com.aliyun.dypnsapi20170525.models.SendSmsVerifyCodeRequest;
import com.aliyun.dypnsapi20170525.models.SendSmsVerifyCodeResponse;
import com.aliyun.dypnsapi20170525.models.SendSmsVerifyCodeResponseBody;
import com.aliyun.teautil.models.RuntimeOptions;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class AliyunPhoneSmsProviderTest {

    @Test
    void 发码必须让阿里云动态生成验证码且禁止SDK自动重试和返回明文验证码() {
        AtomicReference<SendSmsVerifyCodeRequest> captured = new AtomicReference<>();
        AtomicReference<RuntimeOptions> runtime = new AtomicReference<>();
        AliyunPhoneSmsProvider provider = provider(new AliyunPhoneSmsProvider.Gateway() {
            @Override
            public SendSmsVerifyCodeResponse send(
                    SendSmsVerifyCodeRequest request, RuntimeOptions options) {
                captured.set(request);
                runtime.set(options);
                return sendResponse("phone-challenge-00000001", null);
            }

            @Override
            public CheckSmsVerifyCodeResponse check(
                    CheckSmsVerifyCodeRequest request, RuntimeOptions options) {
                throw new AssertionError("不应核验");
            }
        });

        provider.sendVerificationCode("13800138000", "phone-challenge-00000001");

        SendSmsVerifyCodeRequest request = captured.get();
        assertThat(request.getCountryCode()).isEqualTo("86");
        assertThat(request.getPhoneNumber()).isEqualTo("13800138000");
        assertThat(request.getSignName()).isEqualTo("测试签名");
        assertThat(request.getTemplateCode()).isEqualTo("100001");
        assertThat(request.getTemplateParam())
                .isEqualTo(AliyunPhoneSmsProvider.TEMPLATE_PARAMETERS);
        assertThat(request.getCodeLength()).isEqualTo(6L);
        assertThat(request.getValidTime()).isEqualTo(300L);
        assertThat(request.getDuplicatePolicy()).isEqualTo(1L);
        assertThat(request.getInterval()).isEqualTo(60L);
        assertThat(request.getCodeType()).isEqualTo(1L);
        assertThat(request.getReturnVerifyCode()).isFalse();
        assertThat(request.getAutoRetry()).isZero();
        assertThat(request.getSchemeName()).isEqualTo("网页登录");
        assertThat(runtime.get().getAutoretry()).isFalse();
        assertThat(runtime.get().getMaxAttempts()).isEqualTo(1);
    }

    @Test
    void 核验只接受明确PASS而UNKNOWN属于验证码无效() {
        AtomicReference<CheckSmsVerifyCodeRequest> captured = new AtomicReference<>();
        AtomicReference<String> result = new AtomicReference<>("PASS");
        AliyunPhoneSmsProvider provider = provider(new AliyunPhoneSmsProvider.Gateway() {
            @Override
            public SendSmsVerifyCodeResponse send(
                    SendSmsVerifyCodeRequest request, RuntimeOptions options) {
                throw new AssertionError("不应发码");
            }

            @Override
            public CheckSmsVerifyCodeResponse check(
                    CheckSmsVerifyCodeRequest request, RuntimeOptions options) {
                captured.set(request);
                return checkResponse("phone-challenge-00000001", result.get());
            }
        });

        assertThat(provider.verifyCode(
                        "13800138000", "phone-challenge-00000001", "123456"))
                .isTrue();
        result.set("UNKNOWN");
        assertThat(provider.verifyCode(
                        "13800138000", "phone-challenge-00000001", "123456"))
                .isFalse();
        assertThat(captured.get().getOutId()).isEqualTo("phone-challenge-00000001");
        assertThat(captured.get().getSchemeName()).isEqualTo("网页登录");
    }

    @Test
    void 返回验证码正文流水不匹配或供应商异常必须失败关闭() {
        AliyunPhoneSmsProvider leaked = provider(new AliyunPhoneSmsProvider.Gateway() {
            @Override
            public SendSmsVerifyCodeResponse send(
                    SendSmsVerifyCodeRequest request, RuntimeOptions options) {
                return sendResponse("phone-challenge-00000001", "654321");
            }

            @Override
            public CheckSmsVerifyCodeResponse check(
                    CheckSmsVerifyCodeRequest request, RuntimeOptions options) {
                return checkResponse("different-challenge", "PASS");
            }
        });
        assertThatThrownBy(() -> leaked.sendVerificationCode(
                        "13800138000", "phone-challenge-00000001"))
                .isInstanceOf(PhoneProviderUnavailableException.class)
                .hasMessageNotContaining("654321");
        assertThatThrownBy(() -> leaked.verifyCode(
                        "13800138000", "phone-challenge-00000001", "123456"))
                .isInstanceOf(PhoneProviderUnavailableException.class);

        AliyunPhoneSmsProvider unavailable = provider(new AliyunPhoneSmsProvider.Gateway() {
            @Override
            public SendSmsVerifyCodeResponse send(
                    SendSmsVerifyCodeRequest request, RuntimeOptions options) throws Exception {
                throw new Exception("包含敏感供应商上下文");
            }

            @Override
            public CheckSmsVerifyCodeResponse check(
                    CheckSmsVerifyCodeRequest request, RuntimeOptions options) throws Exception {
                throw new Exception("包含敏感供应商上下文");
            }
        });
        assertThatThrownBy(() -> unavailable.sendVerificationCode(
                        "13800138000", "phone-challenge-00000001"))
                .isInstanceOf(PhoneProviderUnavailableException.class)
                .hasMessageNotContaining("敏感供应商上下文");
    }

    private static AliyunPhoneSmsProvider provider(AliyunPhoneSmsProvider.Gateway gateway) {
        return new AliyunPhoneSmsProvider(
                gateway, "测试签名", "100001", "网页登录");
    }

    private static SendSmsVerifyCodeResponse sendResponse(
            String outId, String verifyCode) {
        var model = new SendSmsVerifyCodeResponseBody.SendSmsVerifyCodeResponseBodyModel()
                .setOutId(outId)
                .setVerifyCode(verifyCode)
                .setBizId("biz-id");
        return new SendSmsVerifyCodeResponse()
                .setStatusCode(200)
                .setBody(new SendSmsVerifyCodeResponseBody()
                        .setCode("OK")
                        .setSuccess(true)
                        .setModel(model));
    }

    private static CheckSmsVerifyCodeResponse checkResponse(
            String outId, String verifyResult) {
        var model = new CheckSmsVerifyCodeResponseBody.CheckSmsVerifyCodeResponseBodyModel()
                .setOutId(outId)
                .setVerifyResult(verifyResult);
        return new CheckSmsVerifyCodeResponse()
                .setStatusCode(200)
                .setBody(new CheckSmsVerifyCodeResponseBody()
                        .setCode("OK")
                        .setSuccess(true)
                        .setModel(model));
    }
}
