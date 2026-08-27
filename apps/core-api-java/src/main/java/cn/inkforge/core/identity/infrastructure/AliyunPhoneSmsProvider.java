package cn.inkforge.core.identity.infrastructure;

import cn.inkforge.core.identity.application.PhoneProviderUnavailableException;
import cn.inkforge.core.identity.application.PhoneSmsProvider;
import com.aliyun.dypnsapi20170525.models.CheckSmsVerifyCodeRequest;
import com.aliyun.dypnsapi20170525.models.CheckSmsVerifyCodeResponse;
import com.aliyun.dypnsapi20170525.models.CheckSmsVerifyCodeResponseBody;
import com.aliyun.dypnsapi20170525.models.SendSmsVerifyCodeRequest;
import com.aliyun.dypnsapi20170525.models.SendSmsVerifyCodeResponse;
import com.aliyun.dypnsapi20170525.models.SendSmsVerifyCodeResponseBody;
import com.aliyun.teautil.models.RuntimeOptions;
import java.util.Objects;

/** 阿里云号码认证短信适配器；验证码由供应商生成，Core 永不读取验证码正文。 */
public final class AliyunPhoneSmsProvider implements PhoneSmsProvider {

    static final String TEMPLATE_PARAMETERS = "{\"code\":\"##code##\",\"min\":\"5\"}";
    private static final long CODE_LENGTH = 6L;
    private static final long VALID_SECONDS = 300L;
    private static final long RESEND_INTERVAL_SECONDS = 60L;

    private final Gateway gateway;
    private final String signName;
    private final String templateCode;
    private final String schemeName;

    public AliyunPhoneSmsProvider(
            com.aliyun.dypnsapi20170525.Client client,
            String signName,
            String templateCode,
            String schemeName) {
        this(new Gateway() {
            @Override
            public SendSmsVerifyCodeResponse send(
                    SendSmsVerifyCodeRequest request, RuntimeOptions options) throws Exception {
                return client.sendSmsVerifyCodeWithOptions(request, options);
            }

            @Override
            public CheckSmsVerifyCodeResponse check(
                    CheckSmsVerifyCodeRequest request, RuntimeOptions options) throws Exception {
                return client.checkSmsVerifyCodeWithOptions(request, options);
            }
        }, signName, templateCode, schemeName);
    }

    AliyunPhoneSmsProvider(
            Gateway gateway,
            String signName,
            String templateCode,
            String schemeName) {
        this.gateway = Objects.requireNonNull(gateway);
        this.signName = requireText(signName, "阿里云短信签名", 128);
        this.templateCode = requireText(templateCode, "阿里云短信模板", 64);
        this.schemeName = optionalText(schemeName, "阿里云短信方案名称", 20);
    }

    @Override
    public void sendVerificationCode(String nationalPhone, String challengeId) {
        requirePhone(nationalPhone);
        requireChallengeId(challengeId);
        SendSmsVerifyCodeRequest request = new SendSmsVerifyCodeRequest()
                .setCountryCode("86")
                .setPhoneNumber(nationalPhone)
                .setSignName(signName)
                .setTemplateCode(templateCode)
                .setTemplateParam(TEMPLATE_PARAMETERS)
                .setOutId(challengeId)
                .setCodeLength(CODE_LENGTH)
                .setValidTime(VALID_SECONDS)
                .setDuplicatePolicy(1L)
                .setInterval(RESEND_INTERVAL_SECONDS)
                .setCodeType(1L)
                .setReturnVerifyCode(false)
                .setAutoRetry(0L);
        if (schemeName != null) request.setSchemeName(schemeName);
        try {
            SendSmsVerifyCodeResponse response = gateway.send(request, runtimeOptions());
            if (!validHttp(response == null ? null : response.getStatusCode())) {
                throw unavailable();
            }
            SendSmsVerifyCodeResponseBody body = response.getBody();
            SendSmsVerifyCodeResponseBody.SendSmsVerifyCodeResponseBodyModel model =
                    body == null ? null : body.getModel();
            if (body == null
                    || !Boolean.TRUE.equals(body.getSuccess())
                    || !"OK".equals(body.getCode())
                    || model == null
                    || !challengeId.equals(model.getOutId())
                    || model.getVerifyCode() != null && !model.getVerifyCode().isBlank()) {
                throw unavailable();
            }
        } catch (PhoneProviderUnavailableException exception) {
            throw exception;
        } catch (Exception exception) {
            throw unavailable();
        }
    }

    @Override
    public boolean verifyCode(String nationalPhone, String challengeId, String code) {
        requirePhone(nationalPhone);
        requireChallengeId(challengeId);
        if (code == null || !code.matches("^[0-9]{6}$")) {
            return false;
        }
        CheckSmsVerifyCodeRequest request = new CheckSmsVerifyCodeRequest()
                .setCountryCode("86")
                .setPhoneNumber(nationalPhone)
                .setOutId(challengeId)
                .setVerifyCode(code)
                .setCaseAuthPolicy(1L);
        if (schemeName != null) request.setSchemeName(schemeName);
        try {
            CheckSmsVerifyCodeResponse response = gateway.check(request, runtimeOptions());
            if (!validHttp(response == null ? null : response.getStatusCode())) {
                throw unavailable();
            }
            CheckSmsVerifyCodeResponseBody body = response.getBody();
            CheckSmsVerifyCodeResponseBody.CheckSmsVerifyCodeResponseBodyModel model =
                    body == null ? null : body.getModel();
            if (body == null
                    || !Boolean.TRUE.equals(body.getSuccess())
                    || !"OK".equals(body.getCode())
                    || model == null
                    || !challengeId.equals(model.getOutId())) {
                throw unavailable();
            }
            return "PASS".equals(model.getVerifyResult());
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

    private static boolean validHttp(Integer statusCode) {
        return statusCode != null && statusCode == 200;
    }

    private static void requirePhone(String value) {
        if (value == null || !value.matches("^1[3-9][0-9]{9}$")) {
            throw new IllegalArgumentException("手机号格式无效");
        }
    }

    private static void requireChallengeId(String value) {
        if (value == null || !value.matches("^[A-Za-z0-9_-]{16,64}$")) {
            throw new IllegalArgumentException("手机号挑战标识格式无效");
        }
    }

    private static String requireText(String value, String label, int maximumLength) {
        String normalized = optionalText(value, label, maximumLength);
        if (normalized == null) throw new IllegalArgumentException(label + "不能为空");
        return normalized;
    }

    private static String optionalText(String value, String label, int maximumLength) {
        if (value == null || value.isBlank()) return null;
        String normalized = value.strip();
        if (normalized.length() > maximumLength || normalized.indexOf('\0') >= 0) {
            throw new IllegalArgumentException(label + "格式无效");
        }
        return normalized;
    }

    private static PhoneProviderUnavailableException unavailable() {
        return new PhoneProviderUnavailableException();
    }

    interface Gateway {

        SendSmsVerifyCodeResponse send(
                SendSmsVerifyCodeRequest request, RuntimeOptions options) throws Exception;

        CheckSmsVerifyCodeResponse check(
                CheckSmsVerifyCodeRequest request, RuntimeOptions options) throws Exception;
    }
}
